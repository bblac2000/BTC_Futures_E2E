# 헌법 v1.6 개정안 (초안 · 병합 전)

> **병합 전에는 실주문·페이퍼 주문이 하나도 없다**(P0 실행 감사의 0.001 BTC 대조군 포함). 배포는 claude.ai의 마스터 zip으로만 — 저장소의 스킬 사본은 고치지 않는다.
> 근거: 사용자 결정 2026-10-14(프롬프트 W5 · 레지스트리 #100) · 검토 `reports/advisory/w5_constitution_v16_pre.md` · `reports/codex/`.
> **사용자가 정한 여섯 항목 가운데 1(현물 헤지 다리)과 2(현물 메이커 주문)는 이 판에서 뺐다** — Codex가 (가) 한 방향 연동안에서도 청산 안전 문제로 두 번 BLOCK했고, 사용자가 미리 정한 대체안 (나)를 적용했다(#100). 아래 네 항목은 그 둘에 기대지 않는다.

## 1. 선물 진입 GTX(post-only) — 진입 전용
1. `timeInForce=GTX`는 **진입 의도가 있는 주문에만** 쓴다. 청산·SL·TP·트레일링·킬스위치·청산 거리 게이트 실패 정리는 지금처럼 전부 **MARKET reduceOnly**다.
2. 상태와 결과(고정):
   - (i) **놓을 때 거부**(교차 — 오류 −5022 · 아무것도 놓이지 않음) → 새 같은 쪽 최우선호가로 다시 놓는다 · N에 센다.
   - (ii) **전송 실패 · 결과 미상** → 다음 주문이나 폴백 전에 주문 상태가 **종결로 확인**돼야 한다. 미상은 결코 "건너뛰기"가 되지 않는다. 확인되지 않으면 `OrderOutcomeUnknown`(기존 방식)이 진입을 막고, 감시는 계속된다.
   - (iii) **놓였으나 시도별 시간 초과까지 미체결** → 취소 → 종결 상태 확인.
   - (iv) **부분 체결** → 포지션 = 체결된 수량. **SL 감시는 첫 체결 확인 시점부터** 켠다(취소나 나머지 완료를 기다리지 않는다). 사이징 검사 · MIN_NOTIONAL · 청산 거리 게이트를 실제 수량으로 다시 돌린다. 체결 뒤 게이트가 실패하면 기존의 즉시 MARKET reduceOnly 정리. 설정에 따라 나머지를 MARKET으로 채울 수 있다 — 단 **놓여 있는 GTX를 먼저 취소하고 종결 상태를 확인한 뒤**, 나머지 = 목표 − **누적 체결 수량**으로 다시 계산해서만 보낸다(취소 전에 보낸 MARKET이 놓인 주문의 뒤늦은 체결과 겹쳐 노출이 목표를 넘는 일을 막는다). 결과가 미상이면 나머지를 보내지 않는다. 나머지는 따로 검증하며, MIN_NOTIONAL을 맞추려고 노출을 키우지 않는다. "건너뛰기"는 아무것도 체결되지 않았을 때만.
3. **종결 확인 장벽**: 재호가 · 나머지 · 폴백 — 진입 의도 안에서 새 주문을 하나라도 보내기 전에, 그 의도의 앞선 모든 주문의 종결 상태가 확인돼야 한다(시한 전의 나머지 채우기도 같다). 미상이면 아무것도 보내지 않는다.
3-1. 한도: 진입 의도마다 **재호가 최대 N회 그리고 총 시간 상한**. 어느 쪽이든 닿으면 — 모든 주문의 종결 상태를 확인한 뒤 — 설정에 따라 MARKET 폴백(폴백 가격에서 정규화 · MIN_NOTIONAL · 청산 게이트를 다시 돌린다) 또는 건너뛰기.
4. **진입 의도의 무효화**: 그 포지션의 어떤 청산(SL · TP · 트레일링 · 킬스위치 · 체결 뒤 게이트 정리)이나 킬스위치 발동은 진입 의도를 무효로 한다. 청산을 **먼저** 보내고, 그 뒤 그 의도의 남은 진입 주문을 모두 취소한다(청산을 늦추지 않는다). 취소와 경합한 체결은 새 노출로 보고 기존 MARKET reduceOnly로 즉시 닫는다. 무효가 된 의도로는 재호가도 나머지 폴백도 보내지 않는다. 의도를 닫기 전에 모든 주문의 종결 상태를 확인한다.
5. 주문 갱신 처리(사용자 데이터 스트림 또는 조회)가 필요하다 — 요구만 적고 설계는 하지 않는다.
6. **바뀌는 문장과 남는 문장**:
   - 바뀜: SKILL.md §1-1 "진입·청산 전부 `type=MARKET`" → "**선물 청산은 전부 MARKET reduceOnly · 선물 진입은 MARKET 또는 이 항목의 GTX**" · SKILL.md §3-1 "피라미딩·트레일링·부분익절 … 전부 봇 모니터링 + MARKET(청산 reduceOnly)" → 청산 쪽은 그대로, "피라미딩 추가는 진입이므로 이 항목의 GTX를 쓸 수 있다"를 덧붙임 · references/exchange-rules.md의 주문 정책 · references/open-decisions.md의 MARKET 전용 문장 · references/strategy-modules.md의 고급 주문 점검표("전부 MARKET/reduceOnly")와 §3 머리말("전부 봇 모니터링 + MARKET(청산은 reduceOnly)") → 같은 처리(청산은 그대로 MARKET reduceOnly · 피라미딩 추가 같은 진입은 이 항목의 GTX 허용) · references/exchange-rules.md 정규화 5번("LIMIT을 쓴다면 PERCENT_PRICE … 이 봇은 MARKET 전용이라 해당 없음") → "GTX 진입 주문은 PERCENT_PRICE(mark ±5%) 안이어야 한다 · 그 밖의 주문은 MARKET"으로 적용 범위를 바꾼다.
   - 페이퍼 체결: references/research-protocol.md와 strategy-modules.md의 "페이퍼는 테이커 전용"은 **그대로 유지**한다 — GTX 진입의 페이퍼 체결 모형은 측정된 감사(M-1 등)가 명시적 예외를 허락할 때만 쓰며, "가격 닿음 = 체결"은 어디서도 허용하지 않는다.
   - 남음: 모든 선물 청산 · SL · TP · 트레일링 · 킬스위치 = MARKET reduceOnly · `side`는 BUY/SELL만 · 원웨이 · ISOLATED · 서버측 STOP/TP 없음 · GTX는 진입 의도에만.

## 2. 정오표 — forceOrder 문구(충돌 기록 · 고르지 않음)
> 공식 변경 기록(2026-04-10)은 심볼별 1000 ms 스냅샷이 'latest'에서 'largest'로 바뀌었다고 적는다. 2026-10-14에 읽은 스트림 참조 문구는 여전히 'latest'라고 한다. 상태 **[DOC-CONFLICT]** — 스트림 자체로는 확인할 수 없다(한 번에 한 건만 푸시된다). 운영 결론은 그대로: 청산 총량 지표가 아니다 · 각 푸시는 그 1초 안에서 순위를 모르는 주문 한 건으로 다룬다.
- 출처 1(변경 기록 · https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10): "Liquidation Order Streams (`<symbol>@forceOrder`) and All Market Liquidation Order Streams (`!forceOrder@arr`) — Updated description: changed "only the latest one liquidation order" to "only the largest one liquidation order" within 1000ms."
- 출처 2(스트림 참조 문구 · https://developers.binance.com/en/docs/llms-full.txt, 2026-10-14에 읽음 · Last-Modified 2026-10-13): "The Liquidation Order Snapshot Streams push force liquidation order information for specific symbol. For each symbol，only the latest one liquidation order within 1000ms will be pushed as the snapshot."
- 증거의 한계: 출처 2는 공식 문서 묶음 파일에서 찾았고, 그 블록 자신의 페이지 URL은 묶음에서 복원되지 않는다. v1.5는 출처 1에 따라 "largest"를 적었다.

## 3. 이월 항목(레지스트리 #86 ~ #88 · 사용자 승인 · 트라이얼 #5부터 · 소급 없음)
1. **앵커 전 검정력 관문**: 사전등록에 IS 이전 자료의 표준편차 · 투영 n · 판정기 MDE 식으로 계산한 **N 보정 투영 MDE**를 적는다. **θ = 10 bps(순 엣지 문턱) · MDE > 2θ = 20 bps → 검정력 부족** — N 보정 투영 MDE ≤ 20 bps가 아니면 앵커하지 않는다.
2. **P1의 SL 승계 여부**: 원판에 SL이 있으면 P1 슬롯이 같은 sl_dist의 SL을 물려받는지를 귀무의 정의로 **명시**한다 — 기본값을 두지 않는다.
3. **사이징 가능성 보정**: E_ref · 리스크 예산 · 최소 수량에서 체결할 수 없는 sl_dist × 가격 구간과 그 구간에 드는 후보 비율을 IS 이전 보정에 적는다.

## 4. 가족별 벤치마크(D6 · 프로토콜 조항)
- carry → 3개월 미 재무부 단기채(FRED DTB3 · 시점 기준 · 보유 기간으로 환산) · execution → 결정 시각의 즉시 테이커 실행 가능 가격 · directional → 변동성 목표 롱 온리 BTC.
- 벤치마크는 **보고하는 비교**다. 정식 트라이얼의 P1(노출 정합 무작위 타이밍) 벤치마크 게이트를 대체하지 않는다. references/strategy-modules.md 평가지표 표의 "벤치마크 대비(BTC 보유·무위험) — 최종 게이트" 행은 "보고(가족별 벤치마크)"로 바꾸고, 게이트는 정식 트라이얼의 P1 벤치마크 게이트임을 같은 표에 적는다. 예외: 스크린 프로토콜 v3의 carry 가족 통과 귀무는 DTB3를 쓴다(스크린 한정 · 정식 판정기에는 영향 없음).
