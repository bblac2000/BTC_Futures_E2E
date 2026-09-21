"""단계 2a — 플라시보 P1(규약 a~f)·P4·P1 실행기의 엔진 동등성. 합성 입력만."""
from __future__ import annotations

import datetime as dt
import hashlib
from decimal import Decimal

from backtest import placebo as PL
from backtest import placebo_exec as PX
from backtest.data import MINUTE_MS as M
from backtest.data import Bar1m, Funding
from exchange.gate import Mode
from exchange.orders import Direction
from paper.engine import Engine, EntryIntent
from paper.sender import PaperSender
from paper.types import ExitReason, PositionClosed
from sizing.config import RegimeSizing, SizingLimits
from strategies.trial01 import anchor as A

D = Decimal
T0 = int(dt.datetime(2024, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
WIN_END = T0 + 600 * M - 1
REGIME = RegimeSizing("t1", D("0.01"), 50, 100)


def src(n: int) -> list[PL.SourceTrade]:
    return [PL.SourceTrade(i, T0 + i * 30 * M, T0 + i * 30 * M + (5 + 3 * (i % 4)) * M + 20_000, D("0.004") + D(i) / 10_000)
            for i in range(n)]


GRID = [T0 + i * M for i in range(600)]
ALWAYS = lambda t, d, s: True  # noqa: E731


# ── P1 결정론 ────────────────────────────────────────────────────────────────
def test_p1_two_runs_are_byte_identical_and_match_the_golden_hash():
    a = PL.p1_canonical_json(PL.p1_all(src(8), GRID, T0, WIN_END, ALWAYS, draws=25))
    b = PL.p1_canonical_json(PL.p1_all(src(8), GRID, T0, WIN_END, ALWAYS, draws=25))
    assert a == b
    #  골든: numpy 2.5.3 PCG64 스트림 + 규약 (c)(d)(e)의 호출 순서를 잠근다. 값이 바뀌면 사전등록 귀무분포가 재현되지 않는다
    assert hashlib.sha256(a.encode()).hexdigest() == GOLDEN_P1


GOLDEN_P1 = "68fda588965806daccfaea68ba9dda13a31cb3535a60ab7795947ea87edcf7fe"


def test_p1_rng_is_seeded_from_20260921_spawned_1000_ways():
    import numpy as np
    g = PL.p1_rng(7)
    ref = np.random.Generator(np.random.PCG64(np.random.SeedSequence(20260921).spawn(1000)[7]))
    assert g.integers(0, 10**9) == ref.integers(0, 10**9) and A.P1_MASTER_SEED == 20260921


def test_p1_draws_all_slots_first_then_places_longest_first_without_redrawing_pairs():
    s = PL.sort_source(src(6))
    r = PL.p1_draw(3, s, GRID, T0, WIN_END, ALWAYS)
    rng = PL.p1_rng(3)
    drawn = [(int(rng.integers(0, 6)), int(rng.integers(0, 2))) for _ in range(6)]
    assert r.ok and [(p.pair, p.direction) for p in r.placed] == drawn, "(c) 슬롯 전부 먼저: 쌍 → 방향 · 쌍은 다시 뽑지 않는다"
    assert all(p.h == s[p.pair].h and p.sl_dist == s[p.pair].sl_dist for p in r.placed), "(sl_dist, h)는 한 트레이드의 쌍"
    iv = sorted((p.entry_ms, p.entry_ms + p.h * M) for p in r.placed)
    assert all(a[1] <= b[0] for a, b in zip(iv, iv[1:], strict=False)), "반열린 점유 [t, t+h)는 겹치지 않는다"
    assert all(p.exit_minute_ms <= WIN_END for p in r.placed), "청산 분은 창 안"


def test_p1_eligible_minutes_need_mark_at_both_ends_and_stay_inside_the_window():
    grid = [t for t in GRID if t != T0 + 10 * M]
    el = PL.eligible_minutes(grid, 5, T0, WIN_END)
    assert T0 + 6 * M not in el and T0 + 10 * M not in el and T0 + 5 * M in el
    assert max(el) + 4 * M <= WIN_END - M + 1


def test_p1_a_slot_that_cannot_be_placed_fails_the_whole_draw_and_eleven_failures_are_unevaluable():
    long_trade = [PL.SourceTrade(0, T0, T0 + 10_000 * M, D("0.005"))]      # h > 창 → 적격 분 없음
    r = PL.p1_draw(0, long_trade, GRID, T0, WIN_END, ALWAYS)
    assert not r.ok and r.failed_slot == 0 and r.placed == ()
    fails = [PL.P1Draw(i, False, ()) for i in range(11)] + [PL.P1Draw(99, True, ())] * 989
    assert not PL.p1_evaluable(fails) and PL.p1_evaluable(fails[1:])


def test_p1_sizing_refusal_redraws_only_the_entry_minute():
    refused_once: set[int] = set()

    def picky(t, d, s):
        if t not in refused_once:
            refused_once.add(t)
            return False
        return True
    r = PL.p1_draw(2, src(3), GRID, T0, WIN_END, picky)
    rng = PL.p1_rng(2)
    drawn = [(int(rng.integers(0, 3)), int(rng.integers(0, 2))) for _ in range(3)]
    assert r.ok and [(p.pair, p.direction) for p in r.placed] == drawn


# ── P4 ──────────────────────────────────────────────────────────────────────
def test_p4_levels_are_one_to_one_on_the_tick_grid_inside_the_decision_time_range_and_seeded():
    levels = [PL.Level(i, "swing_low", T0 + i * 60 * M, T0 + i * 60 * M + 2880 * M, D("100") + i) for i in range(20)]
    rng_at = lambda t: (D("95.0"), D("105.0"))  # noqa: E731
    a = PL.p4_levels(0, levels, rng_at, D("0.1"))
    assert a == PL.p4_levels(0, levels, rng_at, D("0.1")) and a != PL.p4_levels(1, levels, rng_at, D("0.1"))
    assert [(x.level_id, x.kind, x.valid_from_ms, x.valid_to_ms) for x in a] == \
        [(x.level_id, x.kind, x.valid_from_ms, x.valid_to_ms) for x in levels]
    assert all(D("95.0") <= x.price <= D("105.0") and (x.price * 10) == int(x.price * 10) for x in a)


# ── P1 실행기: 정본 엔진과 같은 결과 ────────────────────────────────────────────
def _bars(n: int, px: str = "60000", *, crash_at: int | None = None) -> dict[int, Bar1m]:
    out = {}
    for i in range(n):
        p = D(px)
        lo = p * D("0.5") if crash_at == i else p - 5
        out[T0 + i * M] = Bar1m(T0 + i * M, px, str(p + 5), str(lo), px, "1", px, 1, "0", "0", px, str(p + 5), str(lo), px, "archive")
    return out


def test_time_exit_executor_matches_a_normal_engine_trade_exactly(rules):
    bars = _bars(20)
    fund = [Funding(T0 + 7 * M + 15, "0.0001", "60000")]
    res = PX.run_time_exit(bars, fund, entry_ms=T0, h=10, direction=0, sl_dist=D("0.005"), rules=rules,
                           limits=SizingLimits(), equity=D("1000"), regime=REGIME)
    assert res.ok and res.reason == "time_exit" and res.ret is not None
    # 같은 트레이드를 정상 엔진 경로로: SL 0.5%(닿지 않음) · TP 없음 · 같은 분에 시간 청산
    fill, dec = PX.sizing_decision(D("60000"), 0, D("0.005"), rules, SizingLimits(), D("1000"), REGIME)
    eng = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    eng.request_entry(EntryIntent(Direction.LONG, dec.sl, None, REGIME, decided_ms=T0 - 1, decision_mark=D("60000")))
    closed = None
    for i in range(10):
        b = bars[T0 + i * M]
        if i == 7:
            eng.on_funding(ts_ms=fund[0].funding_ms, rate=D("0.0001"), mark=D("60000"))
        eng.on_bar(PX.mark_bar(b))
    for ev in eng.close_now(ref_mark=D("60000"), ts_ms=T0 + 10 * M - 1, reason=ExitReason.MANUAL):
        if isinstance(ev, PositionClosed):
            closed = ev
    assert closed is not None
    assert closed.wallet_after - D("1000") == res.ret.net_pnl, "시간 청산 실행기 = 정본 엔진(체결·수수료·펀딩)"
    assert res.ret.net_bps < 0 and res.ret.gross_bps == 0, "가격이 제자리면 gross 0 · net은 비용만큼 음수"


def test_time_exit_executor_skips_interior_minutes_without_a_mark_bar(rules):
    """규약 (b)는 진입·청산 분의 mark만 요구한다 — 내부 결손 분(IS 2024-08-12 10:02·10:03 같은)은 건너뛰고,
    그 분에 든 펀딩은 그래도 정산한다. 결과 = 결손 분이 판정에 영향이 없는 봉(가격 제자리)과 같다."""
    full = _bars(20)
    gap = {t: b for t, b in full.items() if t not in (T0 + 4 * M, T0 + 5 * M)}
    fund = [Funding(T0 + 5 * M + 15, "0.0001", "60000")]                      # 결손 분 안의 펀딩
    kw = dict(entry_ms=T0, h=10, direction=0, sl_dist=D("0.005"), rules=rules, limits=SizingLimits(),
              equity=D("1000"), regime=REGIME)
    a = PX.run_time_exit(full, fund, **kw)                                       # type: ignore[arg-type]
    b = PX.run_time_exit(gap, fund, **kw)                                        # type: ignore[arg-type]
    assert b.ok and b.reason == "time_exit" and a == b


def test_time_exit_executor_uses_the_engine_liquidation_path(rules):
    res = PX.run_time_exit(_bars(20, crash_at=3), [], entry_ms=T0, h=10, direction=0, sl_dist=D("0.003"), rules=rules,
                           limits=SizingLimits(), equity=D("1000"), regime=REGIME)
    assert res.ok and res.reason == "liquidation" and res.ret is not None and res.ret.net_pnl < 0
    assert res.ret.gross_bps < 0


def test_time_exit_executor_reports_sizing_refusal(rules):
    res = PX.run_time_exit(_bars(5), [], entry_ms=T0, h=2, direction=1, sl_dist=D("0.05"), rules=rules,
                           limits=SizingLimits(), equity=D("1000"), regime=REGIME)
    assert not res.ok and res.reason == "sizing_refused"


def test_p1_null_distribution_is_byte_identical_across_two_runs(rules):
    """사용자 요구(2026-09-21): 같은 입력으로 P1을 두 번 돌리면 귀무분포가 바이트 동일해야 한다."""
    import json
    bars = _bars(600)
    grid = sorted(bars)
    fund = [Funding(T0 + 480 * M + 15, "0.0001", "60000")]
    lim = SizingLimits()

    def ok(t, d, s):
        fill, dec = PX.sizing_decision(bars[t].d("mark_open"), d, s, rules, lim, D("1000"), REGIME)
        return dec.ok

    def run() -> str:
        draws = PL.p1_all(src(6), grid, T0, WIN_END, ok, draws=15)
        dist = PX.p1_null_distribution(draws, bars, fund, rules=rules, limits=lim, equity=D("1000"), regime=REGIME)
        return json.dumps(dist, sort_keys=True, separators=(",", ":"))
    a, b = run(), run()
    assert a == b and len(json.loads(a)) == 15


def test_placebo_rejection_rules_match_the_preregistration_table():
    null = [float(i) for i in range(100)]                     # p95 = 94.05
    assert PL.p1_rejects(94.0, null) and not PL.p1_rejects(95.0, null)
    assert PL.p4_rejects(94.05, null) and not PL.p4_rejects(94.06, null), "P4는 p95 ≥ 원판이면 기각(경계 포함)"
    assert PL.p2_rejects(1.0, 1.0, 0.5) and not PL.p2_rejects(1.1, 1.0, 0.5)
    assert PL.p3_rejects(1.0, 1.0) and not PL.p3_rejects(1.0, 0.9)
    assert PL.variant_args() == {"P2_delay1": ["--delay", "1"], "P2_delay5": ["--delay", "5"], "P3_invert": ["--invert"]}
