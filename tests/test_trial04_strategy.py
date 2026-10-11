"""트라이얼 #4 (d) — 암별 상태 기계 · 인쇄 깔때기 사유·순서 · 히스테리시스 · P2/P3 · 하네스 불변식 · 결정론(규약 C24~C36). 합성만."""
from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from backtest.data import Funding
from exchange.normalize import normalize_price
from exchange.orders import Direction, Intent, side_for
from paper.sender import adverse_fill_estimate
from sizing.position import size_entry
from strategies.trial04 import anchor as A
from strategies.trial04 import harness as H
from strategies.trial04.config import LIMITS, REGIME, TC_V3
from strategies.trial04.exit_schedule import HOLD_MIN
from strategies.trial04.strategy import RunInvariantError, Trial04, Variant
from tests.fixtures import t4_scenario as S

ROOT = Path(__file__).resolve().parent.parent
TICK = S.RULES.symbol_rules.tick_size
ARMS = ["S", "L"]
M, DAY, H8, T_E = S.M, S.DAY, S.H8, S.T_E
N_PRINTS = 90                                               # 창 안 경계(30일 × 3)


def dirn(arm: str) -> Direction:
    return Direction.SHORT if arm == "S" else Direction.LONG


def funnel(r) -> dict[str, int]:
    return dict(r.strategy.funnel)


# ── 끝에서 끝(암마다 · 손으로 계산한 장부) ────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
def test_end_to_end_known_ledger(arm):
    r = S.run(S.Scenario(arm=arm))
    s = r.strategy
    assert funnel(r) == {"not_extreme": N_PRINTS - 1, "candidate": 1} and s.entry == {"filled": 1, "exit.time_exit": 1}
    assert len(r.trades) == 1 and s.window_prints == N_PRINTS and s.state == "IDLE"      # 청산 뒤 띠 안 인쇄가 WAIT를 풀었다
    t, i = r.trades[0], r.trades[0]["t4"]
    d = dirn(arm)
    assert i["T"] == T_E and t["entry_ms"] == T_E + M == i["fill_open"]                 # 결정 = T + 1분 = 체결 봉 시가
    assert t["exit_ms"] == t["entry_ms"] + HOLD_MIN * M and t["exit_reason"] == "time_exit"
    ref, atr = D(i["ref"]), D(i["atr"])
    assert ref == D("60000") and atr == D("1800") and D(i["sl_dist"]) == D("2.0") * atr / ref == D("0.06")
    raw = ref + D("2.0") * atr if d is Direction.SHORT else ref - D("2.0") * atr
    assert D(i["sl"]) == normalize_price(raw, S.RULES.symbol_rules) == D(t["sl"])
    dec = size_entry(ref, D(i["sl"]), d, D(1000), REGIME, S.RULES, LIMITS)              # 결정 시점 B2 = 체결 기준가(C25)
    assert dec.ok and dec.leverage == i["decision_leverage"] == 10 and str(dec.qty) == i["decision_qty"]
    quote = adverse_fill_estimate(side_for(d, Intent.ENTRY), ref, TICK, D("0.0006"))
    assert D(t["entry_fill"]) == quote
    fill_dec = size_entry(quote, D(i["sl"]), d, D(1000), REGIME, S.RULES, LIMITS)       # 체결 시점 재사이징(6 bps 예상 체결가)
    assert D(t["qty"]) == fill_dec.qty and t["leverage"] == fill_dec.leverage == 10
    ex = S.lines(r, "exit")[0]
    sign = D(-1) if arm == "S" else D(1)
    assert D(ex["funding_paid"]) == sign * 15 * D(t["qty"]) * D("60000") * D("0.0001")   # T 정산 없음 · 첫 정산 T + 8h · 15회
    net = (D(t["wallet_after"]) - D(1000)) / (D(t["qty"]) * D(t["entry_fill"])) * 10_000
    assert D(t["net_bps"]) == net
    assert i["p"] == repr(S.EXT[arm]) and i["q10"] < 0 < i["q90"]


@pytest.mark.parametrize("arm", ARMS)
def test_two_runs_are_byte_identical(arm):
    assert S.digest(S.run(S.Scenario(arm=arm))) == S.digest(S.run(S.Scenario(arm=arm)))


def test_real_runs_use_tc_v3_unchanged_and_no_busy_gate_import():
    tree = ast.parse((ROOT / "strategies" / "trial04" / "strategy.py").read_text())
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "busy_check" not in names and "TC_V3" in names


# ── 인쇄 깔때기 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
def test_other_sides_extreme_is_not_extreme_for_this_arm(arm):
    other = "L" if arm == "S" else "S"
    r = S.run(S.Scenario(arm=arm, over={T_E: S.EXT[other]}))
    assert funnel(r) == {"not_extreme": N_PRINTS} and r.trades == []


def test_print_invalid_makes_no_decision_and_does_not_join_the_distribution():
    r = S.run(S.Scenario(invalid={T_E}))
    assert funnel(r) == {"not_extreme": N_PRINTS - 1, "print_invalid": 1} and r.trades == []
    assert r.strategy.ingested == 300 + N_PRINTS - 1


def test_distribution_undefined_until_270_prior_valid_prints():
    r = S.run(S.Scenario(prior=200))
    assert funnel(r) == {"distribution_undefined": 70, "not_extreme": N_PRINTS - 70} and r.trades == []   # T_E는 49번째 → 미정의


def test_print_incomplete_makes_no_decision_but_joins_the_distribution():
    r = S.run(S.Scenario(incomplete={T_E}))
    assert funnel(r) == {"not_extreme": N_PRINTS - 1, "print_incomplete": 1} and r.trades == []
    assert r.strategy.ingested == 300 + N_PRINTS


def test_decision_bar_missing_makes_no_decision_and_never_fills_late():
    r = S.run(S.Scenario(drop={T_E}))
    assert funnel(r) == {"not_extreme": N_PRINTS - 1, "decision_bar_missing": 1} and r.trades == []
    assert r.strategy.ingested == 300 + N_PRINTS


@pytest.mark.parametrize("arm", ARMS)
def test_extreme_during_position_is_recorded_as_busy_not_raised(arm):
    e = S.EXT[arm]
    r = S.run(S.Scenario(arm=arm, over={T_E: e, T_E + H8: e, T_E + 3 * DAY: e}))
    assert funnel(r) == {"not_extreme": N_PRINTS - 3, "candidate": 1, "position_busy": 2} and len(r.trades) == 1


@pytest.mark.parametrize("arm", ARMS)
def test_hysteresis_extreme_then_inside_then_extreme(arm):
    e = S.EXT[arm]
    x1, x2 = T_E + 5 * DAY + H8, T_E + 5 * DAY + 3 * H8          # 청산(T_E + 5일 + 1분) 뒤 첫 인쇄 = 극단 → 흡수 · 그다음 띠 안 · 그다음 극단
    r = S.run(S.Scenario(arm=arm, over={T_E: e, x1: e, x2: e}))
    assert funnel(r) == {"not_extreme": N_PRINTS - 3, "candidate": 2, "wait_absorbed": 1}
    assert [t["entry_ms"] for t in r.trades] == [T_E + M, x2 + M] and r.strategy.entry == {"filled": 2, "exit.time_exit": 2}


def test_incomplete_inside_print_does_not_release_wait():
    e = S.EXT["S"]
    x1, mid, x2 = T_E + 5 * DAY + H8, T_E + 5 * DAY + 2 * H8, T_E + 5 * DAY + 3 * H8
    r = S.run(S.Scenario(over={T_E: e, x1: e, x2: e}, incomplete={mid}))
    assert funnel(r) == {"not_extreme": N_PRINTS - 4, "candidate": 1, "wait_absorbed": 2, "print_incomplete": 1}
    assert len(r.trades) == 1


@pytest.mark.parametrize("arm", ARMS)
def test_print_of_the_exit_bar_does_not_count_for_hysteresis(arm):
    """SL이 경계 봉 안에서 체결(시각 = 그 봉 마감 직전) → 그 봉의 인쇄 T는 '청산 체결 뒤'가 아니다(T > 청산 시각 · 엄격)."""
    e = S.EXT[arm]
    g = T_E + H8
    wick = S.bar(g, lo="56000") if arm == "L" else S.bar(g, hi="64000")
    r = S.run(S.Scenario(arm=arm, over={T_E: e, g + H8: e}, bar_over={g: wick}))
    ex = S.lines(r, "exit")[0]
    assert ex["reason"] == "sl" and g < ex["ts_ms"] < g + M
    assert funnel(r) == {"not_extreme": N_PRINTS - 2, "candidate": 1, "wait_absorbed": 1} and len(r.trades) == 1
    # 대조: 한 인쇄 뒤(띠 안 인쇄가 청산 뒤에 하나 있음)라면 두 번째 극단은 후보다
    r2 = S.run(S.Scenario(arm=arm, over={T_E: e, g + 2 * H8: e}, bar_over={g: wick}))
    assert funnel(r2)["candidate"] == 2 and "wait_absorbed" not in funnel(r2)


# ── not_evaluable · 밴드 · 사이징 ────────────────────────────────────────────
def test_not_evaluable_subreasons_and_state_unchanged():
    t = T_E + M
    cases = {
        "mark_incomplete": S.Scenario(drop={t + 2 * DAY}),
        "funding": S.Scenario(no_funding={T_E + 2 * H8}),
        "atr_days": S.Scenario(drop={S.D0 + 5 * DAY + 7 * M}),
        "window_end": S.Scenario(over={S.D0 + 25 * DAY: S.EXT["S"]}),
    }
    for sub, sc in cases.items():
        r = S.run(sc)
        assert funnel(r) == {"not_extreme": N_PRINTS - 1, "not_evaluable": 1}, sub
        assert dict(r.strategy.sub) == {f"not_evaluable.{sub}": 1} and r.trades == [] and r.strategy.state == "IDLE"


def test_missing_close_of_day_d_minus_15_is_not_evaluable():
    te = S.D0 + 15 * DAY + H8                                      # d = 15 → d − 15 = 0
    r = S.run(S.Scenario(over={te: S.EXT["S"]}, drop={S.D0 + 1439 * M}))
    assert dict(r.strategy.sub) == {"not_evaluable.atr_prev_close": 1} and r.trades == []
    assert S.run(S.Scenario(over={te: S.EXT["S"]})).strategy.entry["filled"] == 1


def test_fill_on_boundary_without_its_own_funding_record_is_still_a_candidate():
    """결정 17: T의 정산은 요구하지 않는다(체결 T + 1분은 반열린 구간의 시작 밖)."""
    r = S.run(S.Scenario(no_funding={T_E}))
    assert funnel(r)["candidate"] == 1 and len(r.trades) == 1


@pytest.mark.parametrize("x,sub", [(60, "floor"), (3500, "ceiling")])
def test_sl_dist_band(x, sub):
    r = S.run(S.Scenario(x=x))
    assert funnel(r) == {"not_extreme": N_PRINTS - 1, "sl_dist_out_of_range": 1}
    assert dict(r.strategy.sub) == {f"sl_dist_out_of_range.{sub}": 1} and r.strategy.state == "IDLE"


def test_band_edges_are_inclusive_and_the_ceiling_is_rejected_by_sizing():
    lo = S.run(S.Scenario(x=150))                                  # 4·150 / 60,000 = 1.0% → 밴드 안
    assert lo.strategy.entry["filled"] == 1 and D(lo.trades[0]["t4"]["sl_dist"]) == D("0.01") and lo.trades[0]["leverage"] == 30
    hi = S.run(S.Scenario(x=3000))                                 # 20.0% → 밴드 안이지만 명목 50 → 수량 내림 뒤 거부(r3 §1)
    assert funnel(hi) == {"not_extreme": N_PRINTS - 1, "sizing_rejected_decision": 1} and hi.trades == []


# ── P2 · P3 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("k", [1, 3])
def test_p2_delays_the_fill_by_k_prints_and_keeps_the_original_sl(arm, k):
    base = S.run(S.Scenario(arm=arm))
    r = S.run(S.Scenario(arm=arm), Variant(delay=k))
    t, i = r.trades[0], r.trades[0]["t4"]
    assert t["entry_ms"] == T_E + k * H8 + M and t["exit_ms"] == t["entry_ms"] + HOLD_MIN * M
    assert i["sl"] == base.trades[0]["t4"]["sl"] == t["sl"] and i["sl_dist"] == base.trades[0]["t4"]["sl_dist"]
    assert i["T"] == T_E and funnel(r) == funnel(base)


def test_p2_emit_bar_print_is_busy_when_extreme():
    e = S.EXT["S"]
    r = S.run(S.Scenario(over={T_E: e, T_E + H8: e}), Variant(delay=1))
    assert funnel(r) == {"not_extreme": N_PRINTS - 2, "candidate": 1, "position_busy": 1} and len(r.trades) == 1


@pytest.mark.parametrize("arm", ARMS)
def test_p2_sl_crossed_before_the_delayed_fill(arm):
    f = T_E + H8 + M
    crossed = S.bar(f, o="56000") if arm == "L" else S.bar(f, o="64000")
    r = S.run(S.Scenario(arm=arm, bar_over={f: crossed}), Variant(delay=1))
    assert r.strategy.entry == {"sl_crossed_before_fill": 1} and r.trades == [] and r.strategy.state == "IDLE"


def test_p2_eligibility_is_evaluated_at_the_original_fill():
    late = S.D0 + 23 * DAY + 2 * H8                               # t + 6일 = 창 끝 직전(적격) · +3 인쇄 체결의 종료 봉 = t + 6일
    r = S.run(S.Scenario(over={late: S.EXT["S"]}), Variant(delay=3))
    assert funnel(r)["candidate"] == 1 and r.trades[0]["exit_ms"] == late + M + 6 * DAY


def test_p2_missing_emit_bar_is_a_run_failure():
    with pytest.raises(H.RunFailure) as ei:
        S.run(S.Scenario(drop={T_E + H8}), Variant(delay=1), eligible=lambda t: None)   # 술어가 막는 경로 — 술어를 대체해 도달
    assert isinstance(ei.value.__cause__, RunInvariantError)


@pytest.mark.parametrize("arm", ARMS)
def test_p3_inverts_direction_and_mirrors_the_sl(arm):
    r = S.run(S.Scenario(arm=arm), Variant(invert=True))
    t, i = r.trades[0], r.trades[0]["t4"]
    opp = Direction.LONG if arm == "S" else Direction.SHORT
    assert t["direction"] == opp.value == i["intent_dir"]
    want = D("60000") - D("3600") if opp is Direction.LONG else D("60000") + D("3600")
    assert D(i["intent_sl"]) == want == D(t["sl"]) and D(i["sl"]) == D("120000") - want
    ex = S.lines(r, "exit")[0]
    assert D(ex["funding_paid"]) == (D(1) if opp is Direction.LONG else D(-1)) * 15 * D(t["qty"]) * D("60000") * D("0.0001")


def test_variant_names_and_registered_values():
    assert [Variant().name, Variant(delay=1).name, Variant(delay=3).name, Variant(invert=True).name] == \
        ["base", "P2_print1", "P2_print3", "P3_invert"]
    for delay, invert in ((2, False), (5, False), (1, True)):
        with pytest.raises(ValueError):
            Variant(delay=delay, invert=invert)


# ── 구조 · 하네스 ────────────────────────────────────────────────────────────
def test_due_bar_is_never_a_boundary_bar():
    for k in range(0, 3 * 400):
        for delay in (0, 1, 3):
            fill = k * H8 + delay * H8 + M
            assert (fill + HOLD_MIN * M) % H8 == M


def test_fill_ref_allows_only_the_bar_being_decided():
    ref = H.FillRef(S.Scenario().bars())
    assert ref(T_E + M, T_E) == D("60000")
    for key in (T_E, T_E + 2 * M, T_E + H8 + M):
        with pytest.raises(RunInvariantError):
            ref(key, T_E)
    with pytest.raises(RunInvariantError):
        H.FillRef(S.Scenario(drop={T_E + M}).bars())(T_E + M, T_E)


def test_validate_prints_contract():
    good = S.Scenario().prints()
    H.validate_prints(good)
    for mutate in (lambda p: p.pop(10), lambda p: p.__setitem__(5, p[5] | {"T": p[5]["T"] + M}),
                   lambda p: p.__setitem__(5, p[5] | {"n_minutes": 470}), lambda p: p.__setitem__(5, p[5] | {"complete": False}),
                   lambda p: p.__setitem__(5, p[5] | {"p": "NaN"}), lambda p: p.__setitem__(5, p[5] | {"p": None}),
                   lambda p: p.append(p[-1])):
        bad = [dict(x) for x in good]
        mutate(bad)
        with pytest.raises(H.InputError):
            H.validate_prints(bad)


def test_validate_inputs_rejects_duplicate_bars_and_funding_buckets():
    sc = S.Scenario(n_days=1)
    with pytest.raises(H.InputError):
        H.validate_inputs([*sc.bars(), sc.bars()[-1]], sc.fundings())
    with pytest.raises(H.InputError):
        H.validate_inputs(sc.bars(), [*sc.fundings(), Funding(S.D0 + 5, S.RATE, S.FMARK)])


def test_load_rules_pins_the_69_snapshot(tmp_path):
    r = H.load_rules()
    assert r.commission.taker == D("0.0005")
    with pytest.raises(H.RulesSnapshotMismatch):
        H.load_rules(expected=A.RULES_SNAPSHOT_SHA256 | {"exchangeInfo": "0" * 64})


def test_fixture_rules_path_is_tests_only():
    src = (ROOT / "strategies" / "trial04" / "harness.py").read_text()
    assert "tests/ 전용" in src and "inspect.stack()" in src


def test_entry_day_outside_v_is_a_run_failure():
    """표본 규칙은 [t, t + 6일]과 앞 14일만 본다 — 진입일의 앞부분에 구멍이 있으면 진입일 ∉ V(C37): 실행 실패로 드러낸다."""
    with pytest.raises(H.RunFailure) as ei:
        S.run(S.Scenario(drop={T_E - 5 * H8 // 8}))                # 같은 날 03:00 봉
    assert isinstance(ei.value.__cause__, RunInvariantError)


def test_v_days_are_complete_days_with_a_defined_distribution():
    r = S.run(S.Scenario(prior=270 - 6, drop={S.D0 + 20 * DAY + 5 * M}, over={}))
    v = H.v_days(r.strategy, H.complete_days(S.Scenario(drop={S.D0 + 20 * DAY + 5 * M}).bars()))
    d0 = S.D0 // DAY
    assert d0 not in v and d0 + 1 not in v and d0 + 2 in v and d0 + 20 not in v and len(v) == 30 - 2 - 1


def test_strategy_object_rejects_unknown_arm():
    with pytest.raises(ValueError):
        Trial04("X", rules=S.RULES, prints=[], eligible=lambda t: None, fill_ref=lambda t, T: D(1))


def test_funnel_sum_equals_window_prints_for_a_busy_scenario():
    e = S.EXT["S"]
    r = S.run(S.Scenario(over={T_E: e, T_E + H8: e, T_E + 6 * DAY: e}, invalid={S.D0 + 3 * H8}, incomplete={S.D0 + 4 * H8}))
    assert sum(r.strategy.funnel.values()) == r.strategy.window_prints == N_PRINTS
    assert replace(TC_V3) == TC_V3


@pytest.mark.parametrize("arm", ARMS)
def test_sl_reference_is_the_fill_bars_mark_open_not_the_decision_close(arm):
    """C25: 결정 봉 종가는 60,000 · 체결 봉 시가는 60,100 → 기준가·SL·sl_dist는 60,100에서 나온다."""
    f = T_E + M
    r = S.run(S.Scenario(arm=arm, bar_over={f: S.bar(f, o="60100")}))
    t, i = r.trades[0], r.trades[0]["t4"]
    assert D(i["ref"]) == D("60100") and D(i["sl_dist"]) == D("3600") / D("60100")
    assert D(i["sl"]) == (D("63700") if arm == "S" else D("56500")) == D(t["sl"]) and D(t["entry_mark"]) == D("60100")
