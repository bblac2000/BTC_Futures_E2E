"""`backtest/stats_t2.py` — 유효일 블록 부트스트랩(H1) · 일별 대비(H1) · ρ̂ 퇴화 규칙(H4). 합성 값만."""
from __future__ import annotations

import numpy as np
import pytest

from backtest import stats_t2 as S


def rng(k: int = 0) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence((20260924, 1)).spawn(8)[k]))


def test_blocks_are_exactly_the_valid_days_and_invalid_days_are_absent():
    days = [10, 11, 13, 14]                                     # 12는 무효(목록에 없음)
    by_day = {10: [5.0], 11: [], 13: [-1.0, 3.0], 14: []}
    ci = S.valid_day_bootstrap_mean(by_day, days, rng(), resamples=2000, level=0.9875)
    assert ci.n_blocks == 4 and ci.mean == pytest.approx((5 - 1 + 3) / 3)
    with pytest.raises(ValueError):
        S.valid_day_bootstrap_mean({10: [1.0], 12: [2.0]}, days, rng(), resamples=10, level=0.9875)   # 무효일 트레이드


def test_bootstrap_reproduces_manual_resampling():
    days = [1, 2, 3, 4, 5]
    by_day = {1: [1.0, 2.0], 2: [], 3: [4.0], 4: [-2.0], 5: []}
    ci = S.valid_day_bootstrap_mean(by_day, days, rng(1), resamples=500, level=0.9875)
    g = rng(1)
    sums = np.array([3.0, 0.0, 4.0, -2.0, 0.0])
    cnts = np.array([2.0, 0.0, 1.0, 1.0, 0.0])
    idx = g.integers(0, 5, size=(500, 5))
    s, c = sums[idx].sum(axis=1), cnts[idx].sum(axis=1)
    ok = c > 0
    vals = s[ok] / c[ok]
    assert ci.lo == float(np.quantile(vals, 0.00625)) and ci.hi == float(np.quantile(vals, 0.99375))
    assert ci.degenerate == int((~ok).sum())


def test_all_resamples_empty_is_undefined():
    ci = S.valid_day_bootstrap_mean({1: [], 2: []}, [1, 2], rng(), resamples=10, level=0.9875)
    assert not ci.defined


def test_daily_diff_is_mean_of_day_differences_with_shared_indices():
    days = [1, 2, 3]
    a = {1: 10.0, 2: -5.0, 3: 0.0}
    b = {1: 10.0, 2: 0.0, 3: 0.0}                               # B 쉼(2) → 0
    ci = S.daily_diff_bootstrap(a, b, days, rng(4), resamples=300, level=0.9875)
    assert ci.mean == pytest.approx((0 + 5 + 0) / 3)
    g = rng(4)
    d = np.array([0.0, 5.0, 0.0])
    idx = g.integers(0, 3, size=(300, 3))
    vals = d[idx].mean(axis=1)
    assert ci.lo == float(np.quantile(vals, 0.00625)) and ci.hi == float(np.quantile(vals, 0.99375))


@pytest.mark.parametrize("x,expect", [([1.0, 2.0], 0.0), ([1.0, 1.0, 1.0, 1.0], 0.0),
                                      ([1.0, 1.0, 1.0, 5.0], 0.0),          # 앞 조각 분산 0 → 정의 안 됨 → 0
                                      ([1.0, float("nan"), 2.0, 3.0], 0.0)])
def test_rho_degenerate_is_zero(x, expect):
    assert S.lag1_rho(x) == expect


def test_rho_regular():
    x = [1.0, 3.0, 2.0, 5.0, 4.0, 6.0]
    assert S.lag1_rho(x) == pytest.approx(float(np.corrcoef(x[:-1], x[1:])[0, 1]))


def test_sharpe_defined_rule():
    assert S.sharpe_or_none([1.0]) is None and S.sharpe_or_none([2.0, 2.0]) is None
    assert S.sharpe_or_none([1.0, 3.0]) == pytest.approx(2.0 / np.std([1.0, 3.0], ddof=1))


def test_empty_day_list_is_undefined_without_warnings():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert not S.valid_day_bootstrap_mean({}, [], rng(), resamples=10, level=0.9875).defined
        assert not S.daily_diff_bootstrap({}, {}, [], rng(), resamples=10, level=0.9875).defined
