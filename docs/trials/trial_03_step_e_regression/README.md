# Trial #3 step (e) — trial #2 regression after the shared `placebo_exec.run_time_exit` fix

Shared change (commit `1d5f941`): `run_time_exit` passes its `reason` argument to `Engine.close_now` (previously overwritten by the
string `"liquidation"`) and asserts the engine exit reason. `scripts/t2_regression_check.py` (no `--skip-runs`) re-ran all 205 trial #2
strategy runs + P1 draws 0..999 in 8 parts + merge on main at `1d5f941`: `identical: true`, 0 mismatches over 1,043 recorded files
(`meta.json` compared without `git_head`/`gate`), diagnostic evaluator recomputation `9223047c…` = closed report; 30:41 wall, max RSS 3.67 GB.
`after_rerun_sha256.txt` (838 non-meta files) is byte-identical to `../trial_03_step_b_regression/baseline_rerun_sha256.txt`
(the pre-change baseline at `77cef80`). Trial #1's P1 golden (`tests/fixtures/golden_p1_trial01.json`, `tests/test_p1_core.py`) passes.
