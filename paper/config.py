"""페이퍼 체결 모델 설정 — 거래소 값이 아니라 **사전확약 정책 값**이다(tests/test_no_exchange_literals.py 허용 목록).

수수료는 여기 없다 — 항상 런타임 `commissionRate`의 taker(RuntimeRules.commission.taker).
"""
from __future__ import annotations

from decimal import Decimal

#  레지스트리 #7(사용자 2026-09-15): mark 기준 체결에 **편도 2 bps**를 불리한 방향으로, 가격은 불리한 tick으로 반올림.
#  근거 = 이 저장소 7일 측정 |mark − mid|/mid p99 1.835 bps(ops_log 2026-09-15). 스킬의 0.016 bps를 페이퍼에 한해 대체.
#  재평가는 페이퍼 14일차 새 행에서만.
#  사용자 결정(2026-09-15, 레지스트리 #7 부기): **LIVE 사이징의 예상 체결가도 이 값**이다(`paper.sender.adverse_fill_estimate`
#  한 함수). 이름에 PAPER가 남은 건 도입 이력 때문 — 실제 체결만 모드별로 다르다.
PAPER_SLIPPAGE_RATE = Decimal("0.0002")
PAPER_SLIPPAGE_TAG = "registry #7 · 2 bps per side (7-day |mark-mid|/mid p99 1.835 bps) · adverse tick · re-evaluate paper day 14"
