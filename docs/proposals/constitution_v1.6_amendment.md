# 헌법 v1.6 개정안 (초안 · 병합 전)

> **병합 전에는 실주문·페이퍼 주문이 하나도 없다**(P0 실행 감사의 0.001 BTC 대조군 포함). 배포는 claude.ai의 마스터 zip으로만 — 저장소의 스킬 사본은 고치지 않는다.
> 근거: 사용자 결정 2026-10-14(프롬프트 W5 · 레지스트리 #100 · #105 · #107 · #113) · 검토 `reports/advisory/w5_constitution_v16_pre.md` · `reports/codex/`.
> **r3(사용자 #105)**: 선물 진입 GTX(post-only) 조항을 뺐다(M-1 ≈ 0.5 bps). Codex 문서 r3 = BLOCK(#106).
> **r4(사용자 #107)**: 현물 헤지 정책 1 ~ 7. Codex 문서 r4 = BLOCK-USER(#109).
> **r5(사용자 #113)**: #109의 답은 (B)였으나, 사용자가 건 조건 — "S-carry-1이 carry 가족을 닫았으면 현물 헤지 1 · 2항은 쓸 전략이 없다 → 빼고 최소 묶음으로" — 이 충족됐다(S-carry-1 RESULT · POST 행 · #110 · learnings L18). 그래서 **현물 헤지 다리와 현물 메이커 조항을 뺐다.** 이 판은 **주문에 닿는 것이 없다**: forceOrder 정오표 · 이월 항목 셋 · 가족별 벤치마크뿐이다. 주문 정책(MARKET 전용 · 청산 reduceOnly · 서버측 STOP/TP 없음)은 v1.5 그대로다. 현물 헤지가 다시 필요해지면 carry 가족 재개(사용자 레지스트리 행)와 새 개정안이 먼저다 — r4까지의 검토 기록(`reports/codex/w5_constitution_v16_rounds.md`)은 그때의 출발점이다.

## 1. 정오표 — forceOrder 문구(충돌 기록 · 고르지 않음)
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

## 2. 이월 항목(레지스트리 #86 ~ #88 · 사용자 승인 · 트라이얼 #5부터 · 소급 없음)
1. **앵커 전 검정력 관문**: 사전등록에 IS 이전 자료의 표준편차 · 투영 n · 판정기 MDE 식으로 계산한 **N 보정 투영 MDE**를 적는다. **θ = 10 bps(순 엣지 문턱) · MDE > 2θ = 20 bps → 검정력 부족** — N 보정 투영 MDE ≤ 20 bps가 아니면 앵커하지 않는다.
2. **P1의 SL 승계 여부**: 원판에 SL이 있으면 P1 슬롯이 같은 sl_dist의 SL을 물려받는지를 귀무의 정의로 **명시**한다 — 기본값을 두지 않는다.
3. **사이징 가능성 보정**: E_ref · 리스크 예산 · 최소 수량에서 체결할 수 없는 sl_dist × 가격 구간과 그 구간에 드는 후보 비율을 IS 이전 보정에 적는다.

## 3. 가족별 벤치마크(D6 · 프로토콜 조항)
- carry → 3개월 미 재무부 단기채(FRED DTB3 · 시점 기준 · 보유 기간으로 환산) · execution → 결정 시각의 즉시 테이커 실행 가능 가격 · directional → 변동성 목표 롱 온리 BTC.
- 벤치마크는 **보고하는 비교**다. 정식 트라이얼의 P1(노출 정합 무작위 타이밍) 벤치마크 게이트를 대체하지 않는다. references/strategy-modules.md 평가지표 표의 "벤치마크 대비(BTC 보유·무위험) — 최종 게이트" 행은 "보고(가족별 벤치마크)"로 바꾸고, 게이트는 정식 트라이얼의 P1 벤치마크 게이트임을 같은 표에 적는다. 예외: 스크린 프로토콜 v4(#111)의 carry 가족 통과 귀무는 DTB3를 쓴다(스크린 한정 · 정식 판정기에는 영향 없음 · carry 가족은 #110에서 닫혔다).
