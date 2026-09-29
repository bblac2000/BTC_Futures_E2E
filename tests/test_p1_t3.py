"""트라이얼 #3 (e) P1 — 날을 넘는 적격 분 · 체결 분 펀딩 제외 · 6 bps(배치·실행) · 튜플 시드 · 병합 불변식 · 결정론(계획 r2). 합성만."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import numpy as np
import pytest

from backtest import p1_core as C
from backtest import p1_t3 as P
from backtest import placebo_exec as PX
from backtest.data import MINUTE_MS, Funding
from sizing.config import SizingLimits
from strategies.trial03.config import REGIME
from strategies.trial03.harness import GRID, InputError, complete_days
from tests.fixtures import t3_scenario as S

ROOT = Path(__file__).resolve().parent.parent
M = MINUTE_MS
DAY = S.DAY
W0, W1 = S.WINDOW
LAST_OPEN = W1 + 1 - M


def brute(bars, fundings, h: int) -> list[int]:
    days = complete_days(bars)
    fund: dict[int, int] = {}
    for f in fundings:
        b = f.funding_ms - f.funding_ms % M
        fund[b] = fund.get(b, 0) + 1
    out = []
    t = W0
    while t <= LAST_OPEN:
        end = t + (h - 1) * M
        ok = end <= LAST_OPEN
        m = t
        while ok and m <= end:
            if m // DAY not in days or (m % DAY in GRID and fund.get(m, 0) != 1):
                ok = False
            m += M
        if ok:
            out.append(t)
        t += M
    return out


@pytest.mark.parametrize("case", ["clean", "missing_16h", "incomplete_day2"])
@pytest.mark.parametrize("h", [1, 7, 240, 500])
def test_cross_day_eligibility_equals_brute_force(case, h):
    sc = S.Scenario()
    bars, fund = sc.bars(), sc.fundings()
    if case == "missing_16h":
        fund = [f for f in fund if f.funding_ms != W0 + 16 * 3_600_000]
    if case == "incomplete_day2":
        bars = [b for b in bars if b.open_ms != W0 + DAY + 100 * M]
    el = P.CrossDayEligible(P.build_segments(bars, fund, S.WINDOW), h)
    assert [el[j] for j in range(len(el))] == brute(bars, fund, h)


def test_midnight_crossing_hold_needs_the_midnight_record():
    sc = S.Scenario()
    bars, fund = sc.bars(), sc.fundings()
    t = W0 + DAY - 120 * M                                              # 22:00 → 01:59(h 240 · 00:00 경계를 지난다)
    el = P.CrossDayEligible(P.build_segments(bars, fund, S.WINDOW), 240)
    assert t in {el[j] for j in range(len(el))}
    fund2 = [f for f in fund if f.funding_ms != W0 + DAY]
    el2 = P.CrossDayEligible(P.build_segments(bars, fund2, S.WINDOW), 240)
    assert t not in {el2[j] for j in range(len(el2))}


def test_window_edges():
    sc = S.Scenario()
    h = 240
    el = P.CrossDayEligible(P.build_segments(sc.bars(), sc.fundings(), S.WINDOW), h)
    assert el[0] == W0 and el[len(el) - 1] == LAST_OPEN - (h - 1) * M
    with pytest.raises(IndexError):
        el[len(el)]


def test_incomplete_day_excluded_at_helper_and_duplicate_rejected_at_run_boundary():
    sc = S.Scenario()
    bars, fund = sc.bars(), sc.fundings()
    short = [b for b in bars if b.open_ms != W0 + 5 * M]                 # 날 1 불완전
    segs = P.build_segments(short, fund, S.WINDOW)
    assert all(a >= W0 + DAY for a, _ in segs)
    dup = bars[:1500] + [bars[1499]] + bars[1500:]
    with pytest.raises(InputError):
        P.run_range("L", [], dup, fund, 0, 0)


# ── 시드 ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm,tag", [("L", 2), ("S", 3)])
def test_tuple_seed_streams_are_the_anchored_ones(arm, tag):
    for d in (0, 1, 999):
        a = C.p1_rng(P.CFGS[arm], d).integers(0, 2**31, 16)
        b = np.random.Generator(np.random.PCG64(np.random.SeedSequence((20260929, tag)).spawn(1000)[d])).integers(0, 2**31, 16)
        assert (a == b).all()
    assert not (C.p1_rng(P.CFGS["L"], 0).integers(0, 2**31, 16) == C.p1_rng(P.CFGS["S"], 0).integers(0, 2**31, 16)).all()


# ── 실행: 체결 분 펀딩 · 6 bps ────────────────────────────────────────────────
def _one(t: int, fundings: list[Funding], h: int = 240) -> D:
    sc = S.Scenario()
    bars = {b.open_ms: b for b in sc.bars()}
    dr = C.P1Draw(0, True, (C.PlacedSlot(0, 0, 0, h, D("0.005"), t),))
    return D(P.null_point(dr, bars, fundings, S.RULES)["mean_net_bps"])


def test_entry_minute_funding_is_never_charged():
    b = W0 + 8 * 3_600_000                                              # 08:00 경계 분에 체결
    base = _one(b, [])
    assert _one(b, [Funding(b, "0.01", "60000")]) == base
    assert _one(b, [Funding(b + 5, "0.01", "60000")]) == base            # 오프셋 기록도 제외(r3 §1 펀딩 행)
    crossed = _one(b - 60 * M, [Funding(b + 5, "0.01", "60000")])         # 07:00 체결 · 08:00을 지난다 → 지불
    assert crossed < _one(b - 60 * M, [])


def test_six_bps_at_execution_mutation():
    mean6 = _one(W0 + 60 * M, [])
    bars = {b.open_ms: b for b in S.Scenario().bars()}
    r2 = PX.run_time_exit(bars, [], entry_ms=W0 + 60 * M, h=240, direction=0, sl_dist=D("0.005"), rules=S.RULES,
                          limits=SizingLimits(leverage_range=(10, 30), liq_fee_on_liq_price=True), equity=D(1000), regime=REGIME)
    assert r2.ret is not None
    assert D(-23) < mean6 < D(-21) and D(-15) < r2.ret.net_bps < D(-13) and mean6 != r2.ret.net_bps


# ── 전체 경로 · 골든 · 결정론 ─────────────────────────────────────────────────
GOLDEN = ROOT / "tests" / "fixtures" / "golden_p1_trial03.json"


def _two_trade_part(arm: str) -> P.P1Part:
    r = S.run(S.Scenario(arm=arm, flushes=[S.F_DEFAULT, S.F_DEFAULT + 715]))
    assert len(r.trades) == 2
    sc = S.Scenario(arm=arm, flushes=[S.F_DEFAULT, S.F_DEFAULT + 715])
    return P.run_range_with_fixture_rules(arm, r.trades, sc.bars(), sc.fundings(), 0, 19, rules=S.RULES, window=S.WINDOW)


def part_digest(p: P.P1Part) -> str:
    return hashlib.sha256((p.draws_json + json.dumps(p.null, sort_keys=True)).encode()).hexdigest()


@pytest.mark.parametrize("arm", ["L", "S"])
def test_two_trade_source_matches_committed_golden_and_is_deterministic_across_processes(arm):
    p = _two_trade_part(arm)
    g = json.loads(GOLDEN.read_text())[arm]
    assert p.n_source == 2 and p.computable
    assert json.loads(p.draws_json)[:3] == g["first_draws"] and p.null[:3] == g["first_null"] and part_digest(p) == g["digest"]
    outs = {subprocess.run([sys.executable, "-m", "tests.fixtures.t3_p1_fixture", arm], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.strip() for _ in range(2)}
    assert outs == {g["digest"]}


def test_source_uses_decision_time_sl_dist():
    r = S.run(S.Scenario())
    src = P.source_trades(r.trades)
    assert src[0].sl_dist == D(r.trades[0]["t3"]["sl_dist"]) and src[0].h == 240


# ── 병합 불변식 ──────────────────────────────────────────────────────────────
def test_merge_checks():
    p = _two_trade_part("L")
    m = P.merge([p], draws_total=20)
    assert m["computable"] and m["n_source"] == 2 and len(m["draws"]) == 20 and m["failed"] + len(m["null"]) == 20
    with pytest.raises(P.P1Error):
        P.merge([p], draws_total=21)                                     # 추출 20이 없다
    bad_null = replace(p, null=p.null[1:])
    with pytest.raises(P.P1Error):
        P.merge([bad_null], draws_total=20)
    bad_n = replace(p, null=[dict(p.null[0], n=3)] + p.null[1:])
    with pytest.raises(P.P1Error):
        P.merge([bad_n], draws_total=20)
    bad_exits = replace(p, null=[dict(p.null[0], exits={"time_exit": 1, "liquidation": 0})] + p.null[1:])
    with pytest.raises(P.P1Error):
        P.merge([bad_exits], draws_total=20)
    with pytest.raises(P.P1Error):
        P.merge([p, replace(p, arm="S")], draws_total=20)


def test_zero_source_is_not_computable_and_failures_over_ten_not_evaluable():
    sc = S.Scenario()
    z = P.run_range_with_fixture_rules("L", [], sc.bars(), sc.fundings(), 0, 19, rules=S.RULES, window=S.WINDOW)
    m = P.merge([z], draws_total=20)
    assert not m["computable"] and m["draws"] == [] and not m["evaluable"]
    p = _two_trade_part("L")
    draws = json.loads(p.draws_json)
    for d in draws[:11]:
        d["ok"] = False
    failing = replace(p, draws_json=json.dumps(draws), null=[r for r in p.null if r["draw"] >= 11])
    assert not P.merge([failing], draws_total=20)["evaluable"]


def test_fixture_path_refuses_callers_outside_tests(tmp_path):
    caller = tmp_path / "evil.py"
    caller.write_text("from backtest.p1_t3 import run_range_with_fixture_rules\n"
                      "def go(*a, **k):\n    return run_range_with_fixture_rules(*a, **k)\n")
    import importlib.util
    spec = importlib.util.spec_from_file_location("evil_p1", caller)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sc = S.Scenario()
    with pytest.raises(P.P1Error):
        mod.go("L", [], sc.bars(), sc.fundings(), 0, 0, rules=S.RULES, window=S.WINDOW)


def test_exit_side_boundary_not_charged_in_p1_disclosed_asymmetry():
    """규약 47(공시): 기본 time_exit는 종료 봉 분의 펀딩을 먼저 낸다((c) 테스트) · P1 점유는 [t, t+h)라 버킷 t+h의 기록은 내지 않는다(§4 (b))."""
    b = W0 + 8 * 3_600_000
    t = b - 240 * M                                                      # 04:00 체결 → 청산 순간 = 08:00
    base = _one(t, [])
    assert _one(t, [Funding(b, "0.01", "60000")]) == base
    assert _one(t, [Funding(b + 5, "0.01", "60000")]) == base
    assert _one(t, [Funding(b - 60 * M, "0.01", "60000")]) != base      # 보유 중 07:00이면 지불(돌연변이 검사)


def test_duplicate_minute_makes_the_day_ineligible_at_the_helper():
    sc = S.Scenario()
    bars, fund = sc.bars(), sc.fundings()
    i = next(k for k, b in enumerate(bars) if b.open_ms == W0 + 5 * M)
    dup = bars[: i + 1] + [bars[i]] + bars[i + 1:]                         # 날 1에 중복 분(1,441행)
    segs = P.build_segments(dup, fund, S.WINDOW)
    assert segs and all(a >= W0 + DAY for a, _ in segs)                  # 날 1 전체가 빠진다


def test_crossed_boundary_is_settled_exactly_once(monkeypatch):
    from paper.engine import Engine
    calls: list[int] = []
    orig = Engine.on_funding

    def spy(self, *, ts_ms, rate, mark):
        calls.append(ts_ms)
        return orig(self, ts_ms=ts_ms, rate=rate, mark=mark)

    monkeypatch.setattr(Engine, "on_funding", spy)
    b = W0 + 8 * 3_600_000
    _one(b - 60 * M, [Funding(b + 5, "0.01", "60000"), Funding(b + DAY, "0.01", "60000")])
    assert calls == [b + 5]                                               # 보유 중 경계 하나 · 한 번만
