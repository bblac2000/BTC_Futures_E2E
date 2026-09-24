"""트라이얼 #2 전략(단계 2e · 사전등록 §1 · §4 · §9 · §11-7 · 설계 r1 + C1~C20) — 합성 봉 + 정본 재생 루프.

기본 세계: 날마다 mark = 60,000 평평 · "범위 날"은 분 100에 (60,000 · 60,600 · 59,400 · 60,000) 봉 하나 → R = 1,200.
거래일 d의 띠 = O_d ± 600(k = 0.5). 거래일 경로는 테스트마다 따로 만든다.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from backtest.data import Bar1m
from backtest.engine_replay import ReplayResult, replay
from exchange.loader import rules_from_snapshot_dir
from sizing.config import SizingLimits
from strategies.trial02 import anchor as A
from strategies.trial02.config import BO_V1
from strategies.trial02.strategy import Trial02, Variant

D = Decimal
MIN = 60_000
DAY = 86_400_000
D0 = 19_723                                   # 2024-01-01
ROOT = Path(__file__).resolve().parent.parent
RULES = rules_from_snapshot_dir(ROOT / A.RULES_SNAPSHOT_DIR, "BTCUSDT")
TICK = RULES.symbol_rules.tick_size
LIM = SizingLimits(leverage_range=(10, 30), liq_fee_on_liq_price=True)
RANGE_BAR = ("60000", "60600", "59400", "60000")


def day(di: int, levels: list[tuple[int, str]] | None = None, bars: dict[int, tuple[str, str, str, str]] | None = None
        ) -> list[Bar1m]:
    lv = sorted(levels or [(0, "60000")])
    out = []
    for m in range(1440):
        p = [px for start, px in lv if start <= m][-1]
        o, h, lo, c = (bars or {}).get(m, (p, p, p, p))
        out.append(Bar1m(di * DAY + m * MIN, o, h, lo, c, "1", "1", 1, "0", "0", o, h, lo, c, "archive"))
    return out


def history(n: int = 22, last: int = D0 - 1, ranges: dict[int, tuple[str, str, str, str]] | None = None) -> list[Bar1m]:
    out: list[Bar1m] = []
    for di in range(last - n + 1, last + 1):
        out += day(di, bars={100: (ranges or {}).get(di, RANGE_BAR)})
    return out


def run(bars: list[Bar1m], trade_days: set[int], variant: Variant | None = None) -> tuple[ReplayResult, Trial02]:
    s = Trial02(tick=TICK, trade_days=trade_days, variant=variant or Variant("A"))
    r = replay(bars, [], s, rules=RULES, limits=LIM, equity=D("1000"), sizing_capital=D("1000"))
    return r, s


def crosses(s: Trial02) -> list[dict]:
    return [x for x in s.log if x["event"] == "first_cross"]


LONG_UP = [(0, "60000"), (300, "60650")]                      # 분 300에 롱 띠(60,600) 교차 · 그 뒤 60,650 유지
LONG_BARS = {300: ("60000", "60700", "60000", "60650")}


# ── 띠 · 첫 교차 · 진입 의도 ─────────────────────────────────────────────
def test_bands_from_open_and_prior_range_and_long_intent():
    r, s = run(history() + day(D0, LONG_UP, LONG_BARS), {D0})
    d = [x for x in s.log if x["event"] == "day" and x["day"] == D0][0]
    assert (D(d["O_d"]), D(d["R_prev"]), D(d["U"]), D(d["D"])) == (D("60000"), D("1200"), D("60600"), D("59400"))
    (c,) = crosses(s)
    assert c["direction"] == "LONG" and c["outcome"] == "intent" and c["minute"] == 300
    (t,) = r.trades
    assert t["direction"] == "LONG" and D(t["sl"]) == D("60000") and 10 <= t["leverage"] <= 30
    assert t["exit_reason"] == "time_exit" and t["exit_ms"] == D0 * DAY + 1439 * MIN


def test_invariant_bands_ignore_todays_highs_lows():
    """§9 ②: 오늘 진행 중 고가/저가를 바꿔도 띠는 그대로(00:00 고정)."""
    _, s1 = run(history() + day(D0, LONG_UP, LONG_BARS), {D0})
    _, s2 = run(history() + day(D0, LONG_UP, LONG_BARS | {10: ("60000", "60590", "59410", "60000")}), {D0})
    b = [(x["U"], x["D"]) for x in s1.log if x["event"] == "day" and x["day"] == D0]
    assert b == [(x["U"], x["D"]) for x in s2.log if x["event"] == "day" and x["day"] == D0]


def test_invariant_same_open_and_range_same_bands():
    """§9 ①: 전일 경로가 달라도 (O_d, R_{d−1})이 같으면 띠가 같다."""
    h2 = history(ranges={D0 - 1: ("60000", "60900", "59700", "60000")})       # 같은 R 1,200 · 다른 수준
    _, s1 = run(history() + day(D0), {D0})
    _, s2 = run(h2 + day(D0), {D0})
    pick = lambda s: [(x["U"], x["D"]) for x in s.log if x["event"] == "day" and x["day"] == D0]  # noqa: E731
    assert pick(s1) == pick(s2)


def test_first_cross_consumes_direction_for_the_day():
    """§9 ④: 첫 교차 뒤 같은 방향은 그날 다시 셋업되지 않는다(두 번째 교차 무시)."""
    path = [(0, "60000"), (300, "60650"), (400, "60300"), (500, "60700")]
    bars = LONG_BARS | {500: ("60300", "60800", "60300", "60700")}
    _, s = run(history() + day(D0, path, bars), {D0})
    assert [c["minute"] for c in crosses(s)] == [300]


def test_cross_on_the_0000_bar():
    r, s = run(history() + day(D0, [(0, "60650")], {0: ("60000", "60700", "60000", "60650")}), {D0})
    assert crosses(s)[0]["minute"] == 0 and len(r.trades) == 1


# ── 동시 교차 · 바쁨 · 반대 방향 ─────────────────────────────────────────
def test_simultaneous_fresh_crosses_conflict_both_consumed():
    _, s = run(history() + day(D0, bars={200: ("60000", "60700", "59300", "60000")}), {D0})
    cs = crosses(s)
    assert sorted(c["direction"] for c in cs) == ["LONG", "SHORT"] and {c["reason"] for c in cs} == {"conflict_cross"}


def test_wide_bar_after_long_consumed_is_a_plain_short_setup():
    """규약 7: 롱이 이미 소비됐으면 두 띠를 다 닿는 봉은 숏 첫 교차(정상 셋업 · conflict 아님)."""
    path = [(0, "60000"), (300, "60650"), (310, "60000"), (600, "59350")]
    bars = LONG_BARS | {600: ("60000", "60700", "59300", "59350")}
    _, s = run(history() + day(D0, path, bars), {D0})
    cs = crosses(s)
    assert [(c["direction"], c["outcome"]) for c in cs] == [("LONG", "intent"), ("SHORT", "intent")]


def test_opposite_cross_always_finds_the_position_already_stopped():
    """구조(보고): 반대 띠 교차는 O_d(= SL)를 지나므로 같은 봉의 on_bar가 먼저 SL 청산 → 기본 전략에서 position_busy는 생기지 않는다
    (P2 지연 결정에서만 가능 — test_p2_busy_is_judged_at_delayed_time)."""
    path = [(0, "60000"), (300, "60650"), (350, "59350")]
    bars = LONG_BARS | {350: ("60650", "60650", "59350", "59350")}
    r, s = run(history() + day(D0, path, bars), {D0})
    assert [(c["direction"], c["outcome"]) for c in crosses(s)] == [("LONG", "intent"), ("SHORT", "intent")]
    assert r.trades[0]["exit_reason"] == "sl" and r.trades[0]["exit_ms"] // MIN % 1440 == 350


def test_opposite_direction_after_same_day_exit_is_allowed():
    path = [(0, "60000"), (300, "60650"), (400, "59990"), (401, "60000"), (600, "59350")]
    bars = LONG_BARS | {400: ("60650", "60650", "59990", "59990"), 600: ("60000", "60000", "59300", "59350")}
    r, s = run(history() + day(D0, path, bars), {D0})
    assert [t["direction"] for t in r.trades] == ["LONG", "SHORT"]


# ── 시각 경계 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("minute,outcome", [(1437, "intent"), (1438, "late_cross"), (1439, None)])
def test_late_boundaries(minute, outcome):
    bars = {minute: ("60000", "60700", "60000", "60650")}
    r, s = run(history() + day(D0, [(0, "60000"), (minute, "60650")], bars), {D0})
    cs = crosses(s)
    if outcome is None:
        assert cs == [] and r.trades == []                    # C4: 23:59 봉의 고저는 보지 않는다
    elif outcome == "intent":
        assert cs[0]["outcome"] == "intent" and r.trades[0]["entry_ms"] == D0 * DAY + 1438 * MIN
    else:
        assert cs[0]["reason"] == "late_cross" and r.trades == []


# ── 결정 시점 게이트 ─────────────────────────────────────────────────────
def test_sl_dist_floor_and_ceiling():
    #  R = 100 → 띠 ±50 → sl_dist ≈ 0.09% < 0.30% 바닥
    small = history(ranges={D0 - 1: ("60000", "60050", "59950", "60000")})
    _, s = run(small + day(D0, [(0, "60000"), (300, "60055")], {300: ("60000", "60060", "60000", "60055")}), {D0})
    c = crosses(s)[0]
    assert c["reason"] == "sl_dist_out_of_range" and c["side"] == "floor"
    #  R = 7,000 → 띠 ±3,500 → sl_dist ≈ 5.5% > 5.00% 천장
    big = history(ranges={D0 - 1: ("60000", "63500", "56500", "60000")})
    _, s = run(big + day(D0, [(0, "60000"), (300, "63600")], {300: ("60000", "63600", "60000", "63600")}), {D0})
    c = crosses(s)[0]
    assert c["reason"] == "sl_dist_out_of_range" and c["side"] == "ceiling"


def test_sl_wrong_side_when_close_back_below_open():
    #  교차 봉이 띠를 찍고 O_d 아래로 마감
    _, s = run(history() + day(D0, [(0, "60000"), (300, "59990")], {300: ("60000", "60700", "59980", "59990")}), {D0})
    assert crosses(s)[0]["reason"] == "sl_wrong_side"


# ── 날 적격성 · 범위 이력 ────────────────────────────────────────────────
def test_invalid_day_does_not_trade_but_keeps_its_range():
    """C1: 거래일 집합에 없는 날(예: 펀딩 결손)은 거래하지 않지만 그 R은 다음 날에 쓴다."""
    h = history(ranges={D0 - 1: ("60000", "60500", "59500", "60000")})         # R_{D0−1} = 1,000
    bars = h + day(D0, bars={100: RANGE_BAR}) + day(D0 + 1, [(0, "60000"), (300, "60650")], LONG_BARS)
    _, s = run(bars, {D0 + 1})
    ds = {x["day"]: x for x in s.log if x["event"] == "day"}
    assert ds[D0]["status"] == "not_trade_day" and D(ds[D0 + 1]["R_prev"]) == D("1200")


def test_no_range_day():
    flat = history(ranges={D0 - 1: ("60000", "60000", "60000", "60000")})
    _, s = run(flat + day(D0, LONG_UP, LONG_BARS), {D0})
    assert [x["status"] for x in s.log if x["event"] == "day" and x["day"] == D0] == ["no_range"]
    assert crosses(s) == []


def test_trade_day_without_prior_range_is_an_error():
    with pytest.raises(AssertionError):
        run(day(D0 - 1, bars={5: RANGE_BAR})[:-3] + day(D0, LONG_UP, LONG_BARS), {D0})


# ── Arm B ────────────────────────────────────────────────────────────────
def test_arm_b_contraction_filter_and_equality_with_a():
    #  d−1 범위 1,000 < 중앙값 1,200 → 수축일(B 거래) · d+1: d의 범위 1,200 = 중앙값 → 엄격 <가 아니라 B 쉼
    h = history(ranges={D0 - 1: ("60000", "60500", "59500", "60000")})
    d0 = day(D0, [(0, "60000"), (300, "60550"), (1200, "60000")], {300: ("60000", "60600", "60000", "60550"), 1300: RANGE_BAR})
    d1 = day(D0 + 1, [(0, "60000"), (300, "60650")], LONG_BARS)
    bars = h + d0 + d1
    ra, _ = run(bars, {D0, D0 + 1}, Variant("A"))
    rb, sb = run(bars, {D0, D0 + 1}, Variant("B"))
    st = {x["day"]: x["status"] for x in sb.log if x["event"] == "day"}
    assert st[D0] == "trading" and st[D0 + 1] == "not_contraction"
    a0 = [t for t in ra.trades if t["entry_ms"] // DAY == D0]
    keys = ("entry_ms", "direction", "entry_fill", "qty", "leverage", "exit_ms", "exit_reason", "exit_ref", "net_bps")
    assert [{k: t[k] for k in keys} for t in rb.trades] == [{k: t[k] for k in keys} for t in a0] and a0


def test_median_is_exact_and_strict():
    s = Trial02(tick=TICK, trade_days=set(), variant=Variant("B"))
    vals = [D(v) for v in range(1000, 1200, 10)]                               # 20개
    assert s.median(vals) == (D(1090) + D(1100)) / 2
    assert not s.contraction(D(1095), vals) and s.contraction(D("1094.99"), vals)


# ── 플라시보 변형 ────────────────────────────────────────────────────────
def test_p2_delay_decides_at_close_of_i_plus_k():
    path = [(0, "60000"), (300, "60650"), (301, "60700")]
    r, s = run(history() + day(D0, path, LONG_BARS), {D0}, Variant("A", delay=1))
    (c,) = crosses(s)
    assert c["minute"] == 300 and c["decided_minute"] == 301 and D(c["m"]) == D("60700")
    assert r.trades[0]["entry_ms"] == D0 * DAY + 302 * MIN


@pytest.mark.parametrize("cross_minute,k", [(1437, 1), (1433, 5), (1438, 1)])
def test_p2_drop_when_fill_would_be_at_or_after_2359(cross_minute, k):
    bars = {cross_minute: ("60000", "60700", "60000", "60650")}
    r, s = run(history() + day(D0, [(0, "60000"), (cross_minute, "60650")], bars), {D0}, Variant("A", delay=k))
    (c,) = crosses(s)
    assert c["reason"] == "dropped" and r.trades == []


def test_p2_simultaneous_sources_conflict_at_delayed_close():
    _, s = run(history() + day(D0, bars={200: ("60000", "60700", "59300", "60000")}), {D0}, Variant("A", delay=5))
    assert {c["reason"] for c in crosses(s)} == {"conflict_cross"} and all(c["decided_minute"] == 205 for c in crosses(s))


def test_p2_busy_is_judged_at_delayed_time():
    #  롱 300 교차 → 305 결정·306 진입 · 숏 교차 302(롱 대기 중이 아님 · 아직 결정 전) → 307 결정 시 롱 보유 → 바쁨
    path = [(0, "60000"), (300, "60650")]
    bars = LONG_BARS | {302: ("60650", "60650", "59300", "60650")}
    _, s = run(history() + day(D0, path, bars), {D0}, Variant("A", delay=5))
    cs = {c["direction"]: c for c in crosses(s)}
    assert cs["LONG"]["outcome"] == "intent" and cs["SHORT"]["reason"] == "position_busy"


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_p3_inverts_with_mirrored_sl(direction):
    if direction == "LONG":
        path, bars = LONG_UP, LONG_BARS
    else:
        path, bars = [(0, "60000"), (300, "59350")], {300: ("60000", "60000", "59300", "59350")}
    r, s = run(history() + day(D0, path, bars), {D0}, Variant("A", invert=True))
    (t,) = r.trades
    assert t["direction"] == ("SHORT" if direction == "LONG" else "LONG")
    f = D(t["entry_fill"])
    assert D(t["sl"]) == 2 * f - D("60000")                   # SL′ = 2F − O_d


def test_p4_k_star_reproduces_the_registered_rng():
    _, s = run(history() + day(D0), {D0}, Variant("A", p4_draw=7))
    d = [x for x in s.log if x["event"] == "day" and x["day"] == D0][0]
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20260924, 4, 7, D0])))
    q = int(rng.integers(1, int(D("1200") / TICK) + 1))
    from decimal import Context, localcontext
    with localcontext(Context(prec=34)):                        # 전략 산술 문맥
        assert D(d["k"]) == D(q) * TICK / D("1200")
    assert D(d["U"]) == D("60000") + D(q) * TICK and D(d["D"]) == D("60000") - D(q) * TICK


def test_p4_no_range_consumes_no_rng_and_draws_differ():
    flat = history(ranges={D0 - 1: ("60000", "60000", "60000", "60000")})
    _, s = run(flat + day(D0), {D0}, Variant("A", p4_draw=3))
    assert [x.get("k") for x in s.log if x["event"] == "day" and x["day"] == D0] == [None]
    ks = set()
    for dd in range(5):
        _, s = run(history() + day(D0), {D0}, Variant("A", p4_draw=dd))
        ks.add([x["k"] for x in s.log if x["event"] == "day" and x["day"] == D0][0])
    assert len(ks) > 1


def test_placebos_are_arm_a_only():
    for v in (dict(delay=1), dict(invert=True), dict(p4_draw=0)):
        with pytest.raises(ValueError):
            Variant("B", **v)  # type: ignore[arg-type]


# ── 시간 청산 · 룩어헤드 · 정적 검사 ─────────────────────────────────────
def test_no_position_survives_2359_and_after_cross_future_bars_do_not_change_decision():
    r1, s1 = run(history() + day(D0, LONG_UP, LONG_BARS), {D0})
    r2, s2 = run(history() + day(D0, LONG_UP + [(900, "61000")], LONG_BARS), {D0})
    assert crosses(s1) == crosses(s2)                          # 결정은 교차 봉 마감까지의 정보만
    assert all(t["exit_ms"] <= D0 * DAY + 1439 * MIN for t in r1.trades + r2.trades)


def test_static_check_no_rolling_extreme_channel():
    """§9 ③ · 규약 14: strategies/trial02에 롤링 극값 채널이 없다."""
    for p in (ROOT / "strategies" / "trial02").glob("*.py"):
        src = p.read_text(encoding="utf-8")
        low = src.lower()
        assert ".rolling(" not in src and "deque" not in src and "donchian" not in low and "channel" not in low, p
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("max", "min"):
                for a in n.args:
                    assert not isinstance(a, ast.Subscript) and not (
                        isinstance(a, ast.GeneratorExp | ast.ListComp) and any(isinstance(g.iter, ast.Subscript) for g in a.generators)), \
                        f"{p}:{n.lineno} max/min over a slice"


def test_does_not_import_trial01():
    for p in (ROOT / "strategies" / "trial02").glob("*.py"):
        mods = [n.module for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))) if isinstance(n, ast.ImportFrom)]
        assert not any(m and "trial01" in m for m in mods), p


def test_config_values_match_bo_v1_table():
    assert (BO_V1.k, BO_V1.sl_floor, BO_V1.sl_ceiling) == (D("0.5"), D("0.0030"), D("0.0500"))
    assert (BO_V1.trail_arm_r, BO_V1.trail_dist_r, BO_V1.tp_r, BO_V1.risk_pct) == (D(1), D(1), D(2), D("0.01"))
    assert (BO_V1.l_min, BO_V1.l_max, BO_V1.e_ref, BO_V1.n_stat) == (10, 30, D(1000), D(1000))


@pytest.mark.parametrize("r_prev_bar,close,expect", [
    (("60000", "60150", "59850", "60000"), "60187", None),              # R 300 · sl 0.311% → 의도
    (("60000", "60150", "59850", "60000"), "60174", "floor"),           # sl 0.289% → 바닥 미달
    (("60000", "63000", "57000", "60000"), "63090", None),              # R 6,000 · sl 4.898% → 의도
    (("60000", "63000", "57000", "60000"), "63230", "ceiling"),         # sl 5.108% → 천장 초과
])
def test_sl_dist_band_near_boundaries(r_prev_bar, close, expect):
    h = history(ranges={D0 - 1: r_prev_bar})
    _, s = run(h + day(D0, [(0, "60000"), (300, close)], {300: ("60000", close, "60000", close)}), {D0})
    c = crosses(s)[0]
    assert (c["outcome"] == "intent") if expect is None else (c["reason"] == "sl_dist_out_of_range" and c["side"] == expect)


def test_arm_b_median_window_excludes_the_tested_day():
    """중앙값 창 = R_{d−21}…R_{d−2}(R_{d−1} 제외): 제외하면 1,150 = 중앙값 → 수축 아님 · 포함했다면 중앙값 1,175 → 수축."""
    rng = {D0 - 1: ("60000", "60575", "59425", "60000")}                       # R_{d−1} = 1,150
    rng |= {di: ("60000", "60550", "59450", "60000") for di in range(D0 - 21, D0 - 11)}   # 1,100 × 10
    _, s = run(history(ranges=rng) + day(D0), {D0}, Variant("B"))
    d = [x for x in s.log if x["event"] == "day" and x["day"] == D0][0]
    assert d["status"] == "not_contraction" and D(d["median"]) == D("1150")
