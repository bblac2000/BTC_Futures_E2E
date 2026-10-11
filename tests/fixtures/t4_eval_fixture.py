"""트라이얼 #4 (f) 판정기 합성 입력 — 두 암 × 네 변형 실행 + P1(추출 40 · 조각 2개 · 게이트 + timing) + kline 일 종가. `t4_outputs` 계약으로 쓴다. 실데이터 없음."""
from __future__ import annotations

import hashlib
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from backtest import evaluate_t4 as E
from backtest import p1_t4 as P1
from backtest import t4_outputs as O
from backtest.data import Bar1m
from strategies.trial04 import anchor as A
from strategies.trial04.config import TC_V3
from strategies.trial04.harness import complete_days, v_days
from strategies.trial04.strategy import Variant
from tests.fixtures import t4_scenario as S

VARIANTS = {"base": Variant(), "P2_print1": Variant(delay=1), "P2_print3": Variant(delay=3), "P3_invert": Variant(invert=True)}
P1_DRAWS = 40
LIQ_FEE = S.RULES.symbol_rules.liquidation_fee


def kline_daily(bars: list[Bar1m]) -> list[dict[str, Any]]:
    last: dict[int, Bar1m] = {}
    for b in bars:
        last[b.open_ms // S.DAY] = b
    return [{"day": d, "minute_ms": b.open_ms, "close": b.close, "source": "archive"} for d, b in sorted(last.items())]


def build(base: Path, **kw: Any) -> dict[str, Any]:
    """두 암이 같은 봉·펀딩을 쓴다(인쇄는 극단의 부호만 다르다 — 유효성은 같다)."""
    scs = {arm: S.Scenario(arm=arm, **kw) for arm in O.ARMS}
    bars, fundings = scs["S"].bars(), scs["S"].fundings()
    for arm, sc in scs.items():
        for name, var in VARIANTS.items():
            r = S.run(sc, var)
            O.write_run(O.run_dir(base, arm, name), r, v_days(r.strategy, complete_days(bars)), tc_v3_sha256=A.TC_V3_SHA256,
                        rules_sha256=A.RULES_SNAPSHOT_SHA256)
            if name == "base":
                cfg = replace(P1.CFGS[arm], draws=P1_DRAWS)
                parts = [P1.run_range_with_fixture_rules(arm, r.trades, bars, fundings, lo, hi, rules=S.RULES, window=sc.window, cfg=cfg)
                         for lo, hi in ((0, 19), (20, 39))]
                for p in parts:
                    O.write_p1_part(base, p)
                O.write_p1_merged(base, arm, parts, draws_total=P1_DRAWS)
    return {"bars": bars, "fundings": fundings, "prints": scs["S"].prints(), "kd": kline_daily(bars), "window": scs["S"].window}


def compute(base: Path, x: dict[str, Any]):
    return E.compute_with_fixture(base, x["bars"], x["fundings"], x["prints"], x["kd"], LIQ_FEE, p=TC_V3, window=x["window"],
                                  p1_draws=P1_DRAWS)


if __name__ == "__main__":                                              # 교차 프로세스 결정론(보고서 바이트 해시)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _, report = compute(base, build(base))
        print(hashlib.sha256(E.report_bytes(report)).hexdigest())
    sys.exit(0)
