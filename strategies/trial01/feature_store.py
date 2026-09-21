"""트라이얼 #1 피처 저장(단계 2b) — **백테스트 전용 sqlite**(`var/backtest/<window>/features.sqlite`)의 `features_adv`.

- 스키마는 봇과 같은 `db.migrate`를 쓰지만 **파일이 다르다**(운영 DB에 백테스트 행을 넣지 않는다).
- `feature_definitions`: 이름마다 `params_version = 1`(= sr_v1) · `params_json`에 sr_v1 SHA256·파라미터·규약(#19)을 적는다.
- 행은 **바뀐 값만** 쓴다: 분마다 atr_1m·vp_*(1m 피처), 15m 버킷이 끝난 분에 atr_15m·bucket_incomplete_15m,
  4h 버킷이 끝난 분에 tsmom_4h·bucket_incomplete_4h. 넓은 형식 내보내기가 느린 피처를 **앞값 채움**한다.
- 스윙 레벨은 스칼라가 아니라 사건이라 `swing_levels.parquet`에 따로 둔다(확정·만료·무효화 시각 포함).
- 결정론 검사: `rows_sha256` = features_adv 행(id 제외)을 (bar_open_ms, name) 순으로 직렬화한 SHA256.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from db import migrate as M
from db import record as R
from strategies.trial01 import anchor as A
from strategies.trial01.features import SR_V1, FeatureRow, SrV1, SwingLevel

PARAMS_VERSION = 1                                 # sr_v1
MODE, SYMBOL = "paper", "BTCUSDT"
MINUTE_FEATURES = ("atr_1m", "vp_poc", "vp_vah", "vp_val")
BUCKET_FEATURES = ("atr_15m", "bucket_incomplete_15m", "tsmom_4h", "bucket_incomplete_4h")
ALL_FEATURES = MINUTE_FEATURES + BUCKET_FEATURES


def params_json(cfg: SrV1 = SR_V1) -> dict[str, Any]:
    return {"params_version": "sr_v1", "sr_v1_sha256": A.SR_V1_SHA256, "prereg_sha256": A.PREREG_SHA256,
            "registry_rows": [18, 19], "cfg": {k: str(v) for k, v in dataclasses.asdict(cfg).items()}}


def open_store(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    M.migrate(con)
    for name in ALL_FEATURES:
        R.register_feature(con, name, PARAMS_VERSION, "features_adv", params_json())
    return con


def write_rows(con: sqlite3.Connection, rows: list[FeatureRow]) -> int:
    data = [(MODE, SYMBOL, r.bar_open_ms, name, PARAMS_VERSION, None if v is None else str(v))
            for r in rows for name, v in sorted(r.values.items())]
    with con:
        con.executemany("INSERT INTO features_adv(mode, symbol, bar_open_ms, name, params_version, value) "
                        "VALUES(?,?,?,?,?,?)", data)
    return len(data)


def rows_sha256(con: sqlite3.Connection) -> str:
    h = hashlib.sha256()
    for row in con.execute("SELECT mode, symbol, bar_open_ms, name, params_version, value FROM features_adv "
                           "ORDER BY bar_open_ms, name, params_version"):
        h.update(json.dumps(row, separators=(",", ":")).encode())
        h.update(b"\n")
    return h.hexdigest()


def export_wide(con: sqlite3.Connection, path: Path) -> int:
    """분마다 한 행 · 느린 피처는 앞값 채움. 반환 = 행 수."""
    cols: dict[str, list[Any]] = {"bar_open_ms": []} | {f: [] for f in ALL_FEATURES}
    last: dict[str, str | None] = {f: None for f in ALL_FEATURES}
    cur_t: int | None = None
    for t, name, value in con.execute("SELECT bar_open_ms, name, value FROM features_adv WHERE params_version=? "
                                      "ORDER BY bar_open_ms, name", (PARAMS_VERSION,)):
        if t != cur_t:
            if cur_t is not None:
                cols["bar_open_ms"].append(cur_t)
                for f in ALL_FEATURES:
                    cols[f].append(last[f])
            cur_t = t
        last[name] = value
    if cur_t is not None:
        cols["bar_open_ms"].append(cur_t)
        for f in ALL_FEATURES:
            cols[f].append(last[f])
    pq.write_table(pa.table(cols), path)
    return len(cols["bar_open_ms"])


def write_swings(levels: list[SwingLevel], path: Path) -> int:
    cols: dict[str, list[Any]] = {"level_id": [], "kind": [], "price": [], "bar_open_ms": [], "confirmed_ms": [],
                                  "expires_ms": [], "invalidated_ms": []}
    for lv in levels:
        for k in cols:
            v = getattr(lv, k)
            cols[k].append(str(v) if k == "price" else v)
    pq.write_table(pa.table(cols), path)
    return len(levels)
