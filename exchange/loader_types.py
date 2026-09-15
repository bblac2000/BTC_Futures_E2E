from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EndpointSpec:
    path: str
    signed: bool
    per_symbol: bool


@dataclass(frozen=True)
class RawFetch:
    endpoint: str
    path: str
    symbol: str
    fetched_at_utc: str
    payload: Any
