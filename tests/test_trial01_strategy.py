"""트라이얼 #1 전략(단계 2c) — 규칙 하나당 테스트 · 손으로 만든 봉 + 고정 피처(StubFeed). 성과·손익은 보지 않는다.

레벨(기본 스냅샷): VP POC 59900 · VAH 60500 · VAL 59000 · swing_low#1 59850 · swing_high#2 60400 ·
ATR_1m 20(밴드 w = 10) · ATR_15m 100 · TSMOM +1.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from backtest.data import MINUTE_MS, Bar1m
from backtest.engine_replay import ReplayContext, replay
from exchange.gate import Mode
from exchange.orders import Direction
from paper.engine import Engine, EntryIntent, Trail
from paper.sender import PaperSender
from sizing.config import SizingLimits
from strategies.trial01.config import SR_V1_PARAMS
from strategies.trial01.features import VP, SwingLevel
from strategies.trial01.strategy import Arm, Snapshot, Trial01

D = Decimal
T0 = 1_704_067_200_000                      # 2024-01-01 00:00Z
TICK = D("0.1")
SL1 = SwingLevel(1, "swing_low", D("59850"), T0 - 10 * 900_000, T0 - 7 * 900_000, T0 + 40 * 3_600_000)
SH2 = SwingLevel(2, "swing_high", D("60400"), T0 - 10 * 900_000, T0 - 7 * 900_000, T0 + 40 * 3_600_000)
SNAP = Snapshot(D(20), VP(D("59900"), D("60500"), D("59000")), (SL1, SH2), (SL1, SH2), D(100), 1)


class StubFeed:
    def __init__(self, snap: Snapshot = SNAP, per_idx: dict[int, Snapshot] | None = None):
        self.snap, self.per_idx, self.i = snap, per_idx or {}, -1

    def step(self, bar: Bar1m) -> Snapshot:
        self.i += 1
        return self.per_idx.get(self.i, self.snap)


def bar(i: int, o, h, lo, c) -> Bar1m:
    o, h, lo, c = (str(x) for x in (o, h, lo, c))
    return Bar1m(T0 + i * MINUTE_MS, o, h, lo, c, "1", "1000", 1, "0", "0", o, h, lo, c, "archive")


FLAT = (60000, 60005, 59995, 59996)          # 어떤 밴드도 건드리지 않고 대기 셋업도 확인하지 않는 봉(종가 하단)
LONG_OK = (60000, 60005, 59905, 59990)       # POC 59900 터치(밴드 안) + 같은 봉 확인(59990 > 59910 · 상위 60%)


class Ctx(ReplayContext):
    """엔진 없이 규칙만 본다 — has_position을 직접 정한다."""

    def __init__(self, pos: bool = False):
        super().__init__(engine=None)  # type: ignore[arg-type]
        self.pos = pos

    @property
    def has_position(self) -> bool:  # type: ignore[override]
        return self.pos


def drive(strat: Trial01, rows, ctx: Ctx | None = None) -> tuple[Ctx, list[EntryIntent | None]]:
    ctx = ctx or Ctx()
    out = []
    for i, r in enumerate(rows):
        ctx.now_ms = T0 + i * MINUTE_MS + MINUTE_MS - 1
        out.append(strat.on_minute_closed(bar(i, *r), ctx))
    return ctx, out


def strat(arm: Arm = "B", **kw) -> Trial01:
    feed = kw.pop("feed", StubFeed())
    return Trial01(feed, TICK, arm=arm, **kw)


def reasons(ctx: Ctx) -> list[str]:
    return [d.get("reason", d["outcome"]) for d in ctx.decisions]


# ── 터치 ─────────────────────────────────────────────────────────────────────
def test_touch_and_same_bar_confirmation_give_a_full_intent():
    ctx, (it,) = drive(strat(), [LONG_OK])
    assert it is not None and it.direction is Direction.LONG
    assert it.sl == D("59750")                                   # swing_low 59850 − 1.0 × ATR_15m 100
    assert it.tp == D("60400")                                   # 반대편 swing_high(410 ≥ 1.5R = 360)
    assert it.decided_ms == T0 + MINUTE_MS - 1 and it.decision_mark == D("59990")
    assert it.trail == Trail(D(1), D(100))
    (d,) = ctx.decisions
    assert d["outcome"] == "intent" and d["level_key"] == ["vp", "59900"] and d["tp_kind"] == "swing_high"
    assert d["candidate"] is True and D(d["sl_dist"]) == D(240) / D(59990)


def test_extreme_that_pierces_through_the_band_is_not_a_touch():
    ctx, (it,) = drive(strat(), [(60000, 60005, 59889, 59990)])   # 저가 59889 < 59890(밴드 하단)
    assert it is None and ctx.decisions == []


def test_only_the_three_nearest_levels_on_each_side_are_candidates():
    far = SwingLevel(9, "swing_low", D("58990"), SL1.bar_open_ms, SL1.confirmed_ms, SL1.expires_ms)
    snap = replace(SNAP, swings_open=(SL1, SH2, far), swings_close=(SL1, SH2, far))
    #  아래쪽 가까운 순: POC 59900 · swing 59850 · VAL 59000 → 58990은 4번째
    ctx, (it,) = drive(strat(feed=StubFeed(snap)), [(60000, 60005, 58985, 59990)])
    assert it is None and ctx.decisions == []


def test_binding_is_the_touched_level_nearest_the_extreme_ties_to_lower_price():
    a = SwingLevel(5, "swing_low", D("59904"), SL1.bar_open_ms, SL1.confirmed_ms, SL1.expires_ms)
    b = SwingLevel(6, "swing_low", D("59896"), SL1.bar_open_ms, SL1.confirmed_ms, SL1.expires_ms)
    vp = VP(D("59700"), D("60500"), D("59000"))
    snap = replace(SNAP, vp=vp, swings_open=(a, b, SH2), swings_close=(a, b, SH2, SL1))
    ctx, _ = drive(strat(feed=StubFeed(snap)), [(60000, 60005, 59900, 59990)])   # 저가가 두 레벨의 정확히 중간
    assert ctx.decisions[0]["level_key"] == ["swing", "6"] and ctx.decisions[0]["level_price"] == "59896"


def test_touch_uses_levels_as_of_bar_open():
    """봉 마감에 막 확정된 스윙(swings_close에만 있음)은 그 봉의 터치 후보가 아니다."""
    vp = VP(D("59000"), D("60500"), D("58000"))
    snap = replace(SNAP, vp=vp, swings_open=(SH2,), swings_close=(SL1, SH2))
    ctx, (it,) = drive(strat(feed=StubFeed(snap)), [(60000, 60005, 59855, 59990)])
    assert it is None and ctx.decisions == []


# ── 확인 ─────────────────────────────────────────────────────────────────────
def test_confirmation_needs_close_beyond_band_and_in_top_60pct():
    ctx, (it,) = drive(strat(), [(60000, 60200, 59905, 59950)])   # 밴드 밖이지만 range 하위 40%
    assert it is None and ctx.decisions == []
    ctx, (it,) = drive(strat(), [(60000, 60005, 59905, 59910)])   # 종가 = 밴드 상단(밖이 아님)
    assert it is None


def test_confirmation_window_is_touch_bar_plus_four():
    touch = (60000, 60005, 59905, 59908)                         # 터치만(종가가 밴드 안)
    ok = (59950, 59995, 59940, 59990)
    _, outs = drive(strat(), [touch, FLAT, FLAT, FLAT, ok])
    assert outs[4] is not None
    s = strat()
    ctx, outs = drive(s, [touch, FLAT, FLAT, FLAT, FLAT, ok])
    assert all(o is None for o in outs) and s.counts["expired"] == 1


def test_doji_bar_never_confirms():
    touch = (60000, 60005, 59905, 59908)
    doji = (59950, 59950, 59950, 59950)                          # range 0 < tick — 가드 없으면 0 ≥ 0으로 확인됐을 봉
    s = strat()
    _, outs = drive(s, [touch, doji])
    assert outs == [None, None] and s.counts["doji"] == 1
    _, outs = drive(strat(), [touch, doji, (59950, 59995, 59940, 59990)])
    assert outs[2] is not None


def test_latest_touch_replaces_the_pending_setup():
    touch_poc = (60000, 60005, 59905, 59908)
    touch_sw = (59920, 59925, 59852, 59856)                       # swing_low 59850 밴드 터치(종가 안 · POC는 시가 아래라 숏 후보 아님)
    ctx, _ = drive(strat(), [touch_poc, touch_sw, (59870, 59880, 59866, 59878)])
    assert [d["level_key"] for d in ctx.decisions] == [["swing", "1"]]


def test_short_side_mirrors():
    ctx, (it,) = drive(strat(), [(60300, 60395, 60290, 60305)])   # swing_high 60400 터치 · 60305 < 60390 · 하위 60%
    assert it is not None and it.direction is Direction.SHORT
    assert it.sl == D("60500")                                   # swing_high 60400 + 100
    assert it.tp == D("59900") and ctx.decisions[0]["tp_kind"] == "poc"   # 아래 POC 거리 405 ≥ 1.5R(292.5)


def test_conflict_signal_skips_both_before_the_filter():
    ctx, (it,) = drive(strat("A"), [(60150, 60400, 59900, 60150)])
    assert it is None
    assert reasons(ctx) == ["conflict_signal", "conflict_signal"]
    assert {d["direction"] for d in ctx.decisions} == {"LONG", "SHORT"}
    assert all(d["candidate"] is False for d in ctx.decisions)


# ── 필터(Arm A만) ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("tsmom", [-1, 0, None])
def test_arm_a_filter_rejects_non_matching_sign(tsmom):
    feed = StubFeed(replace(SNAP, tsmom=tsmom))
    ctx, (it,) = drive(strat("A", feed=feed), [LONG_OK])
    assert it is None and reasons(ctx) == ["filter"] and ctx.decisions[0]["tsmom"] == tsmom


def test_arm_b_has_no_filter():
    feed = StubFeed(replace(SNAP, tsmom=-1))
    _, (it,) = drive(strat("B", feed=feed), [LONG_OK])
    assert it is not None


def test_arm_a_passes_matching_sign():
    _, (it,) = drive(strat("A"), [LONG_OK])
    assert it is not None


# ── 단일 포지션 ───────────────────────────────────────────────────────────────
def test_one_position_rule():
    ctx, (it,) = drive(strat(), [LONG_OK], Ctx(pos=True))
    assert it is None and reasons(ctx) == ["one_position"] and ctx.decisions[0]["candidate"] is False


# ── SL 앵커 ────────────────────────────────────────────────────────────────
def test_no_sl_anchor_when_no_swing_low_at_or_below_the_binding_level():
    snap = replace(SNAP, swings_open=(SH2,), swings_close=(SH2,))
    ctx, (it,) = drive(strat(feed=StubFeed(snap)), [LONG_OK])
    assert it is None and reasons(ctx) == ["no_sl_anchor"] and ctx.decisions[0]["candidate"] is True


def test_sl_anchor_is_nearest_swing_low_at_or_below_the_binding_level_even_for_vp_levels():
    lower = SwingLevel(7, "swing_low", D("59800"), SL1.bar_open_ms, SL1.confirmed_ms, SL1.expires_ms)
    above = SwingLevel(8, "swing_low", D("59950"), SL1.bar_open_ms, SL1.confirmed_ms, SL1.expires_ms)
    snap = replace(SNAP, swings_open=(SL1, SH2), swings_close=(lower, SL1, SH2, above))
    ctx, (it,) = drive(strat(feed=StubFeed(snap)), [LONG_OK])
    assert it is not None and ctx.decisions[0]["sl_anchor"] == ["swing", "1"] and it.sl == D("59750")


@pytest.mark.parametrize("atr15,expect", [(D(20), "tight"), (D(600), "wide")])
def test_sl_dist_out_of_range_is_skipped(atr15, expect):
    #  tight: SL = 59830 → 160/59990 = 0.267% < 0.30% · wide: SL = 59250 → 1.23% > 1.00%
    ctx, (it,) = drive(strat(feed=StubFeed(replace(SNAP, atr15=atr15))), [LONG_OK])
    assert it is None and reasons(ctx) == ["sl_dist_out_of_range"] and ctx.decisions[0]["candidate"] is True


# ── TP ─────────────────────────────────────────────────────────────────────
def test_tp_is_2r_when_the_opposite_level_is_under_1_5r():
    near = SwingLevel(3, "swing_high", D("60200"), SL1.bar_open_ms, SL1.confirmed_ms, SL1.expires_ms)
    snap = replace(SNAP, swings_close=(SL1, near, SH2))
    ctx, (it,) = drive(strat(feed=StubFeed(snap)), [LONG_OK])
    assert it is not None and it.tp == D(59990) + 2 * D(240) and ctx.decisions[0]["tp_kind"] == "2R"


def test_tp_is_2r_when_no_level_ahead():
    snap = replace(SNAP, vp=VP(D("59900"), D("59950"), D("59000")), swings_close=(SL1,))
    _, (it,) = drive(strat(feed=StubFeed(snap)), [LONG_OK])
    assert it is not None and it.tp == D(59990) + 2 * D(240)


# ── 쿨다운(엔진과 함께 · 실제 체결) ─────────────────────────────────────────────
def test_cooldown_blocks_the_same_level_for_60_minutes_after_exit(rules):
    rows = [LONG_OK, (59990, 60000, 59980, 59995), (59995, 60410, 59990, 60405)]   # 진입 · 체결 · TP 60400
    rows += [FLAT] * 10 + [LONG_OK]                                                   # 청산 뒤 11분 → 쿨다운
    rows += [FLAT] * 50 + [LONG_OK]                                                   # 청산 뒤 62분 → 허용
    bars = [bar(i, *r) for i, r in enumerate(rows)]
    r = replay(bars, [], strat(), rules=rules, limits=SizingLimits(), equity=D("1000"))
    got = [(d["ts_ms"], d.get("reason", d["outcome"])) for d in r.decisions]
    exit_ms = T0 + 2 * MINUTE_MS + MINUTE_MS - 1
    kinds = [k for _, k in got]
    assert kinds.count("intent") == 2 and "cooldown" in kinds
    (cd,) = [d for d in r.decisions if d.get("reason") == "cooldown"]
    assert cd["until_ms"] == exit_ms + SR_V1_PARAMS.cooldown_ms
    assert r.trades and r.trades[0]["exit_reason"] == "tp"


def test_other_level_is_not_in_cooldown(rules):
    rows = [LONG_OK, (59990, 60000, 59980, 59995), (59995, 60410, 59990, 60405)]
    rows += [FLAT] * 3 + [(59900, 59905, 59852, 59885)]                              # swing_low 59850 레벨 신호
    bars = [bar(i, *r) for i, r in enumerate(rows)]
    r = replay(bars, [], strat(), rules=rules, limits=SizingLimits(), equity=D("1000"))
    last = r.decisions[-1]
    assert last["level_key"] == ["swing", "1"] and last.get("reason") != "cooldown"
    assert all(d.get("reason") != "cooldown" for d in r.decisions)


# ── P2 지연 · P3 반전 · 트레일링 플래그 ─────────────────────────────────────────
def test_delay_emits_k_bars_later_with_state_at_that_time():
    _, outs = drive(strat(delay=1), [LONG_OK, (59990, 59995, 59985, 59992)])
    assert outs[0] is None and outs[1] is not None
    assert outs[1].decided_ms == T0 + 2 * MINUTE_MS - 1 and outs[1].decision_mark == D(59992)


def test_delay_rechecks_filter_at_emission():
    feed = StubFeed(SNAP, per_idx={5: replace(SNAP, tsmom=-1)})
    ctx, outs = drive(strat("A", delay=5, feed=feed), [LONG_OK] + [(59990, 59995, 59985, 59992)] * 5)
    assert all(o is None for o in outs) and reasons(ctx) == ["filter"]


def test_invert_mirrors_sl_and_tp_around_the_decision_mark():
    _, (it,) = drive(strat(invert=True), [LONG_OK])
    m = D(59990)
    assert it is not None and it.direction is Direction.SHORT
    assert it.sl == 2 * m - D(59750) and it.tp == 2 * m - D(60400)


def test_invert_intent_is_accepted_by_the_engine(rules):
    _, (it,) = drive(strat(invert=True), [LONG_OK])
    assert it is not None
    Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits()).request_entry(it)


def test_trailing_flag_off_gives_no_trail():
    _, (it,) = drive(strat(params=replace(SR_V1_PARAMS, trailing=False)), [LONG_OK])
    assert it is not None and it.trail is None


def test_bad_arm_or_delay_rejected():
    with pytest.raises(ValueError):
        Trial01(StubFeed(), TICK, arm="C")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Trial01(StubFeed(), TICK, arm="A", delay=-1)


def test_warm_up_steps_features_only():
    s = strat()
    s.warm(bar(0, *LONG_OK))
    assert s.idx == -1 and s.pending == {} and s.feed.i == 0   # type: ignore[attr-defined]
