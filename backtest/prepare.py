"""창 데이터 준비 CLI(단계 2a) — 아카이브 + REST 보충 + 확정 펀딩 → `var/backtest/<window>/` parquet 캐시 + 무결성 JSON.

    python -m backtest.prepare --window IS [--var-dir var/backtest]

🔒 **OOS 창은 준비하지 않는다** — `--oos-opening-approved`(G3 개봉, 사전등록 §4-1 단계 4)가 있어야 한다. 데이터 준비 자체는
성과 계산이 아니지만, holdout을 파일로 미리 만들어 두면 "한 번만 개봉" 규칙을 지키는 게 운에 맡겨진다.
통계·성과는 계산하지 않는다(무결성·출처·펀딩 개수만).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from backtest import data as BD
from strategies.trial01 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = {"IS": (A.IS_START_MS, A.IS_END_MS), "OOS": (A.OOS_START_MS, A.OOS_END_MS)}
BAR_COLS = ("open_ms", "open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote",
            "mark_open", "mark_high", "mark_low", "mark_close", "source")
#  UTC 정렬 표본: 창 안 아카이브 구간에서 고정 간격 5개(검사 목적 — 성과 무관)
UTC_SAMPLES = 5


def write_bars(path: Path, bars: list[BD.Bar1m]) -> None:
    cols: dict[str, list[Any]] = {c: [getattr(b, c) for b in bars] for c in BAR_COLS}
    pq.write_table(pa.table(cols), path)


def read_bars(path: Path) -> list[BD.Bar1m]:
    t = pq.read_table(path).to_pydict()
    return [BD.Bar1m(*(t[c][i] for c in BAR_COLS)) for i in range(len(t["open_ms"]))]


def prepare(window: str, out_root: Path, client: Any, archive: Path = BD.ARCHIVE_DIR) -> dict[str, Any]:
    start, end = WINDOWS[window]
    out = out_root / window
    out.mkdir(parents=True, exist_ok=True)
    bars = BD.load_window(archive, client, start, end)
    integ = BD.integrity(bars, start, end)
    arch_times = [b.open_ms for b in bars if b.source == "archive"]
    step = max(1, len(arch_times) // UTC_SAMPLES)
    utc = BD.assert_utc_alignment(bars, client, arch_times[::step][:UTC_SAMPLES]) if arch_times else []
    fundings = BD.fetch_funding(client, start, end)
    write_bars(out / "bars_1m.parquet", bars)
    (out / "funding.json").write_text(json.dumps([f.__dict__ for f in fundings], sort_keys=True))
    report = {"window": window, "start_ms": start, "end_ms": end, "integrity": integ.as_dict(), "utc_alignment": utc,
              "funding_events": len(fundings),
              "bars_sha256": hashlib.sha256((out / "bars_1m.parquet").read_bytes()).hexdigest(),
              "archive_last_ms": max(arch_times) if arch_times else None}
    (out / "integrity.json").write_text(json.dumps(report, sort_keys=True, indent=1))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=sorted(WINDOWS), required=True)
    ap.add_argument("--var-dir", default=str(ROOT / "var" / "backtest"))
    ap.add_argument("--oos-opening-approved", action="store_true")
    a = ap.parse_args(argv)
    if a.window == "OOS" and not a.oos_opening_approved:
        print("🔒 OOS 창은 G3 개봉(사전등록 §4-1 단계 4) 전에는 준비하지 않는다", file=sys.stderr)
        return 4
    from exchange.ccxt_rest import CcxtRestClient
    from exchange.client import ReadOnlyClient
    rep = prepare(a.window, Path(a.var_dir), ReadOnlyClient(CcxtRestClient()))
    print(json.dumps({k: rep[k] for k in ("window", "funding_events", "bars_sha256")} | {"integrity": rep["integrity"]},
                     sort_keys=True, indent=1))
    return 0 if rep["integrity"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
