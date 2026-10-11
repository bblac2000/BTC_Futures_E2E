"""트라이얼 #4 (d) — tc_v3 매개변수 · 순수 계산기(ATR_1d(14) · 후행 270 유효 인쇄 분위수). 합성 값만(규약 C24·C30)."""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

import numpy as np

from backtest.data import MINUTE_MS, Bar1m
from strategies.trial04 import anchor as A
from strategies.trial04 import features as F
from strategies.trial04.config import LIMITS, REGIME, TC_V3, TcParams
from strategies.trial04.exit_schedule import HOLD_MIN

ROOT = Path(__file__).resolve().parent.parent
DAY = 86_400_000
D0 = 1_709_251_200_000                       # 2024-03-01 00:00Z · 합성 날짜


def bar(ms: int, o: str = "60000", lo: str | None = None, hi: str | None = None, c: str | None = None) -> Bar1m:
    low, high, close = lo or o, hi or o, c or o
    return Bar1m(ms, o, high, low, close, "1", o, 1, "0", "0", o, high, low, close, "archive")


def day_bars(d: int, hi: str = "60900", lo: str = "59100", close: str = "60000", drop: set[int] | None = None) -> list[Bar1m]:
    out = []
    for i in range(1440):
        if drop and i in drop:
            continue
        ms = D0 + d * DAY + i * MINUTE_MS
        out.append(bar(ms, hi=hi, lo=lo) if i == 720 else bar(ms, c=close if i == 1439 else None))
    return out


# ── 설정 ─────────────────────────────────────────────────────────────────────
def test_tc_v3_values_match_section_1():
    p = TC_V3
    assert (p.q_lo, p.q_hi, p.n_trail) == (0.10, 0.90, 270)
    assert (p.atr_n, p.k_sl) == (14, D("2.0")) and (p.sl_floor, p.sl_ceiling) == (D("0.010"), D("0.200"))
    assert p.hold_min is HOLD_MIN and p.hold_min == 7_200 and p.slippage == D("0.0006")
    assert (p.risk_pct, p.l_min, p.l_max, p.e_ref, p.n_stat) == (D("0.01"), 3, 30, D(1000), D(1000))
    assert p.p2_delays == (1, 3)
    assert LIMITS.leverage_range == (3, 30) and LIMITS.liq_fee_on_liq_price and LIMITS.pos_pct_max == D("0.40")
    assert (REGIME.risk_pct, REGIME.l_min, REGIME.l_max) == (D("0.01"), 3, 30)
    assert TC_V3 == TcParams()


def test_tc_v3_values_appear_in_the_anchored_table():
    lo, hi = A.TC_V3_LINES
    table = "\n".join((ROOT / A.PREREG_PATH).read_text(encoding="utf-8").split("\n")[lo - 1:hi])
    for needle in ("Q0.90", "Q0.10", "유효 인쇄 270개", "2.0 × ATR_1d(14)", "[1.0%, 20.0%]", "7,200분", "L = [3, 30]",
                   "E_ref 1,000", "risk 1%", "margin 캡 0.40", "6 bps", "N_stat 1,000"):
        assert needle in table, needle


# ── ATR_1d(14) ───────────────────────────────────────────────────────────────
def _atr(days: dict[int, list[Bar1m]]) -> F.DailyAtr:
    a = F.DailyAtr(TC_V3)
    for d in sorted(days):
        for b in days[d]:
            a.add(b)
    return a


def test_atr_is_the_simple_mean_of_fourteen_true_ranges():
    days = {d: day_bars(d) for d in range(0, 15)}
    v, why = _atr(days).atr(D0 // DAY + 15)
    assert why is None and v == D("1800")                              # TR = max(1800, 900, 900) 매일


def test_true_range_uses_the_previous_days_close():
    days = {d: day_bars(d) for d in range(0, 15)}
    days[0] = day_bars(0, close="58000")                               # d−15 종가 → d−14의 TR = max(1800, |60900−58000|, |59100−58000|) = 2900
    days[7] = day_bars(7, close="61500")                               # 다음 날 TR = max(1800, |60900−61500|, |59100−61500|) = 2400
    v, why = _atr(days).atr(D0 // DAY + 15)
    assert why is None and v == (D(1800) * 12 + D(2900) + D(2400)) / D(14)


def test_atr_needs_fourteen_complete_days():
    days = {d: day_bars(d) for d in range(0, 15)}
    days[5] = day_bars(5, drop={100})
    assert _atr(days).atr(D0 // DAY + 15) == (None, "days")
    assert _atr({d: day_bars(d) for d in range(1, 15)} | {0: day_bars(0)}).atr(D0 // DAY + 16) == (None, "days")   # 날 15 없음


def test_atr_needs_the_close_of_day_d_minus_15_only():
    days = {d: day_bars(d) for d in range(0, 15)}
    days[0] = day_bars(0, drop={1439})                                 # 23:59 봉 없음
    assert _atr(days).atr(D0 // DAY + 15) == (None, "prev_close")
    days[0] = day_bars(0, drop={3})                                    # 그 날이 불완전해도 23:59 종가만 있으면 된다
    v, why = _atr(days).atr(D0 // DAY + 15)
    assert why is None and v == D("1800")
    days[0] = [b if b.open_ms != D0 + 1439 * MINUTE_MS else bar(b.open_ms, c="NaN") for b in day_bars(0)]
    assert _atr(days).atr(D0 // DAY + 15) == (None, "prev_close")


def test_atr_ignores_the_decision_day_and_later():
    days = {d: day_bars(d) for d in range(0, 15)} | {15: day_bars(15, hi="70000", lo="50000")}
    v, _ = _atr(days).atr(D0 // DAY + 15)
    assert v == D("1800")


# ── 후행 분포 ────────────────────────────────────────────────────────────────
def test_trailing_needs_270_and_keeps_the_last_270():
    t = F.TrailingPrints(TC_V3)
    for k in range(269):
        t.add(float(k))
    assert t.quantiles() is None and len(t) == 269
    t.add(269.0)
    q = t.quantiles()
    assert q is not None
    lo, hi = q
    assert (lo, hi) == tuple(float(x) for x in np.quantile(np.arange(270.0), [0.10, 0.90], method="linear"))
    t.add(1000.0)                                                      # 가장 오래된 0.0이 빠진다
    assert len(t) == 270
    q2 = t.quantiles()
    assert q2 is not None
    lo2, hi2 = q2
    want = np.quantile(np.array([*np.arange(1.0, 270.0), 1000.0]), [0.10, 0.90], method="linear")
    assert (lo2, hi2) == (float(want[0]), float(want[1]))


def test_quantiles_are_linear_interpolation():
    t = F.TrailingPrints(TC_V3)
    for k in range(270):
        t.add(k * 0.001)
    q = t.quantiles()
    assert q is not None
    lo, hi = q
    assert abs(lo - 0.0269) < 1e-12 and abs(hi - 0.2421) < 1e-12        # (n−1)·q = 26.9 · 242.1
