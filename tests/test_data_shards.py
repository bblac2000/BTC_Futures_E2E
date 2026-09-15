"""layer 5 기록 — E2E `ShardWriter`·`WriterThread`(#138 종료 플러시)·`_shutdown_record` 이식본.

- 60초 shard: 메모리 → tmp 완성 → atomic rename → `manifest.register_shard`(무예외, 실패는 센다)
- 파일 경계·날짜 dir = 거래소 이벤트 시각 열(`ops.delivery_counter.TS_COLUMN`) — 재생 감시가 같은 열을 센다
- 가격·수량은 **Decimal 문자열 그대로**(float 변환 없음)
- #138: writer 하나의 종료 플러시 실패가 뒤 writer를 지우지 않는다 · dispatch 예외는 기록하고 계속 비운다 ·
  처리기 안 로그 실패도 스레드를 죽이지 않는다 · 종료 플러시 중에는 대장에 쓰지 않는다 ·
  clean(`stop`)은 writer 종료 + dispatch 오류 없음 + 플러시 실패 없음일 때만, 아니면 `stop_dirty`
"""
from __future__ import annotations

import queue
import sqlite3
from decimal import Decimal
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from data import manifest
from data import shards as S
from data.feed import KlineEvent
from ops.delivery_counter import TS_COLUMN, scan_window
from paper.types import MarkTick

T0 = 1_789_430_400_000            # 2026-09-15 00:00:00 UTC
D = Decimal


@pytest.fixture(autouse=True)
def tmp_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "MANIFEST_DB", tmp_path / "manifest.sqlite")
    return tmp_path / "manifest.sqlite"


def rows_of(db, sql):
    with sqlite3.connect(db) as con:
        return con.execute(sql).fetchall()


def kline(E, closed=False, c="60010.50"):
    return KlineEvent(event_ms=E, open_ms=T0, close_ms=T0 + 59_999, open=D("60000.10"), high=D("60020.00"),
                      low=D("59990.20"), close=D(c), volume=D("12.345"), quote_volume=D("740000.5"), trades=77,
                      taker_buy_base=D("6.100"), taker_buy_quote=D("366000.2"), closed=closed)


def mark_row(E):
    return S.markprice_row(MarkTick(E, D("60001.20"), D("0.00010000"), T0 + 8 * 3_600_000),
                           {"i": "60003.4", "P": "60002.0"}, recv_ms=E + 90)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ── 스키마 · 행 ─────────────────────────────────────────────────────────────
def test_every_delivery_kind_has_a_writer_whose_boundary_column_is_the_replay_column():
    """🔴 라이브 카운터·shard 경계·재생 감시가 **같은 시계**를 센다(E2E #134 교훈)."""
    assert set(S.SCHEMAS) == set(TS_COLUMN)
    for kind, schema in S.SCHEMAS.items():
        assert S.TS_INDEX[kind] == schema.names.index(TS_COLUMN[kind])


def test_rows_keep_exact_decimal_strings_not_floats():
    r = S.kline_row(kline(T0 + 5, c="60010.50"), recv_ms=T0 + 40)
    schema = S.SCHEMAS["kline1m_update"]
    d = dict(zip(schema.names, r, strict=True))
    assert d["event_time"] == T0 + 5 and d["close"] == "60010.50" and d["taker_buy_base"] == "6.100"
    assert d["closed"] is False and d["trades"] == 77 and d["recv_ms"] == T0 + 40
    m = dict(zip(S.SCHEMAS["markprice"].names, mark_row(T0 + 7), strict=True))
    assert m["mark_price"] == "60001.20" and m["funding_rate"] == "0.00010000" and m["index_price"] == "60003.4"
    assert S.markprice_row(MarkTick(T0, D("1"), D("0"), T0), {}, recv_ms=T0)[2] is None     # 없는 보조 필드는 null


# ── ShardWriter ─────────────────────────────────────────────────────────────
def writer(tmp_path, kind="markprice", clock=None):
    return S.ShardWriter(kind, S.SCHEMAS[kind], f"live_{kind}", root=tmp_path / "raw", symbol="BTCUSDT",
                         ts_index=S.TS_INDEX[kind], monotonic=clock or Clock())


def test_roll_writes_an_atomic_shard_named_by_the_first_event_time_and_registers_it(tmp_path, tmp_manifest):
    w = writer(tmp_path)
    first = T0 + 3_600_000 + 5_123                                  # 01:00:05.123 UTC
    w.add(mark_row(first))
    w.add(mark_row(first + 1000))
    w.roll()
    path = tmp_path / "raw" / "2026-09-15" / "markprice" / "010005_123.parquet"
    assert path.exists() and not list(path.parent.glob(".*.tmp")) and w.rows == []
    t = pq.read_table(path)
    assert t.schema == S.SCHEMAS["markprice"] and t.column("mark_price").to_pylist() == ["60001.20", "60001.20"]
    assert rows_of(tmp_manifest, "SELECT source, symbol, period, parquet_rows, status FROM files") == [
        ("live_markprice", "BTCUSDT", "2026-09-15T010005_123", 2, "converted")]


def test_manifest_failure_never_raises_and_is_counted_the_file_is_already_safe(tmp_path, monkeypatch):
    w = writer(tmp_path)

    def locked(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(manifest, "upsert_file", locked)
    w.add(mark_row(T0))
    w.roll()
    assert w.manifest_errors == 1 and list((tmp_path / "raw").rglob("*.parquet"))


def test_same_first_event_time_never_overwrites_an_existing_shard(tmp_path):
    w = writer(tmp_path)
    for _ in range(2):
        w.add(mark_row(T0))
        w.roll()
    files = sorted(p.name for p in (tmp_path / "raw").rglob("*.parquet"))
    assert files == ["000000_000.parquet", "000000_000_1.parquet"]


def test_due_after_shard_seconds_by_the_injected_monotonic_clock(tmp_path):
    c = Clock()
    w = writer(tmp_path, clock=c)
    assert not w.due()
    w.add(mark_row(T0))
    c.t += S.SHARD_SEC - 0.001
    assert not w.due()
    c.t += 0.002
    assert w.due()


def test_replay_scan_reads_what_the_writer_wrote(tmp_path):
    """재생 어댑터(`scan_window`)가 이 writer의 파일을 그대로 센다 — 경로 규칙·열 이름이 일치."""
    root = tmp_path / "raw"
    for kind in S.SCHEMAS:
        w = S.ShardWriter(kind, S.SCHEMAS[kind], f"live_{kind}", root=root, symbol="BTCUSDT",
                          ts_index=S.TS_INDEX[kind], monotonic=Clock())
        for i in range(3):
            E = T0 + 1000 + i * 1000
            w.add(mark_row(E) if kind == "markprice" else S.kline_row(kline(E, closed=kind == "kline1m_close"), recv_ms=E))
        w.roll()
        sc = scan_window(root, kind, T0, T0 + 60_000)
        assert sc.rows == 3 and sc.first_ms == T0 + 1000 and sc.unreadable_files == 0, kind


# ── WriterThread (#138) ─────────────────────────────────────────────────────
def thread_with_fake_rolls(tmp_path):
    w = S.WriterThread(queue.Queue(), S.default_writers(tmp_path / "raw", "BTCUSDT"))
    flushed: list[str] = []

    def ok_roll(wr):
        def _r():
            flushed.append(wr.name)
            wr.rows = []
        return _r
    for wr in w.writers.values():
        wr.add((1,) * len(wr.schema))
        wr.roll = ok_roll(wr)
    return w, flushed


def test_final_flush_failure_of_one_writer_does_not_drop_the_writers_after_it(tmp_path):
    w, flushed = thread_with_fake_rolls(tmp_path)
    first = next(iter(w.writers.values()))

    def boom():
        raise OSError("disk full")
    first.roll = boom
    w.q.put(("stop", ()))
    w.run()                                                         # 🚫 예외가 새면 안 된다
    assert w.final_flush_failed == [first.name]
    assert flushed == [n for n in w.writers if n != first.name]


def test_dispatch_exception_is_recorded_and_draining_and_final_flush_continue(tmp_path):
    w, flushed = thread_with_fake_rolls(tmp_path)
    w.q.put(("nonsense-kind", (1,)))                                # 모르는 kind → dispatch 오류
    w.q.put(("markprice", mark_row(T0)))                            # 오류 뒤에도 계속 비운다
    w.q.put(("stop", ()))
    w.run()
    assert w.dispatch_errors == 1 and w.fatal_error is not None and "nonsense-kind" in w.fatal_error
    assert flushed == list(w.writers)


def test_a_logging_failure_inside_the_flush_handler_does_not_stop_later_writers(tmp_path, monkeypatch):
    w, flushed = thread_with_fake_rolls(tmp_path)
    first = next(iter(w.writers.values()))

    def broken_log(msg):
        raise BrokenPipeError("stdout closed")
    monkeypatch.setattr(S, "log", broken_log)

    def boom():
        raise OSError("disk")
    first.roll = boom
    w.q.put(("stop", ()))
    w.run()
    assert w.final_flush_failed == [first.name] and flushed == [n for n in w.writers if n != first.name]


def test_final_flush_never_writes_to_the_manifest(tmp_path, monkeypatch):
    """종료 roll 실패의 1순위 원인이 대장 락 — 그 상태에서 대장에 쓰면 매달린다(E2E 08-15)."""
    w, _ = thread_with_fake_rolls(tmp_path)
    calls = []
    monkeypatch.setattr(manifest, "log_event", lambda *a, **k: calls.append(a))

    def boom():
        raise OSError("x")
    for wr in w.writers.values():
        wr.roll = boom
    w.q.put(("stop", ()))
    w.run()
    assert calls == [] and w.final_flush_failed == list(w.writers)


def test_roll_failure_while_running_is_isolated_logged_to_the_manifest_and_not_repeated(tmp_path, tmp_manifest):
    c = Clock()
    writers = S.default_writers(tmp_path / "raw", "BTCUSDT", monotonic=c)
    w = S.WriterThread(queue.Queue(), writers)

    def boom():
        raise OSError("disk full")
    writers["markprice"].roll = boom
    writers["markprice"].add(mark_row(T0))
    writers["kline1m_update"].add(S.kline_row(kline(T0), recv_ms=T0))
    c.t += S.SHARD_SEC + 1
    w.q.put(("event", ("connect", "x")))                            # 한 바퀴 돌며 due 검사
    w.q.put(("stop", ()))
    w.run()
    assert writers["markprice"].rows == []                          # 같은 실패를 무한 반복하지 않는다
    assert list((tmp_path / "raw").rglob("*.parquet"))              # 다른 스트림은 기록됐다
    assert rows_of(tmp_manifest, "SELECT source, kind FROM events ORDER BY id") == [("feed", "connect"), ("feed", "roll_failed")]


def test_socket_events_are_written_by_the_writer_thread_and_failures_are_counted(tmp_path, tmp_manifest, monkeypatch):
    w = S.WriterThread(queue.Queue(), S.default_writers(tmp_path / "raw", "BTCUSDT"))
    w.q.put(("event", ("connect", "wss://x/market/ws/0 btcusdt@kline_1m")))
    w.q.put(("stop", ()))
    w.run()
    assert rows_of(tmp_manifest, "SELECT source, kind, detail FROM events") == [
        ("feed", "connect", "wss://x/market/ws/0 btcusdt@kline_1m")]
    w2 = S.WriterThread(queue.Queue(), S.default_writers(tmp_path / "raw2", "BTCUSDT"))

    def locked(*a, **k):
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(manifest, "log_event", locked)
    w2.q.put(("event", ("reconnect", "x")))
    w2.q.put(("stop", ()))
    w2.run()
    assert w2.event_errors == 1 and w2.fatal_error is None


# ── Recorder: 큐 · 종료 기록 ──────────────────────────────────────────────────
def test_shutdown_record_is_clean_only_when_all_three_conditions_hold():
    ok = SimpleNamespace(is_alive=lambda: False, fatal_error=None, dispatch_errors=0, final_flush_failed=[])
    assert S.shutdown_record(ok, dropped=0)[0] == "stop"
    kind, detail = S.shutdown_record(SimpleNamespace(**{**vars(ok), "is_alive": lambda: True}), dropped=3)
    assert kind == "stop_dirty" and "dropped=3" in detail
    kind, detail = S.shutdown_record(SimpleNamespace(**{**vars(ok), "fatal_error": "dispatch x"}), dropped=0)
    assert kind == "stop_dirty" and "dispatch x" in detail
    kind, detail = S.shutdown_record(SimpleNamespace(**{**vars(ok), "final_flush_failed": ["markprice"]}), dropped=0)
    assert kind == "stop_dirty" and "markprice" in detail


def test_dropped_rows_make_the_shutdown_dirty():
    """큐 포화로 버린 행이 있으면 clean이라 쓰지 않는다(침묵 유실 금지)."""
    ok = SimpleNamespace(is_alive=lambda: False, fatal_error=None, dispatch_errors=0, final_flush_failed=[])
    assert S.shutdown_record(ok, dropped=1)[0] == "stop_dirty"


def test_recorder_put_never_blocks_counts_drops_and_stop_writes_the_shutdown_record(tmp_path, tmp_manifest):
    rec = S.Recorder(tmp_path / "raw", "BTCUSDT", queue_max=2)
    rec.put("markprice", mark_row(T0))
    rec.put("markprice", mark_row(T0 + 1000))
    rec.put("markprice", mark_row(T0 + 2000))                       # 가득 참 — 스레드 시작 전
    assert rec.dropped == 1
    rec.q.get_nowait()                                              # 종료 표지를 넣을 자리
    rec.start()
    kind, _ = rec.stop(timeout=10)
    assert kind == "stop_dirty"
    assert ("feed", "stop_dirty") in rows_of(tmp_manifest, "SELECT source, kind FROM events")
    assert len(pq.read_table(next((tmp_path / "raw").rglob("*.parquet"))).column("event_time")) == 1


def test_recorder_clean_stop_flushes_every_stream(tmp_path, tmp_manifest):
    rec = S.Recorder(tmp_path / "raw", "BTCUSDT")
    rec.start()
    rec.put("kline1m_update", S.kline_row(kline(T0 + 1), recv_ms=T0 + 2))
    rec.put("kline1m_close", S.kline_row(kline(T0 + 59_999, closed=True), recv_ms=T0 + 60_010))
    rec.put("markprice", mark_row(T0 + 3))
    rec.event("connect", "wss://x/market/ws/0")
    assert rec.stop(timeout=10) == ("stop", "clean shutdown, dropped=0")
    assert {p.parent.name for p in (tmp_path / "raw").rglob("*.parquet")} == set(S.SCHEMAS)
    kinds = [k for (k,) in rows_of(tmp_manifest, "SELECT kind FROM events ORDER BY id")]
    assert kinds == ["connect", "stop"]
