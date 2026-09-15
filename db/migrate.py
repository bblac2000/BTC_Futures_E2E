"""버전 마이그레이션 도구 — 스키마 변경의 **유일한** 경로(strategy-modules §5).

    uv run python -m db.migrate var/bot.sqlite            # 최신까지 적용
    uv run python -m db.migrate var/bot.sqlite --status   # 현재 버전
    uv run python -m db.migrate var/bot.sqlite --target 1

fail-closed:
- 적용된 단계의 체크섬 ≠ 코드의 SQL → `SchemaError`(단계를 고쳤다 — 새 단계를 붙여야 한다)
- DB 버전 > 코드가 아는 최신 → `SchemaError`(옛 코드로 새 DB를 열었다)
- target < 현재 → `SchemaError`(다운그레이드 없음)
- 단계는 하나의 트랜잭션 — 실패하면 부분 적용 없이 롤백
- `schema_version` 없이 이미 있는 테이블(layer 1의 `runtime_rules` 등)은 단계의 정의와 **열 모양이 같을 때만** 흡수
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

from db.schema import MIGRATIONS, Migration

__all__ = ["LEGACY_RUNTIME_RULES_DDL", "MIGRATIONS", "Migration", "SchemaError", "current_version", "main", "migrate"]

#  layer 1 `exchange/store.py`가 schema v1 이전에 만들던 DDL(흡수 테스트용 원문 보존)
LEGACY_RUNTIME_RULES_DDL = """
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

VERSION_DDL = """CREATE TABLE IF NOT EXISTS schema_version(
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sql_sha256 TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
)"""


class SchemaError(RuntimeError):
    pass


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _statements(sql: str) -> list[str]:
    out, buf = [], ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())                       # 불완전 문장 — 실행하면 sqlite가 오류를 낸다
    return out


def _has_version_table(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone() is not None


def current_version(con: sqlite3.Connection) -> int:
    if not _has_version_table(con):
        return 0
    return int(con.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0])


def _table_shapes(con: sqlite3.Connection) -> dict[str, list[tuple]]:
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {n: [tuple(c[1:]) for c in con.execute(f"PRAGMA table_info('{n}')")] for n in names}


def _check_preexisting(con: sqlite3.Connection, step: Migration) -> None:
    """`IF NOT EXISTS`가 모양이 다른 옛 테이블을 조용히 통과시키지 않게 — 빈 DB에 단계를 돌려 열 모양을 비교."""
    scratch = sqlite3.connect(":memory:")
    try:
        for s in _statements(step.sql):
            scratch.execute(s)
        want = _table_shapes(scratch)
    finally:
        scratch.close()
    have = _table_shapes(con)
    for name, cols in want.items():
        if name in have and have[name] != cols:
            raise SchemaError(f"v{step.version}: 기존 테이블 {name}의 열 모양이 단계 정의와 다르다 — 흡수 불가")


def migrate(con: sqlite3.Connection, *, target: int | None = None) -> list[int]:
    """적용한 버전 목록을 돌려준다(이미 최신이면 빈 목록)."""
    migrations = MIGRATIONS
    latest = migrations[-1].version if migrations else 0
    target = latest if target is None else target
    if con.in_transaction:
        raise SchemaError("열린 트랜잭션이 있다 — 호출자 작업을 대신 커밋하지 않는다")
    applied = {}
    if _has_version_table(con):
        applied = {v: sha for v, sha in con.execute("SELECT version, sql_sha256 FROM schema_version")}
    by_version = {m.version: m for m in migrations}
    for v, sha in sorted(applied.items()):
        if v not in by_version:
            raise SchemaError(f"DB 스키마 버전 {v}을 이 코드가 모른다(최신 {latest}) — 새 DB를 옛 코드로 열었다")
        if by_version[v].sha256 != sha:
            raise SchemaError(f"v{v} 체크섬 불일치 — 적용된 단계의 SQL이 바뀌었다(append-only 위반, 새 단계를 붙일 것)")
    current = max(applied, default=0)
    if target < current:
        raise SchemaError(f"다운그레이드 없음: 현재 v{current} > target v{target}")
    if target > latest:
        raise SchemaError(f"target v{target} > 코드 최신 v{latest}")
    done = []
    for step in migrations:
        if step.version <= current or step.version > target:
            continue
        if not applied:
            _check_preexisting(con, step)
        con.execute("BEGIN")
        try:
            con.execute(VERSION_DDL)
            for s in _statements(step.sql):
                con.execute(s)
            con.execute("INSERT INTO schema_version(version, name, sql_sha256, applied_at_utc) VALUES (?,?,?,?)",
                        (step.version, step.name, step.sha256, _utcnow()))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        applied[step.version] = step.sha256
        done.append(step.version)
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="db.migrate", description="버전 마이그레이션 도구")
    ap.add_argument("db", type=Path)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--target", type=int)
    a = ap.parse_args(argv)
    a.db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(a.db)
    try:
        if a.status:
            print(f"{a.db}: schema version {current_version(con)} (code latest {MIGRATIONS[-1].version})")
            return 0
        done = migrate(con, target=a.target)
        print(f"{a.db}: applied {done or 'nothing'} → schema version {current_version(con)}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
