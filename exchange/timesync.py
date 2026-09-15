"""서버 시각 오프셋 — `recvWindow` 오류(-1021) 방지(strategy-modules §6 시계 동기).

오프셋 = 서버시각 − 왕복 중점. 여러 표본 중 **왕복시간(rtt)이 가장 짧은** 표본을 쓴다
(네트워크 지연이 적을수록 중점 추정 오차가 작다).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from exchange.client_types import Response


class _TimeClient(Protocol):
    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response: ...


@dataclass(frozen=True)
class _Sample:
    offset_ms: int
    rtt_ms: int
    at_local_ms: int


class TimeSync:
    def __init__(self, max_samples: int = 5):
        self._samples: deque[_Sample] = deque(maxlen=max_samples)
        self._invalidated = False

    def record(self, *, local_send_ms: int, server_ms: int, local_recv_ms: int) -> None:
        rtt = local_recv_ms - local_send_ms
        if rtt < 0:
            raise ValueError(f"음수 rtt {rtt}")
        mid = (local_send_ms + local_recv_ms) // 2
        self._samples.append(_Sample(server_ms - mid, rtt, local_recv_ms))
        self._invalidated = False

    def measure(self, client: _TimeClient, clock_ms: Callable[[], int]) -> None:
        t0 = clock_ms()
        r = client.get("/fapi/v1/time")
        t1 = clock_ms()
        self.record(local_send_ms=t0, server_ms=int(r.data["serverTime"]), local_recv_ms=t1)

    def _best(self) -> _Sample | None:
        return min(self._samples, key=lambda s: s.rtt_ms) if self._samples else None

    @property
    def offset_ms(self) -> int | None:
        b = self._best()
        return None if b is None else b.offset_ms

    @property
    def rtt_ms(self) -> int | None:
        b = self._best()
        return None if b is None else b.rtt_ms

    def server_now_ms(self, local_ms: int) -> int:
        off = self.offset_ms
        if off is None:
            raise RuntimeError("서버 시각 표본 없음 — measure() 먼저")
        return local_ms + off

    def age_ms(self, local_ms: int) -> int | None:
        if not self._samples:
            return None
        return local_ms - max(s.at_local_ms for s in self._samples)

    def invalidate(self) -> None:
        """-1021 등 시계 오류를 받았을 때 — 다음 재측정 전까지 stale로 본다."""
        self._invalidated = True

    def is_stale(self, *, local_ms: int, max_age_ms: int) -> bool:
        age = self.age_ms(local_ms)
        return self._invalidated or age is None or age > max_age_ms
