# ── PROVENANCE ─────────────────────────────────────────────────────────────
# Ported from: /home/cms/project/E2E_Hybrid_Bot/e2e/l2_collector.py
#   ShardWriter (:143-191) · WriterThread run/final flush (:193-303) · _safe_log · Collector._shutdown_record (:590-614)
# Source commit: 90d47aa (#138 + Codex re-review Q1·Q2) · E2E HEAD f1e7d86 · ported 2026-09-15
# Local changes (logged in docs/ops_log.md):
#   - writers are a dict keyed by delivery kind (kline1m_update · kline1m_close · markprice) instead of
#     depth/trade/bookTicker attributes; no depth1s downsampling (no depth stream here)
#   - schemas are this bot's; prices/quantities are exact Decimal strings (pa.string), not float64
#   - root/symbol/monotonic clock injected (tests) instead of module paths; SHARD_SEC unchanged (60)
#   - a shard whose name already exists gets a `_n` suffix instead of being silently overwritten by rename
#   - socket lifecycle events ("event", (kind, detail)) are written to the manifest **by this thread**
#     (never from the asyncio feed loop); failures counted in `event_errors`
#   - `shutdown_record` is a free function; dropped rows (queue full) also make the record `stop_dirty`
#   - `Recorder` = the queue/put/stop part of E2E `Collector` (no websocket code here — ccxt.pro owns sockets)
#   - #138 behaviour unchanged: per-writer roll isolation + `roll_failed` event, dispatch errors recorded
#     without killing the thread, per-writer final flush with `final_flush_failed`, `_safe_log` in handlers,
#     no manifest writes during the final flush
# ───────────────────────────────────────────────────────────────────────────
"""layer 5 기록 — 60초 shard parquet(원자적) + 대장.

리더(ccxt.pro 수신 루프)는 bounded queue에 넣기만 하고, parquet·sqlite 쓰기는 전부 전용 writer 스레드에서 한다.
크래시 손실 ≤ 현재 shard(≤ 60초). 큐 포화는 드롭을 세고 종료 기록을 `stop_dirty`로 만든다(침묵 유실 금지).

경로: `<root>/<YYYY-MM-DD>/<kind>/<HHMMSS_mmm>.parquet` — 날짜·이름 = 첫 행의 **거래소 이벤트 시각**
(`ops.delivery_counter.TS_COLUMN`). 재생 감시(`scan_window`)가 같은 경로·열을 읽는다.
"""
from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from data import manifest

if TYPE_CHECKING:                        # data.feed가 이 모듈의 행 생성기를 쓴다(순환 import 방지)
    from data.feed import KlineEvent
    from paper.types import MarkTick

SHARD_SEC = 60
QUEUE_MAX = 50_000
EVENT_SOURCE = "feed"
RAW_LIVE = manifest.ROOT / "var" / "raw" / "live"

_KLINE = pa.schema([
    ("event_time", pa.int64()), ("open_time", pa.int64()), ("close_time", pa.int64()),
    ("open", pa.string()), ("high", pa.string()), ("low", pa.string()), ("close", pa.string()),
    ("volume", pa.string()), ("quote_volume", pa.string()), ("trades", pa.int64()),
    ("taker_buy_base", pa.string()), ("taker_buy_quote", pa.string()), ("closed", pa.bool_()),
    ("recv_ms", pa.int64()),
])
_MARKPRICE = pa.schema([
    ("event_time", pa.int64()), ("mark_price", pa.string()), ("index_price", pa.string()),
    ("est_settle_price", pa.string()), ("funding_rate", pa.string()), ("next_funding_time", pa.int64()),
    ("recv_ms", pa.int64()),
])
#  kline1m_close는 x=true 행만 따로 둔다 — 재생 감시가 kind마다 dir 하나를 센다(레지스트리 #1)
SCHEMAS: dict[str, pa.Schema] = {"kline1m_update": _KLINE, "kline1m_close": _KLINE, "markprice": _MARKPRICE}
TS_INDEX: dict[str, int] = {k: s.names.index("event_time") for k, s in SCHEMAS.items()}


def kline_row(k: KlineEvent, *, recv_ms: int) -> tuple:
    return (k.event_ms, k.open_ms, k.close_ms, str(k.open), str(k.high), str(k.low), str(k.close), str(k.volume),
            str(k.quote_volume), k.trades, str(k.taker_buy_base), str(k.taker_buy_quote), k.closed, recv_ms)


def markprice_row(t: MarkTick, raw: dict, *, recv_ms: int) -> tuple:
    """보조 필드(index `i` · 추정 정산가 `P`)는 원시 문자열 그대로, 없으면 null — 엔진 입력이 아니라 기록용."""
    def opt(key: str) -> str | None:
        v = raw.get(key) if isinstance(raw, dict) else None
        return None if v is None else str(v)
    return (t.ts_ms, str(t.mark), opt("i"), opt("P"), str(t.funding_rate), t.next_funding_ms, recv_ms)


def log(msg: str) -> None:
    print(f"{manifest.utcnow()} {msg}", flush=True)


def _safe_log(msg: str) -> None:
    """**예외 처리기 안에서만** 쓰는 로그 — 절대 다시 던지지 않는다(E2E #138)."""
    try:
        log(msg)
    except Exception:                    # noqa: BLE001
        pass


class ShardWriter:
    """60초 shard: 메모리 버퍼 → 완성 파일 tmp 작성 → atomic rename → manifest."""

    def __init__(self, name: str, schema: pa.Schema, source: str, *, root: Path, symbol: str, ts_index: int,
                 monotonic: Callable[[], float] = time.monotonic):
        self.name, self.schema, self.source = name, schema, source
        self.root, self.symbol, self.ts_index = Path(root), symbol, ts_index
        self.monotonic = monotonic
        self.rows: list[tuple] = []
        self.opened_mono: float | None = None
        self.manifest_errors = 0

    def add(self, row: tuple) -> None:
        if not self.rows:
            self.opened_mono = self.monotonic()
        self.rows.append(row)

    def due(self) -> bool:
        return bool(self.rows) and self.opened_mono is not None and self.monotonic() - self.opened_mono >= SHARD_SEC

    def roll(self) -> None:
        if not self.rows:
            return
        first_ms = self.rows[0][self.ts_index]
        tm = time.gmtime(first_ms / 1000)
        date = time.strftime("%Y-%m-%d", tm)
        stamp = time.strftime("%H%M%S", tm) + f"_{first_ms % 1000:03d}"
        d = self.root / date / self.name
        d.mkdir(parents=True, exist_ok=True)
        #  🔴 rename은 기존 파일을 조용히 덮는다 — 같은 첫 이벤트 시각이면 접미사(`_file_start_ms`는 None → 건너뛰지 않음)
        name, n = stamp, 0
        while (d / f"{name}.parquet").exists():
            n += 1
            name = f"{stamp}_{n}"
        path, tmp = d / f"{name}.parquet", d / f".{name}.tmp"
        cols = list(zip(*self.rows, strict=True))
        table = pa.table({self.schema.field(i).name: pa.array(c, type=self.schema.field(i).type)
                          for i, c in enumerate(cols)}, schema=self.schema)
        pq.write_table(table, tmp, compression="zstd")
        tmp.rename(path)
        #  🔴 E2E 2026-08-15: 대장 등록 예외가 writer 스레드를 죽였다. 파일은 이미 안전 — 실패는 센다(삼키지 않는다).
        if not manifest.register_shard(self.source, self.symbol, f"{date}T{name}", path,
                                       parquet_path=str(path), parquet_rows=len(self.rows)):
            self.manifest_errors += 1
            log(f"⚠️ 대장 등록 실패(파일은 안전) {path.name} n={self.manifest_errors}")
        self.rows = []


def default_writers(root: Path, symbol: str, *, monotonic: Callable[[], float] = time.monotonic) -> dict[str, ShardWriter]:
    return {k: ShardWriter(k, s, f"live_{k}", root=root, symbol=symbol, ts_index=TS_INDEX[k], monotonic=monotonic)
            for k, s in SCHEMAS.items()}


class WriterThread(threading.Thread):
    """큐 소비 전담. parquet·sqlite 쓰기는 전부 이 스레드에서만 일어난다."""

    def __init__(self, q: queue.Queue, writers: dict[str, ShardWriter]):
        super().__init__(name="feed-writer", daemon=True)
        self.q, self.writers = q, writers
        #  🔴 종료 플러시에서 실패한 writer 이름(#138). 비어 있지 않으면 clean이 아니다.
        self.final_flush_failed: list[str] = []
        #  🔴 dispatch에서 난 예외(#138 Q1). 스레드를 죽이지 않고 계속 비우되, 있었다는 사실은 남긴다.
        self.fatal_error: str | None = None
        self.dispatch_errors = 0
        self.event_errors = 0

    def run(self) -> None:
        while True:
            try:
                item = self.q.get(timeout=1)
            except queue.Empty:
                item = None
            if item is not None:
                kind = item[0] if isinstance(item, tuple) and item else None
                if kind == "stop":
                    break
                try:
                    _, payload = item
                    if kind == "event":
                        self._event(*payload)
                    elif isinstance(kind, str) and kind in self.writers:
                        self.writers[kind].add(payload)
                    else:
                        raise KeyError(f"모르는 기록 kind {kind!r}")
                except Exception as e:       # noqa: BLE001
                    self.dispatch_errors += 1
                    self.fatal_error = self.fatal_error or f"dispatch {kind}: {type(e).__name__}: {e}"
                    if self.dispatch_errors == 1 or self.dispatch_errors % 1000 == 0:
                        _safe_log(f"🔴 writer dispatch 실패 {kind} n={self.dispatch_errors}: {type(e).__name__}: {e}")
            #  🔴 writer 하나가 던져도 스레드 전체를 죽이지 않는다(E2E 2026-08-15) — 나머지 스트림은 계속 기록
            for w in self.writers.values():
                if w.due():
                    try:
                        w.roll()
                    except Exception as e:   # noqa: BLE001
                        _safe_log(f"🔴 shard roll 실패 {w.name}: {type(e).__name__}: {e}")
                        try:
                            manifest.log_event(EVENT_SOURCE, "roll_failed", f"{w.name} {type(e).__name__}: {e}")
                        except Exception:    # noqa: BLE001
                            pass
                        w.rows = []          # 같은 실패를 무한 반복하지 않는다
        #  🔴 #138: writer마다 따로 시도하고 실패는 이름을 남긴다. 🚫 여기서 대장에 쓰지 않는다(락이면 매달린다).
        for w in self.writers.values():
            try:
                w.roll()
            except Exception as e:           # noqa: BLE001
                self.final_flush_failed.append(w.name)
                _safe_log(f"🔴 종료 플러시 실패 {w.name}: {type(e).__name__}: {e} (행 {len(w.rows)}개 유실)")

    def _event(self, kind: str, detail: str) -> None:
        """소켓 수명 이벤트(connect·disconnect·reconnect) — 대장 실패는 세고 넘어간다(수집을 죽이지 않는다)."""
        try:
            manifest.log_event(EVENT_SOURCE, kind, detail)
        except Exception as e:               # noqa: BLE001
            self.event_errors += 1
            _safe_log(f"⚠️ 이벤트 대장 기록 실패 {kind} n={self.event_errors}: {type(e).__name__}: {e}")


def shutdown_record(writer: Any, *, dropped: int) -> tuple[str, str]:
    """종료 기록. 🔴 clean은 모두 통과해야 한다(E2E DR03-A1 · #138 · Codex 재검토 Q1):
    ① writer가 제한 시간 안에 끝났다 ⓪ dispatch 예외 없음 ② 종료 플러시 실패 writer 없음 ③ 큐 포화 드롭 없음."""
    if writer.is_alive():
        return ("stop_dirty", f"writer 제한 시간 내 미완료 — 마지막 shard 유실 가능, dropped={dropped}")
    if getattr(writer, "fatal_error", None):
        return ("stop_dirty", f"writer dispatch 실패 {writer.fatal_error} "
                              f"(n={getattr(writer, 'dispatch_errors', '?')}) — 행 유실, dropped={dropped}")
    if writer.final_flush_failed:
        return ("stop_dirty", f"종료 플러시 실패 {','.join(writer.final_flush_failed)} — 그 스트림의 마지막 shard 유실, "
                              f"dropped={dropped}")
    if dropped:
        return ("stop_dirty", f"큐 포화로 행 유실, dropped={dropped}")
    return ("stop", f"clean shutdown, dropped={dropped}")


class Recorder:
    """피드 → writer 스레드 연결. `put`·`event`는 블록하지도 던지지도 않는다(ccxt 수신 루프 안에서 불린다)."""

    def __init__(self, root: Path = RAW_LIVE / "BTCUSDT", symbol: str = "BTCUSDT", *, queue_max: int = QUEUE_MAX,
                 monotonic: Callable[[], float] = time.monotonic):
        self.q: queue.Queue = queue.Queue(maxsize=queue_max)
        self.writer = WriterThread(self.q, default_writers(Path(root), symbol, monotonic=monotonic))
        self.dropped = 0
        self.dropped_events = 0

    def start(self) -> None:
        self.writer.start()

    def put(self, kind: str, row: tuple) -> None:
        try:
            self.q.put_nowait((kind, row))
        except queue.Full:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 1000 == 0:
                _safe_log(f"🔴 기록 큐 포화 — 행 드롭 n={self.dropped}")

    def event(self, kind: str, detail: str) -> None:
        try:
            self.q.put_nowait(("event", (kind, detail)))
        except queue.Full:
            self.dropped_events += 1
            _safe_log(f"🔴 기록 큐 포화 — 이벤트 드롭 {kind} {detail}")

    def stop(self, *, timeout: float = 30.0) -> tuple[str, str]:
        try:
            self.q.put(("stop", ()), timeout=timeout)
        except queue.Full:
            pass                                            # writer가 멈춰 있다 → is_alive로 dirty
        self.writer.join(timeout=timeout)
        kind, detail = shutdown_record(self.writer, dropped=self.dropped)
        try:
            manifest.log_event(EVENT_SOURCE, kind, detail)
        except Exception as e:                              # noqa: BLE001
            _safe_log(f"🔴 종료 기록 대장 실패 {kind}: {type(e).__name__}: {e}")
        log(("⚠️ DIRTY shutdown — " if kind == "stop_dirty" else "") + detail)
        return kind, detail
