"""stale-data kill — 레지스트리 #1 `DeliveryCounter.stalled()`(스트림별 임계)를 그대로 쓴다. 새 숫자 없음.

- 정지 스트림이 하나라도 있으면 신규 진입 금지. 한 번도 평가하지 않았으면 역시 금지(`not_evaluated`).
- 🔒 레지스트리 #14(사용자 결정 2026-09-16 · #12 ② 대체): 포지션이 있고 **markprice 스트림의 마지막 수신이 grace(120초)를
  넘었으면**(한 번도 안 왔으면 관측 시작 후 grace 경과) `close` → 호출자가 MARKET reduceOnly로 청산하고 알린다.
  근거(사용자): SL은 mark로 평가한다(#5 `SL_TRIGGER_BASIS`) → mark 정지 = SL 감시 불가.
  kline update/close가 grace를 넘기거나 어느 스트림이든 #1 분당 규칙을 어기면 `hold_and_alert` — 진입만 막는다.
  청산 뒤에도 정지가 풀릴 때까지 진입 금지(`blocker`).
- 알림은 **정지 집합이 바뀔 때만**(반복 알림은 사람이 끄고 결국 침묵이 된다 — SKILL §3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ops.delivery_counter import DELIVERY, DeliveryCounter

#  레지스트리 #14: 포지션 자동 청산의 근거가 되는 스트림 — SL 평가 가격(mark)을 나르는 스트림만
CLOSE_STREAMS: tuple[str, ...] = ("markprice",)


@dataclass(frozen=True)
class StaleVerdict:
    ts_ms: int
    stalled: tuple[str, ...]
    entries_allowed: bool
    position_action: Literal["none", "hold_and_alert", "close"]
    close_streams: tuple[str, ...] = ()           # grace를 넘긴 무수신 스트림 중 `CLOSE_STREAMS`(청산 사유)


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
        close_streams = tuple(k for k in self.past_grace(now_ms) if k in CLOSE_STREAMS)
        action: Literal["none", "hold_and_alert", "close"] = "none"
        if has_position and close_streams:
            action = "close"
        elif has_position and stalled:
            action = "hold_and_alert"
        v = StaleVerdict(now_ms, stalled, not stalled, action, close_streams)
        prev = self.last.stalled if self.last is not None else ()
        changes = [StaleChanged(now_ms, stalled, prev)] if stalled != prev else []
        self.last = v
        return v, changes

    def past_grace(self, now_ms: int) -> tuple[str, ...]:
        """마지막 수신 나이 > grace(한 번도 안 왔으면 시작 후 > grace) — #1 `is_stalled`의 나이 규칙과 같은 경계."""
        out = []
        for kind, snap in self.counter.snapshot(now_ms).items():
            grace_ms = DELIVERY[kind].grace_sec * 1000
            age = snap["last_seen_age_sec"]
            if (now_ms - self.counter.start_ms > grace_ms) if age is None else (age * 1000 > grace_ms):
                out.append(kind)
        return tuple(out)

    @property
    def blocker(self) -> str | None:
        if self.last is None:
            return "stale:not_evaluated"
        return None if self.last.entries_allowed else f"stale:{','.join(self.last.stalled)}"
