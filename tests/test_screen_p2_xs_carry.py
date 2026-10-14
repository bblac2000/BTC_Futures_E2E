"""S-xs-carry-1 — 합성 자료로(실제 자료 내려받기 전 · 스펙 r6)."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest

from research.screens.p2 import compute as C
from research.screens.p2.loader import Series, Symbol, dedup

H, DAY, WEEK = C.H, C.DAY, C.WEEK


def ms(*a: int) -> int:
    return int(dt.datetime(*a, tzinfo=dt.UTC).timestamp() * 1000)


T = ms(2024, 3, 4)                                                                  # 월요일


def fund(lo: int, hi: int, g: int = 8 * H, rate: float = 0.001, drop: tuple[int, ...] = (), extra: tuple[tuple[int, float], ...] = ()) -> Series:
    rows = [(t, rate) for t in range(lo, hi + 1, g) if t not in drop] + list(extra)
    return dedup(rows)


def bars(lo: int, hi: int, price=lambda t: 100.0, drop: tuple[int, ...] = ()) -> Series:  # noqa: ANN001
    return dedup([(t, price(t)) for t in range(lo, hi + 1, DAY) if t not in drop])


def sym(name="AUSDT", f=None, b=None) -> Symbol:  # noqa: ANN001
    return Symbol(name, f if f is not None else fund(T - 60 * DAY, T + 8 * DAY), b if b is not None else bars(T - 60 * DAY, T + 8 * DAY),
                  frozenset(), frozenset())


def test_signal_week_complete_on_the_8h_grid_and_sums_21_settlements():
    assert C.signal_window(fund(T - 60 * DAY, T + DAY), T - WEEK, T) == pytest.approx(21 * 0.001)


def test_missing_settlement_at_the_inclusive_lower_boundary_fails():
    assert C.signal_window(fund(T - 60 * DAY, T + DAY, drop=(T - WEEK,)), T - WEEK, T) is None


def test_hourly_cadence_with_one_missing_settlement_fails_and_offgrid_extra_fails():
    assert C.signal_window(fund(T - 9 * DAY, T, g=H), T - WEEK, T) == pytest.approx(168 * 0.001)
    assert C.signal_window(fund(T - 9 * DAY, T, g=H, drop=(T - 3 * DAY + 5 * H,)), T - WEEK, T) is None
    assert C.signal_window(fund(T - 9 * DAY, T, extra=((T - 3 * DAY + 3 * H, 0.001),)), T - WEEK, T) is None


def test_conflicting_duplicate_is_a_bad_record():
    s = dedup([(T, 0.001), (T, 0.002), (T + 8 * H, 0.001), (T + 8 * H, 0.001)])
    assert math.isnan(s.val[0]) and s.val[1] == 0.001 and s.ts.size == 2


def test_hold_funding_codex_cases():
    base = fund(T - DAY, T + 8 * DAY)
    assert C.hold_funding(base, T, T + WEEK, 8 * H).total == pytest.approx(21 * 0.001)
    miss = C.hold_funding(fund(T - DAY, T + 8 * DAY, drop=(T + WEEK,)), T, T + WEEK, 8 * H)
    assert (miss.missing, round(miss.total, 6)) == (1, 0.020)
    coll = C.hold_funding(fund(T - DAY, T + 8 * DAY, extra=((T + WEEK - 30_000, 0.002),)), T, T + WEEK, 8 * H)
    assert (coll.missing, coll.collisions, round(coll.total, 6)) == (1, 1, 0.020)
    empty = C.hold_funding(fund(T - 10 * DAY, T - DAY), T, T + WEEK, 8 * H)
    assert (empty.missing, empty.total) == (21, 0.0)
    assert C.hold_funding(base, T, T, 8 * H).missing == 0


def test_eligibility_uses_only_pre_entry_information():
    assert C.eligible(sym(), T) is not None
    young = sym(f=fund(T - WEEK - 27 * DAY, T + 8 * DAY))
    assert C.eligible(young, T) is None
    old_enough = sym(f=fund(T - WEEK - 28 * DAY, T + 8 * DAY))
    assert C.eligible(old_enough, T) is not None
    no_entry_bar = sym(b=bars(T - 60 * DAY, T + 8 * DAY, drop=(T - DAY,)))
    assert C.eligible(no_entry_bar, T) is None
    later_bad = sym(f=dedup([(t, 0.001) for t in range(T - 60 * DAY, T + 8 * DAY, 8 * H)] + [(T + 2 * DAY, 0.009)]))
    assert C.eligible(later_bad, T) is not None                                     # 보유 주의 나쁜 레코드는 적격을 바꾸지 않는다
    gap_reset = sym(f=dedup([(t, 0.001) for t in range(T - 200 * DAY, T - 120 * DAY, 8 * H)]
                            + [(t, 0.001) for t in range(T - 20 * DAY, T + 8 * DAY, 8 * H)]))
    assert C.eligible(gap_reset, T) is None                                         # 30일 넘는 공백 뒤 재상장 → 나이 다시


def test_daily_check_exits_causally_at_the_last_known_close():
    b = bars(T - 60 * DAY, T + 8 * DAY, price=lambda t: 100.0 + (t - T) / DAY, drop=(T + 2 * DAY,))
    s = sym(b=b)
    e = C.eligible(s, T)
    assert e is not None
    o = C.outcome(s, e, T)
    assert o.forced and o.x == T + 3 * DAY and o.p_exit == pytest.approx(100.0 + 1)  # 일봉 T+1일의 종가
    full = sym(b=bars(T - 60 * DAY, T + 8 * DAY, price=lambda t: 110.0 if t >= T + 6 * DAY else 100.0))
    o2 = C.outcome(full, C.eligible(full, T), T)  # type: ignore[arg-type]
    assert not o2.forced and o2.x == T + WEEK and o2.r == pytest.approx(0.1)


def _week(names, s0, forced=None, ratio=None) -> C.Week:  # noqa: ANN001
    n = len(names)
    w = C.Week(T, list(names), np.array(s0, float), [None] * n, np.zeros(n), np.zeros(n), np.zeros(n),
               np.array(forced if forced is not None else [False] * n), np.zeros(n, bool))
    w.ratio = np.array(ratio if ratio is not None else [1.0] * n)
    order = sorted(range(n), key=lambda i: (w.s0[i], w.names[i]))
    q = n // 10
    w.long, w.short = order[:q], order[n - q:]
    return w


def test_turnover_full_replacement_and_forced_week_end_exit():
    names = [f"S{i:02d}" for i in range(20)]
    w1 = _week(names, list(range(20)))
    w2 = _week(names, list(range(19, -1, -1)))                                        # 다리 맞바꿈 → 완전 교체
    tr = C.turnover([w1, w2], [True, True])
    assert tr[0] == pytest.approx(2.0)                                                # 진입(다리마다 1)
    assert tr[1] == pytest.approx(4.0 + 2.0)                                          # 교체 4 + 마지막 청산 2
    assert C.TAKER_BPS * (tr[1] - 2.0) == pytest.approx(40.0)
    fw = _week(names, list(range(20)), forced=[i == 0 for i in range(20)], ratio=[1.1 if i == 0 else 1.0 for i in range(20)])
    tr2 = C.turnover([fw, _week(names, list(range(20)))], [True, True])
    assert tr2[0] == pytest.approx(2.0 + 0.55)                                        # 진입 2 + 강제 청산 0.55(한 번)
    assert tr2[1] == pytest.approx(0.5 + 2.0)                                         # 다시 들어감 0.5 + 마지막 청산 2


def test_spearman_average_ranks_and_undefined_on_constant():
    assert C.spearman(np.array([1.0, 2.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0, 4.0])) == pytest.approx(0.9486832980505138)
    assert C.spearman(np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0])) is None
    assert C.t_stat([0.1, 0.1, 0.1]) is None


def test_shuffle_null_is_deterministic_and_week_ordered():
    wk = [(np.arange(25.0), np.arange(25.0)[::-1]), (np.arange(30.0), np.arange(30.0))]
    a, b = C.shuffle_null(wk, 20261014, 50), C.shuffle_null(wk, 20261014, 50)
    assert a == b and len(a) == 50


def test_mde_and_benchmark_weekly_bps():
    m = C.mde(np.array([0.0, 10.0] * 8))
    assert m is not None and m["n_eff"] == pytest.approx(16 / 1.6) and m["power_label"] == "feasible"
    assert C.mde(np.array([1.0])) is None
    assert C.dtb3_weekly_bps([("2024-03-01", 5.0)], T) == pytest.approx(1e4 * 0.05 * 7 / 365)
