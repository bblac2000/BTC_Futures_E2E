# Trial #3 step (b) — trial #2 regression evidence

`scripts/t2_regression_check.py` re-ran **all** trial #2 IS runs (205 strategy variants + P1 draws 0..999 in the recorded 8 parts + merge;
1,043 recorded files compared) with gate-free calls, read-only on `var/backtest/t2/IS`, writing only to a scratch directory.

| file | what |
|---|---|
| `baseline_summary.json` | run on **pre-change** code in a git worktree at `77cef80` (`--t2-base` = main repo's ignored `var/backtest/t2/IS`); 36:05 wall, max RSS 3.64 GB |
| `after_summary.json` | run on **post-change** main at `dc23273`; 35:33 wall, max RSS 3.63 GB |
| `baseline_rerun_sha256.txt` / `after_rerun_sha256.txt` | `sha256sum` of every non-`meta.json` re-run output (838 files); the two lists are byte-identical |

Both: `identical: true`, 0 mismatches against the recorded trial #2 outputs (`meta.json` compared without `git_head`/`gate`).
The evaluator hash (`report_sha256_rerun` = `9223047c…`) is a **diagnostic recomputation** through `evaluate_t2`'s own
`compute → verdict_is → report` path with the provenance/inventory/write steps removed (plan r2 B3) — not a new trial #2 evaluation;
the closed `evaluation/` was not touched. A gated rerun is one-shot and, after `dc23273`, refuses on main by design.
Trial #2 provenance fingerprint: `9416d9e2…` at `77cef80` (= recorded gate fingerprint); `1f08d389…` on main at `dc23273`.
