"""트라이얼 #1 전략 파라미터 — `params_version = sr_v1`(사전등록 §1 표 · 레지스트리 #18).

sr_v1 SHA256 = `b02d1a1668261e0adb617e575154f19d1279017ec500f3b51a0354234c3fbce6`(§1 표 17~45행 · `anchor.SR_V1_SHA256`).
값은 전부 §1 표 그대로다. 하나라도 바뀌면 새 버전·새 트라이얼(§8). 피처 쪽 값(스윙 k·ATR 기간·VP)은 `features.SrV1`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from strategies.trial01 import anchor as A

SR_V1_SHA256 = A.SR_V1_SHA256
MINUTE_MS = 60_000


@dataclass(frozen=True)
class Trial01Params:
    band_m: Decimal = Decimal("0.5")              # 밴드 = 레벨 ± 0.5 × ATR_1m(60)
    n_nearest: int = 3                            # 방향마다 mark에 가까운 레벨 3개
    confirm_bars: int = 5                         # 터치 봉 포함 5봉 이내
    confirm_frac: Decimal = Decimal("0.6")        # 종가가 range 상위(롱)·하위(숏) 60%
    cooldown_ms: int = 60 * MINUTE_MS             # 같은 레벨 청산 후 60분
    sl_atr_mult: Decimal = Decimal("1.0")         # SL = 15m 스윙 ∓ 1.0 × ATR_15m(14)
    sl_min: Decimal = Decimal("0.0030")           # sl_dist ∈ [0.30%, 1.00%] 하드
    sl_max: Decimal = Decimal("0.0100")
    tp_min_r: Decimal = Decimal("1.5")            # 반대편 레벨이 1.5R 미만이면
    tp_fallback_r: Decimal = Decimal("2")         # TP = 2R(레벨이 없을 때도)
    trail_arm_r: Decimal = Decimal("1")           # +1R 도달 후
    trail_atr_mult: Decimal = Decimal("1.0")      # trail_dist = 1.0 × ATR_15m(14)
    trailing: bool = True                         # 사전등록 §1은 트레일링을 포함한다 — 엔진 기본값은 꺼짐(EntryIntent.trail=None)
    risk_pct: Decimal = Decimal("0.01")           # 사이징(§1 "기존 코드 그대로")
    l_min: int = 50
    l_max: int = 100


SR_V1_PARAMS = Trial01Params()
