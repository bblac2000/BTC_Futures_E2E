"""트라이얼 #3 (f) 판정기 합성 입력 — 두 암 × 네 변형 실행 + P1(추출 40 · 조각 2개) + kline 일 종가. `t3_outputs` 계약으로 쓴다. 실데이터 없음."""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from typing import Any

from backtest import evaluate_t3 as E
from backtest import p1_t3 as P1
from backtest import t3_outputs as O
from backtest.data import Bar1m
from strategies.trial03 import anchor as A
from strategies.trial03.harness import complete_days, v_days
from strategies.trial03.strategy import Variant
from tests.fixtures import t3_scenario as S

VARIANTS = {"base": Variant(), "P2_delay1": Variant(delay=1), "P2_delay5": Variant(delay=5), "P3_invert": Variant(invert=True)}
P1_DRAWS = 40
LIQ_FEE = S.RULES.symbol_rules.liquidation_fee


def kline_daily(bars: list[Bar1m]) -> list[dict[str, Any]]:
    last: dict[int, Bar1m] = {}
    for b in bars:
        last[b.open_ms // S.DAY] = b
    return [{"day": d, "minute_ms": b.open_ms, "close": b.close, "source": "archive"} for d, b in sorted(last.items())]


def build(base: Path, scenarios: dict[str, S.Scenario] | None = None) -> tuple[list[Bar1m], list[dict[str, Any]]]:
    scs = scenarios or {"L": S.Scenario(arm="L"), "S": S.Scenario(arm="S")}
    bars = scs["L"].bars()
    for arm, sc in scs.items():
        b = sc.bars()
        for name, var in VARIANTS.items():
            r = S.run(sc, var)
            O.write_run(O.run_dir(base, arm, name), r, v_days(r.strategy, complete_days(b)), tf_v1_sha256=A.TF_V1_SHA256,
                        rules_sha256=A.RULES_SNAPSHOT_SHA256)
            if name == "base":
                parts = [P1.run_range_with_fixture_rules(arm, r.trades, b, sc.fundings(), lo, hi, rules=S.RULES, window=S.WINDOW)
                         for lo, hi in ((0, 19), (20, 39))]
                for p in parts:
                    O.write_p1_part(base, p)
                O.write_p1_merged(base, arm, parts, draws_total=P1_DRAWS)
    return bars, kline_daily(bars)


def compute(base: Path, bars: list[Bar1m], kd: list[dict[str, Any]]):
    return E.compute_with_fixture(base, bars, kd, LIQ_FEE, p=S.P, window=S.WINDOW, p1_draws=P1_DRAWS)


if __name__ == "__main__":                                              # 교차 프로세스 결정론(보고서 바이트 해시)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        bars, kd = build(base)
        _, report = compute(base, bars, kd)
        print(hashlib.sha256(E.report_bytes(report)).hexdigest())
    sys.exit(0)
