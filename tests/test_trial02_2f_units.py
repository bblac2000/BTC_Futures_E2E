"""단계 2f — 변형 화이트리스트(G4) · 설정 위치(G2) · 해시 전용 로더(G12) · P1 적격 보기(F2)."""
from __future__ import annotations

import json

import pytest

from strategies.trial02.strategy import Variant

MIN = 60_000
DAY = 86_400_000


@pytest.mark.parametrize("kw", [dict(delay=2), dict(delay=1, invert=True), dict(delay=5, p4_draw=3),
                                dict(invert=True, p4_draw=0), dict(p4_draw=200), dict(delay=-1)])
def test_forbidden_variant_combinations(kw):
    with pytest.raises(ValueError):
        Variant("A", **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("kw", [dict(), dict(delay=1), dict(delay=5), dict(invert=True), dict(p4_draw=0), dict(p4_draw=199)])
def test_allowed_variants(kw):
    Variant("A", **kw)  # type: ignore[arg-type]


def test_limits_and_regime_live_in_config():
    from strategies.trial02 import config as C
    from strategies.trial02 import harness as H
    assert C.LIMITS.leverage_range == (10, 30) and C.LIMITS.liq_fee_on_liq_price and H.LIMITS is C.LIMITS
    assert (C.P1_REGIME.l_min, C.P1_REGIME.l_max, C.P1_REGIME.risk_pct) == (10, 30, C.BO_V1.risk_pct)


def _prepared(tmp_path):
    from backtest import prepare_t2 as P
    from tests.test_prepare_t2 import T0, FakeRest, arow, fund, write_archive
    arch = write_archive(tmp_path / "arch", [arow(T0 + i * MIN) for i in range(10)])
    out = tmp_path / "out"
    P.capture(out / "raw", FakeRest(fund=[fund(T0)]), arch, T0, T0 + 9 * MIN)
    m = P.build(out)
    pins = {"raw": m["raw"], "prepared": {k: m[k] for k in P.PREPARED}}
    return P, out, pins


def test_hash_only_loader_accepts_pinned_and_rejects_tampering(tmp_path):
    from tests.test_prepare_t2 import T0 as T0R
    P, out, pins = _prepared(tmp_path)
    bars, f = P.load_prepared_pinned(out, pins, (T0R, T0R + 9 * MIN))
    assert len(bars) == 10 and len(f) == 1
    (out / "funding.json").write_text("[]")
    m = json.loads((out / "manifest.json").read_text())
    import hashlib
    m["funding.json"] = hashlib.sha256(b"[]").hexdigest()
    (out / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError):
        P.load_prepared_pinned(out, pins, (T0R, T0R + 9 * MIN))
    P.build(out)                                                          # 원복 뒤 범위 불일치도 거부
    with pytest.raises(ValueError):
        P.load_prepared_pinned(out, pins, (T0R, T0R + 10 * MIN))


@pytest.mark.parametrize("h", [1, 2, 1438, 1439, 1440])
def test_same_day_eligible_view_matches_brute_force(h):
    from backtest.p1_t2 import SameDayEligible
    days = [19_700, 19_702, 19_710]                       # 인접하지 않은 유효일
    view = SameDayEligible(days, h)
    brute = [d * DAY + m * MIN for d in days for m in range(1440)
             if (d * DAY + m * MIN + (h - 1) * MIN) // DAY == d and ((d * DAY + m * MIN + (h - 1) * MIN) % DAY) // MIN <= 1438]
    assert len(view) == len(brute) and [view[j] for j in range(len(view))] == brute


def test_variant_name_table():
    from strategies.trial02.run import variant_for
    assert variant_for("A") == Variant("A") and variant_for("P2_delay5") == Variant("A", delay=5)
    assert variant_for("P4_draw042") == Variant("A", p4_draw=42)
    for bad in ("P4_draw200", "P4_draw42", "P2_delay2", "C", "P3"):
        with pytest.raises(ValueError):
            variant_for(bad)


def test_run_execute_writes_outputs_without_aggregates(tmp_path):
    import datetime as dt

    from backtest import prepare_t2 as P
    from strategies.trial02 import harness as H
    from strategies.trial02.run import execute
    from tests.test_prepare_t2 import FakeRest, fund
    from tests.test_trial02_strategy import D0, LONG_BARS, LONG_UP, day, history
    start = (D0 - 22) * DAY
    arch = tmp_path / "arch"
    arch.mkdir()
    hdr = ("timestamp,Open,High,Low,Close,Volume,quote_volume,trades,taker_buy_base,taker_buy_quote,funding_rate,"
           "mark_open,mark_high,mark_low,mark_close")
    rows = [f"{dt.datetime.fromtimestamp(b.open_ms / 1000, dt.UTC):%Y-%m-%d %H:%M:%S},{b.open},{b.high},{b.low},{b.close},1,100,5,"
            f"0.5,50,,{b.mark_open},{b.mark_high},{b.mark_low},{b.mark_close}" for b in history() + day(D0, LONG_UP, LONG_BARS)]
    for y in (2023, 2024):
        (arch / f"BTCUSDT_1m_{y}.csv").write_text(hdr + "\n" + "\n".join(rows) + "\n")
    prep = tmp_path / "prep"
    P.capture(prep / "raw", FakeRest(fund=[fund(start + k * 8 * 3_600_000, mp="60000") for k in range(69)]), arch, start,
              (D0 + 1) * DAY - MIN)
    m = P.build(prep)
    pins = {"raw": m["raw"], "prepared": {k: m[k] for k in P.PREPARED}}
    import strategies.trial02.run as R
    orig = H.run_prepared_is
    H.run_prepared_is = lambda o, p, v: H._run_prepared(o, p, v, (start, (D0 + 1) * DAY - MIN), D0, D0)  # type: ignore[assignment]
    try:
        meta = execute("A", prep, tmp_path / "out", pins, "C0")
    finally:
        H.run_prepared_is = orig  # type: ignore[assignment]
    assert meta["n_trades"] == 1 and R.variant_for(meta["variant_name"]) == Variant("A")
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == ["crosses.jsonl", "days.jsonl", "meta.json", "trades.jsonl", "validity.json"]
    blob = json.dumps(meta).lower()
    assert "wallet" not in blob and "pnl" not in blob and "bps" not in blob
