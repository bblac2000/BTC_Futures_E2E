"""rate-limit 가드 — `RateLimitCounter`(응답 헤더 사용량 · 한도는 exchangeInfo) 기준 **80%**에서 폴링 완화(strategy-modules §6).

신호만 낸다: 무엇을 얼마나 늦출지는 폴링 루프(layer 8)가 정한다. 주문(특히 청산)은 이 신호로 막지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from exchange.ratelimit import RateLimitCounter
from safety.config import RATE_LIMIT_RELAX_AT


@dataclass(frozen=True)
class RateDecision:
    relax_polling: bool
    over: tuple[str, ...]
    max_usage: float


class RateLimitGuard:
    def __init__(self, counter: RateLimitCounter, *, threshold: Decimal = RATE_LIMIT_RELAX_AT):
        if not Decimal(0) < threshold <= Decimal(1):
            raise ValueError(f"threshold (0, 1]: {threshold}")
        self.counter, self.threshold = counter, threshold

    def check(self, now_ms: int) -> RateDecision:
        usage = self.counter.usage(now_ms)
        over = tuple(sorted(k for k, u in usage.items() if Decimal(str(u)) >= self.threshold))
        return RateDecision(bool(over), over, max(usage.values()) if usage else 0.0)
