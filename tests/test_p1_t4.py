"""트라이얼 #4 (e) P1 — 판정 가능 술어의 적격 분 · h 7,200 고정 · 게이트/보고 전용 timing 스트림 · 로컬 실행기(원판 재현) · 병합(규약 D43~D53). 합성만."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backtest import p1_core as C
from backtest import p1_t4 as P
from backtest.data import Funding
from exchange.decimal_context import exec_context
from strategies.trial04 import anchor as A
from strategies.trial04.eligibility import Eligibility
from strategies.trial04.exit_schedule import HOLD_MIN
from tests.fixtures import t4_p1_fixture as FX
from tests.fixtures import t4_scenario as S

ROOT = Path(__file__).resolve().parent.parent
M, DAY, H8, T_E = S.M, S.DAY, S.H8, S.T_E
ARMS = ["S", "L"]
DIR = {"S": C.SHORT, "L": C.LONG}
SMALL = {arm: replace(P.CFGS[arm], draws=20) for arm in ARMS}


def base(arm: str, **kw):
    sc = S.Scenario(arm=arm, **kw)
    return sc, S.run(sc)


def by_t(sc: S.Scenario):
    return {b.open_ms: b for b in sc.bars()}


def run_slot(sc: S.Scenario, t: int, direction: int, sl_dist: str = "0.06", fundings=None) -> Any:
    """`SlotResult`(선택 필드가 많다 — 시험에서는 Any로 읽는다)."""
    return P.execute(by_t(sc), P.FundingIndex(sc.fundings() if fundings is None else fundings), entry_ms=t, direction=direction,
                     sl_dist=D(sl_dist), rules=S.RULES)


# ── 원판 쌍 · 적격 분 ────────────────────────────────────────────────────────
def test_source_uses_decision_sl_dist_and_every_slot_holds_7200_minutes():
    sc, r = base("L", bar_over={T_E + H8: S.bar(T_E + H8, lo="56000")})          # 원판은 SL로 8시간 만에 끝난다
    assert r.trades[0]["exit_reason"] == "sl"
    src = P.source_trades(r.trades)
    assert [(s.entry_ms, s.sl_dist, s.h) for s in src] == [(T_E + M, D(r.trades[0]["t4"]["sl_dist"]), HOLD_MIN)]


def test_eligible_minutes_are_the_predicate_over_the_window_grid():
    sc = S.Scenario()
    e = Eligibility(sc.bars(), sc.fundings(), window_start=sc.window[0], window_end=sc.window[1])
    mins = P.eligible_minutes(e, sc.window)
    assert mins[0] == S.D0 + 14 * DAY and mins[-1] == S.D0 + 24 * DAY - M and len(mins) == 10 * 1440
    assert mins == sorted(mins) and all(e(t) is None for t in (mins[0], mins[777], mins[-1]))
    assert e(mins[0] - M) == "atr_days" and e(mins[-1] + M) == "window_end"
    hole = S.Scenario(no_funding={S.D0 + 20 * DAY})                         # 그 경계를 (t, t + 6일]에 두는 t가 모두 빠진다
    eh = Eligibility(hole.bars(), hole.fundings(), window_start=hole.window[0], window_end=hole.window[1])
    mh = P.eligible_minutes(eh, hole.window)
    assert mh == [t for t in mins if not (t < S.D0 + 20 * DAY <= t + 6 * DAY)] and S.D0 + 20 * DAY in mh


def test_atr_prev_close_is_a_disclosed_report_only_count():
    sc = S.Scenario(drop={S.D0 + 1439 * M})                                 # 날 0의 23:59 봉 → 날 15의 원판은 막히지만 P1은 적격
    e = Eligibility(sc.bars(), sc.fundings(), window_start=sc.window[0], window_end=sc.window[1])
    mins = P.eligible_minutes(e, sc.window)
    #  날 0이 불완전 → 날 14는 술어에서 빠진다(앞 14일) · 날 15는 적격이지만 d − 15 종가가 없다
    assert mins[0] == S.D0 + 15 * DAY and len(mins) == 9 * 1440 and P.count_atr_prev_close_ok(mins, by_t(sc)) == len(mins) - 1440


def test_eligible_for_rejects_any_other_h():
    f = P.eligible_for_factory([1, 2, 3])
    got = f(HOLD_MIN)
    assert [got[i] for i in range(len(got))] == [1, 2, 3]
    with pytest.raises(P.P1Error):
        f(240)


# ── 스트림 ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm,key", [("S", 2), ("L", 3)])
def test_streams_are_the_anchored_children(arm, key):
    seed = (20260930, key)
    assert A.P1_SEEDS[arm] == seed
    for d in (0, 999):
        want = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed).spawn(1000)[d])).integers(0, 10**9, 5)
        assert list(P.rng_gate(P.CFGS[arm], d).integers(0, 10**9, 5)) == list(want)
        wt = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed).spawn(2000)[1000 + d])).integers(0, 10**9, 5)
        assert list(P.rng_timing(P.CFGS[arm], d).integers(0, 10**9, 5)) == list(wt) != list(want)
    a, b = np.random.SeedSequence(seed).spawn(2000)[:1000], np.random.SeedSequence(seed).spawn(1000)
    assert all(x.generate_state(2).tolist() == y.generate_state(2).tolist() for x, y in zip(a, b, strict=True))


class FakeRng:
    def __init__(self):
        self.calls: list[tuple[int, int]] = []

    def integers(self, lo: int, hi: int) -> int:
        self.calls.append((lo, hi))
        return len(self.calls) * 7919 % hi


def _three_source() -> list[dict]:
    return [{"trade_id": i, "entry_ms": S.D0 + (15 + i) * DAY + M, "t4": {"sl_dist": "0.06"}} for i in range(3)]


def test_gate_draws_pair_then_direction_and_timing_draws_pair_only(monkeypatch):
    sc = S.Scenario(n_days=45)
    e = Eligibility(sc.bars(), sc.fundings(), window_start=sc.window[0], window_end=sc.window[1])
    mins, bars, src = P.eligible_minutes(e, sc.window), by_t(sc), P.source_trades(_three_source())
    g, t = FakeRng(), FakeRng()
    monkeypatch.setattr(C, "p1_rng", lambda cfg, d: g)          # 게이트는 p1_core.p1_draw_generic 그대로(D46)
    monkeypatch.setattr(P, "rng_timing", lambda cfg, d: t)
    dg = P.draw(0, SMALL["S"], src, mins, bars, S.RULES)
    dt = P.draw_timing(0, SMALL["S"], src, mins, bars, S.RULES, "S")
    assert g.calls[:6] == [(0, 3), (0, 2)] * 3 and all(c == (0, len(mins)) for c in g.calls[6:]) and len(g.calls) >= 9
    assert t.calls[:3] == [(0, 3)] * 3 and all(c == (0, len(mins)) for c in t.calls[3:]) and len(t.calls) >= 6
    assert dg.ok and dt.ok and {p.direction for p in dt.placed} == {C.SHORT}
    assert all(p.h == HOLD_MIN for p in dg.placed + dt.placed)
    for dr in (dg, dt):
        ts = sorted(p.entry_ms for p in dr.placed)
        assert all(y - x >= HOLD_MIN * M for x, y in zip(ts, ts[1:], strict=False))        # 점유 [t, t + 7,200분) 겹침 없음
    monkeypatch.setattr(P, "rng_timing", lambda cfg, d: FakeRng())
    assert {p.direction for p in P.draw_timing(0, SMALL["L"], src, mins, bars, S.RULES, "L").placed} == {C.LONG}


# ── 실행기: 원판 재현(두 번째 체결 모델이 없다) ───────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("case", ["funding15", "no_funding", "due_gap_liquidation"])
def test_executor_reproduces_the_base_trade_byte_for_byte(arm, case):
    kw: dict = {}
    due = T_E + M + HOLD_MIN * M
    if case == "due_gap_liquidation":
        kw["bar_over"] = {due: S.bar(due, o="70000" if arm == "S" else "50000")}
    sc, r = base(arm, **kw)
    fundings = [] if case == "no_funding" else sc.fundings()
    if case == "no_funding":
        r = S.H.run_arm_with_fixture_rules(sc.bars(), [], sc.prints(), arm, S.BASE, rules=S.RULES, window=sc.window,
                                           eligible=lambda t: None)
    t, ex = r.trades[0], S.lines(r, "exit")[0]
    got = run_slot(sc, t["entry_ms"], DIR[arm], t["t4"]["sl_dist"], fundings)
    assert got.reason == t["exit_reason"] == ("liquidation" if case == "due_gap_liquidation" else "time_exit")
    assert str(got.wallet_after) == t["wallet_after"] and str(got.ret.net_bps) == t["net_bps"] and str(got.ret.gross_bps) == t["gross_bps"]
    assert got.exit_ts == t["exit_ms"] == ex["ts_ms"] and str(got.funding_paid) == ex["funding_paid"]
    assert str(got.qty) == t["qty"] and got.leverage == t["leverage"] and str(got.fill) == t["entry_fill"]


@pytest.mark.parametrize("arm", ARMS)
def test_wallet_identity_for_a_time_exit(arm):
    sc = S.Scenario(arm=arm)
    got = run_slot(sc, T_E + M, DIR[arm])
    sign = D(1) if arm == "L" else D(-1)
    assert got.reason == "time_exit" and got.funding_paid == sign * 15 * got.qty * D("60000") * D("0.0001")
    assert got.price_pnl == sign * got.qty * (got.exit_fill - got.fill) and got.funding_cf == -got.funding_paid
    assert got.wallet_after - D(1000) == got.price_pnl + got.funding_cf - got.commission
    assert got.commission == got.qty * got.fill * D("0.0005") + got.qty * got.exit_fill * D("0.0005")


@pytest.mark.parametrize("arm", ARMS)
def test_entry_minute_funding_is_excluded_exact_and_offset(arm):
    sc = S.Scenario(arm=arm)
    t = T_E + H8                                                            # 경계 분에서 시작하는 슬롯
    clean = run_slot(sc, t, DIR[arm])
    extra = [f for f in sc.fundings() if f.funding_ms != t] + [Funding(t + 17, "0.01", "60000")]
    assert run_slot(sc, t, DIR[arm], fundings=extra).wallet_after == clean.wallet_after
    assert abs(clean.funding_paid) == 15 * clean.qty * D("60000") * D("0.0001")      # (t, t + 5일] = 15 · t 자신은 제외


def test_due_minute_funding_is_paid_before_the_exit():
    sc = S.Scenario(arm="L")
    t = T_E + H8                                                            # 종료 분 = 경계 분
    due = t + HOLD_MIN * M
    only_due = [Funding(due, "0.0001", "60000")]
    got = run_slot(sc, t, C.LONG, fundings=only_due)
    assert got.exit_ts == due and got.funding_paid == got.qty * D("60000") * D("0.0001")
    assert run_slot(sc, t, C.LONG, fundings=[Funding(due + M, "0.0001", "60000")]).funding_paid == 0


@pytest.mark.parametrize("arm", ARMS)
def test_intrabar_liquidation_mid_hold_and_its_identity(arm):
    mid = T_E + M + 3 * DAY
    wick = S.bar(mid, lo="40000") if arm == "L" else S.bar(mid, hi="80000")
    sc = S.Scenario(arm=arm, bar_over={mid: wick}, n_days=30)
    got = run_slot(sc, T_E + M, DIR[arm], fundings=[])
    assert got.reason == "liquidation" and mid < got.exit_ts < mid + M
    n = got.qty * got.fill
    fee = S.RULES.symbol_rules.liquidation_fee
    with exec_context():                                                    # 엔진의 실행 문맥(34자리)에서의 항등식
        want = D(1000) - n / D(got.leverage) - got.qty * got.liq_price_est * fee
    assert got.wallet_after == want                                         # D51 · C26
    assert got.price_pnl is None and got.ret.net_pnl == got.wallet_after - D(1000)


def test_missing_bar_inside_the_span_is_an_error_not_a_skip():
    sc = S.Scenario(drop={T_E + M + DAY})
    with pytest.raises(P.P1Error):
        run_slot(sc, T_E + M, C.LONG)


def test_sizing_refusal_is_reported_not_raised():
    got = run_slot(S.Scenario(), T_E + M, C.SHORT, sl_dist="0.20")           # 명목 50 → 수량 내림 뒤 거부
    assert not got.ok and got.reason == "sizing_refused"


# ── 조각 · 병합 · 결정론 ─────────────────────────────────────────────────────
GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "golden_p1_trial04.json").read_text())


@pytest.mark.parametrize("arm", ARMS)
def test_two_trade_source_matches_committed_golden_and_is_deterministic_across_processes(arm):
    p = FX.part(arm)
    assert p.n_source == 2 and p.computable and FX.digest(p) == GOLDEN[arm]
    out = subprocess.run([sys.executable, "-m", "tests.fixtures.t4_p1_fixture", arm], capture_output=True, text=True, cwd=ROOT,
                         check=True)
    assert out.stdout.strip() == GOLDEN[arm]


@pytest.mark.parametrize("arm", ARMS)
def test_null_rows_shape_and_timing_direction(arm):
    p = FX.part(arm, 0, 5)
    for rows in (p.null, p.timing_null):
        for r in rows:
            assert set(r) == {"draw", "n", "mean_net_bps", "exits", "price_pnl_sum", "funding_cf_sum", "commission_sum",
                              "liquidated_net_sum"}
            assert r["n"] == 2 and sum(r["exits"].values()) == 2 and set(r["exits"]) == {"time_exit", "liquidation"}
    td = json.loads(p.timing_draws_json)
    assert all(pl[2] == DIR[arm] for d in td for pl in d["placed"]) and len(td) == 6 == len(json.loads(p.draws_json))
    sign = D(-1) if arm == "S" else D(1)
    assert all(sign * D(r["funding_cf_sum"]) < 0 for r in p.timing_null)      # 양수 율: 롱은 내고 숏은 받는다
    assert p.n_eligible == 20 * 1440 and p.n_eligible_atr_prev_close_ok == 19 * 1440      # 날 14는 d − 15가 입력 밖


def test_merge_checks_and_timing_is_a_separate_block():
    a, b = FX.part("S", 0, 9), FX.part("S", 10, 19)
    m = P.merge([b, a], draws_total=20)
    assert m["computable"] and m["n_source"] == 2 and [d["draw"] for d in m["draws"]] == list(range(20))
    assert m["failed"] == 0 and m["evaluable"] and set(m["timing"]) == {"draws", "null", "failed"}
    assert [r["draw"] for r in m["timing"]["null"]] == list(range(20)) and "evaluable" not in m["timing"]
    for bad in ([a], [a, a], [a, replace(b, arm="L")], [a, replace(b, n_source=3)], [a, replace(b, null=b.null[:-1])],
                [a, replace(b, timing_null=b.timing_null[:-1])]):
        with pytest.raises(P.P1Error):
            P.merge(bad, draws_total=20)


def test_zero_source_is_not_computable():
    sc = S.Scenario()
    p = P.run_range_with_fixture_rules("S", [], sc.bars(), sc.fundings(), 0, 19, rules=S.RULES, window=sc.window)
    assert not p.computable and p.draws_json == "[]" and p.null == [] and p.timing_null == []
    m = P.merge([p], draws_total=20)
    assert m == {"arm": "S", "computable": False, "n_source": 0, "draws": [], "null": [], "failed": 0, "evaluable": False,
                 "timing": {"draws": [], "null": [], "failed": 0}}


def test_gate_failures_over_the_limit_are_not_evaluable_but_timing_failures_are_only_reported():
    a = FX.part("S", 0, 19)
    draws = json.loads(a.draws_json)
    for d in draws[:11]:
        d["ok"], d["failed_slot"] = False, 0
    cut = replace(a, draws_json=json.dumps(draws), null=a.null[11:])
    assert not P.merge([cut], draws_total=20)["evaluable"]
    tdraws = json.loads(a.timing_draws_json)
    for d in tdraws[:11]:
        d["ok"], d["failed_slot"] = False, 0
    m = P.merge([replace(a, timing_draws_json=json.dumps(tdraws), timing_null=a.timing_null[11:])], draws_total=20)
    assert m["evaluable"] and m["timing"]["failed"] == 11


def test_fixture_path_refuses_callers_outside_tests(tmp_path):
    script = tmp_path / "outside.py"
    script.write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nfrom backtest import p1_t4 as P\n"
                      "try:\n    P.run_range_with_fixture_rules('S', [], [], [], 0, 0, rules=None, window=(0, 1))\n"
                      "except P.P1Error as e:\n    print('refused')\n")
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=tmp_path)
    assert out.stdout.strip() == "refused", out.stderr


def test_run_range_argument_checks():
    sc = S.Scenario()
    for arm, lo, hi in (("X", 0, 0), ("S", 5, 4), ("S", 0, 1000)):
        with pytest.raises(P.P1Error):
            P.run_range_with_fixture_rules(arm, [], sc.bars(), sc.fundings(), lo, hi, rules=S.RULES, window=sc.window)


@pytest.mark.parametrize("arm", ARMS)
def test_due_bar_high_low_are_not_evaluated(arm):
    """종료 봉은 시가만 본다(D49): 그 봉의 고가·저가가 추정 청산가를 넘어도 시가에 TIME_EXIT."""
    due = T_E + M + HOLD_MIN * M
    sc = S.Scenario(arm=arm, bar_over={due: S.bar(due, lo="30000", hi="90000")})
    got = run_slot(sc, T_E + M, DIR[arm])
    assert got.reason == "time_exit" and got.exit_ts == due
