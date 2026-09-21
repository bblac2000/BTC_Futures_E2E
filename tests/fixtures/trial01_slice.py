"""결정론 테스트용 — IS 앞 N일 조각을 **정본 `strategies.trial01.run.run`**으로 돌린다(정본 CLI에 조각 옵션을 두지 않는다).

    python -m tests.fixtures.trial01_slice --arm A --days 30 --out DIR
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from backtest import data as BD
from backtest import prepare as PR
from strategies.trial01 import run as RUN

ROOT = Path(__file__).resolve().parent.parent.parent
IS_DIR = ROOT / "var" / "backtest" / "IS"


def load_slice(days: int) -> tuple[list[BD.Bar1m], list[BD.Bar1m], list[BD.Funding]]:
    start, _ = PR.WINDOWS["IS"]
    end = start + days * 86_400_000 - 1
    t = pq.read_table(IS_DIR / "bars_1m.parquet", filters=[("open_ms", "<=", end)]).to_pydict()
    bars = [BD.Bar1m(*(t[c][i] for c in PR.BAR_COLS)) for i in range(len(t["open_ms"]))]
    fundings = [BD.Funding(**f) for f in json.loads((IS_DIR / "funding.json").read_text()) if f["funding_ms"] <= end]
    warm = BD.load_archive(BD.ARCHIVE_DIR, start - RUN.WARMUP_MS, start - 1)
    return warm, bars, fundings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["A", "B"], required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    warm, bars, fundings = load_slice(a.days)
    r, s = RUN.run(warm, bars, fundings, arm=a.arm)
    RUN.write_outputs(Path(a.out), r, s, {"window": f"IS[:{a.days}d]", "arm": a.arm, "delay": 0, "invert": False,
                                          "window_minutes": len(bars), "warmup_minutes": len(warm)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
