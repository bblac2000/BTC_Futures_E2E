"""트라이얼 #3 (d) — tf_v1 매개변수 · 순수 계산기(r30 · 날별 분위수 · OI 조회 · rv5 · ATR_15m). 합성 값만(계획 r2 D9)."""
from __future__ import annotations

import math
import statistics
from decimal import Decimal as D

import numpy as np
import pytest

from backtest.data import MINUTE_MS, Bar1m
from strategies.trial03 import features as F
from strategies.trial03.config import LIMITS, REGIME, TF_V1

M15 = 15 * MINUTE_MS
T0 = 1_735_689_600_000                       # 2025-01-01 00:00Z


def test_tf_v1_values_match_section_1():
    p = TF_V1
    assert (p.q_lo, p.q_hi, p.w_ref_days, p.quantile_min_defined) == (0.005, 0.995, 90, 128_304)
    assert p.quantile_min_defined == math.ceil(0.99 * 90 * 1440)
    assert (p.r30_ms, p.oi_avail_ms, p.oi_age_ms, p.oi_lookback_ms) == (1_800_000, 300_000, 600_000, 1_800_000)
    assert p.cooldown_ms == 720 * MINUTE_MS
    assert (p.t_min_ms, p.t_max_ms, p.c_cool, p.rv_n, p.rv_peak_lookback_ms) == (20 * MINUTE_MS, 120 * MINUTE_MS, 0.5, 5, 30 * MINUTE_MS)
    assert (p.atr_bucket_ms, p.atr_n, p.k_sl) == (M15, 14, D("1.5"))
    assert (p.sl_floor, p.sl_ceiling) == (D("0.0044"), D("0.0500"))
    assert p.hold_min == 240 and p.slippage == D("0.0006")
    assert (p.risk_pct, p.l_min, p.l_max, p.e_ref, p.n_stat) == (D("0.01"), 10, 30, D(1000), D(1000))
    assert (p.span_before_ms, p.span_after_ms) == (270 * MINUTE_MS, (120 + 5 + 240 + 1) * MINUTE_MS)
    assert LIMITS.leverage_range == (10, 30) and LIMITS.liq_fee_on_liq_price and LIMITS.pos_pct_max == D("0.40")
    assert (REGIME.risk_pct, REGIME.l_min, REGIME.l_max) == (D("0.01"), 10, 30)


# ── r30 · 분위수 ─────────────────────────────────────────────────────────────
def test_r30():
    assert F.r30("101", "100") == math.log(101 / 100)
    assert F.r30("100", None) is None and F.r30("0", "100") is None and F.r30("100", "-1") is None


def _fill(book: F.QuantileBook, day: int, n_defined: int, n_undefined: int = 0, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed + day)
    vals = list(rng.normal(0, 0.003, n_defined))
    for v in vals:
        book.add(day, float(v))
    for _ in range(n_undefined):
        book.add(day, None)
    return vals


def test_quantile_uses_days_d_minus_90_to_d_minus_1_linear():
    book = F.QuantileBook()
    allv: list[float] = []
    for d in range(100, 190):
        allv += _fill(book, d, 1440)
    _fill(book, 190, 1440)                                            # 그날 자신(190)은 쓰지 않는다
    q = book.quantiles(190)
    assert q is not None
    lo, hi = np.quantile(np.array(allv), [0.005, 0.995], method="linear")
    assert q == (float(lo), float(hi))
    assert book.quantiles(191) is not None                            # 101..190


@pytest.mark.parametrize("defined,ok", [(128_304, True), (128_303, False)])
def test_quantile_minimum_defined(defined, ok):
    book = F.QuantileBook()
    per = [1440] * 90
    missing = 129_600 - defined
    for i in range(90):
        take = min(missing, 1440)
        per[i] -= take
        missing -= take
    for i, n in enumerate(per):
        _fill(book, 10 + i, n, 1440 - n)
    assert (book.quantiles(100) is not None) is ok


def test_quantile_missing_day_counts_as_undefined():
    book = F.QuantileBook()
    for d in range(10, 100):
        if d != 50:
            _fill(book, d, 1440)
    assert book.quantiles(100) is None                                # 1,440개 빠짐 → 128,160 < 128,304


# ── OI(§1 25행) ─────────────────────────────────────────────────────────────
def oi(rows: list[tuple[int, str]], unusable: list[int] | None = None) -> F.OiIndex:
    return F.OiIndex([[c, v] for c, v in rows], unusable or [])


def test_oi_availability_and_age_boundaries():
    c = T0
    ix = oi([(c, "100")])
    assert ix.lookup(c + 300_000 - 1) == ("missing", "absent")         # c + 5분 전
    assert ix.lookup(c + 300_000) == ("ok", D("100"))                   # 포함
    assert ix.lookup(c + 300_000 + 600_000) == ("ok", D("100"))         # 나이 10분 포함
    assert ix.lookup(c + 300_000 + 600_001) == ("missing", "absent")


def test_oi_latest_valid_row_and_unusable_subreason():
    c = T0
    ix = oi([(c, "100")], unusable=[c + 300_000])                        # 더 최근 행이 사용 불가
    assert ix.lookup(c + 600_000) == ("ok", D("100"))                   # 나이 5분 → 이전 유효 행
    assert ix.lookup(c + 300_000 + 600_001) == ("missing", "unusable")  # 유효 행은 늙음 · 창 안 사용 불가 슬롯 있음
    ix2 = oi([], unusable=[c])
    assert ix2.lookup(c + 300_000) == ("missing", "unusable")


def test_oi_status_decrease_is_strict_and_uses_t_minus_30():
    c = T0
    t = c + 1_800_000 + 300_000                                          # OI_now = 행 c+30분 · OI_prev = 행 c
    assert oi([(c, "100"), (c + 1_800_000, "99")]).status(t) == ("ok", None)
    assert oi([(c, "100"), (c + 1_800_000, "100")]).status(t) == ("not_decreasing", None)
    assert oi([(c, "100"), (c + 1_800_000, "101")]).status(t) == ("not_decreasing", None)
    assert oi([(c + 1_800_000, "99")]).status(t) == ("missing", "absent")
    assert oi([(c + 1_800_000, "99")], unusable=[c]).status(t) == ("missing", "unusable")


# ── rv5 · ATR_15m ───────────────────────────────────────────────────────────
def test_rv5_ddof1_of_five_log_returns():
    closes = ["100", "101", "100.5", "102", "101", "103"]
    rets = [math.log(float(closes[i + 1]) / float(closes[i])) for i in range(5)]
    assert F.rv5(closes) == statistics.stdev(rets)
    assert F.rv5(closes[:5]) is None and F.rv5(["100", None, "1", "1", "1", "1"]) is None


def mbar(ms: int, o: str, h: str, lo: str, c: str) -> Bar1m:
    return Bar1m(ms, o, h, lo, c, "1", o, 1, "0", "0", o, h, lo, c, "archive")


def feed_buckets(n_buckets: int, start: int = T0) -> tuple[F.AtrBuckets, list[tuple[D, D, D]]]:
    ab = F.AtrBuckets()
    hlc = []
    for k in range(n_buckets):
        base = D(60000 + 10 * k)
        for i in range(15):
            ab.add(mbar(start + k * M15 + i * MINUTE_MS, str(base), str(base + 5 + i), str(base - 3 - i), str(base + i)))
        hlc.append((base + 5 + 14, base - 3 - 14, base + 14))
    return ab, hlc


def expected_atr(hlc: list[tuple[D, D, D]]) -> D:
    trs = [max(h - lo, abs(h - hlc[i - 1][2]), abs(lo - hlc[i - 1][2])) for i, (h, lo, _) in enumerate(hlc) if i > 0]
    return sum(trs, D(0)) / D(len(trs))


def test_atr_uses_last_15_complete_buckets_ending_at_or_before_t():
    ab, hlc = feed_buckets(20)
    t_end = T0 + 20 * M15                                               # 경계 = 마지막 버킷의 끝 → 그 버킷 포함
    assert ab.atr(t_end) == expected_atr(hlc[5:20])
    assert ab.atr(t_end - MINUTE_MS) == expected_atr(hlc[4:19])         # 경계 전 → 막 끝나지 않은 버킷 제외
    assert ab.atr(T0 + 14 * M15) is None                                # 완전 버킷 14개뿐


def test_atr_requires_contiguous_complete_buckets():
    ab = F.AtrBuckets()
    for k in range(16):
        for i in range(15):
            if k == 10 and i == 7:
                continue                                                # 버킷 10 불완전
            ab.add(mbar(T0 + k * M15 + i * MINUTE_MS, "60000", "60010", "59990", "60000"))
    assert ab.atr(T0 + 16 * M15) is None                                # 끝 ≤ T인 마지막 15개 안에 불완전 버킷
