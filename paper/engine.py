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
- 사이징 가격 = 송신기의 예상 체결가(`quote_fill_price`: PAPER·LIVE 모두 레지스트리 #7 mark ± 2 bps 불리 tick — #9). LIVE는 실제 체결만 다르다.
- 체결 후 실제 체결가·수량으로 #5 게이트·SL 손실 재계산 → #5가 깨지면 **즉시 청산**(사전확약 게이트 · Codex L3 검토 4).
  PAPER는 체결가로 사이징하므로 깨지지 않고, LIVE는 실제 슬리피지만큼 깨질 수 있다.
- PAPER 청산 손실 = 남은 격리 지갑(N/L − 진입 수수료 − 누적 펀딩, #4) + N × liquidationFee(#2) → 진입부터 총손실 N/L + N×fee.
- 펀딩: 직전 틱의 nextFundingTime 경계를 지나면 **직전 틱의** 펀딩율·mark로 정산하고 추정 청산가를 갱신(격리 지갑 감소).
  간격이 런타임에 알려져 있으면 경계가 격자(8h → 00/08/16 UTC) 위인지 확인(`FeedError`), 공백으로 건너뛴 경계는
  율을 모르므로 `FundingMissed` + 진입 차단.
- LIVE 청산은 거래소가 들고 있는 수량을 닫는다. 진입 응답 불명이면 거래소 수량을 포지션으로 채택한다.
- 주문 결과 불명(`OrderOutcomeUnknown`) → 진입 차단(대사 전까지). 청산 실패는 포지션을 유지하고 다음 트리거에서 재시도.
- 진입 차단 사유는 **목록**(`entries_blocked`) — 사유를 덮어쓰지 않는다 · 해제는 사람의 /start(`clear_blocks`)만(layer 8).
- 부분 청산 → `PositionReduced`(체결·손익·잔량) · LIVE 봉 대사에서 거래소 flat → `vanish`(주문 없이 내부 close + `PositionVanished`)
  · LIVE 소실 손익은 추정하지 않고 거래소 지갑 재동기화(`sync_wallet` → `WalletResynced`)로 들어온다(사용자 2026-09-16).
- PAPER 재기동 복원: `position_state()`(엔진 스냅샷에 들어감) ↔ `restore_position()`(→ `PositionRestored`) — 대조·판단은
  `ops.restore`. 복원 뒤 첫 틱이 내려가 있던 동안의 펀딩 경계를 넘었으면 `FundingMissed` + 진입 차단(율 추정 없음).
- **트레일링(단계 2c · 트라이얼 #1 사전등록 §1)**: `EntryIntent.trail`이 있을 때만 켜진다 — **기본 None = 꺼짐**.
  None이면 `_trail`이 곧바로 돌아가고 스냅샷에 `trail` 키도 없다 → **돌고 있는 페이퍼 봇(전략 없음 · trail 없음) 경로는 그대로다**.
  켜지면: R = 체결 진입가와 초기 SL의 거리 · 유리한 극값(틱 = mark, 봉 = 롱 고가/숏 저가)이 진입가 ± arm_r×R에 닿으면 무장 →
  SL = 극값 ∓ dist로 **조이기만** 한다. 판정(`_evaluate`) **뒤에** 갱신하므로 새 SL은 다음 봉/틱부터 쓴다(봉 안 순서 불명 · 보수적).
  옮겨진 SL에서 나가면 `ExitReason.TRAIL`(체결 기준은 SL과 같다).
- **체결 뒤 TP(`EntryIntent.tp_rule` · 기본 None)**: R = |체결 진입가 − SL|로 레벨 TP와 폴백 TP(fallback_r × R)를 정한다 —
  트레일링과 같은 R(레지스트리 #21). None이면 기존대로 `intent.tp`를 그대로 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from exchange.errors import BinanceAPIError, LeverageNotConfirmed, OrderParamError, RulesError, TransportError
from exchange.gate import Mode
from exchange.normalize import RejectReason
from exchange.orders import Direction, Intent, close_position_orders, market_order_params, side_for
from exchange.rules import RuntimeRules
from paper.sender import OrderOutcomeUnknown, OrderSender
from paper.types import (
    EntriesBlocked,
    EntryFilled,
    EntrySkipped,
    ExitFailed,
    ExitReason,
    Fill,
    FundingMissed,
    FundingSettled,
    LiquidationThresholdCrossed,
    MarkBar,
    MarkTick,
    PositionClosed,
    PositionReduced,
    PositionRestored,
    PositionRisk,
    PositionSynced,
    PositionVanished,
    PostFillCheck,
    SkipReason,
    StopTrailed,
    WalletResynced,
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
class Trail:
    """트레일링 설정(전략 config에서 온다) — `arm_r` R 이익 뒤 SL = 극값 ∓ `dist`(가격 거리 · 결정 시점에 고정)."""
    arm_r: Decimal
    dist: Decimal


@dataclass(frozen=True)
class TpFromFill:
    """TP를 **체결 뒤** 정한다 — R = |체결 진입가 − SL|(트레일링과 같은 R · 레지스트리 #21).
    `level`이 이익 방향으로 체결가에서 `min_r × R` 이상 떨어져 있으면 TP = level, 아니면(없거나 가깝거나 이미 지남)
    TP = 체결가 ± `fallback_r × R`."""
    level: Decimal | None
    min_r: Decimal
    fallback_r: Decimal


@dataclass(frozen=True)
class EntryIntent:
    """전략 출력 — 무엇을 원하는가. 크기·레버리지는 실행 시점에 엔진이 정한다."""
    direction: Direction
    sl: Decimal
    tp: Decimal | None
    regime: RegimeSizing
    decided_ms: int
    decision_mark: Decimal                 # 결정 시점 mark(기록·TP 방향 검사용 — 체결가 아님)
    trail: Trail | None = None             # 기본 꺼짐 — 트라이얼 전략 config가 켤 때만
    tp_rule: TpFromFill | None = None      # 기본 꺼짐 — 있으면 `tp`는 None이어야 하고 TP는 체결 뒤 정해진다


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
    decision: SizingDecision | None                 # 재기동 복원 포지션은 None(진입 뒤에는 읽지 않는다)
    funding_paid: Decimal
    liq_alerted: bool = False
    trail: Trail | None = None
    trail_r: Decimal | None = None                  # 초기 R(가격 거리) — 체결 진입가와 초기 SL
    trail_armed: bool = False
    trail_moved: bool = False                       # SL이 한 번이라도 옮겨졌다 → 그 SL 청산은 TRAIL

    @property
    def signed_qty(self) -> Decimal:
        return self.qty if self.direction is Direction.LONG else -self.qty


def _vwap(fills: list[Fill]) -> Decimal:
    q = sum((f.qty for f in fills), Decimal())
    return sum((f.qty * f.price for f in fills), Decimal()) / q


def _tp_from_fill(rule: TpFromFill, direction: Direction, entry: Decimal, sl: Decimal) -> Decimal:
    r = abs(entry - sl)
    long_ = direction is Direction.LONG
    if rule.level is not None:
        ahead = rule.level - entry if long_ else entry - rule.level
        if ahead >= rule.min_r * r:
            return rule.level
    return entry + rule.fallback_r * r if long_ else entry - rule.fallback_r * r


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
        self.entries_blocked: list[str] = []
        self._last_tick: MarkTick | None = None
        self._restored_next_funding_ms: int | None = None     # 복원 뒤 첫 틱에서 내려가 있던 동안의 펀딩 경계를 본다
        self.last_entry_tp: Decimal | None = None             # 마지막 체결의 TP(tp_rule이면 체결 뒤 값) — 재생 기록용 · 이벤트·스냅샷 아님

    # ── 입력 ────────────────────────────────────────────────────────────────
    def request_entry(self, intent: EntryIntent) -> None:
        if type(intent.direction) is not Direction:
            raise EntryRefused(f"direction은 Direction: {intent.direction!r}")
        if self.entries_blocked:
            raise EntryRefused(f"진입 차단 중: {' · '.join(self.entries_blocked)}")
        if self.position is not None or self.pending is not None:
            raise EntryRefused("포지션 또는 대기 진입이 이미 있다(원웨이 단일 포지션)")
        long_ = intent.direction is Direction.LONG
        if intent.trail is not None and not (intent.trail.arm_r > 0 and intent.trail.dist > 0):
            raise ValueError(f"trail 값은 양수여야 한다: {intent.trail}")
        if intent.tp_rule is not None:
            if intent.tp is not None:
                raise ValueError("tp와 tp_rule은 함께 줄 수 없다")
            if not (0 < intent.tp_rule.min_r and 0 < intent.tp_rule.fallback_r):
                raise ValueError(f"tp_rule 값은 양수여야 한다: {intent.tp_rule}")
        if intent.tp is not None and ((long_ and intent.tp <= intent.decision_mark)
                                      or (not long_ and intent.tp >= intent.decision_mark)):
            raise EntryRefused(f"TP {intent.tp}가 {intent.direction} 결정 mark {intent.decision_mark}의 잘못된 쪽")
        self.pending = intent

    def on_tick(self, t: MarkTick) -> list[object]:
        self._check_funding_grid(t)
        ev: list[object] = []
        prev = self._last_tick
        nf, self._restored_next_funding_ms = self._restored_next_funding_ms, None
        if nf is not None and prev is None and self.position is not None and t.ts_ms >= nf:
            #  재기동 복원: 내려가 있던 동안 지난 경계의 율은 모른다 — 피드 공백과 같은 규칙(추정 없이 알리고 진입 차단)
            missed = (nf, *self._missed_boundaries(nf, t.ts_ms))
            ev.append(FundingMissed(t.ts_ms, missed, self.position.signed_qty))
            ev.append(self._block(t.ts_ms, f"재기동 중 펀딩 경계 {len(missed)}개 정산 불가(율 불명)"))
        if prev is not None and self.position is not None and prev.ts_ms < prev.next_funding_ms <= t.ts_ms:
            ev.append(self._settle_funding(prev.next_funding_ms, prev.funding_rate, prev.mark))
            missed = self._missed_boundaries(prev.next_funding_ms, t.ts_ms)
            if missed:
                #  🔴 Codex L3 검토 3: 공백 동안의 경계는 율을 모른다 — 추정하지 않고 알리고 진입을 막는다
                ev.append(FundingMissed(t.ts_ms, missed, self.position.signed_qty))
                ev.append(self._block(t.ts_ms, f"피드 공백으로 펀딩 경계 {len(missed)}개 정산 불가(율 불명)"))
        self._last_tick = t
        if self.pending is not None and t.ts_ms > self.pending.decided_ms:
            ev += self._execute_entry(t.mark, t.ts_ms)
            if self.position is None:
                return ev
        if self.position is not None:
            ev += self._evaluate(t.ts_ms, low=t.mark, high=t.mark, sl_ref=t.mark, tp_ref=t.mark, mark=t.mark)
            ev += self._trail(t.ts_ms, t.mark, t.mark)
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
        ev += self._trail(b.close_ms, b.low, b.high)
        return ev

    def on_funding(self, *, ts_ms: int, rate: Decimal, mark: Decimal) -> list[object]:
        """봉 단위 재생용 — 실제 펀딩 이력(정산 시각·율·mark)을 넣는다."""
        return [self._settle_funding(ts_ms, rate, mark)] if self.position is not None else []

    def close_now(self, *, ref_mark: Decimal, ts_ms: int, reason: ExitReason = ExitReason.MANUAL) -> list[object]:
        return self._exit(reason, ref_mark, ts_ms) if self.position is not None else []

    def vanish(self, ts_ms: int, detail: str) -> list[object]:
        """LIVE 봉 대사가 거래소 flat · 내부 보유를 봤다 → **주문 없이** 내부 포지션을 닫는다(사용자 2026-09-16).
        손익은 모른다 — 지갑은 호출자가 거래소 지갑으로 `sync_wallet`한다."""
        pos = self.position
        if pos is None:
            return []
        self.position = None
        return [PositionVanished(ts_ms, pos.direction, pos.qty, pos.entry_price, detail),
                self._block(ts_ms, f"거래소 포지션 소실 — 내부 강제 close: {detail}")]

    def position_state(self) -> dict[str, Any] | None:
        """엔진 스냅샷(`account_snapshots.raw_json`)에 넣는 포지션 상태 — 재기동 복원의 대조 원천(문자열·정수만)."""
        pos = self.position
        if pos is None:
            return None
        st: dict[str, Any] = {
            "direction": pos.direction.value, "qty": str(pos.qty), "entry_price": str(pos.entry_price),
            "leverage": pos.leverage, "sl": str(pos.sl), "tp": None if pos.tp is None else str(pos.tp),
            "liq_price_est": str(pos.liq_price_est), "entry_commission": str(pos.entry_commission),
            "funding_paid": str(pos.funding_paid), "opened_ms": pos.opened_ms, "liq_alerted": pos.liq_alerted,
            "next_funding_ms": self._restored_next_funding_ms if self._last_tick is None else self._last_tick.next_funding_ms}
        if pos.trail is not None:                      # 트레일링 없는 포지션(현 봇)은 키 자체가 없다 — 스냅샷 형태 불변
            st["trail"] = {"arm_r": str(pos.trail.arm_r), "dist": str(pos.trail.dist), "r": str(pos.trail_r),
                           "armed": pos.trail_armed, "moved": pos.trail_moved}
        return st

    def restore_position(self, state: dict[str, Any], *, ts_ms: int, detail: str) -> list[object]:
        """PAPER 재기동 복원 — 호출자(`ops.restore`)가 DB와 스냅샷이 일치함을 확인한 뒤에만 부른다."""
        if self.position is not None or self.pending is not None:
            raise EntryRefused("복원 거부: 엔진에 이미 포지션 또는 대기 진입이 있다")
        nf = state["next_funding_ms"]
        if not isinstance(nf, int):
            raise ValueError("복원 거부: next_funding_ms 없음(펀딩 경계를 판정할 수 없다)")
        pos = OpenPosition(Direction(state["direction"]), Decimal(state["qty"]), Decimal(state["entry_price"]),
                           int(state["leverage"]), Decimal(state["sl"]),
                           None if state["tp"] is None else Decimal(state["tp"]), Decimal(state["liq_price_est"]),
                           Decimal(state["entry_commission"]), int(state["opened_ms"]), None,
                           Decimal(state["funding_paid"]), bool(state["liq_alerted"]))
        tr = state.get("trail")
        if tr is not None:
            pos.trail, pos.trail_r = Trail(Decimal(tr["arm_r"]), Decimal(tr["dist"])), Decimal(tr["r"])
            pos.trail_armed, pos.trail_moved = bool(tr["armed"]), bool(tr["moved"])
        #  Codex L8b #2: 스냅샷의 추정 청산가는 쓰지 않는다 — 현재 규칙으로 다시 계산(`_refresh_liquidation`과 같은 식).
        #  계산할 수 없으면 복원하지 않는다(RulesError를 호출자에게).
        n = pos.qty * pos.entry_price
        pos.liq_price_est = liquidation_estimate(pos.direction, pos.entry_price, n, pos.leverage, self.rules,
                                                 taker=self.rules.commission.taker + pos.funding_paid / n).price
        self.position = pos
        self._last_tick = None
        self._restored_next_funding_ms = nf
        return [PositionRestored(ts_ms, pos.direction, pos.qty, pos.entry_price, detail,
                                 dict(state) | {"liq_price_est_recomputed": str(pos.liq_price_est)})]

    def sync_wallet(self, ts_ms: int, wallet: Decimal, *, source: str, detail: str) -> WalletResynced:
        if not isinstance(wallet, Decimal):
            raise TypeError("wallet은 Decimal")
        previous, self.wallet = self.wallet, wallet
        return WalletResynced(ts_ms, previous, wallet, source, detail)

    def clear_blocks(self) -> list[str]:
        """사람의 /start — 엔진 진입 차단 사유 전부 해제(돌려준 목록을 알린다)."""
        cleared, self.entries_blocked = self.entries_blocked, []
        return cleared

    def cancel_pending(self, ts_ms: int, reason: str) -> list[EntrySkipped]:
        """결정 뒤 체결 전에 진입 게이트가 닫혔다 → 대기 진입을 버리고 기록한다."""
        if self.pending is None:
            return []
        self.pending = None
        return [EntrySkipped(ts_ms, None, SkipReason.ENTRIES_BLOCKED, reason)]

    def unrealized_pnl(self, mark: Decimal) -> Decimal:
        pos = self.position
        if pos is None:
            return Decimal()
        return (mark - pos.entry_price) * pos.qty if pos.direction is Direction.LONG else (pos.entry_price - mark) * pos.qty

    def equity(self, mark: Decimal) -> Decimal:
        """지갑 + mark 기준 미실현 손익 — 킬스위치 일일 손실의 equity(두 모드 같은 정의)."""
        return self.wallet + self.unrealized_pnl(mark)

    # ── 내부 ────────────────────────────────────────────────────────────────
    def _check_funding_grid(self, t: MarkTick) -> None:
        interval = self.rules.funding.interval_hours
        if interval and t.next_funding_ms % (interval * HOUR_MS) != 0:
            raise FeedError(f"nextFundingTime {t.next_funding_ms}이 {interval}h 격자 밖 — 런타임 fundingInfo와 모순")

    def _missed_boundaries(self, settled_ms: int, now_ms: int) -> tuple[int, ...]:
        """정산한 경계 뒤 `now_ms`까지 건너뛴 경계. 간격을 모르면(fundingInfo에 심볼 없음) 셀 수 없어 빈 튜플."""
        interval = self.rules.funding.interval_hours
        if not interval:
            return ()
        step = interval * HOUR_MS
        return tuple(range(settled_ms + step, now_ms + 1, step))

    def _settle_funding(self, ts_ms: int, rate: Decimal, mark: Decimal) -> FundingSettled:
        pos = self.position
        assert pos is not None
        paid = pos.signed_qty * mark * rate
        self.wallet -= paid
        pos.funding_paid += paid
        self._refresh_liquidation(pos)
        return FundingSettled(ts_ms, rate, mark, pos.signed_qty, paid, self.wallet)

    def _refresh_liquidation(self, pos: OpenPosition) -> None:
        """격리 포지션의 펀딩은 격리 지갑에서 나간다(Codex L3 검토 Q3) → WB = N/L − N×taker − 누적 펀딩.
        #4 닫힌꼴에서 WB의 −N×taker 항과 같은 자리이므로 `taker + 펀딩/N`을 넘기면 정확히 같은 식이다."""
        n = pos.qty * pos.entry_price
        try:
            pos.liq_price_est = liquidation_estimate(pos.direction, pos.entry_price, n, pos.leverage, self.rules,
                                                     taker=self.rules.commission.taker + pos.funding_paid / n).price
        except RulesError:
            pass

    def _block(self, ts_ms: int, reason: str) -> EntriesBlocked:
        if reason not in self.entries_blocked:
            self.entries_blocked.append(reason)
        return EntriesBlocked(ts_ms, reason)

    def _read_position(self, ts_ms: int) -> tuple[PositionRisk | None, list[object]]:
        try:
            return self.sender.position_risk(), []
        except (OrderOutcomeUnknown, BinanceAPIError, TransportError, KeyError, TypeError, ArithmeticError,
                AttributeError) as e:
            return None, [self._block(ts_ms, f"positionRisk 조회 실패 {type(e).__name__}: {e} — 대사 필요")]

    def _execute_entry(self, ref_mark: Decimal, ts_ms: int) -> list[object]:
        pe = self.pending
        assert pe is not None
        self.pending = None
        #  SL 트리거 기준은 mark(#5) — 예상 체결가가 아니라 **mark가 이미 SL을 넘었는지**로 건너뛴다
        #  (2 bps 슬리피지에서 BUY 예상가가 SL 위로 올라가 "SL 이미 발동된 진입"을 허용하던 결함 · 레지스트리 #7 전환 중 발견)
        long_ = pe.direction is Direction.LONG
        if (long_ and ref_mark <= pe.sl) or (not long_ and ref_mark >= pe.sl):
            return [EntrySkipped(ts_ms, None, SkipReason.SL_CROSSED_BEFORE_FILL, f"실행 mark {ref_mark} · SL {pe.sl}")]
        quote = self.sender.quote_fill_price(side_for(pe.direction, Intent.ENTRY), ref_mark)
        d = size_entry(quote, pe.sl, pe.direction, self.wallet, pe.regime, self.rules, self.limits)
        if not d.ok or d.leverage is None:
            why = SkipReason.SL_CROSSED_BEFORE_FILL if d.reason is RejectReason.SL_WRONG_SIDE else SkipReason.SIZING_REJECTED
            return [EntrySkipped(ts_ms, d, why, f"실행 mark {ref_mark} · 예상 체결가 {quote} · {d.reason} · {d.detail}")]
        try:
            echo = self.sender.set_leverage(d.leverage)
        except (LeverageNotConfirmed, BinanceAPIError, TransportError) as e:
            return [EntrySkipped(ts_ms, d, SkipReason.LEVERAGE_NOT_CONFIRMED, f"{type(e).__name__}: {e}")]
        if echo != d.leverage:
            return [EntrySkipped(ts_ms, d, SkipReason.LEVERAGE_NOT_CONFIRMED, f"응답 {echo}x ≠ 결정 {d.leverage}x")]

        sr = self.rules.symbol_rules
        fills: list[Fill] = []
        ev: list[object] = []
        failure: Exception | None = None
        try:
            for q in d.chunks:
                p = market_order_params(sr.symbol, d.direction, Intent.ENTRY, q, sr)
                fills.append(self.sender.send_market(p, ref_mark=ref_mark, ts_ms=ts_ms))
        except SEND_ERRORS as e:
            failure = e
            ev.append(self._block(ts_ms, f"진입 주문 실패/불명 {type(e).__name__}: {e} · 체결 확인 {len(fills)}/{len(d.chunks)}조각"))

        qty = sum((f.qty for f in fills), Decimal())
        commission = sum((f.commission for f in fills), Decimal())
        entry = _vwap(fills) if fills else ref_mark
        adopted: PositionRisk | None = None
        if failure is not None and self.mode is Mode.LIVE:
            #  응답을 못 받은 조각이 실제로는 체결됐을 수 있다 → 거래소 수량을 채택해 SL 감시를 한다(방치 금지)
            pr, blocked = self._read_position(ts_ms)
            ev += blocked
            sign = 1 if d.direction is Direction.LONG else -1
            #  🔴 Codex L3 재검토 2: 확인된 체결보다 **클 때만** 채택(줄이지 않는다) · 전 수량을 거래소 평균가로.
            #  소유권은 구분할 수 없다 — LIVE 전제(USDⓈ-M 전용 계정·기동 시 flat)가 같은 방향 잔량을 이 봇 것으로 만든다.
            if pr is not None and pr.amt * sign > 0 and abs(pr.amt) > qty and pr.entry_price > 0:
                extra = abs(pr.amt) - qty
                commission += extra * pr.entry_price * self.rules.commission.taker
                qty, entry = abs(pr.amt), pr.entry_price
                adopted = pr
            elif pr is not None and abs(pr.amt) != qty:
                ev.append(self._block(ts_ms, f"진입 불명 후 거래소 수량 {pr.amt} ≠ 확인 체결 {qty} — 채택 안 함, 대사 필요"))
        if qty == 0:
            if failure is not None and not isinstance(failure, OrderOutcomeUnknown):
                ev.append(EntrySkipped(ts_ms, d, SkipReason.SEND_FAILED, f"{type(failure).__name__}: {failure}"))
            return ev

        self.wallet -= commission
        post = self._post_fill(d, entry, qty)
        tp = pe.tp if pe.tp_rule is None else _tp_from_fill(pe.tp_rule, d.direction, entry, d.sl)
        self.last_entry_tp = tp
        self.position = OpenPosition(d.direction, qty, entry, d.leverage, d.sl, tp, post.liq_price_est, commission,
                                     ts_ms, d, Decimal())
        if pe.trail is not None:
            self.position.trail, self.position.trail_r = pe.trail, abs(entry - d.sl)
        live_ev: list[object] = []
        if self.mode is Mode.LIVE:
            post, live_ev = self._live_after_entry(ts_ms, d, post)
        ev.insert(0, EntryFilled(ts_ms, d, tuple(fills), d.leverage, post, adopted=adopted, entry_commission=commission))
        ev += live_ev
        if not post.gate_ok:
            #  #5는 사전확약 게이트 — 실제 체결 기준으로 깨지면 즉시 청산(Codex L3 검토 4 · 기록만 하는 완화 없음)
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
        return PostFillCheck(entry_price=entry, qty=qty, notional=notional, sl_dist_pct=sl_dist, liq_price_est=liq_price,
                             liq_dist_pct=liq_dist, bracket=bracket, gate_ok=gate_ok, loss_at_sl_usdt=loss,
                             loss_over_budget=loss > d.risk_budget_usdt * (1 + self.limits.loss_tolerance),
                             sl_before_liquidation=sl_first, liquidation_check=None)

    def _live_after_entry(self, ts_ms: int, d: SizingDecision, post: PostFillCheck) -> tuple[PostFillCheck, list[object]]:
        """LIVE 전용 — positionRisk 1회: 청산가 검사(#4 판정 로그) + 수량 대사. 🔴 Codex L3 검토 1: 조회 실패는 예외가
        아니라 진입 차단(포지션은 이미 내부에 기록돼 청산 감시가 계속된다)."""
        pos = self.position
        assert pos is not None
        pr, ev = self._read_position(ts_ms)
        if pr is None:
            return post, ev
        try:
            lc = post_entry_liquidation_check(d, self.rules, entry_price=post.entry_price, qty=post.qty,
                                              exchange_liq_price=pr.liquidation_price)
            post = replace(post, liquidation_check=lc)
        except (RulesError, ValueError, ArithmeticError) as e:
            ev.append(self._block(ts_ms, f"진입 후 청산가 검사 실패 {type(e).__name__}: {e}"))
        if pr.amt != pos.signed_qty:
            ev.append(self._block(ts_ms, f"대사 불일치: 내부 {pos.signed_qty} · 거래소 {pr.amt}"))
        return post, ev

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
            return ev + self._exit(ExitReason.TRAIL if pos.trail_moved else ExitReason.SL, sl_ref, ts_ms)
        tp = pos.tp
        if tp is not None and (high >= tp if long_ else low <= tp):
            return ev + self._exit(ExitReason.TP, tp if tp_ref is None else tp_ref, ts_ms)
        return ev

    def _trail(self, ts_ms: int, low: Decimal, high: Decimal) -> list[object]:
        """판정 뒤에 부른다 — 여기서 조인 SL은 다음 봉/틱부터 쓴다. trail이 없으면(기본) 아무것도 하지 않는다."""
        pos = self.position
        if pos is None or pos.trail is None or pos.trail_r is None:
            return []
        long_ = pos.direction is Direction.LONG
        best = high if long_ else low
        if not pos.trail_armed:
            gain = best - pos.entry_price if long_ else pos.entry_price - best
            if gain < pos.trail.arm_r * pos.trail_r:
                return []
            pos.trail_armed = True
        cand = best - pos.trail.dist if long_ else best + pos.trail.dist
        if (long_ and cand <= pos.sl) or (not long_ and cand >= pos.sl):
            return []
        old, pos.sl, pos.trail_moved = pos.sl, cand, True
        return [StopTrailed(ts_ms, old, cand)]

    def _liquidate(self, ts_ms: int) -> list[object]:
        """PAPER — 남은 격리 지갑(N/L − 진입 수수료 − 누적 펀딩) 전부 + N × liquidationFee."""
        pos = self.position
        assert pos is not None
        n = pos.qty * pos.entry_price
        loss = (n / Decimal(pos.leverage) - pos.entry_commission - pos.funding_paid
                + n * self.rules.symbol_rules.liquidation_fee)
        self.wallet -= loss
        self.position = None
        return [PositionClosed(ts_ms, pos.direction, ExitReason.LIQUIDATION, pos.qty, pos.entry_price, None, (), -loss,
                               Decimal(), pos.funding_paid, self.wallet)]

    def _exit(self, reason: ExitReason, ref_mark: Decimal, ts_ms: int) -> list[object]:
        pos = self.position
        assert pos is not None
        sr = self.rules.symbol_rules
        ev: list[object] = []
        signed = pos.signed_qty
        if self.mode is Mode.LIVE:
            #  거래소가 실제로 들고 있는 수량을 닫는다(부분 불명 조각 포함) — 반대 부호면 닫지 않고 멈춘다
            pr, blocked = self._read_position(ts_ms)
            ev += blocked
            if pr is not None:
                if pr.amt == 0:
                    self.position = None
                    ev.append(PositionVanished(ts_ms, pos.direction, pos.qty, pos.entry_price,
                                               f"청산({reason}) 시도 시 거래소 포지션 0 — 거래소 청산·수동 청산 의심"))
                    ev.append(ExitFailed(ts_ms, reason, "거래소 포지션 0 — 거래소 청산·수동 청산 추정 · 대사 필요"))
                    ev.append(self._block(ts_ms, "청산하려 했으나 거래소 포지션이 이미 0"))
                    return ev
                if pr.amt * signed < 0:
                    ev.append(ExitFailed(ts_ms, reason, f"거래소 수량 {pr.amt}이 내부 방향 {pos.direction}과 반대 — 청산 보류"))
                    ev.append(self._block(ts_ms, "대사 불일치(반대 부호)"))
                    return ev
                if pr.amt != signed:
                    #  🔴 Codex L3 재검토 3: 거래소 기준으로 동기화한 뒤 닫는다(손익 기준 = 거래소 평균 진입가)
                    ev.append(self._block(ts_ms, f"청산 전 대사 불일치: 내부 {signed} → 거래소 {pr.amt}(평균가 {pr.entry_price})로 동기화"))
                    previous_qty, extra_fee = pos.qty, Decimal()
                    if abs(pr.amt) > pos.qty:
                        #  처음 드러난 추가 수량의 진입 수수료 — 거래소 평균가 × 런타임 taker로 추정해 지갑에 반영(Codex 재검토 #2)
                        extra_fee = (abs(pr.amt) - pos.qty) * (pr.entry_price if pr.entry_price > 0 else ref_mark) \
                            * self.rules.commission.taker
                        self.wallet -= extra_fee
                        pos.entry_commission += extra_fee
                    else:
                        #  🔴 Codex L6·7 재검토 #1: 거래소 수량이 **줄었다** — 사라진 부분은 수정 행으로 덮지 않고 소실로 기록
                        #  (부분 청산·ADL·수동 감소 의심 · 손익 모름 → 추정하지 않음 · 킬스위치가 청산 1회로 본다)
                        ev.append(PositionVanished(ts_ms, pos.direction, pos.qty - abs(pr.amt), pos.entry_price,
                                                   f"청산({reason}) 직전 거래소 수량 {pos.qty} → {abs(pr.amt)} 감소 — 부분 청산·ADL·수동 감소 의심"))
                    pos.qty = abs(pr.amt)
                    if pr.entry_price > 0:
                        pos.entry_price = pr.entry_price
                    signed = pr.amt
                    if pos.qty > previous_qty:
                        ev.append(PositionSynced(ts_ms, pos.direction, previous_qty, pos.qty, pos.entry_price, extra_fee, pr))
        fills: list[Fill] = []
        failure: Exception | None = None
        try:
            for p in close_position_orders(signed, sr):
                fills.append(self.sender.send_market(p, ref_mark=ref_mark, ts_ms=ts_ms))
        except SEND_ERRORS as e:
            failure = e
        if fills:
            q = sum((f.qty for f in fills), Decimal())
            px = _vwap(fills)
            pnl = (px - pos.entry_price) * q if pos.direction is Direction.LONG else (pos.entry_price - px) * q
            comm = sum((f.commission for f in fills), Decimal())
            self.wallet += pnl - comm
            if q >= pos.qty:
                self.position = None
                ev.append(PositionClosed(ts_ms, pos.direction, reason, q, pos.entry_price, px, tuple(fills), pnl, comm,
                                         pos.funding_paid, self.wallet))
            else:
                pos.qty -= q
                #  사용자 2026-09-16: 부분 청산도 행을 쓴다 — DB 남은 수량이 엔진 잔량과 같아져 대사가 스스로 맞는다
                ev.append(PositionReduced(ts_ms, pos.direction, reason, q, pos.qty, pos.entry_price, px, tuple(fills), pnl,
                                          comm, self.wallet, f"일부 청산 {q} · 잔량 {pos.qty}"))
                ev.append(ExitFailed(ts_ms, reason, f"일부 청산 {q} · 잔량 {pos.qty}"))
        if failure is not None:
            ev.append(ExitFailed(ts_ms, reason, f"{type(failure).__name__}: {failure}"))
            ev.append(self._block(ts_ms, f"청산 주문 실패/불명 — 대사 필요: {failure}"))
        if self.mode is Mode.LIVE and self.position is None:
            pr, blocked = self._read_position(ts_ms)
            ev += blocked
            if pr is not None and pr.amt != 0:
                ev.append(self._block(ts_ms, f"청산 후 거래소 잔량 {pr.amt} — 대사 필요"))
        return ev
