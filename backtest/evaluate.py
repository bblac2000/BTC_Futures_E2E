"""단계 e 판정기 — 사전등록 §3(게이트)·§4(플라시보)·§7(판정) · 레지스트리 #19·#21·#22·#24. **실행 전에 커밋된다.**

    python -m backtest.evaluate --step-e-dir var/backtest/IS/step_e

- 입력은 격리 실행의 산출물(파일)뿐 — 전략 모듈을 import하지 않는다.
- **모든 실행이 끝나기 전에는 아무 파일도 열지 않는다**: 필요한 산출물(A·B·P2 두 개·P3·P4 200·P1 1,000)이 하나라도 없으면
  읽기 전에 거부한다(사용자 2026-09-22 "Do not open any output until every run has finished").
- OOS(G3)는 계산하지 않는다 — IS 판정만 · OOS 개봉은 사용자 결정.
- 모든 통계는 순수 함수(아래) — 테스트는 합성 입력으로만.

## 해석(레지스트리 #24 — 사전등록이 정하지 않은 것 · 실행 전 기록)
- G0: `n ≥ 48` 그리고 `n / (1 + 4·max(ρ̂, 0.15)) ≥ 30` · ρ̂ = 진입 순 net_bps의 lag-1 자기상관.
- G1 = gross 평균 > 0 ∧ 97.5% CI 하한 > 0 · G2 = net 평균 > 0 ∧ 97.5% CI 하한 > 0. **θ = 10 bps는 §7 분류에만**(참고로 CI 하한 대 θ를 함께 보고).
- 부트스트랩: 블록 = 진입 UTC 달력일(빈 날 유지) · 10,000회 · `SeedSequence((20260921, 1)).spawn(8)[k]`, k = 통계별 고정 번호(`BOOT_CHILD`).
- G-B: 계열 = 트레이드당 net_bps · `PSR(SR*=0) > 0.5` ∧ `n ≥ 30` ∧ `SR̂_A − SR* > 0`(SR* = expected_max_sr([SR̂_A, SR̂_B], N=2)) · 확률형 PSR(SR*) 보고.
- 벤치마크 ① flat 게이트 = Arm A **순손익 합(Σ net_pnl) > 0** · ② P1 노출 정합 게이트 = P1 기각 규칙 · ③ 매수보유(보고만):
  UTC 일 마지막 1m 봉 **kline 종가**의 일간 수익률 Sharpe(연율화 없음)·창 수익률 · Arm A 일간 수익률 = 그날 **청산된** 트레이드 Σ net_pnl ÷ 그날 시작 지갑
  (거래 없는 날 0) · A 일간 Sharpe < 매수보유 일간 Sharpe면 라벨 `ACCEPT — 수동(매수보유)을 이기지는 못함`(판정 변경 아님).
- A/B: 전제 Arm B G0 통과 · Arm A net 평균 > Arm B net 평균 ∧ 짝지음 차이 97.5% CI 하한 > 0.
- 플라시보 원판 = Arm A: P1 `원판 ≤ p95(성공 추출의 트레이드당 평균 net_bps)` → 기각 · 실패 > 10 → **평가 불가 = 폐기** ·
  P2 `원판 ≤ max(+1, +5)` · P3 `원판 ≤ 반전` · P4 `p95(200 추출 평균) ≥ 원판` → 기각. "순엣지" = 트레이드당 평균 net_bps.
- §7 분류(REJECT일 때): MDE = (z₀.₉₇₅ + z₀.₈)·σ(net_bps)/√n_eff(G0와 같은 n_eff) · MDE > 20 → 검정력 부족 ·
  MDE < 5 ∧ net CI 상한 < θ → 효과 부재 · 그 사이 → 결론 보류형.
- 트레이드 0건 = 즉시 FAIL · 창 끝 포지션은 `open_at_end`(트레이드 아님 · #19 ⑤).
- P4 추출 중 트레이드 0건인 것은 순엣지가 정의되지 않으므로 p95 계산에서 빼고 개수를 보고한다(0으로 채우지 않는다).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from backtest import placebo as PL
from backtest import stats as S
from strategies.trial01 import anchor as A

THETA_BPS = 10.0
G0_N_MIN, G0_NEFF_MIN, RHO_PLAN = 48, 30.0, 0.15
GB_N_MIN = 30
LEVEL = 0.975                                              # 양측 97.5% CI(하한 = 1.25 백분위 · #19 ①)
BOOT_CHILD = {"gross_A": 0, "net_A": 1, "gross_B": 2, "net_B": 3, "diff_AB": 4}
MDE_POWER_LACK, MDE_ABSENT = 2 * THETA_BPS, 0.5 * THETA_BPS
DAY_MS = 86_400_000
BASE_RUNS = ("A", "B", "P2_delay1", "P2_delay5", "P3_invert")
STRATEGY_MODULE = "strategies.trial01.strategy"
BH_LABEL = "ACCEPT — 수동(매수보유)을 이기지는 못함"


@dataclass(frozen=True)
class Trade:
    entry_ms: int
    exit_ms: int
    gross_bps: float
    net_bps: float
    net_pnl: Decimal
    exit_reason: str


def trades_from_rows(rows: Sequence[dict[str, Any]]) -> list[Trade]:
    out = [Trade(int(r["entry_ms"]), int(r["exit_ms"]), float(Decimal(r["gross_bps"])), float(Decimal(r["net_bps"])),
                 Decimal(r["net_pnl"]), str(r["exit_reason"])) for r in rows]
    return sorted(out, key=lambda t: (t.entry_ms, t.exit_ms))


def boot_rng(stat: str) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(list(A.BOOTSTRAP_SEED)).spawn(8)[BOOT_CHILD[stat]]))


# ── 게이트 ──────────────────────────────────────────────────────────────────
def g0(nets: Sequence[float]) -> dict[str, Any]:
    n = len(nets)
    rho = S.lag1_autocorr(nets)
    neff = S.n_eff(n, max(rho, RHO_PLAN)) if n else 0.0
    return {"n": n, "rho_hat": rho, "rho_used": max(rho, RHO_PLAN), "n_eff": neff,
            "pass": n >= G0_N_MIN and neff >= G0_NEFF_MIN}


def mean_ci(trades: Sequence[Trade], field: str, stat: str, start_ms: int, end_ms: int,
            resamples: int = A.BOOTSTRAP_RESAMPLES) -> S.CI:
    pairs = [(t.entry_ms, getattr(t, field)) for t in trades]
    return S.block_bootstrap_mean(pairs, start_ms, end_ms, resamples=resamples, level=LEVEL, rng=boot_rng(stat))


def ci_gate(ci: S.CI) -> dict[str, Any]:
    return asdict(ci) | {"pass": ci.mean > 0 and ci.lo > 0}


def gate_b(nets_a: Sequence[float], nets_b: Sequence[float]) -> dict[str, Any]:
    sr_a, sr_b = S.sharpe(nets_a), S.sharpe(nets_b)
    sr_star = S.expected_max_sr([sr_a, sr_b], A.N_TRIALS) if math.isfinite(sr_a) and math.isfinite(sr_b) else float("nan")
    p0 = S.psr(nets_a, 0.0)
    dsr = sr_a - sr_star
    return {"sr_A": sr_a, "sr_B": sr_b, "sr_star": sr_star, "psr_0": p0, "psr_sr_star": S.psr(nets_a, sr_star),
            "dsr_shrunk": dsr, "n": len(nets_a),
            "pass": (p0 > 0.5) and len(nets_a) >= GB_N_MIN and math.isfinite(dsr) and dsr > 0}


def ab_compare(a: Sequence[Trade], b: Sequence[Trade], start_ms: int, end_ms: int, g0_b: dict[str, Any],
               resamples: int = A.BOOTSTRAP_RESAMPLES) -> dict[str, Any]:
    ci = S.paired_block_bootstrap_diff([(t.entry_ms, t.net_bps) for t in a], [(t.entry_ms, t.net_bps) for t in b],
                                       start_ms, end_ms, resamples=resamples, level=LEVEL, rng=boot_rng("diff_AB"))
    ma = sum(t.net_bps for t in a) / len(a) if a else float("nan")
    mb = sum(t.net_bps for t in b) / len(b) if b else float("nan")
    return asdict(ci) | {"mean_A": ma, "mean_B": mb, "precondition_B_g0": g0_b["pass"],
                         "pass": bool(g0_b["pass"]) and ma > mb and ci.lo > 0}


def mean_net(trades: Sequence[Trade]) -> float:
    return sum(t.net_bps for t in trades) / len(trades) if trades else float("nan")


def placebos(orig: float, p1_means: Sequence[float], p1_failures: int, p2: tuple[float, float], p3: float,
             p4_means: Sequence[float]) -> dict[str, Any]:
    p1_ok = p1_failures <= PL.P1_FAIL_LIMIT
    p1_p95 = PL.p95(p1_means) if p1_means else float("nan")
    p4_p95 = PL.p95(p4_means) if p4_means else float("nan")
    return {
        "P1": {"evaluable": p1_ok, "failures": p1_failures, "draws_ok": len(p1_means), "p95": p1_p95,
               "reject": (not p1_ok) or PL.p1_rejects(orig, p1_means) if p1_means else True},
        "P2": {"delay1": p2[0], "delay5": p2[1], "reject": PL.p2_rejects(orig, p2[0], p2[1])},
        "P3": {"inverted": p3, "reject": PL.p3_rejects(orig, p3)},
        "P4": {"draws": len(p4_means), "p95": p4_p95, "reject": PL.p4_rejects(orig, p4_means) if p4_means else True},
        "original_mean_net_bps": orig,
    }


# ── 벤치마크(보고) ───────────────────────────────────────────────────────────
def daily_closes(bars: Sequence[tuple[int, Decimal]]) -> list[tuple[int, Decimal]]:
    """(open_ms, kline close) → UTC 일마다 마지막 1m 봉 종가."""
    last: dict[int, tuple[int, Decimal]] = {}
    for t, c in bars:
        d = t // DAY_MS
        if d not in last or t > last[d][0]:
            last[d] = (t, c)
    return [(d, last[d][1]) for d in sorted(last)]


def buy_hold(bars: Sequence[tuple[int, Decimal]]) -> dict[str, Any]:
    dc = daily_closes(bars)
    rets = [float(dc[i][1] / dc[i - 1][1] - 1) for i in range(1, len(dc))]
    return {"daily_sharpe": S.sharpe(rets), "window_return": float(dc[-1][1] / dc[0][1] - 1) if dc else float("nan"),
            "days": len(rets)}


def strategy_daily(trades: Sequence[Trade], equity0: Decimal, start_ms: int, end_ms: int) -> dict[str, Any]:
    by_day: dict[int, Decimal] = {}
    for t in trades:
        by_day[t.exit_ms // DAY_MS] = by_day.get(t.exit_ms // DAY_MS, Decimal()) + t.net_pnl
    wallet, rets = equity0, []
    for d in range(start_ms // DAY_MS, end_ms // DAY_MS + 1):
        pnl = by_day.get(d, Decimal())
        rets.append(float(pnl / wallet) if wallet != 0 else 0.0)
        wallet += pnl
    return {"daily_sharpe": S.sharpe(rets), "net_pnl_total": str(sum((t.net_pnl for t in trades), Decimal())),
            "final_wallet": str(wallet), "days": len(rets)}


# ── §7 분류 · 판정 ──────────────────────────────────────────────────────────
def classify_reject(nets: Sequence[float], neff: float, net_ci_hi: float) -> dict[str, Any]:
    sd = float(np.std(np.asarray(nets, dtype=float), ddof=1)) if len(nets) > 1 else float("nan")
    m = S.mde(sd, neff, alpha=A.ALPHA) if neff > 0 and math.isfinite(sd) else float("inf")
    if m > MDE_POWER_LACK:
        kind = "검정력 부족"
    elif m < MDE_ABSENT and net_ci_hi < THETA_BPS:
        kind = "효과 부재"
    else:
        kind = "결론 보류형 REJECT"
    return {"sd_net_bps": sd, "mde_bps": m, "kind": kind}


def verdict(g: dict[str, Any]) -> dict[str, Any]:
    """IS 판정 — ACCEPT는 G3(OOS) 뒤에만 가능하므로 IS 통과는 'IS PASS'로 적는다."""
    if g["n_trades_A"] == 0:
        return {"is_verdict": "FAIL — 트레이드 0건", "failed": ["trades"]}
    if not g["placebo"]["P1"]["evaluable"]:
        return {"is_verdict": "폐기 — P1 평가 불가(실패 > 10)", "failed": ["P1_evaluable"]}
    checks = {"G0": g["G0_A"]["pass"], "G1": g["G1_A"]["pass"], "G2": g["G2_A"]["pass"], "G-B": g["GB"]["pass"],
              "bench_flat": g["bench"]["flat_pass"], "bench_P1": not g["placebo"]["P1"]["reject"],
              "A/B": g["AB"]["pass"], "P1": not g["placebo"]["P1"]["reject"], "P2": not g["placebo"]["P2"]["reject"],
              "P3": not g["placebo"]["P3"]["reject"], "P4": not g["placebo"]["P4"]["reject"]}
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        label = BH_LABEL if g["bench"]["A_daily_sharpe"] < g["bench"]["bh_daily_sharpe"] else None
        return {"is_verdict": "IS PASS — G3(OOS 1회 개봉)는 사용자 결정 대기", "failed": [], "checks": checks,
                "label_if_accepted": label}
    return {"is_verdict": "REJECT", "failed": failed, "checks": checks,
            "classification": classify_reject(g["_nets_A"], g["G0_A"]["n_eff"], g["G2_A"]["hi"])}


def evaluate(a: list[Trade], b: list[Trade], *, p2: tuple[float, float], p3: float, p1_means: Sequence[float],
             p1_failures: int, p4_means: Sequence[float], bars_close: Sequence[tuple[int, Decimal]],
             start_ms: int, end_ms: int, equity0: Decimal, resamples: int = A.BOOTSTRAP_RESAMPLES) -> dict[str, Any]:
    nets_a, nets_b = [t.net_bps for t in a], [t.net_bps for t in b]
    g: dict[str, Any] = {"n_trades_A": len(a), "n_trades_B": len(b), "_nets_A": nets_a}
    if not a:
        return {"verdict": verdict(g) | {}, "n_trades_A": 0}
    g["G0_A"], g["G0_B"] = g0(nets_a), g0(nets_b)
    g["G1_A"] = ci_gate(mean_ci(a, "gross_bps", "gross_A", start_ms, end_ms, resamples))
    g["G2_A"] = ci_gate(mean_ci(a, "net_bps", "net_A", start_ms, end_ms, resamples))
    g["G2_A"]["theta_bps"], g["G2_A"]["ci_lo_ge_theta"] = THETA_BPS, g["G2_A"]["lo"] >= THETA_BPS
    g["G1_B"] = asdict(mean_ci(b, "gross_bps", "gross_B", start_ms, end_ms, resamples)) if b else None
    g["G2_B"] = asdict(mean_ci(b, "net_bps", "net_B", start_ms, end_ms, resamples)) if b else None
    g["GB"] = gate_b(nets_a, nets_b)
    g["AB"] = ab_compare(a, b, start_ms, end_ms, g["G0_B"], resamples)
    sa = strategy_daily(a, equity0, start_ms, end_ms)
    bh = buy_hold(bars_close)
    g["bench"] = {"flat_pass": Decimal(sa["net_pnl_total"]) > 0, "A_net_pnl_total": sa["net_pnl_total"],
                  "A_final_wallet": sa["final_wallet"], "A_daily_sharpe": sa["daily_sharpe"],
                  "bh_daily_sharpe": bh["daily_sharpe"], "bh_window_return": bh["window_return"]}
    g["placebo"] = placebos(mean_net(a), p1_means, p1_failures, p2, p3, p4_means)
    g["verdict"] = verdict(g)
    g.pop("_nets_A")
    return g


# ── 보고 부록(게이트 아님) ────────────────────────────────────────────────────
def holding(trades: Sequence[Trade]) -> dict[str, Any]:
    mins = np.asarray([(t.exit_ms - t.entry_ms) / 60_000 for t in trades], dtype=float)
    if not len(mins):
        return {"n": 0}
    q = np.quantile(mins, [0.1, 0.25, 0.5, 0.75, 0.9])
    return {"n": len(mins), "mean_min": float(mins.mean()), "p10": float(q[0]), "p25": float(q[1]), "median": float(q[2]),
            "p75": float(q[3]), "p90": float(q[4]), "max": float(mins.max()),
            "share_ge_60min": float((mins >= 60).mean()), "share_ge_240min": float((mins >= 240).mean())}


def skip_rates(summary: dict[str, Any]) -> dict[str, Any]:
    n = summary["decision_counts"]
    cand = summary["candidates"]

    def rate(k: str) -> float:
        return n.get(k, 0) / cand if cand else float("nan")

    return {"candidates": cand, "sl_dist_out_of_range": rate("sl_dist_out_of_range"), "no_sl_anchor": rate("no_sl_anchor"),
            "conflict_signal": rate("conflict_signal"), "counts": n}


# ── 파일 ───────────────────────────────────────────────────────────────────
def required_paths(root: Path) -> list[Path]:
    out = [root / r / f for r in BASE_RUNS for f in ("trades.jsonl", "summary.json")]
    out += [root / "P4" / f"P4_draw{d:03d}" / "trades.jsonl" for d in range(A.P4_DRAWS)]
    out += [root / "P1" / "p1_null.jsonl", root / "P1" / "p1_draws.json"]
    return out


def missing(root: Path) -> list[Path]:
    return [p for p in required_paths(root) if not p.exists()]


def _jsonl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step-e-dir", required=True)
    ap.add_argument("--is-dir", default=None)
    a = ap.parse_args(argv)
    if STRATEGY_MODULE in sys.modules:
        raise AssertionError("판정기는 전략 모듈을 import하지 않는다(격리)")
    root = Path(a.step_e_dir)
    miss = missing(root)
    if miss:
        print(json.dumps({"refused": "산출물이 다 갖춰지기 전에는 열지 않는다", "missing": len(miss),
                          "first": [str(p) for p in miss[:5]]}, ensure_ascii=False))
        return 3
    from backtest import prepare as PR
    is_dir = Path(a.is_dir) if a.is_dir else root.parent
    bars = PR.read_bars(is_dir / "bars_1m.parquet")
    start, end = A.IS_START_MS, A.IS_END_MS
    tr = {r: trades_from_rows(_jsonl(root / r / "trades.jsonl")) for r in BASE_RUNS}
    summ = {r: json.loads((root / r / "summary.json").read_text()) for r in BASE_RUNS}
    p4 = [mean_net(trades_from_rows(_jsonl(root / "P4" / f"P4_draw{d:03d}" / "trades.jsonl"))) for d in range(A.P4_DRAWS)]
    p1_rows = _jsonl(root / "P1" / "p1_null.jsonl")
    p1_draws = json.loads((root / "P1" / "p1_draws.json").read_text())
    p1_fail = sum(1 for d in p1_draws if not d["ok"])
    g = evaluate(tr["A"], tr["B"], p2=(mean_net(tr["P2_delay1"]), mean_net(tr["P2_delay5"])), p3=mean_net(tr["P3_invert"]),
                 p1_means=[float(Decimal(r["mean_net_bps"])) for r in p1_rows], p1_failures=p1_fail,
                 p4_means=[x for x in p4 if math.isfinite(x)],
                 bars_close=[(b.open_ms, b.d("close")) for b in bars], start_ms=start, end_ms=end, equity0=Decimal("1000"))
    days = (end - start + 1) / DAY_MS
    g["appendix"] = {
        "holding_minutes": {r: holding(tr[r]) for r in ("A", "B")},
        "trades_per_day": {r: len(tr[r]) / days for r in BASE_RUNS},
        "exit_reasons": {r: dict(Counter(t.exit_reason for t in tr[r])) for r in ("A", "B")},
        "skip_rates": {r: skip_rates(summ[r]) for r in BASE_RUNS},
        "open_at_end": {r: summ[r].get("open_at_end") for r in BASE_RUNS},
        "sr_v1_sha256_ok": all(summ[r].get("sr_v1_sha256") == A.SR_V1_SHA256 for r in BASE_RUNS),
        "p4_draws_without_trades": sum(1 for x in p4 if not math.isfinite(x)),
        "window": {"start_ms": start, "end_ms": end, "days": days},
        "evaluated_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (root / "report.json").write_text(json.dumps(g, sort_keys=True, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({"written": str(root / "report.json"), "is_verdict": g["verdict"]["is_verdict"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
