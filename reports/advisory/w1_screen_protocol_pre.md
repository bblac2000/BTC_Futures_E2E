# W1 — 스크린 프로토콜과 원장 · PRE(착수 전 검토)

- 날짜: 2026-10-14 · 항목: W1(CRITICAL) · 검토자: advisor(내장 도구) + Codex(`codex-companion task --effort high` · 읽기 전용)
- 원문은 그대로 붙였다(의역 없음). Codex 스레드 `01a1382e-4162-7e81-8bfc-e4f11f34618a`.

## 1. 계획 r1(검토 대상)
1. docs/screen_protocol.md — 목적 · 두 원장 규칙(D2) · 고정 통과 규칙(D3) · 자료 창과 예약(D4) · S 행 필수 열 · "스크린 결과는 매매 근거가 아니다".
2. 통과 규칙의 자유도 막기: 스펙이 실행 전에 통계·비용·플라시보·꼬리를 고정하고 커밋 · 해시를 S 행에.
3. D4 집행을 코드로: research/screens/window.py · require_window(start_ms, end_ms, *, trial_token=None) · 시험이 2026-07-01 거부를 단언.
4. P0 예외를 좁게: 수집기 전용 로더.
5. docs/screen_registry.md(빈 원장) · 승격 열은 Codex POST MERGE 전까지 "n/a (pending Codex)".
6. 레지스트리 행: 절차 변경 D2~D4와 사용자 결정 문구.
7. 정식 판정기(θ · α · MDE 규칙)는 건드리지 않는다.
검토자에게 묻는 것: 통과 규칙의 사후 자유도 · D4의 코드 집행 · k의 가시성 · 숨은 판정기 문턱 변경.

## 2. advisor PRE — 원문(verbatim)
You're at the W1 PRE (advisor half); #95 is pushed, directories exist, plan r1 is in chat, nothing written yet. **Verdict: PROCEED after four fixes to the plan — one of them is a contradiction in the brief that will become a post-hoc degree of freedom if the protocol freezes it as written.** Save this text verbatim into `reports/advisory/w1_screen_protocol_pre.md` (advisor section) before writing anything else.

**1. The default pass rule fails P1 by construction — resolve the placebo semantics now (answers reviewer Q1)**

D3's second clause is "original statistic outside the placebo p95". W3's primary placebo is random entry dates, and the brief itself says "the carry should not depend on entry timing". If carry is real, the original (1st-of-block 00:00 entries) sits *inside* that distribution — so the literal rule yields FAIL regardless of carry size, or PASS only by a lucky outlier. The protocol must state: **the pass-rule placebo is a null of the hypothesis (no effect), not a robustness check; each spec names it before execution.** Then list per family what that is likely to be and what it isn't:
- carry: the entry-timing placebo is reported (percentile) but is not the pass null; the pass null must be a no-carry construction (spec decides — candidates are the zero-funding ledger as baseline with the bootstrap CI on the difference, or sign-shuffled funding).
- execution (P0): no pass rule — pre-fixed kill rule < 2 bps/side replaces it; say so.
- cross-sectional IC (P2): the cost clause ("≥ 1.5 × round-trip cost") has no defined object when the deliverable is "IC and sd only, no capital assumptions". The protocol must say how the two clauses map for a data-only screen or declare that the spec must define it before running.

Do not pick P1's null in W1 — write the requirement, and put "P1 pass null = ?" and "P2 cost-clause mapping = ?" on the user-decision list for the W3/W4 spec PREs. Also fix the tail per family (one-sided upper for carry; two-sided for IC) and the draw count (1,000) in the protocol.

**2. D4 in code: no token path this round (answers reviewer Q2)**

A `trial_token=None` parameter anyone can pass is prose with a function signature. No formal trial exists in this round, so `require_window` should refuse unconditionally; a bypass is a future code change plus a registry row, and the protocol says so. Two guards, not one: (a) requested range ≤ 2026-06-30 23:59:59.999Z, and (b) **row-level** — after load, assert `max(open_ms) ≤ SCREEN_END` (the `assert t <= PRE_IS_END` discipline from `calibrate_ts.py`), because `BTCUSDT_1m_2026.csv` and any spot download will contain July+ rows. Test asserts `ReserveError` for both a `(2026-06-01, 2026-07-01)` request and a loaded row past the end. The P0 collector loader lives only in `research/screens/p0/`, hard-codes 2026-09-17 → 2026-10-11 06:28Z, reads collector files only; one static test that `p1/` and `p2/` import nothing from `p0/` closes the leak. ~20 lines of code plus two tests — don't build more.

**3. k must be countable (answers reviewer Q3)**

Define "family" in the protocol: execution / carry / cross-sectional carry / directional (P2 is its own family — it has its own benchmark question). k = every S row carrying that family label, FAIL and pilot included. Add to the required columns: spec SHA256, results JSON SHA256, code commit, data range actually read (first/last timestamp) — without the last one the D4 claim isn't auditable from the row. Fix the "parameter change vs bug fix" line: a change to measurement semantics after results exist = new S id (the user's standing rule, item 3).

**4. One disguised-judge issue to disclose, not fix (answers reviewer Q4)**

The brief writes the judge MDE as "3.34 × sd / √(n/1.6)". 3.34 is the N = 8 coefficient (α = 0.05/8). Under N = 64 the family α is 0.05/64 → k ≈ 4.0, MDE ≈ 20 % larger. The protocol must write the coefficient's provenance (N = 8), state screens report MDE as a labeled report-only number, and flag that the coefficient is fixed by the user with N at the first formal pre-registration (after `n_counter_audit.md`). Don't choose; surface it as a user decision in the briefing.

**Also missing from plan r1**

- The user's W1 order includes a Drive upload for createdTime after the protocol commit; the Drive connector is available — upload `screen_protocol.md`, record file id + createdTime + sha256 in registry row #96 and the ledger header. If the connector fails, record sha256 + commit + push time and disclose.
- Benchmark (D6) is a required reported column, not a pass condition — write that sentence; otherwise it's the next narrative softening after results.
- Record format: `reports/advisory/w1_screen_protocol_pre.md` = this text verbatim + Codex r1 raw output + your per-point positions; one short ops_log entry pointing to the file (CLAUDE.md's verbatim-in-ops_log rule is met by the file; say so once).

**Codex PRE (now, before writing):** `codex-companion.mjs task --effort high` without `--write`, prompt = plan r1 verbatim + the four reviewer questions + items 1–4 above as "proposed resolutions", asking for a P0/P1 list and MERGE / FIX-PLAN-FIRST. Save raw. Resolve every P0 before writing the protocol.

**Order:** PRE file (advisor + Codex) → commit it → protocol + `screen_registry.md` + `window.py` + tests → full suite → commit, sha256 → Drive upload → row #96 (D2–D4, user text, createdTime) → Codex POST on the committed files (`review --scope branch` or `task` pointing at the paths) → MERGE → `_post.md` → 8-section briefing. No screen code and no data download until MERGE.

## 3. Codex PRE r1 — 프롬프트(verbatim)
```
READ-ONLY PRE-REVIEW (do not edit any file). Repository: /home/cms/project/BTC_Futures_E2E. Context: registry row #95 in docs/trial_registry.md reopened this repo as a research-only repository. The user is introducing a Stage-1 "screen" funnel before formal pre-registration. Read docs/trial_registry.md rows #84-#95 (tail), docs/learnings.md (trial #4 section), backtest/verdict_t4.py (mde, classify), backtest/prepare_t3.py (OOSGuard pattern) for context.

USER-FIXED DECISIONS (not open for re-decision):
D2 Two ledgers. The trial counter is incremented only by formal IS verdicts. Stage-1 screens go to a new append-only docs/screen_registry.md (S-1, S-2, ...) and never touch N. When a screen family is promoted to a formal trial, the pre-registration must disclose k = number of screens run in that family and use k as the DSR deflation input. A screen re-run with any parameter change is a new S row. P0 (maker-entry execution audit) is a measurement, not an alpha hypothesis: no ledger increment, but its kill threshold is fixed before it runs.
D3 Screen pass rules are frozen BEFORE the first screen executes, in docs/screen_protocol.md, committed, hash recorded in the first S row. Default: PASS = zero-cost mean >= 1.5 x modelled round-trip cost AND original statistic outside the placebo p95; otherwise FAIL. No threshold edits after results.
D4 Screens use 2021-01-01 -> 2026-06-30 only. 2026-07-01 -> present is RESERVED and must not be read by any screen. Enforce in the loader. Exception fixed by the user: P0 is an execution measurement and runs as a single-regime pilot on collector data 2026-09-17 -> 2026-10-11.
D6 Benchmarks are family-specific (carry -> 3M T-bill DTB3; execution -> immediate taker; directional -> vol-targeted long BTC).
Screens planned: P0 maker-entry execution audit (kill: net improvement < 2 bps per side -> stay taker); P1 BTC perp-spot delta-neutral carry, 30-day non-overlapping episodes, cost A = 10 bps, placebo = 1,000 random entry dates plus a zero-funding ledger control; P2 cross-sectional funding-carry rank IC over 14 perps, weekly, "IC and sd only, no portfolio backtest".

PLAN r1 FOR W1 (what I intend to write):
1. docs/screen_protocol.md: purpose; two-ledger rule; frozen pass rule; data window and reserve; required S-row columns (id, date, family, one-line hypothesis, statistic, placebo design, cost model, benchmark, pass rule hash, result, promoted? y/n, nearest rejected trial and what differs); explicit statement that a screen result is not evidence for trading.
2. Close the pass rule's degrees of freedom: each screen spec must fix, before execution and in a committed file whose SHA256 goes into the S row, (a) the statistic and its unit, (b) the cost number, (c) the placebo that serves as the pass-rule null, (d) which tail and the draw count (1,000).
3. D4 in code: research/screens/window.py with SCREEN_START/SCREEN_END and require_window(start_ms, end_ms) raising ReserveError; every screen loader calls it; tests assert refusal for 2026-07-01+.
4. P0 exception kept narrow: a collector-only loader under research/screens/p0/ with the pilot range hard-coded.
5. docs/screen_registry.md (empty ledger, column definitions); "promoted?" reads "n/a (pending Codex)" until the Codex POST review of the protocol is MERGE.
6. Registry row #96 recording the procedure change with the user's decision text.
7. The formal judge (theta = 20 bps, alpha, MDE rule) is not touched.

PROPOSED RESOLUTIONS FROM THE FIRST REVIEWER (advisor) - please agree/disagree per item:
A1. The literal default rule fails P1 by construction: the brief's primary placebo for carry is random entry dates and "carry should not depend on entry timing", so a real carry sits INSIDE that placebo distribution. Proposed: protocol states the pass-rule placebo must be a null of the hypothesis (no effect), not a robustness check; the entry-timing placebo is reported only; the P1 pass null (e.g. zero-funding ledger baseline with a bootstrap CI on the difference, or sign-shuffled funding) is NOT chosen in W1 - it becomes a user decision at the P1 spec. For P2 (IC only, no capital assumptions) the cost clause ">= 1.5 x round-trip cost" has no defined object; the protocol must require the spec to define the mapping before running or the user decides. P0 has no pass rule; its pre-fixed kill rule replaces it. Tails fixed per family (one-sided upper for carry; two-sided for IC).
A2. No token/bypass parameter in require_window this round (no formal trial exists); two guards: requested range and a row-level assertion after load (files such as BTCUSDT_1m_2026.csv contain July+ rows); a static test that p1/ and p2/ import nothing from p0/.
A3. Define "family" (execution / carry / cross-sectional carry / directional); k = every S row with that family label including FAIL and pilot rows; add columns spec SHA256, results JSON SHA256, code commit, data range actually read. A change to measurement semantics after results exist = new S id.
A4. The brief writes the judge MDE as 3.34 x sd / sqrt(n/1.6). 3.34 is this repo's N = 8 coefficient (alpha = 0.05/8). The user states a cross-repository counter N = 64 (to be audited in docs/n_counter_audit.md). Proposed: protocol records the coefficient's provenance, screens report MDE as a labelled report-only number, and the coefficient is fixed by the user together with N at the first formal pre-registration. Benchmark (D6) is a reported column, not a pass condition.

QUESTIONS YOU MUST ANSWER (the user's list):
Q1. Does the pass rule admit a post-hoc degree of freedom (after plan r1 + A1)? Name each remaining one.
Q2. Is the D4 reserve enforced in code, not prose (after A2)? What can still leak 2026-07-01+ data into a screen?
Q3. Does the two-ledger rule make the garden of forking paths visible at promotion (k disclosed and used)? What would let k be under-counted?
Q4. Is anything in the protocol a disguised threshold change to the formal judge (theta = 20, alpha, MDE rule)?
Also: does the P0 exception (reading 2026-09-17 -> 2026-10-11, inside the reserved span) contaminate that span as future OOS for a promoted family, and how should the protocol word it?

OUTPUT FORMAT: a numbered list of findings, each tagged P0 (must fix before writing the protocol), P1 (carry into the protocol with an explicit accepted/rejected line) or P2 (note). Then a per-item agree/disagree on A1-A4. End with exactly one line: VERDICT: MERGE or VERDICT: FIX-PLAN-FIRST.
```

## 4. Codex PRE r1 — 응답 원문(verbatim)
1. **[P0] Q4: “unchanged judge, theta = 20” conflicts with the repository.** [verdict_t4.py](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t4.py:28) sets **θ = 10 bps**. `classify()` uses **MDE > 2θ = 20**, and **MDE < 0.5θ = 5 with net CI upper < θ = 10**. The [signed pre-registration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_04_preregistration_r3.md:125) agrees; learnings L14 uses conflicting notation. Before writing, distinguish the **20 bps MDE cutoff** from θ. Do not silently change the judge or describe θ = 20 as existing behavior: that would move its classification boundaries to 40/10/20.

2. **[P0] Q1: A1 identifies unresolved decision rules; it does not yet close them.** W1 can defer their values, but must explicitly block execution while they remain unresolved:
   - **P1:** designate exactly one hypothesis-null test. Random entry timing remains a reported robustness check. A bootstrap CI criterion is not automatically equivalent to “original statistic outside placebo p95”; any replacement requires an explicit user decision before execution.
   - **P2:** IC is dimensionless, so the cost condition has no defined comparison. Require a user-approved mapping or explicit exception before running; an arbitrary mapping must not introduce undeclared portfolio assumptions.
   - **P0:** record that the fixed kill rule replaces the screen PASS rule. Freeze the definition of “net improvement per side,” including nonfills, fallback execution, fees, adverse selection, and averaging denominator. Retain the exact **< 2 bps** boundary.
   
   “Pending specification” must mean **cannot execute**, rather than permission to choose after exploratory results.

3. **[P0] Q1: The remaining degrees of freedom extend beyond statistic/unit, cost, null, tail, and draw count.** Require each committed spec to fix:
   - Sample construction: universe, eligibility, exclusions, missing data, episode anchor, overlap treatment, weekly timing, and complete outcome horizon.
   - Estimator: weighting, denominator, normalization, funding/basis accounting; for P2, rank convention, ties, forecast horizon, direction, and aggregation across weeks.
   - Null generation: resampling unit, dependence/block treatment, replacement, risk matching, seed, failed-draw handling, and prohibition on selecting among seeds.
   - Decision calculation: quantile interpolation, equality boundaries, undefined statistics, and any multiple-statistic aggregation.
   
   For two-sided IC, define either the central 95% interval or a p95 test of an explicitly transformed statistic such as absolute IC. “Two-sided p95” is ambiguous. Negative IC must not permit an unregistered direction reversal after results. L16 demonstrates why placebo risk semantics also belong in the frozen spec.

4. **[P0] Q2: A2 provides code checks, but post-load assertions alone do not enforce “must not be read.”** The screen guard is currently unwritten, so this is conditional design approval. Require validation **before I/O**, bounded ingestion before value interpretation, and assertions before data reach screen calculations. The [existing bounded reader](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t3.py:81) supplies a useful timestamp-first pattern.
   
   Remaining leakage paths include bulk-loading annual files before filtering; API pagination returning excess rows; direct legacy loaders; indirect or dynamic access to P0; caches or aggregates containing reserve observations; full-series normalization/interpolation; current-universe selection informed by reserve data; and June entries whose 30-day or weekly outcomes require July observations. Validate **all dependencies**, including benchmarks and controls—not just entry timestamps. Fix UTC millisecond boundaries, reject malformed timestamps, and test contaminated inputs and actual loader paths. The static import test catches direct imports only.

5. **[P0] Q3: Two ledgers expose the search only if registration precedes execution and family membership cannot shrink afterward.** Assign the immutable family and S identifier before reading screen data; append completion records without overwriting start records. Count distinct executed screen identifiers, including FAIL, inconclusive, aborted-after-observation, and alpha pilot variants. Parameter or measurement-semantic changes require a new S identifier.
   
   Under-counting remains possible through unlogged exploratory runs, omitted failures, family relabeling/splitting, selection among multiple variants inside one S row, seed selection, and cross-repository screens omitted from the disclosed lineage. Promotion must enumerate the contributing S identifiers and their immutable family relationships. **P0 remains a separately recorded measurement with no ledger increment**, as D2 requires; “including pilot rows” must not accidentally put P0 into S or N.

6. **[P0] Q3/Q4: Disclosing k is insufficient unless promotion defines its actual DSR use.** Freeze how k enters deflation alongside the audited formal count, what statistic inputs are required, and how duplicate counting is avoided. IC-only screens do not provide comparable portfolio Sharpe estimates automatically. Substituting k directly for the existing formal `N_TRIALS` would change the judge’s deflation; for k = 1, the [current implementation](/home/cms/project/BTC_Futures_E2E/backtest/stats.py:109) rejects the input.
   
   W1 need not invent that formula. It should state that **promotion is blocked until the formal pre-registration specifies and verifies k’s use**, while keeping screens out of the formal counter.

7. **[P1] P0 exposes part of the reserve; it does not automatically contaminate every reserved date. Accepted:** document exposure by interval and dependency. Suggested wording:
   
   > “2026-07-01 onward is reserved against alpha-screen access, with one execution-measurement exception: collector data from 2026-09-17 through 2026-10-11 for P0. That pilot interval is exposed execution-development data. It cannot serve as untouched OOS for P0 or for a promoted family whose design, selection, or execution model depends on P0. Promotion must disclose the exposure and pre-register a disjoint evaluation interval with any required embargo. Other reserved dates remain eligible only after a dependency audit.”
   
   Screened dates likewise become development data for promotion. A passing loader guard cannot establish independence from information already inspected by researchers.

8. **[P1] A4’s provenance distinction is necessary. Accepted:** label 3.340 as the historical **N = 8, α = 0.05/8** coefficient. The implemented effective sample size is `n / (1 + 4 × max(rho, 0.15))`; **n/1.6 applies only when the floor binds**. Screen MDE reports must name their units, assumptions, and power target; IC MDE cannot be compared with a bps threshold. The future coefficient should be derived from the audited N and approved alpha rule, rather than chosen independently. Preserve registry #88’s approved formal pre-anchor gate; making screen MDE report-only does not repeal it.

9. **[P1] D6 and the review gate need precise status semantics. Accepted:** family benchmarks are reported comparisons, with methodology frozen before execution. **Rejected:** treating POST-review MERGE as promotion. Use separate protocol-review status and family-promotion status; promotion remains pending until a formal pre-registration exists. Record protocol/spec hashes with evidence of commitment before execution, results hashes, code provenance, and pinned input manifests. Actual minimum/maximum timestamps alone do not prove that derived inputs excluded reserve data.

- **A1 — Agree with qualifications.** Random timing is unsuitable as the primary no-carry null, but does not guarantee failure mathematically. Defer P1/P2 decisions behind an explicit execution block. Accept P0’s replacement kill rule and precisely defined family tails.
- **A2 — Agree with additions.** No bypass parameter; retain both checks and import separation. Add bounded ingestion and dependency validation from finding 4.
- **A3 — Partly agree.** Accept immutable families, complete alpha-screen counting, and provenance columns. Reject including P0 as a ledger pilot; prevent relabeling and omitted exploratory variants.
- **A4 — Partly agree.** Accept coefficient provenance, report-only screen MDE, and report-only benchmarks. Reject freely choosing the coefficient or describing the existing θ as 20. Preserve the implemented dependence formula and approved formal gate.

VERDICT: FIX-PLAN-FIRST


## 5. 입장표(Claude Code)
| # | 출처 | 등급 | 입장 |
|---|---|---|---|
| advisor 1 | 통과 규칙의 플라시보는 가설의 귀무여야 한다 · P1 귀무/P2 비용 대응은 사용자 결정 | — | 동의 — R2 |
| advisor 2 | 우회 인자 없음 · 요청·행 두 겹 | — | 동의 — R4 |
| advisor 3 | 가족 정의 · k 집계 · 해시 열 | — | 동의 — R5(단 P0를 k에 넣는 것은 Codex 5에 따라 철회) |
| advisor 4 | 3.34는 N = 8 계수 | — | 동의 — R8 |
| Codex 1 | 판정기 θ는 10 bps(20은 MDE 문턱 2θ) | P0 | **동의 · 저장소에서 확인** — R1 · Claude Code의 2026-10-11 기록 오류 정정 행 |
| Codex 2 | 미결 규칙은 실행을 막아야 한다 | P0 | 동의 — R2 |
| Codex 3 | 남은 자유도(표본·추정량·귀무 생성·결정 계산) | P0 | 동의 — R3 |
| Codex 4 | I/O 전 검증 · 경계 있는 읽기 · 의존 자료 전부 | P0 | 동의 — R4 |
| Codex 5 | 실행 전 등록 · 가족 불변 · P0는 S·N에 넣지 않는다 | P0 | 동의 — R5(P0 표기는 사용자 결정 목록에) |
| Codex 6 | k의 DSR 사용은 정식 사전등록에서 · 그때까지 승격 차단 | P0 | 동의 — R6 |
| Codex 7 | P0가 예약 구간 일부를 노출 | P1 | accepted — R7 |
| Codex 8 | 계수 출처 · n_eff 식 · #88 유지 | P1 | accepted — R8 |
| Codex 9 | 벤치마크는 보고 · 검토 상태와 승격 상태 분리 | P1 | accepted — R9(POST MERGE를 승격으로 취급하는 것은 rejected because 승격은 정식 사전등록이 있어야 한다) |

## 6. 계획 r2(P0 해소)
## W1 plan r2 (after advisor PRE and Codex PRE r1 — every Codex P0 answered)

R1 (Codex 1 · P0 — judge threshold). Verified against the repository: `backtest/verdict_t4.py:28` THETA = 10.0 and r3 §7-2 "θ = 10 bps: MDE > 2θ = 20 → 검정력 부족; MDE < 0.5θ = 5 ∧ net CI upper < θ = 10 → 효과 부재". The user's brief says "against θ = 20 bps"; Claude Code's own records of 2026-10-11 (learnings L14, registry #85, the trial #5 candidate document) also wrote "2θ = 40 / θ = 20" — that was Claude Code's error. Resolution: (a) the protocol quotes the judge exactly as implemented (θ = 10; cutoffs 20 / 5 / 10) and states it changes none of them; (b) the brief's "20 bps" is recorded as "the judge's 20 bps MDE cutoff (= 2θ)", and the reading is put on the user-decision list — the protocol does not decide it; (c) a registry correction row for the 2026-10-11 mislabel (required sample sizes there were understated 4×; candidate C1 fails the #88 gate under the correct cutoff).
R2 (Codex 2 · P0 — unresolved rules block execution). Protocol clause "EXECUTION BLOCK": a screen may not read data while its spec contains any item marked UNRESOLVED. Listed now as UNRESOLVED and owned by the user: P1 pass-rule null (exactly one hypothesis-null test; the random-entry-date placebo is a reported robustness check; a bootstrap-CI criterion is not equivalent to "outside placebo p95" and needs an explicit user decision); P2 mapping of the cost clause (IC is dimensionless — a user-approved mapping or an explicit exception, no undeclared portfolio assumptions). P0: the pre-fixed kill rule replaces the PASS rule; its spec must freeze "net improvement per side" (paired per decision timestamp; non-fills resolved by the taker fallback and included; maker/taker fees included; adverse selection included via the realised fill/fallback prices; denominator = all sampled decisions, not fills) and keeps the exact boundary "< 2 bps per side at the best T → stay taker".
R3 (Codex 3 · P0 — remaining degrees of freedom). The protocol's spec checklist requires, before execution: sample construction (universe, eligibility, exclusions, missing data, episode anchor, overlap, weekly timing, complete outcome horizon); estimator (weighting, denominator, normalisation, funding/basis accounting; for IC: rank convention, ties, horizon, direction, aggregation); null generation (resampling unit, block/dependence treatment, replacement, risk matching, one seed fixed in the spec, failed-draw handling, no seed selection); decision calculation (quantile interpolation, equality at the boundary, undefined statistics → FAIL, no aggregation of several statistics unless pre-fixed). Tails: carry = one-sided upper (statistic > placebo p95, strict); IC = the pre-registered direction only, tested one-sided on the signed IC against the p95 of the null in that direction — a negative IC cannot be reversed after results; a two-sided variant would be a separate S id.
R4 (Codex 4 · P0 — D4 in code). `research/screens/window.py`: UTC-millisecond constants; `require_window(start_ms, end_ms)` validates BEFORE any I/O and has no bypass parameter; `bounded_rows(iterable_of_(ts_ms,row))` parses the timestamp first, rejects malformed timestamps, and never yields a row past SCREEN_END (rows beyond the end are dropped unread and counted); `assert_within(ts_values)` before data reach a calculation. Protocol rules: outcome horizons must end ≤ SCREEN_END (a June entry whose 30-day or weekly outcome needs July data is excluded); every dependency (benchmark series, controls, universes) passes the same guard; no cache or aggregate built from reserve observations; universe selection may not use reserve data; no full-series normalisation across the boundary; legacy loaders (`backtest.*`, `strategies.*`) may not be imported by screens except through wrappers that call the guard. Tests: refusal of a (2026-06-01, 2026-07-01) request; a contaminated input (rows past the end) yields none of them; malformed timestamp rejected; a static AST test that `research/screens/p1` and `p2` do not import `p0` and that no screen module opens a file without importing `window`.
R5 (Codex 5 · P0 — forking paths). Two-phase rows: a START row (S id, date, immutable family, hypothesis, spec SHA256, protocol SHA256, code commit) is appended and committed BEFORE the screen reads data; a RESULT row (same S id) is appended after. Nothing is overwritten. k for a family = number of distinct S ids with a START row in that family, including FAIL, inconclusive and aborted-after-observation. Family labels are fixed in the protocol (execution / carry / cross-sectional carry / directional) and cannot be changed or split after the START row. One S id = one variant, one seed. Promotion must enumerate the contributing S ids. P0: the user's brief asks for an S row for P0 and also says "no ledger increment" (D2) — resolution proposed: P0 is recorded in `docs/screen_registry.md` in a separate section "측정(Measurements)" with ids M-1, …; M rows are never counted in any k and never touch N. Whether the user wants it labelled S instead is put on the user-decision list (it does not change any count either way if the row is marked not-counted).
R6 (Codex 6 · P0 — k and DSR). The protocol states: promotion is BLOCKED until the formal pre-registration specifies how k enters the deflation next to the audited formal count, verifies it against `backtest/stats.expected_max_sr` (which rejects n_trials < 2), and avoids double counting; W1 does not invent that formula; screens never enter N.
R7 (Codex 7 · P1 — accepted). The reserve wording is adopted verbatim in substance: 2026-07-01+ reserved against alpha-screen access, one execution-measurement exception (collector data 2026-09-17 → 2026-10-11 for P0); that interval is exposed execution-development data and cannot serve as untouched OOS for P0 or for a promoted family whose design depends on P0; promotion must disclose the exposure and pre-register a disjoint evaluation interval; screened dates are development data for any promotion.
R8 (Codex 8 · P1 — accepted). 3.340 is labelled "historical coefficient, N = 8, α = 0.05/8, power 0.80"; effective n = n / (1 + 4·max(ρ̂, 0.15)) and "n/1.6" only when the floor binds; screen MDEs are report-only with units and assumptions named; IC MDE is never compared with a bps threshold; the future coefficient follows from the audited N and the approved α rule; registry #88's pre-anchor power gate for formal trials is untouched.
R9 (Codex 9 · P1 — accepted). Benchmarks (D6) are reported comparisons with methodology frozen in the spec, not pass conditions. Two separate status columns: `protocol review` (n/a (pending Codex) until the Codex POST of the protocol is MERGE — the user's D5 addition) and `promoted?` (stays "no" until a formal pre-registration exists; a MERGE is not a promotion). Rows carry protocol/spec hashes, results hash, code commit, pinned input manifest hash, and the data range actually read.
Advisor items not covered above: Drive upload of the protocol for createdTime after the commit (file id + createdTime + sha256 into the registry row); draw count 1,000 fixed in the protocol.
Files to write: docs/screen_protocol.md · docs/screen_registry.md · research/screens/__init__.py · research/screens/window.py · tests/test_screen_window.py · registry rows (correction, then procedure change).

