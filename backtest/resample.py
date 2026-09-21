"""1m → k분 봉(15m·4h) — UTC 격자 정렬 · **마감된 봉만** 낸다(단계 2a).

- 버킷 = `open_ms // (k·60s) · (k·60s)`. 마감 시각 `close_ms = 버킷 시작 + k분 − 1ms`.
- 버킷은 **다음 버킷의 첫 분이 나타났거나 입력이 버킷 끝을 지났을 때만** 낸다(진행 중인 버킷을 내면 룩어헤드).
- OHLC는 있는 분만으로 계산하고 `n_minutes`로 구성 분 수를 남긴다(결손 분이 있는 버킷을 조용히 완전한 봉으로 보지 않게).
- 가격 열은 kline last(레벨·ATR·VP 계산용)와 mark(보고용) 둘 다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backtest.data import MINUTE_MS, Bar1m


@dataclass(frozen=True)
class BarK:
    open_ms: int
    close_ms: int
    minutes: int                  # k
    n_minutes: int                # 실제 구성 분 수(k면 완전)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    mark_open: Decimal
    mark_high: Decimal
    mark_low: Decimal
    mark_close: Decimal

    @property
    def complete(self) -> bool:
        return self.n_minutes == self.minutes


def _build(group: list[Bar1m], start: int, k: int) -> BarK:
    return BarK(start, start + k * MINUTE_MS - 1, k, len(group), group[0].d("open"), max(b.d("high") for b in group),
                min(b.d("low") for b in group), group[-1].d("close"), sum((b.d("volume") for b in group), Decimal()),
                sum((b.d("quote_volume") for b in group), Decimal()), group[0].d("mark_open"),
                max(b.d("mark_high") for b in group), min(b.d("mark_low") for b in group), group[-1].d("mark_close"))


def resample(bars: list[Bar1m], k: int, *, until_ms: int | None = None) -> list[BarK]:
    """정렬된 1m 봉 → k분 봉. `until_ms`(포함)까지 마감된 버킷만. 없으면 마지막 입력 분까지."""
    if k <= 0:
        raise ValueError("k > 0")
    span = k * MINUTE_MS
    last_seen = bars[-1].open_ms if bars else None
    limit = until_ms if until_ms is not None else (last_seen + MINUTE_MS - 1 if last_seen is not None else -1)
    out: list[BarK] = []
    cur: list[Bar1m] = []
    cur_start: int | None = None
    for b in bars:
        s = b.open_ms // span * span
        if cur_start is not None and s != cur_start:
            out.append(_build(cur, cur_start, k))
            cur = []
        cur_start = s
        cur.append(b)
    if cur and cur_start is not None and cur_start + span - 1 <= limit:
        out.append(_build(cur, cur_start, k))
    return [x for x in out if x.close_ms <= limit]
