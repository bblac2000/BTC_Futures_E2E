# 시행 레지스트리 (append-only)

> 규칙: 삭제·수정 금지, 추가만. 틀린 행은 고치지 않고 정정 행을 덧붙인다(행 번호 인용).
> 파라미터·임계 변경 = 새 행 + 새 사전등록. 실패 후보 이름 바꿔 재제안 금지(research-protocol §4·§7).
> 판정 3분류 ACCEPT / REJECT / 폐기 · 기각은 검정력 부족 vs 효과 부재를 구분한다.

| # | 일자(UTC) | 트랙 | 대상 | 파라미터(해시) | 게이트·OOS 앵커·N | 상태 | 승인·검토자·근거 |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-15 | 운영·데이터 전달 감시 (layer 5 가동 전 사전확약) | `ops/delivery_counter.DELIVERY` — BTCUSDT `/market` 소켓 스트림 전달 임계 | **kline1m_update** `@kline_1m` 모든 push(x=false·x=true)·ts=`E` · min_per_min=**1** · grace_sec=**120** / **kline1m_close** `@kline_1m` x=true만·ts=`E` · min_per_min=**0**(분당 검사 없음) · grace_sec=**120**(마지막 마감 이후 나이 = 마감 2회) / **markprice** `@markPrice@1s` · min_per_min=**1** · grace_sec=**120**. 판정 규칙 `is_stalled()`(E2E #134 동일): 한 번도 안 옴 → 시작 후 grace 경과 시 정지 · 마지막 수신이 grace 초과 → 정지 · min_per_min>0이면 직전 벽시계 완결 분 행 수 미달 → 정지(관측 없던 분 = 0) | 게이트 아님(판정·성과 집계에 들어가지 않는다) · 소비자 = layer 5 live 카운터 → layer 7 stale-data kill 입력, layer 8 health 재생 | 🔒 **사전확약(PRE-COMMIT)** — 이 봇의 스트림 데이터를 **한 건도 보기 전**에 커밋. 🚫 결과를 본 뒤 숫자 변경 금지 — 바꾸려면 새 행 | ✅ **사용자 확정 2026-09-15**(옵션 3 "감시 둘"). 근거: ① **update** = 스트림 침묵 감지. 형성 중 push ~250ms(v6 §10)라 분당 1건은 느슨한 하한이고 120초는 "2분 무수신". ② **close** = "업데이트는 흐르는데 봉이 안 닫힘" 감지. 마감은 분당 정확히 1회라 min_per_min=1이면 **주기와 딱 맞는 분 검사**가 되고, 마감 `E`가 봉 종료 `T`(xx:59.999)와 같게 찍히면 앞 분에 들어가 다음 벽시계 분이 0건 → **가짜 정지**. 그래서 분당 검사를 끄고 나이 규칙만 둔다(정상 간격 ~60초 < 120초 = 마감 2회) — 테스트 `test_close_monitor_ignores_the_59_999_boundary_jitter_that_a_minute_rule_would_flag`. ③ **markprice** = 2026-09-04 로컬 600초 실측 601틱·간격 1.000초·결손 0(메모리 기록), E2E #134와 같은 형태. 🔒 테스트 `test_thresholds_are_exactly_the_pre_committed_values`가 값을 잠근다. 검토자: 사용자(결정)·Claude Code(구현) |
