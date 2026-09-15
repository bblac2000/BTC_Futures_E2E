# ── PROVENANCE ─────────────────────────────────────────────────────────────
# Copied from: /home/cms/project/E2E_Hybrid_Bot/e2e/manifest.py
# Source commit: 23e5005 (E2E HEAD f1e7d86, 2026-09-14) · copied 2026-09-15
# Local changes:
#   - DB path is injected (MANIFEST_DB module attribute, default var/manifest.sqlite) instead of
#     `from .paths import MANIFEST_DB` — this repo has no e2e/paths.py; tests monkeypatch it
#   - source/kind comment examples rewritten for this bot (kline1m, markprice)
#   - logic of connect/upsert_file/register_shard/mark_pruned/log_event/record_gap unchanged
# ───────────────────────────────────────────────────────────────────────────
"""manifest.sqlite — 파일·행수·체크섬·수집공백 대장.

모든 데이터 파일의 출처·무결성·상태와, 수집기의 끊김/재연결 이벤트·커버리지 공백을
단일 sqlite에 기록한다. 🔴 수집기와 **공유 자원**이다 — 유지보수 쓰기가 락을 오래 잡으면
수집기 writer가 죽을 수 있다(E2E 2026-08-15 사고). 그래서 `register_shard`는 예외를 내보내지 않는다.
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DB = ROOT / "var" / "manifest.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,          -- 예: live_kline1m | live_markprice | backfill_kline1m
    symbol TEXT NOT NULL,
    period TEXT NOT NULL,          -- YYYY-MM-DD | YYYY-MM-DDTHHMMSS_mmm (shard)
    path TEXT NOT NULL,
    bytes INTEGER,
    sha256 TEXT,
    checksum_ref TEXT,
    checksum_match INTEGER,        -- 1/0/NULL(제공 없음)
    csv_rows INTEGER,
    parquet_path TEXT,
    parquet_rows INTEGER,
    status TEXT NOT NULL,          -- downloading|downloaded|verified|converted|failed|pruned
    error TEXT,
    note TEXT,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL,
    UNIQUE(source, symbol, period)
);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,            -- connect|disconnect|reconnect|gap|clock_skew|start|stop|stop_dirty|error
    detail TEXT
);
CREATE TABLE IF NOT EXISTS gaps(
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,            -- YYYY-MM-DD (UTC)
    start_utc TEXT NOT NULL,
    end_utc TEXT,                  -- NULL = 진행 중이던 공백(비정상 종료)
    seconds REAL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_gaps_date ON gaps(symbol, date);
"""


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


@contextmanager
def connect():
    MANIFEST_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(MANIFEST_DB, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(files)")]
    #  prune 시점의 **원격 md5**(Google Drive 서버측 MD5) — 다운로드 없이 비트 수준 검증.
    if "remote_md5" not in cols:
        con.execute("ALTER TABLE files ADD COLUMN remote_md5 TEXT")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert_file(source, symbol, period, path, status, **kw):
    cols = {"bytes", "sha256", "checksum_ref", "checksum_match",
            "csv_rows", "parquet_path", "parquet_rows", "error", "note"}
    extra = {k: v for k, v in kw.items() if k in cols}
    now = utcnow()
    with connect() as con:
        con.execute(
            """INSERT INTO files(source,symbol,period,path,status,created_utc,updated_utc)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(source,symbol,period) DO UPDATE SET
                 path=excluded.path, status=excluded.status, updated_utc=excluded.updated_utc""",
            (source, symbol, period, str(path), status, now, now))
        if extra:
            sets = ", ".join(f"{k}=?" for k in extra)
            con.execute(
                f"UPDATE files SET {sets}, updated_utc=? WHERE source=? AND symbol=? AND period=?",
                (*extra.values(), now, source, symbol, period))


def register_shard(source, symbol, period, path, **kw) -> bool:
    """shard 하나를 대장에 등록한다 — **실패해도 예외를 밖으로 내보내지 않는다.**

    🔴 E2E 2026-08-15 사고: 유지보수 스크립트가 SQLite 쓰기 락을 30초 넘게 잡아
       `upsert_file`이 timeout 예외를 던졌고, 그 예외가 writer 스레드를 죽였다.
       프로세스는 `active`인 채 9분 17초를 잃었다.
    ⚠️ `tmp.rename(path)`가 끝난 시점에 **데이터는 이미 안전하다.** 대장 등록은 부차적이다.
    🚫 그렇다고 **삼키지도 않는다** — 실패를 이벤트로 남기고, 미등록 파일은 대사가 고아로 잡는다.
    """
    try:
        upsert_file(source, symbol, period, path, "converted", **kw)
        return True
    except Exception as e:              # noqa: BLE001 — 어떤 예외든 수집을 죽이지 못한다
        try:
            log_event(str(source).split("_")[0] or "collector", "manifest_write_failed",
                      f"{source} {period} {type(e).__name__}: {e}")
        except Exception:               # noqa: BLE001 — 로그마저 실패하면 넘어간다
            pass
        return False


def mark_pruned(paths, note: str, sizes: dict | None = None,
                md5s: dict | None = None) -> int:
    """로컬에서 지운 파일을 대장에 **기록**한다 — 삭제를 날짜 산술로 추측하지 않기 위해.

    🚫 `status`만 바꾸고 **행을 지우지 않는다.** 무엇이 있었는지가 남아야 Drive 사본 검증이
       무엇을 확인할지 안다. ⚠️ 호출자는 반환값(기록한 행 수)을 지운 파일 수와 대조해야 한다
       (E2E #131 stage 0 — "지운 수와 대장에 기록한 수가 다르면 성공이 아니다").
    """
    if not paths:
        return 0
    now = utcnow()
    total = 0
    with connect() as con:
        con.execute("CREATE INDEX IF NOT EXISTS idx_files_ppath ON files(parquet_path)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
        vals = [str(p) for p in paths]
        for i in range(0, len(vals), 500):
            chunk = vals[i:i + 500]
            q = ",".join("?" * len(chunk))
            cur = con.execute(
                f"UPDATE files SET status='pruned', note=?, updated_utc=? "
                f"WHERE parquet_path IN ({q}) OR path IN ({q})",
                (note, now, *chunk, *chunk))
            total += cur.rowcount or 0
        if sizes:
            for i in range(0, len(vals), 500):
                con.executemany(
                    "UPDATE files SET bytes=? WHERE parquet_path=? OR path=?",
                    [(sizes[v], v, v) for v in vals[i:i + 500] if v in sizes])
        if md5s:
            for i in range(0, len(vals), 500):
                con.executemany(
                    "UPDATE files SET remote_md5=? WHERE parquet_path=? OR path=?",
                    [(md5s[v], v, v) for v in vals[i:i + 500] if v in md5s])
    return total


def file_status(source, symbol, period):
    with connect() as con:
        row = con.execute(
            "SELECT status FROM files WHERE source=? AND symbol=? AND period=?",
            (source, symbol, period)).fetchone()
    return row[0] if row else None


def log_event(source, kind, detail=""):
    with connect() as con:
        con.execute("INSERT INTO events(ts_utc,source,kind,detail) VALUES(?,?,?,?)",
                    (utcnow(), source, kind, detail))


def record_gap(source, symbol, date, start_utc, end_utc, seconds, reason):
    with connect() as con:
        con.execute(
            "INSERT INTO gaps(source,symbol,date,start_utc,end_utc,seconds,reason) VALUES(?,?,?,?,?,?,?)",
            (source, symbol, date, start_utc, end_utc, seconds, reason))
