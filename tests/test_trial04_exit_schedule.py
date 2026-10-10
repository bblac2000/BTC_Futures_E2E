"""트라이얼 #4 (c) — 체결 + 7,200분 시간 청산(규약 B13·B14 · r3 §1 "청산 (a) 시간" · 결정 5) · 5일 = 펀딩 15회 · 경계 분 체결.

종료 봉 t_f+7,200 = ① 펀딩 → ② 시가가 추정 청산가 너머면 청산 → ③ 아니면 시가에 time_exit(그 봉의 고가·저가 미판정) ·
t_f … t_f+7,199는 엔진 경로 그대로. 합성 봉만 · 규칙 = #69 스냅샷 · 한계 = (3, 30)((b) · 레지스트리 #72).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal as D
from pathlib import Path

import pytest

import strategies.trial04.exit_schedule as X
from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.engine_replay import ReplayContext, replay
from exchange.loader import rules_from_snapshot_dir
from exchange.orders import Direction, Intent, side_for
from paper.engine import EntryIntent
from paper.sender import adverse_fill_estimate
from paper.types import EntryFilled, ExitReason, PositionClosed
from sizing.config import RegimeSizing, SizingLimits
from strategies.trial03 import exit_schedule as X3
from strategies.trial04 import anchor as A
from strategies.trial04.exit_schedule import (
    EVAL_SPAN_MIN,
    EVAL_TAIL_MIN,
    HOLD_MIN,
    MissingExitBar,
    PositionBusyError,
    schedule,
)

ROOT = Path(__file__).resolve().parent.parent
RULES = rules_from_snapshot_dir(ROOT / A.RULES_SNAPSHOT_DIR, "BTCUSDT")
TICK = RULES.symbol_rules.tick_size
DAY0 = int(dt.datetime(2024, 3, 4, tzinfo=dt.UTC).timestamp() * 1000)        # 00:00Z · 합성 날짜(실데이터 아님)
H_MS = HOLD_MIN * MINUTE_MS
N = HOLD_MIN + 700                                                            # 재생 길이(체결 뒤 종료 봉까지 덮는다)
R6 = D("0.0006")
LIMITS = SizingLimits(leverage_range=(3, 30))
REGIME = RegimeSizing("t4", D("0.01"), 3, 30)
SL, SL_SHORT = D("59400"), D("60600")                                         # sl_dist 1% → L = 30
RATE, FMARK = D("0.0001"), D("60000")


def bar(ms: int, o: str = "60000", lo: str | None = None, hi: str | None = None, c: str | None = None) -> Bar1m:
    low, high, close = lo or o, hi or o, c or o
    return Bar1m(ms, o, high, low, close, "1", o, 1, "0", "0", o, high, low, close, "archive")


def flat(start: int, n: int, over: dict[int, Bar1m] | None = None, drop: set[int] | None = None) -> list[Bar1m]:
    out = []
    for i in range(n):
        t = start + i * MINUTE_MS
        if drop and t in drop:
            continue
        out.append((over or {}).get(t, bar(t)))
    return out


class Scripted:
    """정해진 분 마감에 의도 · 트라이얼 #4 일정(체결 + 7,200) · 종료 봉 누락 가드 — busy_check는 쓰지 않는다(B14)."""

    def __init__(self, decide_at: list[int], direction: Direction = Direction.LONG):
        self.direction, self.sl = direction, (SL if direction is Direction.LONG else SL_SHORT)
        self.sched = schedule()
        self.decide_at = set(decide_at)
        self.open_closes = 0
        self.eng = None

    def before_minute(self, b: Bar1m, eng) -> None:
        self.eng = eng
        self.sched.guard(b)

    def exit_at_bar_open(self, b: Bar1m) -> bool:
        return self.sched.exit_at_bar_open(b)

    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        self.sched.observe(bar, ctx.bar_events)
        if ctx.has_position:
            self.open_closes += 1
        if bar.open_ms in self.decide_at:
            return EntryIntent(self.direction, self.sl, None, REGIME, decided_ms=ctx.now_ms, decision_mark=bar.d("mark_close"))
        return None


def run(bars: list[Bar1m], decide: int, fundings: list[Funding] | None = None, direction: Direction = Direction.LONG):
    events: list[object] = []
    s = Scripted([decide], direction)
    r = replay(bars, fundings or [], s, rules=RULES, limits=LIMITS, equity=D("1000"), on_event=events.append,
               sizing_capital=D("1000"), slippage_rate=R6)
    return r, s, events


def closed(events: list[object]) -> PositionClosed:
    return next(e for e in events if isinstance(e, PositionClosed))


def entered(events: list[object]) -> EntryFilled:
    return next(e for e in events if isinstance(e, EntryFilled))


# ── 상수 · 시계 · 7,200봉 ────────────────────────────────────────────────────
def test_constants_and_reuse_of_the_trial3_clock_unchanged():
    assert (HOLD_MIN, EVAL_TAIL_MIN, EVAL_SPAN_MIN) == (7_200, 1_440, 8_640) and H_MS == 5 * 86_400_000
    s = schedule()
    assert type(s) is X3.TimeExitSchedule and s.hold_ms == H_MS and s.due is None
    assert MissingExitBar is X3.MissingExitBar and PositionBusyError is X3.PositionBusyError


def test_module_does_not_expose_the_decision_level_busy_gate():
    assert not hasattr(X, "busy_check") and "busy_check" not in X.__all__


def test_exit_at_fill_plus_7200_open_and_hold_is_7200_bars():
    d = DAY0 + 60 * MINUTE_MS
    r, s, ev = run(flat(DAY0, N), d)
    t = r.trades[0]
    tf = d + MINUTE_MS
    assert t["entry_ms"] == tf and t["exit_ms"] == tf + H_MS and t["exit_reason"] == str(ExitReason.TIME_EXIT)
    assert s.open_closes == HOLD_MIN                               # t_f … t_f+7,199 마감에 포지션 보유
    assert t["leverage"] == 30 and entered(ev).leverage == 30
    c = closed(ev)
    assert all(f.price == adverse_fill_estimate(side_for(Direction.LONG, Intent.EXIT), D("60000"), TICK, R6) for f in c.fills)
    assert r.open_at_end is None and s.sched.due is None
    s.sched.assert_no_due()


def test_predicate_true_only_at_due():
    s = schedule()
    tf = DAY0 + 5 * MINUTE_MS
    s.observe(bar(tf), [EntryFilled.__new__(EntryFilled)])
    assert s.due == tf + H_MS
    assert [s.exit_at_bar_open(bar(tf + k * MINUTE_MS)) for k in (7_199, 7_200, 7_201)] == [False, True, False]


def test_second_fill_while_scheduled_is_still_an_invariant_violation():
    s = schedule()
    s.observe(bar(DAY0), [EntryFilled.__new__(EntryFilled)])
    with pytest.raises(PositionBusyError):
        s.observe(bar(DAY0 + MINUTE_MS), [EntryFilled.__new__(EntryFilled)])


# ── 종료 봉 ──────────────────────────────────────────────────────────────────
def _exit_bar_case(o: str, lo: str | None = None, hi: str | None = None, direction: Direction = Direction.LONG):
    d = DAY0 + 60 * MINUTE_MS
    due = d + MINUTE_MS + H_MS
    return run(flat(DAY0, N, over={due: bar(due, o, lo, hi)}), d, direction=direction)


def test_exit_bar_open_beyond_liquidation_is_liquidation():
    r, _, ev = _exit_bar_case("50000")
    assert closed(ev).reason is ExitReason.LIQUIDATION and r.trades[0]["exit_reason"] == str(ExitReason.LIQUIDATION)


def test_exit_bar_open_beyond_sl_only_is_time_exit_at_open():
    r, _, ev = _exit_bar_case("59350")                                # SL 59400 너머 · 추정 청산가 위
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT
    assert all(f.price == adverse_fill_estimate(side_for(Direction.LONG, Intent.EXIT), D("59350"), TICK, R6) for f in c.fills)
    t = r.trades[0]
    assert D(t["exit_ref"]) == D("59350") and D(t["exit_ref"]) <= D(t["sl"])


def test_exit_bar_high_low_are_not_evaluated():
    r, _, ev = _exit_bar_case("60000", lo="50000", hi="70000")
    assert closed(ev).reason is ExitReason.TIME_EXIT and D(r.trades[0]["exit_ref"]) == D("60000")


@pytest.mark.parametrize("lo,reason", [("59350", ExitReason.SL), ("50000", ExitReason.LIQUIDATION)])
def test_intrabar_exit_in_last_held_bar_clears_the_schedule(lo, reason):
    d = DAY0 + 60 * MINUTE_MS
    last = d + MINUTE_MS + H_MS - MINUTE_MS                           # t_f + 7,199
    r, s, ev = run(flat(DAY0, N, over={last: bar(last, "60000", lo=lo)}), d)
    assert closed(ev).reason is reason and r.trades[0]["exit_ms"] // MINUTE_MS * MINUTE_MS == last
    assert s.sched.due is None and len(r.trades) == 1


def test_short_exit_bar_open_beyond_liquidation_is_liquidation():
    r, _, ev = _exit_bar_case("70000", direction=Direction.SHORT)
    assert closed(ev).reason is ExitReason.LIQUIDATION and r.trades[0]["direction"] == Direction.SHORT.value


def test_short_exit_bar_open_beyond_sl_only_is_time_exit_at_open():
    r, _, ev = _exit_bar_case("60650", direction=Direction.SHORT)     # SL 60600 너머 · 추정 청산가 아래
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT
    assert all(f.price == adverse_fill_estimate(side_for(Direction.SHORT, Intent.EXIT), D("60650"), TICK, R6) for f in c.fills)
    t = r.trades[0]
    assert D(t["exit_ref"]) == D("60650") and D(t["exit_ref"]) >= D(t["sl"])


# ── 종료 봉 누락 ─────────────────────────────────────────────────────────────
def test_missing_exit_bar_followed_by_later_bar_raises_before_any_engine_event():
    d = DAY0 + 60 * MINUTE_MS
    due = d + MINUTE_MS + H_MS
    events: list[object] = []
    s = Scripted([d])
    f = [Funding(due + MINUTE_MS, str(RATE), str(FMARK))]              # 누락 다음 봉의 펀딩 — 정산되면 안 된다
    with pytest.raises(MissingExitBar):
        replay(flat(DAY0, N, drop={due}), f, s, rules=RULES, limits=LIMITS, equity=D("1000"), on_event=events.append,
               sizing_capital=D("1000"), slippage_rate=R6)
    assert not [e for e in events if isinstance(e, PositionClosed)]
    assert s.eng is not None and s.eng.position is not None and s.eng.position.funding_paid == 0


def test_missing_exit_bar_at_end_of_input_raises_after_replay():
    d = DAY0 + 60 * MINUTE_MS
    last = d + MINUTE_MS + H_MS - MINUTE_MS                                   # 입력이 t_f+7,199에서 끝난다
    bars = flat(DAY0, (last - DAY0) // MINUTE_MS + 1)
    assert bars[-1].open_ms == last
    r, s, _ = run(bars, d)
    assert r.open_at_end is not None and s.sched.due == last + MINUTE_MS
    with pytest.raises(MissingExitBar):
        s.sched.assert_no_due()


# ── 펀딩: 5일 = 15회 · 경계 분 체결 · 경계 분 시간 청산 ──────────────────────
def _grid(start: int, n_bars: int) -> list[Funding]:
    end = start + n_bars * MINUTE_MS
    b = start - start % A.H8_MS
    return [Funding(x, str(RATE), str(FMARK)) for x in range(b, end, A.H8_MS) if x >= start]


def _one(qty: D) -> D:
    return qty * FMARK * RATE                                          # 롱 · 양수 율 → 지불


def test_a_7200_minute_hold_crosses_exactly_fifteen_boundaries():
    """구조적 사실: 경계는 480분 간격, 지불 = (체결 분, 체결 분 + 7,200] 안의 경계 → 모든 체결 분에서 정확히 15."""
    bounds = range(0, HOLD_MIN + 2 * 480, 480)
    assert {sum(1 for x in bounds if f < x <= f + HOLD_MIN) for f in range(480)} == {15}


@pytest.mark.parametrize("off_min", [61, 1, 0])
def test_replay_pays_fifteen_settlements(off_min):
    """체결 분이 경계 사이(61분 뒤) · 경계 바로 다음 분(r3 진입 T + 1분) · 경계 분 자신 — 모두 15회."""
    tf = DAY0 + A.H8_MS + off_min * MINUTE_MS
    r, _, ev = run(flat(DAY0, N), tf - MINUTE_MS, _grid(DAY0, N))
    t, c = r.trades[0], closed(ev)
    assert t["entry_ms"] == tf and c.reason is ExitReason.TIME_EXIT and c.funding_paid_usdt == 15 * _one(D(t["qty"]))


def test_fill_in_boundary_minute_does_not_pay_that_boundary():
    b = DAY0 + A.H8_MS
    r, _, ev = run(flat(DAY0, N), b - MINUTE_MS, [Funding(b, str(RATE), str(FMARK))])
    assert r.trades[0]["entry_ms"] == b and closed(ev).funding_paid_usdt == 0


def test_entry_at_t_plus_one_minute_does_not_pay_t():
    """r3 §1 "T 펀딩": 체결(T + 1분)이 T 뒤 → T 정산 없음 · 첫 정산 = T + 8h."""
    T = DAY0 + A.H8_MS
    r, _, ev = run(flat(DAY0, N), T, [Funding(T, str(RATE), str(FMARK)), Funding(T + A.H8_MS, str(RATE), str(FMARK))])
    t, c = r.trades[0], closed(ev)
    assert t["entry_ms"] == T + MINUTE_MS and c.funding_paid_usdt == _one(D(t["qty"]))


def test_time_exit_in_boundary_minute_pays_first():
    b = DAY0 + A.H8_MS                                                 # 체결 = 경계 분 → 종료 봉 = b + 5일 = 경계 분
    due = b + H_MS
    r, _, ev = run(flat(DAY0, N), b - MINUTE_MS, [Funding(due, str(RATE), str(FMARK))])
    t, c = r.trades[0], closed(ev)
    qty = D(t["qty"])
    assert t["exit_ms"] == due and due % A.H8_MS == 0 and c.reason is ExitReason.TIME_EXIT
    assert c.funding_paid_usdt == _one(qty)
    comm = sum((f.commission for f in entered(ev).fills + c.fills), D(0))
    fx, fe = c.fills[0].price, D(t["entry_fill"])
    assert D(t["wallet_after"]) - D(t["wallet_before"]) == -comm - _one(qty) + (fx - fe) * qty


def test_short_receives_fifteen_settlements():
    tf = DAY0 + A.H8_MS + MINUTE_MS
    r, _, ev = run(flat(DAY0, N), tf - MINUTE_MS, _grid(DAY0, N), direction=Direction.SHORT)
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT and c.funding_paid_usdt == -15 * _one(D(r.trades[0]["qty"]))   # 숏 · 양수 율 → 수취
