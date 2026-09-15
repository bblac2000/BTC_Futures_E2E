# TODO — BTC_Futures_E2E

> 경위는 `docs/ops_log.md`, 판정·사전등록은 `docs/trial_registry.md`, 설계는 `docs/design_v1.md`.

## 📌 현황 (2026-09-15)
- ✅ 부트스트랩 · layer 1 `exchange/` 구현·테스트 — **layer 2 착수 전 보고·확인 대기**
- 🚫 전략 코드 없음(layer 1~8 통과 전 금지) · 실주문 전송 경로 없음(layer 3에서 LIVE+체크리스트 게이트 뒤)

## 다음
1. [x] Codex 독립 검토 layer 1 — Q3·Q4·Q5 채택·수정 완료(ops_log 원문)
1b. [x] Codex 재검토 — F1 PARTIAL · F2 CLOSED · F3 PARTIAL → 동의 항목 수정(ops_log)
1d. [ ] algo 미체결 조회 경로를 공식 문서로 확인 후 헤지 전환 사전검사에 추가(Codex F1-b)
1e. [ ] 재검토 후 수정분(TransportError·_amt 엄격화) Codex 3차 검토 — 선택
1c. [ ] 실계정 read-only 캡처로 positionRisk V2에 `isolated` 필드가 있는지 확인(Codex Q3 불확실 항목)
2. [ ] **사용자 실행 대기** — `uv run python scripts/capture_account_snapshot.py`(read-only 키) → 합성 fixture 교체 + positionRisk `isolated` 필드 판정(1c 해결). 결과 보고 후 `gate._is_isolated` 확정
3. [ ] layer 2 `sizing/` — v6 격리 청산 공식 + liquidationFee(런타임) 속성 테스트
4. [x] 전달 감시 임계 → 레지스트리 #1 확정(kline1m_update·kline1m_close·markprice) — layer 5 writer가 kline을 두 kind로 기록해야 재생 어댑터가 같은 값을 센다
5. [ ] layer 4에서 `exchange/store.py` DDL을 마이그레이션 schema v1로 흡수
6. [ ] layer 5: E2E ShardWriter + #138 종료 플러시 테스트 복원 · layer 8: vps_health 스로틀 구조 · `data_stores` allowlist(설계 #131)
7. [ ] VPS: 봇 전용 Linux 사용자·systemd 유닛 (E2E 수집기와 분리 · 수집기 우선 · 수집기 데이터 디렉터리 금지) — **Codex 검토 대상(수집기 호스트)**
8. [ ] GitHub 원격 미설정 — CI는 푸시 후에야 실제로 돈다(푸시는 사용자 요청 시에만)

## ⚠️ 알고 있는 위험
- ~~패키지명 `telegram/` 가림 위험~~ → 2026-09-15 `notify/`로 개명 완료.
- 패키지명 `data/`는 코드 패키지다. 런타임 데이터는 `var/`(git 미추적).
