# 트라이얼 #2 구현 규약 초안(단계 2i 레지스트리 행의 원천 · 실데이터 실행 전에 행으로 확정)

> 초안 — 레지스트리 행이 되기 전까지 바뀔 수 있다. 각 항목은 근거(ops_log 검토 항목)와 함께.

1. **청산 수수료 기준** = 수량 × 추정 청산가 × liquidationFee(`SizingLimits.liq_fee_on_liq_price=True`) — §1 46행 문언. 레지스트리 #2는 "명목×fee"로 기준 미지정 · 트라이얼 #1은 진입 명목(엔진 기본 · 불변). 근거: advisor 2b·2c #1 · Codex #1.
2. **P3 SL 자리표시**: `EntryIntent.sl == SlFromFill.anchor(= O_d)` · 실제 SL′ = 2 × 예상 체결가 − O_d(사이징 전 확정). 근거: Codex 2b·2c #3(수용).
3. **고정 사이징 자본**: 체결된 진입마다 실행 지갑 → E_ref 1,000 · Δ지갑 = 청산 후 − E_ref · 거부·0체결은 리셋 없음 · 보고 원장 = net_pnl 누적 · 판정기는 `final_wallet`을 읽지 않는다. 근거: before-pass #1.
4. **레버리지 대역**: `SizingLimits(leverage_range=(10,30))` 명시 · 봇 기본 (50,100) 불변(#30 · §11-3).
5. **23:59 봉 7단계**(재생 루프 훅) + 훅 분 전략 판단 뒤 대기 진입 없음 단언. 근거: before-pass #4 · advisor 2b·2c #2.
6. **P2 대기열**: 원 교차에서 소비·대기열 · i+k 마감 판정 · conflict → position_busy → dropped(체결 ≥ 원래 날 23:59) → 가격 게이트 · 다음 날로 넘기지 않음. 근거: before-pass #5.
7. **동시 교차**: 한 봉에서 **아직 소비되지 않은** 두 방향이 함께 처음 교차할 때만 `conflict_cross`(둘 다 소비) · 한 방향이 이미 소비됐으면 다른 방향의 첫 교차는 정상 셋업(§1 35행 "방향별 첫 교차 하나만 셋업"). 근거: advisor 2d·2e #1.
8. **건너뜀 첫 실패 순서**: conflict_cross → position_busy → late_cross → sl_wrong_side → sl_dist_out_of_range(바닥/천장) → (엔진) sl_crossed_before_fill → sizing_rejected / normalization. 보고용(판정 무관).
9. **펀딩 존재 판정**: 경계 b의 확정 펀딩 = b ≤ funding_ms < b + 60,000(재생 정산과 같은 분 버킷).
10. **P4 추출**: 유효·범위 있는 날마다 `integers(1, ⌊R/tick⌋ + 1)` 1회 · 무범위·무효일은 난수 없음.
11. **Arm B 중앙값**: 정확한 Decimal(20개 · 가운데 둘의 평균) · 엄격 `<`.
12. **워밍업**: 창 시작 전 21일은 R·중앙값만 쌓고 진입·분모 없음 · O_d는 그날 첫 봉이 00:00 봉일 때만(아니면 그날은 이미 무효).
13. **플라시보는 Arm A만**(§4 "원판 = Arm A · IS").
14. **§9 ③ 정적 검사 범위**: `strategies/trial02/*.py` — `.rolling(` · `deque` · donchian/channel 이름 · 봉 창 슬라이스 위 max/min 금지.
15. **부트스트랩 스트림 표**: `SeedSequence((20260924,1)).spawn(8)[k]` · k = 0 gross_A · 1 net_A · 2 gross_B · 3 net_B · 4 A/B 일별 대비.
16. **§11-8**: 산출물 스키마 · 격리 CLI 경로 · 커밋/푸시 증거(판정기 푸시 커밋 해시) — 2g에서 채운다.
