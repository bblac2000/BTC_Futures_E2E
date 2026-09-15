"""layer 7 설정 — strategy-modules §6.

- 킬스위치 x(일일 손실 %)·n(연속 손실 횟수)은 **사전확약 게이트 값** → 기본값 없음(레지스트리 PENDING 행, 사용자 결정 대기).
  값이 없으면 기동할 수 없다(조용한 기본값이 게이트를 정하지 않게 — #3과 같은 방식).
- 청산 1회 발동은 스킬이 정한 값이다.
- rate-limit 80%는 스킬 §6("80%에서 폴링 완화")의 값이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

MAX_LIQUIDATIONS = 1
RATE_LIMIT_RELAX_AT = Decimal("0.8")


@dataclass(frozen=True)
class KillSwitchLimits:
    daily_loss_pct: Decimal          # UTC 일 시작 equity 대비 손실 비율 (0, 1)
    max_consecutive_losses: int      # 연속 순손실 청산 횟수 ≥ 1

    def __post_init__(self) -> None:
        if not isinstance(self.daily_loss_pct, Decimal):
            raise TypeError(f"daily_loss_pct는 Decimal: {type(self.daily_loss_pct).__name__}")
        if not Decimal(0) < self.daily_loss_pct < Decimal(1):
            raise ValueError(f"daily_loss_pct는 (0, 1): {self.daily_loss_pct}")
        if isinstance(self.max_consecutive_losses, bool) or not isinstance(self.max_consecutive_losses, int) \
                or self.max_consecutive_losses < 1:
            raise ValueError(f"max_consecutive_losses는 1 이상 정수: {self.max_consecutive_losses!r}")
