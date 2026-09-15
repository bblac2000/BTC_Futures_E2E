"""ccxt `binanceusdm`을 **전송으로만** 쓰는 REST 클라이언트 — 기존 `RestClient` 프로토콜(`get/post(path, params, signed)`)을 구현한다.

레지스트리 #8(사용자 2026-09-15): ccxt==4.5.78 고정. 규칙:
- **원시 응답만** 돌려준다(`request()`의 파싱된 JSON = 거래소 원문). ccxt 정규화 필드(markets·limits·precision)를 쓰지 않는다 →
  `loader`·`gate`·`paper.sender`는 이 클라이언트를 받아도 코드가 그대로다.
- 서명·`timestamp`·`recvWindow`는 ccxt `sign()`이 한 번 붙인다. 우리는 붙이지 않는다(중복 없음 — 테스트가 개수를 센다).
  서버 시각 오프셋 = ccxt `options['timeDifference']`(`sync_time()`) · -1021이면 재동기화 후 예외.
- rate limit: ccxt 스로틀(클라이언트 토큰 버킷)은 그대로 두고, 응답 헤더를 우리 `RateLimitCounter`에 넣는다(판정은 layer 7).
- 주문(`POST /fapi/v1/order`)은 `create_order(type='market', params={'reduceOnly': True, ...})`로 보낸다. 단:
  ① `validate_order_params` 통과한 파라미터만 ② ccxt `amount_to_precision`이 우리 수량과 **값이 다르면 보내지 않는다**(표기 차이 `0.010`↔`0.01`은 허용)
     (ccxt는 수량을 조용히 자른다 — 0.0339→0.033 실측 2026-09-15) ③ `newClientOrderId`는 **우리 것**
     (없으면 ccxt가 자기 브로커 id `x-…`를 주입한다) ④ 돌려주는 값은 `order['info']`(원시 응답).
- 오류: 5xx·타임아웃·연결 실패 → `TransportError`(실행 여부 불명 — Binance 문서 503 "Unknown error") ·
  Binance `{code,msg}` 본문 → `BinanceAPIError(code)`(게이트의 -4046 처리 등이 그대로 동작).
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import ccxt

from exchange.client_types import Response
from exchange.errors import BinanceAPIError, OrderParamError, TransportError
from exchange.orders import validate_order_params
from exchange.ratelimit import RateLimitCounter

#  경로 접두사 → (ccxt api 이름: 서명 안 함, 서명함). 여기 없는 접두사는 거부(모르는 API로 조용히 보내지 않는다).
API_BY_PREFIX: dict[str, tuple[str, str]] = {
    "/fapi/v1/": ("fapiPublic", "fapiPrivate"),
    "/fapi/v2/": ("fapiPublicV2", "fapiPrivateV2"),
    "/fapi/v3/": ("fapiPublicV3", "fapiPrivateV3"),
    "/sapi/v1/": ("sapi", "sapi"),            # capture_account_snapshot.py의 apiRestrictions(읽기 전용)
}
ORDER_PATH = "/fapi/v1/order"
CLIENT_ORDER_ID_PREFIX = "bfe2e-"             # Binance 허용 문자 ^[.A-Z:/a-z0-9_-]{1,36}$
TIMESTAMP_ERROR = -1021


def _wall_ms() -> int:
    return int(time.time() * 1000)


def _split(path: str, signed: bool) -> tuple[str, str]:
    for prefix, (public, private) in API_BY_PREFIX.items():
        if path.startswith(prefix) and len(path) > len(prefix):
            return (private if signed else public), path[len(prefix):]
    raise ValueError(f"지원하지 않는 API 경로 {path!r} — 허용 접두사 {sorted(API_BY_PREFIX)}")


def _binance_body(message: str) -> dict | None:
    """ccxt 예외 메시지(`binanceusdm {"code":-4046,...}`)에 실린 거래소 원문 JSON."""
    i = message.find("{")
    if i < 0:
        return None
    try:
        body = json.loads(message[i:])
    except ValueError:
        return None
    return body if isinstance(body, dict) and "code" in body else None


class CcxtRestClient:
    def __init__(self, *, api_key: str | None = None, secret: str | None = None, recv_window_ms: int = 5000,
                 rate_limits: RateLimitCounter | None = None, clock_ms: Callable[[], int] = _wall_ms,
                 timeout_ms: int = 10_000, exchange: Any = None):
        config: Any = {
            "apiKey": api_key, "secret": secret, "enableRateLimit": True, "timeout": timeout_ms,
            "options": {"recvWindow": recv_window_ms, "adjustForTimeDifference": False, "fetchCurrencies": False},
        }
        self.ex: Any = exchange or ccxt.binanceusdm(config)
        self.rate_limits, self._clock = rate_limits, clock_ms
        self._last_status: int | None = None
        inner_on_rest_response = self.ex.on_rest_response

        def on_rest_response(code, reason, url, method, response_headers, response_body, request_headers, request_body):
            self._last_status = code
            return inner_on_rest_response(code, reason, url, method, response_headers, response_body,
                                          request_headers, request_body)
        self.ex.on_rest_response = on_rest_response

    # ── RestClient ──────────────────────────────────────────────────────────
    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        return self._request("GET", path, params, signed)

    def post(self, path: str, params: dict | None = None, *, signed: bool = True) -> Response:
        if path == ORDER_PATH:
            return self._market_order(dict(params or {}))
        return self._request("POST", path, params, signed)

    def sync_time(self) -> int:
        """ccxt의 서버 시각 오프셋을 갱신한다(`GET /fapi/v1/time`). 이후 서명 요청의 timestamp에 반영된다."""
        self._call("GET", "/fapi/v1/time", lambda: self.ex.load_time_difference())
        return int(self.ex.options["timeDifference"])

    # ── 내부 ────────────────────────────────────────────────────────────────
    def _request(self, method: str, path: str, params: dict | None, signed: bool) -> Response:
        api, sub = _split(path, signed)
        p = {k: v for k, v in (params or {}).items()}
        data = self._call(method, path, lambda: self.ex.request(sub, api, method, p))
        return Response(self._last_status or 200, data, self._headers())

    def _market_order(self, params: dict[str, Any]) -> Response:
        validate_order_params(params)
        if "reduceOnly" in params and params["reduceOnly"] != "true":
            raise OrderParamError(f"reduceOnly={params['reduceOnly']!r}")
        market = self._market(params["symbol"])
        qty = params["quantity"]
        ccxt_qty = self.ex.amount_to_precision(market["symbol"], qty)
        #  값 비교(표기만 다른 "0.010"↔"0.01"은 같은 수량) — 값이 바뀌면 전송하지 않는다
        if Decimal(str(ccxt_qty)) != Decimal(qty):
            raise OrderParamError(f"ccxt 정밀도가 수량을 바꾼다 {qty} → {ccxt_qty} — 우리 정규화가 권위, 전송하지 않는다")
        extra: dict[str, Any] = {
            "newClientOrderId": params.get("newClientOrderId") or CLIENT_ORDER_ID_PREFIX + uuid.uuid4().hex[:24],
            "newOrderRespType": params.get("newOrderRespType", "RESULT"),
        }
        if params.get("reduceOnly") == "true":
            extra["reduceOnly"] = True
        if "positionSide" in params:
            extra["positionSide"] = params["positionSide"]
        order = self._call("POST", ORDER_PATH, lambda: self.ex.create_order(
            market["symbol"], "market", params["side"].lower(), qty, None, extra))
        info = order.get("info") if isinstance(order, dict) else None
        if not isinstance(info, dict):
            raise TransportError(f"POST {ORDER_PATH}: 원시 응답(info)이 없다 — 체결 여부 불명: {order!r}")
        return Response(self._last_status or 200, info, self._headers())

    def _market(self, symbol_id: str) -> dict:
        if not self.ex.markets:
            self._call("GET", "/fapi/v1/exchangeInfo", lambda: self.ex.load_markets())
        hits = [m for m in (self.ex.markets_by_id or {}).get(symbol_id, []) if m.get("swap") and m.get("linear")]
        if len(hits) != 1:
            raise OrderParamError(f"{symbol_id}: USDⓈ-M 무기한 마켓 {len(hits)}개")
        return hits[0]

    def _headers(self) -> dict[str, str]:
        h = dict(self.ex.last_response_headers or {})
        if self.rate_limits is not None and h:
            self.rate_limits.observe_headers(h, self._clock())
        return h

    def _call(self, method: str, path: str, fn: Callable[[], Any]) -> Any:
        self._last_status = None
        try:
            return fn()
        except ccxt.BaseError as e:
            status = self._last_status
            self._headers()
            body = _binance_body(str(e))
            if (status is not None and status >= 500) or (body is None and isinstance(e, ccxt.NetworkError)):
                raise TransportError(f"{method} {path}: {type(e).__name__}: {e} — 거래소 도달·처리 여부 불명") from e
            if body is None:
                raise BinanceAPIError(status or 0, None, f"{type(e).__name__}: {e}", path) from e
            code = int(body["code"])
            if code == TIMESTAMP_ERROR:
                try:
                    self.ex.load_time_difference()
                except ccxt.BaseError:
                    pass
            raise BinanceAPIError(status or 0, code, str(body.get("msg")), path) from e
