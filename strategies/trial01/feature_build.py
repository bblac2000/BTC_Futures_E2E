"""피처 빌드 CLI(단계 2b) — 준비된 창 데이터 + 워밍업 → features_adv + 넓은 형식 + 스윙 + 처리량.

    python -m strategies.trial01.feature_build --window IS [--var-dir var/backtest]

- 입력: `backtest.prepare`가 만든 `var/backtest/<window>/bars_1m.parquet`. OOS는 `prepare`가 G3 전에는 만들지 않는다.
- **워밍업**(구현 규약 · 단계 d Codex 질문): 창 시작 **35일 전**부터의 아카이브 봉으로 피처만 데운다 —
  TSMOM(180 × 4h = 30일)·ATR·스윙이 창 첫 분부터 정의되게. 워밍업 분의 피처는 저장하지 않는다(창 안 행만 저장).
- 성과·손익은 계산하지 않는다. 처리량(분/초)·행 수·SHA256만 보고한다.
"""
from __future__ import annotations

import argparse
import json
import resource
import time
from decimal import Decimal
from pathlib import Path

from backtest import data as BD
from backtest import prepare as PR
from strategies.trial01 import feature_store as FS
from strategies.trial01.features import FeatureRow, run

ROOT = Path(__file__).resolve().parent.parent.parent
WARMUP_MS = 35 * 86_400_000
RULES_DIR = ROOT / "tests" / "fixtures" / "snapshots"   # 캡처된 exchangeInfo(실측) — tickSize는 리터럴로 적지 않는다


def tick_size() -> Decimal:
    from exchange.loader import rules_from_snapshot_dir
    return rules_from_snapshot_dir(RULES_DIR, "BTCUSDT").symbol_rules.tick_size


def carry_into_window(rows: list[FeatureRow], start: int, end: int) -> list[FeatureRow]:
    """창 안 행만 남기되, 첫 행에 워밍업에서 이어진 느린 피처(atr_15m·tsmom_4h·bucket_incomplete_*)를 넣는다 —
    느린 피처는 버킷이 끝나는 분에만 기록되므로, 없으면 창 첫 버킷 마감 전까지 넓은 형식에서 빈 값이 된다."""
    carried: dict[str, Decimal | None] = {}
    out: list[FeatureRow] = []
    for r in rows:
        if r.bar_open_ms < start:
            carried.update({k: v for k, v in r.values.items() if k in FS.BUCKET_FEATURES})
        elif r.bar_open_ms <= end:
            if not out:
                r = FeatureRow(r.bar_open_ms, carried | r.values)
            out.append(r)
    return out


def build(window: str, var_dir: Path, archive: Path = BD.ARCHIVE_DIR) -> dict[str, object]:
    start, end = PR.WINDOWS[window]
    src = var_dir / window
    bars = PR.read_bars(src / "bars_1m.parquet")
    warm = BD.load_archive(archive, start - WARMUP_MS, start - 1)
    warm_integ = BD.integrity(warm, start - WARMUP_MS, start - 1)
    t0 = time.perf_counter()
    tick = tick_size()
    rows, swings = run(warm + bars, tick)
    t1 = time.perf_counter()
    in_window = carry_into_window(rows, start, end)
    store = src / "features.sqlite"
    store.unlink(missing_ok=True)
    con = FS.open_store(store)
    n_rows = FS.write_rows(con, in_window)
    t2 = time.perf_counter()
    sha = FS.rows_sha256(con)
    n_wide = FS.export_wide(con, src / "features_wide.parquet")
    n_sw = FS.write_swings([s for s in swings if s.confirmed_ms <= end], src / "swing_levels.parquet")
    con.close()
    t3 = time.perf_counter()
    minutes = len(warm) + len(bars)
    return {"window": window, "tick_size": str(tick), "minutes_computed": minutes, "warmup_minutes": len(warm),
            "warmup_integrity_ok": warm_integ.ok, "warmup_missing": warm_integ.missing_minutes,
            "window_minutes": len(bars), "feature_rows": n_rows, "wide_rows": n_wide, "swing_levels": n_sw,
            "features_adv_rows_sha256": sha, "compute_s": round(t1 - t0, 2), "store_s": round(t2 - t1, 2),
            "export_s": round(t3 - t2, 2), "throughput_min_per_s": round(minutes / (t1 - t0)),
            "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["IS"], required=True)
    ap.add_argument("--var-dir", default=str(ROOT / "var" / "backtest"))
    a = ap.parse_args(argv)
    print(json.dumps(build(a.window, Path(a.var_dir)), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
