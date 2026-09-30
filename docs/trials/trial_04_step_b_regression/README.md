# Trial #4 step (b) — trial #2 and trial #3 regression evidence

Change under test: `sizing/config.py` appends `(3, 30)` to `REGISTERED_LEVERAGE_BANDS` (commit `6a47bf2`; test-only follow-up `0ddba1d`).
Bot default and the trial #2/#3 `(10, 30)` configurations are unchanged. Every check is a **gate-free diagnostic** writing only to a fresh
scratch directory outside the repo; closed trial directories are read-only. No new verdict, no OOS.

## t2/ — trial #2 (`scripts/t2_regression_check.py`, unchanged since trial #3 (b))
Re-runs all trial #2 IS runs (205 strategy variants + P1 draws 0..999 in the recorded 8 parts + merge) and byte-compares 1,043 recorded files
(`meta.json` without `git_head`/`gate`); recomputes the evaluator report through `evaluate_t2`'s own compute path (diagnostic, not a new evaluation).

| file | what |
|---|---|
| `baseline_summary.json` | **pre-change** code, git worktree at `b1b03e1` (`--t2-base` = main repo's ignored `var/backtest/t2/IS`); 43:17 wall, max RSS 3.65 GB |
| `after_summary.json` | **post-change** main at `0ddba1d`; 41:22 wall, max RSS 3.67 GB |
| `baseline_rerun_sha256.txt` / `after_rerun_sha256.txt` | `sha256sum` of every non-`meta.json` re-run output (838 files) |

Both: `identical: true`, 1,043 files, 0 mismatches; `report_sha256_rerun` = closed report `9223047c…`; verdict equal.
The two sha lists are byte-identical to each other and to `docs/trials/trial_03_step_b_regression/baseline_rerun_sha256.txt`.

## t3/ — trial #3 (`scripts/t3_regression_check.py`, new in this step)
Re-runs the 8 `run_arm` runs (L/S × 4 variants) from the pinned prepared data (`prepare_t3.load_prepared_pinned`), the 16 P1 parts from the
recorded partition using the **re-run** base trades, and both P1 merges; byte-compares 46 output files against the SHA256s recorded in
`docs/trials/trial_03/records/` (`run.outputs`; merge records: top-level `outputs`). Trial #3's gate (`stage_repo`/`child_gate`/pins/receipts)
is bypassed by design — the trial is closed and its gate refuses from `6a47bf2` on (run once, as trial #2 after #51).

| file | what |
|---|---|
| `baseline_summary.json` | **pre-change** code at `b1b03e1`, checker SHA256 `deaa1c3c…` (before the `check_out` guard); 14:54 wall, max RSS 2.17 GB |
| `after_summary.json` | **post-change** main at `6a47bf2`, checker SHA256 `181507c8…` (= committed version; only adds `check_out`); 14:03 wall, max RSS 2.19 GB |
| `baseline_rerun_sha256.txt` / `after_rerun_sha256.txt` | SHA256 of every re-run file (46); the two lists are byte-identical |

Both: `identical: true`, 46 files (8 runs + 16 P1 parts + 2 merges), 0 mismatches.

Trial #3 gate after this step (read-only check with `backtest.t3_provenance`): of the 51 frozen files, only `sizing/config.py` differs from
freeze v2 `H = f087611f…` (#56); fingerprint `8554df6d…` (#56) → `85f3a8a43323eb7ba034dd6044dbddaed310117cb1d9cb5c6756cd78c17bfa8c`,
so `require_frozen` refuses by design.

Note: a first trial #2 baseline attempt was stopped after ~6 min because its `--out` was a stale scratch directory from trial #3 (b)
(a missing output could have been masked by an old file); the recorded baseline ran into a fresh directory.
