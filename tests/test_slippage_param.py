"""트라이얼 #3 (b) — 슬리피지 매개변수(`replay` · `placebo_exec`) · 기본값(#7 2 bps) 불변 · 청산은 송신기를 거치지 않는다.

계획 r2 B1·B5: 기대 체결가는 `adverse_fill_estimate(side, ref, tick, rate)`와 **같다(==)** · 지갑 변화는 정확히 분해된다 ·
22 bps는 명목값(수수료 10 + 슬리피지 12)이다(진입 체결가 분모 때문에 net_bps는 정확히 −22가 아니다).
"""
from __future__ import annotations

import ast
import datetime as dt
from decimal import Decimal as D
from pathlib import Path

import pytest

from backtest import placebo_exec as PX
from backtest.data import MINUTE_MS, Bar1m
from backtest.engine_replay import ReplayContext, replay
from exchange.gate import Mode
from exchange.loader import rules_from_snapshot_dir
from exchange.orders import Direction, Intent, side_for
from paper.config import PAPER_SLIPPAGE_RATE
from paper.engine import Engine, EntryIntent
from paper.sender import PaperSender, adverse_fill_estimate
from paper.types import EntryFilled, ExitReason, PositionClosed
from sizing.config import RegimeSizing, SizingLimits

ROOT = Path(__file__).resolve().parent.parent
RULES = rules_from_snapshot_dir(ROOT / "tests" / "fixtures" / "snapshots", "BTCUSDT")
TICK = RULES.symbol_rules.tick_size
T0 = int(dt.datetime(2025, 6, 1, tzinfo=dt.UTC).timestamp() * 1000)
R6 = D("0.0006")
REGIME = RegimeSizing("t", D("0.01"), 50, 100)


def flat(n: int, p: str = "60000", lows: dict[int, str] | None = None) -> list[Bar1m]:
    out = []
    for i in range(n):
        lo = (lows or {}).get(i, p)
        out.append(Bar1m(T0 + i * MINUTE_MS, p, p, lo, p, "1", p, 1, "0", "0", p, p, lo, p, "archive"))
    return out


class OneShot:
    """분 0 마감에 진입 의도 하나 · 체결 분 + hold에 시간 청산(훅)."""

    def __init__(self, direction: Direction, sl: D, hold: int = 3):
        self.direction, self.sl, self.hold, self.fill_ms = direction, sl, hold, None

    def exit_at_bar_open(self, bar: Bar1m) -> bool:
        return self.fill_ms is not None and bar.open_ms == self.fill_ms + self.hold * MINUTE_MS

    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext):
        for ev in ctx.bar_events:
            if isinstance(ev, EntryFilled):
                self.fill_ms = bar.open_ms
        if bar.open_ms != T0:
            return None
        m = bar.d("mark_close")
        return EntryIntent(self.direction, self.sl, None, REGIME, decided_ms=ctx.now_ms, decision_mark=m)


def run(direction: Direction, sl: D, bars: list[Bar1m], **kw):
    events: list[object] = []
    r = replay(bars, [], OneShot(direction, sl), rules=RULES, limits=SizingLimits(), equity=D("1000"),
               on_event=events.append, **kw)
    return r, events


def _ref(f) -> D:
    assert f.ref_mark is not None
    return f.ref_mark


def _fills(events: list[object]):
    entry = next(e for e in events if isinstance(e, EntryFilled))
    close = next(e for e in events if isinstance(e, PositionClosed))
    return entry, close


@pytest.mark.parametrize("direction,sl", [(Direction.LONG, D("59700")), (Direction.SHORT, D("60300"))])
def test_time_exit_round_trip_at_6bps_exact(direction, sl):
    r, ev = run(direction, sl, flat(10), slippage_rate=R6)
    entry, close = _fills(ev)
    mark = D("60000")
    assert all(f.price == adverse_fill_estimate(side_for(direction, Intent.ENTRY), mark, TICK, R6) for f in entry.fills)
    assert all(f.price == adverse_fill_estimate(side_for(direction, Intent.EXIT), _ref(f), TICK, R6) for f in close.fills)
    assert all(f.raw["slippage_rate"] == "0.0006" for f in entry.fills + close.fills)
    t = r.trades[0]
    qty, fe = D(t["qty"]), D(t["entry_fill"])
    fx = close.fills[0].price
    sign = 1 if direction is Direction.LONG else -1
    comm_in = sum((f.commission for f in entry.fills), D(0))
    comm_out = sum((f.commission for f in close.fills), D(0))
    assert D(t["wallet_after"]) - D(t["wallet_before"]) == -comm_in - comm_out + sign * (fx - fe) * qty
    assert D(t["gross_bps"]) == 0
    assert abs(D(t["net_bps"]) + 22) < D("0.05")                  # 명목 22 bps(10 + 12) · 분모 = 수량 × 진입 체결가


def test_default_is_registry_7_two_bps():
    _, ev = run(Direction.LONG, D("59700"), flat(10))
    entry, close = _fills(ev)
    assert entry.fills[0].price == adverse_fill_estimate(side_for(Direction.LONG, Intent.ENTRY), D("60000"), TICK)
    assert close.fills[0].raw["slippage_rate"] == str(PAPER_SLIPPAGE_RATE)


def test_sl_exit_uses_the_same_rate():
    bars = flat(10, lows={3: "59650"})                              # 분 3에 SL(59700) 관통 · 추정 청산가 위
    _, ev = run(Direction.LONG, D("59700"), bars, slippage_rate=R6)
    _, close = _fills(ev)
    assert close.reason is ExitReason.SL
    assert all(f.price == adverse_fill_estimate(side_for(Direction.LONG, Intent.EXIT), _ref(f), TICK, R6) for f in close.fills)


class CountingSender(PaperSender):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.sent = 0

    def send_market(self, *a, **k):
        self.sent += 1
        return super().send_market(*a, **k)


def _restored(rate: D) -> tuple[Engine, CountingSender]:
    s = CountingSender(RULES, slippage_rate=rate)
    e = Engine(RULES, s, mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    e.restore_position({"direction": Direction.LONG.value, "qty": "0.1", "entry_price": "60000", "leverage": 50,
                        "sl": "0", "tp": None, "liq_price_est": "59000", "entry_commission": "3", "funding_paid": "0",
                        "opened_ms": T0, "liq_alerted": False, "next_funding_ms": T0 + 8 * 3_600_000},
                       ts_ms=T0, detail="test")
    e.wallet = D("997")
    return e, s


def test_liquidation_does_not_use_the_sender_and_ignores_the_rate():
    (e2, s2), (e6, s6) = _restored(PAPER_SLIPPAGE_RATE), _restored(R6)
    ev2 = e2.liquidate_if_open_beyond(D("58000"), ts_ms=T0 + MINUTE_MS)
    ev6 = e6.liquidate_if_open_beyond(D("58000"), ts_ms=T0 + MINUTE_MS)
    c2 = next(x for x in ev2 if isinstance(x, PositionClosed))
    c6 = next(x for x in ev6 if isinstance(x, PositionClosed))
    assert c2 == c6 and c2.fills == () and s2.sent == s6.sent == 0 and e2.wallet == e6.wallet


def test_placebo_exec_rate_reaches_sizing_quote_and_exit():
    fill6, dec6 = PX.sizing_decision(D("60000"), 0, D("0.005"), RULES, SizingLimits(), D("1000"), REGIME, slippage_rate=R6)
    assert fill6 == adverse_fill_estimate(side_for(Direction.LONG, Intent.ENTRY), D("60000"), TICK, R6)
    fill2, _ = PX.sizing_decision(D("60000"), 0, D("0.005"), RULES, SizingLimits(), D("1000"), REGIME)
    assert fill2 == adverse_fill_estimate(side_for(Direction.LONG, Intent.ENTRY), D("60000"), TICK)
    bars = {b.open_ms: b for b in flat(10)}
    def rte(**k):
        return PX.run_time_exit(bars, [], entry_ms=T0, h=5, direction=0, sl_dist=D("0.005"), rules=RULES,
                                limits=SizingLimits(), equity=D("1000"), regime=REGIME, **k)

    r6, r2 = rte(slippage_rate=R6), rte()
    assert r6.ok and r2.ok and r6.ret is not None and r2.ret is not None
    assert abs(r6.ret.net_bps + 22) < D("0.05") and abs(r2.ret.net_bps + 14) < D("0.05")
    assert r6.ret.gross_bps == r2.ret.gross_bps == 0


def test_no_non_default_rate_outside_trial03_and_tests():
    """B5 T6: `slippage_rate=` 인자 — 전달(`slippage_rate=slippage_rate`)은 engine_replay·placebo_exec 두 모듈만 · 다른 값은 strategies/trial03과 테스트만."""
    allowed_prefix = ("strategies/trial03/", "tests/")
    bad = []
    for base in ("backtest", "paper", "ops", "sizing", "exchange", "strategies", "scripts"):
        for p in (ROOT / base).rglob("*.py"):
            rel = str(p.relative_to(ROOT))
            if rel.startswith(allowed_prefix):
                continue
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Call):
                    for k in n.keywords:
                        passthrough = (isinstance(k.value, ast.Name) and k.value.id == "slippage_rate"
                                       and rel in ("backtest/engine_replay.py", "backtest/placebo_exec.py"))
                        if k.arg == "slippage_rate" and not passthrough:
                            bad.append(f"{rel}:{n.lineno}")
    assert bad == []
