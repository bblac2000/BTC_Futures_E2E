"""트라이얼 #1 P1 골든 시나리오(단계 2f 리팩터 전 트리에서 생성) — 합성 원판·격자·봉. 실데이터 없음."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest import placebo as PL  # noqa: E402
from backtest import placebo_exec as PX  # noqa: E402
from backtest.data import MINUTE_MS, Bar1m, Funding  # noqa: E402
from exchange.loader import rules_from_snapshot_dir  # noqa: E402
from sizing.config import RegimeSizing, SizingLimits  # noqa: E402

T0 = 1_704_067_200_000
N = 3000


def run() -> dict:
    rules = rules_from_snapshot_dir(Path(__file__).resolve().parent / "snapshots", "BTCUSDT")
    src = [PL.SourceTrade(i, T0 + (50 + 97 * i) * MINUTE_MS, T0 + (50 + 97 * i + 3 + 11 * (i % 5)) * MINUTE_MS,
                          Decimal("0.004") + Decimal(i % 4) / 1000) for i in range(12)]
    grid = [T0 + m * MINUTE_MS for m in range(N) if m not in (700, 701, 1500)]
    regime = RegimeSizing("g", Decimal("0.01"), 50, 100)
    bars = {}
    for m in range(N):
        p = Decimal(60000) + Decimal((m * 37) % 400 - 200)
        s = str(p)
        bars[T0 + m * MINUTE_MS] = Bar1m(T0 + m * MINUTE_MS, s, str(p + 20), str(p - 20), s, "1", "1", 1, "0", "0", s, str(p + 20),
                                         str(p - 20), s, "archive")

    def ok(t: int, d: int, sl: Decimal) -> bool:
        return bool(PX.sizing_decision(bars[t].d("mark_open"), d, sl, rules, SizingLimits(), Decimal(1000), regime)[1].ok)

    draws = [PL.p1_draw(d, src, grid, T0, T0 + (N - 1) * MINUTE_MS, ok) for d in range(6)]
    fund = [Funding(T0 + 1000 * MINUTE_MS + 5, "0.0003", "60000")]
    null = PX.p1_null_distribution(draws, bars, fund, rules=rules, limits=SizingLimits(), equity=Decimal(1000), regime=regime)
    return {"draws": json.loads(PL.p1_canonical_json(draws)), "null": null}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
