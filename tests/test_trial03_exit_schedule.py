"""트라이얼 #3 (c) — 체결 + 240분 시간 청산(§1 31행 · 결정 (A)) · 펀딩 00/08/16 · 240봉 보유 · position_busy · 종료 봉 누락.

계획 r4: 종료 봉 t_f+240 = ① 펀딩 → ② 시가가 추정 청산가 너머면 청산 → ③ 아니면 시가에 time_exit(그 봉의 고가·저가 미판정) ·
t_f … t_f+239는 엔진 경로 그대로(청산 → SL · 봉 안 고가·저가 · SL 체결 기준 = SL과 시가 중 불리한 쪽). 합성 봉만.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal as D
from pathlib import Path

import pytest

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.engine_replay import ReplayContext, replay
from exchange.loader import rules_from_snapshot_dir
from exchange.orders import Direction, Intent, side_for
from paper.engine import EntryIntent
from paper.sender import adverse_fill_estimate
from paper.types import EntryFilled, ExitReason, PositionClosed
from sizing.config import RegimeSizing, SizingLimits
from strategies.trial03.exit_schedule import (
    HOLD_MIN,
    MissingExitBar,
    PositionBusyError,
    TimeExitSchedule,
    busy_check,
)

ROOT = Path(__file__).resolve().parent.parent
RULES = rules_from_snapshot_dir(ROOT / "tests" / "fixtures" / "snapshots", "BTCUSDT")
TICK = RULES.symbol_rules.tick_size
DAY0 = int(dt.datetime(2025, 6, 2, tzinfo=dt.UTC).timestamp() * 1000)       # 00:00Z
H_MS = 240 * MINUTE_MS
R6 = D("0.0006")
REGIME = RegimeSizing("t", D("0.01"), 50, 100)
SL = D("59700")
SL_SHORT = D("60300")
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
    """정해진 분 마감에 롱 의도 · 트라이얼 #3 일정(체결 + 240) · busy 검사 · 종료 봉 누락 가드."""

    def __init__(self, decide_at: list[int], direction: Direction = Direction.LONG):
        self.direction, self.sl = direction, (SL if direction is Direction.LONG else SL_SHORT)
        self.sched = TimeExitSchedule(HOLD_MIN)
        self.decide_at = set(decide_at)
        self.log: list[dict] = []
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
            busy_check(ctx, self.log, bar.open_ms)
            return EntryIntent(self.direction, self.sl, None, REGIME, decided_ms=ctx.now_ms, decision_mark=bar.d("mark_close"))
        return None


def run(bars: list[Bar1m], decide: int, fundings: list[Funding] | None = None, direction: Direction = Direction.LONG):
    events: list[object] = []
    s = Scripted([decide], direction)
    r = replay(bars, fundings or [], s, rules=RULES, limits=SizingLimits(), equity=D("1000"), on_event=events.append,
               slippage_rate=R6)
    return r, s, events


def closed(events: list[object]) -> PositionClosed:
    return next(e for e in events if isinstance(e, PositionClosed))


# ── 시계 · 240봉 ─────────────────────────────────────────────────────────────
def test_constants():
    assert HOLD_MIN == 240 and H_MS == 14_400_000


def test_exit_at_fill_plus_240_open_and_hold_is_240_bars():
    d = DAY0 + 60 * MINUTE_MS
    r, s, ev = run(flat(DAY0, 400), d)
    t = r.trades[0]
    tf = d + MINUTE_MS
    assert t["entry_ms"] == tf and t["exit_ms"] == tf + H_MS and t["exit_reason"] == str(ExitReason.TIME_EXIT)
    assert s.open_closes == 240                                    # t_f … t_f+239 마감에 포지션 보유
    c = closed(ev)
    assert all(f.price == adverse_fill_estimate(side_for(Direction.LONG, Intent.EXIT), D("60000"), TICK, R6) for f in c.fills)
    assert r.open_at_end is None and s.sched.due is None
    s.sched.assert_no_due()


def test_predicate_true_only_at_due():
    s = TimeExitSchedule(HOLD_MIN)
    tf = DAY0 + 5 * MINUTE_MS
    s.observe(bar(tf), [EntryFilled.__new__(EntryFilled)])
    assert s.due == tf + H_MS
    assert [s.exit_at_bar_open(bar(tf + k * MINUTE_MS)) for k in (239, 240, 241)] == [False, True, False]


# ── 종료 봉(결정 (A)) ────────────────────────────────────────────────────────
def _exit_bar_case(o: str, lo: str | None = None, hi: str | None = None):
    d = DAY0 + 60 * MINUTE_MS
    due = d + MINUTE_MS + H_MS
    return run(flat(DAY0, 400, over={due: bar(due, o, lo, hi)}), d)


def test_exit_bar_open_beyond_liquidation_is_liquidation():
    r, _, ev = _exit_bar_case("50000")
    assert closed(ev).reason is ExitReason.LIQUIDATION and r.trades[0]["exit_reason"] == str(ExitReason.LIQUIDATION)


def test_exit_bar_open_beyond_sl_only_is_time_exit_at_open():
    r, _, ev = _exit_bar_case("59650")                                # SL 59700 너머 · 추정 청산가 위
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT
    assert all(f.price == adverse_fill_estimate(side_for(Direction.LONG, Intent.EXIT), D("59650"), TICK, R6) for f in c.fills)
    t = r.trades[0]
    assert D(t["exit_ref"]) == D("59650") and D(t["exit_ref"]) <= D(t["sl"])      # (f) 보고 부분 개수(X9)의 입력


def test_exit_bar_high_low_are_not_evaluated():
    r, _, ev = _exit_bar_case("60000", lo="50000", hi="70000")
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT and D(r.trades[0]["exit_ref"]) == D("60000")


@pytest.mark.parametrize("lo,reason", [("59650", ExitReason.SL), ("50000", ExitReason.LIQUIDATION)])
def test_intrabar_exit_in_last_held_bar_clears_the_schedule(lo, reason):
    d = DAY0 + 60 * MINUTE_MS
    last = d + MINUTE_MS + H_MS - MINUTE_MS                           # t_f + 239
    r, s, ev = run(flat(DAY0, 400, over={last: bar(last, "60000", lo=lo)}), d)
    assert closed(ev).reason is reason and r.trades[0]["exit_ms"] // MINUTE_MS * MINUTE_MS == last
    assert s.sched.due is None and len(r.trades) == 1


# ── 종료 봉 누락 · busy ──────────────────────────────────────────────────────
def test_missing_exit_bar_followed_by_later_bar_raises_before_any_engine_event():
    d = DAY0 + 60 * MINUTE_MS
    due = d + MINUTE_MS + H_MS
    events: list[object] = []
    s = Scripted([d])
    f = [Funding(due + MINUTE_MS, str(RATE), str(FMARK))]              # 누락 다음 봉의 펀딩 — 정산되면 안 된다
    with pytest.raises(MissingExitBar):
        replay(flat(DAY0, 400, drop={due}), f, s, rules=RULES, limits=SizingLimits(), equity=D("1000"),
               on_event=events.append, slippage_rate=R6)
    assert not [e for e in events if isinstance(e, PositionClosed)]
    assert s.eng is not None and s.eng.position is not None                  # 포지션은 열린 채(청산 안 됨)
    assert s.eng.position.funding_paid == 0                                  # 다음 봉의 펀딩이 정산되기 전에 멈췄다


def test_missing_exit_bar_at_end_of_input_raises_after_replay():
    d = DAY0 + 60 * MINUTE_MS
    last = d + MINUTE_MS + H_MS - MINUTE_MS                                   # 입력이 t_f+239에서 끝난다
    bars = flat(DAY0, (last - DAY0) // MINUTE_MS + 1)
    assert bars[-1].open_ms == last
    r, s, _ = run(bars, d)
    assert r.open_at_end is not None and s.sched.due == last + MINUTE_MS
    with pytest.raises(MissingExitBar):
        s.sched.assert_no_due()


def test_event_while_position_open_is_recorded_then_raises():
    d = DAY0 + 60 * MINUTE_MS
    s = Scripted([d, d + 10 * MINUTE_MS])
    with pytest.raises(PositionBusyError):
        replay(flat(DAY0, 400), [], s, rules=RULES, limits=SizingLimits(), equity=D("1000"), slippage_rate=R6)
    assert s.log == [{"ts_ms": d + 10 * MINUTE_MS, "reason": "position_busy"}]


# ── 펀딩 00/08/16 × 가로지름 / 경계 분 체결 / 경계 분 시간 청산 ─────────────────
BOUNDARIES = {"00": DAY0, "08": DAY0 + 480 * MINUTE_MS, "16": DAY0 + 960 * MINUTE_MS}


def _funding_run(b: int, fill: int):
    start = b - 300 * MINUTE_MS
    return run(flat(start, 900), fill - MINUTE_MS, [Funding(b, str(RATE), str(FMARK))])


def _one_settlement(qty: D) -> D:
    return qty * FMARK * RATE                                          # 롱 · 양수 율 → 지불


@pytest.mark.parametrize("name", ["00", "08", "16"])
def test_funding_crossed_during_hold_paid_once(name):
    b = BOUNDARIES[name]
    r, _, ev = _funding_run(b, b - 60 * MINUTE_MS)
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT and c.funding_paid_usdt == _one_settlement(D(r.trades[0]["qty"]))


@pytest.mark.parametrize("name", ["00", "08", "16"])
def test_fill_in_boundary_minute_pays_nothing(name):
    b = BOUNDARIES[name]
    r, _, ev = _funding_run(b, b)
    assert r.trades[0]["entry_ms"] == b and closed(ev).funding_paid_usdt == 0


@pytest.mark.parametrize("name", ["00", "08", "16"])
def test_time_exit_in_boundary_minute_pays_first(name):
    b = BOUNDARIES[name]
    r, _, ev = _funding_run(b, b - H_MS)
    t, c = r.trades[0], closed(ev)
    qty = D(t["qty"])
    assert t["exit_ms"] == b and c.reason is ExitReason.TIME_EXIT
    assert c.funding_paid_usdt == _one_settlement(qty)
    entry = next(e for e in ev if isinstance(e, EntryFilled))
    comm = sum((f.commission for f in entry.fills + c.fills), D(0))
    fx, fe = c.fills[0].price, D(t["entry_fill"])
    assert D(t["wallet_after"]) - D(t["wallet_before"]) == -comm - _one_settlement(qty) + (fx - fe) * qty


def test_a_240_minute_hold_pays_at_most_one_funding():
    """구조적 사실: 경계는 480분 간격, 지불 = (체결 분, 체결 분 + 240] 안의 경계 → 모든 체결 분에서 ≤ 1."""
    bounds = [0, 480, 960, 1440]
    assert max(sum(1 for x in bounds if f < x <= f + HOLD_MIN) for f in range(1440)) == 1


# ── 숏(Arm S도 판정 대상) ────────────────────────────────────────────────────
def _short_exit_bar(o: str, lo: str | None = None, hi: str | None = None):
    d = DAY0 + 60 * MINUTE_MS
    due = d + MINUTE_MS + H_MS
    return run(flat(DAY0, 400, over={due: bar(due, o, lo, hi)}), d, direction=Direction.SHORT)


def test_short_exit_bar_open_beyond_liquidation_is_liquidation():
    r, _, ev = _short_exit_bar("70000")
    assert closed(ev).reason is ExitReason.LIQUIDATION and r.trades[0]["direction"] == Direction.SHORT.value


def test_short_exit_bar_open_beyond_sl_only_is_time_exit_at_open():
    r, _, ev = _short_exit_bar("60350")                               # SL 60300 너머 · 추정 청산가 아래
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT
    assert all(f.price == adverse_fill_estimate(side_for(Direction.SHORT, Intent.EXIT), D("60350"), TICK, R6) for f in c.fills)
    t = r.trades[0]
    assert D(t["exit_ref"]) == D("60350") and D(t["exit_ref"]) >= D(t["sl"])      # X9 입력(숏)


@pytest.mark.parametrize("name", ["00", "08", "16"])
def test_short_funding_crossed_received_once(name):
    b = BOUNDARIES[name]
    r, _, ev = run(flat(b - 300 * MINUTE_MS, 900), b - 61 * MINUTE_MS, [Funding(b, str(RATE), str(FMARK))], direction=Direction.SHORT)
    c = closed(ev)
    assert c.reason is ExitReason.TIME_EXIT and c.funding_paid_usdt == -_one_settlement(D(r.trades[0]["qty"]))   # 숏 · 양수 율 → 수취
