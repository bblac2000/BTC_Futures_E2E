"""P4 무작위 레벨(레지스트리 #22) — 합성 봉(삼각파 · 7일)에서 규칙을 무차별 재계산과 대조한다. 손익은 보지 않는다."""
from __future__ import annotations

from decimal import Decimal

import pytest

from backtest.data import MINUTE_MS, Bar1m
from backtest.placebo import p4_args
from strategies.trial01 import anchor as A
from strategies.trial01.features import FeatureEngine, SwingLevel
from strategies.trial01.p4 import DAY_MS, P4Feed, _Range24h, vp_rng
from strategies.trial01.strategy import EngineFeed
from tests.fixtures.dummy_replay_strategy import bars as tri_bars

D = Decimal
TICK = D("0.1")
N = 7 * 1440


def _bars() -> list[Bar1m]:
    out = []
    for i, b in enumerate(tri_bars(N)):                      # 삼각파 + 분마다 조금씩 다른 거래대금(VP 동률 방지)
        out.append(Bar1m(b.open_ms, b.open, b.high, b.low, b.close, b.volume, str(1000 + i % 17), b.trades,
                         b.taker_buy_base, b.taker_buy_quote, b.mark_open, b.mark_high, b.mark_low, b.mark_close, b.source))
    return out


def _run(draw: int, bars: list[Bar1m]):
    closes = [b.d("close") for b in bars]
    feed = P4Feed(EngineFeed(FeatureEngine(TICK, min(closes), max(closes))), draw, TICK)
    snaps, vps, buckets = [], [], []
    for b in bars:
        snaps.append(feed.step(b))
        vps.append(feed.last_vp)
        buckets += list(feed.fe.b15_complete)
    return feed, snaps, vps, buckets


@pytest.fixture(scope="module")
def run0():
    bars = _bars()
    return bars, *_run(0, bars)


def _range_close(bars: list[Bar1m], t: int) -> tuple[Decimal, Decimal]:
    sel = [b for b in bars if t - DAY_MS < b.open_ms + MINUTE_MS - 1 <= t]
    return min(b.d("low") for b in sel), max(b.d("high") for b in sel)


def test_swings_are_replaced_one_to_one_with_same_kind_and_validity(run0):
    bars, feed, *_ = run0
    real = feed.fe.swing_events
    assert len(real) >= 20 and set(feed.by_real) == {lv.level_id for lv in real}
    for lv in real:
        r = feed.by_real[lv.level_id]
        assert (r.kind, r.bar_open_ms, r.confirmed_ms, r.expires_ms) == (lv.kind, lv.bar_open_ms, lv.confirmed_ms, lv.expires_ms)
        lo, hi = _range_close(bars, lv.confirmed_ms)                 # 확정 시각 직전 24h 마감 1m
        assert lo <= r.price <= hi and (r.price - lo) % TICK == 0


def test_random_swings_follow_the_same_invalidation_rule(run0):
    _, feed, _, _, buckets = run0
    band_mult = feed.fe.cfg.invalidate_atr_mult
    for r in feed.by_real.values():
        want = None
        for bk, a15 in buckets:
            if a15 is None or not (r.confirmed_ms < bk.close_ms < r.expires_ms):
                continue
            band = band_mult * a15
            if (r.kind == "swing_high" and bk.close > r.price + band) or (r.kind == "swing_low" and bk.close < r.price - band):
                want = bk.close_ms
                break
        assert r.invalidated_ms == want, r


def test_vp_is_three_levels_per_minute_from_the_prior_24h_with_the_minute_seed(run0):
    bars, _, snaps, vps, _ = run0
    seen = 0
    for i in range(0, N, 37):
        vp = vps[i]
        if vp is None:
            continue
        b = bars[i]
        prior = [x for x in bars[:i] if x.open_ms >= b.open_ms - DAY_MS]
        lo, hi = min(x.d("low") for x in prior), max(x.d("high") for x in prior)
        g = vp_rng(0, b.open_ms // MINUTE_MS)
        n = int((hi - lo) / TICK)
        want = sorted(lo + TICK * int(g.integers(0, n + 1)) for _ in range(3))
        assert [vp.val, vp.poc, vp.vah] == want and snaps[i].vp == vp
        seen += 1
    assert seen > 100


def test_vp_range_excludes_the_decision_bar():
    r = _Range24h()
    base = _bars()[:10]
    for b in base[:9]:
        r.push(b)
    spike = base[9]
    before = r.as_of_open(spike.open_ms)
    r.push(Bar1m(spike.open_ms, "1", "999999", "1", "1", "1", "1", 1, "0", "0", "1", "1", "1", "1", "archive"))
    assert before is not None and before[1] < D("999999")
    assert r.as_of_open(spike.open_ms + MINUTE_MS) == (D("1"), D("999999"))      # 다음 분부터 들어간다


def test_real_features_are_untouched_and_draws_are_deterministic(run0):
    bars, feed, snaps, vps, _ = run0
    closes = [b.d("close") for b in bars]
    plain = EngineFeed(FeatureEngine(TICK, min(closes), max(closes)))
    for i, b in enumerate(bars):
        s = plain.step(b)
        assert (s.atr1_open, s.atr15, s.tsmom) == (snaps[i].atr1_open, snaps[i].atr15, snaps[i].tsmom)
    _, snaps_b, vps_b, _ = _run(0, bars)
    assert snaps_b == snaps and vps_b == vps
    f1, _, vps1, _ = _run(1, bars)
    assert [f1.by_real[k].price for k in sorted(f1.by_real)] != [feed.by_real[k].price for k in sorted(feed.by_real)]
    assert vps1 != vps


def test_strategy_runs_end_to_end_on_random_levels(rules):
    from backtest.engine_replay import replay
    from sizing.config import SizingLimits
    from strategies.trial01.strategy import Trial01
    bars = _bars()
    closes = [b.d("close") for b in bars]
    feed = P4Feed(EngineFeed(FeatureEngine(TICK, min(closes), max(closes))), 3, TICK)
    s = Trial01(feed, TICK, arm="B")
    warm, win = bars[:3 * 1440], bars[3 * 1440:]
    for b in warm:
        s.warm(b)
    r = replay(win, [], s, rules=rules, limits=SizingLimits(), equity=D("1000"))
    assert r.decisions and s.counts["touch_LONG"] + s.counts["touch_SHORT"] > 0
    anchors = [d["sl_anchor"] for d in r.decisions if "sl_anchor" in d]
    assert all(a[0] == "swing" and int(a[1]) in feed.by_real for a in anchors)


def test_p4_arguments_and_bounds(tmp_path):
    from strategies.trial01 import run as RUN
    args = p4_args()
    assert len(args) == A.P4_DRAWS == 200 and args["P4_draw000"] == ["--p4-draw", "0"] and args["P4_draw199"][1] == "199"
    for bad in ("-1", "200"):
        with pytest.raises(SystemExit):
            RUN.main(["--window", "IS", "--arm", "A", "--p4-draw", bad, "--out", str(tmp_path)])
    with pytest.raises(ValueError):
        P4Feed(EngineFeed(FeatureEngine(TICK, D(1), D(2))), 200, TICK)


def test_swing_level_objects_are_not_shared_with_the_real_tracker(run0):
    _, feed, *_ = run0
    real_ids = {id(x) for x in feed.fe.swing_events}
    assert not any(id(x) in real_ids for x in feed.by_real.values())
    assert all(isinstance(x, SwingLevel) for x in feed.by_real.values())
