"""M-1 읽기 계약(스펙 r6 §2-3) — 복원 루트 아래 shard만 · 시각 칸 조건을 pyarrow 행 필터로 먼저 걸어 범위 밖 행의 값은 꺼내지 않는다."""
from __future__ import annotations

import datetime as dt
import functools
import json
import sqlite3

import numpy as np
import pyarrow.parquet as pq

from research.screens.p0 import sim
from research.screens.p0 import span as SP

DATA = SP.RESTORE / "BTCUSDT"
PLAN = SP.RESTORE / "M-1_plan.json"
RESTORE_JSON = SP.ROOT / "research" / "screens" / "p0" / "results" / "M-1_restore.json"
TS_COLS = {"depth100ms": ("recv_ms",), "bookticker": ("recv_ms",), "aggtrade": ("recv_ms", "transact_time")}


def _iso_ms(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def _shard_ms(date: str, name: str) -> int:
    hh, mm, ss, ms = int(name[0:2]), int(name[2:4]), int(name[4:6]), int(name[7:10])
    d0 = int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.UTC).timestamp() * 1000)
    return d0 + ((hh * 60 + mm) * 60 + ss) * 1000 + ms


def restore_record() -> dict:
    """검증 기록 — 없거나 ok가 아니면 실패(사용자 #105 강화 1)."""
    if not RESTORE_JSON.exists():
        raise RuntimeError(f"복원 검증 기록이 없다: {RESTORE_JSON}")
    rec = json.loads(RESTORE_JSON.read_text(encoding="utf-8"))
    if rec.get("ok") is not True:
        raise RuntimeError("복원 검증이 ok가 아니다")
    return rec


def excluded_files() -> set[str]:
    return {e["file"] for e in restore_record()["excluded"]}


@functools.lru_cache(maxsize=1)
def allowed_files() -> frozenset[str]:
    """짝지어진 파일 − 검증 제외 = 읽어도 되는 shard(사용자 #105 강화 2)."""
    matched = json.loads(PLAN.read_text(encoding="utf-8"))["matched"]
    return frozenset(set(matched) - excluded_files())


def bad_intervals(extra: list[tuple[int, int]] | None = None) -> list[tuple[int, int]]:
    """매니페스트 gaps · clock_skew(기록 시각 ±60초) · 제외 파일의 shard 구간 · 품질 보고서 FAIL 구간(`extra`)."""
    con = sqlite3.connect(f"file:{SP.RESTORE / 'manifest.sqlite'}?mode=ro", uri=True)
    out: list[tuple[int, int]] = []
    for s, e in con.execute("SELECT start_utc, end_utc FROM gaps WHERE date BETWEEN ? AND ?", (SP.DATES[0], SP.DATES[-1])):
        out.append((_iso_ms(s), _iso_ms(e) if e else SP.EXPOSED_END_MS))
    for (ts,) in con.execute("SELECT ts_utc FROM events WHERE kind='clock_skew' AND ts_utc BETWEEN ? AND ?",
                             (SP.DATES[0], SP.DATES[-1] + "T23:59:59Z")):
        t = _iso_ms(ts)
        out.append((t - 60_000, t + 60_000))
    ex = excluded_files()
    for stream in SP.STREAMS:
        for date in SP.DATES:
            d = DATA / date / stream
            names = sorted(f.name for f in d.glob("*.parquet")) if d.exists() else []
            allnames = sorted(set(names) | {r.split("/")[2] for r in ex if r.startswith(f"{date}/{stream}/")})
            for i, n in enumerate(allnames):
                if f"{date}/{stream}/{n}" in ex:
                    nxt = _shard_ms(date, allnames[i + 1]) if i + 1 < len(allnames) else _shard_ms(date, n) + 120_000
                    out.append((_shard_ms(date, n), nxt))
    return sorted(out + (extra or []))


def _read(stream: str, lo: int, hi: int, cols: list[str]) -> dict[str, np.ndarray]:
    """[lo, hi]가 노출 구간 안이어야 한다 · 해당 날짜와 전날 디렉터리의 shard만 · 행 필터(시각 칸) 뒤에만 값 칸을 꺼낸다."""
    if not (SP.EXPOSED_START_MS <= lo <= hi <= SP.EXPOSED_END_MS):
        raise ValueError(f"[{lo}, {hi}]가 노출 구간 밖")
    ex, allowed = excluded_files(), allowed_files()
    d_lo = dt.datetime.fromtimestamp(lo / 1000, dt.UTC).date() - dt.timedelta(days=1)
    d_hi = dt.datetime.fromtimestamp(hi / 1000, dt.UTC).date()
    parts: list[dict[str, np.ndarray]] = []
    d = d_lo
    while d <= d_hi:
        date = d.isoformat()
        d += dt.timedelta(days=1)
        if date not in SP.DATES:
            continue
        for f in sorted((DATA / date / stream).glob("*.parquet")):
            rel = f"{date}/{stream}/{f.name}"
            if rel in ex:
                continue
            if rel not in allowed:
                raise RuntimeError(f"짝지어지지 않은 shard: {rel}")
            flt = [(c, ">=", lo) for c in TS_COLS[stream]] + [(c, "<=", hi) for c in TS_COLS[stream]]
            t = pq.read_table(f, columns=cols, filters=flt)
            if t.num_rows:
                parts.append({c: t.column(c).to_numpy() for c in cols})
    if not parts:
        return {c: np.array([]) for c in cols}
    out = {c: np.concatenate([p[c] for p in parts]) for c in cols}
    o = np.argsort(out["recv_ms"], kind="stable")
    return {c: v[o] for c, v in out.items()}


def book(lo: int, hi: int, bad: list[tuple[int, int]]) -> sim.Book:
    lo, hi = max(lo, SP.EXPOSED_START_MS), min(hi, SP.EXPOSED_END_MS)
    bt = _read("bookticker", lo, hi, ["recv_ms", "bid_price", "bid_qty", "ask_price", "ask_qty"])
    dcols = ["recv_ms"] + [f"{s}{k}{i}" for s in ("b", "a") for i in range(1, sim.LEVELS + 1) for k in ("p", "q")]
    dp = _read("depth100ms", lo, hi, dcols)
    ag = _read("aggtrade", lo, hi, ["recv_ms", "agg_trade_id", "price", "quantity", "transact_time", "is_buyer_maker"])
    return sim.Book(
        bt_recv=bt["recv_ms"].astype(np.int64),
        bt=np.column_stack([bt["bid_price"], bt["bid_qty"], bt["ask_price"], bt["ask_qty"]]) if len(bt["recv_ms"]) else np.zeros((0, 4)),
        dp_recv=dp["recv_ms"].astype(np.int64),
        dp=np.column_stack([dp[c] for c in dcols[1:]]) if len(dp["recv_ms"]) else np.zeros((0, 4 * sim.LEVELS)),
        ag_recv=ag["recv_ms"].astype(np.int64), ag_id=ag["agg_trade_id"].astype(np.int64), ag_tick=sim.ticks(ag["price"]),
        ag_qty=ag["quantity"].astype(float), ag_tt=ag["transact_time"].astype(np.int64), ag_bm=ag["is_buyer_maker"].astype(bool),
        lo_ms=lo, hi_ms=hi, bad=[(s, e) for s, e in bad if s < hi and e > lo])
