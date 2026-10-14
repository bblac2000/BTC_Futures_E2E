# W5 — 헌법 v1.6 개정안 초안 · POST(완료 후 검토)

- 문서 `docs/proposals/constitution_v1.6_amendment.md` · Codex 문서 r1 FIX → **r2 MERGE**(4d95025) · 회전 원문 `reports/codex/w5_constitution_v16_rounds.md` · advisor POST ACCEPT(초안으로서).
- advisor POST의 충실도 두 항목은 ca09f39에서 고쳤다(사용자 영어 원문 추가 · 출처 1의 원래 줄 바꿈). 문안만 바뀌었고 규칙은 그대로라 Codex를 다시 돌리지 않았다(공시).
- **사용자 판단 대기(Q1)**: Codex 마지막 답 원문 — "Q1: **YES** — lines 13, 16, and 31 affect first-fill SL arming, entry invalidation and racing-fill cleanup, and research P1 SL inheritance; exits remain immediate MARKET reduceOnly." · Claude Code의 읽기: 31행(P1 SL 승계)은 연구 규칙이지 주문 경로가 아니다 · 나머지 둘(첫 체결 SL · 청산 뒤 진입 주문 취소)을 빼면 놓여 있던 GTX가 SL 뒤에 체결돼 노출을 다시 여는 길이 생긴다 — 선택은 "이 접촉을 받아들인다" 대 "GTX 진입을 아예 하지 않는다"다.
- 병합 뒤 저장소 영향(문서 밖 · 지금 코드 0): CLAUDE.md 하드 규칙 "MARKET only" · `exchange/orders.py`의 주문 유형 검증과 그 시험 · `tests/test_no_exchange_literals.py` 범위 · LIMIT 경로가 생기면 전송 고정 #8.

## advisor POST — 원문(verbatim)
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


## 마감(2026-10-14) — r3 → r5
- 초안 r3(#105 · GTX 삭제 · 현물 1 · 2 복원) → Codex 문서 r3 **BLOCK**(#106) → 사용자 #107 → r4 → Codex r4 **BLOCK-USER**(#109) → 사용자 #113: (B)이지만 조건부 범위 축소(carry 가족 닫힘 확인) → **r5 최소 묶음** → **Codex r5 MERGE**(#114).
- 회전 원문: `reports/codex/w5_constitution_v16_rounds.md`(r3 · r4 · r5 절) · 전체 로그 `w5_constitution_v16_r3_full_log.txt` · `_r4_full_log.txt`.
- 병합 · 배포는 사용자(마스터 zip) — 그 전까지 D5(주문 0) 유효.

### advisor POST(r5) — 원문(verbatim)
**Advisor POST for v1.6 r5: ACCEPT.** Scope-cut condition verified from the ledger (S-carry-1 RESULT/POST, #110, L18); r5 contains exactly the three items the user named; nothing operative touches order types, exits, SL/TP, kill-switch, margin or spot; Codex MERGE with no findings; the one open point (independent Last-Modified check on source 2) is already disclosed in the draft as an evidence limitation and does not block. Save this verbatim, then append a closing section to the existing `reports/advisory/w5_constitution_v16_post.md` (it still ends at doc r2): r3 → #106 BLOCK, r4 → #109 BLOCK-USER, r5 → #114 MERGE, advisor POST ACCEPT, pointer to the rounds file. Without that, the `_post.md` for W5 describes a draft that no longer exists.
