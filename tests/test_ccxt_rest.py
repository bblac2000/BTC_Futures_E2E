"""`exchange/ccxt_rest.py` — ccxt(`binanceusdm`)를 **전송으로만** 쓰는 `RestClient` 어댑터(레지스트리 #8).

- 원시 엔드포인트 응답을 그대로 돌려준다(ccxt 정규화 필드 사용 금지) → loader·gate·sender는 바이트 동일
- 서명·timestamp·recvWindow는 ccxt가 **한 번만** 붙인다(우리가 덧붙이지 않는다)
- 주문은 `create_order(type='market', reduceOnly=True)` — 단 wire body가 우리가 검증한 파라미터와 같아야 하고,
  ccxt 정밀도가 수량을 바꾸면 **보내지 않는다**, `newClientOrderId`는 우리 것(ccxt 브로커 id 주입 차단)
- 오류: Binance `{code,msg}` → `BinanceAPIError(code)` · 5xx·타임아웃·연결 끊김 → `TransportError`(결과 불명)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import requests

from exchange.ccxt_rest import CLIENT_ORDER_ID_PREFIX, CcxtRestClient
from exchange.errors import BinanceAPIError, OrderParamError, ReadOnlyViolation, TransportError
from exchange.gate import Mode, run_startup_gate
from exchange.loader import load_runtime_rules
from exchange.orders import Direction, Intent, market_order_params
from exchange.ratelimit import RateLimitCounter
from tests.conftest import load_snapshot
from tests.fake_http import FakeHttp
from tests.test_gate import FakeAccount

SNAP = {"/fapi/v1/exchangeInfo": "exchangeInfo", "/fapi/v1/leverageBracket": "leverageBracket",
        "/fapi/v1/commissionRate": "commissionRate", "/fapi/v1/fundingInfo": "fundingInfo"}


def make(route, **kw) -> tuple[CcxtRestClient, FakeHttp]:
    http = FakeHttp(route)
    c = CcxtRestClient(api_key="KEY", secret="SECRET", **kw)
    c.ex.session.request = http.request          # type: ignore[method-assign]
    info = load_snapshot("exchangeInfo")["response"]
    c.ex.set_markets(c.ex.parse_markets([s for s in info["symbols"] if s["symbol"] == "BTCUSDT"]))
    return c, http


def ok(payload: Any):
    return lambda m, p, q: (200, payload)


# ── 경로·서명 ────────────────────────────────────────────────────────────────
def test_public_get_returns_the_raw_exchange_info_payload_unsigned(snap):
    raw = snap["exchangeInfo"]["response"]
    c, http = make(ok(raw))
    r = c.get("/fapi/v1/exchangeInfo")
    assert r.data == raw and "rateLimits" in r.data and "serverTime" in r.data
    (s,) = http.sent
    assert s.method == "GET" and s.url.startswith("https://fapi.binance.com/fapi/v1/exchangeInfo")
    assert s.count("signature") == 0 and s.count("timestamp") == 0 and "X-MBX-APIKEY" not in s.headers


@pytest.mark.parametrize("path, host_path", [
    ("/fapi/v2/positionRisk", "/fapi/v2/positionRisk"),
    ("/fapi/v3/positionRisk", "/fapi/v3/positionRisk"),
    ("/fapi/v1/positionSide/dual", "/fapi/v1/positionSide/dual"),
    ("/fapi/v1/multiAssetsMargin", "/fapi/v1/multiAssetsMargin"),
    ("/fapi/v1/openAlgoOrders", "/fapi/v1/openAlgoOrders"),
    ("/fapi/v1/leverageBracket", "/fapi/v1/leverageBracket"),
    ("/fapi/v1/commissionRate", "/fapi/v1/commissionRate"),
    ("/fapi/v1/userTrades", "/fapi/v1/userTrades"),
])
def test_signed_get_has_exactly_one_timestamp_recvwindow_and_signature(path, host_path):
    c, http = make(ok([]), recv_window_ms=5000)
    c.get(path, {"symbol": "BTCUSDT"}, signed=True)
    (s,) = http.sent
    assert s.path == host_path and s.method == "GET"
    assert s.count("timestamp") == 1 and s.count("recvWindow") == 1 and s.count("signature") == 1
    assert s.all_params()["recvWindow"] == "5000" and s.all_params()["symbol"] == "BTCUSDT"
    assert s.headers.get("X-MBX-APIKEY") == "KEY"


def test_unknown_api_prefix_fails_closed_without_a_request():
    c, http = make(ok({}))
    for p in ("/dapi/v1/positionRisk", "/api/v3/account", "fapi/v1/time", "/fapi/v9/x"):
        with pytest.raises(ValueError):
            c.get(p)
    assert http.sent == []


def test_post_leverage_returns_raw_echo():
    c, http = make(lambda m, p, q: (200, {"symbol": q["symbol"], "leverage": int(q["leverage"]), "maxNotionalValue": "1"}))
    r = c.post("/fapi/v1/leverage", {"symbol": "BTCUSDT", "leverage": "75"})
    assert r.data["leverage"] == 75
    (s,) = http.sent
    assert s.method == "POST" and s.path == "/fapi/v1/leverage" and s.count("timestamp") == 1


def test_rate_limit_headers_feed_our_counter(snap):
    from exchange.rules import parse_rate_limits
    counter = RateLimitCounter(parse_rate_limits(snap["exchangeInfo"]["response"]))
    c, _ = make(ok({}), rate_limits=counter, clock_ms=lambda: 120_000)
    c.get("/fapi/v1/time")
    assert any(v > 0 for v in counter.usage(120_000).values())


def test_time_sync_uses_ccxt_offset_and_does_not_add_our_own_timestamp():
    c, http = make(lambda m, p, q: (200, {"serverTime": 1_789_000_000_000}) if p.endswith("/time") else (200, []))
    c.ex.milliseconds = lambda: 1_789_000_000_500           # type: ignore[method-assign]
    c.sync_time()
    assert c.ex.options["timeDifference"] == 500
    c.get("/fapi/v2/positionRisk", signed=True)
    s = http.sent[-1]
    assert s.count("timestamp") == 1 and s.all_params()["timestamp"] == "1789000000000"


# ── 주문 ─────────────────────────────────────────────────────────────────────
def order_route(m, p, q):
    if p.endswith("/order") and m == "POST":
        return 200, {"orderId": 7, "symbol": q["symbol"], "status": "FILLED", "clientOrderId": q["newClientOrderId"],
                     "avgPrice": "60000.10", "executedQty": q["quantity"], "side": q["side"], "type": "MARKET",
                     "reduceOnly": q.get("reduceOnly") == "true", "updateTime": 1789000000123}
    raise AssertionError(f"unexpected {m} {p}")


@pytest.mark.parametrize("intent, qty", [(Intent.ENTRY, "0.033"), (Intent.EXIT, "0.033"), (Intent.ENTRY, "0.010"),
                                         (Intent.EXIT, "1.200")])
def test_order_goes_through_create_order_with_the_exact_validated_wire_body(rules, intent, qty):
    c, http = make(order_route)
    params = market_order_params("BTCUSDT", Direction.LONG, intent, Decimal(qty), rules.symbol_rules)
    sent_params = params | {"newOrderRespType": "RESULT"}
    r = c.post("/fapi/v1/order", sent_params)
    (s,) = http.sent
    wire = s.all_params()
    for k in ("timestamp", "recvWindow", "signature"):
        assert s.count(k) == 1
        wire.pop(k)
    coid = wire.pop("newClientOrderId")
    assert coid.startswith(CLIENT_ORDER_ID_PREFIX) and not coid.startswith("x-"), "ccxt 브로커 id가 아니라 우리 id"
    assert 1 <= len(coid) <= 36
    assert Decimal(wire.pop("quantity")) == Decimal(sent_params["quantity"]), "수량은 값이 같다(표기만 ccxt 형식)"
    assert wire == {k: v for k, v in sent_params.items() if k != "quantity"}, "wire body = 우리가 검증한 파라미터(ccxt가 더하거나 바꾼 키 없음)"
    assert r.data["status"] == "FILLED" and Decimal(r.data["executedQty"]) == Decimal(qty), "원시 응답(info)을 돌려준다"


def test_caller_supplied_client_order_id_is_kept(rules):
    c, http = make(order_route)
    p = market_order_params("BTCUSDT", Direction.SHORT, Intent.ENTRY, Decimal("0.010"), rules.symbol_rules)
    c.post("/fapi/v1/order", p | {"newClientOrderId": "mine-123"})
    assert http.sent[0].all_params()["newClientOrderId"] == "mine-123"


def test_ccxt_precision_disagreement_refuses_to_send(rules, monkeypatch):
    """ccxt `create_order`는 수량을 조용히 `amount_to_precision`으로 자른다(0.0339→0.033 실측).
    우리 정규화가 권위다 — ccxt가 바꾸려 하면 보내지 않는다."""
    c, http = make(order_route)
    p = market_order_params("BTCUSDT", Direction.LONG, Intent.ENTRY, Decimal("0.033"), rules.symbol_rules)
    monkeypatch.setattr(c.ex, "amount_to_precision", lambda symbol, amount: "0.03")
    with pytest.raises(OrderParamError):
        c.post("/fapi/v1/order", p)
    assert http.sent == []


@pytest.mark.parametrize("bad", [
    {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT", "quantity": "0.033", "price": "1"},
    {"symbol": "BTCUSDT", "side": "LONG", "type": "MARKET", "quantity": "0.033"},
    {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.033", "reduceOnly": "false"},
    {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.033", "stopPrice": "1"},
    {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.033"},
])
def test_invalid_order_params_never_reach_the_wire(bad):
    c, http = make(order_route)
    with pytest.raises((OrderParamError, ValueError)):
        c.post("/fapi/v1/order", bad)
    assert http.sent == []


def test_read_only_wrapper_still_blocks_posts_over_ccxt():
    from exchange.client import ReadOnlyClient
    c, http = make(ok({}))
    with pytest.raises(ReadOnlyViolation):
        ReadOnlyClient(c).post("/fapi/v1/leverage", {"symbol": "BTCUSDT", "leverage": "5"})
    assert http.sent == []


# ── 오류 매핑 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status, body, code", [
    (400, {"code": -4046, "msg": "No need to change margin type."}, -4046),
    (400, {"code": -2019, "msg": "Margin is insufficient."}, -2019),
    (400, {"code": -1111, "msg": "Precision is over the maximum defined for this asset."}, -1111),
    (400, {"code": -1008, "msg": "Request throttled by system-level protection."}, -1008),
    (429, {"code": -1003, "msg": "Too many requests."}, -1003),
    (401, {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."}, -2015),
])
def test_binance_error_bodies_become_binance_api_error_with_the_code(status, body, code):
    c, _ = make(lambda m, p, q: (status, body))
    with pytest.raises(BinanceAPIError) as e:
        c.post("/fapi/v1/marginType", {"symbol": "BTCUSDT", "marginType": "ISOLATED"})
    assert e.value.code == code and e.value.status == status and e.value.path == "/fapi/v1/marginType"


def test_timestamp_error_resyncs_time_then_raises():
    calls = {"time": 0}

    def route(m, p, q):
        if p.endswith("/time"):
            calls["time"] += 1
            return 200, {"serverTime": 1}
        return 400, {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}
    c, _ = make(route)
    with pytest.raises(BinanceAPIError) as e:
        c.get("/fapi/v2/positionRisk", signed=True)
    assert e.value.code == -1021 and calls["time"] == 1


@pytest.mark.parametrize("status, body", [
    (503, {"code": -1000, "msg": "Unknown error, please check your request or try again later."}),
    (502, "<html>bad gateway</html>"),
    (500, {"code": -1000, "msg": "Internal error; unable to process your request. Please try again."}),
])
def test_5xx_is_outcome_unknown_even_with_a_json_body(status, body):
    """Binance 문서: 503 "Unknown error"는 **실행 여부 불명** — 주문 POST였다면 체결됐을 수 있다."""
    c, _ = make(lambda m, p, q: (status, body))
    with pytest.raises(TransportError):
        c.post("/fapi/v1/leverage", {"symbol": "BTCUSDT", "leverage": "5"})


@pytest.mark.parametrize("exc", [requests.exceptions.ReadTimeout("Read timed out"),
                                 requests.exceptions.ConnectionError("Connection aborted."),
                                 ConnectionResetError("reset")])
def test_transport_failures_are_transport_error(exc):
    def route(m, p, q):
        raise exc
    c, _ = make(route)
    with pytest.raises(TransportError):
        c.post("/fapi/v1/order", {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.033"})


# ── 기존 계층이 ccxt 전송 위에서 그대로 돈다 ─────────────────────────────────
def account_route(acct: FakeAccount, snap: dict):
    def route(m, p, q):
        if p in SNAP:
            return 200, snap[SNAP[p]]["response"]
        q = {k: v for k, v in q.items() if k not in ("timestamp", "recvWindow", "signature")}
        try:
            r = acct.get(p, q, signed=True) if m == "GET" else acct.post(p, q)
        except BinanceAPIError as e:
            return e.status, {"code": e.code, "msg": e.msg}
        return 200, r.data
    return route


def test_loader_builds_runtime_rules_from_raw_payloads_over_ccxt(snap, rules):
    c, _ = make(account_route(FakeAccount(), snap))
    r, fetches = load_runtime_rules(c, "BTCUSDT")
    assert r.symbol_rules == rules.symbol_rules and r.brackets == rules.brackets and r.commission == rules.commission
    assert r.funding == rules.funding and r.rate_limits == rules.rate_limits


def test_live_startup_gate_over_ccxt_switches_to_isolated_and_confirms_leverage(snap, rules):
    acct = FakeAccount(margin_type="cross", leverage=5)
    c, http = make(account_route(acct, snap))
    res = run_startup_gate(c, rules, Mode.LIVE, leverage=75)
    assert res.isolated_confirmed and res.leverage_set == 75
    assert [s.path for s in http.sent if s.method == "POST"] == ["/fapi/v1/marginType", "/fapi/v1/leverage"]


def test_paper_gate_over_ccxt_sends_no_posts(snap, rules):
    c, http = make(account_route(FakeAccount(margin_type="cross", dual=True), snap))
    run_startup_gate(c, rules, Mode.PAPER, leverage=75)
    assert all(s.method == "GET" for s in http.sent)
