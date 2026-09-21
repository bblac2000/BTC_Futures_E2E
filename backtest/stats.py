"""판정 통계(단계 2a) — 사전등록 §3·§7. 전부 순수 함수 · 시드 고정.

- **일 단위 블록 부트스트랩**: 블록 = UTC 달력일(거래 0건인 날도 빈 블록으로 유지) · 10,000 재표본 · **양측 97.5% CI**
  (Bonferroni α = 0.025와 같은 수준 → 하한 = 1.25 백분위). 짝지음(A−B)은 **같은 재표본 날짜**로 두 암을 함께 뽑는다.
- **PSR**(Bailey·López de Prado 2012): `Φ((SR̂ − SR*)·√(n−1) / √(1 − γ₃·SR̂ + (γ₄−1)/4·SR̂²))` · γ₄는 원 첨도(정규 = 3).
- **DSR**: `SR* = √V[SR̂] · ((1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)))`, γ = 오일러-마스케로니 · N = 2(암 수) ·
  V[SR̂] = 두 암 SR̂의 표본분산. 게이트 "DSR > 0"은 **SR̂ − SR* > 0**(수축 Sharpe가 양수)로 읽는다 — 확률형 DSR(=PSR(SR*))도 함께 보고.
- **MDE**(사후): `(z_{1−α} + z_{0.80}) · σ / √n_eff`, 단측 α = 0.025 · n_eff = n/(1+4ρ̂).
- **ρ̂**: 진입 시각 순 트레이드 순수익의 lag-1 자기상관.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

DAY_MS = 86_400_000
EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


@dataclass(frozen=True)
class CI:
    mean: float
    lo: float
    hi: float
    level: float
    resamples: int
    degenerate: int               # 재표본에 거래가 0건이라 통계가 정의되지 않은 횟수


def _day_index(ts_ms: int, start_ms: int) -> int:
    return (ts_ms - start_ms) // DAY_MS


def _blocks(trades: Sequence[tuple[int, float]], start_ms: int, end_ms: int) -> list[list[float]]:
    n_days = (end_ms - start_ms) // DAY_MS + 1
    days: list[list[float]] = [[] for _ in range(n_days)]
    for ts, x in trades:
        if not (start_ms <= ts <= end_ms):
            raise ValueError(f"거래 시각 {ts}가 창 밖")
        days[_day_index(ts, start_ms)].append(x)
    return days


def _quantiles(vals: np.ndarray, level: float) -> tuple[float, float]:
    a = (1 - level) / 2
    return float(np.quantile(vals, a)), float(np.quantile(vals, 1 - a))


def block_bootstrap_mean(trades: Sequence[tuple[int, float]], start_ms: int, end_ms: int, *, resamples: int, level: float,
                         rng: np.random.Generator) -> CI:
    """트레이드당 평균의 일 블록 부트스트랩 CI. 창 시작은 UTC 자정이어야 한다."""
    if dt.datetime.fromtimestamp(start_ms / 1000, dt.UTC).time() != dt.time(0):
        raise ValueError("블록은 UTC 달력일 — 창 시작이 자정이어야 한다")
    days = _blocks(trades, start_ms, end_ms)
    sums = np.array([sum(d) for d in days], dtype=float)
    counts = np.array([len(d) for d in days], dtype=float)
    idx = rng.integers(0, len(days), size=(resamples, len(days)))
    s, c = sums[idx].sum(axis=1), counts[idx].sum(axis=1)
    ok = c > 0
    stats = s[ok] / c[ok]
    lo, hi = _quantiles(stats, level)
    mean = float(sum(x for _t, x in trades) / len(trades)) if trades else float("nan")
    return CI(mean, lo, hi, level, resamples, int((~ok).sum()))


def paired_block_bootstrap_diff(a: Sequence[tuple[int, float]], b: Sequence[tuple[int, float]], start_ms: int, end_ms: int,
                                *, resamples: int, level: float, rng: np.random.Generator) -> CI:
    """mean(A) − mean(B) — **같은 재표본 날짜**로 두 암을 함께 뽑는다(짝지음)."""
    da, db = _blocks(a, start_ms, end_ms), _blocks(b, start_ms, end_ms)
    sa, ca = np.array([sum(d) for d in da]), np.array([len(d) for d in da], dtype=float)
    sb, cb = np.array([sum(d) for d in db]), np.array([len(d) for d in db], dtype=float)
    idx = rng.integers(0, len(da), size=(resamples, len(da)))
    na, nb = ca[idx].sum(axis=1), cb[idx].sum(axis=1)
    ok = (na > 0) & (nb > 0)
    stats = sa[idx].sum(axis=1)[ok] / na[ok] - sb[idx].sum(axis=1)[ok] / nb[ok]
    lo, hi = _quantiles(stats, level)
    mean = (sum(x for _t, x in a) / len(a) - sum(x for _t, x in b) / len(b)) if a and b else float("nan")
    return CI(float(mean), lo, hi, level, resamples, int((~ok).sum()))


def sharpe(returns: Sequence[float]) -> float:
    r = np.asarray(returns, dtype=float)
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if len(r) > 1 and sd > 0 else float("nan")


def _moments(returns: Sequence[float]) -> tuple[float, float]:
    r = np.asarray(returns, dtype=float)
    m, s = r.mean(), r.std(ddof=0)
    return float(((r - m) ** 3).mean() / s**3), float(((r - m) ** 4).mean() / s**4)     # 왜도, 원 첨도


def psr(returns: Sequence[float], sr_star: float) -> float:
    n = len(returns)
    sr = sharpe(returns)
    g3, g4 = _moments(returns)
    denom = 1 - g3 * sr + (g4 - 1) / 4 * sr**2
    if n < 2 or not math.isfinite(sr) or denom <= 0:
        return float("nan")
    return _N.cdf((sr - sr_star) * math.sqrt(n - 1) / math.sqrt(denom))


def expected_max_sr(sr_estimates: Sequence[float], n_trials: int) -> float:
    """`SR*` — N개 시도의 SR̂ 분산에서 기대 최대값(수축 기준)."""
    if n_trials < 2:
        raise ValueError("DSR은 N ≥ 2에서만 의미가 있다(프로토콜 §2)")
    v = float(np.var(np.asarray(sr_estimates, dtype=float), ddof=1))
    return math.sqrt(v) * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
                           + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e)))


def lag1_autocorr(x: Sequence[float]) -> float:
    a = np.asarray(x, dtype=float)
    if len(a) < 3 or a.std() == 0:
        return 0.0
    return float(np.corrcoef(a[:-1], a[1:])[0, 1])


def n_eff(n: int, rho: float) -> float:
    return n / (1 + 4 * rho)


def mde(sd: float, n_effective: float, *, alpha: float, power: float = 0.80) -> float:
    return (_N.inv_cdf(1 - alpha) + _N.inv_cdf(power)) * sd / math.sqrt(n_effective)
