# W4 · S-xs-carry-1 POST(완료 후 검토)

- 대상: S-xs-carry-1 RESULT · 실행 커밋 af665b1(코드 = 코드 검토 r4 MERGE 03095f2와 같음 — 그 사이 바뀐 것은 내려받기 로그와 목록뿐) · 결과 JSON `d81e9c3c…`.
- **advisor POST: ACCEPT WITH NOTES** · **Codex POST: ACCEPT WITH NOTES**(독립 구현으로 숫자 75개 재현 · 최대 차 2.84e−14 · 6주 적격 집합 일치 · 판정 불변).
- 동결 산출물(JSON · 로그)은 고치지 않는다.

## 입장표(Claude Code)
| 출처 | 요지 | 입장 |
|---|---|---|
| Codex 1 · advisor | 한 번의 실행 · MERGE 코드와 같음 | 확인(`git diff --stat 03095f2..af665b1 -- research tests` = 로그 · 목록뿐) |
| Codex 2 | 독립 재계산 일치 | 확인 |
| **Codex 2 P2** | 신호 합의 부동소수 오차가 같은 소수 합(예 0.0021)을 다른 순위로 가른다 — 정수(10⁻⁸) 합으로 하면 순위 125주 · 다리 구성 52주가 바뀐다 · 진단값: IC 0.02272(t 3.19) · 지연 IC 0.01903(t 2.78) · 총/순 64.01/43.21 bps · 다리 sd 1,094.0/1,119.2 — **두 기각 사유(다리 sd > 250 · 지연 무너짐 불충족) 모두 그대로** · 주 하나의 최대 차 345.9 bps | 동의 — 공시. 동결 결과는 그대로. **다음 승인된 실행 전에** 신호를 정확한 10진(정수 10⁻⁸) 합으로 순위 매기고 주기가 다른 같은 합의 회귀 시험을 둔다(코드 변경 없음 · 기록만) |
| Codex 3 | RESULT 행 숫자 정확(0.5 × IC_0 = 0.0111569606 반올림 0.0112) | 확인 |
| Codex 4 · advisor 2 | 해석을 낮출 것: "펀딩 지속성과 부합 · 가격만 IC는 평균 단조 신호를 찾지 못함 · 한 주 지연에 IC의 83.7% 유지(16.3% 감소)" · Spearman(S₀, F) 0.603 · Spearman(S₀, S₁) 0.618 | 동의 — POST 행 · L19 · 브리핑 |
| advisor 1 | 달러 스프레드는 유의하지 않다 — 순 41.09 · sd 755.2 · n 281 → t ≈ 0.91 | 동의 — IC t 옆에 적는다 |
| advisor 2 | 분해가 핵심: 펀딩 +109 · 가격 −47(2024-07 ~: +165 · −280) — 펀딩이 높은 이름이 가격으로 펀딩보다 더 올랐다 | 동의 |
| advisor 3 | 250 bps 조항은 헤지 없는 알트코인 다리에서 구조적으로 걸린다(스프레드 sd 755도) — 바꾸려면 사용자만(프로토콜 변경 · 새 S id) | 동의 — 브리핑 §5에 알림만 |
| advisor 4 | 격자 밖 8,084는 더했고(2024–25 주기 변경) 빠진 7,091은 더하지 않았다 · 펀딩 결손 이름-주 602 ≈ 전체의 1% · 제외 민감도로 IC 변화 0.0005 | 동의 — 공시 |
| advisor 5 | 판정 표기: "실행 불가"가 판정 · "③도 불충족"은 덧붙임 | 동의 — POST 행 |
| advisor 6 | xs-carry 가족의 처분은 미리 정해져 있지 않다 — "닫힘"을 쓰지 않고 사용자 결정으로 | 동의 |
| Codex 5-4 | 커밋 778868c 설명의 "IC t 3.13 > null p95"는 "평균 IC > null p95"가 맞다 | 동의 — 여기서 정정 |

## advisor POST — 원문(verbatim)
**Advisor POST for S-xs-carry-1: ACCEPT WITH NOTES** — conditional on `git diff --stat 03095f2..af665b1 -- research tests` showing no code (run it yourself now; don't wait on Codex for that one line). Save this verbatim to the scratchpad first, then into `reports/advisory/w4_xs_carry_post.md`.

Nothing threatens the verdict: leg sd 1,093 / 1,111 bps is 4.4× the 250 bps clause, and an equal-weight decile of ~20 altcoin perps at weekly horizon plausibly carries ~11% weekly sd — no unit bug is indicated. ③ failing independently makes the row FAIL under either reading.

Items your checks didn't cover — all belong in the POST file and the briefing:

1. **The dollar spread is not significant; only the IC is.** mean_net 41.09, sd_net 755.2, n 281 → t ≈ 0.91 (se ≈ 45 bps). The cost clause passes on means, but a reader who sees "IC t 3.13" and "(가) ✓" will infer a significant edge. State the spread t next to the IC t.

2. **The decomposition is the finding.** Funding part +109 bps/week, price part −47; since 2024-07 funding +165, price −280. High-funding names *outperformed in price by more than the funding collected*. Say it in one sentence in the briefing — it's the economic content, and it's consistent with price-only IC ≈ 0 and the lag IC not decaying (persistence, not prediction).

3. **The 250 bps clause binds by construction for any unhedged altcoin leg.** That's a #100 rule and it stands. But flag in §5 of the briefing that no weekly cross-section of USDT perps can pass it as written (spread sd 755 also fails it); if the user wants the family explored further, it's a protocol change and a new S id — user-only, not something you propose.

4. **Off-grid settlements 8,084 and missing 7,091 need one explanatory line.** Off-grid were *added* (cadence changes to 4h/1h in 2024–25), missing were *not*; funding-deficit name-weeks are 602 of ~58k (≈1%) and the exclusion sensitivity moves IC by 0.0005. Disclose the counts with that framing. A read-only diagnostic of where the off-grid settlements concentrate by year is fine for the POST file; no rerun.

5. **Verdict label.** The RESULT row says "실행 불가(FAIL)". Spec §6 has three labels; use "실행 불가" as the verdict and "③ 또한 불충족" as a clause, so it doesn't read as two verdicts. Clarify in the POST row, don't edit RESULT.

6. **Family disposition is not pre-committed for xs-carry.** Unlike carry (#100 had a close rule), nothing says this family closes on one FAIL. Write L19 as the finding (k = 1, 실행 불가, IC = funding persistence, spread t 0.9, price adverse since 2024-07) and leave "close / keep open" as a user decision in §5. Don't write "닫힘".

7. **Codex's number recomputation**: if it reproduces IC/spread/leg sd within rounding, close `promoted? = no`. If it finds a bug in turnover or leg sd that changes numbers, stop and report before learnings — but given the margin, expect notes, not a reversal.

Then: POST row + L19 + registry #112 → **briefing** (user asked for one after W4). §5 must carry three decisions: W5 (A)/(B) with your recommendation stated once; xs-carry disposition (item 6); `var/p2_archive` (157 MB, reproducible from the manifest) delete or keep. Update the screens-round memory state line after the briefing.

## Codex POST — 원문(verbatim · 최종 메시지)
The recorded run is reproducible, and **실행 불가 remains the correct verdict**. I found one non-verdict-changing numerical defect in signal ties and wording that needs qualification. Reviewed HEAD `85a2726` read-only; no files changed.

**1. Single result-producing execution**

The repository evidence supports **one recorded successful execution at the MERGEd code**:

- `03095f2..af665b1 -- research tests` adds only the fetch log and manifest. Relevant code, tests, and window guard remain unchanged through HEAD.
- START was committed at 10:50:00Z; fetch began at 10:50:06Z and ended at 10:56:55Z.
- The [run log](/home/cms/project/BTC_Futures_E2E/research/screens/p2/S-xs-carry-1_run.log:1) records HEAD `af665b1`, 10:57:05Z–10:58:30Z, rc 0. Timing stderr independently reports exit 0 and 85.43 seconds.
- The JSON first appears in `778868c`. `write_result` uses exclusive creation.

This establishes the recorded execution and committed code identity. Logs and Git cannot independently prove the absence of unrecorded executions or transient working-tree edits; I found no evidence of either.

All **37,649 archive hashes** match the manifest; its entries exactly match the JSON inventory. No extra ZIPs or failure markers exist. Spec, protocol, benchmark, manifest, JSON, and table hashes match their recorded values.

**2. Independent recomputation**

I wrote a separate archive parser and calculation implementation, without using production calculation functions. It read 2,378,916 funding records and 573,249 daily bars.

Using the runner’s sequential signal summation, **75 scalar numeric fields matched the [JSON](/home/cms/project/BTC_Futures_E2E/research/screens/p2/results/S-xs-carry-1.json), with maximum absolute difference `2.84e-14`**. Count distributions and diagnostics also matched.

| Statistic | Independently reproduced |
|---|---:|
| IC mean / t | 0.0223139213 / 3.1271740 |
| Seeded null p95 / mean | 0.0069902523 / −0.0000399364 |
| Lag IC / t | 0.0186689275 / 2.7284667 |
| Matched-sample IC₀ | 0.0221608470 |
| Price-only IC / t | −0.0023113536 / −0.3192576 |
| Gross / cost / net, bps | 61.824809 / 20.730568 / 41.094241 |
| Mean traded notional, both legs | 2.0730567575 |
| Price / funding contribution, bps | −47.440993 / 109.265802 |
| Long / short weekly SD, bps | 1093.201057 / 1111.049176 |
| MDE, coefficients 2.80 / 4.00 | 159.559851 / 227.942645 |
| Recent-window gross / net, bps | −114.906669 / −132.265618 |

Independent weekly examples:

| Week | Eligible | IC | Gross bps | Turnover |
|---|---:|---:|---:|---:|
| 2021-02-08 | 81 | 0.014137 | 1500.757 | 2.000000 |
| 2021-02-15 | 81 | 0.092796 | −59.037 | 2.784875 |
| 2022-11-07 | 149 | 0.014815 | −757.342 | 2.103123 |
| 2022-11-14 | 147 | −0.174048 | 803.985 | 2.216646 |
| 2024-07-01 | 277 | −0.103476 | −754.269 | 1.390405 |
| 2026-06-22 | 556 | −0.029604 | −517.678 | 3.668190 |

For these six weeks, eligibility **sets**, not just counts, exactly match production. Exclusion sensitivities, benchmark, recent-window statistics, and diagnostics—119 early exits, 602 funding-deficit name-weeks, 7,091 missing slots, eight collisions, 8,084 off-grid settlements—also reproduce. **43 read-only tests passed; 14 requiring filesystem writes were deselected.**

**New P2: floating-point summation splits economically exact ties.** [Signal accumulation](/home/cms/project/BTC_Futures_E2E/research/screens/p2/compute.py:78) can represent the same decimal sum `0.0021` as `0.002099999999999999` or `0.0021000000000000003`. Exact-float ranking then treats these differently.

Summing signals in integer `10⁻⁸` units—all archive rates have at most eight decimal places—changes ranks in **125 weeks** and leg membership in **52 weeks**. This diagnostic gives:

- IC 0.02272253; t 3.19196.
- Lag IC 0.01902841; t 2.78187.
- Gross/net 64.00912/43.21220 bps.
- Long/short SD 1094.04/1119.19 bps.

Both rejection grounds remain intact. The largest individual-week gross difference is **345.89 bps**, so this deserves disclosure despite the small aggregate change.

**3. RESULT-row accuracy**

Every displayed numerical value in the [RESULT row](/home/cms/project/BTC_Futures_E2E/docs/screen_registry.md:20) agrees with the frozen JSON at its stated precision. Dates, counts, hashes, and the LENDUSDT explanation also check out.

The rounded half-IC threshold `0.0112` is correct; its unrounded value is `0.0111569606`. No numerical ledger correction is required **for the recorded implementation**.

**4. Interpretation and likely reviewer objections**

Funding persistence is a **well-supported interpretation**, but the categorical attribution is too strong. Additional independent diagnostics give mean `Spearman(S₀,F)` **0.602825** and matched `Spearman(S₀,S₁)` **0.617742**.

A second reviewer would reasonably object that:

- Near-zero price-only IC shows no detected average monotonic price signal; it does not establish absent price predictability. Spearman ICs cannot be additively decomposed.
- Lag IC retains **83.66%** of original IC—about **16.34% decay**. “Almost unchanged” should be quantified.
- Persistent cross-sectional differences can explain these correlations; the diagnostics do not uniquely identify a causal mechanism.
- Ordinary t statistics ignore serial dependence, and independent weekly shuffles break temporal dependence, as already disclosed.
- Exact ties affect ranks and portfolios. Early-exit proxy prices and fixed-notional funding remain modeling limitations.

The leg SDs exceed the threshold by **4.37× and 4.44×**. Lag collapse fails both inequalities. I found no bug that changes either conclusion.

**5. Required corrections**

1. Qualify the interpretation in the ledger and [result table](/home/cms/project/BTC_Futures_E2E/research/screens/p2/results/S-xs-carry-1.md:24):  
   “The diagnostics are consistent with funding persistence; price-only IC shows no detected average monotonic signal. One-week lag retains 83.7% of IC.”
2. Append the decimal-tie finding and diagnostic sensitivity to POST. Preserve the frozen JSON and hash.
3. Before another authorized result-producing run, use exact decimal signal sums for ranking and add a regression covering equal sums across funding cadences.
4. Clarify the `778868c` commit-description typo in POST: **IC mean**, rather than IC t, is compared with null p95.

**ACCEPT WITH NOTES**
