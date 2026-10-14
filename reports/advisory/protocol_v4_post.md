# 스크린 프로토콜 v4 · POST(앵커 후 검토)

- **advisor POST: ACCEPT** · **Codex POST: MERGE** — 앵커 #111(SHA256 d29aa024… · Drive createdTime 2026-10-14T09:51:32.375Z).
- Codex가 지적한 증거 공백(저장소 안에 Drive 확인 영수증 없음)은 아래 "앵커 영수증"으로 닫는다 — #111의 주장은 사실이었고 영수증만 없었다(정정 행 불필요).

## 입장표
| 출처 | 요지 | 입장 |
|---|---|---|
| Codex 1 · 3 · 4 | 해시 · MERGE 판과 바이트 동일 · 원장 머리줄 · PRE 기록 | 확인 |
| Codex 2 | Drive 영수증이 저장소에 없음 | 동의 — 아래에 원문 그대로 |
| Codex 5 · advisor | W4 스펙이 고정할 것(유니버스 · 추정량 · 섞음 · 정규화 · 회전 · 결손 · 주/지연 정렬) | 동의 — W4 스펙 PRE에서 |

## 앵커 영수증(원문 그대로)
- `rclone lsjson --metadata gdrive:BTC_Futures_E2E/screens/screen_protocol_v4_d29aa024.md` 중 필드: `"Size":25152` · `"ModTime":"2026-10-14T09:43:28.887Z` · `"ID":"1Yg0bICGjdR20ZZaTSuZ_s4jRDN5kDBfq` · `"btime":"2026-10-14T09:51:32.375Z`
- `rclone md5sum`: `31ec49841ff3eb5f4b69fcc5708025ef  screen_protocol_v4_d29aa024.md` · 로컬 `md5sum docs/screen_protocol.md` = 31ec49841ff3eb5f4b69fcc5708025ef
- Drive 커넥터 `get_file_metadata`(excludeContentSnippets):
```
{"canAddChildren":false,"createdTime":"2026-10-14T09:51:32.375Z","fileExtension":"md","fileSize":"25152","id":"1Yg0bICGjdR20ZZaTSuZ_s4jRDN5kDBfq","mimeType":"text/markdown","modifiedTime":"2026-10-14T09:43:28.887Z","owner":"(사용자 계정)","parentId":"1qqfI2EINwwjEP20zGs5xiVEKqghxFIor","title":"screen_protocol_v4_d29aa024.md","viewUrl":"https://drive.google.com/file/d/1Yg0bICGjdR20ZZaTSuZ_s4jRDN5kDBfq/view?usp=drivesdk"}
```
(소유자 전자우편은 저장소에 남기지 않으려고 바꿔 적었다 — 그 밖은 그대로.)

## advisor POST — 원문(verbatim)
**Advisor POST for the protocol v4 anchor: ACCEPT.** Hash equals the MERGEd text (diff empty vs 8fe3902), Drive createdTime 09:51:32.375Z confirmed through the connector with MD5 equality, full suite 1,940 / rc 0, ruff and both pyright scopes clean, #111 and the ledger header accurate per Codex. Nothing blocks W4.

Write `reports/advisory/protocol_v4_post.md` now with: this text verbatim; Codex POST verbatim; a position table; and — to close Codex's evidence gap — the raw `get_file_metadata` JSON, the `rclone lsjson --metadata` lines, and the `rclone md5sum` line pasted as-is under a heading "앵커 영수증". No #111 correction is needed: the claim was true, it just lacked a receipt in-repo. The W4 START row can carry "v4 POST: advisor ACCEPT / Codex MERGE" as one clause, same pattern as M-1.

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

## Codex POST — 원문(verbatim)
No merge-blocking defect found at `2a9c7b9`. No files changed.

1. **Protocol identity: PASS.** SHA256 is exactly `d29aa024f73700de303a905916a3f7e971b7792498970e476e7ed8f78cfce2da`. `git diff 8fe3902 HEAD -- docs/screen_protocol.md` is empty; direct byte comparison also passes. MD5 is `31ec49841ff3eb5f4b69fcc5708025ef`; size is 25,152 bytes.

2. **[Registry #111](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:119): consistent.** It is the last row. The v3→v4 differences match #105/#108 and the protocol diff. The frozen spec and START record support the v3+#105+#108 lineage and omission of (가). JSON gross means round to 39.57/177.17, exceeding both hurdles without changing the frozen procedure.

   **Evidence limitation:** Drive ID `1Yg0bICGjdR20ZZaTSuZ_s4jRDN5kDBfq` and createdTime `2026-10-14T09:51:32.375Z` match your supplied values. However, the repo contains no connector receipt independently supporting “connector confirmed” or remote MD5 equality. Local MD5 equality is verified.

3. **[Ledger header](/home/cms/project/BTC_Futures_E2E/docs/screen_registry.md:8): PASS.** It records the correct v4 hash, anchor timestamp, #111 reference, and S-carry-1 lineage. Existing rows remain unchanged.

4. **[PRE trail](/home/cms/project/BTC_Futures_E2E/reports/advisory/protocol_v4_pre.md:16): present.** Full messages labeled verbatim include advisor PRE ACCEPT and Codex r1 FIX → r2 MERGE, plus the P0 advisor POST ACCEPT statement and guard-review pointers. No independent original transcript exists in the repo to authenticate exact transcription. The full-suite log supports 1,940 passes and `rc=0`; fresh Ruff and both project/screen Pyright checks pass.

5. **Before W4:** §7 still requires recording advisor and Codex POST in the currently absent `reports/advisory/protocol_v4_post.md`. W4’s spec must pin a historical, delisted-aware universe, estimator, shuffle construction, normalization, turnover, missingness, and week/lag alignment before START/data reads. No additional user-owned unresolved protocol decision was found.

VERDICT: MERGE
