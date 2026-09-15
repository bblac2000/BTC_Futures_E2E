"""layer 2 사이징 — SL 거리 → 레버리지 → 레짐 클램프 → 청산 거리 검사(런타임 MMR + liquidationFee) → 명목 → 수량 → 정규화.

🔴 "v6 공식"의 정확한 의미: v6 §4.4 격리·원웨이 청산가는 `LONG entry×(1−1/L+MMR)`, `SHORT entry×(1+1/L−MMR)` —
   **liquidationFee가 없다.** 사용자 결정(2026-09-15)은 검사에 liquidationFee를 **더한다**. 그래서 속성은
   "SL×buffer + liqFee×entry 가 v6 청산 거리 안에 들어간다"로 쓴다(v6 공식에 fee를 섞어 v6라고 부르지 않는다).
"""
from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from exchange.normalize import RejectReason
from exchange.orders import Direction
from exchange.rules import Bracket
from sizing.config import PERMITTED_LEVERAGE, RegimeSizing
from sizing.position import size_entry

D = Decimal
LONG, SHORT = Direction.LONG, Direction.SHORT


TEN_PCT = D("0.10")


def regime(*, risk_pct: Decimal = TEN_PCT, pos_pct: Decimal = TEN_PCT, l_min: int = 50,
           l_max: int = 100) -> RegimeSizing:
    return RegimeSizing("test", risk_pct, pos_pct, l_min, l_max)


def lev(d) -> int:
    assert d.leverage is not None
    return d.leverage


def mmr(d) -> Decimal:
    assert d.mmr is not None
    return d.mmr


def v6_liq_price(direction: Direction, entry: Decimal, L: int, mmr: Decimal) -> Decimal:
    """v6 §4.4 원문 공식 그대로(liquidationFee 없음)."""
    inv = 1 / D(L)
    return entry * (1 - inv + mmr) if direction is LONG else entry * (1 + inv - mmr)


# ── 설정 검증 ────────────────────────────────────────────────────────────
def test_permitted_leverage_is_the_user_decision():
    assert PERMITTED_LEVERAGE == (50, 100)


@pytest.mark.parametrize("kw", [dict(l_min=49), dict(l_max=101), dict(l_min=80, l_max=60),
                                dict(pos_pct=D("0")), dict(pos_pct=D("1.01")), dict(risk_pct=D("0")),
                                dict(risk_pct=D("1"))])
def test_regime_config_outside_decided_bounds_is_rejected(kw):
    with pytest.raises(ValueError):
        regime(**kw)


def test_buffer_below_one_would_loosen_the_check_and_is_refused(rules):
    with pytest.raises(ValueError):
        size_entry(D("60000"), D("59900"), LONG, D("1000"), regime(), rules, buffer=D("0.99"))


def test_float_inputs_are_refused(rules):
    with pytest.raises(TypeError):
        size_entry(60000.0, D("59900"), LONG, D("1000"), regime(), rules, buffer=D("1"))  # type: ignore[arg-type]


# ── 방향·SL ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(("direction", "sl"), [(LONG, D("60000")), (LONG, D("60100")), (SHORT, D("59900"))])
def test_sl_on_the_wrong_side_is_a_recorded_rejection(rules, direction, sl):
    d = size_entry(D("60000"), sl, direction, D("1000"), regime(), rules, buffer=D("1"))
    assert not d.ok and d.reason is RejectReason.SL_WRONG_SIDE and d.qty == 0


# ── 레버리지 도출 · 클램프 (레짐 라벨 → L 직접 매핑 금지) ──────────────
def test_leverage_inside_the_range_is_floor_of_l_raw_not_a_bound(rules):
    """SL 0.2%·risk 10.5% → L_raw 52.5 → **52**. 경계값(50·100)이 나오면 라벨 매핑이다."""
    d = size_entry(D("60000"), D("59880"), LONG, D("1000"), regime(risk_pct=D("0.105")), rules, buffer=D("1"))
    assert d.ok and d.l_raw == D("52.5") and d.leverage == 52 and d.leverage_start == 52
    assert d.bracket == 1 and d.mmr == D("0.004") and d.liquidation_fee == D("0.012500")


def test_l_raw_below_l_min_clamps_up_and_realized_loss_is_not_the_risk_budget(rules):
    """🔴 미결(설계서 §8) — 클램프가 걸리면 risk_pct는 결과에 들어가지 않는다.
    실제 SL 손실 = qty × |entry−sl| ≈ equity×pos_pct×L×sl_dist ≠ equity×risk_pct. 값을 숨기지 않고 노출한다."""
    d = size_entry(D("60000"), D("59880"), LONG, D("1000"), regime(risk_pct=D("0.01")), rules, buffer=D("1"))
    assert d.ok and d.l_raw == D("5") and d.leverage == 50
    assert d.risk_budget_usdt == D("10.00")
    assert d.loss_at_sl_usdt == d.qty * D("120") and d.loss_at_sl_usdt != d.risk_budget_usdt


def test_100x_is_infeasible_and_leverage_is_lowered_to_the_largest_feasible_integer(rules):
    """fixture: MMR 0.4% + liqFee 1.25% = 1.65%. 100x 청산 거리 = 1% − 1.65% < 0 → 불가능.
    SL 0.10%·buffer 1: 최대 L = floor(1/(0.0165+0.001)) = 57."""
    d = size_entry(D("60000"), D("59940"), LONG, D("1000"), regime(risk_pct=D("0.5")), rules, buffer=D("1"))
    assert d.ok and d.leverage_start == 100 and d.leverage == 57
    assert d.liq_dist_pct is not None and d.liq_dist_pct > d.sl_dist_pct
    #  58은 불가능해야 한다(최대성)
    assert 1 / D(58) - mmr(d) - d.liquidation_fee <= d.sl_dist_pct


@pytest.mark.parametrize(("sl_pct", "expected_l"), [(D("0.0015"), 55), (D("0.0030"), 51)])
def test_feasibility_table_from_fixture_values(rules, sl_pct, expected_l):
    entry = D("60000")
    d = size_entry(entry, entry * (1 - sl_pct), LONG, D("1000"), regime(risk_pct=D("0.9")), rules, buffer=D("1"))
    assert d.ok and d.leverage == expected_l


def test_sl_too_wide_even_at_l_min_is_refused(rules):
    """SL 0.36%: 50x 청산 거리 2% − 1.65% = 0.35% < 0.36% → 거부(레버리지를 50 밑으로 내리지 않는다)."""
    d = size_entry(D("60000"), D("59784"), LONG, D("1000"), regime(), rules, buffer=D("1"))
    assert not d.ok and d.reason is RejectReason.LIQ_DISTANCE and d.qty == 0


def test_buffer_tightens_the_check(rules):
    loose = size_entry(D("60000"), D("59880"), LONG, D("1000"), regime(risk_pct=D("0.9")), rules, buffer=D("1"))
    tight = size_entry(D("60000"), D("59880"), LONG, D("1000"), regime(risk_pct=D("0.9")), rules, buffer=D("1.5"))
    assert loose.ok and tight.ok and lev(tight) < lev(loose)


# ── 브라켓은 명목에서 조회한다 (tier1 가정 금지) ─────────────────────────
def _two_tier(rules, *, tier2_lev: int, tier2_mmr: str, cap: str = "5000"):
    b1 = Bracket(1, 150, D("0"), D(cap), D("0.004"), D("0"))
    b2 = Bracket(2, tier2_lev, D(cap), D("1000000000"), D(tier2_mmr), D("5"))
    return replace(rules, brackets=(b1, b2))


def test_notional_crossing_the_tier_cap_uses_tier2_mmr_and_leverage_cap(rules):
    """equity 1000·pos 10%: L=55면 명목 5500 → tier2(초기 레버리지 52) → L을 낮춰 52 → 명목 5200 여전히 tier2 → tier2 MMR."""
    r2 = _two_tier(rules, tier2_lev=52, tier2_mmr="0.003")
    d = size_entry(D("60000"), D("59910"), LONG, D("1000"), regime(risk_pct=D("0.9")), r2, buffer=D("1"))
    assert d.ok and d.leverage == 52 and d.bracket == 2 and d.mmr == D("0.003")


def test_bracket_leverage_cap_below_l_min_is_refused(rules):
    r2 = _two_tier(rules, tier2_lev=40, tier2_mmr="0.003", cap="4000")      # 50x에서도 명목 5000 → tier2(40x)
    d = size_entry(D("60000"), D("59970"), LONG, D("1000"), regime(risk_pct=D("0.9")), r2, buffer=D("1"))
    assert not d.ok and d.reason is RejectReason.LEVERAGE_INFEASIBLE


# ── 정규화 연결 ──────────────────────────────────────────────────────────
def test_notional_below_min_notional_is_refused_via_normalization(rules):
    d = size_entry(D("60000"), D("59940"), LONG, D("0.5"), regime(), rules, buffer=D("1"))
    assert not d.ok and d.reason in (RejectReason.MIN_NOTIONAL, RejectReason.BELOW_MIN_QTY)


def test_accepted_result_is_on_step_and_internally_consistent(rules):
    d = size_entry(D("61234.5"), D("61298.0"), SHORT, D("1000"), regime(risk_pct=D("0.3")), rules, buffer=D("1.2"))
    s = rules.symbol_rules
    assert d.ok and d.qty % s.market_step == 0 and d.notional == d.qty * D("61234.5")
    assert abs(d.margin * lev(d) - d.notional) < D("1e-18") and sum(d.chunks) == d.qty
    assert d.liq_price_v6 is not None and d.liq_price_v6 > d.sl > d.entry      # SHORT: 진입 < SL < 청산가


# ── 속성 테스트 ──────────────────────────────────────────────────────────
#  ⚠️ 균등한 SL 0.03%~2%로 뽑으면 fixture 규칙에서 **99%가 거부**된다(2만 건 중 수락 206 · L 50~59).
#     그러면 수락 쪽 속성은 사실상 검사되지 않는다. 그래서 두 생성기로 나눈다:
#     ① 수락 가능 구간(SL ≤ 0.34%, buffer ≤ 1.3, **l_min ≤ 55**)에 몰아 수락 속성을 충분히 본다(수락 비율을 테스트가 확인)
#        ⚠️ l_min > ~60인 레짐은 fixture 규칙에서 **어떤 SL로도 수락이 없다**(1/60 − 1.65% ≈ 0.017%) — 설계서 §8 미결
#     ② 넓은 구간(0.03%~2%, buffer ≤ 2)에서 거부 속성을 본다
FEE_CASE = dict(entry=st.decimals(min_value=D("10000"), max_value=D("200000"), places=1),
                long_=st.booleans(),
                equity=st.decimals(min_value=D("50"), max_value=D("5000"), places=2),
                width=st.integers(min_value=0, max_value=50),
                pos_bp=st.integers(min_value=1000, max_value=4000),
                risk_bp=st.integers(min_value=10, max_value=9000))
_seen = {"ok": 0, "total": 0}


def _check(rules, entry, sl_bp, long_, equity, l_min, width, pos_bp, risk_bp, buf_c):
    l_max = min(100, l_min + width)
    direction = LONG if long_ else SHORT
    sl_dist = D(sl_bp) / 10000
    sl = entry * (1 - sl_dist) if long_ else entry * (1 + sl_dist)
    buffer = D(buf_c) / 100
    reg = regime(l_min=l_min, l_max=l_max, pos_pct=D(pos_bp) / 10000, risk_pct=D(risk_bp) / 10000)
    d = size_entry(entry, sl, direction, equity, reg, rules, buffer=buffer)
    fee = rules.symbol_rules.liquidation_fee

    def feasible_at(L: int) -> bool:
        b = rules.bracket_for_notional(equity * reg.pos_pct * L)
        return L <= b.initial_leverage and sl_dist * buffer < 1 / D(L) - b.maint_margin_ratio - fee

    start = max(l_min, min(l_max, math.floor(reg.risk_pct / sl_dist)))
    if d.ok:
        L = lev(d)
        assert l_min <= L <= l_max and L <= start
        liq = v6_liq_price(direction, entry, L, mmr(d))
        assert abs(entry - sl) * buffer + fee * entry < abs(entry - liq), "SL×buffer + liqFee가 v6 청산 거리 안에"
        assert (liq < sl < entry) if long_ else (entry < sl < liq)
        if L < start:
            assert not feasible_at(L + 1), "더 높은 가능한 L을 버리지 않는다(최대성)"
        assert feasible_at(L)
        assert d.notional >= rules.symbol_rules.min_notional and d.qty % rules.symbol_rules.market_step == 0
        assert d.loss_at_sl_usdt == d.qty * abs(entry - sl)
    elif d.reason is RejectReason.LIQ_DISTANCE:
        assert not any(feasible_at(L) for L in range(l_min, start + 1))
    else:
        assert d.reason in (RejectReason.MIN_NOTIONAL, RejectReason.BELOW_MIN_QTY, RejectReason.LEVERAGE_INFEASIBLE)
    return d


@settings(max_examples=400, deadline=None)
@given(sl_bp=st.integers(min_value=3, max_value=34), buf_c=st.integers(min_value=100, max_value=130),
       l_min=st.integers(min_value=50, max_value=55), **FEE_CASE)
def test_property_accepted_sizes_keep_sl_plus_fee_inside_the_v6_liquidation_distance(rules, **kw):
    d = _check(rules, **kw)
    _seen["total"] += 1
    _seen["ok"] += int(d.ok)


def test_the_accept_side_property_actually_saw_accepted_sizes():
    """위 속성 테스트가 수락 사례를 **실제로** 충분히 검사했는지 — 대부분 거부면 속성이 공허하게 통과한다."""
    if _seen["total"] == 0:
        pytest.skip("속성 테스트가 이 실행에서 돌지 않았다(단독 실행)")
    assert _seen["ok"] / _seen["total"] >= 0.3, _seen


@settings(max_examples=300, deadline=None)
@given(sl_bp=st.integers(min_value=3, max_value=200), buf_c=st.integers(min_value=100, max_value=200),
       l_min=st.integers(min_value=50, max_value=100), **FEE_CASE)
def test_property_wide_range_rejections_are_correct(rules, **kw):
    _check(rules, **kw)
