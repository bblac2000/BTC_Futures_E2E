"""종합 진입 게이트 — 킬스위치 · 수동 일시정지 · stale-data · 대사. 사유를 **전부** 나열한다(첫 사유만 보면 나머지를 놓친다).

- `/pause` → `pause(actor)` · `/start` → `resume(actor, ts_ms=)`: 사람이 풀 수 있는 것(일시정지·킬스위치·sticky 대사)만 푼다.
  피드 정지는 사람이 풀 수 없다 — 남은 사유를 문구로 알린다.
- 🔒 레지스트리 #13: 일일 손실 트립 날짜에는 `/start`가 **아무것도 바꾸지 않는다**(일시정지·대사도 그대로) —
  "blocked by daily-loss limit until 00:00 UTC". `ts_ms`는 필수(기본값이 있으면 1970년 날짜로 판정해 풀어 버린다).
- 일시정지·킬스위치·대사 sticky 상태는 함께 저장한다(`safety_state` "safety_gate").
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from db import record as R
from safety.config import DAILY_LOSS_RESUME_REFUSED, KillSwitchLimits
from safety.killswitch import KillSwitch
from safety.reconcile import ReconcileGuard, ReconcileResult
from safety.stale import StaleDataGuard

STATE_NAME = "safety_gate"


class SafetyGate:
    def __init__(self, kill_switch: KillSwitch, stale: StaleDataGuard, reconcile: ReconcileGuard):
        self.kill_switch, self.stale, self.reconcile = kill_switch, stale, reconcile
        self.paused_by: str | None = None
        #  엔진 진입 차단 사유(펀딩 경계 누락·주문 결과 불명 등)의 저장본 — 런타임이 저장 전에 채우고 기동 때 엔진에 되돌린다
        #  (Codex L8b #1: 메모리에만 있으면 재기동이 차단을 지운다). 해제는 사람의 /start(엔진 clear_blocks → 다음 저장).
        self.engine_blocks: list[str] = []

    def pause(self, actor: str) -> str:
        if not actor:
            raise ValueError("일시정지는 사람(actor)만")
        self.paused_by = actor
        return f"신규 진입 중지 ({actor}) — 포지션 유지"

    def observe_reconcile(self, result: ReconcileResult, ts_ms: int) -> list[str]:
        """봉마다 대사 → 대사 차단 갱신. LIVE에서 내부 포지션이 있는데 거래소가 0이면 킬스위치(청산 의심)도 발동."""
        msgs = self.reconcile.update(result)
        if result.exchange_signed is not None and result.exchange_signed == 0 and result.internal_signed != 0:
            #  정상 경로는 layer 8이 대사 **전에** `Engine.vanish`로 내부를 0으로 만들고 `PositionVanished`를 킬스위치에 넘긴다.
            #  여기 걸리면 그 경로를 건너뛴 것 — 방어선으로 발동만 한다.
            for t in self.kill_switch.trip(ts_ms, "position_vanished",
                                            f"대사: 내부 {result.internal_signed} · 거래소 0 — 청산·수동 청산 의심"):
                msgs.append(f"🛑 킬스위치 발동: {t.reason} — {t.detail}")
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

    def resume_refused(self, ts_ms: int) -> bool:
        return self.kill_switch.resume_refused(ts_ms)

    def resume(self, actor: str, *, ts_ms: int) -> str:
        if not actor:
            raise ValueError("재개는 사람(actor)만")
        if self.resume_refused(ts_ms):
            return f"{DAILY_LOSS_RESUME_REFUSED} — 변경 없음\n⚠️ 진입 금지: {', '.join(self.entry_blockers())}"
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

    def to_state(self) -> dict:
        return {"paused_by": self.paused_by, "kill_switch": self.kill_switch.to_state(),
                "reconcile": self.reconcile.to_state(), "engine_blocks": list(self.engine_blocks)}

    def save(self, con: sqlite3.Connection, *, ts_ms: int, mode: str) -> int:
        return R.save_safety_state(con, STATE_NAME, self.to_state(), ts_ms=ts_ms, mode=mode)

    @classmethod
    def load(cls, con: sqlite3.Connection, limits: KillSwitchLimits, stale: StaleDataGuard, *, mode: str,
             wallet: Decimal) -> SafetyGate:
        return cls.from_state(R.load_safety_state(con, STATE_NAME, mode=mode), limits, stale, wallet=wallet)

    @classmethod
    def from_state(cls, state: dict | None, limits: KillSwitchLimits, stale: StaleDataGuard, *,
                   wallet: Decimal) -> SafetyGate:
        if state is None:
            return cls(KillSwitch(limits, wallet=wallet), stale, ReconcileGuard())
        rec = ReconcileGuard()
        rec.restore(state.get("reconcile") or {})
        gate = cls(KillSwitch.from_state(limits, state["kill_switch"], wallet=wallet), stale, rec)
        gate.paused_by = state.get("paused_by")
        gate.engine_blocks = [str(r) for r in state.get("engine_blocks") or []]
        return gate
