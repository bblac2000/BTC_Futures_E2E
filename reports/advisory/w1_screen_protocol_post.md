# W1 — 스크린 프로토콜과 원장 · POST(완료 후 검토)

- 날짜: 2026-10-14 · 항목: W1(CRITICAL) · 검토자: advisor(내장 도구) + Codex(`codex-companion task` · 읽기 전용 · r1~r3 effort high · r4~r5 medium)
- 원문은 그대로 붙였다. PRE 기록: `w1_screen_protocol_pre.md`.

## 1. 회전 표(최종)
| 단계 | 회전 | 대상 커밋 | 판정 |
|---|---|---|---|
| PRE | advisor | 계획 r1 | PROCEED(수정 4) |
| PRE | Codex r1 | 계획 r1 | FIX-PLAN-FIRST(P0 6) |
| PRE | Codex r2 | 계획 r2 | FIX-PLAN-FIRST(P0 2) |
| PRE | Codex r3 | 계획 r3 | **MERGE** |
| POST | Codex r1 | 5537911(프로토콜 v1) | FIX(P0 4 — 문구 2 · 코드/시험 2) |
| POST | Codex r2 | 1c25106(v2 첫 문안) | FIX(P0 2 · P1 2) |
| POST | Codex r3 | 945e2ce(v2 확정 문안 367a04ba) | **MERGE**(남은 우회 = 스크린별 검토로 넘길 P1) |
| POST | advisor | 8701bb2 | ACCEPT(HEAD에서 Codex 한 회전 더) |
| POST | Codex r4 | 945e2ce..8701bb2 | FIX(P2 2) |
| POST | Codex r5 | 8701bb2..43caa8c | **MERGE** |
마지막 연속 MERGE 행 = Codex POST r5(HEAD 43caa8c). 프로토콜 문안은 945e2ce 이후 바뀌지 않았다(SHA256 367a04ba…).

## 2. 공시(두 번째 검토자가 찾을 것)
- (a) "v2" 문안은 POST r2 뒤 한 번 더 고쳐졌다(78e72cc0 → 367a04ba · 읽기 함수 이름과 "정적 규칙은 심층 방어" 문장) — 앵커(Drive · 레지스트리)는 367a04ba에만 있다. v2 머리말은 r1의 수정 둘만 언급한다(앵커된 해시라 고치지 않는다).
- (b) `test_alpha_screen_modules_obey_the_static_rule`은 `research/screens/p1` · `p2`가 생기기 전에는 검사할 대상이 없다(공허). 규칙 자체는 회귀 사례 23개로 시험된다.
- (c) HEAD의 코드는 §4-2의 글보다 엄격하다(로더가 아닌 모듈은 `PUBLIC_NON_LOADER`만 · 별칭 import 금지 · `fetch_json_rows`에 전송 교체 인자 없음) — 더 엄한 방향이라 문안은 그대로 둔다.
- (d) Codex는 읽기 전용 제약으로 파일을 쓰는 시험 6개를 돌리지 못했다 — Claude Code가 전체 시험을 돌렸다(8701bb2에서 1,899 통과 · 43caa8c는 시험 파일만 바뀌어 해당 파일 35 통과).
- (e) Codex POST r1 발견 4("P0 예외가 승인된 것보다 넓다")는 Claude Code의 추가가 아니라 사용자 답변 3의 문장이었다 — v2가 원문을 인용하고 같은 노출 규칙을 붙였다.

## 3. 입장표(POST)
| 출처 | 등급 | 요지 | 입장 |
|---|---|---|---|
| Codex r1-1 | P0(문안) | 같음 규칙 모호 | 동의 — v2 §3-1 · §3-4 4 |
| Codex r1-2 | P0(코드) | 가드가 콜백 경계에서 끝난다 | 동의 — 가드 모듈이 파일·zip·API를 직접 읽는다 |
| Codex r1-3 | P0(시험) | 로더 경유가 강제되지 않는다 | 동의 — 읽기 경로 시험 + 허용 목록 정적 규칙 |
| Codex r1-4 | P0(문안) | P0 예외가 r3보다 넓다 | 부분 동의 — 근거(사용자 결정 원문)와 노출 규칙을 적음 · 허용 자체는 사용자 결정이라 유지 |
| Codex r1-8 | P1 | #97이 D4를 줄여 인용 | accepted — #98에 예외와 가드를 적는다 |
| Codex r2-1 | P0 | 생산자가 시각 검사 전에 돈다 | 동의 — `bounded_records` 삭제 · `fetch_json_rows` |
| Codex r2-2 | P0 | import 경유 우회 | 동의 — 허용 목록 · 금지 이름 |
| Codex r2-3 | P1 | zip 머리줄 자동 판별 | accepted — `header` 명시 · `zip_has_header`의 꼴 검사 |
| Codex r2-4 | P1 | 결과 생성이 원자적이지 않다 | accepted — 모드 "x" |
| Codex r3 | P1 carry | 전송 교체 · 별칭 import · 머리줄 | accepted — 8701bb2에서 코드로 막음(그래도 스크린별 PRE에서 다시 본다) |
| Codex r4 | P2 ×2 | `bounded_records` 금지 복원 · 정확한 `numpy as np` | 동의 — 43caa8c |
| advisor POST 1 | — | HEAD에서 Codex 한 회전 더 | 동의 — r4 · r5 |
| advisor POST 2~4 | — | 공시 셋 · #98 내용 · 원장 머리말 · 메모 | 동의 |
| advisor POST 6 | — | N 감사: 표를 만들고 합이 떨어지는 대로 | 동의 — 다음 항목 |

## 4. advisor POST — 원문(verbatim)
You're at the W1 close-out: protocol v2 (`367a04ba`) anchored on Drive (`1umUVbGZJjI5x3yA8wcRaTu8iJBAgUOrc`, createdTime 2026-10-14T02:49:45.052Z, cmp identical), Codex POST r3 = MERGE at 945e2ce, full suite 1,899 at HEAD 8701bb2. **Advisor POST verdict: ACCEPT as produced, with one short Codex round still owed before you can write the gate as passed.** Save this text verbatim into `reports/advisory/w1_screen_protocol_post.md` (advisor section) first.

**1. The matrix's last row must be at HEAD**

8701bb2 (no `opener`, alias/banned imports, readers loader-only, header schema) was committed *after* r3 MERGE. The protocol hash is unchanged, so the anchor stands — but the user's rule is "the last consecutive MERGE row of the final matrix is the verdict", and #98 will cite HEAD. Run one Codex r4 restricted to the 945e2ce..8701bb2 diff ("were the three carry items closed without weakening anything; MERGE/FIX"). Five minutes; it turns "MERGE at a prior commit plus an unreviewed delta" into a clean matrix. Until it's back, W1 is not gate-passed.

**2. `_post.md` must contain**

Prompts and raw outputs of POST r1/r2/r3 (and r4), your per-finding positions, the round table (PRE r1 FIX → r2 FIX → r3 MERGE; POST r1 FIX → r2 FIX → r3 MERGE → r4 ?), and three disclosures a second reviewer will otherwise find: (a) "v2" text was revised once more after POST r2 (78e72cc0 → 367a04ba) before anchoring; the v2 header cites only r1's fixes — hash is anchored, don't edit, disclose; (b) `test_alpha_screen_modules_obey_the_static_rule` is vacuous until `p1/`/`p2/` exist (Codex said so); (c) the code at HEAD is stricter than §4-2's prose (non-loaders get `PUBLIC_NON_LOADER`, aliases banned) — acceptable direction, state it.

**3. Registry #98 (supersedes #97's anchor)**

v2 SHA256 `367a04ba…` · MD5 `65b4cac0…` · 16,554 B · text commit 945e2ce · HEAD after hardening · Drive id/createdTime above · "no screen ran under v1; v1 Drive file retained" · Codex POST rounds with the r4 result · `protocol review` status now MERGE → per §5 every future row's `promoted?` reads `no` (not `n/a`) · the UNRESOLVED list unchanged (P1 null, P2 cost mapping, "θ = 20" reading, P0 S-vs-M). Precheck as always ([1,2]/7/[1]/3, no `t3_`/`t4_` tokens).

**4. Small items**

- One ops_log line pointing at `_pre.md`/`_post.md` (say once that the verbatim rule is met by those files).
- Optional, zero-risk while the ledger has no rows: a header line in `screen_registry.md` naming protocol v2's hash and createdTime.
- Memory `screens-round-2026-10.md`: W1 closed (v2 hash, Drive id, what's blocked).

**5. Briefing, then don't stop**

The user asked for the 8-section Korean briefing after W1 — read `status-briefing-format.md` for the exact sections, give it, then proceed to `n_counter_audit.md` in the same turn (their words: don't batch, don't wait).

**6. N audit — what your grep already shows**

Rows to read in full: TriadBot `docs/design/N_count.md` (#72: 45 rows at 2026-09-22, base inventory) · #77 (Q-1 O3 rule) · #81 (N = 51 user-confirmed) · #295 (N = 56 — list its composition) · #314/#316 (N = 60, "sensitivities 62/63") · ThresholdBot #22–#24 (N = 62) · MetaGateBot #13 ("62 + Δ + K, K = 1") and CLOSURE. The user's own chain does not close arithmetically: 56 + T-CAF's 4 arms = 60, not 62; TriadBot records 60 with 62/63 as alternatives. Don't reconcile in prose — build the table one row per increment (repo · trial · arms · date · row) and let the sum fall where it falls. Your trial #3 and #4 arms (4 arms, both anchored 2026-09-30, after T-S2c's 2026-09-27 count) are exactly the size of the 56 → 60 step — check whether #316's D-1 lists them, or whether 60 is T-S3's own arms, before writing "included/excluded". Also state what this repo's N = 8 comprises (1A/1B/2A/2B/3L/3S/4S/4L) so the cross-repo table can show each counted once. If the total ≠ 64, that conclusion is CRITICAL under the standing rule: advisor + Codex on the conclusion before its registry row; N is reported, never changed.

## 5. Codex POST r1 — 프롬프트와 응답 원문(verbatim)
```
READ-ONLY POST-REVIEW ROUND 1 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E, committed state at HEAD. You approved plan r3 for the W1 screen protocol (PRE record: reports/advisory/w1_screen_protocol_pre.md). Now review what was actually produced:
- docs/screen_protocol.md (v1; SHA256 30229b256809bb51ea72d8a6992d44aeb55e7ef3f0faac24d909a46b067b16d4, committed in 0597d36 and uploaded to Google Drive, createdTime 2026-10-14T02:30:44.771Z)
- docs/screen_registry.md (empty ledger)
- research/screens/window.py and tests/test_screen_window.py
- docs/trial_registry.md rows #95 (resume), #96 (theta correction), #97 (procedure change)
Check each plan item R1-R9, R4+, R5+ and the new P1 ("best T") against the committed text and code. Answer the user's four questions against the files, not the plan:
Q1. Does the pass rule admit a post-hoc degree of freedom?
Q2. Is the D4 reserve enforced in code, not prose? Try to find an ingestion path in research/screens/window.py that interprets a reserve-dated payload, and judge whether tests/test_screen_window.py would catch a p1/p2 module that reads data outside its loader.
Q3. Does the two-ledger rule make the garden of forking paths visible at promotion (k disclosed and used)?
Q4. Is anything in the protocol a disguised threshold change to the formal judge (theta = 10 bps, MDE cutoff 2*theta = 20, alpha, MDE rule, registry #88)?
Also check that registry #97 quotes the user decisions without altering them and that N is neither consumed nor redefined.
Note: the protocol file is hash-anchored. If you find a P0 in the protocol TEXT, say so explicitly, because fixing it means protocol v2 with a new hash and a new registry row before any screen runs (no screen has run). Findings in code/tests can be fixed in place.
OUTPUT: numbered findings tagged P0/P1/P2 with file:line; then one line per Q1-Q4; end with exactly one line: VERDICT: MERGE or VERDICT: FIX.
```
1. **[P0 — PROTOCOL TEXT; R3] Ambiguous equality rule.** [docs/screen_protocol.md:34](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:34) admits equality at `mean = 1.5 × cost`, but [line 38](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:38) says boundary equality means FAIL without limiting that statement to p95. When cost equality holds and the null test passes, two readings produce different verdicts. Explicitly preserve cost `≥` and null-statistic strict `>`. Also constrain [line 57](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:57)’s permission to declare departures from §3-1; a spec must not silently override frozen decision rules.

2. **[P0 — CODE; R4/R4+] Reserve protection stops at the callback boundary.** [research/screens/window.py:37](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:37) accepts arbitrary iterables and timestamp callbacks. In an in-memory reproduction, an upstream generator converted a July payload to `float` before yielding it; `bounded` subsequently discarded the row, after interpretation had occurred. A timestamp callback can likewise interpret reserve values. The compliant callback path filters correctly, but no committed ingestion implementation enforces timestamp-first interpretation end to end.

3. **[P0 — TESTS; R4/R4+] Loader routing is not enforced.** [tests/test_screen_window.py:90](/home/cms/project/BTC_Futures_E2E/tests/test_screen_window.py:90) scans limited call names and checks only imports inside loaders. Running its actual assertions against in-memory module sources accepted:
   - `open` aliased to `read_file` outside a loader;
   - `pandas.read_json` outside a loader;
   - a loader importing `window` but reading CSV without invoking any guard;
   - `from .. import p0`.

   Moreover, p1/p2 currently do not exist, so those scans are vacuous. [Line 40](/home/cms/project/BTC_Futures_E2E/tests/test_screen_window.py:40) tests helper callbacks, not a file/API ingestion path. Add ingestion-level coverage and regression cases for these routing failures.

4. **[P0 — PROTOCOL TEXT; R7] The P0 exception is wider than approved r3.** [docs/screen_protocol.md:76](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:76) identifies one exposed interval, September 17–October 11. [Line 77](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:77) additionally authorizes July 24–September 16 for “touch frequency.” That expands the approved reserve exception, even if the output is report-only, and leaves those additional dates outside the stated exposure accounting. Remove that permission or obtain and record an explicit decision with matching exposure rules. **The protocol-text P0s require protocol v2, a new hash, and a new registry row before any screen runs. Code/test findings can be fixed in place.**

5. **[P2 — R1/R8 verified] Formal judge preserved.** [docs/screen_protocol.md:26](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:26) matches [backtest/verdict_t4.py:28](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t4.py:28): θ = 10, insufficient-power cutoff `MDE > 20`, absence cutoff `MDE < 5` with net CI upper `< 10`, and negative-CI precedence. Historical α/coefficient provenance, the dependence formula, report-only screen MDE, and #88’s gate are preserved. Registry [#96, line 104](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:104) corrects notation without changing the judge.

6. **[P2 — R2/R3/new P1 verified, subject to finding 1] Execution blocking and “best T” requirements are present.** [docs/screen_protocol.md:43](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:43) blocks unresolved specs. [Line 49](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:49) fixes `{30,60,120}`, mean improvement over a common decision sample, smaller-T ties, fallback accounting, and a new M id for added candidates. The strict `< 2 bps` kill boundary and sample/estimator/null checklist are included.

7. **[P2 — R5/R5+/R6/R9 verified] Promotion accounting is explicit.** [docs/screen_protocol.md:17](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:17) requires committed START records, immutable families, complete counting, and new ids for changed variants. [Line 21](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:21) requires the entire cross-repository lineage and blocks promotion until k’s actual DSR use is specified and verified without double counting. Provenance, report-only benchmarks, and separate review/promotion statuses are present; [docs/screen_registry.md:7](/home/cms/project/BTC_Futures_E2E/docs/screen_registry.md:7) remains empty.

8. **[P1 — Registry fidelity] #97 preserves the quoted D2/D3 decisions and D4 window, but abbreviates D4.** [docs/trial_registry.md:105](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:105) labels these as excerpts and omits loader enforcement and the narrow P0 exception. It supplies no authorization for finding 4’s additional interval. #95, #97, and protocol §1 keep N unused and unchanged; the formal anchor remains `N_TRIALS = 8`.

9. **[P2 — Validation]** All nine committed screen-window tests pass. HEAD’s protocol SHA256 matches the supplied anchor. The reproductions used synthetic data and in-memory sources; no files changed.

Q1. **Yes:** the equality ambiguity permits a post-hoc interpretation; otherwise unresolved choices and “best T” are required to be fixed before execution.

Q2. **Not fully:** compliant helper use is guarded, but upstream payload interpretation and loader bypasses remain possible and undetected.

Q3. **Yes at the protocol level:** complete lineage and verified k use are mandatory before promotion; DSR integration remains intentionally blocked pending formal specification.

Q4. **No:** θ, α/MDE rules, classification boundaries, and registry #88 are preserved; N is neither consumed nor redefined.

VERDICT: FIX


## 6. Codex POST r2 — 프롬프트와 응답 원문(verbatim)
```
READ-ONLY POST-REVIEW ROUND 2 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E at HEAD 1c25106. Your POST round 1 gave four P0s on the W1 screen protocol. What changed:
1 (equality) docs/screen_protocol.md is now v2 (SHA256 78e72cc0ce7ece551d52262d8d237aaba69c5e13fdd6e710fe9beb5be511107e): §3-1 states (가) uses >= (equality satisfies) and (나) uses strict > (equality fails); §3-4 item 4 says a spec cannot change or loosen §3-1..§3-3 and the protocol wins on conflict.
2 (callback boundary) research/screens/window.py: the generic helper is now private (_bounded); the only read paths for loaders are bounded_csv_file / bounded_zip_csv (the guard module opens the file, cuts ONLY the timestamp cell from each line, and hands in-window lines to the caller's parse) and bounded_records (API rows already bounded at request level; an out-of-window row raises). write_result writes a result once.
3 (loader routing) tests/test_screen_window.py: ingestion-path tests on real files and zips with a spy parse; a static rule screen_violations(src, is_loader) with regression cases for your four bypasses (open alias, pandas outside loader, loader importing window but reading directly, relative import of p0) plus importlib and legacy-layer imports; it is applied to every module under research/screens/p1 and p2 as soon as those directories exist (none exists yet - no screen code has been written).
4 (P0 exception width) the 2026-07-24 -> 2026-09-16 auxiliary interval is NOT my addition: it is the user's written decision of 2026-10-14, quoted verbatim in §4-4 ("The 07-24 → 09-16 span (depth/bookTicker only) may feed a 'touch frequency' auxiliary column only — never the fill decision and never the conclusion."). v2 now cites it and applies the same exposure rule to that interval, and states the total reserve span P0 may expose (2026-07-24 -> 2026-10-11).
No screen has run under v1; v1's registry row is #97. After your verdict I will upload v2 to Drive for createdTime and append a registry row that supersedes v1's hash.
TASK: state RESOLVED / PARTIAL / OPEN for round-1 findings 1-4 against the committed files; try again to construct (a) a reading of §3 with two verdicts for the same numbers, (b) a loader-side path through the PUBLIC functions of window.py that interprets a reserve-dated payload, (c) a p1/p2 module that reads data and passes screen_violations. List NEW findings tagged P0/P1/P2 with file:line. One line each for Q1-Q4 (post-hoc freedom in the pass rule; D4 enforced in code; k visible at promotion; disguised change to the formal judge). End with exactly one line: VERDICT: MERGE or VERDICT: FIX.
```
Reviewed HEAD `1c25106`; the protocol SHA256 matches the supplied v2 hash. No files changed.

| Round-1 finding | Status | Assessment |
|---|---|---|
| 1. Equality ambiguity | **RESOLVED** | §3-1 explicitly fixes `≥` versus strict `>`; §3-4 makes the protocol prevail over conflicting specs. [screen_protocol.md:35](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:35) |
| 2. Callback boundary | **PARTIAL** | CSV/ZIP timestamp extraction is now internal. `bounded_records` still advances caller-controlled producers before checking timestamps. [window.py:142](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:142) |
| 3. Loader routing | **PARTIAL** | The reported bypasses have regression coverage, but another ordinary data-reading module passes the rule, demonstrated below. [test_screen_window.py:154](/home/cms/project/BTC_Futures_E2E/tests/test_screen_window.py:154) |
| 4. P0 exception width | **RESOLVED** | The auxiliary interval now has the quoted user authorization, restricted use, exposure treatment, and total permitted span. [screen_protocol.md:80](/home/cms/project/BTC_Futures_E2E/docs/screen_protocol.md:80) |

**(a) Two verdicts from §3:** I could not construct two compliant verdicts for identical numbers and the same frozen spec. For cost `10`, gross mean `15`, statistic `5`, and null p95 `5`, the verdict is **FAIL**. Raising the statistic above `5` yields **PASS**. A spec choosing inclusive p95 would conflict with §3-4.

**(b) Public-function counterexample:** This loader uses only the public `bounded_records` reader and passes `screen_violations(..., is_loader=True)`:

```python
from research.screens.window import (
    bounded_records, ReserveError, SCREEN_START_MS, SCREEN_END_MS,
)

def load(rows):
    seen = []
    def incoming():
        for row in rows:
            seen.append(float(row["fundingRate"]))
            yield row
    try:
        list(bounded_records(
            incoming(), "fundingTime", dict,
            start_ms=SCREEN_START_MS, end_ms=SCREEN_END_MS,
        ))
    except ReserveError:
        pass
    return seen
```

For `fundingTime = SCREEN_END_MS + 1` and `fundingRate = "9.0"`, it returns `[9.0]`: interpretation precedes refusal. This violates the intended producer discipline, but the public API and static check accept it. The “already bounded API response” requirement remains a caller obligation.

**(c) Data-reading module accepted by the static rule:**

```python
from research.screens.window import io
payload = io.FileIO("reserve.csv").read()
```

As `p1/analysis.py` or `p2/analysis.py`, this produces `screen_violations(..., is_loader=False) == []`. I executed it against the committed protocol document to verify the unguarded read without opening market data.

Additional findings:

1. **[P0] Producer execution remains outside the timestamp boundary.** [window.py:142](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:142): counterexample (b) preserves the reserve-exposure problem despite the eventual exception. Enforce bounded ingestion upstream of producer interpretation, or withhold this route until that boundary exists.

2. **[P0] Imported dependencies escape the routing check.** [test_screen_window.py:154](/home/cms/project/BTC_Futures_E2E/tests/test_screen_window.py:154): counterexample (c) imports through `research`, avoiding the I/O-module check; `FileIO` and `read` also escape the name check. Independently, allowed `numpy.fromregex(...)` reads files and passes. Import provenance and allowed reader calls need stronger enforcement.

3. **[P1] Default ZIP header detection silently skips malformed data.** [window.py:126](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:126): a ZIP beginning `not-a-time,9.0`, followed by a valid row, returns the valid row without raising. Require an explicit header declaration or recognize a defined header schema.

4. **[P1] Result creation is not atomic.** [window.py:153](/home/cms/project/BTC_Futures_E2E/research/screens/window.py:153): two writers can both pass `exists()` and then overwrite the same result at line 157. A synchronized memory-only reproduction produced two successful calls. Use exclusive creation.

Validation: **17 tests passed; 4 file-writing tests were deselected** under the read-only constraint. Additional reproductions used memory-only inputs.

Q1: No remaining conflicting §3 reading found; unresolved P1/P2 choices remain explicitly blocked before execution.  
Q2: D4 is **partially** enforced in code; producer interpretation and accepted unguarded readers still permit exposure.  
Q3: k is visible at promotion through mandatory lineage disclosure and verified DSR use; enforcement currently depends on registration and review.  
Q4: No disguised formal-judge change found: θ remains 10 bps, the MDE cutoff remains 20 bps, and the formal judge is untouched.

VERDICT: FIX


## 7. Codex POST r3 — 프롬프트와 응답 원문(verbatim)
```
READ-ONLY POST-REVIEW ROUND 3 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E at HEAD. Round 2 left two P0s (producer runs before the timestamp check in bounded_records; imported dependencies escape the routing check) and two P1s (zip header auto-detection skips malformed data; non-atomic result creation). Changes:
- bounded_records is REMOVED. API access is `fetch_json_rows(url, params, ts_key, parse)` in research/screens/window.py: the guard module performs the GET itself (request startTime/endTime validated before any network call), decodes the body, checks EVERY row's timestamp, and only then calls parse; if any row is outside the requested window no row is parsed and it raises. A loader never holds an iterator/producer of unvalidated rows.
- Static rule is now an ALLOW-LIST (tests/test_screen_window.py::screen_violations): imports limited to pure-computation stdlib modules, numpy, the same family package, and only the names in window.PUBLIC from research.screens.window (loader.py may also import pathlib.Path); a banned-name set applies to both Name and Attribute nodes (open, read, load, fromregex, FileIO, io, json, getattr, __import__, ...). Regression cases include your (c) `from research.screens.window import io`, `W.io.FileIO`, numpy.fromregex, private `_bounded`, pandas, and cross-family imports.
- bounded_zip_csv requires an explicit `header: bool`; `zip_has_header` looks at the timestamp cell of the first line only; a malformed first data line raises.
- write_result opens with mode "x".
- docs/screen_protocol.md (still v2, not yet anchored; text updated to name fetch_json_rows and to say the static rule is defence in depth, with per-screen PRE/POST review as the other layer).
TASK: RESOLVED / PARTIAL / OPEN for the round-2 P0s and P1s; attempt once more (b) a loader that passes screen_violations(is_loader=True) and interprets a reserve-dated payload through window's PUBLIC functions, and (c) a non-loader module that passes screen_violations and reads a file or the network. Judge proportionality: the protocol states the static rule is defence in depth and that every screen's code gets its own PRE/POST review; say explicitly whether any remaining bypass is a P0 for W1 or a P1/P2 to carry into each screen's review. One line each for Q1-Q4. End with exactly one line: VERDICT: MERGE or VERDICT: FIX.
```
Read-only review at `945e2ce`; no files changed. **23 tests passed, 6 file-writing tests deselected**; bypass and header checks used memory fixtures.

1. **Producer-before-timestamp P0 — PARTIAL; remainder P1.** Default `fetch_json_rows` validates the request before I/O and every timestamp before `parse`. However, a caller-supplied `opener` can interpret payloads first.
2. **Imported-dependency routing P0 — PARTIAL; remainder P1.** Known examples are rejected, but aliased `ImportFrom` names evade `BANNED_NAMES`; non-loaders can also call PUBLIC readers.
3. **Malformed zip-header P1 — PARTIAL.** Explicit `header=False` raises correctly, but the documented `header=zip_has_header(p)` path still silently skips `not-a-time,9.0`, returning the subsequent valid row.
4. **Non-atomic result creation P1 — RESOLVED.** Mode `"x"` provides atomic exclusive creation and prevents overwrite. It does not guarantee crash-complete publication.

**(b) Successful bypass:** this loader returns `screen_violations(..., is_loader=True) == []`:

```python
from research.screens.window import fetch_json_rows, SCREEN_START_MS, SCREEN_END_MS

seen = []
def hook(url, timeout):
    response = fetch_json_rows.__kwdefaults__["opener"](url, timeout=timeout)
    for row in response:
        seen.append(float(row.split(b'"value":')[1].split(b'}')[0]))
    return response

def rows():
    return fetch_json_rows(
        "https://example.invalid/rows",
        {"startTime": SCREEN_START_MS, "endTime": SCREEN_END_MS},
        "timestamp", lambda row: row["value"], opener=hook)
```

An in-memory response containing `[{"timestamp":1782864000000,"value":123.45}]` produced `seen == [123.45]` before `JSONDecodeError`. The reserve value was already interpreted.

**(c) Successful bypass:** this non-loader returns no violations and actually read the repository document:

```python
from numpy import fromregex as scan
result = scan("docs/screen_protocol.md", r"v(\d+)", [("version", int)])
```

**Proportionality:** these remaining bypasses are **P1 carry items for each screen’s PRE/POST review, not W1 P0s**. No alpha-screen modules exist yet, and §4-2 explicitly makes static checking defence in depth. Each PRE must inspect imported aliases, opener callbacks, timestamp selection, and header identification before approving data access.

Q1: Unresolved screen decisions remain execution-blocking; W1 can merge with those decisions deferred.
Q2: Default ingestion is guarded; remaining P1 bypasses require explicit inspection in every screen’s PRE/POST review.
Q3: Registration and counting requirements remain intact; anchor the current v2 hash before any screen reads data.
Q4: The formal judge remains θ = 10 bps with existing 20/5/10 cutoffs; no judge change is introduced.

VERDICT: MERGE


## 8. Codex POST r4 — 프롬프트와 응답 원문(verbatim)
```
READ-ONLY POST-REVIEW ROUND 4 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E. Your round 3 verdict was MERGE at 945e2ce with three P1 carry items. Commit 8701bb2 (HEAD) then closed them in code. Review ONLY the diff `git diff 945e2ce 8701bb2 -- research/screens/window.py tests/test_screen_window.py` (docs/screen_protocol.md is unchanged: SHA256 367a04ba63d4c93ec22d1f11440eb9a57aa6dfd7a2311a6308bc97436459f787):
- fetch_json_rows no longer accepts an `opener`; it calls urllib.request.urlopen directly.
- screen_violations: any `from X import name` where name is in BANNED_NAMES or any aliased ImportFrom is a violation; `import x as y` allowed only for numpy as np; dunder introspection names (__kwdefaults__, __globals__, ...) banned; non-loader modules may import from window only the names in window.PUBLIC_NON_LOADER (no reader functions).
- zip_has_header raises unless the first cell is all digits (data) or matches [A-Za-z_]+ (a column name).
Question: were the three carry items closed without weakening any earlier guarantee or test? List findings tagged P0/P1/P2 with file:line. End with exactly one line: VERDICT: MERGE or VERDICT: FIX.
```
The three carry-item examples are closed, but the diff weakens one existing rule and incompletely implements another.

- **P2 — tests/test_screen_window.py:177:** `bounded_records` was removed from `BANNED_NAMES`. Previously rejected code such as `loader.bounded_records(records, timestamp, parse)` now passes. Restore the existing ban to preserve the earlier guarantee.
- **P2 — tests/test_screen_window.py:193:** The alias check permits any allowed module with alias `np`, including `import math as np` and `import numpy.linalg as np`. Require the exact pair `numpy as np`.

No P0/P1 findings. Transport ownership, introspection rejection, non-loader window imports, and malformed-header rejection behaved as intended in the checked cases.

Validation: 26 tests passed; six filesystem-writing tests were excluded under read-only restrictions. In-memory probes confirmed both findings. The protocol SHA256 matches the supplied value; no files were modified.

VERDICT: FIX


## 9. Codex POST r5 — 프롬프트와 응답 원문(verbatim)
```
READ-ONLY POST-REVIEW ROUND 5 (do not edit any file). Repository /home/cms/project/BTC_Futures_E2E at HEAD. Round 4 gave two P2 findings in tests/test_screen_window.py: (1) `bounded_records` removed from BANNED_NAMES; (2) alias rule accepted `import math as np` / `import numpy.linalg as np`. HEAD restores the ban and requires the exact pair (numpy, np), with three regression cases added. Review `git diff 8701bb2 HEAD -- tests/test_screen_window.py` only. Are both closed, with nothing else weakened? End with exactly one line: VERDICT: MERGE or VERDICT: FIX.
```
Both P2 findings are closed: `bounded_records` is banned again, and aliases are allowed only for the exact `(numpy, np)` pair. The three regression cases cover the reported bypasses. Nothing else is weakened in the specified diff.

VERDICT: MERGE

