"""종합 진입 게이트 — 킬스위치 · 수동 일시정지 · stale-data · 대사. 사유를 **전부** 나열한다(첫 사유만 보면 나머지를 놓친다).

- `/pause` → `pause(actor)` · `/start` → `resume(actor)`: 사람이 풀 수 있는 것(일시정지·킬스위치·sticky 대사)만 푼다.
  피드 정지는 사람이 풀 수 없다 — 남은 사유를 문구로 알린다.
- 일시정지·킬스위치·대사 sticky 상태는 함께 저장한다(`safety_state` "safety_gate").
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from db import record as R
from safety.config import KillSwitchLimits
from safety.killswitch import KillSwitch
from safety.reconcile import ReconcileGuard, ReconcileResult
from safety.stale import StaleDataGuard

STATE_NAME = "safety_gate"


class SafetyGate:
    def __init__(self, kill_switch: KillSwitch, stale: StaleDataGuard, reconcile: ReconcileGuard):
        self.kill_switch, self.stale, self.reconcile = kill_switch, stale, reconcile
        self.paused_by: str | None = None

    def pause(self, actor: str) -> str:
        if not actor:
            raise ValueError("일시정지는 사람(actor)만")
        self.paused_by = actor
        return f"신규 진입 중지 ({actor}) — 포지션 유지"

    def observe_reconcile(self, result: ReconcileResult, ts_ms: int) -> list[str]:
        """봉마다 대사 → 대사 차단 갱신. LIVE에서 내부 포지션이 있는데 거래소가 0이면 킬스위치(청산 의심)도 발동."""
        msgs = self.reconcile.update(result)
        if result.exchange_signed is not None and result.exchange_signed == 0 and result.internal_signed != 0:
            for t in self.kill_switch.trip(ts_ms, "position_vanished",
                                            f"대사: 내부 {result.internal_signed} · 거래소 0 — 청산·수동 청산 의심"):
                msgs.append(f"🛑 킬스위치 발동: {t.reason} — {t.detail}")
            self.kill_switch.liquidations = max(self.kill_switch.liquidations, 1)
        return msgs

    def entry_blockers(self) -> list[str]:
        out = []
        if self.paused_by is not None:
            out.append(f"paused:{self.paused_by}")
        if self.kill_switch.tripped is not None:
            out.append(f"kill_switch:{self.kill_switch.tripped.reason}")
        if self.stale.blocker is not None:
            out.append(self.stale.blocker)
        if self.reconcile.blocker is not None:
            out.append(self.reconcile.blocker)
        return out

    @property
    def entries_allowed(self) -> bool:
        return not self.entry_blockers()

    def resume(self, actor: str, *, ts_ms: int = 0) -> str:
        if not actor:
            raise ValueError("재개는 사람(actor)만")
        lines = []
        if self.paused_by is not None:
            lines.append(f"일시정지 해제 ({actor})")
            self.paused_by = None
        if self.kill_switch.tripped is not None:
            lines.append(self.kill_switch.resume(ts_ms, actor=actor))
        r = self.reconcile.resume(actor=actor)
        if r:
            lines.append(r)
        remaining = self.entry_blockers()
        lines.append("신규 진입 허용" if not remaining else f"⚠️ 아직 진입 금지: {', '.join(remaining)}")
        return "\n".join(lines)

    def save(self, con: sqlite3.Connection, *, ts_ms: int, mode: str) -> None:
        R.save_safety_state(con, STATE_NAME, {"paused_by": self.paused_by, "kill_switch": self.kill_switch.to_state(),
                                              "reconcile": self.reconcile.to_state()}, ts_ms=ts_ms, mode=mode)

    @classmethod
    def load(cls, con: sqlite3.Connection, limits: KillSwitchLimits, stale: StaleDataGuard, *, mode: str,
             wallet: Decimal) -> SafetyGate:
        state = R.load_safety_state(con, STATE_NAME, mode=mode)
        if state is None:
            return cls(KillSwitch(limits, wallet=wallet), stale, ReconcileGuard())
        rec = ReconcileGuard()
        rec.restore(state.get("reconcile") or {})
        gate = cls(KillSwitch.from_state(limits, state["kill_switch"], wallet=wallet), stale, rec)
        gate.paused_by = state.get("paused_by")
        return gate
