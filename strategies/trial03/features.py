"""트라이얼 #3 순수 계산기(단계 2 (d) · 계획 r2 D9 · 사전등록 §1 23~29행) — 인과적(결정 시각까지의 값만) · 전략 상태와 분리.

- r30: float64(`math.log`) · 두 종가 모두 유한 양수여야 정의.
- `QuantileBook`: 날(day_index)별 정의된 r30 · 날 d의 분위수 = d−90 … d−1 날의 정의된 값 전부(`numpy.quantile(..., method="linear")`) ·
  정의 수 < 128,304 → None(그날 `quantile_invalid`).
- `OiIndex`: §1 25행 — 행(create_time c)은 c + 5분부터 · 기준 시각에서 나이 ≤ 10분인 **가장 최근 유효 행** · 없으면 결측
  (사용 불가 슬롯이 그 나이 창 안에 있으면 부사유 `unusable`, 아니면 `absent` · 창 밖으로 더 찾지 않는다) · 감소 = now − prev < 0(Decimal).
- `rv5`: t−5 … t mark 종가 6개 → 로그수익률 5개의 표본표준편차(ddof 1 · `statistics.stdev`).
- `AtrBuckets`: UTC 15분 버킷 [b, b+15분) · H = mark_high 최대 · L = mark_low 최소 · C = 마지막 분 mark_close · 완전 = 1m 봉 15개 ·
  ATR(T) = 끝 경계 ≤ T인 마지막 연속 완전 버킷 15개의 TR 14개 단순평균(Decimal) · 조건 불충족 → None.
"""
from __future__ import annotations

import bisect
import math
import statistics
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np

from backtest.data import Bar1m
from strategies.trial03.config import TF_V1, TfParams


def _pos_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(Decimal(str(v)))
    except (InvalidOperation, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def r30(close_now: Any, close_prev: Any) -> float | None:
    a, b = _pos_float(close_now), _pos_float(close_prev)
    return None if a is None or b is None else math.log(a / b)


class QuantileBook:
    def __init__(self, p: TfParams = TF_V1):
        self.p = p
        self.days: dict[int, list[float]] = {}

    def add(self, day: int, value: float | None) -> None:
        lst = self.days.setdefault(day, [])
        if value is not None:
            lst.append(value)

    def prune(self, keep_from_day: int) -> None:
        for d in [d for d in self.days if d < keep_from_day]:
            del self.days[d]

    def quantiles(self, day: int) -> tuple[float, float] | None:
        parts = [self.days.get(d, []) for d in range(day - self.p.w_ref_days, day)]
        n = sum(len(x) for x in parts)
        if n < self.p.quantile_min_defined:
            return None
        arr = np.fromiter((v for x in parts for v in x), dtype=np.float64, count=n)
        lo, hi = np.quantile(arr, [self.p.q_lo, self.p.q_hi], method="linear")
        return float(lo), float(hi)


class OiIndex:
    def __init__(self, rows: Sequence[Sequence[Any]], unusable: Sequence[int], p: TfParams = TF_V1):
        self.p = p
        srt = sorted((int(c), Decimal(str(v))) for c, v in rows)
        self.cs = [c for c, _ in srt]
        self.vs = [v for _, v in srt]
        self.bad = sorted(int(c) for c in unusable)

    def lookup(self, t_ref: int) -> tuple[str, Any]:
        avail, age = self.p.oi_avail_ms, self.p.oi_age_ms
        i = bisect.bisect_right(self.cs, t_ref - avail) - 1
        if i >= 0 and t_ref - (self.cs[i] + avail) <= age:
            return "ok", self.vs[i]
        lo = bisect.bisect_left(self.bad, t_ref - avail - age)
        hi = bisect.bisect_right(self.bad, t_ref - avail)
        return "missing", ("unusable" if hi > lo else "absent")

    def status(self, t: int) -> tuple[str, str | None]:
        now, prev = self.lookup(t), self.lookup(t - self.p.oi_lookback_ms)
        miss = [x[1] for x in (now, prev) if x[0] == "missing"]
        if miss:
            return "missing", ("unusable" if "unusable" in miss else "absent")
        return ("ok", None) if now[1] - prev[1] < 0 else ("not_decreasing", None)


def rv5(closes: Sequence[Any]) -> float | None:
    """closes = t−5 … t mark 종가 6개(오름차순)."""
    if len(closes) != 6:
        return None
    xs = [_pos_float(c) for c in closes]
    if any(x is None for x in xs):
        return None
    fx = [x for x in xs if x is not None]
    return statistics.stdev([math.log(fx[i + 1] / fx[i]) for i in range(5)])


class AtrBuckets:
    def __init__(self, p: TfParams = TF_V1, keep: int = 64):
        self.p, self.keep = p, keep
        self.b: dict[int, list[Any]] = {}                  # 시작 → [H, L, 마지막 분 ms, C, 봉 수]

    def add(self, bar: Bar1m) -> None:
        w = self.p.atr_bucket_ms
        s = bar.open_ms - bar.open_ms % w
        h, lo, c = bar.d("mark_high"), bar.d("mark_low"), bar.d("mark_close")
        x = self.b.get(s)
        if x is None:
            self.b[s] = [h, lo, bar.open_ms, c, 1]
            if len(self.b) > self.keep:
                del self.b[min(self.b)]
            return
        x[0], x[1] = max(x[0], h), min(x[1], lo)
        if bar.open_ms > x[2]:
            x[2], x[3] = bar.open_ms, c
        x[4] += 1

    def atr(self, t: int) -> Decimal | None:
        w, n = self.p.atr_bucket_ms, self.p.atr_n
        end = t - t % w                                    # 끝 경계 ≤ T인 마지막 버킷의 끝
        starts = [end - w * j for j in range(n + 1, 0, -1)]
        bs = [self.b.get(s) for s in starts]
        full = w // 60_000
        if any(x is None or x[4] != full for x in bs):
            return None
        trs = []
        for i in range(1, n + 1):
            h, lo, c_prev = bs[i][0], bs[i][1], bs[i - 1][3]   # type: ignore[index]
            trs.append(max(h - lo, abs(h - c_prev), abs(lo - c_prev)))
        return sum(trs, Decimal(0)) / Decimal(n)
