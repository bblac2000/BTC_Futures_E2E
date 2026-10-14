"""S-carry-1 실행기(스펙 §4 · §5) — 한 번만(결과 파일이 있으면 `write_result`가 거부).

    uv run python -m research.screens.p1.run
"""
from __future__ import annotations

import numpy as np

from research.screens.p1 import loader, reprice
from research.screens.window import SCREEN_END_MS, SCREEN_START_MS, assert_within, write_result

OUT = loader.DATA.parent / "results" / "S-carry-1.json"
ARMS = {"G1": "v1_restated", "hysteresis": "v2_primary"}
REPORT_ONLY = ("v1_original", "v2_no_accounting_fix")
SUB_START_MS = 1719792000000                                                    # 2024-07-01T00:00Z
SEED, N_DRAW = 20261014, 1000
KEYS = ("net_B_slip_dtb3", "gross", "net_A", "net_B", "net_C", "net_A_dtb3", "net_B_dtb3", "net_C_dtb3", "net_B_dgs2", "dtb3", "dgs2", "orig_net",
        "orig_cost")


def window_stats(rows: list[dict[str, float]], entries: list[int], start_ms: int) -> dict:
    v = np.array([r["net_B_dtb3"] for r in rows])
    out: dict = {"n": len(rows)}
    if not rows:                                                                   # 스펙 §4-4: 통계와 CI는 null
        out.update({"sd_net_B": None, "mean": {k: None for k in KEYS}, "blocks": reprice.n_blocks(start_ms, SCREEN_END_MS),
                    "n_seeded_rate": 0, "mean_net_B_dtb3_without_seeded": None, "sd_net_B_dtb3": None, "mde": None})
        for key in ("net_B_dtb3", "net_A_dtb3", "net_C_dtb3"):
            out[f"ci95_block60_{key}"] = out[f"redraws_{key}"] = out[f"ci95_trade_iid_{key}"] = None
        return out
    out["sd_net_B"] = float(np.std([r["net_B"] for r in rows], ddof=1)) if len(rows) > 1 else None
    out["mean"] = {k: float(np.mean([r[k] for r in rows])) for k in KEYS}
    k = reprice.n_blocks(start_ms, SCREEN_END_MS)
    blocks = np.array([reprice.block_of(e, start_ms) for e in entries])
    out["blocks"] = k
    for key in ("net_B_dtb3", "net_A_dtb3", "net_C_dtb3"):
        vals = np.array([r[key] for r in rows])
        ci, redraws = reprice.block_boot(vals, blocks, k, np.random.default_rng(SEED), N_DRAW)
        out[f"ci95_block60_{key}"], out[f"redraws_{key}"] = ci, redraws
        out[f"ci95_trade_iid_{key}"] = reprice.iid_boot(vals, np.random.default_rng(SEED), N_DRAW)
    keep = [r["net_B_dtb3"] for r in rows if not r["seeded_rate"]]
    out["n_seeded_rate"] = len(rows) - len(keep)
    out["mean_net_B_dtb3_without_seeded"] = float(np.mean(keep)) if keep else None
    if len(rows) >= 2:                                                             # sd(ddof 1)가 정의되는 한 MDE를 적는다
        m0, n_eff, rho = reprice.mde(v, reprice.COEF_UNCORRECTED)
        m1, _, _ = reprice.mde(v, reprice.COEF_N64)
        out["sd_net_B_dtb3"] = float(np.std(v, ddof=1))
        out["mde"] = {"uncorrected_2.80": m0, "n64_4.00": m1, "n64_two_sided_4.20": m0 / 2.80 * 4.20, "n_eff": n_eff, "rho_lag1": rho,
                      "power_label": reprice.power_label(m0)}
    return out


def main() -> int:
    trades, dropped = loader.trades()
    rates = loader.dtb3()
    assert_within([t.exit_ms for t in trades] + [t.entry_ms for t in trades])
    res: dict = {"id": "S-carry-1", "dropped_exit_after_2026_06_30": dropped, "seed": SEED, "n_draw": N_DRAW,
                 "costs_bps": reprice.COSTS, "arms": {}, "report_only": {}}
    for label, run in [*ARMS.items(), *((r, r) for r in REPORT_ONLY)]:
        ts = sorted((t for t in trades if t.run == run), key=lambda t: t.entry_ms)
        rows = [reprice.per_trade(t, rates) for t in ts]
        full = window_stats(rows, [t.entry_ms for t in ts], SCREEN_START_MS)
        sub_i = [i for i, t in enumerate(ts) if t.entry_ms >= SUB_START_MS]
        sub = window_stats([rows[i] for i in sub_i], [ts[i].entry_ms for i in sub_i], SUB_START_MS)
        a = {"run": run, "full": full, "sub_2024_07": sub,
             "orig_net_usdt_sum": float(sum(t.net_pnl for t in ts))}
        if label in ARMS:
            ci = full.get("ci95_block60_net_B_dtb3")
            effect = bool(ci and ci[0] > 0)
            sub_pos = bool(sub.get("n") and sub["mean"]["net_B_dtb3"] > 0)
            mde64 = (full.get("mde") or {}).get("n64_4.00")
            a["effect_pass"] = effect
            a["power_label"] = (full.get("mde") or {}).get("power_label")
            a["promotion"] = {"ci_lower_gt_0": effect, "sub_mean_gt_0": sub_pos, "mde_n64_le_20": bool(mde64 is not None and mde64 <= 20),
                              "all": bool(effect and sub_pos and mde64 is not None and mde64 <= 20)}
            res["arms"][label] = a
        else:
            res["report_only"][label] = a
    s = write_result(OUT, res)
    print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
