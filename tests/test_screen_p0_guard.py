"""M-1(P0 실행 감사) 가드와 체결 규칙 — 실제 자료 없이 합성 배열·합성 shard로(스펙 r6 §7)."""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import numpy as np
import pytest

from research.screens.p0 import sim
from research.screens.p0 import span as SP

ROOT = Path(__file__).resolve().parent.parent
P0 = ROOT / "research" / "screens" / "p0"


def ms(*a: int) -> int:
    return int(dt.datetime(*a, tzinfo=dt.UTC).timestamp() * 1000)


def test_span_constants_equal_the_protocol_exposure_and_skip_the_auxiliary_span():
    assert SP.EXPOSED_START_MS == ms(2026, 9, 17) and SP.EXPOSED_END_MS == ms(2026, 10, 11, 6, 22, 15)
    assert SP.DATES[0] == "2026-09-17" and SP.DATES[-1] == "2026-10-11" and len(SP.DATES) == 25
    for p in P0.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        for aux in ("2026-07-2", "2026-08-", "2026-09-0", "2026-09-10", "2026-09-16"):
            assert aux not in src, (p, aux)


def test_p0_imports_no_legacy_layer_and_has_no_order_path():
    for p in P0.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
            n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any(m.split(".")[0] in ("backtest", "strategies", "paper", "exchange") for m in mods), p
        assert "create_order" not in src and "/fapi/v1/order" not in src and "new_order" not in src, p


def test_p0_reads_only_under_the_restore_root_or_the_pinned_rules_snapshot():
    for p in P0.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert "/home/" not in src and "expanduser" not in src, p
    assert "trial_04_rules_snapshot" in (P0 / "sim.py").read_text(encoding="utf-8")


def test_loader_refuses_ranges_outside_the_exposed_span():
    from research.screens.p0 import loader
    with pytest.raises(ValueError):
        loader._read("aggtrade", SP.EXPOSED_START_MS - 1, SP.EXPOSED_START_MS + 1000, ["recv_ms"])
    with pytest.raises(ValueError):
        loader._read("aggtrade", SP.EXPOSED_END_MS - 1000, SP.EXPOSED_END_MS + 1, ["recv_ms"])


# ---------- 합성 책 ----------
T0 = ms(2026, 9, 20, 12, 0, 0)
BID, ASK = 100000.0, 100000.1


def book(trades=(), *, bid=BID, ask=ASK, bq=5.0, aq=5.0, depth_bid_q=None, gap_at=None, bt_step=100, ids=None, lo=None, hi=None):
    t_lo, t_hi = T0 - 20_000, T0 + 200_000
    bt_recv = np.arange(t_lo, t_hi, bt_step, dtype=np.int64)
    bt = np.tile([bid, bq, ask, aq], (len(bt_recv), 1)).astype(float)
    dp_recv = np.arange(t_lo, t_hi, 100, dtype=np.int64)
    if gap_at is not None:
        dp_recv = dp_recv[(dp_recv < gap_at) | (dp_recv > gap_at + 3000)]
    row = []
    for side, top, q0 in (("b", bid, depth_bid_q if depth_bid_q is not None else bq), ("a", ask, aq)):
        for k in range(sim.LEVELS):
            px = top - k * sim.TICK if side == "b" else top + k * sim.TICK
            row += [px, q0 if k == 0 else 1.0]
    dp = np.tile(row, (len(dp_recv), 1)).astype(float)
    tr = sorted(trades, key=lambda x: x[0])
    n = len(tr)
    ag_ids = np.array(ids if ids is not None else list(range(1000, 1000 + n)), dtype=np.int64)
    return sim.Book(bt_recv, bt, dp_recv, dp,
                    np.array([x[0] for x in tr], dtype=np.int64), ag_ids,
                    sim.ticks(np.array([x[1] for x in tr], dtype=float)) if n else np.array([], dtype=np.int64),
                    np.array([x[2] for x in tr], dtype=float), np.array([x[3] for x in tr], dtype=np.int64),
                    np.array([x[4] for x in tr], dtype=bool), lo if lo is not None else t_lo, hi if hi is not None else t_hi, [])


def run(bk, buy=True, b_ms=0, t_ms=30_000):
    pl = sim.place(bk, T0, buy)
    assert isinstance(pl, sim.Placed), pl
    tape = sim.tape_of(bk, T0 - sim.PRE_MS, T0 + sim.DELTA_MS + sim.POST_MS)
    return pl, sim.outcome(pl, tape, b_ms, t_ms), tape


def sell(t, qty, px=BID, tt=None):                                         # 매도 공격(is_buyer_maker=True) — 매수호가를 친다
    return (t, px, qty, t if tt is None else tt, True)


def test_queue_must_be_exhausted_at_exactly_our_price_including_the_boundary():
    tp = T0 + sim.DELTA_MS
    _, (path, _, mk), _ = run(book([sell(tp + 1000, 5.0)], bq=5.0))         # 누적 5.0 = Q — Q + 0.001 미만
    assert path == "timeout" and not mk
    _, (path, px, mk), _ = run(book([sell(tp + 1000, 5.0), sell(tp + 2000, 0.001)], bq=5.0))      # 정확히 Q + 0.001
    assert path == "maker" and mk and px == BID


def test_trades_through_our_price_do_not_fill_and_touch_is_not_fill():
    tp = T0 + sim.DELTA_MS
    _, (path, *_), _ = run(book([sell(tp + 1000, 50.0, px=BID - 5 * sim.TICK)], bq=5.0))       # 넘어선 체결
    assert path == "timeout"
    _, (path, *_), _ = run(book([(tp + 1000, BID, 50.0, tp + 1000, False)], bq=5.0))            # 같은 가격이지만 매수 공격
    assert path == "timeout"


def test_trades_before_the_exchange_side_placement_bound_are_ignored():
    tp = T0 + sim.DELTA_MS
    bk = book([sell(tp + 500, 10.0, tt=tp + 400)], bq=5.0)
    assert run(bk, b_ms=0)[1][0] == "maker"
    assert run(bk, b_ms=400)[1][0] == "timeout"                             # tt = t_place + B → 엄격 > 이므로 무시


def test_receive_deadline_and_late_conflict_diagnostic():
    tp = T0 + sim.DELTA_MS
    bk = book([sell(tp + 30_000 + 2000, 10.0, tt=tp + 29_000)], bq=5.0)    # 거래소에선 제때 · 수신은 시간 초과 뒤
    pl, (path, *_), tape = run(bk, t_ms=30_000)
    assert path == "timeout" and sim.late_conflict(pl, tape, 0, 30_000)
    assert run(bk, t_ms=60_000)[1][0] == "maker"


def test_post_only_reject_uses_executable_price():
    bk = book(bid=BID, ask=BID + sim.TICK)
    pl = sim.place(bk, T0, True)
    assert isinstance(pl, sim.Placed) and not pl.reject


def test_fallback_walks_depth_when_display_is_short_and_fails_when_depth_is_short():
    tp = T0 + sim.DELTA_MS
    bk = book([], aq=0.0004)
    _pl, (path, px, _), _ = run(bk)
    assert path == "timeout" and abs(px - (0.0004 * ASK + 0.0006 * (ASK + sim.TICK)) / 0.001) < 1e-6
    bk2 = book([], aq=0.0004)
    bk2.dp[:, 2 * sim.LEVELS + 1::2] = 0.00001                                 # 20단계 합이 0.001에 못 미친다
    bk2.bt[:, 3] = 0.0004
    assert sim.place(bk2, T0, True) == "baseline_depth"
    _ = tp


def test_stale_quotes_and_stream_gaps_make_the_decision_ineligible():
    assert sim.place(book(gap_at=T0 + 10_000), T0, True) == "depth_gap"
    assert sim.place(book(bt_step=6_000), T0, True) in ("bookticker_gap", "baseline_quote")
    assert sim.place(book(lo=T0), T0, True) == "span"


def test_aggtrade_id_gap_and_conflicting_duplicates_are_ineligible():
    tp = T0 + sim.DELTA_MS
    assert sim.place(book([sell(tp + 100, 1.0), sell(tp + 200, 1.0)], ids=[1000, 1002]), T0, True) == "aggtrade_id_gap"
    assert sim.place(book([sell(tp + 100, 1.0), sell(tp + 200, 2.0)], ids=[1000, 1000]), T0, True) == "dup_conflict"
    bk = book([sell(tp + 100, 5.0005, tt=tp + 100), sell(tp + 150, 5.0005, tt=tp + 100)], ids=[1000, 1000], bq=5.0)
    _pl, (path, *_), _ = run(bk)
    assert path == "timeout"                                                 # 중복을 두 번 세면 5.0005 × 2 > Q + 0.001 → 체결이 됐을 것


def test_crossed_sources_are_ineligible():
    bk = book(depth_bid_q=5.0)
    bk.dp[:, 0] = ASK + sim.TICK                                            # depth 최우선 매수가 bookticker 매도보다 높다
    assert sim.place(bk, T0, True) == "baseline_quote"


def test_donor_tape_shift_preserves_exact_price_and_moves_time_back():
    tp = T0 + sim.DELTA_MS
    other = book([sell(tp + 1000 + 86_400_000, 10.0, px=BID + 50 * sim.TICK)])
    other.ag_recv = other.ag_recv
    tape = sim.tape_of(other, tp - 10_000 + 86_400_000, tp + 200_000 + 86_400_000, shift_ms=86_400_000, tick_shift=-50)
    assert int(tape.tick[0]) == int(sim.ticks(BID)) and int(tape.tt[0]) == tp + 1000


def test_b_bound_uses_pooled_values_when_a_day_is_thin():
    r = np.arange(100, dtype=np.int64) + 50
    t = np.arange(100, dtype=np.int64)
    pooled = (np.arange(20_000, dtype=np.int64) + 10, np.arange(20_000, dtype=np.int64))
    assert sim.b_bound(r, t, pooled=pooled) == 20 and sim.b_bound(r, t) == 100


def test_head_statistic_is_time_share_weighted_and_undefined_without_a_stratum():
    from research.screens.p0 import run as R
    rows = [{"stratum": "prox", "x": 10.0}, {"stratum": "other", "x": 0.0}]
    h = R.head(rows, "x")
    assert h is not None and abs(h - 10 * 30 / 1440) < 1e-12
    assert R.head([{"stratum": "other", "x": 1.0}], "x") is None


def test_sample_is_deterministic_and_stratified():
    from research.screens.p0 import sample
    a, b = sample.draw(), sample.draw()
    assert a == b and len(a) == 9698
    assert sum(1 for _, _, s in a if s == "prox") == 2416


# ---------- 강화(사용자 #105 · 다음 M/S 실행 전) ----------
def _restore_fixture(tmp_path, monkeypatch, *, ok=True, matched=(), excluded=()):
    from research.screens.p0 import loader
    data = tmp_path / "BTCUSDT"
    plan = tmp_path / "plan.json"
    rj = tmp_path / "restore.json"
    plan.write_text(json_dumps({"matched": {k: {"stream": k.split("/")[1]} for k in matched}}), encoding="utf-8")
    rj.write_text(json_dumps({"ok": ok, "excluded": [{"file": k, "why": "x"} for k in excluded]}), encoding="utf-8")
    monkeypatch.setattr(loader, "DATA", data)
    monkeypatch.setattr(loader, "PLAN", plan)
    monkeypatch.setattr(loader, "RESTORE_JSON", rj)
    loader.allowed_files.cache_clear()
    return loader, data


def json_dumps(o) -> str:
    import json
    return json.dumps(o)


def _shard(data: Path, rel: str, recv: list[int], tt: list[int] | None = None) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    f = data / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    cols = {"recv_ms": pa.array(recv, pa.int64()), "price": pa.array([float(i) for i in range(len(recv))])}
    if tt is not None:
        cols["transact_time"] = pa.array(tt, pa.int64())
    pq.write_table(pa.table(cols), f)


def test_runner_refuses_when_restore_is_not_ok(tmp_path, monkeypatch):
    from research.screens.p0 import run
    _restore_fixture(tmp_path, monkeypatch, ok=False)
    monkeypatch.setattr(run, "OUT_JSON", tmp_path / "M-x.json")
    monkeypatch.setattr(run.sample, "draw", lambda: pytest.fail("draw before the restore check"))
    assert run.main() != 0
    assert not (tmp_path / "M-x.json").exists()


def test_runner_refuses_when_restore_record_is_missing(tmp_path, monkeypatch):
    from research.screens.p0 import loader, run
    _restore_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(loader, "RESTORE_JSON", tmp_path / "absent.json")
    monkeypatch.setattr(run, "OUT_JSON", tmp_path / "M-x.json")
    monkeypatch.setattr(run.sample, "draw", lambda: pytest.fail("draw before the restore check"))
    assert run.main() != 0


def test_loader_fails_loudly_on_a_shard_outside_the_paired_allow_list(tmp_path, monkeypatch):
    loader, data = _restore_fixture(tmp_path, monkeypatch, matched=("2026-09-20/bookticker/120000_000.parquet",))
    _shard(data, "2026-09-20/bookticker/120000_000.parquet", [T0])
    _shard(data, "2026-09-20/bookticker/120100_000.parquet", [T0 + 60_000])          # 짝지어지지 않은 파일
    with pytest.raises(RuntimeError):
        loader._read("bookticker", T0 - 1000, T0 + 120_000, ["recv_ms"])


def test_loader_skips_verification_excluded_shards_without_reading_them(tmp_path, monkeypatch):
    rel = "2026-09-20/bookticker/120000_000.parquet"
    loader, data = _restore_fixture(tmp_path, monkeypatch, matched=(rel,), excluded=(rel,))
    f = data / rel
    f.parent.mkdir(parents=True)
    f.write_bytes(b"not a parquet file")
    assert len(loader._read("bookticker", T0 - 1000, T0 + 1000, ["recv_ms"])["recv_ms"]) == 0


def test_boundary_shard_rows_outside_the_window_are_not_returned(tmp_path, monkeypatch):
    lo, hi = T0, T0 + 60_000
    rels = ("2026-09-20/bookticker/115930_000.parquet", "2026-09-20/aggtrade/115930_000.parquet")
    loader, data = _restore_fixture(tmp_path, monkeypatch, matched=rels)
    recv = [lo - 30_000, lo - 1, lo, lo + 1, hi - 1, hi, hi + 1, hi + 30_000]
    _shard(data, rels[0], recv)
    got = loader._read("bookticker", lo, hi, ["recv_ms", "price"])
    assert got["recv_ms"].tolist() == [lo, lo + 1, hi - 1, hi]
    assert got["price"].tolist() == [2.0, 3.0, 4.0, 5.0]                                 # 값 칸도 같은 행만
    # aggtrade: 두 시각 칸이 모두 [lo, hi] 안이어야 한다
    _shard(data, rels[1], [lo, lo + 10, hi], tt=[lo - 5, lo + 5, hi])
    got = loader._read("aggtrade", lo, hi, ["recv_ms", "transact_time"])
    assert got["recv_ms"].tolist() == [lo + 10, hi]


def test_verify_excludes_a_shard_whose_comparison_meta_is_missing(tmp_path, monkeypatch):
    import json

    from research.screens.p0 import restore
    rels = {"2026-09-20/bookticker/a.parquet": {"md5": None, "parquet_rows": 1},
            "2026-09-20/bookticker/b.parquet": {"md5": "x", "parquet_rows": None}}
    for rel in rels:
        _shard(tmp_path / "BTCUSDT", rel, [T0])
    plan = {"matched": {k: {**v, "stream": "bookticker", "remote_md5": None} for k, v in rels.items()},
            "by_stream": {s: {"expected": 2, "missing_on_drive": []} for s in SP.STREAMS}}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(restore, "PLAN", tmp_path / "plan.json")
    monkeypatch.setattr(restore, "OUT", tmp_path / "restore.json")
    monkeypatch.setattr(restore.SP, "RESTORE", tmp_path)
    restore.verify()
    out = json.loads((tmp_path / "restore.json").read_text(encoding="utf-8"))
    assert sorted(e["file"] for e in out["excluded"]) == sorted(rels)
    assert all("missing comparison meta" in e["why"] for e in out["excluded"])
