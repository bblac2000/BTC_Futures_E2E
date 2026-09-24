"""트라이얼 #2 P1(단계 2f F2 · G2·G5·G6) — 합성 봉·원판만."""
from __future__ import annotations

from decimal import Decimal

import numpy as np

from backtest import p1_core as C
from backtest import p1_t2 as P
from backtest.data import Funding
from strategies.trial02 import harness as H
from tests.test_trial02_strategy import D0, DAY, MIN, day

D = Decimal
RULES = H.load_rules()


def bars_for(days, levels=None, bars=None):
    out = {}
    for d in days:
        for b in day(d, levels, bars):
            out[b.open_ms] = b
    return out


def test_config_is_registered():
    assert P.CFG == C.P1Config(master_seed=20260924, draws=1000, slot_attempts=1000, fail_limit=10)


def test_seed_reproduces_first_slot_draws():
    src = [C.SourceTrade(i, D0 * DAY + (60 + i) * MIN, D0 * DAY + (120 + i) * MIN, D("0.01")) for i in range(3)]
    for d in (0, 7, 999):
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(20260924).spawn(1000)[d]))
        want = [(int(rng.integers(0, 3)), int(rng.integers(0, 2))) for _ in range(3)]
        dr = P.draw(d, src, [D0, D0 + 1], bars_for([D0, D0 + 1]), RULES)
        assert dr.ok and sorted((p.pair, p.direction) for p in dr.placed) == sorted(want)


def test_placement_respects_same_day_and_2358():
    src = [C.SourceTrade(0, D0 * DAY + 10 * MIN, D0 * DAY + 1439 * MIN, D("0.01"))]      # h = 1429
    for d in range(20):
        dr = P.draw(d, src, [D0, D0 + 5], bars_for([D0, D0 + 5]), RULES)
        p = dr.placed[0]
        assert p.entry_ms // DAY == p.exit_minute_ms // DAY and (p.exit_minute_ms % DAY) // MIN <= 1438


def test_slot_with_no_eligible_minutes_fails_the_draw():
    src = [C.SourceTrade(0, 0, 1440 * MIN, D("0.01"))]                                 # h = 1440 → 빈 목록
    dr = P.draw(0, src, [D0], bars_for([D0]), RULES)
    assert not dr.ok and dr.failed_slot == 0


def test_all_sizing_refused_exhausts_attempts():
    src = [C.SourceTrade(0, D0 * DAY + 60 * MIN, D0 * DAY + 70 * MIN, D("0.60"))]      # sl 60% → 명목 < MIN_NOTIONAL
    dr = P.draw(0, src, [D0], bars_for([D0]), RULES)
    assert not dr.ok


def test_null_point_time_exit_reason_and_funding():
    src = [C.SourceTrade(0, D0 * DAY + 60 * MIN, D0 * DAY + 600 * MIN, D("0.01"))]
    bars = bars_for([D0])
    dr = P.draw(3, src, [D0], bars, RULES)
    base = P.null_point(dr, bars, [], RULES)
    assert base["exits"] == {"time_exit": 1, "liquidation": 0} and base["n"] == 1
    t = dr.placed[0].entry_ms
    f = [Funding(t + 2 * MIN + 5, "0.001", "60000")]
    assert D(P.null_point(dr, bars, f, RULES)["mean_net_bps"]) != D(base["mean_net_bps"])


def test_null_point_liquidation_uses_liq_price_fee_basis():
    """P1 트레이드가 청산되면 손실의 수수료 명목 = 수량 × 추정 청산가(config.LIMITS)."""
    src = [C.SourceTrade(0, D0 * DAY + 60 * MIN, D0 * DAY + 900 * MIN, D("0.003"))]    # 30x 근처
    crash = {m: ("50000", "50000", "50000", "50000") for m in range(0, 1440)}
    found = None
    for d in range(50):
        dr0 = P.draw(d, src, [D0], bars_for([D0]), RULES)
        if dr0.placed[0].direction == 0 and (dr0.placed[0].entry_ms % DAY) // MIN < 1300:
            found = dr0
            break
    assert found is not None
    dr, p = found, found.placed[0]
    e = (p.entry_ms % DAY) // MIN
    bars = bars_for([D0], bars={m: v for m, v in crash.items() if m > e + 5})
    pt = P.null_point(dr, bars, [], RULES)
    assert pt["exits"]["liquidation"] == 1
    from backtest import placebo_exec as PX
    from sizing.config import SizingLimits
    from strategies.trial02.config import BO_V1, LIMITS, P1_REGIME
    old = PX.run_time_exit(bars, [], entry_ms=p.entry_ms, h=p.h, direction=0, sl_dist=p.sl_dist, rules=RULES,
                           limits=SizingLimits(leverage_range=(10, 30)), equity=BO_V1.e_ref, regime=P1_REGIME)
    new = PX.run_time_exit(bars, [], entry_ms=p.entry_ms, h=p.h, direction=0, sl_dist=p.sl_dist, rules=RULES,
                           limits=LIMITS, equity=BO_V1.e_ref, regime=P1_REGIME)
    assert old.ret is not None and new.ret is not None and new.ret.net_bps > old.ret.net_bps   # 롱: 청산가 < 진입가 → 수수료 작다


def _prep_world(tmp_path, with_cross=True):
    import datetime as dt

    from backtest import prepare_t2 as PT
    from tests.test_prepare_t2 import FakeRest, fund
    from tests.test_trial02_strategy import LONG_BARS, LONG_UP, history
    start = (D0 - 22) * DAY
    arch = tmp_path / "arch"
    arch.mkdir()
    hdr = ("timestamp,Open,High,Low,Close,Volume,quote_volume,trades,taker_buy_base,taker_buy_quote,funding_rate,"
           "mark_open,mark_high,mark_low,mark_close")
    d0 = day(D0, LONG_UP, LONG_BARS) if with_cross else day(D0)
    rows = [f"{dt.datetime.fromtimestamp(b.open_ms / 1000, dt.UTC):%Y-%m-%d %H:%M:%S},{b.open},{b.high},{b.low},{b.close},1,100,5,"
            f"0.5,50,,{b.mark_open},{b.mark_high},{b.mark_low},{b.mark_close}" for b in history() + d0]
    for y in (2023, 2024):
        (arch / f"BTCUSDT_1m_{y}.csv").write_text(hdr + "\n" + "\n".join(rows) + "\n")
    prep = tmp_path / "prep"
    rng = (start, (D0 + 1) * DAY - MIN)
    PT.capture(prep / "raw", FakeRest(fund=[fund(start + k * 8 * 3_600_000, mp="60000") for k in range(69)]), arch, *rng)
    m = PT.build(prep)
    pins = {"raw": m["raw"], "prepared": {k: m[k] for k in PT.PREPARED}}
    return prep, pins, rng


def _a_dir(tmp_path, prep, pins, rng):
    from strategies.trial02 import harness as H
    from strategies.trial02.run import execute
    from strategies.trial02.strategy import Variant  # noqa: F401
    orig = H.run_prepared_is
    H.run_prepared_is = lambda o, p, v: H._run_prepared(o, p, v, rng, D0, D0)  # type: ignore[assignment]
    try:
        execute("A", prep, tmp_path / "A", pins, "C0")
    finally:
        H.run_prepared_is = orig  # type: ignore[assignment]
    return tmp_path / "A"


def test_p1_run_range_and_merge(tmp_path):
    import json

    from backtest import p1_t2_run as R
    prep, pins, rng = _prep_world(tmp_path)
    a = _a_dir(tmp_path, prep, pins, rng)
    s1 = R.run_range(a, prep, pins, 0, 2, tmp_path / "parts" / "p0", expect_range=rng, days=(D0, D0))
    s2 = R.run_range(a, prep, pins, 0, 2, tmp_path / "parts" / "p0b", expect_range=rng, days=(D0, D0))
    assert s1 == s2 and s1["source_trades"] == 1 and s1["computable"]
    assert (tmp_path / "parts/p0/p1_draws.json").read_bytes() == (tmp_path / "parts/p0b/p1_draws.json").read_bytes()
    exp = {"p0": {f: R._sha(tmp_path / "parts/p0" / f) for f in ("p1_draws.json", "p1_null.jsonl")}}
    import pytest
    with pytest.raises(ValueError):
        R.merge(tmp_path / "parts", exp, tmp_path / "merged")         # 0..999를 덮지 않는다
    (tmp_path / "parts/p0/p1_null.jsonl").write_text("{}\n")
    with pytest.raises(ValueError):
        R.merge(tmp_path / "parts", exp, tmp_path / "merged")         # 조각 변조
    assert json.loads((a / "validity.json").read_text())["v_a"] == [D0]


def test_p1_not_computable_when_no_source_trades(tmp_path):
    import json

    from backtest import p1_t2_run as R
    prep, pins, rng = _prep_world(tmp_path, with_cross=False)
    a = _a_dir(tmp_path, prep, pins, rng)
    s = R.run_range(a, prep, pins, 0, 9, tmp_path / "p", expect_range=rng, days=(D0, D0))
    assert s["computable"] is False and json.loads((tmp_path / "p/p1_not_computable.json").read_text())["reason"] == "n_A=0"
    m = R.merge(tmp_path, {"p": {f: R._sha(tmp_path / "p" / f) for f in ("p1_draws.json", "p1_null.jsonl")}}, tmp_path / "m")
    assert m["computable"] is False


def test_p1_source_reader_requires_pair_fields(tmp_path):
    import pytest

    from backtest import p1_t2_run as R
    (tmp_path / "t.jsonl").write_text('{"trade_id": 1, "entry_ms": 0, "exit_ms": 60000, "sl_dist": "0.01", "net_bps": "5"}\n')
    assert R.source_trades(tmp_path / "t.jsonl")[0].sl_dist == D("0.01")
    (tmp_path / "u.jsonl").write_text('{"trade_id": 1, "entry_ms": 0, "exit_ms": 60000}\n')
    with pytest.raises(ValueError):
        R.source_trades(tmp_path / "u.jsonl")
