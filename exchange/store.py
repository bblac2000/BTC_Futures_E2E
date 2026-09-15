"""`runtime_rules` 테이블 — 기동 시 조회한 규칙 원문 + 조회 시각(드리프트 감사·복기 재현용).

TODO(layer 4): `db/` 버전 마이그레이션 도구가 이 DDL을 schema v1로 흡수한다. 그 전까지 여기서
`CREATE TABLE IF NOT EXISTS`만 한다(ALTER 금지 — 스키마 변경은 마이그레이션 도구로만).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from typing import Any

from exchange.loader_types import RawFetch

MODES = ("paper", "live")

DDL = """
CREATE TABLE IF NOT EXISTS runtime_rules(
    id INTEGER PRIMARY KEY,
    load_id TEXT NOT NULL,              -- 한 번의 로드(엔드포인트 묶음)
    endpoint TEXT NOT NULL,             -- exchangeInfo | leverageBracket | ...
    path TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('paper','live')),
    source TEXT NOT NULL,               -- rest | snapshot:<path>
    fetched_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runtime_rules_ep ON runtime_rules(endpoint, symbol, fetched_at_utc);
"""


def ensure(con: sqlite3.Connection) -> None:
    con.executescript(DDL)


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
