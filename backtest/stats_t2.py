"""트라이얼 #2 판정 통계(단계 2g H1·H4 · 사전등록 §3-1) — 순수 함수. `backtest.stats`의 달력일 블록 함수는 쓰지 않는다.

- 유효일 블록 부트스트랩: 블록 = **주어진 날 목록 그대로**(거래 없는 유효일은 빈 블록 · 무효일은 목록에 없다 — 0으로 채우지 않는다) ·
  통계 = 재표본 블록 합 / 재표본 거래 수 · 거래 0건 재표본은 빼고 센다 · CI = numpy 선형 분위수 (1−level)/2, 1−(1−level)/2.
- 일별 대비: 날 목록 위 (B_day − A_day)의 평균 · 같은 재표본 날짜.
- ρ̂: (x[:-1], x[1:])의 피어슨 상관 · n < 3 · 어느 조각 분산 0 · 유한하지 않음 → 0(§3-1 퇴화 규칙 · G0는 max(ρ̂, 0.15)).
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DayCI:
    mean: float
    lo: float
    hi: float
    level: float
    resamples: int
    degenerate: int                      # 거래 0건 재표본 수
    n_blocks: int

    @property
    def defined(self) -> bool:
        return math.isfinite(self.lo) and math.isfinite(self.hi)


def _q(vals: np.ndarray, level: float) -> tuple[float, float]:
    if len(vals) == 0:
        return float("nan"), float("nan")
    a = (1 - level) / 2
    return float(np.quantile(vals, a)), float(np.quantile(vals, 1 - a))


def valid_day_bootstrap_mean(by_day: Mapping[int, Sequence[float]], days: Sequence[int], rng: np.random.Generator, *,
                             resamples: int, level: float) -> DayCI:
    dset = set(days)
    extra = [d for d, xs in by_day.items() if xs and d not in dset]
    if extra:
        raise ValueError(f"유효일 목록 밖 날의 거래: {sorted(extra)[:5]}")
    order = list(days)
    if not order:
        return DayCI(float("nan"), float("nan"), float("nan"), level, resamples, resamples, 0)
    sums = np.array([float(sum(by_day.get(d, ()))) for d in order])
    cnts = np.array([float(len(by_day.get(d, ()))) for d in order])
    idx = rng.integers(0, len(order), size=(resamples, len(order)))
    s, c = sums[idx].sum(axis=1), cnts[idx].sum(axis=1)
    ok = c > 0
    lo, hi = _q(s[ok] / c[ok], level)
    n = cnts.sum()
    mean = float(sums.sum() / n) if n > 0 else float("nan")
    return DayCI(mean, lo, hi, level, resamples, int((~ok).sum()), len(order))


def daily_diff_bootstrap(a_day: Mapping[int, float], b_day: Mapping[int, float], days: Sequence[int], rng: np.random.Generator,
                         *, resamples: int, level: float) -> DayCI:
    order = list(days)
    if not order:
        return DayCI(float("nan"), float("nan"), float("nan"), level, resamples, 0, 0)
    d = np.array([float(b_day.get(x, 0.0)) - float(a_day.get(x, 0.0)) for x in order])
    idx = rng.integers(0, len(order), size=(resamples, len(order)))
    lo, hi = _q(d[idx].mean(axis=1), level)
    return DayCI(float(d.mean()) if len(d) else float("nan"), lo, hi, level, resamples, 0, len(order))


def lag1_rho(x: Sequence[float]) -> float:
    a = np.asarray(x, dtype=float)
    if len(a) < 3 or not np.all(np.isfinite(a)):
        return 0.0
    u, v = a[:-1], a[1:]
    if u.std() == 0 or v.std() == 0:
        return 0.0
    r = float(np.corrcoef(u, v)[0, 1])
    return r if math.isfinite(r) else 0.0


def sharpe_or_none(x: Sequence[float]) -> float | None:
    """mean / std(ddof=1) · n < 2 또는 분산 0 → 정의되지 않음(None)."""
    a = np.asarray(x, dtype=float)
    if len(a) < 2:
        return None
    sd = float(a.std(ddof=1))
    if sd == 0 or not math.isfinite(sd):
        return None
    return float(a.mean() / sd)


def p95(values: Sequence[float]) -> float:
    """§3-1: P1·P4 p95 = numpy 선형 분위수 0.95(트라이얼 #1 p1_core.p95와 같은 식)."""
    return float(np.quantile(np.asarray(values, dtype=float), 0.95))
