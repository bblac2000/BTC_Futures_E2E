"""트라이얼 #1 정본 실행 진입점(단계 2c) — 격리 러너(`backtest.replay.run_isolated`)가 subprocess로 띄운다.

    python -m strategies.trial01.run --window IS --arm A|B [--delay K] [--invert] --out DIR

- 입력: `backtest.prepare`가 만든 `var/backtest/<window>/`(bars_1m.parquet · funding.json) + 창 시작 **35일 전** 아카이브 봉(워밍업).
  OOS는 선택지에 없다 — G3 개봉 전에는 `prepare`가 만들지도 않는다.
- 워밍업 봉은 **피처만** 데운다(`Trial01.warm` · 레지스트리 #20 ②) — `replay`에 넣지 않으므로 워밍업 중 트레이드가 없다.
  VP 배열 범위(lo/hi)는 `feature_build`와 같게 워밍업 + 창 종가로 잡는다(피처 값은 범위와 무관 · 2b 정본과 같은 계산).
- 출력: `decisions.jsonl`(건너뜀 사유 전부 · 의도) · `trades.jsonl`(엔진 체결 기록) · `summary.json`(개수·설정만).
  🚫 **요약에 지갑·수익 집계를 넣지 않는다** — 성과 계산은 단계 e(IS 측정)의 몫이다.
- equity 1,000 USDT(사전등록 §1-1 표의 기준) · 복리(엔진 하나 · 레지스트리 #19 ④).
"""
from __future__ import annotations

import argparse
import dataclasses
import decimal
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtest import data as BD
from backtest import prepare as PR
from backtest.engine_replay import ReplayResult, replay
from backtest.replay import write_jsonl
from exchange.rules import RuntimeRules
from sizing.config import SizingLimits
from strategies.trial01 import anchor as A
from strategies.trial01.config import SR_V1_PARAMS, Trial01Params
from strategies.trial01.feature_build import RULES_DIR, WARMUP_MS
from strategies.trial01.features import DECIMAL_CTX, FeatureEngine
from strategies.trial01.strategy import Arm, EngineFeed, Trial01

ROOT = Path(__file__).resolve().parent.parent.parent
EQUITY = Decimal("1000")


def load_rules() -> RuntimeRules:
    from exchange.loader import rules_from_snapshot_dir
    return rules_from_snapshot_dir(RULES_DIR, "BTCUSDT")


def load_inputs(window: str, var_dir: Path, archive: Path = BD.ARCHIVE_DIR
                ) -> tuple[list[BD.Bar1m], list[BD.Bar1m], list[BD.Funding]]:
    start, _ = PR.WINDOWS[window]
    src = var_dir / window
    bars = PR.read_bars(src / "bars_1m.parquet")
    fundings = [BD.Funding(**f) for f in json.loads((src / "funding.json").read_text())]
    warm = BD.load_archive(archive, start - WARMUP_MS, start - 1)
    return warm, bars, fundings


def build_strategy(warm: list[BD.Bar1m], bars: list[BD.Bar1m], tick: Decimal, *, arm: Arm, delay: int = 0,
                   invert: bool = False, params: Trial01Params = SR_V1_PARAMS) -> Trial01:
    closes = [b.d("close") for b in warm] + [b.d("close") for b in bars]
    s = Trial01(EngineFeed(FeatureEngine(tick, min(closes), max(closes))), tick, arm=arm, delay=delay, invert=invert,
                params=params)
    for b in warm:
        s.warm(b)
    return s


def run(warm: list[BD.Bar1m], bars: list[BD.Bar1m], fundings: list[BD.Funding], *, arm: Arm, delay: int = 0,
        invert: bool = False, rules: RuntimeRules | None = None) -> tuple[ReplayResult, Trial01]:
    rules = rules or load_rules()
    with decimal.localcontext(DECIMAL_CTX):                       # 엔진 산술까지 정본 문맥(features.DECIMAL_CTX)
        s = build_strategy(warm, bars, rules.symbol_rules.tick_size, arm=arm, delay=delay, invert=invert)
        r = replay(bars, fundings, s, rules=rules, limits=SizingLimits(), equity=EQUITY)
    return r, s


def summary(r: ReplayResult, s: Trial01, meta: dict[str, Any]) -> dict[str, Any]:
    """개수·설정만 — 지갑·수익 없음."""
    reasons = Counter(d.get("reason", d["outcome"]) for d in r.decisions)
    cand = sum(1 for d in r.decisions if d.get("candidate") is True)
    return meta | {"sr_v1_sha256": A.SR_V1_SHA256, "params": {k: str(v) for k, v in dataclasses.asdict(s.p).items()},
                   "n_trades": len(r.trades), "open_at_end": r.open_at_end is not None,
                   "decision_counts": dict(sorted(reasons.items())), "candidates": cand,
                   "strategy_counts": dict(sorted(s.counts.items()))}


def write_outputs(out: Path, r: ReplayResult, s: Trial01, meta: dict[str, Any]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "decisions.jsonl", r.decisions)
    write_jsonl(out / "trades.jsonl", r.trades)
    oae = [] if r.open_at_end is None else [r.open_at_end]
    write_jsonl(out / "open_at_end.jsonl", oae)
    summ = summary(r, s, meta)
    (out / "summary.json").write_text(json.dumps(summ, sort_keys=True, indent=1) + "\n")
    return summ


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["IS"], required=True)
    ap.add_argument("--arm", choices=["A", "B"], required=True)
    ap.add_argument("--delay", type=int, default=0)
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--var-dir", default=str(ROOT / "var" / "backtest"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.delay < 0:
        ap.error("--delay ≥ 0")
    warm, bars, fundings = load_inputs(a.window, Path(a.var_dir))
    r, s = run(warm, bars, fundings, arm=a.arm, delay=a.delay, invert=a.invert)
    summ = write_outputs(Path(a.out), r, s, {"window": a.window, "arm": a.arm, "delay": a.delay, "invert": a.invert,
                                             "window_minutes": len(bars), "warmup_minutes": len(warm)})
    print(json.dumps({k: summ[k] for k in ("window", "arm", "delay", "invert", "n_trades", "candidates")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
