# TODO — BTC_Futures_E2E

> 경위는 `docs/ops_log.md`, 판정·사전등록은 `docs/trial_registry.md`, 설계는 `docs/design_v1.md`.

## 📌 현황 (2026-09-15)
- ✅ layer 1·2 수용(사용자 2026-09-15) · ✅ layer 3 `paper/` 구현·테스트·Codex MERGE — **layer 4 착수 전 보고·확인 대기**
- 🚫 전략 코드 없음(layer 1~8 통과 전 금지) · 🔴 실주문 경로 `paper/sender.py LiveSender` 존재(LIVE+체크리스트 전 항목 게이트 · 기동 배선 없음) · 테스트넷 프로브 **폐기**(파일만 미사용 보존)

## 다음
1. [x] Codex 독립 검토 layer 1 — Q3·Q4·Q5 채택·수정 완료(ops_log 원문)
1b. [x] Codex 재검토 — F1 PARTIAL · F2 CLOSED · F3 PARTIAL → 동의 항목 수정(ops_log)
1d. [x] algo 미체결 사전검사 — 공식 문서 확인 `GET /fapi/v1/openAlgoOrders`(`64a1a23`)
1e. [ ] 재검토 후 수정분(TransportError·_amt 엄격화) Codex 3차 검토 — 선택
1c. [ ] 실계정 read-only 캡처로 positionRisk V2에 `isolated` 필드가 있는지 확인(Codex Q3 불확실 항목)
2. [ ] **사용자 실행 대기** — `uv run python scripts/capture_account_snapshot.py`(read-only 키) → 합성 fixture 교체 + positionRisk `isolated` 필드 판정(1c 해결). 결과 보고 후 `gate._is_isolated` 확정
3. [x] layer 2 `sizing/` 구현·테스트(`d1ed96d`)
3a. [x] 사용자 결정 B1·B2 → 레지스트리 #2 · layer 2 재작업 완료
3d. [x] 레지스트리 #5 buffer 확정(1.5·10bp·mark)
3e. [x] Codex 재검토 — layer 2 이전 수정분 + B1·B2 + algo 사전검사(`task-mu27w8m4-oicyfq`) → Q4 수정
3f. [x] B5 → 레지스트리 #4 정확식 구현
3g. [x] B6 → 라이브 체크리스트(설계서 §10)
3i. [ ] 백로그: COIN-M(dapi) 포지션·미체결·algo 읽기 사전검사 — **엔드포인트 공식 문서 원문 확인 먼저**
3j. [ ] 페이퍼 14일차: 레지스트리 #5 재평가 새 행(체결 슬리피지 p99 · 모니터 주기 mark 이동 p99)
3k. [ ] **첫 라이브 진입부터**: 진입 후 검사 로그로 #4 수수료 가정 판정(레지스트리 #6) · 그때까지 보수 가정 유지(테스트넷·최소 명목 프로브 없음 — 사용자 2026-09-15)
3l. [x] ~~테스트넷 수수료 프로브~~ — **폐기**(사용자 2026-09-15). 파일 미사용 보존
3m. [x] layer 3 `paper/` — 송신기·엔진·테스트(설계서 §12)
3n. [x] layer 3 사용자 결정(2026-09-15): 실행 시점 재사이징 승인 · 체결 후 #5 위반 즉시 청산 승인 · 페이퍼 슬리피지 2 bps → 레지스트리 #7
3p. [ ] 페이퍼 14일차: 레지스트리 #7 슬리피지 재평가 새 행
3q. [ ] ccxt/ccxt.pro 전환(레지스트리 #8): 티어 테스트 · REST 어댑터 · watch 피드(layer 5) · Codex 검토
3h. [x] layer 3: 진입 전 `POST /leverage` 응답 == decision.leverage · 체결 후 positionRisk.liquidationPrice 재조회 → `post_entry_liquidation_check(실제 체결가·qty)` · 실제 체결 기준 SL 손실 재계산(Codex Q7)
3b. [x] Codex layer 2 검토 반영 — 동의 7건 수정(최종 명목 재검증·브라켓 단조 검증·NOTIONAL_CAP·Decimal 문맥)
3c. [x] layer 3: 진입 전 `POST /fapi/v1/leverage` 응답 == `SizingDecision.leverage` 확인 + 최종 브라켓 기록(Codex L2 Q5)
4. [x] 전달 감시 임계 → 레지스트리 #1 확정(kline1m_update·kline1m_close·markprice) — layer 5 writer가 kline을 두 kind로 기록해야 재생 어댑터가 같은 값을 센다
5. [ ] layer 4에서 `exchange/store.py` DDL을 마이그레이션 schema v1로 흡수
6. [ ] layer 5: E2E ShardWriter + #138 종료 플러시 테스트 복원 · layer 8: vps_health 스로틀 구조 · `data_stores` allowlist(설계 #131)
7. [ ] VPS: 봇 전용 Linux 사용자·systemd 유닛 (E2E 수집기와 분리 · 수집기 우선 · 수집기 데이터 디렉터리 금지) — **Codex 검토 대상(수집기 호스트)**
8. [ ] GitHub 원격 미설정 — CI는 푸시 후에야 실제로 돈다(푸시는 사용자 요청 시에만)

## ⚠️ 알고 있는 위험
- ~~패키지명 `telegram/` 가림 위험~~ → 2026-09-15 `notify/`로 개명 완료.
- 패키지명 `data/`는 코드 패키지다. 런타임 데이터는 `var/`(git 미추적).
