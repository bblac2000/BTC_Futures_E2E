"""layer 8 런타임 — 피드 → 엔진 → DB → 안전 게이트 → 텔레그램을 **한 소유자**가 묶는다.

## 스레드 소유권 (Codex 검토 질문 대상)
- 엔진·`SafetyGate`·`CommandBot`·sqlite 연결은 **asyncio 루프 스레드 하나만** 만진다: `on_mark`·`on_kline`(피드 콜백) ·
  `safety_tick`(1초 벽시계 태스크) · 컨트롤러 메서드(`safety_tick` 안에서 `CommandBot`이 부른다).
- 텔레그램 폴 스레드는 `TelegramPoller.fetch()`(네트워크·offset)만 하고 받은 업데이트를 `inbox`에 넣는다.
  발송 스레드는 `outbox`의 행동을 실행한다. 두 스레드는 엔진·게이트·봇 상태를 바꾸지 않는다.
- 그래서 `/close`의 청산은 틱 처리 중간에 끼어들 수 없다(같은 스레드에서 차례로 돈다).

## 안전 경로
- **진입 게이트는 하나**: `entry_blockers()` = 엔진 차단 사유(`engine:`) ∪ `SafetyGate.entry_blockers()` ∪ 런타임 사유(`db:`).
  `submit_entry`만 `Engine.request_entry`를 부른다 · 결정 뒤 체결 전에 게이트가 닫히면 대기 진입을 버리고 기록한다.
- **stale은 벽시계로 판정한다**(데이터가 안 오면 봉 콜백도 안 온다): `safety_tick` → `StaleDataGuard.update` →
  레지스트리 #12 `close`면 마지막 mark로 `close_now(STALE_DATA)` · 정지가 계속되는 동안 틱마다 재시도 · 청산마다 알림.
- **봉마다**(마감 kline): 봉 기록 → (LIVE) positionRisk → 거래소 flat · 내부 보유면 `Engine.vanish`(주문 없음) + 거래소 지갑
  재동기화(`sync_wallet` + `KillSwitch.sync_flat_wallet`) → 3자 대사 → 일일 손실 equity → account_snapshots → 상태 저장(바뀔 때만).
- 이벤트 처리 순서: 킬스위치 관측(기록 실패와 무관하게) → DB 기록(실패하면 보관 후 매 틱 재시도 + 진입 금지) → 알림 → 스냅샷.
- 킬스위치·stale·차단 해제 같은 운영 사건은 `engine_events`에 `record_ops_event`로 남긴다.

## 사용자 결정 반영 (레지스트리 #11·#12·#13 · 2026-09-16)
- `/stop` = 진입 차단 + 전량 청산 · `/close` = 청산만 · `/pause` = 진입 차단, 포지션 유지.
- `/start`는 일일 손실 트립 날짜에 아무것도 바꾸지 않는다("blocked by daily-loss limit until 00:00 UTC").
- LIVE 소실 손익은 추정하지 않는다 — 거래소 지갑으로 재동기화하고 그 차이가 `WalletResynced`·account_snapshots에 남는다.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import queue
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from data.feed import KlineEvent
from db import record as R
from exchange.gate import Mode
from notify.bot import Answer, CommandBot, Send
from paper.engine import Engine, EntryIntent, EntryRefused
from paper.types import (
    EntriesBlocked,
    EntryFilled,
    EntrySkipped,
    ExitFailed,
    ExitReason,
    FundingMissed,
    FundingSettled,
    LiquidationThresholdCrossed,
    MarkTick,
    PositionClosed,
    PositionReduced,
    PositionRisk,
    PositionVanished,
    WalletResynced,
)
from safety.gate import SafetyGate
from safety.killswitch import KillSwitchTripped
from safety.rate_guard import RateLimitGuard
from safety.reconcile import reconcile

logger = logging.getLogger(__name__)

SNAPSHOT_EVENTS = (EntryFilled, PositionClosed, PositionReduced, PositionVanished, WalletResynced, FundingSettled)


@dataclass(frozen=True)
class ExchangeAccount:
    """LIVE 거래소 계좌 요약(USDT) — 원문은 `raw`로 account_snapshots에 남는다."""
    wallet_balance: Decimal
    margin_balance: Decimal | None
    available_balance: Decimal | None
    isolated_margin: Decimal | None
    unrealized_pnl: Decimal | None
    raw: dict[str, Any] = field(default_factory=dict)


class ExchangeReader(Protocol):
    """LIVE 전용 읽기(서명 GET) — PAPER 런타임은 이것을 받지 않는다(레지스트리 #6)."""

    def position_risk(self) -> PositionRisk: ...

    def account(self) -> ExchangeAccount: ...


def _fmt(x: Decimal | None, q: str = "0.01") -> str:
    return "-" if x is None else str(x.quantize(Decimal(q)))


def _utc_day_start_ms(ts_ms: int) -> int:
    d = dt.datetime.fromtimestamp(ts_ms / 1000, dt.UTC).date()
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.UTC).timestamp() * 1000)


class BotRuntime:
    def __init__(self, *, engine: Engine, gate: SafetyGate, con: sqlite3.Connection, symbol: str,
                 clock_ms: Callable[[], int], exchange: ExchangeReader | None = None,
                 rate_guard: RateLimitGuard | None = None, status_path: Path | None = None):
        if (engine.mode is Mode.LIVE) != (exchange is not None):
            raise ValueError("LIVE는 거래소 읽기(ExchangeReader)가 필요하고 PAPER는 받지 않는다(레지스트리 #6)")
        self.engine, self.gate, self.con, self.symbol = engine, gate, con, symbol
        self.mode = engine.mode
        self.clock_ms, self.exchange, self.rate_guard, self.status_path = clock_ms, exchange, rate_guard, status_path
        self.bot: CommandBot | None = None
        self.poller: Any = None                                   # TelegramPoller(handle만 쓴다)
        self.inbox: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        self.outbox: queue.SimpleQueue[Send | Answer] = queue.SimpleQueue()
        self.last_mark: Decimal | None = None
        self.last_mark_ms: int | None = None
        self.last_bar_open_ms: int | None = None
        self.unrecorded: list[tuple[list[object], Decimal | None]] = []
        self.db_errors = 0
        self.bar_conflicts = 0
        self.wallet_resync_due = False
        self.last_reconcile_detail: str | None = None
        self._intent_tp: Decimal | None = None
        self._saved_state: str | None = None
        self._last_exit_failure: str | None = None
        self.counts: dict[str, int] = {"ticks": 0, "bars": 0, "safety_ticks": 0, "stale_closes": 0, "alerts": 0}

    # ── 알림 ────────────────────────────────────────────────────────────────
    def alert(self, text: str, *, important: bool = False) -> None:
        self.counts["alerts"] += 1
        logger.info("알림: %s", text.splitlines()[0])
        if self.bot is None:
            return
        for a in self.bot.alert(text, important=important, now_ms=self.clock_ms()):
            self.outbox.put(a)

    # ── 진입 게이트(하나) ───────────────────────────────────────────────────
    def entry_blockers(self) -> list[str]:
        out = [f"engine:{r}" for r in self.engine.entries_blocked]
        out += self.gate.entry_blockers()
        if self.unrecorded:
            out.append(f"db:unrecorded_events({len(self.unrecorded)})")
        if self.wallet_resync_due:
            out.append("exchange:wallet_resync_due")
        return out

    def submit_entry(self, intent: EntryIntent) -> None:
        blockers = self.entry_blockers()
        if blockers:
            raise EntryRefused(f"진입 게이트 닫힘: {' · '.join(blockers)}")
        self.engine.request_entry(intent)
        self._intent_tp = intent.tp

    def _cancel_pending_if_blocked(self, ts_ms: int) -> None:
        if self.engine.pending is None:
            return
        blockers = self.entry_blockers()
        if blockers:
            self.handle_events(self.engine.cancel_pending(ts_ms, " · ".join(blockers)), ts_ms)

    # ── 피드 콜백 ───────────────────────────────────────────────────────────
    def on_mark(self, t: MarkTick) -> None:
        self.counts["ticks"] += 1
        self.last_mark, self.last_mark_ms = t.mark, t.ts_ms
        self._cancel_pending_if_blocked(t.ts_ms)
        self.handle_events(self.engine.on_tick(t), t.ts_ms)

    def on_kline(self, k: KlineEvent) -> None:
        if not k.closed:
            return
        self.counts["bars"] += 1
        self.last_bar_open_ms = k.open_ms
        bar = R.BarRow(k.open_ms, k.close_ms, k.open, k.high, k.low, k.close, k.volume, k.quote_volume, k.trades,
                       k.taker_buy_base, k.taker_buy_quote)
        self.record_bar(bar, source="ws")
        self.on_bar_close(k.event_ms)

    def record_bar(self, bar: R.BarRow, *, source: str) -> str | None:
        try:
            res = R.record_bar(self.con, bar, mode=self.mode.value, symbol=self.symbol, source=source)
        except (sqlite3.Error, R.TransactionOpen) as e:
            self.db_errors += 1
            self.alert(f"🔴 봉 기록 실패 {bar.open_ms}: {type(e).__name__}: {e}", important=True)
            return None
        if res == "conflict":
            self.bar_conflicts += 1
            self.alert(f"⚠️ 봉 {bar.open_ms} 값 충돌({source}) — 덮어쓰지 않음")
        return res

    # ── 봉마다 ──────────────────────────────────────────────────────────────
    def on_bar_close(self, ts_ms: int) -> None:
        pr: PositionRisk | None = None
        err: str | None = None
        if self.mode is Mode.LIVE:
            assert self.exchange is not None
            if self.rate_guard is not None and self.rate_guard.check(ts_ms).relax_polling:
                err = "rate_limit_relax(80%)"                       # 스킵 → exchange_unavailable(다음 성공으로 해제)
            else:
                try:
                    pr = self.exchange.position_risk()
                except Exception as e:  # noqa: BLE001 — 조회 실패는 대사 사유(자동 해제)로
                    err = f"{type(e).__name__}: {e}"
            if pr is not None and pr.amt == 0 and self.engine.position is not None:
                #  사용자 2026-09-16: 거래소 flat · 내부 보유 → 주문 없이 내부 close(PositionVanished) · 손익은 지갑 재동기화로
                self.handle_events(self.engine.vanish(ts_ms, f"봉 대사: 내부 {self.engine.position.signed_qty} · 거래소 0"),
                                   ts_ms)
                self.wallet_resync_due = True
            if self.wallet_resync_due:
                self._resync_wallet(ts_ms)
        db = R.open_position_state(self.con, mode=self.mode.value, symbol=self.symbol)
        internal = self.engine.position.signed_qty if self.engine.position is not None else Decimal(0)
        result = reconcile(self.mode, internal_signed=internal, exchange=pr if self.mode is Mode.LIVE else None,
                           exchange_error=err if self.mode is Mode.LIVE else None, db=db)
        self.last_reconcile_detail = result.detail
        was = self.gate.kill_switch.tripped
        for m in self.gate.observe_reconcile(result, ts_ms):
            self.alert(m, important=True)
        if was is None and self.gate.kill_switch.tripped is not None:     # 알림은 observe_reconcile 문구로 이미 나갔다
            self._on_trips([self.gate.kill_switch.tripped], ts_ms, alert=False)
        if self.last_mark is not None:
            self._on_trips(self.gate.kill_switch.observe_equity(ts_ms, self.engine.equity(self.last_mark)), ts_ms)
        self.snapshot(ts_ms, "bar")
        self.save_state(ts_ms)

    def _resync_wallet(self, ts_ms: int) -> None:
        assert self.exchange is not None
        try:
            acct = self.exchange.account()
        except Exception as e:  # noqa: BLE001 — 다음 봉에 재시도 · 그동안 진입 금지
            self.alert(f"🔴 거래소 지갑 재동기화 실패(다음 봉 재시도 · 진입 금지): {type(e).__name__}: {e}", important=True)
            return
        ev = self.engine.sync_wallet(ts_ms, acct.wallet_balance, source="exchange", detail="포지션 소실 뒤 거래소 지갑")
        if self.engine.position is None:
            self.gate.kill_switch.sync_flat_wallet(acct.wallet_balance)
        self.wallet_resync_due = False
        self.handle_events([ev], ts_ms)
        self._exchange_snapshot(ts_ms, acct, "wallet_resync")

    # ── 벽시계 1초 ───────────────────────────────────────────────────────────
    def safety_tick(self, now_ms: int) -> None:
        self.counts["safety_ticks"] += 1
        self._retry_unrecorded(now_ms)
        has_position = self.engine.position is not None
        verdict, changes = self.gate.stale.update(now_ms, has_position=has_position)
        for c in changes:
            if c.stalled:
                self.alert(f"⚠️ 피드 정지(레지스트리 #1): {', '.join(c.stalled)} — 신규 진입 금지", important=True)
            else:
                self.alert(f"✅ 피드 회복: {', '.join(c.previous)} — stale 차단 해제")
            self.record_ops("StaleChanged", f"{list(c.previous)} → {list(c.stalled)}", now_ms,
                            {"stalled": list(c.stalled), "previous": list(c.previous)})
        if verdict.position_action == "close" and self.engine.position is not None:
            self._stale_close(now_ms, verdict.close_streams)
        self._cancel_pending_if_blocked(now_ms)
        self._drain_telegram(now_ms)
        self.write_status(now_ms)

    def _stale_close(self, now_ms: int, streams: tuple[str, ...]) -> None:
        pos = self.engine.position
        assert pos is not None
        if self.last_mark is None:
            self.alert("🔴 stale 청산 필요하나 받은 mark가 없다 — 사람 확인", important=True)
            return
        age = (now_ms - (self.last_mark_ms or now_ms)) / 1000
        ev = self.engine.close_now(ref_mark=self.last_mark, ts_ms=now_ms, reason=ExitReason.STALE_DATA)
        self.counts["stale_closes"] += 1
        self.handle_events(ev, now_ms, alert_exits=False)
        closed = [e for e in ev if isinstance(e, PositionClosed)]
        detail = (f"무수신 grace 초과 {', '.join(streams)} · 기준 mark {self.last_mark}(나이 {age:.0f}s · "
                  f"{'LIVE 실체결' if self.mode is Mode.LIVE else 'PAPER는 마지막 mark로 체결'})")
        self.record_ops("StaleClose", detail, now_ms, {"streams": list(streams), "closed": bool(closed)})
        if closed:
            c = closed[0]
            self.alert(f"🛑 stale 청산(레지스트리 #12) {c.direction} {c.qty} @ {c.exit_price} · 손익 {_fmt(c.realized_pnl_usdt)}"
                       f" · 지갑 {_fmt(c.wallet_after)} · {detail}", important=True)
            self._last_exit_failure = None
            return
        failure = " / ".join(e.detail for e in ev if isinstance(e, ExitFailed)) or "청산 이벤트 없음"
        if failure != self._last_exit_failure:              # 매초 재시도 — 같은 실패 문구는 한 번만 알린다
            self._last_exit_failure = failure
            self.alert(f"🔴 stale 청산 실패 — 틱마다 재시도: {failure} · {detail}", important=True)

    def _drain_telegram(self, now_ms: int) -> None:
        if self.bot is None:
            return
        updates: list[dict[str, Any]] = []
        while True:
            try:
                updates.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        actions: list[Send | Answer] = []
        if updates and self.poller is not None:
            actions += self.poller.handle(updates)
        actions += self.bot.on_tick(now_ms)
        for a in actions:
            self.outbox.put(a)

    # ── 이벤트 ──────────────────────────────────────────────────────────────
    def handle_events(self, events: Iterable[object], ts_ms: int, *, alert_exits: bool = True) -> None:
        events = list(events)
        if not events:
            return
        self._on_trips(self.gate.kill_switch.observe(events, ts_ms), ts_ms)   # 기록 실패와 무관하게 먼저
        tp = self._intent_tp if any(isinstance(e, EntryFilled | EntrySkipped) for e in events) else None
        self._record(events, tp, ts_ms)
        for e in events:
            self._alert_event(e, alert_exits=alert_exits)
        if any(isinstance(e, SNAPSHOT_EVENTS) for e in events):
            self.snapshot(ts_ms, type(next(e for e in events if isinstance(e, SNAPSHOT_EVENTS))).__name__)
            if self.mode is Mode.LIVE and any(isinstance(e, EntryFilled | PositionClosed | PositionReduced) for e in events):
                self._exchange_snapshot(ts_ms, None, "fill")

    def _record(self, events: list[object], tp: Decimal | None, ts_ms: int) -> None:
        try:
            R.record_events(self.con, events, mode=self.mode.value, symbol=self.symbol, tp=tp)
        except (sqlite3.Error, R.TransactionOpen) as e:
            self.db_errors += 1
            first = not self.unrecorded
            self.unrecorded.append((events, tp))
            if first:
                self.alert(f"🔴 DB 기록 실패 — 진입 금지 · 틱마다 재시도: {type(e).__name__}: {e}", important=True)

    def _retry_unrecorded(self, now_ms: int) -> None:
        while self.unrecorded:
            events, tp = self.unrecorded[0]
            try:
                R.record_events(self.con, events, mode=self.mode.value, symbol=self.symbol, tp=tp)
            except (sqlite3.Error, R.TransactionOpen):
                self.db_errors += 1
                return
            self.unrecorded.pop(0)
            if not self.unrecorded:
                self.alert("✅ DB 기록 재시도 성공 — db 차단 해제")

    def _on_trips(self, trips: list[KillSwitchTripped], ts_ms: int, *, alert: bool = True) -> None:
        for t in trips:
            self.record_ops("KillSwitchTripped", t.detail, ts_ms, {"reason": t.reason})
            if alert:
                self.alert(f"🛑 킬스위치 발동(레지스트리 #11): {t.reason} — {t.detail} · 신규 진입 중단 · 재개는 /start",
                           important=True)
            self.save_state(ts_ms)

    def _alert_event(self, e: object, *, alert_exits: bool) -> None:
        if isinstance(e, EntryFilled):
            pf = e.post_fill
            self.alert(f"📈 진입 {e.decision.direction} {pf.qty} @ {pf.entry_price} · {e.leverage}x · SL {e.decision.sl}"
                       f" · 추정 청산가 {pf.liq_price_est}" + (" · 거래소 수량 채택" if e.adopted is not None else ""))
        elif isinstance(e, PositionClosed) and alert_exits:
            self.alert(f"📉 청산({e.reason}) {e.direction} {e.qty} @ {e.exit_price} · 손익 {_fmt(e.realized_pnl_usdt)}"
                       f" · 수수료 {_fmt(e.exit_commission_usdt)} · 지갑 {_fmt(e.wallet_after)}")
        elif isinstance(e, PositionReduced):
            self.alert(f"⚠️ 일부 청산({e.reason}) {e.qty} · 잔량 {e.remaining_qty} · 손익 {_fmt(e.realized_pnl_usdt)}",
                       important=True)
        elif isinstance(e, PositionVanished):
            self.alert(f"🛑 포지션 소실 {e.direction} {e.qty} — {e.detail}", important=True)
        elif isinstance(e, EntriesBlocked):
            self.alert(f"⛔ 진입 차단(엔진): {e.reason}", important=True)
        elif isinstance(e, ExitFailed) and alert_exits:
            self.alert(f"🔴 청산 실패({e.reason}): {e.detail}", important=True)
        elif isinstance(e, FundingMissed):
            self.alert(f"⚠️ 펀딩 경계 {len(e.boundaries_ms)}개 정산 불가(피드 공백)", important=True)
        elif isinstance(e, LiquidationThresholdCrossed):
            self.alert(f"🛑 mark {e.mark}가 추정 청산가 {e.liq_price_est}를 넘었다", important=True)
        elif isinstance(e, WalletResynced):
            self.alert(f"💰 지갑 재동기화({e.source}) {_fmt(e.previous)} → {_fmt(e.wallet)} · 차이 {_fmt(e.wallet - e.previous)}",
                       important=True)

    def record_ops(self, kind: str, detail: str, ts_ms: int, payload: dict[str, Any] | None = None) -> None:
        try:
            R.record_ops_event(self.con, kind, detail, ts_ms=ts_ms, mode=self.mode.value, symbol=self.symbol,
                               payload=payload)
        except (sqlite3.Error, R.TransactionOpen) as e:
            self.db_errors += 1
            logger.error("운영 이벤트 기록 실패 %s: %s", kind, e)

    # ── 스냅샷·상태 ─────────────────────────────────────────────────────────
    def snapshot(self, ts_ms: int, reason: str) -> None:
        e, pos = self.engine, self.engine.position
        upnl = e.unrealized_pnl(self.last_mark) if self.last_mark is not None else (None if pos else Decimal(0))
        iso = pos.qty * pos.entry_price / Decimal(pos.leverage) if pos is not None else Decimal(0)
        try:
            R.record_account_snapshot(self.con, mode=self.mode.value, symbol=self.symbol, ts_ms=ts_ms, source="engine",
                                      wallet_balance=e.wallet,
                                      margin_balance=None if upnl is None else e.wallet + upnl,
                                      available_balance=e.wallet - iso, isolated_margin=iso, unrealized_pnl=upnl,
                                      raw={"reason": reason, "mark": None if self.last_mark is None else str(self.last_mark)})
        except (sqlite3.Error, R.TransactionOpen) as ex:
            self.db_errors += 1
            logger.error("스냅샷 기록 실패: %s", ex)

    def _exchange_snapshot(self, ts_ms: int, acct: ExchangeAccount | None, reason: str) -> None:
        assert self.exchange is not None
        if acct is None:
            try:
                acct = self.exchange.account()
            except Exception as e:  # noqa: BLE001 — 스냅샷 실패는 기록만(봉마다 다시 읽는다)
                logger.warning("거래소 계좌 조회 실패(%s): %s", reason, e)
                return
        try:
            R.record_account_snapshot(self.con, mode=self.mode.value, symbol=self.symbol, ts_ms=ts_ms, source="exchange",
                                      wallet_balance=acct.wallet_balance, margin_balance=acct.margin_balance,
                                      available_balance=acct.available_balance, isolated_margin=acct.isolated_margin,
                                      unrealized_pnl=acct.unrealized_pnl, raw={"reason": reason, "account": acct.raw})
        except (sqlite3.Error, R.TransactionOpen) as ex:
            self.db_errors += 1
            logger.error("거래소 스냅샷 기록 실패: %s", ex)

    def save_state(self, ts_ms: int) -> None:
        state = json.dumps({"paused_by": self.gate.paused_by, "kill_switch": self.gate.kill_switch.to_state(),
                            "reconcile": self.gate.reconcile.to_state()}, sort_keys=True)
        if state == self._saved_state:
            return
        try:
            self.gate.save(self.con, ts_ms=ts_ms, mode=self.mode.value)
            self._saved_state = state
        except (sqlite3.Error, R.TransactionOpen) as e:
            self.db_errors += 1
            logger.error("안전 상태 저장 실패: %s", e)

    def status(self, now_ms: int) -> dict[str, Any]:
        pos = self.engine.position
        return {
            "ts_ms": now_ms, "mode": self.mode.value, "symbol": self.symbol,
            "entries_allowed": not self.entry_blockers(), "blockers": self.entry_blockers(),
            "position": None if pos is None else {"direction": pos.direction.value, "qty": str(pos.qty),
                                                  "entry_price": str(pos.entry_price)},
            "wallet": str(self.engine.wallet), "last_mark": None if self.last_mark is None else str(self.last_mark),
            "last_mark_age_s": None if self.last_mark_ms is None else (now_ms - self.last_mark_ms) / 1000,
            "last_bar_open_ms": self.last_bar_open_ms,
            "stalled": list(self.gate.stale.last.stalled) if self.gate.stale.last is not None else None,
            "delivery": self.gate.stale.counter.snapshot(now_ms),
            "kill_switch": self.gate.kill_switch.to_state(),
            "db_errors": self.db_errors, "unrecorded": len(self.unrecorded), "bar_conflicts": self.bar_conflicts,
            "counts": dict(self.counts),
        }

    def write_status(self, now_ms: int, extra: dict[str, Any] | None = None) -> None:
        if self.status_path is None:
            return
        body = self.status(now_ms) | (extra or {})
        tmp = self.status_path.with_suffix(".tmp")
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(body, ensure_ascii=False, default=str))
            os.replace(tmp, self.status_path)                  # 원자적 — health가 반쯤 쓴 파일을 읽지 않게
        except OSError as e:
            logger.error("상태 파일 쓰기 실패: %s", e)

    # ── BotController (텔레그램 · 같은 루프 스레드에서 불린다) ────────────────
    def status_text(self) -> str:
        now = self.clock_ms()
        blockers = self.entry_blockers()
        lines = [f"[{self.mode.value}] {self.symbol} · 신규 진입 {'허용' if not blockers else '금지'}"]
        lines += [f" · {b}" for b in blockers]
        lines.append(self.position_text())
        age = "-" if self.last_mark_ms is None else f"{(now - self.last_mark_ms) / 1000:.0f}s 전"
        lines.append(f"mark {self.last_mark if self.last_mark is not None else '-'} ({age}) · 지갑 {_fmt(self.engine.wallet)}")
        st = self.gate.stale.last
        lines.append(f"피드 정지: {', '.join(st.stalled) if st and st.stalled else '없음'}"
                     + ("" if st is not None else " (미평가)"))
        ks = self.gate.kill_switch
        lines.append(f"킬스위치: {'발동 ' + ks.tripped.reason if ks.tripped else '정상'} · 연속손실 {ks.consecutive_losses}"
                     f" · 청산 {ks.liquidations} · 소실 {ks.vanished}")
        if self.db_errors or self.unrecorded:
            lines.append(f"DB 오류 {self.db_errors} · 미기록 {len(self.unrecorded)}")
        return "\n".join(lines)

    def position_text(self) -> str:
        pos = self.engine.position
        if pos is None:
            return "포지션 없음"
        mark = self.last_mark
        upnl = "-" if mark is None else _fmt(self.engine.unrealized_pnl(mark))
        return (f"{pos.direction} {pos.qty} @ {pos.entry_price} · {pos.leverage}x · mark {mark if mark is not None else '-'}"
                f" · uPnL {upnl} USDT · SL {pos.sl} · TP {pos.tp if pos.tp is not None else '-'} · 추정 청산가 {pos.liq_price_est}")

    def profit_text(self) -> str:
        now = self.clock_ms()
        day0 = _utc_day_start_ms(now)
        rows = self.con.execute("SELECT ts_ms, realized_pnl_usdt, exit_commission_usdt FROM positions "
                                "WHERE mode=? AND symbol=? AND event='close'", (self.mode.value, self.symbol)).fetchall()
        def net(r: tuple) -> Decimal:
            return Decimal(r[1] or 0) - Decimal(r[2] or 0)
        today = [r for r in rows if r[0] >= day0]
        first = self.con.execute("SELECT wallet_balance FROM account_snapshots WHERE mode=? AND source='engine' "
                                 "ORDER BY id LIMIT 1", (self.mode.value,)).fetchone()
        start = Decimal(first[0]) if first and first[0] is not None else None
        total = "-" if start is None else _fmt(self.engine.wallet - start)
        return (f"오늘(UTC) 청산 행 {len(today)} · 실현−청산수수료 {_fmt(sum((net(r) for r in today), Decimal()))} USDT\n"
                f"지갑 {_fmt(self.engine.wallet)} · 첫 스냅샷 대비 {total} USDT(진입 수수료·펀딩 포함) · 전체 청산 행 {len(rows)}")

    def has_position(self) -> bool:
        return self.engine.position is not None

    def pause_entries(self, actor: str) -> str:
        now = self.clock_ms()
        text = self.gate.pause(actor)
        self._cancel_pending_if_blocked(now)
        self.record_ops("Paused", actor, now)
        self.save_state(now)
        return text

    def resume(self, actor: str) -> str:
        now = self.clock_ms()
        if self.gate.resume_refused(now):
            self.record_ops("ResumeRefused", actor, now, {"reason": "daily_loss"})
            return self.gate.resume(actor, ts_ms=now)
        lines = self.gate.resume(actor, ts_ms=now).splitlines()[:-1]
        cleared = self.engine.clear_blocks()
        lines += [f"엔진 차단 해제: {c}" for c in cleared]
        self.record_ops("Resumed", actor, now, {"engine_cleared": cleared})
        self.save_state(now)
        remaining = self.entry_blockers()
        lines.append("신규 진입 허용" if not remaining else f"⚠️ 아직 진입 금지: {', '.join(remaining)}")
        return "\n".join(lines)

    def close_all(self, actor: str) -> str:
        now = self.clock_ms()
        if self.engine.position is None:
            return "포지션 없음 — 청산할 것이 없다"
        if self.last_mark is None:
            return "받은 mark가 없다 — 청산 기준가 없음, 실행 안 함"
        ev = self.engine.close_now(ref_mark=self.last_mark, ts_ms=now, reason=ExitReason.MANUAL)
        self.handle_events(ev, now, alert_exits=False)
        self.record_ops("ManualClose", actor, now)
        closed = [e for e in ev if isinstance(e, PositionClosed)]
        if closed:
            c = closed[0]
            return (f"청산 완료 {c.direction} {c.qty} @ {c.exit_price} · 손익 {_fmt(c.realized_pnl_usdt)}"
                    f" · 지갑 {_fmt(c.wallet_after)} ({actor})")
        fails = " / ".join(e.detail for e in ev if isinstance(e, ExitFailed)) or "청산 이벤트 없음"
        return f"청산 실패 — 포지션 유지: {fails}"
