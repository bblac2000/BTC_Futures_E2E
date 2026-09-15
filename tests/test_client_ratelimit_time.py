"""REST 클라이언트 서명·에러 보존 · rate-limit 카운터 · 서버 시각 오프셋."""
from __future__ import annotations

import io
import json
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from exchange.client import BinanceRestClient, sign
from exchange.errors import BinanceAPIError, CredentialsMissing
from exchange.ratelimit import RateLimitCounter
from exchange.timesync import TimeSync


def test_hmac_signature_matches_the_binance_documentation_example():
    """Binance API 문서의 공개 서명 예시(가짜 키) — 알고리즘 회귀 잠금."""
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
    q = ("symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1"
         "&recvWindow=5000&timestamp=1499827319559")
    assert sign(secret, q) == "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"


class _Resp(io.BytesIO):
    def __init__(self, body: bytes, headers: dict, status: int = 200):
        super().__init__(body)
        self.headers, self.status = headers, status

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


def _client(opener, **kw):
    return BinanceRestClient(api_key="k", api_secret="s", opener=opener, clock_ms=lambda: 1_000_000,
                             recv_window_ms=5000, **kw)


def test_signed_get_carries_timestamp_recv_window_signature_and_api_key_header():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["headers"], seen["method"] = req.full_url, dict(req.header_items()), req.get_method()
        return _Resp(b'{"dualSidePosition": false}', {"X-MBX-USED-WEIGHT-1M": "7"})
    ts = TimeSync()
    ts.record(local_send_ms=999_900, server_ms=1_000_300, local_recv_ms=1_000_100)   # offset +300
    r = _client(opener, time_sync=ts).get("/fapi/v1/positionSide/dual", signed=True)
    q = parse_qs(urlsplit(seen["url"]).query)
    assert r.data == {"dualSidePosition": False} and seen["method"] == "GET"
    assert q["timestamp"] == ["1000300"] and q["recvWindow"] == ["5000"]
    raw_q = urlsplit(seen["url"]).query
    unsigned, sig = raw_q.rsplit("&signature=", 1)
    assert sig == sign("s", unsigned)
    assert seen["headers"].get("X-mbx-apikey") == "k"


def test_signed_request_without_credentials_raises_before_network():
    c = BinanceRestClient(opener=lambda *a, **k: pytest.fail("network touched"))
    with pytest.raises(CredentialsMissing):
        c.get("/fapi/v1/commissionRate", {"symbol": "BTCUSDT"}, signed=True)


def test_error_json_code_and_msg_are_preserved():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {},  # type: ignore[arg-type]
                                     io.BytesIO(json.dumps({"code": -4164, "msg": "Order's notional must be no smaller than 50"}).encode()))
    with pytest.raises(BinanceAPIError) as e:
        _client(opener).post("/fapi/v1/order", {"symbol": "BTCUSDT"})
    assert (e.value.status, e.value.code) == (400, -4164) and "notional" in e.value.msg


@pytest.mark.parametrize("exc", [TimeoutError("read timed out"), ConnectionResetError("reset"),
                                 urllib.error.URLError("dns failure")])
def test_transport_failures_become_transport_error_with_unknown_outcome(exc):
    """🔴 Codex 재검토 F3 — HTTPError가 아닌 전송 실패는 '보냈는지 모름'이다. 이름 있는 예외로 올린다."""
    from exchange.errors import TransportError

    def opener(req, timeout):
        raise exc
    with pytest.raises(TransportError) as e:
        _client(opener).post("/fapi/v1/leverage", {"symbol": "BTCUSDT", "leverage": "50"})
    assert "/fapi/v1/leverage" in str(e.value) and type(exc).__name__ in str(e.value)


def test_minus_1021_marks_time_sync_stale():
    ts = TimeSync()
    ts.record(local_send_ms=0, server_ms=10, local_recv_ms=20)

    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {},  # type: ignore[arg-type]
                                     io.BytesIO(b'{"code": -1021, "msg": "Timestamp outside recvWindow"}'))
    with pytest.raises(BinanceAPIError):
        _client(opener, time_sync=ts).get("/fapi/v2/positionRisk", signed=True)
    assert ts.is_stale(local_ms=21, max_age_ms=10_000), "-1021 이후엔 재측정 전까지 stale"


def test_response_headers_feed_the_rate_limit_counter(rules):
    rl = RateLimitCounter(rules.rate_limits)

    def opener(req, timeout):
        return _Resp(b"{}", {"X-MBX-USED-WEIGHT-1M": "1920", "X-MBX-ORDER-COUNT-10S": "12"})
    _client(opener, rate_limits=rl).get("/fapi/v1/exchangeInfo")
    u = rl.usage(1_000_000)
    assert u["REQUEST_WEIGHT/MINUTE/1"] == pytest.approx(0.8)
    assert u["ORDERS/SECOND/10"] == pytest.approx(12 / 300)
    assert rl.over(0.8, 1_000_000) == ["REQUEST_WEIGHT/MINUTE/1"]


# ── rate limit ───────────────────────────────────────────────────────────
def test_rate_limit_limits_come_from_rules_and_expire_with_the_window(rules):
    rl = RateLimitCounter(rules.rate_limits)
    assert RateLimitCounter.header_name(rules.rate_limits[0]) == "X-MBX-USED-WEIGHT-1M"
    rl.observe_headers({"x-mbx-used-weight-1m": "2400"}, now_ms=60_000 * 10 + 5)
    assert rl.max_usage(60_000 * 10 + 59_000) == pytest.approx(1.0)
    assert rl.max_usage(60_000 * 11 + 1) == 0.0, "다음 분 창에서는 이전 창 사용량이 아니다"


def test_rate_limit_counter_rejects_unknown_limit_types():
    from exchange.errors import RulesError
    from exchange.rules import RateLimit
    with pytest.raises(RulesError):
        RateLimitCounter([RateLimit("RAW_REQUESTS", "MINUTE", 5, 6100)])


# ── time sync ────────────────────────────────────────────────────────────
def test_offset_uses_round_trip_midpoint_and_min_rtt_sample():
    ts = TimeSync(max_samples=3)
    ts.record(local_send_ms=1000, server_ms=1600, local_recv_ms=1200)    # rtt 200, off +500
    ts.record(local_send_ms=2000, server_ms=2530, local_recv_ms=2040)    # rtt 40,  off +510
    assert ts.offset_ms == 510 and ts.rtt_ms == 40
    assert ts.server_now_ms(10_000) == 10_510


def test_no_sample_means_no_offset_and_stale():
    ts = TimeSync()
    assert ts.offset_ms is None and ts.is_stale(local_ms=0, max_age_ms=1)
    with pytest.raises(RuntimeError):
        ts.server_now_ms(0)


def test_measure_calls_fapi_time(rules):
    ts = TimeSync()
    clock = iter([100, 140])

    class C:
        def get(self, path, params=None, *, signed=False):
            assert path == "/fapi/v1/time" and not signed
            from exchange.client import Response
            return Response(200, {"serverTime": 5120}, {})
    ts.measure(C(), clock_ms=lambda: next(clock))
    assert ts.offset_ms == 5000 and ts.age_ms(141) == 1
