"""layer 3 송신기 — 페이퍼·라이브가 **같은 인터페이스**(`OrderSender`), 모드 플래그로만 갈린다.

PAPER: taker 전용 · mark 기준 체결 + 보수 슬리피지(불리한 방향 · tick 불리 반올림) · 수수료 = 런타임 taker · POST 0회
LIVE : `Mode.LIVE` + 라이브 체크리스트 전 항목 없이는 **생성 자체가 불가** · 레버리지 응답 확인 · 전송 불명은 이름 있는 예외
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from exchange.client import ReadOnlyClient, Response
from exchange.errors import LeverageNotConfirmed, OrderParamError, TransportError
from exchange.gate import Mode
from exchange.orders import Direction, Intent, Side, market_order_params
from paper.config import PAPER_SLIPPAGE_RATE, PAPER_SLIPPAGE_TAG
from paper.sender import (
    LiveChecklist,
    LiveNotAuthorized,
    LiveSender,
    OrderOutcomeUnknown,
    PaperSender,
    adverse_fill_estimate,
    make_sender,
)

D = Decimal


def params(rules, direction=Direction.LONG, intent=Intent.ENTRY, qty="0.010"):
    return market_order_params("BTCUSDT", direction, intent, D(qty), rules.symbol_rules)


def all_checked() -> LiveChecklist:
    return LiveChecklist(**{f.name: True for f in fields(LiveChecklist)})


# ── PAPER ────────────────────────────────────────────────────────────────────
def test_slippage_constant_is_the_pre_committed_registry_7_value():
    """레지스트리 #7(사용자 2026-09-15): 편도 2 bps + 불리 tick — 7일 |mark−mid|/mid p99 1.835 bps 근거. 0.016 bps 대체."""
    assert PAPER_SLIPPAGE_RATE == D("0.0002")
    assert "#7" in PAPER_SLIPPAGE_TAG


def test_paper_buy_fills_above_mark_and_sell_below_on_tick_grid(rules):
    s = PaperSender(rules)
    tick = rules.symbol_rules.tick_size
    mark = D("60000.03")
    buy = s.send_market(params(rules), ref_mark=mark, ts_ms=1)
    sell = s.send_market(params(rules, Direction.LONG, Intent.EXIT), ref_mark=mark, ts_ms=2)
    assert buy.price > mark and buy.price % tick == 0
    assert sell.price < mark and sell.price % tick == 0
    assert buy.price == D("60012.1") and sell.price == D("59988.0")      # 60000.03×(1±0.0002) → 불리한 tick
    assert buy.commission == buy.qty * buy.price * rules.commission.taker
    assert sell.reduce_only and not buy.reduce_only
    assert buy.side.value == "BUY" and sell.side.value == "SELL"


@settings(max_examples=200, deadline=None)
@given(mark=st.decimals(min_value=D("1000"), max_value=D("500000"), places=2), buy=st.booleans())
def test_property_paper_fill_is_never_better_than_mark(rules, mark, buy):
    s = PaperSender(rules)
    p = params(rules, Direction.LONG, Intent.ENTRY if buy else Intent.EXIT)
    f = s.send_market(p, ref_mark=mark, ts_ms=0)
    assert (f.price >= mark) if buy else (f.price <= mark)
    assert abs(f.price - mark) <= mark * PAPER_SLIPPAGE_RATE + rules.symbol_rules.tick_size


def test_paper_leverage_is_recorded_and_echoed(rules):
    s = PaperSender(rules)
    assert s.set_leverage(73) == 73 and s.leverage == 73


def test_paper_never_reads_exchange_position(rules):
    """레지스트리 #6: 페이퍼 포지션은 거래소에 없다 → positionRisk를 읽지 않는다."""
    assert PaperSender(rules).position_risk() is None


def test_paper_validates_params_like_live(rules):
    s = PaperSender(rules)
    bad = params(rules) | {"type": "LIMIT"}
    with pytest.raises(OrderParamError):
        s.send_market(bad, ref_mark=D("60000"), ts_ms=0)


# ── LIVE: 생성 게이트 ──────────────────────────────────────────────────────────
@dataclass
class FakeLive:
    echo: int | None = None
    order_status: str = "FILLED"
    transport_on_order: bool = False
    trades: bool = True
    amt: str = "0.010"
    calls: list = field(default_factory=list)

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        self.calls.append(("GET", path, dict(params or {})))
        if path == "/fapi/v1/userTrades":
            if not self.trades:
                return Response(200, [], {})
            return Response(200, [{"orderId": 7, "qty": "0.006", "price": "60000.1", "commission": "0.18000030",
                                   "commissionAsset": "USDT"},
                                  {"orderId": 7, "qty": "0.004", "price": "60000.4", "commission": "0.12000080",
                                   "commissionAsset": "USDT"}], {})
        if path == "/fapi/v2/positionRisk":
            return Response(200, [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": self.amt,
                                   "entryPrice": "60000.22", "liquidationPrice": "59700.1", "marginType": "isolated"}], {})
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, params: dict | None = None, *, signed: bool = True) -> Response:
        p = dict(params or {})
        self.calls.append(("POST", path, p))
        if path == "/fapi/v1/leverage":
            return Response(200, {"symbol": p["symbol"], "leverage": self.echo or int(p["leverage"])}, {})
        if path == "/fapi/v1/order":
            if self.transport_on_order:
                raise TransportError("POST /fapi/v1/order: TimeoutError")
            return Response(200, {"orderId": 7, "status": self.order_status, "avgPrice": "60000.22",
                                  "executedQty": "0.010", "side": p["side"], "reduceOnly": p.get("reduceOnly") == "true",
                                  "updateTime": 1700000000123}, {})
        raise AssertionError(f"unexpected POST {path}")


@pytest.mark.parametrize("mode", [Mode.PAPER, "live", None])
def test_live_sender_requires_live_mode(rules, mode):
    with pytest.raises(LiveNotAuthorized):
        LiveSender(FakeLive(), rules, mode=mode, checklist=all_checked())  # type: ignore[arg-type]


def test_live_sender_requires_every_checklist_item(rules):
    names = [f.name for f in fields(LiveChecklist)]
    assert "usdm_only_account_no_coinm" in names and "user_approval" in names and "registry5_day14_row_exists" in names
    assert LiveChecklist().missing() == names, "기본값은 전부 미충족"
    for n in names:
        cl = LiveChecklist(**{f: f != n for f in names})
        with pytest.raises(LiveNotAuthorized) as e:
            LiveSender(FakeLive(), rules, mode=Mode.LIVE, checklist=cl)
        assert n in str(e.value)


def test_live_sender_refuses_read_only_client(rules):
    with pytest.raises(LiveNotAuthorized):
        LiveSender(ReadOnlyClient(FakeLive()), rules, mode=Mode.LIVE, checklist=all_checked())


def test_checklist_values_must_be_real_bools(rules):
    cl = LiveChecklist(**{f.name: "yes" for f in fields(LiveChecklist)})  # type: ignore[arg-type]
    with pytest.raises(LiveNotAuthorized):
        LiveSender(FakeLive(), rules, mode=Mode.LIVE, checklist=cl)


def test_make_sender_paper_needs_no_client_and_live_is_gated(rules):
    assert isinstance(make_sender(Mode.PAPER, rules), PaperSender)
    with pytest.raises(LiveNotAuthorized):
        make_sender(Mode.LIVE, rules, client=FakeLive(), checklist=LiveChecklist())
    assert isinstance(make_sender(Mode.LIVE, rules, client=FakeLive(), checklist=all_checked()), LiveSender)


# ── LIVE: 동작 ────────────────────────────────────────────────────────────────
def live(rules, **kw) -> tuple[LiveSender, FakeLive]:
    c = FakeLive(**kw)
    return LiveSender(c, rules, mode=Mode.LIVE, checklist=all_checked()), c


def test_live_leverage_echo_must_match(rules):
    s, c = live(rules)
    assert s.set_leverage(73) == 73
    s2, _ = live(rules, echo=50)
    with pytest.raises(LeverageNotConfirmed):
        s2.set_leverage(73)


def test_live_order_uses_result_response_and_trade_commissions(rules):
    s, c = live(rules)
    f = s.send_market(params(rules), ref_mark=D("60000"), ts_ms=5)
    post = [x for x in c.calls if x[0] == "POST"][0]
    assert post[1] == "/fapi/v1/order" and post[2]["newOrderRespType"] == "RESULT" and post[2]["type"] == "MARKET"
    assert f.price == D("60000.22") and f.qty == D("0.010")
    assert f.commission == D("0.30000110") and not f.commission_estimated
    assert f.order_id == "7" and f.ts_ms == 1700000000123


def test_live_commission_falls_back_to_runtime_taker_and_is_flagged(rules):
    s, _ = live(rules, trades=False)
    f = s.send_market(params(rules), ref_mark=D("60000"), ts_ms=5)
    assert f.commission_estimated and f.commission == f.qty * f.price * rules.commission.taker


def test_live_transport_error_on_order_is_outcome_unknown(rules):
    s, _ = live(rules, transport_on_order=True)
    with pytest.raises(OrderOutcomeUnknown):
        s.send_market(params(rules), ref_mark=D("60000"), ts_ms=5)


@pytest.mark.parametrize("status", ["NEW", "EXPIRED", "CANCELED", "REJECTED"])
def test_live_non_filled_status_is_outcome_unknown(rules, status):
    s, _ = live(rules, order_status=status)
    with pytest.raises(OrderOutcomeUnknown):
        s.send_market(params(rules), ref_mark=D("60000"), ts_ms=5)


def test_live_position_risk_is_read(rules):
    s, _ = live(rules)
    pr = s.position_risk()
    assert pr is not None and pr.amt == D("0.010") and pr.liquidation_price == D("59700.1")


def test_live_sender_posts_only_order_and_leverage(rules):
    s, c = live(rules)
    s.set_leverage(60)
    s.send_market(params(rules), ref_mark=D("60000"), ts_ms=5)
    s.position_risk()
    assert {x[1] for x in c.calls if x[0] == "POST"} == {"/fapi/v1/leverage", "/fapi/v1/order"}


def test_paper_quote_equals_the_fill_price(rules):
    s = PaperSender(rules)
    for side, intent in ((Side.BUY, Intent.ENTRY), (Side.SELL, Intent.EXIT)):
        f = s.send_market(params(rules, Direction.LONG, intent), ref_mark=D("60000.03"), ts_ms=0)
        assert s.quote_fill_price(side, D("60000.03")) == f.price


@pytest.mark.parametrize("mark", [D("60000"), D("60000.03"), D("61234.56")])
def test_live_quote_uses_the_registry_7_adverse_model_same_as_paper(rules, mark):
    """사용자 결정(2026-09-15): LIVE 예상 체결가도 #7(편도 2 bps 불리 + 불리 tick) — mark로 추정하면 모든 진입이 #5 경계에
    붙고 실제 슬리피지가 곧 체결 후 청산이 된다. 같은 코드 경로, 실제 체결만 다르다."""
    s, _ = live(rules)
    paper = PaperSender(rules)
    for side in (Side.BUY, Side.SELL):
        assert s.quote_fill_price(side, mark) == paper.quote_fill_price(side, mark) == adverse_fill_estimate(
            side, mark, rules.symbol_rules.tick_size)
    assert s.quote_fill_price(Side.BUY, mark) > mark > s.quote_fill_price(Side.SELL, mark)


@pytest.mark.parametrize("bad", [
    [{"orderId": 7, "qty": "0.010", "commissionAsset": "USDT"}],                                   # commission 없음
    [{"orderId": 7, "qty": "0.010", "commission": "abc", "commissionAsset": "USDT"}],              # 숫자 아님
    [{"orderId": 8, "qty": "0.010", "commission": "0.3", "commissionAsset": "USDT"}],              # 다른 주문
    [{"orderId": 7, "qty": "0.004", "commission": "0.3", "commissionAsset": "USDT"}],              # 수량 합 불일치
    [{"orderId": 7, "qty": "0.010", "commission": "0.3", "commissionAsset": "BNB"}],               # USDT 아님
    [{"orderId": 7, "symbol": "ETHUSDT", "qty": "0.010", "commission": "0.3", "commissionAsset": "USDT"}],
    {"not": "a list"},
])
def test_live_malformed_or_mismatched_trades_never_raise_after_a_fill(rules, bad):
    """Codex L3 검토 2: 체결된 뒤 수수료 조회가 이상해도 예외로 새지 않는다 — 런타임 taker 추정 + 표시."""
    s, c = live(rules)
    real_get = c.get

    def get(path, params=None, *, signed=False):
        if path == "/fapi/v1/userTrades":
            return Response(200, bad, {})
        return real_get(path, params, signed=signed)
    c.get = get  # type: ignore[method-assign]
    f = s.send_market(params(rules), ref_mark=D("60000"), ts_ms=5)
    assert f.commission_estimated and f.commission == f.qty * f.price * rules.commission.taker


def test_live_unparseable_update_time_falls_back_to_local_ts(rules):
    s, c = live(rules)
    real_post = c.post

    def post(path, params=None, *, signed=True):
        r = real_post(path, params, signed=signed)
        return Response(200, r.data | {"updateTime": "soon"}, {}) if path == "/fapi/v1/order" else r
    c.post = post  # type: ignore[method-assign]
    assert s.send_market(params(rules), ref_mark=D("60000"), ts_ms=5).ts_ms == 5


@pytest.mark.parametrize("rows", [
    [{"symbol": "BTCUSDT", "positionSide": "BOTH", "entryPrice": "1", "liquidationPrice": "1"}],          # positionAmt 없음
    [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "abc", "entryPrice": "1", "liquidationPrice": "1"}],
    {"not": "a list"},
    [None],
])
def test_live_malformed_position_risk_is_outcome_unknown_not_a_parser_error(rules, rows):
    """Codex L3 재검토 1: 주문 뒤 대사 조회의 모양 오류도 이름 있는 예외 하나로 — 엔진이 잡아 진입을 막는다."""
    s, c = live(rules)
    c.get = lambda path, params=None, *, signed=False: Response(200, rows, {})  # type: ignore[method-assign]
    with pytest.raises(OrderOutcomeUnknown):
        s.position_risk()
