"""페이퍼 체결 모델 설정 — 거래소 값이 아니라 **측정값·정책 값**이다(tests/test_no_exchange_literals.py 허용 목록).

수수료는 여기 없다 — 항상 런타임 `commissionRate`의 taker(RuntimeRules.commission.taker).
"""
from __future__ import annotations

from decimal import Decimal

#  스킬 exchange-rules §6 · strategy-modules §6 "페이퍼 체결 모델": 실측 왕복 슬리피지 0.016 bps(E2E Phase 1-A, 50~1,000 USDT, 2026-08 레짐).
#  보수: **편도마다 왕복값 전체**를 불리한 방향으로 적용하고, 가격은 불리한 쪽 tick으로 반올림한다.
PAPER_SLIPPAGE_RATE = Decimal("0.0000016")
PAPER_SLIPPAGE_TAG = "0.016 bps round-trip measured E2E Phase 1-A 2026-08 regime (50~1,000 USDT) · applied per side · recalibrate"
