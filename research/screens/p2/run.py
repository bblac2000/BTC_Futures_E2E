"""S-xs-carry-1 실행기(스펙 r6 §6 · §7) — 한 번만(결과 파일이 있으면 `write_result`가 거부).

    uv run python -m research.screens.p2.run
"""
from __future__ import annotations

import math

import numpy as np

from research.screens.p2 import compute, loader
from research.screens.window import assert_within, write_result

OUT = loader.Path(__file__).resolve().parent / "results" / "S-xs-carry-1.json"
FIRST_T = 1612742400000                                                         # 2021-02-08T00:00Z(월)
LAST_T = 1782086400000                                                          # 2026-06-22T00:00Z(월)
SUB_T = 1719792000000                                                           # 2024-07-01T00:00Z
SEED, N_DRAW = 20261014, 1000


def stats_block(weeks: list[compute.Week], hold: list[bool], traded: list[float], rates: list[tuple[str, float]], sel: list[int]) -> dict:
    ix = [k for k in sel if hold[k]]
    if not ix:
        return {"n_weeks": 0}
    R = np.array([sum(compute.leg_returns(weeks[k])) for k in ix])
    Lg = np.array([compute.leg_returns(weeks[k])[0] for k in ix])
    Sg = np.array([compute.leg_returns(weeks[k])[1] for k in ix])
    cost = np.array([compute.TAKER_BPS * traded[k] for k in ix])
    maker = np.array([compute.MAKER_BPS * traded[k] for k in ix])
    price = np.array([1e4 * (float(np.mean(weeks[k].r[weeks[k].long])) - float(np.mean(weeks[k].r[weeks[k].short]))) for k in ix])
    fund = np.array([1e4 * (float(np.mean(weeks[k].f[weeks[k].short])) - float(np.mean(weeks[k].f[weeks[k].long]))) for k in ix])
    bench = np.array([compute.dtb3_weekly_bps(rates, weeks[k].t0) for k in ix])
    net = R - cost
    sd = lambda a: float(np.std(a, ddof=1)) if a.size > 1 else None  # noqa: E731
    return {"n_weeks": len(ix), "mean_R": float(R.mean()), "mean_C": float(cost.mean()), "mean_net": float(net.mean()),
            "mean_net_maker": float((R - maker).mean()), "mean_price_part": float(price.mean()), "mean_funding_part": float(fund.mean()),
            "sd_long_leg": sd(Lg), "sd_short_leg": sd(Sg), "sd_net": sd(net), "mean_net_minus_dtb3": float((net - bench).mean()),
            "mean_dtb3_weekly_bps": float(bench.mean()), "cost_clause": bool(R.mean() >= 1.5 * cost.mean()),
            "mde_net": compute.mde(net)}


def ic_block(weeks: list[compute.Week], ix: list[int], keep_fn=None) -> dict:  # noqa: ANN001
    ics, ics_price = [], []
    for k in ix:
        w = weeks[k]
        keep = np.ones(len(w.names), dtype=bool) if keep_fn is None else keep_fn(w)
        v = compute.spearman(w.s0[keep], w.y[keep]) if keep.sum() >= compute.MIN_N else None
        if v is not None:
            ics.append(v)
        p = compute.spearman(w.s0[keep], -w.r[keep]) if keep.sum() >= compute.MIN_N else None
        if p is not None:
            ics_price.append(p)
    spr = [sum(compute.leg_returns(weeks[k], None if keep_fn is None else keep_fn(weeks[k]))) for k in ix]
    spr = [v for v in spr if math.isfinite(v)]
    return {"n_ic": len(ics), "mean_ic": float(np.mean(ics)) if ics else None, "t": compute.t_stat(ics),
            "mean_R_gross": float(np.mean(spr)) if spr else None,
            "price_only_mean_ic": float(np.mean(ics_price)) if ics_price else None, "price_only_t": compute.t_stat(ics_price)}


def main() -> int:
    syms = [loader.read_symbol(n) for n in loader.symbols()]
    rates = loader.dtb3()
    t_list = list(range(FIRST_T, LAST_T + 1, compute.WEEK))
    weeks: list[compute.Week] = []
    counts: list[int] = []
    for t0 in t_list:
        rows = []
        for sym in syms:
            e = compute.eligible(sym, t0)
            if e is not None:
                rows.append((e, compute.outcome(sym, e, t0)))
        counts.append(len(rows))
        weeks.append(compute.build_week(t0, rows))
        assert_within([t0 - 2 * compute.WEEK] + [o.x for _, o in rows])
    hold = [c >= compute.MIN_N for c in counts]
    traded = compute.turnover(weeks, hold)
    H_ix = [k for k in range(len(weeks)) if hold[k]]

    # ① ② — IC가 정의된 주만(정의 안 되면 빼고 센다)
    obs: list[float] = []
    null_in: list[tuple[np.ndarray, np.ndarray]] = []
    undefined_ic = 0
    for k in H_ix:
        v = compute.spearman(weeks[k].s0, weeks[k].y)
        if v is None:
            undefined_ic += 1
            continue
        obs.append(v)
        null_in.append((weeks[k].s0, weeks[k].y))
    ic0 = float(np.mean(obs)) if obs else math.nan
    t0_stat = compute.t_stat(obs)
    null = compute.shuffle_null(null_in, SEED, N_DRAW) if obs else []
    p95 = float(np.percentile(null, 95)) if null and all(math.isfinite(x) for x in null) else None

    # ③ 지연
    lag, matched, lag_names = [], [], []
    lag_excluded = 0
    for k in H_ix:
        w = weeks[k]
        keep = np.array([s is not None for s in w.s1])
        if keep.sum() < compute.MIN_N:
            lag_excluded += 1
            continue
        s1 = np.array([s for s in w.s1 if s is not None])
        v = compute.spearman(s1, w.y[keep])
        if v is None:
            lag_excluded += 1
            continue
        lag.append(v)
        lag_names.append(int(keep.sum()))
        m = compute.spearman(w.s0[keep], w.y[keep])
        if m is not None:
            matched.append(m)
    ic_lag = float(np.mean(lag)) if lag else math.nan
    t_lag = compute.t_stat(lag)

    full = stats_block(weeks, hold, traded, rates, list(range(len(weeks))))
    sub = stats_block(weeks, hold, traded, rates, [k for k in range(len(weeks)) if weeks[k].t0 >= SUB_T])
    infeasible = any(v is not None and v > 250 for v in (full.get("sd_long_leg"), full.get("sd_short_leg")))
    defined = (len(obs) >= 3 and t0_stat is not None and p95 is not None and math.isfinite(ic0) and len(lag) >= 3 and t_lag is not None
               and math.isfinite(ic_lag))
    c1 = bool(defined and t0_stat is not None and t0_stat >= 2)
    c2 = bool(defined and p95 is not None and ic0 > p95)
    c3 = bool(defined and t_lag is not None and abs(ic_lag) <= 0.5 * abs(ic0) and t_lag < 2)
    ca = bool(full.get("cost_clause"))
    verdict = "실행 불가" if infeasible else ("PASS" if (defined and c1 and c2 and c3 and ca) else "FAIL")

    early = sum(int(weeks[k].forced.sum()) for k in H_ix)
    deficit = sum(int(weeks[k].fund_deficit.sum()) for k in H_ix)
    res = {
        "id": "S-xs-carry-1", "verdict": verdict, "infeasible": infeasible, "defined": defined,
        "conditions": {"ic_t_ge_2": c1, "ic_gt_null_p95": c2, "lag_collapse": c3, "cost_clause": ca},
        "ic": {"n_ic": len(obs), "undefined_weeks": undefined_ic, "mean_ic": ic0, "t": t0_stat, "null_p95": p95,
               "null_mean": float(np.mean(null)) if null else None, "seed": SEED, "n_draw": N_DRAW},
        "lag": {"n_weeks": len(lag), "excluded_weeks": lag_excluded, "mean_ic_lag1": ic_lag, "t_lag1": t_lag,
                "matched_ic0_same_names_weeks": float(np.mean(matched)) if matched else None,
                "names_per_week_median": float(np.median(lag_names)) if lag_names else None},
        "spread_full": full, "spread_sub_2024_07": sub,
        "ic_sub_2024_07": ic_block(weeks, [k for k in H_ix if weeks[k].t0 >= SUB_T]),
        "ic_full_report": ic_block(weeks, H_ix),
        "sensitivity_excl_early_exit": ic_block(weeks, H_ix, lambda w: ~w.forced),
        "sensitivity_excl_funding_deficit": ic_block(weeks, H_ix, lambda w: ~w.fund_deficit),
        "weeks": {"scheduled": len(weeks), "holding": len(H_ix), "below_min_n": len(weeks) - len(H_ix),
                  "eligible_count_quantiles": [float(x) for x in np.percentile(counts, [0, 25, 50, 75, 100])]},
        "early_exit_name_weeks": early, "funding_deficit_name_weeks": deficit,
        "missing_settlements": sum(weeks[k].missing for k in H_ix), "collisions": sum(weeks[k].collisions for k in H_ix),
        "symbols_loaded": len(syms),
        "note": "단일 스크린 · 매매 근거 아님 · 이른 청산 가격은 대체값(스펙 §4-3) · 입력 목록과 SHA256은 fetch_manifest.tsv",
    }
    print(write_result(OUT, res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
