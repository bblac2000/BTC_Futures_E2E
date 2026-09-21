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
    STALE_DATA = "stale_data"              # 레지스트리 #12 — 피드 무수신이 #1 grace를 넘었다(PAPER는 마지막 수신 mark로 체결)
    TRAIL = "trail"                        # 트레일링으로 옮겨진 SL에서 청산(`EntryIntent.trail`이 있을 때만 · 기본 꺼짐)


class SkipReason(StrEnum):
    LEVERAGE_NOT_CONFIRMED = "leverage_not_confirmed"
    SL_CROSSED_BEFORE_FILL = "sl_crossed_before_fill"
    SIZING_REJECTED = "sizing_rejected"       # 실행 mark로 다시 한 사이징이 거부(사유는 decision.reason)
    SEND_FAILED = "send_failed"
    ENTRIES_BLOCKED = "entries_blocked"       # 결정 뒤 체결 전에 진입 게이트가 닫혔다(layer 8 EntryGate)


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
    #  LIVE 채택(주문 결과 불명 → 거래소 수량이 확인 체결보다 큼)일 때 **채택 시점 positionRisk** — 수량·평균가의 진리원.
    #  이 이벤트가 채택 포지션의 open 행이다(db: reason='adopted_from_exchange'). 정상 체결은 None.
    adopted: PositionRisk | None = None
    #  지갑에서 뺀 진입 수수료 합(확인 체결 + 채택 수량의 런타임 taker 추정) — 체결 합과 다를 수 있다(Codex L6·7 #4)
    entry_commission: Decimal | None = None


@dataclass(frozen=True)
class PositionSynced:
    """LIVE 청산 직전 거래소 수량이 내부보다 **커서** 거래소 기준으로 동기화했다(진리원 = 그 시점 positionRisk).
    줄어든 경우는 사라진 부분을 `PositionVanished`로 낸다(수정 행으로 덮지 않는다 · Codex L6·7 재검토 #1).
    db: root open 행의 수정 행(reason 'adopted_from_exchange') — close보다 먼저 나온다(Codex L6·7 #3)."""
    ts_ms: int
    direction: Direction
    previous_qty: Decimal
    qty: Decimal
    entry_price: Decimal
    extra_commission: Decimal              # 늘어난 수량의 진입 수수료 추정(줄었으면 0)
    position_risk: PositionRisk


@dataclass(frozen=True)
class PositionVanished:
    """LIVE — 내부 포지션의 전부(거래소 수량 0) 또는 일부(청산 직전 거래소 수량 감소)가 거래소에서 사라졌다
    (거래소 강제 청산·ADL·수동 청산 의심). `qty` = 사라진 수량.
    손익은 모른다(추정하지 않는다) · 킬스위치는 청산 1회로 본다(Codex L6·7 #2)."""
    ts_ms: int
    direction: Direction
    qty: Decimal
    entry_price: Decimal
    detail: str


@dataclass(frozen=True)
class PositionRestored:
    """PAPER 재기동 — DB 열린 root 포지션과 마지막 엔진 스냅샷이 일치해 엔진에 복원했다(사용자 2026-09-16 (a)).
    DB: `engine_events`(root open 행은 그대로 — 뒤따르는 close가 같은 root에 붙는다)."""
    ts_ms: int
    direction: Direction
    qty: Decimal
    entry_price: Decimal
    detail: str
    state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PositionAbandoned:
    """PAPER 재기동 — DB에 열린 포지션이 있으나 스냅샷과 **일치하지 않아** 복원하지 않았다. 엔진은 flat으로 시작한다.
    DB: 그 root에 close 행(reason `restart_unrestored`, 손익 없음 — 추정하지 않는다). 거래 결과가 아니므로 킬스위치는 세지 않는다."""
    ts_ms: int
    direction: Direction
    qty: Decimal
    entry_price: Decimal
    detail: str


@dataclass(frozen=True)
class EntrySkipped:
    ts_ms: int
    decision: SizingDecision | None
    reason: SkipReason
    detail: str


@dataclass(frozen=True)
class TrailSet:
    """체결 직후 트레일링 설정(`EntryIntent.trail`이 있을 때만) — DB가 복원 대조용으로 남긴다(Codex 단계 d #3·#4)."""
    ts_ms: int
    arm_r: Decimal
    dist: Decimal
    r: Decimal                               # |체결 진입가 − 초기 SL|


@dataclass(frozen=True)
class TrailArmed:
    """+arm_r × R에 닿아 트레일링이 무장됐다(이후 SL을 조일 수 있다)."""
    ts_ms: int
    best: Decimal                            # 무장시킨 유리한 극값


@dataclass(frozen=True)
class StopTrailed:
    """트레일링이 SL을 조였다(`EntryIntent.trail`이 있을 때만 나온다). 새 SL은 **다음 봉/틱부터** 판정한다."""
    ts_ms: int
    old_sl: Decimal
    new_sl: Decimal


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
class PositionReduced:
    """청산 주문 일부만 체결(뒤 조각 실패·불명) — 체결된 부분의 손익·수수료는 지갑에 이미 반영됐다.
    db: 체결마다 `orders` + root에 연결된 `positions` close 행(수량 = 이번 체결분) → DB 남은 수량 = 엔진 잔량
    (사용자 2026-09-16: 대사가 스스로 맞도록). 킬스위치 연속 손실은 flat이 되는 `PositionClosed`에서만 센다."""
    ts_ms: int
    direction: Direction
    reason: ExitReason
    qty: Decimal                           # 이번에 닫힌 수량
    remaining_qty: Decimal
    entry_price: Decimal
    exit_price: Decimal
    fills: tuple[Fill, ...]
    realized_pnl_usdt: Decimal
    exit_commission_usdt: Decimal
    wallet_after: Decimal
    detail: str


@dataclass(frozen=True)
class WalletResynced:
    """엔진 지갑을 외부 진리원으로 옮겼다(LIVE: 소실 뒤 거래소 지갑 — 소실 손익은 추정하지 않고 이 차이로 들어온다)."""
    ts_ms: int
    previous: Decimal
    wallet: Decimal
    source: str                            # exchange
    detail: str


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
