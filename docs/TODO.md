# TODO — BTC_Futures_E2E

> 경위는 `docs/ops_log.md`, 판정·사전등록은 `docs/trial_registry.md`, 설계는 `docs/design_v1.md`.

## 📌 현황 (2026-09-15)
- ✅ 부트스트랩 · layer 1 `exchange/` 구현·테스트 — **layer 2 착수 전 보고·확인 대기**
- 🚫 전략 코드 없음(layer 1~8 통과 전 금지) · 실주문 전송 경로 없음(layer 3에서 LIVE+체크리스트 게이트 뒤)

## 다음
1. [x] Codex 독립 검토 layer 1 — Q3·Q4·Q5 채택·수정 완료(ops_log 원문)
1b. [ ] **Codex 재검토 — 위 수정분**(계정 전역 헤지 사전검사 · Intent 기반 생성기 · 모양 예외 처리)
1c. [ ] 실계정 read-only 캡처로 positionRisk V2에 `isolated` 필드가 있는지 확인(Codex Q3 불확실 항목)
2. [ ] 실계정 read-only 캡처로 `positionSideDual`·`multiAssetsMargin` 합성 fixture 교체 (`exchange.loader.capture_snapshots`, 사용자 키 필요)
3. [ ] layer 2 `sizing/` — v6 격리 청산 공식 + liquidationFee(런타임) 속성 테스트
4. [ ] `ops/delivery_counter.DELIVERY` PROVISIONAL 값 → 레지스트리 행으로 확정 (layer 5 가동 전)
5. [ ] layer 4에서 `exchange/store.py` DDL을 마이그레이션 schema v1로 흡수
6. [ ] layer 5: E2E ShardWriter + #138 종료 플러시 테스트 복원 · layer 8: vps_health 스로틀 구조 · `data_stores` allowlist(설계 #131)
7. [ ] VPS: 봇 전용 Linux 사용자·systemd 유닛 (E2E 수집기와 분리 · 수집기 우선 · 수집기 데이터 디렉터리 금지) — **Codex 검토 대상(수집기 호스트)**
8. [ ] GitHub 원격 미설정 — CI는 푸시 후에야 실제로 돈다(푸시는 사용자 요청 시에만)

## ⚠️ 알고 있는 위험
- 패키지명 `telegram/`은 PyPI `python-telegram-bot`의 import 이름과 같다 — 그 라이브러리를 들이면 가려진다. 현재는 urllib 직접 호출이라 무해.
- 패키지명 `data/`는 코드 패키지다. 런타임 데이터는 `var/`(git 미추적).
