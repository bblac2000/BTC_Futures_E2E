# W5 — 헌법 v1.6 개정안 · Codex 독립 검토 회전 원문

- 날짜: 2026-10-14 · 대상: 계획(PRE r1~r3) → 문서 `docs/proposals/constitution_v1.6_amendment.md`(검토 r1~r2)
- 회전 표: PRE r1 **BLOCK-USER**(현물 헤지 다리) → 사용자 결정 (가) → PRE r2 **BLOCK-USER**(청산 안전 — 잔여 델타 가드가 현물 상태에서 선물 청산으로) → 사용자 대체안 (나) 적용 → PRE r3 FIX-PLAN-FIRST(P1만) → 문서 작성 → 문서 r1 FIX(P0 1 · P1 2) → **문서 r2 MERGE**(마지막 연속 MERGE 행).
- 사용자 질문 Q1("청산·SL·TP·트레일링·킬스위치 경로에 닿는가 — NO여야 한다")에 대한 Codex의 마지막 답: **YES** — 첫 체결부터 SL 감시를 켜는 것, 청산 시 진입 의도 무효화와 경합 체결 정리, P1의 SL 승계 명시가 그 경로에 닿는다. 다만 "청산 실행 자체는 즉시 MARKET reduceOnly로 남는다"고 판단했고 BLOCK은 내지 않았다 — 이 답은 사용자 판단 사항으로 보고한다.

## PRE r1 — 프롬프트 · 응답
```
READ-ONLY PRE-REVIEW (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E. Item W5: a DRAFT amendment package for the shared trading constitution (v1.6). It touches the order path, so it needs independent review before it is written and again after. The current constitution copy is .claude/skills/quant-bot-constitution/SKILL.md and references/*.md (read-only here; the master is maintained elsewhere). Relevant repo code: exchange/orders.py, paper/sender.py (LiveSender, OrderOutcomeUnknown), exchange/gate.py. The user fixed the six items and said "exactly these items and nothing else".
PLAN r2 (verbatim):
## W5 plan r2 — docs/proposals/constitution_v1.6_amendment.md (draft only; no merge; no skill-copy edits; no code)
Header (one line): restates D5 — zero live or paper orders of any kind until v1.6 is merged; deployment only via the master zip on claude.ai. Then EXACTLY six numbered items, nothing else.

1. Spot hedge leg. Permitted only as a simultaneous 1:1 delta hedge of a BTCUSDT perp position in the same account; pairs BTC/FDUSD and BTC/USDT only; naked spot forbidden; sizing derives from the perp leg.
 (a) Leg order and transient, pre-fixed: perp leg first (it carries the exchange-rule gates), then spot leg; if the spot leg fails or times out → the perp leg is closed MARKET reduceOnly immediately; if a spot fill exists without a perp position (any cause) → spot sold MARKET immediately. Both unwinds are bounded (one attempt each, then kill-switch + alert); unwinds are time-critical (item 2).
 (b) Margin isolation: spot BTC sits in the spot wallet and does not fund perp margin; the perp leg's liquidation distance is computed from futures-wallet collateral only; perp leg leverage is capped (config, at most the constitution's range) and a top-up / reduce rule fires before the liquidation gate is breached.
 (c) Quantity matching: spot quantity is rounded to the perp quantity (futures step 0.001 and spot step from the runtime exchangeInfo — values from runtime, not literals).
 (d) Reconcile includes spot balances; tolerance |spot BTC − perp BTC| ≤ one futures step; residual dust rule (reported, never traded alone).
 (e) Depeg monitor: source = FDUSDUSDT spot ticker (and USDT pair where relevant); a configurable threshold blocks NEW entries only.
2. Spot maker orders. Permitted for the hedge leg only; maximum resting time then taker fallback; every placement, fill, timeout and fallback logged; forbidden for any time-critical order, defined as any exit, unwind, kill-switch or margin action. Resting orders require order-update handling (user data stream or polling) — requirement named, not designed here.
3. Perp entry via timeInForce=GTX (post-only), ENTRY ONLY. Three states, each with a fixed outcome:
 (i) refused on placement (would cross; error −5022, nothing placed) → re-quote at the new same-side best, counted toward N;
 (ii) resting and not filled by the per-attempt timeout → cancel; the cancel/fill race is resolved by querying order status (the existing OrderOutcomeUnknown idiom — never assume);
 (iii) partially filled before cancel → the position is the filled quantity; per config either complete the remainder with MARKET or keep the partial; in both cases sizing checks, MIN_NOTIONAL and the liquidation-distance gate are re-run on the actual quantity, and the SL monitor arms only after fill confirmation. "Skip" is valid only when nothing filled.
 Bounds: at most N re-quotes AND a total time cap per entry intent; after either bound, per config MARKET fallback (re-running normalisation, MIN_NOTIONAL and the liquidation gate at the fallback price) or skip.
 Changed vs unchanged clause list: changed — SKILL.md §1-1 "진입·청산 전부 type=MARKET" becomes "청산은 전부 MARKET; 진입은 MARKET 또는 GTX(이 항목의 규칙)". Unchanged — all exits, SL, TP, trailing, kill-switch and unwinds are MARKET reduceOnly; side BUY/SELL only; one-way mode; no server-side STOP/TP; GTX only with the entry intent.
4. Errata: forceOrder stream wording. Two official texts conflict in the official docs dump (https://developers.binance.com/en/docs/llms-full.txt, last-modified 2026-10-13): the USDⓈ-M change-log entry dated 2026-04-10 (dump line 52659-52662: "Updated description: changed \"only the latest one liquidation order\" to \"only the largest one liquidation order\" within 1000ms.") and the current stream reference text (dump lines 202637 and 202753, carrying "After CM migration" annotations: "For each symbol，only the latest one liquidation order within 1000ms will be pushed as the snapshot."); no reversal entry exists in the change-log. v1.5 adopted "largest" from the change-log. The conclusion (forceOrder is not usable as a liquidation-volume measure) is unchanged under either wording. Which wording becomes the master text is a USER DECISION; the draft quotes both and does not settle it.
5. Carry-over (registry #86–#88, user-approved): pre-anchor power gate stated symbolically with the repo value — θ = 10 bps, "projected MDE > 2θ (= 20 bps) → do not anchor"; P1 SL-inheritance must be declared in the pre-registration as the definition of the null; sizing-feasibility calibration (the sl_dist × price band where the minimum quantity cannot be bought at E_ref and the risk budget, and the share of candidates in it).
6. Family-specific benchmarks as a protocol clause (D6): carry → 3-month US T-bill (FRED DTB3, point-in-time, converted to the holding period); execution → immediate-taker execution price; directional → vol-targeted long-only BTC. Benchmarks are reported, not pass conditions.
Not in the doc (go to the Codex packet / briefing): repo impact — CLAUDE.md hard rule "MARKET only", exchange/orders.py validation, tests, the spot transport under registry #8's pin.

THE USER'S QUESTIONS (answer each in one line, then justify in findings):
Q1 Does any clause touch exit, SL, TP, trailing or kill-switch paths? (must be NO)
Q2 Does the spot leg have any path to be naked?
Q3 Does GTX rejection handling create an unbounded re-quote loop?
Q4 Is the forceOrder erratum exact to the official text? (verify against https://developers.binance.com/en/docs/llms-full.txt if you can fetch it; otherwise say you could not)
Also: anything in the plan that would make the merged constitution unsafe, ambiguous, or inconsistent with the unchanged invariants.
OUTPUT: numbered findings tagged P0 (must fix before the doc is written) / P1 / P2 / BLOCK-USER (needs a user decision between safety and function); one line per Q1-Q4; end with exactly one line: VERDICT: MERGE or VERDICT: FIX-PLAN-FIRST.
```
No files edited.

Q1: YES — items 1 and 3 touch unwind, kill-switch, margin-reduction and SL-arming paths; the required NO is not satisfied.
Q2: YES — late spot fills, partial perp reductions and failed spot unwinds can leave unhedged spot exposure.
Q3: NO — re-quotes count toward N, and the entry intent also has a total time cap.
Q4: NOT FULLY VERIFIED — I could not fetch the official dump; the accessible official changelog confirms its quoted amendment.

1. **[BLOCK-USER] Q1 conflicts with enabling the hedge safely.** Preserving existing perp MARKET/reduceOnly execution is achievable, but hedge cleanup must respond to existing exits, partial reductions and liquidation. Choose between authorizing that narrowly scoped integration or deferring spot execution. A literal “touches no exit/SL/TP/kill-switch paths” certification would be inaccurate.

2. **[P0] Items 1(a)/2 leave the spot cancel/fill race unresolved.** A maker order can time out, trigger perp closure, then fill afterward. Before taker fallback, require confirmed terminal status and use only the confirmed unfilled remainder. Unknown placement/cancellation outcomes must block replacement entries; pending-order and balance monitoring must continue after kill-switch activation. Naming order-update handling alone does not establish these outcomes.

3. **[P0] Item 1 covers perp disappearance but not partial reduction.** For example, reducing a matched 0.010 BTC perp to 0.005 leaves 0.005 BTC excess spot. Reconciliation currently specifies a tolerance without a corrective outcome. Define time-critical MARKET disposal of excess hedge inventory after any confirmed perp reduction, including partial TP and ADL, while preserving the existing perp exit policy.

4. **[P0] Items 1/3 apply futures exit semantics too broadly.** “All … unwinds are MARKET reduceOnly” conflicts with the new spot unwind: Binance’s spot order interface has no `reduceOnly` parameter. Scope that invariant explicitly to perp orders; spot disposal must be MARKET SELL bounded by actual hedge inventory. Spot MARKET orders can also face notional filters, so “sell immediately” needs an explicit unsellable-dust exception consistent with item 1(d). [Spot order interface](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/trade), [spot filters](https://developers.binance.com/en/docs/products/spot/filters).

5. **[P0] Item 1 needs explicit direction and quantity semantics.** Unborrowed long spot hedges a **short** perp. Define matching against confirmed fills and net BTC inventory after fees, using both venues’ runtime filters. The reconciliation expression must use signed net delta, or explicitly define “perp BTC” as the absolute short quantity; the repository’s `PositionRisk.amt` is signed. One-step tolerance must be a dust allowance, not permission for deliberate unmatched exposure. [Position type](/home/cms/project/BTC_Futures_E2E/paper/types.py:48).

6. **[P0] Item 1(b) does not precisely preserve isolated-margin safety.** “Futures-wallet collateral” could include free funds unavailable to the isolated position. Specify collateral actually allocated to that position, retaining ISOLATED and the existing leverage, risk and margin caps. Pre-fix the top-up/reduce trigger and the outcome when top-up fails or would breach a cap. Any perp reduction also requires item 1’s spot adjustment. [Startup isolation gate](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:214), [constitution sizing constraints](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/SKILL.md:77).

7. **[P0] Item 3 bounds re-quotes but leaves unknown outcomes insufficiently specified.** The three states omit placement transport failure. Querying status also does not resolve a race if the result remains nonterminal or unavailable. Require confirmed terminal status before another placement or MARKET fallback, including at the total deadline; unknown must never become “skip.” The existing `OrderOutcomeUnknown` idiom blocks entries—it is not an existing LIMIT cancellation/status implementation. Explicit −5022 handling is correct. [LiveSender](/home/cms/project/BTC_Futures_E2E/paper/sender.py:149), [official error definition](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/error-code#-5022-gtx_order_reject).

8. **[P0] Item 3 must fix the partial-fill safety outcome.** Require SL monitoring from the **first confirmed nonzero fill**, without waiting for cancellation or remainder completion. State that a failed post-fill liquidation gate triggers the existing immediate MARKET reduceOnly closure; “keep partial” cannot override it. Validate any new MARKET remainder separately, and never enlarge existing exposure merely to satisfy MIN_NOTIONAL. [Existing post-fill failure action](/home/cms/project/BTC_Futures_E2E/paper/engine.py:521).

9. **[P1] The master clause-change mapping is incomplete.** Item 3 names only SKILL.md §1-1, while the references still declare MARKET-only execution and taker-only paper fills. Item 6 also needs to distinguish its report-only family benchmarks from the existing P1 pass gate and the benchmark table labelled “final gate.” Resolve those references within the same six items. Item 5 should retain #88’s prospective-only application and explicit declaration of **whether** P1 inherits SL, with no default. Its θ = 10 / 2θ = 20 correction is accurate.

10. **[P2] Item 4 is only partially corroborated independently.** The accessible changelog reproduces the stated latest-to-largest amendment under 2026-04-10. I could not verify the dump’s line numbers, Last-Modified date, stream quotations, migration annotations or absence of a reversal. Preserve that evidence limitation and the unresolved master wording decision; the draft should not settle it. [Official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10).

VERDICT: FIX-PLAN-FIRST


## PRE r2 — 프롬프트 · 응답
```
READ-ONLY PRE-REVIEW ROUND 2 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E. Item W5: v1.6 amendment draft plan. Your round-1 output (BLOCK-USER + P0s 2-8, P1 9, P2 10) is below verbatim; the user has decided the BLOCK as option (a) with a one-directional coupling. Plan r3 follows verbatim. TASK: for round-1 items 1-10 say RESOLVED / PARTIAL / OPEN (one line each). Then answer: does (a) as specified still touch exit safety? If yes, BLOCK-USER with the specific reason (the user's fallback is (b): drop clauses 1-2). Re-answer Q1-Q4 in one line each (Q1 exit/SL/TP/trailing/kill touched? Q2 naked-spot path? Q3 unbounded re-quote loop? Q4 erratum faithful to the sources?). List NEW findings P0/P1/P2/BLOCK-USER. End with exactly one line: VERDICT: MERGE or VERDICT: FIX-PLAN-FIRST or VERDICT: BLOCK-USER.

## W5 plan r3 — docs/proposals/constitution_v1.6_amendment.md (draft only; no merge; no skill-copy edits; no code)
User decision 2026-10-14 (registry #100) on your round-1 BLOCK: option (a) — narrow, ONE-DIRECTIONAL coupling. If you still BLOCK on (a) for a reason that touches exit safety, the fallback is (b): clauses 1–2 are removed from v1.6.
Header: zero live or paper orders of any kind until v1.6 is merged; deployment only via the master zip. Then exactly six items.

1. Spot hedge leg (long spot BTC hedging a SHORT BTCUSDT perp, same account; pairs BTC/FDUSD, BTC/USDT; naked spot forbidden; sizing from the perp leg).
 1.1 One-directional dependency: the spot leg SUBSCRIBES to perp position events (entry fill, partial reduce incl. partial TP and ADL, full exit, liquidation, kill-switch close) and reacts AFTER the fact. The perp exit path (MARKET reduceOnly, SL, TP, trailing, kill-switch) never waits for, queries, or is modified by spot state. No code path from spot into perp exit.
 1.2 Entry order: perp entry first; spot hedge only after the perp fill is CONFIRMED (terminal order status), for the confirmed filled quantity. If the spot hedge is not confirmed within its bound → the spot leg's own unwind (1.4) and the residual guard (1.5) handle it; the perp leg is left to its normal exit policy (the guard may close a perp residual only through the existing MARKET reduceOnly path, as an added kill-switch trigger).
 1.3 Quantity and direction: target spot inventory = |perp short quantity| (signed perp amt < 0); matching uses confirmed fills and NET BTC inventory after fees, under both venues' runtime filters (no literals); spot quantity rounds to the perp quantity; the one-futures-step tolerance is a dust allowance, never deliberate exposure.
 1.4 Spot unwind on any confirmed perp reduction (incl. partial and liquidation): sell the EXCESS spot inventory with MARKET on the same pair by default (safety over fee); optional maker-with-short-timeout then MARKET, config flag, default OFF. Spot orders have no reduceOnly: the sell quantity is bounded by the actual hedge inventory. Before any replacement or fallback order, the previous spot order's terminal status must be confirmed; an unknown outcome blocks new entries and keeps monitoring running (also after kill-switch). Unsellable dust below spot filters is reported, never traded alone.
 1.5 Residual-delta guard (addition to the kill-switch set, not a change to existing exits): every reconcile cycle computes |spot BTC − |perp short|| × mark; if it exceeds a configured threshold for longer than a configured time → close the residual at MARKET (spot excess: spot MARKET sell; perp excess: existing MARKET reduceOnly) and alert.
 1.6 Margin isolation: spot BTC does not fund perp margin; the perp leg keeps ISOLATED with the existing leverage, risk and margin caps; liquidation distance uses the collateral actually allocated to the isolated position; a pre-fixed top-up/reduce trigger before the liquidation gate is breached; if a top-up fails or would breach a cap → reduce via the existing MARKET reduceOnly path (then 1.4 follows).
 1.7 Depeg monitor: source FDUSDUSDT spot ticker (and the USDT pair where relevant); a configured threshold blocks NEW entries only.
 1.8 Cost model consequence: forced-exit episodes pay spot taker on exit (P1 cost scenario B).
2. Spot maker orders: hedge-leg ENTRY only; maximum resting time then taker fallback; placement, fill, timeout, fallback logged; order-update handling required (user data stream or polling — named, not designed); forbidden for any time-critical order = any exit, unwind, residual-guard close, kill or margin action.
3. Perp entry via timeInForce=GTX (post-only), ENTRY ONLY. States: (i) refused on placement (−5022, nothing placed) → re-quote, counts toward N; (ii) transport failure / unknown outcome → status must be CONFIRMED terminal before any further placement or fallback; unknown never becomes skip; unresolved → OrderOutcomeUnknown blocks entries (existing idiom) while monitoring continues; (iii) resting and unfilled at the per-attempt timeout → cancel, then confirm terminal status; (iv) partial fill → the SL monitor arms from the FIRST confirmed nonzero fill; sizing, MIN_NOTIONAL and the liquidation-distance gate run on the actual quantity; a failed post-fill liquidation gate triggers the existing immediate MARKET reduceOnly close; a MARKET remainder (config) is validated separately and never enlarges exposure just to satisfy MIN_NOTIONAL; "skip" only when nothing filled. Bounds: at most N re-quotes AND a total time cap per entry intent; after either → MARKET fallback (re-running normalisation, MIN_NOTIONAL, liquidation gate at the fallback price) or skip, per config, only after terminal status is confirmed.
 Changed vs unchanged clauses: changed — SKILL.md §1-1 "진입·청산 전부 type=MARKET" → "perp exits all MARKET reduceOnly; perp entries MARKET or GTX under item 3"; the same change in references/exchange-rules.md (order policy) and references/strategy-modules.md where they state MARKET-only or taker-only paper fills (paper fill model for GTX entries follows the measured M-1 audit, not touch = fill). Unchanged — every PERP exit, SL, TP, trailing, kill-switch and perp unwind is MARKET reduceOnly; side BUY/SELL; one-way; ISOLATED; no server-side STOP/TP; GTX only with an entry intent. reduceOnly invariants are scoped to perp orders; spot disposal is MARKET SELL bounded by inventory (item 1.4).
4. forceOrder wording — conflict recorded, not chosen (user text): "Official change log (2026-04-10) states the per-symbol 1000 ms snapshot changed from 'latest' to 'largest'; the stream reference page as read on 2026-10-14 still says 'latest'. Status [DOC-CONFLICT], unverifiable from the stream itself (only one order is ever pushed). Operational conclusion unchanged: not a liquidation-volume measure; treat each push as one order of unknown rank within its second." Both source sentences quoted verbatim with URLs (change-log page https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10; stream reference sentence as found in https://developers.binance.com/en/docs/llms-full.txt read 2026-10-14, last-modified 2026-10-13), with the evidence limitation that the reference block's own page URL is not recoverable from the dump.
5. Carry-over (#86–#88): pre-anchor power gate = projected N-corrected MDE ≤ 20 bps (θ = 10 bps is the net-edge threshold; MDE > 2θ = 20 → underpowered); declared — never defaulted — whether P1 inherits the SL (prospective only, no retroactive use); sizing-feasibility calibration.
6. Family-specific benchmarks (carry → DTB3 point-in-time over the holding period; execution → immediate-taker executable price; directional → vol-targeted long-only BTC) — REPORTED comparisons; they do not replace the existing P1 random-timing benchmark gate or the pass rules; the reference table that labels a benchmark "final gate" is reconciled to say which gate is which.

YOUR ROUND-1 OUTPUT:
No files edited.

Q1: YES — items 1 and 3 touch unwind, kill-switch, margin-reduction and SL-arming paths; the required NO is not satisfied.
Q2: YES — late spot fills, partial perp reductions and failed spot unwinds can leave unhedged spot exposure.
Q3: NO — re-quotes count toward N, and the entry intent also has a total time cap.
Q4: NOT FULLY VERIFIED — I could not fetch the official dump; the accessible official changelog confirms its quoted amendment.

1. **[BLOCK-USER] Q1 conflicts with enabling the hedge safely.** Preserving existing perp MARKET/reduceOnly execution is achievable, but hedge cleanup must respond to existing exits, partial reductions and liquidation. Choose between authorizing that narrowly scoped integration or deferring spot execution. A literal “touches no exit/SL/TP/kill-switch paths” certification would be inaccurate.

2. **[P0] Items 1(a)/2 leave the spot cancel/fill race unresolved.** A maker order can time out, trigger perp closure, then fill afterward. Before taker fallback, require confirmed terminal status and use only the confirmed unfilled remainder. Unknown placement/cancellation outcomes must block replacement entries; pending-order and balance monitoring must continue after kill-switch activation. Naming order-update handling alone does not establish these outcomes.

3. **[P0] Item 1 covers perp disappearance but not partial reduction.** For example, reducing a matched 0.010 BTC perp to 0.005 leaves 0.005 BTC excess spot. Reconciliation currently specifies a tolerance without a corrective outcome. Define time-critical MARKET disposal of excess hedge inventory after any confirmed perp reduction, including partial TP and ADL, while preserving the existing perp exit policy.

4. **[P0] Items 1/3 apply futures exit semantics too broadly.** “All … unwinds are MARKET reduceOnly” conflicts with the new spot unwind: Binance’s spot order interface has no `reduceOnly` parameter. Scope that invariant explicitly to perp orders; spot disposal must be MARKET SELL bounded by actual hedge inventory. Spot MARKET orders can also face notional filters, so “sell immediately” needs an explicit unsellable-dust exception consistent with item 1(d). [Spot order interface](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/trade), [spot filters](https://developers.binance.com/en/docs/products/spot/filters).

5. **[P0] Item 1 needs explicit direction and quantity semantics.** Unborrowed long spot hedges a **short** perp. Define matching against confirmed fills and net BTC inventory after fees, using both venues’ runtime filters. The reconciliation expression must use signed net delta, or explicitly define “perp BTC” as the absolute short quantity; the repository’s `PositionRisk.amt` is signed. One-step tolerance must be a dust allowance, not permission for deliberate unmatched exposure. [Position type](/home/cms/project/BTC_Futures_E2E/paper/types.py:48).

6. **[P0] Item 1(b) does not precisely preserve isolated-margin safety.** “Futures-wallet collateral” could include free funds unavailable to the isolated position. Specify collateral actually allocated to that position, retaining ISOLATED and the existing leverage, risk and margin caps. Pre-fix the top-up/reduce trigger and the outcome when top-up fails or would breach a cap. Any perp reduction also requires item 1’s spot adjustment. [Startup isolation gate](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:214), [constitution sizing constraints](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/SKILL.md:77).

7. **[P0] Item 3 bounds re-quotes but leaves unknown outcomes insufficiently specified.** The three states omit placement transport failure. Querying status also does not resolve a race if the result remains nonterminal or unavailable. Require confirmed terminal status before another placement or MARKET fallback, including at the total deadline; unknown must never become “skip.” The existing `OrderOutcomeUnknown` idiom blocks entries—it is not an existing LIMIT cancellation/status implementation. Explicit −5022 handling is correct. [LiveSender](/home/cms/project/BTC_Futures_E2E/paper/sender.py:149), [official error definition](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/error-code#-5022-gtx_order_reject).

8. **[P0] Item 3 must fix the partial-fill safety outcome.** Require SL monitoring from the **first confirmed nonzero fill**, without waiting for cancellation or remainder completion. State that a failed post-fill liquidation gate triggers the existing immediate MARKET reduceOnly closure; “keep partial” cannot override it. Validate any new MARKET remainder separately, and never enlarge existing exposure merely to satisfy MIN_NOTIONAL. [Existing post-fill failure action](/home/cms/project/BTC_Futures_E2E/paper/engine.py:521).

9. **[P1] The master clause-change mapping is incomplete.** Item 3 names only SKILL.md §1-1, while the references still declare MARKET-only execution and taker-only paper fills. Item 6 also needs to distinguish its report-only family benchmarks from the existing P1 pass gate and the benchmark table labelled “final gate.” Resolve those references within the same six items. Item 5 should retain #88’s prospective-only application and explicit declaration of **whether** P1 inherits SL, with no default. Its θ = 10 / 2θ = 20 correction is accurate.

10. **[P2] Item 4 is only partially corroborated independently.** The accessible changelog reproduces the stated latest-to-largest amendment under 2026-04-10. I could not verify the dump’s line numbers, Last-Modified date, stream quotations, migration annotations or absence of a reversal. Preserve that evidence limitation and the unresolved master wording decision; the draft should not settle it. [Official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10).

VERDICT: FIX-PLAN-FIRST
```
No files edited.

1. OPEN — 1.5 creates spot-state → perp-exit coupling; 1.6 adds margin-reduction triggers, so exit safety remains affected.
2. RESOLVED — terminal confirmation before replacement/fallback, unknown-outcome entry blocking, and monitoring after kill are specified.
3. RESOLVED — 1.4 explicitly disposes of excess spot after partial TP, ADL, liquidation, and other confirmed reductions.
4. RESOLVED — reduceOnly is scoped to perps; spot disposal is inventory-bounded MARKET SELL with an unsellable-dust exception.
5. RESOLVED — short-perp direction, confirmed quantities, net inventory after fees, runtime filters, and dust-only tolerance are explicit.
6. RESOLVED — allocated isolated collateral, existing caps, and failed-top-up outcomes are specified; the added exit triggers remain subject to item 1’s block.
7. RESOLVED — transport failures and unresolved outcomes require terminal confirmation before further placement; unknown cannot become skip.
8. RESOLVED — first-fill SL arming, immediate post-fill gate closure, and separate remainder validation are explicit.
9. PARTIAL — references, benchmark gates, and prospective SL declaration are addressed; [SKILL.md §3-1’s MARKET-only wording](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/SKILL.md:80) still needs an explicit change-or-preserve disposition.
10. PARTIAL — the conflict remains unresolved as requested; independent verification of the dump’s stream quotation and Last-Modified date remains incomplete.

**Yes, option (a) still touches exit safety. [BLOCK-USER]** Clause 1.5 reads spot inventory and can close a perp residual. That directly contradicts 1.1’s “No code path from spot into perp exit.” Clause 1.6 additionally changes when margin reductions occur. Reusing MARKET reduceOnly preserves execution semantics, but adds exit decisions. The already-authorized fallback **(b): remove clauses 1–2** therefore applies; no further user choice is needed. Item 3 still requires the correction below.

Q1: YES — residual/margin triggers affect exits and kill-switch behavior; item 3 also changes SL-arming requirements.
Q2: YES — pending spot buys can fill after perp closure; failed disposal and below-threshold residuals can leave naked spot.
Q3: NO — N and total-time bounds prevent unbounded re-quotes; unresolved status holds entries blocked while monitoring continues.
Q4: NOT FULLY VERIFIED — the [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10) confirms the description amendment; the dump quotation and timestamp remain independently unverified.

NEW findings:

- **[BLOCK-USER] Clauses 1.1 and 1.5 conflict.** A spot-derived kill trigger is a dependency into perp exit, even if the exit executor never queries spot. Apply fallback (b), including removal of dependencies on clauses 1–2 elsewhere in the draft.
- **[P0] Item 3 leaves a resting GTX remainder alive across exits.** Example: an entry partially fills, SL closes that quantity, then the outstanding remainder fills and recreates exposure. Require entry-intent invalidation on exit/kill/post-fill-gate failure, cancellation of outstanding entry orders, and handling of racing fills without delaying the existing immediate exit. Terminal confirmation must also prevent subsequent remainder fallback. The existing [immediate gate-failure close](/home/cms/project/BTC_Futures_E2E/paper/engine.py:521) does not establish this new LIMIT-order lifecycle.
- **[P0] Clauses 1.2–1.5 do not explicitly invalidate pending spot buys when the perp reduces or disappears.** A perp exit can occur while spot inventory is zero; the pending BUY then fills after the reduction event. Require cancellation, current-position revalidation before placement/fallback, and disposal on each confirmed late fill. Threshold-and-time reconciliation alone can leave a tradable excess below its threshold indefinitely. This finding disappears from v1.6 under fallback (b).
- **[P0] Clause 1.4 permits maker unwind while item 2 forbids it.** Default OFF still permits enabling maker execution for a time-critical hedge unwind. Remove that exception if retaining these clauses; fallback (b) removes the conflict.

No additional new P1/P2 findings; round-1 items 9–10 remain partial.

VERDICT: BLOCK-USER


## PRE r3 — 프롬프트 · 응답
```
READ-ONLY PRE-REVIEW ROUND 3 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E. Item W5. Your round-2 verdict was BLOCK-USER on option (a); the user's pre-authorised fallback (b) now applies. Plan r4 (verbatim) below, then your round-2 output verbatim. TASK: RESOLVED / PARTIAL / OPEN for your round-2 new P0 on item 3 (resting GTX remainder across exits) and items 9-10; confirm that removing clauses 1-2 leaves no dangling dependency; Q1-Q4 one line each (Q1 exit/SL/TP/trailing/kill touched? — note item 1 now cancels entry orders on exit: judge whether that touches exit safety; Q2 naked-spot path? Q3 unbounded re-quote? Q4 erratum faithful?). NEW findings P0/P1/P2/BLOCK-USER. End with exactly one line: VERDICT: MERGE or VERDICT: FIX-PLAN-FIRST or VERDICT: BLOCK-USER.

## W5 plan r4 — fallback (b) applied (user decision #100: "If Codex still BLOCKs on (a) with a reason that touches exit safety, fall back to (b): remove clauses 1–2 from v1.6 and proceed with GTX entry + errata + benchmarks only; report both positions verbatim.")
Header: zero live or paper orders of any kind until v1.6 is merged; deployment only via the master zip. Items (renumbered; the user's items 1–2 — spot hedge leg and spot maker orders — are REMOVED from v1.6, with a one-line note that they were withdrawn under the user's fallback after two Codex BLOCKs; nothing in items 1–4 depends on them):
1. Perp entry via timeInForce=GTX (post-only), ENTRY ONLY — as plan r3 item 3, plus the round-2 P0: an ENTRY INTENT is invalidated by any exit of that position (SL, TP, trailing, kill-switch, post-fill liquidation-gate close) and by kill-switch activation; invalidation cancels every outstanding entry order of that intent without delaying the existing immediate exit (the exit is sent first; cancellation follows); a fill that races the cancel is treated as a new exposure that is closed at once by the existing MARKET reduceOnly path; once an intent is invalidated no remainder fallback and no re-quote may be sent; terminal status confirmation applies to every outstanding order before the intent is closed.
 Changed vs unchanged clauses: changed — SKILL.md §1-1 "진입·청산 전부 type=MARKET" → "perp exits all MARKET reduceOnly; perp entries MARKET or GTX under item 1"; SKILL.md §3-1 line on pyramiding/trailing/partial TP ("전부 봇 모니터링 + MARKET(청산 reduceOnly)") is PRESERVED for exits and adds: "pyramiding additions are entries and may use GTX under item 1"; the same disposition in references/exchange-rules.md (order policy) and references/strategy-modules.md (taker-only paper fills: a GTX paper fill model must follow a measured audit, never touch = fill). Unchanged — every perp exit, SL, TP, trailing, kill-switch is MARKET reduceOnly; side BUY/SELL; one-way; ISOLATED; no server-side STOP/TP; GTX only with an entry intent.
2. forceOrder wording — conflict recorded, not chosen (user text, as plan r3 item 4), with the evidence limitation stated: the change-log entry is verifiable on its page; the stream-reference sentence was found in llms-full.txt (read 2026-10-14, last-modified 2026-10-13) whose block lacks its own page URL.
3. Carry-over (#86–#88): pre-anchor power gate = projected N-corrected MDE ≤ 20 bps (θ = 10 bps net-edge threshold; MDE > 2θ = 20 → underpowered); P1 SL inheritance declared, never defaulted, prospective only; sizing-feasibility calibration.
4. Family-specific benchmarks — reported comparisons; they do not replace the P1 random-timing benchmark gate; the reference table labelling a benchmark "final gate" is reconciled.

YOUR ROUND-2 OUTPUT:
No files edited.

1. OPEN — 1.5 creates spot-state → perp-exit coupling; 1.6 adds margin-reduction triggers, so exit safety remains affected.
2. RESOLVED — terminal confirmation before replacement/fallback, unknown-outcome entry blocking, and monitoring after kill are specified.
3. RESOLVED — 1.4 explicitly disposes of excess spot after partial TP, ADL, liquidation, and other confirmed reductions.
4. RESOLVED — reduceOnly is scoped to perps; spot disposal is inventory-bounded MARKET SELL with an unsellable-dust exception.
5. RESOLVED — short-perp direction, confirmed quantities, net inventory after fees, runtime filters, and dust-only tolerance are explicit.
6. RESOLVED — allocated isolated collateral, existing caps, and failed-top-up outcomes are specified; the added exit triggers remain subject to item 1’s block.
7. RESOLVED — transport failures and unresolved outcomes require terminal confirmation before further placement; unknown cannot become skip.
8. RESOLVED — first-fill SL arming, immediate post-fill gate closure, and separate remainder validation are explicit.
9. PARTIAL — references, benchmark gates, and prospective SL declaration are addressed; [SKILL.md §3-1’s MARKET-only wording](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/SKILL.md:80) still needs an explicit change-or-preserve disposition.
10. PARTIAL — the conflict remains unresolved as requested; independent verification of the dump’s stream quotation and Last-Modified date remains incomplete.

**Yes, option (a) still touches exit safety. [BLOCK-USER]** Clause 1.5 reads spot inventory and can close a perp residual. That directly contradicts 1.1’s “No code path from spot into perp exit.” Clause 1.6 additionally changes when margin reductions occur. Reusing MARKET reduceOnly preserves execution semantics, but adds exit decisions. The already-authorized fallback **(b): remove clauses 1–2** therefore applies; no further user choice is needed. Item 3 still requires the correction below.

Q1: YES — residual/margin triggers affect exits and kill-switch behavior; item 3 also changes SL-arming requirements.
Q2: YES — pending spot buys can fill after perp closure; failed disposal and below-threshold residuals can leave naked spot.
Q3: NO — N and total-time bounds prevent unbounded re-quotes; unresolved status holds entries blocked while monitoring continues.
Q4: NOT FULLY VERIFIED — the [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10) confirms the description amendment; the dump quotation and timestamp remain independently unverified.

NEW findings:

- **[BLOCK-USER] Clauses 1.1 and 1.5 conflict.** A spot-derived kill trigger is a dependency into perp exit, even if the exit executor never queries spot. Apply fallback (b), including removal of dependencies on clauses 1–2 elsewhere in the draft.
- **[P0] Item 3 leaves a resting GTX remainder alive across exits.** Example: an entry partially fills, SL closes that quantity, then the outstanding remainder fills and recreates exposure. Require entry-intent invalidation on exit/kill/post-fill-gate failure, cancellation of outstanding entry orders, and handling of racing fills without delaying the existing immediate exit. Terminal confirmation must also prevent subsequent remainder fallback. The existing [immediate gate-failure close](/home/cms/project/BTC_Futures_E2E/paper/engine.py:521) does not establish this new LIMIT-order lifecycle.
- **[P0] Clauses 1.2–1.5 do not explicitly invalidate pending spot buys when the perp reduces or disappears.** A perp exit can occur while spot inventory is zero; the pending BUY then fills after the reduction event. Require cancellation, current-position revalidation before placement/fallback, and disposal on each confirmed late fill. Threshold-and-time reconciliation alone can leave a tradable excess below its threshold indefinitely. This finding disappears from v1.6 under fallback (b).
- **[P0] Clause 1.4 permits maker unwind while item 2 forbids it.** Default OFF still permits enabling maker execution for a time-critical hedge unwind. Remove that exception if retaining these clauses; fallback (b) removes the conflict.

No additional new P1/P2 findings; round-1 items 9–10 remain partial.

VERDICT: BLOCK-USER
```
No files edited. These are plan-level findings.

- **Round-2 item 3 P0: RESOLVED.** Exit/kill invalidation, exit-first cancellation, immediate closure of racing fills, prohibition of further remainder placement, and terminal confirmation cover the resting-GTX failure.
- **Item 9: PARTIAL.** R4 explicitly resolves SKILL.md §3-1 and the benchmark distinction, but additional master clauses still need dispositions below.
- **Item 10: PARTIAL.** The [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10) confirms the amendment. The dump quotation and Last-Modified remain independently unverified; r4 faithfully discloses that limitation and leaves the conflict unchosen.

**Removing original clauses 1–2 leaves no dangling spot dependency in r4 items 1–4.** The spot-related P0s and spot-derived exit/margin triggers disappear. The inherited GTX requirements operate independently.

Q1: YES — exit/SL/TP/trailing/kill now invalidate and cancel entry orders, and racing fills require closure; this touches exit safety while preserving immediate MARKET reduceOnly execution and requires no renewed user decision.  
Q2: NO — fallback (b) removes both spot execution clauses and their naked-spot path.  
Q3: NO — inherited N/time bounds remain, and invalidated intents prohibit re-quotes and remainder fallback.  
Q4: YES to the conflict-recording decision; PARTIAL independent verification of the cited evidence.

NEW findings:

- **[P1] Additional master clauses remain outside the explicit change-or-preserve map.** [open-decisions.md](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/open-decisions.md:20) still declares MARKET-only execution; [research-protocol.md](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/research-protocol.md:65) mandates taker-only paper fills; [strategy-modules.md’s review checklist](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/strategy-modules.md:151) requires all advanced orders to be MARKET/reduceOnly. Extend r4’s mapping to these clauses: exits remain MARKET reduceOnly, GTX entries follow item 1, and paper stays taker-only until the measured GTX audit permits its explicit exception.

No new P0/P2/BLOCK-USER findings. The remaining correction is a plan clarification within the authorized fallback.

VERDICT: FIX-PLAN-FIRST


## 문서 r1 — 프롬프트 · 응답
```
READ-ONLY INDEPENDENT REVIEW, ROUND 1 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E at HEAD. Document: docs/proposals/constitution_v1.6_amendment.md — the v1.6 amendment DRAFT, written after your plan reviews (record: reports/advisory/w5_constitution_v16_pre.md; your plan round 3 returned P1 only). The user's fallback (b) removed the spot hedge leg and spot maker clauses. Current constitution copy: .claude/skills/quant-bot-constitution/ (read-only).
Answer the user's questions against the document text: Q1 does any clause touch exit, SL, TP, trailing or kill-switch paths (state precisely how, and whether exit execution itself stays MARKET reduceOnly and undelayed)? Q2 any path to naked spot? Q3 any unbounded re-quote loop? Q4 is the forceOrder erratum exact to the sources it quotes?
Also: does the changed/unchanged clause map now cover every master clause that states MARKET-only or taker-only (your plan-round-3 P1); is anything ambiguous, unsafe, or inconsistent with the unchanged invariants.
OUTPUT: numbered findings P0/P1/P2/BLOCK-USER with file:line; one line per Q1-Q4; end with exactly one line: VERDICT: MERGE or VERDICT: FIX or VERDICT: BLOCK-USER.
```
1. **[P0] Partial-fill completion lacks an explicit cancellation barrier.** [docs/proposals/constitution_v1.6_amendment.md:13](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:13) permits MARKET completion without explicitly cancelling the resting GTX, confirming terminal status, and recomputing the unfilled remainder from cumulative fills. A 0.010 BTC order could fill 0.004, trigger 0.006 MARKET completion, then fill its resting 0.006, producing 0.016 BTC exposure. Extend the terminal-confirmation requirement to **every replacement or remainder order**, including completion before the deadline; unresolved outcomes must block it.

2. **[P1] The clause map remains incomplete.** [docs/proposals/constitution_v1.6_amendment.md:18](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:18) now covers the three omissions identified in plan round 3, but still omits [strategy-modules.md:77](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/strategy-modules.md:77), which independently requires all advanced execution to use MARKET, and [exchange-rules.md:46](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/exchange-rules.md:46), which declares LIMIT filtering inapplicable because the bot is MARKET-only. Give both explicit dispositions: retain MARKET reduceOnly exits, allow GTX additions under item 1, and revise LIMIT-filter applicability.

3. **[P1] The benchmark correction targets the wrong file.** [docs/proposals/constitution_v1.6_amendment.md:35](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:35) names a “final gate” table in research-protocol.md; that table is actually [strategy-modules.md:63](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/strategy-modules.md:63). Correct the target so BTC-holding/risk-free comparisons become report-only while the formal P1 gate remains intact.

Q1: **YES** — draft:13 changes first-fill SL arming; draft:15 makes exits/SL/TP/trailing/kill invalidate entries, cancel resting orders after sending the exit, and immediately close racing fills; draft:30 specifies research P1 SL inheritance. Exit execution itself expressly remains **MARKET reduceOnly, undelayed** (draft:8,15,20).

Q2: **NO** — draft:5 removes both spot-execution clauses; the remaining provisions introduce no naked-spot path.

Q3: **NO** — draft:10,14 bound re-quotes by N and total time; draft:11 blocks replacements on unknown outcomes, and draft:15 prohibits re-quotes after invalidation. Continuing reconciliation is not permission to re-quote indefinitely.

Q4: **Quoted wording matches, with qualifications** — draft:24 matches the [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10) after joining its bullets with an editorial dash; draft:25 exactly matches the opening sentences at [cached llms-full.txt:202753](/home/cms/project/BTC_Futures_E2E/var/docs_fetch/llms-full.txt:202753). The conflict is accurately recorded without choosing a winner; the stated Last-Modified header was not independently verified.

VERDICT: FIX


## 문서 r2 — 프롬프트 · 응답
```
READ-ONLY INDEPENDENT REVIEW, ROUND 2 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E at HEAD; document docs/proposals/constitution_v1.6_amendment.md. Your round-1 output is below. Check the fixes for findings 1-3 against the committed text (git diff HEAD~1 -- docs/proposals/constitution_v1.6_amendment.md) and re-answer Q1-Q4 in one line each. Any NEW finding P0/P1/P2/BLOCK-USER. End with exactly one line: VERDICT: MERGE or VERDICT: FIX or VERDICT: BLOCK-USER.

1. **[P0] Partial-fill completion lacks an explicit cancellation barrier.** [docs/proposals/constitution_v1.6_amendment.md:13](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:13) permits MARKET completion without explicitly cancelling the resting GTX, confirming terminal status, and recomputing the unfilled remainder from cumulative fills. A 0.010 BTC order could fill 0.004, trigger 0.006 MARKET completion, then fill its resting 0.006, producing 0.016 BTC exposure. Extend the terminal-confirmation requirement to **every replacement or remainder order**, including completion before the deadline; unresolved outcomes must block it.

2. **[P1] The clause map remains incomplete.** [docs/proposals/constitution_v1.6_amendment.md:18](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:18) now covers the three omissions identified in plan round 3, but still omits [strategy-modules.md:77](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/strategy-modules.md:77), which independently requires all advanced execution to use MARKET, and [exchange-rules.md:46](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/exchange-rules.md:46), which declares LIMIT filtering inapplicable because the bot is MARKET-only. Give both explicit dispositions: retain MARKET reduceOnly exits, allow GTX additions under item 1, and revise LIMIT-filter applicability.

3. **[P1] The benchmark correction targets the wrong file.** [docs/proposals/constitution_v1.6_amendment.md:35](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:35) names a “final gate” table in research-protocol.md; that table is actually [strategy-modules.md:63](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/strategy-modules.md:63). Correct the target so BTC-holding/risk-free comparisons become report-only while the formal P1 gate remains intact.

Q1: **YES** — draft:13 changes first-fill SL arming; draft:15 makes exits/SL/TP/trailing/kill invalidate entries, cancel resting orders after sending the exit, and immediately close racing fills; draft:30 specifies research P1 SL inheritance. Exit execution itself expressly remains **MARKET reduceOnly, undelayed** (draft:8,15,20).

Q2: **NO** — draft:5 removes both spot-execution clauses; the remaining provisions introduce no naked-spot path.

Q3: **NO** — draft:10,14 bound re-quotes by N and total time; draft:11 blocks replacements on unknown outcomes, and draft:15 prohibits re-quotes after invalidation. Continuing reconciliation is not permission to re-quote indefinitely.

Q4: **Quoted wording matches, with qualifications** — draft:24 matches the [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10) after joining its bullets with an editorial dash; draft:25 exactly matches the opening sentences at [cached llms-full.txt:202753](/home/cms/project/BTC_Futures_E2E/var/docs_fetch/llms-full.txt:202753). The conflict is accurately recorded without choosing a winner; the stated Last-Modified header was not independently verified.

VERDICT: FIX
```
Findings 1–3 are fixed at HEAD `4d95025`: cancellation, terminal confirmation, and cumulative-fill remainder calculation ([lines 13–14](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:13)); explicit dispositions for both omitted clauses ([line 19](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:19)); corrected benchmark-table target with the formal P1 gate preserved ([line 36](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:36)).

Q1: **YES** — lines 13, 16, and 31 affect first-fill SL arming, entry invalidation and racing-fill cleanup, and research P1 SL inheritance; exits remain immediate MARKET reduceOnly.

Q2: **NO** — line 5 excludes both spot provisions; no remaining clause introduces a naked-spot path.

Q3: **NO** — re-quotes have count and time limits; unknown outcomes block further entries, and invalidation prohibits replacements or completion.

Q4: **Matches, with qualifications** — line 25 matches the [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10), joining bullets with an editorial dash; line 26 matches the cached dump at line 202753; the live dump was inaccessible and Last-Modified remains independently unverified.

No new P0/P1/P2/BLOCK-USER findings. No files edited.

VERDICT: MERGE


## 문서 r3 — 사용자 #105(GTX 제거 · 현물 1 · 2 복원) · 프롬프트 요지: Q1~Q6 · 첫 BLOCK에서 멈춤
- 대상 커밋 89cd55a(초안 r3) · 결과 **VERDICT: BLOCK**(BLOCK-USER 1 · P0 2 · P1 1) → #105 규칙대로 **이 회전에서 멈춘다**(고치지 않음 · 다음 회전 없음).

```
[codex] Turn completed.
Read-only review at HEAD `89cd55a`; no files edited. Stopping this round at **BLOCK-USER**.

- **Q1: NO for perp exit/SL/TP/trailing/kill-switch/margin decisions as specified.** Clauses 1-1, 1-2 and 1-7 preserve existing policies. Spot cleanup receives perp events afterward—the coupling already authorized.
- **Q2: YES, an inadequately bounded naked-spot path remains.** A resting spot BUY can survive perp closure, then fill; timeout fallback can also buy the obsolete remainder.
- **Q3: NOT ESTABLISHED.** GTX re-quotes are gone, but spot rejection/retry handling and repeated guard orders have no explicit attempt or total-time bounds.
- **Q4: PARTIALLY VERIFIED.** The erratum preserves the supplied user wording, and the [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10) confirms the latest-to-largest description change. I could not independently retrieve the official dump to verify its stream quotation or Last-Modified date.
- **Q5: PARTLY.** 1-2 adequately preserves existing perp safeguards during an hours-long unhedged interval; it does not resolve the spot-order lifecycle failures below. GTX removal is complete in the operative draft and clause map; the remaining GTX mentions describe its removal or prohibition.
- **Q6: USER CONFIRMATION REQUIRED.** The rewrite satisfies the direction of dependency, but selects a materially different response to hedge failure.

1. **[P0] Pending spot entry invalidation remains missing.** [Clauses 1-5 and 2-1](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:12) require terminal confirmation before replacement, but do not require cancellation when the perp reduces/disappears, current-short revalidation before fallback, or immediate cleanup on late spot fills. Example: the perp closes while spot inventory is zero; cleanup sells nothing; the resting BUY later fills. If its value is below the residual threshold but above dust, cleanup has no guaranteed trigger. This is the unresolved [PRE r2 finding](/home/cms/project/BTC_Futures_E2E/reports/codex/w5_constitution_v16_rounds.md:148). Require those outcomes entirely within the spot subscriber, without delaying or changing perp exits.

2. **[P0] The signed residual trigger cannot detect hedge deficits as written.** [Clause 1-6](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:13) tests `d × mark > threshold`. For a positive threshold, negative `d` never reaches the deficit branch. Test magnitude, `|d| × mark`, then branch on sign. Tradable excess from late fills also needs unconditional cleanup independent of this threshold.

3. **[P1] Bound order retries explicitly.** [Clauses 1-6 and 2-1](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:19) do not establish a total bound across maker rejection/replacement attempts or failed cleanup retries. Specify exhausted-bound behavior and prevent timer resets from extending an entry intent indefinitely. Continued monitoring is separate from submitting repeated orders.

4. **[BLOCK-USER] One-directional consistency does not establish design authorization.** [The disclosed rewrite](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:5) replaces hedge-deficit MARKET cleanup with alert plus blocked entries, allowing the existing short to remain unhedged until its ordinary exit. It also removes the prior plan’s added margin top-up/reduction policy. These changes eliminate PRE r2’s contradictory perp actions, but [registry #105](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:113) does not explicitly approve these replacement outcomes. Confirm the concrete policy: **hedge failure never causes perp closure, reduction or margin action; existing perp safeguards continue unchanged, even after the hedge deadline.** Disclosure and standalone safety are useful, but cannot substitute for that user decision.

VERDICT: BLOCK
```

## 문서 r4 — 사용자 #107 정책 1~7 · 첫 BLOCK-USER에서 멈춤
- 대상 커밋 72adbb6(초안 r4) · 결과 **VERDICT: BLOCK**(BLOCK-USER 1 · P0 2) → #107 규칙대로 **이 회전에서 멈춘다**.

```
[codex] Turn completed.
Read-only review at HEAD `72adbb6`; no files edited. Stopping at the next **BLOCK-USER**.

(a) R3 findings:

- **Q2 — PARTIAL:** Late fills after perp closure are covered; ordinary-close inventory, shrink-related excess, and failed perp entry still have gaps.
- **Q3 — RESOLVED:** Clause 1-6 establishes total attempt/time caps, prohibits timer extension, and specifies flat escalation.
- **P0-1 — PARTIAL:** Cancellation, terminal confirmation, and fallback revalidation are explicit; immediate cleanup of late excess after a partial shrink remains unspecified.
- **P0-2 — RESOLVED:** Clause 1-5 tests `|d| × mark` before branching on sign.
- **P1-3 — RESOLVED:** Spot placements, replacements, and guard orders have explicit bounds and exhaustion outcomes.
- **BLOCK-USER-4 — RESOLVED:** #107 explicitly rejects the former sentence and authorizes TargetState flat escalation and removal of margin top-up/reduction.

(b) Q1–Q6:

- **Q1: NO** — perp exit/SL/TP/trailing/kill-switch/margin paths remain unchanged; hedge-derived exits use the carry strategy’s TargetState.
- **Q2: YES** — authorized spot-first entry creates transient naked spot, and the cleanup gaps below can leave it persistent.
- **Q3: NO** — order submission is explicitly bounded; continued monitoring is separate.
- **Q4: PARTIALLY VERIFIED** — the user’s erratum remains verbatim and the [official changelog](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10) confirms the description amendment; I could not retrieve the official dump to verify its quotation or Last-Modified date.
- **Q5: GTX REMOVAL COMPLETE; EXPOSURE HANDLING PARTIAL** — the hours-long maker wait no longer precedes an unhedged perp short, but spot cleanup remains incomplete.
- **Q6: PARTIAL** — most of #107 is reflected faithfully; its conflicting instructions for a positive guard breach remain unresolved.

(c) New findings, ending at the first new BLOCK-USER:

1. **[P0] Ordinary perp closure/reduction lost its explicit inventory cleanup rule.** [Clause 1-4](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:12) explicitly sells late fills after closure and inventory after liquidation, but does not explicitly sell already-held inventory after an ordinary close, or excess after a partial reduction. R3 required disposal after every confirmed reduction. A tradable residual below the guard threshold can now remain indefinitely. Require inventory-bounded MARKET disposal after every confirmed reduction/close, including racing excess fills, independently of the guard threshold and without delaying perp exits.

2. **[P0] Spot-first entry lacks complete failed-perp-entry outcomes.** [Clause 1-1](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:9) cleans spot when entry gates fail, but does not specify cleanup when the subsequent perp MARKET order is rejected, confirms less than the intended quantity, or remains unresolved. With no established perp position, there may be no shrink/close event to trigger 1-4. Require confirmed-position reconciliation and bounded disposal of unmatched spot; unknown perp execution must be resolved before selling potentially matched inventory. Setting an already-flat perp TargetState alone cannot dispose of spot.

3. **[BLOCK-USER] #107 gives conflicting outcomes for a positive guard breach.** [Registry #107](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:115), item 2, requires strategy flat when the guard trips **“for either sign of d.”** Item 5 instead specifies excess-spot MARKET sale for `d > 0`; [draft clause 1-5](/home/cms/project/BTC_Futures_E2E/docs/proposals/constitution_v1.6_amendment.md:13) states only that sale. Successful repair can therefore retain the short under one reading, while the other requires closing it. The user must choose whether a positive breach requires **flat plus spot cleanup**, or **spot repair with flat only on exhausted bounds**. Both can preserve Q1 through TargetState; the draft cannot silently choose precedence.

VERDICT: BLOCK
```
