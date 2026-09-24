# TODO — BTC_Futures_E2E

> 경위는 `docs/ops_log.md`, 판정·사전등록은 `docs/trial_registry.md`, 설계는 `docs/design_v1.md`.

## 📌 현황 (2026-09-15)
- ✅ layer 1~7 수용(사용자 2026-09-16) · ✅ 레지스트리 #11·#12·#13 · ✅ layer 8 `ops/` 런타임·러너·VPS 템플릿·런북 · 페이퍼 드라이런 3회 · Codex MERGE(검토 5회) · **보고 → VPS 배포 논의 대기**
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
3q. [x] ccxt/ccxt.pro 전환(레지스트리 #8): 티어 테스트 · REST 어댑터 · watch 피드(layer 5) · 라이브 전달 프로브 — Codex MERGE(어댑터 검토 4회·피드·백필 1회)
3r. [x] layer 5: `data/shards.py`(E2E ShardWriter·WriterThread·#138·shutdown_record 이식) · 소켓별 connect/disconnect/reconnect 대장 이벤트 · 소켓별 23h 선제 재연결 · klines limit 공식 렌더링 확인(max 1500 · 운영 1000=weight 5) · 기동 배선은 layer 8
3s. [x] 사용자 결정(2026-09-15): LIVE 예상 체결가 = #7 모델(레지스트리 #9) · `adverse_fill_estimate` 공용 — Codex 검토 대상(LiveSender)
3h. [x] layer 3: 진입 전 `POST /leverage` 응답 == decision.leverage · 체결 후 positionRisk.liquidationPrice 재조회 → `post_entry_liquidation_check(실제 체결가·qty)` · 실제 체결 기준 SL 손실 재계산(Codex Q7)
3b. [x] Codex layer 2 검토 반영 — 동의 7건 수정(최종 명목 재검증·브라켓 단조 검증·NOTIONAL_CAP·Decimal 문맥)
3c. [x] layer 3: 진입 전 `POST /fapi/v1/leverage` 응답 == `SizingDecision.leverage` 확인 + 최종 브라켓 기록(Codex L2 Q5)
4. [x] 전달 감시 임계 → 레지스트리 #1 확정(kline1m_update·kline1m_close·markprice) — layer 5 writer가 kline을 두 kind로 기록해야 재생 어댑터가 같은 값을 센다
5. [x] layer 4 `db/`: 마이그레이션 도구 · v1(§5 전 테이블 + runtime_rules 흡수) · 이벤트 기록(설계서 §14)
5a. [x] LIVE 채택 출처: `EntryFilled.adopted`(positionRisk) → open 행 reason `adopted_from_exchange`(사용자 2026-09-15 · 전제 정정: 채택도 EntryFilled를 냈다) — Codex 배치(6+7) 대상
5d. [x] 사용자 결정(2026-09-16) → 레지스트리 #11(킬스위치 5%·5·1·1) · #12(stale 자동 청산) · #13(명령 의미·대사 해제·일일 손실 /start)
5c. [x] `_exit` 동기화 기록(`PositionSynced` → root open 수정 행) · LIVE 거래소 수량 소실(`PositionVanished` → 킬스위치) · 채택 추정 수수료 — Codex L6·7 #2~#4
5b. [x] layer 8 기동 배선(`ops/runtime.py`·`ops/run_bot.py`) — 설계서 §17
5e. [ ] 페이퍼 14일차 재평가 새 행: #5 · #7 · #9 · **#11**
5f. [x] 페이퍼 재기동 복원 (a) · 런타임 규칙 (ii) · 레지스트리 #14 (2026-09-16 구현) · [ ] LIVE `ExchangeReader` 계좌 필드 공식 문서 확인 · LIVE 거래소 읽기 비동기화(Codex L8 #3) · 런타임 규칙 주기 재조회
5i. [x] 재기동 복원 드라이런(SIGKILL · 읽기 전용 키 · 2026-09-15 20:32–20:39 UTC, ops_log) · [x] `TELEGRAM_OWNER_IDS`(사용자) · [x] 캡처 스크립트(2026-09-15 22:22 UTC) · [ ] rclone remote = D1 3단계
5j. [ ] VPS 배포 시점: E2E Restart B(2026-09-17 00:12 UTC) 24h 게이트 종료 뒤(earliest 09-18) · 라이브 호스트 변경 하루 1건
5h. [ ] 보류: `engine_events` op_id 조회 인덱스(스키마 v3) · shard `roll_failed` health 경보 · 키 `ipRestrict` 기동 확인 · [x] 짝 없는 start/connect → `dirty_previous_run`(#15 ⑤)
5k. [ ] LIVE 체크리스트 추가(#15 ③④): 규칙 주기 재조회 ≥6h·24h 초과 규칙 진입 금지 · 일시정지 사유 집합화
5l. [ ] prune 시각: D2(09-19) 뒤 VPS `list-timers` 실측 → 모든 E2E 타이머에서 ≥30분 떨어진 시각 · 별도 변경(런북 §9.6)
5m. [x] 배포 완료: D1 2026-09-18 · **D2 2026-09-19 00:40 UTC 기동**(커밋 05d6031) → Restart B 게이트 종료(09-18 00:16 UTC) → D1 09-18 · D2 09-19(00:35–02:30 UTC) · 사용자: rclone·OWNER_IDS·캡처 → §9.1 로컬 점검 → 화이트리스트
5g. [ ] VPS 배포(런북 `docs/runbook_vps.md`) — 사용자 논의 후 · 외부 heartbeat · Drive 사본 재검증 도구 · 대장 reconcile 도구
6. [x] layer 5: E2E ShardWriter + #138 종료 플러시 테스트 복원(`tests/test_data_shards.py`) · [x] layer 8: health 스로틀 구조 · `data_stores` allowlist(설계 #131) · [ ] shard `roll_failed` 대장 이벤트를 health가 읽는 경보(상태 파일에 없음)
7. [x] VPS 템플릿: 봇 전용 Linux 사용자 user 유닛(`ops/systemd/`)·런북 — **배포는 Codex 검토 + 사용자 논의 후**
8. [x] GitHub 원격 설정됨(`bblac2000/BTC_Futures_E2E`) — 푸시는 사용자 요청 시에만

## ⚠️ 알고 있는 위험
- ~~패키지명 `telegram/` 가림 위험~~ → 2026-09-15 `notify/`로 개명 완료.
- 패키지명 `data/`는 코드 패키지다. 런타임 데이터는 `var/`(git 미추적).

5n. [ ] 비차단 잔여(Codex 배포 전 재검토 #2): 오래된 breadcrumb 격리 이동 뒤 재생 커밋 전 사망 시 운영 이벤트가 stale 파일에만 남음 — 복사 후 재생 성공 시 삭제로 바꿀지 결정
5o. [ ] 설계 메모만(코드 없음 · D2 뒤 · 페이퍼 첫 주 뒤 평가, 사용자 2026-09-16): breadcrumb 파일을 **DB 쪽 journal 테이블**로 대체 검토 — DB와 동기화하는 두 번째 상태 저장소라 세 배치 연속 추가 검토 라운드를 불렀다. 단일 저장소 · op_id 멱등 · 5n 해소. 평가 때 볼 것: DB 자체가 잠겨 쓸 수 없을 때(breadcrumb가 존재한 이유)의 fail-closed 경로를 무엇이 대신하는가.
    - **증거 추가(2026-09-21 · Codex 단계 d 후속 · 사용자)** — "복구·재시도 상태가 두 번째 저장소"라서 생긴 결함 두 개(둘 다 `05d6031`부터 있던 봇 결함 · 레지스트리 #23):
      ① 이벤트 행과 엔진 스냅샷이 **별도 트랜잭션** — 사이에서 죽으면 DB(새 값)와 스냅샷(옛 값)이 갈려 복원이 멀쩡한 포지션을 버린다 → 한 트랜잭션으로.
      ② 메모리 재시도 큐 `unrecorded`가 **FIFO가 아니었다** — 진입 기록 실패 뒤 청산이 직접 써져 고아 close·재시도 때 유령 open root → 큐가 비어 있지 않으면 뒤 묶음도 줄 뒤로.
      둘 다 "DB 밖(메모리·파일)에 들고 있는 상태를 DB와 맞추는 코드"에서 나왔다 — journal 테이블 평가의 근거.
    - **남은 것(Codex 단계 d 후속 3차 · MERGE 뒤 비차단)**: ③ FIFO는 엔진 이벤트·엔진 스냅샷 묶음만 — 운영 이벤트·안전 상태(킬스위치)는 앞선 미기록 묶음보다 먼저
      커밋될 수 있다(청산이 메모리에만 있는데 킬스위치 상태는 DB에 → 재기동 시 청산 전 포지션 + 청산 후 안전 상태 · fail-closed지만 인과 불일치).
      Codex: 안전 상태를 휘발성 큐 뒤로 미루지 말고 **journal 설계(5o)로** 해결. ④ DB 장애 중 봉마다 스냅샷 묶음이 쌓여 큐가 무한 성장 · 복구 때 한 번에 동기 배출 →
      연속된 스냅샷 전용 항목 합치기 + 깊이 알림(별도 소규모 변경 · Codex 검토 대상).
5p. [x] D2 전 유닛 템플릿 수정 + **Codex MERGE(2026-09-18 · 3라운드)** → D2 해시 `05d6031`
5q. [x] **완료 2026-09-24**(레지스트리 #29): 봇 MemoryPeak 214.7 MB(400 MB 상한) · memory.events 전부 0 · **00:10~00:12 실측 최저 가용 509 MB**(> ~300 MB) → **swap 파일 만들지 않는다**. 원래 항목: D2 뒤 3일: `bsc show btcfut-bot -p MemoryPeak` · `memory.events`(cgroup) 포함 — 봇 실측 peak RSS · 00:10 겹침 여유 < ~300 MB면 swap 파일을 별도 날 라이브 변경으로(사용자 2026-09-18)
