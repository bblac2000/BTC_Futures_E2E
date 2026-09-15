"""layer 5 REST 백필 — `GET /fapi/v1/klines`·`/fapi/v1/markPriceKlines` 원시 배열 → Decimal 봉(ccxt 전송 · `RestClient`).

- **닫힌 봉만**(closeTime < now) — 형성 중인 봉은 WS가 준다
- 페이지 크기는 호출자가 준다(거래소 최대값을 여기서 추측하지 않는다) · 응답이 요청보다 많거나 시각이 역행/정체하면 멈춘다
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from data.backfill import BackfillError, Bar, fetch_closed_klines, fetch_closed_mark_klines
from exchange.client_types import Response
from paper.types import MarkBar

M = 60_000
T0 = 1_789_430_400_000


def kl(t: int, c: str = "60000.5") -> list:
    return [t, "60000.1", "60010.0", "59990.0", c, "1.234", t + M - 1, "74000.1", 42, "0.6", "36000.2", "0"]


def mkl(t: int) -> list:
    return [t, "60000.1", "60010.0", "59990.0", "60001.0", "0", t + M - 1, "0", 0, "0", "0", "0"]


class FakeRest:
    def __init__(self, rows_by_path, page_override=None):
        self.rows, self.calls, self.page_override = rows_by_path, [], page_override

    def get(self, path, params=None, *, signed=False):
        params = dict(params or {})
        self.calls.append((path, params, signed))
        rows = [r for r in self.rows[path] if params["startTime"] <= r[0] <= params["endTime"]]
        n = self.page_override or params["limit"]
        return Response(200, rows[:n], {})

    def post(self, *a, **k):
        raise AssertionError("백필은 POST하지 않는다")


def test_pages_through_and_returns_only_closed_bars_as_decimals():
    rows = [kl(T0 + i * M) for i in range(7)]
    c = FakeRest({"/fapi/v1/klines": rows})
    now = T0 + 6 * M + 30_000                                    # 7번째 봉은 형성 중
    bars = fetch_closed_klines(c, "BTCUSDT", start_ms=T0, end_ms=T0 + 10 * M, page_limit=3, now_ms=now)
    assert [b.open_ms for b in bars] == [T0 + i * M for i in range(6)]
    assert all(isinstance(b, Bar) and isinstance(b.close, Decimal) for b in bars)
    assert bars[0].close == Decimal("60000.5") and bars[0].trades == 42 and bars[0].taker_buy_quote == Decimal("36000.2")
    #  다음 페이지는 마지막 openTime + 1ms부터(startTime은 포함 조건)
    assert [call[1]["startTime"] for call in c.calls] == [T0, T0 + 2 * M + 1, T0 + 5 * M + 1]
    assert all(call[1]["interval"] == "1m" and call[1]["symbol"] == "BTCUSDT" and call[1]["limit"] == 3 and not call[2]
               for call in c.calls)


def test_mark_klines_become_engine_mark_bars():
    c = FakeRest({"/fapi/v1/markPriceKlines": [mkl(T0), mkl(T0 + M)]})
    bars = fetch_closed_mark_klines(c, "BTCUSDT", start_ms=T0, end_ms=T0 + 2 * M, page_limit=500, now_ms=T0 + 5 * M)
    assert bars == [MarkBar(T0, T0 + M - 1, Decimal("60000.1"), Decimal("60010.0"), Decimal("59990.0"), Decimal("60001.0")),
                    MarkBar(T0 + M, T0 + 2 * M - 1, Decimal("60000.1"), Decimal("60010.0"), Decimal("59990.0"), Decimal("60001.0"))]


@pytest.mark.parametrize("rows, override", [
    ([kl(T0), kl(T0)], None),                                  # 시각 정체
    ([kl(T0 + M), kl(T0)], None),                              # 역행
    ([kl(T0 + i * M) for i in range(5)], 5),                   # 요청(3)보다 많은 응답
    ([[T0, "1", "2"]], None),                                  # 모양 오류
    ([kl(T0, c="x")], None),                                   # 숫자 아님
])
def test_malformed_pages_fail_closed(rows, override):
    c = FakeRest({"/fapi/v1/klines": rows}, page_override=override)
    with pytest.raises(BackfillError):
        fetch_closed_klines(c, "BTCUSDT", start_ms=T0, end_ms=T0 + 10 * M, page_limit=3, now_ms=T0 + 20 * M)


@pytest.mark.parametrize("kw", [{"page_limit": 0}, {"start_ms": T0 + M, "end_ms": T0}])
def test_bad_arguments(kw):
    args = {"start_ms": T0, "end_ms": T0 + M, "page_limit": 3, "now_ms": T0 + 5 * M} | kw
    with pytest.raises(ValueError):
        fetch_closed_klines(FakeRest({"/fapi/v1/klines": []}), "BTCUSDT", **args)
