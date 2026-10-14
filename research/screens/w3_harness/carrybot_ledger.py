"""W3 격리 하네스(사용자 #105 (b)(가)) — carrybot 정본 측정 스크립트를 **수정 없이** 그 저장소의 동결 커밋 작업 트리에서 돌리고,
`run_backtest` 호출을 감싸 거래별 장부를 꺼낸다. 이 파일은 carrybot의 파이썬(동결 uv.lock)으로 실행된다 — E2E 코드를 import하지 않는다.

    uv run --project <worktree> python research/screens/w3_harness/carrybot_ledger.py <worktree> <out_dir>

- 재현 확인: 스크립트의 `main()`이 그대로 결과 JSON을 작업 트리에 쓴다 → 호출자가 `git -C <worktree> diff`로 커밋된 결과와 비교한다.
- 장부: 호출마다 거래(진입·청산 시각 · 명목 · 묶인 자본 · 펀딩 · 잔여 델타 · 수수료 · 슬리피지 · 기회비용 · 사유)를 CSV로.
  첫 칸 = 청산 시각(ms) — E2E 쪽 로더가 `bounded_csv_file(ts_field=0)`로 2026-06-30 뒤에 닫힌 거래를 값 해석 없이 버린다.
- 이 하네스는 시장 값을 해석하지 않는다(정본 코드가 낸 장부를 옮겨 적을 뿐).
"""
from __future__ import annotations

import csv
import importlib
import os
import sys
from pathlib import Path

LABELS = {"carry_backtest": ["v1_original"], "carry_backtest_v2": ["v2_primary", "v2_no_accounting_fix", "v1_restated"]}
COLS = ["exit_ms", "entry_ms", "run", "notional", "locked", "funding_collected", "funding_paid", "residual_delta_pnl", "fees",
        "slippage", "opportunity_cost", "net_pnl", "holding_periods", "exit_reason", "forced"]


def main() -> int:
    wt, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chdir(wt)
    sys.path.insert(0, str(wt / "docs" / "measure_scripts"))
    rows: list[list[object]] = []
    for name, labels in LABELS.items():
        mod = importlib.import_module(name)
        real, calls = mod.run_backtest, []

        def wrapped(*a, _real=real, _calls=calls, **k):  # noqa: ANN002, ANN003, ANN202
            r = _real(*a, **k)
            _calls.append((a, k, r))
            return r

        mod.run_backtest = wrapped
        rc = mod.main()
        if rc not in (0, None):
            return 10
        if len(calls) != len(labels):
            print(f"{name}: 호출 {len(calls)} ≠ 예상 {len(labels)}", file=sys.stderr)
            return 11
        for label, (a, k, r) in zip(labels, calls, strict=True):
            ts, cfg = a[0], (a[6] if len(a) > 6 else k["cfg"])
            for t in r.trades:
                locked = t.notional * (1 + 1 / cfg.leverage + cfg.buffer_ratio)
                rows.append([int(ts[t.exit_idx]), int(ts[t.entry_idx]), label, repr(float(t.notional)), repr(float(locked)), repr(float(t.funding_collected)),
                             repr(float(t.funding_paid)), repr(float(t.residual_delta_pnl)), repr(float(t.fees)), repr(float(t.slippage)), repr(float(t.opportunity_cost)),
                             repr(float(t.net_pnl)), t.holding_periods, t.exit_reason, int(t.forced)])
            print(f"{label}: 거래 {len(r.trades)} · 순손익 {r.net_pnl!r}")
    rows.sort(key=lambda x: (str(x[2]), int(x[1])))                  # type: ignore[arg-type]
    with (out / "carrybot_trades.csv").open("x", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
