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
| 3 | `paper/` 체결 엔진(taker-only·mark 기준+보수 슬리피지·같은 봉 SL 우선·펀딩 실율·maxQty 분할). 라이브 전송기는 LIVE+체크리스트 게이트 뒤 | ⏸ |
| 4 | `db/` 버전 마이그레이션 SQLite(bars_1m·features_*·decisions·orders·positions·funding_events·account_snapshots·runtime_rules) | ⏸ (`runtime_rules` DDL은 임시로 `exchange/store.py`) |
| 5 | `data/` 1m kline(/market) + REST 백필 · markPrice@1s 같은 소켓 · 스트림별 전달 감시 · manifest | ⏸ (`ops/delivery_counter.py`·`data/manifest.py` 복사 완료) |
| 6 | `notify/` 텔레그램 명령·확인·재전송·만료 (2026-09-15 `telegram/`에서 개명 — PyPI `python-telegram-bot` import 이름 가림 방지) | ⏸ (`notify/sender.py` 복사 완료) |
| 7 | `safety/` 킬스위치·stale-data kill·봉마다 대사·rate-limit 80% 가드 | ⏸ |
| 8 | `ops/` VPS systemd 템플릿·health/alert 타이머·Drive 검증 prune·런북 | ⏸ |
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
| `e2e/l2_collector.py` `ShardWriter`(:143-191)·`WriterThread` 종료 플러시(:193-303, #138 `final_flush_failed`→`stop_dirty`) | `data/` (layer 5) | `90d47aa` | **패턴 — 미복사** | 60초 shard·tmp→atomic rename·writer별 독립 종료 플러시. 여기서 테스트할 수 없는 800줄 결합 코드라 layer 5에서 이식 |
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
| B4 | 2026-09-15 | `SizingLimits.buffer` 값 | ⏸ 레지스트리 #3 값 사전등록 대기 |
