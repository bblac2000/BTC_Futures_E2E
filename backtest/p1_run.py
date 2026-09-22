"""P1 무작위 타이밍 귀무분포(단계 e) — 격리 실행용 CLI. 사전등록 §4 P1 행 규약 (a)~(f) · `backtest.placebo`·`placebo_exec`.

    python -m backtest.p1_run --step-e-dir var/backtest/IS/step_e --draws 0-249 --out var/backtest/IS/step_e/P1/part_000_249
    python -m backtest.p1_run --step-e-dir var/backtest/IS/step_e --merge            # 조각 → P1/p1_draws.json · P1/p1_null.jsonl

- 원판 Arm A `trades.jsonl`에서 **P1 입력만** 읽는다: `trade_id · entry_ms · exit_ms · sl_dist`(쌍으로). 수익 필드는 읽지도 출력하지도 않는다.
- 추출 d의 난수는 `SeedSequence(20260921).spawn(1000)[d]` 하나뿐이라 **추출 범위로 나눠 돌려도** 한 번에 돈 것과 바이트가 같다.
- 격자 = IS 준비 봉의 분 시작 시각(mark 관측이 있는 분 · #19 ⑧로 결손 2분 제외) · 사이징·실행 = 정본 B2 + 정본 엔진(`placebo_exec`) ·
  equity = 초기 자본 고정 1,000(#19 ④) · 레짐 = 전략과 같은 risk 1% · L 50~100.
- 출력(stdout)은 개수만: 추출 수 · 실패 수.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from backtest import data as BD
from backtest import placebo as PL
from backtest import placebo_exec as PX
from backtest import prepare as PR
from backtest.replay import write_jsonl
from sizing.config import RegimeSizing, SizingLimits
from strategies.trial01 import anchor as A

EQUITY = Decimal("1000")
REGIME = RegimeSizing("trial01_P1", Decimal("0.01"), 50, 100)
P1_FIELDS = ("trade_id", "entry_ms", "exit_ms", "sl_dist")


def source_trades(trades_path: Path) -> list[PL.SourceTrade]:
    out = []
    for ln in trades_path.read_text().splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        out.append(PL.SourceTrade(int(r["trade_id"]), int(r["entry_ms"]), int(r["exit_ms"]), Decimal(r["sl_dist"])))
    return out


def run_range(step_e: Path, is_dir: Path, lo: int, hi: int, out: Path) -> dict[str, int]:
    from strategies.trial01.run import load_rules
    rules, limits = load_rules(), SizingLimits()
    src = source_trades(step_e / "A" / "trades.jsonl")
    bars = PR.read_bars(is_dir / "bars_1m.parquet")
    by_t = {b.open_ms: b for b in bars}
    fundings = [BD.Funding(**f) for f in json.loads((is_dir / "funding.json").read_text())]
    start, end = A.IS_START_MS, A.IS_END_MS
    grid = sorted(by_t)
    index = PL.EligibleIndex(grid, start, end)

    def sizing_ok(t: int, direction: int, sl_dist: Decimal) -> bool:
        _, d = PX.sizing_decision(by_t[t].d("mark_open"), direction, sl_dist, rules, limits, EQUITY, REGIME)
        return bool(d.ok)

    draws = [PL.p1_draw(d, src, grid, start, end, sizing_ok, index=index) for d in range(lo, hi + 1)]
    null = PX.p1_null_distribution(draws, by_t, fundings, rules=rules, limits=limits, equity=EQUITY, regime=REGIME)
    out.mkdir(parents=True, exist_ok=True)
    (out / "p1_draws.json").write_text(PL.p1_canonical_json(draws))
    write_jsonl(out / "p1_null.jsonl", null)
    return {"draws": len(draws), "failed": sum(1 for d in draws if not d.ok), "source_trades": len(src)}


def merge(step_e: Path) -> dict[str, int]:
    """조각들을 합친다 — 0..999를 **정확히 한 번씩** 덮어야 한다(빠짐·겹침이면 거부)."""
    parts = sorted((step_e / "P1").glob("part_*"))
    draws: list[dict] = []
    null: list[dict] = []
    for p in parts:
        draws += json.loads((p / "p1_draws.json").read_text())
        null += [json.loads(ln) for ln in (p / "p1_null.jsonl").read_text().splitlines() if ln.strip()]
    ids = sorted(d["draw"] for d in draws)
    if ids != list(range(A.P1_DRAWS)):
        raise SystemExit(f"P1 조각이 0..{A.P1_DRAWS - 1}을 정확히 덮지 않는다(개수 {len(ids)})")
    draws.sort(key=lambda d: d["draw"])
    null.sort(key=lambda r: r["draw"])
    (step_e / "P1" / "p1_draws.json").write_text(json.dumps(draws, sort_keys=True, separators=(",", ":")))
    write_jsonl(step_e / "P1" / "p1_null.jsonl", null)
    return {"draws": len(draws), "failed": sum(1 for d in draws if not d["ok"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step-e-dir", required=True)
    ap.add_argument("--is-dir", default=None)
    ap.add_argument("--draws", default=None)                  # "lo-hi"(포함)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    step_e = Path(a.step_e_dir)
    if a.merge:
        print(json.dumps(merge(step_e)))
        return 0
    if a.draws is None or a.out is None:
        ap.error("--draws lo-hi 와 --out 이 필요하다(또는 --merge)")
    lo, hi = (int(x) for x in a.draws.split("-"))
    if not 0 <= lo <= hi < A.P1_DRAWS:
        ap.error(f"--draws 범위는 0..{A.P1_DRAWS - 1}")
    is_dir = Path(a.is_dir) if a.is_dir else step_e.parent
    print(json.dumps(run_range(step_e, is_dir, lo, hi, Path(a.out))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
