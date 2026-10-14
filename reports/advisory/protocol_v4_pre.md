# 스크린 프로토콜 v4 · PRE(앵커 전 검토)

- 회전: advisor PRE ACCEPT(초안) → 문구 고침 bf830dd → Codex PRE r1 **FIX**(P1 거래 단위 일반화 · P2 둘) → 고침 8fe3902 → **Codex PRE r2 MERGE**.
- **P0 강화(#105) advisor POST = ACCEPT**(네 항목 존재 · 고치기 전 옛 로더의 경계 처리가 맞음을 확인 · Codex Part A MERGE) — `reports/advisory/w3_carry_pre.md`에는 advisor 판정이 요약으로만 있어 여기 명시한다.
- 가드 변경(#108 `bounded_benchmark_csv`)의 Codex 검토는 `reports/advisory/w3_carry_pre.md`의 PRE r3(Part 2 가드 검토)와 r4 MERGE — W1 가드 기록 사슬.

## 입장표
| 출처 | 요지 | 입장 |
|---|---|---|
| advisor | #105/#108 옮겨 적기 일치 · (가) 1.5 × B는 평이한 읽기 · S-carry-1은 (가)를 평가하지 않았다(공시) · 문구 셋 | 동의 — bf830dd · #111에 공시 |
| Codex r1 P1 | 거래 단위 허용이 일반 예외가 됨 | 동의 — S-carry-1 한정으로 |
| Codex r1 P2 | 7행 낡은 문구 · §4-2 "모든 파일" 범위 | 동의 — 8fe3902 |
| Codex r1 Q2 | 26.25는 승인된 비용 교체에서 나온 값 — 별도 사용자 확인 불필요 · 앞으로만 | 동의 |
| Codex r2 | 전부 RESOLVED · 새 발견 없음 · MERGE | — |

## advisor PRE — 원문(verbatim)
**Advisor PRE for protocol v4: ACCEPT as a draft, pending Codex.** Save this verbatim to the scratchpad now, then into `reports/advisory/protocol_v4_pre.md` (the v4 header already cites that file; it doesn't exist yet). Also record in the same file, explicitly: **advisor POST for the P0 hardening = ACCEPT** (four items present, old loader confirmed boundary-correct before the change, Codex Part A MERGE) — the standing rule wants an advisor verdict on record, and `w3_carry_pre.md` only has mine as a summary.

Transcription check against #105/#108: ①–④, cost-B primary with A/C roles, promotion-uses-B, power-label column, and the file-keyed 10-day benchmark exception all match the user's text. Nothing added.

**(가) → 1.5 × B.** Plain reading, not a new threshold: §3-1 (가) is "≥ 1.5 × 모형 왕복 비용" and #105 made B the model cost for this family. Keep it disclosed; no separate user confirmation needed unless Codex objects. But the related gap you haven't surfaced: **S-carry-1's spec §5 evaluated (나) only — (가) was never in its pass column.** Gross means 39.57 / 177.17 clear both 15 and 26.25, so no verdict changes and no S-row correction is needed, but say so in the v4 POST and in the #111 anchor row ("(가) not evaluated by S-carry-1; satisfied under either threshold; disclosed"). A reviewer comparing v4 §3-1a to the S-carry-1 spec will find it.

Three small text fixes before anchoring (hash isn't fixed yet):
- Line 4 still says "새 판(v2)" — stale.
- §3-1a "가족 상태: carry 가족은 … 닫혔다" is state inside a frozen rule document; phrase it "v4 시점(2026-10-14)" so a reopening row (#8 now lists it as user-only) doesn't force a v5.
- Check that L17/L18 in `learnings.md` sit under a table header row like L16 does; a lone `| L18 | … |` under a `##` won't render as a table.

Anchor sequence once Codex MERGEs (same as v3): run the **full suite first** — your briefing §7 promised it and `window.py` (W1 guard) plus p0 changed since the last full run — ruff, pyright on `research/screens` explicitly (`w3_harness` is outside project pyright; exclude it from that call) → commit → sha → rclone to the folder #101 used (pull the path/file-ID from the #101 row) → `get_file_metadata` createdTime → registry #111 (v4 replaces v3; S-carry-1 ran under v3+#105+#108; (가) disclosure; hardening POST pointer) → append a ledger header line "적용 프로토콜(createdTime 이후 START): v4 …" → Codex POST → `protocol_v4_post.md`. Add one line in the v4 POST pointing to the guard change's Codex review (w3 PRE r3, part 2) so the W1 record chain isn't broken.

Start the full suite in the background now while Codex runs — ~8 minutes, independent.

**W4 orientation only (no reads, no code before MERGE)** — the thing v4 doesn't pin and the W4 spec must: the **universe** for the cross-section. "유니버스 선정에 예약 구간 정보를 쓰지 않는다" (§4-3) plus survivorship means you can't use today's exchangeInfo symbol list. Two candidate rules, decide in the spec PRE: (a) point-in-time from data — a symbol is in the week's universe if its fundingRate archive has rows for that week and it listed ≥ N weeks earlier (listing = first archive row); (b) onboardDate from exchangeInfo, which drops delisted symbols. (a) is the plain choice. Before writing, inventory `binance.vision` `futures/um/monthly/fundingRate/` directory names (names only, nothing opened) to see whether delisted symbols' archives still exist — that fact decides whether (a) is survivorship-free. Weekly spread returns also need per-symbol price data (daily klines suffice); size that download before the spec. Universe size and listing-age are spec details, not θ/α/N — pin them yourself and present in PRE, but expect Codex to probe them.

W5 waits on (A)/(B); nothing to do there.

## Codex PRE r1 — 원문(verbatim)
**P0: none. BLOCK-USER: none. One P1 requires a wording fix before anchoring.**

- **P1 — W3-specific unit permission becomes a general exception.** [#105](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:113) authorizes “trade = unit, … no re-gridding” specifically for W3. [v4](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:58) permits trade units for every carry post-hoc cost sensitivity, while line 55 says “or the unit specified by the spec.” Line 61 bounds the choices but still generalizes W3’s permission. Restrict the trade-unit exception to **S-carry-1**; retain non-overlapping 30-day episodes for ordinary carry screens.

- **P2 — Stale historical wording.** [Line 7](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:7) still says no S row has run under v3. Change this to “at v3 anchoring, no S row had run,” consistent with the following paragraph.

Answers to the five questions:

1. **The four resolved answers and cost hierarchy are faithfully transcribed:** report-only MDE with separate power labels; 60-calendar-day date blocks with episode resampling as sensitivity; two-sided 95% CI with lower bound strictly above zero; and both specified lag-collapse conditions. B/A/C and promotion using B also match. The added freedom is the unit generalization above. #108’s flag and exclusion sensitivity remain in the [S-carry-1 spec](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:18).

2. **26.25 bps is a faithful derived reading.** #105 makes B the carry family’s PRIMARY cost scenario and relegates A to upside sensitivity. Keeping the approved `1.5 × modelled cost` rule therefore gives `1.5 × 17.5 = 26.25`. The numerical cutoff changes, but it follows from the authorized cost substitution; it needs no separate user confirmation. Document it prospectively in v4.

3. **The historical lineage holds.** The [START record](/home/cms/project/BTC_Futures_E2E/docs/screen_registry.md:14) cites v3 + #105 + #108 before calculation. S-carry-1 did not evaluate (가), so avoid implying that it executed every v4 clause. Its reported gross means exceed both hurdles; this does not justify rewriting its frozen decision procedure.

4. **No additional user-owned UNRESOLVED item blocks W4.** Its clauses retain `t ≥ 2`, strict one-sided shuffle-p95 exceedance, both lag-collapse inequalities, `1.5 × weekly turnover cost` at 10 bps per leg per side, and infeasibility above 250 bps leg SD. Keep `t(IC_lag1) < 2` exactly as approved. W4 still needs its committed spec to fix estimator, shuffle construction, normalization, turnover, missingness, and week/lag alignment before START and data reads.

5. **No guard weakening found.** [Implementation](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:140) enforces the DTB3 basename pattern, fixed ten-day lookback, unchanged reserve ceiling, and no widening argument. This authenticates filenames, not file contents; provenance review remains necessary. Qualify §4-2’s “all files” as **files governed by these readers**, preserving the explicit P0 exception in §4-4.

Read-only review; no edits or screen execution.

VERDICT: FIX

## Codex PRE r2 — 원문(verbatim)
Read-only review at HEAD `8fe3902`.

- **RESOLVED — P1 trade-unit generalization:** [lines 55–61](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:55) restrict trade units to S-carry-1 and require non-overlapping 30-day episodes for ordinary carry screens. The 26.25 bps hurdle is explicitly prospective; S-carry-1’s frozen procedure is preserved.
- **RESOLVED — P2 stale line 7:** [line 7](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:7) now correctly describes the state at v3 anchoring.
- **RESOLVED — §4-2 “all files” scope:** [line 98](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:98) limits the claim to files governed by those readers, preserves the P0 exception, and requires provenance review.

**bf830dd adds no freedom.** [Line 4](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:4) retains the new-version, new-registry-row and non-retroactivity requirements. [Line 59](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:59) records carry’s state at v4 time; reopening still requires a user registry row under §8.

The #105/#108 transcription, W4 inequalities, cost hierarchy and historical lineage remain intact. P0 §§3-3 and 4-4 are unchanged.

**NEW findings: P0 none; P1 none; P2 none; BLOCK-USER none.**

No edits or screen execution.

VERDICT: MERGE
