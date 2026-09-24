"""트라이얼 #2 실행 고정부·결합·교차 모듈 검사(단계 2d·2e after-pass · Codex #1~#4 · advisor #1~#2). 합성 데이터만."""
from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from backtest import days as DY
from backtest.data import Funding
from exchange.normalize import RejectReason
from paper.types import EntrySkipped, SkipReason
from strategies.trial02 import anchor as A
from strategies.trial02 import harness as H
from strategies.trial02.strategy import Variant
from tests.test_trial02_strategy import D0, DAY, LONG_BARS, LONG_UP, MIN, RANGE_BAR, day, history

D = Decimal
ROOT = Path(__file__).resolve().parent.parent
HOUR = 3_600_000


def test_rules_snapshot_is_hash_verified(tmp_path):
    H.load_rules()
    d = tmp_path / "snap"
    shutil.copytree(ROOT / A.RULES_SNAPSHOT_DIR, d)
    (d / "commissionRate.json").write_text((d / "commissionRate.json").read_text().replace("0.000500", "0.000400"))
    with pytest.raises(H.RulesSnapshotMismatch):
        H.load_rules(d)


def test_run_pins_limits_capital_and_tick():
    run = H.run_t2(history() + day(D0, LONG_UP, LONG_BARS), [], {D0}, Variant("A"))
    (t,) = run.result.trades
    assert t["wallet_before"] == "1000" and 10 <= t["leverage"] <= 30
    assert run.strategy.tick == H.load_rules().symbol_rules.tick_size
    assert H.LIMITS.leverage_range == (10, 30) and H.LIMITS.liq_fee_on_liq_price


def test_section_7_3_join_engine_skip_to_cross():
    #  교차 봉 마감 60,650 → 다음 봉 시가 59,990(< O_d = SL) → 엔진 sl_crossed_before_fill
    bars = history() + day(D0, [(0, "60000"), (300, "60650"), (301, "59990")], LONG_BARS)
    run = H.run_t2(bars, [], {D0}, Variant("A"))
    (c,) = run.crosses
    assert c["outcome"] == "intent" and c["engine"] == "skipped" and c["final_reason"] == "sl_crossed_before_fill"
    ok = H.run_t2(history() + day(D0, LONG_UP, LONG_BARS), [], {D0}, Variant("A")).crosses[0]
    assert ok["engine"] == "entered" and ok["final_reason"] is None


@pytest.mark.parametrize("reason,expect", [(RejectReason.MIN_NOTIONAL, "normalization"),
                                           (RejectReason.BELOW_MIN_QTY, "normalization"),
                                           (RejectReason.LIQ_DISTANCE, "sizing_rejected")])
def test_skip_reason_mapping(reason, expect):
    class Dec:
        pass
    dec = Dec()
    dec.reason = reason  # type: ignore[attr-defined]
    ev = EntrySkipped(0, dec, SkipReason.SIZING_REJECTED, "")  # type: ignore[arg-type]
    assert H.skip_reason(ev) == expect


def test_funding_at_0000_never_settles_and_0800_does():
    """C20: 00:00 펀딩은 보유 중이 아니라 정산되지 않는다(23:59 청산) · 08:00 펀딩은 보유 중이면 정산."""
    base = history() + day(D0, LONG_UP, LONG_BARS) + day(D0 + 1)
    t0 = H.run_t2(base, [], {D0}, Variant("A")).result.trades[0]
    f00 = [Funding((D0 + 1) * DAY + 3, "0.01", "60000")]
    t1 = H.run_t2(base, f00, {D0}, Variant("A")).result.trades[0]
    assert t1["net_pnl"] == t0["net_pnl"]
    f08 = [Funding(D0 * DAY + 8 * HOUR + 3, "0.001", "60650")]
    t2 = H.run_t2(base, f08, {D0}, Variant("A")).result.trades[0]
    assert D(t2["net_pnl"]) < D(t0["net_pnl"])


def test_not_trade_day_path_affects_next_day_only_through_its_range():
    """C10: 거래하지 않는 날 X의 장중 경로를 바꿔도(범위 같음) 다음 날 결과는 같다 · 범위를 바꾸면 띠가 바뀐다."""
    x = D0
    nxt = day(D0 + 1, [(0, "60000"), (300, "60650")], LONG_BARS)
    a = history() + day(x, bars={100: RANGE_BAR}) + nxt
    b = history() + day(x, [(0, "60000"), (500, "60300")], {100: RANGE_BAR, 900: ("60300", "60500", "59500", "60300")}) + nxt
    ra, rb = H.run_t2(a, [], {D0 + 1}, Variant("A")), H.run_t2(b, [], {D0 + 1}, Variant("A"))
    keys = ("entry_ms", "entry_fill", "qty", "leverage", "exit_ms", "exit_ref", "net_bps")
    assert [{k: t[k] for k in keys} for t in ra.result.trades] == [{k: t[k] for k in keys} for t in rb.result.trades]
    c = history() + day(x, bars={100: ("60000", "60800", "59400", "60000")}) + nxt       # R_X 1,400
    rc = H.run_t2(c, [], {D0 + 1}, Variant("A"))
    u = [x2["U"] for x2 in rc.strategy.log if x2["event"] == "day" and x2["day"] == D0 + 1]
    assert u == ["60700.0"]


def test_median_depends_only_on_window_members():
    """룩어헤드·창 경계: d−22 범위를 바꿔도 중앙값 불변 · 창 안(d−2) 값을 바꾸면 중앙값이 바뀔 수 있다."""
    base = {D0 - 1: ("60000", "60500", "59500", "60000")}
    def med(extra):
        r = H.run_t2(history(n=23, ranges=base | extra) + day(D0), [], {D0}, Variant("B"))
        return [x["median"] for x in r.strategy.log if x["event"] == "day" and x["day"] == D0][0]
    m0 = med({})
    assert med({D0 - 22: ("60000", "61000", "59000", "60000")}) == m0
    lows = {di: ("60000", "60400", "59600", "60000") for di in range(D0 - 11, D0 - 1)}             # 창 절반을 800으로
    assert med(lows) != m0


def test_p2_fill_bar_contents_do_not_change_the_decision():
    base = [(0, "60000"), (300, "60650")]
    a = H.run_t2(history() + day(D0, base, LONG_BARS), [], {D0}, Variant("A", delay=1))
    b = H.run_t2(history() + day(D0, base, LONG_BARS | {302: ("60650", "61500", "60600", "61400")}), [], {D0},
                 Variant("A", delay=1))
    strip = lambda cs: [{k: v for k, v in c.items() if k not in ("engine", "final_reason")} for c in cs]  # noqa: E731
    assert strip(a.crosses) == strip(b.crosses)


def test_strategy_duplicate_minute_is_an_error():
    bars = history() + day(D0)
    bars.insert(len(bars) - 10, bars[-11])
    with pytest.raises(ValueError):
        H.run_t2(bars, [], {D0}, Variant("A"))


def test_days_rejects_unvalidated_funding():
    with pytest.raises(ValueError):
        DY.funding_boundaries([Funding(D0 * DAY + 8 * HOUR, "0.0001", "1"), Funding(D0 * DAY + 8 * HOUR + 5, "0.0001", "1")])
    with pytest.raises(ValueError):
        DY.funding_boundaries([Funding(D0 * DAY + 8 * HOUR, "NaN", "1")])


def test_prepared_input_days_and_strategy_agree(tmp_path):
    """교차 모듈: prepare_t2 빌드 → days.complete_mark_days == 전략 범위 이력(마지막 날 제외)."""
    from backtest import prepare_t2 as P
    from tests.test_prepare_t2 import FakeRest, arow, fund
    start = (D0 - 3) * DAY
    rows = [arow(start + i * MIN) for i in range(3 * 1440) if i != 1440 + 77]           # 둘째 날에 결손 1분
    rows += [arow(start + 3 * 1440 * MIN + i * MIN) for i in range(1440)]
    arch = tmp_path / "arch"
    arch.mkdir()
    import datetime as dt
    y = dt.datetime.fromtimestamp(start / 1000, dt.UTC).year
    hdr = ("timestamp,Open,High,Low,Close,Volume,quote_volume,trades,taker_buy_base,taker_buy_quote,funding_rate,"
           "mark_open,mark_high,mark_low,mark_close")
    (arch / f"BTCUSDT_1m_{y}.csv").write_text(hdr + "\n" + "\n".join(rows) + "\n")
    out = tmp_path / "out"
    fs = [fund(start + k * 8 * HOUR) for k in range(12)]
    P.capture(out / "raw", FakeRest(fund=fs), arch, start, start + 4 * 1440 * MIN - MIN)
    P.build(out)
    from tests.test_prepare_t2 import lp
    bars, fundings = lp(out)
    comp = DY.complete_mark_days(bars)
    run = H.run_t2(bars, fundings, set(), Variant("A"))
    assert set(run.strategy.ranges) == comp - {D0} and D0 - 2 not in comp


def test_verify_rebuild_catches_prepared_edit_with_updated_manifest(tmp_path):
    import hashlib
    import json

    from backtest import prepare_t2 as P
    from tests.test_prepare_t2 import T0, FakeRest, arow, fund, write_archive
    arch = write_archive(tmp_path / "arch", [arow(T0 + i * MIN) for i in range(10)])
    out = tmp_path / "out"
    P.capture(out / "raw", FakeRest(fund=[fund(T0)]), arch, T0, T0 + 9 * MIN)
    P.build(out)
    P.verify_rebuild(out)
    (out / "funding.json").write_text("[]")                                             # 산출물 변조 + 매니페스트 갱신
    m = json.loads((out / "manifest.json").read_text())
    m["funding.json"] = hashlib.sha256(b"[]").hexdigest()
    (out / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError):
        P.verify_rebuild(out)
    with pytest.raises(ValueError):
        P.analyze(out / "raw", expect_range=(T0, T0 + 10 * MIN))                          # 범위 밖 캡처 거부


def test_verdict_entry_requires_is_range_and_pins(tmp_path):
    import json

    from backtest import prepare_t2 as P
    from tests.test_prepare_t2 import T0, FakeRest, arow, write_archive
    arch = write_archive(tmp_path / "arch", [arow(T0 + i * MIN) for i in range(10)])
    out = tmp_path / "out"
    P.capture(out / "raw", FakeRest(), arch, T0, T0 + 9 * MIN)
    P.build(out)
    pins = json.loads((out / "manifest.json").read_text())["raw"]
    with pytest.raises(ValueError):
        H.run_prepared_is(out, pins, Variant("A"))                        # 합성 캡처 범위 ≠ IS + 21일
    with pytest.raises(ValueError):
        H._run_prepared(out, pins | {"funding.jsonl": "0" * 64}, Variant("A"), (T0, T0 + 9 * MIN), D0, D0)


def test_verdict_entry_runs_on_verified_prepared_input(tmp_path):
    import datetime as dt
    import json

    from backtest import prepare_t2 as P
    from tests.test_prepare_t2 import FakeRest, fund
    start = (D0 - 22) * DAY
    arch = tmp_path / "arch"
    arch.mkdir()
    hdr = ("timestamp,Open,High,Low,Close,Volume,quote_volume,trades,taker_buy_base,taker_buy_quote,funding_rate,"
           "mark_open,mark_high,mark_low,mark_close")
    rows = []
    for b in history() + day(D0, LONG_UP, LONG_BARS):
        t = dt.datetime.fromtimestamp(b.open_ms / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M:%S")
        rows.append(f"{t},{b.open},{b.high},{b.low},{b.close},1,100,5,0.5,50,,{b.mark_open},{b.mark_high},{b.mark_low},{b.mark_close}")
    for y in (2023, 2024):
        (arch / f"BTCUSDT_1m_{y}.csv").write_text(hdr + "\n" + "\n".join(rows) + "\n")
    out = tmp_path / "out"
    fs = [fund(start + k * 8 * HOUR, mp="60000") for k in range(3 * 23)]
    P.capture(out / "raw", FakeRest(fund=fs), arch, start, (D0 + 1) * DAY - MIN)
    P.build(out)
    pins = json.loads((out / "manifest.json").read_text())["raw"]
    run, v = H._run_prepared(out, pins, Variant("A"), (start, (D0 + 1) * DAY - MIN), D0, D0)
    assert v.v_a == {D0} and len(run.result.trades) == 1 and run.crosses[0]["final_reason"] is None


def _ranges_and_vals():
    ranges: dict[int, tuple[str, str, str, str]] = {}
    vals: dict[int, Decimal] = {}
    for j, di in enumerate(range(D0 - 23, D0)):
        half = 300 + 37 * ((j * 7) % 23)                          # 서로 다른 반폭
        ranges[di] = ("60000", str(60000 + half), str(60000 - half), "60000")
        vals[di] = D(2 * half)
    return ranges, vals


def _b_median(ranges) -> Decimal:
    r = H.run_t2(history(n=23, ranges=ranges) + day(D0), [], {D0}, Variant("B"))
    return D([x["median"] for x in r.strategy.log if x["event"] == "day" and x["day"] == D0][0])


def _expected(vals: dict[int, Decimal]) -> Decimal:
    w = sorted(vals[D0 - j] for j in range(2, 22))
    return (w[9] + w[10]) / 2


def test_median_each_member_matters_and_neighbours_do_not():
    """창 구성원 20개를 **하나씩** 반대쪽 극단으로 옮겨 중앙값이 기대값(그 목록의 Decimal 중앙값)대로 바뀌는지 ·
    d−1 · d−22를 옮겨도 불변(창 밖)."""
    ranges, vals = _ranges_and_vals()
    m0 = _b_median(ranges)
    assert m0 == _expected(vals)
    for j in range(2, 22):
        di = D0 - j
        half = 5000 if vals[di] <= m0 else 10                   # 중앙값 아래면 매우 크게 · 위면 매우 작게 → 가운데 둘이 바뀐다
        v2 = vals | {di: D(2 * half)}
        got = _b_median(ranges | {di: ("60000", str(60000 + half), str(60000 - half), "60000")})
        assert got == _expected(v2) and got != m0, j
    for di in (D0 - 1, D0 - 22):
        assert _b_median(ranges | {di: ("60000", "65000", "55000", "60000")}) == m0


def test_no_funding_settled_event_at_0000(monkeypatch):
    """C20: 엔진 `on_funding`의 반환 이벤트를 직접 본다 — 00:00 경계에서는 FundingSettled가 없다."""
    from paper.engine import Engine
    from paper.types import FundingSettled
    seen: list[object] = []
    orig = Engine.on_funding

    def spy(self, *, ts_ms, rate, mark):
        ev = orig(self, ts_ms=ts_ms, rate=rate, mark=mark)
        seen.extend(ev)
        return ev
    monkeypatch.setattr(Engine, "on_funding", spy)
    fs = [Funding(D0 * DAY + 3, "0.01", "60000"), Funding(D0 * DAY + 8 * HOUR + 3, "0.001", "60650"),
          Funding((D0 + 1) * DAY + 3, "0.01", "60000")]
    H.run_t2(history() + day(D0, LONG_UP, LONG_BARS) + day(D0 + 1), fs, {D0}, Variant("A"))
    settled = [e for e in seen if isinstance(e, FundingSettled)]
    assert [e.ts_ms % DAY for e in settled] == [8 * HOUR + 3]
