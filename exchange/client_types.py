"""REST 응답·클라이언트 프로토콜 — 순환 import 없이 공유하기 위해 분리."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Response:
    status: int
    data: Any
    headers: dict[str, str] = field(default_factory=dict)


class RestClient(Protocol):
    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response: ...

    def post(self, path: str, params: dict | None = None, *, signed: bool = True) -> Response: ...
