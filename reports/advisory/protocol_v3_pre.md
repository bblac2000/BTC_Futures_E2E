# 스크린 프로토콜 v3 · PRE(착수 전 검토)

- 날짜: 2026-10-14 · 항목: 프로토콜 변경(CRITICAL) · 검토자: advisor + Codex(`codex-companion task --effort high` · 읽기 전용)
- 결과: advisor PROCEED(수정 5) → 계획 r2 → Codex PRE r1 **FIX-PLAN-FIRST(P0 없음 · P1 3 · P2 2)** → P1을 문안에 반영(아래 입장표)해 v3를 썼다. 사용자 규칙("열린 P0가 없으면 진행 · P1은 accepted/rejected로 스펙에")에 따라 진행했고, 같은 문제를 POST에서 다시 본다.

## 1. 계획 r1
A. M- 접두 정의 · B. θ = 10 순 엣지 · MDE ≤ 20 검정력 · 보정 전 2.80과 N = 64 본페로니 ≈ 4.0을 함께 보고 · 스크린 통과 규칙에 MDE는 들지 않고 승격에 N 보정 MDE ≤ 20 · C. carry 가족 예약 2026-08-01 · D. carry 통과 귀무 H0 = 평균(net_A − DTB3_30d) ≤ 0 · 블록 부트스트랩 95% CI 하한 > 0 · E. xs-carry 가족 조항(사용자 원문) · F. S 종류 "닫힌 트라이얼의 사후 비용 민감도".

## 2. advisor PRE — 원문(verbatim)
You're at the protocol v3 PRE (advisor half): #100 recorded, M-1 restore at ~7k/104k in the background, W5 Codex r2 running, v3 plan r1 in chat, nothing written. **Verdict: PROCEED after five fixes; send Codex the fixed plan (r2), not r1.** Save this verbatim to `reports/advisory/protocol_v3_pre.md` first.

**1. You reinterpreted the user on MDE (fix before Codex sees it)**

The user wrote "Screen pass rules use the uncorrected one; promotion additionally requires N-corrected projected MDE ≤ 20." Your plan says MDE isn't in screen pass rules at all. Don't substitute. The coherent reading that matches their own P2 clause (t ≥ 2) is: *any significance threshold inside a screen pass rule is at uncorrected α; screen MDE is a reported number carrying both coefficients; promotion adds the N-corrected gate.* Write it that way and put the reading on the confirmation list. State both coefficients with their tails, because they don't match: uncorrected 2.80 = z(0.975) + z(0.80) is **two-sided** α 0.05; "≈ 4.0" = z(1 − 0.05/64) + z(0.80) = 4.00 is **one-sided** (the judge's convention; two-sided would be 4.21). Disclose, don't harmonise.

**2. Carry null — three things the clause must pin or it's a post-hoc freedom**

- It makes the benchmark part of the pass test, which v2 §3-1 forbids ("보고 열이지 통과 조건이 아니다"). v3 must carve the exception explicitly for `carry` and say clause (가)'s cost for this family = scenario A (10 bps → 15 bps gross per episode).
- Resampling unit and level: "day-block bootstrap CI of that mean [over episodes]" only makes sense with episode = the block (30-day non-overlapping). Write: resample episodes with replacement, 1,000 draws, seed in the spec. Level: "CI lower bound > 0" is ambiguous between one-sided 95% (v2's p95 convention) and two-sided 95%. Pick the two-sided (stricter, literal "CI"), state the equivalence, and flag for confirmation.
- The W3 re-pricing ledger is carrybot's 8h-settlement series, not 30-day episodes; the spec must say how settlements are chunked into non-overlapping 30-day episodes from the ledger start. Protocol: require it; don't define it.

**3. xs-carry clause has an undefined threshold**

"One-week-delay IC collapses toward zero" is not a frozen rule. Either the user supplies a number (e.g. |IC_delay| ≤ ½|IC|, or delayed IC inside the shuffle p95) or v3 marks it **UNRESOLVED** so §3-2 blocks W4 until they do. Also pre-state the direction (positive IC under the position-return convention — v2 forbids post-hoc reversal), that t is computed over non-overlapping weekly ICs (spec fixes the estimator), and that the MDE reported for this family is on the spread's weekly bps return, not on IC.

**4. Post-hoc-sensitivity S type — define its standing**

It counts in k (every START row does), `promoted?` can never be yes for it, and the user's "new formal pre-registration if conditions hold" still goes through §1.7 (full carry lineage = CarryBot G1, v2-hysteresis, this S row; k = carry S rows) — the user's three conditions are *additional* preconditions, not a bypass. Carry-family reserve from 2026-08-01 sits in §4-4 as a family-specific line; the universal 2026-06-30 screen ceiling is unchanged.

**5. Version mechanics**

v3 supersedes #98's anchor; new Drive upload, new row (#101), ledger header updated. Prove §3-3 and §4-4 are unchanged (diff shows only the header and the new/amended sections) so M-1 keeps citing v2 — write that sentence into v3 and into the M-1 RESULT row. Replace v2's line 31 ("이 읽기의 확정은 사용자 결정 목록에") with "confirmed #100".

**Correction list the user asked for (θ = 20 propagation) — report in the briefing, don't edit**

Your grep already found them: `docs/trials/trial_05_candidates_2026-10-11.md` lines 78/89 (hash-pinned by #90 → corrected by #96), `learnings.md` L14 (append-only → #96), `reports/advisory/w1_screen_protocol_pre.md` lines 68/80 (verbatim record of plan r1 — the error originated there), `screen_protocol.md` v2 line 31 (recorded the reading; v3 restates as confirmed). State "no in-place edits; all covered by #96 and #100; v3 carries the correct text."

**Process**

Plan r2 with 1–5 → Codex PRE ("protocol change; does any clause reopen a post-hoc freedom; does the carry carve-out leak into other families; is anything a disguised judge change") → write v3 → full suite (window tests unaffected) → commit, sha → Drive upload, createdTime → #101 → Codex POST → ledger header → `_post.md`. M-1 and W5 r2 keep running; don't start W3 or W4 code until v3 is MERGE and the M-1 briefing is out, per #100's order.

## 3. 계획 r2(verbatim)
## Screen protocol v3 — plan r2 (changes to v2 only; user decisions of 2026-10-14, registry #100)
A. M- prefix: one explicit line — M rows are measurements (execution etc.), ids M-1, M-2, …, never counted in any family's k nor in N.
B. Thresholds: θ = 10 bps is the judge's net-edge threshold; the power threshold is MDE ≤ 20 bps (MDE > 2θ = 20 → underpowered). v2 line 31's open reading becomes "confirmed (#100)". Screen MDE is a REPORTED number given with two coefficients and their tails stated: uncorrected 2.80 = z(0.975)+z(0.80) (two-sided α 0.05, power 0.8) and N = 64 Bonferroni 4.00 = z(1−0.05/64)+z(0.80) (one-sided — the judge's convention; two-sided would be 4.21). Disclosed, not harmonised. Any significance threshold inside a screen pass rule is at UNCORRECTED α (e.g. the xs-carry t ≥ 2). Promotion to a formal trial additionally requires the N-corrected projected MDE ≤ 20 bps (the v1.6 pre-anchor gate). This reading of the user's words ("screen pass rules use the uncorrected one") is put on the confirmation list.
C. Family `carry` — clause replacing v2 §3-1 (나) for this family only (explicit carve-out from "benchmark is a reported column"): H0 = mean over episodes of (net_A − DTB3_30d) ≤ 0; test = bootstrap resampling EPISODES with replacement (episode = non-overlapping 30-day hold = the block), 1,000 draws, seed fixed in the spec; (나) is met iff the TWO-SIDED 95% percentile CI lower bound > 0 (equivalently one-sided 97.5%; the level is put on the confirmation list). Clause (가) for carry: gross mean per episode ≥ 1.5 × cost scenario A (10 bps → 15 bps). Random-entry-date draws = robustness column; funding = 0 control = reported, not tested. Any spec in this family must state how its ledger is chunked into non-overlapping 30-day episodes (the protocol requires it, does not define it). The carve-out applies to `carry` only; other families keep v2 §3-1.
D. Family `carry` reserve: carrybot read data through 2026-07-31, so for this family the untouched window starts 2026-08-01 (family-specific line in §4-4); the universal screen ceiling 2026-06-30 is unchanged.
E. Family `xs-carry` clause (user text), replacing v2 §3-1 for this family: information test = Spearman rank IC: pass iff t ≥ 2 (computed over non-overlapping weekly ICs; estimator fixed in the spec) AND the original mean IC is outside the rank-shuffle p95 (one-sided in the PRE-STATED direction: positive IC under the convention "position return of short-top/long-bottom including funding"; no post-hoc reversal) AND the one-week-delay IC "collapses toward zero" — THIS THRESHOLD IS UNRESOLVED (no number given) → §3-2 execution block applies to W4 until the user fixes it. Cost clause: weekly return in bps of the dollar-neutral long-bottom/short-top spread (including funding paid/received); pass only if mean gross ≥ 1.5 × weekly turnover cost, weekly cost = realised turnover × 10 bps per leg per side (taker); 2 bps (maker) reported as sensitivity. Feasibility: per-leg weekly sd ≤ 250 bps, otherwise "infeasible" regardless of IC. The MDE reported for this family is on the spread's weekly bps return, not on IC.
F. New S-row type "post-hoc cost sensitivity of a closed trial": the original trial's results were already read (disclosed in the row); it COUNTS in the family's k like every START row; promoted? can never be "yes" for this type; a later formal pre-registration still goes through §1.7 (full lineage — for carry: CarryBot G1, CarryBot G1 v2-hysteresis, this S row; k = carry S rows) and the user's three conditions (#100) are ADDITIONAL preconditions, not a bypass.
G. Version mechanics: v3 supersedes #98's anchor (new Drive upload, new registry row #101, ledger header updated). §3-3 (P0 kill rule) and §4-4's P0 exception text are unchanged, so M-1 (started under v2) keeps citing v2 — stated in v3 and in M-1's RESULT row.

## 4. Codex PRE r1 — 프롬프트(verbatim)
```
READ-ONLY PRE-REVIEW (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E. Item: PROTOCOL CHANGE — docs/screen_protocol.md v2 (anchored, registry #98) → v3. User decisions are registry row #100 in docs/trial_registry.md (read it). Plan r2 (verbatim):
## Screen protocol v3 — plan r2 (changes to v2 only; user decisions of 2026-10-14, registry #100)
A. M- prefix: one explicit line — M rows are measurements (execution etc.), ids M-1, M-2, …, never counted in any family's k nor in N.
B. Thresholds: θ = 10 bps is the judge's net-edge threshold; the power threshold is MDE ≤ 20 bps (MDE > 2θ = 20 → underpowered). v2 line 31's open reading becomes "confirmed (#100)". Screen MDE is a REPORTED number given with two coefficients and their tails stated: uncorrected 2.80 = z(0.975)+z(0.80) (two-sided α 0.05, power 0.8) and N = 64 Bonferroni 4.00 = z(1−0.05/64)+z(0.80) (one-sided — the judge's convention; two-sided would be 4.21). Disclosed, not harmonised. Any significance threshold inside a screen pass rule is at UNCORRECTED α (e.g. the xs-carry t ≥ 2). Promotion to a formal trial additionally requires the N-corrected projected MDE ≤ 20 bps (the v1.6 pre-anchor gate). This reading of the user's words ("screen pass rules use the uncorrected one") is put on the confirmation list.
C. Family `carry` — clause replacing v2 §3-1 (나) for this family only (explicit carve-out from "benchmark is a reported column"): H0 = mean over episodes of (net_A − DTB3_30d) ≤ 0; test = bootstrap resampling EPISODES with replacement (episode = non-overlapping 30-day hold = the block), 1,000 draws, seed fixed in the spec; (나) is met iff the TWO-SIDED 95% percentile CI lower bound > 0 (equivalently one-sided 97.5%; the level is put on the confirmation list). Clause (가) for carry: gross mean per episode ≥ 1.5 × cost scenario A (10 bps → 15 bps). Random-entry-date draws = robustness column; funding = 0 control = reported, not tested. Any spec in this family must state how its ledger is chunked into non-overlapping 30-day episodes (the protocol requires it, does not define it). The carve-out applies to `carry` only; other families keep v2 §3-1.
D. Family `carry` reserve: carrybot read data through 2026-07-31, so for this family the untouched window starts 2026-08-01 (family-specific line in §4-4); the universal screen ceiling 2026-06-30 is unchanged.
E. Family `xs-carry` clause (user text), replacing v2 §3-1 for this family: information test = Spearman rank IC: pass iff t ≥ 2 (computed over non-overlapping weekly ICs; estimator fixed in the spec) AND the original mean IC is outside the rank-shuffle p95 (one-sided in the PRE-STATED direction: positive IC under the convention "position return of short-top/long-bottom including funding"; no post-hoc reversal) AND the one-week-delay IC "collapses toward zero" — THIS THRESHOLD IS UNRESOLVED (no number given) → §3-2 execution block applies to W4 until the user fixes it. Cost clause: weekly return in bps of the dollar-neutral long-bottom/short-top spread (including funding paid/received); pass only if mean gross ≥ 1.5 × weekly turnover cost, weekly cost = realised turnover × 10 bps per leg per side (taker); 2 bps (maker) reported as sensitivity. Feasibility: per-leg weekly sd ≤ 250 bps, otherwise "infeasible" regardless of IC. The MDE reported for this family is on the spread's weekly bps return, not on IC.
F. New S-row type "post-hoc cost sensitivity of a closed trial": the original trial's results were already read (disclosed in the row); it COUNTS in the family's k like every START row; promoted? can never be "yes" for this type; a later formal pre-registration still goes through §1.7 (full lineage — for carry: CarryBot G1, CarryBot G1 v2-hysteresis, this S row; k = carry S rows) and the user's three conditions (#100) are ADDITIONAL preconditions, not a bypass.
G. Version mechanics: v3 supersedes #98's anchor (new Drive upload, new registry row #101, ledger header updated). §3-3 (P0 kill rule) and §4-4's P0 exception text are unchanged, so M-1 (started under v2) keeps citing v2 — stated in v3 and in M-1's RESULT row.
QUESTIONS: (1) Does any clause reopen a post-hoc degree of freedom? (2) Does the carry carve-out leak into other families or into the formal judge? (3) Is anything a disguised change to the formal judge (θ = 10 bps, MDE cutoffs 20/5, α, MDE rule, registry #88)? (4) Is the xs-carry clause executable as written, and is marking the delay threshold UNRESOLVED the right handling? (5) Do v2's guarantees (D4 reserve in code, two-ledger k counting, START-before-data) survive unchanged? Also check the arithmetic of the two MDE coefficients.
OUTPUT: numbered findings P0/P1/P2; one line per question; end with exactly one line: VERDICT: MERGE or VERDICT: FIX-PLAN-FIRST.
```

## 5. Codex PRE r1 — 응답 원문(verbatim)
1. **P1 — Q1:** C changes #100’s “daily-block bootstrap” to resampling 30-day episodes; this can change the verdict and needs explicit confirmation. Add the block unit to the confirmation list; keep it, the CI level, and B’s interpretation UNRESOLVED until confirmed. W3 must preserve the original ledger and freeze its episode mapping before recomputation. [#100](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:108)
2. **P2 — Q2:** The carry carve-out is adequately confined to carry screens; it does not authorize replacing another family’s rule or the formal judge. Explicitly reconcile the overrides with §3-1’s existing tail language, §3-4’s precedence rule, and §6’s “reported benchmark” wording.
3. **P2 — Q3:** No disguised formal-judge change is apparent: θ=10, MDE cutoffs 20/5, formal α/n_eff, and #88 remain intact; N=64 reporting must not settle future formal α. Arithmetic: uncorrected **2.801585→2.80**, corrected one-sided **4.004439→4.00**, corrected two-sided **4.200975→4.20**, not 4.21.
4. **P1 — Q4:** xs-carry is not executable while “collapses toward zero” lacks a numerical criterion; UNRESOLVED plus §3-2’s pre-data block is correct. The user must fix the delay criterion, and the spec must freeze the estimator, shuffle construction, portfolio normalization, turnover accounting, and missing-data handling before W4 reads data.
5. **P1 — Q5:** D4’s code ceiling and S-family k/M-excluded N counting survive. START-before-data needs an explicit historical-exposure qualification for F: START precedes the new repricing/read, while prior results remain disclosed. W3’s inherited ledger and outcomes must still pass the June ceiling; August 1 denotes carry’s potential untouched reserve, not permission to process July. M-1 correctly retains v2.
VERDICT: FIX-PLAN-FIRST


## 6. 입장표
| 출처 | 등급 | 요지 | 입장 |
|---|---|---|---|
| advisor 1 | — | MDE의 사용자 문장을 바꿔 읽지 말 것 · 계수 꼬리 공시 | 동의 — v3 §2 |
| advisor 2 | — | carry 예외의 명시 · 재표본 단위 · CI 수준 · 에피소드 나누기 | 동의 — v3 §3-1a |
| advisor 3 | — | xs-carry 지연 문턱 미정 → UNRESOLVED · 방향 · t의 추정 · MDE 대상 | 동의 — v3 §3-1a |
| advisor 4 | — | 사후 민감도 S 종류의 지위 | 동의 — v3 §5 |
| advisor 5 | — | 판 관리 · §3-3 · §4-4 불변 증명 | 동의 — diff로 확인(§3-3 · §4-4 동일) |
| Codex 1 | P1 | 사용자 원문은 "day-block bootstrap" — 에피소드 재표본은 바꿔 읽기 · 단위·수준·B의 읽기를 확인 전 UNRESOLVED로 | **accepted** — v3 §3-1a carry ①② UNRESOLVED(W3 실행 차단) |
| Codex 2 | P2 | carry 예외를 §3-1 꼬리 · §3-4 우선 · §6 보고 문구와 맞춰라 | accepted — §3-1a 머리말 |
| Codex 3 | P2 | 계수 산수 4.20(4.21 아님) | accepted — v3 §2 |
| Codex 4 | P1 | xs-carry는 지연 문턱 없이 실행 불가 · 스펙이 고정할 것 목록 | accepted — §3-1a |
| Codex 5 | P1 | 사후 민감도의 START 의미 · 물려받은 장부도 6월 상한 · 8월은 7월 허용이 아님 | accepted — §4-5 · §5 |
