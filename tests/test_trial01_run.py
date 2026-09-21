"""트라이얼 #1 실행(단계 2c) — CLI 가드 · 2b 정본 피처와의 대조 · **30일 조각 결정론**(실데이터가 있을 때만).

결정론 검사는 출력 파일의 SHA256만 비교한다 — 트레이드 수익 필드는 읽지 않는다(단계 e 전 손익 금지).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from backtest import prepare as PR
from backtest.data import ARCHIVE_DIR, MINUTE_MS
from backtest.replay import run_isolated
from strategies.trial01 import run as RUN
from strategies.trial01.feature_build import tick_size
from strategies.trial01.strategy import EngineFeed

ROOT = Path(__file__).resolve().parent.parent
IS_DIR = ROOT / "var" / "backtest" / "IS"
HAVE_DATA = (IS_DIR / "bars_1m.parquet").exists() and (IS_DIR / "features_wide.parquet").exists() and ARCHIVE_DIR.exists()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="var/backtest/IS 또는 아카이브 없음")


def test_cli_refuses_oos_and_bad_arm(tmp_path, capsys):
    for argv in (["--window", "OOS", "--arm", "A", "--out", str(tmp_path)],
                 ["--window", "IS", "--arm", "C", "--out", str(tmp_path)],
                 ["--window", "IS", "--arm", "A", "--delay", "-1", "--out", str(tmp_path)]):
        with pytest.raises(SystemExit) as e:
            RUN.main(argv)
        assert e.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_summary_has_no_wallet_or_return_fields():
    from backtest.engine_replay import ReplayResult
    from strategies.trial01.strategy import Trial01
    from tests.test_trial01_strategy import StubFeed
    s = Trial01(StubFeed(), Decimal("0.1"), arm="A")
    out = RUN.summary(ReplayResult([], [], Decimal("1234")), s, {"window": "x"})
    flat = json.dumps(out)
    assert "1234" not in flat and not {"final_wallet", "net_bps", "gross_bps", "net_pnl"} & set(out)


@needs_data
def test_strategy_features_match_the_2b_store_on_sampled_minutes():
    """전략이 보는 피처 = 2b 정본 features_adv(넓은 형식) — 워밍업·배열 범위가 달라 값이 흔들리지 않는다."""
    from tests.fixtures.trial01_slice import load_slice
    warm, bars, _ = load_slice(3)
    s = RUN.build_strategy(warm, bars, tick_size(), arm="B")
    assert isinstance(s.feed, EngineFeed)
    feed = s.feed
    start = bars[0].open_ms
    t = pq.read_table(IS_DIR / "features_wide.parquet",
                      filters=[("bar_open_ms", ">=", start), ("bar_open_ms", "<=", bars[-1].open_ms)])
    want = {r["bar_open_ms"]: r for r in t.to_pylist() if (r["bar_open_ms"] - start) % (97 * MINUTE_MS) == 0}
    assert len(want) > 30
    from tests.test_trial01_strategy import Ctx
    ctx = Ctx()                                          # 엔진 없이(포지션 없음) — 피처 대조만
    seen = 0
    for b in bars:
        s.on_minute_closed(b, ctx)
        w = want.get(b.open_ms)
        if w is None:
            continue
        row = feed.last_row
        for k in ("atr_1m", "vp_poc", "vp_vah", "vp_val"):
            assert (None if row[k] is None else str(row[k])) == w[k], (b.open_ms, k)
        assert str(feed.fe.atr15.value) == w["atr_15m"] and str(Decimal(feed.fe.tsmom.value or 0)) == w["tsmom_4h"]
        seen += 1
    assert seen == len(want)


SLICE_OUTPUTS = {"decisions.jsonl", "trades.jsonl", "open_at_end.jsonl", "summary.json"}
STRATEGY_REASONS = {"conflict_signal", "filter", "cooldown", "one_position", "no_sl_anchor", "sl_dist_out_of_range"}


@pytest.fixture(scope="module")
def slice_runs(tmp_path_factory):
    """30일 조각 × 두 암 × 별도 프로세스 두 번(병렬). 수익 필드는 읽지 않는다."""
    import sys
    from concurrent.futures import ThreadPoolExecutor
    sys.modules.pop("tests.fixtures.trial01_slice", None)        # 대조 테스트가 import했을 수 있다(격리 검사)
    root = tmp_path_factory.mktemp("slice")
    jobs = [(arm, i) for arm in ("A", "B") for i in (1, 2)]
    with ThreadPoolExecutor(4) as ex:
        recs = list(ex.map(lambda j: run_isolated("tests.fixtures.trial01_slice", ["--arm", j[0], "--days", "30"],
                                                  root / f"{j[0]}{j[1]}", timeout_s=900), jobs))
    for r in recs:
        assert r.returncode == 0, r.stderr[-2000:]
    return {f"{a}{i}": (r, root / f"{a}{i}") for (a, i), r in zip(jobs, recs, strict=True)}


@needs_data
@pytest.mark.parametrize("arm", ["A", "B"])
def test_30_day_slice_is_deterministic_across_processes(slice_runs, arm):
    """같은 조각을 별도 프로세스 두 번 → 출력 파일 SHA256이 모두 같다."""
    r1, r2 = slice_runs[f"{arm}1"][0], slice_runs[f"{arm}2"][0]
    assert set(r1.outputs) == SLICE_OUTPUTS and r1.outputs == r2.outputs
    summ = json.loads((slice_runs[f"{arm}1"][1] / "summary.json").read_text())
    assert summ["window_minutes"] == 30 * 1440 and summ["decision_counts"]


@needs_data
@pytest.mark.parametrize("arm", ["A", "B"])
def test_skip_rate_denominator_reconciles_per_setup(slice_runs, arm):
    """셋업(확인된 신호) 하나 = 전략 결정 행 하나 · 후보 = 필터 통과 확인 − cooldown − one_position(사전등록 분모)."""
    out = slice_runs[f"{arm}1"][1]
    summ = json.loads((out / "summary.json").read_text())
    dec = [json.loads(ln) for ln in (out / "decisions.jsonl").read_text().splitlines()]
    c, n = summ["strategy_counts"], summ["decision_counts"]
    setups = c["confirm_LONG"] + c["confirm_SHORT"]
    strat_rows = [d for d in dec if d.get("reason") in STRATEGY_REASONS or d["outcome"] == "intent"]
    assert len(strat_rows) == setups                                     # 셋업마다 결정 행 정확히 하나
    signals = setups - n.get("conflict_signal", 0)
    passed_filter = signals - n.get("filter", 0)
    assert arm == "A" or n.get("filter", 0) == 0
    cands = passed_filter - n.get("cooldown", 0) - n.get("one_position", 0)
    assert cands == summ["candidates"] == c["candidate"]
    assert cands == n.get("no_sl_anchor", 0) + n.get("sl_dist_out_of_range", 0) + n["intent"]
    assert all(d["candidate"] is (d.get("reason") not in {"conflict_signal", "filter", "cooldown", "one_position"})
               for d in strat_rows)
    engine_rows = [d for d in dec if d["outcome"] == "skipped" and d.get("reason") not in STRATEGY_REASONS]
    assert n["intent"] - n.get("entered", 0) - len(engine_rows) in (0, 1)   # 1 = 창 끝에 대기 중인 의도


def test_windows_constant_has_no_oos_bars_here():
    assert "OOS" in PR.WINDOWS and not (ROOT / "var" / "backtest" / "OOS" / "bars_1m.parquet").exists()
