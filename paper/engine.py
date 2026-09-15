"""체결·포지션 엔진 — **페이퍼와 라이브가 같은 코드 경로**다. 모드 차이는 송신기(`OrderSender`)와 아래 두 곳뿐:
  ① 진입 후 `positionRisk` 재조회 · `post_entry_liquidation_check` · 수량 대사 → **LIVE만**(레지스트리 #6)
  ② mark가 추정 청산가를 넘으면 PAPER는 청산을 **시뮬레이션**, LIVE는 알리고 SL 청산을 시도(청산은 거래소가 한다)

규칙(strategy-modules §6 · 레지스트리 #2·#4·#5):
- 전략은 **진입 의도**(방향·SL·TP·레짐)를 낸다. 결정 **이후** 첫 mark 틱(또는 다음 봉 시가)에서 그 mark와 현재 지갑으로
  `size_entry`를 다시 돌려 체결한다 — 결정 시점 최고 L은 #5 경계에 붙어 있어 가격이 조금만 움직여도 게이트를 깬다.
  체결 직전 SL이 이미 넘어갔으면(`SL_WRONG_SIDE`) 건너뛴다.
- 진입 전 레버리지 설정 응답 == decision.leverage 여야 주문한다.
- 한 틱/봉 안 우선순위 **청산 > SL > TP**. 봉 SL 체결 기준 = SL과 시가 중 불리한 쪽, 봉 TP = TP(갭 이득 없음).
- SL·TP·청산 판정 가격 = mark(#5 SL_TRIGGER_BASIS).
- 체결 후 실제 체결가·수량으로 #5 게이트·SL 손실 재계산 → **기록**(슬리피지·tick만큼 경계를 넘을 수 있다).
  SL 거리가 추정 청산 거리 이상(SL 전에 청산)이면 물리적 불변식 위반 → **즉시 청산**.
- PAPER 청산 손실 = 남은 격리 지갑(N/L − 진입 수수료, #4) + N × liquidationFee(#2) → 진입부터 총손실 N/L + N×fee.
- 펀딩: 직전 틱의 nextFundingTime 경계를 지나면 **직전 틱의** 펀딩율·mark로 정산. 간격이 런타임에 알려져 있으면
  경계가 그 간격의 배수(8h → 00/08/16 UTC)인지 확인, 아니면 `FeedError`.
- 주문 결과 불명(`OrderOutcomeUnknown`) → 진입 차단(대사 전까지). 청산 실패는 포지션을 유지하고 다음 트리거에서 재시도.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from exchange.errors import BinanceAPIError, LeverageNotConfirmed, OrderParamError, RulesError, TransportError
from exchange.gate import Mode
from exchange.normalize import RejectReason
from exchange.orders import Direction, Intent, close_position_orders, market_order_params
from exchange.rules import RuntimeRules
from paper.sender import OrderOutcomeUnknown, OrderSender
from paper.types import (
    EntriesBlocked,
    EntryFilled,
    EntrySkipped,
    ExitFailed,
    ExitReason,
    Fill,
    FundingSettled,
    LiquidationThresholdCrossed,
    MarkBar,
    MarkTick,
    PositionClosed,
    PostFillCheck,
    SkipReason,
)
from sizing.config import RegimeSizing, SizingLimits
from sizing.position import (
    SizingDecision,
    liquidation_estimate,
    post_entry_liquidation_check,
    size_entry,
    sl_gate_passes,
)

HOUR_MS = 3_600_000
SEND_ERRORS = (OrderOutcomeUnknown, BinanceAPIError, TransportError, OrderParamError)


class EntryRefused(ValueError):
    """진입 요청을 받을 수 없는 상태(거부된 결정·포지션/대기 중·진입 차단)."""


class FeedError(ValueError):
    """피드 값이 런타임 규칙과 모순(예: 펀딩 시각이 간격 격자 밖)."""


@dataclass(frozen=True)
class EntryIntent:
    """전략 출력 — 무엇을 원하는가. 크기·레버리지는 실행 시점에 엔진이 정한다."""
    direction: Direction
    sl: Decimal
    tp: Decimal | None
    regime: RegimeSizing
    decided_ms: int
    decision_mark: Decimal                 # 결정 시점 mark(기록·TP 방향 검사용 — 체결가 아님)


@dataclass
class OpenPosition:
    direction: Direction
    qty: Decimal
    entry_price: Decimal
    leverage: int
    sl: Decimal
    tp: Decimal | None
    liq_price_est: Decimal
    entry_commission: Decimal
    opened_ms: int
    decision: SizingDecision
    funding_paid: Decimal
    liq_alerted: bool = False

    @property
    def signed_qty(self) -> Decimal:
        return self.qty if self.direction is Direction.LONG else -self.qty


def _vwap(fills: list[Fill]) -> Decimal:
    q = sum((f.qty for f in fills), Decimal())
    return sum((f.qty * f.price for f in fills), Decimal()) / q


class Engine:
    def __init__(self, rules: RuntimeRules, sender: OrderSender, *, mode: Mode, wallet: Decimal, limits: SizingLimits):
        if sender.mode is not mode:
            raise ValueError(f"엔진 모드 {mode} ≠ 송신기 모드 {sender.mode}")
        if not isinstance(wallet, Decimal):
            raise TypeError("wallet은 Decimal")
        self.rules, self.sender, self.mode, self.limits = rules, sender, mode, limits
        self.wallet = wallet
        self.position: OpenPosition | None = None
        self.pending: EntryIntent | None = None
        self.entries_blocked: str | None = None
        self._last_tick: MarkTick | None = None

    # ── 입력 ────────────────────────────────────────────────────────────────
    def request_entry(self, intent: EntryIntent) -> None:
        if type(intent.direction) is not Direction:
            raise EntryRefused(f"direction은 Direction: {intent.direction!r}")
        if self.entries_blocked:
            raise EntryRefused(f"진입 차단 중: {self.entries_blocked}")
        if self.position is not None or self.pending is not None:
            raise EntryRefused("포지션 또는 대기 진입이 이미 있다(원웨이 단일 포지션)")
        long_ = intent.direction is Direction.LONG
        if intent.tp is not None and ((long_ and intent.tp <= intent.decision_mark)
                                      or (not long_ and intent.tp >= intent.decision_mark)):
            raise EntryRefused(f"TP {intent.tp}가 {intent.direction} 결정 mark {intent.decision_mark}의 잘못된 쪽")
        self.pending = intent

    def on_tick(self, t: MarkTick) -> list[object]:
        ev: list[object] = []
        prev = self._last_tick
        if prev is not None and self.position is not None and prev.ts_ms < prev.next_funding_ms <= t.ts_ms:
            ev.append(self._settle_funding(prev.next_funding_ms, prev.funding_rate, prev.mark))
        self._check_funding_grid(t)
        self._last_tick = t
        if self.pending is not None and t.ts_ms > self.pending.decided_ms:
            ev += self._execute_entry(t.mark, t.ts_ms)
            if self.position is None:
                return ev
        if self.position is not None:
            ev += self._evaluate(t.ts_ms, low=t.mark, high=t.mark, sl_ref=t.mark, tp_ref=t.mark, mark=t.mark)
        return ev

    def on_bar(self, b: MarkBar) -> list[object]:
        ev: list[object] = []
        if self.pending is not None and b.open_ms > self.pending.decided_ms:
            ev += self._execute_entry(b.open, b.open_ms)
        pos = self.position
        if pos is None:
            return ev
        if pos.direction is Direction.LONG:
            sl_ref, tp_ref = min(pos.sl, b.open), pos.tp
        else:
            sl_ref, tp_ref = max(pos.sl, b.open), pos.tp
        ev += self._evaluate(b.close_ms, low=b.low, high=b.high, sl_ref=sl_ref, tp_ref=tp_ref, mark=b.close)
        return ev

    def on_funding(self, *, ts_ms: int, rate: Decimal, mark: Decimal) -> list[object]:
        """봉 단위 재생용 — 실제 펀딩 이력(정산 시각·율·mark)을 넣는다."""
        return [self._settle_funding(ts_ms, rate, mark)] if self.position is not None else []

    def close_now(self, *, ref_mark: Decimal, ts_ms: int, reason: ExitReason = ExitReason.MANUAL) -> list[object]:
        return self._exit(reason, ref_mark, ts_ms) if self.position is not None else []

    # ── 내부 ────────────────────────────────────────────────────────────────
    def _check_funding_grid(self, t: MarkTick) -> None:
        interval = self.rules.funding.interval_hours
        if interval and t.next_funding_ms % (interval * HOUR_MS) != 0:
            raise FeedError(f"nextFundingTime {t.next_funding_ms}이 {interval}h 격자 밖 — 런타임 fundingInfo와 모순")

    def _settle_funding(self, ts_ms: int, rate: Decimal, mark: Decimal) -> FundingSettled:
        pos = self.position
        assert pos is not None
        paid = pos.signed_qty * mark * rate
        self.wallet -= paid
        pos.funding_paid += paid
        return FundingSettled(ts_ms, rate, mark, pos.signed_qty, paid, self.wallet)

    def _block(self, ts_ms: int, reason: str) -> EntriesBlocked:
        self.entries_blocked = reason
        return EntriesBlocked(ts_ms, reason)

    def _execute_entry(self, ref_mark: Decimal, ts_ms: int) -> list[object]:
        pe = self.pending
        assert pe is not None
        self.pending = None
        d = size_entry(ref_mark, pe.sl, pe.direction, self.wallet, pe.regime, self.rules, self.limits)
        if not d.ok or d.leverage is None:
            why = SkipReason.SL_CROSSED_BEFORE_FILL if d.reason is RejectReason.SL_WRONG_SIDE else SkipReason.SIZING_REJECTED
            return [EntrySkipped(ts_ms, d, why, f"실행 mark {ref_mark} · {d.reason} · {d.detail}")]
        try:
            echo = self.sender.set_leverage(d.leverage)
        except (LeverageNotConfirmed, BinanceAPIError, TransportError) as e:
            return [EntrySkipped(ts_ms, d, SkipReason.LEVERAGE_NOT_CONFIRMED, f"{type(e).__name__}: {e}")]
        if echo != d.leverage:
            return [EntrySkipped(ts_ms, d, SkipReason.LEVERAGE_NOT_CONFIRMED, f"응답 {echo}x ≠ 결정 {d.leverage}x")]

        sr = self.rules.symbol_rules
        fills: list[Fill] = []
        ev: list[object] = []
        try:
            for q in d.chunks:
                p = market_order_params(sr.symbol, d.direction, Intent.ENTRY, q, sr)
                fills.append(self.sender.send_market(p, ref_mark=ref_mark, ts_ms=ts_ms))
        except SEND_ERRORS as e:
            if not fills or isinstance(e, OrderOutcomeUnknown):
                ev.append(self._block(ts_ms, f"진입 주문 실패/불명 {type(e).__name__}: {e} · 체결 {len(fills)}조각"))
            if not fills:
                if not isinstance(e, OrderOutcomeUnknown):
                    ev.append(EntrySkipped(ts_ms, d, SkipReason.SEND_FAILED, f"{type(e).__name__}: {e}"))
                return ev
            if not self.entries_blocked:
                ev.append(self._block(ts_ms, f"진입 일부 조각만 체결 {len(fills)}/{len(d.chunks)}"))

        qty = sum((f.qty for f in fills), Decimal())
        entry = _vwap(fills)
        commission = sum((f.commission for f in fills), Decimal())
        self.wallet -= commission
        post = self._post_fill(d, entry, qty)
        self.position = OpenPosition(d.direction, qty, entry, d.leverage, d.sl, pe.tp, post.liq_price_est, commission,
                                     ts_ms, d, Decimal())
        ev.insert(0, EntryFilled(ts_ms, d, tuple(fills), d.leverage, post))

        if self.mode is Mode.LIVE:
            ev += self._live_reconcile(ts_ms, expected=self.position.signed_qty)
        if not post.sl_before_liquidation:
            ev += self._exit(ExitReason.POST_FILL_GATE, ref_mark, ts_ms)
        return ev

    def _post_fill(self, d: SizingDecision, entry: Decimal, qty: Decimal) -> PostFillCheck:
        assert d.leverage is not None
        long_ = d.direction is Direction.LONG
        notional = qty * entry
        sl_dist = (entry - d.sl) / entry if long_ else (d.sl - entry) / entry
        loss = qty * abs(entry - d.sl)
        try:
            est = liquidation_estimate(d.direction, entry, notional, d.leverage, self.rules)
            liq_price, liq_dist, bracket = est.price, est.dist_pct, est.bracket
            gate_ok = (sl_dist > 0 and sl_gate_passes(sl_dist, liq_dist, self.limits)
                       and d.leverage <= self.rules.bracket_for_notional(notional).initial_leverage)
            sl_first = 0 < sl_dist < liq_dist
        except RulesError:
            assert d.liq_price_est is not None and d.liq_dist_pct is not None and d.bracket is not None
            liq_price, liq_dist, bracket, gate_ok, sl_first = d.liq_price_est, d.liq_dist_pct, d.bracket, False, False
        lc = None
        if self.mode is Mode.LIVE:
            pr = self.sender.position_risk()
            if pr is not None:
                lc = post_entry_liquidation_check(d, self.rules, entry_price=entry, qty=qty,
                                                  exchange_liq_price=pr.liquidation_price)
        return PostFillCheck(entry_price=entry, qty=qty, notional=notional, sl_dist_pct=sl_dist, liq_price_est=liq_price,
                             liq_dist_pct=liq_dist, bracket=bracket, gate_ok=gate_ok, loss_at_sl_usdt=loss,
                             loss_over_budget=loss > d.risk_budget_usdt * (1 + self.limits.loss_tolerance),
                             sl_before_liquidation=sl_first, liquidation_check=lc)

    def _live_reconcile(self, ts_ms: int, *, expected: Decimal) -> list[object]:
        try:
            pr = self.sender.position_risk()
        except (OrderOutcomeUnknown, BinanceAPIError, TransportError) as e:
            return [self._block(ts_ms, f"positionRisk 재조회 실패 {type(e).__name__}: {e}")]
        if pr is None or pr.amt != expected:
            return [self._block(ts_ms, f"대사 불일치: 내부 {expected} · 거래소 {None if pr is None else pr.amt}")]
        return []

    def _evaluate(self, ts_ms: int, *, low: Decimal, high: Decimal, sl_ref: Decimal, tp_ref: Decimal | None,
                  mark: Decimal) -> list[object]:
        pos = self.position
        assert pos is not None
        long_ = pos.direction is Direction.LONG
        ev: list[object] = []
        liq_hit = low <= pos.liq_price_est if long_ else high >= pos.liq_price_est
        if liq_hit:
            if self.mode is Mode.PAPER:
                return self._liquidate(ts_ms)
            if not pos.liq_alerted:
                pos.liq_alerted = True
                ev.append(LiquidationThresholdCrossed(ts_ms, mark, pos.liq_price_est))
        sl_hit = low <= pos.sl if long_ else high >= pos.sl
        if sl_hit:
            return ev + self._exit(ExitReason.SL, sl_ref, ts_ms)
        tp = pos.tp
        if tp is not None and (high >= tp if long_ else low <= tp):
            return ev + self._exit(ExitReason.TP, tp if tp_ref is None else tp_ref, ts_ms)
        return ev

    def _liquidate(self, ts_ms: int) -> list[object]:
        pos = self.position
        assert pos is not None
        n = pos.qty * pos.entry_price
        loss = n / Decimal(pos.leverage) - pos.entry_commission + n * self.rules.symbol_rules.liquidation_fee
        self.wallet -= loss
        self.position = None
        return [PositionClosed(ts_ms, pos.direction, ExitReason.LIQUIDATION, pos.qty, pos.entry_price, None, (), -loss,
                               Decimal(), pos.funding_paid, self.wallet)]

    def _exit(self, reason: ExitReason, ref_mark: Decimal, ts_ms: int) -> list[object]:
        pos = self.position
        assert pos is not None
        sr = self.rules.symbol_rules
        fills: list[Fill] = []
        failure: Exception | None = None
        try:
            for p in close_position_orders(pos.signed_qty, sr):
                fills.append(self.sender.send_market(p, ref_mark=ref_mark, ts_ms=ts_ms))
        except SEND_ERRORS as e:
            failure = e
        ev: list[object] = []
        if fills:
            q = sum((f.qty for f in fills), Decimal())
            px = _vwap(fills)
            pnl = (px - pos.entry_price) * q if pos.direction is Direction.LONG else (pos.entry_price - px) * q
            comm = sum((f.commission for f in fills), Decimal())
            self.wallet += pnl - comm
            if q == pos.qty:
                self.position = None
                ev.append(PositionClosed(ts_ms, pos.direction, reason, q, pos.entry_price, px, tuple(fills), pnl, comm,
                                         pos.funding_paid, self.wallet))
            else:
                pos.qty -= q
                ev.append(ExitFailed(ts_ms, reason, f"일부 청산 {q} · 잔량 {pos.qty}"))
        if failure is not None:
            ev.append(ExitFailed(ts_ms, reason, f"{type(failure).__name__}: {failure}"))
            ev.append(self._block(ts_ms, f"청산 주문 실패/불명 — 대사 필요: {failure}"))
        if self.mode is Mode.LIVE and self.position is None:
            ev += self._live_reconcile(ts_ms, expected=Decimal())
        return ev

