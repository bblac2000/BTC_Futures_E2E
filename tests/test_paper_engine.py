"""layer 3 엔진 — 페이퍼·라이브 공통 경로(송신기만 다르다).

- 전략은 **진입 의도**(방향·SL·TP·레짐)를 낸다. 엔진은 결정 **이후** 첫 mark 틱(또는 다음 봉 시가)에서
  그 mark·현재 지갑으로 `size_entry`를 다시 돌려 사이징하고 체결한다(미래 참조 없음 · 최고 L 경계에서 헛진입 없음)
- 한 틱/봉 안 우선순위: **청산 > SL > TP** (같은 봉 SL·TP 동시 → SL)
- 청산은 #4 모델(수수료 차감) 추정가로 **PAPER만** 시뮬레이션 · LIVE는 알림만(청산은 거래소가 한다 · #6)
- 펀딩: 틱의 nextFundingTime 경계에서 정산(8h 간격이면 00/08/16 UTC) · 실제 펀딩율 · LONG은 양수일 때 지불
- 체결 후 재검증(Codex L2 Q7): 실제 체결가·수량으로 #5 게이트·SL 손실 재계산 → 기록.
  **SL이 추정 청산가보다 앞에 있지 않으면**(물리적 불변식) 즉시 청산
- LIVE만 진입 후 `post_entry_liquidation_check`(positionRisk.liquidationPrice)
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from exchange.errors import LeverageNotConfirmed
from exchange.gate import Mode
from exchange.normalize import RejectReason
from exchange.orders import Direction, Side
from paper.engine import Engine, EntryIntent, EntryRefused, FeedError
from paper.sender import OrderOutcomeUnknown, PaperSender
from paper.types import (
    EntriesBlocked,
    EntryFilled,
    EntrySkipped,
    ExitReason,
    Fill,
    FundingSettled,
    LiquidationThresholdCrossed,
    MarkBar,
    MarkTick,
    PositionClosed,
    PositionRisk,
    SkipReason,
)
from sizing.config import RegimeSizing, SizingLimits
from sizing.position import size_entry

D = Decimal
LONG, SHORT = Direction.LONG, Direction.SHORT
H = 3_600_000
DAY0 = 1_789_430_400_000                  # 2026-09-15 00:00:00 UTC
RATE = D("0.0001")
W0 = D("1000")


def next_funding(ts: int) -> int:
    return (ts // (8 * H) + 1) * 8 * H


def tick(ts: int, mark: str | Decimal, rate: Decimal = RATE) -> MarkTick:
    return MarkTick(ts_ms=ts, mark=D(mark), funding_rate=rate, next_funding_ms=next_funding(ts))


def intent(direction=LONG, *, sl=None, tp=None, risk="0.01", decided_ms=DAY0, mark="60000") -> EntryIntent:
    m = D(mark)
    sl = D(sl) if sl is not None else (m * D("0.995") if direction is LONG else m * D("1.005"))
    return EntryIntent(direction=direction, sl=sl, tp=None if tp is None else D(tp),
                       regime=RegimeSizing("t", D(risk), 50, 100), decided_ms=decided_ms, decision_mark=m)


def engine(rules, sender=None, mode=Mode.PAPER) -> Engine:
    return Engine(rules, sender or PaperSender(rules), mode=mode, wallet=W0, limits=SizingLimits())


def of(events, kind):
    return [e for e in events if isinstance(e, kind)]


# ── 진입 ─────────────────────────────────────────────────────────────────────
def test_entry_is_sized_and_filled_on_the_first_tick_after_the_decision(rules):
    e = engine(rules)
    e.request_entry(intent(decided_ms=DAY0 + 60_000))
    assert e.on_tick(tick(DAY0 + 60_000, "60000")) == [], "결정 시각과 같은 틱은 체결하지 않는다"
    ev = e.on_tick(tick(DAY0 + 61_000, "60010"))
    (fill,) = of(ev, EntryFilled)
    d = fill.decision
    #  사이징은 체결 틱의 mark·그때의 지갑으로 다시 한다
    expect = size_entry(D("60010"), intent().sl, LONG, W0, intent().regime, rules, SizingLimits())
    assert d == expect and d.entry == D("60010")
    assert fill.fills[0].ref_mark == D("60010") and fill.fills[0].price > D("60010")
    assert fill.leverage == d.leverage and e.position is not None and e.position.qty == d.qty
    assert e.wallet == W0 - sum(f.commission for f in fill.fills)
    assert fill.post_fill.sl_before_liquidation


def test_sizing_at_execution_lowers_leverage_when_price_moved_away_from_sl(rules):
    """결정 시점 최고 L은 게이트 경계에 붙어 있다 → 실행 mark로 다시 사이징하면 필요한 만큼 L이 낮아진다."""
    at_decision = size_entry(D("60000"), intent().sl, LONG, W0, intent().regime, rules, SizingLimits())
    e = engine(rules)
    e.request_entry(intent())
    (fill,) = of(e.on_tick(tick(DAY0 + 1000, "60150")), EntryFilled)
    assert at_decision.leverage is not None and fill.leverage < at_decision.leverage
    assert e.position is not None


def test_request_entry_refuses_open_position_pending_and_wrong_side_tp(rules):
    e = engine(rules)
    with pytest.raises(EntryRefused):
        e.request_entry(intent(tp="59000"))                      # LONG TP가 아래
    e.request_entry(intent())
    with pytest.raises(EntryRefused):
        e.request_entry(intent())
    e.on_tick(tick(DAY0 + 1000, "60000"))
    with pytest.raises(EntryRefused):
        e.request_entry(intent(decided_ms=DAY0 + 1000))


def test_engine_mode_must_match_sender_mode(rules):
    with pytest.raises(ValueError):
        Engine(rules, PaperSender(rules), mode=Mode.LIVE, wallet=W0, limits=SizingLimits())


def test_entry_is_split_by_market_lot_max_qty(rules):
    sr = replace(rules.symbol_rules, market_max_qty=D("0.010"))
    r2 = replace(rules, symbol_rules=sr)
    e = engine(r2)
    e.request_entry(intent(sl="59820", risk="0.02"))           # 작은 SL → 큰 명목 → 여러 조각
    (fill,) = of(e.on_tick(tick(DAY0 + 1000, "60000")), EntryFilled)
    d = fill.decision
    assert len(d.chunks) > 1 and len(fill.fills) == len(d.chunks) and sum(f.qty for f in fill.fills) == d.qty
    assert all(f.qty <= D("0.010") for f in fill.fills)
    (closed,) = of(e.close_now(ref_mark=D("60000"), ts_ms=DAY0 + 2000), PositionClosed)
    assert len(closed.fills) == len(d.chunks) and sum(f.qty for f in closed.fills) == d.qty


def test_sl_already_crossed_at_execution_skips_entry(rules):
    e = engine(rules)
    i = intent()
    e.request_entry(i)
    (skip,) = of(e.on_tick(tick(DAY0 + 1000, i.sl - 1)), EntrySkipped)
    assert skip.reason is SkipReason.SL_CROSSED_BEFORE_FILL and e.position is None and e.pending is None


def test_sizing_rejection_at_execution_is_recorded_with_the_reason(rules):
    e = engine(rules)
    e.request_entry(intent(sl="58800"))                         # SL 2% — 50x 청산 거리 ~1.5% → #5 불가
    (skip,) = of(e.on_tick(tick(DAY0 + 1000, "60000")), EntrySkipped)
    assert skip.reason is SkipReason.SIZING_REJECTED and skip.decision is not None
    assert skip.decision.reason is RejectReason.LIQ_DISTANCE and e.position is None


@dataclass
class SpySender:
    """PaperSender를 감싸 호출을 기록하고 실패를 주입한다. `mode`를 바꾸면 LIVE 흉내."""
    inner: PaperSender
    mode: Mode = Mode.PAPER
    echo: int | None = None
    raise_on_leverage: bool = False
    unknown_on_send: int | None = None          # n번째 send에서 OrderOutcomeUnknown
    exchange_liq: Decimal | None = None
    exchange_amt: Decimal | None = None
    calls: list = field(default_factory=list)

    def set_leverage(self, leverage: int) -> int:
        self.calls.append(("leverage", leverage))
        if self.raise_on_leverage:
            raise LeverageNotConfirmed("echo mismatch")
        return self.echo if self.echo is not None else self.inner.set_leverage(leverage)

    def send_market(self, params, *, ref_mark, ts_ms) -> Fill:
        self.calls.append(("send", dict(params)))
        n = sum(1 for c in self.calls if c[0] == "send")
        if self.unknown_on_send == n:
            raise OrderOutcomeUnknown("timeout")
        return self.inner.send_market(params, ref_mark=ref_mark, ts_ms=ts_ms)

    def position_risk(self) -> PositionRisk | None:
        self.calls.append(("position_risk",))
        if self.mode is Mode.PAPER:
            raise AssertionError("PAPER에서 positionRisk를 읽으면 안 된다(#6)")
        return PositionRisk(self.exchange_amt if self.exchange_amt is not None else D("0"),
                            D("0"), self.exchange_liq or D("0"))


@pytest.mark.parametrize("kw", [{"echo": 20}, {"raise_on_leverage": True}])
def test_leverage_not_confirmed_skips_entry_without_orders(rules, kw):
    s = SpySender(PaperSender(rules), **kw)
    e = engine(rules, s)
    e.request_entry(intent())
    (skip,) = of(e.on_tick(tick(DAY0 + 1000, "60000")), EntrySkipped)
    assert skip.reason is SkipReason.LEVERAGE_NOT_CONFIRMED
    assert [c for c in s.calls if c[0] == "send"] == [] and e.position is None


def test_leverage_is_set_before_the_first_order(rules):
    s = SpySender(PaperSender(rules))
    e = engine(rules, s)
    e.request_entry(intent())
    (fill,) = of(e.on_tick(tick(DAY0 + 1000, "60000")), EntryFilled)
    assert s.calls[0] == ("leverage", fill.decision.leverage) and s.calls[1][0] == "send"


def test_order_outcome_unknown_blocks_entries(rules):
    s = SpySender(PaperSender(rules), unknown_on_send=1)
    e = engine(rules, s)
    e.request_entry(intent())
    ev = e.on_tick(tick(DAY0 + 1000, "60000"))
    assert of(ev, EntriesBlocked) and e.entries_blocked
    with pytest.raises(EntryRefused):
        e.request_entry(intent(decided_ms=DAY0 + 1000))


# ── 체결 후 재검증 ─────────────────────────────────────────────────────────────
def test_post_fill_recomputes_from_actual_fill_and_paper_has_no_exchange_check(rules):
    s = SpySender(PaperSender(rules))
    e = engine(rules, s)
    e.request_entry(intent())
    (fill,) = of(e.on_tick(tick(DAY0 + 1000, "60030")), EntryFilled)
    d, pf = fill.decision, fill.post_fill
    fp = fill.fills[0].price
    assert pf.entry_price == fp and pf.qty == d.qty and pf.notional == d.qty * fp
    assert pf.sl_dist_pct == (fp - d.sl) / fp
    assert pf.loss_at_sl_usdt == d.qty * (fp - d.sl)
    assert pf.liquidation_check is None and ("position_risk",) not in s.calls
    assert e.position is not None and e.position.liq_price_est == pf.liq_price_est


def test_buffer_violation_from_slippage_is_flagged_not_closed(rules):
    """#5 버퍼(×1.5·10bp)만 깨졌고 SL은 여전히 청산가 앞 → 기록만(청산 주문으로 수수료를 더 쓰지 않는다)."""
    e = engine(rules, PaperSender(rules, slippage_rate=D("0.001")))
    e.request_entry(intent())
    ev = e.on_tick(tick(DAY0 + 1000, "60000"))
    (fill,) = of(ev, EntryFilled)
    assert fill.post_fill.gate_ok is False and fill.post_fill.sl_before_liquidation is True
    assert fill.post_fill.loss_over_budget is True
    assert of(ev, PositionClosed) == [] and e.position is not None


def test_sl_not_before_liquidation_after_fill_closes_immediately(rules):
    e = engine(rules, PaperSender(rules, slippage_rate=D("0.004")))
    e.request_entry(intent())
    ev = e.on_tick(tick(DAY0 + 1000, "60000"))
    (fill,) = of(ev, EntryFilled)
    assert fill.post_fill.sl_before_liquidation is False
    (closed,) = of(ev, PositionClosed)
    assert closed.reason is ExitReason.POST_FILL_GATE and e.position is None


def test_live_mode_runs_post_entry_liquidation_check(rules):
    s = SpySender(PaperSender(rules), mode=Mode.LIVE)
    e = Engine(rules, s, mode=Mode.LIVE, wallet=W0, limits=SizingLimits())
    e.request_entry(intent())
    probe = size_entry(D("60000"), intent().sl, LONG, W0, intent().regime, rules, SizingLimits())
    s.exchange_amt = probe.qty
    (fill,) = of(e.on_tick(tick(DAY0 + 1000, "60000")), EntryFilled)
    lc = fill.post_fill.liquidation_check
    assert ("position_risk",) in s.calls and lc is not None and lc.status == "CHECK"   # 거래소 값 0 → 해석 불가 = CHECK


def test_live_position_amount_mismatch_blocks_entries(rules):
    s = SpySender(PaperSender(rules), mode=Mode.LIVE, exchange_liq=D("59000"), exchange_amt=D("0.001"))
    e = Engine(rules, s, mode=Mode.LIVE, wallet=W0, limits=SizingLimits())
    e.request_entry(intent())
    ev = e.on_tick(tick(DAY0 + 1000, "60000"))
    assert of(ev, EntriesBlocked) and e.entries_blocked


# ── 청산 우선순위 ─────────────────────────────────────────────────────────────
def opened(rules, direction=LONG, tp=None, mode=Mode.PAPER, sender=None):
    e = Engine(rules, sender or PaperSender(rules), mode=mode, wallet=W0, limits=SizingLimits())
    e.request_entry(intent(direction, tp=tp))
    ev = e.on_tick(tick(DAY0 + 1000, "60000"))
    (fill,) = of(ev, EntryFilled)
    assert e.position is not None
    return e, fill.decision


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_sl_on_mark_tick_fill_is_never_better_than_sl(rules, direction):
    e, d = opened(rules, direction)
    beyond = d.sl - 5 if direction is LONG else d.sl + 5
    (c,) = of(e.on_tick(tick(DAY0 + 2000, beyond)), PositionClosed)
    assert c.reason is ExitReason.SL and c.exit_price is not None
    assert (c.exit_price <= d.sl) if direction is LONG else (c.exit_price >= d.sl)


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_tp_on_mark_tick(rules, direction):
    tp = "60600" if direction is LONG else "59400"
    e, _ = opened(rules, direction, tp=tp)
    (c,) = of(e.on_tick(tick(DAY0 + 2000, tp)), PositionClosed)
    assert c.reason is ExitReason.TP and c.realized_pnl_usdt > 0


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_same_bar_sl_and_tp_takes_sl(rules, direction):
    tp = D("60600") if direction is LONG else D("59400")
    e, d = opened(rules, direction, tp=tp)
    bar = MarkBar(DAY0 + 60_000, DAY0 + 119_999, d.entry, max(tp, d.sl) + 1, min(tp, d.sl) - 1, d.entry)
    (c,) = of(e.on_bar(bar), PositionClosed)
    assert c.reason is ExitReason.SL


def test_bar_gapping_through_sl_fills_at_open_not_at_sl(rules):
    e, d = opened(rules, LONG)
    gap_open = d.sl - 20
    bar = MarkBar(DAY0 + 60_000, DAY0 + 119_999, gap_open, gap_open + 1, gap_open - 1, gap_open)
    (c,) = of(e.on_bar(bar), PositionClosed)
    assert c.reason is ExitReason.SL and c.exit_price is not None and c.exit_price <= gap_open


def test_bar_tp_never_fills_better_than_tp(rules):
    tp = D("60600")
    e, _ = opened(rules, LONG, tp=tp)
    bar = MarkBar(DAY0 + 60_000, DAY0 + 119_999, tp + 50, tp + 60, tp + 40, tp + 55)
    (c,) = of(e.on_bar(bar), PositionClosed)
    assert c.reason is ExitReason.TP and c.exit_price is not None and c.exit_price <= tp


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_paper_liquidation_beats_sl_and_loses_margin_plus_liquidation_fee(rules, direction):
    e, _ = opened(rules, direction)
    pos = e.position
    assert pos is not None
    wallet_before = e.wallet
    through = pos.liq_price_est - 10 if direction is LONG else pos.liq_price_est + 10
    (c,) = of(e.on_tick(tick(DAY0 + 2000, through)), PositionClosed)
    assert c.reason is ExitReason.LIQUIDATION and c.exit_price is None and c.fills == ()
    n = pos.qty * pos.entry_price
    #  레지스트리 #2·#4: 남은 격리 지갑(N/L − 진입 수수료) 전부 + 명목 × liquidationFee
    expected = n / pos.leverage - pos.entry_commission + n * rules.symbol_rules.liquidation_fee
    assert c.realized_pnl_usdt == -expected and e.wallet == wallet_before - expected
    #  진입부터 합치면 총손실 = N/L + N×fee
    assert abs((W0 - e.wallet) - (n / pos.leverage + n * rules.symbol_rules.liquidation_fee)) < D("1e-20")


def test_live_does_not_simulate_liquidation_it_alerts_and_exits_by_sl(rules):
    s = SpySender(PaperSender(rules), mode=Mode.LIVE, exchange_liq=D("1"))
    probe = size_entry(D("60000"), intent().sl, LONG, W0, intent().regime, rules, SizingLimits())
    s.exchange_amt = probe.qty
    e = Engine(rules, s, mode=Mode.LIVE, wallet=W0, limits=SizingLimits())
    e.request_entry(intent())
    e.on_tick(tick(DAY0 + 1000, "60000"))
    pos = e.position
    assert pos is not None and not e.entries_blocked
    s.exchange_amt = D("0")
    ev = e.on_tick(tick(DAY0 + 2000, pos.liq_price_est - 10))
    assert of(ev, LiquidationThresholdCrossed)
    (c,) = of(ev, PositionClosed)
    assert c.reason is ExitReason.SL and not e.entries_blocked


# ── 펀딩 ─────────────────────────────────────────────────────────────────────
def test_funding_settles_at_00_08_16_utc_with_the_rate_seen_before_the_boundary(rules):
    e, _ = opened(rules, LONG)
    pos = e.position
    assert pos is not None
    events = []
    for i in range(1, 25):                                  # 01:00:01 ~ 다음날 00:00:01
        events += e.on_tick(tick(DAY0 + i * H + 1000, "60000", rate=RATE * i))
    fs = of(events, FundingSettled)
    assert [(f.ts_ms - DAY0) // H % 24 for f in fs] == [8, 16, 0]
    for f in fs:
        hour = (f.ts_ms - DAY0) // H
        assert f.rate == RATE * (hour - 1), "경계 직전 틱의 펀딩율"
        assert f.paid_usdt == pos.qty * D("60000") * f.rate > 0, "LONG · 양수 펀딩 → 지불"
    assert e.wallet == W0 - pos.entry_commission - sum(f.paid_usdt for f in fs)


def test_short_receives_positive_funding(rules):
    e, _ = opened(rules, SHORT)
    fs = of(e.on_tick(tick(next_funding(DAY0) + 1000, "60000")), FundingSettled)
    assert len(fs) == 1 and fs[0].paid_usdt < 0


def test_no_funding_when_flat_at_the_boundary(rules):
    e = engine(rules)
    e.on_tick(tick(DAY0 + 1000, "60000"))
    assert of(e.on_tick(tick(next_funding(DAY0) + 1000, "60000")), FundingSettled) == []
    assert e.wallet == W0


def test_funding_time_off_the_interval_grid_is_a_feed_error(rules):
    assert rules.funding.interval_hours == 8
    e = engine(rules)
    with pytest.raises(FeedError):
        e.on_tick(MarkTick(DAY0 + 1000, D("60000"), RATE, DAY0 + 3 * H))


def test_explicit_funding_event_for_bar_replay(rules):
    e, _ = opened(rules, LONG)
    pos = e.position
    assert pos is not None
    (f,) = of(e.on_funding(ts_ms=DAY0 + 8 * H, rate=D("-0.0002"), mark=D("60100")), FundingSettled)
    assert f.paid_usdt == pos.qty * D("60100") * D("-0.0002")


# ── 수동 청산 ─────────────────────────────────────────────────────────────────
def test_close_now_is_reduce_only_manual_exit(rules):
    s = SpySender(PaperSender(rules))
    e, _ = opened(rules, SHORT, sender=s)
    (c,) = of(e.close_now(ref_mark=D("60000"), ts_ms=DAY0 + 5000), PositionClosed)
    assert c.reason is ExitReason.MANUAL and e.position is None
    last = [x for x in s.calls if x[0] == "send"][-1][1]
    assert last["side"] == Side.BUY.value and last["reduceOnly"] == "true"


# ── 성질: 회계 보존 ────────────────────────────────────────────────────────────
@settings(max_examples=120, deadline=None)
@given(direction=st.sampled_from([LONG, SHORT]),
       steps=st.lists(st.integers(min_value=-60, max_value=60), min_size=1, max_size=400),
       use_tp=st.booleans(), rate_bp=st.integers(min_value=-5, max_value=5))
def test_property_wallet_conservation_and_sl_never_better(rules, direction, steps, use_tp, rate_bp):
    e = engine(rules)
    tp = ("60360" if direction is LONG else "59640") if use_tp else None
    i = intent(direction, tp=tp)
    e.request_entry(i)
    events: list = []
    mark = D("60000")
    ts = DAY0
    rate = RATE * rate_bp
    for s in steps:
        ts += 5 * 60_000                                    # 5분 간격 → 400걸음 ≈ 33시간, 펀딩 경계 여러 번
        mark = max(D("1000"), mark + D(s) * 10)
        events += e.on_tick(tick(ts, mark, rate))
    fills = of(events, EntryFilled)
    comm = sum(f.commission for x in fills for f in x.fills)
    closed = of(events, PositionClosed)
    exit_comm = sum(c.exit_commission_usdt for c in closed)
    funding = sum(f.paid_usdt for f in of(events, FundingSettled))
    realized = sum(c.realized_pnl_usdt for c in closed)
    assert e.wallet == W0 - comm - exit_comm - funding + realized
    entry_qty = sum(f.qty for x in fills for f in x.fills)
    for c in closed:
        if c.reason is not ExitReason.LIQUIDATION:
            assert sum(f.qty for f in c.fills) == entry_qty == c.qty
            assert c.exit_price is not None
            pnl = (c.exit_price - c.entry_price) * c.qty
            assert c.realized_pnl_usdt == (pnl if direction is LONG else -pnl), "실현손익은 체결가 기준"
        if c.reason is ExitReason.SL:
            assert c.exit_price is not None
            assert (c.exit_price <= i.sl) if direction is LONG else (c.exit_price >= i.sl)
