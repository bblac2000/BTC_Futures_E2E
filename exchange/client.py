"""Binance USDⓈ-M REST 클라이언트 — 서명 · 에러 원문 보존 · rate-limit 헤더 · 시계 오프셋.

🔴 이 저장소는 결국 라이브로 간다. 그래서 **계정 변경(POST) 경로의 문을 둘로** 둔다:
   ① PAPER는 `ReadOnlyClient`로 감싸 POST 자체를 예외로 만든다(이 모듈).
   ② 주문 전송은 layer 3에서 LIVE 모드 + 라이브 체크리스트 통과 시에만 연결된다.
이 모듈 자체는 주문 엔드포인트를 알지 못한다 — 경로 문자열은 호출자가 준다.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from exchange.client_types import Response, RestClient
from exchange.errors import BinanceAPIError, CredentialsMissing, ReadOnlyViolation, TransportError
from exchange.ratelimit import RateLimitCounter
from exchange.timesync import TimeSync

__all__ = ["BASE_URL", "BinanceRestClient", "ReadOnlyClient", "Response", "RestClient", "sign"]

BASE_URL = "https://fapi.binance.com"
TIMESTAMP_ERROR = -1021


def sign(secret: str, query: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def _wall_ms() -> int:
    return int(time.time() * 1000)


class BinanceRestClient:
    def __init__(self, base_url: str = BASE_URL, api_key: str | None = None, api_secret: str | None = None, *,
                 recv_window_ms: int = 5000, time_sync: TimeSync | None = None,
                 rate_limits: RateLimitCounter | None = None,
                 opener: Callable[..., Any] = urllib.request.urlopen,
                 clock_ms: Callable[[], int] = _wall_ms, timeout_s: float = 10.0):
        self.base_url, self._key, self._secret = base_url.rstrip("/"), api_key, api_secret
        self.recv_window_ms, self.time_sync, self.rate_limits = recv_window_ms, time_sync, rate_limits
        self._open, self._clock, self.timeout_s = opener, clock_ms, timeout_s

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        return self._request("GET", path, params, signed)

    def post(self, path: str, params: dict | None = None, *, signed: bool = True) -> Response:
        return self._request("POST", path, params, signed)

    def _request(self, method: str, path: str, params: dict | None, signed: bool) -> Response:
        items = [(k, str(v)) for k, v in (params or {}).items()]
        headers = {}
        if signed:
            if not (self._key and self._secret):
                raise CredentialsMissing(f"{method} {path}: 서명 요청인데 API 키/시크릿이 없다")
            now = self._clock()
            ts = self.time_sync.server_now_ms(now) if (self.time_sync and self.time_sync.offset_ms is not None) else now
            items += [("recvWindow", str(self.recv_window_ms)), ("timestamp", str(ts))]
            q = urllib.parse.urlencode(items)
            q = f"{q}&signature={sign(self._secret, q)}"
            headers["X-MBX-APIKEY"] = self._key
        else:
            q = urllib.parse.urlencode(items)
        url = f"{self.base_url}{path}" + (f"?{q}" if q else "")
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with self._open(req, timeout=self.timeout_s) as r:
                hdrs = dict(r.headers.items())
                status = int(getattr(r, "status", 200))
                body = r.read().decode()
        except urllib.error.HTTPError as e:
            hdrs = dict(e.headers.items()) if e.headers else {}
            self._observe(hdrs)
            raw = e.read().decode() if e.fp else ""
            try:
                j = json.loads(raw)
                code, msg = j.get("code"), str(j.get("msg"))
            except (ValueError, AttributeError):
                code, msg = None, raw[:500]
            if code == TIMESTAMP_ERROR and self.time_sync is not None:
                self.time_sync.invalidate()
            raise BinanceAPIError(e.code, code, msg, path) from e
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            #  🔴 Codex 재검토 F3 — HTTP 응답 없이 끊겼다 = 처리 여부 불명. 이름 있는 예외로 올린다.
            raise TransportError(f"{method} {path}: {type(e).__name__}: {e} — 거래소 도달·처리 여부 불명") from e
        self._observe(hdrs)
        return Response(status, json.loads(body) if body else None, hdrs)

    def _observe(self, hdrs: dict[str, str]) -> None:
        if self.rate_limits is not None:
            self.rate_limits.observe_headers(hdrs, self._clock())


class ReadOnlyClient:
    """PAPER용 — GET만 통과. POST는 **네트워크에 닿기 전에** 예외(exchange-rules §4 "PAPER는 계정 SET 금지")."""

    def __init__(self, inner: RestClient):
        self._inner = inner

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        return self._inner.get(path, params, signed=signed)

    def post(self, path: str, params: dict | None = None, *, signed: bool = True) -> Response:
        raise ReadOnlyViolation(f"PAPER 읽기 전용 클라이언트: POST {path} 거부")
