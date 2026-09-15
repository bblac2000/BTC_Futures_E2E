"""layer 2 사이징 — 레지스트리 #2(위험 예산) · #4(B5 정확 청산식) · #5(SL 버퍼)가 규칙이다.

#4 청산 거리(신규 격리 포지션, 바이낸스 공식 원식에서 유도 · WB = N/L − N×taker):
    LONG  dist = (1/L − taker − MMR_eff) / (1 − MMR)
    SHORT dist = (1/L − taker − MMR_eff) / (1 + MMR)
    MMR·cum = max(진입 명목, 청산가에서의 명목)의 티어.
#5 게이트(둘 다): sl_dist × 1.5 < dist  AND  dist − sl_dist ≥ 10 bps. SL 트리거는 mark 가격 기준.

이 파일의 오라클 `official_liq_price`는 **바이낸스 FAQ 원식 그대로**(분자·분모 형태)를 계산한다 —
구현의 닫힌꼴과 독립이므로 두 계산이 일치하는지가 곧 유도 검증이다.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from exchange.errors import RulesError
from exchange.normalize import RejectReason
from exchange.orders import Direction
from exchange.rules import Bracket
from sizing import position as P
from sizing.config import (
    PERMITTED_LEVERAGE,
    SL_BUFFER_REL,
    SL_LIQ_MIN_GAP,
    SL_TRIGGER_BASIS,
    RegimeSizing,
    SizingLimits,
)
from sizing.position import liquidation_estimate, size_entry

D = Decimal
LONG, SHORT = Direction.LONG, Direction.SHORT
PCT1 = D("0.01")
ZERO = D("0")
ONE = D("1")


def regime(*, risk_pct: Decimal = PCT1, l_min: int = 50, l_max: int = 100) -> RegimeSizing:
    return RegimeSizing("test", risk_pct, l_min, l_max)


def limits(**kw) -> SizingLimits:
    return SizingLimits(**kw)


def lev(d) -> int:
    assert d.leverage is not None
    return d.leverage


# ── 오라클: 바이낸스 FAQ 원식 (격리·원웨이: TMM=0, UPNL=0, cumL=cumS=0) ─────────
def official_liq_price(rules, direction: Direction, entry: Decimal, qty: Decimal, L: int,
                       taker: Decimal | None = None) -> tuple[Decimal, Bracket]:
    """LP = (WB + cum_B − Side·Pos·EP) / (Pos·MMR_B − Side·Pos), WB = N/L − N×taker.
    티어 = max(진입 명목, 청산가 명목)의 브라켓 — 바뀌면 그 티어로 다시 계산."""
    side = 1 if direction is LONG else -1
    t = rules.commission.taker if taker is None else taker
    N = qty * entry
    wb = N / L - N * t
    b = rules.bracket_for_notional(N)
    seen: list[Bracket] = []
    while True:
        lp = (wb + b.cum - side * qty * entry) / (qty * b.maint_margin_ratio - side * qty)
        nb = rules.bracket_for_notional(max(N, qty * lp))
        if nb == b or nb in seen:
            return lp, b
        seen.append(b)
        b = nb


def official_dist(rules, direction, entry, qty, L, taker=None) -> Decimal:
    lp, _ = official_liq_price(rules, direction, entry, qty, L, taker)
    return (entry - lp) / entry if direction is LONG else (lp - entry) / entry


def gate(sl_dist: Decimal, dist: Decimal, lim: SizingLimits) -> bool:
    return sl_dist * lim.buffer_rel < dist and dist - sl_dist >= lim.min_gap


# ── 설정 (레지스트리 #2·#5) ─────────────────────────────────────────────
def test_pre_committed_constants():
    assert PERMITTED_LEVERAGE == (50, 100)
    assert (SL_BUFFER_REL, SL_LIQ_MIN_GAP, SL_TRIGGER_BASIS) == (D("1.5"), D("0.0010"), "MARK")
    lim = limits()
    assert (lim.buffer_rel, lim.min_gap) == (D("1.5"), D("0.0010"))
    assert (lim.pos_pct_max, lim.pos_pct_min, lim.loss_tolerance) == (D("0.40"), D("0.10"), D("0"))


@pytest.mark.parametrize("kw", [dict(l_min=49), dict(l_max=101), dict(l_min=80, l_max=60),
                                dict(risk_pct=D("0")), dict(risk_pct=D("1"))])
def test_regime_config_outside_decided_bounds_is_rejected(kw):
    with pytest.raises(ValueError):
        regime(**kw)


@pytest.mark.parametrize("kw", [dict(buffer_rel=D("0.99")), dict(min_gap=D("-0.0001")), dict(pos_pct_max=D("1.01")),
                                dict(pos_pct_max=D("0")), dict(pos_pct_min=D("0.5"), pos_pct_max=D("0.4")),
                                dict(loss_tolerance=D("-0.01"))])
def test_limits_validation(kw):
    with pytest.raises(ValueError):
        SizingLimits(**kw)


def test_float_inputs_are_refused(rules):
    with pytest.raises(TypeError):
        size_entry(60000.0, D("59700"), LONG, D("1000"), regime(), rules, limits())  # type: ignore[arg-type]


@pytest.mark.parametrize(("direction", "sl"), [(LONG, D("60000")), (LONG, D("60100")), (SHORT, D("59900"))])
def test_sl_on_the_wrong_side_is_a_recorded_rejection(rules, direction, sl):
    d = size_entry(D("60000"), sl, direction, D("1000"), regime(), rules, limits())
    assert not d.ok and d.reason is RejectReason.SL_WRONG_SIDE and d.qty == 0


# ── #4 정확 청산식 ──────────────────────────────────────────────────────
@pytest.mark.parametrize(("direction", "qty", "L"), [
    (LONG, D("0.1"), 100), (SHORT, D("0.1"), 100),            # tier1
    (LONG, D("10"), 100), (SHORT, D("10"), 100),              # tier2 (cum 300)
    (SHORT, D("4.99"), 100),                                  # 진입 tier1 · 청산가 명목 tier2
    (LONG, D("0.5"), 57), (SHORT, D("0.5"), 73),
])
def test_closed_form_matches_the_official_formula(rules, direction, qty, L):
    entry = D("60000")
    est = liquidation_estimate(direction, entry, qty * entry, L, rules)
    lp, b = official_liq_price(rules, direction, entry, qty, L)
    assert est.bracket == b.bracket
    assert abs(est.price - lp) < D("1e-18"), (est.price, lp)
    assert abs(est.dist_pct - official_dist(rules, direction, entry, qty, L)) < D("1e-24")


def test_parser_rejects_discontinuous_cum():
    """Codex L2 전체검토 Q2 — cum 연속성(cum_i = cum_{i−1} + floor_i × (MMR_i − MMR_{i−1}))이 없으면
    유지증거금이 경계에서 불연속이 되고 티어 탐색이 진동할 수 있다. 실제 5심볼 fixture는 정확히 만족한다."""
    from exchange.rules import parse_brackets
    resp = [{"symbol": "BTCUSDT", "brackets": [
        {"bracket": 1, "initialLeverage": 100, "notionalFloor": 0, "notionalCap": 100, "maintMarginRatio": "0.004", "cum": 0},
        {"bracket": 2, "initialLeverage": 100, "notionalFloor": 100, "notionalCap": 1000000, "maintMarginRatio": "0.005",
         "cum": 0}]}]
    with pytest.raises(RulesError, match="cum"):
        parse_brackets(resp, "BTCUSDT")


def test_no_tier_fixed_point_fails_closed(rules):
    """파서를 우회해 불연속 브라켓을 주입하면(Codex 입력) 티어가 진동한다 → 추정하지 않고 RulesError(사이징은 거부)."""
    b1 = Bracket(1, 100, D("0"), D("100"), D("0.004"), D("0"))
    b2 = Bracket(2, 100, D("100"), D("1000000"), D("0.005"), D("0"))
    bad = replace(rules, brackets=(b1, b2))
    with pytest.raises(RulesError, match="고정점"):
        liquidation_estimate(SHORT, D("1"), D("99.5"), 100, bad)


@settings(max_examples=400, deadline=None)
@given(exp=st.floats(min_value=1.0, max_value=8.9), long_=st.booleans(), L=st.integers(min_value=1, max_value=100))
def test_property_chosen_tier_is_a_fixed_point_on_real_brackets(rules, exp, long_, L):
    """구현의 탐색 방식과 **독립적인** 성질: 선택된 티어는 자신의 기준 명목 max(진입, 청산가 명목)을 실제로 포함한다."""
    notional = D(str(round(10 ** exp, 2)))
    direction = LONG if long_ else SHORT
    try:
        est = liquidation_estimate(direction, D("60000"), notional, L, rules)
    except RulesError:
        return                                                               # 청산가 명목이 브라켓 밖 — 추정 없음
    assert rules.bracket_for_notional(est.tier_basis_notional).bracket == est.bracket
    expected = max(notional, notional * est.price / D("60000"))
    assert abs(est.tier_basis_notional - expected) <= expected * D("1e-26")


def test_short_uses_the_tier_of_the_notional_at_the_liquidation_price(rules):
    """진입 명목 299,400(tier1)인 SHORT 100x → 청산가 명목 ≈ 301,039(tier2) → MMR 0.5%·cum 300으로 계산."""
    est = liquidation_estimate(SHORT, D("60000"), D("299400"), 100, rules)
    assert est.bracket == 2 and est.mmr == D("0.005") and est.cum == D("300")
    assert est.tier_basis_notional > D("300000")
    long_est = liquidation_estimate(LONG, D("60000"), D("299400"), 100, rules)
    assert long_est.bracket == 1, "LONG은 청산가 명목이 진입보다 작다 → 진입 티어"


def test_long_distance_exceeds_short_distance_at_same_inputs(rules):
    lo = liquidation_estimate(LONG, D("60000"), D("6000"), 100, rules)
    sh = liquidation_estimate(SHORT, D("60000"), D("6000"), 100, rules)
    assert lo.dist_pct > sh.dist_pct
    tol = D("1e-26")
    assert abs(lo.dist_pct - (1 / D(100) - D("0.0005") - D("0.004")) / (1 - D("0.004"))) < tol
    assert abs(sh.dist_pct - (1 / D(100) - D("0.0005") - D("0.004")) / (1 + D("0.004"))) < tol


def test_opening_fee_assumption_shrinks_the_distance(rules):
    with_fee = liquidation_estimate(LONG, D("60000"), D("6000"), 100, rules)
    no_fee = liquidation_estimate(LONG, D("60000"), D("6000"), 100, rules, taker=ZERO)
    assert abs((no_fee.dist_pct - with_fee.dist_pct) - rules.commission.taker / (1 - D("0.004"))) < D("1e-26")


def test_liquidation_fee_is_not_in_the_distance_but_in_the_liquidation_loss(rules):
    d = size_entry(D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits())
    assert d.ok and d.liq_dist_pct is not None
    fee = rules.symbol_rules.liquidation_fee
    assert abs(d.liq_dist_pct - official_dist(rules, LONG, D("60000"), d.qty, lev(d))) < D("1e-24")
    assert d.loss_at_liquidation_usdt == d.margin + d.notional * fee


# ── #5 게이트 ───────────────────────────────────────────────────────────
def test_codex_short_example_is_now_refused_at_100x(rules):
    """🔴 Codex 재검토 Q2 반례: SHORT entry 60,000 · SL 60,359.4(0.599%) — 옛 행#2 식(1/L − MMR = 0.6%)은 100x를 수락했다.
    정확식(fee 포함)으로 100x 거리 = 0.5478% < 0.599% → 100x 불가.
    · 게이트만 격리(buffer 1·floor 0): 95x(96x 거리 0.5893% < 0.599%)
    · 레지스트리 #5(1.5배·10bp): 73x(74x 거리 0.8978% < 0.8985%)"""
    entry, sl = D("60000"), D("60359.4")
    old_row2_dist_100 = 1 / D(100) - D("0.004")
    assert (sl - entry) / entry < old_row2_dist_100, "옛 식은 100x를 통과시켰다"
    iso = size_entry(entry, sl, SHORT, D("1000"), regime(), rules, limits(buffer_rel=ONE, min_gap=ZERO))
    assert iso.ok and lev(iso) == 95
    reg = size_entry(entry, sl, SHORT, D("1000"), regime(), rules, limits())
    assert reg.ok and lev(reg) == 73


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_100x_threshold_from_the_exact_formula_with_registry_buffers(rules, direction):
    """tier1·fixture 값: 100x 수락 ⇔ sl < min(dist₁₀₀/1.5, dist₁₀₀ − 10bp). 경계 바로 아래 100x · 바로 위 99x 이하."""
    entry = D("60000")
    d100 = liquidation_estimate(direction, entry, D("6000"), 100, rules).dist_pct
    thr = min(d100 / SL_BUFFER_REL, d100 - SL_LIQ_MIN_GAP)
    below = thr - D("0.00001")
    above = thr + D("0.00001")
    sgn = -1 if direction is LONG else 1
    ok = size_entry(entry, entry * (1 + sgn * below), direction, D("1000"), regime(), rules, limits())
    no = size_entry(entry, entry * (1 + sgn * above), direction, D("1000"), regime(), rules, limits())
    assert ok.ok and lev(ok) == 100
    assert no.ok and lev(no) < 100


def test_min_gap_condition_is_enforced_independently(rules):
    """buffer 1·floor 20bp: 100x LONG 거리 0.5522% · SL 0.40% → 비율 조건은 통과, 간격 0.15% < 0.20% → 100x 불가."""
    entry = D("60000")
    d = size_entry(entry, entry * (1 - D("0.004")), LONG, D("1000"), regime(), rules,
                   limits(buffer_rel=ONE, min_gap=D("0.0020")))
    assert d.ok and lev(d) < 100
    assert d.liq_dist_pct is not None and d.liq_dist_pct - d.sl_dist_pct >= D("0.0020")


def test_refused_when_no_leverage_in_range_passes(rules):
    """SL 1.1%: 50x LONG 거리 ≈ 1.556% / 1.5 = 1.037% < 1.1% → 거부(50 밑으로 내리지 않는다)."""
    d = size_entry(D("60000"), D("59340"), LONG, D("1000"), regime(), rules, limits())
    assert not d.ok and d.reason is RejectReason.LIQ_DISTANCE and d.qty == 0


def test_sl_trigger_basis_is_recorded_as_mark(rules):
    d = size_entry(D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits())
    assert d.sl_trigger_basis == "MARK"


# ── #2 위험 예산 ────────────────────────────────────────────────────────
def test_notional_comes_from_risk_budget_and_pos_pct_is_derived(rules):
    """equity 1000·risk 1%·SL 0.3% → budget 10 → 목표 명목 3,333.33 → L = 게이트 통과 최고 정수."""
    d = size_entry(D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits())
    assert d.ok and d.risk_budget_usdt == D("10")
    assert abs(d.notional_target - D("10") / D("0.003")) < D("1e-24")
    L = lev(d)
    assert gate(d.sl_dist_pct, liquidation_estimate(LONG, D("60000"), d.notional_target, L, rules).dist_pct, limits())
    if L < 100:
        assert not gate(d.sl_dist_pct, liquidation_estimate(LONG, D("60000"), d.notional_target, L + 1, rules).dist_pct,
                        limits())
    assert d.qty == D("0.055") and d.notional == D("3300")
    assert d.pos_pct == d.margin / D("1000") and d.loss_at_sl_usdt == D("9.9")


def test_pos_pct_below_min_is_advisory_only_and_size_is_not_inflated(rules):
    d = size_entry(D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits())
    assert d.ok and d.pos_pct_below_min is True and d.notional <= d.notional_target and "pos_pct" in d.detail


def test_pos_pct_max_caps_margin_and_loss_falls_below_budget(rules):
    """budget 50·SL 0.1% → 목표 50,000 → 100x → 마진 500 = 50% > 40% → 명목 40,000으로 줄인다."""
    d = size_entry(D("60000"), D("59940"), LONG, D("1000"), regime(risk_pct=D("0.05")), rules, limits())
    assert d.ok and d.pos_pct_capped is True and lev(d) == 100
    assert d.notional == D("39960") and d.pos_pct <= D("0.40") and d.loss_at_sl_usdt < d.risk_budget_usdt


def test_loss_over_budget_after_final_qty_is_refused(rules, monkeypatch):
    real = P.normalize_entry_qty

    def step_up(raw, price, r, **kw):
        q = real(raw, price, r, **kw)
        return replace(q, qty=q.qty + r.market_step * 5, notional=(q.qty + r.market_step * 5) * price)
    monkeypatch.setattr(P, "normalize_entry_qty", step_up)
    d = size_entry(D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits())
    assert not d.ok and d.reason is RejectReason.LOSS_OVER_BUDGET
    ok = size_entry(D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits(loss_tolerance=D("0.2")))
    assert ok.ok


# ── 브라켓 ──────────────────────────────────────────────────────────────
def test_b3_highest_leverage_is_chosen_on_the_target_bracket_before_the_pos_pct_cap(rules):
    """B3(사용자 확인 · 보수적 유지) — Codex 반례를 문서로 고정: LONG entry 60,000·SL 0.1%·equity 10,000·risk 50%
    → 목표 5,000,000은 tier4(최대 50x) → L=50 → 캡 후 명목 199,980. 캡 뒤 명목(tier1)이면 100x도 통과하지만
    레지스트리 #2 ③ 순서대로 목표 명목 티어로 고른다."""
    d = size_entry(D("60000"), D("59940"), LONG, D("10000"), regime(risk_pct=D("0.5")), rules, limits())
    assert d.ok and lev(d) == 50 and d.pos_pct_capped and d.notional == D("199980")


def test_notional_beyond_every_bracket_is_notional_cap(rules):
    d = size_entry(D("60000"), D("59940"), LONG, D("1000000000"), regime(risk_pct=D("0.5")), rules, limits())
    assert not d.ok and d.reason is RejectReason.NOTIONAL_CAP


def test_bracket_leverage_cap_below_l_min_is_leverage_infeasible(rules):
    """목표 명목 5,000,000 → tier4(최대 50x). 레짐 [60, 100] → 어떤 L도 브라켓 상한을 못 넘는다."""
    d = size_entry(D("60000"), D("59940"), LONG, D("500000"), regime(l_min=60), rules, limits())
    assert not d.ok and d.reason is RejectReason.LEVERAGE_INFEASIBLE


def test_reported_bracket_is_the_final_floored_notional(rules):
    """목표 명목이 정확히 300,000(tier2 경계, LONG) → 내림 후 299,987.8 → tier1으로 보고."""
    d = size_entry(D("61234.5"), D("61173.2655"), LONG, D("30000"), regime(), rules, limits())
    assert d.ok and d.notional_target == D("300000") and d.notional < D("300000") and d.bracket == 1


def test_flooring_into_a_riskier_bracket_is_revalidated_and_refused(rules):
    """비단조 브라켓 우회 주입: 목표 5,000은 tier2(MMR 0.1%)로 통과, 내림 후 4,980은 tier1(MMR 2%) → 거부."""
    b1 = Bracket(1, 150, D("0"), D("5000"), D("0.020"), D("0"))
    b2 = Bracket(2, 150, D("5000"), D("1000000000"), D("0.001"), D("0"))
    bad = replace(rules, brackets=(b1, b2))
    d = size_entry(D("60000"), D("59700"), LONG, D("2500"), regime(l_min=50, l_max=50), bad,
                   limits(buffer_rel=ONE, min_gap=ZERO))
    assert not d.ok and d.reason is RejectReason.LIQ_DISTANCE and "내림 후" in d.detail


def test_parser_rejects_non_monotone_brackets():
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
    d = size_entry(D("60000"), D("59820"), LONG, D("2"), regime(), rules, limits())
    assert not d.ok and d.reason in (RejectReason.MIN_NOTIONAL, RejectReason.BELOW_MIN_QTY)


def test_result_does_not_depend_on_the_callers_decimal_context(rules):
    import decimal
    args = (D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits())
    base = size_entry(*args)
    with decimal.localcontext() as ctx:
        ctx.prec = 6
        low = size_entry(*args)
    assert (base.ok, base.leverage, base.qty, base.liq_dist_pct) == (low.ok, low.leverage, low.qty, low.liq_dist_pct)


# ── 진입 후 검사: 거래소 청산가가 진리원 · 수수료 가정은 여기서 판정된다 ───
def _long(rules):
    d = size_entry(D("60000"), D("59820"), LONG, D("1000"), regime(), rules, limits())
    assert d.ok and d.liq_price_est is not None and d.liq_dist_pct is not None
    return d


def test_post_entry_ok_when_exchange_liq_matches_estimate(rules):
    d = _long(rules)
    assert d.liq_price_est is not None
    c = P.post_entry_liquidation_check(d, rules, entry_price=D("60000"), qty=d.qty, exchange_liq_price=d.liq_price_est)
    assert c.status == "OK" and c.closer_model == "fee"


def test_closer_model_reports_a_tie_instead_of_defaulting_to_fee(rules):
    """Codex Q5 — 진단 필드다. 두 모델과 똑같이 떨어져 있으면 'fee'로 기울이지 않고 'tie'."""
    d = _long(rules)
    fee = liquidation_estimate(LONG, D("60000"), d.notional, lev(d), rules)
    nofee = liquidation_estimate(LONG, D("60000"), d.notional, lev(d), rules, taker=ZERO)
    mid = (fee.price + nofee.price) / 2
    c = P.post_entry_liquidation_check(d, rules, entry_price=D("60000"), qty=d.qty, exchange_liq_price=mid)
    assert c.closer_model == "tie"


def test_post_entry_check_when_exchange_liq_is_closer_than_estimate_by_more_than_buffer(rules):
    d = _long(rules)
    est = liquidation_estimate(LONG, D("60000"), d.notional, lev(d), rules).dist_pct
    closer = D("60000") * (1 - est / D("1.6"))                   # × 1.5 < 추정
    c = P.post_entry_liquidation_check(d, rules, entry_price=D("60000"), qty=d.qty, exchange_liq_price=closer)
    assert c.status == "CHECK"
    near = D("60000") * (1 - est / D("1.4"))                     # × 1.5 ≥ 추정
    assert P.post_entry_liquidation_check(d, rules, entry_price=D("60000"), qty=d.qty,
                                          exchange_liq_price=near).status == "OK"


@pytest.mark.parametrize("bad", [D("0"), D("60010")])
def test_post_entry_missing_or_wrong_side_exchange_liq_is_check(rules, bad):
    d = _long(rules)
    assert P.post_entry_liquidation_check(d, rules, entry_price=D("60000"), qty=d.qty,
                                          exchange_liq_price=bad).status == "CHECK"


def test_post_entry_estimate_is_recomputed_from_the_actual_fill(rules):
    """Codex Q4 — 실제 체결가·수량으로 브라켓을 다시 구한다(재사용 금지)."""
    d = size_entry(D("60000"), D("59940"), LONG, D("20000"), regime(risk_pct=D("0.03")), rules, limits())
    assert d.ok and d.bracket == 2
    fill, qty = D("30000"), d.qty
    c = P.post_entry_liquidation_check(d, rules, entry_price=fill, qty=qty, exchange_liq_price=fill * D("0.99"))
    expected = liquidation_estimate(LONG, fill, fill * qty, lev(d), rules)
    assert c.estimate_dist_pct == expected.dist_pct and c.bracket == expected.bracket


def test_post_entry_logs_which_fee_model_the_exchange_matches(rules):
    """수수료가 격리 마진을 줄이는지(레지스트리 #4 가정)는 첫 페이퍼 주의 거래소 청산가로 판정한다 —
    두 모델(수수료 차감/미차감)의 추정 거리와 각각의 차이를 남긴다."""
    d = _long(rules)
    no_fee = liquidation_estimate(LONG, D("60000"), d.notional, lev(d), rules, taker=ZERO)
    c = P.post_entry_liquidation_check(d, rules, entry_price=D("60000"), qty=d.qty, exchange_liq_price=no_fee.price)
    assert c.closer_model == "no_fee" and c.gap_vs_no_fee_pct is not None and abs(c.gap_vs_no_fee_pct) < D("1e-30")
    assert c.estimate_no_fee_dist_pct > c.estimate_dist_pct and c.gap_vs_fee_pct is not None and c.gap_vs_fee_pct > 0


# ── 속성 테스트 ─────────────────────────────────────────────────────────
_seen = {"ok": 0, "total": 0}


@settings(max_examples=300, deadline=None)
@given(entry=st.decimals(min_value=D("20000"), max_value=D("120000"), places=1),
       frac=st.integers(min_value=1, max_value=999),
       long_=st.booleans(),
       equity=st.decimals(min_value=D("200"), max_value=D("5000"), places=2),
       risk_bp=st.integers(min_value=50, max_value=500))
def test_property_100x_accepted_exactly_below_the_exact_formula_threshold_on_tier1(rules, entry, frac, long_, equity,
                                                                                    risk_bp):
    direction = LONG if long_ else SHORT
    lim = limits()
    d100 = liquidation_estimate(direction, entry, D("6000"), 100, rules).dist_pct   # tier1·cum 0 → 명목 무관
    thr = min(d100 / lim.buffer_rel, d100 - lim.min_gap)
    sl_dist = thr * D(frac) / 1000                                                  # 임계 아래
    budget = equity * D(risk_bp) / 10000
    target = budget / sl_dist
    assume(target < D("290000"))
    assume(min(target, lim.pos_pct_max * equity * 100) - rules.symbol_rules.market_step * entry
           >= rules.symbol_rules.min_notional)
    sl = entry * (1 - sl_dist) if long_ else entry * (1 + sl_dist)
    d = size_entry(entry, sl, direction, equity, regime(risk_pct=D(risk_bp) / 10000), rules, lim)
    assert d.ok and lev(d) == 100, (d.reason, d.detail)


@settings(max_examples=500, deadline=None)
@given(entry=st.decimals(min_value=D("10000"), max_value=D("200000"), places=1),
       sl_bp=st.integers(min_value=1, max_value=150),
       long_=st.booleans(),
       equity=st.decimals(min_value=D("50"), max_value=D("50000"), places=2),
       risk_bp=st.integers(min_value=10, max_value=500),
       l_min=st.integers(min_value=50, max_value=100),
       width=st.integers(min_value=0, max_value=50))
def test_property_exact_gate_pos_cap_and_loss_budget(rules, entry, sl_bp, long_, equity, risk_bp, l_min, width):
    l_max = min(100, l_min + width)
    direction = LONG if long_ else SHORT
    sl_dist = D(sl_bp) / 10000
    sl = entry * (1 - sl_dist) if long_ else entry * (1 + sl_dist)
    lim = limits()
    reg = regime(risk_pct=D(risk_bp) / 10000, l_min=l_min, l_max=l_max)
    d = size_entry(entry, sl, direction, equity, reg, rules, lim)
    target = equity * reg.risk_pct / sl_dist
    _seen["total"] += 1

    def passes(L: int, notional: Decimal) -> bool:
        try:
            b = rules.bracket_for_notional(notional)
            dist = official_dist(rules, direction, entry, notional / entry, L)
        except RulesError:
            return False
        return L <= b.initial_leverage and gate(sl_dist, dist, lim)

    if d.ok:
        _seen["ok"] += 1
        L = lev(d)
        assert l_min <= L <= l_max
        assert passes(L, d.notional), "최종 명목에서 **바이낸스 원식** 기준 게이트 통과"
        assert d.pos_pct <= lim.pos_pct_max
        assert d.loss_at_sl_usdt <= d.risk_budget_usdt
        if L < l_max:
            assert not passes(L + 1, target), "구간 안 최고 정수 L(최대성)"
        assert d.liq_price_est is not None
        assert abs(entry - sl) * lim.buffer_rel < abs(entry - d.liq_price_est), "SL×1.5가 청산가 안쪽"
        assert d.qty % rules.symbol_rules.market_step == 0 and d.notional >= rules.symbol_rules.min_notional
    elif d.reason is RejectReason.LIQ_DISTANCE and "내림 후" not in d.detail:
        assert not any(passes(L, target) for L in range(l_min, l_max + 1))


def test_the_wide_property_actually_saw_accepted_sizes():
    if _seen["total"] == 0:
        pytest.skip("속성 테스트가 이 실행에서 돌지 않았다(단독 실행)")
    assert _seen["ok"] / _seen["total"] >= 0.2, _seen
