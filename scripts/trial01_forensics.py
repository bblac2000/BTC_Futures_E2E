"""트라이얼 #1 사후 측정(사용자 2026-09-22 · 사전등록 없이 허용된 **실행 사실** 측정 — 전략 가설 아님 · 판정 불변).

    uv run python scripts/trial01_forensics.py

(a) Arm A 청산(liquidation) 26건 포렌식: 레버리지 · 체결 뒤 sl_dist · 추정 청산 거리 · 사건 1m 봉(mark·kline 극값과 range) ·
    봉 안에서 SL과 청산가를 한 번에 지났는지(유형) · 진입 뒤 경과 시간 · 그 봉의 불리한 극값을 견디는 **가장 높은 레버리지**
    (같은 명목 · 진입 시점 청산식 · 펀딩 무시). 결과는 open-decisions #1(레버리지 범위) 판단 자료 — 트라이얼과 무관.
(b) sl_dist_out_of_range로 건너뛴 셋업의 sl_dist 분포(0 이하 = SL이 잘못된 쪽 · 0.30% 미만 · 1.00% 초과).
출력: `var/backtest/IS/step_e/forensics.json` + 표준출력 요약.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest import prepare as PR  # noqa: E402
from backtest.data import Bar1m  # noqa: E402
from exchange.decimal_context import exec_context  # noqa: E402
from exchange.orders import Direction  # noqa: E402
from sizing.position import liquidation_estimate  # noqa: E402
from strategies.trial01.run import load_rules  # noqa: E402

STEP_E = ROOT / "var" / "backtest" / "IS" / "step_e"
MIN = 60_000


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def liquidation_forensics(rules, bars: dict[int, Bar1m]) -> list[dict]:
    out = []
    for t in jl(STEP_E / "A" / "trades.jsonl"):
        if t["exit_reason"] != "liquidation":
            continue
        d = Direction(t["direction"])
        long_ = d is Direction.LONG
        E, sl, liq = Decimal(t["entry_fill"]), Decimal(t["sl"]), Decimal(t["exit_ref"])
        L, qty = int(t["leverage"]), Decimal(t["qty"])
        b = bars[t["exit_ms"] - (MIN - 1)]
        mo, mh, ml, mc = (b.d(k) for k in ("mark_open", "mark_high", "mark_low", "mark_close"))
        kh, kl = b.d("high"), b.d("low")
        prev = bars.get(b.open_ms - MIN)
        if long_:
            kind = ("opened beyond liquidation" if mo <= liq else
                    "opened past SL, before liquidation" if mo <= sl else
                    "crossed SL and liquidation inside one bar")
            extreme = ml
            excursion = (E - ml) / E
        else:
            kind = ("opened beyond liquidation" if mo >= liq else
                    "opened past SL, before liquidation" if mo >= sl else
                    "crossed SL and liquidation inside one bar")
            extreme = mh
            excursion = (mh - E) / E
        n = qty * E
        survive = None
        with exec_context():
            for lev in range(L, 0, -1):
                try:
                    p = liquidation_estimate(d, E, n, lev, rules).price
                except Exception:  # noqa: BLE001 — 브라켓 밖 등
                    continue
                if (long_ and p < extreme) or (not long_ and p > extreme):
                    survive = lev
                    break
        out.append({
            "trade_id": t["trade_id"], "direction": d.value, "leverage": L, "entry_fill": str(E), "sl": str(sl),
            "sl_dist": float(Decimal(t["sl_dist"])), "liq_price": str(liq), "liq_dist": float(abs(E - liq) / E),
            "minutes_since_entry": (t["exit_ms"] - t["entry_ms"]) / MIN,
            "bar_open_utc_ms": b.open_ms, "mark_ohlc": [str(mo), str(mh), str(ml), str(mc)],
            "mark_range_pct": float((mh - ml) / E), "kline_high_low": [str(kh), str(kl)],
            "kline_minus_mark_extreme": str((kl - ml) if long_ else (kh - mh)),
            "prev_mark_close": None if prev is None else str(prev.d("mark_close")),
            "adverse_excursion_pct": float(excursion), "kind": kind, "max_surviving_leverage": survive,
        })
    return out


def skip_distribution(arm: str) -> dict:
    xs = np.array([float(Decimal(d["sl_dist"])) for d in jl(STEP_E / arm / "decisions.jsonl")
                   if d.get("reason") == "sl_dist_out_of_range"])
    below_zero, low, high = xs[xs <= 0], xs[(xs > 0) & (xs < 0.003)], xs[xs > 0.01]

    def q(a: np.ndarray) -> dict:
        if not len(a):
            return {"n": 0}
        qs = np.quantile(a, [0.1, 0.25, 0.5, 0.75, 0.9])
        return {"n": int(len(a)), "p10": float(qs[0]), "p25": float(qs[1]), "median": float(qs[2]),
                "p75": float(qs[3]), "p90": float(qs[4])}
    return {"n": int(len(xs)), "le_0 (SL wrong side)": q(below_zero), "below_0.30%": q(low), "above_1.00%": q(high),
            "share_below_0.30%": float(len(low) / len(xs)), "share_above_1.00%": float(len(high) / len(xs)),
            "share_le_0": float(len(below_zero) / len(xs))}


def main() -> None:
    rules = load_rules()
    bars = {b.open_ms: b for b in PR.read_bars(ROOT / "var" / "backtest" / "IS" / "bars_1m.parquet")}
    liq = liquidation_forensics(rules, bars)
    kinds: dict[str, int] = {}
    for r in liq:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    res = {"liquidations": liq, "liquidation_kinds": kinds,
           "skip_sl_dist": {a: skip_distribution(a) for a in ("A", "B")}}
    (STEP_E / "forensics.json").write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps({"liquidation_kinds": kinds, "n": len(liq)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
