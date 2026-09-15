"""layer 2 사이징 — 레지스트리 #2(2026-09-15 사용자 결정 B1·B2)가 규칙이다.

B1 청산 거리 = 거래소 공식(v6 §4.4): `liq_dist(L) = 1/L − MMR_eff`, `MMR_eff = MMR_bracket − cumB/notional`.
   liquidationFee는 **거리에 들어가지 않는다**(청산 뒤 남은 격리 마진에서 부과) → "청산 손실 = 마진 전액 + fee"로만 모델링.
   게이트: `sl_dist × buffer < liq_dist(L)`.
B2 위험 예산이 1차 제약이다: budget = equity×risk_pct → notional_target = budget/sl_dist → 구간 안 최고 정수 L(브라켓+청산 검사)
   → margin = notional/L → pos_pct 도출. pos_pct_max(40%) 초과면 명목을 줄인다(손실은 예산 아래로 — 허용).
   pos_pct_min(10%)은 **권고만**(기록, 부풀리지 않음). 최종 qty 내림 후 loss_at_sl > budget×(1+tol)이면 거부.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from exchange.normalize import RejectReason
from exchange.orders import Direction
from exchange.rules import Bracket
from sizing import position as P
from sizing.config import PERMITTED_LEVERAGE, RegimeSizing, SizingLimits
from sizing.position import size_entry

D = Decimal
LONG, SHORT = Direction.LONG, Direction.SHORT
ONE = D("1")
PCT1 = D("0.01")


def regime(*, risk_pct: Decimal = PCT1, l_min: int = 50, l_max: int = 100) -> RegimeSizing:
    return RegimeSizing("test", risk_pct, l_min, l_max)


def limits(buffer: Decimal = ONE, **kw) -> SizingLimits:
    return SizingLimits(buffer=buffer, **kw)


def lev(d) -> int:
    assert d.leverage is not None
    return d.leverage


def mmr_eff_for(rules, notional: Decimal) -> tuple[Bracket, Decimal]:
    b = rules.bracket_for_notional(notional)
    return b, b.maint_margin_ratio - b.cum / notional


# ── 설정 ────────────────────────────────────────────────────────────────
def test_decided_constants():
    assert PERMITTED_LEVERAGE == (50, 100)
    lim = limits()
    assert (lim.pos_pct_max, lim.pos_pct_min, lim.loss_tolerance) == (D("0.40"), D("0.10"), D("0"))


@pytest.mark.parametrize("kw", [dict(l_min=49), dict(l_max=101), dict(l_min=80, l_max=60),
                                dict(risk_pct=D("0")), dict(risk_pct=D("1"))])
def test_regime_config_outside_decided_bounds_is_rejected(kw):
    with pytest.raises(ValueError):
        regime(**kw)


@pytest.mark.parametrize("kw", [dict(buffer=D("0.99")), dict(pos_pct_max=D("1.01")), dict(pos_pct_max=D("0")),
                                dict(pos_pct_min=D("0.5"), pos_pct_max=D("0.4")), dict(loss_tolerance=D("-0.01"))])
def test_limits_validation(kw):
    with pytest.raises(ValueError):
        SizingLimits(**({"buffer": ONE} | kw))


def test_buffer_is_required_no_silent_default():
    with pytest.raises(TypeError):
        SizingLimits()  # type: ignore[call-arg]


def test_float_inputs_are_refused(rules):
    with pytest.raises(TypeError):
        size_entry(60000.0, D("59700"), LONG, D("1000"), regime(), rules, limits())  # type: ignore[arg-type]


@pytest.mark.parametrize(("direction", "sl"), [(LONG, D("60000")), (LONG, D("60100")), (SHORT, D("59900"))])
def test_sl_on_the_wrong_side_is_a_recorded_rejection(rules, direction, sl):
    d = size_entry(D("60000"), sl, direction, D("1000"), regime(), rules, limits())
    assert not d.ok and d.reason is RejectReason.SL_WRONG_SIDE and d.qty == 0


# ── B1: 거래소 공식 청산 거리 (fee 없음) ────────────────────────────────
def test_100x_is_accepted_for_sl_below_0_6_percent_on_tier1(rules):
    """tier1 MMR 0.4%·cum 0 → liq_dist(100) = 1% − 0.4% = 0.6%. SL 0.5% < 0.6% → 100x."""
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits())
    assert d.ok and lev(d) == 100 and d.bracket == 1
    assert d.mmr_eff == D("0.004") and d.liq_dist_pct == D("0.006")


def test_sl_exactly_at_liq_distance_is_not_accepted_at_that_leverage(rules):
    """SL 0.6% = liq_dist(100) → 100x 불가(엄격 <) → 99x(1/99 − 0.4% ≈ 0.6101%)."""
    d = size_entry(D("60000"), D("59640"), LONG, D("1000"), regime(), rules, limits())
    assert d.ok and lev(d) == 99


def test_refused_when_sl_times_buffer_reaches_liq_distance_even_at_l_min(rules):
    """SL 1.7%: liq_dist(50) = 2% − 0.4% = 1.6% ≤ 1.7% → 거부(50 밑으로 내리지 않는다)."""
    d = size_entry(D("60000"), D("58980"), LONG, D("1000"), regime(), rules, limits())
    assert not d.ok and d.reason is RejectReason.LIQ_DISTANCE and d.qty == 0


def test_buffer_tightens_the_gate(rules):
    """SL 0.5%·buffer 1.25 → 0.625% 필요 → 1/L > 1.025% → L = 97."""
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits(buffer=D("1.25")))
    assert d.ok and lev(d) == 97


def test_liquidation_fee_is_not_in_the_distance_but_in_the_liquidation_loss(rules):
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits())
    fee = rules.symbol_rules.liquidation_fee
    assert d.mmr_eff is not None
    assert d.liq_dist_pct == 1 / D(100) - d.mmr_eff, "거리에 fee 항이 없다"
    assert d.loss_at_liquidation_usdt == d.margin + d.notional * fee


def test_mmr_eff_subtracts_bracket_cum_over_notional(rules):
    """fixture tier2: MMR 0.5%·cum 300. 명목 600,000 → MMR_eff = 0.5% − 300/600,000 = 0.45%."""
    d = size_entry(D("60000"), D("59940"), LONG, D("20000"), regime(risk_pct=D("0.03")), rules, limits())
    assert d.ok and d.bracket == 2 and d.cum == D("300")
    assert d.notional == D("600000") and d.mmr_eff == D("0.0045")
    assert d.liq_dist_pct == D("0.0055") and lev(d) == 100


def test_liq_price_estimate_uses_mmr_eff_and_brackets_sl(rules):
    d = size_entry(D("61234.5"), D("61540.6725"), SHORT, D("1000"), regime(), rules, limits(buffer=D("1.2")))
    assert d.ok and d.liq_price_est is not None and d.mmr_eff is not None
    assert abs(d.liq_price_est - d.entry * (1 + 1 / D(lev(d)) - d.mmr_eff)) < D("1e-20")
    assert d.liq_price_est > d.sl > d.entry


# ── B2: 위험 예산이 1차 제약 ───────────────────────────────────────────
def test_notional_comes_from_risk_budget_and_pos_pct_is_derived(rules):
    """equity 1000·risk 1%·SL 0.5% → budget 10 → 목표 명목 2,000 → 100x → qty 0.033 → 명목 1,980 → 마진 19.8."""
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits())
    assert d.risk_budget_usdt == D("10") and d.notional_target == D("2000")
    assert d.qty == D("0.033") and d.notional == D("1980") and d.margin == D("19.8")
    assert d.pos_pct == D("0.0198") and d.loss_at_sl_usdt == D("9.9") and d.loss_at_sl_usdt <= d.risk_budget_usdt


def test_pos_pct_below_min_is_advisory_only_and_size_is_not_inflated(rules):
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits())
    assert d.ok and d.pos_pct_below_min is True and d.notional <= d.notional_target
    assert "pos_pct" in d.detail


def test_pos_pct_max_caps_margin_and_loss_falls_below_budget(rules):
    """budget 50·SL 0.1% → 목표 50,000 → 100x → 마진 500 = 50% > 40% → 명목을 40,000으로 줄인다."""
    d = size_entry(D("60000"), D("59940"), LONG, D("1000"), regime(risk_pct=D("0.05")), rules, limits())
    assert d.ok and d.pos_pct_capped is True and lev(d) == 100
    assert d.notional_target == D("50000") and d.notional == D("39960")
    assert d.pos_pct <= D("0.40") and d.loss_at_sl_usdt < d.risk_budget_usdt


def test_loss_over_budget_after_final_qty_is_refused(rules, monkeypatch):
    """내림만 하면 손실 ≤ 예산이 보장되지만, 가드는 결과를 직접 재계산한다 — 정규화가 수량을 올리면 잡혀야 한다."""
    real = P.normalize_entry_qty

    def step_up(raw, price, r, **kw):
        q = real(raw, price, r, **kw)
        return replace(q, qty=q.qty + r.market_step * 5, notional=(q.qty + r.market_step * 5) * price)
    monkeypatch.setattr(P, "normalize_entry_qty", step_up)
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits())
    assert not d.ok and d.reason is RejectReason.LOSS_OVER_BUDGET
    ok = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits(loss_tolerance=D("0.2")))
    assert ok.ok, "허용 오차 안이면 통과"


# ── 브라켓 ──────────────────────────────────────────────────────────────
def test_notional_beyond_every_bracket_is_notional_cap(rules):
    d = size_entry(D("60000"), D("59940"), LONG, D("1000000000"), regime(risk_pct=D("0.5")), rules, limits())
    assert not d.ok and d.reason is RejectReason.NOTIONAL_CAP


def test_bracket_leverage_cap_below_l_min_is_leverage_infeasible(rules):
    """목표 명목 5,000,000 → fixture tier4(최대 50x). 레짐 [60, 100] → 어떤 L도 브라켓 상한을 못 넘는다."""
    d = size_entry(D("60000"), D("59940"), LONG, D("500000"), regime(l_min=60), rules, limits())
    assert not d.ok and d.reason is RejectReason.LEVERAGE_INFEASIBLE


def test_reported_bracket_is_the_final_floored_notional(rules):
    """Codex L2 Q5 — 목표 명목이 정확히 300,000(tier2 경계) → 내림 후 299,987.8 → tier1으로 보고."""
    d = size_entry(D("61234.5"), D("61173.2655"), LONG, D("30000"), regime(), rules, limits())
    assert d.ok and d.notional_target == D("300000") and d.notional < D("300000")
    assert d.bracket == 1 and d.mmr_eff == D("0.004")


def test_flooring_into_a_riskier_bracket_is_revalidated_and_refused(rules):
    """Codex L2 Q1 — 비단조 브라켓 우회 주입: 목표 5,000은 tier2(MMR 0.1%)로 통과, 내림 후 4,980은 tier1(MMR 2%) → 거부."""
    b1 = Bracket(1, 150, D("0"), D("5000"), D("0.020"), D("0"))
    b2 = Bracket(2, 150, D("5000"), D("1000000000"), D("0.001"), D("0"))
    bad = replace(rules, brackets=(b1, b2))
    d = size_entry(D("60000"), D("59700"), LONG, D("2500"), regime(l_min=50, l_max=50), bad, limits())
    assert not d.ok and d.reason is RejectReason.LIQ_DISTANCE and "내림 후" in d.detail


def test_parser_rejects_non_monotone_brackets():
    from exchange.errors import RulesError
    from exchange.rules import parse_brackets

    def resp(*rows):
        return [{"symbol": "BTCUSDT", "brackets": [
            {"bracket": i + 1, "initialLeverage": lv, "notionalFloor": lo, "notionalCap": hi,
             "maintMarginRatio": m, "cum": c} for i, (lv, lo, hi, m, c) in enumerate(rows)]}]
    with pytest.raises(RulesError, match="MMR"):
        parse_brackets(resp((150, 0, 5000, "0.02", 0), (150, 5000, 10**9, "0.001", 0)), "BTCUSDT")
    with pytest.raises(RulesError, match="cum"):
        parse_brackets(resp((150, 0, 5000, "0.004", -1),), "BTCUSDT")
    with pytest.raises(RulesError, match="레버리지"):
        parse_brackets(resp((50, 0, 5000, "0.004", 0), (100, 5000, 10**9, "0.005", 5)), "BTCUSDT")


def test_min_notional_refusal_via_normalization(rules):
    d = size_entry(D("60000"), D("59700"), LONG, D("2"), regime(), rules, limits())
    assert not d.ok and d.reason in (RejectReason.MIN_NOTIONAL, RejectReason.BELOW_MIN_QTY)


def test_result_does_not_depend_on_the_callers_decimal_context(rules):
    import decimal
    args = (D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits())
    base = size_entry(*args)
    with decimal.localcontext() as ctx:
        ctx.prec = 6
        low = size_entry(*args)
    assert (base.ok, base.leverage, base.qty, base.mmr_eff) == (low.ok, low.leverage, low.qty, low.mmr_eff)


# ── 진입 후 검사: 거래소 청산가가 진리원 ───────────────────────────────
def test_post_entry_ok_when_exchange_liq_matches_estimate(rules):
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits(buffer=D("1.2")))
    assert d.ok and d.liq_price_est is not None
    c = P.post_entry_liquidation_check(d, entry_price=D("60000"), exchange_liq_price=d.liq_price_est)
    assert c.status == "OK"


def test_post_entry_check_when_exchange_liq_is_closer_than_estimate_by_more_than_buffer(rules):
    """해석(레지스트리 #2): 거래소 청산 거리 × buffer < 추정 청산 거리 → CHECK(로그·점검)."""
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits(buffer=D("1.2")))
    est = d.liq_dist_pct
    assert est is not None
    closer = D("60000") * (1 - est / D("1.3"))                   # 거래소 거리 = 추정/1.3 < 추정/1.2
    c = P.post_entry_liquidation_check(d, entry_price=D("60000"), exchange_liq_price=closer)
    assert c.status == "CHECK" and c.exchange_dist_pct is not None and c.exchange_dist_pct < c.estimate_dist_pct
    near = D("60000") * (1 - est / D("1.1"))                     # 추정/1.1 > 추정/1.2 → 버퍼 안
    assert P.post_entry_liquidation_check(d, entry_price=D("60000"), exchange_liq_price=near).status == "OK"


@pytest.mark.parametrize("bad", [D("0"), D("60010")])
def test_post_entry_missing_or_wrong_side_exchange_liq_is_check(rules, bad):
    d = size_entry(D("60000"), D("59700"), LONG, D("1000"), regime(), rules, limits())
    assert P.post_entry_liquidation_check(d, entry_price=D("60000"), exchange_liq_price=bad).status == "CHECK"


# ── 속성 테스트 ─────────────────────────────────────────────────────────
_seen = {"ok": 0, "total": 0}


@settings(max_examples=300, deadline=None)
@given(entry=st.decimals(min_value=D("20000"), max_value=D("120000"), places=1),
       sl_bp=st.integers(min_value=1, max_value=59),                          # SL 0.01% ~ 0.59% < 0.6%
       long_=st.booleans(),
       equity=st.decimals(min_value=D("200"), max_value=D("5000"), places=2),
       risk_bp=st.integers(min_value=50, max_value=500),
       l_min=st.integers(min_value=50, max_value=100))
def test_property_100x_is_accepted_for_every_sl_below_0_6_percent_on_tier1(rules, entry, sl_bp, long_, equity,
                                                                            risk_bp, l_min):
    sl_dist = D(sl_bp) / 10000
    sl = entry * (1 - sl_dist) if long_ else entry * (1 + sl_dist)
    lim = limits()
    budget = equity * D(risk_bp) / 10000
    target = budget / sl_dist
    final_notional = min(target, lim.pos_pct_max * equity * 100)
    #  🔴 L은 **목표 명목**의 브라켓으로 고른다(레지스트리 #2 3단계). 목표가 tier1이어야 "tier1에서 100x"다.
    #     목표가 상위 티어면 캡으로 최종 명목이 tier1이 돼도 L은 그 티어 상한에 묶인다(보수적 · 설계서 §9 B3 기록).
    assume(target < D("300000"))
    step, min_notional = rules.symbol_rules.market_step, rules.symbol_rules.min_notional
    assume(final_notional - step * entry >= min_notional)                   # 내림 1 step 뒤에도 MIN_NOTIONAL 이상
    d = size_entry(entry, sl, LONG if long_ else SHORT, equity, regime(risk_pct=D(risk_bp) / 10000, l_min=l_min),
                   rules, lim)
    assert d.ok and lev(d) == 100, (d.reason, d.detail)


@settings(max_examples=500, deadline=None)
@given(entry=st.decimals(min_value=D("10000"), max_value=D("200000"), places=1),
       sl_bp=st.integers(min_value=1, max_value=300),                         # 0.01% ~ 3%
       long_=st.booleans(),
       equity=st.decimals(min_value=D("50"), max_value=D("50000"), places=2),
       risk_bp=st.integers(min_value=10, max_value=500),
       l_min=st.integers(min_value=50, max_value=100),
       width=st.integers(min_value=0, max_value=50),
       buf_c=st.integers(min_value=100, max_value=200))
def test_property_gate_pos_cap_and_loss_budget(rules, entry, sl_bp, long_, equity, risk_bp, l_min, width, buf_c):
    l_max = min(100, l_min + width)
    direction = LONG if long_ else SHORT
    sl_dist = D(sl_bp) / 10000
    sl = entry * (1 - sl_dist) if long_ else entry * (1 + sl_dist)
    lim = limits(buffer=D(buf_c) / 100)
    reg = regime(risk_pct=D(risk_bp) / 10000, l_min=l_min, l_max=l_max)
    d = size_entry(entry, sl, direction, equity, reg, rules, lim)
    target = equity * reg.risk_pct / sl_dist
    _seen["total"] += 1

    def gate(L: int, notional: Decimal) -> bool:
        b, me = mmr_eff_for(rules, notional)
        return L <= b.initial_leverage and sl_dist * lim.buffer < 1 / D(L) - me

    if d.ok:
        _seen["ok"] += 1
        L = lev(d)
        assert l_min <= L <= l_max
        assert gate(L, d.notional), "최종 명목에서 게이트 통과"
        assert d.pos_pct <= lim.pos_pct_max, "pos_pct는 절대 40%를 넘지 않는다"
        assert d.loss_at_sl_usdt <= d.risk_budget_usdt, "수락된 모든 결과에서 SL 손실 ≤ 예산"
        assert d.loss_at_sl_usdt == d.qty * abs(entry - sl)
        if L < l_max:
            assert not gate(L + 1, target), "구간 안 최고 정수 L(최대성)"
        assert d.liq_price_est is not None
        assert abs(entry - sl) * lim.buffer < abs(entry - d.liq_price_est)
        assert d.qty % rules.symbol_rules.market_step == 0 and d.notional >= rules.symbol_rules.min_notional
    elif d.reason is RejectReason.LIQ_DISTANCE and "내림 후" not in d.detail:
        b, me = mmr_eff_for(rules, target)
        assert all(sl_dist * lim.buffer >= 1 / D(L) - me for L in range(l_min, l_max + 1)
                   if L <= b.initial_leverage), "sl×buffer ≥ liq_dist 인 경우에만 거부"
    #  명시: 가장 느슨한 l_min에서도 게이트를 못 넘으면 절대 수락되지 않는다
    from exchange.errors import RulesError
    try:
        _, me_t = mmr_eff_for(rules, target)
    except RulesError:                                                      # 모든 브라켓 밖
        assert not d.ok and d.reason is RejectReason.NOTIONAL_CAP
    else:
        if sl_dist * lim.buffer >= 1 / D(l_min) - me_t:
            assert not d.ok


def test_the_wide_property_actually_saw_accepted_sizes():
    if _seen["total"] == 0:
        pytest.skip("속성 테스트가 이 실행에서 돌지 않았다(단독 실행)")
    assert _seen["ok"] / _seen["total"] >= 0.2, _seen
