# W4 · S-xs-carry-1 PRE(착수 전 검토)

- 회전: advisor(W4 설계 안내 — 아래 원문 · v4 POST 호출에 포함) → 스펙 r1 → Codex PRE r1 **FIX**(P1 5 · P2 3) → r2 → r2 **FIX**(P1 4 · P2 1) → r3 → r3 **FIX**(P1 3) → r4 → r4 **FIX**(P1 1) → r5 → r5 **MERGE**(P2 1: 허용 목록 두 줄 섞임) → r6 → **r6 MERGE**.
- 공시: S3 목록(이름 · 크기)만 봤다 · 내려받기는 START 뒤.

## 입장표(Claude Code)
| 회전 | 요지 | 입장 |
|---|---|---|
| r1 | T 일봉 적격 = 미래 정보 · 상장 폐지/공백 혼동 · 목표 가중 회전 · 나이 관측 범위 · 벤치마크 식 | 동의 — r2 |
| r2 | 보유 주 나쁜 레코드가 적격에 영향 · 사후 청산 · 주기 무시 완전성 · 지연 두 정의 · 정의 안 되는 통계 | 동의 — r3 |
| r3 | 경계 결손 · 나쁜 보유 레코드 수치 처리 · 주 끝 강제 청산 이월 | 동의 — r4 |
| r4 | 한 칸 다중 일치 | 동의 — r5(충돌 → 빠진 정산) |
| r5 | 허용 목록 두 줄 섞임(P2) | 동의 — r6(심볼별 다시 만듦 · 문법 검사 · 빠진 키 3개 복구 · 비 ASCII 5개 제외 규칙) |
| r6 | 전부 RESOLVED · 비 ASCII 제외는 자료 전 규칙으로 수용 · MERGE | — |

## advisor — W4 설계 안내 원문(verbatim · v4 POST 호출에서)
**W4 — order of operations.** Spec → advisor + Codex PRE (`reports/advisory/w4_xs_carry_pre.md`) → START row (`S-xs-carry-1`, k = 1 for that family, cites v4 `d29aa024…`) → download → single run → RESULT → POST → briefing. Download comes *after* START, as M-1 did; only names and sizes before.

**Two facts to get before writing the spec, both without opening data:**
- Size the download from the S3 listing itself: list *objects* (not just prefixes) under `data/futures/um/monthly/fundingRate/` and `klines/*/1d/`; the XML carries `<Size>`. Sum bytes and count files for months ≤ 2026-06. That tells you whether 988 symbols × 66 months × two streams is minutes or hours, and whether you need a listing-age floor just to make it tractable.
- Funding archive schema: Binance's monthly fundingRate CSVs changed over time (header vs no header; `calc_time,funding_interval_hours,last_funding_rate` in newer files). Fetch two zip *names* from different years and check with `zip_has_header` only after START; but note in the spec that the loader passes `header=` explicitly per file and fails on a non-integer timestamp cell rather than guessing.

**What the spec must pin** (v4 §3-1a lists five; Codex POST added four; here they are concretely so Codex can't call any of them open):
1. Universe: point-in-time — a symbol is in week t's cross-section iff its fundingRate archive has settlements for every day of signal week t−1 *and* its first archive row is ≥ L weeks earlier (pick L, e.g. 4). USDT-quoted perps only (state what happens to BUSD twins). Minimum cross-section per week (e.g. 20); weeks below it are excluded and counted.
2. Week = Monday 00:00 UTC → Monday 00:00 UTC. Signal = sum of settled funding rates in week t−1. Position held week t. Lag-1 column uses week t−2's signal for week t.
3. Estimator: Spearman IC per week between signal and the position-week spread return; t = mean/sd × √n over non-overlapping weeks (ddof 1). MDE on the weekly dollar-neutral spread in bps, same n_eff/ρ̂ rule as S-carry-1.
4. Portfolio: equal-weight long bottom decile / short top decile (state decile → quantile rule when n < 20), 100% gross each leg. Return per name = price return from klines close at week boundaries, signed, plus funding received/paid during the week. Per-leg weekly sd for the 250 bps rule from these.
5. Turnover: fraction of each leg replaced at the rebalance × 2 sides; cost = turnover × 10 bps per leg-side; 2 bps maker column.
6. Missingness: listed mid-week → excluded that week; delisted mid-week → return to last available close (keep it — dropping is the survivorship bias you just confirmed the archive lets you avoid); missing funding row within an included week → the symbol is excluded that week and counted.
7. Shuffle null: permute ranks within each week independently, recompute mean IC, 1,000 draws, one seed, fresh RNG per column, p95 linear; direction fixed as the v4 convention (positive IC = short-top/long-bottom earns).
8. Reads: p2 modules under the static rule; `bounded_zip_csv` only; never fetch a 2026-07+ archive name at all; input manifest (file list + SHA256) in the RESULT row.

**One blind spot to pre-empt in the spec, not after.** Funding is strongly autocorrelated, so an IC between last week's funding and a return that *includes* this week's funding will be positive almost by construction. That's the carry hypothesis, so it's fine as the pass statistic — but add a reported decomposition column: spread return split into price component and funding component, and the IC against the price component alone. Report-only, not a pass condition, declared before data. Without it a reviewer reads a t ≥ 2 and asks whether anything beyond funding persistence was measured.

W5 still waits on (A)/(B); nothing to do there.

## Codex PRE r1 — 원문(verbatim · 최종 메시지)
**Not ready for START.** The decision thresholds are faithful to v4, but eligibility, missingness, and realised turnover still need fixes. Review was read-only: no files changed and no market data downloaded. No P0 or BLOCK-USER finding; these are spec-level corrections.

- **P1 — Entry eligibility uses future information.** [Spec line 25](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:25) requires a daily bar with `open_time=T`. That bar’s existence reflects trading during the holding day and is not necessarily known at entry. It can exclude symbols that stop trading around entry, conditioning the universe on subsequent survival. Define eligibility entirely from information available before the stated entry event; handle subsequent missing prices through the outcome policy.

- **P1 — Delisting and ordinary data gaps are conflated.** [Line 30](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:30) treats any missing terminal daily bar as mid-week delisting and substitutes the last close. There is no rule for distinguishing delisting from an incomplete archive, handling no holding-week bars, establishing the exit timestamp, or accounting for the remaining cash period and exit trade. Likewise, “one funding settlement per day” does not establish completeness within each day. Pin deterministic rules for missing archives, intraday funding gaps, duplicate/nonfinite records, genuine delisting, and unresolved outcomes. Keeping historical symbol names helps, but does **not yet establish survivorship-free outcomes**.

- **P1 — Turnover measures changes in target weights, rather than realised traded notional.** [Lines 38–40](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:38) compare successive `1/q` weights. Unchanged membership gives zero turnover even when price drift means restoring each leg’s total notional to one requires trades. The formula also lacks an explicit treatment of intrawEEK delisting exits and the resulting cash state. Pin quantities, pre-rebalance notionals, funding cash treatment, actual closing/opening trades, and final liquidation. **The cost coefficients themselves are correct:** summed turnover × 10 bps, 2 bps sensitivity, gross mean ≥ 1.5 × mean cost, and leg SD strictly >250 bps overriding the information tests.

- **P1 — “First funding settlement” has an unresolved observation scope.** [Line 24](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:24) does not distinguish the first-ever settlement from the first settlement observable inside the guarded window. The manifest contains **1,016 pre-2021 archives**, whose funding values cannot establish age through the ordinary guarded reader. Define age from permitted observations, disclose left censoring and the distinction from actual listing age, and specify relisting/symbol-reuse treatment. Under a first-in-window definition, even a first observation on January 1 cannot satisfy this age rule before the February 8 holding week; earlier scheduled weeks must consequently be excluded.

- **P1 — Benchmark arithmetic is not fully pinned.** [Line 55](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:55) subtracts `DTB3/52` from a spread measured in bps without defining DTB3’s units or where the weekly benchmark is averaged. Specify `mean_t(net_t − benchmark_t)`, the percent-to-bps conversion, the chosen holding-period conversion, and missing-observation handling. For an annual quote of 5%, the `/52` convention gives approximately **9.62 weekly bps**, not `5/52` bps. Identify the reused benchmark file and hash explicitly; its existing specification can supply provenance.

- **P2 — Price/funding event alignment needs an explicit modelling statement.** [Lines 16–18](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:16) define half-open calendar weeks, while [lines 30–32](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:30) use preceding daily closes and funding in `(T,T+7d]`. This can be coherent as **entry after settlement at T and exit after settlement at T+7d**, using prior closes as price proxies. State that convention explicitly, including actual bar-close timestamps and delisting endpoints. Summed funding rates also fix an unchanged-notional approximation; disclose how that assumption relates to the price-return and turnover accounting. Excluding funding settled at T from the signal is safe; the completed preceding-day close is not itself future information under the stated event ordering.

- **P2 — Lag-collapse algebra is exact, but sample composition changes.** [Line 47](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:47) reproduces #105 ④ exactly: `|IC_lag1| ≤ 0.5|IC_0| AND t(IC_lag1)<2`. Keep the signed t inequality unchanged. However, lag IC uses fewer symbols and potentially fewer weeks than IC₀, so apparent collapse can include composition effects. Explicitly use the lag sample’s count in its t estimator and report both counts. A matched-sample comparison may be reported separately; it must not silently replace the specified decision statistic.

- **P2 — Null reproducibility and power disclosures need completion.** [Lines 45–46](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:45) correctly fix positive signed IC, average-rank ties, 1,000 within-week permutations, one RNG seed, linear p95, and **strict `>`** without reversal. Pin chronological week order, symbol order, RNG traversal, and explicit failure handling: undefined observed/permuted IC must not invite dropping weeks or retrying draws. Independent weekly shuffles explicitly break temporal dependence; disclose the exchangeability assumption and that the specified ordinary t estimator does not adjust serial dependence. [Line 53](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:53) correctly separates the power label from PASS and uses the required thresholds, spread units, ddof and effective-sample formula. Add the required tail/α/power disclosures for coefficients 2.80, 4.00 and 4.20, plus handling of undefined MDE.

The **upper-ceiling plan is sound on paper**: the manifest hash matches, all 38,664 unique archive keys have months ≤2026-06, and the final scheduled outcome ends June 29. The existing guard rejects reserved archive names and filters timestamps before value parsing. Nevertheless, filtering klines by `open_time` alone does not certify their outcome endpoints: the implementation must check close/exit/funding timestamps with `assert_within`, record actual read ranges and input hashes, and enforce the archive allow-list before downloading. No p2 Python implementation exists yet, so the static rule currently provides no implementation-specific assurance.

Thus Q1 is **no**; Q2 is **not established**; Q3 and Q4 are **yes for the declared conventions**; Q5 has **correct thresholds but deficient realised-turnover accounting**; Q6 is **correct with disclosure gaps**; Q7 has **a compliant ceiling design requiring implementation verification**.

VERDICT: FIX

## Codex PRE_r2 — 원문(verbatim · 최종 메시지)
Reviewed HEAD `d605b7b` read-only. No files changed or market data downloaded. **Not ready for START.** No P0 or BLOCK-USER finding.

- **R1 P1 — Entry eligibility: PARTIAL.** The future `open_time=T` requirement is removed, but whole-week invalid-record exclusions can still use holding-period information.
- **R1 P1 — Delisting/data gaps: PARTIAL.** Exit, cash-period and zero-bar formulas are specified; causal exits, archive failures and holding-period completeness remain unresolved.
- **R1 P1 — Realised turnover: PARTIAL.** Price drift, side changes, funding cash and liquidation amounts are pinned; early exits still inherit retrospective timing and imputed prices.
- **R1 P1 — First-settlement scope: RESOLVED.** Guarded first observation, left censoring, gap-based resets and the February 8 first scheduled holding week are explicit.
- **R1 P1 — Benchmark arithmetic: RESOLVED.** File/hash, annual-percent conversion, `7/365`, weekly averaging and missing-observation handling are pinned.
- **R1 P2 — Event alignment: RESOLVED.** After-settlement ordering, preceding-close proxies and fixed-entry-notional funding are disclosed.
- **R1 P2 — Lag sample composition: RESOLVED.** The lag sample supplies its own count; both samples and a reporting-only matched comparison are required.
- **R1 P2 — Null reproducibility/power: PARTIAL.** Traversal, exclusions, dependence assumptions and power disclosures are specified; aggregate undefined-statistic handling needs completion.

New findings:

- **P1 — Record cleaning can reintroduce future-conditioned eligibility.** [Line 25](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:25) makes the timestamp’s week ineligible for conflicting duplicates or nonfinite values. A bad record at `T+2d` therefore disqualifies an entry at `T`, conflicting with the pre-entry restriction at line 27. Restrict eligibility checks to required information available before entry. Freeze admitted names; handle later invalid records through a predetermined outcome-failure policy rather than removing positions retrospectively.

- **P1 — Early liquidation is chosen with hindsight.** [Line 42](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:42) selects the last holding-week bar only after establishing that the terminal bar is absent. At `X=d+1d`, subsequent absences through week-end are not yet known. With no holding-week bars, it backdates liquidation to `T` using information learned later. Avoiding information *after week-end* does not make these exits causal. Pin an observable exit trigger and price; unresolved archive gaps must not become zero-return trades. If retained as an imputation, it cannot establish executable exits or survivorship-free outcomes.

- **P1 — Funding completeness remains insufficient.** [Line 28](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:28) permits an eight-hour gap even for the hourly/four-hour funding regimes explicitly admitted at line 36. Seven missing hourly settlements can pass; the initial eight-hour allowance can also admit a missing boundary settlement. [Line 43](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:43) simply sums available holding-period records without a completeness test. Pin cadence-aware expected settlements, boundary checks and failure handling through `X`. Distinguish unavailable/corrupt archives from validated missing market records; neither silently implies zero funding.

- **P1 — The lag horizon has two incompatible definitions.** [Line 36](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:36) defines `s(t)` over `[T−7d,T)`. Consequently, `s(t−2)` covers `[T−21d,T−14d)`, while [line 62](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:62) checks `[T−14d,T−7d)`, which is `s(t−1)`. Implementers can obtain different collapse verdicts. Use the latter interval consistently for the required one-week delay; preserve the signed collapse inequality.

- **P2 — Restore explicit failure handling for undefined aggregate statistics.** [Lines 60–65](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:60) retain only the explicit `n_ic<3` failure rule, removing r1’s `sd=0` guard. Constant positive weekly ICs can produce `+inf`; constant negative lag ICs can produce `−inf` and satisfy the signed inequality numerically. The [protocol requires FAIL for undefined statistics/null distributions](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:46). State that rule locally for both t statistics and nonfinite observed/permutation aggregates, without additional dropping or retries.

**Turnover arithmetic is now implementable given valid prices and fixed exits.** An unchanged member with `q=2` and a 10% price increase requires `|0.50−0.55|=0.05` traded notional; full replacement of both legs at unchanged prices costs 40 bps. Early-exit and terminal-liquidation amounts are likewise explicit. The unresolved issue is the validity and observability of the exits feeding that accounting.

The manifest, benchmark and v4 hashes match. All 38,664 archive keys are unique and have months ≤2026-06; the final scheduled outcome ends June 29. The ceiling design remains compliant on paper. No p2 implementation exists yet, so loader enforcement and actual timestamp/read-range auditing remain unverified.

VERDICT: FIX

## Codex PRE_r3 — 원문(verbatim · 최종 메시지)
Reviewed HEAD `2ffa701` read-only. No files changed or data downloaded. **START remains blocked by specification fixes.** No P0 or BLOCK-USER finding.

Round-2 item status, one line each:

- **R1 entry eligibility — RESOLVED:** holding-period bad records no longer change entry eligibility.
- **R1 delisting/data gaps — PARTIAL:** causal price imputation is specified; funding-failure handling remains incomplete.
- **R1 realised turnover — PARTIAL:** ordinary arithmetic is pinned; a forced exit exactly at week-end creates a rollover ambiguity.
- **R1 first-settlement scope — RESOLVED:** guarded first observation, resets and first holding week remain explicit.
- **R1 benchmark arithmetic — RESOLVED:** conversion, averaging and missing-observation rules remain pinned.
- **R1 event alignment — RESOLVED:** settlement ordering and price/notional approximations remain disclosed.
- **R1 lag sample composition — RESOLVED:** separate counts and the matched reporting comparison remain required.
- **R1 null reproducibility/power — RESOLVED:** traversal, seed, dependence disclosures and aggregate failure guards are specified.
- **R2 record cleaning/eligibility — RESOLVED:** post-entry invalid records cannot retrospectively remove admitted names.
- **R2 hindsight liquidation — RESOLVED:** daily checks remove retrospective timing; stale-price imputation is a recorded screen limitation.
- **R2 funding completeness — PARTIAL:** shorter internal gaps are detected, but boundary omissions and missing-count construction remain unresolved.
- **R2 incompatible lag horizons — RESOLVED:** both definitions consistently use `S_1`.
- **R2 undefined aggregate statistics — RESOLVED:** zero variance, insufficient samples and nonfinite aggregates explicitly produce FAIL.

Remaining finding:

- **P1 — Funding boundary completeness still fails.** [Line 29](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:29) allows the first settlement one full cadence after the inclusive signal boundary. For an eight-hour schedule, removing the settlement at `T−7d` leaves every condition satisfied. Applying the same boundaries in [line 44](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:44) also accepts a missing settlement at the inclusive exit boundary `X`. Synthetic timestamp checks confirmed both cases pass. Pin expected settlement times, including phase and endpoint inclusion, and an explicit missing-count rule for empty and singleton holding series. This blocks START.

New findings:

- **P1 — Bad holding funding records have no deterministic numerical treatment.** [Line 25](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:25) marks conflicting duplicates and nonfinite values as bad, but [line 44](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:44) checks timestamp gaps and sums observed settlements without specifying which bad records enter that sum. Conflicting finite duplicates can therefore produce different `F_i` values. Explicitly treat invalid settlements as missing, count them, and pin the partial/empty-sum outcome policy. This blocks START.

- **P1 — Week-end forced liquidation can suppress reopening turnover.** A missing seventh daily bar forces liquidation at `X=T+7d` under [line 41](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:41). At the next rebalance, [line 51](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:51) uses `X=T` to identify carried positions. That timestamp also describes this forced liquidation. An unchanged selected name can consequently receive zero reopening turnover despite having been closed. Specify that every missing/bad-bar exit leaves zero carried notional, including at week-end, and charge its closure exactly once. This blocks START.

The early-exit disclosure in [line 42](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:42) is sufficient **as a limitation for this SCREEN**, with counts and exclusion sensitivity required. It is **not itself a P1 blocking START** and cannot support executable-exit or survivorship-free claims.

The manifest, benchmark and protocol hashes match. The 38,664 archive keys are unique and remain within the month ceiling. No p2 implementation exists yet; enforcement remains unverified.

VERDICT: FIX

## Codex PRE_r4 — 원문(verbatim · 최종 메시지)
Reviewed r4 at HEAD `c5eaa92` read-only. No files changed or data downloaded. **One new P1 still blocks START.**

- **R3 funding boundary completeness — RESOLVED:** [line 29](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:29) includes `T−7d`; line 44 includes `X` and defines missing counts for empty/singleton observations.
- **R3 bad holding funding records — RESOLVED:** [line 44](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:44) excludes bad records, counts missing slots, and pins partial/all-missing sums.
- **R3 week-end forced-liquidation turnover — RESOLVED:** [lines 51–53](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:51) require zero carried notional, one closure charge, and a separate reopening charge.
- **R1 delisting/data gaps — PARTIAL:** causal price substitution and funding-failure treatment are specified; the new holding-grid collision case below remains undefined.
- **R1 realised turnover — RESOLVED:** forced exits at week-end now have explicit closure and rollover treatment.

Synthetic checks passed for an eight-hour grid, `X=T+7d`, and valid settlement rates of `0.001`:

| Case | r4 result |
|---|---|
| Missing settlement at `T−7d` | Signal incomplete; entry rejected |
| Missing settlement at `X` | 1 missing of 21 expected; `F_i=0.020`, flagged |
| Empty observed holding series | 21 missing; `F_i=0`, all-missing flag |
| Singleton observed holding series | 20 missing; `F_i=0.001`, flagged |

A bad record at `X` produces the same result as a missing settlement. A forced week-end exit with `q=2` and price ratio `1.1` charges closure notional `0.55` once, carries `0`, and charges reopening notional `0.5`.

**NEW P1 — Multiple valid records within one holding-grid tolerance have no deterministic treatment.** [Line 44](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:44) specifies one valid match and no valid match, but omits multiple matches. Two finite records at `X−30s` and `X`, with rates `0.002` and `0.001`, survive the same-timestamp cleaning rule and both match the expected settlement at `X`. Neither is outside that slot’s ±60-second tolerance. With the other 20 settlements each `0.001`, selecting either candidate yields `F_i=0.022` or `0.021`; summing both yields `0.023`. The synthetic check confirmed this collision.

Pin a deterministic multiple-match rule, its missing-count treatment, and whether rejected candidates can enter the off-grid sum. This blocks START because it changes funding returns and potentially the verdict.

No new P0, P2, or BLOCK-USER finding. Manifest, benchmark and protocol hashes match; all 38,664 archive keys are unique and within the month ceiling. No p2 implementation exists, so enforcement remains unverified.

VERDICT: FIX

## Codex PRE_r5 — 원문(verbatim · 최종 메시지)
Reviewed r5 at HEAD `a82369d` read-only. No files changed or data downloaded.

- **R4 P1, multiple matches — RESOLVED.** [Line 44](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:44) deterministically excludes every collision candidate, counts one missing slot, flags funding deficiency, reports the collision, and prohibits off-grid reuse.
- **R1 delisting/data gaps — RESOLVED at specification level.** Causal exits, price substitution, unusable files, missing/bad funding, and collisions now have defined treatment. The disclosed stale-price limitation remains: this does not establish executable delisting exits or complete removal of survivorship bias.

The independent, in-memory synthetic rerun passed:

| Eight-hour grid; 21 expected settlements | `F_i` | Missing | Collisions |
|---|---:|---:|---:|
| Original collision: `X−30s = 0.002`, `X = 0.001`; other 20 each `0.001` | 0.020 | 1 | 1 |
| Missing or bad settlement at `X` | 0.020 | 1 | 0 |
| Empty holding series | 0 | 21 | 0 |
| Singleton holding series | 0.001 | 20 | 0 |

Reversing record order leaves the collision result unchanged. Collision handling also passed for all four permitted cadences. Signal rejection, off-grid accounting, and forced week-end turnover regressions passed.

**NEW P2 — Two allowlist keys are malformed.** [Row 19600](/home/cms/project/BTC_Futures_E2E/research/screens/p2/data/archive_listing_le_2026-06.tsv:19600) concatenates an `AAVEUSD…` prefix with the ACEUSDT December 2023 key; [row 37629](/home/cms/project/BTC_Futures_E2E/research/screens/p2/data/archive_listing_le_2026-06.tsv:37629) concatenates an `XEMUSD…` prefix with the YALAUSDT August 2025 key. Correct the listing, validate complete key syntax, and refresh the [spec’s manifest hash](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:11).

This is nonblocking for the defined calculations: the earliest possible entry bars under the 35-day age requirement are January 7, 2024 for ACE and September 7, 2025 for YALA—both after the affected months.

No new P0, P1, or BLOCK-USER finding. Protocol, benchmark, and listing hashes match. All 38,664 rows have unique keys; 38,662 pass archive-key syntax validation. No START row or p2 implementation exists, so implementation enforcement remains unverified.

VERDICT: MERGE

## Codex PRE_r6 — 원문(verbatim · 최종 메시지)
Reviewed r6 at HEAD `d3425a2` read-only. No files changed or data downloaded.

- **Round-5 P2 — RESOLVED.** All **38,665 keys** pass full-string archive syntax validation, including matching directory/filename symbols and valid calendar months. All keys are unique; every month is **≤ 2026-06** (range: 2020-01–2026-06). Counts match: **18,935 funding + 19,730 daily-bar files**, covering **788 symbols**. SHA256 matches the [spec manifest](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:11): `32cfccee8f366627ae707b8105d2b52ddeac18a36dcbf355634c5ebee9d21d45`. The diff removes exactly two malformed rows and restores exactly the three stated keys, each once.

- **Non-ASCII exclusion — acceptable pre-data rule.** The [rule](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:12) is deterministic, name-based, disclosed, and committed before START. The directory inventory contains exactly five USDT names failing `[A-Z0-9]+USDT`; none appeared in the r5 manifest either. There is no evidence here of selection based on observed funding or returns. It narrows the target population to ASCII-named USDT perpetuals; conclusions should retain that scope. The rule must remain fixed after data access.

**NEW findings: none.** Protocol and benchmark hashes match. No START row or p2 implementation exists, so downloader and calculation enforcement remain unverified.

VERDICT: MERGE

## 코드 대 스펙 검토(START 전) — Codex r1 FIX(P1 3 · P2 4) → r2 FIX(P2 3 · 스펙 r7 칸 단위 매칭 수용) → r3 FIX(P2 2) → **r4 MERGE**
입장: 전부 동의 — 고침 6a6bd6b · 38d6d2d · 03095f2(가드 `zip_has_header(names=)`는 좁히기만 · W1 가드 변경으로 검토됨).

### 코드 검토 r1 — 원문(verbatim)
Reviewed HEAD `98fa770` against r6. No downloads or file changes. **No P0 findings; three P1 and four P2 findings.**

1. **P1 — Holding funding violates `(T, X]` and the off-grid rule.** [compute.py:106](/home/cms/project/BTC_Futures_E2E/research/screens/p2/compute.py:106) admits records through `X+60s`; its off-grid classification also includes the excluded `T` grid point. Synthetic cases confirm that `X+30s` funding is included, while `T+30s` funding is silently omitted. This changes funding returns, IC, spreads and missing-settlement counts. Restrict actual records to `(T, X]` and classify against `E_hold`.

2. **P1 — Unusable bar months do not disqualify the signal week.** [compute.py:164](/home/cms/project/BTC_Futures_E2E/research/screens/p2/compute.py:164) checks only `unusable_funding`; `unusable_bars` is never consulted. A February bar archive marked unusable still permits entry on March 4 when the March 3 entry bar exists. Under §3, the signal week’s intersection with February must make that symbol ineligible. This changes eligible counts, deciles and statistics.

3. **P1 — ZIP-opening failures abort instead of producing an unusable month.** [loader.py:78](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:78) propagates opening/reading failures. R6 §3 requires these archives to become unusable and follow eligibility or outcome missing-data rules. Handle archive failures per file, discard any partially collected rows, and record the month as unusable. Preserve the required exceptions for malformed timestamps and reserved archives.

4. **P2 — Failed-fetch recovery can consume stale ZIP contents.** [fetch.py:61](/home/cms/project/BTC_Futures_E2E/research/screens/p2_fetch/fetch.py:61) writes failure markers without deleting an existing ZIP; [loader.py:76](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:76) subsequently reads ZIPs even when their markers exist. After an interrupted fetch and failed retry, stale funding or prices can enter holding outcomes instead of becoming missing. Delete failed ZIPs and make markers authoritative.

5. **P2 — Age/reset history adds an unstated valid-only filter.** [compute.py:129](/home/cms/project/BTC_Futures_E2E/research/screens/p2/compute.py:129) removes bad records before determining first observation and 30-day gaps. R6 defines first observation as the first readable funding settlement, separately restricting bad-record eligibility to `[T−8d,T)`. With a bad observation at `T−50d` and valid observations starting at `T−20d`, the exactly-30-day gap should not reset age; the code instead rejects the symbol as young.

6. **P2 — `assert_within` coverage is incomplete.** The sole calculation check, [run.py:74](/home/cms/project/BTC_Futures_E2E/research/screens/p2/run.py:74), checks a lag-window boundary and exit times, after outcomes have been calculated. Actual signal settlements, entry times, holding settlements and bar-close times never receive the assertions required by §1.

7. **P2 — Required funding diagnostics disappear from the result.** [compute.py:284](/home/cms/project/BTC_Futures_E2E/research/screens/p2/compute.py:284) drops `HoldFunding.offgrid`, and the result does not distinguish wholly missing funding from partial deficits. Preserve and report off-grid counts and the §4-3 “all missing” flag.

**Verification:** 39 selected existing tests passed. Independent synthetic checks confirmed exact shuffle RNG ordering, tie ordering, realised-notional turnover, skipped-week/final liquidation handling and constant-IC FAIL. The allow-list hash matches; scheduling contains exactly 281 weeks, **2021-02-08 through 2026-06-22**.

No further discrepancies found in cadence completeness, causal daily exits, S₀/S₁ bounds, spread/decomposition, lag thresholds, cost clause, `>250 bps` override, power formulas, DTB3 conversion or static-rule compliance. The disclosed manifest-location deviation is accepted.

VERDICT: FIX

### 코드 검토_r2 — 원문(verbatim)
Reviewed HEAD `6a6bd6b` against r7. No downloads or file changes. **Three P2 issues remain; no P0/P1 issues remain.**

The slot clarification is **acceptable before START**: it changes r6’s literal timestamp treatment, but r7 fixes the tolerance, boundary ownership and off-grid rule explicitly. It leaves no choice based on observed results. The code matches those rules.

| Round-1 finding | Status | Assessment |
|---|---|---|
| P1-1: Holding funding boundaries | **RESOLVED** | Matches r7, including inclusive ±60-second slots and strict off-grid boundaries. |
| P1-2: Unusable bar months | **RESOLVED** | Eligibility checks both funding and bar months across `[T−8d,T)`. |
| P1-3: ZIP-opening failures | **PARTIAL** | Opening/read failures mark the month unusable and discard partial rows. Exception preservation has the new edge case below. |
| P2-4: Stale ZIP after failed fetch | **RESOLVED** | Existing ZIPs are deleted before fetching; markers prevent stale contents from being read. Successful recovery has a separate regression below. |
| P2-5: Valid-only age history | **RESOLVED** | Bad funding records now count toward first observation and gap resets. |
| P2-6: Assertion coverage | **PARTIAL** | Sorted-series extrema cover raw funding/open timestamps. Calculation checks still occur after use, and derived bar-close timestamps lack assertions. |
| P2-7: Funding diagnostics | **RESOLVED** | Off-grid and wholly missing counts propagate into the result JSON. |

**Remaining round-1 P2 — Assertions still occur after calculation.** [run.py:74](/home/cms/project/BTC_Futures_E2E/research/screens/p2/run.py:74) runs after eligibility, outcomes and week construction. An instrumented synthetic run confirmed this ordering. [loader.py:105](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:105) checks raw-series extrema, but derived daily close times remain unchecked. Move calculation-boundary assertions before use and include the close timestamps required by §1.

**NEW P2 — Successful retry leaves an authoritative failure marker.** [fetch.py:69](/home/cms/project/BTC_Futures_E2E/research/screens/p2_fetch/fetch.py:69) writes the verified ZIP and returns `ok` without removing an existing `.unusable` marker. After an interrupted fetch containing an earlier failure, a successful retry therefore produces an `ok` manifest entry while [loader.py:83](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:83) discards that month. This changes eligibility and missing outcomes. Remove the marker after successfully writing the verified ZIP. Reproduced entirely in memory.

**NEW P2 — Markers bypass the reserved-name exception.** [loader.py:79](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:79) accepts marker names, then skips marked ZIPs before checking reserved archive names. A `2026-07.zip` raises `ReserveError` alone but becomes silently “unusable” when its marker exists, contrary to r7 §3. Validate archive names before applying marker skips, including marker-only entries. No reserved contents were read.

**Verification:** 43 read-only selected tests passed. In-memory checks additionally verified corrupt ZIP handling, partial-read rollback, malformed-timestamp exceptions, exact slot boundaries, result diagnostics and both new regressions. The allow-list hash matches; the working tree remains clean.

VERDICT: FIX

### 코드 검토_r3 — 원문(verbatim)
Reviewed HEAD `38d6d2d` against r7, before START. **All three round-2 P2 issues are resolved. Two new P2 findings remain; no P0/P1 findings.**

| Round-2 item | Status | Assessment |
|---|---|---|
| Assertions after calculation; unchecked daily closes | **RESOLVED** | [compute.py:165](/home/cms/project/BTC_Futures_E2E/research/screens/p2/compute.py:165) and [compute.py:199](/home/cms/project/BTC_Futures_E2E/research/screens/p2/compute.py:199) check boundaries before use, including entry and holding-bar close timestamps. |
| Successful retry retains failure marker | **RESOLVED** | [fetch.py:70](/home/cms/project/BTC_Futures_E2E/research/screens/p2_fetch/fetch.py:70) removes the marker after writing the verified ZIP. |
| Markers bypass reserved-name exception | **RESOLVED** | [loader.py:80](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:80) checks marker and ZIP names before skips, including marker-only entries. |

Previously resolved round-1 items remain resolved. ZIP-opening failures now fully preserve the reserved-name exception.

**NEW P2 — Malformed first-row timestamps can be silently discarded.** [window.py:162](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:162) accepts any alphabetic first timestamp cell as a header. In-memory ZIPs beginning with `NaN,8,0.5`, `NULL,8,0.5`, or `inf,8,0.5` loaded subsequent records successfully without raising or marking the month unusable. The same malformed timestamp on a later row raises `ReserveError`. This violates r7 §1/§3’s malformed-timestamp exception rule and can silently alter completeness or age history. Recognize supported headers explicitly; reject other noninteger first-row timestamps.

**NEW P2 — Result JSON omits the required input inventory and hashes.** [run.py:149](/home/cms/project/BTC_Futures_E2E/research/screens/p2/run.py:149) supplies only a note referring to `fetch_manifest.tsv`; the runner never loads or embeds that inventory. A captured four-week synthetic result confirmed there are no input-file or SHA256 fields. [Spec §1](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_spec.md:15) explicitly requires the file/SHA256 inventory inside the result JSON. Include it before exclusive result creation so the result binds to its inputs.

**Verification:** 43 selected tests passed. Additional in-memory checks verified all three fixes, corrupt-ZIP handling, partial-read rollback and both new findings. The allow-list hash matches. No downloads or file changes; working tree clean.

VERDICT: FIX

### 코드 검토_r4 — 원문(verbatim)
Reviewed HEAD `03095f2` against r7, before START.

| Round-3 finding | Status | Assessment |
|---|---|---|
| Malformed first-row timestamps silently discarded | **RESOLVED** | [loader.py:91](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:91) supplies the four supported header names. `NaN`, `NULL`, `inf`, and other unknown first cells now propagate `ReserveError`. |
| Result JSON omits input inventory and hashes | **RESOLVED** | [loader.py:124](/home/cms/project/BTC_Futures_E2E/research/screens/p2/loader.py:124) reads the CSV through `bounded_csv_file`; [run.py:150](/home/cms/project/BTC_Futures_E2E/research/screens/p2/run.py:150) embeds every inventory key, status, and SHA256 before exclusive result creation. |

The three earlier fixes remain **RESOLVED**: assertions precede calculation, successful retries clear failure markers, and reserved marker/ZIP names stop before skips.

**W1 guard review:** [window.py:151](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:151)’s optional `names=` only narrows header acceptance. Default behavior, timestamp filtering, and outer/member reserved-name checks remain intact.

**NEW findings:** None.

**Verification:** 52 selected tests passed; 18 tests requiring filesystem writes were deselected. In-memory checks covered loader failures and rollback, header compatibility, reserved boundaries, retry cleanup, all **37,649 downloadable manifest keys**, and exact inventory embedding in a four-week synthetic result. Allow-list SHA256 matches. No downloads or file changes; working tree clean.

VERDICT: MERGE
