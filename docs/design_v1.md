# BTC_Futures_E2E — 설계서 v1 (2026-09-15)

> 상위 규칙: `.claude/skills/quant-bot-constitution/`(스킬 v1.1) → `docs/바이낸스문서API_2026_v6.md`(v6) → 이 문서.
> 충돌하면 위가 이긴다. **거래소 값 자체는 어떤 문서도 진리원이 아니다 — 런타임 API 조회가 최종이다.**

## 1. 왜 새 저장소인가
`E2E_Hybrid_Bot`은 실주문 경로 구현을 금지하고 `ops/scan_order_path.py`로 집행한다. 이 봇은 결국 라이브로 가야 하므로 여기 산다.
E2E를 fork하지 않고, 런타임에 E2E를 import하지 않는다. 필요한 모듈은 **복사**(출처 헤더)하고, 복사본을 고치면 `docs/ops_log.md`에 적어 역이식 후보로 남긴다.

## 2. 확정 결정 (재론 금지 — open-decisions.md 2026-09-12 행)
| 항목 | 결정 |
|---|---|
| 대상 | BTCUSDT · USDⓈ-M 무기한 · 원웨이 + ISOLATED · MARKET 전용 · 청산 reduceOnly |
| 기동 게이트 | exchange-rules §4. LIVE는 ISOLATED 확정 실패 시 기동 중단(진입 금지·청산 허용). PAPER는 읽기 전용 |
| 의사결정 봉 | 1m |
| 레버리지 | 50~100x는 **허용 범위**. 실효 L = f(SL 거리) → 클램프 → `SL×buffer < 청산 거리` 하드 체크. 레짐→레버리지 직접 매핑 금지 |
| 페이퍼 | 도쿄 VPS 1개월. **E2E 수집기와 별도 Linux 사용자·별도 systemd 유닛**. 메모리·디스크는 수집기 우선. 수집기 데이터 디렉터리 접근 금지 |
| 라이브 | 사용자 승인 **그리고** 라이브 체크리스트(strategy-modules §6) 전부 통과. BTC부터 |
| 텔레그램 `/stop` `/close` | 주인 ID 화이트리스트 → 포지션·uPnL 포함 확인 버튼 → 무응답 시 3초 간격 3회 재전송 → 여전히 무응답이면 취소 + "청산 안 됨" 통보 · 콜백 만료 60초 · 한글 별칭(시작/중지/일시정지/상태) |
| 역할 | Claude Code 구현 · claude.ai 검토·프롬프트 · **삭제·라이브·자금·수집기 호스트에 닿는 변경은 Codex 검토** |
| 값 리터럴 | tick/step/MIN_NOTIONAL/MMR/수수료/펀딩 cap/브라켓 리터럴 금지 — 런타임 조회 또는 캡처 스냅샷 (`tests/test_no_exchange_literals.py`가 `exchange/`·`sizing/`·`paper/`를 AST로 검사) |
| 자본 | 1,000 USDT. KRW 표시는 config 환율(기본 1500), 로직에는 절대 들어가지 않는다 |
| 환경 | WSL2 · uv · TDD · pyright clean · ruff · 모든 WS URL은 `build_stream_url()` 경유 · 양방향 정적 검사 CI |

## 3. 빌드 순서 — 전략 독립 계층 먼저. 1~8 통과 전 전략 코드 금지
| # | 계층 | 상태(2026-09-15) |
|---|---|---|
| 1 | `exchange/` 런타임 규칙 로더·정규화·주문 매트릭스·기동 게이트·rate-limit 카운터·서버 시각 오프셋 | ✅ 구현·테스트 (Codex 검토: 아래 §7) |
| 2 | `sizing/` 위험 예산 → 목표 명목 → 최고 정수 L(브라켓·거래소 공식 청산 거리) → pos_pct 캡 → 수량 → 최종 재검증·손실 예산 (레지스트리 #2) | ✅ B1·B2로 재작업·테스트 — Codex 재검토 §7 · buffer 값 대기(#3) |
| 3 | `paper/` 체결 엔진(taker-only·mark 기준+보수 슬리피지·같은 봉 SL 우선·펀딩 실율·maxQty 분할). 라이브 전송기는 LIVE+체크리스트 게이트 뒤 | ✅ 구현·테스트(351) · Codex LiveSender MERGE · 엔진 MERGE(검토 4회) — **사용자 확인 대기**(§12) |
| 4 | `db/` 버전 마이그레이션 SQLite(bars_1m·features_*·decisions·orders·positions·funding_events·account_snapshots·runtime_rules) | ✅ 구현·테스트(§14) · `runtime_rules` DDL을 v1로 흡수 — Codex 검토 대상 아님(자금·삭제·라이브 무관) · 기록 배선은 layer 8 |
| 5 | `data/` 1m kline(/market) + REST 백필 · markPrice@1s · 스트림별 전달 감시 · manifest | ✅ ccxt.pro 피드·REST 백필·전달 감시 · shard 기록(E2E #138 이식)·소켓별 이벤트·소켓별 23h 재연결(§13) — Codex MERGE(검토 2회 · `task-mu2kq6ib-uro1pe`·`task-mu2l1ukd-e0sy2c`) |
| 6 | `notify/` 텔레그램 명령·확인·재전송·만료 (2026-09-15 `telegram/`에서 개명 — PyPI `python-telegram-bot` import 이름 가림 방지) | ✅ 구현·테스트(§15) · Codex MERGE(검토 3회) · 배선은 layer 8 |
| 7 | `safety/` 킬스위치·stale-data kill·봉마다 대사·rate-limit 80% 가드 | ✅ 구현·테스트(§16) · Codex MERGE(검토 3회) · 킬스위치 값 **레지스트리 #10 PENDING** · 배선은 layer 8 |
| 8 | `ops/` VPS systemd 템플릿·health/alert 타이머·Drive 검증 prune·런북 | ✅ 런타임·러너·템플릿·런북 구현·테스트(§17) · 페이퍼 드라이런 3회(최종 `d20d8a1` clean) · **Codex MERGE(검토 5회)** · **VPS 배포는 사용자 논의 후** |
| – | `strategies/` 플러그인(피처 in → 목표 포지션 out). 첫 전략은 `docs/trial_registry.md`에 사전등록 **후** 백테스트 열람 | 🚫 1~8 통과 전 금지 |

⚠️ 상시 발견: 30분 이하 신호는 대부분 비용 게이트(G2)에서 실패했다. 1m 의사결정 전략은 **비용 차감 후 순엣지**를 명시적으로 보여야 한다.
⚠️ Donchian 계열은 E2E #74가 REJECT(효과 부재·MDE 4.2 ≪ 13 bps) — 제안하려면 먼저 #74와 무엇이 다른지 답한다(research-protocol §7). 이 저장소는 어떤 Donchian 코드도 가져오지 않았다.

## 4. 재사용 표 (E2E → 이 저장소)
E2E HEAD = `f1e7d86`(2026-09-14). "커밋"은 해당 파일의 마지막 변경 커밋. 복사 시 원본 working tree 변경 없음 확인.

| E2E 원본 | 로컬 경로 | 커밋 | 방식 | 비고 |
|---|---|---|---|---|
| `ops/stream_tiers.py` | `ops/stream_tiers.py` | `4718287` | 복사 + 출처 헤더 | 변경: `SCAN_DIRS`만 이 저장소 패키지로. `@trade` measured 근거·fail-closed·ALLOWLIST 1개 유지 |
| `tests/test_stream_tiers.py` | `tests/test_stream_tiers.py` | `4718287` | 복사·적응 | `e2e.l2_collector` import 테스트 2개 제외, 봇 스트림(kline_1m+markPrice@1s) 테스트 추가 |
| `ops/delivery_counter.py` | `ops/delivery_counter.py` | `98da74d` | 복사 + 출처 헤더 | 판정 규칙·라이브/재생 어댑터 로직 동일. `DELIVERY`를 이 봇 스트림으로 재정의(§5 · 레지스트리 #1), `E2E_COLLECT_DERIVS` 제거 |
| `tests/test_delivery_counter.py` | `tests/test_delivery_counter.py` | `d0d6426` | 부분 복사 | 순수 판정·재생 테스트만. l2_collector·vps_health·quality 의존 테스트(#138 포함)는 layer 5/8에서 복원 |
| `e2e/manifest.py` | `data/manifest.py` | `23e5005` | 복사 + 출처 헤더 | DB 경로 주입(`var/manifest.sqlite`). register_shard 무예외·mark_pruned 행 보존 유지 |
| `e2e/paper/notify.py` (F-TGDAEMON 수정본) | `notify/sender.py` | `a60f4f8` | 복사 + 출처 헤더 | 응답 `ok` 검증 + atexit join 유지. prefix `[BTC]`, opener 주입(테스트) |
| `e2e/l2_collector.py` `ShardWriter`(:143-191)·`WriterThread` 종료 플러시(:193-303, #138 `final_flush_failed`→`stop_dirty`)·`_shutdown_record`(:590-614) | `data/shards.py` (layer 5) | `90d47aa` | **이식 + 출처 헤더**(2026-09-15) | writer = kind별 dict · 가격 Decimal 문자열 · 이름 충돌 접미사 · 소켓 이벤트를 writer 스레드가 대장에 · 드롭 → `stop_dirty`. #138 동작 불변, 테스트 복원 `tests/test_data_shards.py`. 변경 목록 ops_log |
| `ops/vps_health.py` 경보 구조(:742-819 `STATE`/`STATE_ONCE`, `problem_items` :498) | `ops/` (layer 8) | `90d47aa` | **패턴 — 미복사** | 반복형 = 고정 스로틀 키(날짜·숫자 없음)·3h / 확정 사실 = 하루 1통 / 발송 실패 시 상태 미갱신. 텔레그램 도달성 재시도 1회(:261) |
| `ops/data_stores.py` allowlist prune 모델 | `ops/` (layer 8) | — | **원본 없음** | ⚠️ f1e7d86에 **코드로 존재하지 않는다**(`git log --all` 0건). 설계만 있음: `docs/설계_prune확장_2026-09-12.md`(`f836d16`, 레지스트리 #131, Codex 검토 완료·단계 0→4). 현행 코드는 `ops/prune_local.py`(`e6e5125`, denylist `NEVER_TOUCH`). layer 8에서 설계 v2대로 `deletion_mode="drive_verified_prune"`·30일·파생물 `expired_local_derivative` 별도 구현 |
| 비용 모델 왕복 10.02 bps | `paper/` config (layer 3) | — | **원본은 문서** | ⚠️ `e2e/cost/*.py`에 10.02 상수 없음. 출처 `docs/Phase1A_계측결과_2026-08-15.md:180,197`(`8f457ef`): 수수료 10 bps + 슬리피지 0.016 bps. 꼬리표 **"2026-08 regime, recalibrate"**. 수수료 부분은 리터럴이 아니라 `commissionRate` 런타임 값에서, 슬리피지 0.016 bps만 꼬리표 달린 실측 파라미터로 둔다 |
| `docs/바이낸스문서API_2026_v6.md` | `docs/바이낸스문서API_2026_v6.md` | `175c356` | **원문 그대로**(md5 `02c31418…` 일치) | 부기 정정 포함(§10 forceOrder largest/1초·/market/ws 티어, §WebSocket Base·:989 kline 예제). 🚫여기서 수정 금지 — 새 정정은 날짜·출처 달린 부기로만 |
| 테스트 스냅샷(exchangeInfo·leverageBracket·commissionRate·fundingInfo) | `tests/fixtures/snapshots/` | VolumeClockBot `6d0129d` | 원문 그대로(md5 일치) | 2026-09-02 mainnet read-only 캡처. positionSideDual·multiAssetsMargin은 **합성**(캡처 없음, v6 §1.0(A) 값) — 라이브 전 실캡처로 교체. `PROVENANCE.md` |

## 5. 데이터 전달 감시 임계 — **레지스트리 #1로 확정**(2026-09-15)
| kind | 스트림·계수 대상 | min_per_min | grace_sec | 감지 대상 |
|---|---|---|---|---|
| `kline1m_update` | `@kline_1m` 모든 push(x=false·x=true) | 1 | 120 | 스트림 침묵 |
| `kline1m_close` | `@kline_1m` x=true만 | **0** | 120(= 마감 2회) | 업데이트는 오는데 봉이 안 닫힘 — 분당 검사를 끈 이유는 xx:59.999 경계 흔들림 가짜 정지 |
| `markprice` | `@markPrice@1s` | 1 | 120 | 스트림 침묵 |

근거·전문은 `docs/trial_registry.md` #1. 🚫 결과를 본 뒤 변경 금지.

## 6. layer 1 구현 요약 (`exchange/`)
- `rules.py` 응답 → 불변 dataclass(Decimal). 필터·브라켓 누락/불연속은 `RulesError`(fail-closed). fundingInfo 부재 심볼은 `present=False`(cap 추정 안 함). rate limit은 `exchangeInfo.rateLimits`.
- `loader.py` 6개 엔드포인트 GET(서명 4) → `RuntimeRules` + `RawFetch`; 스냅샷 로드·캡처(tmp→rename). 서명 불가 시 조용히 넘기지 않음.
- `store.py` `runtime_rules`(load_id·endpoint·symbol·mode CHECK·source·fetched_at_utc·payload_json·sha256). layer 4 마이그레이션이 흡수.
- `normalize.py` floor → **내림 후** MIN_NOTIONAL 재확인 → 예산 내 1 step 상향 or 포기 · tick HALF_UP Decimal(float 거부) · MARKET_LOT maxQty 분할(진입 조각 전부 MIN_NOTIONAL 이상) · reduceOnly 면제 · positionAmt step 불일치는 예외.
- `orders.py` 공개 생성기는 `(Direction, Intent)`만 받아 side·reduceOnly를 **함께** 도출(청산인데 reduceOnly를 끌 방법이 없다 — Codex Q4) · MARKET 전용 · 금지 키/허용 목록 검증기. **전송하지 않는다.**
- `gate.py` LIVE: status·레버리지 범위(브라켓 조회값) → 원웨이 확정(헤지 전환 전 **계정 전 심볼** flat 확인 — Codex Q3) → multiAssets 중단 → ISOLATED 전환(포지션·미체결 0일 때만, -4046 허용) + **재조회 확정** → leverage 설정 + 응답 일치 → 실패·응답 모양 이상 전부 `StartupAbort`(진입 금지·청산 허용 — Codex Q5). PAPER: `ReadOnlyClient`로 POST 0회 구조 보장, WARNING만.
- `client.py` HMAC 서명(Binance 문서 예시로 회귀 잠금) · 에러 JSON code/msg 보존 · -1021 시 시계 무효화 · 응답 헤더 → rate-limit 카운터 · `ReadOnlyClient`.
- `ratelimit.py` 한도는 규칙에서, 사용량은 `X-MBX-USED-WEIGHT-1M`/`X-MBX-ORDER-COUNT-10S|1M` 헤더에서(이름 도출), 창 경계 만료. 80% 정책은 layer 7.
- `timesync.py` 왕복 중점 오프셋, 최소 rtt 표본, stale 판정.

## 7. 검토 상태
| 대상 | 검토 | 상태 |
|---|---|---|
| layer 2 재작업(B1·B2) + 이전 수정분 + algo 사전검사 | Codex 재검토 read-only (`task-mu27w8m4-oicyfq`, `0c78d37`) | ✅ 완료 — Q1·Q3·Q5 OK · Q4 수정(실제 체결 재계산) · **Q2 → §9 B5 · Q6 → §9 B6 사용자 결정 대기** |
| layer 2 `sizing/` | Codex 독립 검토 read-only (`task-mu21ai6o-slrnyc`) | ✅ 완료 — Q2·Q3 OK · Q1·Q4·Q5 ISSUE → 전부 동의·수정(178 green). liquidationFee 모델은 §9 B1로 사용자 결정 대기. 수정분 재검토 미실시 |
| layer 1 `exchange/gate.py` LIVE 분기(계정 설정 변경) · `client.py` 서명/POST · `orders.py`/`normalize.py` | Codex 독립 검토 read-only (2026-09-15, job `task-mu1zv0h4-qazyjb`) | ✅ **완료** — Q1·Q2 OK · Q3·Q4·Q5 ISSUE → 전부 채택·수정·테스트(125 green). 원문·조치표 `docs/ops_log.md`. 재검토(`task-mu20lg9y-h4uua9`): F1 PARTIAL · F2 CLOSED · F3 PARTIAL → 동의 항목 수정(전송 실패→StartupAbort '상태 불명' · positionAmt 엄격). algo 미체결 사전검사는 문서 확인 후(TODO). 재수정분은 3차 검토 미실시 |

## 8. 미결·결정 표 (open-decisions.md 원문 복사 · md5 `ef25c7f5…` 시점)

## 충돌 항목

| # | 항목 | 기본환경설정v1 | v6 헌법 / 현행 | 왜 중요한가 |
|---|---|---|---|---|
| 1 | 레버리지 범위 | 레짐별 동적 **50x~100x** | 봇은 **3~7x** 사용(§3), 사이징은 SL 거리에서 레버리지 도출(learnings sizing v2) | 50x 이상은 tier1에서도 청산가가 진입가 1~2% 안에 온다. 1m 봉 ATR로는 SL이 청산가 밖에 놓이기 어렵다. v1 값이 의도라면 사이징 규칙 전체를 다시 써야 한다 |
| 2 | 포지션 사이징 | 자본의 10%~40% 동적 | RL 환경 예시 최대 50%, 실제 봇은 SL 거리 기반 | 1번과 묶여 있다 — %자본×레버리지가 곧 명목이다 |
| 3 | 메인 분봉 | **1m** | VCB T1_v2는 4h TSMOM, E2E는 틱/100ms 수집·1m은 의사결정 주기 | 30분 이하 신호는 비용이 엣지를 먹는다는 것이 기각된 발견이다. 1m 메인이면 비용 게이트(G2)가 사실상 통과 불가 |
| 4 | 라이브 전환 | 페이퍼 1개월 후 사용자 판단으로 전환, 언제든 페이퍼↔라이브 | VCB는 181일 전진 페이퍼 사전등록 후 창 종료 시 1회 판정; E2E는 실주문 경로 구현 자체 금지 | "1개월"과 "사용자가 봤을 때 성과 충족"은 사전등록 규율과 충돌한다. 전환 기준을 게이트로 정의할지, 재량으로 둘지 |
| 5 | 대상 심볼 | 비트코인(BTCUSDT) | v6 라이브 로스터 ETH·XRP(BTC 봇 없음), VCB 5심볼, 라이브는 BTC부터 단계적 | 문서마다 다르다. 어느 트랙의 어느 단계 얘기인지 명시 필요 |
| 6 | 자본금 표기 | 1,000 USDT, KRW 병행(고정환율 1,500원) | — | 충돌은 아니나 고정환율은 하드코딩 금지 원칙과 마찰. config 값으로 두고 리터럴 금지 |
| 7 | 서버측 SL/TP | "동적 TP·SL 구현" (방식 미지정) | 서버측 STOP/TP 사용 안 함, 봇 모니터링 후 MARKET reduceOnly | v1대로 읽으면 algoOrder를 쓰려 할 수 있다. 헌법은 MARKET 전용 |
| 8 | 구현 도구 | WSL + Claude Code, UV, TDD, pyright | VCB는 Antigravity CLI 구현 + Claude 검토 + Codex 독립 검토 | 역할 분담이 트랙마다 다르면 프롬프트 형식도 달라야 한다 |
| 9 | 텔레그램 명령 | /start /stop(청산) /pause /status /position /close /profit /help + 한글 텍스트 | E2E는 digest/alert 단방향 | 양방향 명령(특히 /stop=강제청산)은 라이브에서 안전장치가 필요하다(확인 단계, 권한) |

## 확정된 것 (참고)
- 원웨이 + 격리 + MARKET 전용 — v1·v6 일치.
- 하드코딩 금지(값), 동적 조회 — 일치.
- 로그·매매일지·DB는 심층분석용으로 최대한 자세히 — 일치(E2E manifest·운영일지 방식).
- 페이퍼와 라이브 로직은 같은 코드 경로, 모드 플래그로 분기 — 일치(단 E2E는 예외적으로 라이브 경로 금지).

## 결정 기록
| 날짜 | 항목 | 결정 | 따라오는 제약 (스킬이 강제) |
|---|---|---|---|
| 2026-09-12 | #1 레버리지 | **50x~100x 레짐별 동적** (사용자 확정) | 이는 *허용 범위*이고 실효 레버리지는 SL 거리에서 도출(sizing v2)한 뒤 범위로 클램프한다. 100x·tier1 MMR 0.4%면 청산가는 진입가에서 LONG 0.6%·SHORT 0.6%다 — SL은 반드시 청산 거리 안쪽 + 버퍼(q_c=0.9995)에 놓여야 하고, 놓을 수 없으면 레버리지를 낮추거나 진입하지 않는다. `references/strategy-modules.md §1` |
| 2026-09-12 | #3 메인 분봉 | **1m** (사용자 확정) | 30분 이하 신호는 비용이 엣지 대부분을 먹는다는 기각 발견이 그대로 적용된다. 1m 봉이 *의사결정 주기*라는 뜻이지 모든 신호가 1m 스케일이어야 한다는 뜻은 아니다 — 상위 스케일(15m/1h/4h) 컨텍스트를 1m에서 평가하는 구조를 권장. G2 비용 게이트는 면제되지 않는다 |
| 2026-09-12 | #4 라이브 전환 | **페이퍼 1개월 후 사용자 만족 시 전환. 페이퍼는 도쿄 VPS에서 실행** (사용자 확정) | "사용자 만족"은 재량이므로 최소 객관 조건을 함께 둔다: 1개월 동안 킬스위치·청산 0회, 대장↔거래소 대사 불일치 0건, 비용 차감 후 순손익 보고. 전환은 BTCUSDT부터, 전환 시각·config 해시를 레지스트리에 기록. E2E 저장소는 여전히 실주문 금지 |
| 2026-09-12 | #2 사이징 | **동적 포지션 사이징** (사용자 추가요청) | `strategy-modules.md §1` |
| 2026-09-12 | #5 대상 심볼 | **BTCUSDT** (비트코인 선물매매봇 트랙) | v6의 ETH/XRP 로스터는 E2E·다른 트랙 얘기다. BTC 값(MIN_NOTIONAL 50, tick 0.10, step 0.001, MARKET maxQty 120, 150x/12단)을 런타임 조회로 확인. VCB 5심볼은 별개 |
| 2026-09-12 | #9 텔레그램 강제청산 | **중간 수준 + 3회 재알림**: `/stop`·`/close` 수신 → 봇 주인 ID 화이트리스트 확인 → "정말 청산할까요? [예/아니오]" 인라인 버튼 → 응답 없으면 **3초 간격으로 3회** 재전송 → 예 응답 시 MARKET reduceOnly 전량 | 3회 후에도 무응답이면 **취소하고 "청산 안 됨" 통보**(미확인 청산은 오터치일 수 있으므로). 확인 메시지에는 현재 포지션·미실현손익을 함께 보여준다. 일반 알림(진입·청산·펀딩·킬스위치)도 사용자가 놓치지 않게 중요 이벤트는 같은 3회 규칙 적용 가능(config). `strategy-modules.md §6` |
| 2026-09-12 | #8 구현 도구 역할 | **Claude Code 구현 + Claude(claude.ai) 검토·프롬프트 작성 + 삭제·라이브·자금 관련 변경은 Codex 독립 검토** | 프롬프트는 영문, SKILL.md §4 형식. Codex가 불가하면 해당 변경은 대기(시간 압박이 없으면 기다리고, 있으면 먼저 "지우지 않는" 대안을 찾는다 — 2026-09-12 EBS 사례) |
| 2026-09-12 | 평가지표·고급전략·지지저항·DB컬럼 | 사용자 추가요청 | `strategy-modules.md §2~§5` |

## 9. 이 저장소에서 발견한 미결·해결 기록
| # | 발견일 | 항목 | 상태 |
|---|---|---|---|
| B1 | 2026-09-15 | liquidationFee를 청산 거리에 넣으면 BTC 100x가 구조적으로 불가(구 스킬 식) | ✅ **해결 — 레지스트리 #2**: 스킬 식 오류. 거래소 공식 `1/L − (MMR − cum/notional)`, fee는 청산 손실로만. v6 사본 §1.0·§5.4 정정 부기 |
| B2 | 2026-09-15 | 클램프 시 risk_pct가 손실에 반영되지 않음(구 스킬 식) | ✅ **해결 — 레지스트리 #2**: 위험 예산이 1차 제약, pos_pct는 도출(캡 40%·권고 10%), 최종 손실 > 예산×(1+tol) 거부 |
| B3 | 2026-09-15 | **목표 명목이 상위 티어**면 pos_pct 캡으로 최종 명목이 tier1로 내려와도 L은 **목표 명목 티어의 레버리지 상한**에 묶인다(예: 목표 1,867,630 → tier3 최대 75x → 캡 후 명목 112,058(tier1)인데 L=75). 레지스트리 #2 ③ 순서 그대로의 결과 — 보수적(더 낮은 L·더 작은 명목·손실 더 작음) | 📝 **기록만** — 규칙대로 구현. 1,000 USDT 자본에서는 목표가 300,000을 넘으려면 risk/sl ≥ 300배(예: risk 3%·SL 0.01%)라 드묾. 바꾸려면 새 행 |
| B4 | 2026-09-15 | `SizingLimits.buffer` 값 | ✅ **레지스트리 #5**: b_rel 1.5 AND 절대 간격 10bp · SL 트리거 mark · 14일차 재평가(새 행) |
| **B5** | 2026-09-15 | 행 #2 청산 거리는 바이낸스 정확식의 근사 — SHORT 반보수 | ✅ **레지스트리 #4**: (a) 방향별 정확식 · 티어 = max(진입, 청산가 명목) · 진입 수수료가 격리 마진을 줄인다는 보수 가정(진입 후 검사가 두 모델 차이를 로그해 판정) |
| **B6** | 2026-09-15 | 헤지→원웨이 사전검사가 COIN-M(dapi)을 못 본다 | ✅ **라이브 체크리스트 항목**(§10) "USDⓈ-M 전용 계정 · COIN-M 포지션·미체결 0". 기동은 거래소 거부 시 이미 안전하게 중단. COIN-M 읽기 검사는 백로그(엔드포인트 원문 확인 먼저) |
| B3 | 2026-09-15 | (재확인) 목표 명목 티어가 L 상한을 정한다 | ✅ 사용자 확인 — 보수적이므로 유지 · 기록 |

## 10. 라이브 전환 체크리스트 (strategy-modules §6 + 이 저장소 결정) — 하나라도 빠지면 전환 금지
- [ ] 격리 확정(기동 게이트 재조회) · 레버리지 설정 응답 일치 · 원웨이 확인
- [ ] `runtime_rules` 스냅샷 기록 · config 해시 레지스트리 기록
- [ ] 킬스위치 테스트(페이퍼에서 강제 발동) · 텔레그램 왕복 테스트
- [ ] **USDⓈ-M 전용 계정 — COIN-M 포지션·미체결 0**(2026-09-15 B6 · 헤지 모드 전환 사전검사가 dapi를 보지 않는다)
- [ ] 레지스트리 #4 수수료 가정 판정 결과 기록 — **첫 라이브 진입부터**의 진입 후 검사 로그(레지스트리 #6: 페이퍼 포지션은 `positionRisk`에 없다). 그때까지 보수 가정(수수료가 격리 마진을 줄인다) 유지 · 테스트넷 프로브는 **폐기**(사용자 2026-09-15)
- [ ] 레지스트리 #5 14일차 재평가 행 존재
- [ ] **LIVE 거래소 읽기(positionRisk·계좌)를 루프 스레드 밖으로** — 타임아웃 있는 비동기/작업자 큐(Codex L8 #3 · 지금은 동기 · PAPER에서는 호출 없음)
- [ ] **런타임 규칙 주기 재조회 ≥ 6시간마다 + 24시간 넘은 규칙으로는 진입 금지**(레지스트리 #15 ③ · `LiveChecklist.runtime_rules_refresh_6h_and_entries_need_rules_under_24h` — 페이퍼는 기동 때만)
- [ ] **거래 권한 키는 LIVE 전환 때 새로 발급** — 화이트리스트 VPS IP 하나 · VPS `.env`에만(로컬·저장소·백업 금지) · 페이퍼 읽기 전용 키는 승격하지 않는다(레지스트리 #17 · `LiveChecklist.trading_key_separate_vps_ip_only_and_never_local`)
- [ ] **일시정지 사유를 집합으로**(레지스트리 #15 ④ · `LiveChecklist.pause_reasons_are_a_set` — 지금은 단일값이라 사유 문구가 덮인다)
- [ ] LIVE `ExchangeReader` 실구현 — 계좌 응답 필드를 공식 문서 렌더링 + 실캡처로 확인(v6에는 가중치 표만) · 러너 LIVE 경로 + 기동 게이트 호출 · 재기동 시 거래소 포지션 처리 결정


## 11. 테스트넷 수수료 가정 프로브 — 해석 규칙 사전확약 (2026-09-15 · 스크립트 작성·실행 **전**)
> ⛔ **폐기(사용자 2026-09-15 방향 전환)** — 테스트넷을 쓰지 않는다. `scripts/testnet_fee_probe.py`는 미사용으로 남긴다(삭제하지 않음). #4 수수료 가정은 보수적으로 유지하고 레지스트리 #6대로 첫 LIVE 진입에서 판정. 아래 규칙은 기록으로만 남는다.
사용자 결정 2026-09-15: 레지스트리 #4의 "진입 taker 수수료가 격리 마진을 줄이는가"를 **Binance Futures 테스트넷에서 먼저** 판정한다.
테스트넷은 **메커니즘 전용** — 테스트넷의 MMR·수수료 **값**은 어디에도 쓰지 않는다(값은 항상 메인넷 런타임 조회). 결과는 스크립트가 레지스트리에 새 행(#7 예정)으로 쓴다.
실계정 최소 명목 프로브는 테스트넷이 INCONCLUSIVE일 때만, **Codex 검토 + 사용자 명시 승인** 후.

**고정 파라미터**: BTCUSDT · ISOLATED · 원웨이 · **L = 100**(테스트넷 브라켓 최대가 100 미만이면 중단 — 자동으로 낮추지 않는다) · MARKET ·
수량 = `ceil_to_step(MIN_NOTIONAL × 1.1 / mark)`(런타임 규칙) · **LONG 한 번 → 청산·flat 확인 → SHORT 한 번 → 청산·flat 확인**.
기동은 `run_startup_gate(Mode.LIVE)`(테스트넷 계정에서 layer 1 LIVE 경로를 그대로 탄다).

**읽는 값**(체결 직후, 청산 전): `positionRisk` v2·v3의 BOTH 행 전 필드(`positionAmt`·`entryPrice`·`leverage`·`isolatedWallet`·`isolatedMargin`·`unRealizedProfit`·`liquidationPrice`·`markPrice`·`marginType`, `isolated` 필드 존재 여부) ·
`GET /fapi/v1/userTrades?orderId=`의 체결별 `commission`·`commissionAsset`.

**정의**: Q = |positionAmt| · E = entryPrice · N = Q×E · L = 행의 leverage(게이트 응답과 다르면 INCONCLUSIVE) · C = Σ commission(USDT, 아니면 INCONCLUSIVE) ·
tol = Q × tick_size / L + 0.00000002(진입가 1 tick + 8자리 표시 반올림 두 번) · **W_fee = N/L − C** · **W_nofee = N/L**.
사전조건: C > 2×tol(두 모델이 구별 가능) — 아니면 INCONCLUSIVE.

**판정(다리별)**
- A(1차 · 거래소가 잠근 마진 직접 관측): |isolatedWallet − W_fee| ≤ tol 이고 |isolatedWallet − W_nofee| > tol → **FEE** · 반대 → **NO_FEE** · 그 밖 → **A_NEITHER**
- B(2차 · 청산가): `liquidation_estimate(E, N, L, 테스트넷 규칙, taker=C/N)`과 `taker=0`의 가격을 `liquidationPrice`에서 **tick 수**로 비교 → fee / no_fee / tie
- 다리 판정: A=FEE 이고 B≠no_fee → **FEE** · A=NO_FEE 이고 B≠fee → **NO_FEE** · 그 밖 → **INCONCLUSIVE**

**전체 판정**: 두 다리 모두 FEE → **CONFIRMED_FEE**(#4 가정이 메커니즘상 맞다) · 두 다리 모두 NO_FEE → **CONFIRMED_NO_FEE**(#4는 보수적이나 사실과 다르다 — 게이트를 바꾸려면 **새 행**, 자동 완화 없음) · 그 밖 → **INCONCLUSIVE** → 실계정 프로브 경로(Codex + 사용자 승인).
부가 기록(판정에 쓰지 않음): `isolatedMargin − isolatedWallet`와 `unRealizedProfit`의 차 · v2/v3 `isolated` 필드 존재(테스트넷 모양일 뿐 — 메인넷 `_is_isolated`는 메인넷 캡처로 확정).
**재실행 규칙**: 운영 실패(주문 거부·청산 실패·전송 오류)로 판정까지 못 간 실행은 시도로만 기록하고 재실행 가능. **판정까지 간 첫 실행의 결과가 확정** — 결과를 보고 재실행해 다른 판정을 고르지 않는다.
- 보충(2026-09-15 · 스크립트 작성 전 · 실행 전): B를 계산할 수 없으면(`liquidationPrice ≤ 0`·해석 불가·청산식 `RulesError`) "B≠…" 조건을 **충족하지 않은 것으로** 본다 → 그 다리는 INCONCLUSIVE. `userTrades`가 체결 직후 비어 있으면 최대 5회 1초 간격 재조회, 그래도 없으면 INCONCLUSIVE.


## 12. layer 3 `paper/` 요약 (2026-09-15)
| 모듈 | 역할 |
|---|---|
| `paper/sender.py` | `OrderSender` 프로토콜 · `PaperSender`(mark ± 슬리피지, 불리 방향·불리 tick · 수수료 = 런타임 taker · positionRisk 없음) · `LiveSender`(**생성 조건** `Mode.LIVE` + `LiveChecklist` 전 항목 True + 쓰기 클라이언트 · 레버리지 응답 확인 · MARKET RESULT · 수수료 userTrades · 전송 불명 → `OrderOutcomeUnknown`) |
| `paper/engine.py` | 페이퍼·라이브 공통 엔진 — 모드 차이는 송신기 + LIVE 전용 positionRisk 검사·대사 + PAPER 전용 청산 시뮬레이션 |
| `paper/config.py` | 슬리피지 **0.0002(2 bps 편도, 레지스트리 #7)** + 불리 tick — 0.016 bps를 페이퍼에 한해 대체 |
| `paper/types.py` | 피드 입력(MarkTick·MarkBar)·Fill·이벤트(layer 4 행의 원천) |

**엔진 규칙** (테스트 `tests/test_paper_engine.py`가 잠근다)
- 전략은 `EntryIntent`(방향·SL·TP·레짐)를 낸다. 결정 **이후** 첫 mark 틱(봉 재생은 다음 봉 시가)에서 **송신기의 예상 체결가(`quote_fill_price`: PAPER·LIVE 모두 #7 mark ± 2 bps 불리 tick — 레지스트리 #9)·현재 지갑으로 `size_entry` 재실행** → 레버리지 설정 응답 확인 → MARKET(maxQty 분할).
  이유: 사이징은 #5를 통과하는 **최고** L을 고르므로 결정 시점 L은 게이트 경계에 붙어 있다 — 가격이 몇 USD만 움직여도 체결 기준으로 게이트를 깬다(구현 중 테스트로 발견).
- 한 틱/봉 안 **청산 > SL > TP**(같은 봉 SL·TP → SL). 봉 SL 체결 기준 = min(SL, 시가)(LONG), 봉 TP = TP(갭 이득 없음). 판정 가격은 mark.
- 체결 후 실제 체결가·수량으로 청산 추정(#4)·#5 게이트·SL 손실 재계산 → `PostFillCheck`. **#5가 깨지면 즉시 청산**(사전확약 게이트 — Codex L3 검토로 "기록만"에서 변경). PAPER는 체결가로 사이징하므로 깨지지 않고, LIVE는 실제 슬리피지만큼 깨질 수 있다. 예산 초과(`loss_over_budget`)는 기록만.
- PAPER 청산: mark가 추정 청산가를 넘으면 손실 = N/L − 진입 수수료 − 누적 펀딩 + N×liquidationFee(진입부터 총 N/L + N×fee). 펀딩 정산마다 격리 지갑이 줄어든 만큼 추정 청산가를 갱신(#4 식에 `taker + 펀딩/N`). LIVE는 `LiquidationThresholdCrossed` 알림 후 SL 청산 시도(청산은 거래소가 한다 · #6).
- 펀딩: 틱이 직전 틱의 nextFundingTime을 지나면 **직전 틱의** 펀딩율·mark로 정산(LONG·양수 → 지불). fundingInfo 간격(8h)이 있으면 경계가 격자(00/08/16 UTC) 위인지 확인 → 아니면 `FeedError`. 피드 공백으로 건너뛴 경계는 율을 모르므로 `FundingMissed` + 진입 차단(추정 금지). 봉 재생은 `on_funding`으로 실제 펀딩 이력을 넣는다.
- LIVE만: 진입 후 `positionRisk` 1회 → `post_entry_liquidation_check` + 수량 대사(불일치·조회 실패 → 진입 차단, 포지션은 유지). 청산은 **거래소 보유 수량**을 닫고(반대 부호·0이면 멈추고 차단), 청산 후 flat 대사.
- `OrderOutcomeUnknown` → 진입 차단. LIVE는 거래소 수량을 포지션으로 채택해 SL 감시(방치 금지). 청산 실패 → 포지션 유지·다음 트리거에서 재시도 + 진입 차단. 체결 후 수수료 조회 이상은 예외가 아니라 taker 추정 + 표시.
- 아직 없음: 기동 배선(config → 모드 → 송신기), DB 기록(layer 4), 피드 어댑터(layer 5), 킬스위치(layer 7).


## 13. ccxt/ccxt.pro 전송 (2026-09-15 · 사용자 결정 · 레지스트리 #8)
| 모듈 | 역할 |
|---|---|
| `exchange/ccxt_rest.py` | `RestClient` 구현 — 원시 응답, ccxt가 서명 1회, `POST /fapi/v1/order` → `create_order(market, reduceOnly)` + 우리 `newClientOrderId` + 정밀도 값 가드, 5xx·전송 실패 → `TransportError` |
| `data/feed.py` | `TeeBinanceUsdm`(원시 kline·markPrice·forceOrder 티) · `MarketFeed`(DeliveryCounter를 이벤트 시각으로, 재연결 백오프, 콜백 실패 → `FeedFailure`) |
| `data/backfill.py` | 닫힌 1m kline·mark kline REST 백필(페이지 크기 `data/config.py` 1000 · 문서 최대 1500 초과 거부) |
| `data/shards.py` | 60초 shard parquet(원자적)·대장 등록·writer 스레드(#138)·`Recorder`(큐·드롭·종료 기록) |
| `tests/test_ccxt_stream_tiers.py` | ccxt.pro가 **실제로 여는** URL·SUBSCRIBE를 `ops/stream_tiers.py`로 검증(ccxt 업그레이드마다) |
| `scripts/feed_delivery_probe.py` | 읽기 전용 라이브 전달 프로브 |

- 규칙 값(필터·브라켓·cum·수수료·fundingInfo·positionRisk)은 원시 응답에서만. ccxt 정규화 필드 사용 금지. 수량 정규화는 우리 코드가 권위.
- 게이트·로더·송신기는 코드 변경 없이 ccxt 전송 위에서 테스트한다(`tests/test_ccxt_rest.py`).
- layer 5 완료(2026-09-15): shard 이식·#138 · 소켓별 connect/disconnect/reconnect 이벤트 · **소켓별 23h 선제 재연결**(`client.on_error(ProactiveRefresh)` → 백오프 없이 재watch) · 기록 `recorder.put`(kline1m_update·kline1m_close·markprice, 경계 열 = `TS_COLUMN`) · klines limit 렌더링 확인. 기동 배선(피드 + Recorder + 엔진)은 layer 8.
- LIVE 예상 체결가 = #7(레지스트리 #9, `paper.sender.adverse_fill_estimate` 공용).


## 14. layer 4 `db/` (2026-09-15)
| 모듈 | 역할 |
|---|---|
| `db/schema.py` | 단계 목록(append-only). v1 = §5 테이블 + `engine_events`·`feature_definitions` + `runtime_rules`(layer 1 DDL 글자 그대로) |
| `db/migrate.py` | 유일한 스키마 경로 · `python -m db.migrate <db> [--status] [--target N]` · 체크섬 불일치·DB가 더 새 버전·다운그레이드·열린 트랜잭션 → `SchemaError` · 단계 = 한 트랜잭션 · schema_version 없이 있던 테이블은 열 모양이 같을 때만 흡수 |
| `db/record.py` | layer 3 이벤트 → 행(한 호출 = 한 트랜잭션 · 호출자 트랜잭션이 열려 있으면 `TransactionOpen`) · `record_bar`(inserted/duplicate/enriched/conflict — 값 있는 필드는 덮어쓰지 않음) · close는 같은 방향 open에만 연결 · 중첩 float 거부 · 피처 등록·기록 |

- 모든 데이터 테이블 `mode` CHECK(paper|live) · 가격·수량·비율 TEXT(Decimal 원문, float → `TypeError`) · bool 0/1 CHECK.
- 테스트가 **이벤트 필드 ⊆ 열**을 잠근다(`SizingDecision`→decisions · `PostFillCheck`→`positions.pf_*` · `LiquidationCheck`→`positions.lc_*` · `Fill`→orders · `PositionClosed`→positions · `FundingSettled`→funding_events). 필드를 추가하면 새 마이그레이션 단계가 필요하다.
- 피처: 긴 형식 `(name, params_version, value)` + `feature_definitions`(같은 이름·버전에 다른 파라미터 → `FeatureDefinitionConflict`).
  **스킬 §5(피처마다 열)에서 의도적으로 벗어난다 — 사용자 수용 2026-09-15.** 이유: ① 피처를 추가·버전업할 때마다 마이그레이션 단계가 필요 없다 ② `(name, params_version)` 추적이 행 단위로 강제된다(같은 이름에 다른 정의를 덮어쓸 열 자체가 없다) ③ 한 봉의 피처 집합이 전략마다 달라도 스키마가 같다.
  v2: `(bar_open_ms, name, params_version)` 인덱스(두 피처 테이블) · 재생·백테스트용 넓은 형식은 `db.record.wide_features()`(키 `name@vN`, 값 Decimal/None — SQL 뷰로는 동적 피벗 불가라 조회 함수) · 봉 하나의 피처 집합 왕복 테스트.
- v2 `safety_state`: 킬스위치 등 안전 상태의 append-only 이력(최신 행 = 현재) — 재시작이 트립을 풀지 않게.
- LIVE 채택: `EntryFilled.adopted`(채택 시점 positionRisk) → open 행 `reason='adopted_from_exchange'`·`liq_price_exchange`·positionRisk 원문(`detail`).
- `orders.slippage_vs_mark_bps` = 불리한 방향 양수(BUY `(체결−mark)/mark`, SELL 반대) × 10⁴ — 레지스트리 #7·#9 14일차 재평가의 원천.
- ⚠️ 정정(2026-09-15): "채택은 open 이벤트를 내지 않는다"는 **틀린 보고였다** — 채택 시에도 `EntryFilled`(fills=())가 나가 close가 연결된다. 실제 공백은 출처 표시(채택 여부·positionRisk)였고 `adopted` 필드로 메웠다.
- Codex L6·7 배치로 추가: `EntryFilled.entry_commission`(채택 추정 수수료 포함) · `PositionSynced`(청산 직전 거래소 수량 동기화 → root open의 **수정 행**, reason `adopted_from_exchange`) · `PositionVanished`(LIVE 거래소 수량 0 → close 행 reason `vanished`, 체결가·손익 NULL). 포지션 연결: root = `position_id = id`인 open 행 · 남은 수량 = 최신 open 행(root 또는 수정 행) − close 합.
- 아직 없음: 엔진·피드 → DB 배선, 봉 기록 경로(WS 마감봉·REST 백필), account_snapshots 생산자 — layer 8 기동 배선.


## 15. layer 6 `notify/` (2026-09-15 · Bot API 10.3 렌더링 확인 — ops_log)
| 모듈 | 역할 |
|---|---|
| `notify/commands.py` | 등록 명령 8개(`start stop pause status position close profit help` — BotCommand 1-32자 소문자 제약) · 한글 별칭(시작·중지·일시정지·상태·포지션·청산·수익·도움말)은 텍스트 · 답장 키보드(메뉴 버튼) · `/cmd@다른봇` 거부 |
| `notify/bot.py` | 순수 상태기계 `CommandBot` → 행동(`Send`·`Answer`). 주인 ID 화이트리스트(`TELEGRAM_OWNER_IDS`) · 개인 채팅만 · 기동 전 날짜 메시지 무시 |
| `notify/telegram_api.py` | POST JSON · `ok` 검증 · 토큰을 예외 문구에서 `<token>`으로 가림 · 문서 한도 사전 검사(text 1-4096 · answer 0-200 · callback_data 1-64 bytes) |
| `notify/poller.py` | getUpdates 롱폴링(offset = 최대 update_id + 1, 응답마다) · 처리 실패도 offset 넘김(재처리로 두 번 청산 방지) · 확인 대기 중 1초 폴링 · `setup()` = setMyCommands + MenuButtonCommands |

- 확인 흐름(open-decisions #9): `/stop`·`/close` → 포지션·uPnL + [예/아니오] → +3·+6·+9초 재전송 → +12초 무응답 취소 "청산 안 됨" · **+12초 기한은 콜백에서도 검사**(tick이 멈춰도 늦은 '예' 불실행 · Codex L6·7 #1) · 콜백 nonce 60초 만료(마지막 방어선) · 모든 콜백에 answer.
- 레지스트리 #13(2026-09-16 확정): `/stop` 예 = 진입 차단 + 전량 청산, `/close` 예 = 청산만, `/pause` = 진입 차단·포지션 유지. 이 저장소의 해석: 확인 대기는 하나 · flat이면 `/close`는 확인 없이 "포지션 없음" · 컨트롤러 예외는 "실패" 문구.
- 중요 이벤트 3회 규칙은 `important_resend` 설정(기본 꺼짐) — [확인] 버튼, 3초 간격 3회.
- 아직 없음: `BotController` 구현(엔진·`SafetyGate`·DB 배선) · 폴링 스레드·백오프 — layer 8.

## 16. layer 7 `safety/` (2026-09-15)
| 모듈 | 역할 |
|---|---|
| `safety/killswitch.py` | 일일 손실(UTC 날짜 첫 equity 기준) · 연속 순손실 n회(직전 flat 지갑 대비 — 수수료·펀딩 포함) · 청산 1회 → 발동(첫 사유 유지) · 사람 `resume`만 해제 · 상태 저장/복원 |
| `safety/stale.py` | 레지스트리 #1 `DeliveryCounter.stalled()` → 진입 금지 · 미평가도 금지 · 포지션 있으면 `hold_and_alert` · **markprice**가 grace 초과면 `close`(레지스트리 #14가 #12 ② 대체, 2026-09-16 · kline 정지는 보유) · 정지 집합이 바뀔 때만 알림 |
| `safety/reconcile.py` | 부호 있는 수량 3자 대사(LIVE: 내부↔positionRisk↔DB · PAPER: 내부↔DB, 거래소 값 주면 오류) · 수량 불일치 sticky(사람 해제) · 조회 실패는 다음 성공으로 해제 · 사유 종류가 바뀔 때만 알림 |
| `safety/rate_guard.py` | 어떤 한도든 사용량 ≥ 80% → `relax_polling` 신호(주문은 막지 않음) |
| `safety/gate.py` | `SafetyGate` — 차단 사유 전부 나열 · `/pause` · `/start`(일시정지·킬스위치·sticky 대사 해제, 피드 정지는 못 풂 → 남은 사유 알림) · 저장/복원(`safety_state`) |

- LIVE 청산 감지: 거래소 청산은 `PositionClosed(LIQUIDATION)`로 오지 않는다 → `PositionVanished`(청산 경로) · 봉마다 대사에서 내부≠0·거래소=0(`SafetyGate.observe_reconcile`)을 청산 1회로 보고 발동(Codex L6·7 #2).
- ~~사용자 결정 대기~~ → **2026-09-16 확정**: 킬스위치 값 레지스트리 #11(5%·5회·청산 1·소실 1) · stale 자동 청산 #12(#1 grace 초과 → MARKET reduceOnly) → **#14로 정정: markprice grace 초과만 청산, kline 정지·분당 규칙은 진입 금지만** · 운영 통제 #13(`/stop`·`/close`·`/pause` 의미 · 대사 수량 불일치 사람만 해제 · 일일 손실 날 `/start` 무변경 "blocked by daily-loss limit until 00:00 UTC").
- 배선은 §17(layer 8).

## 17. layer 8 `ops/` + 기동 배선 (2026-09-16)
| 모듈 | 역할 |
|---|---|
| `ops/runtime.py` | `BotRuntime` — 피드·엔진·`SafetyGate`·DB·`CommandBot`의 **단일 소유자**(asyncio 루프 스레드). 진입 게이트 하나(엔진 ∪ 안전 ∪ DB·지갑 재동기화) · 벽시계 1초 `safety_tick`(stale #14 청산(markprice)·텔레그램 inbox 처리·상태 파일) · 봉마다(기록·LIVE 소실/지갑 재동기화·3자 대사·일일 손실 equity·account_snapshots·상태 저장은 바뀔 때만) · `BotController` 구현 |
| `ops/run_bot.py` | PAPER 전용 기동(LIVE → 종료 코드 4) · 인스턴스 락 · **규칙 = 런타임 조회**(읽기 전용 키 권한 실측 → 서명 GET 6종, `runtime:signed` · 읽기 외 권한 키는 종료 코드 4) · 실패/키 없음 → 캡처 스냅샷 fallback + 진입 차단 `rules_from_snapshot`(/start로 안 풀림, 사용자 2026-09-16 (ii)) · 지갑·안전 상태 복원 · **포지션 복원**(`ops/restore.py`) · REST 백필 · 기록기 · 텔레그램 · 피드 + 1초 안전 틱 · 종료 순서 |
| `ops/restore.py` | PAPER 재기동 복원(사용자 2026-09-16 (a)): DB 열린 root 포지션 + 마지막 엔진 스냅샷(`raw_json.position`)이 방향·수량·진입가·레버리지·SL·TP·진입 시각·누적 펀딩까지 일치할 때만 `Engine.restore_position`(→ `PositionRestored`) · 불일치 → flat · `paused:system:restart_position_mismatch` · 알림 · DB 고아 행은 `restart_unrestored` close(손익 없음 · 킬스위치 미계수) · 내려가 있던 동안 지난 펀딩 경계는 첫 틱에 `FundingMissed` + 진입 차단 |
| `ops/run_events.py` | 직전 실행 종료 판정(레지스트리 #15 ⑤): 기동마다 대장 `start` · 마지막 `stop`/`stop_dirty`/`dirty_previous_run` 뒤 `start`/`connect` → `dirty_previous_run`(대장 + `DirtyPreviousRun` 운영 이벤트) · 상태 파일 `confirmed_facts`(최근 24시간, 기동 때 한 번 읽음) → health가 한 번 알림 |
| `exchange/permissions.py` | 키 권한 실측(`apiRestrictions`) — 러너·캡처 스크립트 공용 |
| `scripts/dryrun_restart_restore.py` | 드라이런 하네스(PAPER 전용 · 운영 유닛은 부르지 않음): 진입 1건 주입 → SIGKILL → 재기동 → 복원·진입 재허용 확인 · 키는 `--use-binance-key` 명시 때만 |
| `ops/telegram_link.py` | 폴 스레드(`fetch` → inbox, 백오프 1·2·5·10·30·60초) · 발송 스레드(outbox → API, `message_id`로 배달 집계) — 엔진 상태를 만지지 않는다 |
| `ops/data_stores.py` | 저장소 표(allowlist): `raw_live` shard만 `drive_verified_prune` · sqlite(봇 DB·manifest)는 `never` · 원격 = `BTCFUT_DRIVE_REMOTE`(E2E 폴더 거부) |
| `ops/drive_sync.py` | `rclone copy --checksum --min-age 90s` + sqlite 온라인 백업 → `copyto` · 원격 삭제 없음 · 실패 시 마커 미갱신 |
| `ops/prune.py` | 🔴 삭제: `=`만 · 그날 하나라도 미검증이면 전체 보류 · 삭제 전 원격 md5 · 대장 기록 수 ≠ 삭제 수 → 실패 · `.parquet`만 · 심볼릭 링크 불추종 · 기본 dry-run · 보존 30일 · 최대 7일/회 |
| `ops/health.py` | 상태 파일·마커·디스크 → 고정 키 문제 목록 · 반복형 3h 스로틀 · 확정 사실 하루 1회 · 발송 실패 시 상태 미갱신 · digest |
| `ops/notify_failure.py` | `OnFailure=` 알림(유닛에 코드 박지 않음) |
| `ops/systemd/` | 봇 사용자 user 유닛 템플릿: bot(Nice 10·IO best-effort 7·MemoryMax 700M) · health-alert 5분 · digest 00:30 UTC · sync 매시 :20 · prune 일 03:30 UTC(첫 배포 미설치) · failed@ |
| `docs/runbook_vps.md` | 사용자 생성·설치·수집기 우선 확인·기동 후 대조표(vps-ops §8)·prune 켜기 절차·정지/재기동 |

엔진·안전 변경(같은 배치 · Codex 검토):
- `PositionReduced` — 부분 청산 체결·손익·잔량 → `orders` + `positions` close 행(detail `partial`) → DB 남은 수량 = 엔진 잔량 → 대사가 사람 없이 맞는다(사용자 2026-09-16). 킬스위치 연속 손실은 flat이 되는 `PositionClosed`에서만.
- `Engine.vanish` — LIVE 봉 대사에서 거래소 flat · 내부 보유 → 주문 없이 내부 close(`PositionVanished` 전량) + 진입 차단. 손익은 거래소 지갑 재동기화(`sync_wallet` → `WalletResynced` + `KillSwitch.sync_flat_wallet` + account_snapshots source exchange)로 들어온다. 조회 실패면 `exchange:wallet_resync_due` 차단 · 다음 봉 재시도.
- `Engine.entries_blocked`는 **사유 목록** · `/start`가 `clear_blocks`로 해제(일일 손실 날은 무변경) · `cancel_pending`(결정 뒤 게이트 닫힘 → `EntrySkipped(entries_blocked)`) · `equity(mark)` = 지갑 + 미실현.
- `ExitReason.STALE_DATA` — PAPER stale 청산의 체결 기준가는 **마지막으로 받은 mark**(`orders.ref_mark`로 분리 가능).

Codex L8 1차 반영: 운영 이벤트·안전 상태 저장 실패도 보관·재시도 + `db:unrecorded_ops`·`db:unsaved_safety_state` 차단 · 봉 DB 읽기 실패는 피드 밖으로 던지지 않고 `db:read_failed` 차단(다음 봉 성공으로 해제) · prune은 모든 대상의 원격 md5가 없으면 그날 전체 보류 · 폴 스레드는 루프 소유 `fast_poll` 이벤트만 읽는다 · LIVE 동기 읽기는 §10 체크리스트로 명시 보류. 재검토 #1 반영: 저장 안 된 안전 상태는 DB 밖 breadcrumb(`var/run/safety_unsaved.json`)에 남고, 재기동 때 복원 + 진입 일시정지(해석 불가도 일시정지 · 파일 보존). 재검토 #2·#3 반영: 운영 이벤트 `op_id` 멱등 · breadcrumb 신선도는 **행 id**(`base_state_id` vs DB 최신 `safety_state.id`)로 판정, breadcrumb에만 있는 트립은 항상 복원 · 보류: `engine_events` op_id 조회 인덱스(스키마 v3 필요).

운영 경보 값(게이트 아님 · health): 상태 파일 나이 > 120초(레지스트리 #1 grace 재사용) · sync 마커 > 3시간 · prune 마커 > 8일 · 텔레그램 폴 마지막 성공 > 10분 · 디스크 여유 < 5 GB · 반복형 스로틀 3시간(E2E 값).

알려진 한계(보고 · 결정 필요):
- ~~페이퍼 포지션은 재기동 때 엔진에 복원되지 않는다~~ → **2026-09-16 (a) 구현**: 일치할 때만 복원(`ops/restore.py`).
- 런타임 규칙은 **기동 때만** 읽는다(주기 재조회 없음) — `rules_from_snapshot` 차단은 재기동으로만 풀린다.
- PAPER 러너는 기동 게이트(`run_startup_gate`)를 부르지 않는다 — 게이트는 계정을 **변경**(격리·레버리지 POST)하는데 PAPER는 POST 금지이고 읽기 전용 키로는 할 수도 없다. LIVE 배선 때 필수.
- SIGKILL 뒤 shard 기록기의 미기록 버퍼(최대 한 롤 주기)는 사라진다 — **수용**(레지스트리 #15 ⑥ · E2E가 정본 수집기 · 드라이런 약 17초).
  대장에 `stop` 없이 `start`/`connect`만 남은 직전 실행은 기동 때 `dirty_previous_run`으로 기록·한 번 알림(`ops/run_events.py` · #15 ⑤).
- 확정 사실(`confirmed_facts`): `restart_unrestored`는 /start 확인 전까지 /status + health 하루 한 번 · `dirty_previous_run`은 한 번(#15 ①⑤).
- LIVE `ExchangeReader`(positionRisk·계좌)는 **프로토콜과 가짜 구현 테스트만** 있다 — 계좌 응답 필드는 v6에 없어(가중치 표만) 공식 문서 렌더링·실캡처 확인이 먼저다.
- `important_resend` 알림 재전송은 30초 롱폴링 중에는 늦을 수 있다(기본 꺼짐) — 확인 흐름 재전송은 안전 틱(1초)이 돌린다.
