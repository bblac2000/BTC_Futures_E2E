"""격리 러너 테스트용 가짜 전략 — 합성 봉 위에서 30분마다 롱(SL 0.5% · TP 1%)을 낸다. 실데이터를 읽지 않는다."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.engine_replay import ReplayContext, replay
from backtest.replay import write_jsonl
from exchange.loader import rules_from_snapshot_dir
from exchange.orders import Direction
from paper.engine import EntryIntent
from sizing.config import RegimeSizing, SizingLimits

T0 = int(dt.datetime(2024, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
FIX = Path(__file__).resolve().parent / "snapshots"


def bars(n: int) -> list[Bar1m]:
    out = []
    for i in range(n):
        k = i % 240                                    # 삼각파 ±900(±1.5%) — SL 0.5%·TP 1%가 실제로 닿는다
        p = Decimal(60000) + Decimal(-900 + 15 * k if k < 120 else 900 - 15 * (k - 120))
        s = str(p)
        out.append(Bar1m(T0 + i * MINUTE_MS, s, str(p + 30), str(p - 30), s, "1", s, 1, "0", "0", s, str(p + 30), str(p - 30), s,
                         "archive"))
    return out


class Every30:
    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext):
        if ctx.has_position or (bar.open_ms // MINUTE_MS) % 30 != 0:
            return None
        m = bar.d("mark_close")
        return EntryIntent(Direction.LONG, m * Decimal("0.995"), m * Decimal("1.01"), RegimeSizing("t", Decimal("0.01"), 50, 100),
                           decided_ms=ctx.now_ms, decision_mark=m)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=600)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    rules = rules_from_snapshot_dir(FIX, "BTCUSDT")
    r = replay(bars(a.minutes), [Funding(T0 + 480 * MINUTE_MS + 15, "0.0001", "60000")], Every30(), rules=rules,
               limits=SizingLimits(), equity=Decimal("1000"))
    write_jsonl(out / "trades.jsonl", r.trades)
    write_jsonl(out / "decisions.jsonl", r.decisions)
    (out / "summary.json").write_text(json.dumps({"final_wallet": str(r.final_wallet), "n": len(r.trades),
                                                   "open_at_end": r.open_at_end}, sort_keys=True))
    print(f"trades={len(r.trades)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
