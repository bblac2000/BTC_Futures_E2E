# W5 — 헌법 v1.6 개정안 초안 · PRE(착수 전 검토) — **BLOCK-USER로 멈춤**

- 날짜: 2026-10-14 · 항목: W5(CRITICAL · 주문 경로에 닿음) · 검토자: advisor + Codex(`codex-companion task --effort high` · 읽기 전용)
- 결과: Codex PRE r1이 **BLOCK-USER**(사용자 결정 필요) 1건과 P0 7건을 냈다. 사용자 지시("stop at MERGE or at the first BLOCK that needs a user decision")에 따라 **개정안 문서는 쓰지 않았다.** 초안 문서·스킬 사본·코드 변경 없음.

## 1. 계획 r1(advisor 검토 대상)
1. 현물 헤지 다리: 같은 계정 BTCUSDT 무기한 포지션의 동시 1:1 델타 헤지로만 · BTC/FDUSD · BTC/USDT만 · 현물 단독 금지 · 대사에 현물 잔고 · 사이징은 선물 다리에서 · FDUSD/USDT 디페그 감시(문턱 → 신규 진입 차단).
2. 현물 메이커 주문: 헤지 다리에만 · 최대 대기 뒤 테이커 폴백 · 전부 기록 · 시간이 급한 주문에 금지.
3. 선물 진입 GTX: 진입만 · 거부 시 최대 N회 재호가 뒤 MARKET 폴백 또는 건너뛰기(N과 총 시간 상한) · 청산·SL·TP·트레일링·킬스위치는 MARKET reduceOnly 그대로.
4. forceOrder 정오표: 공식 문서 덤프에서 두 문구가 갈림 — 두 출처를 원문과 함께 적고 결론은 불변 · 정본 문구는 사용자 결정.
5. 이월: 앵커 전 검정력 관문 · P1 SL 승계 명시 · 사이징 가능성 보정(#86~#88).
6. 가족별 벤치마크(D6).

## 2. advisor PRE — 원문(verbatim)
You're at the W5 PRE (advisor half) with plan r1 in chat; M-1 is in the restore step (fetch running, 0 files landed when you last looked). **W5 verdict: PROCEED with four draft-level fixes and one scope rule; Codex PRE on plan r2, not r1.** Save this verbatim into `reports/advisory/w5_constitution_v16_pre.md` first. One operational item on the restore at the end — check it before anything else, it may be burning hours.

**Restore (check now)**

`rclone copy --files-from … --no-traverse` does one Drive lookup per listed file before any transfer — 104k lookups at Drive's pacer is hours before the first byte. If `find var/p0_restore/BTCUSDT -name '*.parquet' | wc -l` is still 0, stop the job and copy per directory instead: 75 `rclone copy gdrive:…/BTCUSDT/<date>/<stream>/ var/p0_restore/BTCUSDT/<date>/<stream>/` (matched set == whole directories because `drive_orphans` = 0 and Drive-missing files simply don't exist). `verify` already iterates the plan's matched list and flags "not downloaded", so nothing in the spec changes. Don't list the parent `BTCUSDT/` tree — it contains the auxiliary-span dates.

**Item 4 — you've mischaracterised the evidence**

The "latest" text at llms-full lines 202637/202753 is not an orphaned mini-program block: it carries "After CM migration" annotations and Operation IDs for the USDⓈ-M stream reference, so it's a *current* reference page whose `URL:` header is lost in the dump. What you have is two official texts in conflict: the USDⓈ-M change-log entry 2026-04-10 ("latest → largest") and a present-day stream reference saying "latest", with no reversal entry in the log. The user's claim is therefore supportable. Draft item 4 as: quote both verbatim with dump line numbers and the dump's `last-modified: 2026-10-13`; state v1.5 adopted "largest" from that change-log; conclusion (not a liquidation-volume measure) unchanged either way; **which wording becomes the master text is a user decision** → it goes on the decision list, not into the draft as settled. Delete the "엉뚱한" framing from the record.

**Item 5 — do not carry the #96 error into the master**

Write the pre-anchor power gate symbolically with the repo value stated: θ = 10 bps, "projected MDE > 2θ (= 20) → do not anchor". The constitution is cross-repo; this is where a wrong θ would propagate.

**Item 1 — the draft as planned leaves a naked path and an unfunded leg (P0)**

"Naked spot forbidden" needs: (a) leg order and the transient — one leg will fill first; pre-fix the sequence and a bounded auto-unwind when the second leg fails (spot filled, perp fails → sell spot MARKET immediately; perp filled, spot fails → close perp reduceOnly); (b) margin isolation — the spot BTC sits in the spot wallet and does not fund the perp short's margin; the perp leg's liquidation distance is computed from futures-wallet collateral only, so cap the perp leg's leverage or require a top-up rule; (c) quantity matching across different lot sizes (spot BTC step vs futures 0.001) — spot qty rounds to the perp qty; (d) reconcile tolerance |spot − perp| ≤ futures step, dust rule; (e) depeg monitor: name the source (FDUSDUSDT spot ticker) and that it blocks new entries only (the user's words).

**Item 3 — "GTX rejection" is one of three states (P0)**

On USDⓈ-M a post-only order that would cross is refused (error −5022, nothing placed). The draft must also cover: a resting GTX that doesn't fill → timeout → cancel → MARKET fallback or skip (cancel is a new order-path action; handle the cancel/fill race via order status — `OrderOutcomeUnknown` is the existing idiom); a **partial fill** before cancel (skip is not a valid outcome with a partial position — complete with MARKET or run sizing/SL on the actual qty, say which); fill confirmation before the SL monitor arms; fallback re-runs normalisation + MIN_NOTIONAL + the liquidation gate at the fallback price; N re-quotes **and** a total time cap. Keep the invariants list: exits/SL/TP/trailing/kill = MARKET reduceOnly, side BUY/SELL, no server-side STOP/TP, GTX only with the entry intent.

**Scope rule**

The user said "exactly these items and nothing else" — six numbered items, no extra sections. Your "바뀌는 문장 대조표" belongs *inside* item 3 as the changed/unchanged clause list; the repo-impact list (CLAUDE.md hard rule, `exchange/orders.py` validation, tests, spot transport under registry #8's pin) goes in the Codex packet and the briefing, not the doc. One header line restating D5 (zero orders until merge; deploy only via the master zip) is fine.

**P1 (carry with accepted/rejected lines)**
- Item 2: define "time-critical" = any exit, unwind, kill, or margin action.
- Resting entries need order-update handling (user data stream or polling) — name the requirement, don't design it.
- Spot API is a new transport surface; the pin row (#8) scope covers it when implemented.

**Process**
Plan r2 with the above → Codex PRE (prompt = r2 + the user's W5 questions: any clause touching exit/SL/TP/trailing/kill? any naked-spot path? unbounded re-quote loop? erratum exact to official text?) → write the doc → Codex independent review rounds saved verbatim under **`reports/codex/`** (the user's W5 location; advisory PRE/POST stay in `reports/advisory/`) → stop at MERGE or at the first BLOCK that needs the user (the forceOrder wording is already one). No skill-copy edits, no code.

## 3. 계획 r2(Codex 검토 대상 · verbatim)
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

## 4. Codex PRE r1 — 프롬프트(verbatim)
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

## 5. Codex PRE r1 — 응답 원문(verbatim)
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


## 6. 입장표(Claude Code)
| 출처 | 등급 | 요지 | 입장 |
|---|---|---|---|
| advisor 항목 4 | — | "latest" 문구는 엉뚱한 블록이 아니라 현재의 스트림 참조 문서(머리 URL이 덤프에서 빠짐)로 보인다 · 두 공식 문구의 충돌로 적는다 | 동의 — 계획 r1의 표현을 철회 · 계획 r2 4항 |
| advisor 항목 5 | — | θ = 10 · 2θ = 20을 기호와 함께 | 동의 |
| advisor 항목 1 · 3 | P0 | 다리 순서 · 마진 격리 · 수량 맞춤 · 대사 허용 · 디페그 출처 / GTX 세 상태 · 부분 체결 · 시간 상한 | 동의 — 계획 r2 |
| advisor 범위 | — | 여섯 항목만 · 저장소 영향은 문서 밖 | 동의 |
| Codex 1 | **BLOCK-USER** | 헤지를 안전하게 하려면 정리 동작이 기존 청산·부분 감소·청산(liquidation)에 반응해야 한다 — "청산·SL·TP·킬스위치 경로에 닿지 않는다"는 정확히 말할 수 없다. 좁게 범위를 정해 그 연동을 허용할지, 현물 실행을 미룰지 | **동의 — 사용자 결정 목록으로**(Claude Code는 고르지 않는다) |
| Codex 2~8 | P0 | 현물 취소/체결 경합 · 부분 감소 뒤 초과 현물 처분 · 현물에는 reduceOnly가 없음 · 방향·수량의 부호 정의 · 격리 마진의 실제 담보 · 주문 결과 미상 처리 · 첫 체결부터 SL | 동의 — BLOCK 결정 뒤 계획 r3에서 반영 |
| Codex 9 | P1 | 참조 문서들의 MARKET 전용 문구 · 벤치마크와 P1 게이트 구분 · #88의 소급 없음 | accepted — r3 |
| Codex 10 | P2 | forceOrder: 변경 기록은 확인 · 덤프의 줄 번호·참조 문구는 Codex가 직접 확인 못 함 | 동의 — 증거 한계를 문서에 적는다 |

## 7. 사용자 결정 필요(이 항목이 다시 움직이려면)
1. **현물 헤지 다리의 범위(Codex BLOCK)**: (가) 헤지 정리를 기존 청산·부분 감소·청산 이벤트에 반응하도록 **좁게 연동하는 것을 허용**(선물 다리의 청산 정책 자체는 그대로 MARKET reduceOnly) · (나) **현물 실행 조항(1 · 2항)을 v1.6에서 빼고** GTX 진입(3항)과 나머지만 진행.
2. **forceOrder 정본 문구**: 변경 기록(2026-04-10, "largest")과 현재 스트림 참조("latest")가 갈린다 — 어느 쪽을 마스터에 적을지.
