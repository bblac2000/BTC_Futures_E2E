"""트라이얼 #4 순수 계산기((d) · 규약 C28·C30 · 사전등록 r3 §1) — 인과적(결정 시각까지의 값만) · 전략 상태와 분리.

- `DailyAtr`: UTC 날별 H = mark 고가 최대 · L = mark 저가 최소 · C = 23:59 봉 mark 종가 · 완전 = 1m 봉 1,440개(유한 양수) ·
  ATR(d) = d − 14 … d − 1의 TR 14개 단순평균(Decimal) · TR_i = max(H − L, |H − C_{i−1}|, |L − C_{i−1}|) ·
  14일 중 하나라도 불완전 → (None, "days") · d − 15의 23:59 종가가 없거나 유한 양수가 아님 → (None, "prev_close")(H − L로 대신하지 않는다).
- `TrailingPrints`: 마지막 유효 인쇄 270개(float) · 분위수 = `numpy.quantile(method="linear")` · 270개 미만 → None.
"""
from __future__ import annotations

from collections import deque
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np

from backtest.data import MINUTE_MS, Bar1m
from strategies.trial04.config import TC_V3, TcParams

DAY = 86_400_000
LAST_MINUTE = DAY - MINUTE_MS


def _pos_dec(v: Any) -> Decimal | None:
    try:
        x = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return x if x.is_finite() and x > 0 else None


class DailyAtr:
    def __init__(self, p: TcParams = TC_V3, keep: int = 40):
        self.p, self.keep = p, keep
        self.d: dict[int, list[Any]] = {}                  # 날 → [H, L, 23:59 종가(없으면 None), 유효 봉 수, 불량]

    def add(self, bar: Bar1m) -> None:
        day = bar.open_ms // DAY
        x = self.d.get(day)
        if x is None:
            x = self.d[day] = [None, None, None, 0, False]
            for old in [k for k in self.d if k < day - self.keep]:
                del self.d[old]
        h, lo, c = _pos_dec(bar.mark_high), _pos_dec(bar.mark_low), _pos_dec(bar.mark_close)
        if bar.open_ms % MINUTE_MS or h is None or lo is None or c is None or _pos_dec(bar.mark_open) is None:
            x[4] = True
            return
        x[0] = h if x[0] is None else max(x[0], h)
        x[1] = lo if x[1] is None else min(x[1], lo)
        if bar.open_ms % DAY == LAST_MINUTE:
            x[2] = c
        x[3] += 1

    def atr(self, day: int) -> tuple[Decimal | None, str | None]:
        n = self.p.atr_n
        days = [self.d.get(i) for i in range(day - n, day)]
        if any(x is None or x[4] or x[3] != 1440 for x in days):
            return None, "days"
        prev = self.d.get(day - n - 1)
        c_prev = None if prev is None else prev[2]
        if c_prev is None:
            return None, "prev_close"
        trs = []
        for x in days:
            h, lo = x[0], x[1]                              # type: ignore[index]
            trs.append(max(h - lo, abs(h - c_prev), abs(lo - c_prev)))
            c_prev = x[2]                                   # type: ignore[index]
        return sum(trs, Decimal(0)) / Decimal(n), None


class TrailingPrints:
    def __init__(self, p: TcParams = TC_V3):
        self.p = p
        self.v: deque[float] = deque(maxlen=p.n_trail)

    def __len__(self) -> int:
        return len(self.v)

    def add(self, value: float) -> None:
        self.v.append(value)

    def quantiles(self) -> tuple[float, float] | None:
        if len(self.v) < self.p.n_trail:
            return None
        lo, hi = np.quantile(np.fromiter(self.v, dtype=np.float64, count=len(self.v)), [self.p.q_lo, self.p.q_hi], method="linear")
        return float(lo), float(hi)
