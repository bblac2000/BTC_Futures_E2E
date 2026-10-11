"""트라이얼 #4 매개변수(`params_version = tc_v3` · 사전등록 r3 §1 표 16~39행 · 레지스트리 #70) — 결과를 본 뒤 바꾸지 않는다(§8).

규약 C24: 보유 상수는 `exit_schedule.HOLD_MIN`을 import한다(두 번째 리터럴 없음). C26 [PROPOSED]: 청산 수수료 명목 = 수량 × 추정 청산가
(트라이얼 #2·#3과 같은 값 — `liq_dist`에는 들어가지 않는다). 슬리피지 0.0006은 §2(체결 시점 모델).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sizing.config import RegimeSizing, SizingLimits
from strategies.trial04.exit_schedule import HOLD_MIN


@dataclass(frozen=True)
class TcParams:
    q_lo: float = 0.10                         # L: p_T ≤ Q0.10
    q_hi: float = 0.90                         # S: p_T ≥ Q0.90
    n_trail: int = 270                         # T보다 엄격히 앞선 유효 인쇄
    atr_n: int = 14                            # ATR_1d(14)
    k_sl: Decimal = Decimal("2.0")
    sl_floor: Decimal = Decimal("0.010")
    sl_ceiling: Decimal = Decimal("0.200")
    hold_min: int = HOLD_MIN
    slippage: Decimal = Decimal("0.0006")
    risk_pct: Decimal = Decimal("0.01")
    l_min: int = 3
    l_max: int = 30
    e_ref: Decimal = Decimal(1000)
    n_stat: Decimal = Decimal(1000)
    p2_delays: tuple[int, ...] = (1, 3)        # P2: +1 · +3 인쇄(8h · 24h)


TC_V3 = TcParams()
LIMITS = SizingLimits(leverage_range=(TC_V3.l_min, TC_V3.l_max), liq_fee_on_liq_price=True)
REGIME = RegimeSizing("trial04", TC_V3.risk_pct, TC_V3.l_min, TC_V3.l_max)
