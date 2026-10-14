# 헌법 v1.6 개정안 (초안 · 병합 전)

> **병합 전에는 실주문·페이퍼 주문이 하나도 없다**(P0 실행 감사의 0.001 BTC 대조군 포함). 배포는 claude.ai의 마스터 zip으로만 — 저장소의 스킬 사본은 고치지 않는다.
> 근거: 사용자 결정 2026-10-14(프롬프트 W5 · 레지스트리 #100 · #105 · #107) · 검토 `reports/advisory/w5_constitution_v16_pre.md` · `reports/codex/`.
> **r3(사용자 #105)**: W5 Q1 = (B) — 선물 진입 GTX(post-only) 조항을 뺐다(M-1이 메이커 진입 전체를 ≈0.5 bps로 쟀다). 현물 헤지 다리(1)와 현물 메이커(2)를 다시 넣었다. Codex 문서 r3 = BLOCK(#106).
> **r4(사용자 #107)**: r3의 "헤지 실패는 선물을 닫지 않는다"는 **거부됐다** — 선물 숏은 캐리 헤지로만 존재하며, 현물 다리 없는 선물 숏은 의도하지 않은 방향 베팅이다. 1 · 2는 #107의 정책 1~7을 그대로 옮긴 것이다(현물 먼저 진입 · 헤지 실패 = 전략 수준 flat 신호 · 증거금 보충/감축 규칙 삭제 · 현물 생애 주기 · 부호 · 재시도 한도 · 진입 차단).

## 1. 현물 헤지 다리(같은 계정 BTCUSDT 무기한 **숏**을 덮는 현물 BTC **롱** · BTC/FDUSD · BTC/USDT만 · 현물 단독 금지 · 사이징은 선물 다리 규칙에서 — 현물 목표 수량 = 선물 사이징이 정한 숏 수량)
1. **진입 순서 — 현물 먼저(#107-1)**: 현물 다리를 먼저 놓는다(BTC/FDUSD 메이커 · 설정 시한 · 시간 단위 · 항목 2). **선물 숏은 현물 체결이 확인된 뒤에만, 확인된 현물 수량만큼 MARKET으로** 연다. 현물 재고가 있기 전에 선물 숏을 여는 일은 없다 — 진입 시 헤지 실패는 구조적으로 없다. 선물 진입은 기존 규칙(정규화 · MIN_NOTIONAL · 청산 거리 게이트 · 마진 캡)을 그대로 통과해야 하고, 통과하지 못하면 선물을 열지 않고 확인된 현물 재고를 MARKET으로 판다(1-4와 같은 정리).
2. **한 방향 의존과 유일한 접점(#107-2)**: 현물 모듈은 선물 청산 함수를 부르지도 · 막지도 · 바꾸지도 않는다. 현물 → 선물의 **유일한 접점은 캐리 전략의 TargetState**다 — 전략이 선물 TargetState를 flat으로 두면 **기존 선물 청산 경로(MARKET reduceOnly)**가 다른 모든 전략 청산과 똑같이 숏을 닫는다. 선물 청산 경로 · SL · TP · 트레일링 · 킬스위치 자체는 바뀌지 않는다. 선물 다리의 기존 안전장치(사이징 · SL · 청산 거리 게이트 · 마진 캡 · 레버리지)는 그대로 적용된다.
3. 수량과 방향: 목표 선물 숏 = 확인된 현물 순 BTC 재고(수수료 뒤 · 두 거래소 쪽 런타임 필터 · 리터럴 없음) · d = 현물 BTC − |선물 숏|(부호 있는 선물 amt < 0) · 선물 한 step 허용치는 먼지 허용이지 의도한 노출이 아니다.
4. **선물 감소 · 청산 · 강제 청산 사건마다 현물 쪽(한 방향 구독 · #107-4)**: ① 놓여 있는 현물 주문을 **모두 취소**하고 종결 상태를 확인한다 ② 어떤 폴백이든 보내기 전에 **살아 있는 선물 숏을 다시 확인**한다 ③ 선물 청산 뒤 늦게 체결된 현물은 **즉시 MARKET 매도**로 정리한다(잔여 가드 문턱과 무관 · 현물 필터 아래 먼지는 보고만) ④ 선물 강제 청산 뒤 현물 재고는 단독 롱이므로 같은 규칙으로 **MARKET 매도**한다. 현물에는 reduceOnly가 없으므로 매도 수량은 실제 헤지 재고로 묶는다. 결과 미상이면 대체 주문을 보내지 않고 진입을 막으며 감시는 계속한다(킬스위치 뒤에도).
5. **잔여 델타 가드(#107-2 · #107-5)**: 대사 주기마다 **|d| × mark > 문턱이 설정 시간보다 오래** 이어지면 부호로 나눈다 — **d > 0**(현물 초과) → 초과 현물을 MARKET 매도 · **d < 0**(숏이 현물보다 큼) → **전략 수준 flat 신호**(1-2: 선물 TargetState = flat → 기존 MARKET reduceOnly 청산 → 그 청산 사건으로 1-4가 현물을 정리).
6. **재시도 한도(#107-6)**: 현물 배치 · 재호가 · 가드 주문은 **총 시도 상한과 총 벽시계 상한**(설정값 · 진입 의도 또는 가드 사건마다 · 타이머를 다시 시작해 늘리지 않는다)을 가진다. 어느 쪽이든 닿으면 **전략 flat 신호(1-5)와 경보**로 올린다. 끝없는 반복은 없다. 감시는 주문 반복과 별개로 계속된다.
7. **진입 차단(#107-7)**: 헤지 실패 조건(가드 발동 · 결과 미상 · 한도 소진 · 디페그)이 하나라도 살아 있는 동안 신규 진입을 **막는다**(경보만이 아니다).
8. **증거금 보충/감축 규칙은 두지 않는다(#107-3 · 의도적)**: 헤지가 없으면 답은 포지션 없음이지 증거금 추가가 아니다. 현물 BTC는 선물 증거금이 되지 않는다 · 선물 다리는 ISOLATED · 기존 레버리지 · 위험 · 마진 캡 · 청산 거리 게이트를 그대로 쓴다.
9. 디페그 감시: FDUSDUSDT 현물 시세(해당하면 USDT 짝도) · 설정 문턱은 신규 진입을 막는다(1-7).
10. 비용 모형의 결과: 진입은 현물 메이커 + 선물 테이커, 정리는 테이커(P1 비용 시나리오 B · #105는 carry 가족의 주 시나리오를 B로 정했다).

## 2. 현물 메이커 주문 — 헤지 다리 **진입 전용**
1. 헤지 다리 진입(1-1)에만 현물 메이커(post-only · LIMIT_MAKER) 주문을 쓴다. **최대 대기 시간은 설정값이며 시간 단위**(#105). 시한에 닿으면 앞 주문을 취소하고 **종결 상태를 확인한 뒤**, 진입 의도가 아직 유효할 때만 확인된 미체결 나머지를 테이커(MARKET)로 — 또는 설정에 따라 진입을 접는다. 결과 미상이면 아무것도 보내지 않고 진입 차단(1-7) · 감시 계속. 모든 시도는 1-6의 한도 안이다.
2. 대기 중에는 선물 숏이 아직 없다(1-1) — 덮이지 않은 선물 노출이 생기지 않는다. 대기 중 체결된 부분 현물에 대해서만 선물 숏을 연다(확인된 수량).
3. 시간에 묶인 주문(모든 청산 · 현물 정리 · 잔여 가드 정리 · 킬)에는 메이커를 **금지**한다.
4. 배치 · 체결 · 시간 초과 · 폴백을 기록한다 · 주문 갱신 처리(사용자 데이터 스트림 또는 조회)가 필요하다 — 요구만 적고 설계는 하지 않는다.
5. 페이퍼 체결: "페이퍼는 테이커 전용"을 **그대로 유지**한다 — 현물 메이커의 페이퍼 체결 모형은 측정된 감사가 명시적 예외를 허락할 때만(현물 수동 체결 측정은 아직 없다 · #105) · "가격 닿음 = 체결"은 어디서도 허용하지 않는다.

### 1 · 2의 바뀌는 문장과 남는 문장
- 바뀜: SKILL.md §1-1 "진입·청산 전부 `type=MARKET`" → "**선물 주문은 전부 MARKET(청산 reduceOnly)** · 현물 헤지 다리는 항목 1 · 2(진입은 시간 한도 있는 메이커 또는 MARKET · 정리는 재고로 묶인 MARKET 매도)" · references/exchange-rules.md의 주문 정책(같은 처리 · 현물 필터는 현물 exchangeInfo 런타임 조회 · v6 문서는 선물 문서이므로 현물 값의 진리원이 아님) · references/open-decisions.md의 대상 심볼(BTCUSDT 무기한 + 헤지 다리 한정 BTC/FDUSD · BTC/USDT 현물)과 MARKET 전용 문장 · references/strategy-modules.md의 고급 주문 점검표와 §3 머리말(선물은 그대로 · 현물 헤지 다리 예외 한 줄) · 안전장치 목록에 "잔여 델타 가드 → 전략 flat 신호"와 "헤지 실패 중 진입 차단" 추가 · 대사 항목에 현물 잔고 추가.
- 남음: **모든 선물 주문** = MARKET · 선물 청산 · SL · TP · 트레일링 · 킬스위치 = MARKET reduceOnly · `side`는 BUY/SELL만 · 원웨이 · ISOLATED · 서버측 STOP/TP 없음 · 선물 진입 GTX 없음 · reduceOnly 불변식은 선물 주문 범위.

## 3. 정오표 — forceOrder 문구(충돌 기록 · 고르지 않음)
> 공식 변경 기록(2026-04-10)은 심볼별 1000 ms 스냅샷이 'latest'에서 'largest'로 바뀌었다고 적는다. 2026-10-14에 읽은 스트림 참조 문구는 여전히 'latest'라고 한다. 상태 **[DOC-CONFLICT]** — 스트림 자체로는 확인할 수 없다(한 번에 한 건만 푸시된다). 운영 결론은 그대로: 청산 총량 지표가 아니다 · 각 푸시는 그 1초 안에서 순위를 모르는 주문 한 건으로 다룬다.
> **User master text (verbatim, English):** "Official change log (2026-04-10) states the per-symbol 1000 ms snapshot changed from 'latest' to 'largest'; the stream reference page as read on 2026-10-14 still says 'latest'. Status [DOC-CONFLICT], unverifiable from the stream itself (only one order is ever pushed). Operational conclusion unchanged: not a liquidation-volume measure; treat each push as one order of unknown rank within its second."

- 출처 1(변경 기록 · https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log#2026-04-10 · 원래 줄 바꿈 그대로):
  ```
  - Liquidation Order Streams (`<symbol>@forceOrder`) and All Market Liquidation Order Streams
    (`!forceOrder@arr`)
    - Updated description: changed "only the latest one liquidation order" to "only the largest one
      liquidation order" within 1000ms.
  ```
- 출처 2(스트림 참조 문구 · https://developers.binance.com/en/docs/llms-full.txt, 2026-10-14에 읽음 · Last-Modified 2026-10-13): "The Liquidation Order Snapshot Streams push force liquidation order information for specific symbol. For each symbol，only the latest one liquidation order within 1000ms will be pushed as the snapshot."
- 증거의 한계: 출처 2는 공식 문서 묶음 파일에서 찾았고, 그 블록 자신의 페이지 URL은 묶음에서 복원되지 않는다. v1.5는 출처 1에 따라 "largest"를 적었다.

## 4. 이월 항목(레지스트리 #86 ~ #88 · 사용자 승인 · 트라이얼 #5부터 · 소급 없음)
1. **앵커 전 검정력 관문**: 사전등록에 IS 이전 자료의 표준편차 · 투영 n · 판정기 MDE 식으로 계산한 **N 보정 투영 MDE**를 적는다. **θ = 10 bps(순 엣지 문턱) · MDE > 2θ = 20 bps → 검정력 부족** — N 보정 투영 MDE ≤ 20 bps가 아니면 앵커하지 않는다.
2. **P1의 SL 승계 여부**: 원판에 SL이 있으면 P1 슬롯이 같은 sl_dist의 SL을 물려받는지를 귀무의 정의로 **명시**한다 — 기본값을 두지 않는다.
3. **사이징 가능성 보정**: E_ref · 리스크 예산 · 최소 수량에서 체결할 수 없는 sl_dist × 가격 구간과 그 구간에 드는 후보 비율을 IS 이전 보정에 적는다.

## 5. 가족별 벤치마크(D6 · 프로토콜 조항)
- carry → 3개월 미 재무부 단기채(FRED DTB3 · 시점 기준 · 보유 기간으로 환산) · execution → 결정 시각의 즉시 테이커 실행 가능 가격 · directional → 변동성 목표 롱 온리 BTC.
- 벤치마크는 **보고하는 비교**다. 정식 트라이얼의 P1(노출 정합 무작위 타이밍) 벤치마크 게이트를 대체하지 않는다. references/strategy-modules.md 평가지표 표의 "벤치마크 대비(BTC 보유·무위험) — 최종 게이트" 행은 "보고(가족별 벤치마크)"로 바꾸고, 게이트는 정식 트라이얼의 P1 벤치마크 게이트임을 같은 표에 적는다. 예외: 스크린 프로토콜 v3의 carry 가족 통과 귀무는 DTB3를 쓴다(스크린 한정 · 정식 판정기에는 영향 없음).
