"""사이징 설정 — 레짐 표 + 사이징 한계. 값은 config(사전등록 대상)이고, 여기서는 **범위 검증만** 한다.

레지스트리 #2(2026-09-15 사용자 결정): 위험 예산이 1차 제약이고 pos_pct는 **도출**된다(레짐이 고르지 않는다).
🔴 레짐은 레버리지를 직접 고르지 않는다 — 허용 구간 `[l_min, l_max]`와 risk_pct만 준다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#  사용자 확정(2026-09-12 open-decisions #1): 허용 레버리지 **범위**. 거래소 값이 아니라 정책 값이다.
#  거래소 상한(브라켓 initialLeverage)은 런타임 규칙에서 따로 적용된다.
PERMITTED_LEVERAGE: tuple[int, int] = (50, 100)

#  사용자 확정(2026-09-15 레지스트리 #2) 정책 값 — 거래소 값 아님(tests/test_no_exchange_literals.py 허용 목록)
#  레지스트리 #5(2026-09-15 · 시장 데이터를 보기 전에 사전확약) — SL·청산 게이트. 14일 페이퍼 후 새 행으로만 재평가, 사후 완화 금지.
SL_BUFFER_REL = Decimal("1.5")            # 조건 1: sl_dist × 1.5 < liq_dist
SL_LIQ_MIN_GAP = Decimal("0.0010")        # 조건 2: liq_dist − sl_dist ≥ 10 bps (절대)
SL_TRIGGER_BASIS = "MARK"                 # SL 트리거는 mark 가격(청산과 같은 기준) — last 가격 아님
POS_PCT_MAX_DEFAULT = Decimal("0.40")     # 하드 캡: 마진 ≤ equity × 40%
POS_PCT_MIN_DEFAULT = Decimal("0.10")     # 권고: 미만이면 기록만, 크기를 부풀리지 않는다
LOSS_TOLERANCE_DEFAULT = Decimal("0")     # 최종 loss_at_sl > budget × (1 + tol) 이면 거부


@dataclass(frozen=True)
class RegimeSizing:
    name: str
    risk_pct: Decimal      # risk_budget = equity × risk_pct
    l_min: int
    l_max: int

    def __post_init__(self):
        lo, hi = PERMITTED_LEVERAGE
        if not isinstance(self.risk_pct, Decimal):
            raise TypeError(f"{self.name}.risk_pct는 Decimal이어야 한다")
        if not (isinstance(self.l_min, int) and isinstance(self.l_max, int)):
            raise TypeError(f"{self.name}: l_min/l_max는 정수(거래소 레버리지는 정수)")
        if not lo <= self.l_min <= self.l_max <= hi:
            raise ValueError(f"{self.name}: [{self.l_min}, {self.l_max}]가 허용 범위 [{lo}, {hi}] 밖이거나 역전")
        if not 0 < self.risk_pct < 1:
            raise ValueError(f"{self.name}: risk_pct {self.risk_pct}는 (0, 1)")


@dataclass(frozen=True)
class SizingLimits:
    """게이트 한계. 기본값은 **사전확약 값 그 자체**다(레지스트리 #2·#5) — 테스트가 값을 잠근다."""
    buffer_rel: Decimal = SL_BUFFER_REL
    min_gap: Decimal = SL_LIQ_MIN_GAP
    pos_pct_max: Decimal = POS_PCT_MAX_DEFAULT
    pos_pct_min: Decimal = POS_PCT_MIN_DEFAULT
    loss_tolerance: Decimal = LOSS_TOLERANCE_DEFAULT

    def __post_init__(self):
        for f in ("buffer_rel", "min_gap", "pos_pct_max", "pos_pct_min", "loss_tolerance"):
            if not isinstance(getattr(self, f), Decimal):
                raise TypeError(f"SizingLimits.{f}는 Decimal이어야 한다")
        if self.buffer_rel < 1:
            raise ValueError(f"buffer_rel {self.buffer_rel} < 1은 청산 거리 게이트를 **느슨하게** 만든다")
        if self.min_gap < 0:
            raise ValueError(f"min_gap {self.min_gap} < 0")
        if not 0 < self.pos_pct_max <= 1:
            raise ValueError(f"pos_pct_max {self.pos_pct_max}는 (0, 1]")
        if not 0 <= self.pos_pct_min <= self.pos_pct_max:
            raise ValueError(f"pos_pct_min {self.pos_pct_min}는 [0, pos_pct_max]")
        if self.loss_tolerance < 0:
            raise ValueError(f"loss_tolerance {self.loss_tolerance} < 0")
