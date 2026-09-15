"""데이터 소스 측정(사전등록 불요) — 레지스트리 #5의 10bp 절대 하한 sanity check.

지표:
- `|mark − mid| / mid` — mark(1s, premiumIndex REST)와 **그 시각 직전 마지막 bookTicker mid**의 괴리
  (SL은 mark로 트리거되고 청산 체결은 호가에서 난다 → 두 기준 사이 거리)
- `|mark_t − mark_{t−1s}| / mark` — 모니터 1초 주기 동안의 mark 이동
분위수 p50 · p99 · p99.9 · max, 일별 + 전체.

입력(읽기 전용):
- bookTicker: E2E 로컬 raw `E2E_Hybrid_Bot/data/raw/l2live/BTCUSDT/<day>/bookticker/*.parquet` (event_ts, bid_price, ask_price)
- mark 1s: Drive `gdrive_ro:E2E_Hybrid_Bot/l2live/BTCUSDT/<day>/markprice_rest`를 스크래치로 복사한 것 (event_time, mark_price)
🚫 E2E 데이터를 쓰지 않는다. 결과는 docs/ops_log.md에 붙인다(측정 사실 — 판정 아님).

사용: uv run python scripts/measure_mark_vs_mid.py --book <E2E raw BTCUSDT dir> --mark <copied dir> 2026-08-08 [...]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as _pc
import pyarrow.parquet as pq

pc: Any = _pc


def _read(files: list[str], cols: list[str]) -> pa.Table:
    return pa.concat_tables([pq.read_table(f, columns=cols) for f in files]) if files else pa.table({})


def quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    s = sorted(values)
    n = len(s)

    def q(p: float) -> float:
        return s[min(n - 1, max(0, math.ceil(p * n) - 1))]
    return {"n": n, "p50": q(0.50), "p99": q(0.99), "p999": q(0.999), "max": s[-1]}


def day(book_root: Path, mark_root: Path, d: str) -> dict[str, Any]:
    bt = _read(sorted(glob.glob(str(book_root / d / "bookticker" / "*.parquet"))), ["event_ts", "bid_price", "ask_price"])
    mk = _read(sorted(glob.glob(str(mark_root / d / "*.parquet"))), ["event_time", "mark_price"])
    if bt.num_rows == 0 or mk.num_rows == 0:
        return {"day": d, "skipped": f"book rows {bt.num_rows} · mark rows {mk.num_rows}"}
    #  초별 마지막 mid(초 안 이벤트 시각 순서대로 정렬 후 last)
    bt = bt.sort_by("event_ts")
    sec = pc.divide(bt["event_ts"], 1000)          # int64 ÷ int → 정수 나눗셈(내림, 양수 시각)
    mid = pc.divide(pc.add(bt["bid_price"], bt["ask_price"]), 2)
    last_mid = pa.table({"sec": sec, "mid": mid}).group_by("sec", use_threads=False).aggregate([("mid", "last")])
    mid_by_sec = dict(zip(last_mid["sec"].to_pylist(), last_mid["mid_last"].to_pylist(), strict=True))
    mk = mk.sort_by("event_time")
    times, marks = mk["event_time"].to_pylist(), mk["mark_price"].to_pylist()
    dev, move, unmatched = [], [], 0
    prev_t, prev_m = None, None
    for t, m in zip(times, marks, strict=True):
        #  mark event_time은 초 경계(…000ms) → 직전 초의 마지막 호가가 "그 시각 직전 mid"
        md = mid_by_sec.get(t // 1000 - 1)
        if md is None or md <= 0:
            unmatched += 1
        else:
            dev.append(abs(m - md) / md)
        if prev_t is not None and prev_m and t - prev_t == 1000:
            move.append(abs(m - prev_m) / prev_m)
        prev_t, prev_m = t, m
    return {"day": d, "book_rows": bt.num_rows, "mark_rows": mk.num_rows, "unmatched_mark": unmatched,
            "mark_vs_mid": quantiles(dev), "mark_move_1s": quantiles(move), "_dev": dev, "_move": move}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=Path, required=True)
    ap.add_argument("--mark", type=Path, required=True)
    ap.add_argument("days", nargs="+")
    a = ap.parse_args(argv)
    all_dev: list[float] = []
    all_move: list[float] = []
    out = []
    for d in a.days:
        r = day(a.book, a.mark, d)
        all_dev += r.pop("_dev", [])
        all_move += r.pop("_move", [])
        out.append(r)
    summary = {"days": out, "all_mark_vs_mid": quantiles(all_dev), "all_mark_move_1s": quantiles(all_move)}

    def bps(x: Any) -> Any:
        return {k: (round(v * 10000, 3) if isinstance(v, float) else v) for k, v in x.items()} if isinstance(x, dict) else x
    for r in summary["days"]:
        for k in ("mark_vs_mid", "mark_move_1s"):
            if k in r:
                r[k] = bps(r[k])
    summary["all_mark_vs_mid"] = bps(summary["all_mark_vs_mid"])
    summary["all_mark_move_1s"] = bps(summary["all_mark_move_1s"])
    print("단위: bps (분위수) · 행 수는 개수")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
