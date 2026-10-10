"""트라이얼 #4 (c) — 판정 가능 술어(규약 B15~B20 · r3 §1 표본 규칙 · 결정 16·17). 합성 봉만.

닫힌 mark 구간 [t, t + 6일](8,641분) · 반열린 펀딩 구간 (t, t + 6일](경계 18개) · 결정일 앞 14 UTC 날 · 창 경계 · 사유 순서.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from backtest.data import MINUTE_MS, Bar1m, Funding
from strategies.trial04 import anchor as A
from strategies.trial04.eligibility import REASONS, Eligibility, boundaries, complete_days
from strategies.trial04.exit_schedule import EVAL_SPAN_MIN

DAY = 86_400_000
SPAN = EVAL_SPAN_MIN * MINUTE_MS
D0 = int(dt.datetime(2024, 3, 1, tzinfo=dt.UTC).timestamp() * 1000)          # 합성 날짜(실데이터 아님)
T0 = D0 + 14 * DAY                                                            # 앞 14일이 정확히 차는 첫 날 00:00
N_DAYS = 22


def bar(ms: int, o: str = "60000") -> Bar1m:
    return Bar1m(ms, o, o, o, o, "1", o, 1, "0", "0", o, o, o, o, "archive")


BARS = [bar(D0 + i * MINUTE_MS) for i in range(N_DAYS * 1440)]
FUNDS = [Funding(D0 + k * A.H8_MS, "0.0001", "60000") for k in range(N_DAYS * 3 + 1)]
WIN = {"window_start": D0, "window_end": D0 + N_DAYS * DAY - 1}


def elig(bars=None, funds=None, **kw) -> Eligibility:
    return Eligibility(BARS if bars is None else bars, FUNDS if funds is None else funds, **(WIN | kw))


def without(ms: int) -> list[Bar1m]:
    return [b for b in BARS if b.open_ms != ms]


def test_reason_order_is_fixed():
    assert REASONS == ("window_start", "window_end", "mark_incomplete", "atr_days", "funding")


def test_clean_input_is_eligible_on_and_off_the_grid():
    e = elig()
    for t in (T0, T0 + MINUTE_MS, T0 + 479 * MINUTE_MS, T0 + A.H8_MS, T0 + DAY + 7 * MINUTE_MS):
        assert e(t) is None, t


def test_unaligned_t_is_a_caller_bug():
    with pytest.raises(ValueError):
        elig()(T0 + 1)


# ── 펀딩: 반열린 (t, t + 6일] · 경계 18개 ────────────────────────────────────
def test_eighteen_boundaries_for_every_fill_minute():
    for f in range(0, 1440):
        t = T0 + f * MINUTE_MS
        bs = boundaries(t)
        assert len(bs) == 18 and bs[0] > t and bs[-1] <= t + SPAN and bs[0] - t <= A.H8_MS
        assert all(b % A.H8_MS == 0 for b in bs) and all(y - x == A.H8_MS for x, y in zip(bs, bs[1:], strict=False))


def test_fill_on_a_boundary_does_not_require_that_boundary():
    """결정 17 · 트라이얼 #3 Admissibility(닫힌 구간)와의 의도된 차이: t = 경계에 펀딩 기록이 없어도 적격."""
    t = T0 + A.H8_MS
    assert boundaries(t)[0] == t + A.H8_MS and boundaries(t)[-1] == t + SPAN
    assert elig(funds=[f for f in FUNDS if f.funding_ms != t])(t) is None


def test_fill_on_a_boundary_requires_the_eighteenth_at_t_plus_6d():
    t = T0 + A.H8_MS
    assert elig(funds=[f for f in FUNDS if f.funding_ms != t + SPAN])(t) == "funding"


def test_boundary_just_after_the_span_is_not_required():
    t = T0 + MINUTE_MS                                              # 마지막 요구 경계 = T0 + 6일(< t + 6일) · 그다음 경계는 구간 밖
    assert elig(funds=[f for f in FUNDS if f.funding_ms != T0 + SPAN + A.H8_MS])(t) is None
    assert elig(funds=[f for f in FUNDS if f.funding_ms != T0 + SPAN])(t) == "funding"


def test_missing_interior_settlement_and_duplicate_settlement():
    b = T0 + 3 * DAY + A.H8_MS
    assert elig(funds=[f for f in FUNDS if f.funding_ms != b])(T0) == "funding"
    assert elig(funds=[*FUNDS, Funding(b + 17, "0.0001", "60000")])(T0) == "funding"       # 같은 분 버킷에 2건(오프셋 시각)


def test_offset_timestamp_in_the_boundary_minute_counts_once():
    b = T0 + 2 * DAY
    funds = [f for f in FUNDS if f.funding_ms != b] + [Funding(b + 9, "0.0001", "60000")]
    assert elig(funds=funds)(T0) is None


def test_off_grid_funding_records_are_not_examined():
    assert elig(funds=[*FUNDS, Funding(T0 + DAY + 5 * MINUTE_MS, "0.0001", "60000")])(T0) is None


# ── mark: 닫힌 [t, t + 6일] · 분 단위 ────────────────────────────────────────
def test_missing_interior_minute():
    assert elig(bars=without(T0 + 2 * DAY + 123 * MINUTE_MS))(T0) == "mark_incomplete"


def test_missing_fill_minute_and_missing_last_minute():
    t = T0 + 7 * MINUTE_MS
    assert elig(bars=without(t))(t) == "mark_incomplete"
    assert elig(bars=without(t + SPAN))(t) == "mark_incomplete"          # P2 +3 인쇄의 종료 봉(B18)


def test_minute_just_outside_the_span_is_not_required():
    t = T0 + 7 * MINUTE_MS
    assert elig(bars=without(t + SPAN + MINUTE_MS))(t) is None
    assert elig(bars=without(t - MINUTE_MS))(t) is None                   # 같은 날 앞 분은 구간 밖 · 앞 14일도 아님


def test_non_finite_or_non_positive_mark_field_and_duplicate_minute():
    m = T0 + DAY + MINUTE_MS
    for field, bad in (("mark_open", "NaN"), ("mark_high", "0"), ("mark_low", "-1"), ("mark_close", "x")):
        b = dataclasses.replace(bar(m), **{field: bad})
        assert elig(bars=[b if x.open_ms == m else x for x in BARS])(T0) == "mark_incomplete", field
    assert elig(bars=[*BARS, bar(m)])(T0) == "mark_incomplete"


def test_span_running_past_the_input_is_incomplete_not_an_error():
    t = D0 + (N_DAYS - 6) * DAY + MINUTE_MS                              # t + 6일 = 입력 끝 다음 분
    assert elig(window_end=D0 + (N_DAYS + 1) * DAY)(t) == "mark_incomplete"


# ── ATR 날: day(t) 앞 14 UTC 날 ──────────────────────────────────────────────
def test_fourteen_prior_days_required():
    assert elig()(T0 - MINUTE_MS) == "atr_days"                          # 앞 13일만(입력이 D0에서 시작)
    hole = T0 - 14 * DAY + 5 * MINUTE_MS
    assert elig(bars=without(hole))(T0) == "atr_days"
    assert elig(bars=without(hole))(T0 + DAY) is None                     # 15일 전 날의 구멍은 무관


def test_decision_day_is_day_of_t_even_at_midnight():
    hole = T0 - DAY + 5 * MINUTE_MS                                      # 전날
    assert elig(bars=without(hole))(T0) == "atr_days"
    assert elig(bars=without(T0 + 5 * MINUTE_MS))(T0 + DAY) == "atr_days"


def test_complete_days_copy():
    days = complete_days([*BARS, bar(D0 + 3 * DAY)])
    assert D0 // DAY in days and D0 // DAY + 3 not in days and len(days) == N_DAYS - 1


# ── 창 경계 · 사유 순서 ──────────────────────────────────────────────────────
def test_window_start_and_end():
    assert elig(window_start=T0 + MINUTE_MS)(T0) == "window_start"
    assert elig(window_start=T0)(T0) is None
    assert elig(window_end=T0 + SPAN)(T0) is None                         # 분 시작 시각 비교 · 같으면 적격
    assert elig(window_end=T0 + SPAN - 1)(T0) == "window_end"
    assert elig(window_end=T0 + SPAN + 59_999)(T0 + MINUTE_MS) == "window_end"


def test_default_window_is_the_anchored_is_window():
    e = Eligibility(BARS, FUNDS)
    assert (e.window_start, e.window_end) == (A.WINDOW_START_MS, A.IS_END_MS)


def test_first_failing_reason_wins_in_the_fixed_order():
    no_fund = [f for f in FUNDS if f.funding_ms != T0 + DAY]
    hole14 = without(T0 - 14 * DAY + MINUTE_MS)
    both = [b for b in hole14 if b.open_ms != T0 + DAY + MINUTE_MS]
    assert elig(bars=hole14, funds=no_fund)(T0) == "atr_days"
    assert elig(bars=both, funds=no_fund)(T0) == "mark_incomplete"
    assert elig(bars=both, funds=no_fund, window_end=T0 + SPAN - 1)(T0) == "window_end"
    assert elig(bars=both, funds=no_fund, window_end=T0 + SPAN - 1, window_start=T0 + MINUTE_MS)(T0) == "window_start"


def test_same_answer_regardless_of_call_order():
    e = elig(bars=without(T0 + DAY))
    ts = [T0, T0 + DAY, T0 + MINUTE_MS, T0 + DAY + MINUTE_MS]
    first = [e(t) for t in ts]
    assert [e(t) for t in reversed(ts)] == first[::-1] and first == ["mark_incomplete", "mark_incomplete", "mark_incomplete", None]
