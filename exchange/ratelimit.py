"""rate-limit 사용량 카운터 — 한도는 `exchangeInfo.rateLimits`(런타임)에서, 사용량은 응답 헤더에서.

헤더 이름은 한도에서 **도출**한다: REQUEST_WEIGHT → `X-MBX-USED-WEIGHT-<n><unit>`,
ORDERS → `X-MBX-ORDER-COUNT-<n><unit>` (unit: S/M/H/D). 80% 가드 정책은 layer 7 `safety/`가 가진다 —
이 모듈은 비율을 계산할 뿐 임계를 모른다.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from exchange.errors import RulesError
from exchange.rules import RateLimit

_UNIT = {"SECOND": "S", "MINUTE": "M", "HOUR": "H", "DAY": "D"}
_PREFIX = {"REQUEST_WEIGHT": "X-MBX-USED-WEIGHT-", "ORDERS": "X-MBX-ORDER-COUNT-"}


def key_of(rl: RateLimit) -> str:
    return f"{rl.rate_limit_type}/{rl.interval}/{rl.interval_num}"


class RateLimitCounter:
    def __init__(self, limits: Iterable[RateLimit]):
        self._limits: dict[str, RateLimit] = {}
        self._seen: dict[str, tuple[int, int]] = {}         # key → (window_start_ms, used)
        for rl in limits:
            self.header_name(rl)                           # 모르는 유형은 여기서 거부
            self._limits[key_of(rl)] = rl
        if not self._limits:
            raise RulesError("rate limit 한도 0개")

    @staticmethod
    def header_name(rl: RateLimit) -> str:
        if rl.rate_limit_type not in _PREFIX or rl.interval not in _UNIT:
            raise RulesError(f"헤더를 도출할 수 없는 rate limit {rl} — 감시 못 하는 한도를 조용히 무시하지 않는다")
        return f"{_PREFIX[rl.rate_limit_type]}{rl.interval_num}{_UNIT[rl.interval]}"

    def observe_headers(self, headers: Mapping[str, str], now_ms: int) -> None:
        low = {k.lower(): v for k, v in headers.items()}
        for k, rl in self._limits.items():
            v = low.get(self.header_name(rl).lower())
            if v is None:
                continue
            w = rl.window_ms
            self._seen[k] = (now_ms // w * w, int(v))

    def usage(self, now_ms: int) -> dict[str, float]:
        out = {}
        for k, rl in self._limits.items():
            w = rl.window_ms
            start, used = self._seen.get(k, (-1, 0))
            out[k] = used / rl.limit if start == now_ms // w * w else 0.0
        return out

    def max_usage(self, now_ms: int) -> float:
        return max(self.usage(now_ms).values())

    def over(self, threshold: float, now_ms: int) -> list[str]:
        return [k for k, u in self.usage(now_ms).items() if u >= threshold]
