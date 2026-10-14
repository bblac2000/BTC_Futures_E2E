# W3 · S-carry-1 POST(완료 후 검토)

- 대상: S-carry-1 RESULT(`docs/screen_registry.md`) · 실행 커밋 6f974aa · 결과 커밋 1a1bdfe · 결과 JSON `c27121855ee2aa2d…`.
- **advisor POST: ACCEPT WITH NOTES** · **Codex POST: ACCEPT WITH NOTES**(322개 숫자 독립 재계산 일치 · 최대 차 4.27e−14 · 재실행 불필요 · 문서 정정만).
- 동결 산출물(JSON · 로그)은 고치지 않는다. 정정은 POST 행 · 이 파일 · `S-carry-1.md`(JSON에서 만든 표)로.

## 입장표(Claude Code)
| 출처 | 요지 | 입장 |
|---|---|---|
| Codex 1 · advisor 6 | 파싱 고침이 MERGE 뒤 유일한 코드 변경 · 202행 전 칸이 csv.reader와 일치 · 스키마 한정 파서 | 확인 — 공시 |
| Codex 2 | 스펙 §6의 `.md` 결과 없음 | 동의 — JSON에서 만들어 추가(`S-carry-1.md` · 578bba07…) |
| Codex 3 · advisor 2 | RESULT 행 숫자 정확 · sd(net_B)가 행에 없음 | 동의 — POST 행 첫 숫자로 |
| Codex 4 · advisor 5 | G1 부분 구간 블록 CI 퇴화 — 폭 0은 정밀함이 아니다 · 처분은 점 추정이라 불변 | 동의 — `.md` · POST 행 |
| Codex 5 | "장세 의존"은 단정이 아니다(창 차이 검정 없음) | 동의 — "최근 창 추정이 음수 · 장세 의존과 부합"으로 낮춤 |
| Codex 5 | 사후 효과 통과는 독립 발견 증거가 아니다 · 장부 n MDE는 미래 검정력이 아니다 · 진입 기준 블록의 한계 | 동의 — 공시 |
| Codex 5 | PRE 기록이 r3 FIX에서 끝남 | 동의 — r4 MERGE 원문 덧붙임 |
| advisor 1 | G1 효과 판정은 고정된 비용(B)과 재표본 단위(60일)에 달림 — A 블록 CI · B 거래 독립 CI는 하한 > 0 | 동의 — `.md` · 브리핑 |
| advisor 3 | learnings: 효과 부재가 아니라 검정력 불가 + 최근 창 음수 | 동의 — L18 |
| advisor 4 | 히스테리시스 2024-07 이후: DTB3 85.72 bps > gross 79.30 — 비용 전에도 단기채를 못 넘음 | 동의 — 브리핑 |
| advisor 7 | carry k = 1 · promoted? = no | 동의 — POST 행 |

## advisor POST — 원문(verbatim)
You're at POST for S-carry-1 with the result committed and ledgered. **Advisor POST: ACCEPT WITH NOTES** — conditional on Codex confirming `git diff aedcd4e..6f974aa` is the parse fix alone. Save this text verbatim into the scratchpad now, then into `reports/advisory/w3_carry_post.md`. Last time you saved a summary and had to disclose it; don't repeat that.

Nothing in the output threatens the verdict. Items your checks didn't cover:

1. **Two pre-committed choices each flip G1's effect column — say so.** G1 under A−DTB3 is [4.19, 62.68]; G1 under trade-iid B−DTB3 is [4.32, 40.10]. Both would pass. B-primary (#105) and 60-day blocks (#105 ②) were fixed before any computation, so "effect fail" stands, but a reviewer who reads the sensitivity cells and the verdict cell will ask. State it in the POST file and the briefing: "G1's effect verdict depends on the pre-committed cost scenario and resampling unit; both fixed in #105 before the ledger was read."

2. **sd(net_B) is missing from the RESULT row.** The user's step 4 says "sd of net_B per trade printed first." It's in the JSON (81.29 / 158.23) but not in the ledger. Put it in the POST row as the first number, and lead the briefing table with it.

3. **Learnings classification.** The close is pre-committed (#100, spec §5) so it needs no new approval — but the constitution distinguishes 검정력 부족 from 효과 부재, and neither arm is 효과 부재: hysteresis full-window CI is strictly positive, G1 straddles zero; both MDEs ≫ 20. Write L18 as "carry family closed — power infeasible (MDE 43.6 / 180.9 uncorrected) with regime concentration (hysteresis +145 bps avg on the 15 pre-2024-07 trades, −23.9 on the 9 after), not absence of effect." Note the user can reopen with a registry row.

4. **The sub-window finding in plain language.** Hysteresis 2024-07+: DTB3 85.72 bps vs gross 79.30 — the hedge no longer covers the T-bill at 2024–26 rates even before costs. That's the sentence the briefing needs, not the sign of a mean.

5. **Degenerate G1 sub-window CI.** Correctly disclosed; add that the trade-iid interval [−13.33, −5.05] is the informative one for that window and the block interval is uninformative by construction (11 trades, one block).

6. **Parse fix after MERGE.** Disclosed, correction row written, Codex POST checking. Acceptable. If Codex reports anything in that diff beyond `_trade` and its test, stop and report before writing learnings.

7. **k counter.** S-carry-1 is the first S row; carry k = 1. The POST row should say so and close `promoted? = no`.

Then, in the user's order: POST row + L18 + registry row → **briefing** (W3 is done; the user asked for one here) → v4 protocol PRE with the four #105 answers, cost-B clause, and the #108 benchmark exception → W4. W5 waits on the (A)/(B) answer from #109; put that decision in the briefing's §5 with your recommendation stated once.

## Codex POST — 원문(verbatim · 최종 메시지)
The numerical result and family-closure decision are sound. I found documentation issues, but no calculation error. Reviewed HEAD `663f0e9` read-only; no files changed.

1. **Parse fix: correct for this frozen ledger.** At [loader.py:31](/home/cms/project/BTC_Futures_E2E/research/screens/p1/loader.py:31), `split(",", 13)` preserves the first 13 fields, and `rsplit(",", 1)` separates the final `forced` field from the comma-containing reason.

   I compared all 15 parsed columns against Python’s `csv.reader` for **all 202 retained rows**, including 18 comma-containing reasons: every column matched. The two excluded rows are filtered by exit timestamp before `_trade` runs.

   `git diff aedcd4e..6f974aa -- research tests` contains exactly:
   - This parser change.
   - Its regression test.
   - The crash log.

   Thus it is the **only production-code change**; the literal diff also contains those supporting artifacts. Outside that scope, the registry gained START/correction rows. Spec, repricing and statistical logic remained unchanged.

   This is a schema-specific parser, not a general CSV parser. Quoted numeric fields, commas in `run`, multiline fields, or malformed extra columns could fail or be swallowed into the unused reason. None occurs in the retained frozen ledger. No parser correction is required for this result.

2. **JSON: computationally faithful to r3.** I independently reconstructed every result field, including both report-only runs: **322 numeric leaves matched**, with maximum absolute difference `4.27e−14`; flags and other fields matched exactly.

   Checks covered cost replacement, `locked = 1.6 × notional`, elapsed milliseconds/365-day scaling, preceding DTB3 observations, flags/exclusion sensitivity, entry-based windows and blocks, fresh seeded generators, accepted-draw counts, both bootstrap methods, sample SD, lag correlation, MDE and promotion conditions.

   Selected independent calculations, in bps:

   | Arm / entry | DTB3 observation / annual % | Gross | net_B | DTB3 cost | net_B − DTB3 |
   |---|---|---:|---:|---:|---:|
   | G1 / 2021-01-01 | 2020-12-31 / 0.09% | 11.581072 | −5.918928 | 0.039452 | −5.958380 |
   | G1 / 2021-01-02 | 2020-12-31 / 0.09% | 293.152982 | 275.652982 | 0.315616 | 275.337366 |
   | Hysteresis / 2022-09-11 | 2022-09-09 / 2.98% | 248.853723 | 231.353723 | 219.458630 | 11.895093 |
   | Hysteresis / 2024-09-17 | 2024-09-17 / 4.75% | 110.403406 | 92.903406 | 113.132420 | −20.229014 |

   For example, the first G1 trade uses gross USDT `0.1324884591 + 0.0842502524`, notional `187.1490954460`, and almost exactly one elapsed day. Both January entries correctly use December 31, avoiding the January 4 future observation.

   **Reporting deviation:** [spec §6](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:55) promises `{json,md}`; the Markdown result is absent.

3. **RESULT row: every numerical claim checked is accurate.** The [RESULT row](/home/cms/project/BTC_Futures_E2E/docs/screen_registry.md:16) agrees with the JSON at its stated rounding, including counts, means, CIs, MDEs, sensitivity values, benchmark means, correlations and redraws.

   | Promotion input | G1 | Hysteresis |
   |---|---:|---:|
   | Full n | 77 | 24 |
   | Full B − DTB3 mean | 19.96 | 81.66 |
   | Block 95% CI | [−3.31, 55.18] | [17.95, 157.60] |
   | Uncorrected MDE | 43.58 | 180.92 |
   | N-corrected MDE | 62.26 | 258.45 |
   | Sub-window n / mean | 11 / −9.49 | 9 / −23.92 |
   | Promotion conditions | false / false / false | true / false / false |

   The result SHA256 matches `c2712185…`; input/spec/harness hashes also match their recorded values. The successful log contains exactly the saved JSON, identifies `6f974aa`, and records `rc=0`. The crash occurred during initial loading, before rates, repricing, statistics or output creation. “One successful result-producing run” is substantiated.

4. **Degenerate G1 sub-window CI: correctly reported.** All 11 entries, November 10–December 7, occupy block 2: **[2024-10-29, 2024-12-28)**. Of 13 calendar blocks, only that block contains trades.

   Every accepted draw therefore repeats the same 11-trade collection and has the same mean. The tiny endpoint difference in JSON is floating-point rounding. I reproduced **570 rejected empty draws plus 1,000 accepted draws**, separately for A/B/C.

   The interval measures no between-occupied-block uncertainty here. Its zero width must not imply precise estimation. The reported IID sensitivity `[−13.33, −5.05]` is correctly computed, but assumes independent trades. Promotion uses the sub-window **point estimate**, so this degeneracy does not change the disposition.

5. **Closure: correct under #100 as clarified by #105 and spec §5.** G1 fails all three conditions; hysteresis passes the full-window effect condition but fails the sub-window mean and corrected-MDE conditions. Neither qualifies for consideration of a new formal preregistration. Closing the carry family in learnings follows [spec §5](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:45).

   A second reviewer could reasonably object to:
   - **“Regime dependent” as a firm finding.** Hysteresis’s sub-window CI includes zero; no regime-effect or window-difference test was performed. “Negative recent-window estimate, consistent with regime dependence” is supported.
   - Treating the post-hoc effect pass as independent discovery evidence, or observed-sample MDE as demonstrated future power.
   - Entry-based blocks assigning long trades wholly to one block despite exposure spanning multiple blocks. This is the frozen method’s limitation.
   - Missing provenance: the cited [PRE report](/home/cms/project/BTC_Futures_E2E/reports/advisory/w3_carry_pre.md) ends at **r3 FIX**, without the r4 MERGE record referenced by START.

Verification also passed all **13 carry tests** with memory-only file fixtures and five relevant guard/static checks.

Required corrections, through appended documentation while preserving the frozen JSON and logs:

- Supply the promised Markdown result from the existing JSON, with the sparse-block caveat and `sd(net_B)` displayed as specified.
- Soften the regime-dependence claim.
- Append or link the actual PRE r4 MERGE evidence.
- Record POST acceptance and the carry-family closure in learnings; finalize `promoted? = no`.

**ACCEPT WITH NOTES — documentation corrections required; no numerical correction or rerun required.**

## Codex POST — 실행 로그 전체
```
[codex] Starting Codex task thread.
[codex] Thread ready (01a139c1-0619-7e80-9f1f-e59a56acbf82).
[codex] Turn started (01a139c1-084a-7d10-8a38-1e1c6fc97ee5).
[codex] Assistant message captured: I’ll review the parse-fix diff, trace the result back to the ledger and DTB3 data, and check ...
[codex] Running command: /bin/bash -lc "pwd; git status --short; rg --files -g AGENTS.md -g '*carry*' -g '*DTB3*' -g '...
[codex] Command completed: /bin/bash -lc "pwd; git status --short; rg --files -g AGENTS.md -g '*carry*' -g '*DTB3*' -g '... (exit 0)
[codex] Running command: /bin/bash -lc 'cat /home/cms/.codex/skills/karpathy-guidelines/SKILL.md'
[codex] Command completed: /bin/bash -lc 'cat /home/cms/.codex/skills/karpathy-guidelines/SKILL.md' (exit 0)
[codex] Running command: /bin/bash -lc "rg --files -g AGENTS.md -g '*stats*' research/screens/p1; git log -8 --oneline...
[codex] Command completed: /bin/bash -lc "rg --files -g AGENTS.md -g '*stats*' research/screens/p1; git log -8 --oneline... (exit 0)
[codex] Running command: /bin/bash -lc 'cat research/screens/p1/loader.py research/screens/p1/reprice.py research/scre...
[codex] Command completed: /bin/bash -lc 'cat research/screens/p1/loader.py research/screens/p1/reprice.py research/scre... (exit 0)
[codex] Running command: /bin/bash -lc 'cat research/screens/p1/results/S-carry-1.json; cat research/screens/p1/S-carr...
[codex] Command completed: /bin/bash -lc 'cat research/screens/p1/results/S-carry-1.json; cat research/screens/p1/S-carr... (exit 0)
[codex] Running command: /bin/bash -lc 'for p in /AGENTS.md /home/AGENTS.md /home/cms/AGENTS.md /home/cms/project/AGEN...
[codex] Command completed: /bin/bash -lc 'for p in /AGENTS.md /home/AGENTS.md /home/cms/AGENTS.md /home/cms/project/AGEN... (exit 0)
[codex] Running command: /bin/bash -lc 'cat tests/test_screen_p1_carry.py; cat research/screens/window.py; cat researc...
[codex] Command completed: /bin/bash -lc 'cat tests/test_screen_p1_carry.py; cat research/screens/window.py; cat researc... (exit 0)
[codex] Running command: /bin/bash -lc "rg -n '#100|#105|#108|carry 가족|carry family|S-carry-1' docs research/screens/w...
[codex] Command completed: /bin/bash -lc "rg -n '#100|#105|#108|carry 가족|carry family|S-carry-1' docs research/screens/w... (exit 0)
[codex] Running command: /bin/bash -lc "tail -n 5 docs/screen_registry.md; sed -n '112,114p' docs/trial_registry.md"
[codex] Command completed: /bin/bash -lc "tail -n 5 docs/screen_registry.md; sed -n '112,114p' docs/trial_registry.md" (exit 0)
[codex] Running command: /bin/bash -lc 'cat tests/test_screen_p1_carry.py'
[codex] Command completed: /bin/bash -lc 'cat tests/test_screen_p1_carry.py' (exit 0)
[codex] Running command: /bin/bash -lc 'cat research/screens/window.py'
[codex] Command completed: /bin/bash -lc 'cat research/screens/window.py' (exit 0)
[codex] Running command: /bin/bash -lc 'cat research/screens/w3_harness/carrybot_ledger.py'
[codex] Command completed: /bin/bash -lc 'cat research/screens/w3_harness/carrybot_ledger.py' (exit 0)
[codex] Running command: /bin/bash -lc "rg --files reports | rg 'w3_carry|carry.*pre'; cat pyproject.toml; ls -ld .ven...
[codex] Command completed: /bin/bash -lc "rg --files reports | rg 'w3_carry|carry.*pre'; cat pyproject.toml; ls -ld .ven... (exit 0)
[codex] Assistant message captured: The diff shows one code change—the parser fix—plus its regression test, crash log, and regist...
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY' import csv, dataclasses...
[codex] Command completed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY' import csv, dataclasses... (exit 0)
[codex] Running command: /bin/bash -lc "cat reports/advisory/w3_carry_pre.md; cat research/screens/p1/data/carrybot_re...
[codex] Command completed: /bin/bash -lc "cat reports/advisory/w3_carry_pre.md; cat research/screens/p1/data/carrybot_re... (exit 0)
[codex] Running command: /bin/bash -lc 'cat tests/test_screen_window.py; git diff --name-status aedcd4e..HEAD -- resea...
[codex] Command completed: /bin/bash -lc 'cat tests/test_screen_window.py; git diff --name-status aedcd4e..HEAD -- resea... (exit 0)
[codex] Running command: /bin/bash -lc "rg -n '"'^def test_|''^## Codex PRE r4|''^## 6|결과 `|장세 의존|'"\\| S-carry-1' tes...
[codex] Command completed: /bin/bash -lc "rg -n '"'^def test_|''^## Codex PRE r4|''^## 6|결과 `|장세 의존|'"\\| S-carry-1' tes... (exit 0)
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY' import inspect,io,runpy...
[codex] Command completed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY' import inspect,io,runpy... (exit 0)
[codex] Assistant message captured: The independent rebuild matched all JSON fields, including 322 numeric values, to floating-po...
[codex] Running command: /bin/bash -lc "rg -n 'PRE r4|r4 MERGE|VERDICT: MERGE|VERDICT.*MERGE|aedcd4e' reports/advisory...
[codex] Command completed: /bin/bash -lc "rg -n 'PRE r4|r4 MERGE|VERDICT: MERGE|VERDICT.*MERGE|aedcd4e' reports/advisory... (exit 0)
[codex] Running command: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY' import csv,datetime as ...
[codex] Command completed: /bin/bash -lc "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY' import csv,datetime as ... (exit 0)
[codex] Assistant message captured: The numerical result and family-closure decision are sound. I found documentation issues, but...
[codex] Turn completed.
The numerical result and family-closure decision are sound. I found documentation issues, but no calculation error. Reviewed HEAD `663f0e9` read-only; no files changed.

1. **Parse fix: correct for this frozen ledger.** At [loader.py:31](/home/cms/project/BTC_Futures_E2E/research/screens/p1/loader.py:31), `split(",", 13)` preserves the first 13 fields, and `rsplit(",", 1)` separates the final `forced` field from the comma-containing reason.

   I compared all 15 parsed columns against Python’s `csv.reader` for **all 202 retained rows**, including 18 comma-containing reasons: every column matched. The two excluded rows are filtered by exit timestamp before `_trade` runs.

   `git diff aedcd4e..6f974aa -- research tests` contains exactly:
   - This parser change.
   - Its regression test.
   - The crash log.

   Thus it is the **only production-code change**; the literal diff also contains those supporting artifacts. Outside that scope, the registry gained START/correction rows. Spec, repricing and statistical logic remained unchanged.

   This is a schema-specific parser, not a general CSV parser. Quoted numeric fields, commas in `run`, multiline fields, or malformed extra columns could fail or be swallowed into the unused reason. None occurs in the retained frozen ledger. No parser correction is required for this result.

2. **JSON: computationally faithful to r3.** I independently reconstructed every result field, including both report-only runs: **322 numeric leaves matched**, with maximum absolute difference `4.27e−14`; flags and other fields matched exactly.

   Checks covered cost replacement, `locked = 1.6 × notional`, elapsed milliseconds/365-day scaling, preceding DTB3 observations, flags/exclusion sensitivity, entry-based windows and blocks, fresh seeded generators, accepted-draw counts, both bootstrap methods, sample SD, lag correlation, MDE and promotion conditions.

   Selected independent calculations, in bps:

   | Arm / entry | DTB3 observation / annual % | Gross | net_B | DTB3 cost | net_B − DTB3 |
   |---|---|---:|---:|---:|---:|
   | G1 / 2021-01-01 | 2020-12-31 / 0.09% | 11.581072 | −5.918928 | 0.039452 | −5.958380 |
   | G1 / 2021-01-02 | 2020-12-31 / 0.09% | 293.152982 | 275.652982 | 0.315616 | 275.337366 |
   | Hysteresis / 2022-09-11 | 2022-09-09 / 2.98% | 248.853723 | 231.353723 | 219.458630 | 11.895093 |
   | Hysteresis / 2024-09-17 | 2024-09-17 / 4.75% | 110.403406 | 92.903406 | 113.132420 | −20.229014 |

   For example, the first G1 trade uses gross USDT `0.1324884591 + 0.0842502524`, notional `187.1490954460`, and almost exactly one elapsed day. Both January entries correctly use December 31, avoiding the January 4 future observation.

   **Reporting deviation:** [spec §6](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:55) promises `{json,md}`; the Markdown result is absent.

3. **RESULT row: every numerical claim checked is accurate.** The [RESULT row](/home/cms/project/BTC_Futures_E2E/docs/screen_registry.md:16) agrees with the JSON at its stated rounding, including counts, means, CIs, MDEs, sensitivity values, benchmark means, correlations and redraws.

   | Promotion input | G1 | Hysteresis |
   |---|---:|---:|
   | Full n | 77 | 24 |
   | Full B − DTB3 mean | 19.96 | 81.66 |
   | Block 95% CI | [−3.31, 55.18] | [17.95, 157.60] |
   | Uncorrected MDE | 43.58 | 180.92 |
   | N-corrected MDE | 62.26 | 258.45 |
   | Sub-window n / mean | 11 / −9.49 | 9 / −23.92 |
   | Promotion conditions | false / false / false | true / false / false |

   The result SHA256 matches `c2712185…`; input/spec/harness hashes also match their recorded values. The successful log contains exactly the saved JSON, identifies `6f974aa`, and records `rc=0`. The crash occurred during initial loading, before rates, repricing, statistics or output creation. “One successful result-producing run” is substantiated.

4. **Degenerate G1 sub-window CI: correctly reported.** All 11 entries, November 10–December 7, occupy block 2: **[2024-10-29, 2024-12-28)**. Of 13 calendar blocks, only that block contains trades.

   Every accepted draw therefore repeats the same 11-trade collection and has the same mean. The tiny endpoint difference in JSON is floating-point rounding. I reproduced **570 rejected empty draws plus 1,000 accepted draws**, separately for A/B/C.

   The interval measures no between-occupied-block uncertainty here. Its zero width must not imply precise estimation. The reported IID sensitivity `[−13.33, −5.05]` is correctly computed, but assumes independent trades. Promotion uses the sub-window **point estimate**, so this degeneracy does not change the disposition.

5. **Closure: correct under #100 as clarified by #105 and spec §5.** G1 fails all three conditions; hysteresis passes the full-window effect condition but fails the sub-window mean and corrected-MDE conditions. Neither qualifies for consideration of a new formal preregistration. Closing the carry family in learnings follows [spec §5](/home/cms/project/BTC_Futures_E2E/research/screens/p1/S-carry-1_spec.md:45).

   A second reviewer could reasonably object to:
   - **“Regime dependent” as a firm finding.** Hysteresis’s sub-window CI includes zero; no regime-effect or window-difference test was performed. “Negative recent-window estimate, consistent with regime dependence” is supported.
   - Treating the post-hoc effect pass as independent discovery evidence, or observed-sample MDE as demonstrated future power.
   - Entry-based blocks assigning long trades wholly to one block despite exposure spanning multiple blocks. This is the frozen method’s limitation.
   - Missing provenance: the cited [PRE report](/home/cms/project/BTC_Futures_E2E/reports/advisory/w3_carry_pre.md) ends at **r3 FIX**, without the r4 MERGE record referenced by START.

Verification also passed all **13 carry tests** with memory-only file fixtures and five relevant guard/static checks.

Required corrections, through appended documentation while preserving the frozen JSON and logs:

- Supply the promised Markdown result from the existing JSON, with the sparse-block caveat and `sd(net_B)` displayed as specified.
- Soften the regime-dependence claim.
- Append or link the actual PRE r4 MERGE evidence.
- Record POST acceptance and the carry-family closure in learnings; finalize `promoted? = no`.

**ACCEPT WITH NOTES — documentation corrections required; no numerical correction or rerun required.**
```
