# ── PROVENANCE ─────────────────────────────────────────────────────────────
# Copied from: /home/cms/project/E2E_Hybrid_Bot/tests/test_delivery_counter.py
# Source commit: d0d6426 (E2E HEAD f1e7d86, 2026-09-14) · copied 2026-09-15
# Local changes:
#   - ported only the pure judgement-rule and replay tests; dropped every test that imports
#     e2e.l2_collector / ops.vps_health / e2e.quality / tests.test_prune (not in this repo —
#     the #138 flush tests come back with ShardWriter at layer 5, health throttle at layer 8)
#   - stream kinds remapped to this repo's DELIVERY (kline1m, markprice)
#   - threshold-lock test asserts this repo's PROVISIONAL values (docs/design_v1.md §5)
# ───────────────────────────────────────────────────────────────────────────
"""전달 감시 테스트 — 깨진 스트림의 증상은 예외가 아니라 **0**이다(E2E #132·#133·#134)."""
from __future__ import annotations

import datetime as dt

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ops import delivery_counter as D
from ops.delivery_counter import (
    DELIVERY,
    TS_COLUMN,
    DeliveryCounter,
    scan_window,
    silence_summary,
    stalled_from_scan,
    window_files,
)
from ops.stream_tiers import build_stream_url

M = 60_000
DAY = 86_400_000
T0 = 1_789_000_000_000 // DAY * DAY          # 어떤 UTC 자정(2026-09 부근)


def _iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC)


def _write_shards(root, kind, ts_list, *, col=None, extra=None):
    """ts 목록을 **실제 수집기처럼 60초 shard**로 나눠 `<일>/<kind>/HHMMSS_mmm.parquet`에 쓴다."""
    col = col or TS_COLUMN[kind]
    ts_list = sorted(ts_list)
    chunks, cur, first = [], [], None
    for t in ts_list:
        if first is None or t - first >= 60_000:
            if cur:
                chunks.append(cur)
            cur, first = [], t
        cur.append(t)
    if cur:
        chunks.append(cur)
    for ch in chunks:
        d = _iso(ch[0])
        sd = root / d.strftime("%Y-%m-%d") / kind
        sd.mkdir(parents=True, exist_ok=True)
        cols = {col: pa.array(ch, pa.int64())}
        for k, fn in (extra or {}).items():
            cols[k] = pa.array([fn(t) for t in ch])
        pq.write_table(pa.table(cols), sd / f"{d.strftime('%H%M%S')}_{ch[0] % 1000:03d}.parquet")


# ── 임계 고정 ──────────────────────────────────────────────────────────
def test_thresholds_are_exactly_the_pre_committed_values():
    """🔒 데이터를 보기 전에 커밋한 값(PROVISIONAL). 바꾸려면 **레지스트리 행이 먼저**다."""
    got = {k: (s.ws_suffix, s.grace_sec, s.min_per_min, s.live) for k, s in DELIVERY.items()}
    assert got == {
        "kline1m": ("@kline_1m", 120, 1, True),
        "markprice": ("@markPrice@1s", 120, 1, True),
    }
    assert set(TS_COLUMN) == set(DELIVERY)


def test_every_monitored_stream_is_market_tier_and_fits_one_socket():
    """티어는 `stream_tiers`에서 **도출**한다 — 두 스트림이 한 market 소켓에 실린다."""
    assert {D.tier_of(k) for k in DELIVERY} == {"market"}
    build_stream_url("market", [D.ws_stream(k) for k in DELIVERY])     # 섞이면 예외


def test_kinds_for_streams_round_trips_and_reports_unknowns():
    kinds, unknown = D.kinds_for_streams(["btcusdt@kline_1m", "btcusdt@markPrice@1s", "btcusdt@trade"])
    assert kinds == ("kline1m", "markprice") and unknown == ("btcusdt@trade",)


# ── 판정 규칙 ───────────────────────────────────────────────────────
def test_a_stream_that_stops_is_reported_by_age_and_by_empty_minute():
    m = DeliveryCounter(("markprice",), start_ms=0)
    for i in range(60):
        m.observe("markprice", i * 1000)            # 0분대 매초
    assert m.stalled(60_000 + 30_000) == []         # 직전 분 = 0분대 60건 · 나이 31초
    assert m.stalled(120_000 + 1_000) == ["markprice"]   # 직전 분(1분대) 0건


def test_a_stream_that_never_delivered_is_stalled_only_after_grace_from_start():
    """한 번도 안 온 스트림: *판단 보류*로 영원히 두지 않되, **막 켠 순간**에 울리지도 않는다."""
    c = DeliveryCounter(("markprice", "kline1m"), start_ms=10 * M)
    assert c.stalled(10 * M + 1_000) == []
    assert c.stalled(10 * M + 120_001) == ["markprice", "kline1m"]


def test_streams_are_judged_independently_not_aggregated():
    c = DeliveryCounter(("kline1m", "markprice"), start_ms=0)
    now = 10 * M
    for i in range(600):
        c.observe("kline1m", now - (599 - i) * 250)
    assert c.stalled(now) == ["markprice"]


def test_b3_an_empty_wall_clock_minute_counts_as_zero_not_the_last_observed_minute():
    """🔴 B3 — 5분대 60건 → 6분대 **0건** → 지금 7분 10초. 나이(71초)로는 안 잡히고 빈 분으로만 잡힌다."""
    c = DeliveryCounter(("markprice",), start_ms=0)
    for i in range(60):
        c.observe("markprice", 5 * M + i * 1000)
    now = 7 * M + 10_000
    assert c.snapshot(now)["markprice"]["prev_minute_count"] == 0
    assert c.stalled(now) == ["markprice"]


def test_a_minute_that_started_before_observation_is_not_evidence():
    c = DeliveryCounter(("markprice",), start_ms=5 * M + 30_000)
    c.observe("markprice", 5 * M + 31_000)
    now = 6 * M + 10_000
    assert c.snapshot(now)["markprice"]["prev_minute_count"] is None
    assert c.stalled(now) == []


def test_unknown_streams_raise_instead_of_being_dropped():
    with pytest.raises(KeyError):
        DeliveryCounter(("nope",), start_ms=0)
    c = DeliveryCounter(("kline1m",), start_ms=0)
    with pytest.raises(KeyError):
        c.observe("markprice", 0)


# ── 재생 어댑터 ─────────────────────────────────────────────────────
def test_replay_judges_exactly_like_the_live_counter(tmp_path):
    ts = [T0 + 5 * M + i * 1000 for i in range(60)] + [T0 + 7 * M + 5_000]
    _write_shards(tmp_path, "markprice", ts)
    for now in (T0 + 6 * M + 30_000, T0 + 7 * M + 30_000, T0 + 8 * M + 1_000,
                T0 + 9 * M + 10_000):
        live = DeliveryCounter(("markprice",), start_ms=T0)
        for t in ts:
            if t <= now:
                live.observe("markprice", t)
        L = D.prev_minute_of(now)
        sc = scan_window(tmp_path, "markprice", now - 720_000, now, count_minute=L)
        assert sc.minute_count == live.snapshot(now)["markprice"]["prev_minute_count"], now
        assert stalled_from_scan(sc, now_ms=now, start_ms=T0) == \
            (live.stalled(now) == ["markprice"]), now


def test_scan_reads_the_writer_column_not_recv_ms(tmp_path):
    _write_shards(tmp_path, "kline1m", [T0 + 1000, T0 + 2000],
                  extra={"recv_ms": lambda t: t + 999_999})
    sc = scan_window(tmp_path, "kline1m", T0, T0 + 10_000)
    assert (sc.rows, sc.first_ms, sc.last_ms) == (2, T0 + 1000, T0 + 2000)


def test_c3_a_shard_filed_under_yesterday_is_seen_just_after_midnight(tmp_path):
    ts = [T0 - 30_000 + i * 1000 for i in range(55)]
    _write_shards(tmp_path, "markprice", ts)
    assert not (tmp_path / _iso(T0).strftime("%Y-%m-%d")).exists()
    now = T0 + 60_000
    fs = window_files(tmp_path, "markprice", now - 720_000, now)
    assert len(fs) == 1 and _iso(T0 - DAY).strftime("%Y-%m-%d") in str(fs[0])
    sc = scan_window(tmp_path, "markprice", now - 720_000, now, count_minute=D.prev_minute_of(now))
    assert sc.last_ms == T0 + 24_000
    assert stalled_from_scan(sc, now_ms=now, start_ms=now - 720_000) is False


def test_gap_between_shard_files_is_an_interior_silence(tmp_path):
    ts = [T0 + i * 1000 for i in range(60)] + [T0 + 400_000 + i * 1000 for i in range(60)]
    _write_shards(tmp_path, "markprice", ts)
    sc = scan_window(tmp_path, "markprice", T0, T0 + 460_000)
    assert sc.max_interior_gap_ms == 400_000 - 59_000
    assert sc.interior_over_grace == 1


def test_unreadable_shards_are_counted_not_silently_skipped(tmp_path):
    sd = tmp_path / _iso(T0).strftime("%Y-%m-%d") / "markprice"
    sd.mkdir(parents=True)
    (sd / "000000_000.parquet").write_bytes(b"not parquet")
    summ = silence_summary("markprice", [scan_window(tmp_path, "markprice", T0, T0 + 60_000)])
    assert summ["unreadable_files"] == 1 and summ["ok"] is False


def test_c4_boundary_silence_at_both_ends_counts_even_with_no_interior_gap(tmp_path):
    ts = [T0 + 600_000 + i * 1000 for i in range(2401)]
    _write_shards(tmp_path, "markprice", ts)
    sc = scan_window(tmp_path, "markprice", T0, T0 + 3_600_000)
    assert sc.interior_over_grace == 0
    summ = silence_summary("markprice", [sc])
    assert summ["silences_beyond_grace"] == 2
    assert summ["max_silence_sec"] == 600.0
    assert summ["ok"] is False


def test_an_expected_stream_with_no_rows_is_not_ok():
    summ = silence_summary("kline1m", [D.WindowScan("kline1m", T0, T0 + 3_600_000)])
    assert summ == dict(summ, rows=0, ok=False, silences_beyond_grace=1, max_silence_sec=3600.0)
