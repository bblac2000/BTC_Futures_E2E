"""layer 7 설정 — strategy-modules §6.

- 킬스위치 값은 **레지스트리 #11**(사용자 결정 2026-09-16 · #10 PENDING 해소): 일일 손실 5%(UTC 날짜 시작 equity 대비) ·
  연속 순손실 5회 · 청산 1회 · 포지션 소실 1회. 페이퍼 14일차 재평가는 **새 행**으로만.
  `KillSwitchLimits` 필드에는 여전히 기본값이 없다 — 기동 배선은 `REGISTERED_KILL_SWITCH`를 명시적으로 넘긴다.
- stale 자동 청산(레지스트리 #12)은 새 숫자가 없다 — 레지스트리 #1 `DeliverySpec.grace_sec`(120초)를 그대로 쓴다.
- 일일 손실 트립 날의 `/start`(레지스트리 #13)는 00:00 UTC까지 아무것도 바꾸지 않고 아래 문구로 답한다.
- rate-limit 80%는 스킬 §6("80%에서 폴링 완화")의 값이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#  🔒 레지스트리 #11 (사용자 결정 2026-09-16) — 테스트 `test_kill_switch_values_are_exactly_registry_11`이 잠근다
DAILY_LOSS_PCT = Decimal("0.05")
MAX_CONSECUTIVE_LOSSES = 5
MAX_LIQUIDATIONS = 1
MAX_VANISHED = 1
#  🔒 레지스트리 #13 — 사용자가 정한 응답 문구(글자 그대로)
DAILY_LOSS_RESUME_REFUSED = "blocked by daily-loss limit until 00:00 UTC"
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


REGISTERED_KILL_SWITCH = KillSwitchLimits(daily_loss_pct=DAILY_LOSS_PCT, max_consecutive_losses=MAX_CONSECUTIVE_LOSSES)
