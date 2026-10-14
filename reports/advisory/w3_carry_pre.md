# W3 · S-carry-1 PRE(착수 전 검토) + P0 강화 POST

- advisor PRE(#105 이후 단계 전체 · 한 번의 호출): 아래는 **요약 기록**이다 — advisor 원문은 대화 기록에서 암호화돼 있어 그대로 옮길 수 없었다(저장 메모 `advisor_105_pre.md`를 그대로 붙인다 · 공시).
- Codex 스레드: PRE r1(Part A 강화 POST + Part B 스펙 PRE) → **Part A MERGE · Part B FIX** → 스펙 r2 · 코드 반영 → PRE r2(아래에 덧붙인다).

## 입장표(Claude Code · Codex PRE r1)
| 항목 | 요지 | 입장 |
|---|---|---|
| A | 강화 4건 구현 확인 · 회귀 없음 · 한계: restore.ok가 현재 계획·바이트에 묶이지 않음 · 허용 목록 캐시 | 동의 — 기록(다음 실행 전 강화 후보) |
| B1 | 재현 건전 · "스크립트가 만든 숫자 칸"으로 문구 | 동의 — r2 |
| B2 | 암 대응 타당 · v1 두 실행은 날짜·규칙 같고 명목 다름 | 동의 — r2 |
| B3 | D7 산수 = 수수료 · 슬리피지 0은 스펙의 규약 | 동의 — 규약으로 공시 + 슬리피지 민감도 열 |
| B4 | DTB3 빈 칸 · 가드가 2020-12를 버림 · 첫 G1 진입 01-01 · 고정 비율 공시 | 동의 — 첫 관측 규칙(D4 때문의 유일한 예외 · 공시 · 민감도) · 그 밖 실패 |
| B5 | 블록 경계 · 받아들인 추출 · 0건 · 난수 초기화 | 동의 — r2 |
| B6 | ρ̂ 정의 · ddof | 동의 — r2 |
| B7 | 암이 갈릴 때 가족 처분 | 동의 — r2(둘 다 실패 → 닫음 · 하나라도 통과 → 사용자 검토 · 자동 승격 없음) |

## advisor PRE — 저장 메모(요약)
(advisor PRE for post-#105 phase — saved verbatim from transcript; see conversation)
0. Read Trade.net_pnl fully; pin gross formula. Pin A/B/C semantics from D7/#100: plain reading = scenario X replaces fees+slippage all-in, cost = X bps × notional; disclose.
1. Hardening TDD, one Codex PRE covering hardening + W3 spec, one POST. If boundary-shard test fails on current loader → correction row before fixing.
2. Reproduction in detached worktree of 5ba96a0 in scratchpad; symlink data read-only; uv sync from frozen lock; run both scripts unmodified; diff JSONs bit-identical else stop. Arms: G1 = v1_restated, hysteresis = v2_primary; report carry_backtest.py original v1 n. Driver wraps mod.run_backtest, calls mod.main(); capture ts. Check window guard scope before placing driver; E2E-side reader uses bounded_* and truncates at load.
3. W3 spec pinned before step 3, START row: whole-trade truncation exit>06-30; DTB3 FRED bounded, holding days/365 × notional at entry-date rate; subwindow by entry date; 60-day blocks by entry date, 1000 draws, seed, 0-trade draw rule; units bps of notional; power label 2.80 and ~4.0; disclosure originals read; basis v3 §3-1a + #105 (v4 pending).
4. W5 r3 drafted in parallel; stop at MERGE or first BLOCK.
5. Commit fetch.log/verify.log; no deletion until user confirms.

## Codex PRE r1 — 원문(verbatim · 최종 메시지)
The reproduction claim checks out. P0 implements the four approved items; P1 still has choices that need fixing before calculation. I changed no files and computed no means or CIs of `net_B − DTB3`.

**Part A — P0 POST review**

- **Runner requires `restore.ok`: implemented.** [run.py:74](/home/cms/project/BTC_Futures_E2E/research/screens/p0/run.py:74) checks before sampling. Missing records and anything other than JSON `true` fail closed. Malformed JSON also stops execution, though through an uncaught exception.
- **Paired-file allow-list: implemented.** [loader.py:45](/home/cms/project/BTC_Futures_E2E/research/screens/p0/loader.py:45) constructs `matched − excluded`; `_read` skips excluded files and raises before reading an unpaired shard. This is deliberately conservative: an unexpected file in a scanned directory stops the read even if its rows would fall outside the requested interval.
- **Missing comparison metadata: implemented at shard level.** [restore.py:112](/home/cms/project/BTC_Futures_E2E/research/screens/p0/restore.py:112) excludes a shard missing Drive MD5 or manifest row count and records the reason. Verification can still succeed if retained coverage remains ≥99%; it does **not** make every metadata omission fatal to the whole restore.
- **Boundary test: appropriate regression coverage.** [test_screen_p0_guard.py:261](/home/cms/project/BTC_Futures_E2E/tests/test_screen_p0_guard.py:261) checks inclusive endpoints, aligned value columns, and both aggtrade timestamps. Your observation is correct: the old loader already filtered these rows. The change adds coverage, not new boundary behavior.

I found no regression in those contracts. Their limit is snapshot integrity: `restore.ok` is not bound to the current plan or current file bytes, and the cached allow-list does not refresh after replanning. They assume the verified restore remains fixed; replacing inputs afterward is not detected by these four checks.

Verification: 45 existing checks passed. All six new guard tests passed using in-memory file fixtures and real Parquet encoding/filtering; ordinary temporary-file tests could not run under the read-only sandbox.

**Part B — P1 PRE review**

1. **Reproduction: sound.** I independently replayed the frozen scripts with output writes redirected to memory. The v2 JSON was byte-identical, and the reconstructed ledger matched SHA256 `c00f7312…`. V1 differences were confined to the hand-added fields and stress annotations, including `ok: true → null`; generated numeric outputs matched. Both v1 gaps equal the first trade’s entry cost to floating-point precision: approximately 0.318153 and 0.355583 USDT. [Spec:9](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:9) is substantiated. More precise wording would be “script-generated numeric fields,” since some annotations themselves contain numbers.

2. **Arm mapping: reasonable and faithful to the corrected-accounting interpretation of #105.** `v1_restated` preserves the G1 entry/exit sequence while applying residual-delta accounting and 2 bps per leg per direction; `v2_primary` adds hysteresis with that same accounting. Their frozen identities are pinned. However, `v1_original` and `v1_restated` have different notionals because accounting affects subsequent capital. Describe them as the same trade dates/rules, not identical original dollar exposure. [Spec:13](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:13)

3. **Cost normalization is faithful; the “all-in” attribution needs correction.** D7’s arithmetic establishes a **pair round trip**, normalized by one leg’s notional: A = 0 + 10, B = 7.5 + 10, C = 15 + 10 bps. But those components are fees. D7 alone does not establish that they also replace slippage. [Spec:22](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:22) pins a zero-additional-slippage convention, but presents it as implied by D7. Identify that convention explicitly and reconcile it with the binding cost decision. The cited 0.016 bps measurement does not itself establish zero slippage for this hedge execution path.

4. **DTB3: reasonable capital basis, but currently incompatible with the specified loader.** `notional × 1.6` matches carrybot’s locked-capital basis, and elapsed days/365 is a clear holding-period proxy. It is **not merely a rate substitution**: carrybot accrues changing DGS2 rates at valid settlements, whereas this spec freezes the entry-date rate over elapsed time. Also, DTB3 is a discount-basis quote, so disclose this as a benchmark proxy rather than an exact realized Treasury return. [FRED DTB3](https://fred.stlouisfed.org/series/DTB3)

   Two concrete fixes are required at [spec:17](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:17): the CSV uses **blank missing values**, not `"."`; and `bounded_csv_file` discards December 2020. The first G1 entry is January 1, whose rate is blank, so its required preceding observation becomes unavailable. Pin a guard-compatible benchmark seed/warm-up rule and a hard failure for unavailable rates—no future filling, zero substitution, or trade dropping. Disclose that same-day observations provide date-level, not intraday availability.

5. **Bootstrap: the statistical construction is mostly pinned.** Entry-date assignment, uniform resampling of all blocks including empty ones, and pooling all sampled trades correctly retain trade weighting. The 34/13 block counts match the windows. Remaining choices at [spec:34](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:34): explicitly state half-open block boundaries, truncated final blocks, **1,000 accepted draws**, and failure when the original arm/window contains zero trades. Crucially, pin RNG initialization and draw reuse across arms, windows, B/A/C, and sensitivity columns. A seed alone does not determine that execution.

6. **Power rules follow #105, but `ρ̂` is underspecified.** Separate effect/power columns, the 0.15 floor, coefficients 2.80/4.00, and disclosure of the differing tails are correct. At [spec:38](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:38), name the autocorrelation input series, estimator, sample scope, and undefined-value handling. Also specify `ddof=1` for the MDE SD. Using current ledger `n` is pinned, but remains an observed-sample projection, not demonstrated power for a future design.

7. **Remaining disposition freedom:** [spec:43](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:43) says failure closes the family, then evaluates arms separately. Pin the family disposition when their flags disagree. Report both; satisfying these conditions permits consideration of a new user-approved preregistration, not automatic promotion or retrospective arm selection. Carry the separate power-label column into the S registry row.

I treated #105’s W3-specific trade unit, B-primary rule, and execution order as overriding the older protocol’s unresolved/30-day wording. Requiring re-gridding or protocol revision before W3 would contradict that decision.

**Part A verdict: MERGE.**  
**Part B verdict: FIX — DTB3 missing values/initial rate, cost attribution, bootstrap RNG/edge rules, autocorrelation/MDE definition, mixed-arm family disposition.**

## Codex PRE r1 — 실행 로그 전체
```
[codex] Starting Codex task thread.
[codex] Thread ready (01a139a1-348b-7590-90d7-7517cd418c84).
[codex] Turn started (01a139a1-3a2f-7eb2-bec6-5f3a7559467d).
[codex] Assistant message captured: I’ll read the binding registry decisions first, then review the P0 diff and P1 spec against t...
[codex] Running command: /bin/bash -lc 'cat /home/cms/.codex/skills/karpathy-guidelines/SKILL.md'
[codex] Command completed: /bin/bash -lc 'cat /home/cms/.codex/skills/karpathy-guidelines/SKILL.md' (exit 0)
[codex] Running command: /bin/bash -lc "pwd; rg --files -g AGENTS.md -g '*spec*' -g '*repro*' -g '*registry*' -g '*pro...
[codex] Command completed: /bin/bash -lc "pwd; rg --files -g AGENTS.md -g '*spec*' -g '*repro*' -g '*registry*' -g '*pro... (exit 0)
[codex] Running command: /bin/bash -lc "rg -n '"'^'"\\| *10[05] *\\||D7|G1|hyst|cost|carrybot' docs/trial_registry.md;...
[codex] Command completed: /bin/bash -lc "rg -n '"'^'"\\| *10[05] *\\||D7|G1|hyst|cost|carrybot' docs/trial_registry.md;... (exit 0)
[codex] Running command: /bin/bash -lc 'git status --short; git diff b9173c0..e8857eb -- research/screens/p0 tests/tes...
[codex] Command completed: /bin/bash -lc 'git status --short; git diff b9173c0..e8857eb -- research/screens/p0 tests/tes... (exit 0)
[codex] Running command: /bin/bash -lc 'cat docs/screen_protocol.md; cat research/screens/window.py; cat tests/test_sc...
[codex] Command completed: /bin/bash -lc 'cat docs/screen_protocol.md; cat research/screens/window.py; cat tests/test_sc... (exit 0)
[codex] Running command: /bin/bash -lc 'for p in /AGENTS.md /home/AGENTS.md /home/cms/AGENTS.md /home/cms/project/AGEN...
[codex] Command completed: /bin/bash -lc 'for p in /AGENTS.md /home/AGENTS.md /home/cms/AGENTS.md /home/cms/project/AGEN... (exit 0)
[codex] Running command: /bin/bash -lc "rg -n '"'^'"\\| 100 |"'^'"\\| 105 ' docs/trial_registry.md; nl -ba research/sc...
[codex] Command completed: /bin/bash -lc "rg -n '"'^'"\\| 100 |"'^'"\\| 105 ' docs/trial_registry.md; nl -ba research/sc... (exit 0)
[codex] Running command: /bin/bash -lc 'nl -ba docs/screen_protocol.md'
[codex] Command completed: /bin/bash -lc 'nl -ba docs/screen_protocol.md' (exit 0)
[codex] Running command: /bin/bash -lc 'nl -ba research/screens/p0/restore.py; nl -ba research/screens/p0/loader.py; n...
[codex] Command completed: /bin/bash -lc 'nl -ba research/screens/p0/restore.py; nl -ba research/screens/p0/loader.py; n... (exit 0)
[codex] Running command: /bin/bash -lc 'git -C /home/cms/project/carrybot status --short; git -C /home/cms/project/car...
[codex] Command completed: /bin/bash -lc 'git -C /home/cms/project/carrybot status --short; git -C /home/cms/project/car... (exit 0)
[codex] Running command: /bin/bash -lc "nl -ba research/screens/window.py | sed -n '1,250p'; nl -ba /home/cms/project/...
[codex] Command failed: /bin/bash -lc "nl -ba research/screens/window.py | sed -n '1,250p'; nl -ba /home/cms/project/... (exit 2)
[codex] Running command: /bin/bash -lc "nl -ba research/screens/p0/restore.py | sed -n '1,190p'; nl -ba research/scree...
[codex] Running command: /bin/bash -lc "rg -n 'D7|17\\.5|0\\.016|slippage|all.in' docs reports research/screens/p1; nl...
[codex] Command completed: /bin/bash -lc "nl -ba research/screens/p0/restore.py | sed -n '1,190p'; nl -ba research/scree... (exit 0)
[codex] Command completed: /bin/bash -lc "rg -n 'D7|17\\.5|0\\.016|slippage|all.in' docs reports research/screens/p1; nl... (exit 0)
[codex] Assistant message captured: The P0 changes preserve the existing row filters; the boundary test adds coverage rather than...
[codex] Running command: /bin/bash -lc "nl -ba /home/cms/project/carrybot/src/carrybot/carry/backtest.py | sed -n '1,3...
[codex] Command completed: /bin/bash -lc "nl -ba /home/cms/project/carrybot/src/carrybot/carry/backtest.py | sed -n '1,3... (exit 0)
[codex] Running command: /bin/bash -lc "rg -n 'D7|17\\.5|0\\.016' docs reports research/screens/p1; nl -ba /home/cms/p...
[codex] Command completed: /bin/bash -lc "rg -n 'D7|17\\.5|0\\.016' docs reports research/screens/p1; nl -ba /home/cms/p... (exit 0)
[codex] Running command: /bin/bash -lc "rg -l 'D7|spot BTC/FDUSD maker both ways' docs reports --glob '*.md'; rg -n '2...
[codex] Command completed: /bin/bash -lc "rg -l 'D7|spot BTC/FDUSD maker both ways' docs reports --glob '*.md'; rg -n '2... (exit 0)
[codex] Running command: /bin/bash -lc 'git -C /tmp/claude-1000/-home-cms-project-BTC-Futures-E2E/e1aa6b96-4da3-4d5e-b...
[codex] Command completed: /bin/bash -lc 'git -C /tmp/claude-1000/-home-cms-project-BTC-Futures-E2E/e1aa6b96-4da3-4d5e-b... (exit 0)
[codex] Running command: /bin/bash -lc "nl -ba /home/cms/project/carrybot/src/carrybot/carry/dataset.py | sed -n '1,26...
[codex] Command completed: /bin/bash -lc "nl -ba /home/cms/project/carrybot/src/carrybot/carry/dataset.py | sed -n '1,26... (exit 0)
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests...
[codex] Command failed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests... (exit 1)
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 /home/cms/project/carrybot/.venv/bin/python - <<'PY'...
[codex] Command failed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 /home/cms/project/carrybot/.venv/bin/python - <<'PY'... (exit 127)
[codex] Running command: /bin/bash -lc "ls -l /home/cms/project/carrybot/.venv/bin/python*; rg -n -A3 'name = \"numpy\...
[codex] Command completed: /bin/bash -lc "ls -l /home/cms/project/carrybot/.venv/bin/python*; rg -n -A3 'name = \"numpy\... (exit 0)
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m...
[codex] Command failed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m... (exit 1)
[codex] Running command: /bin/bash -lc "ls -l /tmp/claude-1000/-home-cms-project-BTC-Futures-E2E/e1aa6b96-4da3-4d5e-b1...
[codex] Command completed: /bin/bash -lc "ls -l /tmp/claude-1000/-home-cms-project-BTC-Futures-E2E/e1aa6b96-4da3-4d5e-b1... (exit 0)
[codex] Searching:
[codex] Assistant message captured: I found a concrete DTB3 conflict: the guard drops all December 2020 observations, but the fir...
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 /tmp/claude-1000/-home-cms-project-BTC-Futures-E2E/e...
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY' import csv, datetime as dt...
[codex] Command completed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY' import csv, datetime as dt... (exit 0)
[codex] Running command: /bin/bash -lc "rg -n 'def .*rho|corrcoef|autocorr|n_eff|sd' backtest/verdict_t4.py backtest/e...
[codex] Command completed: /bin/bash -lc "rg -n 'def .*rho|corrcoef|autocorr|n_eff|sd' backtest/verdict_t4.py backtest/e... (exit 0)
[codex] Command completed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 /tmp/claude-1000/-home-cms-project-BTC-Futures-E2E/e... (exit 0)
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY' import importlib.util, jso...
[codex] Command completed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY' import importlib.util, jso... (exit 0)
[codex] Assistant message captured: The frozen replay checks out: v2 JSON is byte-identical, v1’s generated numeric outputs match...
[codex] Running command: /bin/bash -lc "rg -n '17\\.5|DTB3|0\\.016' research/screens/p1/S-carry-1_spec.md docs/proposa...
[codex] Command completed: /bin/bash -lc "rg -n '17\\.5|DTB3|0\\.016' research/screens/p1/S-carry-1_spec.md docs/proposa... (exit 0)
[codex] Assistant message captured: The reproduction claim checks out. P0 implements the four approved items; P1 still has choice...
[codex] Turn completed.
The reproduction claim checks out. P0 implements the four approved items; P1 still has choices that need fixing before calculation. I changed no files and computed no means or CIs of `net_B − DTB3`.

**Part A — P0 POST review**

- **Runner requires `restore.ok`: implemented.** [run.py:74](/home/cms/project/BTC_Futures_E2E/research/screens/p0/run.py:74) checks before sampling. Missing records and anything other than JSON `true` fail closed. Malformed JSON also stops execution, though through an uncaught exception.
- **Paired-file allow-list: implemented.** [loader.py:45](/home/cms/project/BTC_Futures_E2E/research/screens/p0/loader.py:45) constructs `matched − excluded`; `_read` skips excluded files and raises before reading an unpaired shard. This is deliberately conservative: an unexpected file in a scanned directory stops the read even if its rows would fall outside the requested interval.
- **Missing comparison metadata: implemented at shard level.** [restore.py:112](/home/cms/project/BTC_Futures_E2E/research/screens/p0/restore.py:112) excludes a shard missing Drive MD5 or manifest row count and records the reason. Verification can still succeed if retained coverage remains ≥99%; it does **not** make every metadata omission fatal to the whole restore.
- **Boundary test: appropriate regression coverage.** [test_screen_p0_guard.py:261](/home/cms/project/BTC_Futures_E2E/tests/test_screen_p0_guard.py:261) checks inclusive endpoints, aligned value columns, and both aggtrade timestamps. Your observation is correct: the old loader already filtered these rows. The change adds coverage, not new boundary behavior.

I found no regression in those contracts. Their limit is snapshot integrity: `restore.ok` is not bound to the current plan or current file bytes, and the cached allow-list does not refresh after replanning. They assume the verified restore remains fixed; replacing inputs afterward is not detected by these four checks.

Verification: 45 existing checks passed. All six new guard tests passed using in-memory file fixtures and real Parquet encoding/filtering; ordinary temporary-file tests could not run under the read-only sandbox.

**Part B — P1 PRE review**

1. **Reproduction: sound.** I independently replayed the frozen scripts with output writes redirected to memory. The v2 JSON was byte-identical, and the reconstructed ledger matched SHA256 `c00f7312…`. V1 differences were confined to the hand-added fields and stress annotations, including `ok: true → null`; generated numeric outputs matched. Both v1 gaps equal the first trade’s entry cost to floating-point precision: approximately 0.318153 and 0.355583 USDT. [Spec:9](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:9) is substantiated. More precise wording would be “script-generated numeric fields,” since some annotations themselves contain numbers.

2. **Arm mapping: reasonable and faithful to the corrected-accounting interpretation of #105.** `v1_restated` preserves the G1 entry/exit sequence while applying residual-delta accounting and 2 bps per leg per direction; `v2_primary` adds hysteresis with that same accounting. Their frozen identities are pinned. However, `v1_original` and `v1_restated` have different notionals because accounting affects subsequent capital. Describe them as the same trade dates/rules, not identical original dollar exposure. [Spec:13](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:13)

3. **Cost normalization is faithful; the “all-in” attribution needs correction.** D7’s arithmetic establishes a **pair round trip**, normalized by one leg’s notional: A = 0 + 10, B = 7.5 + 10, C = 15 + 10 bps. But those components are fees. D7 alone does not establish that they also replace slippage. [Spec:22](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:22) pins a zero-additional-slippage convention, but presents it as implied by D7. Identify that convention explicitly and reconcile it with the binding cost decision. The cited 0.016 bps measurement does not itself establish zero slippage for this hedge execution path.

4. **DTB3: reasonable capital basis, but currently incompatible with the specified loader.** `notional × 1.6` matches carrybot’s locked-capital basis, and elapsed days/365 is a clear holding-period proxy. It is **not merely a rate substitution**: carrybot accrues changing DGS2 rates at valid settlements, whereas this spec freezes the entry-date rate over elapsed time. Also, DTB3 is a discount-basis quote, so disclose this as a benchmark proxy rather than an exact realized Treasury return. [FRED DTB3](https://fred.stlouisfed.org/series/DTB3)

   Two concrete fixes are required at [spec:17](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:17): the CSV uses **blank missing values**, not `"."`; and `bounded_csv_file` discards December 2020. The first G1 entry is January 1, whose rate is blank, so its required preceding observation becomes unavailable. Pin a guard-compatible benchmark seed/warm-up rule and a hard failure for unavailable rates—no future filling, zero substitution, or trade dropping. Disclose that same-day observations provide date-level, not intraday availability.

5. **Bootstrap: the statistical construction is mostly pinned.** Entry-date assignment, uniform resampling of all blocks including empty ones, and pooling all sampled trades correctly retain trade weighting. The 34/13 block counts match the windows. Remaining choices at [spec:34](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:34): explicitly state half-open block boundaries, truncated final blocks, **1,000 accepted draws**, and failure when the original arm/window contains zero trades. Crucially, pin RNG initialization and draw reuse across arms, windows, B/A/C, and sensitivity columns. A seed alone does not determine that execution.

6. **Power rules follow #105, but `ρ̂` is underspecified.** Separate effect/power columns, the 0.15 floor, coefficients 2.80/4.00, and disclosure of the differing tails are correct. At [spec:38](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:38), name the autocorrelation input series, estimator, sample scope, and undefined-value handling. Also specify `ddof=1` for the MDE SD. Using current ledger `n` is pinned, but remains an observed-sample projection, not demonstrated power for a future design.

7. **Remaining disposition freedom:** [spec:43](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:43) says failure closes the family, then evaluates arms separately. Pin the family disposition when their flags disagree. Report both; satisfying these conditions permits consideration of a new user-approved preregistration, not automatic promotion or retrospective arm selection. Carry the separate power-label column into the S registry row.

I treated #105’s W3-specific trade unit, B-primary rule, and execution order as overriding the older protocol’s unresolved/30-day wording. Requiring re-gridding or protocol revision before W3 would contradict that decision.

**Part A verdict: MERGE.**  
**Part B verdict: FIX — DTB3 missing values/initial rate, cost attribution, bootstrap RNG/edge rules, autocorrelation/MDE definition, mixed-arm family disposition.**
```

## Codex PRE r2 — 원문(verbatim · 최종 메시지) · VERDICT: FIX(P1 사용자 승인 필요 · P2 둘)
Reviewed HEAD `4fe617c` read-only. No files changed and no real-ledger means or CIs computed.

1. **RESOLVED** — Reproduction wording now correctly distinguishes script-generated numeric fields from annotations.
2. **RESOLVED** — Arm mapping distinguishes shared trade dates/rules from differing dollar notionals.
3. **RESOLVED** — Fees and the explicit zero-additional-slippage convention are separated; the 8 bps slippage sensitivity is implemented.
4. **PARTIAL** — Blank rates, benchmark-proxy disclosures, seed flags, exclusion sensitivity, and unavailable-rate failure are implemented; the future-observation exception needs approval.
5. **PARTIAL** — RNG initialization, half-open blocks, truncated coverage, and 1,000 accepted draws match r2; empty-window output omits the specified `null` statistics/CIs.
6. **PARTIAL** — Series, ordering, Pearson estimator, floor, coefficients, and `ddof=1` are pinned; small-sample and undefined-rho reporting differ from r2.
7. **RESOLVED** — Mixed-arm disposition is pinned, effects and power remain separate, and family disposition can appropriately remain in the report.

The ordinary computation path matches r2: fresh RNG per arm/window/column/method, accepted-draw resampling, trade pooling, and all three promotion flags. Family disposition is deliberately absent from the runner.

New findings:

- **P0:** None.
- **P1 — First-observation exception requires explicit user approval for the primary statistic.** January 4 is a future observation for January 1/2 entries. D4 restricts reads; it does not authorize that substitution. The binding benchmark remains “시점 기준” (point-in-time) in [protocol §6](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:119), and #105 does not waive it. Disclosure and exclusion sensitivity make the exception reviewable, but do not make the primary benchmark point-in-time. Approve the exact [r2 exception](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:18), or revise it before calculation.
- **P2 — Power edge cases violate r2.** [run.py:39](/home/cms/project/BTC_Futures_E2E/research/screens/p1/run.py:39) suppresses MDE/power for `n=2`, although r2 prescribes rho fallback zero and the sample SD is defined. Constant synthetic data reports `rho_lag1: NaN` rather than zero; serialization then emits a nonstandard JSON value. Compute the defined two-trade MDE and normalize undefined rho to zero.
- **P2 — Empty-window schema differs from r2.** [run.py:24](/home/cms/project/BTC_Futures_E2E/research/screens/p1/run.py:24) returns only `{"n": 0}` instead of explicit `null` statistics/CIs. Its decision conditions correctly remain false.

Verification: 36 checks passed directly, three loader tests passed with in-memory CSV fixtures, and additional synthetic checks confirmed fresh RNGs, accepted-draw counts, seeded exclusion, and promotion flags.

VERDICT: FIX

입장: P2 둘 동의 — 고침(정의 안 되는 ρ̂ = 0 · n = 2도 MDE · 빈 창 null). P1 동의 — 첫 관측 예외는 사용자 결정으로 올린다(계산 전 · 고정 전).

## Codex PRE r3 — 원문(verbatim · 최종 메시지) · VERDICT: FIX(P2 하나)
Reviewed `d610e65` read-only. HEAD advanced to `adeeb30` during review; all scoped files remain identical. I made no edits and computed no real-ledger excess-return means or CIs.

| Prior item | Status | Assessment |
|---|---|---|
| R2 P1: first-observation exception | **RESOLVED** | Binding #108 authorizes the DTB3 lookback. Lookup now uses the last observation on/before entry; flags and exclusion sensitivity remain. |
| R2 P2: rho / n=2 | **PARTIAL** | Two-trade MDE is fixed. Constant-series rho still has an edge-case defect below. |
| R2 P2: empty-window nulls | **RESOLVED** | Explicit null statistics/CIs; decision conditions remain false. |
| Earlier item 4 | **RESOLVED** | Missing-rate handling, disclosures, point-in-time lookup, flags, and sensitivity match r3. |
| Earlier item 5 | **RESOLVED** | RNG, blocks, accepted draws, and empty-window output match r3. |
| Earlier item 6 | **PARTIAL** | Ordering, estimator, coefficients, floor, and `ddof=1` match; constant-series detection remains incomplete. |

The guard exception is keyed to the **DTB3 basename pattern**, with fixed bounds of `2020-12-22` through `2026-06-30` and no window-widening parameter. Ordinary market/funding/premium filenames are rejected before opening. Reserved filenames are refused, and reserved rows never reach the parser. Existing CSV/ZIP paths retain `require_window`; API validation is unchanged. `_filtered` is excluded from both public allowlists, and direct-import/module-access probes are rejected by the static rule.

This is filename enforcement: it cannot authenticate the contents of a renamed or symlinked file. The current loader uses the specified DTB3 file, with no market-data use of the exception.

The code otherwise implements r3, but **not exactly**:

- **P0:** None.
- **P1:** None.
- **P2 — Constant decimal series can report rho ≈ 1 instead of zero.** In [reprice.py:81](/home/cms/project/BTC_Futures_E2E/research/screens/p1/reprice.py:81), checking `np.std(...) == 0.0` misses some exactly constant inputs because of floating-point rounding. Synthetic `np.full(4, 0.1)` produces `rho_lag1 = 1.0` and `n_eff = 0.8`; r3 requires `rho_lag1 = 0.0` and `n_eff = 2.5`. Detect constant pair slices directly, and add this decimal-valued regression case.

Verification: **49 existing targeted checks passed**, including 11 file-fixture tests using in-memory files. Additional synthetic checks confirmed guard boundaries, static rejection of `_filtered`, two-trade MDE, flags, empty-arm decisions, and strict JSON serialization.

VERDICT: FIX

입장: 동의 — 상수 판정을 값 비교로 · 회귀 시험 추가.
