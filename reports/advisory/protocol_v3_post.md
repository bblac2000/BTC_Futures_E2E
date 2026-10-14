# 스크린 프로토콜 v3 · POST(완료 후 검토)

- 회전: Codex POST r1 FIX(P1 2 — MDE 읽기가 확인 없이 작동) → 고침(74c0151) → **Codex POST r2 MERGE** · advisor POST ACCEPT · 앵커 #101(Drive createdTime 2026-10-14T04:39:57.311Z).
- 공시(advisor): v3 §2에서 UNRESOLVED 표시 앞의 두 문장은 읽기 (i)를 단정하는 모양으로 남아 있다 — **작동하는 문안은 UNRESOLVED 블록**이다. 다음 판(v4)이 생기면 두 문장을 합친다(앵커된 해시라 지금 고치지 않는다).
- 레지스트리 사전 점검(#100~#102 뒤): `[1, 2] 7 [1] 3` 그대로.

## 입장표
| 출처 | 요지 | 입장 |
|---|---|---|
| Codex POST r1-1 · 6 | MDE 읽기를 실행 차단 UNRESOLVED로 | 동의 — 74c0151 |
| Codex POST r1-2~5 | carry 예외 국한 · 판정기 불변 · UNRESOLVED 차단 · v2 보장 유지 | 확인 |
| advisor POST | §2 앞 두 문장 공시 · UNRESOLVED 넷을 A/B로 브리핑 · 사전 점검 | 동의 |

## advisor POST — 원문(verbatim · 프로토콜 v3와 W5를 함께 본 한 번의 호출)
You're at the POST for two items at once: protocol v3 (anchored #101, Codex POST r2 MERGE at 74c0151) and the v1.6 draft (#102, Codex doc r2 MERGE at 4d95025), with M-1 restoring at 22.7k/104k. **Advisor POST: protocol v3 — ACCEPT. W5 draft — ACCEPT as a draft, with one framing the briefing must carry and two small fidelity items.** Save this verbatim into both `_post.md` files (advisor section), then the Codex rounds and your positions.

**Protocol v3 — nothing blocks; record these**

- §2 still *asserts* reading (i) in the two sentences before the UNRESOLVED note. Codex accepted the fix; disclose in `_post.md` that the operative text is the UNRESOLVED block, not the sentences above it, and that v4 (if any) should collapse them.
- UNRESOLVED list now gates everything S: MDE reading, carry resampling unit, carry CI level, xs-carry delay threshold. Put all four in the briefing's decisions section with the two concrete options each — the user can't answer "confirm" to a question they haven't seen stated as A/B.
- Run the provenance precheck once (`[1,2]/7/[1]/3`) — rows #100–#102 skipped it; cheap, and the briefing claims a clean registry.

**W5 — the thing the briefing must say plainly**

Codex's Q1 is YES on the final text, and the user wrote "must be NO". Codex didn't BLOCK because exit *execution* is unchanged; what's added is a cancel of outstanding entry orders *after* the exit is sent, SL arming from the first fill, and the P1 SL-inheritance line (that last one is a research rule, not an order path — say so, it doesn't belong in Q1). Frame the decision correctly: the alternative to the cancel-after-exit rule is a resting GTX that fills after the SL and re-opens exposure — i.e. the choice is "accept this touch" vs "no GTX entries at all". Present both positions verbatim (Codex r2 Q1 line; your reading) and let the user pick. Until they do, #102's status is "Codex MERGE on text; user criterion Q1 open".

Two fidelity items, both because the user said "verbatim":
- Item 2's `[DOC-CONFLICT]` paragraph is your Korean rendering of the user's English master text, and source 1 is bullet-joined with an editorial dash (Codex noted it). The master has English in exactly that spot (`exchange-rules.md:103`). Fix in one commit: add the user's English text verbatim under the Korean, and quote source 1 with its original line breaks. Note the new commit in the briefing and the `_post.md`; #102 describes the draft, it doesn't hash-anchor it, so no correction row.
- Repo impact list the doc rightly omits but the briefing owes: CLAUDE.md hard rule "MARKET only", `exchange/orders.py` type validation and its tests, `tests/test_no_exchange_literals.py` scope, the pin row #8 if a LIMIT path lands. Post-merge items, zero code now.

**Before M-1 runs (not optional)**

Full suite at HEAD — the last full run (1,899 at 8701bb2) predates every p0 module; you've only run the 52-test subset. Then `verify` → coverage ≥ 99 % after exclusions → `run` once → RESULT row citing v2 with the "§3-3/§4-4 unchanged in v3" sentence → POST.

**Use the restore wait on W3 step 1 only**

#100 says "locate the carrybot ledger and its cost model; extract verbatim; report them before touching numbers." That extraction is reading closed-trial documents, not re-pricing: find the per-settlement ledger file and quote spot fee/side, perp fee/side, slippage, funding accounting, exit rule from `CarryBot_G1_사전등록_v2` and the result reports; note the ledger's last date (2026-07-31 → June ceiling drops the tail) and whether it's 8h rows (episode chunking is then a spec decision). Put it in the M-1 briefing. No S-row START, no numbers — W3 is blocked by the carry UNRESOLVED items regardless.

**Briefing (after M-1), in this order**

M-1 result table by T and stratum, verdict, restore counts, exclusions, B_d per day; the θ = 20 correction list exactly as the user asked (four locations, no in-place edits, covered by #96/#100, v3 carries the correct text); W5 Q1 framing + fidelity fix; the UNRESOLVED decisions with options; W3 extraction report; repo-impact list. Memory `screens-round-2026-10.md`: one line — v3 anchored, v1.6 draft at Codex MERGE with Q1 open, the four UNRESOLVED gates.

## Codex POST r1 — 프롬프트 · 응답
```
READ-ONLY POST-REVIEW (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E at HEAD. docs/screen_protocol.md is now v3 (SHA256 996ed2ac2a11239dd61dc92dab6f8980d13cf0e9a3f58268ce299e71c49431c2, not yet anchored). Compare it with v2 (`git show 945e2ce:docs/screen_protocol.md`). Your PRE findings and my positions are in reports/advisory/protocol_v3_pre.md §5-6. User decisions: docs/trial_registry.md row #100.
Check against the committed text: (1) any post-hoc degree of freedom reopened; (2) carry carve-out confined to carry; (3) any disguised change to the formal judge (θ = 10, MDE cutoffs 20/5, α, MDE rule, #88); (4) the UNRESOLVED items block execution as intended (carry: resampling unit and CI level; xs-carry: delay threshold); (5) v2 guarantees intact (D4 in code, k counting, START-before-data, §3-3 and §4-4 P0 text unchanged); (6) faithfulness to #100's wording.
OUTPUT: numbered findings P0/P1/P2 with file:line; one line per check; end with exactly one line: VERDICT: MERGE or VERDICT: FIX.
```
1. **P1 — Check 1:** [docs/screen_protocol.md:35](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:35) makes the pending MDE interpretation operative; accepted PRE required it UNRESOLVED until confirmation ([PRE:68](/home/cms/project/BTC_Futures_E2E/reports/advisory/protocol_v3_pre.md:68)). Add that execution block.
2. **P2 — Check 2:** [docs/screen_protocol.md:49](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:49) confines overrides to their named families; line 53 expressly limits the benchmark exception to carry.
3. **P2 — Check 3:** [docs/screen_protocol.md:29](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:29) preserves θ=10, cutoffs 20/5, formal α/MDE/n_eff and #88; judge and anchor code are unchanged; coefficient arithmetic is correct.
4. **P2 — Check 4:** [docs/screen_protocol.md:54](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:54), [line 59](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:59) and §3-2 block carry pending resampling-unit/CI-level decisions and xs-carry pending the delay threshold.
5. **P2 — Check 5:** [docs/screen_protocol.md:20](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:20), [line 111](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:111) preserve START-before-new-data and k counting; D4 remains enforced in code; §3-3 and §4-4 P0 text match v2 exactly.
6. **P1 — Check 6:** [docs/screen_protocol.md:35](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:35) interprets [#100:108](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:108)’s “uncorrected coefficient” as uncorrected significance with report-only MDE; naming a confirmation list does not establish confirmation. Other reviewed decisions are faithfully represented.
VERDICT: FIX


## Codex POST r2 — 프롬프트 · 응답
```
READ-ONLY POST-REVIEW ROUND 2 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E at HEAD; docs/screen_protocol.md v3. Your round-1 output is below; findings 1 and 6 (P1) asked that the MDE-coefficient reading be an execution-blocking UNRESOLVED item rather than an operative interpretation. Check the committed fix (search 'UNRESOLVED(사용자 확인 전 S 행 실행 차단') and whether anything else changed. End with exactly one line: VERDICT: MERGE or VERDICT: FIX.

1. **P1 — Check 1:** [docs/screen_protocol.md:35](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:35) makes the pending MDE interpretation operative; accepted PRE required it UNRESOLVED until confirmation ([PRE:68](/home/cms/project/BTC_Futures_E2E/reports/advisory/protocol_v3_pre.md:68)). Add that execution block.
2. **P2 — Check 2:** [docs/screen_protocol.md:49](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:49) confines overrides to their named families; line 53 expressly limits the benchmark exception to carry.
3. **P2 — Check 3:** [docs/screen_protocol.md:29](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:29) preserves θ=10, cutoffs 20/5, formal α/MDE/n_eff and #88; judge and anchor code are unchanged; coefficient arithmetic is correct.
4. **P2 — Check 4:** [docs/screen_protocol.md:54](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:54), [line 59](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:59) and §3-2 block carry pending resampling-unit/CI-level decisions and xs-carry pending the delay threshold.
5. **P2 — Check 5:** [docs/screen_protocol.md:20](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:20), [line 111](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:111) preserve START-before-new-data and k counting; D4 remains enforced in code; §3-3 and §4-4 P0 text match v2 exactly.
6. **P1 — Check 6:** [docs/screen_protocol.md:35](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:35) interprets [#100:108](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:108)’s “uncorrected coefficient” as uncorrected significance with report-only MDE; naming a confirmation list does not establish confirmation. Other reviewed decisions are faithfully represented.
VERDICT: FIX
```
Both P1 findings are resolved: [line 35](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:35) marks the two MDE readings UNRESOLVED and explicitly blocks every S row until the user chooses. M-1 is exempt.

Commit `74c0151` changes only that line; no other files changed. The working tree is clean, and the diff check passes.

VERDICT: MERGE

