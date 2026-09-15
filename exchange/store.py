"""`runtime_rules` 테이블 — 기동 시 조회한 규칙 원문 + 조회 시각(드리프트 감사·복기 재현용).

DDL은 layer 4 `db/schema.py` v1로 흡수됐다 — 여기서는 `db.migrate.migrate`로 스키마를 보장하고 행만 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from typing import Any

from db.migrate import migrate
from exchange.loader_types import RawFetch

MODES = ("paper", "live")

def ensure(con: sqlite3.Connection) -> None:
    """스키마는 `db.migrate`만 만든다(v1이 이 테이블을 흡수 · 2026-09-15)."""
    migrate(con)


def persist_fetches(con: sqlite3.Connection, fetches: Iterable[RawFetch], *, mode: str, source: str) -> str:
    if mode not in MODES:
        raise ValueError(f"mode={mode!r} — {MODES} 중 하나")
    ensure(con)
    load_id = uuid.uuid4().hex
    with con:
        for f in fetches:
            payload = json.dumps(f.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            con.execute(
                "INSERT INTO runtime_rules(load_id,endpoint,path,symbol,mode,source,fetched_at_utc,"
                "payload_json,payload_sha256) VALUES(?,?,?,?,?,?,?,?,?)",
                (load_id, f.endpoint, f.path, f.symbol, mode, source, f.fetched_at_utc, payload,
                 hashlib.sha256(payload.encode()).hexdigest()))
    return load_id


def latest_payload(con: sqlite3.Connection, endpoint: str, symbol: str) -> Any | None:
    ensure(con)
    row = con.execute("SELECT payload_json FROM runtime_rules WHERE endpoint=? AND symbol=? "
                      "ORDER BY fetched_at_utc DESC, id DESC LIMIT 1", (endpoint, symbol)).fetchone()
    return None if row is None else json.loads(row[0])
