"""사이징 설정 — 레짐별 파라미터 표. 값은 config(사전등록 대상)이고, 여기서는 **범위 검증만** 한다.

🔴 레짐은 레버리지를 **직접 고르지 않는다**(strategy-modules §1 · "레짐 라벨 → 레버리지 직접 매핑 반려").
   레짐이 주는 것은 허용 구간 `[l_min, l_max]`와 비율(risk_pct·pos_pct)뿐이고, 실제 L은 SL 거리에서 도출된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#  사용자 확정(2026-09-12 open-decisions #1): 허용 레버리지 **범위**. 거래소 값이 아니라 정책 값이다.
#  거래소 상한(브라켓 initialLeverage)은 런타임 규칙에서 따로 적용된다.
PERMITTED_LEVERAGE: tuple[int, int] = (50, 100)


@dataclass(frozen=True)
class RegimeSizing:
    name: str
    risk_pct: Decimal      # L_raw = risk_pct / sl_dist_pct 의 분자
    pos_pct: Decimal       # 진입 격리 마진 = equity × pos_pct (명목 = 마진 × L)
    l_min: int
    l_max: int

    def __post_init__(self):
        lo, hi = PERMITTED_LEVERAGE
        for f in ("risk_pct", "pos_pct"):
            if not isinstance(getattr(self, f), Decimal):
                raise TypeError(f"{self.name}.{f}는 Decimal이어야 한다")
        if not (isinstance(self.l_min, int) and isinstance(self.l_max, int)):
            raise TypeError(f"{self.name}: l_min/l_max는 정수(거래소 레버리지는 정수)")
        if not lo <= self.l_min <= self.l_max <= hi:
            raise ValueError(f"{self.name}: [{self.l_min}, {self.l_max}]가 허용 범위 [{lo}, {hi}] 밖이거나 역전")
        if not 0 < self.risk_pct < 1:
            raise ValueError(f"{self.name}: risk_pct {self.risk_pct}는 (0, 1)")
        if not 0 < self.pos_pct <= 1:
            raise ValueError(f"{self.name}: pos_pct {self.pos_pct}는 (0, 1]")
