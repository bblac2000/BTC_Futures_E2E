"""`backtest/days.py` — 트라이얼 #2 유효일 V_A·V_B(§1 데이터 완결성 · §3-1 · 설계 C1·C2·C5·C18). 합성 봉만."""
from __future__ import annotations

import pytest

from backtest import days as DY
from backtest.data import Bar1m, Funding

MIN = 60_000
DAY = 86_400_000
H = 3_600_000
D0 = 19_723                                  # 2024-01-01의 day_index


def day_bars(di: int, *, skip: set[int] = frozenset(), p: str = "100") -> list[Bar1m]:  # type: ignore[assignment]
    return [Bar1m(di * DAY + m * MIN, p, p, p, p, "1", "1", 1, "0", "0", p, p, p, p, "archive")
            for m in range(1440) if m not in skip]


def fund(di: int) -> list[Funding]:
    return [Funding(di * DAY + h * H + 7, "0.0001", "100") for h in (0, 8, 16)]


def world(first: int, last: int, *, gaps: dict[int, set[int]] | None = None, no_fund: dict[int, tuple[int, ...]] | None = None):
    bars: list[Bar1m] = []
    fs: list[Funding] = []
    for di in range(first, last + 1):
        bars += day_bars(di, skip=(gaps or {}).get(di, set()))
        fs += [f for f in fund(di) if (f.funding_ms - di * DAY) // H not in (no_fund or {}).get(di, ())]
    return bars, fs


def test_complete_mark_grid_is_exact():
    assert DY.complete_mark_days(day_bars(D0)) == {D0}
    assert DY.complete_mark_days(day_bars(D0, skip={5})) == set()
    dup = day_bars(D0, skip={5}) + [day_bars(D0)[6]]                          # 1,440개지만 중복 + 결손
    with pytest.raises(ValueError):
        DY.complete_mark_days(dup)                                            # 준비 단계가 중복을 없앤다 — 여기서는 오류
    bad = day_bars(D0)
    bad[10] = Bar1m(bad[10].open_ms, "1", "1", "1", "1", "1", "1", 1, "0", "0", "NaN", "1", "1", "1", "archive")
    assert DY.complete_mark_days(bad) == set()
    mis = day_bars(D0, skip={5}) + [Bar1m(D0 * DAY + 5 * MIN + 1, "1", "1", "1", "1", "1", "1", 1, "0", "0", "1", "1", "1", "1",
                                          "archive")]
    assert DY.complete_mark_days(mis) == set()


def test_all_complete_gives_every_window_day():
    bars, fs = world(D0 - 21, D0 + 9)
    v = DY.validity(bars, fs, D0, D0 + 9)
    assert v.v_a == set(range(D0, D0 + 10)) and v.v_b == v.v_a


def test_gap_day_rule_matches_section_5():
    """결손 날 X → A: X·X+1 무효 · B: X·X+1 + (X+2 … X+21)(20일 창 d−21…d−2가 X를 포함)."""
    x = D0 + 3
    bars, fs = world(D0 - 21, D0 + 30, gaps={x: {602, 603}})
    v = DY.validity(bars, fs, D0, D0 + 30)
    assert set(range(D0, D0 + 31)) - v.v_a == {x, x + 1}
    assert set(range(D0, D0 + 31)) - v.v_b == {x, x + 1} | set(range(x + 2, x + 22))
    assert v.reasons[x] == ["missing_bars_d"] and v.reasons[x + 1] == ["missing_bars_prev"]
    assert v.reasons_b[x + 2] == ["missing_bars_window_b"]


def test_funding_missing_invalidates_only_that_day_and_keeps_its_range():
    x = D0 + 4
    bars, fs = world(D0 - 21, D0 + 9, no_fund={x: (8,)})
    v = DY.validity(bars, fs, D0, D0 + 9)
    assert set(range(D0, D0 + 10)) - v.v_a == {x} and v.reasons[x] == ["missing_funding_08"]
    assert x + 1 in v.v_a and x + 1 in v.v_b                     # C1: X의 격자는 완전 → X+1의 R_{d−1}은 있다
    assert x in DY.complete_mark_days(bars)


def test_funding_16_and_00_is_not_required():
    x = D0 + 2
    bars, fs = world(D0 - 21, D0 + 9, no_fund={x: (0,)})
    assert x in DY.validity(bars, fs, D0, D0 + 9).v_a
    bars, fs = world(D0 - 21, D0 + 9, no_fund={x: (16,)})
    v = DY.validity(bars, fs, D0, D0 + 9)
    assert x not in v.v_a and v.reasons[x] == ["missing_funding_16"]


def test_funding_bucket_is_one_minute():
    bars, fs = world(D0 - 21, D0)
    fs = [f for f in fs if f.funding_ms != D0 * DAY + 8 * H + 7] + [Funding(D0 * DAY + 8 * H + MIN, "0.0001", "100")]
    v = DY.validity(bars, fs, D0, D0)
    assert v.v_a == set() and v.reasons[D0] == ["missing_funding_08"]


def test_warmup_days_are_never_in_v_sets():
    bars, fs = world(D0 - 21, D0 + 1)
    v = DY.validity(bars, fs, D0, D0 + 1)
    assert min(v.v_a) == D0 and min(v.v_b) == D0


def test_b_needs_full_20_day_window_before_first_day():
    bars, fs = world(D0 - 20, D0 + 1)                             # d−21 없음 → 첫날 B 무효
    v = DY.validity(bars, fs, D0, D0 + 1)
    assert D0 in v.v_a and D0 not in v.v_b and D0 + 1 in v.v_b
