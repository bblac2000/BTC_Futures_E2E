# S-carry-1 스펙 — carrybot G1 장부의 사후 비용 민감도(r1 · 계산 전 고정)

- 종류 · 가족: **post-hoc cost sensitivity of a closed trial (carrybot G1)** · carry 가족(k에 들어간다 · N = 64 불변 — 정식 판정이 아니다).
- 근거: 프로토콜 v3 §3-1a(carry) + **사용자 결정 #100 · #105**. v3 본문은 아직 net_A와 UNRESOLVED를 적고 있다 — 이 스크린은 #105의 답(① 검정력 표지 · ② 60일 날짜 블록 · ③ 양쪽 95% · 비용 B 주 시나리오)을 따른다. v4(그 답을 넣은 판)는 #105 순서대로 이 스크린 **뒤에** PRE/MERGE한다(공시).
- **공시(#100)**: 원래 결과를 이미 읽었다 — v1 77건 · v1 정정 순손익 −0.36 · v2 25건 · 순손익 +23.67 · "G1 REJECT (최종)". 이 스크린은 같은 거래를 다시 값 매길 뿐 거래를 고르지 않는다(매개변수 · 규칙 · 거래 집합 불변).
- 결과는 매매 근거가 아니다. n ≈ 25 / 77이라 **비용 민감도 정보이지 검정력 주장이 아니다**(#105).

## 1. 장부(재현 확인 — 1단계 완료)
- carrybot 동결 커밋 **5ba96a0**(FREEZE.md를 만든 커밋 · carry 코드와 결과 JSON은 HEAD f33a40e와 바이트 동일)의 분리 작업 트리에서 `uv sync --frozen` → 정본 측정 스크립트 `carry_backtest.py` · `carry_backtest_v2.py`를 **수정 없이** `main()`으로 실행. 하네스 `research/screens/w3_harness/carrybot_ledger.py`(SHA256 6980ffbb…)는 `run_backtest`를 감싸 거래만 옮겨 적는다.
- 재현: v2 결과 JSON **비트 동일**(git diff 없음). v1 결과 JSON은 숫자 칸 전부 동일 — 다른 것은 실행 뒤 손으로 덧붙인 주석 칸(`verdict` N/A · `exit_reasons` · `known_limitations` · `scope` 등)뿐. 표준 출력: v1 77건 1.5804556808 · v2_primary 25건 23.6659548890 · v1_restated 77건 −0.3575615876. 로그 `research/screens/p1/data/carrybot_repro.log`.
- **보고된 순손익과 거래 합의 차이(공시)**: v1 두 실행의 첫 거래는 표본 첫 정산(2021-01-01 00:00Z)에 들어가 그 진입 비용 절반이 `equity[0]`에 들어갔다 — carrybot의 `net_pnl = equity[-1] − equity[0]`은 그 비용을 빠뜨린다. 차이 = 그 거래의 진입 수수료 + 진입 슬리피지(v1 0.3182 · v1_restated 0.3556 USDT · 센트까지 일치). **이 스크린은 거래별 장부를 쓴다.**
- 장부 `research/screens/p1/data/carrybot_trades.csv`(SHA256 c00f7312…) — 첫 칸 = 청산 시각(ms).
- **암**: G1 = `v1_restated`(v1 규칙 + 사용자가 적은 원래 모형 "30 bps RT + 2 bps per leg" = 레그별 슬리피지) · 히스테리시스 = `v2_primary`. `v1_original`(77건 · 같은 거래)과 `v2_no_accounting_fix`는 보고만.

## 2. 자료 창(2단계)
- 로더는 `window.bounded_csv_file(ts_field = 0)`로 장부를 읽는다 → **청산 시각 > 2026-06-30T23:59:59.999Z인 거래는 값 해석 없이 버린다**(거래 통째 · 부분 절단 없음). 알려진 것: v2_primary의 `end_of_sample` 1건(07-31 청산). 버린 수를 보고한다.
- DTB3: FRED `fredgraph.csv?id=DTB3&cosd=2020-12-01&coed=2026-06-30`(SHA256 2dba6ae2…) · `bounded_csv_file(ts_kind = "iso")` · 값 "."은 관측 없음.
- carry 예약은 2026-08-01부터(#100) — carrybot 코드의 07-31 읽기는 예약에 닿지 않는다. 스크린 자체는 06-30까지만 쓴다.

## 3. 값 매기기(3단계 · 거래 i · 단위 = 그 거래 명목의 bps)
- gross_i = `funding_collected` + `residual_delta_pnl`(USDT · carrybot `Trade.net_pnl`의 수수료 · 슬리피지 · 기회비용 앞부분 그대로).
- 비용 X ∈ {A 10 · **B 17.5(주)** · C 25} bps(D7 · #105): **현물 + 무기한 짝의 왕복 전부**로 읽는다(D7 원문 "A = 10 bps (spot BTC/FDUSD maker both ways + perp taker 5+5)" — 레그별 수수료의 합) → cost_X,i = X/10⁴ × notional_i가 원래의 `fees` + `slippage`를 **대체**한다. 슬리피지를 따로 더하지 않는다(헌법 영역 A 7: 이 규모의 왕복 슬리피지 실측 0.016 bps · 공시).
- net_X,i = gross_i − cost_X,i.
- DTB3_i = locked_i × r_i/100 × (exit_ms − entry_ms)/(365 × 86,400,000) · locked_i = notional × (1 + 1/2 + 0.10)(carrybot 기회비용과 같은 바탕 — 비율만 DGS2 → DTB3) · r_i = 진입 날짜(UTC) 이하의 마지막 DTB3 관측.
- DGS2 열 = carrybot 원래 `opportunity_cost`(비교용 보고).
- 원래 모형 열 = carrybot `net_pnl`(거래별) — 재현 확인용.
- 모든 USDT 값을 ×10⁴/notional_i로 bps.

## 4. 보고(4단계 · 암마다 · 이 순서)
1. n(전 구간 · 2024-07-01 이후 진입) · 버린 거래 수.
2. **sd(net_B)**(bps · ddof 1) 먼저.
3. 평균: gross · net_A · net_B · net_C · net_B − DTB3 · net_B − DGS2 · 원래 net(DGS2 차감) — 전 구간과 부분 구간(진입 2024-07-01 ~ · 청산 ≤ 06-30).
4. **주 통계 = 평균(net_B − DTB3)** · 양쪽 95% 날짜 블록 부트스트랩 CI:
   - 블록 = 2021-01-01T00:00Z부터 60일 달력 구간(부분 구간은 2024-07-01부터) · 거래는 **진입 시각**으로 블록에 든다 · 창을 덮는 블록 K개(빈 블록 포함 · 전 구간 34 · 부분 구간 13)를 복원 추출 → 뽑힌 블록의 거래 전부(중복 포함)의 평균.
   - 거래 0건인 추출은 버리고 다시 뽑는다(다시 뽑은 수 보고) · 1,000회 · 시드 20261014 · `numpy.random.default_rng` · 분위 2.5/97.5(numpy 선형).
   - 민감도 열: 거래 단위 독립 부트스트랩(에피소드 = 블록 · #105 ②(i)) · 같은 시드 · 같은 회수.
   - A · C의 (net − DTB3) 평균과 CI도 보고.
5. 검정력 표지(#105 ①): MDE = 계수 × sd(net_B − DTB3)/√n_eff · n_eff = n/(1 + 4 · max(ρ̂, 0.15)) · ρ̂ = 진입 순서 거래열의 1차 자기상관 · 보정 전 계수 2.80 → **표지** 실현 가능 ≤ 20 / 경계 ≤ 40 / 불가 > 40 · N = 64 계수 4.00(한쪽 · 양쪽 4.20은 공시)도 함께. "투영"은 장부의 n 그대로(새 설계의 n이 없다 · 공시).
6. **효과 열과 검정력 열은 따로**(합쳐 한 판정으로 만들지 않는다).

## 5. 판정 열(고정 · #100 · #105)
- 효과(스크린 통과): 전 구간 평균(net_B − DTB3)의 양쪽 95% CI 하한 > 0.
- **새 정식 사전등록 조건**(셋 다): 전 구간 (net_B − DTB3) CI 하한 > 0 ∧ 2024-07 → 2026-06 평균(net_B − DTB3) > 0(점 추정) ∧ N 보정 MDE(4.00) ≤ 20 bps. 하나라도 아니면 **learnings에서 carry 가족을 닫는다**(#100).
- 암 둘을 따로 판정한다. 어느 암도 다른 암의 결과로 고르지 않는다.

## 6. 코드 · 시험
- `research/screens/p1/loader.py`(창 가드 읽기만) · `research/screens/p1/reprice.py`(순수 계산) · `research/screens/p1/run.py`(한 번 실행 · `write_result` 배타 생성) — `tests/test_screen_window.py`의 p1 정적 규칙 적용.
- 시험(실행 전 통과): 07-01 이후 청산 거래가 값 해석 없이 버려짐 · 비용 대체 식 · DTB3 일수 환산과 진입일 이하 마지막 관측 · 블록 배정과 0건 재추출 · 결정적 시드.
- 결과 `research/screens/p1/results/S-carry-1.{json,md}`.
