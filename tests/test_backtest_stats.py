"""단계 2a — 리샘플·판정 통계(합성 입력만)."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from backtest import resample as RS
from backtest import stats as ST
from backtest.data import MINUTE_MS as M
from backtest.data import Bar1m

T0 = int(dt.datetime(2024, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)


def bar(t: int, px: int) -> Bar1m:
    s = str(px)
    return Bar1m(t, s, str(px + 2), str(px - 2), s, "1", s, 1, "0", "0", s, str(px + 1), str(px - 1), s, "archive")


def test_resample_emits_only_closed_utc_aligned_buckets_and_counts_minutes():
    bars = [bar(T0 + i * M, 100 + i) for i in range(31)]            # 15m 버킷 2개 완전 + 1분짜리 진행 중
    out = RS.resample(bars, 15)
    assert [b.open_ms for b in out] == [T0, T0 + 15 * M] and all(b.complete for b in out)
    assert out[0].open == 100 and out[0].close == 114 and out[0].high == 116 and out[0].low == 98
    assert RS.resample(bars, 15, until_ms=T0 + 45 * M - 1)[-1].open_ms == T0 + 30 * M, "마감 시각이 지나면 낸다"
    gappy = [b for b in bars[:15] if b.open_ms != T0 + 3 * M]
    g = RS.resample(gappy + [bar(T0 + 15 * M, 1)], 15)
    assert g[0].n_minutes == 14 and not g[0].complete, "결손 분을 조용히 완전한 봉으로 보지 않는다"
    assert RS.resample([bar(T0 + i * M, 1) for i in range(240)], 240)[0].close_ms == T0 + 240 * M - 1


def test_block_bootstrap_is_seeded_calendar_day_blocks_and_two_sided_975():
    trades = [(T0 + d * ST.DAY_MS + 3600_000, 0.001 * ((d % 5) - 1)) for d in range(60)]
    end = T0 + 60 * ST.DAY_MS - 1
    a = ST.block_bootstrap_mean(trades, T0, end, resamples=2000, level=0.975, rng=np.random.default_rng(1))
    b = ST.block_bootstrap_mean(trades, T0, end, resamples=2000, level=0.975, rng=np.random.default_rng(1))
    assert a == b and a.lo < a.mean < a.hi and a.level == 0.975
    with pytest.raises(ValueError):
        ST.block_bootstrap_mean(trades, T0 + 1, end, resamples=10, level=0.975, rng=np.random.default_rng(1))
    empty_days = ST.block_bootstrap_mean(trades[:1], T0, end, resamples=500, level=0.975, rng=np.random.default_rng(2))
    assert empty_days.degenerate > 0, "거래 0건 재표본은 정의되지 않은 것으로 센다(0으로 채우지 않는다)"


def test_paired_bootstrap_uses_the_same_days_for_both_arms():
    a = [(T0 + d * ST.DAY_MS, 0.002) for d in range(30)]
    b = [(T0 + d * ST.DAY_MS, 0.001) for d in range(30)]
    ci = ST.paired_block_bootstrap_diff(a, b, T0, T0 + 30 * ST.DAY_MS - 1, resamples=500, level=0.975,
                                        rng=np.random.default_rng(3))
    assert math.isclose(ci.lo, 0.001) and math.isclose(ci.hi, 0.001), "같은 날짜 짝지음이면 상수 차이는 폭 0"


def test_psr_properties_and_dsr_deflation_with_two_trials():
    rng = np.random.default_rng(5)
    r = list(rng.normal(0.001, 0.01, 400))
    sr = ST.sharpe(r)
    assert math.isclose(ST.psr(r, sr), 0.5, abs_tol=1e-12), "SR* = SR̂면 PSR = 0.5"
    assert ST.psr(r, sr - 0.05) > 0.5 > ST.psr(r, sr + 0.05)
    s_star = ST.expected_max_sr([0.10, 0.06], 2)
    assert s_star > 0 and math.isclose(s_star, math.sqrt(np.var([0.10, 0.06], ddof=1)) * (
        (1 - ST.EULER_GAMMA) * 0.0 + ST.EULER_GAMMA * ST._N.inv_cdf(1 - 1 / (2 * math.e))))
    with pytest.raises(ValueError):
        ST.expected_max_sr([0.1], 1)


def test_neff_mde_and_rho():
    assert ST.n_eff(48, 0.15) == 30.0
    assert math.isclose(ST.mde(0.01, 100, alpha=0.025), (1.959963984540054 + 0.8416212335729143) * 0.001, rel_tol=1e-9)
    assert ST.lag1_autocorr([1, 2, 3, 4, 5, 6]) > 0.9 and ST.lag1_autocorr([1, 1, 1]) == 0.0
