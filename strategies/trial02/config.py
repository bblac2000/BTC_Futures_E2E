"""트라이얼 #2 파라미터(`params_version = bo_v1` · 사전등록 §1 표 · 레지스트리 #35) — 결과를 본 뒤 바꾸지 않는다(§8)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sizing.config import RegimeSizing, SizingLimits


@dataclass(frozen=True)
class BoParams:
    k: Decimal                 # 띠 = O_d ± k × R_{d−1}
    sl_floor: Decimal          # sl_dist 바닥(포함)
    sl_ceiling: Decimal        # sl_dist 천장(포함)
    trail_arm_r: Decimal       # +1R 무장
    trail_dist_r: Decimal      # 거리 1R
    tp_r: Decimal              # TP +2R
    risk_pct: Decimal          # budget = E_ref × 1%
    l_min: int
    l_max: int
    e_ref: Decimal             # 실행 원장 고정 사이징 자본
    n_stat: Decimal            # 통계 원장
    b_median_days: int         # Arm B 중앙값 창(d−21 … d−2)
    last_cross_minute: int     # 체결(다음 시가) < 23:59 → 교차 봉 분 ≤ 1437 · 1438은 late_cross · 1439는 보지 않는다
    exit_minute: int           # 23:59 봉 시가 time_exit


BO_V1 = BoParams(k=Decimal("0.5"), sl_floor=Decimal("0.0030"), sl_ceiling=Decimal("0.0500"), trail_arm_r=Decimal(1),
                 trail_dist_r=Decimal(1), tp_r=Decimal(2), risk_pct=Decimal("0.01"), l_min=10, l_max=30, e_ref=Decimal(1000),
                 n_stat=Decimal(1000), b_median_days=20, last_cross_minute=1437, exit_minute=1439)

#  실행 고정값(§1 사이징 행 · 규약 1·3·4) — 레버리지 대역 (10,30) · 청산 수수료 = 수량 × 추정 청산가
LIMITS = SizingLimits(leverage_range=(BO_V1.l_min, BO_V1.l_max), liq_fee_on_liq_price=True)
P1_REGIME = RegimeSizing("trial02_P1", BO_V1.risk_pct, BO_V1.l_min, BO_V1.l_max)
