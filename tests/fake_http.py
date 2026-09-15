"""ccxt 동기 클라이언트용 가짜 HTTP 세션 — `ex.session.request`를 대체해 **ccxt의 서명·오류 처리 코드를 그대로** 통과시킨다.

라우트 함수는 (method, path, params) → (status, json_body) 또는 예외(`requests` 예외 = 전송 실패 흉내).
"""
from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class FakeResponse:
    status_code: int
    body: Any
    headers: dict[str, str]
    reason: str = "OK"

    @property
    def text(self) -> str:
        return self.body if isinstance(self.body, str) else json.dumps(self.body)

    @property
    def content(self) -> bytes:
        return self.text.encode()

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=None)  # type: ignore[arg-type]


@dataclass
class Sent:
    method: str
    url: str
    path: str
    query: dict[str, list[str]]
    body: dict[str, list[str]]
    headers: dict[str, str]

    def all_params(self) -> dict[str, str]:
        merged = {**{k: v[-1] for k, v in self.query.items()}, **{k: v[-1] for k, v in self.body.items()}}
        return merged

    def count(self, key: str) -> int:
        return len(self.query.get(key, [])) + len(self.body.get(key, []))


Route = Callable[[str, str, dict[str, str]], tuple[int, Any]]


@dataclass
class FakeHttp:
    route: Route
    headers: dict[str, str] = field(default_factory=lambda: {"X-MBX-USED-WEIGHT-1M": "11"})
    sent: list[Sent] = field(default_factory=list)

    def request(self, method, url, data=None, headers=None, **kw) -> FakeResponse:
        u = urllib.parse.urlsplit(url)
        body = data.decode() if isinstance(data, bytes) else (data or "")
        s = Sent(method, url, u.path, urllib.parse.parse_qs(u.query), urllib.parse.parse_qs(body), dict(headers or {}))
        self.sent.append(s)
        status, payload = self.route(method, u.path, s.all_params())
        return FakeResponse(status, payload, dict(self.headers), reason="OK" if status < 400 else "ERR")
