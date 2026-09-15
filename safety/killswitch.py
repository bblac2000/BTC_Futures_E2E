"""킬스위치 — 일일 손실 한도 · 연속 손실 n회 · 청산 1회 → 신규 진입 중단(strategy-modules §6). 재개는 **사람의 /start만**.

- 거래 손익 = 청산 뒤 지갑 − **직전 flat 지갑**(진입 수수료·펀딩·청산 수수료 전부 포함). 이벤트의 `realized_pnl_usdt`만 보면
  진입 수수료가 빠져 "수수료에 먹힌 이익"이 이긴 거래로 세진다.
- 일일 손실: UTC 날짜별 첫 equity 관측이 기준 · `equity ≤ 기준 × (1 − x)`면 발동(경계 포함). 날짜가 바뀌어도 트립은 풀리지 않는다.
- LIVE에서 거래소 수량이 사라지면(`PositionVanished` · 봉마다 대사에서 내부≠0·거래소=0) 청산 1회로 본다 — 거래소 청산은
  `PositionClosed(LIQUIDATION)`로 오지 않는다(Codex L6·7 #2).
- 한 번 발동하면 다음 사유로 다시 발동 이벤트를 내지 않는다(첫 사유 유지) · 사람의 `resume`만 해제(연속 손실·청산 수 초기화).
  일일 손실로 발동한 날 재개하면 같은 날 다음 equity 평가에서 다시 발동한다(기준을 낮춰 한도를 풀지 않는다).
- 상태는 `db.record.save_safety_state`(append-only)로 남긴다 — 재시작이 트립을 풀지 않게.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from db import record as R
from paper.types import ExitReason, PositionClosed, PositionVanished
from safety.config import MAX_LIQUIDATIONS, KillSwitchLimits

STATE_NAME = "kill_switch"


@dataclass(frozen=True)
class KillSwitchTripped:
    ts_ms: int
    reason: str                     # daily_loss | consecutive_losses | liquidation | position_vanished
    detail: str


def _utc_day(ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(ts_ms / 1000, dt.UTC).date().isoformat()


class KillSwitch:
    def __init__(self, limits: KillSwitchLimits, *, wallet: Decimal):
        self.limits = limits
        self.tripped: KillSwitchTripped | None = None
        self.consecutive_losses = 0
        self.liquidations = 0
        self.last_flat_wallet = wallet
        self.day: str | None = None
        self.day_start_equity: Decimal | None = None
        self.resumed_by: str | None = None

    @property
    def entries_allowed(self) -> bool:
        return self.tripped is None

    def trip(self, ts_ms: int, reason: str, detail: str) -> list[KillSwitchTripped]:
        if self.tripped is not None:
            return []
        self.tripped = KillSwitchTripped(ts_ms, reason, detail)
        return [self.tripped]

    def observe(self, events: Iterable[object], ts_ms: int) -> list[KillSwitchTripped]:
        out: list[KillSwitchTripped] = []
        for ev in events:
            if isinstance(ev, PositionVanished):
                #  LIVE 청산은 PositionClosed(LIQUIDATION)로 오지 않는다 — 거래소 수량 소실을 청산 1회로 본다(Codex L6·7 #2)
                self.liquidations += 1
                out += self.trip(ev.ts_ms, "position_vanished", f"거래소 포지션 소실(청산·수동 청산 의심): {ev.detail}")
                continue
            if not isinstance(ev, PositionClosed):
                continue
            net = ev.wallet_after - self.last_flat_wallet
            self.last_flat_wallet = ev.wallet_after
            self.consecutive_losses = self.consecutive_losses + 1 if net < 0 else 0
            if ev.reason is ExitReason.LIQUIDATION:
                self.liquidations += 1
                if self.liquidations >= MAX_LIQUIDATIONS:
                    out += self.trip(ev.ts_ms, "liquidation", f"청산 {self.liquidations}회 · 거래 손익 {net}")
            if self.consecutive_losses >= self.limits.max_consecutive_losses:
                out += self.trip(ev.ts_ms, "consecutive_losses",
                                  f"연속 순손실 {self.consecutive_losses}회(한도 {self.limits.max_consecutive_losses})")
        return out

    def observe_equity(self, ts_ms: int, equity: Decimal) -> list[KillSwitchTripped]:
        day = _utc_day(ts_ms)
        if day != self.day or self.day_start_equity is None:
            self.day, self.day_start_equity = day, equity
        floor = self.day_start_equity * (1 - self.limits.daily_loss_pct)
        if equity <= floor:
            return self.trip(ts_ms, "daily_loss", f"{day} 시작 equity {self.day_start_equity} → {equity} "
                                                   f"(한도 {self.limits.daily_loss_pct} · 기준선 {floor})")
        return []

    def resume(self, ts_ms: int, *, actor: str) -> str:
        if not actor:
            raise ValueError("재개는 사람(actor)만")
        was = self.tripped
        self.tripped, self.consecutive_losses, self.liquidations, self.resumed_by = None, 0, 0, actor
        if was is None:
            return f"킬스위치 발동 상태 아님 ({actor})"
        warn = " · ⚠️ 일일 손실 기준은 그대로 — 같은 UTC 날짜 안에서는 다음 평가에서 다시 발동할 수 있다" \
            if was.reason == "daily_loss" else ""
        return f"킬스위치 해제: {was.reason} ({actor}){warn}"

    # ── 영속 ────────────────────────────────────────────────────────────────
    def to_state(self) -> dict[str, Any]:
        t = self.tripped
        return {"tripped": None if t is None else {"ts_ms": t.ts_ms, "reason": t.reason, "detail": t.detail},
                "consecutive_losses": self.consecutive_losses, "liquidations": self.liquidations,
                "last_flat_wallet": str(self.last_flat_wallet), "day": self.day,
                "day_start_equity": None if self.day_start_equity is None else str(self.day_start_equity),
                "resumed_by": self.resumed_by}

    @classmethod
    def from_state(cls, limits: KillSwitchLimits, state: dict[str, Any], *, wallet: Decimal) -> KillSwitch:
        ks = cls(limits, wallet=wallet)
        t = state.get("tripped")
        ks.tripped = None if t is None else KillSwitchTripped(int(t["ts_ms"]), str(t["reason"]), str(t["detail"]))
        ks.consecutive_losses = int(state["consecutive_losses"])
        ks.liquidations = int(state["liquidations"])
        ks.last_flat_wallet = Decimal(state["last_flat_wallet"])
        ks.day = state.get("day")
        ks.day_start_equity = None if state.get("day_start_equity") is None else Decimal(state["day_start_equity"])
        ks.resumed_by = state.get("resumed_by")
        return ks

    def save(self, con: sqlite3.Connection, *, ts_ms: int, mode: str) -> None:
        R.save_safety_state(con, STATE_NAME, self.to_state(), ts_ms=ts_ms, mode=mode)

    @classmethod
    def load(cls, con: sqlite3.Connection, limits: KillSwitchLimits, *, mode: str, wallet: Decimal) -> KillSwitch:
        state = R.load_safety_state(con, STATE_NAME, mode=mode)
        return cls(limits, wallet=wallet) if state is None else cls.from_state(limits, state, wallet=wallet)
