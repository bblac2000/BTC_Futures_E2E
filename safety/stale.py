"""stale-data kill — 레지스트리 #1 `DeliveryCounter.stalled()`(스트림별 임계)를 그대로 쓴다. 새 숫자 없음.

- 정지 스트림이 하나라도 있으면 신규 진입 금지. 한 번도 평가하지 않았으면 역시 금지(`not_evaluated`).
- 포지션이 있으면 `hold_and_alert`: mark가 끊기면 SL을 평가할 가격이 없다 — 자동 청산하지 않고 알린다
  (스킬 §6 "청산 검토"를 사람 판단으로 해석 · 자동 청산 여부는 사용자 결정 대기).
- 알림은 **정지 집합이 바뀔 때만**(반복 알림은 사람이 끄고 결국 침묵이 된다 — SKILL §3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ops.delivery_counter import DeliveryCounter


@dataclass(frozen=True)
class StaleVerdict:
    ts_ms: int
    stalled: tuple[str, ...]
    entries_allowed: bool
    position_action: Literal["none", "hold_and_alert"]


@dataclass(frozen=True)
class StaleChanged:
    ts_ms: int
    stalled: tuple[str, ...]
    previous: tuple[str, ...]


class StaleDataGuard:
    def __init__(self, counter: DeliveryCounter):
        self.counter = counter
        self.last: StaleVerdict | None = None

    def update(self, now_ms: int, *, has_position: bool) -> tuple[StaleVerdict, list[StaleChanged]]:
        stalled = tuple(self.counter.stalled(now_ms))
        v = StaleVerdict(now_ms, stalled, not stalled, "hold_and_alert" if stalled and has_position else "none")
        prev = self.last.stalled if self.last is not None else ()
        changes = [StaleChanged(now_ms, stalled, prev)] if stalled != prev else []
        self.last = v
        return v, changes

    @property
    def blocker(self) -> str | None:
        if self.last is None:
            return "stale:not_evaluated"
        return None if self.last.entries_allowed else f"stale:{','.join(self.last.stalled)}"
