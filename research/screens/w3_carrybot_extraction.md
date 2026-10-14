# W3 1단계 — carrybot G1 장부와 비용 모형 추출(숫자를 다시 계산하기 전 · 읽기만)

> 사용자 결정 #100 1단계: "Locate the carrybot G1 trade/episode ledger and its cost model (extract verbatim …). Report them before touching numbers."
> 이 문서는 닫힌 트라이얼의 문서·코드·결과 파일을 **읽기만** 했다. 재가격 계산 · S 행 START · 새 자료 읽기는 하지 않았다. carry 가족은 프로토콜 v3의 UNRESOLVED 두 항목(재표본 단위 · CI 수준)으로 실행이 막혀 있다.
> 출처 저장소: `~/project/carrybot`(읽기 전용). 원래 결과는 이미 읽힌 것이며 이 추출도 그 결과를 다시 본다(공시).

## 1. 무엇이 측정됐나(원문)
- v1: `docs/CarryBot_G1_결과_2026-08-29.md` 제목 "CarryBot G1 결과 보고서 — **REJECT** (마찰비용이 캐리를 삼킴)" · 사전등록 `docs/CarryBot_G1_사전등록_v2_2026-08-29.md`.
- v2(히스테리시스): `docs/CarryBot_G1_v2_결과_2026-08-29.md` 제목 "CarryBot G1 v2 결과 — **사전등록 기준 REJECT** · 가설은 확증, 라벨은 기준 결함에 민감" · 사전등록 `docs/CarryBot_G1_사전등록_v2hyst_2026-08-29.md`(커밋 aa95f80) · 결과 JSON `verdict = "G1 REJECT (최종)"` · `N = 2`.
- 구조: BTCUSDT 무기한 **숏** + 현물 롱(델타 중립) · 기간 2021-01-01 ~ 2026-07-31(5.58년) · 8시간 정산 6,114건.

## 2. 비용 모형(원문 · 파일:행)
| 항목 | 원문 | 출처 |
|---|---|---|
| 왕복 비용 | "왕복비용 0.3% (선물 taker 0.05%×2 + 현물 0.10%×2)" | 사전등록 v2 :174(A2) · 코드 `round_trip_cost=0.003` (`carry_backtest_v2.py:28`) |
| 선물 수수료(편도) | 0.05%(taker) | 같은 곳 |
| 현물 수수료(편도) | 0.10% | 같은 곳 |
| 슬리피지 | "슬리피지 `cfg.slippage_bp` 가정치" · 코드 `slippage_bp=2.0` | 사전등록 v2 :175(A3) · `carry_backtest_v2.py:28` |
| 펀딩 회계 | "정산별 순손익 = 펀딩수취 − 잔여델타손익 − (진입/청산 시) 수수료 − 슬리피지 − 기회비용 · 펀딩수취 = N × funding_8h_norm (숏이므로 funding>0 = 수취)" · "funding_8h_norm = last_funding_rate × (8 / funding_interval_hours)" | 사전등록 v2 :101 · :126~127 |
| 기회비용(벤치마크) | "기회비용 = (N + N/L + B) × DGS2_annual × (8/24/365)" — **DGS2(2년물)** · "해당일 이전 최신 공시치만" | 사전등록 v2 :128 · :185 |
| 진입 규칙 | "ENTER (AND): net_edge ≥ min_net_edge_8h ∧ funding_pctile_30d ≥ entry_pctile ∧ \|basis_pct\| ≤ max_entry_basis ∧ sign(ema_short)==sign(funding)" · `min_net_edge_8h = 0.00005` · `entry_pctile 0.50` | 사전등록 v2 :105 · :114~115 |
| 청산 규칙(v1) | "EXIT (OR) : net_edge ≤ 0 ∨ pctile < exit_pctile" · `exit_pctile 0.30` | 사전등록 v2 :107 · :115 |
| 청산 규칙(v2) | 히스테리시스(v2hyst 사전등록) — 결과의 청산 사유: regime_exit 16 · liq_distance 8 · end_of_sample 1 | v2 결과 JSON `exit_reasons` |
| 레버리지 · 배분 | `leverage=2.0` · `max_alloc=0.30` · `buffer_ratio=0.10` · `initial_capital=1000` | `carry_backtest_v2.py:27~29` |
| 판정 기준(요지) | "기회비용 차감 후 전체 순손익 > 0 AND 거래당 평균 > 0" · "net carry / capital locked > DGS2 평균" 등 | 사전등록 v2 :138~143 |

## 3. 원래 숫자(재현 확인의 기준 · 결과 JSON 그대로)
| 실행 | 거래 수 | 펀딩 수취 | 수수료 | 슬리피지 | 기회비용 | 순손익(USDT) | 비고 |
|---|---|---|---|---|---|---|---|
| v1(정정 전 · `carry_backtest_results.json`) | 77 | 53.83 | 43.81 | 5.84 | 2.91 | +1.58 | 정오표: 정정 뒤 −0.36 |
| v1_restated(`carry_backtest_v2_results.json`) | 77 | — | — | — | — | −0.358 | |
| **v2_primary** | **25** | 82.50 | 14.41 | 3.84 | 41.28 | **+23.67** | 보유 중앙 146 정산(≈ 49일) · 평균 176 |
| v2_no_accounting_fix | 25 | 82.51 | 14.41 | 1.92 | 41.30 | +24.88 | |

## 4. 장부의 모양 — 사용자 지시와 맞지 않는 점(숫자를 만지기 전에 보고)
1. **에피소드 장부가 아니다.** carrybot G1은 펀딩 분위·순 엣지 조건으로 들어가고 나오는 **거래 장부**다(v2: 25건 · 보유 중앙 ≈ 49일 · 고정 30일이 아니다). 사용자 지시 3("per episode … DTB3 30-day benchmark at entry")과 v3 carry 귀무("겹치지 않는 30일 에피소드")는 30일 고정 에피소드를 가정한다 — 거래 장부를 어떻게 에피소드로 바꿀지(거래 = 에피소드 · 거래를 30일 조각으로 나눔 · 30일 격자에 펀딩을 다시 모음)는 결정이 필요하다.
2. **거래별 장부 파일이 없다.** 결과 JSON에는 합계만 있다. 거래별 값은 carrybot 코드(`carrybot.carry.backtest.run_backtest`의 `r.trades`)를 **다시 돌려야** 나온다 — 그 코드는 `/home/cms/project/carrybot/data/vision`의 2026-07-31까지 자료를 읽는다. 이 저장소의 스크린 가드(2026-06-30 상한 · 우회 없음)는 그 코드 경로를 지나지 않는다 → 재현을 돌리려면 (가) carrybot 코드를 그대로 돌려 원래 숫자를 재현한 뒤 2026-06-30 이후 거래를 빼고 재가격하거나 (나) 이 저장소에서 같은 장부를 가드 위로 다시 만들어야 한다(재구현은 헌법 "측정용 재구현 금지"와 부딪힌다).
3. **벤치마크가 다르다.** carrybot은 DGS2(2년물)를 기회비용으로 이미 뺐다. 사용자 지시는 DTB3(3개월) 30일 환산이다 → 재가격은 carrybot의 기회비용을 빼지 않은 값(gross − 비용)에서 DTB3를 따로 비교해야 하고, 원래 숫자 재현은 DGS2 그대로 해야 한다.
4. **마지막 거래**: v2 청산 사유에 `end_of_sample` 1건 — 2026-07-31 끝에서 강제로 닫힌 거래가 있다. 6월 30일 상한을 지키면 그 거래(와 7월에 걸친 부분)는 빠진다.
5. **비용 시나리오의 대응**: carrybot의 왕복 0.3%(= 30 bps)는 사용자 시나리오 C(25 bps · BTC/USDT 테이커 + BNB)보다 크다 — 원래 모형 = 30 bps + 슬리피지 2 bps/다리.

## 5. 사용자 결정이 필요한 것(W3 2단계 전에)
1. 거래 장부 → 에피소드 대응(위 4-1의 셋 가운데 하나 · 또는 "거래 = 단위"로 귀무 H0를 거래 평균으로 읽기).
2. 장부를 얻는 길(4-2의 (가) carrybot 코드 재실행 + 6월 상한 절단 · 또는 (나)).
3. 프로토콜 v3 carry의 UNRESOLVED 둘(재표본 단위 · CI 수준).
