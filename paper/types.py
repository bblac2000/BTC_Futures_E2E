"""layer 3 값 타입 — 피드 입력 · 체결 · 엔진 이벤트. layer 4 `orders`·`positions`·`funding_events` 행의 원천."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from exchange.orders import Direction, Side
from sizing.position import LiquidationCheck, SizingDecision


@dataclass(frozen=True)
class MarkTick:
    """markPrice 1s 한 틱(`@markPrice@1s`: E·p·r·T). SL·TP·청산 판정의 기준 가격(레지스트리 #5 SL_TRIGGER_BASIS=MARK)."""
    ts_ms: int
    mark: Decimal
    funding_rate: Decimal          # r — 다음 정산에 적용될 펀딩율
    next_funding_ms: int           # T — 다음 정산 시각


@dataclass(frozen=True)
class MarkBar:
    """mark 1m 봉(markPriceKlines) — 봉 단위 재생. 펀딩은 봉에 없으므로 `Engine.on_funding`으로 따로 넣는다."""
    open_ms: int
    close_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class Fill:
    order_id: str
    side: Side
    qty: Decimal
    price: Decimal
    commission: Decimal
    reduce_only: bool
    ts_ms: int
    ref_mark: Decimal | None
    commission_estimated: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PositionRisk:
    """LIVE 전용 — 거래소 positionRisk BOTH 행 요약. PAPER는 항상 None(레지스트리 #6)."""
    amt: Decimal
    entry_price: Decimal
    liquidation_price: Decimal
    raw: dict[str, Any] = field(default_factory=dict)


class ExitReason(StrEnum):
    SL = "sl"
    TP = "tp"
    LIQUIDATION = "liquidation"
    POST_FILL_GATE = "post_fill_gate"      # 실제 체결 기준 #5 게이트 실패(또는 SL이 청산가 뒤) → 즉시 청산
    MANUAL = "manual"                      # 텔레그램 /close 등


class SkipReason(StrEnum):
    LEVERAGE_NOT_CONFIRMED = "leverage_not_confirmed"
    SL_CROSSED_BEFORE_FILL = "sl_crossed_before_fill"
    SIZING_REJECTED = "sizing_rejected"       # 실행 mark로 다시 한 사이징이 거부(사유는 decision.reason)
    SEND_FAILED = "send_failed"


@dataclass(frozen=True)
class PostFillCheck:
    """체결 후 재검증(Codex L2 Q7) — 결정 시점 값이 아니라 **실제 체결가·수량**으로 다시 계산한다."""
    entry_price: Decimal
    qty: Decimal
    notional: Decimal
    sl_dist_pct: Decimal
    liq_price_est: Decimal                 # #4 모델(수수료 차감) — PAPER 청산 시뮬레이션 기준
    liq_dist_pct: Decimal
    bracket: int
    gate_ok: bool                          # #5 게이트 + 브라켓 레버리지 상한 — 실패 시 즉시 청산(사전확약 게이트)
    sl_before_liquidation: bool            # 물리적 불변식: SL 거리 < 추정 청산 거리(gate_ok면 항상 참 · 진단용)
    loss_at_sl_usdt: Decimal
    loss_over_budget: bool                 # 기록만(슬리피지로 예산을 약간 넘을 수 있다) — 청산 사유 아님
    liquidation_check: LiquidationCheck | None   # LIVE만(positionRisk.liquidationPrice) · PAPER None


@dataclass(frozen=True)
class EntryFilled:
    ts_ms: int
    decision: SizingDecision
    fills: tuple[Fill, ...]
    leverage: int
    post_fill: PostFillCheck


@dataclass(frozen=True)
class EntrySkipped:
    ts_ms: int
    decision: SizingDecision | None
    reason: SkipReason
    detail: str


@dataclass(frozen=True)
class PositionClosed:
    ts_ms: int
    direction: Direction
    reason: ExitReason
    qty: Decimal
    entry_price: Decimal
    exit_price: Decimal | None             # 청산(LIQUIDATION)은 체결이 없다
    fills: tuple[Fill, ...]
    realized_pnl_usdt: Decimal             # 체결가 기준(mark 아님) · 청산은 손실액
    exit_commission_usdt: Decimal
    funding_paid_usdt: Decimal             # 보유 중 누적(+ = 지불)
    wallet_after: Decimal


@dataclass(frozen=True)
class FundingSettled:
    ts_ms: int                             # 정산 시각(T)
    rate: Decimal
    mark: Decimal
    signed_qty: Decimal
    paid_usdt: Decimal                     # + = 지불(LONG·양수 펀딩)
    wallet_after: Decimal


@dataclass(frozen=True)
class FundingMissed:
    """피드 공백으로 건너뛴 정산 경계 — 그 경계의 펀딩율을 모르므로 **추정하지 않고** 알린다(엔진은 진입 차단)."""
    ts_ms: int
    boundaries_ms: tuple[int, ...]
    signed_qty: Decimal


@dataclass(frozen=True)
class LiquidationThresholdCrossed:
    """LIVE — mark가 추정 청산가를 넘었다. 청산은 거래소가 한다(엔진은 지갑을 바꾸지 않고 알린다)."""
    ts_ms: int
    mark: Decimal
    liq_price_est: Decimal


@dataclass(frozen=True)
class EntriesBlocked:
    ts_ms: int
    reason: str


@dataclass(frozen=True)
class ExitFailed:
    ts_ms: int
    reason: ExitReason
    detail: str
