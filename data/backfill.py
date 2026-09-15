"""layer 5 REST 백필 — 원시 kline 배열 → Decimal 봉. 전송은 `RestClient`(운영에서는 `exchange.ccxt_rest.CcxtRestClient`).

- **닫힌 봉만** 돌려준다(`closeTime < now_ms`). 형성 중인 봉은 WS 피드의 몫.
- 페이지 크기(`page_limit`)는 **호출자가 준다** — 거래소 최대값을 여기서 추측하지 않는다(값은 config·문서 확인 후).
- fail-closed: 응답이 요청보다 많음 · openTime 역행/정체 · 모양·숫자 오류 → `BackfillError`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from exchange.client_types import RestClient
from paper.types import MarkBar

KLINES = "/fapi/v1/klines"
MARK_KLINES = "/fapi/v1/markPriceKlines"
INTERVAL = "1m"


class BackfillError(ValueError):
    pass


@dataclass(frozen=True)
class Bar:
    open_ms: int
    close_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int
    taker_buy_base: Decimal
    taker_buy_quote: Decimal


def _d(row: list, i: int) -> Decimal:
    try:
        v = Decimal(str(row[i]))
    except (IndexError, InvalidOperation, TypeError) as e:
        raise BackfillError(f"열 {i}: {row!r}") from e
    if not v.is_finite():
        raise BackfillError(f"열 {i} 유한수 아님: {row!r}")
    return v


def _i(row: list, i: int) -> int:
    try:
        v = row[i]
    except IndexError as e:
        raise BackfillError(f"열 {i}: {row!r}") from e
    if isinstance(v, bool) or not isinstance(v, int):
        raise BackfillError(f"열 {i} 정수 아님: {row!r}")
    return v


def _pages(client: RestClient, path: str, symbol_id: str, start_ms: int, end_ms: int, page_limit: int) -> list[list]:
    if page_limit <= 0 or end_ms < start_ms:
        raise ValueError(f"page_limit={page_limit} start={start_ms} end={end_ms}")
    out: list[list] = []
    cursor = start_ms
    last_open: int | None = None
    while cursor <= end_ms:
        data: Any = client.get(path, {"symbol": symbol_id, "interval": INTERVAL, "startTime": cursor,
                                      "endTime": end_ms, "limit": page_limit}).data
        if not isinstance(data, list):
            raise BackfillError(f"{path}: 리스트가 아니다 {type(data).__name__}")
        if len(data) > page_limit:
            raise BackfillError(f"{path}: 요청 {page_limit}행보다 많은 {len(data)}행")
        for row in data:
            if not isinstance(row, list):
                raise BackfillError(f"{path}: 행이 리스트가 아니다 {row!r}")
            t = _i(row, 0)
            if last_open is not None and t <= last_open:
                raise BackfillError(f"{path}: openTime 역행/정체 {last_open} → {t}")
            last_open = t
            out.append(row)
        if len(data) < page_limit or last_open is None:
            break
        cursor = last_open + 1
    return out


def fetch_closed_klines(client: RestClient, symbol_id: str, *, start_ms: int, end_ms: int, page_limit: int,
                        now_ms: int) -> list[Bar]:
    bars = []
    for r in _pages(client, KLINES, symbol_id, start_ms, end_ms, page_limit):
        if len(r) < 11:
            raise BackfillError(f"kline 열 부족: {r!r}")
        b = Bar(_i(r, 0), _i(r, 6), _d(r, 1), _d(r, 2), _d(r, 3), _d(r, 4), _d(r, 5), _d(r, 7), _i(r, 8),
                _d(r, 9), _d(r, 10))
        if b.close_ms < now_ms:
            bars.append(b)
    return bars


def fetch_closed_mark_klines(client: RestClient, symbol_id: str, *, start_ms: int, end_ms: int, page_limit: int,
                             now_ms: int) -> list[MarkBar]:
    bars = []
    for r in _pages(client, MARK_KLINES, symbol_id, start_ms, end_ms, page_limit):
        if len(r) < 7:
            raise BackfillError(f"markPriceKline 열 부족: {r!r}")
        b = MarkBar(_i(r, 0), _i(r, 6), _d(r, 1), _d(r, 2), _d(r, 3), _d(r, 4))
        if b.close_ms < now_ms:
            bars.append(b)
    return bars
