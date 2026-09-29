"""트라이얼 #3 매개변수(`params_version = tf_v1` · 사전등록 §1 표 20~39행 · 레지스트리 #50) — 결과를 본 뒤 바꾸지 않는다(§8).

시각 값은 ms. 분위수 최소 정의 수 = ceil(0.99 × 90 × 1,440) = 128,304(§1 24행 "99% 이상"). 판정 가능 구간 = [t0 − 270분, t0 + 366분]
(= 120 + 5 + 240 + 1 · §1 35행). 슬리피지 0.0006은 §2(체결 시점 모델 · 결정 시점 B2는 기준가 m 그대로 — §1 29행).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from sizing.config import RegimeSizing, SizingLimits
from strategies.trial03.exit_schedule import HOLD_MIN

MIN_MS = 60_000


@dataclass(frozen=True)
class TfParams:
    q_lo: float = 0.005                        # p_evt
    q_hi: float = 0.995
    w_ref_days: int = 90
    quantile_min_defined: int = math.ceil(0.99 * 90 * 1440)
    r30_ms: int = 30 * MIN_MS
    oi_avail_ms: int = 5 * MIN_MS              # create_time + 5분부터
    oi_age_ms: int = 10 * MIN_MS               # 나이 ≤ 10분
    oi_lookback_ms: int = 30 * MIN_MS          # OI_prev = t − 30분
    cooldown_ms: int = 720 * MIN_MS            # 12시간(끝 제외)
    t_min_ms: int = 20 * MIN_MS
    t_max_ms: int = 120 * MIN_MS
    c_cool: float = 0.5
    rv_n: int = 5
    rv_peak_lookback_ms: int = 30 * MIN_MS
    atr_bucket_ms: int = 15 * MIN_MS
    atr_n: int = 14
    k_sl: Decimal = Decimal("1.5")
    sl_floor: Decimal = Decimal("0.0044")
    sl_ceiling: Decimal = Decimal("0.0500")
    hold_min: int = HOLD_MIN
    slippage: Decimal = Decimal("0.0006")
    risk_pct: Decimal = Decimal("0.01")
    l_min: int = 10
    l_max: int = 30
    e_ref: Decimal = Decimal(1000)
    n_stat: Decimal = Decimal(1000)
    span_before_ms: int = 270 * MIN_MS
    span_after_ms: int = (120 + 5 + 240 + 1) * MIN_MS


TF_V1 = TfParams()
#  실행 고정값(§1 38행 · 트라이얼 #2와 같은 헌법 값): 레버리지 대역 (10,30) · 청산 수수료 = 수량 × 추정 청산가 · pos_pct 캡 0.40(기본)
LIMITS = SizingLimits(leverage_range=(TF_V1.l_min, TF_V1.l_max), liq_fee_on_liq_price=True)
REGIME = RegimeSizing("trial03", TF_V1.risk_pct, TF_V1.l_min, TF_V1.l_max)
