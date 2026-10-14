# W2 — P0 메이커 진입 실행 감사(M-1) 스펙 · PRE(착수 전 검토)

- 날짜: 2026-10-14 · 항목: W2 스펙(CRITICAL) · 검토자: advisor + Codex(`codex-companion task` · 읽기 전용 · 회전마다 새 스레드라 직전 회전의 응답을 프롬프트에 붙였다)
- 원문은 그대로 붙였다. 스펙 초안 r1~r5는 확정본(r6) 커밋 전의 작업본이며, 회전마다의 차이는 스펙 §10에 적혀 있다.

## 1. 회전 표
| 회전 | 대상 | 판정 |
|---|---|---|
| advisor | r1 | FIX-FIRST(P0 4 · P1 6) |
| Codex r1 | r2 | FIX-SPEC-FIRST(P0 7 · P1 1) |
| Codex r2 | r3 | FIX-SPEC-FIRST(PARTIAL 3 · 새 P0 2 · P1 1) |
| Codex r3 | r4 | FIX-SPEC-FIRST(PARTIAL 4 · 새 P0 1 · P1 2) |
| Codex r4 | r5 | FIX-SPEC-FIRST(PARTIAL 2 · P2 1) |
| Codex r5 | r6 | **MERGE** |

## 2. 입장표(요지 — 모두 반영)
| 출처 | 요지 | 입장 |
|---|---|---|
| advisor A | 머리 통계를 시간 몫으로 가중 · 수수료 차이 공시 · BNB 민감도 | 동의(r2) · 공시 문구는 Codex r1-8로 정정(절감 ≈ 3 bps × 체결 비율) |
| advisor B | 같은 가격과 넘어선 체결을 분리 · δ | 동의(r2) → Codex r1-1이 넘어선 체결 규칙 자체가 사용자 규칙 위반이라 지적 → **삭제**(r3) |
| advisor C | 복원 전제(매니페스트 대조 · 99%) · START는 내려받기 전 | 동의 · Codex r1-4: 매니페스트에 shard SHA256이 없다 → Drive MD5 · `remote_md5` · footer 행 수로(r3) |
| advisor D | p0 전용 가드 시험 · 합성 shard | 동의(§7) |
| advisor P1 | 불균형 부호 · 대조 ② · 25 블록 · MIN_NOTIONAL · 지표 의미 · M-1 | accepted 전부 |
| Codex r1-2 · r2-9 · r2-10 · r3-9 | 배치 시점과 시계 | 동의 — 재생 원칙 하나 · B_d = 2 × p99.9(가정 공시 + B = 0 / 6,000 ms 민감도) · `clock_skew` 구간 제외(r5) |
| Codex r1-3 · r2-3 · r3-3 · r4-3 | 대조의 대칭 | 동의 — 방향 뒤집기 재생 · 기증 규칙 · 틱 이동 · 부호 있는 시각 이동 · 짝지은 모집단(r3~r6) |
| Codex r1-5 · r2-5 · r3-5 | 적격 · 실행 가능 가격 | 동의 — `agg_trade_id` 연속 · 중복 처리 · 원천 교차 · 단계 평균가 · 20단계 부족(r4~r5) |
| Codex r1-6 | 경계 읽기 계약 | 동의(§2-3 · 시험) |
| Codex r1-7 | 표본 구성 | 동의(§3) |
| Codex r3-12 · 13 · 14 | 벤치마크 b₀ · 거부 폴백 · 늦은 체결 진단 범위 | 동의(r5 · r6) |

## 3. advisor PRE — 원문(verbatim)
You're at the W2 PRE (advisor half): spec r1 drafted, no data read, restore not started, nothing committed. **Verdict: FIX-FIRST on four spec items, then Codex PRE on r2.** Save this verbatim into `reports/advisory/w2_p0_spec_pre.md` before anything else. Write r2 with A–D folded in, then send Codex r2 (not r1) — it saves a round.

**A. The kill statistic is undefined as written (P0).** The sample is 25 % settlement-proximity decisions on 2 % of the clock (30 of 1,440 min). "평균 편도 순 개선" over all eligible decisions weights the settlement stratum ~12×. Pre-fix the headline: time-share weighting (settlement 30/1440, other 1410/1440), which is what a bot entering at arbitrary minutes faces; per-stratum means are the decomposition. Then disclose the arithmetic the threshold hides: fee differential alone = 5 − 2 = **3 bps**, so "≥ 2 bps" means "price effects (fallback slippage, adverse fills) cost ≤ 1 bps". The account probe shows BNB ×0.75 enabled → 1.5/3.75, differential 2.25 — add that pair as a **report-only sensitivity** (primary stays 2/5 per the user's text) and say the kill is nearly decided by the fee assumption.

**B. Fill rule — separate "at our price" from "through our price" (P0).** Cumulative volume toward Q must count only aggressor trades **at exactly our price** (BUY: `is_buyer_maker=True`, price == our bid). A trade strictly beyond our price (BUY: sell-aggressor below our bid) is a sweep → fill at that trade's time, full size. Mixing them into one `≤` cumulative double-counts. Also state: the resting price never changes (no re-quote), queue growth behind us is irrelevant, cancellations ahead are ignored (conservative for fill rate), and the placement latency — pick δ (0 or e.g. 200 ms after t0, book state at t0+δ) and write it; "t0 state" is an unstated zero-latency assumption.

**C. Restore has a precondition you haven't checked (P0).** The Drive copy may not match `manifest.sqlite` rows (compact/resort tools exist in E2E; the manifest's `source` enum doesn't obviously list `l2live_bookticker`/`l2live_aggtrade` paths as shards — verify before assuming). Order: download `manifest.sqlite` (596 MB) first → count `files` rows per source for 09-17..10-11 and compare with the Drive listing (~1,432/1,438/1,432 per day) → if coverage < a pre-fixed floor (say 99 %), stop and report; otherwise restore the three streams to `var/p0_restore/` (gitignored, ~7.6 GB), verify sha256 per file + rclone `--checksum` md5, write `M-1_restore.json`. Write the **M-1 START row before the download** (the protocol says before reading data; don't argue the download/interpretation distinction — just do it). Deletion of the restore afterwards is a user-confirmed step; don't schedule it.

**D. p0 needs its own guard test (P0).** The p1/p2 static rule skips p0 by design. Add `tests/test_screen_p0_guard.py`: p0 constants equal the protocol's exposed span (2026-09-17 00:00Z → 2026-10-11 06:22:15Z, and the 07-24→09-16 auxiliary span is *not* referenced since the spec drops it); p0 imports nothing from `backtest`/`strategies`/`paper`/`exchange`; p0 opens only paths under the restore root; no order-path strings. Also test the fill rule on synthetic shards (queue-ahead boundary, sweep, timeout fallback) before touching real data.

**P1 — carry into r2 with accepted/rejected lines**
- Imbalance terciles: sign relative to order direction (favourable/against), one set of boundaries from the full eligible sample.
- Tape-shift control: well-defined but odd (book at t0, tape from t0+Δ price-shifted). Keep report-only, or replace with "same clock, different day" tape; state which and why. The always-fallback lower bound is the useful one.
- CI: 25 day-blocks is the effective sample; say so next to "9,700 decisions". 10-10's FAIL window is excluded by the gap rule — confirm the manifest `gaps` table actually contains it.
- Notional: 0.001 BTC must clear MIN_NOTIONAL 50 at the decision mid; exclusion rule if not (can't check the price before START — write the rule).
- Metric disclosure: IS vs immediate taker equals a common-horizon P&L comparison only if both paths exit on the same clock from t0; a time-exit measured from fill would shift holding time. One sentence.
- Label: proceed as M-1; S-vs-M stays on the user list.

**Process after r2:** Codex PRE (prompt = r2 verbatim + the user's spec questions: statistic pre-fixed? placebo symmetric? cost model measured? reads 2026-07-01+ only within the exposed span? touch=fill anywhere?) → resolve P0s → commit spec, sha256 → M-1 START row (spec hash, protocol v2 hash, code commit) → manifest download + coverage check → restore + verify → code under `p0/` with synthetic-shard tests → one run → RESULT row → POST. No restore and no `p0/` code until the START row is in.

## 4. Codex PRE r1 — 프롬프트와 응답 원문
```
READ-ONLY PRE-REVIEW (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E. Item: W2 = P0 maker-entry execution audit, recorded as measurement M-1 under docs/screen_protocol.md v2 (read §1, §3-3, §4-4, §5 first). The spec r2 to review is research/screens/p0_exec_audit_spec.md (uncommitted working copy; r1 + the first reviewer's fixes). Collector writer code (for the parquet schemas and manifest table) is in /home/cms/project/E2E_Hybrid_Bot/e2e/l2_collector.py and e2e/manifest.py. No data has been read.
User-fixed facts: kill rule "if net improvement including fallback cost is < 2 bps per side at the best T, the result is stay taker"; T in {30,60,120} s; fees maker 2 / taker 5 bps on perp; fill rule "a resting order counts as filled only when the cumulative opposite-side aggTrade volume at that price level after placement exceeds the visible queue ahead at placement; price-touched-equals-filled is NOT allowed"; placebo: direction randomisation plus a shuffled-timestamp control; data 2026-09-17 -> 2026-10-11 single-regime pilot; the 07-24 -> 09-16 span may only feed a touch-frequency column (the spec chooses not to use it).
ANSWER THE USER'S QUESTIONS for this spec:
Q1 Is the statistic pre-fixed (including stratum weighting, best-T selection, tie rule, denominator)?
Q2 Is the placebo/control symmetric with the measured ledger (same eligibility, same fill rule, same fees)?
Q3 Is the cost model the measured one (fees as stated; slippage only through recorded book/tape)?
Q4 Does the design read 2026-07-01+ data outside the exposed span (2026-09-17 -> 2026-10-11 06:22:15Z)?
Q5 Does the fill rule assume touch = fill anywhere (including the sweep rule, latency, and fallback)?
Also: is anything a post-hoc degree of freedom; is the restore/verification order sound; is the START-before-download rule satisfied by the plan.
OUTPUT: numbered findings tagged P0 (must fix before the spec is committed) / P1 (carry with accepted/rejected) / P2; one line per Q1-Q5; end with exactly one line: VERDICT: MERGE or VERDICT: FIX-SPEC-FIRST.
```
1. **[P0] Sweep rule violates the user-fixed fill rule.** [Spec:32](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:32) grants a full fill from one trade beyond the limit, without cumulative opposite-side volume **at the order price** exceeding Q. Remove this alternate trigger. The same-price `Q + 0.001` threshold is conservative and satisfies the required queue threshold.

2. **[P0] Placement chronology is insufficient.** [Spec:30](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:30) filters only by `recv_ms`; a trade executed before placement but received afterward can consume Q. The schema includes `transact_time` ([collector:101](/home/cms/project/E2E_Hybrid_Bot/e2e/l2_collector.py:101)). Freeze clock alignment, exclusion of preplacement executions, and equal-timestamp/deadline ordering. A locally observed same-side quote also does not establish guaranteed post-only acceptance.

3. **[P0] The shuffled control is not a fully specified symmetric ledger.** [Spec:46](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:46) replaces only aggTrade tape; donor eligibility, donor-mid timestamp, failed-donor handling, queue/book mapping, fallback prices, and fee treatment remain incomplete. An arbitrary mid-price translation can also destroy exact-price matching. Freeze these rules and a separate direction-randomized replay; random directions in the original sample alone do not define that comparison.

4. **[P0] Restore verification assumes checksums the writer does not supply.** [Spec:15](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:15) requires `files.sha256`, but [collector:185](/home/cms/project/E2E_Hybrid_Bot/e2e/l2_collector.py:185) registers only path and row count. The manifest separately supports persisted `remote_md5` ([manifest:69](/home/cms/project/E2E_Hybrid_Bot/e2e/manifest.py:69)). Freeze handling of absent hashes and distinguish historical checksum evidence from newly computed restore hashes. The order is otherwise sensible; calculate the 99% ratio from **matched expected file identities**, and recheck retained coverage after verification exclusions.

5. **[P0] Eligibility does not establish complete tape or executable prices.** [Spec:23](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:23) relies on three-stream gaps, but this collector records depth-silence gaps under `l2collector` ([collector:408](/home/cms/project/E2E_Hybrid_Bot/e2e/l2_collector.py:408)). Verified shards cannot rule out an internal aggTrade interruption. Freeze stream-completeness checks and handling of stale/missing baseline and fallback quotes, insufficient displayed quantity, and inconsistent books. Otherwise full-size L1 fills can understate measured costs.

6. **[P0] Exact exposure boundaries need an ingestion contract.** [Spec:49–50](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:49) requires constants and a restore-root restriction, without specifying timestamp filtering for boundary shards. Shards rotate from their first row and use different timestamp columns ([collector:164](/home/cms/project/E2E_Hybrid_Bot/e2e/l2_collector.py:164)). Explicitly bound all decision lookbacks, timeout outcomes, and donor windows; prevent outside-span price/volume interpretation and test mixed-boundary shards. Manifest metadata inspection is distinct from market-data exposure.

7. **[P0] Sample construction retains implementation choices.** [Spec:21](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:21) leaves hourly 12/13 allocation, partial-day rounding, replacement, and overlap handling unspecified. Freeze these plus exact direction assignment and empty-stratum behavior. A fixed seed alone does not resolve them. The stated statistic, weights, T selection, tie rule, and denominator are otherwise explicit.

8. **[P1 — carry; proposed disposition: ACCEPT] Correct the interpretation claims.** [Spec:35](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:35) treats fee savings as 3 bps across all decisions; they are approximately **3 × maker-fill fraction**, since fallback still pays taker fees. Thus the 2-bps threshold is not generally equivalent to price costs ≤1 bps. “Always fallback” is a comparator, not a guaranteed lower bound, and ignoring cancellations does not guarantee conservative **net improvement** ([spec:55](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:55)).

9. **[P2] START-before-download is satisfied by the plan.** [Spec:6](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:6) and its ordered restore procedure require committed START before even downloading the manifest. This is a plan-level finding; no execution compliance is claimed.

Q1: **Yes for the named statistic components**; sample construction and undefined-stratum handling remain post-hoc freedoms until finding 7 is fixed.

Q2: **No.** Control eligibility, execution mapping, fallback, and fees are not fully frozen symmetrically.

Q3: **Partial.** Primary fees are correctly 2/5 bps and no external slippage adder is specified; chronology and executable-book handling still prevent certification of the measured cost ledger.

Q4: **No outside-span market data is intentionally requested**, including the unused July–September auxiliary span; exact boundary exclusion is not yet adequately specified.

Q5: **The required fill rule is not satisfied.** Sweep bypasses exact-price queue exhaustion, latency can count preplacement executions, and taker fallback needs explicit executable-quantity handling.

VERDICT: FIX-SPEC-FIRST


## 5. Codex PRE r2 — 응답 원문(프롬프트 = r1 응답 + 과제 문장)
```
READ-ONLY PRE-REVIEW ROUND 2 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E. Your round-1 review of the P0 spec gave P0 findings 1-7 and P1 8. The spec is now r3: research/screens/p0_exec_audit_spec.md (uncommitted working copy; section 10 lists what changed). Collector code: /home/cms/project/E2E_Hybrid_Bot/e2e/l2_collector.py, e2e/manifest.py, ops/verify_drive_copies.py.
TASK: for findings 1-8 say RESOLVED / PARTIAL / OPEN with one line each against r3; list NEW findings tagged P0/P1/P2 (only things that must be fixed in the SPEC before it is committed; implementation will get its own POST review). Re-answer in one line each: Q1 statistic pre-fixed; Q2 placebo/control symmetric with the measured ledger; Q3 cost model = measured; Q4 reads data outside 2026-09-17 -> 2026-10-11 06:22:15Z; Q5 touch = fill anywhere. End with exactly one line: VERDICT: MERGE or VERDICT: FIX-SPEC-FIRST.
```
1. **RESOLVED** — r3 permits maker fills only from exact-price opposite-side volume reaching `Q + 0.001`; sweep fills are removed. [r3:58](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:58)
2. **PARTIAL** — Exchange-time bounds and local post-only limitations are explicit, but the clock correction admits preplacement executions, and same-timestamp quote/deadline ordering remains incomplete. [r3:57](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:57)
3. **PARTIAL** — Controls now specify donors, failures, tick translation and fees, but donor `p′` needs an exact anchor, mapped timestamps need equations, and paired eligibility remains inconsistent. [r3:78](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:78)
4. **RESOLVED** — Verification uses available MD5/footer evidence, distinguishes restore hashes, matches file identities and rechecks retention after exclusions. [r3:21](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:21)
5. **PARTIAL** — Collector gaps and quote freshness are addressed, but aggTrade continuity/duplicate checks, baseline executable quantity, fallback depth freshness, inconsistent books and insufficient total depth still lack fixed handling. [r3:46](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:46)
6. **RESOLVED** — Timestamp-first filtering explicitly bounds market values, lookbacks, outcomes and donor windows; mixed-boundary shard tests are required. [r3:29](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:29)
7. **RESOLVED** — Allocation, partial-day rounding, replacement, draw order, directions, overlap and empty primary strata are fixed. [r3:34](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:34)
8. **RESOLVED** — Fee savings depend on maker-fill fraction; always-fallback is a comparator; cancellation omission has no guaranteed improvement bias. [r3:65](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:65)

New findings:

9. **[P0] The new clock correction subtracts receive latency from placement time.** `recv_ms − transact_time` contains both clock offset and receive delay; it cannot identify clock offset alone. With synchronized clocks and 100 ms receive delay, placement at exchange time 10.200 becomes `t_exch = 10.100`, admitting a trade executed at 10.150 before placement. Freeze independently justified clock alignment or conservatively exclude timing uncertainty; define calibration availability and failure handling. [r3:57](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:57)

10. **[P0] The replay specifies conflicting chronology rules.** §2-3 requires all market values in receive order and says exchange timestamps serve only the postplacement test; §4-3 instead accumulates in exchange order and applies an exchange-time deadline. A qualifying execution received after local timeout therefore lacks a defined relationship to fallback. Freeze whether this reconstructs actual exchange fills or replays locally available information, including late-fill reconciliation and deadline ties, and apply that rule to controls. [r3:31](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:31), [r3:58](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:58)

11. **[P1] Control-only exclusions can change the comparison population.** The common-eligibility promise conflicts with donor failures being removed only from control ②; reversing direction can also expose different quantity/fallback failures. Specify paired eligibility and report the measured statistic recomputed on each control’s retained decisions with identical weights and denominator. [r3:76](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:76)

Q1: **Yes for the named statistic and sampling rules**; unresolved execution eligibility still prevents a fully frozen measurement.

Q2: **No** — control timestamp mapping and paired eligibility are not yet fully symmetric.

Q3: **Partial** — fees are fixed at 2/5 bps and prices come from observations, but chronology and full-size executable-price handling remain incomplete.

Q4: **No outside-span market values are authorized**; outside-row timestamps and manifest/footer metadata are inspected under the bounded ingestion contract.

Q5: **No touch/sweep-as-fill rule remains**; exact-price queue exhaustion is required, but the clock defect can still admit preplacement volume.

VERDICT: FIX-SPEC-FIRST


## 6. Codex PRE r3 — 응답 원문
Item 2 — **PARTIAL**: Quote/deadline equality rules are explicit; a valid exchange-time placement bound remains unresolved. [r4:58](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:58)

Item 3 — **PARTIAL**: `p′` and paired populations are specified; freeze the signed mapping `t_mapped = t′ − (d′−d)×86,400,000` and donor-anchor freshness/validity. The current shift lacks an explicit subtraction. [r4:80](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:80)

Item 5 — **PARTIAL**: Continuity, depth quantity, freshness and cross-source checks are added; duplicate IDs still need earliest-receipt retention and exclusion of conflicting payloads, since arbitrary retention can change deadline eligibility. [r4:46](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:46)

Item 9 — **PARTIAL**: Subtraction is removed, but empirical p99 is not an arrival bound: negative clock skew or greater outbound latency can still admit pre-arrival trades; full-day/full-span calibration also lacks availability rules consistent with local-information replay. Freeze justified clock/latency bounds and calibration availability/failure handling. [r4:58](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:58)

Item 10 — **RESOLVED**: Receive-time deadline inclusion, strict exchange-time lower bounds and fallback treatment of late arrivals now define the primary replay chronology. [r4:59](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:59)

Item 11 — **RESOLVED**: Each control uses paired eligibility and recomputes the primary statistic with identical weights and denominator on retained decisions. [r4:85](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:85)

NEW 12 — **[P0] Benchmark pricing contradicts the headline formula**: §4-1 permits depth-weighted immediate-taker prices, but §§4-4/5 still use `ask₀`/`bid₀`. Define executable benchmark prices separately and use them throughout the statistic and controls. [quantity rule](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:47), [formula](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:71)

NEW 13 — **[P1] Rejection fallback bypasses executable-quantity handling**: §4-2 prices an immediate rejection fallback entirely at the opposite best quote; require the same full-size depth pricing and insufficient-depth exclusion as timeout fallback. [r4:54](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:54)

NEW 14 — **[P1] Late-conflict diagnostics lack fixed bounds**: Specify the latest eligible exchange execution and receipt-observation horizon; otherwise post-timeout executions can count as conflicts and the diagnostic has no defined relationship to the fixed `+125s` outcome window. [r4:60](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:60)

Q1: **PARTIAL** — Statistic, weights, denominator and T selection are pre-fixed; the executable benchmark input remains contradictory.

Q2: **PARTIAL** — Paired populations are symmetric; donor timestamp mapping and anchor validity remain incomplete.

Q3: **PARTIAL** — Prices are observed and fees fixed, but timing bounds, benchmark pricing and rejection sizing prevent a fully specified executable-cost measurement.

Q4: **No outside-span market values are authorized** — Only outside-row timestamps and manifest/footer metadata may be inspected; July–September auxiliary data remain excluded.

Q5: **No touch-as-fill rule remains anywhere** — Exact-price opposite-side queue exhaustion is required; unresolved timing bounds can still admit invalid volume.

VERDICT: FIX-SPEC-FIRST


## 7. Codex PRE r4 — 응답 원문
Item 2 — **RESOLVED**: Equality rules and placement timing are fixed under the explicitly disclosed B_d assumption. [r5:59](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:59)

Item 3 — **PARTIAL**: Signed mapping and bookticker freshness are fixed; require donor depth used for the cross-source check to be received by the donor anchor and ≤1 second old. [r5:83](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:83)

Item 5 — **RESOLVED**: Duplicate IDs retain earliest receipt; conflicting payloads exclude the decision. [r5:51](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:51)

Item 9 — **RESOLVED**: The disclosed assumption, calibration availability and B=0/6000 sensitivities are acceptable for this assumption-conditioned offline report-and-kill measurement; an independent clock reference is not required. [r5:59–60](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:59)

Item 12 — **RESOLVED**: Executable benchmark b₀=X(t0, direction) is used consistently throughout the cost statistic. [r5:73](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:73)

Item 13 — **RESOLVED**: Rejection fallback uses X, including full-size depth pricing and insufficient-depth exclusion. [r5:55](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:55)

Item 14 — **PARTIAL**: Receipt observation is bounded at deadline+5 seconds; explicitly bound exchange execution under the declared cancellation-grace model and restrict conflict counting to primary timeout/fallback decisions. [r5:62](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:62)

NEW 15 — **[P2] Stale guard-test parameter**: §7 still specifies undefined `q_d`; replace it with `B_d` so the required placement-bound test matches r5. [r5:93](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:93)

Q1: **RESOLVED** — Statistic, weights, denominator, executable benchmark and T selection are fixed.

Q2: **PARTIAL** — Mapping and paired populations are fixed; donor depth freshness remains incomplete.

Q3: **RESOLVED** — Primary executable costs are specified under disclosed timing, queue and acceptance assumptions.

Q4: **No outside-span market values are authorized** — Outside-row timestamps and manifest/footer metadata are permitted; auxiliary market data remain excluded.

Q5: **No touch-as-fill rule remains** — Exact-price opposite-side volume must exhaust Q+0.001, subject to the declared timing assumption.

VERDICT: FIX-SPEC-FIRST


## 8. Codex PRE r5 — 응답 원문
Item 3 — **RESOLVED**: Donor bookticker and depth must both be received by the donor anchor and ≤1 second old before the cross-source check. [r6:83](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:83)

Item 14 — **RESOLVED**: Exchange execution is bounded by deadline + B_d under the declared cancellation assumption; receipt by deadline + 5 seconds; counting is restricted to primary timeout fallbacks. [r6:62](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:62)

Item 15 — **RESOLVED**: The guard-test requirement now uses `B_d`, matching the placement bound. [r6:93](/home/cms/project/BTC_Futures_E2E/research/screens/p0_exec_audit_spec.md:93)

NEW spec-level findings — None identified.

Q1: **RESOLVED** — Statistic, weights, denominator, executable benchmark and T selection remain fixed.

Q2: **RESOLVED** — Signed mapping, paired populations and donor-source freshness are specified.

Q3: **RESOLVED** — Primary executable costs are specified under disclosed timing, queue and acceptance assumptions.

Q4: **No outside-span market values are authorized** — Outside-row timestamps and manifest/footer metadata are permitted; auxiliary market data remain excluded.

Q5: **No touch-as-fill rule remains** — Exact-price opposite-side volume must exhaust Q + 0.001, subject to the declared timing assumption.

VERDICT: MERGE

