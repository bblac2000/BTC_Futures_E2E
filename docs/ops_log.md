# 운영일지 (새 항목은 맨 위)

> 판정·사전등록·정정의 정본은 `docs/trial_registry.md`. 여기는 경위·맥락, 그리고 **복사해 온 E2E 모듈을 고친 기록**(역이식 후보)을 둔다.

## 2026-09-15 — 저장소 부트스트랩 · layer 1

**한 일**
- git init · uv(py3.12) · ruff/pyright/pytest · CI(`.github/workflows/ci.yml`: ruff → pyright → pytest → `python -m ops.stream_tiers --scan`).
- v6 원문 복사(E2E `175c356`, md5 일치). 스냅샷 fixture 4종 복사(VolumeClockBot `6d0129d`, md5 일치) + 합성 2종(positionSideDual·multiAssetsMargin — 캡처 없음).
- E2E 모듈 복사: stream_tiers · delivery_counter · manifest · telegram sender (`docs/design_v1.md` §4).
- layer 1 `exchange/` 구현. 테스트 먼저 작성 → 5개 파일 수집 오류(모듈 부재)로 red 확인 → 구현 → green.

**정정 1건 (같은 날)**: Donchian 프로토타입을 E2E `e2e/paper/`(Track P)에서 `legacy/proto_donchian_v0/`로 복사했다가 **사용자 정정으로 삭제**했다.
지시는 "그 프로토타입을 쓰지 말라"였지 옮기라는 게 아니었다. 이 저장소에는 어떤 Donchian 코드도 없다. E2E 원본은 처음부터 변경 없음(`git status` 확인).

**결함 1건 자체 발견·수정 (같은 날, advisor 검토)**: `gate.py`가 positionRisk에서 `positionSide=BOTH` 행만 찾았다. 헤지 모드의 실제 응답은 **LONG·SHORT 두 행이고 BOTH가 없다** →
LIVE는 `dualSidePosition→false` 전환 단계에 가기 전에 "조회 실패"로 중단(fail-closed라 위험은 없었으나 docstring 1단계가 사문화), PAPER는 헤지 계정을 "읽을 수 없다"로 오분류.
기존 테스트가 통과한 이유: 가짜 계정이 `dual=True`여도 BOTH 행을 돌려줬다. 가짜 계정을 실제 모양으로 고치자 **4개 red**(기존 2 + 신규 2) → 헤지 flat 판정을 두 다리 합산으로 수정 → green 123.
형태: *"docstring이 약속한 불변식을 코드가 안 지킨다"*(ExecVerifyBot F-DDLBEFOREVER 등과 같은 형태) — **테스트 더블이 실제 응답 모양을 따르지 않으면 테스트가 그 약속을 증명하지 못한다.**

**발견 — 부트스트랩 지시와 실제가 다른 것 (추측으로 메우지 않음)**
1. `ops/data_stores.py`(allowlist prune)는 E2E f1e7d86에 **코드로 없다** — 설계 문서뿐(#131). layer 8에서 설계대로 구현.
2. 비용 10.02 bps는 `e2e/cost` 코드 상수가 아니라 문서 값(`Phase1A_계측결과:180,197`). layer 3에서 수수료=런타임 commissionRate, 슬리피지=꼬리표 달린 실측값으로 분리.
3. ShardWriter/#138 종료 플러시와 vps_health 스로틀 구조는 800줄 결합 코드라 **패턴으로만** 등록, layer 5/8에서 테스트와 함께 이식.

### 복사본 수정 기록 (역이식 후보)
| 로컬 파일 | 수정 | E2E로 역이식할 가치 |
|---|---|---|
| `notify/sender.py` (옛 `telegram/sender.py`) | `_post(opener=...)` 주입 — 200 + `ok:false`를 실패로 읽는지 테스트 가능 | ✅ E2E `notify.py`에 같은 테스트가 없다 |
| `ops/delivery_counter.py` | `silence_summary`에서 `first_ms/last_ms is None` 가드 추가(pyright), pyarrow.compute를 `Any`로 받아 pyright clean | 🟡 동작 동일 · 타입만 |
| `data/manifest.py` | DB 경로를 모듈 속성으로 주입 가능하게 | ➖ E2E 구조에선 불필요 |

## 2026-09-15 — Codex 독립 검토 · layer 1 (read-only) · 원문

- 의뢰 범위: `exchange/gate.py` LIVE 분기 · `client.py` 서명/POST · `orders.py`+`normalize.py` 매트릭스. 코드 수정 금지(read-only). job `task-mu1zv0h4-qazyjb`, 3m52s
- 판정 요약: Q1 OK · Q2 OK · Q3 ISSUE · Q4 ISSUE · Q5 ISSUE — **셋 다 채택·수정**(아래 조치)

### 조치 (TDD: 테스트 추가 → 4 red → 수정 → 125 green)
| Codex | 조치 | 테스트 |
|---|---|---|
| Q3 헤지 전환 사전검사가 BTC만 봄(포지션 모드는 계정 전역) | `_account_flat()` — 심볼 없이 positionRisk·openOrders 전체 조회, 하나라도 있으면 POST 전 중단. COIN-M(dapi)은 이 API로 안 보임 → 거래소 거부 시 중단(fail-closed) 명시 | `test_live_hedge_switch_preflight_is_account_wide_not_just_btc` |
| Q4 공개 `market_order_params(side, reduce_only)`로 의미상 청산을 reduceOnly 없이 생성 가능 | 공개 서명을 `(symbol, Direction, Intent, qty, rules)`로 교체 — side·reduceOnly를 Intent에서 함께 도출. side 직접 생성기는 `_params` 비공개 | `test_exit_intent_always_carries_reduce_only_and_entry_never_does` |
| Q5 응답 모양 이상이 KeyError 등으로 새어 StartupAbort가 아님 | LIVE: 모양 예외 전부 `StartupAbort`; bool 필드 `_bool()` 검증; 레버리지 응답 키 검증. PAPER: 같은 예외를 WARNING으로 | `test_live_unexpected_response_shape_is_a_startup_abort_not_a_bare_exception` |
| Q3 불확실 — positionRisk V2에 `isolated` bool 미기재 | `_is_isolated` docstring에 기록. `marginType` 판정 + `isolated` 키가 있으면 true 요구. 라이브 전 실캡처로 확인(TODO) | — |

### Codex 회신 원문 (verbatim)

```text
Q1. **OK**  
Evidence: LIVE only sets `entries_allowed=True` after one-way confirmation, multi-assets abort check, isolated re-read confirmation, and leverage echo check in [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:137), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:150), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:169), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:175), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:183).  
Concrete failure scenario: if `marginType` POST “succeeds” but re-read still shows non-isolated, `_is_isolated` fails and `abort()` raises `StartupAbort` with entries off/exits on at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:126), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:170), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:171). If leverage echo differs, it aborts at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:175).

Q2. **OK**  
Evidence: `run_startup_gate(..., Mode.PAPER)` wraps the supplied client in `ReadOnlyClient` before `_paper` runs at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:85); `_paper` only calls `get()` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:100); `ReadOnlyClient.post()` raises before network at [exchange/client.py](/home/cms/project/BTC_Futures_E2E/exchange/client.py:105).  
Concrete failure scenario: PAPER with cross margin, hedge mode, multi-assets, and a position still records zero posts in the test at [tests/test_gate.py](/home/cms/project/BTC_Futures_E2E/tests/test_gate.py:84).

Q3. **ISSUE**  
POST query-string signing is OK: the client puts signed POST params in the URL query at [exchange/client.py](/home/cms/project/BTC_Futures_E2E/exchange/client.py:63) and [exchange/client.py](/home/cms/project/BTC_Futures_E2E/exchange/client.py:69). Binance says POST params may be query string or form body, and signed `signature` may be query/body with `totalParams` signed: official docs lines 170-173 and 275-279 at https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info.  
Behavior issue: the gate preflights hedge-mode switch using only the bot symbol via `_flat(client, sym, _symbol_rows(...))` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:139), then calls global `positionSide/dual` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:142). Binance documents that position mode is “on EVERY symbol” and rejects if either side has any open order/position, lines 169-176 at https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade. Concrete failure scenario: ETH has an open position, BTCUSDT is flat; this code sends the global mode-change POST, Binance rejects, and the gate aborts safely. It should not proceed to entries, but the preflight assumption is too narrow.  
Uncertain: local v6 requires re-read `isolated=true` at [docs/바이낸스문서API_2026_v6.md](/home/cms/project/BTC_Futures_E2E/docs/바이낸스문서API_2026_v6.md:48), while current official PositionRisk V2 docs list `marginType` but not an `isolated` boolean, lines 6411-6417 and 6500-6506 at the trade doc. The code treats missing `isolated` as true at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:68), so this is probably pragmatic, but worth documenting.

Q4. **ISSUE**  
Evidence: `side=LONG/SHORT` and non-MARKET types are blocked by `market_order_params()` and `validate_order_params()` at [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:67), [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:110), [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:112). `close_position_orders()` correctly sets `reduce_only=True` at [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:94).  
Concrete failure scenario: a future layer can call the public low-level `market_order_params("BTCUSDT", Side.SELL, qty, rules, reduce_only=False)` for what is semantically a long exit; validation passes because the dict has no intent marker and `reduceOnly` is only checked when present at [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:65), [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:116). That order could reduce, flip, or open exposure instead of being reduce-only.

Q5. **ISSUE**  
StartupAbort semantics are good for `BinanceAPIError`/missing credentials, but unexpected response shapes can escape as `KeyError`, `TypeError`, or `ValueError`, not `StartupAbort`: direct indexing/conversion happens at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:137), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:150), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:176), while the catch only covers two exception classes at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:180). Concrete failure scenario: leverage response lacks `leverage` or returns a non-int-like value; process gets a generic exception instead of `StartupAbort(result.entries_allowed=False, exits_allowed=True)`.

Recommended changes:
1. Preflight `positionSide/dual` as an account-global change: inspect all UM/CM positions/open orders or document a dedicated-account invariant before sending that POST.
2. Make exit order construction intent-safe: remove/privatize the public low-level `reduce_only` escape hatch, or require an `Intent` and force exits to include `reduceOnly="true"`.
3. Wrap unexpected gate response-shape errors into `StartupAbort` so entries are always off and exits remain explicitly allowed.
4. Add tests for all-symbol hedge-mode preflight and for “semantic exit without reduceOnly cannot be built.”
5. Document the `positionRisk` `isolated` field mismatch: local v6 wants `isolated=true`, current official V2 docs show `marginType` but not that boolean.

Observed tests: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -s -p no:cacheprovider tests/test_gate.py tests/test_client_ratelimit_time.py tests/test_orders.py tests/test_normalize.py` passed: `64 passed`, with one Hypothesis in-memory storage warning. Full suite could not complete because unrelated tmp-path tests need a writable temp directory in this read-only environment.

Codex session ID: 01a0a2af-239e-73a3-84f0-5120df9ee591
Resume in Codex: codex resume 01a0a2af-239e-73a3-84f0-5120df9ee591
```

## 2026-09-15 — Codex 재검토 · layer 1 수정 3건 (read-only) · 판정과 동의 여부

- 의뢰: 커밋 `e9e7a32` 기준, 1차 검토(Q3·Q4·Q5)로 들어간 수정 F1·F2·F3만 재검토. 코드 수정 금지. job `task-mu20lg9y-h4uua9`, 4m9s.
- 판정: **F1 PARTIAL · F2 CLOSED · F3 PARTIAL** + 신규 1건.

### 항목별 동의 여부와 조치 (TDD: 테스트 7개 추가 → red → 수정 → 전체 green)
| # | Codex 지적 | 동의 | 조치 · 근거 |
|---|---|---|---|
| F1-a | `_account_flat`이 `positionAmt` 없는 행을 `"0"`으로 쳐서, 깨진 행이 계정 전역 POST 전 검사를 통과 | ✅ **동의** | `_amt()` 엄격 해석(필드 없으면 TypeError → LIVE StartupAbort). `_flat`·PAPER 스캔도 같은 함수. 테스트 `test_live_account_preflight_row_without_position_amt_aborts_before_post`, `test_live_margin_switch_row_without_position_amt_aborts_before_post` |
| F1-b | 일반 `openOrders`는 별도 **algo 미체결**을 보여주지 않는다 → 사전검사 통과 후 POST가 -4067로 거부될 수 있음(fail-closed이나 사전검사로는 불충분) | 🟡 **원칙 동의 · 이번엔 미구현** | 이 봇은 algo 주문을 쓰지 않지만 수동으로 걸어 둔 주문은 있을 수 있다. 다만 algo 미체결 조회 경로를 **문서로 확인하지 않은 채 추측으로 넣지 않는다**(Codex도 불확실 표기). 현재도 거래소 거부 → `BinanceAPIError` → StartupAbort로 **진입은 막힌다**. TODO: 공식 문서로 경로 확인 후 사전검사에 추가 |
| F1-c | COIN-M은 fapi로 안 보이고 거래소 거부에 의존 — 변경 시도 POST는 나간다 | ✅ **동의(수용)** | UM·CM이 `dualSidePosition`을 공유하고 한쪽에 포지션·미체결이 있으면 POST가 거부된다(Codex가 공식 문서 인용). 거부된 POST는 상태를 바꾸지 않으므로 fail-closed로 수용. 전용 계정 운용을 라이브 체크리스트 항목으로 둔다 |
| F2 | CLOSED. `_params`는 공개 경로는 아니나 유지보수 위험 | ✅ **동의** | orders.py 밖에서 `_params`를 참조하면 실패하는 AST 테스트 추가(`test_private_params_builder_is_not_used_outside_orders_module`) |
| F3 | **POST가 거래소에 닿아 상태를 바꾼 뒤** 타임아웃·연결 끊김 등 `HTTPError`가 아닌 전송 실패가 나면 StartupAbort가 아닌 예외로 새어 나간다 | ✅ **동의 — 이번 재검토의 가장 중요한 지적** | `client.py`: `URLError`·`OSError`·`http.client.HTTPException` → `TransportError`("거래소 도달·처리 여부 불명"). `gate.py` LIVE: `TransportError`·`OSError` → StartupAbort, 사유에 **"계정 상태 불명 · 직전 actions · 재조회 후 재기동"** 기록. 테스트 `test_transport_failures_become_transport_error_with_unknown_outcome`(3종), `test_live_transport_failure_after_a_mutating_post_is_a_startup_abort` |
| F3-참고 | ValueError/TypeError를 잡으면 프로그래밍 버그가 기동 중단으로 가려질 수 있으나 진입을 허용하지는 않음 | ✅ 동의 | 유지. 중단 사유에 예외 타입·메시지를 남겨 버그가 묻히지 않게 한다 |
| 신규 | PAPER 포지션 다리 스캔이 `try` 밖이라 잘못된 `positionAmt`에서 `InvalidOperation`이 샌다 | ✅ **동의** | 스캔을 `try` 안으로, `InvalidOperation`·`TransportError`·`OSError`도 WARNING 처리. 테스트 `test_paper_bad_position_amt_is_a_warning_not_a_crash` |

⚠️ 이 수정분(F1-a·F2 테스트·F3·신규)은 **Codex 3차 검토를 받지 않았다.** 변경은 fail-closed 방향(중단 조건 추가)뿐이다.

### Codex 재검토 회신 원문 (verbatim)

```text
**F1: PARTIAL**

Evidence: [_account_flat](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:82) now does no-symbol `GET /fapi/v2/positionRisk` and no-symbol `GET /fapi/v1/openOrders` before the global mode POST at [_live](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:159). The targeted BTC-only bug is closed: the test covers other-symbol positions and orders before POST at [tests/test_gate.py](/home/cms/project/BTC_Futures_E2E/tests/test_gate.py:162).

For documented USD-M position rows, this is the right shape: Binance documents `positionRisk` V2 as signed, weight 5, optional `symbol`, returning rows with `positionAmt`, `symbol`, and `positionSide`. `openOrders` without `symbol` returns all-symbol orders, weight 40, with no pagination parameter shown. Startup-only weight 45 is acceptable.

Concrete remaining scenarios:
- Row-shape gap: `_account_flat` treats missing `positionAmt` as `"0"` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:85). A malformed row can pass the preflight instead of aborting before POST.
- Uncertainty: normal `openOrders` does not prove absence of separate algo orders. Binance exposes “Current All Algo Open Orders” separately; a manual/foreign algo order could make preflight pass and then the mode POST fail with `-4067`. That is fail-closed, but not a sufficient preflight.
- COIN-M: official docs now say UM and CM share `dualSidePosition`, and the POST is rejected if either side has open orders/positions. Relying on that rejection is acceptable fail-closed, though it still sends a mutating endpoint attempt.

**F2: CLOSED**

Evidence: public construction now requires `(Direction, Intent)` and derives side plus `reduceOnly` together at [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:65). `ENTRY` omits `reduceOnly`; `EXIT` sets `"true"` via [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:74) and [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:89). `close_position_orders` derives held direction from `position_amt` sign at [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:104). Validator rejects `side=LONG/SHORT`, non-`BOTH` positionSide, and bad reduceOnly values at [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:120).

No public path I found can produce an exit without `reduceOnly="true"`, an entry with `reduceOnly`, or API `side` LONG/SHORT. The private `_params` at [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:77) is still technically callable in Python, but `rg` shows no production caller except `market_order_params`; I would treat it as a maintenance risk, not an open public escape hatch. Binance also documents order `side` as BUY/SELL, `positionSide` default BOTH in one-way, and `reduceOnly` as true/false string, not for hedge mode.

**F3: PARTIAL**

Evidence: response-shape issues inside `_live` are mostly closed: `_bool` validates bool response objects at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:76), leverage echo shape/key is checked at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:199), and shape exceptions are converted to `StartupAbort` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:208). The targeted tests cover bad leverage and bad bool response at [tests/test_gate.py](/home/cms/project/BTC_Futures_E2E/tests/test_gate.py:175).

Concrete remaining failure scenario: `BinanceRestClient._request` catches `HTTPError` only at [exchange/client.py](/home/cms/project/BTC_Futures_E2E/exchange/client.py:71). If a POST reaches Binance and mutates state, then the socket times out, connection resets, or body read raises a non-`HTTPError` transport exception, `_live` does not catch it at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:206). That can escape as a non-`StartupAbort` after `/positionSide/dual`, `/marginType`, or `/leverage` has changed account state.

Catching `ValueError`/`TypeError` does not look dangerous for trading: it fails closed before `entries_allowed=True` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:212). It can hide a programming bug as a startup abort, but not in a way that permits entries.

**New Issues**

Potentially introduced by F1: missing `positionAmt` defaults to zero in `_account_flat`, so malformed position rows do not fail closed before the mode-change POST.

Separate note: PAPER does not fully catch all shape errors as warnings; invalid `positionAmt` in the warning leg scan at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:137) can still raise `InvalidOperation` outside the `try`.

Verification: `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q -s -p no:cacheprovider tests/test_gate.py tests/test_orders.py` passed, 45 tests.

Codex session ID: 01a0a2c1-ef47-7043-986d-4fd3101d8b5e
Resume in Codex: codex resume 01a0a2c1-ef47-7043-986d-4fd3101d8b5e
```

## 2026-09-15 — 사용자 결정 반영 (layer 1 수용 후)

- **CI**: 첫 커밋 `e9e7a32` 푸시 → https://github.com/bblac2000/BTC_Futures_E2E/actions/runs/34918527016 ✓(ruff·pyright·pytest·stream-tier scan). 저장소 **PUBLIC** 확인 → 계정 캡처는 BTCUSDT 행·권한 bool만 기록.
- **`.env`**: 사용자가 저장. git 미추적 확인, 키 이름 4개 확인(값은 보지 않음), 권한 644 → **600**으로 조정.
- **개명** `telegram/` → `notify/` (PyPI `python-telegram-bot` import 가림 방지). import·pyright·stream_tiers 스캔 대상·문서 갱신.
- **레지스트리 #1** 전달 감시 임계 사전확약 — kline 감시 둘(update·close) + markprice. 사용자 옵션 3.
- **캡처 스크립트** `scripts/capture_account_snapshot.py` — GET 전용(ReadOnlyClient), 키 권한 실측 후 읽기 외 권한이 있으면 쓰기 없이 exit 2. 사용자 실행 대기. ⚠️ 이 스크립트는 테스트를 코드와 **함께** 작성했다(red 단계를 따로 보이지 않음).

## 2026-09-15 — layer 2 `sizing/` (`d1ed96d`)

- `sizing/position.size_entry` 순수 함수: SL 가격 입력 → sl_dist → L_raw → floor → 레짐 클램프 → 정수 L을 1씩 낮추며 (브라켓 initialLeverage · `1/L − MMR − liquidationFee > sl×buffer`) 검사 → 수락 시 `normalize_entry_qty`·`split_market_qty` 재사용. 거부 사유는 `normalize.RejectReason`에 합침(sl_wrong_side·liq_distance·leverage_infeasible).
- TDD: `tests/test_sizing.py` 먼저 → 수집 오류(모듈 부재) red → 구현 → green.
- 🔴 **속성 테스트가 공허하게 통과하던 것을 잡았다**: SL 0.03~2% 균등 생성이면 fixture 규칙에서 99% 거부(2만 건 중 수락 206) → 400 예제 중 수락 ~4건만 검사. 생성기를 둘로 나누고(수락 구간 SL ≤ 0.34%·buffer ≤ 1.3·l_min ≤ 55 / 넓은 구간은 거부 속성), **수락 비율이 30% 이상인지 테스트가 확인**한다(실측 270/400). 조사 과정에서 `l_min > ~60` 레짐은 BTC에서 수락이 없다는 것도 확인 → 설계서 §9 B1.
- 미결 2건을 설계서 §9에 기록(B1 liquidationFee 포함 시 100x 구조적 불가 · B2 클램프 시 risk_pct 무의미). **임의로 고르지 않았다** — 사용자 지시식(MMR + liquidationFee) 그대로 구현.

## 2026-09-15 — Codex 독립 검토 · layer 2 `sizing/` (read-only, `d1ed96d`) · 판정과 동의 여부

- job `task-mu21ai6o-slrnyc`. Codex는 읽기 전용 환경에서 `uv` 캐시 잠금을 못 만들어 **pytest를 직접 돌리지 못했다**(원문 첫 줄) — 판정은 코드 판독 기반.
- 판정: Q1 OK(단조 브라켓 전제)·불변식 미검증 ISSUE · Q2 OK(불확실 표기) · Q3 OK · Q4 ISSUE · Q5 ISSUE.

### 항목별 동의 여부와 조치 (TDD: 테스트 6개 추가 → 4 red → 수정 → 전체 178 green)
| # | Codex 지적 | 동의 | 조치 |
|---|---|---|---|
| Q1 | 수량 내림 후 최종 명목이 **다른 브라켓**에 들 수 있는데 계획 명목의 브라켓·MMR로 검사한 채 수락. 비단조 브라켓이면 불안전 수락이 가능(실제 BTC 단조 티어에선 발현 안 함) | ✅ **동의** | 최종 명목으로 브라켓·L 상한·청산 거리를 **재검증**, 실패 시 `LIQ_DISTANCE`("내림 후 …"). 테스트 `test_flooring_into_a_riskier_bracket_is_revalidated_and_refused`(Codex 입력 그대로) |
| 권고2 | 파서가 MMR 비감소·cum ≥ 0·레버리지 상한 비증가를 검증하지 않는다 | ✅ **동의** | `parse_brackets`에 세 검증 추가 — 사이징의 보수성 전제(명목↓ ⇒ 위험↓, cum 무시 = 보수)를 로드 단계에서 강제. fixture 12티어 통과. 테스트 `test_parser_rejects_non_monotone_brackets` |
| Q2 | cum 무시는 cum ≥ 0이면 보수적. liquidationFee 차감은 exchange-rules §5 모델이면 맞고, v6 §4.4 기준이면 보수적(불확실) | ✅ 동의 | cum ≥ 0을 파서가 강제(위). liquidationFee 포함 여부는 **설계서 §9 B1 사용자 결정 대기**로 둔다 — Codex 판정과 같은 결론(모델 선택 문제) |
| Q3 | 탐색 최대성 OK. 아주 작은 SL이면 거대한 정수를 만든 뒤 클램프 | ✅ 동의 | `floor(min(L_raw, l_max))`로 먼저 자름. 테스트 `test_tiny_sl_distance_clamps_without_materializing_a_huge_integer` |
| Q4 | 모든 브라켓 cap 초과가 `LEVERAGE_INFEASIBLE`로 뭉개진다 | ✅ **동의** | `RejectReason.NOTIONAL_CAP` 추가, 사유 우선순위 = 청산거리 > 브라켓 레버리지 > 명목 cap. 테스트 `test_notional_beyond_every_bracket_has_its_own_reason` |
| Q5-a | 결과의 bracket·MMR·청산가가 계획 명목 기준(경계 300000 → 내림 후 tier1인데 tier2 보고) | ✅ **동의** | 결과는 **최종 명목 기준**으로 기록. 테스트 `test_reported_bracket_is_the_final_floored_notional_not_the_planned_one`(Codex 입력 그대로) |
| Q5-b | layer 3는 주문 전 `POST /leverage == decision.leverage` 확인 필수, 최종 브라켓 기록 | ✅ 동의 | layer 3 TODO로 등록(아직 전송 경로 없음) |
| 권고4 | 나눗셈 많은 검사에 로컬 Decimal 문맥 고정 | ✅ 동의 | `size_entry`가 `localcontext(prec=34)` 안에서 계산. 테스트 `test_result_does_not_depend_on_the_callers_decimal_context`(※ 이 테스트는 수정 전에도 통과했다 — prec 6에서도 판정이 같았음. 회귀 잠금으로 유지) |

### Codex layer 2 검토 원문 (verbatim)

```text
Read-only review only. I did not modify files. I could not run `uv run pytest -q tests/test_sizing.py`: `uv` tried to create a temp/cache lock under `/home/cms/.cache/uv`, and the read-only filesystem rejected it.

**Q1. OK with required invariant / ISSUE if unvalidated rules**
For valid Binance BTCUSDT brackets where MMR is nondecreasing as notional tier increases, I do not see an accepted LONG/SHORT size whose buffered SL is outside the checked liquidation distance. The strict check is at [sizing/position.py:117-119](/home/cms/project/BTC_Futures_E2E/sizing/position.py:117), and LONG/SHORT only differ in SL side and reported v6 price at [sizing/position.py:70-72](/home/cms/project/BTC_Futures_E2E/sizing/position.py:70).

But the safety depends on an invariant the parser does not enforce: after qty flooring, final notional can fall into a lower bracket, while `size_entry` keeps the pre-floor bracket/MMR. Evidence: planned bracket is selected before normalization at [sizing/position.py:108-119](/home/cms/project/BTC_Futures_E2E/sizing/position.py:108), then qty is floored and returned without bracket recomputation at [sizing/position.py:130-144](/home/cms/project/BTC_Futures_E2E/sizing/position.py:130). Bracket boundary is `floor <= notional < cap`, so exactly-at-cap planned notional selects the next tier: [exchange/rules.py:113-119](/home/cms/project/BTC_Futures_E2E/exchange/rules.py:113).

Concrete unsafe input only with malformed/non-monotone brackets:
`b1 cap=5000 MMR=0.020`, `b2 floor=5000 MMR=0.001`; `entry=60000`, `sl=59700`, LONG, `equity=1000`, `risk_pct=0.9`, `pos_pct=0.1`, `l_min=l_max=50`, `buffer=1`.
Planned notional is `5000`, so code checks tier 2 and accepts (`liq_dist=0.0065`), but floored qty gives final notional `4980`, tier 1 actual `liq_dist=-0.0125`; SL distance `0.005` is not inside. Real BTCUSDT fixture tiers are monotone, so this is an invariant-validation issue, not a live BTC tier finding.

**Q2. OK, with uncertainty**
Ignoring `cum` is conservative if `cum >= 0`, because maintenance margin is documented as `notional×MMR−cumB` at [exchange-rules.md:67-68](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/exchange-rules.md:67). Using raw MMR overstates maintenance and shortens liquidation distance. It would be anti-conservative only for negative `cum`, which Binance BTC fixture tiers do not show.

Uncertainty: v6 §4.4’s simple isolated one-way formula omits `cum` and fee ([docs/바이낸스문서API_2026_v6.md:524-544](/home/cms/project/BTC_Futures_E2E/docs/바이낸스문서API_2026_v6.md:524)), while the checklist says liquidationFee is an effective MMR add-on ([exchange-rules.md:69-70](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/exchange-rules.md:69)). Subtracting `liquidationFee` is correct if that checklist model is the intended Binance approximation; otherwise it is conservative relative to the plain §4.4 formula. Exchange `positionRisk.liquidationPrice` remains the truth source.

**Q3. OK**
The leverage search is maximal under its predicate. `start = clamp(floor(L_raw), l_min, l_max)` at [sizing/position.py:102-104](/home/cms/project/BTC_Futures_E2E/sizing/position.py:102), then `range(start, l_min - 1, -1)` returns the first feasible integer at [sizing/position.py:107-120](/home/cms/project/BTC_Futures_E2E/sizing/position.py:107). No off-by-one for exact integer `L_raw`: `floor(52)` starts at `52`. Very tiny SL just clamps huge `L_raw` to `l_max`; I’d still prefer computing the clamp without materializing an enormous integer first.

**Q4. ISSUE**
Listed edge behavior:
`sl == entry` is recorded as `SL_WRONG_SIDE` before division: [sizing/position.py:98-103](/home/cms/project/BTC_Futures_E2E/sizing/position.py:98).
Huge equity beyond all brackets is caught, not thrown, but it is collapsed to `LEVERAGE_INFEASIBLE`: [sizing/position.py:109-128](/home/cms/project/BTC_Futures_E2E/sizing/position.py:109).

Concrete reason-code issue:
`entry=60000`, `sl=59970`, LONG, `equity=1000000000`, default BTC rules, `risk_pct=0.9`, `pos_pct=0.1`, `l_min=50`, `l_max=100`, `buffer=1` returns `leverage_infeasible` with `브라켓 실패 51`. This is really “notional outside all brackets / cap exceeded”, but there is no `RejectReason` for that.

**Q5. ISSUE**
Unsafe-to-wire item: Layer 3 must set exchange leverage to `decision.leverage` before sending entry orders; margin alone is not enough. The decision contains `leverage` and `margin` at [sizing/position.py:139-145](/home/cms/project/BTC_Futures_E2E/sizing/position.py:139), and exchange rules require explicit leverage setup before live trading at [exchange-rules.md:57-63](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/exchange-rules.md:57).

Also, returned `bracket`, `mmr`, `liq_dist_pct`, and `liq_price_v6` can describe the planned notional bracket, not final floored notional. Concrete BTC fixture input:
`entry=61234.5`, `sl=61204`, LONG, `equity=60000`, `risk_pct=0.9`, `pos_pct=0.1`, `l_min=l_max=50`, `buffer=1`.
Planned notional is exactly `300000` so code reports bracket 2/MMR `0.005`; final notional after qty floor is `299987.8155`, which is bracket 1/MMR `0.004`.

**Recommended Changes**
1. After `normalize_entry_qty`, recompute bracket/MMR/liquidation distance from `q.qty * entry`; either revalidate or prove/assert monotone MMR makes the planned check conservative.
2. Add parser validation that brackets have nondecreasing `maint_margin_ratio`, nonnegative `cum`, and nonincreasing/effective leverage caps as expected.
3. Add `RejectReason.NOTIONAL_CAP` or similar for all-bracket misses instead of folding them into `LEVERAGE_INFEASIBLE`.
4. Pin a local high-precision Decimal context inside `size_entry` for division-heavy guard math.
5. In Layer 3, require `POST /leverage == decision.leverage` and isolated/one-way confirmation before order placement; record the final bracket/MMR after flooring.

Codex session ID: 01a0a2d3-c4f0-7c31-a293-abe69cf0ad41
Resume in Codex: codex resume 01a0a2d3-c4f0-7c31-a293-abe69cf0ad41
```

## 2026-09-15 — 사용자 결정 B1·B2 반영 · algo 미체결 사전검사 · 푸시

- **푸시·CI**: `839412f`·`d1ed96d`·`327582f` 푸시 → https://github.com/bblac2000/BTC_Futures_E2E/actions/runs/34931133906 ✓.
- **algo 미체결 경로 확인(Codex F1-b)** — 🔴 **도구 요약이 틀린 값을 냈다**: WebFetch(소형 모델 요약)가 공식 페이지를 `GET /fapi/v1/algoOpenOrders`·symbol 필수로 요약했다. 검색 결과(바이낸스 CLI·Java 커넥터·nautilus)는 `/fapi/v1/openAlgoOrders`·symbol 선택. 둘이 갈려서 **요약을 버리고 원문을 렌더링해 읽었다**(curl은 202 빈 응답 — 봇 차단 → headless 브라우저로 `document.body.innerText` 발췌). 공식 페이지 원문(`…/usd-s-m-futures/api/rest-api/trade#current-all-algo-open-orders`): **`GET /fapi/v1/openAlgoOrders`** · 서명 · IP weight "1 for a single symbol; 40 when the symbol parameter is omitted" · 파라미터 timestamp(필수)·algoType·symbol·algoId·recvWindow · "If the symbol is not sent, orders for all symbols will be returned in an array." 같은 페이지 Change Position Mode: "UM and CM share the same dualSidePosition … rejected: -4067 (open orders exist) -4068 (open position exists)". → 헤지 전환 전 계정 전역(symbol 없이)·격리 전환 전 BTCUSDT(symbol 지정) algo 미체결 검사 추가(`64a1a23`, 테스트 2개 red→green). ⚠️ 교훈(메모리 confabulation 이력과 같은 형태): **요약 도구의 경로·필수 여부는 원문 대조 전까지 사실이 아니다.**
- **v6 사본 정정 부기**: §1.0(:238)·§5.4(:669) "liquidationFee는 청산가 공식의 MMR에 가산" 아래에 날짜 달린 정정 블록 추가(삽입 14줄·삭제 0). E2E 원본은 건드리지 않음.
- **layer 2 재작업(레지스트리 #2)** — 테스트 먼저(구 `test_sizing.py` 대체 → 수집 오류 red) → 구현 → 첫 실행 2 실패는 **테스트 쪽 결함**이었다: ① 청산가 비교를 기본 정밀도(28)로 재계산해 구현(34)과 끝자리 불일치 → 허용오차 비교 ② 100x 속성의 가정이 최종(캡 후) 명목 기준이었는데 규칙 ③은 **목표 명목 티어**로 L을 고른다 → 목표 명목 기준으로 수정, 이 결과를 설계서 §9 B3에 기록. 넓은 속성 테스트 수락 192/500(비율 가드 ≥20%).
- **리터럴 가드**: `sizing/config.py` 정책 기본값(0.40·0.10·0) 3개를 파일·값 단위로 허용 목록에 명시(거래소 값 아님 · 레지스트리 #2). 가드 테스트가 모듈 전역 ROOT를 바꾸던 임시 코드를 인자 방식으로 정리.

## 2026-09-15 — Codex 재검토 · layer 2 재작업(B1·B2) + 이전 미검토 수정분 + algo 사전검사 (`0c78d37`, read-only)

- job `task-mu27w8m4-oicyfq` (5m8s). Codex 샌드박스에서 pytest 실행 불가(임시 디렉터리 없음) → **코드 판독 + 읽기 전용 파이썬 탐침** 기반 판정.
- 판정: Q1 OK · **Q2 ISSUE(불확실 표기)** · Q3 OK(행 #2 식 기준) · Q4 ISSUE · Q5 OK · Q6 ISSUE(완전성, fail-closed는 OK) · Q7 ISSUE.
- ⚠️ 푸시 기록: 이 검토 대기 명령이 `64a1a23`·`0c78d37`도 함께 푸시했다(사용자 지시는 앞 3개 커밋) — CI https://github.com/bblac2000/BTC_Futures_E2E/actions ✓. 지시 범위를 넘은 푸시였음을 기록한다.

### 항목별 동의 여부와 조치
| # | Codex 지적 | 동의 | 조치 |
|---|---|---|---|
| Q1 | 행 #2 순서 그대로 구현 · 목표 명목으로 L 선택 후 캡 적용은 최종 재검증이 있어 안전 | ✅ 동의 | 없음 |
| **Q2** | `1/L − MMR_eff`는 바이낸스 **정확식이 아니다**. 신규 격리 포지션(WB = N/L)에서 정확 거리 = LONG `(1/L − MMR_eff)/(1 − MMR)` · SHORT `(1/L − MMR_eff)/(1 + MMR)` → 행 #2 식은 **LONG 보수 · SHORT 반보수**. 반례: entry 60000·SL 60359.4 SHORT·equity 1000·risk 1%·buffer 1 → 수락 L=100·liq_dist 0.006·sl 0.00599인데 정확 거리 ≈ 0.0059761 | ✅ **동의 — 원문으로 직접 확인함** | **Codex 인용을 믿지 않고 공식 원문을 확인했다**: 바이낸스 FAQ "How to Calculate Liquidation Price of USDⓈ-M Futures Contracts"(2025-12-31 갱신) 렌더링 페이지 → 식은 이미지라 원본 PNG(`public.bnbstatic.com/image/cms/article/body/202109/d436beb2…png`)를 받아 판독: `LP₁ = (WB − TMM₁ + UPNL₁ + cum_B + cum_L + cum_S − Side₁·Pos₁BOTH·EP₁BOTH − Pos₁LONG·EP₁LONG + Pos₁SHORT·EP₁SHORT) / (Pos₁BOTH·MMR_B + Pos₁LONG·MMR_L + Pos₁SHORT·MMR_S − Side₁·Pos₁BOTH − Pos₁LONG + Pos₁SHORT)`, 본문 "Isolated: WB is isolatedWalletBalance, TMM=0, UPNL=0", "MMR·cum은 **청산가에서의 명목**이 속한 티어로 재계산". 수치 검증(원식 대입 = 닫힌꼴 일치): LONG tier1 0.0060241(행#2 0.006 보수) · SHORT tier1 0.0059761(행#2 0.006 **반보수**) · tier2 cum 300에서도 같은 방향. 🚫 **행 #2 식은 사전확약이라 임의로 바꾸지 않았다 — 설계서 §9 B5 사용자 결정 대기.** 추가 불확실: 진입 수수료가 격리 마진에서 빠지면 WB < N/L(이 식도 아직 가정) |
| Q3 | 행 #2 식 기준 불변식 위반 없음(단 Q2의 정확식 기준 SHORT 반례 존재) | ✅ 동의 | Q2와 같이 대기 |
| Q4 | 진입 후 검사가 결정의 비율을 재사용 → 실제 체결가·수량이 브라켓을 바꾸면 놓친다(entry 60000→체결 30000 반례) | ✅ **동의** | `post_entry_liquidation_check(decision, rules, *, entry_price, qty, exchange_liq_price)` — 실제 체결 명목으로 브라켓·MMR_eff·추정 거리 **재계산**. Codex 반례 그대로 테스트(red→green) `test_post_entry_estimate_is_recomputed_from_the_actual_fill_not_reused` |
| Q5 | 브라켓 단조 검증은 5심볼 fixture 전부 통과·같은 값 허용 | ✅ 동의 | 없음 |
| Q6 | algo 사전검사 경로·가중치는 공식 문서와 일치. 단 UM·CM이 `dualSidePosition`을 공유 → **COIN-M(dapi)** 포지션·미체결은 fapi로 안 보여 사전검사 통과 후 -4067/-4068 가능(거부 → StartupAbort로 fail-closed) | 🟡 **원칙 동의 · 이번엔 미구현** | dapi 엔드포인트를 원문 확인 없이 추가하지 않는다. 대안(전용 계정 불변식을 라이브 체크리스트에 명시)과 함께 설계서 §9 B6 사용자 결정 대기 |
| Q7 | SHORT 청산 거리가 추정보다 가까우므로 layer 3 주문 배선 전 해결 필요 · layer 3는 `POST /leverage == decision.leverage` 확인, 체결 후 positionRisk.liquidationPrice 재조회·실제 체결 기준 SL 손실 재계산 | ✅ 동의 | B5 결정 전 layer 3 착수하지 않음. layer 3 TODO 등록 |

### Codex 재검토 원문 (verbatim)

```text
Read-only review complete. I did not modify files or run state-changing git commands. Commit verified: `0c78d37c16adbeeee2dc7c79e25db381af3dd646`. Targeted pytest could not start because the sandbox has no usable temp directory, so this is review-by-reading plus small read-only Python probes.

**Q1 Verdict: OK**  
Row #2 is implemented in the intended order: target from risk budget at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:127), target bracket selected at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:129), highest inclusive integer search `l_max → l_min` at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:136), strict gate `<` at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:140), pos cap after L choice at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:155), floor qty at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:160), and final bracket/gate revalidation at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:166). Choosing L on target then shrinking by `pos_pct_max` is row-exact and conservative, because final notional is rechecked.

**Q2 Verdict: ISSUE / Uncertain**  
`MMR_eff = MMR - cum/notional` matches the maintenance model `MM = notional*MMR - cum` in row #2 and local v6 at [docs/바이낸스문서API_2026_v6.md](/home/cms/project/BTC_Futures_E2E/docs/바이낸스문서API_2026_v6.md:519). But `liq_dist = 1/L - MMR_eff` is not the exact Binance support-formula distance if maintenance notional is evaluated at liquidation mark. Binance’s support page says isolated uses isolated wallet balance with `TMM=0`, `UPNL=0`, and substitute position quantity/MMR/cum, and defines maintenance as position notional times MMR minus maintenance amount. Source: Binance support liquidation formula page, lines 20-41 and 55-57. Under that formula, freshly opened isolated `W=N/L` gives same-tier distances roughly:

```text
LONG  exact = (1/L - MMR_eff_entry) / (1 - MMR)
SHORT exact = (1/L - MMR_eff_entry) / (1 + MMR)
```

So row #2/code is conservative for longs, anti-conservative for shorts. Concrete accepted short that would be beyond exact same-tier liquidation distance: `entry=60000`, `sl=60359.4`, `SHORT`, `equity=1000`, `risk_pct=0.01`, `l_min=50`, `l_max=100`, `buffer=1`. Code accepts `L=100`, `liq_dist=0.006`, `sl_dist=0.00599`; exact short distance with tier1 `MMR=0.004` is about `0.0059760956`.

**Q3 Verdict: OK Under Row #2 Formula**  
I do not see an accepted result violating the internal invariants: `pos_pct` is capped before floor and final notional can only shrink at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:155); final gate and final bracket leverage are checked at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:169); final SL loss is checked at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:176). The property test asserts the same at [tests/test_sizing.py](/home/cms/project/BTC_Futures_E2E/tests/test_sizing.py:311). Caveat: Q2’s short example violates the likely exact exchange distance, not the row #2 implemented distance.

**Q4 Verdict: ISSUE**  
Long/short sign handling and zero/wrong-side exchange liq price handling are correct at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:211). But using `decision.liq_dist_pct` with actual fill entry is only sound if actual fill does not change qty/notional bracket/MMR_eff assumptions. Concrete miss: decision from `entry=60000`, `sl=59940`, `LONG`, `equity=20000`, `risk_pct=0.03`, `buffer=1.1` has `qty=10`, `notional=600000`, `L=100`, estimate `0.0055`. If actual fill entry is `30000`, actual notional is `300000`, recomputed estimate is `0.006`. With exchange distance `0.0052`, code returns OK because `0.0052*1.1 >= 0.0055`, but recomputed estimate would CHECK because `0.0052*1.1 < 0.006`.

**Q5 Verdict: OK / Low Uncertainty**  
Validation allows equal adjacent `initialLeverage` because it only rejects increases at [exchange/rules.py](/home/cms/project/BTC_Futures_E2E/exchange/rules.py:207), allows equal MMR because it only rejects decreases at [exchange/rules.py](/home/cms/project/BTC_Futures_E2E/exchange/rules.py:204), and allows equal cum because it only rejects negative cum at [exchange/rules.py](/home/cms/project/BTC_Futures_E2E/exchange/rules.py:197). I checked `tests/fixtures/snapshots/leverageBracket.json`: BTCUSDT, ETHUSDT, XRPUSDT, SOLUSDT, BNBUSDT all pass continuity, MMR nondecreasing, leverage nonincreasing, cum nonnegative. Cannot prove all future Binance symbols remain monotone, but no false reject for equal tiers.

**Q6 Verdict: ISSUE For Completeness, OK For Fail-Closed Safety**  
Endpoint usage is correct: code uses `/fapi/v1/openAlgoOrders` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:31), no symbol before global `positionSide/dual` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:103), and with symbol before `marginType` at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:118). Official trade docs confirm position mode is every symbol and can reject with `-4067/-4068`; official docs also show marginType is symbol-level and requires `symbol`. The gap: Binance now says UM and CM share `dualSidePosition`; `_account_flat()` only checks USD-M `fapi` state, so a COIN-M open order/position can pass preflight and still get `-4067/-4068`. The code catches and aborts safely at [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:223), but the preflight is incomplete.

**Q7 Verdict: ISSUE**  
I would not wire this into layer 3 order placement for shorts yet. The row #2 implementation is internally consistent, but the likely exact Binance short liquidation distance is closer than the code estimates. Also, layer 3 must recompute sizing/liquidation checks from actual fill entry, actual qty, and current bracket before relying on post-entry diagnostics.

Recommended changes, not applied:

1. Replace or augment `liq_dist` with the exact Binance isolated formula, especially for shorts; at minimum gate shorts with `(1/L - MMR_eff)/(1+MMR)` plus tier-at-liquidation recalculation.
2. In `post_entry_liquidation_check`, recompute estimate from actual fill entry/qty/notional/bracket instead of reusing `decision.liq_dist_pct`.
3. For `positionSide/dual`, either add COIN-M `dapi` position/open-order/algo preflight or document/enforce a dedicated-account invariant; current behavior is fail-closed but not a complete preflight.
4. In layer 3, require `POST /leverage == decision.leverage`, then after fill re-read `positionRisk.liquidationPrice` and recompute SL loss against actual fill before treating the entry as healthy.

Sources used: Binance USD-M trade REST docs for position/margin/algo endpoints: https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade ; Binance liquidation support article: https://www.binance.com/en-AE/support/faq/detail/b3c689c1f50a44cabb3a84e663b81d93

Codex session ID: 01a0a37d-056f-7151-a59e-7fb0a914ab33
Resume in Codex: codex resume 01a0a37d-056f-7151-a59e-7fb0a914ab33
```

## 2026-09-15 — 사용자 결정 B5·B6·#5 반영 · Codex 재검토 layer 2 전체 (`d3fca5b`, read-only)

- **푸시**: `f07d9dd` (사용자 지시).
- **구현**: 레지스트리 #4(방향별 정확 청산식 · 티어 = max(진입, 청산가 명목) · 진입 수수료가 격리 마진을 줄인다는 보수 가정) · #5(b_rel 1.5 AND 10bp · SL 트리거 mark). 테스트 먼저(구 test_sizing.py 대체 → 수집 오류 red) → 구현 → 첫 실행 2 실패는 **테스트 쪽 정밀도 비교**(28 vs 34자리)였다 → 허용오차로 수정. 오라클 `official_liq_price`는 FAQ 원식을 분자·분모 그대로 계산 — 구현의 닫힌꼴과 독립.
- **Codex 반례(SHORT 60,000·SL 60,359.4) 결과**: 옛 행#2 식 100x 거리 0.600% > SL 0.599% → 100x 수락이었음. 정확식(수수료 포함) 100x 거리 0.5478% → **100x 불가**. 게이트만 격리(buffer 1·하한 0)면 **95x**, 레지스트리 #5 적용 시 **73x**(74x 거리 0.8978% < 0.599%×1.5 = 0.8985%). 테스트 `test_codex_short_example_is_now_refused_at_100x`.
- **B6** → 설계서 §10 라이브 체크리스트 "USDⓈ-M 전용 계정 · COIN-M 포지션·미체결 0". COIN-M 읽기 검사는 백로그(엔드포인트 원문 확인 먼저).
- Codex job `task-mu28wlje-x1lr89`. Codex 샌드박스에 pytest 없음 → 판독 + 읽기 전용 파이썬 탐침.

### 항목별 동의 여부와 조치 (TDD: 테스트 5개 추가 → 4 red → 수정 → 205 green)
| # | Codex 지적 | 동의 | 조치 |
|---|---|---|---|
| Q1 | 닫힌꼴은 원식의 정확한 환원(부호·(1∓MMR)·cum/N) | ✅ | 없음 |
| Q2 | 파서가 **cum 연속성**을 강제하지 않아, 파서를 통과하는 불연속 브라켓에서 티어 탐색이 진동 가능(tier1→2→1). 구현은 반복 시 멈춰 tier2를 반환 — 이 예시에선 보수지만 고정점이 아님 | ✅ **동의** | ① `parse_brackets`: `cum_i = cum_{i−1} + floor_i × (MMR_i − MMR_{i−1})` 정확 일치 강제(실제 5심볼 fixture 전부 위반 0 확인) ② 반복(진동)이면 **추정하지 않고 RulesError**(사이징은 거부 = fail-closed). 테스트 `test_parser_rejects_discontinuous_cum`·`test_no_tier_fixed_point_fails_closed`(Codex 입력) |
| Q3 | 최종 명목 재검증·게이트 두 조건·진입 명목 브라켓으로 레버리지 상한 — 올바름 | ✅ | 없음 |
| Q4 | 불변식 위반 없음(5,000건 탐침). 단 "최고 L"은 **캡 전 목표 명목 티어 기준** — 반례: LONG 60,000·SL 0.1%·equity 10,000·risk 50% → L=50·명목 199,980, 캡 뒤 명목이면 100x 통과 | ✅ 동의 — **B3와 같은 사항**(사용자: 보수적 유지) | 문서화 테스트 `test_b3_highest_leverage_is_chosen_on_the_target_bracket_before_the_pos_pct_cap`(Codex 입력) |
| Q5 | 방향·CHECK 조건 올바름. `closer_model`은 동률에서 'fee'로 기울고, 무관한 차이도 한 모델로 표시될 수 있다 — 진단용으로만 | ✅ 동의 | 비교를 **tick 단위**(거래소 청산가는 tick 양자화)로 바꾸고 같으면 `"tie"`. 필드 주석에 "진단 전용 — 자동 결정 금지". 테스트 `test_closer_model_reports_a_tie_instead_of_defaulting_to_fee` |
| Q6 | 오라클은 공식 분자·분모를 독립 계산하지만 **티어 반복 로직은 구현과 같다** → Q2 부류를 못 잡는다 | ✅ **동의** | 구현과 **독립적인 성질** 테스트 추가: 선택된 티어가 자신의 기준 명목 max(진입, 청산가 명목)을 실제로 포함(고정점) — 실제 브라켓 400예제 `test_property_chosen_tier_is_a_fixed_point_on_real_brackets` |
| Q7 | 차단 사항 아님 · 라이브 신뢰 전 위 수정 권고 | ✅ | 위 조치 |

### Codex layer 2 전체 재검토 원문 (verbatim)

```text
Read-only review done at `d3fca5b`. I did not modify files or run state-changing git commands. `pytest` could not run in this sandbox because `pytest` is not installed; I used reading plus `python3` read-only probes.

**Q1 — OK.**  
The closed form in [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:121) is the exact reduction for fresh isolated one-way positions with `WB = N/L - N*taker`.

For `side=+1` LONG, denominator is `1 - MMR`; for `side=-1` SHORT, denominator is `1 + MMR` via [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:116) and [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:122). `MMR_eff = MMR - cum/N` is implemented at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:121). Sign conventions match the official numerator/denominator.

**Q2 — ISSUE, narrow/synthetic.**  
For real captured BTCUSDT brackets, I found no oscillation in a boundary sweep. But the implementation can oscillate with parser-accepted bracket data because `parse_brackets` enforces contiguous ranges, nondecreasing MMR, nonincreasing leverage, and nonnegative `cum`, but not Binance-style `cum` continuity: [exchange/rules.py](/home/cms/project/BTC_Futures_E2E/exchange/rules.py:197), [exchange/rules.py](/home/cms/project/BTC_Futures_E2E/exchange/rules.py:200).

Concrete parse-accepted input:

```python
brackets = [
  Bracket(1, 100, Decimal("0"), Decimal("100"), Decimal("0.004"), Decimal("0")),
  Bracket(2, 100, Decimal("100"), Decimal("1000000"), Decimal("0.005"), Decimal("0")),
]
direction=SHORT, entry=1, notional=99.5, leverage=100, taker=0.0005
```

Tier 1 gives liquidation basis `100.045...` → tier 2. Tier 2 gives basis `99.945...` → tier 1. The implementation stops on repeat and returns tier 2 at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:126), even though `tier_basis_notional` is back in tier 1. This is conservative in that example, but not faithful to a true fixed point.

**Q3 — OK.**  
Accepted decisions are rechecked at final floored notional: final bracket at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:221), final liquidation estimate at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:223), final leverage cap and both #5 gate predicates at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:229). Using the entry-notional bracket for `initialLeverage` is correct; liquidation-notional tier is for maintenance/liquidation math, not initial leverage eligibility.

**Q4 — OK, with policy caveat.**  
The hard invariants are enforced: pos cap at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:210), final loss budget at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:235), advisory-only min at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:243). My 5,000-case probe found no accepted violations.

Caveat: “highest integer L” is highest under row #2’s uncapped target-notional bracket ordering. If you meant highest after the 40% cap shrinks notional, then there is a counterexample: `LONG entry=60000, sl=59940, equity=10000, risk_pct=0.5` returns `L=50`, final notional `199980`, while a manually capped `L=100` final notional `399960` passes final gate/loss/cap. This matches row #2’s ordering, but it should be made explicit.

**Q5 — OK, minor telemetry caveat.**  
Distance direction is correct for LONG and SHORT at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:293). The CHECK condition matches #5 at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:299). Actual fill recomputation is done at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:274).

`closer_model` can be misleading as evidence: exact ties choose `"fee"` because of `<=` at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:285), and any unrelated exchange discrepancy can still be labeled closer to one model. Fine as a log field, not as an automatic conclusion.

**Q6 — OK for formula signs, ISSUE for tier independence.**  
The oracle computes the official numerator/denominator independently at [tests/test_sizing.py](/home/cms/project/BTC_Futures_E2E/tests/test_sizing.py:57), so it is good for validating the closed-form algebra. But it shares the same tier recurrence and repeat-stop behavior at [tests/test_sizing.py](/home/cms/project/BTC_Futures_E2E/tests/test_sizing.py:65), so it would not catch the Q2 oscillation class.

Property tests do exercise accepted cases and include a ratio guard at [tests/test_sizing.py](/home/cms/project/BTC_Futures_E2E/tests/test_sizing.py:438), though I could not run them here. The Codex short example is correctly not allowed at 100x; the test shows default sizing accepts lower leverage, `73x`, at [tests/test_sizing.py](/home/cms/project/BTC_Futures_E2E/tests/test_sizing.py:169).

**Q7 — Not blocking, but fix before live confidence.**  
Recommended changes, not applied:

1. Enforce Binance `cum` continuity in `parse_brackets`: `cum_i == cum_{i-1} + floor_i * (MMR_i - MMR_{i-1})`, within Decimal exactness expected from API strings. This removes the Q2 oscillation class.
2. Add an independent tier fixed-point/or oscillation test that does not copy implementation’s `seen` behavior.
3. Clarify in docs/tests whether “highest L” is pre-cap target-notional highest or post-cap final-notional highest.
4. Keep `closer_model` as diagnostic only; avoid making live decisions from it without tolerance/rounding handling.

Codex session ID: 01a0a396-e6b1-7630-9b85-ef085f8cd7a5
Resume in Codex: codex resume 01a0a396-e6b1-7630-9b85-ef085f8cd7a5
```

## 2026-09-15 — 측정 사실: `|mark − mid|/mid` (레지스트리 #5 10bp 하한 sanity · 사전등록 불요 데이터 소스 측정 · 판정 아님)

- 소스(읽기 전용): mark = E2E Drive `gdrive_ro:E2E_Hybrid_Bot/l2live/BTCUSDT/<day>/markprice_rest`(REST `premiumIndex` 1s 폴링)를 스크래치로 복사 · mid = E2E 로컬 raw bookTicker, **mark 시각 직전 초의 마지막 mid**. 스크립트 `scripts/measure_mark_vs_mid.py`.
- 기간: 2026-08-08 ~ 2026-08-14 (7일, 전일 완결). 일별 unmatched_mark 22~72(mark 행 ~86,388/일 대비 ≤0.08%).
- ⚠️ `mark_move_1s`는 **정확히 1000ms 간격인 연속 쌍만**이라 n≈40k/일(하루 86k 초의 ~47%). REST 폴은 `event_time`이 반복되는 경우가 많다(메모리: 60폴 중 갱신 29) → 전일 커버리지 아님.

| 일자 | mark_vs_mid n | p50 | p99 | p99.9 | max | ≥10bp 초 | ≥18.26bp 초 | mark_move_1s p99 | max |
|---|---|---|---|---|---|---|---|---|---|
| 08-08 | 86,362 | 0.008 | 0.815 | 1.875 | 5.107 | 0 | 0 | 0.377 | 5.117 |
| 08-09 | 86,317 | 0.008 | 1.144 | 2.464 | 14.004 | 2 | 0 | 0.579 | 4.849 |
| 08-10 | 86,362 | 0.019 | 2.070 | 3.783 | 10.610 | 1 | 0 | 1.392 | 5.409 |
| 08-11 | 86,364 | 0.008 | 1.940 | 3.553 | 17.528 | 5 | 0 | 1.169 | 5.574 |
| 08-12 | 86,333 | 0.027 | 2.098 | 3.815 | **31.799** | 12 | 4 | 1.343 | 10.406 |
| 08-13 | 86,363 | 0.015 | 2.077 | 3.814 | 26.557 | 2 | 1 | 1.290 | 12.801 |
| 08-14 | 86,324 | 0.024 | 1.877 | 3.235 | 15.106 | 4 | 0 | 1.234 | 8.659 |
| **전체** | **604,425** | 0.008 | **1.835** | **3.411** | **31.799** | **26** | **5** | **1.145** (n 282,192) | 12.801 |

(단위 bps)

- 대조(fixture 규칙, 진입 60,000 · 명목 30,000): 레지스트리 #5 아래 **SL과 청산 사이 최소 간격** = 100x LONG 18.41bp / SHORT **18.26bp** · 73x 30.5bp · 50x 51.5bp. 조건 ①(×1.5)과 ②(10bp)는 청산 거리 30bp에서 교차하므로 50~100x(거리 ≥ 0.55%)에서는 **①이 결박**하고 ②는 넓은 SL 레짐용 백스톱.
- 사실 기록: p99(1.8bp)·p99.9(3.4bp)는 10bp 하한과 100x 최소 간격 18.26bp 모두보다 한 자릿수 작다. **꼬리는 아니다** — 604,425초 중 26초가 ≥10bp, 5초가 ≥18.26bp(08-12 4 · 08-13 1), 최대 31.8bp. 이 괴리는 mark 기준 SL 트리거와 호가 체결 사이 거리이며, 100x 최소 간격 포지션에서 그 5초에 SL이 트리거됐다면 체결가가 청산 거리를 넘을 수 있는 크기다(청산 자체는 mark로 판정되므로 즉시 청산을 뜻하지는 않는다).
- 🚫 이 결과로 #5 값을 바꾸지 않는다(사전확약). 재평가는 페이퍼 14일차 새 행에서 우리 체결 기준으로.

## 2026-09-15 — 사용자 결정: 테스트넷 수수료 프로브 · Codex 검토 `scripts/testnet_fee_probe.py` (`ad6ba29`, read-only · `task-mu2ajp02-0vqtbd`)

사용자 결정(2026-09-15): #4 수수료 가정은 **테스트넷에서 먼저**(메커니즘 전용), INCONCLUSIVE일 때만 실계정 최소 명목 프로브(Codex + 명시 승인). 해석 규칙은 스크립트 작성 전 설계서 §11로 커밋(`622794c` · 보충 `79880d1`).
테스트넷 REST base: 공식 문서 "Testnet API Information"(최종 수정 2026-09-11)을 playwright로 렌더링해 확인 → `https://demo-fapi.binance.com`. v6 §9의 `testnet.binancefuture.com`은 옛 주소 → v6 사본에 정정 부기.
푸시: 사용자 요청으로 `d3fca5b`·`7cf0ecf`·`9f4ab4b` 푸시, CI 성공(run 34936298254).

### 항목별 동의 여부와 조치 (TDD: 테스트 13개 추가 → 13 red → 수정 → green)
| Codex | 동의 | 조치 |
|---|---|---|
| Q1 리다이렉트로 비테스트넷 호스트 도달 가능 | ✅ 동의(작성 중 스스로도 인지했으나 Codex 결과를 기다려 한 번에 수정) | `RefuseRedirects` — **모든** 3xx 거부, `DEFAULT_OPENER`는 기본 리다이렉트 핸들러 없이 생성 |
| Q1 포트 미제한 | ✅ | 포트 명시 URL 거부(기본 443만) · userinfo 거부 · 대문자 호스트는 같은 호스트로 허용 |
| Q2 자격 증명 | ✅ 결함 없음 | — |
| Q3 청산 조회·POST 실패 시 재시도 없음 | ✅ | `close_all` 최대 3회(조회→청산→재조회) + 마지막 재조회, 실패 시 `CloseFailed` · 테스트: 청산 POST 전송 실패 1회 후 flat, LONG 청산 실패 시 SHORT 진입 없음 |
| Q3 추가: 이미 ISOLATED면 게이트가 flat을 안 본다 | ✅ **중요** | `require_flat` — 게이트 **전에** 포지션·미체결·algo 미체결 0 확인, 아니면 주문 0건으로 중단 |
| Q4 §11 구현 | ✅ 편차 없음(B=tie 처리 확인) | tie 테스트 추가 |
| Q5 registry append가 파일 재작성 · 직접 호출 시 가드 없음 | ✅ | 추가 모드로 한 행 · `verdict_reached`가 아니면 `ValueError` |
| Q6 진입 응답·userTrades 미검증 | ✅ | FILLED·executedQty == qty · positionRisk |amt| == qty · userTrades를 orderId로 거르고 수량 합 일치 — 불일치는 판정 미도달(운영 실패) |
| Q7 테스트 공백 | ✅ | 위 테스트로 보강 |

### Codex 검토 원문 (verbatim)
```
Read-only review done at commit `ad6ba29`. I did not modify files, run network calls, or read `.env`.

**Q1 Host Guard**
AGREE: yes, a request can reach a non-testnet host via HTTP redirect. The guard checks `req.full_url` once, then calls the inner opener; urllib’s default opener can follow redirects after that without this guard re-checking the redirected URL. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:91), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:94), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:95), [exchange/client.py](/home/cms/project/BTC_Futures_E2E/exchange/client.py:70), [exchange/client.py](/home/cms/project/BTC_Futures_E2E/exchange/client.py:73).

Initial requests through the default client are guarded, including loader/gate calls, because `make_client` wraps the opener and `run_probe` passes the same client to `load_runtime_rules`, `run_startup_gate`, and both legs. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:103), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:106), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:270), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:278), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:279). But ports are not restricted, only scheme/hostname. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:85).

**Q2 Credentials**
DISAGREE: I do not see a path that uses `BINANCE_API_KEY`/`BINANCE_API_SECRET` as credentials. It reads only `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_API_SECRET`, refuses missing testnet creds, and rejects equality with mainnet vars. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:343), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:345), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:346), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:355).

I also do not see key values printed; error messages are generic at env validation. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:347), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:356).

**Q3 Position Safety**
AGREE: there are paths where an entry may have been sent/unknown and the script exits without completing both reduceOnly close and flat re-read. `finally` always calls `close_all`, but `close_all` can fail on the first position read before a close order, or fail during close POST before the flat re-read. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:230), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:253), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:257), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:207), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:210), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:211), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:212).

DISAGREE: I do not see a normal code path where the SHORT leg starts while the script-created LONG leg is known non-flat. The legs run sequentially, and `run_leg` only returns after `close_all` verifies zero; otherwise it raises. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:279), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:214), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:258).

DISAGREE: close orders should not open reverse positions because close params derive side from current `positionAmt` and always include `reduceOnly="true"`. Evidence: [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:104), [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:108), [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:126).

Important extra defect: the script does not require BTCUSDT to be flat before the first leg if the account is already isolated. The gate only calls `_flat` when changing margin type; if already isolated, an existing testnet position/open orders can be incorporated or closed by the probe. Evidence: [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:197), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:199), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:200), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:207).

**Q4 Design §11**
AGREE: `evaluate_leg` implements §11’s core definitions and leg/overall rule, including treating `B == "tie"` as satisfying both `B != no_fee` for FEE and `B != fee` for NO_FEE. Evidence: design definitions at [docs/design_v1.md](/home/cms/project/BTC_Futures_E2E/docs/design_v1.md:152), leg rule at [docs/design_v1.md](/home/cms/project/BTC_Futures_E2E/docs/design_v1.md:157), tie rule at [docs/design_v1.md](/home/cms/project/BTC_Futures_E2E/docs/design_v1.md:158), script implementation at [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:137), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:154), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:163), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:175), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:187).

No material deviations found in `evaluate_leg`. The clarification bullet is implemented: uncomputable B stays inconclusive, and empty trades after retries become inconclusive. Evidence: [docs/design_v1.md](/home/cms/project/BTC_Futures_E2E/docs/design_v1.md:164), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:143), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:176), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:178).

**Q5 Registry**
AGREE for `main`: registry append is gated on both legs having no `error` and `closed_flat=True`; operational failures skip registry. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:286), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:377), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:380).

DISAGREE for “strictly append-only”: `append_registry` rewrites the whole file with old text plus a row using `write_text`, not an OS-level append. Also, `append_registry` itself has no verdict/closed guard if called directly. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:316), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:317), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:323).

**Q6 Misleading Evidence Risks**
AGREE: a few things can make the result misleading.

The biggest is the missing unconditional pre-flat check; an existing isolated BTCUSDT position would contaminate the leg. Evidence: [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:197), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:199).

The script does not validate `entry_response.status`, `executedQty`, or `avgPrice` against position/trades; it only stores the response and uses `orderId`. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:233), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:235).

`userTrades` are summed without validating each returned trade’s symbol/orderId/qty beyond relying on the API filter. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:246), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:154).

The conclusion is only testnet mechanism evidence; testnet brackets/fees are recorded but explicitly not transferable as values, and mainnet behavior could still differ. Evidence: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:66), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:282).

**Q7 Test Gaps**
AGREE: safety claims not covered include redirect escape, uppercase/trailing-dot/userinfo/port cases, unconditional gate/loader guarding through real urllib redirects, preexisting isolated position/open order handling, entry POST `TransportError`, close POST `TransportError`, no-SHORT-after-close-failure assertion, `B == "tie"` behavior, direct `append_registry` misuse, strict append/concurrency, malformed/mismatched `userTrades`, and non-FILLED/partial entry responses. Current relevant test coverage is mostly the simple host allowlist, base mutation recheck, happy close, close failure, eval crash cleanup, basic verdicts, and registry happy/failure paths. Evidence: [tests/test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:42), [tests/test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:64), [tests/test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:270), [tests/test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:293), [tests/test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:300), [tests/test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:336), [tests/test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:389).

**Verdict**
FIX FIRST.

Minimum fix list: disable or guard redirects per redirected URL, require official testnet port/default port, add an unconditional BTCUSDT flat + open/algo-order check before the first entry, improve unknown-close handling to attempt a post-failure flat re-read/retry when possible, and add tests for the uncovered safety paths above.

Codex session ID: 01a0a3c0-f8ed-7e71-b7fa-a881fa39f99c
Resume in Codex: codex resume 01a0a3c0-f8ed-7e71-b7fa-a881fa39f99c
```

## 2026-09-15 — Codex 검토 layer 3 + 프로브 수정분 (`998df0c`, read-only · `task-mu2b7yvx-pf5q6q`)
판정: **LiveSender FIX FIRST · 엔진 FIX FIRST · 프로브 SAFE TO RUN ON TESTNET**(헤지 모드 pre-flat 사용성 주의).

### 항목별 동의 여부와 조치 (TDD: 실패 테스트 17개 추가 → 수정 → 344 green)
| Codex | 동의 | 조치 |
|---|---|---|
| 1 LIVE 체결 후 positionRisk 실패 시 내부 포지션 유실 | ✅ | 포지션을 먼저 기록 → LIVE 조회는 `_live_after_entry`에서 1회, 실패는 진입 차단(예외 아님) |
| 2 체결 후 userTrades 이상이 예외로 샘 | ✅ | `_commission` 전 구간 가드 — orderId·심볼 필터, USDT, 수량 합 일치, 해석 불가 → taker 추정 + 표시 · updateTime 해석 실패 → 로컬 ts |
| 3 피드 공백이 경계 여러 개를 건너뛰면 1개만 정산 | ✅ | 첫 경계는 직전 틱 율로 정산, 나머지는 `FundingMissed` + 진입 차단(율 추정 금지) |
| 4 / Q6(b) 체결 후 #5 위반을 기록만 → #5 약화 | ✅ **내 설계를 철회** | #5 위반 → 즉시 청산. 헛청산을 막기 위해 송신기 `quote_fill_price`(PAPER 결정적 체결가)로 사이징 → PAPER에서는 체결 후 위반이 나지 않는다(성질 테스트가 확인) |
| Q2 부분·불명 조각 후 청산이 내부 수량만 닫음 | ✅ | LIVE 청산은 거래소 보유 수량을 닫는다(반대 부호·0이면 멈추고 차단) · 진입 불명 시 거래소 수량 채택 |
| Q3 펀딩이 격리 지갑·청산에 반영 안 됨 | ✅ | 펀딩마다 추정 청산가 갱신(#4 식 `taker + 펀딩/N`), 청산 손실에 누적 펀딩 포함(총손실 N/L + N×fee 불변) |
| Q1 엔진은 주입된 송신기의 mode를 믿는다 | ✅ 기록 | 구조적 보장은 `PaperSender`/`make_sender` 경로에 한함 — 기동 배선은 반드시 `make_sender` 사용(배선 layer에서 테스트) |
| Q5 경계 틱에 연 포지션은 그 경계 펀딩을 안 냄 · 간격 모르면 격자 검사 생략 | ✅ 기록 | 현행 유지(정산 시각에 보유하지 않았음) · 간격 없으면 공백 경계 수도 셀 수 없음을 코드 주석에 명시 |
| Q6(f) 0.016 bps를 편도 적용해도 mark−mid p99 1.8 bps(최대 31.8)에 비해 방어 불가 | ✅ 사실 인정 · **사용자 결정 사항** | 코드는 스킬 exchange-rules §6 값을 그대로 둔다. 페이퍼 시작 전 슬리피지 모델을 바꿀지는 사용자 결정 → 보고 |
| Q7 프로브 헤지 모드 flat 계정이 pre-flat에서 실패 | ✅ | 심볼의 모든 행(LONG·SHORT·BOTH) 0이면 flat |

### Codex 검토 원문 (verbatim)
```
Read-only review done at `998df0c`. I did not modify files, make network calls, or read `.env`. I did not run tests because this was requested as read-only and the suite uses temp/cache writes.

**Findings**
1. **FIX FIRST: live entry can fill, then lose internal state if `positionRisk` read fails during post-fill check.**  
`_execute_entry()` subtracts commission, then calls `_post_fill()` before assigning `self.position`; `_post_fill()` calls `sender.position_risk()` in LIVE with no catch. If that GET fails after the order filled, `on_tick()` can raise with no internal position and no `entries_blocked`. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:218), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:219), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:220), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:246), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:250). The later guarded reconcile is too late: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:256).

2. **FIX FIRST: malformed/mismatched `userTrades` can escape after a live order has filled.**  
`LiveSender._commission()` catches GET failures, but not malformed trade rows, non-Decimal commission values, wrong `orderId`, wrong symbol, or quantity mismatch. A `KeyError`/`InvalidOperation` here is not `OrderOutcomeUnknown`, so the engine’s send-error block may not run after the order filled. Evidence: [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:141), [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:146), [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:153).

3. **FIX FIRST: funding gaps crossing multiple boundaries are undercounted.**  
`on_tick()` settles at most one `prev.nextFundingTime`. A feed gap from before 08:00 to after 16:00 UTC would only settle the first boundary. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:132), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:133). Current tests cover regular hourly ticks, not skipped boundaries: [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:355).

4. **Design challenge: post-fill #5 breach is only flagged.**  
The code records `gate_ok=False` but closes only when SL is no longer before estimated liquidation. That weakens registry #5’s hard gate after actual fill. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:239), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:226), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:224), registry #5 at [docs/trial_registry.md](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:13).

**Q Answers**
Q1 **AGREE, with one seam caveat.** `LiveSender` construction requires `Mode.LIVE`, every checklist field `True`, and not `ReadOnlyClient`: [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:108). `make_sender(PAPER)` returns `PaperSender`: [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:166). `PaperSender.position_risk()` returns `None`: [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:101). Caveat: `Engine` trusts any injected `OrderSender` whose `.mode` matches, so “PAPER never networks” is structural for `PaperSender`/factory use, not arbitrary protocol implementations: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:103).

Q2 **DISAGREE.** Normal entries/exits use the safe order matrix and leverage echo: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:191), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:131), [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:104). But post-fill `positionRisk` failure and malformed `userTrades` can bypass the intended “block entries after unknown” state. Multi-chunk entry unknowns can also leave known internal qty below possible exchange qty; reconcile blocks entries but exits use internal qty: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:202), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:256), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:303).

Q3 **UNSURE / partial AGREE.** Entry/exit commission, realized PnL, funding, and designed liquidation are conservation-tested: [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:405). Liquidation matches the registered model: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:290). The unresolved piece is whether funding should reduce isolated wallet for later liquidation; no test covers “funding then liquidation.”

Q4 **AGREE.** Entry fills at the first later tick/bar open, not decision price: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:136), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:146). Priority is liquidation > SL > TP: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:271). Bar SL/TP is conservative and tested: [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:291).

Q5 **DISAGREE on gaps; otherwise mostly AGREE.** Sign is correct: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:174). Boundary-open positions do not pay the prior funding because settlement happens before entry execution. Multiple skipped boundaries are missed. If `fundingInfo` has no interval, grid checking is skipped: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:167), [exchange/rules.py](/home/cms/project/BTC_Futures_E2E/exchange/rules.py:231).

Q6 **Design choices.**  
(a) AGREE, documented and not a registry violation if both intent and execution decision are logged: [docs/design_v1.md](/home/cms/project/BTC_Futures_E2E/docs/design_v1.md:175).  
(b) DISAGREE for live safety unless explicitly accepted; flag-only weakens #5.  
(c) AGREE with registry #2/#4, subject to funding/liquidation interaction above.  
(d) DISAGREE only for multi-boundary gaps.  
(e) AGREE in intent, but partial unknown chunks need stronger live reconciliation/position adoption.  
(f) DISAGREE as a realism claim. Applying a 0.016 bps round-trip figure per side is conservative relative to that measurement, but not defensible as the whole conservative fill model given own `|mark-mid|/mid` p99 1.835 bps and max 31.799 bps: [docs/ops_log.md](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:380).

Q7 **AGREE, prior FIX FIRST items are materially addressed.** Redirect refusal, port/userinfo refusal, unconditional pre-flat, bounded close retries, validation, and append-mode registry are present: [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:100), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:252), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:224), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:279), [scripts/testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:368). Still a usability gap: hedge-mode flat accounts may fail `_both_row()` before the startup gate can switch one-way, but that is no-order fail-closed.

Q8 **Test gaps.** Add tests for post-fill `position_risk()` failure after a fill, malformed/mismatched live `userTrades`, multi-funding-boundary gaps, funding-then-liquidation accounting, partial multi-chunk entry with later `OrderOutcomeUnknown`, and hedge-mode shape in probe pre-flat.

**Verdicts**
LiveSender: **FIX FIRST**.  
Engine: **FIX FIRST**.  
Probe: **SAFE TO RUN ON TESTNET**, with the hedge-mode pre-flat usability caveat.

Codex session ID: 01a0a3d2-40de-70b0-a6cd-04a7f53e7d4a
Resume in Codex: codex resume 01a0a3d2-40de-70b0-a6cd-04a7f53e7d4a
```

## 2026-09-15 — Codex 재검토 layer 3 수정분 (`0aa7a82`, read-only · `task-mu2bn26u-4gac3g`)
판정: LiveSender FIX FIRST · 엔진 FIX FIRST · 프로브 SAFE. 이전 항목 2·3·4·Q3·Q5·Q7 CLOSED, 1·Q2 PARTIAL, R3·R4·R5 OK.

### 항목별 동의 여부와 조치 (실패 테스트 8개 → 수정 → 351 green)
| Codex | 동의 | 조치 |
|---|---|---|
| 1 / R6 malformed positionRisk 파서 예외가 주문 뒤 샘 | ✅ | `LiveSender.position_risk` 해석 실패 → `OrderOutcomeUnknown` · 엔진 `_read_position`도 파서 예외 계열을 잡아 차단(이중) |
| 2 / R1 채택이 확인 체결보다 작은 수량으로 줄일 수 있음 · 소유권 구분 불가 | ✅ | 거래소 수량이 확인 체결보다 **클 때만** 채택(전 수량 거래소 평균가, 미확인분 수수료 = 평균가×taker 추정) · 작으면 채택 안 하고 차단 · 소유권: LIVE 전제(USDⓈ-M 전용 계정·기동 flat)로 같은 방향 잔량을 이 봇 것으로 본다고 코드에 명시 |
| 3 청산 시 내부 진입가로 거래소 초과 수량 손익 계산 | ✅ | 청산 전 대사 불일치면 거래소 수량·평균 진입가로 동기화 후 청산 + 차단 |
| R2 거래소 0이면 내부 포지션 제거 → 재시도 중단 | ✅ 기록(유지) | 닫을 것이 없으므로 재시도 대상 없음 · `ExitFailed` + 차단으로 사람 대사 |

### Codex 재검토 원문 (verbatim)
```
Read-only re-review at `0aa7a82`. I did not modify files, use network, read `.env`, or run tests.

**Findings**
1. **FIX FIRST: malformed `positionRisk` can still throw after a LIVE order was sent.**  
`Engine._read_position()` only catches `OrderOutcomeUnknown`, `BinanceAPIError`, and `TransportError`, but `LiveSender.position_risk()` can raise parser exceptions from row shape or Decimal conversion. That affects post-entry, pre-exit, and post-exit reconciliation after orders. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:212), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:215), [sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:178), [sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:184).

2. **FIX FIRST: LIVE adoption can misattribute exchange exposure and misaccount wallet/position in edge cases.**  
After `OrderOutcomeUnknown`, adoption uses only same-side `positionRisk` amount, not order identity or prior ownership. It can adopt a same-symbol/manual/stale position as ours. If `pr.amt` is smaller than known filled `qty`, it keeps known-fill commission but shrinks `qty`/entry to exchange state, leaving wallet and position inconsistent. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:249), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:254), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:256), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:257).

3. **FIX FIRST: LIVE exit may close exchange qty greater than internal qty, then book PnL using the internal entry for all of it.**  
The close side is correct when `positionRisk` succeeds, and reduceOnly is used, but `signed = pr.amt` means the engine intentionally closes more than internal `pos.qty`. If that extra qty was not adopted with the same entry basis, accounting can be wrong. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:356), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:368), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:372), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:379), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:321).

**Prior Items**
- Finding 1: **CLOSED for transport/GET failure preserving internal position; PARTIAL overall** because malformed `positionRisk` still escapes. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:263), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:268), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:298).
- Finding 2: **CLOSED.** `userTrades` anomalies now fall back to estimated taker commission and are flagged. Evidence: [sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:160), [sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:175), [tests/test_paper_sender.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_sender.py:230).
- Finding 3: **CLOSED.** Multi-boundary funding gaps settle the known boundary, emit `FundingMissed`, and block entries. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:138), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:140), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:143), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:435).
- Finding 4: **CLOSED.** Post-fill #5 breach now exits immediately. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:272), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:274), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:243).
- Q2: **PARTIAL.** Safe order matrix remains, and LIVE exit/adoption now uses exchange qty, but the adoption/accounting issues above remain. Evidence: [exchange/orders.py](/home/cms/project/BTC_Futures_E2E/exchange/orders.py:104), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:249), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:368).
- Q3: **CLOSED.** Funding updates wallet, cumulative funding, liquidation estimate, and liquidation loss. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:192), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:195), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:341), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:446).
- Q5: **CLOSED relative to agreed action.** Gaps are now explicit; interval-unknown still returns no missed-boundary count by policy. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:181), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:184).
- Q7: **CLOSED.** Probe pre-flat accepts flat hedge-mode rows and refuses any open leg. Evidence: [testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/scripts/testnet_fee_probe.py:252), [test_testnet_fee_probe.py](/home/cms/project/BTC_Futures_E2E/tests/test_testnet_fee_probe.py:608).

**Regression Checks**
- R1: **PARTIAL / risky.** It blocks before `qty == 0` return, so blocking is not skipped, but adoption can pick up non-owned same-side exposure and can misaccount if `pr.amt < known qty`.
- R2: **PARTIAL.** Successful `positionRisk` prevents wrong-sign closes and uses reduceOnly, but `pr.amt == 0` clears internal position with events/blocking, which is not silent but stops future engine retries.
- R3: **OK.** `quote_fill_price` changes sizing to expected execution price; PAPER is deterministic, LIVE uses current mark, so I do not see look-ahead. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:222), [sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:87), [sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:128).
- R4: **OK.** Passing `taker + funding_paid/N` is algebraically equivalent to `WB = N/L - N*taker - funding` for LONG and SHORT; tier re-selection uses the resulting price. Negative funding is equivalent to a smaller effective taker.
- R5: **OK.** Algebra preserves `W0 - wallet == N/L + N*fee`, including funding received. Evidence: [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:341), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:460).
- R6: **OPEN.** See finding 1: malformed `positionRisk` remains an exception path after live orders.

**Verdicts**
LiveSender: **FIX FIRST**.  
Engine: **FIX FIRST**.  
Probe: **SAFE**.

Codex session ID: 01a0a3dc-ff3c-7522-af6a-d7fff3312f18
Resume in Codex: codex resume 01a0a3dc-ff3c-7522-af6a-d7fff3312f18
```

## 2026-09-15 — Codex 재검토 #2 layer 3 (`8ef6ba6`, read-only · `task-mu2btpde-zcgapx`)
판정: **LiveSender MERGE** · 엔진 FIX FIRST(1건). 이전 1·2·R6 CLOSED, 3 PARTIAL. 소유권 한계 문서화 적정.

| Codex | 동의 | 조치 |
|---|---|---|
| 청산 시 동기화로 드러난 추가 수량의 진입 수수료 미반영 → 지갑 보존 깨짐 | ✅ | 추가 수량 × 거래소 평균가 × taker를 지갑·`entry_commission`에 반영 · 테스트에 지갑 보존 단언 추가(red → green) |

### Codex 재검토 #2 원문 (verbatim)
```
**Findings**
1. **Engine FIX FIRST: exit sync still misses entry fees for extra exchange qty discovered only at close.**  
`_exit()` now syncs `pos.qty` and `pos.entry_price` to `positionRisk`, so the gross PnL basis is fixed, but it does not add estimated entry commission for the extra qty before closing. If entry adoption previously failed because `_read_position()` failed, the later sync can close `pr.amt > internal qty` and book `wallet += pnl - exit_comm` without ever subtracting the extra entry fee. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:373), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:376), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:390), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:392). The new test checks PnL basis but not wallet/entry-fee conservation: [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:334).

**Prior Items**
- Finding 1 / R6 malformed `positionRisk` escapes: **CLOSED.** `LiveSender.position_risk()` converts row-shape and Decimal parse failures to `OrderOutcomeUnknown`, and engine `_read_position()` also catches parser exceptions defensively. Evidence: [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:178), [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:190), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:212), [tests/test_paper_sender.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_sender.py:270).

- Finding 2 LIVE adoption misattribution / shrink: **CLOSED under the accepted ownership design.** Shrink is fixed: adoption happens only when exchange qty is larger than confirmed fills, otherwise it blocks without reducing internal qty. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:255), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:257), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:261), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:355).

- Finding 3 exit closes more than internal qty with internal entry basis: **PARTIAL.** The entry basis is now synced to exchange average entry before close, so the original gross-PnL basis problem is fixed. The missing extra entry-fee accounting above keeps this from being fully closed. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:373), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:378).

**Ownership Documentation**
Adequately documented in code. The adoption branch explicitly says ownership cannot be distinguished and relies on the LIVE preconditions: dedicated USD-M account plus flat at startup. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:256). The checklist includes USD-M-only/no COIN-M, and the startup gate documents/enforces one-way, isolated, and flat checks around mode/margin changes. Evidence: [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:60), [exchange/gate.py](/home/cms/project/BTC_Futures_E2E/exchange/gate.py:3).

**Verdicts**
LiveSender: **MERGE**.  
Engine: **FIX FIRST**.

I did not modify files, use network, read `.env`, or run tests. `git diff --check 0aa7a82..HEAD -- paper/ tests/` is clean.

Codex session ID: 01a0a3e1-ba12-7f32-866d-abf310306357
Resume in Codex: codex resume 01a0a3e1-ba12-7f32-866d-abf310306357
```

## 2026-09-15 — Codex 재검토 #3 layer 3 엔진 (`382eb1d`, read-only · `task-mu2bxrji-efiary`)
판정: **엔진 MERGE** — 발견 없음(추가 수량 수수료 CLOSED · 이중 부과 없음 · 거래소 수량이 작을 때 추가 부과 없음 확인). Codex는 환경에 pytest가 없어 테스트를 돌리지 못했다고 명시 — 로컬 351 passed.
**layer 3 최종: LiveSender MERGE(#2) · 엔진 MERGE(#3) · 테스트넷 프로브 SAFE TO RUN ON TESTNET(1차 재검토).**

### Codex 재검토 #3 원문 (verbatim)
```
No findings.

The FIX FIRST looks closed at [paper/engine.py:376](/home/cms/project/BTC_Futures_E2E/paper/engine.py:376): close-time sync now charges only `abs(pr.amt) - pos.qty` when the exchange position is larger than internal, subtracts it from wallet, and adds it to `pos.entry_commission`.

Regression checks:
- No double charge after entry adoption: adoption already raises `pos.qty` and `pos.entry_commission` at [paper/engine.py:257](/home/cms/project/BTC_Futures_E2E/paper/engine.py:257), so the close-time guard `abs(pr.amt) > pos.qty` is false for the same extra.
- `pr.amt < internal qty`: no extra fee is charged; the engine syncs down to exchange qty before close at [paper/engine.py:382](/home/cms/project/BTC_Futures_E2E/paper/engine.py:382). That matches “close what exchange actually holds” and does not introduce a new synthetic fee.
- Test coverage was updated at [tests/test_paper_engine.py:339](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:339) to assert wallet includes the discovered extra entry commission.

Verdict: engine MERGE.

I could not run the test suite because `pytest` is not installed in this environment (`pytest: command not found`).

Codex session ID: 01a0a3e4-9e32-7113-a247-9cbcc72edc54
Resume in Codex: codex resume 01a0a3e4-9e32-7113-a247-9cbcc72edc54
```

## 2026-09-15 — 사용자 방향 전환: 테스트넷 폐기 · ccxt/ccxt.pro 채택 · layer 3 결정 3건
- **테스트넷 폐기**: `scripts/testnet_fee_probe.py`와 그 테스트는 **미사용으로 보존**(삭제하지 않음). 설계서 §11은 폐기 표시. #4 수수료 가정은 보수적(수수료가 격리 마진을 줄인다)으로 유지, 레지스트리 #6대로 첫 LIVE 진입에서 판정. `.env.example` 테스트넷 블록 미사용 표시.
- **결정 1·2 승인**: 실행 시점 예상 체결가로 재사이징 · 체결 후 #5 위반 즉시 청산.
- **결정 3**: 페이퍼 슬리피지 2 bps 편도 + 불리 tick → 레지스트리 #7(0.016 bps를 페이퍼에 한해 대체).
- **ccxt 고정**: `ccxt==4.5.78`(PyPI 최신, 2026-09-15 확인) → 레지스트리 #8. 푸시: 로컬 9커밋 `9f4ab4b..0a604f0` 사용자 요청으로 푸시.
- **슬리피지 2 bps 전환 중 엔진 결함 발견·수정**: 진입 스킵 판단이 SL을 **예상 체결가**와 비교했다. 0.016 bps에서는 드러나지 않았으나 2 bps에서 LONG 예상가(mark×1.0002)가 SL 위로 올라가 **mark가 이미 SL을 넘은 진입**을 허용했다(`test_sl_already_crossed_at_execution_skips_entry`가 잡음). SL 트리거 기준(mark, #5)으로 먼저 판정하도록 수정. LIVE 흉내 테스트 송신기 4곳은 슬리피지 0으로 고정(LIVE 예상가 = mark와 맞추기 위한 테스트 더블 조정 · 단언 변경 없음).
- ⚠️ 열린 항목: `LiveSender.quote_fill_price`는 여전히 mark다. 실제 라이브 슬리피지가 2 bps 수준이면 최고 L 경계(한 L 단계 ≈ 청산 거리 1.45e-4)보다 `1.5 × 슬리피지`가 커서 **체결 후 #5 위반 → 즉시 청산이 자주 날 수 있다**. LIVE 예상가에도 #7 모델을 쓸지는 사용자 결정(라이브 배선 전).

## 2026-09-15 — ccxt/ccxt.pro 전환 (레지스트리 #8) — exchange 전송 · layer 5 피드 · 검증 결과

### watch 메서드 확인 (ccxt 4.5.78 `ccxt.pro.binanceusdm`, `ex.has` + 소스)
`watchOHLCV` ✅ · `watchMarkPrice`/`watchMarkPrices` ✅ · `watchLiquidations` ✅ · `watchBidsAsks`(bookTicker) ✅ · `watchTicker`(miniTicker) ✅ · `watchTrades`(@trade) ✅ · `watchOrderBook`(@depth@100ms) ✅ · `watchFundingRate` 메서드 존재.
→ 원시 구독(raw subscription) 대체가 필요한 스트림 없음.

### 티어 검증 테스트 출력 (verbatim · `tests/test_ccxt_stream_tiers.py`)
```
[ccxt 4.5.78] ccxt.pro.binanceusdm 가 연 소켓
  watch_ohlcv_1m       wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@kline_1m']
  watch_mark_price     wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@markPrice@1s']
  watch_liquidations   wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@forceOrder']
  watch_trades         wss://fstream.binance.com/public/ws/0  SUBSCRIBE ['btcusdt@trade']
  watch_bids_asks      wss://fstream.binance.com/public/ws/0  SUBSCRIBE ['btcusdt@bookTicker']
  watch_order_book     wss://fstream.binance.com/public/ws/0  SUBSCRIBE ['btcusdt@depth@100ms']
  watch_ticker         wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@miniTicker']
[ccxt 4.5.78] data.feed.TeeBinanceUsdm 가 연 소켓
  watch_ohlcv_1m       wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@kline_1m']
  watch_mark_price     wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@markPrice@1s']
  watch_liquidations   wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@forceOrder']
  watch_trades         wss://fstream.binance.com/public/ws/0  SUBSCRIBE ['btcusdt@trade']
  watch_bids_asks      wss://fstream.binance.com/public/ws/0  SUBSCRIBE ['btcusdt@bookTicker']
  watch_order_book     wss://fstream.binance.com/public/ws/0  SUBSCRIBE ['btcusdt@depth@100ms']
  watch_ticker         wss://fstream.binance.com/market/ws/0  SUBSCRIBE ['btcusdt@miniTicker']
```
- 경로 끝의 `/0`은 ccxt 스트림 인덱스이며 구독은 SUBSCRIBE 프레임으로 한다. 재작성은 `get_ws_url`이 future 기본 URL이 정확히 `/ws`로 끝날 때만 한다 — 기본 URL을 `/stream`으로 바꾼 흉내에서 `wss://fstream.binance.com/stream/0`(legacy)이 열리고 검증이 실패함을 테스트로 고정.

### 라이브 전달 프로브 (읽기 전용 · 키 없음 · `scripts/feed_delivery_probe.py 150` · 로컬 WSL)
urls_opened `market/ws/0·1·2` · 150초 kline push 309 · 마감 2 · markPrice@1s 149 · forceOrder 0 · stalled [] · 해석 오류 0 · 재연결 0.
forceOrder 0건은 BTC 강제청산이 드문 탓일 수 있어 **판정 불가**(이 봇은 청산 스트림을 소비하지 않는다).

### 구현 중 확인한 사실 (소스·모의 HTTP로 실측)
1. **`create_order`는 수량을 조용히 자른다**: `amount_to_precision` 때문에 0.0339 → wire `quantity=0.033`. → 어댑터가 ccxt 정밀도 결과와 우리 수량의 **값**이 다르면 전송 거부(표기 차이 `0.010`↔`0.01`은 같은 값이라 허용 — 처음엔 문자열 비교로 정상 주문을 거부해 테스트가 잡음).
2. **ccxt는 `newClientOrderId`가 없으면 자기 브로커 id(`x-cvBPrNm9…`)를 주입한다** → 어댑터가 항상 우리 id(`bfe2e-…`)를 넣는다.
3. **`watch_ohlcv`는 `E`·`x`를 버리고 float으로 줄인다** → `TeeBinanceUsdm`이 핸들러에서 원시 메시지를 먼저 받는다(`super()` 유지). 원시 `ex.watch(url,…)`는 binance `handle_message`가 자기 해시만 풀어 우리 퓨처가 안 풀리므로 쓰지 않았다.
4. 서명: ccxt `sign()`이 `timestamp`·`recvWindow`(options, 5000으로 설정)·`signature`를 1회 붙인다(테스트가 개수 검사). 시각 오프셋은 ccxt `timeDifference`(`sync_time()`), -1021이면 재동기화. 우리 `TimeSync`는 ccxt 경로에서 쓰지 않는다(중복 없음).
5. rate limit: ccxt 스로틀은 클라이언트 토큰 버킷(`enableRateLimit`), 헤더 카운터는 없다 → 응답 헤더를 우리 `RateLimitCounter`에 넣는다.
6. 오류: ccxt는 HTTP 상태를 예외에 싣지 않는다 → `on_rest_response`를 감싸 상태를 잡는다. 5xx(503 "Unknown error" 포함)·타임아웃·연결 실패 → `TransportError`, Binance `{code,msg}` → `BinanceAPIError(code)`.
7. ccxt는 구독마다 소켓을 따로 연다(kline·markPrice가 다른 `/market` 소켓) — 설계서 layer 5 "같은 소켓"과 다르나 티어 동일·스트림별 감시(기록).
8. `exchange/client.py` urllib `BinanceRestClient`는 운영 경로에서 제거(미사용 프로브·자기 테스트만, 가드 테스트). `capture_account_snapshot.py`는 ccxt 전송으로 이식.

## 2026-09-15 — Codex 검토 ccxt 전환 (`f0268f0`, read-only · `task-mu2j7hg4-z7qv2i`)
판정: **ccxt REST 어댑터 FIX FIRST · 피드 MERGE · 백필 MERGE** · 엔진 변경·2 bps 회귀 없음 · WS 티어 테스트 가로채기 충분(Q5 AGREE).

### 항목별 동의 여부와 조치 (실패 테스트 10개 → 수정 → 444 green)
| Codex | 동의 | 조치 |
|---|---|---|
| 1 -1006·-1007(실행 여부 불명)이 4xx 본문이면 `BinanceAPIError`로 분류 | ✅ | 코드 -1006·-1007 → HTTP 상태와 무관하게 `TransportError` |
| 2 `newOrderRespType` 값 미고정(호출자가 ACK 등으로 덮을 수 있음) | ✅ | 어댑터가 RESULT 외 거부 · ccxt에 항상 RESULT |
| 3 ccxt 내부 호출(sync_time·load_markets) 헤더가 카운터에 안 들어감 | ✅ | `_call` 성공 경로마다 헤더 관측 |
| Q3 `returnResponseHeaders=True`가 원시 응답을 변형 | ✅ | 설정에서 False 고정 · 주입된 거래소가 True면 생성 거부 |
| Q2 ccxt가 HTTP 전에 거부(InvalidOrder) | ✅ 확인 | 요청 0건 · `BinanceAPIError(code None)`(실행 안 됨) 테스트 추가 |

### Codex 검토 원문 (verbatim)
```
Read-only review completed. I did not modify files, did not use network, and did not read `.env`. Targeted pytest could not start because the read-only sandbox has no usable temp directory.

**Findings**
1. **FIX FIRST: unknown order outcomes can be misclassified.**  
   `CcxtRestClient._call()` maps JSON `{code,msg}` on non-5xx to `BinanceAPIError` even for ccxt/Binance unknown-outcome codes. ccxt maps `-1006` as execution status unknown and `-1007` as send/execution status unknown: [ccxt/binance.py:2660](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:2660>), [ccxt/binance.py:2661](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:2661>). Adapter logic: [exchange/ccxt_rest.py:153](</home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:153>). For order POST, these should be `TransportError`/unknown regardless of HTTP status.

2. **FIX FIRST: lower-level order adapter allows non-`RESULT` response type.**  
   `newOrderRespType` is allowlisted without value validation: [exchange/orders.py:51](</home/cms/project/BTC_Futures_E2E/exchange/orders.py:51>), and adapter forwards caller value: [exchange/ccxt_rest.py:119](</home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:119>). ccxt sets `RESULT` for swaps, but later extends request params, so caller params can override: [ccxt/binance.py:6924](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:6924>), [ccxt/binance.py:7088](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:7088>). `LiveSender` pins `RESULT`, but `CcxtRestClient.post('/fapi/v1/order')` should reject anything else.

3. **Medium: rate-limit header accounting misses hidden ccxt calls.**  
   `sync_time()` and first-order `_market()->load_markets()` go through ccxt but do not call `_headers()`: [exchange/ccxt_rest.py:97](</home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:97>), [exchange/ccxt_rest.py:134](</home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:134>). ccxt throttling still applies: [ccxt/base/exchange.py:5650](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/base/exchange.py:5650>), but `RateLimitCounter` undercounts.

**Q Verdicts**
- **Q1: DISAGREE, with caveat.** side/type/quantity/reduceOnly are guarded; forbidden `closePosition`, `workingType`, `priceProtect`, `timeInForce`, stop/algo/test/papi/sor params are rejected before ccxt: [exchange/orders.py:48](</home/cms/project/BTC_Futures_E2E/exchange/orders.py:48>), [exchange/orders.py:112](</home/cms/project/BTC_Futures_E2E/exchange/orders.py:112>). ccxt would route papi/algo if those params existed: [ccxt/binance.py:6740](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:6740>), [ccxt/binance.py:6746](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:6746>). Quantity string precision guard is sound: ccxt uses `Decimal(str(n))`: [ccxt/base/decimal_to_precision.py:97](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/base/decimal_to_precision.py:97>). Caveat: `newOrderRespType` value needs locking.

- **Q2: AGREE.** Unknown `-1006/-1007` can become `BinanceAPIError`. `_last_status` is reliable only after `on_rest_response`: [ccxt/base/exchange.py:614](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/base/exchange.py:614>). Pre-fetch ccxt validation has no status and may become `BinanceAPIError(0)` or leak if raised before `_call`.

- **Q3: DISAGREE for current production path.** `ex.request()` returns parsed exchange JSON from `fetch2`: [ccxt/base/exchange.py:5691](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/base/exchange.py:5691>). Rules/sizing consume raw payloads: [exchange/loader.py:70](</home/cms/project/BTC_Futures_E2E/exchange/loader.py:70>). Caveat: `returnResponseHeaders=True` mutates object responses: [ccxt/base/exchange.py:626](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/base/exchange.py:626>).

- **Q4: PARTIAL/AGREE.** Exactly one timestamp/recvWindow/signature is correct via `sign()`: [ccxt/binance.py:12313](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:12313>). `sync_time()` uses USD-M time because `binanceusdm` defaultType is `swap`: [ccxt/binanceusdm.py:38](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binanceusdm.py:38>), [ccxt/binance.py:3123](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/binance.py:3123>). Rate-limit headers are undercounted on hidden calls.

- **Q5: AGREE.** `Client.create_connection` interception captures used ccxt.pro sockets; `Client.open()` calls it directly: [ccxt/ws/client.py:189](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/async_support/base/ws/client.py:189>). Legacy mutation is realistic because rewrite only happens when URL ends exactly `/ws`: [ccxt/pro/binance.py:270](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/pro/binance.py:270>).

- **Q6: AGREE.** Handler overrides are correct: [data/feed.py:137](</home/cms/project/BTC_Futures_E2E/data/feed.py:137>). ccxt unwraps combined `stream/data` wrappers first: [ccxt/pro/binance.py:5224](</home/cms/project/BTC_Futures_E2E/.venv/lib/python3.12/site-packages/ccxt/pro/binance.py:5224>). DeliveryCounter uses `E`, and close only on `x=true`: [data/feed.py:174](</home/cms/project/BTC_Futures_E2E/data/feed.py:174>). Feed MERGE.

- **Q7: AGREE.** Backfill paging is monotonic and fail-closed on overlong pages, malformed rows, and time reversal: [data/backfill.py:60](</home/cms/project/BTC_Futures_E2E/data/backfill.py:60>). Backfill MERGE.

- **Q8: DISAGREE with regression concern.** Engine now checks SL against mark before quote/sizing: [paper/engine.py:223](</home/cms/project/BTC_Futures_E2E/paper/engine.py:223>). 2 bps paper slippage is locked: [paper/config.py:12](</home/cms/project/BTC_Futures_E2E/paper/config.py:12>). Engine MERGE.

- **Q9: Test gaps.** Add tests for `-1006/-1007` order mapping, `newOrderRespType != RESULT`, `returnResponseHeaders=True`, `sync_time/load_markets` header accounting, and ccxt pre-fetch `InvalidOrder` behavior.

**Verdicts**
- ccxt REST adapter, including order path: **FIX FIRST**.
- feed: **MERGE**.
- backfill: **MERGE**.

Codex session ID: 01a0a49e-f24a-7e11-ba4f-ad31bff60030
Resume in Codex: codex resume 01a0a49e-f24a-7e11-ba4f-ad31bff60030
```

## 2026-09-15 — Codex 재검토 ccxt 어댑터 (`70e808e`, read-only · `task-mu2jhylz-ca92xu`)
1·2·Q3 CLOSED · 3 PARTIAL: -1021 재동기화의 `/time` 응답 헤더가 카운터에 안 들어감 → ✅ 동의, 실패 테스트 → 수정(재동기화 후 헤더 관측) → 445 green.

### Codex 재검토 원문 (verbatim)
```
**Verdict: FIX FIRST**

1. **CLOSED**: `-1006` / `-1007` now map to `TransportError` even on 4xx. The unknown-code check is before `-1021` handling, and 5xx still wins first. See [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:163) and [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:168). Covered by [tests/test_ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/tests/test_ccxt_rest.py:311).

2. **CLOSED**: `newOrderRespType` is pinned to `RESULT`; non-`RESULT` caller input is refused before send, and the ccxt order params always use `"RESULT"`. See [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:116) and [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:126). Covered by [tests/test_ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/tests/test_ccxt_rest.py:321).

3. **PARTIAL**: hidden ccxt success-path calls now feed `RateLimitCounter` once via `_call()` at [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:157), and response construction no longer re-observes headers at [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:110) / [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:137). No double-observe regression found for normal calls.

   Remaining gap: the `-1021` resync path still calls `self.ex.load_time_difference()` directly at [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:172), outside `_call()`, so that `/time` response’s rate-limit headers are not observed. That keeps the original hidden-ccxt-call issue partially open.

4. **CLOSED**: `returnResponseHeaders` is explicitly disabled for constructed exchanges and rejected for injected exchanges at [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:75) and [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:79). Raw payloads stay clean, while `Response.headers` are still returned from `last_response_headers`.

I could not run the tests: `pytest` is not installed, and `python3 -m pytest` reports no pytest module. Static review was against clean `70e808e`.

Codex session ID: 01a0a4a6-65dd-7b11-be14-c69f20203efe
Resume in Codex: codex resume 01a0a4a6-65dd-7b11-be14-c69f20203efe
```

## 2026-09-15 — Codex 재검토 #2 ccxt 어댑터 (`9b911a9`, read-only · `task-mu2jljte-a0glix`)
성공 경로 CLOSED · 재동기화 `/time`이 실패(429+헤더)하면 헤더 유실 OPEN → ✅ 동의, 실패 테스트 → `finally`로 관측 → 446 green. 주문 경로 회귀 없음(Codex가 로컬 venv로 좁은 테스트 10개 실행 통과).

### Codex 재검토 #2 원문 (verbatim)
```
**Findings**

OPEN, partial remains: [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:171) observes resync headers only when `self.ex.load_time_difference()` succeeds. If the `/fapi/v1/time` resync request itself gets an exchange response with rate-limit headers and ccxt raises, the `except ccxt.BaseError: pass` at line 174 skips `_headers()`, so those headers are still lost. The narrow fix is to observe in a `finally` around the resync call.

CLOSED for the success path: [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:173) now feeds successful `-1021` resync `/time` headers into `RateLimitCounter`, and [tests/test_ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/tests/test_ccxt_rest.py:364) covers that path.

**Regression / Order Path**

No order-path regression found in this diff. I ran the narrow ccxt REST/order/error tests with the project venv and no network:

`10 passed`

I also manually probed the failed-resync header case: original request raised `-1021`, resync `/time` returned `429` with `X-MBX-USED-WEIGHT-1M`, and counter usage stayed `0.0`.

**Verdict**

FIX FIRST for the whole ccxt REST adapter. The original partial finding is only half closed; success-path resync is fixed, failed resync with response headers is still open.

Codex session ID: 01a0a4a8-f3fb-7932-93fb-606eee26c526
Resume in Codex: codex resume 01a0a4a8-f3fb-7932-93fb-606eee26c526
```

## 2026-09-15 — Codex 재검토 #3 ccxt 어댑터 (`7fee6f6`, read-only · `task-mu2jp5u0-4op9hx`)
판정: **MERGE** — 발견 없음(Codex가 로컬 venv로 `tests/test_ccxt_rest.py` 56 passed 확인).
**ccxt 전환 최종: REST 어댑터(주문 경로 포함) MERGE · 피드 MERGE · 백필 MERGE.**

### Codex 재검토 #3 원문 (verbatim)
```
No findings.

CLOSED: `-1021` failed resync `/time` headers are now observed. The `finally` path at [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:170) calls `_headers()` after `load_time_difference()` whether that resync succeeds or raises, and the regression test at [tests/test_ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/tests/test_ccxt_rest.py:385) covers the `429 + X-MBX-USED-WEIGHT-1M` case.

OPEN: none.

Regression check: none observed for the ccxt REST adapter, including the order path. Order validation, `create_order`, raw `info` response handling, unknown-execution mapping, and rate-limit header paths remain covered.

Verified:
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -s tests/test_ccxt_rest.py -p no:cacheprovider`  
Result: `56 passed`

No network, no `.env`, no changes. Worktree clean at `7fee6f6cb05622f8f05e033443d3f1cced2e8885`.

Final verdict: **MERGE**.

Codex session ID: 01a0a4ab-8632-7b13-896a-a279415a704e
Resume in Codex: codex resume 01a0a4ab-8632-7b13-896a-a279415a704e
```

## 2026-09-15 — 사용자 결정: 마이그레이션 수락 · LIVE 예상 체결가 #7 · 소켓당 1스트림 · layer 5 마무리 → layer 4

### 보고 원문 재게시(사용자 요청 — 붙여 넣은 보고가 줄 중간에서 잘려 도착)
사용자가 인용한 보고 "What ccxt actually does"의 항목 1과 5를 **전문 그대로** 다시 적는다(내용은 위 "구현 중 확인한 사실" 1·5·6과 같고, Codex 수정 뒤의 최종 상태를 반영).

**Item 1 — `create_order` silently truncates the quantity.**
ccxt 4.5.78 `binance.create_order` passes the amount through `amount_to_precision(symbol, amount)` before building the request, so a quantity of `0.0339` goes on the wire as `quantity=0.033` with no error and no warning. Our sizing already floors to stepSize, so in normal operation the two agree; but if they ever disagree (a stale market cache in ccxt, a precision change on the exchange, a bug on our side), ccxt would silently send a different quantity from the one sizing approved. The adapter (`exchange/ccxt_rest.py::_market_order`) still sends through `create_order`, but first computes `Decimal(ex.amount_to_precision(symbol, qty))` and compares it **by value** with `Decimal(qty)`; if they differ it raises `OrderParamError` and nothing is sent. The comparison is by value, not by string: format-only differences such as `"0.010"` vs ccxt's `"0.01"` are the same quantity and are allowed (the first implementation compared strings and refused a valid order; the test caught it). `amount_to_precision` is used only as this guard — never as our normalization or final check (registry #8); normalization stays `floor → MIN_NOTIONAL recheck → tick` in our code. Related: ccxt also injects its own broker `newClientOrderId` (`x-cvBPrNm9…`) when none is given, so the adapter always supplies ours (`bfe2e-` + 24 hex), pins `newOrderRespType=RESULT` and sends `reduceOnly=True` for exits.

**Item 5 — error mapping.**
ccxt raises typed exceptions but does not carry the HTTP status on them, so the adapter wraps `on_rest_response` to capture the status and headers of every response (including ccxt's hidden calls such as `load_markets` and the time sync). Mapping in `CcxtRestClient._call`:
- HTTP 5xx (including 503 "Unknown error"), timeouts and connection failures (`ccxt.NetworkError` family with no Binance body: `RequestTimeout`, `ExchangeNotAvailable`, `DDoSProtection` without a body) → `TransportError` — the request's outcome is unknown.
- Binance codes **-1006 and -1007** ("unexpected response / timeout waiting for backend — execution status unknown") → `TransportError` **regardless of HTTP status** (Codex review fix: they had been classified as a normal API error). For an order this becomes `OrderOutcomeUnknown` in `LiveSender`, which blocks entries until positionRisk is re-read.
- Any other Binance `{code, msg}` body → `BinanceAPIError(status, code)` with the exchange code preserved, so callers that branch on codes keep working (the startup gate still treats **-4046** "no need to change margin type" as success).
- **-1021** (timestamp outside recvWindow) → one `load_time_difference()` resync, then `BinanceAPIError` is raised (no automatic re-send of the original request). The resync response headers are fed to our rate-limit counter in a `finally`, so they are counted whether the resync succeeds or fails (Codex re-reviews #1–#2).
- An order ccxt refuses before any HTTP request (e.g. `InvalidOrder` from its own checks) → `BinanceAPIError` with `code=None`; zero requests are sent, so it is a definite not-executed.
- `returnResponseHeaders` must be False (it mutates the raw payload); a supplied exchange with it enabled is refused at construction.

### 결정 1 — LIVE 예상 체결가 = #7 (레지스트리 #9)
`paper.sender.adverse_fill_estimate(side, mark, tick, rate=0.0002)` 하나를 PAPER·LIVE가 같이 부른다. `LiveSender.quote_fill_price`가 mark 대신 이 값을 돌려준다. 테스트: 실제 `LiveSender`로 체결가가 추정과 **정확히 같을 때**(LONG·SHORT) 체결 후 #5 `gate_ok` · 청산 없음 · 진입 차단 없음. LIVE 흉내 송신기(`SpySender`)의 "LIVE 추정 = mark" 가정을 걷어내고 기본 슬리피지로 돌렸다(`ZERO_SLIP` 제거 · 사전 사이징 probe도 추정가로) — 기존 LIVE 테스트 전부 통과.

### 결정 2 — `/market` 소켓은 스트림마다 1개(수락)
ccxt.pro가 구독마다 소켓을 연다: kline_1m · markPrice@1s(· forceOrder 구독 시 셋째). 매니페스트 `events`에 **소켓별** connect / disconnect / reconnect(URL·스트림 포함)를 남기고 DeliveryCounter는 스트림별 그대로.
📌 **23 h 선제 재연결 비용은 이제 소켓마다 든다**: 스트림 N개면 23 h마다 재연결 N번(현재 2 · forceOrder 소비 시 3). 각 재연결은 그 스트림에만 짧은 공백을 만들고, 봉 공백은 REST 백필이 메운다(layer 5). 스트림들이 같은 시각에 끊기지 않게 소켓별 연결 시각 기준으로 따로 잰다.

### 결정 3 — klines 페이지 크기 (공식 문서 **렌더링** 확인, WebFetch 요약 아님)
2026-09-15 playwright로 공식 레퍼런스 페이지를 렌더링해 읽었다: `https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#kline-candlestick-data`(구 경로 `/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data`는 404).
- `GET /fapi/v1/klines` · `GET /fapi/v1/markPriceKlines`: `limit` — **integer · int64 · max: 1500 · Default: 500**
- IP weight(LIMIT 기준): [1,100) → **1** · [100,500) → **2** · [500,1000] → **5** · >1000 → **10**
- 설정: `data/config.py` `KLINES_PAGE_LIMIT = 1000` — 가중치 5인 최대 크기(1500은 가중치 10으로 봉당 비용이 1.33배). 30일 1m 백필 = 43,200봉 = 44페이지 × 5 = 220 weight(분당 한도 대비 작다 · 한도 값은 런타임 헤더 카운터가 본다). 문서상 최대 1500 초과 요청은 `data.backfill`이 거부한다.

### layer 5 마무리 — E2E 이식 기록 (`data/shards.py` · 출처 `e2e/l2_collector.py` @ `90d47aa`, E2E HEAD `f1e7d86`)
| E2E 원본 | 여기 | 변경 |
|---|---|---|
| `ShardWriter`(:143-191) | `data.shards.ShardWriter` | root·symbol·monotonic 주입 · 스키마는 이 봇(kline 14열·markprice 7열, **가격·수량 `pa.string` Decimal 원문**, E2E는 float64) · 같은 이름 shard가 있으면 `_n` 접미사(rename이 조용히 덮는 것 방지 — `_file_start_ms`는 None을 돌려 재생에서 건너뛰지 않는다) · register_shard 무예외·`manifest_errors` 불변 |
| `WriterThread`(:193-303) | `data.shards.WriterThread` | writer = kind별 dict(kline1m_update·kline1m_close·markprice) · depth1s 다운샘플 없음 · `("event", (kind, detail))`을 **writer 스레드가** `manifest.log_event("feed", …)`(asyncio 루프에서 sqlite 금지) · 실패 `event_errors` · 모르는 kind는 dispatch 오류. #138 동작 불변: roll 격리 + `roll_failed` · dispatch 예외 기록 후 계속 · writer별 종료 플러시 + `final_flush_failed` · 처리기 `_safe_log` · 종료 플러시 중 대장 쓰기 없음 |
| `Collector._shutdown_record`(:590-614) | `data.shards.shutdown_record` | 자유 함수 · **큐 포화 드롭 > 0도 `stop_dirty`**(E2E는 드롭 수만 문구에) |
| `Collector` 큐·`_put`·run 종료부 | `data.shards.Recorder` | 소켓 코드 없음(ccxt.pro가 소유) · `put`/`event`는 put_nowait(블록·예외 없음) · `stop()` = stop 표지 → join(30s) → 종료 기록을 대장에 |
| `consume` 23h 선제 재연결(:505) | `data.feed.MarketFeed._refresh_loop` | 소켓마다 `client.connectionEstablished` 기준 · 넘은 소켓만 `client.on_error(ProactiveRefresh)` → 그 watch만 끝나고 백오프 없이 재watch(ccxt가 같은 URL로 새 소켓·SUBSCRIBE — 가짜 소켓 실험·테스트로 확인) |
테스트 복원(`tests/test_data_shards.py` 17건): E2E #138 네 건(첫 writer 플러시 실패·dispatch 예외 후 계속·처리기 로그 실패·종료 기록 조건)을 이 구조로 옮기고, 대장 쓰기 금지·roll 실패 격리·재생 스캔 호환(`scan_window`가 writer 파일을 그대로 셈)·드롭 → dirty 추가. 피드(`tests/test_data_feed.py` +5): 소켓별 connect 이벤트 · 23h 초과 소켓만 재연결·전달 재개 · 기록 행 · 훅 실패 무전파 · 취소로 끝난 watch 루프 → `FeedFailure`(구현 중 발견: 예전 `run()`은 취소된 태스크를 건너뛰어 스트림 하나가 조용히 죽을 수 있었다).

## 2026-09-15 — Codex 검토: LIVE 예상 체결가 #9 + layer 5 마무리 (`65ce4b6..c9c38fa`, read-only · `task-mu2kq6ib-uro1pe`)
판정: **A(LIVE 추정 #9) MERGE · B(layer 5) FIX FIRST** — A1·A2·A3·B1·B3·B4·B5 OK, B6 OK(단서 = #1).

### 항목별 동의 여부와 조치 (실패 테스트 2개 → 수정 → green)
| Codex | 동의 | 조치 |
|---|---|---|
| 1 High `MarketFeed.sink()`가 `FeedMessageError`만 잡는다 — 카운터 설정 오류(`kline1m_close` 없음 → `KeyError`)가 ccxt 수신 루프로 새 소켓이 `FeedFailure` 없이 멈춘다(Codex 재현) | ✅ | ① sink의 비메시지 예외는 전부 `_failure`로 저장 → `run()`이 `FeedFailure` ② `run()`이 소켓을 열기 전에 카운터가 `FED_STREAMS`(kline1m_update·kline1m_close·markprice)를 모두 세는지 확인 → 아니면 `ValueError` ③ `TeeBinanceUsdm._socket`도 예외 차단. 기록(`recorder.put`) 실패는 원래대로 `errors`에 남기고 피드는 계속 |

### Codex 검토 원문 (verbatim)
```
1. **High** — [data/feed.py](/home/cms/project/BTC_Futures_E2E/data/feed.py:230): `MarketFeed.sink()` only catches `FeedMessageError`, but it calls `DeliveryCounter.observe()` inside that same ccxt receive-loop callback. If the counter is misconfigured, e.g. missing `kline1m_close`, a closed kline raises `KeyError` from [ops/delivery_counter.py](/home/cms/project/BTC_Futures_E2E/ops/delivery_counter.py:182). That exception escapes through `TeeBinanceUsdm.handle_ohlcv()` before ccxt schedules the next receive, so the socket receive loop can stop without `FeedFailure`. I reproduced this directly with a counter containing only `("kline1m_update", "markprice")`.

**Per Question**
A1. **OK** — Entry sizing uses `sender.quote_fill_price()` before `size_entry()` in [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:228). SL-crossed skip still uses mark at line 226. BUY quotes higher, SELL quotes lower in [paper/sender.py](/home/cms/project/BTC_Futures_E2E/paper/sender.py:70), so SHORT entries are adverse, not favorable. Reduce-only exits are not sized from the quote in LIVE; PAPER exit fills remain adverse by side.

A2. **OK** — post-fill #5 uses actual fill VWAP from `fills` only: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:254), then `_post_fill(d, entry, qty)` at line 274. If `gate_ok` is false, it immediately exits at lines 282-284.

A3. **OK** — I did not find a LIVE test weakened by removing `ZERO_SLIP`. The probes that depend on expected qty were updated to use the quoted adverse price, and the new real `LiveSender` test covers LONG/SHORT exact-quote fills.

B1. **OK** — #138 behavior is preserved: roll isolation, dispatch error recording, final flush per writer, no manifest writes during final flush, and dirty shutdown for alive/dispatch/final-flush/drop conditions. Local `_n` suffix is an intentional extension.

B2. **ISSUE** — finding #1.

B3. **OK** — For ccxt 4.5.78, `client.on_error()` rejects outstanding futures, calls exchange `on_error`, and removes the errored client from `ex.clients`; the next watch creates a fresh client. I did not find unresolved futures, double-reconnect of the other stream, or inherited old `connectionEstablished`.

B4. **OK** — shard path/name uses first `event_time`; `TS_COLUMN` agrees. `_n` suffix files parse as unknown start and are included, then filtered by the parquet `event_time`, so they are not skipped.

B5. **OK** — sqlite writes are on the writer thread via `Recorder`; feed-loop calls are queue puts/events, not direct sqlite.

B6. **OK with caveat** — queue-full row drops are counted; roll failures are logged as `roll_failed`; unreadable replay files are counted. The caveat is finding #1: a receive-loop escape can stop future delivery rather than count a row drop.

Tests: attempted the requested pytest command with `PYTHONDONTWRITEBYTECODE=1`, but pytest could not start because the sandbox has no writable temp directory (`/tmp`, `/var/tmp`, `/usr/tmp`, and repo cwd all unavailable).

**Verdict**
A: **MERGE**

B: **FIX FIRST** due to the receive-loop exception escape in `MarketFeed.sink()`.

Codex session ID: 01a0a4c5-e0db-7a63-8f90-a7839becb261
Resume in Codex: codex resume 01a0a4c5-e0db-7a63-8f90-a7839becb261
```

## 2026-09-15 — Codex 재검토: layer 5 수정분 + layer 4 메모 (`c906a3d`, read-only · `task-mu2l1ukd-e0sy2c`)
판정: **#1 CLOSED · B(layer 5) MERGE**. → **LIVE 추정 #9 MERGE · layer 5 MERGE.** db/는 검토 범위 밖 메모 4건 → 전부 동의·수정.

### 항목별 동의 여부와 조치 (실패 테스트 4개 → 수정 → 506 green)
| Codex | 동의 | 조치 |
|---|---|---|
| 메모: 콜백 실패가 `_failure = e`로 앞선 sink 실패를 덮을 수 있음(비차단) | ✅ | 콜백도 `self._failure or e`(첫 실패 보존) |
| db #1 `_json`이 중첩 float를 거부하지 못함(`default=`는 float에 안 불림) | ✅ | `_no_floats`가 중첩까지 검사 → `TypeError` |
| db #2 `record_bar` 비교가 mark/index/funding/is_closed를 빼먹어 보강 데이터가 duplicate로 버려짐 | ✅ | 전 필드 비교 · 비어 있던 mark/index/funding만 채우면 `enriched` · 값 있는 필드가 다르면 `conflict`(덮어쓰기 없음) |
| db #3 `with con:`가 호출자의 열린 트랜잭션을 커밋/롤백 | ✅ | 모든 기록 함수가 열린 트랜잭션이면 `TransactionOpen`(migrate와 같은 규칙) |
| db #4 close를 방향 무관하게 최근 open에 연결 | ✅ | 같은 방향 open만 연결 · 없으면 고아(NULL + 사유) |

### Codex 재검토 원문 (verbatim)
```
**Findings**

No feed findings. I traced the ccxt callback paths in [data/feed.py](/home/cms/project/BTC_Futures_E2E/data/feed.py:153): `_socket()` is guarded, `sink()` now catches parser/counter/row-builder/recorder-adjacent unexpected exceptions, callbacks are converted to `_failure`, and `run()` checks `_failure` both while running and after `stop` is set at [data/feed.py](/home/cms/project/BTC_Futures_E2E/data/feed.py:320) and [data/feed.py](/home/cms/project/BTC_Futures_E2E/data/feed.py:332). I do not see the old `DeliveryCounter` `KeyError` escape path anymore.

One small diagnostic caveat: callback failures assign `_failure = e` at [data/feed.py](/home/cms/project/BTC_Futures_E2E/data/feed.py:267), while non-callback unexpected sink failures preserve the first failure with `self._failure or e` at [data/feed.py](/home/cms/project/BTC_Futures_E2E/data/feed.py:260). A later callback exception can mask an earlier stored sink failure before `run()` polls, but it still fails loud as `FeedFailure`; I would not block on this.

**#1 Status**

CLOSED.

**B Verdict**

MERGE.

**db/ Note**

I’d flag these separately from B:

1. [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:93): `_json()` does not actually reject nested floats because `json.dumps(default=...)` is not called for native `float`. Scenario: `Fill.raw`, `decision_json`, custom features, or engine payloads containing `60000.1` as a float are silently persisted with binary-float precision instead of being refused.

2. [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:228): `record_bar()` duplicate/conflict comparison ignores `mark_close`, `index_close`, `funding_rate`, and `is_closed`. Scenario: a WS bar is inserted with those nullable fields missing, then a REST/enriched bar for the same OHLCV arrives with funding/mark data; it returns `"duplicate"` and silently drops the enrichment.

3. [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:199): `record_events()` uses `with con:` without guarding `con.in_transaction`. If a caller already has an open transaction, this function can commit or roll back the caller’s broader transaction boundary. `migrate()` correctly guards this at [db/migrate.py](/home/cms/project/BTC_Futures_E2E/db/migrate.py:106); `record_events()` does not.

4. [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:146): `open_position_id()` links a close to the latest open position by mode/symbol/remaining quantity only, not direction. Scenario: an orphan/adopted `SHORT` close arrives while an unmatched `LONG` open row exists; `_position_closed()` will link it to the long position instead of recording an orphan.

I did not run tests, per the read-only/no-modification constraint.

Codex session ID: 01a0a4ce-2f74-7ac1-81fe-f2384dc1fb3b
Resume in Codex: codex resume 01a0a4ce-2f74-7ac1-81fe-f2384dc1fb3b
```

## 2026-09-15 — 사용자 결정: layer 4·5 수용 · 피처 긴 형식 수용 · 채택 open 이벤트 · klines 1000 승인 → layer 6·7

### 보고 원문 재게시(사용자 요청 — 보고 세 줄이 단어 중간에서 잘려 도착)
- "Dropped rows (queue full) now make the shutdown record `stop_dirty`." — 기록 위치: 위 layer 5 이식 표 `Collector._shutdown_record` 행("큐 포화 드롭 > 0도 `stop_dirty`").
- "Features: stored one row per value, keyed by `(name, params_version)`, instead of the skill's one column per feature. That way a new feature needs no migration, and redefining an existing name and version is refused." — 이 줄은 설계서 §14에만 있었다 → 여기 추가.
- "Codex also flagged four `db/` issues, and all four are fixed: nested floats weren't refused; bar dedup ignored the mark/index/funding fields; a recorder could commit the caller's transaction; a close was linked to an open position without checking direction." — 기록 위치: 위 Codex 재검토 표(db #1~#4).

### 전제 정정 — LIVE 채택
지난 보고의 "채택 포지션은 open 이벤트가 없어 close가 연결되지 않는다"는 **틀렸다.** 엔진은 채택 시에도 `EntryFilled(fills=())`를 내고 그 `post_fill`이 채택 수량·거래소 평균가를 담는다 → close는 이미 open 행에 연결됐다(확인: 채택 테스트에서 `of(ev, EntryFilled)` = 1건, fills=()). 빠져 있던 것은 **출처**(채택이라는 표시·채택 시점 positionRisk)였다.
조치: 두 번째 open 이벤트를 만들지 않고(open 행이 둘이면 `open_position_id` 연결이 깨진다) `EntryFilled.adopted: PositionRisk | None`을 추가 → db open 행 `reason='adopted_from_exchange'` · `liq_price_exchange` · `detail = {"positionRisk": 원문}`. 사용자 결정의 목표("모든 close 행이 open 행에 연결 · 진리원 = 채택 시점 positionRisk")를 이 형태로 충족.
남은 경우(미구현 · 사용자 판단): `_exit`이 청산 직전 거래소 수량이 **더 크면** 그 수량으로 동기화 — close 수량이 open 수량보다 크게 기록되고 늘어난 부분의 open 기록은 없다.

### Telegram Bot API — 공식 문서 렌더링 확인 (playwright · 2026-09-15 · `https://core.telegram.org/bots/api` · 최신 변경 "August 24, 2026 — Bot API 10.3")
- 요청: `https://api.telegram.org/bot<token>/METHOD_NAME` · GET/POST · `application/json` 허용 · 응답 JSON은 항상 Boolean `ok`, 실패 시 `description`·`error_code`(내용은 바뀔 수 있음)·선택 `parameters`.
- `getUpdates`: `offset` = 이전에 받은 최대 update_id + 1("An update is considered confirmed as soon as getUpdates is called with an offset higher than its update_id") · `limit` 1-100 · `timeout` 초(롱폴링, 0=숏폴링은 테스트용) · `allowed_updates` 목록(생략 시 이전 설정 유지) · 웹훅이 설정돼 있으면 동작 안 함 · "recalculate offset after each server response".
- `BotCommand.command`: **1-32자, 영문 소문자·숫자·밑줄만** → 한글 별칭은 명령으로 등록할 수 없다(텍스트·답장 키보드로 처리). `description` 1-256자. `setMyCommands` 최대 100개.
- `setChatMenuButton(chat_id?, menu_button)` · `MenuButtonCommands {type:"commands"}` = 명령 목록을 여는 메뉴 버튼(기본값도 명령 목록).
- `InlineKeyboardButton.callback_data`: **1-64 bytes**. `CallbackQuery`: "Telegram clients will display a progress bar until you call answerCallbackQuery. It is, therefore, necessary to react by calling answerCallbackQuery even if no notification to the user is needed" → **모든 콜백에 answer**(거부·만료 포함). `answerCallbackQuery.text` 0-200자.
- `sendMessage.text` 1-4096자 · `reply_markup` = InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | ForceReply. `ReplyKeyboardMarkup`: `keyboard`(KeyboardButton 행), `is_persistent`, `resize_keyboard`, `input_field_placeholder` 1-64자 · 텍스트 버튼은 누르면 그 텍스트가 메시지로 전송.

## 2026-09-15 — Codex 검토: layer 6·7 + 채택 출처 + db v2 (`3758daf..177d59f`, read-only · `task-mu2m8qsr-gwy4yp`)
판정: **(1) 채택 출처 · (2) 텔레그램 강제 청산 · (3) 킬스위치 · (4) 대사 — 전부 FIX FIRST**. Q1(주인 '예'·nonce·비주인·재처리) OK · Q6(adopted 설정 범위) OK · db v2 체크섬·wide·safety_state OK.

### 항목별 동의 여부와 조치 (실패 테스트 12개 → 수정 → 590 green)
| Codex | 동의 | 조치 |
|---|---|---|
| 1 HIGH 무응답 취소(+12초)가 tick에만 달려 있어, 폴링이 멈춘 사이 +30초의 '예'가 TTL 60초 안이라 실행된다 | ✅ | 콜백에서 `cancel_deadline_ms`(발행 + (3+1)×3초)를 직접 검사 → 넘으면 "응답 기한 지남 — 실행 안 함" + "청산 안 됨". TTL은 설정이 바뀔 때의 마지막 방어선으로 유지(두 경로 모두 테스트) |
| 2 HIGH LIVE 청산은 `PositionClosed(LIQUIDATION)`를 내지 않는다 — 거래소 수량 0이면 `ExitFailed`만 → 청산 1회 킬스위치가 안 걸린다 | ✅ | 엔진이 `PositionVanished`(방향·수량·진입가·사유)를 명시 이벤트로 · 킬스위치가 청산 1회로 발동(`position_vanished`) · `SafetyGate.observe_reconcile`: 봉마다 대사에서 내부≠0·거래소=0이면 발동(조회 실패는 제외) · DB는 close 행 reason `vanished`(체결가·손익 NULL — 추정 안 함) |
| 3 MEDIUM 청산 직전 거래소 수량이 더 크면 close 0.014가 open 0.010에 붙어 flat으로 보이고 늘어난 0.004의 기록이 없다 | ✅ | 엔진이 `PositionSynced`(이전·새 수량, 거래소 평균가, 추가 수수료 추정, positionRisk)를 close **앞에** 냄 → DB는 root open 행의 **수정 행**(reason `adopted_from_exchange`, `position_id` = root) · 남은 수량 = 최신 open 행 수량 − close 합 · root 판별 = `position_id = id` |
| 4 MEDIUM 채택 수량의 추정 진입 수수료가 지갑에서는 빠지는데 DB `entry_commission_usdt`는 체결 합(fills=()이면 0) | ✅ | `EntryFilled.entry_commission`(지갑에서 뺀 합) · DB가 이 값을 기록 |
| 5 LOW(기존) 복사본 `notify/sender.py`가 전송 예외 문구를 토큰 가림 없이 로그·stderr에 남길 수 있다 | ✅ | 예외 문구에서 토큰 → `<token>`(PROVENANCE 헤더에 변경 기록 · 테스트) |

### Codex 검토 원문 (verbatim)
```
1. **HIGH** [notify/bot.py:132](/home/cms/project/BTC_Futures_E2E/notify/bot.py:132), [notify/bot.py:223](/home/cms/project/BTC_Futures_E2E/notify/bot.py:223)  
   Confirmation auto-cancel is enforced only by `on_tick()`, but callback execution checks only the 60s TTL. If the poll loop stalls after issuing `/close` and the owner presses “yes” at +30s, the close executes even though the +12s no-answer cancel should already have invalidated it. The 1s fast poll reduces the chance, but does not make the cancel deadline independent of ticks.

2. **HIGH** [safety/killswitch.py:60](/home/cms/project/BTC_Futures_E2E/safety/killswitch.py:60), [paper/engine.py:333](/home/cms/project/BTC_Futures_E2E/paper/engine.py:333), [paper/engine.py:371](/home/cms/project/BTC_Futures_E2E/paper/engine.py:371)  
   Live liquidation can be missed by the kill switch. `KillSwitch.observe()` only trips liquidation on `PositionClosed(reason=LIQUIDATION)`, but LIVE does not emit that: it emits `LiquidationThresholdCrossed`, and if `positionRisk` is already zero during exit it emits `ExitFailed` and drops the internal position. Result: one real exchange liquidation may not trip `MAX_LIQUIDATIONS=1`.

3. **MEDIUM** [db/record.py:198](/home/cms/project/BTC_Futures_E2E/db/record.py:198), [paper/engine.py:380](/home/cms/project/BTC_Futures_E2E/paper/engine.py:380)  
   Reconcile can report OK after an exit-time sync to a larger exchange quantity. If open is `0.010`, LIVE syncs close qty to `0.014`, DB stores close `0.014` against open `0.010`; `open_position_id()` treats it as flat because closed >= open. Current-state reconcile then sees internal/exchange/DB all flat and clears, hiding the unrecorded extra `0.004` exposure noted in design §14 as “대사 대상 · 미구현”.

4. **MEDIUM** [paper/engine.py:264](/home/cms/project/BTC_Futures_E2E/paper/engine.py:264), [paper/engine.py:282](/home/cms/project/BTC_Futures_E2E/paper/engine.py:282), [db/record.py:214](/home/cms/project/BTC_Futures_E2E/db/record.py:214)  
   Adopted-entry estimated commission is lost in DB. The engine estimates fee for adopted extra qty and subtracts it from wallet, but `EntryFilled` carries no total entry commission and `db._entry_filled()` records `sum(ev.fills)`. For a fully adopted fill (`fills=()`), `positions.entry_commission_usdt` becomes `0` while engine wallet already paid the estimate.

5. **LOW, pre-existing/out of this diff** [notify/sender.py:72](/home/cms/project/BTC_Futures_E2E/notify/sender.py:72)  
   The older send-only notifier can log `str(e)` from opener failures without token redaction. I did not execute this path or read `.env`; the new `notify/telegram_api.py` command API does redact.

**Questions**

Q1: **OK** for explicit owner yes inside 60s TTL: owner allowlist, nonce match, stale/cancelled nonce rejection, non-owner callback answer, `/cmd@otherbot` rejection, private-message command gate, offset advance before handler all look safe. Caveat: finding #1 means “inside TTL” is too broad versus the +12s cancel rule.

Q2: **ISSUE**: finding #1.

Q3: **OK for new command API**, **ISSUE residual** in old `notify/sender.py`.

Q4: **ISSUE**: finding #2. Wallet-delta trade PnL is conceptually right for engine events, including funding/live extra-fee/adopted-fee wallet effects, but live liquidation may not produce the event the kill switch watches.

Q5: **ISSUE**: finding #3. Partial-exit mismatch is safely sticky; exchange-qty-zero exit becomes sticky via DB mismatch. Over-close can false-OK after flat.

Q6: **OK** for `adopted`: set only when LIVE failure path adopts larger same-direction `positionRisk`, not normal fills.

Q7: **ISSUE**: migrations/checksum, wide features, and latest-row safety state look OK; silent data loss in adopted commission is finding #4.

**Verdicts**

1. Adoption provenance: **FIX FIRST**  
2. Telegram forced close: **FIX FIRST**  
3. Kill switch + human resume: **FIX FIRST**  
4. Reconcile/stale/rate guard: **FIX FIRST**

Verification: focused pytest passed with `TMPDIR=/dev/shm .venv/bin/python -m pytest -q -s -p no:cacheprovider ...` for the requested test set.

Codex session ID: 01a0a4ec-b917-72c2-9c98-d6f06674be19
Resume in Codex: codex resume 01a0a4ec-b917-72c2-9c98-d6f06674be19
```

## 2026-09-15 — Codex 재검토 #1: layer 6·7 수정분 (`66272b4`, read-only · `task-mu2mkh2b-iwgaap`)
판정: 원 발견 #1~#5 **전부 CLOSED**. 새 발견 2건 → (1) 채택 FIX FIRST · (2) 텔레그램 FIX FIRST · **(3) 킬스위치 MERGE** · (4) 대사 FIX FIRST.

### 항목별 동의 여부와 조치 (실패 테스트 3개 → 수정 → green)
| Codex | 동의 | 조치 |
|---|---|---|
| 새 1 HIGH 청산 직전 거래소 수량이 **작으면** 수정 행이 수량을 덮어 사라진 0.004의 close·소실·지갑 기록이 없다 | ✅ | 줄어든 경우 사라진 수량을 `PositionVanished`(부분 청산·ADL·수동 감소 의심)로 내고 `PositionSynced`는 **늘어난 경우만** → DB: vanished close 행 + 청산 close 행으로 수량 전부 설명 · 킬스위치는 청산 1회로 발동 |
| 새 2 MEDIUM 정확히 +12초의 '예'가 tick 먼저면 거부·콜백 먼저면 실행(>= vs >) | ✅ | 콜백도 `>=` — 경계에서 처리 순서와 무관하게 실행 안 함(경계 −1ms 실행 · 경계 거부 · tick +12초 취소 테스트) |

### Codex 재검토 #1 원문 (verbatim)
```
**Per-Finding Status**

1. **CLOSED** — Callback now checks the no-answer deadline independently of ticks via `cancel_deadline_ms()` and rejects late confirmations. Evidence: [notify/bot.py](/home/cms/project/BTC_Futures_E2E/notify/bot.py:160), [notify/bot.py](/home/cms/project/BTC_Futures_E2E/notify/bot.py:228), [tests/test_notify_bot.py](/home/cms/project/BTC_Futures_E2E/tests/test_notify_bot.py:296).

2. **CLOSED** — LIVE exchange-flat exits now emit `PositionVanished`, and both kill switch observation and per-bar reconcile can trip on it. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:373), [safety/killswitch.py](/home/cms/project/BTC_Futures_E2E/safety/killswitch.py:63), [safety/gate.py](/home/cms/project/BTC_Futures_E2E/safety/gate.py:35).

3. **CLOSED for the original larger-quantity case** — Exit-time sync emits `PositionSynced` before `PositionClosed`, DB stores an amendment against the root, and remaining qty uses latest open amendment minus closes. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:384), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:398), [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:181), [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:244).

4. **CLOSED** — `EntryFilled` now carries total entry commission, including adopted estimates, and DB records it instead of recomputing only from fills. Evidence: [paper/types.py](/home/cms/project/BTC_Futures_E2E/paper/types.py:98), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:284), [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:221).

5. **CLOSED** — Legacy sender redacts the bot token from transport exception text before logging/stderr. Evidence: [notify/sender.py](/home/cms/project/BTC_Futures_E2E/notify/sender.py:73).

**New Findings**

1. **HIGH** — [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:384), [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:181)  
   Exit sync also amends downward when exchange qty is smaller than internal qty. Scenario: internal LONG `0.010`, exchange LONG `0.006`; `_exit` rewrites position qty to `0.006`, closes `0.006`, and DB becomes flat because `_remaining()` uses the latest open amendment. The missing `0.004` has no close/vanished event and no wallet accounting. This is a provenance/accounting regression.

2. **MEDIUM** — [notify/bot.py](/home/cms/project/BTC_Futures_E2E/notify/bot.py:136), [notify/bot.py](/home/cms/project/BTC_Futures_E2E/notify/bot.py:229)  
   Exact cancel-deadline behavior depends on ordering: `on_tick()` cancels at `now_ms >= deadline`, but callback execution allows `now_ms == deadline` because it rejects only `> deadline`. So a “yes” exactly at +12s executes if callback is processed first, but is rejected if tick runs first.

**Area Verdicts**

1. Adoption provenance: **FIX FIRST** due to the downward sync provenance/accounting gap.
2. Telegram forced close: **FIX FIRST** due to the deadline boundary race.
3. Kill switch + human resume: **MERGE**.
4. Reconcile/stale/rate guard: **FIX FIRST** because the downward sync can make DB/internal/exchange appear flat after losing unrecorded quantity.

Verification: `TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/dev/shm/hypothesis .venv/bin/python -m pytest -q -p no:cacheprovider tests/` passed. Worktree remained clean.

Codex session ID: 01a0a4f5-12c9-7af1-b02c-efcb0b4b7994
Resume in Codex: codex resume 01a0a4f5-12c9-7af1-b02c-efcb0b4b7994
```

## 2026-09-15 — Codex 재검토 #2: layer 6·7 (`e2167cb`, read-only · `task-mu2mqfkh-o1j9e7`)
판정: 재검토 #1 발견 2건 **CLOSED** · 새 발견 없음 · 부분 소실 킬스위치 발동 "acceptable/safe". **(1) 채택 출처 · (2) 텔레그램 강제 청산 · (3) 킬스위치 · (4) 대사·stale·rate — 전부 MERGE.** (Codex가 전체 테스트 통과 확인)

### Codex 재검토 #2 원문 (verbatim)
```
No new findings. Both re-review #1 findings are **CLOSED**.

**Per-Finding Status**
1. **CLOSED** — Downward exit-sync no longer overwrites quantity with an amendment. `_exit` emits `PositionVanished` for the missing slice, only emits `PositionSynced` when exchange qty increased, then closes the exchange-visible qty. Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:397), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:403), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:420), [tests/test_paper_engine.py](/home/cms/project/BTC_Futures_E2E/tests/test_paper_engine.py:702).

2. **CLOSED** — Telegram callback deadline now matches tick cancellation at the boundary: `now_ms >= cancel_deadline_ms(p)`. Evidence: [notify/bot.py](/home/cms/project/BTC_Futures_E2E/notify/bot.py:160), [notify/bot.py](/home/cms/project/BTC_Futures_E2E/notify/bot.py:229), [tests/test_notify_bot.py](/home/cms/project/BTC_Futures_E2E/tests/test_notify_bot.py:306).

**Regression Checks**
`paper/engine.py::_exit`: downward path is now `EntriesBlocked` diagnostic, then `PositionVanished`, then `PositionClosed`; vanished qty is recorded with unknown PnL, while the remaining exchange qty gets normal close PnL/commission wallet accounting. Upward path still emits `PositionSynced` before close and charges estimated extra entry commission. See [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:384).

`db/record.py`: vanished + close sequences work with `_remaining()` as latest open amendment minus close rows; partial vanish leaves remaining qty, then the close flattens it. Evidence: [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:181), [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:257), [tests/test_db.py](/home/cms/project/BTC_Futures_E2E/tests/test_db.py:498).

Kill switch on partial vanish: **acceptable/safe**. Any exchange-side disappearance has unknown PnL/provenance, so tripping `position_vanished` is conservative and human-resumable. Evidence: [safety/killswitch.py](/home/cms/project/BTC_Futures_E2E/safety/killswitch.py:63), [safety/killswitch.py](/home/cms/project/BTC_Futures_E2E/safety/killswitch.py:92).

`notify/bot.py` boundary: fixed and covered at boundary -1ms, exact boundary, and tick cancellation at +12s.

**Area Verdicts**
1. Adoption provenance: **MERGE**
2. Telegram forced close: **MERGE**
3. Kill switch + human resume: **MERGE**
4. Reconcile/stale/rate guard: **MERGE**

Verification passed: `TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/dev/shm/hypothesis .venv/bin/python -m pytest -q -p no:cacheprovider tests/`. Worktree stayed clean.

Codex session ID: 01a0a4f9-50c9-7e02-878f-f5148dddd3e7
Resume in Codex: codex resume 01a0a4f9-50c9-7e02-878f-f5148dddd3e7
```

## 2026-09-16 — 사용자 결정(#11·#12·#13) · layer 8 `ops/` 배선 · 페이퍼 드라이런 #1

**사용자 지시(2026-09-16)**: layers 6/7 + 채택 수정 수용 · 로컬 6커밋 푸시(`3758daf..0f2e0e8` 완료) · 결정 5건 → 레지스트리 행 · layer 8 + 부분 청산 행을 한 Codex 배치로 · 드라이런(피드 → 엔진 → DB → 텔레그램, 거래소 쓰기 없음) 후 보고, VPS 배포는 그다음 논의.

**구현(커밋)**: `4491a86` 레지스트리 #11–#13 · 킬스위치/stale/게이트 · 엔진 `PositionReduced`·`vanish`·차단 목록·equity·지갑 재동기화 · db 행 / `2dff230` `ops/runtime.py` / `e6dbfa6` `ops/run_bot.py`·`ops/telegram_link.py` / `b02a28d` 배달 증거(message_id) / `044cdcd` VPS 템플릿·prune·sync·health·런북.

**해석 기록(보고 대상)**
- #12 "stale data"를 레지스트리 #1의 **세 스트림 전부**(kline1m_update·kline1m_close·markprice)로 읽었다 — markprice만이 아니다(보수 쪽).
- #12 청산 조건 = 나이 규칙(마지막 수신 > grace 120초). #1의 분당 규칙으로만 정지면 진입만 막고 청산하지 않는다(새 숫자를 만들지 않기 위해).
- 드라이런은 **바이낸스 키를 쓰지 않았다**: 서명 엔드포인트(leverageBracket·commissionRate)는 2026-09-02 캡처 스냅샷, exchangeInfo·fundingInfo는 공개 GET. 실계정 읽기는 사용자 실행 캡처 스크립트 몫으로 남겼다(Codex 검토 + 사용자 승인 규칙).
- 드라이런 셸에만 `TELEGRAM_OWNER_IDS=$TELEGRAM_CHAT_ID`(개인 채팅이면 chat.id == from.id) — `.env`는 수정하지 않았다. 값은 출력하지 않았다(양의 정수 형식만 확인).

**드라이런 #1** (2026-09-15 15:44:30–15:48:46 UTC · `--duration-s 250` · `var/dryrun-20260916/`)
| 항목 | 값 |
|---|---|
| 종료 | exit 0 · 기록기 `stop`(clean, dropped=0) |
| 규칙 | exchangeInfo=rest(15:44:30Z) · fundingInfo=rest · leverageBracket·commissionRate=snapshot(2026-09-02) → `runtime_rules` 4행 |
| 봉 | REST 백필 29(inserted 29 · conflict 0) + WS 마감 4 · 경계 연속(rest 마지막 open 1789486980000 → ws 첫 1789487040000) |
| 틱 | mark 250 · 안전 틱 250 · stale 청산 0 · 정지 스트림 없음 · 차단 사유 없음 |
| 전달 | kline1m_update 직전 분 159 · kline1m_close 1 · markprice 60 |
| DB | account_snapshots engine 5(bar 4 + shutdown) · safety_state 1(첫 저장, 이후 변화 없음) · positions/orders/decisions 0(전략 없음 — 진입 경로는 재생 테스트) · db_errors 0 |
| shard | kline1m_update 5파일 641행 · kline1m_close 3파일 4행 · markprice 5파일 250행 · 대장 connect 2 · disconnect 2 · stop 1 |
| 텔레그램 | 폴 오류 0(409 없음) · setMyCommands · 발송 1(기동) — ⚠️ 이 실행은 배달 `message_id`를 기록하지 않았고 정지 알림 발송 전에 상태를 썼다 → `b02a28d`에서 수정, 드라이런 #2에서 확인 |
| 거래소 쓰기 | 없음 — 공개 클라이언트는 `ReadOnlyClient(CcxtRestClient())`(키 없음), 러너에 `LiveSender` 경로 없음 |

**드라이런 뒤 추가**: `b02a28d` 배달 증거 · `044cdcd` VPS 템플릿 · 러너 경로 절대경로화(shard 대장 path = prune 대조 키).

### Codex 검토: layer 8 + 부분 청산 (`0f2e0e8..044cdcd`, read-only · `task-mu2uwybx-8790gs`)
판정: A engine/db MERGE · B runtime FIX FIRST · C safety FIX FIRST · D prune FIX FIRST · E health/systemd MERGE.

| # | 지적 | 동의 | 조치 |
|---|---|---|---|
| 1 HIGH | 운영 이벤트·안전 상태 저장 실패가 버려져 DB 잠김 중 킬스위치 트립이 재기동에서 사라질 수 있다 | ✅ 동의 — 코드로 확인(`record_ops`·`save_state`가 로그만) | 보관·틱마다 재시도 + `db:unrecorded_ops`·`db:unsaved_safety_state` 진입 금지 · 테스트 중 발견: 봉의 DB 읽기(`open_position_state`) 실패가 피드 콜백 밖으로 새어 프로세스를 죽였다 → `db:read_failed` 차단으로 흡수 |
| 2 HIGH | `rclone lsf` 실패·누락이어도 삭제해 md5 없는 유일본이 생긴다 | ✅ 동의 | 모든 대상의 원격 md5가 있어야 삭제 · 하나라도 없으면 그날 전체 보류(파라미터 테스트 2종) |
| 3 MEDIUM | LIVE 거래소 읽기가 루프 스레드에서 동기 | ✅ 동의 — 단 러너가 LIVE를 거부해 PAPER에서는 호출 경로 없음 | 코드 변경 대신 **LIVE 배선 선결 조건**으로 설계서 §10 체크리스트·런타임 docstring에 명시 |
| 4 LOW | 폴 스레드가 `bot.pending`/`alerts`를 읽는다(소유권 문구 위반) | ✅ 동의 | 루프 스레드가 세우는 `threading.Event fast_poll`만 넘긴다 |

```
Codex session ID: `01a0a5ca-fee4-7482-8847-bbf7c4711c3d`  
Reviewed range: `0f2e0e8..044cdcd6d5b7da79678f4be9a4c3925f943e1318`  
Verification: `TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/dev/shm/hypothesis .venv/bin/python -m pytest -q -p no:cacheprovider tests/` passed.  
Worktree remained clean.

1. [HIGH] Safety/ops DB writes are not retained or retried, so a kill-switch trip can be lost across restart.
Evidence: `ops/runtime.py:311-329` retries only `record_events`; `ops/runtime.py:333-339` records kill-switch trips via `record_ops` and `save_state`; `ops/runtime.py:366-372` drops failed ops-event writes after logging; `ops/runtime.py:406-416` drops failed safety-state saves after logging.
Scenario: sqlite is locked or unavailable when daily loss trips. The in-memory gate blocks entries, but `KillSwitchTripped` and `safety_state` fail to persist. If the process restarts before a later successful bar save, the restored gate may not know daily-loss was tripped, allowing unsafe entries.
Suggested fix: add retry queues for ops events and dirty safety-state writes, and expose a `db:` entry blocker until both are durably saved.

2. [HIGH] Prune can delete files even when remote md5 collection failed or is incomplete.
Evidence: `ops/prune.py:75-82` returns `{}` when `rclone lsf` fails; `ops/prune.py:119-131` still unlinks files when hashes are missing; `ops/prune.py:140-142` only reports `remote_md5_recorded`; `ops/prune.py:162-171` can still mark the run healthy if ledger count matches deletion count.
Scenario: `rclone check` reports `=`, then `rclone lsf --format hp` fails or omits rows. Apply mode deletes local parquet files and marks prune success, but the ledger lacks remote md5s, breaking later verification of the only remaining copy.
Suggested fix: in apply mode, require remote hashes for every deletion target before unlinking anything. Missing hash should fail/hold the whole day and leave files untouched.

3. [MEDIUM] LIVE runtime paths perform synchronous exchange reads on the asyncio loop.
Evidence: `ops/runtime.py:196-198` calls `exchange.position_risk()` in `on_bar_close`; `ops/runtime.py:224-229` calls `exchange.account()` for wallet resync; `ops/runtime.py:392-394` calls `exchange.account()` for snapshots; `ops/run_bot.py:265-273` runs safety ticks and feed on the same asyncio loop.
Scenario: in future LIVE wiring, a signed GET stalls for 30s. During that time safety ticks, stale close retries, Telegram command handling, and feed callbacks can be delayed on the single owner loop.
Suggested fix: make `ExchangeReader` async with explicit timeouts, or run blocking reads through a bounded executor/worker queue and feed results back onto the loop thread.

4. [LOW] Telegram poll thread reads `CommandBot` state despite the “threads only touch queues/fetch/execute” ownership claim.
Evidence: `ops/run_bot.py:237-238` passes `fast=lambda: bot.pending is not None or bool(bot.alerts)` into `TelegramLink`; `ops/telegram_link.py:40-45` calls that from the poll thread.
Scenario: the loop thread mutates `bot.pending`/`bot.alerts` while the poll thread reads them. This likely only affects polling speed, but it violates the documented ownership boundary.
Suggested fix: keep a thread-safe fast-poll flag owned by the runtime/link, or always use a fixed short poll timeout when confirmation/alert latency matters.

Per-area verdicts:

A. engine/db partial-close + vanish + wallet resync: MERGE. Partial close accounting, DB remaining qty, vanish, wallet resync, and `last_flat_wallet` handling match the stated contract.

B. runtime/runner/threading/telegram: FIX FIRST. LIVE loop blocking and the poll-thread state read should be corrected or explicitly scoped out before relying on this architecture for live trading.

C. safety decisions #11-#13: FIX FIRST. Runtime behavior is mostly correct, but kill-switch/ops persistence on DB failure is not durable enough.

D. prune/sync/data stores deletion: FIX FIRST. The md5-before-delete invariant is not enforced.

E. health + systemd + runbook: MERGE. OnFailure placement, oneshot shape, `%h` paths, collector-priority settings, first-deploy prune instructions, data-freshness health, fixed alert keys, throttling, and send-failure behavior look aligned.

Codex session ID: 01a0a5ca-fee4-7482-8847-bbf7c4711c3d
Resume in Codex: codex resume 01a0a5ca-fee4-7482-8847-bbf7c4711c3d
```

### Codex 재검토 #1: layer 8 수정분 (`044cdcd..225a538`, read-only · `task-mu2v78yb-h5a24f`)
판정: A engine/db FIX FIRST · B runtime MERGE(PAPER 한정) · C safety FIX FIRST · D prune MERGE · E health/systemd MERGE.

| # | 상태 | 조치 |
|---|---|---|
| 1 | PARTIAL — DB 장애 중 재기동하면 메모리의 보관 이벤트·저장 실패 표시가 사라져 트립을 잃는다 | ✅ 동의 → **DB 밖 breadcrumb**(`var/run/safety_unsaved.json`, 원자적): 저장 실패·운영 이벤트 보관 중 게이트 상태·이벤트를 쓰고 DB에 다 들어간 뒤에만 삭제. 러너 기동 시 있으면 게이트를 그 상태로 복원 + `system:restart_with_unsaved_safety_state` 일시정지 + 이벤트 재기록 + 알림. 해석 불가면 일시정지하고 파일 보존(fail-closed) |
| 2 | CLOSED | — |
| 3 | CLOSED(PAPER 한정) — LIVE 배선 전 FIX FIRST | 설계서 §10 체크리스트 유지 |
| 4 | CLOSED | — |

```
Codex session ID: `01a0a5d2-516f-7ff3-8ad8-a6dc6d072216`  
Reviewed range: `044cdcd6d5b7..225a538a641c`  
Verification: `TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/dev/shm/hypothesis .venv/bin/python -m pytest -q -p no:cacheprovider tests/` passed.  
Worktree remained clean.

**Per-Finding Status**

1. **PARTIAL** — transient DB outage handling is fixed, but restart durability is still not fixed.
Evidence: retry queues/blockers now exist in [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:121), [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:145), [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:356), [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:410), [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:454). The regression test verifies retry/no duplicate insert after recovery in [tests/test_ops_runtime.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_runtime.py:371).

Residual scenario: if sqlite is unavailable when a kill-switch trip happens and the process restarts before `_retry_unrecorded()`/`save_state()` succeeds, the in-memory `unrecorded_ops` and `state_save_failed` are lost. Startup restores only DB state: wallet at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:220), safety state at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:223), [safety/gate.py](/home/cms/project/BTC_Futures_E2E/safety/gate.py:87), and [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:462). There is no durable fallback for the failed trip before restart.

Bar-close DB read failure is improved: it sets `db:read_failed` and returns from the feed callback at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:223), [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:230), while existing sticky reconcile blockers are not overwritten by non-sticky success/failure paths in [safety/reconcile.py](/home/cms/project/BTC_Futures_E2E/safety/reconcile.py:65).

Fix: persist a fail-closed restart breadcrumb outside the main failing DB path, or make startup refuse entries/start in a recoverable maintenance state after an unsaved safety-state/write-failure status.

2. **CLOSED** — apply-mode prune now requires a non-empty remote md5 for every deletion target before unlinking.
Evidence: `lsf` failure returns no hashes at [ops/prune.py](/home/cms/project/BTC_Futures_E2E/ops/prune.py:76); apply mode holds the whole day before deletion if any target lacks a hash at [ops/prune.py](/home/cms/project/BTC_Futures_E2E/ops/prune.py:120); deletion uses required hashes at [ops/prune.py](/home/cms/project/BTC_Futures_E2E/ops/prune.py:130). Ledger/marker health still fails on skipped/gapped runs at [ops/prune.py](/home/cms/project/BTC_Futures_E2E/ops/prune.py:164). Tests cover dry-run, ledger gap, lsf failure, and partial lsf listing in [tests/test_ops_vps.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_vps.py:141), [tests/test_ops_vps.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_vps.py:179), [tests/test_ops_vps.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_vps.py:320).

3. **CLOSED for a PAPER-only merge** — LIVE synchronous exchange reads remain, but the scope-out is acceptable here because the runner refuses LIVE and PAPER cannot receive an `ExchangeReader`.
Evidence: LIVE refusal at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:176), mode/exchange invariant at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:108), LIVE-only sync reads at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:207), and the LIVE checklist prerequisite at [docs/design_v1.md](/home/cms/project/BTC_Futures_E2E/docs/design_v1.md:131). This remains FIX FIRST before any LIVE wiring.

4. **CLOSED** — poll thread no longer reads `CommandBot`/engine state.
Evidence: loop-owned `threading.Event` at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:125), loop thread sets/clears it at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:311), runner passes only `rt.fast_poll.is_set` at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:237), and poll thread only calls `fast()` at [ops/telegram_link.py](/home/cms/project/BTC_Futures_E2E/ops/telegram_link.py:39). Test coverage: [tests/test_ops_runtime.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_runtime.py:393).

**New Findings**

No new findings beyond the residual restart-durability gap from previous finding #1.

**Area Verdicts**

A. engine/db: **FIX FIRST** due to the remaining restart-loss path for unsaved safety/ops state.

B. runtime/runner/threading/telegram: **MERGE** for PAPER-only. LIVE sync reads are explicitly blocked/scoped before LIVE.

C. safety #11-#13: **FIX FIRST** because a kill-switch trip can still be lost across restart if DB recovery has not happened yet.

D. prune/sync/data stores: **MERGE**.

E. health/systemd/runbook: **MERGE**.

Codex session ID: `01a0a5d2-516f-7ff3-8ad8-a6dc6d072216`  
Resume in Codex: `codex resume 01a0a5d2-516f-7ff3-8ad8-a6dc6d072216`

Codex session ID: 01a0a5d2-516f-7ff3-8ad8-a6dc6d072216
Resume in Codex: codex resume 01a0a5d2-516f-7ff3-8ad8-a6dc6d072216
```

### Codex 재검토 #2: breadcrumb (`225a538..231122a`, read-only · 세션 `01a0a5d8-b770-7220-92dc-97963b2f6188`)
판정: A MERGE · B FIX FIRST · C FIX FIRST · D MERGE · E MERGE.

| # | 지적 | 동의 | 조치 |
|---|---|---|---|
| 1 PARTIAL | 원래 재기동 손실 경로는 닫힘 · breadcrumb 수명 주기 엣지 2건 | ✅ | 아래 |
| 새 1 MEDIUM | 읽을 수 있는 **오래된** breadcrumb가 더 새로운 DB 상태를 무조건 덮는다(삭제 실패·잔존 시) | ✅ | 기동 시 breadcrumb `ts_ms` ≤ DB `safety_state` 최신 `ts_ms`면 복원하지 않고 `safety_unsaved.stale-<ts>.json`으로 격리 · 진입 일시정지·알림은 유지 |
| 새 2 LOW | 재생 중 삽입 후 breadcrumb 갱신 전에 죽으면 운영 이벤트 이중 기록 | ✅ | 운영 이벤트마다 `op_id`(uuid) · `record_ops_event(op_id=)` 멱등(같은 mode·kind·op_id 있으면 건너뜀, `payload_json.op_id`) · 재시도 진행마다 breadcrumb 재기록 |

```
Codex session ID: `01a0a5d8-b770-7220-92dc-97963b2f6188`

**Per-Finding Status**

1. **PARTIAL**: the original restart-loss path is closed, but the breadcrumb lifecycle still has edge-case regressions.

Evidence for closed part: trip handling observes before DB recording at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:339), records the kill-switch op and saves state at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:381), writes a breadcrumb on ops-record failure at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:422), writes on safety-state save failure at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:471), and startup restores it before entries can run at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:230).

Edge checks:
- Breadcrumb before crash on trip path: **OK** via [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:383) -> [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:425) / [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:477).
- Breadcrumb deletion vs later failure: **OK in the single runtime thread**; later ops failures rewrite it at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:414).
- Pause cannot be silently cleared except by human `/start`: **OK**; pause is restored at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:239), and clear goes through resume at [safety/gate.py](/home/cms/project/BTC_Futures_E2E/safety/gate.py:64).
- Daily-loss day `/start` no-op after restore: **OK** via [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:587) and [safety/killswitch.py](/home/cms/project/BTC_Futures_E2E/safety/killswitch.py:96).
- `SafetyGate.load` behavior unchanged: **OK**; it delegates to equivalent `from_state` at [safety/gate.py](/home/cms/project/BTC_Futures_E2E/safety/gate.py:90).
- Ops events not double-recorded: **PARTIAL**, see new finding #2.

**New Findings**

1. **MEDIUM**: stale readable breadcrumb unconditionally overrides newer DB safety state.
Scenario: if breadcrumb deletion fails after DB durability, or an old breadcrumb is left behind, startup loads DB state at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:227) but then always replaces it from the file at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:233). `_clear_breadcrumb_if_durable` only logs unlink failure at [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:493). Fix: compare breadcrumb `ts_ms` or generation against latest `safety_state` and quarantine older breadcrumbs instead of restoring them.

2. **LOW**: ops events can be duplicated if the process crashes during breadcrumb replay/retry after the DB insert but before breadcrumb rewrite/delete.
Scenario: startup replays every breadcrumb op at [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:244), but the file is not cleared until [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:248). `engine_events` has no uniqueness key at [db/schema.py](/home/cms/project/BTC_Futures_E2E/db/schema.py:202), and `record_ops_event` always inserts at [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:332). Fix: add a stable idempotency key for queued ops, or rewrite breadcrumb progress after each successful replay.

**Verification**

Ran requested command read-only with temp/cache outside repo:

`TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/dev/shm/hypothesis .venv/bin/python3 -Bc "import pytest,sys; sys.exit(pytest.main(['-q','-p','no:cacheprovider','tests/']))"`

Result: passed. Worktree remained clean.

**Area Verdicts**

A. engine/db: **MERGE**
B. runtime/runner/threading/telegram: **FIX FIRST**
C. safety #11-#13: **FIX FIRST**
D. prune/sync/data stores: **MERGE**
E. health/systemd/runbook: **MERGE**
```

### Codex 재검토 #3: breadcrumb 신선도·멱등 (`231122a..4e7c758`, read-only · 세션 `01a0a5de-c740-75a2-9329-303e2d797a2a`)
판정: A·B·C FIX FIRST · D·E MERGE.

| # | 지적 | 동의 | 조치 |
|---|---|---|---|
| 멱등 재생 | CLOSED | — | — |
| 새 1 MEDIUM | 신선도를 `ts_ms`로 판정 — 이벤트 시각(breadcrumb)과 벽시계(재시도·종료 저장)가 섞여 **진짜 새 트립이 격리될 수 있다**(Codex가 /dev/shm에서 재현) | ✅ 동의 — 내가 넣은 `db_ts >= crumb_ts`가 원인 | 신선도 = **행 id**: `save_safety_state`가 id 반환 → 런타임 `saved_state_id` → breadcrumb `base_state_id`. 기동 시 DB 최신 id > 기준 id **이고** breadcrumb에만 있는 트립이 없을 때만 격리 · 기준 id 없음(옛 형식)·트립만 breadcrumb에 있음 → 복원(fail-closed). Codex 시나리오 그대로 테스트 |
| 성능 메모 | `engine_events`에 op_id 조회 인덱스 없음 | 기록 | 운영 이벤트는 하루 수십 건 규모 — 인덱스는 새 스키마 단계(v3)가 필요해 보류, 보고 항목 |

```
Codex session ID: `01a0a5de-c740-75a2-9329-303e2d797a2a`

**Per-Finding Status**
1. Re-review #2 finding #1: **PARTIAL**. The breadcrumb restore path exists, but a real newer breadcrumb can still be quarantined as stale because freshness is based on mixed-domain `ts_ms`.
2. New #1 stale breadcrumb override: **PARTIAL**. Old breadcrumbs no longer blindly override DB state, but the `db_ts >= crumb_ts` test can misclassify.
3. New #2 duplicate ops replay: **CLOSED** for new/fixed breadcrumbs. `op_id` is generated in `ops/runtime.py:417`, persisted into breadcrumbs at `ops/runtime.py:487`, replayed/fallbacked at `ops/run_bot.py:247`, and deduped in `db/record.py:342`. Legacy breadcrumbs without `op_id` get deterministic fallback IDs, but rows already inserted by pre-fix code without an `op_id` cannot be deduped retroactively.

**New Findings**
1. **MEDIUM**: Real unsaved trip can be quarantined as stale due to mixed timestamp domains.
   Evidence: startup uses `max(ts_ms)` from `safety_state` and quarantines when `db_ts >= crumb_ts` at `ops/run_bot.py:237`. Breadcrumb `ts_ms` is written from event/retry time at `ops/runtime.py:417` and `ops/runtime.py:483`, while DB safety saves may use wall-clock retry/shutdown time at `ops/runtime.py:270` and `ops/run_bot.py:325`. Scenario: DB has a later wall-clock normal safety row, then a DB-outage trip writes a breadcrumb with older market-event `ts_ms`; restart quarantines it, leaving `kill_switch.tripped` lost, though entries are paused. Reproduced in `/dev/shm`: latest DB state remained `tripped=None`, pause set, breadcrumb quarantined.
   Fix: do not decide breadcrumb staleness solely from `ts_ms`. Use a monotonic safety-state generation/latest row id, or compare state content and restore/fail-closed whenever the breadcrumb contains a trip/blocker not present in DB. At minimum, avoid treating equal timestamps as stale.

**Idempotency / Perf Notes**
`json_extract(payload_json, '$.op_id')` is functionally correct in this environment; the full suite passed. There is no index on `engine_events` for this lookup (`db/schema.py:202`), so idempotent inserts scan growing history by `mode/kind/op_id`. That is a scaling concern, not the merge blocker here.

**Verification**
Requested command passed:
`TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/dev/shm/hypothesis .venv/bin/python -m pytest -q -p no:cacheprovider tests/`

Worktree remained clean before and after (`git status --short` empty).

**Area Verdicts**
A. engine/db: **FIX FIRST**
B. runtime/runner/threading/telegram: **FIX FIRST**
C. safety #11-#13: **FIX FIRST**
D. prune/sync/data stores: **MERGE**
E. health/systemd/runbook: **MERGE**
```

### Codex 재검토 #4: 행 id 신선도 (`4e7c758..d20d8a1`, read-only · 세션 `01a0a5e4-0435-7972-8afe-04893a98e5fe`)
판정: **A·B·C·D·E 전부 MERGE** · 새 지적 없음. 남은 동작(의도): 사람이 이미 푼 트립이 오래된 breadcrumb에만 남아 있으면 재기동 때 다시 걸린다(fail-closed · 진입 일시정지 + 알림 · 사람의 /start로 해제).

```
Codex session ID: `01a0a5e4-0435-7972-8afe-04893a98e5fe`

Read-only re-review of `d20d8a1` over `4e7c758..d20d8a1`: **no edits, no git writes, no external network tools used**. Worktree check after tests: clean for tracked and untracked files.

**Per-Finding Status**
`Codex re-review #3 new finding #1 MEDIUM`: **CLOSED**.

Evidence:
- `save_safety_state()` now returns the inserted durable row id: db/record.py:465
- `latest_safety_state_id()` reads the latest durable generation by row id: db/record.py:473
- `SafetyGate.save()` returns that id: safety/gate.py:86
- Runtime records `saved_state_id` on successful changed-state save: ops/runtime.py:473
- Breadcrumb writes `base_state_id`: ops/runtime.py:489
- Startup initializes `rt.saved_state_id` from DB latest id on every run: ops/run_bot.py:259
- Startup quarantines only when `latest_id > base_id` and no breadcrumb-only trip exists: ops/run_bot.py:240
- Mixed-clock regression test covers the original failure mode: tests/test_ops_run_bot.py:327

**Residual Behavior**
No remaining path found that loses a kill-switch trip silently across restart. Breadcrumb-only trips are restored even when DB has a later row: ops/run_bot.py:241.

A stale breadcrumb can still re-impose a trip a human already cleared if the file is old but contains a trip absent from DB. That is intentional fail-closed behavior under this patch: startup restores it, pauses entries with `system:restart_with_unsaved_safety_state`, and persists that pause: ops/run_bot.py:256, ops/run_bot.py:264. For stale pause/reconcile-only breadcrumbs, exact old blocker content may be quarantined, but entries are still paused.

`saved_state_id` correctness looks good. Unchanged-state saves do not create a new row and do not need to change `saved_state_id`: ops/runtime.py:466. Across runs, it is refreshed from DB latest id at startup: ops/run_bot.py:259. Successful changed-state saves update it to the new row id: ops/runtime.py:473.

**New Findings**
None.

**Verification**
Requested command passed:

`TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 HYPOTHESIS_STORAGE_DIRECTORY=/dev/shm/hypothesis .venv/bin/python -m pytest -q -p no:cacheprovider tests/`

Result: exit code `0`, full suite passed.

**Area Verdicts**
- `(A) engine/db`: **MERGE**
- `(B) runtime/runner/threading/telegram`: **MERGE**
- `(C) safety #11-#13`: **MERGE**
- `(D) prune/sync/data stores`: **MERGE**
- `(E) health/systemd/runbook`: **MERGE**
```

### 드라이런 #2 · #3 (거래소 쓰기 없음 · 키 없음 · 실제 공개 피드 · 실제 텔레그램)
| 항목 | #2 (`231122a` · 16:13:34–16:17:46 UTC) | #3 (**최종 `d20d8a1`** · 16:29:07–16:33:17 UTC) |
|---|---|---|
| 종료 | exit 0 · `stop` clean dropped=0 | exit 0 · `stop` clean dropped=0 |
| 규칙 | exchangeInfo·fundingInfo rest · 서명 2종 snapshot(2026-09-02) | 같음 |
| 봉 | REST 29 + WS 4 · 경계 연속 · conflict 0 | REST 29 + WS 4 · 경계 연속(rest 마지막 1789489680000 → ws 첫 1789489740000) · conflict 0 |
| 틱/안전 틱 | 250 / 250 · stale 청산 0 · 정지 없음 · 차단 없음 | 249 / 250 · 같음 |
| 전달(직전 분) | update 159 · close 1 · markprice 60 | update 125 · close 1 · markprice 60 |
| DB | account_snapshots engine 5 · safety_state 1 · Backfill 이벤트 · db_errors 0 | 같음 + 운영 이벤트 `op_id` 기록 확인 · breadcrumb 파일 없음 |
| shard | update 5파일 666행 · close 2파일 4행 · markprice 5파일 250행 | update 5파일 527행 · close 3파일 4행 · markprice 5파일 249행 |
| 텔레그램 | 발송 2 · **배달 2**(message_id 응답) · 폴 오류 0 · send_errors 0 | 발송 2 · **배달 2** · 폴 오류 0 · send_errors 0 |
| 참고 | 첫 백그라운드 실행은 환경(메모리 경고)이 SIGTERM으로 끊었고 러너가 38초 만에 clean 종료·정지 알림까지 했다(정상 종료 경로 실측) — 그 데이터는 버리고 전경으로 재실행 | — |

## 2026-09-16 — 사용자 결정 #14 · (a) 페이퍼 재기동 복원 · (ii) 런타임 규칙 · Codex 배치

**사용자 지시(2026-09-16)**: layer 8 수용 · 11커밋 푸시(`0f2e0e8..db13657` 완료) · #12 정정(markprice만 청산) → 대체 행 ·
(a) DB 열린 행 + 마지막 엔진 스냅샷 일치 시에만 복원, 불일치면 flat·진입 차단·알림 · (ii) 읽기 전용 키로 런타임 조회,
스냅샷은 fixture + 진입 차단 fallback(`rules_from_snapshot`) · health 값 승인(sync >3h · prune >8d · 텔레그램 폴 10분 · 디스크 <5GB) ·
배포는 E2E Restart B(09-17 00:12 UTC) 24h 게이트 뒤(earliest 09-18) · 라이브 호스트 변경 하루 1건.

**정정(2026-09-16, 이전 기록 수정 없이 덧붙임)**: 위 layer 8 항목의 해석 기록 "#12 stale data = 세 스트림 전부"는 사용자가
**markprice만**으로 정정 → 레지스트리 #14(`a899a1a`).

**구현**: `a899a1a` #14 · `1608073` (a)·(ii)·드라이런 하네스 · Codex 1차 반영 커밋(아래).
해석 기록(보고 대상):
- 불일치 시 DB의 열린 행은 `restart_unrestored` close 행(손익 없음)으로 닫는다 — 닫지 않으면 대사 sticky가 매 봉 다시 걸려 /start로 풀 수 없다. 킬스위치는 세지 않는다(거래 결과 아님).
- 불일치 차단은 `SafetyGate.pause("system:restart_position_mismatch")`(safety_state에 저장 · /start로 해제).
- 키 권한 조회가 **전송 오류**로 실패하면 기동 거부가 아니라 fallback + 진입 차단(권한이 확인된 거래 권한 키만 종료 코드 4).
- 런타임 규칙은 기동 때만 읽는다(주기 재조회 없음 — TODO 5f).

### Codex 검토: #14 + (a) + (ii) + 하네스 (`db13657..1608073`, read-only · `task-mu33w506-t6zb9q`)
| # | Codex | 동의 | 조치 |
|---|---|---|---|
| 1 HIGH | 복원 뒤 FundingMissed 엔진 차단이 메모리에만 있어 두 번째 재기동에서 사라진다 | ✅ | 엔진 차단 사유 전체를 `safety_state.engine_blocks`로 저장·기동 때 엔진에 복원 · EntriesBlocked마다 저장 · /start 해제도 저장 |
| 2 HIGH | 복원 대조가 `entry_commission`·`liq_price_est`를 검증하지 않는다 | ✅ | 진입 수수료 = open 행 합과 대조 · 추정 청산가는 복원 때 현재 규칙으로 재계산(계산 불가 → 불일치) · 알림에 재계산 값 |
| 3 MEDIUM | fallback 사유에 ccxt 예외의 서명 URL(signature·timestamp·recvWindow)이 남아 알림·상태 파일로 간다 | ✅ | `safe_error`: URL 쿼리·API 키 헤더·서명 파라미터·키 값 구조적 제거 · 300자 |
| 4 MEDIUM | 키를 실은 클라이언트의 첫 요청이 `sync_time`(권한 조회 전) | ✅ | 시각 오프셋은 키 없는 클라이언트로 받아 옮김 → 키 클라이언트의 첫 요청 = apiRestrictions |
| 5 LOW | 하네스가 자식 프로세스 환경에서 키를 지우지 않는다 | ✅ | `child_env`로 Popen·러너 환경 모두 정리 |

<details><summary>Codex 원문 (verbatim)</summary>

```
Read-only review complete. I did not modify files, did not use the network, and did not read `.env`. Tests passed: `TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q` with only read-only cache warnings.

1. [HIGH] FundingMissed entry block is lost after a second restart

Evidence: [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:151), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:154), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:292), [safety/gate.py](/home/cms/project/BTC_Futures_E2E/safety/gate.py:82), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:203)

Scenario: restore crosses a funding boundary, first tick emits `FundingMissed` and adds an engine block. That block is only `Engine.entries_blocked`; it is not in `safety_state`, not in `position_state`, and not restored from `engine_events`/`funding_events`. After any later snapshot advances `next_funding_ms`, a second restart can restore the position with no engine block and allow entries even though funding was never settled.

Suggested fix: persist unresolved engine blocks, or specifically treat any open-position `funding_events.missed=1` after the root open as a restored engine/safety blocker until human `/start`.

2. [HIGH] Restore agreement does not verify restored risk fields

Evidence: [ops/restore.py](/home/cms/project/BTC_Futures_E2E/ops/restore.py:101), [ops/restore.py](/home/cms/project/BTC_Futures_E2E/ops/restore.py:105), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:208), [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:221), [db/record.py](/home/cms/project/BTC_Futures_E2E/db/record.py:224)

Scenario: DB and snapshot can agree on direction/qty/entry/leverage/SL/TP/opened/funding, while the snapshot carries a stale or corrupted `liq_price_est` or `entry_commission`. The restore code only checks those fields are parseable, then the engine adopts them. At 50–100x this can make paper liquidation ordering and liquidation-loss accounting wrong after restart.

Suggested fix: include `entry_commission_usdt` in the DB comparison, and either recompute `liq_price_est` from entry + funding + current rules during restore or record/compare an explicit liquidation-estimate state row.

3. [MEDIUM] Signed-rule fallback can leak signed request material

Evidence: [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:183), [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:222), [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:530), [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:163), `.venv/lib/python3.12/site-packages/ccxt/base/exchange.py:649`

Scenario: `_redact` only replaces literal key/secret values. ccxt network exceptions include the full request URL; signed GET URLs include `timestamp`, `recvWindow`, and `signature`. That fallback reason is put into alerts and `status.json`.

Suggested fix: sanitize exception text structurally: strip query params such as `signature`, `timestamp`, `recvWindow`, redact API headers, and avoid storing raw ccxt exception strings in user-visible status/alerts.

4. [MEDIUM] Permission check is not the first use of the key-configured client

Evidence: [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:206), [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:208), [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:216), [exchange/ccxt_rest.py](/home/cms/project/BTC_Futures_E2E/exchange/ccxt_rest.py:100)

Scenario: with `BINANCE_API_KEY/SECRET`, the runner constructs `CcxtRestClient` and calls `inner.sync_time()` before `check_permissions`. That is a GET, not a POST, but it violates the stated “apiRestrictions check before refusal” ordering for a non-read-only key.

Suggested fix: move `sync_time()` after `check_permissions(ReadOnlyClient(inner))`, or perform time sync through a no-key public client before constructing the signed client.

5. [LOW] Dry-run harness does not actually keep keys out of child processes by default

Evidence: [scripts/dryrun_restart_restore.py](/home/cms/project/BTC_Futures_E2E/scripts/dryrun_restart_restore.py:73), [scripts/dryrun_restart_restore.py](/home/cms/project/BTC_Futures_E2E/scripts/dryrun_restart_restore.py:74), [scripts/dryrun_restart_restore.py](/home/cms/project/BTC_Futures_E2E/scripts/dryrun_restart_restore.py:110), [scripts/dryrun_restart_restore.py](/home/cms/project/BTC_Futures_E2E/scripts/dryrun_restart_restore.py:137)

Scenario: parent `Popen` inherits `os.environ`, and the child reads `.env` before stripping Binance keys for `RB.run`. The runner still receives a stripped env unless `--use-binance-key`, and systemd does not call this script, but the docstring guarantee “only passes keys with `--use-binance-key`” is not true at process-env level.

Suggested fix: pass an explicit sanitized `env=` to both child `Popen` calls unless `--use-binance-key`, and avoid loading Binance keys from `.env` in child mode when the flag is absent.

Area verdicts:

A. MERGE. Stale close behavior matches registry #14.

B. FIX FIRST. Findings 1 and 2 affect restart safety/accounting.

C. FIX FIRST. Findings 3 and 4 should be fixed before using real keys.

D. FIX FIRST. Production/systemd reachability and entry gate look OK, but key stripping claim needs correction before running the harness with real credentials.

Codex session ID: 01a0a6b1-1364-7c32-aaac-21e78d60ae19
Resume in Codex: codex resume 01a0a6b1-1364-7c32-aaac-21e78d60ae19
```
</details>

### Codex 재검토 #1: L8b 수정분 (`1608073..2171383`, read-only · `task-mu34apl6-1xs6sb`)
판정: 1 HIGH·2 HIGH·4 MEDIUM·5 LOW **CLOSED** · 3 MEDIUM **PARTIAL** — 영역 A·B·D MERGE, C FIX FIRST.
| # | Codex | 동의 | 조치 |
|---|---|---|---|
| 새 MEDIUM | `safe_error`가 JSON·콜론 형식(`"signature":"…"`)과 스킴 없는 경로 쿼리를 못 지운다 | ✅ | 쿼리 제거를 스킴 없는 경로까지 · 서명 필드를 `=`·`:`·따옴표 형식 모두 `<signed>`로 · 파라미터화 테스트 5형식 |

<details><summary>Codex 원문 (verbatim)</summary>

```
**Findings**
[MEDIUM] `safe_error` still misses JSON/body-style signed fields.  
Evidence: [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:184) strips `https://...?...`, `X-MBX-APIKEY`, and `signature|timestamp|recvwindow=` forms, but not colon/JSON forms such as `{"signature":"deadbeef","timestamp":1789,"recvWindow":5000}`.  
Scenario: a ccxt/transport exception includes serialized request kwargs or a JSON body rather than a URL query. The API key header may be removed, but the signed request material remains in `fallback_reason`, alert/status text, or stderr.  
Fix: add a case-insensitive JSON/header/body redactor for `signature`, `timestamp`, and `recvWindow` with `:` separators, and preferably strip query strings for scheme-less paths too, e.g. `/fapi/v1/x?...`.

**Prior Findings**
1. HIGH FundingMissed engine block lost after second restart: **CLOSED**.  
Evidence: `engine_blocks` is persisted in [safety/gate.py](/home/cms/project/BTC_Futures_E2E/safety/gate.py:85), restored into `engine.entries_blocked` in [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:116), saved on `EntriesBlocked` in [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:358), and cleared through `/start` plus `save_state` in [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:607).

2. HIGH restore agreement misses `entry_commission` / `liq_price_est`: **CLOSED**.  
Evidence: DB-side `entry_commission` is computed and compared in [ops/restore.py](/home/cms/project/BTC_Futures_E2E/ops/restore.py:66) and [ops/restore.py](/home/cms/project/BTC_Futures_E2E/ops/restore.py:108). Snapshot `liq_price_est` must parse, but is not trusted; restore recomputes it in [paper/engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:228).

3. MEDIUM fallback reason can leak signed request material: **PARTIAL**.  
Evidence: common URL query/header forms are scrubbed in [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:189), but the JSON/body gap above remains.

4. MEDIUM `sync_time` before permission check on keyed client: **CLOSED**.  
Evidence: [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:202) syncs time with an unkeyed client, then copies `timeDifference` before constructing the keyed read-only client.

5. LOW harness child env keeps keys: **CLOSED**.  
Evidence: [scripts/dryrun_restart_restore.py](/home/cms/project/BTC_Futures_E2E/scripts/dryrun_restart_restore.py:70) strips Binance key env vars unless `--use-binance-key`, and both child `Popen` calls pass the stripped env.

**Area Verdicts**
A. Persisting engine blocks: **MERGE**. I do not see a stale-block reimpose or dropped-block path in normal DB/breadcrumb flows.

B. Restore agreement and liquidation recompute: **MERGE**. `restore_position` and `_refresh_liquidation` use the same formula.

C. Error sanitization: **FIX FIRST**. The remaining JSON/body signed-field gap is small but real.

D. Keyed-client ordering and dry-run env: **MERGE**.

I did not run tests because this was a read-only review and pytest would create temp artifacts/caches.

Codex session ID: 01a0a6bb-7167-70b1-b4da-da15aeec3184
Resume in Codex: codex resume 01a0a6bb-7167-70b1-b4da-da15aeec3184
```
</details>

### Codex 재검토 #2: `safe_error` 형식 확장 (`2171383..8a0799a`, read-only · `task-mu34fop8-lvqfo4`)
판정: 이전 PARTIAL **CLOSED** · A·B·D MERGE · C FIX FIRST(새 발견 1). 과잉 가림 없음(`code=-2015`·`msg` 유지).
| # | Codex | 동의 | 조치 |
|---|---|---|---|
| 새 MEDIUM | 스킴 없는 경로 정규식이 긴 `/` 반복 입력에서 초선형(40k자 ~6초) | ✅ | 경로 조각은 `/` + 한 글자 이상 · 경로 시작 앞 lookbehind · 키 값 치환 뒤 **2000자로 먼저 자른 다음** 정규식 · 병리 입력 4종 < 0.2초 테스트 |

<details><summary>Codex 원문 (verbatim)</summary>

```
**Findings**
[MEDIUM] `_URL_QUERY` has quadratic worst-case behavior on long slash-only text before the 300-char cap runs.  
Evidence: [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:185) has an unanchored scheme-less path alternative where `/` is both the start token and allowed inside the repeated path class. A local regex probe on synthetic strings showed `/` repeated 10k -> ~0.38s, 20k -> ~1.51s, 40k -> ~5.97s. This is not classic exponential catastrophic backtracking, but it is super-linear enough for `safe_error` to stall on a crafted/very odd exception string. Fix first by avoiding regex for scheme-less URL stripping or making the path start more selective.

**Carried PARTIAL**
CLOSED for the original sanitizer coverage gap.  
Evidence: [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:185) now strips scheme-less path queries, and [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:188) handles `=`, `:`, JSON/dict-ish quoting, and case-insensitive `recvWindow`. The requested 5-form test is present at [tests/test_ops_run_bot.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_run_bot.py:536).

Over-redaction check: `code=-2015` and `msg=...` survive in normal text/JSON body forms; only URL query contents are stripped, which matches the existing sanitizer contract.

**Area Verdicts**
A stale #14: MERGE. Only `markprice` is in `CLOSE_STREAMS`, and kline stalls hold/alert while blocking entries.

B restart restore: MERGE. DB/snapshot agreement includes `entry_commission`; liquidation is recomputed on restore.

C rules source + error sanitisation: FIX FIRST. Leak coverage is closed, but `_URL_QUERY` needs the super-linear regex fix.

D dry-run harness: MERGE. Child env strips Binance keys unless `--use-binance-key`.

I did not run pytest because this was a read-only review; I only ran bytecode-free local regex probes.

Codex session ID: 01a0a6be-fc35-72e3-a1c5-179505e7ae34
Resume in Codex: codex resume 01a0a6be-fc35-72e3-a1c5-179505e7ae34
```
</details>

### Codex 재검토 #3: 정규식 선형화 (`8a0799a..cd8a0d7`, read-only · `task-mu34l6ya-gc8o0g`)
판정: 이전 MEDIUM **CLOSED** · 새 발견 없음 · **A·B·C·D 전부 MERGE**.

<details><summary>Codex 원문 (verbatim)</summary>

```
**Findings**
None.

Prior MEDIUM `_URL_QUERY` super-linear issue: **CLOSED**. Evidence: [_URL_QUERY](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:186) no longer lets `/` be both the start token and repeated path body for scheme-less paths, and `safe_error` now caps scan input at 2000 chars after literal secret replacement and before regex passes: [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:197). The regression test is present at [tests/test_ops_run_bot.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_run_bot.py:550).

Local probes, no network:
`/` repeated 10k/20k/40k/80k took ~0.00011s / 0.00009s / 0.00011s / 0.00023s. The committed pathological cases all stayed sub-millisecond in my run.

Cap/leak checks:
A full configured secret cannot be partially exposed by the 2000-char scan cap because exact secret replacement happens before that cap. A signed field visible in the returned 300 chars is inside the regex scan window and is redacted before the final return cap. Probe with separated `signature=` crossing the 300-char output boundary returned `<signed>` and no signature/value fragment.

URL-query stripping still works:
`https://host/path?timestamp=...&signature=...`, `/path?timestamp=...&signature=...`, and `/fapi/v1/leverageBracket?...` all kept the path and removed the query/signature material.

Area verdicts:
A stale #14: **MERGE**  
B restart restore: **MERGE**  
C rules source + error sanitization: **MERGE**  
D dry-run harness: **MERGE**

I did not modify files, read `.env`, use the network, or print real secrets. Worktree stayed clean.

Codex session ID: 01a0a6c2-e7cf-7243-b4e5-a62bbec146fd
Resume in Codex: codex resume 01a0a6c2-e7cf-7243-b4e5-a62bbec146fd
```
</details>

### 페이퍼 드라이런 — 재기동 복원(SIGKILL) · 런타임 규칙(읽기 전용 키) (`3233ab2`, 2026-09-15 20:32:53–20:39:25 UTC · `var/dryrun-restore-20260916/`)
사용자 확인(2026-09-16): `.env`의 키 = 이 봇용 읽기 전용 키, 드라이런 사용 승인. 하네스 `scripts/dryrun_restart_restore.py --use-binance-key --hold-s 75 --run2-s 300`.
| 항목 | 값 |
|---|---|
| 규칙 | 두 기동 모두 `runtime:signed` 6종(exchangeInfo·leverageBracket·commissionRate·fundingInfo·positionSideDual·multiAssetsMargin) · 권한 조회 통과(읽기 외 권한 없음) · fallback 사유 없음 |
| 1차 | 기동 20:32:54 · 진입 주입 LONG 0.026 @ 75697.20 · 84x · SL 75323.39 (20:32:59, 게이트 통과 `pf_gate_ok=1`) · 엔진 스냅샷 3개(체결 1 + 봉 2) · **SIGKILL 20:34:15**(returncode −9) · manifest: connect 2, stop 없음 |
| kill 직후 DB | open 행 1(root 1) · close 0 · orders entry 1 · 마지막 스냅샷 3(20:34:00)에 포지션 |
| 2차 | 기동 20:34:20 · `RestartRestore` "root 1 · 스냅샷 3 · 일치" · 추정 청산가 재계산 75134.429… = 스냅샷 값 · 90초 뒤 상태: 포지션 LONG 0.026 · **blockers [] · entries_allowed true** · stalled [] |
| 청산 | 하네스 `close_all` 20:38:23 SELL 0.026 @ 75784.30 · close 행 `position_id=1`(같은 root) · 실현 2.2646 · 청산 수수료 0.9852 · 지갑 1000.2953 · 대사 차단 없음 |
| 봉 | REST 29 + WS 7 · kill 전후 간격 0 |
| 안전 상태 | safety_state 3행 · `engine_blocks []` · 킬스위치 발동 없음 · stale 청산 0 · FundingMissed 없음(다음 경계 00:00 UTC) |
| 2차 종료 | exit 0 · `stop`(clean, dropped 0) · db_errors 0 |
| 텔레그램 | 2차 발송 5 · 배달 5(message_id) · poll_errors 0 · send_errors 0 · 1차 배달 수는 SIGKILL로 상태 파일이 덮여 기록 없음 |
| 거래소 쓰기 | 없음 — `ReadOnlyClient`(키 있어도 POST 구조적 불가) · 체결은 `PaperSender` · positionRisk 미조회 |
| 비밀값 | report.json·status.json에서 키·시크릿·봇 토큰 문자열 검색 0건 |

## 2026-09-16 — 조건부 승인(#15) · dirty_previous_run · 배포 창 런북 준비

**사용자 지시(2026-09-16)**: 복원 드라이런 수용 · 8커밋 푸시(`db13657..69a1757` 완료) · 선택 1–4 조건부 승인 · 배포 전 추가:
stop 없는 start/connect → `dirty_previous_run` + 확정 사실 알림 한 번(테스트 먼저 · 배포 전 Codex 배치) · 배포 런북은 E2E Restart A/B 모양으로 준비만.

**수용 기록(사용자)**: SIGKILL 때 봇 raw shard의 미기록 버퍼 유실(드라이런 2026-09-15 20:33:58–20:34:15 UTC, 약 17초)은
**봇 자체 raw 저장소에 한해 수용** — E2E가 정본 수집기다(레지스트리 #15 ⑥).

**구현**: 레지스트리 #15 · `ops/run_events.py`(러너가 기동마다 대장 `start` · 마지막 종결 이벤트 뒤 start/connect → `dirty_previous_run`
대장 + `DirtyPreviousRun` 운영 이벤트 · 상태 파일 `confirmed_facts` 24시간) · `SafetyGate.notices`(`restart_unrestored` · /start 확인 · 저장) ·
health `confirmed_facts`(daily = 오늘 날짜 키, 아니면 기록 날짜 키) · `LiveChecklist` 2항목 · 불일치 뒤 flat 엔진 스냅샷.

**구현 중 발견(수정)**:
- health once 키 보관 필터가 **날짜 없는 키(`dirty_shutdown:<ts>`)를 저장하지 않아** 발송 성공 뒤에도 5분마다 재발송할 상태였다(layer 8 이후 · 미배포라 영향 0).
  → once 키 = `이름:YYYY-MM-DD[:id]` · 현재 문제 목록의 키는 날짜와 무관하게 보관 · 오래된 키만 40일 뒤 삭제.
- 불일치 복원 뒤 마지막 엔진 스냅샷이 여전히 포지션을 가리켜 **두 번째 재기동이 같은 불일치를 다시 판정**했다 → 불일치 적용 직후 flat 스냅샷.
- 봇 prune 타이머(일 03:30 UTC)가 E2E `e2e-integrity.timer`(일 03:30, 추적 사본 기준)와 겹친다 — prune은 미설치, 켜기 전 VPS 실측으로 결정(TODO 5l).
- 로컬에서 캡처 `--dry-run`으로 `ipRestrict=true`를 확인할 수 없다(화이트리스트가 켜지면 로컬 조회 실패) → 런북 §9: VPS에서 확인.

## 2026-09-16 — 배포 계획 확정(#16) · 기동 알림 한 줄 · Codex 배포 전 배치

**사용자 지시(2026-09-16)**: D1 09-18 · D2 09-19(00:35–02:30 UTC, E2E 00:10 판정 뒤) · prune 미설치, D2 뒤 VPS 실측 타이머에서 ≥30분 슬롯을 별도 변경으로 ·
`dirty_previous_run` health 알림 유지 + 기동 알림 한 줄 · `8b14ae2`·`daff756` 푸시(`69a1757..daff756` 완료) · 배포 전 Codex 배치 → 판정·항목별 동의 보고 ·
MERGE 전·Restart B 게이트 종료(09-18 00:16 UTC) 전 배포 단계 금지.

**구현**: 직전 실행 판정을 기동 알림 **앞**으로 옮기고 새로 판정한 기동에서만 🟢 알림에 `dirty_previous_run` 한 줄 · 런북 §9 날짜·화이트리스트 순서·§9.6 prune 시각 절차 · 레지스트리 #16.

### Codex 배포 전 배치 (`69a1757..29e52f2`, read-only · `task-mu37ggqz-h3ya7l`)
판정: A run_events MERGE · B notices/restore **FIX FIRST** · C health MERGE · D LiveChecklist MERGE · E runbook §9 **FIX FIRST**.
| # | Codex | 동의 | 조치(`25f08cb`) |
|---|---|---|---|
| 1 MEDIUM | 고아 close 행 기록 뒤 notice·safety_state 저장 전에 죽으면 확인 요청이 사라진다 | ✅ | notice 원천 = DB `restart_unrestored` close 행: 기동 때 확인 이벤트 없는 행마다 되살림 · /start가 `NoticeAcknowledged` 운영 이벤트를 남긴다 · 일일 손실 거부 /start는 확인 아님 |
| 2 MEDIUM | 봇 유닛 명령이 `sudo -iu btcfut` 셸의 사용자 버스에 기댄다 | ✅ | `bsc`/`bjc` 함수(`sudo -u btcfut XDG_RUNTIME_DIR=/run/user/<uid> systemctl/journalctl --user`)로 설치·show·정지·롤백 전부 · `/run/user/<uid>` 없으면 STOP · cgroup 경로도 btcfut uid |
Codex가 남긴 잔여(동의 · 기록만): `log_start()` 전에 SIGKILL이면 이 방식으로는 보이지 않는다 · 대장 자체가 죽으면 알림만 가능.

<details><summary>Codex 원문 (verbatim)</summary>

```
**Findings**

1. [MEDIUM] `restart_unrestored` notice can be lost if the runner dies between orphan close and notice persistence  
Evidence: [ops/restore.py:144](/home/cms/project/BTC_Futures_E2E/ops/restore.py:144), [ops/restore.py:150](/home/cms/project/BTC_Futures_E2E/ops/restore.py:150), [ops/restore.py:156](/home/cms/project/BTC_Futures_E2E/ops/restore.py:156), [ops/runtime.py:543](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:543)  
Scenario: On restore mismatch, the DB orphan position is closed via `PositionAbandoned` before the `restart_unrestored` notice is appended and before `save_state()` persists it. A SIGKILL after the close row is durable but before the notice/state save leaves the DB flat on the next start, so `decide_paper_restore()` returns `none` or a DB-flat mismatch and the human-confirmation notice is not shown until `/start`.  
Suggested fix: Make the notice durable atomically with, or derivable from, the `restart_unrestored` close row. A robust shape is: load unacknowledged `restart_unrestored` close rows into `SafetyGate.notices`, and persist an acknowledgement key on `/start` so they do not reappear after human confirmation.

2. [MEDIUM] D2 user-unit commands rely on an ambient `systemctl --user` session for `btcfut`  
Evidence: [docs/runbook_vps.md:15](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:15), [docs/runbook_vps.md:46](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:46), [docs/runbook_vps.md:151](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:151), [docs/runbook_vps.md:173](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:173)  
Scenario: The E2E checks correctly use `sudo -u ubuntu XDG_RUNTIME_DIR=... systemctl --user`, but the bot install/enable/show/rollback steps assume `sudo -iu btcfut` provides a working user bus. On some Ubuntu/sudo setups it will not, even with linger enabled, and D2 can fail mid-run or invite ad hoc retries.  
Suggested fix: Define and use an explicit bot-user systemctl form everywhere, e.g. `sudo -u btcfut XDG_RUNTIME_DIR=/run/user/$(id -u btcfut) systemctl --user ...` for daemon-reload, enable/start, show, stop, and rollback.

**Area Verdicts**

A. `ops/run_events.py` + `ops/run_bot.py`: MERGE  
No blocking issue found. False positives are limited by the bot-local manifest and current event writers. Double counting is prevented by `dirty_previous_run` as a terminal event. Known residual: SIGKILL before `log_start()` is inherently invisible to this scheme, and total manifest failure can only alert, not record.

B. `safety/gate.py` + `ops/restore.py`: FIX FIRST  
Finding #1.

C. `ops/health.py`: MERGE  
Once keys are date-bearing, send failure does not advance state, current problem keys are retained, recurring keys remain stable.

D. `paper/sender.py`: MERGE  
Confirmed: the new `LiveChecklist` fields are included in `fields(LiveChecklist)`, default to false, and `LiveSender` rejects construction unless every field is exactly `True`.

E. `docs/runbook_vps.md` §9: FIX FIRST  
Finding #2. Otherwise the deploy window ordering, whitelist order, prune deferral, E2E read-only posture, and rollback scope look coherent.

Tests: `TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider` passed. I did not read `.env`, did not modify files, did not use the network, and did not SSH.

Codex session ID: 01a0a70c-6ed0-71e3-b825-527c979b66cc
Resume in Codex: codex resume 01a0a70c-6ed0-71e3-b825-527c979b66cc
```
</details>

### Codex 배포 전 재검토 #1 (`29e52f2..` 수정분, read-only · `task-mu37o96e-si3pev`)
판정: 이전 1·2 **CLOSED** · 새 발견 2 · A·C·D MERGE · B·E FIX FIRST.
| # | Codex | 동의 | 조치 |
|---|---|---|---|
| 새 1 MEDIUM | ack 기록 실패 → breadcrumb(옛 base id) → 상태 저장 성공 → 재기동이 breadcrumb를 "오래됨"으로 격리하며 **대기 중 ack 이벤트도 버린다** | ✅(범위 넓음: 격리 breadcrumb의 운영 이벤트 전부가 재생되지 않았다 — layer 8부터) | 격리하든 복원하든 breadcrumb의 운영 이벤트는 op_id 멱등으로 재생 · 상태 저장 성공 때 남은 이벤트가 있으면 breadcrumb를 새 base id로 다시 쓴다 |
| 새 2 MEDIUM | D2 커밋 확인이 운영자 셸의 `~`를 쓴다 | ✅ | `sudo -u btcfut git -C /home/btcfut/BTC_Futures_E2E rev-parse HEAD` · §2는 btcfut 셸임을 명시 · §6 prune dry-run 절대경로 |

<details><summary>Codex 원문 (verbatim)</summary>

```
**Findings**

1. **MEDIUM, B notices/restore: queued ack can be dropped after a later durable safety-state save.**  
   In [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:621), `/start` copies notices, clears them via `gate.resume()`, records `NoticeAcknowledged`, then saves state. If `record_ops()` fails, it queues the ack and writes a breadcrumb using the old `saved_state_id` ([ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:433), [ops/runtime.py](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:506)). If the following `save_state()` succeeds, the notice-cleared state is durable, but the breadcrumb still has the old `base_state_id`; on restart, [ops/run_bot.py](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:366) quarantines it as superseded when there is no missing trip. Result: the notice is suppressed, but the `NoticeAcknowledged` row may never be replayed. This violates the new DB-ack source of truth.

2. **MEDIUM, E runbook §9: D2 commit check still depends on the wrong `~`.**  
   The new `bsc`/`bjc` guidance says bot user-unit commands run from an operator shell ([docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:12)), but D2 checks `git -C ~/BTC_Futures_E2E rev-parse HEAD` ([docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:157)). In that shell, `~` is the operator home, not `/home/btcfut`; this can fail or validate the wrong checkout. Use an absolute `/home/btcfut/...` path, ideally under `sudo -u btcfut`.

**Prior Issues**

1. `restart_unrestored` lost between orphan close and notice persistence: **CLOSED for the original crash window.**  
   Evidence: `sync_unrestored_notices()` rebuilds notices from `positions` close rows lacking `NoticeAcknowledged` ([ops/restore.py](/home/cms/project/BTC_Futures_E2E/ops/restore.py:131)), and `apply_restore()` calls it before restore action handling ([ops/restore.py](/home/cms/project/BTC_Futures_E2E/ops/restore.py:155)). New ack-replay issue above remains.

2. Runbook ambient `systemctl --user` session: **CLOSED for systemctl/journalctl usage.**  
   Evidence: `bsc`/`bjc` are defined with explicit `sudo -u btcfut XDG_RUNTIME_DIR=/run/user/...` ([docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:15)), and bot unit commands now use them. New wrong-`~` issue above remains.

**New-issue Checks**

Payload shape is OK: `record_ops_event()` merges `op_id` into `payload_json`, preserving `kind` and `id`, so `sync_unrestored_notices()` can still read them. Mode filtering is present; symbol filtering is applied on close-row rebuild, and position ids are table-global, so I do not see a symbol-collision issue.

Runbook E2E steps remain read-only: E2E commands list/show units, timers, baseline state, and shard timestamps; I did not find an E2E write step.

`git diff --check` fails only on trailing whitespace in the added `docs/ops_log.md` transcript. Focused verification passed: `TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ops_restore.py` → 22 passed. No files modified; no network, `.env`, SSH, or secrets touched.

**Batch Verdicts**

A run_events: **MERGE**  
B notices/restore: **FIX FIRST**  
C health: **MERGE**  
D LiveChecklist: **MERGE**  
E runbook §9: **FIX FIRST**

Codex session ID: 01a0a711-f8d6-7e22-9f94-55977e5bec1f
Resume in Codex: codex resume 01a0a711-f8d6-7e22-9f94-55977e5bec1f
```
</details>

### Codex 배포 전 재검토 #2 (`25f08cb..354b9d5`, read-only · `task-mu37vggp-7w8rtx`)
판정: 이전 2건 **CLOSED** · 새 FIX FIRST 없음 · **A·B·C·D·E 전부 MERGE**.
잔여(Codex · 비차단 · 동의 · 수정 안 함): 오래된 breadcrumb를 `safety_unsaved.stale-*`로 옮긴 직후 재생 커밋 전에 죽으면 그 운영 이벤트는
stale 파일에만 남는다(기동 순간의 짧은 창 · 전원 차단 원자성 아님). 사람이 stale 파일을 볼 수 있다 — 고치려면 "복사 후 재생 성공 시 원본 삭제" 형태(새 검토 필요).

<details><summary>Codex 원문 (verbatim)</summary>

```
No FIX FIRST findings.

State:
- Prior MEDIUM queued `NoticeAcknowledged` loss: **CLOSED**. `ops/run_bot.py` now extracts breadcrumb ops before the quarantine/restore decision, replays them through `rt.unrecorded_ops`, and `_retry_unrecorded()` records only `engine_events`.
- Stale gate re-imposition check: **CLOSED**. In the stale branch, `SafetyGate.from_state(...)` is not called; only the current DB-loaded gate is paused fail-closed. Breadcrumb gate state is not restored.
- Duplicate replay check: **CLOSED**. `record_ops_event()` uses `(mode, kind, op_id)` lookup before insert, and existing tests cover already-recorded breadcrumb replay.
- Breadcrumb freshness rules: **CLOSED**. Row-id freshness is still `latest_id > base_state_id`; trip-only-in-breadcrumb still restores fail-closed.
- Prior MEDIUM D2 `~` runbook bug: **CLOSED**. §9.4 now uses `sudo -u btcfut git -C /home/btcfut/BTC_Futures_E2E rev-parse HEAD`.

Residual note: I did not run tests because this was a read-only review and pytest would create cache/temp artifacts. One non-blocking recovery nuance remains: if the process dies after moving a stale breadcrumb to `safety_unsaved.stale-*` but before replay commits, those ops would only be in the stale file. I do not see this as a stated merge blocker, but it is not power-fail atomic during that tiny startup window.

Final verdicts:
- A run_events: **MERGE**
- B notices/restore: **MERGE**
- C health: **MERGE**
- D LiveChecklist: **MERGE**
- E runbook §9: **MERGE**

Codex session ID: 01a0a717-1974-7462-bb39-40fb61b76ede
Resume in Codex: codex resume 01a0a717-1974-7462-bb39-40fb61b76ede
```
</details>

## 2026-09-16 — 배포 전 배치 수용 · 푸시 · 백로그 메모

**사용자 지시(2026-09-16)**: 배포 전 배치 수용 · `29e52f2..149c98a` 푸시 · 배포 게이트: Codex MERGE ✓ · Restart B 게이트 종료 2026-09-18 00:16 UTC ·
D1 창 09-18 00:35–02:30 UTC · 여기서 멈춤(사용자 항목: rclone remote·TELEGRAM_OWNER_IDS·캡처 스크립트 → D1 전 확인 · 화이트리스트는 §9.1 뒤).
**백로그(설계 메모만, D2 전 금지)**: breadcrumb → DB journal 테이블 대체를 페이퍼 첫 주 뒤 평가(TODO 5o).

## 2026-09-16 — 순서 정정: btcfut rclone remote는 D1 안에서

**사용자 정정(2026-09-16)**: btcfut 사용자는 D1에 생기므로 rclone remote를 D1 전에 만들 수 없다 → 런북 §9.3 3단계(사용자 생성 직후):
`sudo -u btcfut rclone config`(drive · 기존 vcb-rclone OAuth 클라이언트 · scope `drive.file` · headless — 사용자가 로컬에서 `rclone authorize` 후 토큰 붙여 넣기) →
`rclone lsd` 확인 → `BTCFUT_DRIVE_REMOTE`. §9.0 사용자 선행 항목에서 rclone 제거.
사용자 확인: `TELEGRAM_OWNER_IDS`가 `.env`에 있음(개인 ID = 채팅 ID) · 계정에 열린 포지션 없음.

## 2026-09-15 22:21–22:23 UTC — 계정 read-only 캡처(사용자 "go")

- `--dry-run`(22:21:00Z) → 사용자 확인 → 실제 실행(22:22:57Z, exit 0). POST 없음(`ReadOnlyClient`) · 키 값 출력·기록 0(파일 검색 0건).
- 키 권한(`apiRestrictions`): enabled = `enableReading`·`ipRestrict`만 · 거래·출금·이체·옵션·포트폴리오·FIX 전부 false.
- `positionSideDual` = false · `multiAssetsMargin` = false → 합성 fixture 두 개를 실측으로 교체(값 동일 · 테스트 716 통과).
- `positionRisk_v2` BTCUSDT 1행: `positionAmt 0.000` · `positionSide BOTH` · `marginType cross` · leverage 5 · **`isolated` 필드 있음**(False) → PROVENANCE 기록.
  `positionRisk_v3` 0행(포지션 없음이면 빈 배열). 계정 전체 flat은 사용자 확인(스크립트는 BTCUSDT만 조회).
- ⚠️ 키가 **이미 `ipRestrict=true`**(허용 IP = 로컬). 사용자 확정 순서: §9.1 동안 유지 → D1 5단계 전 VPS IP 추가 → 로컬 점검 뒤 로컬 IP 제거 →
  증명 = VPS `--dry-run` 성공 + 로컬 실패. VPS 공인 IP·Elastic IP 여부는 D1 읽기 전용 사전 점검(§9.2)에서 알린다. 런북 §9 반영.

## 2026-09-15 22:45–22:49 UTC — §9.1 로컬 worktree 사전 점검 (커밋 `54b5af8`)

`git worktree add ../btcfut-deploy-54b5af8 54b5af8` · `uv sync --frozen`.
| 항목 | 값 |
|---|---|
| 테스트·정적검사 | pytest **716 passed** · ruff clean · pyright 0 errors · stream-tiers 위반 0 |
| 유닛 파일 | `git diff 25f08cb..54b5af8 -- ops/systemd/` **비어 있음**(Codex 검토 범위 그대로) |
| 규칙 | `runtime:signed` 6종(exchangeInfo·fundingInfo=rest · leverageBracket·commissionRate·positionSideDual·multiAssetsMargin=rest:signed) · `fallback_reason null` |
| 드라이런 240초 | exit 0 · `stop`(clean, dropped 0) · `blockers []` · `entries_allowed true` · `stalled []` · `confirmed_facts []` · db_errors 0 · bar_conflicts 0 |
| 봉 | REST 백필 179 + WS 4 · 스냅샷 5 · 운영 이벤트 Backfill 1 · 포지션 0(전략 없음) |
| shard | parquet 11개(kline1m_update·kline1m_close·markprice) |
| 텔레그램 | 발송 2 · 배달 2 · poll_errors 0 · send_errors 0 |
| 전달 나이 | kline1m_update 0.6s · markprice 1.5s · kline1m_close 15.9s(모두 grace 120초 안) |

**사용자 결정(2026-09-16 · 점검 중 수신)**: 읽기 전용 키 화이트리스트에 **로컬 IP를 남긴다**(VPS 35.79.38.63 추가됨) →
§9.1/§9에서 "로컬 IP 제거" 단계 삭제 · D1 증명 = **VPS 캡처 `--dry-run` 성공**만. 거래 권한 키는 **LIVE 전환 때 새로 발급**(VPS IP 하나 · VPS `.env`에만) → 레지스트리 #17 · 라이브 체크리스트 필드.

## 2026-09-18 00:31–00:57 UTC — **D1 실행**(도쿄 VPS · 커밋 `54b5af8` · 유닛 설치 없음)

호스트 `ip-172-31-38-160`(i-0fbf1cd7e1d261bea · t4g.small · Ubuntu 26.04 · 2 vCPU) · 공인 IP 35.79.38.63(ifconfig.me = IMDS).

**§9.2 읽기 전용 기준선(00:31)**: E2E 서비스 3종 active(l2collector·markprice·depthdiff) · `NRestarts=0` ·
l2collector ActiveEnter 2026-09-17 00:13:23 UTC(= Restart B) · 최근 1시간 parquet 551개 · 09-17 판정 **PASS**(rows_1s 86,425/86,400 · gap 0.0% · reconnects 1 · `counts_toward_gate` true) ·
디스크 96G 중 43G 사용(53G 여유) · 메모리 1834 MB(가용 1078 MB) · **swap 없음** · cgroup 위임에 `memory` 포함 ·
E2E 타이머 실측: quality 00:10 · digest 00:30 · health-alert 30분 · sync 매시 :07 · prune 일 02:30 · integrity 일 03:30 ·
btcfut 사용자·홈 없음 · rclone v1.74.4·git·python3 존재.
🔴 **발견 — 메모리가 가장 좁다**: E2E quality가 매일 00:10에 **595 MB**(MemoryPeak 실측)까지 쓴다 + 수집기 117 MB + 봇 상한 700 MB vs 총 1834 MB·swap 0.
사용자 결정: **A로 진행**(D1은 유닛 없음) · D2 전 템플릿만 수정(MemoryMax 400M · OOMScoreAdjust 500 · digest 00:40 · 00:10 창에 봇 타이머 없음) · swap은 D2 뒤 3일 실측(00:10 겹침 여유 < ~300 MB면 별도 날 변경).

**D1 쓰기 단계**
| 단계 | 결과 |
|---|---|
| 사용자 생성(00:34) | uid 1001 · 그룹 `btcfut`,`users`만 · linger yes · `/run/user/1001` 존재 · **수집기 홈 읽기 실패 확인**(`ls /home/ubuntu` → Permission denied) |
| rclone(사용자 헤드리스 인증, 00:50) | remote `btcfut-drive` · type drive · **scope `drive.file`** · `lsd` exit 0 · conf 600 · 수집기 conf(00:30 갱신, OAuth 토큰 자동 갱신분) 그대로 |
| 코드 | `git clone` → `checkout 54b5af8`(=`54b5af8b6f30…`) · uv 0.12.15 · `uv sync --frozen` · `var/` 700 |
| `.env` | 로컬 `.env`를 파이프로 복사(값 출력 없음) · 600 · `BTCFUT_DRIVE_REMOTE=btcfut-drive:BTC_Futures_E2E`로 설정 · `remote_root()` 통과 |
| 캡처 `--dry-run`(00:52, btcfut) | exit 0 · `enabled = ['enableReading','ipRestrict']` · BTCUSDT flat · **파일 쓰기 없음**(written []) → **D1 증명: VPS에서 키가 동작한다** |
| 페이퍼 드라이런 240초(00:52:38–00:56:39) | exit 0 · `stop`(clean, dropped 0) · `rules.source runtime:signed`(6종) · `fallback_reason null` · blockers [] · stalled [] · confirmed_facts [] · db_errors 0 · bar_conflicts 0 · 봉 REST 179 + WS 4 · 스냅샷 5 · 포지션 0 · parquet 11 · 텔레그램 발송 2·배달 2·오류 0 · var 1.5M |

**D1 뒤 E2E 대조(00:57)**: 서비스 active · `NRestarts=0` · ActiveEnter 불변 · 최근 5분 parquet 48개 · 디스크 44G 사용(+1G = btcfut 468M) ·
가용 메모리 1066 MB(기준선 1078) · btcfut 프로세스 = `systemd --user`·`sd-pam`뿐(봇 미기동) · `~btcfut/.config/systemd/user` 없음(유닛 0).

**D2 전 템플릿 수정(호스트 변경 아님 · Codex 검토 대상)**: `MemoryMax=400M` · `OOMScoreAdjust=500` · health-digest `00:40` ·
health-alert `*:03/5:30`(00:10~00:12 창 회피) · 테스트 `test_no_bot_timer_fires_during_the_e2e_quality_window`·MemoryMax/OOMScoreAdjust 잠금.
prune 타이머는 미설치 유지 — §9.6 시각 결정 때 실측 타이머 기준(quality 00:10·digest 00:30·health 30분·sync :07·prune 일 02:30·integrity 일 03:30) 사용.

### btcfut Drive remote — OAuth 클라이언트 출처(사용자 확인 2026-09-18)
- `btcfut-drive`는 **vcb-rclone** OAuth 클라이언트를 쓴다(VolumeClockBot과 같은 클라이언트) · 수집기(`ubuntu`의 `gdrive:`)는 **e2e-rclone** 클라이언트로 별개다.
  대조는 값 없이 지문으로: client_id sha256 앞 16자 — btcfut `f983259b5940a7e0` ≠ ubuntu `8444fd3f00aa97c4`.
- 두 클라이언트 모두 **프로덕션 게시**(published) 상태라 7일 refresh 만료가 없다 → 봇 전용 클라이언트를 따로 만들지 않는다(사용자 결정).
- `scope = drive.file`은 **그 클라이언트가 만든 파일만** 보여준다 → `rclone lsd`에 VolumeClockBot 폴더(`VCB_null_paper_tokyo`·`VCB_t1_paper_tokyo`)가 보이는 것은 **예상된 동작**이다.
- 🔒 쓰기 경로는 `BTCFUT_DRIVE_REMOTE=btcfut-drive:BTC_Futures_E2E` 하나뿐이다(`ops/drive_sync.py`는 그 아래로만 copy · 원격 삭제 동사 없음 · `ops/prune.py`는 로컬만 지운다 · E2E 폴더 이름은 `remote_root()`가 거부).

### Codex 검토: D2 유닛 템플릿 (`77597e0..e59107f`, read-only · `task-mu697jxr-os0eck`)
판정: **FIX FIRST**(1 MEDIUM · 2 LOW).
| # | Codex | 동의 | 조치 |
|---|---|---|---|
| 1 MEDIUM | 런북이 D1 해시를 그대로 쓰면 **D2가 옛 유닛(700M·00:30)을 설치**한다 | ✅ (실제 함정) | §9.0·§9.4: D2 해시는 **Codex MERGE 커밋** · VPS에서 fetch·checkout·`rev-parse` 대조 · `uv sync --frozen` · 설치 직후 `bsc cat`으로 MemoryMax/OOMScoreAdjust/OnCalendar 대조, 다르면 STOP |
| 2 LOW | `Persistent=true` 따라잡기가 부팅 직후 00:10 창에 발화할 수 있다 | ✅ | health-alert(5분)는 **Persistent 제거** · digest(하루 1통)는 유지하고 사유 기록 · 테스트로 두 조건 잠금 |
| 3 LOW | 설계서 §17·digest Description이 옛 값(700M·00:30) | ✅ | 둘 다 갱신 |
Codex 답변(기록): `MemoryMax=400M`은 정상 경로에서 그럴듯하나 **미증명** — 온호스트 `MemoryPeak`(기동·백필·첫 shard roll·텔레그램·00:10 겹침)과 `memory.events`로 판정,
부족하면 700M 복귀가 아니라 500~512M. `OOMScoreAdjust=500`은 전역 OOM에서 봇을 먼저 고르게 하며 cgroup(MemoryMax) 킬과는 무관 ·
반복 OOM은 `StartLimitBurst=5`에 걸릴 수 있다. `*:03/5:30`은 `systemd-analyze calendar`로 :03,:08,:13… 확인(00:10~00:12 없음).

<details><summary>Codex 원문 (verbatim)</summary>

```
1. [MEDIUM] D2 can still install the old unit templates unless the VPS checkout is explicitly advanced.
Evidence: `docs/ops_log.md:1812` records D1 checked out `54b5af8`; `docs/ops_log.md:1820` says the 400M/timer changes are D2-before-template changes; `docs/runbook_vps.md:114` fixes deploy hash `D`; `docs/runbook_vps.md:172` only checks current VPS HEAD equals `D` before copying units.
Scenario: If D remains the D1 hash, D2 copies the old `54b5af8` unit files, leaving `MemoryMax=700M`, digest `00:30`, and health-alert on the old schedule.
Suggested fix: Update §9.4 to set/verify the D2 deploy hash as the reviewed commit (`e59107f`) and fetch/checkout it on the VPS before copying units. Then show copied unit contents with `bsc cat/show` before enabling.

2. [LOW] `Persistent=true` can bypass the scheduled quality-window avoidance.
Evidence: `ops/systemd/btcfut-health-digest.timer:6-7` and `ops/systemd/btcfut-health-alert.timer:6-7`; the test only parses nominal `OnCalendar` minutes at `tests/test_ops_vps.py:354-370`.
Scenario: A missed `00:40` digest, or another persistent timer, can catch up immediately when the user timer is activated/booted, including at `00:10` during E2E quality. The health jobs are light, but this weakens the “no bot timer in quality window” guarantee.
Suggested fix: Either remove `Persistent=true` from health timers, or document/test the residual catch-up behavior and accept it as lightweight. Sync is heavier, so be especially deliberate there.

3. [LOW] Some authoritative text still says the old timer/memory values.
Evidence: `docs/design_v1.md:270` still says `MemoryMax 700M` and digest `00:30 UTC`; `ops/systemd/btcfut-health-digest.timer:2` still describes the digest as `00:30 UTC`.
Scenario: Later D2/audit work may follow the summary text rather than the template and miss the collector-priority change.
Suggested fix: Update §17 and the timer description to `MemoryMax=400M`, `OOMScoreAdjust=500`, digest `00:40`.

Notes on the direct questions: `MemoryMax=400M` looks plausible for normal operation but not proven. The normal path is bounded: 180 one-minute backfill, two ccxt.pro watches, three 60s parquet writers, sqlite, Telegram threads. Local import-only RSS reached about 130 MB before sockets/runtime state, so I do not see an obvious normal-operation OOM. The settling evidence is on-host `MemoryPeak` across startup/backfill, first shard rolls, Telegram active, and the 00:10 quality overlap, plus `memory.events`. If it OOMs normally, I’d try `500M`/`512M`, not jump back to `700M`.

`OOMScoreAdjust=500` does make the kernel strongly prefer the bot over a default `oom_score_adj=0` collector under global OOM. It does not affect `MemoryMax` cgroup kills; those happen inside the bot service cgroup. `Restart=on-failure` should restart an OOM-killed bot, but repeated OOMs can hit `StartLimitBurst=5`.

The calendar expression is right: `systemd-analyze calendar` confirms `*:03/5:30 UTC` fires at `:03,:08,:13,...` with second `:30`, so not `00:10-00:12` on its scheduled path. `_fires_at()` is correct enough for the current timer forms and would fail if a timer moved back into that window.

I could not run pytest in this sandbox because there is no usable temp directory. I did not use the network, read `.env`, modify files, or SSH.

Verdict: FIX FIRST, because D2 needs an explicit checkout/hash step or the reviewed unit changes may not be what gets installed.

Codex session ID: 01a0b209-4b25-75f1-a713-4508db275016
Resume in Codex: codex resume 01a0b209-4b25-75f1-a713-4508db275016
```
</details>

### Codex 재검토 #1: D2 템플릿 수정분 (`e59107f..0328653`, read-only · `task-mu69h2c8-e4wgcr`)
판정: **FIX FIRST**(이전 3건 중 1 CLOSED · 2 PARTIAL · 새 MEDIUM 2).
| # | Codex | 동의 | 조치 |
|---|---|---|---|
| 1 MEDIUM | §9.4가 §3을 부르는데 §3 블록에 `enable --now`가 있어 **대조·cgroup 게이트 전에 기동**될 수 있다 | ✅ | §3을 **3a 설치 / 3b 대조 / 3c 기동**으로 분리 · §9.4는 3a→3b(→cgroup)→3c 순서 |
| 2 MEDIUM | D2 해시가 리터럴이 아니다(`<D2>`) · `bsc cat` 검사에 health-alert `Persistent` 부재가 빠졌다 | ✅ | D2 = **ops_log "D2 해시" 줄의 리터럴** · 3b에 **`diff -q`(저장소 ↔ 설치본 8개 파일)** 추가 — 해시를 잘못 골라도 잡힌다 · `grep -E "OnCalendar|Persistent"`로 부재 확인 |
| 잔여 PARTIAL | `btcfut-sync.timer`는 Persistent 유지(더 무겁다) | ✅ 유지 + 근거 | sync는 `Nice=15`·`IOSchedulingClass=idle`이라 따라잡기가 수집기를 밀어내지 않는다 — 타이머에 근거 주석 · 테스트로 잠금 |
CLOSED: 설계서 §17·digest Description 문구.

<details><summary>Codex 원문 (verbatim)</summary>

```
**Findings**
1. **MEDIUM:** D2 order is still unsafe as written. [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:179) says to use §3 for unit install, but §3’s command block includes `bsc enable --now` at [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:57). That can start the bot/timers before the installed-unit checks at [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:180) and before the cgroup `memory` STOP gate at [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:183). Fix first by splitting copy+`daemon-reload` from enable, or by inlining only the copy/reload commands in §9.4 step 3.

2. **MEDIUM:** The D2 commit is still not a literal pinned hash. [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:114) says D2 is “the Codex MERGE commit,” and [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:177) uses `<D2>`. In this range, `e59107f` is the pre-fix unit-template commit and `0328653` is the review-fix commit. If the operator chooses the wrong “reviewed” commit, the current `bsc cat` checks cover `MemoryMax`/`OOMScoreAdjust`/`OnCalendar` but not `health-alert`’s missing `Persistent=`.

**Prior Findings**
- **D2 may install old unit templates: PARTIAL.** Fetch/checkout, `rev-parse`, `status --short`, `uv sync --frozen`, and post-copy `bsc cat` checks were added at [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:176). But the hash is not concrete, and §3 can enable before the checks.
- **Persistent catch-up can fire in the quality window: PARTIAL.** `health-alert` removed `Persistent` at [ops/systemd/btcfut-health-alert.timer](/home/cms/project/BTC_Futures_E2E/ops/systemd/btcfut-health-alert.timer:6), and digest documents its retained risk at [ops/systemd/btcfut-health-digest.timer](/home/cms/project/BTC_Futures_E2E/ops/systemd/btcfut-health-digest.timer:7). Tests cover alert/digest at [tests/test_ops_vps.py](/home/cms/project/BTC_Futures_E2E/tests/test_ops_vps.py:375). Remaining gap: `btcfut-sync.timer` still has `Persistent=true` and is heavier.
- **Stale design/digest text: CLOSED.** Design §17 now says `MemoryMax 400M`, `OOMScoreAdjust 500`, alert `:03`, digest `00:40` at [docs/design_v1.md](/home/cms/project/BTC_Futures_E2E/docs/design_v1.md:270), and the digest timer Description is updated at [ops/systemd/btcfut-health-digest.timer](/home/cms/project/BTC_Futures_E2E/ops/systemd/btcfut-health-digest.timer:2).

**D2 Runbook Check**
Intended order is good, but the written runbook does not enforce it because §3 includes enablement. No D2 step writes to the E2E user beyond read-only status/timer/baseline checks; the host risk is shared resources, not direct E2E mutation. Failed checkout should be caught by command failure, and dirty worktree should be caught by `status --short`, assuming the operator stops on mismatch. Rollback remains bot-only: [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:206) disables only `btcfut-*` units and [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:207) keeps deletion gated.

Verdict: **FIX FIRST**. I did not modify files, use the network, read `.env`, print secrets, or SSH.

Codex session ID: 01a0b210-087d-79f3-8beb-dbfd83b44244
Resume in Codex: codex resume 01a0b210-087d-79f3-8beb-dbfd83b44244
```
</details>

### D2 해시 (2026-09-18 고정)
**D2 = `05d6031b49fbba24df20ac3a133f6712bd11575c`** — 유닛 템플릿 최종본(MemoryMax 400M · OOMScoreAdjust 500 · digest 00:40 · health-alert `*:03/5:30`·Persistent 없음 ·
sync Persistent 유지 + Nice 15·IO idle). D1은 `54b5af8`이었다. D2 창에서 VPS 체크아웃을 이 해시로 옮기고 `rev-parse`로 리터럴 대조한다
(`diff -q`는 체크아웃↔설치본만 본다 — 옛 커밋 체크아웃은 잡지 못한다 · Codex 2026-09-18 재검토 #2).

### Codex 재검토 #2(D2 최종 게이트) (`05d6031..da42ed8`, read-only · `task-mu69tu4z-fahjfy`)
판정: **MERGE** · 새 발견 없음 · MEDIUM #2 CLOSED. Codex 확인: 고정 해시 `05d6031…` = `HEAD^`이고 그 뒤 커밋은 docs 2개만 바꾼다(`ops/systemd/` 불변) ·
D2 검사 3종 커버 확인 — (a) 오래된 체크아웃 = 리터럴 `rev-parse`, (b) 설치 불일치 = 8파일 `diff -q`, (c) 손으로 고친 설치본 = 같은 diff.

<details><summary>Codex 원문 (verbatim)</summary>

```
No findings.

MEDIUM #2: **CLOSED**. Evidence: [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:130) pins `D2 = 05d6031b49fbba24df20ac3a133f6712bd11575c`; [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:131) says `rev-parse HEAD` catches stale/wrong checkout, while [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:132) and [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:198) correctly limit `diff -q` to checkout-to-installed mismatch. The health-alert absence check is now `grep -c "^Persistent"` at [docs/runbook_vps.md](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:68), so the comment line no longer counts.

Pinned hash consistency: **confirmed**. `05d6031b49fbba24df20ac3a133f6712bd11575c` is exactly `HEAD^`, and `05d6031..HEAD` changes only `docs/ops_log.md` and `docs/runbook_vps.md`; `ops/systemd/` is unchanged. The pinned unit contents match the reviewed final state: bot `MemoryMax=400M` / `OOMScoreAdjust=500` at [ops/systemd/btcfut-bot.service](/home/cms/project/BTC_Futures_E2E/ops/systemd/btcfut-bot.service:28), digest `00:40` with retained `Persistent=true` at [ops/systemd/btcfut-health-digest.timer](/home/cms/project/BTC_Futures_E2E/ops/systemd/btcfut-health-digest.timer:6), health-alert `*:03/5:30` with no `Persistent=` directive at [ops/systemd/btcfut-health-alert.timer](/home/cms/project/BTC_Futures_E2E/ops/systemd/btcfut-health-alert.timer:6), and sync retains `Persistent=true` with `Nice=15` / IO idle at [ops/systemd/btcfut-sync.timer](/home/cms/project/BTC_Futures_E2E/ops/systemd/btcfut-sync.timer:8).

D2 checks now cover the requested cases: stale checkout is caught by the literal `rev-parse HEAD` comparison in §9.4 step 2; install mismatch is caught by the eight-file `diff -q` loop in §3 3b; a hand-edited installed unit is also caught by that same checkout-to-installed diff.

Verdict: **MERGE**. Read-only review only; I did not modify files, use the network, read `.env`, print secrets, or SSH.

Codex session ID: 01a0b219-2042-7ed1-a6eb-01fcf5ec638f
Resume in Codex: codex resume 01a0b219-2042-7ed1-a6eb-01fcf5ec638f
```
</details>

## 2026-09-19 00:39–00:45 UTC — **D2 실행**(유닛 설치·기동 · 커밋 `05d6031`)

**게이트**: 09-18 판정 **PASS**(rows_1s 86,380/86,400 · gap 0.0231% · reconnects 1 · `counts_toward_gate` true · 00:11:26Z 기록) ·
E2E 서비스 3종 active · `NRestarts=0` · 최근 5분 shard 49개 · 디스크 45G/96G · 가용 메모리 1074 MB.

| 단계 | 결과 |
|---|---|
| 2 코드 | `fetch` → `checkout 05d6031b…` → **`rev-parse` 리터럴 일치** · `status --short` 비어 있음 · `uv sync --frozen` 변화 없음(34 패키지) |
| 3a 설치 | 유닛 8개 복사 + `daemon-reload`(기동 없음) |
| 3b 대조 | 8파일 `diff -q` **MISMATCH 0** · `MemoryMax=400M`·`OOMScoreAdjust=500`·`Nice=10` · digest `00:40` · health-alert `*:03/5:30` · health-alert `^Persistent` **0줄** |
| 4 cgroup 게이트 | btcfut(uid 1001) controllers = `cpu memory pids` → **memory 위임 확인**(MemoryMax 실효) |
| 5 기동(00:40:20) | `enable --now` 4개 · `btcfut-bot` **active(running)** · `NRestarts=0` · 다음 타이머 health-alert 00:43:30 · sync 01:20 · digest 내일 00:40 — **00:10~00:12 발화 없음** |

**기동 후 대조**
- 🟢 기동 알림 **배달 확인**(`sent 1 = delivered 1` · poll_errors 0 · send_errors 0).
- 상태 파일 나이 0~1초 · `blockers []` · `stalled []` · `entries_allowed true` · `confirmed_facts []`(첫 기동 = 대장 비어 있음 → dirty 없음) · db_errors 0.
- 규칙 `runtime:signed` 6종 · `fallback_reason null` — VPS에서 읽기 전용 키로 런타임 조회 성공.
- 봉: REST 백필 179 + WS 누적 · 전달 나이 mark 0.06초·update 0.14초·close 55초(전부 grace 안).
- **첫 sync 수동 실행(00:42:06 → 00:42:16 success)**: 원격에 **`BTC_Futures_E2E` 폴더 생성**(`db/bot.sqlite`·`db/manifest.sqlite`) ·
  마커 `LAST_SYNC.txt` = `sync ok · raw_live: ok · bot_db: ok · manifest: ok` · E2E 폴더는 건드리지 않는다.
- 첫 health-alert(00:43:30): `[health] alert none` — 문제 없음.
- **메모리**: 봇 RSS 218 MB(기동·백필) → 227 MB(정상) · `MemoryPeak` 227 MB · cgroup `memory.events` **전부 0**(low/high/max/oom/oom_kill 0) → 400 MB 상한 대비 여유.
- **E2E 불변**: 서비스 3종 active · `NRestarts=0` · ActiveEnter 2026-09-17 00:13:23(Restart B) 그대로 · 최근 5분 shard 45개 · 가용 메모리 962 MB(봇 기동 후).

**다음**: 3일 실측(09-22 보고) — `MemoryPeak`·`memory.events`·00:10 겹침 여유. 겹침 여유 < ~300 MB면 swap을 별도 날 변경으로(레지스트리 #16 · TODO 5q).

## 2026-09-19 — 트라이얼 #1 사전등록 Codex 1차 검토 (`task-mu7pkyzf-r3duoh` · read-only · 코드 없음)
판정: **FIX FIRST**(BLOCKER 3 · MAJOR 4 · MINOR 1). Codex가 통과로 확인한 것: §7 기각 목록과 비중복 · 비용이 G2에 들어감 · B2 사이징 표 재현(0.30%→L100·margin 33.308·liq 0.5522% / 1.20% 거부) · 15m SL + 1m 감시가 옛 실패의 반대편.
| # | Codex | 동의 | 조치 |
|---|---|---|---|
| 1 BLOCKER | 레벨 결합·SL 앵커·TP 레벨이 모호(터치가 VP면 SL 근거 불명) | ✅ | 롱=지지/숏=저항 각 3개 · 결합 레벨 = 봉 극값에 가장 가까운 터치 레벨(동률 저가) · SL 앵커 = 확정 15m 스윙(없으면 `no_sl_anchor` 건너뜀) · TP = 시각 유효 레벨 중 최근접(없으면 2R) · 동시 신호 `conflict_signal` |
| 2 BLOCKER | 1m OHLCV로 VP를 구현할 수 없다(분배·동률 미정) | ✅ | 봉 quote volume 전부를 **종가 bin**에 · 창 = 직전 마감 1440봉 · POC 동률 저가 · VA 확장은 큰 쪽(동률 아래) · VAH/VAL = 포함 bin의 바깥 경계 |
| 3 BLOCKER | 매수보유를 보고만 하면 최종 벤치마크를 못 이겨도 ACCEPT 가능 | ⚠️ **사용자 결정(P3)과 충돌** | 문서 §8-1에 미결로 명시 — (A) 사용자안 유지 (B) Sharpe 게이트 (C) 노출 조정 Sharpe 게이트 중 **앵커 전 사용자 확정** |
| 4 MAJOR | `n_eff` 표기와 Arm B 게이트 의미가 불명확 | ✅ | `n_eff = n/(1+4ρ̂) ≥ 30` · ρ̂ > 0.15면 ρ̂로 재계산 · G1~G-B·벤치마크는 **Arm A만** · B는 대조군(짝지음 전제로만 n_eff ≥ 30) |
| 5 MAJOR | A/B 짝지음 비교가 N=2 다중검정 밖 | ✅ | 짝지음 차이도 **97.5% CI** |
| 6 BLOCKER | P4가 "당일 range"로 미래 정보 누출 | ✅ | 추출 범위 = 시각 t 기준 **직전 24h 마감 1m 고저** |
| 7 MAJOR | 플라시보 기각 규칙이 층마다 불일치 | ✅ | P2·P3는 결정론적 대조(원판 ≤ 지연/반전이면 기각) · P1·P4는 분포 p95 유지 |
| 8 MAJOR | OOS 끝이 앵커 시각에 따라 안전하지 않다 | ✅ | `OOS_end` = createdTime 이전 **완전 마감된 마지막 UTC 일** |
| 9 MINOR | `skip_rate` 분모 미정의 | ✅ | 분모 = 터치+확인+필터+쿨다운+단일포지션 통과 셋업(=`sl_dist`·사이징 게이트 직전) · 암별·창별 · `no_sl_anchor`·`conflict_signal`도 같은 분모로 별도 보고 |
**사용자 입장(§9-1)에 대한 Codex 판단**: (a) 1.00% 천장 = 사전확약 안전 밴드이지 튜닝 아님 — **동의** · (b) `sl_dist` 건너뜀은 결정 시점 정보라 룩어헤드 아님 — **동의**, 무효화 임계 **불필요**(G0가 이미 검정력 부족을 잡는다), 단 분모 정의는 필요(#9).

<details><summary>Codex 원문 (verbatim)</summary>

```
**Findings**

1. [BLOCKER] S/R trade construction is still ambiguous enough to produce different trades.  
Evidence: [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:26), [line 34](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:34), [line 37](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:37).  
Why: “nearest 3 levels,” “SL = swing_low/high,” and “opposite level” do not say which level binds the trade, especially when the touched level is VP rather than a swing level.  
Fix: precommit rules: eligible long levels are support levels below/at mark, shorts resistance above/at mark; bind the touched level with deterministic tie-breaks; SL anchor = nearest confirmed valid 15m swing outside the entry side, else skip `no_sl_anchor`; TP = nearest valid level on profit side from the timestamp-valid level set, else `2R`; simultaneous long/short confirmations skip as `conflict_signal`.

2. [BLOCKER] Volume profile is not implementable from 1m klines as written.  
Evidence: [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:23), [line 25](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:25), [line 139](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:139).  
Why: 1m OHLCV does not say how volume is allocated into price bins; POC/VAH/VAL ties are unspecified.  
Fix: define one deterministic method, e.g. “assign each closed 1m bar’s quote volume to the close-price bin; POC tie = lower price; VA expansion picks larger adjacent volume, tie = lower side; include whole bins until cumulative volume >=70%; use only the 1440 closed bars strictly before the decision close.”

3. [BLOCKER] Benchmark gate is weakened versus the protocol.  
Evidence: protocol requires benchmark after G-B [research-protocol.md](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/research-protocol.md:24); draft says BTC buy-and-hold is “보고만 · 게이트 아님” [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:87).  
Why: this makes ACCEPT possible without beating the stated final benchmark.  
Fix: make it mechanical: `Arm A daily net-equity Sharpe > BTC buy-and-hold daily Sharpe over the same window`, and keep `Arm A net return > 0` as the flat gate.

4. [MAJOR] G0 notation and Arm B gate semantics are not clean.  
Evidence: protocol says `n_eff >= 30 ⇔ n >= 30(1+4ρ)` [research-protocol.md](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/research-protocol.md:22); draft writes `n_eff >= 30(1+4ρ)` but interprets it as `n >= 48` [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:82). It also says gates are evaluated per arm [line 79](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:79), while the hypothesis is Arm A superiority.  
Why: one implementation may require B to be independently profitable; another may treat B only as control.  
Fix: write `n_eff = n / (1 + 4ρ_hat); require n_eff >= 30; prereg planning rho=0.15 implies n >= 48, but if rho_hat > 0.15 use rho_hat and fail as power-shortfall if short.` Apply G1/G2/G3/G-B/benchmark to Arm A; require Arm B `n_eff >= 30` only for the paired A/B comparison; report B standalone metrics.

5. [MAJOR] PSR/DSR/Bonferroni are partly specified, but the paired A/B test is not integrated with N=2.  
Evidence: N=2 is declared [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:151), G-B uses N=2 [line 86](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:86), A/B uses a separate 95% CI [line 88](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:88).  
Why: the primary two-arm comparison can escape the same multiplicity discipline.  
Fix: declare A as the only alpha candidate for PSR/DSR, with B as paired control, or keep N=2 and use Bonferroni-adjusted `97.5%` CI for the A-B paired difference too.

6. [BLOCKER] P4 placebo leaks future information via “당일 range.”  
Evidence: random levels are drawn from the day’s range [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:98).  
Why: intraday decisions before the daily close cannot know the full day high/low.  
Fix: draw random levels from a decision-time range only, e.g. rolling prior 24h closed 1m high-low as of timestamp `t`, preserving level counts and validity.

7. [MAJOR] Placebo rejection rules are inconsistent across layers.  
Evidence: P1/P4 use distributions and p95; P2/P3 use direct comparisons [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:95).  
Why: “must exceed each placebo distribution’s p95” is not actually defined for P2/P3.  
Fix: either define P2/P3 as deterministic controls: reject if original net edge `<= max(delay+1, delay+5)` or `<= inverted`; or bootstrap each placebo 1,000 times and require original `> p95`.

8. [MAJOR] OOS endpoint depends on anchor timing.  
Evidence: OOS is `2026-07-01 00:00Z → 앵커일 전일 23:59Z` [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:112).  
Why: if Drive createdTime is before that prior UTC day is fully available, the endpoint is not mechanically safe.  
Fix: `OOS_end = latest fully closed UTC day strictly before Drive createdTime`; if anchoring on 2026-09-19 UTC after 00:05Z, end may be 2026-09-18 23:59Z; otherwise use 2026-09-17 23:59Z.

9. [MINOR] `skip_rate` denominator needs a rule.  
Evidence: skip reporting is precommitted but “후보 셋업 수” is not defined [trial_01_preregistration.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:36).  
Why: skip rate can change depending on whether candidates are counted before/after filter, cooldown, conflict, or one-position rules.  
Fix: report per arm and per window: denominator = setups that pass S/R touch, rejection confirmation, direction filter if applicable, cooldown, and one-position rule, before `sl_dist` and sizing/liquidation gates.

**Checks That Pass**

The non-overlap argument is mostly honest: this is not Donchian breakout + meta-label, not volatility/chop as base signal, not spread, VPIN, funding-alone, or sub-30-minute signal reuse. The 1m bar is timing, while direction is 4h and SL/TP geometry is 15m/hours-scale.

The cost model is at the right gate: 14 bps plus realized funding enters G2, after gross edge and before OOS.

The sizing table is consistent with the current B2 path. I verified the canonical snapshot path gives `0.30% -> L=100, margin=33.308, liq_dist=0.5522%`; `0.50% -> L=83`; `1.00% -> L=51`; `1.20% -> liq_distance reject`.

I agree with §9-1(a): the 1.00% cap is a precommitted geometry/safety band alongside the dynamic #5 gate, not tuning. I agree with §9-1(b): the skip uses decision-time information and should shrink `n`, not create look-ahead. I do not require an invalidation threshold; G0 already invalidates underpowered realized samples. Just define the denominator as above.

The 15m SL monitored on 1m mark is the correct side of the prior scale failure, not a repeat of “15m buffer + 4h SL.”

**Verdict: FIX FIRST**

No data should be examined to settle these. Realized `n`, `rho_hat`, skip rate, MDE, and placebo distributions are only settleable after anchoring and implementation.

Codex session ID: 01a0b747-8a87-7ec3-8509-a0b862cc3571
Resume in Codex: codex resume 01a0b747-8a87-7ec3-8509-a0b862cc3571
```
</details>


### 트라이얼 #1 재검토 보류 — Codex 쿼터 소진 (2026-09-19 01:38 UTC · `task-mu7pxyo7-845c95` **failed**)
1차 검토(FIX FIRST)는 끝났고 수정도 반영했으나, **재검토(MERGE 판정)는 시작 직후 쿼터로 중단**됐다.
로그 원문: `Codex error: You've hit your usage limit. … try again at Sep 21st, 2026 7:25 AM.` — 모델이 diff를 읽은 뒤 판정 전에 끊겼다(부분 출력만 존재, 판정 없음).
→ **앵커는 재검토 MERGE 뒤**. 프롬프트는 `scratchpad/codex_trial01_b_prompt.md`에 그대로 대기(범위 `22cddbd..HEAD`). 쿼터 복구 시각 이후 재전송한다.
그 사이 문서 변경 금지(변경하면 재검토 범위가 달라진다).

**사용자 입장 기록 — P1 재표집(2026-09-19 · Codex 재검토 전)**: Arm A의 실현 `sl_dist`·보유시간을 재표집하는 것은 **기하(노출·트레이드당 위험·지속시간)를 맞추는 것**이고
방향과 타이밍은 무작위이므로 **신호 정보는 넘어가지 않는다** — 노출 정합 대조군의 표준 구성이다. Codex가 이견을 낼 수 있다(프롬프트 (5)에 포함).
**재전송 예약**: 2026-09-21 07:30 UTC(=16:30 KST) 세션 내 1회성 작업 `0cf017b6`. ⚠️ 세션이 끝나면 예약도 사라진다 — 그 경우 사용자가 수동 트리거.

## 2026-09-21 — 트라이얼 #1 사전등록 Codex 재검토 (`task-mub0dymr-41d8zh` · 쿼터 오류 없음 확인 · read-only)
재전송 경위: 09-21 07:30 UTC 예약 작업은 세션 종료로 사라졌고(스크래치패드도 비워짐) 실행된 적 없다 → 사용자 지시로 08:54 UTC 수동 전송. 프롬프트는 이전 전송분과 같은 내용으로 재작성.
판정: **FIX FIRST**(남은 것 = 레지스트리 초안 문구 2건 + P1 명세 MAJOR 1건).
| # | Codex | 동의 | 조치(사용자 확인 후) |
|---|---|---|---|
| 1·2·5·6·7·9 | CLOSED | — | — |
| 3 벤치마크 | **CLOSED — P1을 프로토콜 §2 벤치마크 비교로 수용**(이견 기록 아님) · 매수보유 미달 라벨도 과학적 판정을 약화하지 않는다고 확인 | ✅ | — |
| 4 | PARTIAL — 사전등록은 고쳐졌으나 **레지스트리 초안**이 여전히 `n_eff ≥ 30(1+4ρ̄)`·"암당 n ≥ 48" | ✅ | 초안 행을 `n_eff = n/(1+4ρ̂) ≥ 30`·계획 n ≥ 48·ρ̂ 재계산·Arm A 판정 주체로 |
| 8 | PARTIAL — **레지스트리 초안**이 "앵커 전일"로 적혀 createdTime 규칙과 갈릴 수 있다 | ✅ | 초안 행을 `OOS_end` = createdTime 이전 완전 마감 UTC 일 규칙 문구로 |
| 새 MAJOR | P1 명세 비결정: ① `sl_dist`·보유시간을 **따로** 재표집하면 위험×기간 노출이 달라진다 → **한 트레이드의 쌍으로 공동 재표집** ② 창 끝 근처 진입의 청산이 창 밖으로 나가는 경우 규칙 없음 → **보유시간 안에 창 안에서 청산되는 진입 시각에서만 추출, 겹치면 다시 뽑기** | ✅ | 사전등록 P1 행 두 줄 추가 |
**P1 재표집에 대한 판단**: 사용자 입장에 **동의**. 단 "신호 정보가 전혀 넘어가지 않는다"는 약간 과한 표현 — **전략이 만든 기하(노출·위험·기간)는 의도적으로 넘어가고**, 넘어가지 않는 것은 *원 신호의 시각·방향과 이후 수익의 정렬*이다. 무조건부 ATR 분포 대안은 **권하지 않음**(다른 질문에 답하고 노출 정합을 약화한다).

<details><summary>Codex 원문 (verbatim)</summary>

```
Verdict: **FIX FIRST**. The scientific benchmark choice is acceptable, but two implementation/record inconsistencies remain before anchoring.

## Prior findings

1. **CLOSED — level binding / SL / TP.** Long/short eligibility, binding-level selection, tie-breaking, swing-only SL anchors, `no_sl_anchor`, profit-side TP selection, and `conflict_signal` are now deterministic. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:26)

2. **CLOSED — volume profile.** Quote-volume allocation, the strictly prior 1,440-bar window, POC tie-breaking, VA expansion, and VA boundaries are fully specified. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:25)

3. **CLOSED — benchmark comparison.** I accept P1 as the protocol §2 benchmark comparison. The protocol requires a benchmark but does not require buy-and-hold specifically; the hard P1 p95 gate is an exposure-matched null comparison, while buy-and-hold remains a reported deployment reference. [Protocol §2](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/research-protocol.md:24), [benchmark gate](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:93), [verdict rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:128)

   This is acceptance, not a recorded disagreement. The passive-underperformance verdict suffix is also clearly non-scientific and does not weaken ACCEPT/REJECT.

4. **PARTIAL — G0 and arm scope.** The canonical preregistration is corrected: `n_eff = n/(1+4ρ̂)`, planning `n ≥ 48`, Arm A is the verdict subject, and Arm B needs power only for the paired comparison. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:84)

   However, the registry draft still says the mathematically wrong `n_eff ≥ 30(1+4ρ̄)` and “per-arm `n ≥ 48`.” [Registry draft](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_registry_row_draft.md:8)

5. **CLOSED — paired A/B multiplicity.** The paired difference now uses a 97.5% block-bootstrap CI. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:94)

6. **CLOSED — P4 leakage.** Random levels use only the preceding closed 24-hour 1m range at decision time. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:104)

7. **CLOSED — placebo decision rules.** P2/P3 are deterministic comparisons; P1/P4 retain distributional p95 gates. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:101)

8. **PARTIAL — OOS endpoint.** The preregistration has the exact createdTime-derived rule. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:118)

   The registry draft still says `앵커 전일`, rather than deriving `OOS_end` from the UTC date of Drive createdTime. That is often equivalent, but the draft can diverge if “anchor date” is entered independently, so the record should use the exact canonical rule. [Registry draft](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_registry_row_draft.md:8)

9. **CLOSED — skip-rate denominator.** The denominator, arm/window breakdown, and separate `no_sl_anchor`/`conflict_signal` reporting are defined. [Preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:40)

## P1 resampling judgment

I agree with the user’s substantive position.

Using realized Arm A `sl_dist` and holding-time distributions is legitimate for an offline conditional placebo. It is not a look-ahead trading rule: P1 is not meant to be executable prospectively. It conditions on observed risk and exposure geometry, while random direction and entry timing break the mapping from the original signal to subsequent returns.

The statement that “no signal information transfers” is slightly too absolute: the empirical distributions were generated by the original strategy, so strategy-conditioned geometry transfers intentionally. What does not transfer is the original signal’s timestamp/direction-to-return alignment. That distinction does not invalidate P1.

I do not recommend the unconditional ATR-based alternative; it would answer a different question and weaken exposure matching.

## New P1 specification issue

**MAJOR:** P1 is not yet fully deterministic at two points. [P1 specification](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:101)

- `sl_dist` and holding time are described as separate resamples. Separate marginal sampling versus joint sampling of `(sl_dist, holding_time)` can materially change risk-times-duration exposure and therefore the p95 gate. To support the stated geometry-matching rationale, resample the pair jointly from one original Arm A trade.
- An entry drawn near the window end may have an exit beyond the window. The document must precommit whether such draws are rejected/redrawn; clipping, dropping, or reading beyond the window produce different nulls. The clean rule is: draw only from entry timestamps for which the sampled holding time exits inside the same evaluation window, then reject/redraw overlaps.

These are specification fixes, not disagreement with realized-geometry resampling or with P1 serving as the benchmark.

The interrupted second session was not treated as a verdict. No files were modified; no network or `.env` access was used.

Codex session ID: 01a0c32c-5f8c-7a62-abd3-3c2a58c740e4
Resume in Codex: codex resume 01a0c32c-5f8c-7a62-abd3-3c2a58c740e4
```
</details>


**문구 정정(2026-09-21 · 위 사용자 입장 기록을 고치지 않고 덧붙인다)**: "신호 정보는 넘어가지 않는다"는 과한 표현이었다(Codex) →
**"전략이 만든 기하(노출·위험·보유시간)는 설계상 넘어가고, 원 신호의 시각·방향과 이후 수익의 정렬은 넘어가지 않는다."** 사전등록 P1 행에 이 문구로 반영.
사용자 지시로 3개 수정 적용: 레지스트리 초안 G0 표기·Arm A 판정 주체 · 초안 `OOS_end` createdTime 규칙 · P1 쌍 공동 재표집 + 창 안 청산만 추출(창 끝 과소표집 수용).

### 좁힌 재검토 (`206401a..233ce74` · `task-mub0o6xc-3amkft` · 쿼터 오류 없음)
판정: **FIX FIRST** — #4 **CLOSED** · #8 **CLOSED** · P1 **PARTIAL(결정론만)**: 통계 설계와 룩어헤드 없음은 확인, 1,000회·p95 규칙 유지 확인.
남은 것 = 같은 시드로 두 구현자가 같은 귀무분포를 내도록 **① 진입 시각 격자 ② 진입+보유시간 → 청산 관측 매핑 ③ 구간 끝점·겹침·배치 순서 ④ RNG 알고리즘·추출 순서 ⑤ 재추출·사이징 실패 시 처리** 고정. 동의 — 사용자 확인 후 반영.

<details><summary>Codex 원문 (verbatim)</summary>

```
Verdict: **FIX FIRST**

1. **#4 — CLOSED.** The registry now matches the pre-registration: identical `n_eff = n/(1+4ρ̂) ≥ 30`, planning threshold `n ≥ 48`, recomputation above `ρ̂=0.15`, power-shortfall classification, Arm A as verdict subject, and Arm B’s requirement limited to the paired-comparison precondition. Evidence: [registry draft:8](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_registry_row_draft.md:8), [pre-registration:84](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:84), [pre-registration:88](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:88), [pre-registration:94](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:94).

2. **#8 — CLOSED.** Both documents derive `OOS_end` mechanically from Drive `createdTime` as the end of the preceding fully closed UTC day; the registry explicitly forbids separately entering the date. Evidence: [registry draft:8](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_registry_row_draft.md:8), [pre-registration:118](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:118).

3. **P1 — PARTIAL.** The substantive statistical design is now present: joint `(sl_dist, holding_time)` resampling, B2 sizing, duration-only exit without SL/TP, identical costs, in-window eligibility, overlap redraw, no clipping/dropping/out-of-window reads, accepted edge under-sampling, and the revised rationale. It introduces no return-based look-ahead: eligibility depends only on the sampled duration and fixed window boundary. The row also retains **1,000 draws** and rejection at **strategy net edge ≤ placebo p95**. Evidence: [pre-registration:101](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:101).

The remaining blocker is determinism. Two implementers given the same seed can still obtain different null samples because line 101 does not define:

- The eligible “timestamp” grid—1-minute boundaries, available mark observations, or another set.
- How `entry + holding_time` maps to an exit observation.
- Interval endpoint/overlap semantics and placement order.
- RNG algorithm and random-draw order.
- Deterministic handling when overlap redraws or B2 sizing cannot produce the required trade count.

Until those conventions are frozen, the P1 null distribution and its p95 are implementation-dependent. No files were modified.

Codex session ID: 01a0c333-a67b-7ed3-81dd-0586899056f6
Resume in Codex: codex resume 01a0c333-a67b-7ed3-81dd-0586899056f6
```
</details>

**사용자 결정(2026-09-21) — P1 결정론 규약 적용**: 제안한 규약 그대로 + 2건 변경 — ① 안전장치 결과 = **폐기(설계 결함)**, REJECT 아님(평가 불가 귀무분포는 하네스 결함 · 재등록은 N+1이라 보수성 유지 · 1% 임계 유지)
② 시드 = **고정 공개 시드 20260921**(사전확약) · `sr_v1` SHA256은 별도 필드 · `SeedSequence(master).spawn(1000)[d]` · 시도마다 쌍 → 방향 → 진입 분.

### 최종 좁힌 재검토 (`c8a53f9..ee1a786` · `task-mub1ofwm-lmig9j` · 쿼터 오류 없음)
판정: **FIX FIRST** — DISCARD 일관성 **CLOSED**(프로토콜 §4 3분류와 일치) · P1 결정론 **PARTIAL**:
① **청산 시각 off-by-one(작성자 오류)**: 분 t 시가 진입 + 분 t+h **종가** 청산 = 약 h+1분 노출인데 구간은 `[t, t+h)`로 적어 겹침·노출이 어긋난다
② 재추출과 RNG 호출 순서 모순((e) 진입 분만 재추출 vs (g) 시도마다 쌍→방향→진입) · 카운터 초기화·정렬·방향 매핑·NumPy 호출 미정
③ 실패한 추출을 p95 계산에서 어떻게 다루는지 미정
④ **편향**: 겹침 실패 1,000회 뒤 쌍을 다시 뽑으면 **긴 보유시간 쌍이 선택적으로 빠져** 노출이 짧아진다 — 1% 안전장치로는 안 잡힌다.
동의 — 사용자 확인 후 반영.

<details><summary>Codex 원문 (verbatim)</summary>

```
Verdict: **FIX FIRST**

**P1 determinism: PARTIAL.** Two conforming implementers can still produce different seeded null samples.

1. **Exit timing is internally inconsistent.**  
   Entry at minute `t`’s open and exit at minute `t+h`’s close produces approximately `h+1` minutes of exposure, while `[entry, exit)` treats the exit as `t+h` and permits another trade to enter at `t+h`. That creates both an off-by-one exposure increase and an apparent overlap during the exit minute. [trial_01_preregistration.md:101](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:101)

   Exact fix: choose either:

   - exit at the close of minute `t+h-1`, occupancy `[t,t+h)`, next entry allowed at `t+h`; or
   - retain close of `t+h`, use occupancy `[t,t+h+1)`, next entry at `t+h+1`.

2. **Retry and RNG call order remain ambiguous.**  
   Rule (e) says retries draw only a new entry minute, but (g) says every attempt calls `pair → direction → entry`. It is also unclear whether a pair redraw redraws direction, when counters reset, and whether “100 pair redraws” includes the initial pair. These choices consume different RNG values. [trial_01_preregistration.md:101](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:101)

   Canonical ordering/mapping is also missing: Arm A trade ordering, eligible-minute ordering, `0/1 → LONG/SHORT`, and exact NumPy sampling calls.

3. **Failed-draw handling is incomplete.**  
   If 1–10 of 1,000 draws fail, (f) does not say whether p95 uses successful draws only or how failed draws are represented/replaced. [trial_01_preregistration.md:101](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:101)

**Look-ahead/bias**

- Ceiling `h` is not look-ahead; it is an ex-post exposure-matching convention. Correctly indexed, it adds less than one minute. As currently written, the exit-bar mismatch adds an additional full minute systematically.
- Entry-only redraw after B2 refusal does not introduce future-price look-ahead. It conditions entry times on contemporaneous executability, which is defensible.
- However, redrawing the pair after 1,000 overlap failures can preferentially replace long-duration pairs, shortening exposure even when the overall draw eventually succeeds. The >1% draw-failure guard does not detect that within-draw duration-selection bias.

**DISCARD consistency: CLOSED.** The research protocol explicitly defines `ACCEPT / REJECT / 폐기` as its three classes, and does not restrict discard to pre-measurement events. [research-protocol.md:36](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/research-protocol.md:36) The added §7 sentence clearly classifies a measurement-time harness defect as non-evidentiary discard with re-registration as N+1. [trial_01_preregistration.md:135](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:135)

No files were modified; no network was used; `.env` was not read.

Codex session ID: 01a0c34d-7502-70c3-8a03-35757d16c99e
Resume in Codex: codex resume 01a0c34d-7502-70c3-8a03-35757d16c99e
```
</details>

**사용자 결정(2026-09-21) — P1 결정론 최종 규약 적용**: 청산 = 분 t+h−1 종가 · 점유 `[t, t+h)` · 다음 진입 t+h · 슬롯 전부 먼저 추출(쌍→방향, 0=LONG) · h 내림차순 배치(동률 슬롯 번호) ·
**쌍 재추출 없음**(슬롯이 1,000회 실패하면 추출 실패) · p95는 성공 추출만 · 실패 10회 초과 → 폐기 · 시드 20260921 · 정렬·NumPy 호출 명시.

### ✅ 트라이얼 #1 사전등록 Codex **MERGE** (`cdd4ebf..657cc7b` · `task-mub1ynbk-ojmkau` · 쿼터 오류 없음)
P1 **CLOSED** — 시드 20260921·같은 입력·정본 B2 경로면 두 구현자가 **같은 귀무분포**를 낸다(남은 모호함 없음) · 행 안 모순 없음 · **MERGE — 앵커 준비 완료**.
앵커 전 상태: 사전등록 문서 `docs/trials/trial_01_preregistration.md` · 레지스트리 초안 행(미추가) · 코드 없음. 다음 = **사용자의 앵커 날짜 확인 → Drive 업로드(createdTime) → 레지스트리 행 append**.
Codex 검토 이력(트라이얼 #1): 1차 FIX FIRST(B3·M4·m1) → 재검토 FIX FIRST(레지스트리 문구 2·P1 명세) → 좁힌 재검토 FIX FIRST(P1 결정론) → 최종 FIX FIRST(off-by-one·RNG 순서·실패 추출·보유 선택 편향) → **MERGE**.

<details><summary>Codex 원문 (verbatim)</summary>

```
- **P1: CLOSED.** All four prior issues are resolved by conventions (a)–(f). Evidence: [trial_01_preregistration.md:101](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:101).
- **Reproducibility:** Yes—two conforming implementers using seed `20260921`, identical inputs, and the canonical B2 path will produce the identical null distribution; no remaining ambiguity.
- **Contradictions:** None; the preceding summary does not contradict conventions (a)–(f).
- **Verdict: MERGE — ready to anchor.**

Codex session ID: 01a0c354-b904-70c1-9eac-6731a0bc9fc2
Resume in Codex: codex resume 01a0c354-b904-70c1-9eac-6731a0bc9fc2
```
</details>

## 2026-09-21 09:51 UTC — 🔒 **트라이얼 #1 앵커**
- 앵커 직전 문구 수정 2줄(사이징 행 B2 · §9 분위수 행) → Codex 1문항 확인 **YES/MERGE**(`01a0c35e…`, 텍스트만) → 새 SHA256 `e4442ff4…cdd7ef`.
- 업로드 경로: 로컬 `gdrive_ro`는 `drive.readonly`라 쓰기 불가 · 호스트는 read-only 유지 → **Google Drive 커넥터**로 업로드(`text/markdown`, 변환 없음).
- **createdTime `2026-09-21T09:51:14.150Z`** — 커넥터 응답과 rclone `lsjson --metadata`(btime) **일치** · Drive MD5 `77d4cf7d…` = 로컬 · 내려받은 사본 SHA256 = 로컬 → **바이트 동일**.
- **OOS_end = 2026-09-20T23:59:59.999Z**(createdTime의 UTC 날짜 시작 − 1 ms, 코드로 계산 · 손입력 없음).
- `sr_v1` = §1 표(17~45행) SHA256 `b02d1a16…fbce6` · 시드 20260921 · N = 2 → 레지스트리 #18 append.
- 다음: 단계 2a(하네스) — 전략 코드 금지 해제는 **앵커 이후 구현 단계**로만(IS 실행은 Codex 검토 뒤).


## 2026-09-21 — 단계 2a 하네스(전략 무관) · 테스트만 · 실데이터 통계 없음
**구성**: `strategies/trial01/anchor.py`(앵커·창·시드 — 날짜를 손으로 쓰는 유일한 곳 · 문서 SHA256·sr_v1·레지스트리 #18을 테스트가 대조) ·
`backtest/data.py`(아카이브 로더·REST 보충·확정 펀딩·무결성·UTC 정렬 검사·봇 DB 대조) · `backtest/resample.py`(15m/4h · 마감 봉만) ·
`backtest/stats.py`(일 블록 부트스트랩 10k·양측 97.5% CI·짝지음 · PSR · DSR(N=2) · MDE · ρ̂) · `backtest/placebo.py`(P1 규약 a~f · P4 · P2/P3 변형 인자 · 기각 규칙) ·
`backtest/placebo_exec.py`(P1 시간 청산 = 정본 엔진 `restore_position` 경로 · 정상 엔진 트레이드와 손익 동일 테스트) · `backtest/returns.py` ·
`backtest/engine_replay.py`(전략 프로세스 안 봉 재생) · `backtest/replay.py`(격리 러너 + verbatim 기록기) · `backtest/prepare.py`(창 데이터 CLI · **OOS 준비 거부**).
numpy **2.5.3 정확 고정**(Generator 스트림이 버전 간 보장되지 않는다 → P1 귀무분포 재현성).

**데이터 사실(2a 설계 입력)**
- 아카이브 타임스탬프 = **UTC 봉 시작**(REST klines·markPriceKlines와 OHLCV·mark 정확 일치) · 파일은 **KST 연도**로 나뉜다.
- 아카이브 끝 **2026-06-18 14:59 UTC** → IS 끝 12.4일(17,820분)은 REST로 보충(`source=rest`) · OOS는 전부 REST(아직 준비 안 함).
- 아카이브 `funding_rate` 열은 분마다 앞값 채움 → 펀딩은 REST `/fapi/v1/fundingRate`(확정율·정산 mark)만.
- **IS 무결성(실데이터 · 개수만)**: 예상 1,313,280분 · 실제 1,313,278 · 중복 0 · 단조 · mark 결손 0 · 아카이브 1,295,458 + REST 17,820 · 확정 펀딩 2,736건(912일×3) ·
  UTC 표본 5개 일치 · bars SHA256 `70ef8a73…e120b3` · 🔴 **결손 2분 = 2024-08-12 10:02·10:03 UTC — 거래소 markPriceKlines 자체에 없다**(kline은 있음 · 아카이브 mark 열도 비어 있음).
  메우지 않았다(데이터를 만들지 않는다) → 처리 규칙은 사용자 결정 대기.

### 앵커 후 · 측정 전 구현 규약(2026-09-21 기록 — 실데이터 통계 계산 **전**)
사전등록이 정하지 않은 구현 선택. 이탈이 아니라 해석이며, 단계 d Codex 검토 대상이다. 사용자가 원하면 레지스트리 #19로 올린다.
- 부트스트랩 블록 = 트레이드 **진입 시각**의 UTC 달력일 · 거래 0건인 날도 빈 블록으로 유지 · 양측 97.5% CI(하한 = 1.25 백분위).
- PSR·DSR 계열 = **트레이드당 net_bps**(G-B의 n ≥ 30이 트레이드 수이므로) · "DSR > 0" = **SR̂ − SR* > 0** · 확률형 PSR(SR*)도 보고.
- 사전등록 밖 시드: 부트스트랩 `(20260921, 1)` · P4 `(20260921, 4)`(SeedSequence 엔트로피) · P1의 20260921만 사전등록 값.
- equity: 전략 암은 복리(엔진 하나 · 봇과 같다) · P1은 트레이드마다 초기 자본 고정 사이징 — net_bps는 명목 대비라 차이는 수량 내림(step)에서만.
- 창 끝에 열린 포지션(`open_at_end`)은 트레이드로 세지 않고 따로 보고 · IS→OOS는 flat에서 시작.
- gross = mark 대 mark(청산 체결의 `ref_mark` · 청산(liquidation)은 추정 청산가) · net = Δ지갑 / (수량 × 진입 체결가).
- 틱 규칙의 봉 근사: 진입 = 다음 봉 `mark_open` · SL/TP = 그 봉 `mark_low/high`(엔진 우선순위 청산 > SL > TP · SL 체결 기준 = SL과 시가 중 불리한 쪽) ·
  펀딩 = 경계가 든 분의 시작에서 `on_bar` 전에 정산.
- 수정(2026-09-21, advisor): 전략 트레이드 gross가 체결가(±2 bps)를 쓰던 것을 `ref_mark`로 — P1(mark 종가)과 같은 기준.


## 2026-09-21 — 단계 2b 피처(sr_v1 · 증분 · 손익 계산 없음)
**구성**: `strategies/trial01/features.py`(Wilder ATR_1m(60)·ATR_15m(14) · 15m/4h 버킷 + #19 ⑨ 2/3 규칙(통째로 빈 버킷도 불완전으로 낸다) ·
15m fractal k=3 스윙(엄격 비교 · 확정 = 3번째 뒤 봉 마감 · 48h · 0.25×ATR_15m 초과 종가로 무효화) · 24h 롤링 VP(종가 bin · **정수 거래대금**으로 더하고 빼도 오차 없음 ·
결정 봉 제외 · POC 동률 저가 · VA 큰 쪽/동률 아래) · TSMOM_4h(180)) · `feature_store.py`(백테스트 전용 sqlite `features_adv` · params_version 1 = sr_v1 · 정의에 sr_v1 SHA256) ·
`feature_build.py`(CLI · 워밍업 35일 · 창 첫 행에 워밍업의 느린 피처를 이어 넣음 · tickSize는 캡처 규칙에서).
**검증**: 롤링 VP = 처음부터 다시 계산한 값(매 분 340회 대조) · 버킷·스윙·TSMOM 경계 테스트 · features_adv 행 결정론(합성 + **실데이터 두 번 빌드 SHA256 동일**).
**IS 실측(피처만)**: 계산 1,363,678분(워밍업 50,400 + IS 1,313,278) · **68.2초 = 19,992분/초** · 저장 13.0초 · 내보내기 17.5초 · 최대 RSS 3.95 GB(로컬) ·
features_adv 5,439,164행 · 넓은 형식 1,313,278행(느린 피처 빈 값 0) · 스윙 17,629(고 8,853·저 8,776 · 무효화 14,242) · 불완전 버킷 0(결손 2분의 버킷 13/15·238/240은 계산) ·
**features_adv 행 SHA256 `dec39c92daebf8ccf78b94a4f3dc24a0abc44529f763b2e6bea48efab7b5bc08`**(두 번 동일).
**단계 d 질문으로 넘길 구현 선택**: POC 가격 = POC bin **중앙**(사전등록은 VAH/VAL 경계만 정함) · 워밍업 35일(창 전 아카이브로 피처만) ·
VP 창은 **봉 1440개**(결손 분이 있으면 시간상 1440분보다 길다) · 결손이 버킷 마지막 분이면 버킷은 다음 버킷 첫 봉에서 낸다.


## 2026-09-21 — 단계 2c 전략 플러그인 trial_01(Arm A/B) + 트레일링(엔진 · 기본 꺼짐) · 손익 계산 없음
**구성**: `strategies/trial01/config.py`(§1 표 값 · sr_v1 SHA256) · `strategy.py`(`Trial01` — touch → confirmation(도지 가드) → conflict_signal →
filter(Arm A만) → cooldown 60분 → one_position → [분모 `candidate=True`] → SL 앵커(no_sl_anchor) → sl_dist 범위(sl_dist_out_of_range) → TP → 의도 ·
`--delay`(P2)·`--invert`(P3) 플래그) · `run.py`(정본 CLI `python -m strategies.trial01.run --window IS --arm A|B [--delay K] [--invert] --out DIR` ·
워밍업 35일은 피처만 · 출력 decisions/trades/open_at_end.jsonl + summary.json(**개수·설정만, 지갑·수익 없음**)) ·
`backtest/engine_replay.py`: `ctx.bar_events`(그 분 엔진 이벤트 — 쿨다운용 청산 시각).
**트레일링(`paper/engine.py`)**: `EntryIntent.trail: Trail | None = None` — **기본 None = 꺼짐**. None이면 `_trail`이 즉시 돌아가고 스냅샷에 `trail` 키도 없다
→ **돌고 있는 페이퍼 봇(D2 `05d6031` · 전략 없음 · trail 없음)의 경로·이벤트·스냅샷 형태는 바뀌지 않는다**(테스트: 3R 상승에도 SL 불변 · 기본값 = 명시적 None과
이벤트 동일 · 스냅샷 키 집합 불변). 켜지면 R = |체결 진입가 − 초기 SL| · 유리한 극값(봉 = 롱 mark 고가/숏 저가 · 틱 = mark)이 +arm_r×R이면 무장 →
SL = 극값 ∓ dist로 조이기만 · **판정 뒤 갱신 → 다음 봉/틱부터 적용**(봉 안 순서 불명 · 보수적) · 옮겨진 SL 청산 = `ExitReason.TRAIL`(새 값) · 이벤트 `StopTrailed` ·
스냅샷/복원에 trail 상태 포함(있을 때만). 트라이얼 #1 config는 `trailing=True`(사전등록 §1에 트레일링 행이 있다).
**10진 문맥 고정**: ccxt `decimal_to_precision`은 호출 시 스레드 전역 rounding을 **HALF_UP으로 바꿔 놓고 되돌리지 않는다**(전체 테스트 순서에서 ATR_15m
28번째 자리 차이로 발견). 백테스트 프로세스는 ccxt를 import하지 않아(`load_rules()` 뒤에도 `sys.modules`에 없음 — 확인) 2b 값은 영향 없음 — 그래도 `features.DECIMAL_CTX`(28자리·HALF_EVEN = 파이썬 기본)를
`FeatureEngine.step`·`Trial01.on_minute_closed`·`run.run`(엔진 산술 포함)에 명시 고정. **재빌드 features_adv SHA256 `dec39c92…` 동일**.
🔴 단계 d 질문: 봇 프로세스는 ccxt를 쓰므로 `sizing/position.py`의 `localcontext()`(prec만 설정)는 HALF_UP rounding을 물려받는다 — 기존 동작, 이번에 바꾸지 않음.
**검증**: 814 passed · ruff·pyright 0 · stream-tiers 위반 0. 규칙별 테스트 32개(손으로 만든 봉 + 고정 피처) · 트레일링 11개 · 2b 정본 피처와 전략 피처 대조(표본 분) ·
**30일 조각(IS 첫 30일 + 워밍업 35일) 결정론: 별도 프로세스 두 번 × 두 암 = 출력 SHA256 전부 동일**(A decisions `29e0e2fb…` · trades `5178ef05…` ·
B decisions `8e94247f…` · trades `e8f65063…`) · 조각 1회 약 16초 · RSS 0.8 GB. trades.jsonl의 수익 필드는 읽지 않았다.
**조각 개수(성과 아님)**: 터치 롱 5,344·숏 4,975 · 확인 롱 2,263·숏 2,100 · 만료 1,043 · 동시 신호 32봉 ·
A: filter 2,186 · cooldown 18 · one_position 1,393 · 후보 702(no_sl_anchor 40 · sl_dist_out_of_range 525 · 의도 137 → 체결 136 · 엔진 사이징 거부 1) ·
B: cooldown 66 · one_position 3,401 · 후보 832(no_sl_anchor 84 · sl_dist_out_of_range 564 · 의도·체결 184).
**단계 d 질문(레지스트리 #21 후보)**: `strategy.py` 머리말 ⓐ~ⓚ(터치·확인 = mark 봉 · 봉 시작 기준 레벨 집합 · 밴드 "안" 문언 · 최근 터치가 대체 · conflict는 필터 전 ·
쿨다운 레벨 신원 · 결정 봉 마감 기준 SL/TP · TP 후보 = 전체 유효 레벨 · 트레일 거리 진입 때 고정 · 지연/반전 정의) + 트레일 무장·극값 봉 근사 · equity 1,000.
  + R 기준 두 가지: 트레일 R = |체결 진입가(2 bps 슬리피지 포함) − SL| · TP 2R·1.5R = |결정 mark − SL| · conflict를 필터 뒤로 두면 Arm A 분모가 커진다(조각 32봉).


## 2026-09-21 — 단계 2c 보완(사용자 "2c accepted with three actions before step d") · 손익 계산 없음
1. **skip_rate 분모**: 보고서의 "대사 불일치"는 **내 산수 오류**였다(확인 롱+숏 − conflict = 4,299를 2,299로 적음). 확인된 셋업 하나가
   신호 하나 → 결정 행 하나이므로 셈은 이미 셋업 단위였고 항등식이 성립했다(A 4,299 − 2,186 − 18 − 1,393 = 702 · B 4,299 − 66 − 3,401 = 832).
   코드 셈법은 바꾸지 않았고 대사 테스트를 추가: `test_skip_rate_denominator_reconciles_per_setup`(30일 조각 · 두 암) —
   셋업마다 전략 결정 행 정확히 하나 · 후보 = 필터 통과 확인 − cooldown − one_position = no_sl_anchor + sl_dist_out_of_range + intent.
2. **10진 rounding 고정(라이브 엔진 경로 · Codex 단계 d 묶음 · 검토 전 호스트 배포 안 함)**: `exchange/decimal_context.py`(`pinned` · `pinned_rounding` —
   산술 rounding HALF_EVEN·기본 트랩 고정 · 정밀도는 호출자/인자). 적용: `sizing/position.py` 세 곳(34자리) · `exchange/normalize.py`
   floor/ceil_to_step·normalize_price·normalize_entry_qty·split_market_qty · `paper/sender.adverse_fill_estimate`.
   양자화 rounding 명시: 가격 `quantize(tick, ROUND_HALF_UP)`(헌법 exchange-rules §정규화) · 수량 문자열 `quantize(step, ROUND_DOWN)`.
   테스트 `tests/test_decimal_context.py`: 전역 문맥 HALF_UP+Underflow 트랩(ccxt와 같은 변형) 및 **실제 ccxt `decimal_to_precision` 호출 뒤**
   사이징·청산가·정규화·분할·체결가 추정·주문 파라미터·진입 후 검사 3,994개 출력이 기본 문맥과 바이트 동일(수정 전 19개 불일치) ·
   exchange/sizing/paper의 quantize·to_integral 호출은 전부 rounding 명시(정적 검사).
   **기본 문맥에서의 결과는 수정 전과 같다**: 수정 전 커밋(fc9dde0)과 수정 후 코드의 같은 3,994개 출력 SHA256 `a0c4bf2c…` 동일.
   → 돌고 있는 봇에 미치는 영향은 ccxt가 전역 문맥을 바꾼 **뒤**의 호출에서만(마지막 자리 차이 제거). 엔진의 일반 산술(지갑·손익·VWAP)은 고정 대상 밖 — Codex 질문.
3. **레지스트리 #21**(사용자 결정 · 기록 시각 2026-09-21T11:36:37Z · 손익 계산 전): 2c 규약 전부 + **R = |체결 진입가 − SL| 하나** —
   트레일 무장과 **레벨 TP 1.5R 판정·2R 폴백도 체결가 기준**. 구현: `paper/engine.py` `EntryIntent.tp_rule: TpFromFill | None = None`(기본 꺼짐 ·
   `tp`와 동시 금지) → 체결 뒤 TP 결정 · `Engine.last_entry_tp`(재생 기록용 속성 — 이벤트·스냅샷 형태 불변) · 전략은 TP 레벨 후보만 넘긴다.
**검증**: 825 passed · ruff·pyright 0 · stream-tiers 0. 30일 조각(별도 프로세스 두 번 · 두 암) 해시 동일:
A decisions `789bf4d5…` · trades `13ca3691…` · summary `2fe670b5…` / B decisions `f9155ad6…` · trades `c55d018d…` · summary `2c58064b…`.
**조각 개수(성과 아님)**: A 후보 703(no_sl_anchor 40 · sl_dist_out_of_range 526 · 의도 137 → 체결 136 · 엔진 사이징 거부 1) · filter 2,186 · cooldown 18 · one_position 1,392 ·
B 후보 838(84 · 569 · 의도·체결 185) · cooldown 66 · one_position 3,395. (TP가 체결 기준으로 바뀌어 청산 시각이 달라지면 one_position이 조금 움직인다.)


## 2026-09-21 — 단계 d Codex 검토(2a~2c + rounding + 트레일/TpFromFill + #19~#21) · task-mub68i9q-a0yhgl · 판정 FIX-FIRST
프롬프트: 손익 금지(trades.jsonl·var/backtest 산출물 열람 금지 · 전체 IS 실행 금지 · OOS 금지) · 읽기 전용. 아래 원문 그대로.
확인(Claude): #3 `db/record.py` 알 수 없는 이벤트 → TypeError 확인 · #1 `placebo_exec` `bars[t]` 내부 분 인덱싱 확인(IS 결손 2분 존재) ·
#9 IS quote_volume 소수 자릿수 최대 5(1,313,278행 중 5 초과 0) → 정수 변환은 IS에서 정확, 규약 기록만 빠짐.

> ## Findings
> 
> 1. **HIGH** — [backtest/placebo_exec.py:78](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:78)
> 
>    **Wrong:** P1 eligibility requires marks only at entry and exit, but execution indexes every
>    intervening minute with `bars[t]`.
> 
>    **Scenario:** A placebo interval crosses a known missing mark minute. Its endpoints are valid,
>    yet execution raises `KeyError`, aborting the mandatory 1,000-draw placebo run.
> 
>    **Fix:** Iterate observed bars within the interval while preserving clock-time duration and
>    endpoint-only eligibility. Add an interior-gap regression test.
> 
> 2. **HIGH** — [backtest/placebo.py:180](/home/cms/project/BTC_Futures_E2E/backtest/placebo.py:180),
>    [strategies/trial01/strategy.py:179](/home/cms/project/BTC_Futures_E2E/strategies/trial01/strategy.py:179)
> 
>    **Wrong:** P4 only has a random-level generator. The strategy has no injection path that
>    replaces both entry-band levels and swing SL anchors.
> 
>    **Scenario:** Step e cannot run the preregistered 200 P4 draws through the canonical
>    strategy/engine chain.
> 
>    **Fix:** Add a deterministic level-provider interface and a P4 runner that replaces both
>    level classes using only the prior 24-hour range. Add end-to-end P4 tests.
> 
> 3. **HIGH** — [paper/engine.py:503](/home/cms/project/BTC_Futures_E2E/paper/engine.py:503),
>    [db/record.py:300](/home/cms/project/BTC_Futures_E2E/db/record.py:300)
> 
>    **Wrong:** The engine emits `StopTrailed`, but the DB recorder has no handler for it and
>    raises `TypeError`.
> 
>    **Scenario:** The first enabled trail ratchet terminates event recording. If execution
>    continues or restarts, the DB still contains the original SL.
> 
>    **Fix:** Persist effective SL/trail state durably and add a runtime→DB→restart test.
> 
> 4. **HIGH** — [ops/restore.py:103](/home/cms/project/BTC_Futures_E2E/ops/restore.py:103)
> 
>    **Wrong:** Restore compares the snapshot’s ratcheted SL with the DB’s initial SL.
> 
>    **Scenario:** Any restart after a successful ratchet is treated as a DB/snapshot mismatch,
>    causing the position to be abandoned.
> 
>    **Fix:** Restore from the latest persisted effective SL and trail state, not only the
>    original entry row.
> 
> 5. **HIGH** — [paper/engine.py:428](/home/cms/project/BTC_Futures_E2E/paper/engine.py:428),
>    [ops/runtime.py:175](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:175),
>    [db/record.py:220](/home/cms/project/BTC_Futures_E2E/db/record.py:220)
> 
>    **Wrong:** `_tp_from_fill` resolves TP inside the engine, but runtime records the original
>    intent TP, which is `None` for `TpFromFill`.
> 
>    **Scenario:** The snapshot contains the resolved TP while the DB contains null. A restart
>    rejects or abandons an otherwise valid open position.
> 
>    **Fix:** Put resolved TP on `EntryFilled`, or record `engine.last_entry_tp` atomically.
>    Test normal and immediate `POST_FILL_GATE` cases.
> 
> 6. **HIGH** — [strategies/trial01/feature_build.py:53](/home/cms/project/BTC_Futures_E2E/strategies/trial01/feature_build.py:53),
>    [strategies/trial01/run.py:51](/home/cms/project/BTC_Futures_E2E/strategies/trial01/run.py:51)
> 
>    **Wrong:** Warm-up loads only the archive. That archive does not reach the OOS boundary,
>    leaving a substantial gap before OOS.
> 
>    **Scenario:** A future approved OOS run starts with stale ATR, momentum, swing, and VP
>    state rather than a continuous 35-day feature warm-up.
> 
>    **Fix:** Before step e, freeze a unified archive-plus-prior-IS warm-up loader. Add synthetic
>    boundary tests. Do not open or execute OOS while doing this.
> 
> 7. **MEDIUM** — [exchange/decimal_context.py:19](/home/cms/project/BTC_Futures_E2E/exchange/decimal_context.py:19)
> 
>    **Wrong:** `pinned_rounding` pins rounding and traps but inherits caller precision,
>    exponent limits, capitals, and clamp.
> 
>    **Scenario:** A library that lowers thread precision can still change normalization or
>    sizing output despite the context fix.
> 
>    **Fix:** Use a named fixed context, or require explicit precision at each arithmetic
>    boundary. Test several caller precisions and exponent settings.
> 
> 8. **MEDIUM** — [paper/engine.py:403](/home/cms/project/BTC_Futures_E2E/paper/engine.py:403),
>    [paper/engine.py:503](/home/cms/project/BTC_Futures_E2E/paper/engine.py:503)
> 
>    **Wrong:** Wallet, funding, VWAP, PnL, post-fill distance, TP, and trail arithmetic still
>    inherit the thread-global Decimal context.
> 
>    **Scenario:** ccxt’s HALF_UP context can change a post-fill gate, minimum-R TP decision,
>    or trail boundary at a rounding edge. That is material in LIVE.
> 
>    **Fix:** Pin the entire engine transaction/event calculation to one explicit context.
>    Compare complete event, snapshot, and DB bytes under default, ccxt-mutated, and
>    low-precision caller contexts.
> 
> 9. **LOW** — [strategies/trial01/features.py:48](/home/cms/project/BTC_Futures_E2E/strategies/trial01/features.py:48),
>    [strategies/trial01/features.py:200](/home/cms/project/BTC_Futures_E2E/strategies/trial01/features.py:200)
> 
>    **Wrong:** Quote volume is converted to an integer at fixed `1e-5` resolution. This
>    numerical convention is not recorded in registry row #20.
> 
>    **Scenario:** Truncation changes a very close VP-bin tie, hence POC or value-area selection.
> 
>    **Fix:** Preserve exact Decimal units or preregister the scale explicitly before P&L.
> 
> 10. **LOW** — [strategies/trial01/feature_store.py:34](/home/cms/project/BTC_Futures_E2E/strategies/trial01/feature_store.py:34)
> 
>    **Wrong:** Feature metadata cites registry rows 18 and 19 but omits row 20, which defines
>    the feature conventions.
> 
>    **Scenario:** An artifact lacks complete provenance for POC, warm-up, VP-window, and late
>    emission rules.
> 
>    **Fix:** Include row 20 in artifact metadata.
> 
> ## Q1 — Frequency versus “hours”
> 
> No code branch clearly fires more often than the anchored mechanical rules permit.
> 
> The main frequency amplifiers are themselves recorded in row #21:
> 
> - VP levels and their prices can change every minute.
> - Cooldown identity for VP is exact price, so a moved POC/VAH/VAL is a new identity.
> - A later touch replaces and refreshes the pending setup.
> - Confirmation may occur on the touch bar.
> - Three levels per side are considered.
> 
> Conversely, the extreme-inside-band rule is restrictive, and one-position filtering binds
> heavily. The confirmation formula, conflict handling, candidate selection, one-position
> rule, SL, TP, and trailing exits match the recorded interpretation.
> 
> Thus the observed intent count exceeds the narrative expectation, but does not establish
> an implementation bug. The VP price identity is an interpretation of ambiguous
> “same level,” not a silent rule change. Trial #1 must not be changed now.
> 
> ## Q2 — Decimal change and running paper bot
> 
> **(a)** ccxt changes rounding and the Underflow trap, not precision. The fix restores the
> intended default-context outputs for sizing, normalization, and fill estimates.
> 
> It is not byte-identical to the old bot under ccxt’s mutated context—that erroneous
> behavior is what changes. Deployment risk to D2 is low while it has no active strategy,
> but the shared-engine persistence findings should be fixed before enabling entries.
> 
> **(b)** Caller precision should not remain implicit. It is sufficient for the observed ccxt
> mutation, but not for general determinism. Fix or explicitly pass precision.
> 
> **(c)** Yes, shared-engine arithmetic should also be pinned. Most wallet differences are tiny,
> but post-fill gates, TP eligibility, and trail thresholds can change execution behavior.
> That matters for LIVE.
> 
> ## Q3 — Trailing stop and `TpFromFill`
> 
> With both new options left `None`, the prior path remains unchanged:
> 
> - No `StopTrailed` event is emitted.
> - Conditional trail snapshot keys are absent.
> - Existing event and DB payload shapes are unchanged.
> - `EntryIntent` additions are not persisted by `db/record.py`.
> 
> The bar approximation is correct: existing exits are checked first; arming and ratcheting
> use that bar’s favorable extreme; the new stop applies from the next bar.
> `ExitReason.TRAIL` is used only after an actual ratchet.
> 
> Trail state is present in snapshot/restore. `_tp_from_fill` correctly chooses the fallback
> when the fill has passed the level. LIVE replaces entry with exchange average price before
> TP resolution. The post-fill gate runs after resolution and exits immediately when needed.
> 
> The enabled path is nevertheless unsafe because resolved TP and ratcheted SL are not
> persisted consistently.
> 
> ## Q4 — Carried questions
> 
> - `open_at_end`: matches row #19. It is an explicit censoring convention, not silent.
> - Returns: gross mark-to-mark via `ref_mark`; net wallet delta divided by entry notional.
> - DSR: implements `SR̂ − SR* > 0` with `N = 2`.
> - Warm-up: feature-only and 35 days for IS; future OOS loading is defective as noted.
> - POC midpoint: disclosed interpretation of otherwise unspecified level price.
> - VP: 1,440 observed bars, as registered; missing minutes make it longer than wall-clock 24h.
> - Late buckets: emitted without future data and do not create look-ahead.
> - P1: endpoint conventions match, but sparse interior minutes can crash execution.
> - P1 execution uses restore/manual entry rather than the normal entry path. This is disclosed
>   in row #19, but increases future divergence risk.
> - P2/P3 flags match row #21, including delayed-state gating and post-gate inversion.
> - Equity 1,000 is implemented.
> - Skip-rate denominator reconciliation correctly accounts for confirmation sides,
>   conflict rows, filters, cooldown, one-position, and candidate outcomes.
> - P4 is not wired into the executable strategy chain.
> 
> ## Q5 — Look-ahead
> 
> No base-strategy look-ahead was found:
> 
> - Touch uses ATR and levels available at bar open.
> - VP excludes the decision bar.
> - Swing confirmation becomes available only after its confirming 15-minute close.
> - Invalidation occurs at close and affects subsequent availability.
> - TP selection uses levels valid at decision close.
> - Funding is applied before `on_bar`.
> 
> The full-window price bounds used to allocate VP bins affect storage geometry, not bin
> mapping or signal values. P4 look-ahead cannot be verified end-to-end because P4 is not
> integrated.
> 
> ## Q6 — Other issues and verification
> 
> The additional risks are the missing P4 execution path, sparse-minute P1 crash, incomplete
> trail/TP persistence, future OOS warm-up discontinuity, and remaining Decimal-context
> dependence.
> 
> Read-only targeted verification produced 80 passing tests. One `tmp_path` test and the
> full suite could not run because the environment provides no writable temporary/cache
> directory. The worktree remained clean, and no trade files or prohibited backtest output
> were opened.
> 
> VERDICT: FIX-FIRST — blockers: P1 sparse-gap execution, P4 integration, trail/TP persistence and restore, and the future OOS continuous warm-up path.
> 
> Codex session ID: 01a0c3c2-4230-71f3-8bd7-68beb8a78a43
> Resume in Codex: codex resume 01a0c3c2-4230-71f3-8bd7-68beb8a78a43


## 2026-09-21 — 단계 d 후속 수정(사용자 "Fix order approved … one follow-up Codex batch") · 손익 계산 없음
1. **P1 내부 결손 분**(Codex #1): `backtest/placebo_exec.run_time_exit` — mark 봉이 없는 내부 분은 판정 없이 넘기고 그 분의 펀딩은 정산.
   테스트: 내부 2분 결손(그 안의 펀딩 포함) = 결손 없는 같은 가격 경로와 결과 동일. P1 골든 해시 불변.
2. **워밍업 로더**(Codex #6): `feature_build.load_warmup` = 아카이브 우선 + 빈 분만 **앞선 창의 준비된 봉**(OOS ← IS parquet) ·
   창 시작 이후 봉은 넣지 않음 · 채울 수 없는 분은 결손으로 남김. IS는 앞선 창이 없어 아카이브만(기존과 같음). `run.load_inputs`·`feature_build.build`·조각 픽스처가 사용.
   테스트는 합성 경계만(합성 IS parquet → OOS 워밍업 35일 연속 · OOS 디렉터리 생성·읽기 없음). **OOS 미개봉 유지.**
3. **트레일·체결 뒤 TP 영속화·복원**(Codex #3·#4·#5): 엔진이 `TrailSet`(체결 직후)·`TrailArmed`(무장)·`StopTrailed`(조임)을 내고
   `db.record`가 `engine_events`에 기록(스키마 변경 없음) · 런타임은 체결 시 `engine.last_entry_tp`(tp_rule이면 체결 뒤 값 · 아니면 intent.tp와 같음)를
   open 행 TP로 기록 · `StopTrailed`·`TrailArmed`는 스냅샷 트리거 · `ops.restore`는 유효 SL = 마지막 `StopTrailed.new_sl`(없으면 open 행)과
   트레일 상태(arm_r·dist·R·armed·moved)를 DB에서 다시 만들어 스냅샷과 대조. 테스트: 런타임 → DB → 재기동(조인 SL·체결 뒤 TP 복원) ·
   무장만 된 상태 복원 · StopTrailed 행 삭제 → 불일치 · 트레일 없는 포지션은 트레일 행 0·기존대로 복원 · POST_FILL_GATE 즉시 청산에도 open 행 TP 기록.
   트레일/TP 규칙이 없는 현 봇 경로: 이벤트·DB 행·스냅샷 형태 불변(TP는 intent.tp와 같은 값).
4. **이름 붙은 고정 10진 문맥 `EXEC_CTX`**(Codex #7·#8): 정밀도 34 · HALF_EVEN · 기본 트랩 · 기본 지수 범위 — 호출자 값을 하나도 쓰지 않는다.
   적용: 엔진 공개 메서드 전부(`request_entry`·`on_tick`·`on_bar`·`on_funding`·`close_now`·`vanish`·`position_state`·`restore_position`·
   `sync_wallet`·`cancel_pending`·`unrealized_pnl`·`equity`) · 정규화 5함수 · 사이징(이미 34자리) · `adverse_fill_estimate` · `db.record.record_events`.
   테스트: 호출자 문맥 기본 / ccxt 모양(HALF_UP+Underflow) / 낮은 정밀도(6자리·DOWN)에서 사이징·정규화 3,994개 출력 + **엔진 시나리오 전체
   (트레일·체결 뒤 TP·펀딩·청산)의 이벤트·스냅샷·DB 행** 바이트 동일 · 실제 ccxt 호출 뒤에도 동일.
   🔴 **돌고 있는 봇에 대한 영향**: 엔진 산술이 28자리(호출자 기본) → 34자리가 된다 — 지갑·손익·VWAP 등 긴 나눗셈 결과의 29~34번째 자리가
   생긴다(DB 문자열이 길어질 수 있음). 결정(진입·청산·게이트)은 이 자릿수에서 바뀌지 않도록 설계돼 있으나 Codex 확인 대상. 엔진 테스트 기대값도 EXEC_CTX에서 계산.
5. **피처 메타데이터** `registry_rows` = [18, 19, 20, 22](Codex #10) · QV_SCALE 주석에 #22.
**P4**(사용자 승인 · 레지스트리 #22): `strategies/trial01/p4.py` `P4Feed`(정본 `EngineFeed`를 감싸 레벨만 교체 — 스윙 1:1·같은 무효화 규칙·확정 시각 기준
직전 24h 범위 · VP 분마다 3개·시드 `[20260921, 4, d, minute_index]` · 추출 번호 d 포함은 구현이 더한 해석) · `run.py --p4-draw d` · `placebo.p4_args()`(200개) ·
`FeatureEngine.b15_complete`(무효화 재현용 훅 — 피처 값 불변).
테스트(합성 7일): 1:1·종류·유효기간·확정 시각 범위·tick 격자 · 무효화 = 무차별 재계산 · VP = 분 시드 재계산·직전 24h 범위·결정 봉 제외 · 정본 피처 불변 ·
같은 추출 결정론·다른 추출은 다름 · 전략 끝까지 실행(SL 앵커 = 무작위 스윙).
**검증**: 847 passed · ruff·pyright 0 · stream-tiers 0 · **IS 피처 재빌드 SHA256 `dec39c92…` 동일** · 30일 조각 별도 프로세스 두 번:
A decisions `789bf4d5…`(수정 전과 같음) · trades `80991df7…`(34자리 엔진 산술로 값 문자열 변화) · P4 추출 0 decisions `cd81a95a…` · trades `49327350…` 동일.
조각 1회: 정본 약 22초 · P4 약 30초 → 전체 IS P4 200회는 추출당 약 15분 × 200(병렬 필요 — 단계 e 계획 사항).


## 2026-09-21 — push `ce1cd2c` · 사용자 결정 기록 · 배포 flat 조건
- push 전 점검(읽기만): 작업트리 깨끗 · 올릴 커밋 1개 · 저장소 **PUBLIC** · 비밀 값 grep(`api key|secret|token|password|export X=`) 걸림 0 ·
  새 파일은 `strategies/trial01/p4.py`·`tests/test_trial01_p4.py`뿐(로그·보고 파일 없음) · 로컬 게이트 847 passed · pyright·ruff 0 → `8fd658c..ce1cd2c` push(force 없음).
- **앵커 후 실행 경로 변경(sizing·normalize·engine)의 의미 판정**: 버그 수정·결정론 강화이지 규칙 변경이 아니다 — 30일 조각 Arm A에서
  수정 전(f9bbae9)·후(ce1cd2c) **결정 행 바이트 동일** · 트레이드 136건의 구조 필드(진입·청산 시각·방향·수량·레버리지·SL·TP·청산 사유·체결가) **전부 동일**
  (수익 필드는 비교·출력하지 않음) · 달라진 것은 34자리 산술로 생긴 값 문자열 자릿수뿐 → **거래 집합·사이징 불변, 정정 행 불필요**.
  사이징(자금) 코드 변경의 Codex 검토: 단계 d(task-mub68i9q) 지적 #7·#8의 수정 · 후속 검토 task-mubcqczj 진행 중.
- 사용자 확정: P4 VP 시드 `(20260921, 4, draw, minute_index)`가 맞다 — 사용자 문언이 추출 번호를 빠뜨렸을 뿐, **#22가 정본**.
- 사용자 사전확약(배포 조건): 엔진 문맥 업그레이드는 **flat(열린 포지션·대기 진입 없음)일 때만 깨끗한 정지 → 기동** — 업그레이드 전 스냅샷을
  업그레이드 뒤 DB 값과 대조하는 일이 없게. 현 봇은 전략이 없어 늘 성립하지만 점검은 매번 → 런북 §9.7(정지 전 status.json `position None · pending False` ·
  정지 알림 `stop` · 정지 후 DB 열린 root 0 · 해시 고정 checkout · 기동 알림 복원 없음). `status.json`에 `pending` 필드 추가(상태 파일만 · DB·이벤트 불변 · 테스트).
- 사용자 단계 e 계획(Codex MERGE 뒤): 전체 IS Arm A·B → P1(1,000) · P2(+1/+5) · P3 · P4(200 · **로컬 병렬, VPS 금지**) · 사전등록 200회 유지 ·
  **모든 게이트를 한 보고서에서 함께 계산·개봉** · IS 통과 전 OOS 미개봉.


## 2026-09-21 — 단계 d 후속 Codex 검토(ce1cd2c) · task-mubcqczj-a0n4md · 판정 FIX-FIRST
프롬프트: 손익 금지·OOS 금지·읽기 전용(Codex는 tmp 쓰기 불가로 테스트 미실행 — 로컬에서는 847/848 통과). 아래 원문 그대로.

> ## Findings
> 
> 1. **HIGH** — [ops/runtime.py:353](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:353),
>    [ops/runtime.py:370](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:370)
> 
>    Event recording and snapshot recording are separate transactions.
> 
>    A crash after `StopTrailed` commits but before its snapshot leaves DB at the new SL
>    and the latest snapshot at the old SL. Restore declares a mismatch and abandons
>    the otherwise reconstructable position.
> 
>    Fix: atomically commit events plus engine snapshot, or replay durable events newer
>    than the snapshot. Add a crash-injection test between `_record()` and `snapshot()`.
> 
> 2. **HIGH** — [ops/runtime.py:375](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:375),
>    [ops/runtime.py:398](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:398)
> 
>    `_record()` does not preserve FIFO while `unrecorded` already contains work.
> 
>    If entry recording fails, a later trail or close batch can succeed before the
>    queued entry. A close becomes orphaned; retrying the entry then creates a phantom
>    open root.
> 
>    Fix: when `unrecorded` is non-empty, append without attempting a direct write.
>    Test entry-write failure followed by trail, partial close, and full close.
> 
> 3. **HIGH** — [exchange/decimal_context.py:18](/home/cms/project/BTC_Futures_E2E/exchange/decimal_context.py:18),
>    [ops/restore.py:67](/home/cms/project/BTC_Futures_E2E/ops/restore.py:67),
>    [ops/restore.py:143](/home/cms/project/BTC_Futures_E2E/ops/restore.py:143)
> 
>    The precision upgrade has no persisted context version or transition guard.
> 
>    Restore reconstructs accumulated DB decimals under the caller’s context, then
>    compares them exactly with snapshot aggregates. A position spanning the 28→34
>    upgrade can mismatch after new events, even when both histories are legitimate.
> 
>    Fix: deploy only while flat, or persist an arithmetic-version/checkpoint and
>    reconstruct under the matching context. Add a mixed-version restart test.
> 
> 4. **MEDIUM** — [ops/restore.py:61](/home/cms/project/BTC_Futures_E2E/ops/restore.py:61),
>    [ops/restore.py:82](/home/cms/project/BTC_Futures_E2E/ops/restore.py:82)
> 
>    Trail and funding ownership is inferred only from `ts_ms >= root_ts`.
> 
>    If a trailed position closes and a non-trailed position opens in the same
>    millisecond, the old `TrailSet` can be attached to the new root. Funding has the
>    same timestamp-boundary ambiguity.
> 
>    Fix: persist and query a root position ID or durable engine sequence number.
> 
> 5. **MEDIUM** — [ops/runtime.py:458](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:458),
>    [tests/test_decimal_context.py:112](/home/cms/project/BTC_Futures_E2E/tests/test_decimal_context.py:112)
> 
>    Actual account-snapshot arithmetic is still caller-context dependent.
> 
>    Isolated margin, available balance, and margin balance are calculated outside
>    `EXEC_CTX`. The “snapshot” byte test exercises `Engine.position_state()`, not
>    `BotRuntime.snapshot()` and its persisted account row.
> 
>    Fix: wrap snapshot arithmetic in `EXEC_CTX` and compare real account-snapshot rows.
> 
> 6. **LOW** — [strategies/trial01/p4.py:56](/home/cms/project/BTC_Futures_E2E/strategies/trial01/p4.py:56),
>    [strategies/trial01/p4.py:108](/home/cms/project/BTC_Futures_E2E/strategies/trial01/p4.py:108)
> 
>    P4 retains only one extra hour for late confirmation-time range lookups.
> 
>    A sufficiently long data gap can emit a complete-enough past bucket whose
>    confirmation window has already been pruned, causing the assertion at line 109.
>    The known two-minute IS gap is safe.
> 
>    Fix: retain history based on the oldest emitted bucket, or defer pruning until all
>    late buckets have been processed.
> 
> 7. **LOW** — [tests/test_ops_restore.py:370](/home/cms/project/BTC_Futures_E2E/tests/test_ops_restore.py:370)
> 
>    `test_armed_but_unmoved_trail_restores` never arms the trail; it asserts
>    `armed=False`.
> 
>    Fix: create a bar that reaches the arm threshold while producing no SL improvement,
>    then assert `armed=True, moved=False` before and after restart.
> 
> ## Q1 — Six prior HIGH findings
> 
> 1. **RESOLVED** — Interior mark gaps are skipped while funding is still processed:
>    [placebo_exec.py:80](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:80).
>    Test: `test_time_exit_executor_skips_interior_minutes_without_a_mark_bar`.
> 
> 2. **RESOLVED** — `P4Feed` replaces swing and VP levels, `--p4-draw` reaches the
>    canonical runner, and SL anchoring consumes replaced swings:
>    [p4.py:77](/home/cms/project/BTC_Futures_E2E/strategies/trial01/p4.py:77),
>    [run.py:55](/home/cms/project/BTC_Futures_E2E/strategies/trial01/run.py:55).
>    Tests: `test_swings_are_replaced_one_to_one_with_same_kind_and_validity`,
>    `test_strategy_runs_end_to_end_on_random_levels`.
>    The long-gap robustness issue above remains LOW.
> 
> 3. **PARTIAL** — Trail events are now recorded:
>    [record.py:304](/home/cms/project/BTC_Futures_E2E/db/record.py:304).
>    Test: `test_trailed_sl_and_resolved_tp_survive_a_restart`.
>    Crash atomicity and FIFO ordering remain unresolved.
> 
> 4. **PARTIAL** — Restore derives effective SL and trail state:
>    [restore.py:82](/home/cms/project/BTC_Futures_E2E/ops/restore.py:82).
>    Tests: `test_trailed_sl_and_resolved_tp_survive_a_restart`,
>    `test_missing_trail_rows_are_a_mismatch`.
>    Same-millisecond ownership and record/snapshot crash boundaries remain unresolved.
> 
> 5. **RESOLVED** — Runtime records the engine-resolved TP and queues that captured
>    value:
>    [runtime.py:358](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:358),
>    [runtime.py:381](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:381).
>    Test: `test_post_fill_gate_exit_records_resolved_tp`.
> 
> 6. **RESOLVED** — Warm-up merges archive-first with preceding prepared windows:
>    [feature_build.py:39](/home/cms/project/BTC_Futures_E2E/strategies/trial01/feature_build.py:39),
>    [feature_build.py:52](/home/cms/project/BTC_Futures_E2E/strategies/trial01/feature_build.py:52).
>    Tests: `test_merge_warmup_prefers_archive_fills_gaps_from_prior_window_and_never_crosses_start`,
>    `test_oos_warmup_continues_from_the_prior_is_bars_on_a_synthetic_var_dir`.
> 
> Therefore, four are resolved and two are only partial.
> 
> ## Q2 — P4
> 
> Adding `d` to `[20260921, 4, d, minute_index]` is the right reading.
> 
> Without it, all 200 draws share their VP levels; only swings vary. Row #22 records
> this interpretation before measurement, so it is transparent and reproducible.
> 
> The implementation otherwise matches the registered rule:
> 
> - Swings are created one-for-one at the same confirmation times with the same IDs,
>   kinds, nominal expiry, and invalidation rule.
> - VP produces three draws for every VP-ready minute.
> - Swing and VP prices use kline-last high/low ranges.
> - Replaced swings feed SL anchoring.
> - The SL-distance floor and cap remain in canonical strategy code.
> - VP excludes the decision bar by querying before `range.push(bar)`.
> - Late bucket lookup uses its historical confirmation time and filters out later bars.
> 
> There is no look-ahead. The only late-emission issue is the one-hour retention limit.
> 
> “Same density” is satisfied as creation count: identical swing confirmations and
> three VP records per minute. Effective active swing count may differ because random
> prices invalidate at different times; that is inherent in “same invalidation rule,”
> not a deviation.
> 
> Sorting and labelling the draws as `VAL ≤ POC ≤ VAH` is acceptable because row #22
> explicitly fixes that mapping. It makes POC the median draw rather than a true volume
> mode, which is appropriate for this registered placebo.
> 
> ## Q3 — `EXEC_CTX` and deployment
> 
> Compared with the old default precision, the new context can change:
> 
> - Boundary decisions in post-fill gating, TP fallback selection, trail arming, and
>   liquidation ordering.
> - Decimal contents and occasionally timing/reason of emitted events.
> - Stored decision, order, position, funding, and engine-event strings.
> - Engine position snapshots and future sizing through accumulated balance changes.
> - Exact restore comparisons across mixed-version histories.
> 
> Sizing itself was already largely computed at precision 34. The material new surface
> is the remainder of engine transaction arithmetic.
> 
> An old snapshot and entirely old DB history should normally compare as before.
> Once an open position continues under the new arithmetic, exact mixed-history
> reconstruction is not guaranteed.
> 
> Deployment is safe only with a confirmed flat engine and a fresh post-upgrade
> snapshot. Unconditional deployment over an open position is not safe.
> 
> Yes, restore needs either an explicit arithmetic-version guard or a documented,
> enforced flat-only upgrade boundary.
> 
> ## Q4 — Restore failure modes
> 
> - Effective SL: the latest ordered `StopTrailed` after the root timestamp is used.
>   This works for the normal single-root case.
> - Crash after events, before snapshot: unresolved; it causes a false mismatch and
>   abandonment.
> - Partial closes: ordinary `PositionReduced` rows are reflected in remaining
>   quantity and trigger snapshots. No new test combines partial close, trail state,
>   and restart.
> - Same millisecond positions: unresolved timestamp ownership ambiguity.
> - DB retry TP: the resolved TP is captured at the correct time in `(events, tp)`.
> - DB retry ordering: unresolved; later batches may bypass the queued batch.
> 
> ## Q5 — Other observations
> 
> Rows #21 and #22 generally match the code. QV scale and feature provenance are
> recorded correctly, including metadata rows `[18, 19, 20, 22]`.
> 
> The default no-trail/no-TP-rule path emits none of the new trail events and retains
> the old snapshot shape. It is not numerically byte-identical to the prior bot because
> the 28→34 engine arithmetic change is intentional.
> 
> Tests could not be executed. `uv run pytest` could not create its cache lock, and the
> existing virtualenv could not find any writable temporary directory. The unrun
> files were:
> 
> - `tests/test_backtest_placebo.py`
> - `tests/test_trial01_p4.py`
> - `tests/test_trial01_features.py`
> - `tests/test_decimal_context.py`
> - `tests/test_ops_restore.py`
> - `tests/test_paper_engine.py`
> 
> No files were edited; the worktree remained clean.
> 
> VERDICT: FIX-FIRST (atomic event/snapshot persistence, FIFO DB retry, Decimal upgrade guard)
> 
> Codex session ID: 01a0c468-be98-7a32-b5e2-2fa11bd43972
> Resume in Codex: codex resume 01a0c468-be98-7a32-b5e2-2fa11bd43972


## 2026-09-22(UTC 09-21 20:0x) — 단계 d 후속 2차 수정(사용자 "Batch approved as proposed — all seven items") · 손익 계산 없음
1. **이벤트 + 스냅샷 한 트랜잭션**(봇 결함 · 05d6031부터 · 레지스트리 #23): `db.record.record_events(..., snapshot=…)` · 런타임은 SNAPSHOT_EVENTS가 있으면
   스냅샷 행을 이벤트와 함께 넘긴다 · 봉 스냅샷도 같은 경로. **장애 주입 테스트**: 하위 프로세스가 `StopTrailed` 이벤트 행을 넣은 직후·스냅샷 행을 넣기 직전
   `os._exit(137)`로 **실제 종료**(마커 파일로 지점 확인) → 부모: 종료 코드 137 · StopTrailed 행 0(롤백) · 마지막 스냅샷 SL = 이동 전 → 재기동 `restore`(버리지 않음).
2. **DB 재시도 FIFO**(봇 결함 · 05d6031부터 · #23): `unrecorded`가 비어 있지 않으면 뒤 묶음(봉 스냅샷 포함)은 직접 쓰지 않고 줄 뒤로 · 항목 = (이벤트, TP, 스냅샷 행).
   테스트: 진입 기록 실패(주입) → 트레일 이동 · 부분 청산 · 전량 청산이 모두 줄 뒤에 섬(직접 쓰기 0회) → 재시도 후 open 1 · close 2개 모두 같은 root · 고아 0 · StopTrailed position_id = root.
3. **산술 버전 가드**(#23): 엔진 스냅샷 `raw_json.arith = exec_ctx/v1/prec34/half_even` · 복원은 태그가 다르거나 없으면 불일치(flat + 차단 + 알림) ·
   flat이면 대조할 것이 없어 영향 없음(§9.7 정상 경로 테스트). 복원 판단 자체도 `EXEC_CTX`.
4. **소유 = position_id**(스키마 v3 · 추가 전용 NULL 허용 열 `funding_events.position_id`·`engine_events.position_id` + 인덱스): 펀딩·트레일 행은 기록 시 열린 root id ·
   복원은 id로 묶고 옛(NULL) 펀딩 행만 시각 경계로. 테스트: 같은 ms에 트레일 포지션이 닫히고 새 포지션이 열려도 앞 포지션의 펀딩·StopTrailed가 새 root에 붙지 않음 · v2→v3 마이그레이션(기존 행 보존·NULL).
5. **계좌 스냅샷 산술 EXEC_CTX**: 테스트가 런타임 전체(틱·봉·진입·트레일·스냅샷)를 호출자 문맥 기본/ccxt 모양/6자리에서 돌려 **DB 전체 표(account_snapshots 포함)** 바이트 동일(벽시계 열만 제외).
6. **P4 이력 보존**: 조회용 봉 이력은 아직 내지 않은 15m 버킷 마감 − 24h − 1분까지 유지(1시간 여유 규칙 폐기) · 30시간 결손 합성 테스트로 불변식 확인.
7. **무장만 된 트레일 테스트 교정**: dist 900(> 2R)로 실제로 +1R에 무장하되 SL은 그대로 → armed=True · moved=False가 재기동을 넘어 유지.
**문서**: 레지스트리 #23(1·2는 **봇 결함 수정**이지 트라이얼 변경이 아님) · TODO 5o에 두 결함을 "두 번째 저장소" 증거로 · 런북 §9.7에 v3 마이그레이션(사본 → `--status` → 적용 → `--status`)과 새 스냅샷의 arith 태그 확인.
**검증**: 856 passed · ruff·pyright 0 · stream-tiers 0 · 백테스트 경로 불변: 30일 조각 A decisions `789bf4d5…`·trades `80991df7…` · P4 추출 0 decisions `cd81a95a…`·trades `49327350…`(이전과 동일).
**메모리 판독**: 작업 a8905872는 살아 있고 09-22 00:07 UTC(00:10 겹침 창 직전)에 실행 예정 — 수동 실행은 그 창을 놓치므로 하지 않음.


## 2026-09-21 — 단계 d 후속 3차 Codex 검토(97a89a9) · task-mubog0qp-clw9vz · 판정 **MERGE**
비차단 지적 처리: #1(FIFO 전역 아님)·#3(장애 중 큐 무한 성장) → TODO 5o에 기록 · #2(롤백 절차 없음) → 런북 §9.7에 `.backup` 사본·integrity_check·롤백 절차 추가(문서만). 아래 원문 그대로.

> ## Findings
> 
> 1. **MEDIUM — FIFO is not global**
>    [runtime.py:359](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:359),
>    [runtime.py:452](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:452),
>    [runtime.py:502](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:502)
> 
>    `unrecorded` orders engine-event/snapshot batches only.
>    Ops events and safety state may commit ahead of an older failed batch.
> 
>    A close can remain memory-only while its kill-switch state becomes durable.
>    A crash then restores the pre-close position with post-close safety state.
> 
>    This is fail-closed, but causally inconsistent.
>    Fix through the durable journal design in TODO 5o.
>    Do not merely delay safety persistence behind the volatile queue.
> 
> 2. **LOW — rollback procedure is incomplete**
>    [migrate.py:112](/home/cms/project/BTC_Futures_E2E/db/migrate.py:112),
>    [runbook_vps.md:237](/home/cms/project/BTC_Futures_E2E/docs/runbook_vps.md:237)
> 
>    `05d6031` cannot normally start on a v3 DB.
>    Its migration guard rejects the unknown version.
> 
>    The runbook creates a pre-v3 copy but does not document restoring it.
>    A code rollback against the migrated DB therefore causes startup failure.
> 
>    Add explicit rollback steps.
>    Prefer SQLite `.backup`, or checkpoint WAL before copying.
> 
> 3. **LOW — outage queue is unbounded**
>    [runtime.py:381](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:381),
>    [runtime.py:481](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:481),
>    [runtime.py:408](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:408)
> 
>    Every bar adds a snapshot-only batch while DB recording is unavailable.
>    A long outage grows memory without limit.
>    Recovery drains the complete backlog synchronously on the loop thread.
> 
>    Restore ordering remains correct.
>    Consider coalescing consecutive snapshot-only entries and alerting on depth.
> 
> ## Q1 — Seven items
> 
> | Item | Status | Evidence |
> |---|---|---|
> | 1. Atomic event + snapshot | **RESOLVED** | [record.py:313](/home/cms/project/BTC_Futures_E2E/db/record.py:313), [runtime.py:355](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:355); `test_kill_between_event_rows_and_snapshot_rolls_back_both_and_restore_stays_consistent` |
> | 2. FIFO retry | **RESOLVED for engine batches** | [runtime.py:379](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:379), [runtime.py:395](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:395); `test_db_retry_is_fifo_entry_failure_then_trail_partial_and_full_close` |
> | 3. Upgrade guard | **RESOLVED** | [decimal_context.py:18](/home/cms/project/BTC_Futures_E2E/exchange/decimal_context.py:18), [restore.py:114](/home/cms/project/BTC_Futures_E2E/ops/restore.py:114), [restore.py:142](/home/cms/project/BTC_Futures_E2E/ops/restore.py:142); arithmetic-version and flat-upgrade tests |
> | 4. Position ownership | **RESOLVED** | [schema.py:229](/home/cms/project/BTC_Futures_E2E/db/schema.py:229), [record.py:346](/home/cms/project/BTC_Futures_E2E/db/record.py:346), [restore.py:71](/home/cms/project/BTC_Futures_E2E/ops/restore.py:71); same-ms ownership and v2→v3 tests |
> | 5. Snapshot context | **RESOLVED** | [runtime.py:468](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:468); `test_runtime_db_including_account_snapshots_is_byte_identical_under_any_caller_context` |
> | 6. P4 retention | **RESOLVED** | [p4.py:55](/home/cms/project/BTC_Futures_E2E/strategies/trial01/p4.py:55), [p4.py:121](/home/cms/project/BTC_Futures_E2E/strategies/trial01/p4.py:121); long-gap retention test |
> | 7. Armed/unmoved test | **RESOLVED** | [test_ops_restore.py:371](/home/cms/project/BTC_Futures_E2E/tests/test_ops_restore.py:371); asserts armed before and after restart |
> 
> The crash test is genuine.
> 
> The fixture inserts all event rows, writes a marker, then calls `os._exit(137)`
> from the patched snapshot insertion:
> [fixture:31](/home/cms/project/BTC_Futures_E2E/tests/fixtures/crash_between_event_and_snapshot.py:31).
> 
> That occurs inside `record_events()`’ still-open transaction.
> `os._exit` performs no Python context-manager cleanup.
> The next connection verifies SQLite rolled back both sides.
> 
> ## Q2 — FIFO boundaries
> 
> No ownership-sensitive engine event or `source='engine'` snapshot bypasses
> `unrecorded`.
> 
> These independent paths can still write while it is non-empty:
> 
> - Ops events: [runtime.py:452](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:452)
> - Safety state: [runtime.py:502](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:502)
> - Exchange snapshots: [runtime.py:485](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:485)
> - Bar rows: [runtime.py:211](/home/cms/project/BTC_Futures_E2E/ops/runtime.py:211)
> 
> Exchange snapshots, bars, and safety rows are not inputs to paper-position restore.
> Ops events that bypass the queue are not trail events and have no ownership role.
> 
> Thus they do not recreate the orphan-close/phantom-root defect.
> They do leave the broader crash-consistency risk in Finding 1.
> 
> Queued per-bar snapshots are restore-safe because each is replayed FIFO.
> Any committed prefix ends at a transaction boundary.
> Growth and recovery-loop latency remain unbounded as noted above.
> 
> ## Q3 — Migration and rollback
> 
> The v2→v3 migration is safe for the forward deployment:
> 
> - Only nullable columns and indexes are added.
> - Existing rows remain `NULL`.
> - Applied v1/v2 checksums are validated.
> - The entire v3 step and its version row share one transaction:
>   [migrate.py:128](/home/cms/project/BTC_Futures_E2E/db/migrate.py:128).
> - Rollback on statement failure is explicit.
> - Standard v2 upgrade does not depend on legacy absorption.
> - The migration regression test passed here.
> 
> Old SQL inserts would tolerate the extra nullable columns.
> Normal `05d6031` startup does not: its migration code rejects schema v3.
> 
> Section 9.7 is sufficient for the planned forward, flat-only deployment.
> It is not a complete code-rollback procedure.
> Document restoring the pre-v3 backup or rolling forward to a compatibility build.
> 
> ## Q4 — Default path
> 
> No unintended trading-path change found.
> 
> The healthy default path changes only as intended:
> 
> - Atomic event/snapshot commits.
> - FIFO engine-batch retry.
> - Arithmetic tags.
> - Nullable ownership IDs.
> - Snapshot calculations under `EXEC_CTX`.
> - The status file gains `pending`.
> - P4 retention affects only the trial P4 feed.
> 
> Flat restore remains compatible with untagged snapshots.
> [restore.py:134](/home/cms/project/BTC_Futures_E2E/ops/restore.py:134)
> returns `none` before applying the arithmetic-version guard.
> 
> An untagged snapshot with an open DB position deliberately fails closed.
> 
> ## Q5 — Other risks and verification
> 
> Registry row 23, TODO 5o evidence, and §9.7 match the implementation.
> No OOS command, backtest runner, trade file, VPS, or credential was touched.
> 
> Passed in this read-only environment:
> 
> - FIFO retry
> - v2→v3 migration
> - Full runtime Decimal-context invariance
> - P4 long-gap retention
> - Status `pending` coverage
> 
> The five file-backed restore/crash tests could not run because no writable
> temporary directory exists; `.codex_tmp` is absent and unwritable.
> Their code and assertions were reviewed statically.
> 
> The worktree remained clean.
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0c594-ed57-74f2-b004-72ec53ce8cb5
> Resume in Codex: codex resume 01a0c594-ed57-74f2-b004-72ec53ce8cb5


## 2026-09-21 20:37 UTC — §9.7 배포(2026-09-22 00:35–02:30 UTC 승인) 창 밖 사전 점검(읽기만)
- ⚠️ **접속 주의**: `~/.ssh/config`의 `tokyo` 별칭은 **54.95.163.55**(다른 호스트 · `/home/btcfut` 없음)다 — 이 봇 VPS가 아니다.
  봇 VPS = `ssh -i ~/.ssh/e2e-bot-key.pem ubuntu@35.79.38.63`(호스트 `ip-172-31-38-160`). 잘못된 호스트에는 읽기 명령(hostname·uptime·which·ls)만 실행됨.
- VPS: `sqlite3` CLI 있음(`/usr/bin/sqlite3` · 파이썬 sqlite 3.46.1) · 봇 HEAD `05d6031` · 작업트리 깨끗 · status.json 나이 0.8초 ·
  `position None` · 차단 [] · db_errors 0 · unrecorded 0(옛 코드라 `pending` 필드 없음) · btcfut-bot active(2026-09-19 00:40:20 UTC) · NRestarts 0 · MemoryPeak 229.5 MB ·
  타이머 3개 waiting.
- E2E 기준선: e2e-l2collector active(2026-09-17 00:13:23 UTC) · NRestarts 0 · depthdiff·markprice running · e2e-sync activating(정상 주기) · 메모리 available 896 MB · 디스크 47%.
- 배포 커밋 = `2a47d94`(Codex MERGE 97a89a9 + 문서만). 창 시작 예약(세션 작업) 00:36 UTC.


## 실패 패턴 목록(near-miss 포함 · 2026-09-21 신설 · 새 항목은 이 절에 이어 붙인다)
| # | 날짜(UTC) | 패턴 | 무슨 일이 있었나 | 막은 것 · 재발 방지 |
|---|---|---|---|---|
| F1 | 2026-09-21 20:37 | **이름이 모호한 SSH 별칭이 다른 호스트를 가리킴** | 배포 창 밖 점검에서 `ssh tokyo`를 썼는데 `tokyo` = **54.95.163.55**(VCB 호스트)였다 — 봇 VPS는 35.79.38.63. `/home/btcfut` 없음 출력으로 알아챘다. 실행된 것은 읽기 명령(hostname·uptime·which·ls)뿐 | **첫 출력의 hostname을 기대값(`ip-172-31-38-160`)과 대조**해 멈췄다. 로컬 `~/.ssh/config`에 명시 이름 `e2e-vps`(35.79.38.63 · e2e-bot-key.pem · IdentitiesOnly)·`vcb-tokyo`(54.95.163.55) 추가(원본 `config.bak-20260921` 보존 · `tokyo`는 그대로) · 둘 다 hostname으로 확인. 런북 명령은 **명시 IP 그대로** 둔다(사용자 2026-09-21). 규칙: 호스트에 닿는 모든 세션의 첫 명령은 `hostname` 대조 |
| F2 | 2026-09-22~23 | **정해진 시각의 측정 창을 세션 수명에 맡김** | 00:07/00:08 메모리 표집을 세션 전용 cron(09-22)·사용자 요청 시점(09-23)에 의존 → 이틀 연속 창을 놓치고 추정값만 남았다 | 측정 창이 있는 작업은 **세션과 무관한 예약**으로: `scripts/vps_memory_sampler.sh`(읽기 전용) + 로컬 nohup 예약(09-24 00:07:50 UTC). 호스트 타이머는 호스트 변경이라 쓰지 않는다 |


## 2026-09-22 — 메모리 판독(09-22) + §9.7 배포(창 00:35–02:30 UTC · 커밋 2a47d94 · E2E 호스트 변경 없음)
**세션 재생성**: 예약 작업 a8905872(00:07 판독)·9be71a2f(00:36 창 시작)는 세션 전용이라 이전 세션과 함께 사라졌다 → 01:51 UTC에 수동 진행.
### 메모리 판독(읽기만 · 01:51 UTC — 실시간 00:08–00:15 표집은 **놓쳤다**)
- 봇: active(2026-09-19 00:40:20부터 3일) · NRestarts 0 · MemoryCurrent 163 MB · **MemoryPeak 229.5 MB**(09-19 기동 이후 · 정지 로그 "218.8M memory peak") · 상한 400 MB 대비 여유.
- cgroup `memory.events`: low 0 · high 0 · max 0 · oom 0 · oom_kill 0 · oom_group_kill 0(sock_throttled 2 — 메모리 압박 아님).
- e2e-quality(09-22): 00:10:00 시작 · 00:11:32 종료 · Result success · **MemoryPeak 544.6 MB**(09-18 기준 595 MB보다 낮음) · `l2-2026-09-21.json` 00:11 생성.
- e2e-l2collector: active · NRestarts 0 · ActiveEnter 2026-09-17 00:13:23 UTC(**기준선 그대로**) · 커널 OOM 로그(00:00–00:30) 없음.
- sysstat(10분 간격): 00:10:00 kbavail 964,616(= 942 MB · quality 시작 시점) · 00:20:00 965,132. **00:10–00:12 최저 가용은 직접 관측되지 않음** —
  추정 ≈ 942 − 545 ≈ **~400 MB**(quality 피크가 시작 뒤 전부 새로 쓴다고 보는 보수적 추정 · 측정값 아님) → ~300 MB 기준 **위로 추정**, swap 결정은 보류.
  실측 확정은 다음 00:10(09-23)에 5초 표집을 다시 돌려서(세션 전용 예약의 한계 — 수동 또는 호스트 쪽 도구 필요).
### §9.7 배포(모든 호스트 명령 전 `hostname` = ip-172-31-38-160 확인)
- 정지 전: status.json 나이 0.7초 · position None · 옛 코드라 pending 필드 없음 · 차단 [] · db_errors 0 · unrecorded 0.
- 01:52:19 `bsc stop` → 01:52:21 inactive · Result success · exit 0 · status.json `shutdown=stop`(stop_dirty 아님) · delivered 2 = sent 2.
- DB 열린 root **0** · 스키마 2 · `sqlite3 .backup` → `var/bot.sqlite.pre-v3`(2,740,224 B) · `PRAGMA integrity_check` **ok** · 사본 스키마 2 · 엔진 스냅샷 4,393행.
- `git fetch` → `checkout 2a47d944566edaf42398359b283402a6aca7825f`(rev-parse 확인) · `uv sync --frozen`(numpy 2.5.3 설치만) ·
  `db.migrate --status` 2 → 적용 [3] → `--status` 3 · `funding_events.position_id` 열 확인 · 이후 `integrity_check` ok · 스키마 3.
- 01:53:05 `bsc start` → active · NRestarts 0 · 01:53:09 기동 알림(🟢 기동 [paper] BTCUSDT · 지갑 1000 · 규칙 rest/rest:signed) **delivered 1 = sent 1** · poll_errors 0.
- 복원 경로: 결정 `none`(DB flat · 스냅샷 flat) — 설계상 운영 이벤트·알림 없음 · 기동 뒤 엔진 이벤트는 `Backfill`(inserted 1 · failed 0)뿐.
- status.json: position None · **pending False** · 차단 [] · db_errors 0 · unrecorded 0 · rules runtime:signed · mark 나이 1초.
- 새 스냅샷: id 4394(01:54:00)·4395(01:55:00) `arith = exec_ctx/v1/prec34/half_even` · reason bar · position null.
- bot.log 01:53 이후 ERROR/Traceback/WARNING 0 · 메모리 214 MB(기동·백필 직후).
- E2E: e2e-l2collector ActiveEnter 2026-09-17 00:13:23 · NRestarts 0 그대로 · depthdiff·markprice running · failed 유닛 없음.
- 롤백 불필요. 첫 btcfut-sync(02:20) 확인은 아래에 덧붙인다.
- 첫 btcfut-sync(기동 뒤): 02:20:12 시작 → 02:21:44 Finished · Result success · exit 0 · 1분 32초 · peak 119 MB(직전 01:20 실행 1분 34초 · 121 MB와 같은 모양).
  같은 시점: 봇 active · NRestarts 0 · MemoryPeak 214.7 MB · status.json position None · pending False · 차단 [] · db_errors 0 · unrecorded 0 · delivered 1 = sent 1 ·
  e2e-l2collector ActiveEnter 2026-09-17 00:13:23 · NRestarts 0. **배포 완료 · 롤백 없음** · 백업 `var/bot.sqlite.pre-v3`는 남겨 둔다(삭제는 사람 확인 + Codex).


## 2026-09-22 — 단계 e 준비: 판정기·P1 실행기·실행기 커밋(**어떤 실행보다 먼저**)
- `backtest/evaluate.py`(게이트 순수 함수 + 모든 산출물이 있어야만 여는 main · 전략 모듈 import 금지) · `backtest/p1_run.py`(Arm A에서 P1 입력 4필드만 · 추출 범위 분할 · 병합은 0..999 정확히) ·
  `backtest/step_e.py`(격리 실행 · verbatim 기록 · 이어 하기 · 최대 자식 RSS) · `placebo.EligibleIndex`(전체 IS에서 h별 적격 목록을 만들지 않는 게으른 색인 — 원래 목록과 같음을 테스트).
- 해석 = 레지스트리 #24(기록 시각 2026-09-22T02:37:44Z). 테스트 874 passed · ruff·pyright 0.
- 순서(사용자): 전체 IS Arm A(벽시계·RSS 실측) → B · P2(+1/+5) · P3 → P1 1,000(분할) → P4 200(로컬 병렬 · VPS 금지) → 판정기 한 번 → 보고 하나. OOS 닫힘.


## 2026-09-22 07:04 UTC — 단계 e 결과(IS · 판정기 한 번 · 커밋 b05d2e8의 판정기) · **IS 판정 REJECT** · OOS 닫힘 유지
실행(모두 격리 · verbatim 기록 `var/backtest/IS/step_e/_records/`): Arm A 159 s · B·P2(+1·+5)·P3 병렬 4 · P1 1,000(8조각 · 실패 0) · P4 200(병렬 4 · 4h13m · 실패 0) ·
최대 자식 RSS 2.4 GB · sr_v1 SHA 일치 · open_at_end 없음. `report.json` SHA256 `11c8845295823c24b107ab6ddd3b4d60c695eff5898b0a1cc89d05869b935e0d`.
| 게이트 | 값 | 규칙 | 결과 |
|---|---|---|---|
| G0(A) | n 1,297 · ρ̂ −0.016 → 0.15 사용 · n_eff 810.6 | n ≥ 48 ∧ n_eff ≥ 30 | 통과 |
| G1(A) gross | 평균 −1.18 bps · 97.5% CI [−5.46, +3.14] | 평균 > 0 ∧ 하한 > 0 | **실패** |
| G2(A) net | 평균 −18.54 bps · 97.5% CI [−23.34, −13.70] · θ 10 | 평균 > 0 ∧ 하한 > 0 | **실패** |
| G3 | — | OOS 1회 | **닫힘(미개봉)** |
| G-B | PSR(0) 0.000 · SR̂_A −0.238 · SR* 0.0012 · SR̂−SR* −0.239 · n 1,297 | PSR > 0.5 ∧ n ≥ 30 ∧ SR̂−SR* > 0 | **실패** |
| A/B | 평균 A −18.54 · B −18.22 · 차이 −0.33 · 97.5% CI [−5.52, +4.92] · B G0 통과(n 1,372 · n_eff 857.5) | A > B ∧ 하한 > 0 | **실패** |
| 벤치 flat | A Σ net_pnl −980.53 USDT(지갑 1,000 → 19.47) | > 0 | **실패** |
| 벤치 P1 | = P1 행 | — | 통과 |
| 매수보유(보고) | 일간 Sharpe 0.0248 · 창 수익률 +32.5% · A 일간 Sharpe −0.263 | 보고만 | — |
| P1 | p95 −33.38 · 성공 1,000 · 실패 0 | 원판 ≤ p95 → 기각 | 기각 안 됨(원판 −18.54 > −33.38) |
| P2 | +1 −20.33 · +5 −19.34 | 원판 ≤ max → 기각 | 기각 안 됨 |
| P3 | 반전 −15.19 | 원판 ≤ 반전 → 기각 | **기각** |
| P4 | p95 −14.44(200 · 트레이드 0건 추출 0) | p95 ≥ 원판 → 기각 | **기각** |
§7 분류: σ(net) 77.91 bps · MDE 7.67 bps(5 < MDE ≤ 20) → **결론 보류형 REJECT**(효과 부재 조건 MDE < 5 불충족 — net CI 상한 −13.7은 θ를 배제).
부록: 보유시간(분) A 중앙 93 · p10 15 · p25 38 · p75 198 · p90 371 · 평균 170 · ≥60분 64% · ≥240분 21% / B 중앙 80 · 평균 155 · ≥60분 59% ·
트레이드/일(912일) A 1.42 · B 1.50 · P2 1.37·1.43 · P3 1.67 · 청산 사유 A sl 655 · trail 491 · tp 125 · liquidation 26 / B sl 692 · trail 509 · tp 145 · liquidation 26 ·
skip_rate(분모 = 후보) A sl_dist_out_of_range 48.9% · no_sl_anchor 2.4% · conflict 2.9%(후보 50,925) / B 45.6% · 3.2% · 1.5%(후보 102,449).
🔴 **발견(판정 변경 아님)**: 복리(#19 ④) 지갑이 2024년 안에 무너져(A 분기말 지갑 343 → 147 → 37.5 → 24.5) 이후 의도 대부분이 **엔진 사이징에서 최소 수량 미달로 거부**
(A `sizing_rejected` 23,498 중 below_min_qty 23,489 · 청산 게이트 9 / B 51,078 중 51,064) → A 체결은 2024년(1,271)과 2026년(26)뿐 · B는 2024Q3 이후 0.
IS 트레이드 표본은 사실상 **2024년 9~12개월**이다(트레이드당 bps 통계는 규모와 무관하므로 정의대로 유효하나, 2025~2026 시장은 거의 검정되지 않았다).
30일 조각의 하루 4.5건 대 전체 1.4건의 차이도 이것이다. 고정 자본으로 다시 돌리는 것은 **새 트라이얼**(§8).


## 2026-09-22 — 트라이얼 #1 포스트모템(문서만 · 새 가설 없음 · 파라미터 변경 없음)
- 사용자: 판정 수락(REJECT · 결론 보류형) · **OOS 영구 닫힘** · f0dc171 push 완료. 레지스트리 #25(판정 · holdout 개봉 0 · 표본 범위 단서) · #26(청산 포렌식) · #27(sl_dist 건너뜀 분포).
- learnings: `docs/learnings.md` 신설(L1~L5 + 측정 부록) — 헌법 스킬 learnings 표 반영은 사용자 결정.
- 측정 스크립트 `scripts/trial01_forensics.py`(실행 사실만 · 판정 불변) → `var/backtest/IS/step_e/forensics.json`.


## 2026-09-22 — 포스트모템 후속
- e5c5f7f push. 헌법 스킬(저장소 사본) `references/research-protocol.md` §7 "이미 기각된 것" 표에 L1~L5 + 측정 행 추가(레지스트리 #25~#27 인용) — 스킬 원본 v1.2는 사용자가 따로.
- 레지스트리 #28: #26 상태 보충(open-decisions #1 자료 · 트라이얼 #2 사전등록 전 사용자 판단 · 1m 봉 보수성과 뉴스 틱 반례 · 봇 레버리지 설정 변경 없음).
- 다음 트라이얼 논의 없음. 호스트 읽기 전용 · 봇은 전략 없이 계속. 09-23 00:08 UTC 5초 메모리 표집(수동 시작).


## 2026-09-23 00:51 UTC — 메모리 표집: **오늘 창(00:08~00:15) 놓침** · 보존값만 · 09-24 예약
- 사용자 요청이 00:51에 도착해 5초 표집 창이 이미 지났다(quality는 00:10:00~00:11:25에 이미 끝남) — 실측 최저 가용은 **오늘도 없음**.
- 보존값(읽기만): quality Result success · **MemoryPeak 544.3 MB**(어제 544.6과 사실상 같음) · 봇 active(09-22 01:53:05 배포 기동) · NRestarts 0 ·
  MemoryCurrent 157 MB · **MemoryPeak 214.7 MB** · cgroup memory.events 전부 0(sock_throttled 0) · 커널 OOM 0건 · e2e-l2collector NRestarts 0 · ActiveEnter 2026-09-17 그대로.
- sar(10분 간격): 00:10:00 kbavail 968,784(= **946 MB** · quality 시작 시점) · 00:20:00 989,548 → 00:10~00:12 최저는 **관측 안 됨** ·
  보수적 추정 946 − 544 ≈ **~400 MB**(측정 아님) → ~300 MB 기준 위 → **swap 변경 없음**(판정 보류: 실측 뒤 확정).
- 재발 방지: `scripts/vps_memory_sampler.sh`(읽기 전용 5초 표집 · 호스트 변경 없음) + 로컬 백그라운드 예약(세션과 무관하게 09-24 00:07:50 UTC 시작 ·
  출력 `var/mem/sampler_2026-09-24.log`). 세션 전용 cron이 세션과 함께 죽는 문제(09-22)와 같은 실패를 F2로 기록.
- **VPS 일회성 임시(transient) 표집 작업 등록**(사용자 승인 2026-09-23 · 읽기 전용): `systemd-run --user --collect --unit=btcfut-memsample
  --on-calendar="2026-09-24 00:07:50 UTC"` (btcfut 사용자 · `XDG_RUNTIME_DIR=/run/user/1001`) → `var/mem/sampler.sh <로그> 90 5`.
  스크립트는 **읽기만** 한다: `free -m` + cgroup `memory.current`(봇·e2e-quality·e2e-l2collector) 5초 간격 90회(00:07:50~00:15:20) ·
  끝에 봇 ActiveState/NRestarts/MemoryPeak·`memory.events`·`free -m`. 출력 `/home/btcfut/BTC_Futures_E2E/var/mem/sampler_2026-09-24.log`(추가 기록).
  **영구 유닛 파일 없음**(`Transient=yes` · `~/.config/systemd/user/`에 memsample 없음 · `--collect`로 실행 뒤 정리 · 재부팅하면 사라진다) ·
  `list-timers` 확인: NEXT 2026-09-24 00:07:50 UTC. 스모크 테스트(2회·3초) 정상 — quality는 비활성이라 `-`, 00:10에 cgroup이 생기면 값이 찍힌다.
  로컬 nohup 예약(내 기기)은 **백업으로 유지** — 둘 다 같은 로그 이름을 쓰지 않는다(VPS는 호스트 경로, 로컬은 저장소 `var/mem/`).
  호스트 파일 추가는 `var/mem/sampler.sh`(gitignore 안 · 유닛 아님) 하나뿐이고 봇 설정·유닛·DB는 건드리지 않았다.


## 2026-09-24 00:07:52~00:15:19 UTC — 메모리 5초 표집 **실측**(읽기 전용) · swap 결정: **만들지 않는다**
- 실행: VPS 일회성 transient 타이머(btcfut · `btcfut-memsample`)가 정시에 돌았고, 로컬 백업 예약도 같은 창을 돌았다(둘 다 읽기 전용 · 로그 두 벌 동일 구간).
- **00:10~00:12 최저 가용 메모리 = 509 MB**(00:11:28 · quality 종료 3초 전) · 표집 창 전체 최저도 509 MB · 기준 ~300 MB **위로 209 MB**.
- quality 구간 진행: 00:10:02 924 MB → 00:10:22 723 → 00:10:58 635 → 00:11:28 **509** → 00:11:33 936(quality 종료 · 00:11:31) → 창 끝 952.
- 봇: 표집 중 158~167 MB · **MemoryPeak 214.7 MB**(09-22 배포 기동 이후 · 상한 400 MB) · NRestarts 0 · cgroup memory.events 전부 0(oom/oom_kill 0).
- e2e-quality: Result success · 00:10:00~00:11:31 · **MemoryPeak 540.5 MB**(5초 표집으로 본 최대 484 MB — 표집은 피크를 놓칠 수 있어 systemd 값이 정본).
- e2e-l2collector: 최대 127 MB · NRestarts 0 · ActiveEnter 2026-09-17 00:13:23 그대로. 커널 OOM 없음.
- **판정: swap 파일 만들지 않는다**(레지스트리 #29 · TODO 5q 종결). 재검토 조건: 봇에 전략이 붙어 상주 메모리가 커질 때 · E2E quality 피크 증가 시.
- 정리: 호스트 임시 스크립트 `var/mem/sampler.sh` 삭제(로그는 보존) · transient 유닛·타이머는 `--collect`로 자동 정리됨(유닛 0·타이머 0·영구 유닛 파일 0) · 로컬 예약 작업도 남아 있지 않다.
  저장소의 `scripts/vps_memory_sampler.sh`(ssh 래퍼)는 다음 측정을 위해 남긴다.


## 2026-09-24 — 트라이얼 #2 사전등록 초안 **사전 검토(before-pass)** · advisor + Codex(task-muet5ijx-7eh6g8) · 둘 다 PROCEED
상시 규칙(CLAUDE.md 2026-09-24): 큰 작업 전후로 advisor + Codex 심층 검토 · 원문 기록 · 항목별 동의/이견.
Codex 제약: 코드·문서만 읽음(시장 데이터·var/·OOS 열람 금지 — 트라이얼 #2 값은 데이터를 보기 전에 정한다).

### Claude Code 항목별 입장(동의 ✅ · 이견 ⚠️ · 사용자 결정 🔶)
| 쟁점 | advisor | Codex | Claude Code 입장(초안 반영) |
|---|---|---|---|
| N 카운터 | 누적 N = 4(α 0.0125)가 헌법 기본 · N = 2면 "N 무증가" 근거 필요 | N = 2는 결정 수준에서 충족 | 🔶 **사용자 결정 N = 2를 따른다** + 초안에 "N 무증가" 근거(다른 신호 가족 · #1 영구 종결 · #1 신호 재사용 없음) 명시 · 보고서 맨 앞에 다시 올림 |
| 판정 주체 · A/B | B ⊂ A → A−B = (n_e/n)(μ_e−μ_c) 항등식 명시 · A/B는 부호와 함께 보고(게이트 아님) · 팔별 판정 | A가 1차 가설 · B는 "control"이 아니라 수축 필터 정책/하위집단 · A/B를 ACCEPT 게이트로 두면 필터 실패로 멀쩡한 돌파가 기각됨 | ✅ 둘 다 동의 — **Arm A = 판정 주체**, Arm B = 사전지정 하위집단 정책(보고 + 활성화 후보 아님) · A/B 97.5% CI는 **계산·보고**(일별 정책 PnL 차이 · 비활성일 0) · ⚠️ 사용자 문언("gates … A/B paired 97.5% CI")과 다르므로 🔶 확인 요청 |
| OOS 검정력 | ~85일 → n < 48 가능 · 실현 n으로 평가, 미달은 검정력 부족 | G0는 면제 못 함 | ✅ 창은 사용자 지정 그대로 · **G3는 실현 n으로 G0 규칙 적용 · 미달 = "검정력 부족"(통과 아님)** 사전확약 |
| 청산 0 생존 게이트 | 블랙스완 게이트 — 문언 그대로 사전확약 · Arm A IS에 적용 | Arm A의 IS·OOS·전진 | ✅ Codex 범위(A의 IS·OOS·전진) · B·플라시보는 보고 |
| TP | SL=시가·k 0.5면 2R은 거의 안 닿음 → 없음 또는 2R | +2R | ✅ **+2R 유지**(사용자 문언에 TP 있음 · #1 관례) + "드물게 발동" 공시 |
| 트레일 거리 | ATR_15m×1.0(진입 때 고정) | **1R**(일 스케일) | ⚠️ advisor에 이견 — SL이 일 스케일(k·전일 범위)인데 트레일을 15m ATR로 두면 "ATR 스케일 ≠ 실행 스케일" 실패(learnings)를 되풀이 → **Codex 안: +1R 무장 · 거리 1R** |
| 마지막 진입 | 판단 봉 ≤ 21:59:59(보유 ≥ 2h) | 진입이 23:59:00 전이면 허용 | ⚠️ 자의 파라미터를 줄이려 **Codex 안**(체결이 23:59:00 전) · 짧은 보유는 보유시간 분포로 보고 |
| P4 정의 | k ~ U(0,1) · SeedSequence([20260924,4,d,day]) | 틱 오프셋 q ~ U{1틱…⌊R/틱⌋} → k* = q/R · 노출 정합 아님(수준 특이성 귀무) · 190/200 미만이면 폐기 | ✅ **Codex 틱 격자 + advisor 시드 규칙(#22 방식 일별 시드)** · "무엇을 검정하는가"(k 선택 대 무작위 k — 기준점·범위 척도는 남는다) 명시 · 평가 불가 기준 190/200 |
| 고정 명목 | 사이징 자본 1,000 고정(엔진 플래그) · 지갑은 누적 보고 | 실행 원장과 통계 원장 분리 | ✅ 둘은 같은 뜻 — **B2 사이징 자본 매 진입 1,000 USDT 고정**(복리 없음) · 통계 = 트레이드당 bps |
| 시간 청산 경로 | 엔진 exit 훅 + ExitReason.TIME_EXIT(구현 규약 행) | 23:59:00 첫 mark | ✅ 초안은 규칙만 · 구현은 코드 단계에서 규약 행 |
| 첫 교차 소비 | 막혀도 소비 · 청산 뒤 반대 방향 허용 | 같음 + 동시 교차 = 둘 다 소비(conflict) | ✅ |
| 수축 중앙값 | 최근 20일 | R[d−1] < median(R[d−21]…R[d−2]) · 짝수 = 가운데 둘 평균 · 21일 워밍업 | ✅ Codex 정의(검정 대상 날 제외) |
| 봉 안 순서 | 청산 > SL > TP(#19 ⑦) | 청산 → SL/트레일 → TP · 펀딩 후 청산가 재계산 | ✅ |
| P1 일 단위 | (h 최대 1,440분에서도 배치 가능) | 일별 0/1/2 개수 벡터를 적격 일에 섞고 분 무작위 · 방향/일 1회 · 23:59 전 청산 | ✅ Codex 적응안(트라이얼 #1 (a)~(f) 유지 + 일 단위 제약) |
| 킬스위치 | — | 생존 게이트로 0회 권고 | ⚠️ 백테스트는 킬스위치를 모사하지 않음 → **보고 불가 공시 · 전진 G-F에서 0회 확인**(생존 게이트는 사용자 결정대로 청산 0) |
| sl_dist 띠 | 사용자 [0.30%, 2.00%] | [0.30%, 5.00%] 권고 | ✅ **사용자 값 [0.30%, 2.00%]** · 상한 초과 비율 보고 |
| 비용 문턱 | R 50~200 bps 대비 비용 8~30% | 손익분기 이동 14 bps + 펀딩 · θ 포함 24 bps · 넓은 띠만으로 L4를 피하지 못함 | ✅ 둘 다 초안 §2에 반영 · 보유시간 분포 필수 보고 |
| 증류 | 24/7 시장엔 세션 시가가 없다 — 기준점의 정보성은 가설의 일부 | #74와 차이를 식·불변식으로 | ✅ §0·§9에 식과 테스트할 불변식 4개 |

### advisor 원문(verbatim)
> You're at the trial #2 before-pass. CLAUDE.md rule and registry #30 are committed (98c8199, unpushed); Codex is running. This is the advisor half. Wait for Codex, log both verbatim with per-point agree/disagree, then draft — don't start the draft before both land.
> 
> **Findings**
> 
> 1. **HIGH — N counter.** You wrote N = 2, α = 0.025. Constitution §1: "트라이얼을 추가하면 N이 오르고 임계가 올라간다 — 'N 무증가'를 주장하려면 그 근거를 적는다." Trial #1 spent 2 hypotheses. Cumulative N = 4 → α = 0.0125, CI 99.375% two-sided… no: Bonferroni α = 0.05/4 = 0.0125 → CI level 0.9875, and DSR's SR* over 4 SR̂s (trial #1's are −0.238/−0.235). If the user wants N = 2, the draft must state the "N 무증가" justification (different signal family; trial #1 definitively closed). This changes every CI and G-B — user decides before drafting; flag it first in your report.
> 
> 2. **HIGH — Arm roles are inverted vs trial #1 and B ⊂ A.** B's trades are *identical* to A's on compression days. So A−B = (n_e/n)(μ_e − μ_c): the "A/B" statistic is just a scaled expansion-vs-compression contrast. State that identity in the draft. Then pre-declare: (a) which arm is the judgment subject — recommend **arm-level verdicts, both arms run every gate, ACCEPT = any arm passes all, A activates if both pass, B only if A fails and B passes** (same shape as the T-S2 decision you were shown); (b) the A/B row is *reported with sign*, not a gate requiring A > B (that would test "the filter hurts").
> 
> 3. **HIGH — OOS is underpowered as specified.** OOS = 2026-07-01 → anchor−1 ≈ 85 days. At ≤2 trades/day and realistic ~0.4/day → ~35 trades < 48 (constitution: n ≥ 30(1+4ρ̄), "T1 계열은 창 ≥ 150일"). Either pre-commit "G3 evaluated on realized n; n < 48 → G3 = power shortfall, not effect-absent" or move the split (e.g. IS → 2026-03-31, OOS from 2026-04-01 ≈ 175 days). User's call; the draft cannot leave it implicit.
> 
> 4. **MEDIUM — Zero-liquidation gate is a black-swan gate.** At 30x, liq_dist ≈ 2.9%; with sl_dist cap 2.0%, B2 drops to L≈28 (2.0×1.5 = 3.0 > 2.88). Gap SL→liq ≈ 0.9–1.0%. Trial #1 forensics: median liquidation-bar range 0.49%, max 2.49%. On 1m-bar priority (liq > SL, #19 ⑦) one flash bar wider than the gap books a liquidation and REJECTs the trial. That's what the user asked for — pre-commit it verbatim, and pre-commit that it applies to **Arm A's IS run** (report B's count).
> 
> 5. **MEDIUM — Time exit needs a new engine path.** `engine_replay` has no strategy-driven exit hook, and `ExitReason` has no TIME_EXIT. Draft states the rule; implementation convention (registry row before P&L): strategy returns an exit request → `close_now(ref_mark = mark_open of the 23:59 bar, ts = 23:59:00, reason = TIME_EXIT)`. Adding the enum value is the same benign shape as TRAIL. Default path unchanged.
> 
> 6. **MEDIUM — Fixed notional needs an engine flag.** `replay()` compounds via `Engine.wallet`. Pre-commit: sizing equity fixed at 1,000 USDT per entry (`Engine(sizing_equity=…)`, default None = current behaviour); wallet still accumulates for the flat benchmark and final-wallet report. Same pattern as P1 in #19 ④.
> 
> 7. **MEDIUM — P4 as worded is a parameter null, not an information null.** "Random k per day from the prior 24h range, same band geometry" tests "is k = chosen better than k = random" — the anchor (today's open) and the range scale stay informative. Trial #1's P4 randomised the *level's information*. State plainly what this P4 tests. Propose exact rule: k_d,day ~ U(0, 1) via `SeedSequence([20260924, 4, d, day_index])`, symmetric band, same SL-at-open rule (sl_dist moves with k_d), same floor/cap. If the user meant "level ~ U[low_prev, high_prev] as a price, band = open ± |level−open|", say so — nearly equivalent, but pick one.
> 
> 8. **MEDIUM — TP geometry.** With k = 0.5 and SL = open: entry ≈ open+0.5R, sl_dist = 0.5R, trail arms at open+1.0R, TP = 2R sits at open+1.5R — today must exceed 1.5× yesterday's range. TP will almost never fire; exits will be trail/time/SL. Either accept 2R as the trial-#1 convention (mostly decorative, say so) or pre-commit **no TP** as the purer "continues through the day" test. User chooses.
> 
> 9. **LOW — "First cross per direction" when not flat.** Long open, short band crossed → skipped (one_position). Is the day's short *consumed*? Pre-commit: yes, consumed (stricter, deterministic, no "wait for a convenient cross"). Also pre-commit: after a stop-out, the other direction's first cross is eligible (reversal allowed).
> 
> 10. **LOW — 24/7 market has no session open.** The classical ORB premise is overnight-information release at the open. BTC's 00:00 UTC is a funding boundary and the daily-candle roll, not a session. Put one sentence in §0 saying the anchor's information content is part of the hypothesis, not assumed.
> 
> **Q1–Q6, short**
> 
> - **Q1** Distinct from #74 (1m rolling channel + meta-label) and from Donchian generally: the level is `open ± k·(prior H−L)`, not the prior H/L themselves; no N-bar highest/lowest anywhere (Arm B's 20-day *median of ranges* is a scalar, not a channel). Draft must carry the CLAUDE.md-mandated "how it differs from #74" paragraph. Not on the §7 short-signal list: hold is hours–1 day.
> - **Q2** A alone answers "does the breakout have edge". A/B (with the identity in #2) answers only "compression days vs expansion days within the same signal". It cannot answer "does the filter add information beyond the day partition" — that would need a different filter.
> - **Q3** Top invalidators, in order: N miscount (#1), zero-liq black swan (#4), OOS power (#3), look-ahead in "today's open"/20-day median (both are available at 00:00:00 if defined on closed data — say so), late entries with minutes of hold (see cutoff below), P1 placement failures with h up to 1,440 min (~365 slots × ~600 min ≈ 17% occupancy — should place; 10-failure rule stands).
> - **Q5** R here is 50–200 bps (k·R with BTC daily range 1–4%) vs ~16 bps cost (14 + ~2 funding for 2 boundaries) → cost ≈ 8–30% of R. Breakeven win-rate at 1R loss/2R win ≈ 38% net. Structurally clears L4's failure mode (trial #1 had ~20 bps moves vs 14 bps cost). The floor 0.30% skips low-vol days; the 2.0% cap skips high-vol days — report both skip shares.
> - **Q6** §8 gaps to close in the draft: expected-n row (say "G0 on realized n only", as #1 did), cost regime tag (copy trial #1 §2), OOS window vs n_eff (#3), N counter (#1), implementation conventions that will need registry rows before P&L (#5, #6, #7, P1 seed derivation).
> 
> **Pre-commit table (proposals + source — user confirms or overrides)**
> 
> | Field | Proposal | Source |
> |---|---|---|
> | Series | mark for open, range, cross, SL/TP/trail/fills (one series, no basis gap) | trial #1 #19 ⑦ analog |
> | Today's open | mark_open of the 00:00 bar; the 00:00 bar itself is cross-eligible | definitional |
> | Prior range R | max(mark_high) − min(mark_low) over prior UTC day's closed bars; < 2/3 minutes present → no trade | #19 ⑨ analog |
> | k | 0.5 | Williams (1999), Crabel (1990); standard 변동성 돌파 default |
> | Cross | closed 1m bar mark_high ≥ open+k·R (long) / mark_low ≤ open−k·R (short) | hypothesis wording |
> | Entry | next bar mark_open (engine re-sizes) | #19 ⑦ |
> | SL | today's UTC open → sl_dist = k·R/entry | classic ORB stop-at-open |
> | sl_dist band | [0.30%, 2.00%], skip + reason | user |
> | Trail | arm +1R, dist 1.0×ATR_15m(14) frozen at entry | #21 ⓙⓚ |
> | TP | user chooses: none, or 2R (#21 ⓙ) | see #8 |
> | Time exit | close_now at mark_open of 23:59 bar, ts 23:59:00, TIME_EXIT | user |
> | Last entry | decision bar close ≤ 21:59:59.999 (≥ ~2h min hold) | design; user confirms |
> | Direction rule | first cross per direction consumed even if skipped; reversal after stop-out allowed | see #9 |
> | Arm B filter | R_prev < strict median of the 20 most recent complete days' R | user |
> | Funding | actual history at 08:00/16:00 (00:00 never held) | #19 ⑦ |
> | Sizing | B2, risk 1%, L ∈ [10,30], **sizing equity fixed 1,000** | #30, L5 |
> | Skip denominator | first-cross setups passing one_position | #21 analog |
> | Seeds | P1 20260924; bootstrap (20260924,1); P4 (20260924,4) | #19 ③ pattern |
> | Survival | Arm A IS liquidations = 0 else REJECT(survival) | user |
> | Verdict classes | §7 of trial #1 + survival REJECT | trial #1 |
> 
> **BEFORE-PASS: PROCEED** — with #1 (N), #2 (arm roles), #3 (OOS split), #8 (TP) as explicit user decisions listed at the top of the draft's report. Everything else is a stated convention.

### Codex 원문(verbatim · task-muet5ijx-7eh6g8)
> I reviewed only source code and documentation.  
> I did not open `var/`, market-data files, backtest artifacts, or either trial’s OOS.
> 
> ## Numbered findings
> 
> 1. **HIGH — Arm B is not a control arm.**  
>    It is a prespecified subset of Arm A’s days.  
>    Calling it “control” overstates what the comparison identifies.
> 
> 2. **HIGH — Arm A must carry the primary alpha hypothesis.**  
>    An A/B gate would otherwise reject a profitable breakout merely because the contraction filter adds nothing.  
>    That would conflate breakout alpha with filter efficacy.
> 
> 3. **HIGH — P4 is not yet dimensionally defined.**  
>    A scalar `k` cannot literally be drawn “from a price range.”  
>    The draft must define either a random offset or a dimensionless distribution for `k`.
> 
> 4. **HIGH — “Fixed notional” and B2 sizing need reconciliation.**  
>    B2 produces risk-scaled execution notional.  
>    L5 requires equal statistical weight without compounding.  
>    These should be separate execution and statistical ledgers.
> 
> 5. **HIGH — 1m intrabar chronology can decide survival.**  
>    Cross, SL, trail, TP, funding, and liquidation may share a bar.  
>    The ordering must be conservative and frozen before implementation.
> 
> 6. **MEDIUM — Trial #1’s paired CI is not trade-paired.**  
>    It resamples the same UTC dates, then subtracts separate trade-weighted means.  
>    Empty B days disappear from B’s denominator.  
>    See [stats.py](/home/cms/project/BTC_Futures_E2E/backtest/stats.py:72).
> 
> 7. **MEDIUM — Trial #1’s P1 cannot be reused unchanged.**  
>    Global random-minute placement does not preserve the daily signal cap, UTC close censoring, or daily funding geometry.
> 
> 8. **MEDIUM — P4 can be well-defined but is not exposure-matched.**  
>    Random offsets alter crossing frequency and holding time.  
>    Treat P4 only as a level-specificity null; P1 remains the exposure null.
> 
> 9. **MEDIUM — The 1m implementation remains exposed to the short-signal finding.**  
>    Daily bands are structurally slower, but post-entry continuation can still end within minutes.  
>    Realized holding time must be reported; it cannot be assumed.
> 
> 10. **LOW — The Trial #1 evaluator is not a Trial #2 evaluator.**  
>     It hardcodes Trial #1’s module, thresholds, and A−B semantics.  
>     See [evaluate.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate.py:47).
> 
> ## Q1 — Scope and overlap
> 
> The hypothesis is materially distinct from Donchian #74, but it is still part of the broader breakout/continuation family.
> 
> The defensible distinction is mechanical:
> 
> \[
> R_{d-1}=\max(H_{d-1})-\min(L_{d-1})
> \]
> 
> \[
> U_d=O_d+kR_{d-1},\qquad D_d=O_d-kR_{d-1}
> \]
> 
> Both levels are fixed at 00:00 UTC and remain unchanged through day \(d\).
> 
> The draft must state:
> 
> - `O_d` is the 00:00 UTC 1m mark-bar open.
> - `R_{d-1}` uses only fully closed mark bars from the prior UTC day.
> - Levels never use a rolling highest-high or lowest-low.
> - Levels do not update intraday.
> - There is no channel lookback or Donchian function/import.
> - There is no logistic meta-label or secondary classifier.
> - There are at most two signal opportunities per day: first cross per direction.
> - No Trial #1 S/R, swing, VP, rejection, or 4h TSMOM feature is used.
> - The 1m bar is crossing/execution resolution; the level scale is daily.
> - E2E #74 remains prior negative evidence for breakout continuation generally.
> 
> Required tests:
> 
> - Two histories with equal `O_d` and `R_{d-1}` must produce identical bands.
> - Changing today’s running high/low must not move either band.
> - No rolling-extrema channel may exist in the code path.
> - Each direction’s first cross must permanently consume that direction for the UTC day.
> 
> That makes the distinction testable and complies with the repository’s Donchian prohibition in [CLAUDE.md](/home/cms/project/BTC_Futures_E2E/CLAUDE.md:38).
> 
> ## Q2 — What A/B can answer
> 
> Arm A should be the primary hypothesis:
> 
> > Does the daily fixed-band breakout possess positive gross and net post-entry continuation edge?
> 
> Arm B should be renamed the **contraction-filter policy** or **prespecified subgroup**, not control.
> 
> A/B can answer:
> 
> - Whether deploying only on contraction-qualified days improves policy-level results.
> - Whether qualifying days have different conditional trade quality.
> - Whether excluding non-contraction days helps or hurts.
> 
> It cannot answer:
> 
> - Whether the breakout itself has alpha.
> - Whether contraction causes the difference.
> - Whether B independently reproduces A.
> - Whether fewer B trades represent superior timing rather than reduced exposure.
> 
> Recommended contrasts:
> 
> 1. **Primary:** Arm A versus flat and P1.
> 2. **Policy contrast:** daily fixed-notional PnL  
>    `B_day − A_day`, with zero on days B is inactive.
> 3. **Filter-enrichment diagnostic:**  
>    B trades versus `C = A trades on non-contraction days`.
> 
> Use the same resampled UTC dates for the CI.
> 
> Do not call this trade pairing.
> 
> The Trial #1 statistic subtracts two separately normalized trade means.  
> That is not inherently biased for those two per-trade estimands, but:
> 
> - B’s selected dates receive different weights.
> - Empty B days vanish.
> - A and B overlap.
> - The difference is not a treatment effect.
> - Sparse B trading widens and destabilizes the CI.
> 
> The mandatory 97.5% A/B CI should therefore be secondary.
> 
> If it remains an overall ACCEPT gate, the registered hypothesis must explicitly be a conjunction:
> 
> > Arm A has alpha, and the contraction-only policy improves the prespecified A/B estimand.
> 
> Otherwise a valid Arm A breakout could be rejected for an unrelated filter failure.
> 
> ## Q3 — Main invalidation risks
> 
> 1. **Today’s open look-ahead**  
>    Use only the 00:00 mark open known at that instant.  
>    Never derive it from a completed daily candle.
> 
> 2. **Prior-range look-ahead**  
>    Use exactly the fully closed prior UTC day.  
>    No current-day extrema.
> 
> 3. **Median timing**  
>    Define whether the candidate prior day is included.  
>    I recommend comparing `R[d−1]` with the median of `R[d−21]…R[d−2]`.
> 
> 4. **UTC boundary artifact**  
>    Levels reset abruptly at midnight and all positions close daily.  
>    This is part of the strategy, not a neutral bookkeeping choice.
> 
> 5. **Late signals**  
>    A signal whose scheduled entry is 23:59 has no holding interval.  
>    It must be skipped by rule.
> 
> 6. **Funding boundaries**  
>    Entry/exit ordering at 00:00, 08:00, and 16:00 must be fixed.  
>    P1 must preserve comparable boundary exposure.
> 
> 7. **Intrabar ambiguity**  
>    A 1m bar can touch liquidation, SL, trail, and TP.  
>    Conservative ordering is necessary.
> 
> 8. **Liquidation after funding**  
>    Funding can reduce isolated collateral.  
>    Recalculate effective liquidation geometry after funding.
> 
> 9. **Trade-count power**  
>    The ceiling is only two signals per day.  
>    Actual crossings, busy-position skips, and B filtering can make B underpowered.
> 
> 10. **Within-day dependence**  
>     Two trades on one day are clustered.  
>     UTC-day block bootstrap is necessary; lag-1 trade autocorrelation alone is insufficient.
> 
> 11. **Regime concentration**  
>     A strong directional period can make long breakouts dominate.  
>     Report long/short and calendar-year results as diagnostics only.
> 
> 12. **Short OOS**  
>     The OOS period may satisfy calendar length but still fail G0, especially for B.  
>     G0 may not be waived.
> 
> 13. **P4 distribution**  
>     Uniform random offsets test the registered `k` against arbitrary offsets.  
>     They do not exposure-match the canonical strategy.
> 
> 14. **P1 daily cadence**  
>     Unrestricted global placement can put trades on too many days or violate the per-direction daily cap.
> 
> 15. **Contraction persistence**  
>     B days may cluster across regimes.  
>     A paired date bootstrap preserves that clustering but does not remove selection.
> 
> 16. **First-cross consumption**  
>     If a blocked or unsized first cross is silently ignored and a later cross is accepted, the strategy has been retrospectively improved.
> 
> ## Q4 — Conventions that must be frozen
> 
> | Convention | Recommended pre-commit | Source |
> |---|---|---|
> | Price family | Mark 1m OHLC for open, range, crossing, exits, and liquidation | Hypothesis consistency; Trial #1 mark basis |
> | Daily range | Prior UTC day `00:00…23:59` mark high minus mark low | User hypothesis |
> | `k` | `0.50`; no sweep | Williams-style volatility-breakout convention |
> | Daily bands | `O ± 0.5R`; fixed until next UTC midnight | Hypothesis |
> | Contraction median | Strict `R[d−1] < median(R[d−21]…R[d−2])`; even median = mean of middle two | Recommended; excludes the tested observation |
> | Warm-up | Require all 21 preceding complete days | Implied by the median definition |
> | Cross | Long: prior observed mark below U and current bar high reaches/exceeds U; short symmetric | Deterministic OHLC rule |
> | Signal entry | Next 1m mark open after the cross bar | Registry #19 precedent |
> | Entry fill | Next mark open plus 2 bps adverse slippage and adverse tick | Registry #7/#19 |
> | Gap beyond level | Reference `max(U, next_open)` long; `min(D, next_open)` short | Conservative stop-entry treatment |
> | Last eligible cross | Scheduled entry must be before 23:59:00 | Required by time exit |
> | SL | UTC open `O_d` | Natural invalidation of an open-relative breakout |
> | `R` for exits | Absolute distance from adverse entry fill to SL | Registry #21 precedent |
> | `sl_dist` band | Recommend `[0.30%, 5.00%]`; user must approve | 0.30% cost floor from Trial #1; 5% derived from 10x survival geometry |
> | TP | Full exit at `+2R` | Trial #1’s fixed fallback |
> | Trail | Arm at `+1R`; trail distance `1R`; ratchet only; effective next bar | Trial #1 structure, daily-scale adaptation |
> | Time exit | MARKET at the first mark observation at exactly 23:59:00 UTC | User decision |
> | Same-bar exit order | Liquidation → SL/trail → TP | Conservative Trial #1 precedent |
> | Entry-bar exit | No same-bar exit because entry occurs next bar; after entry, apply ordinary priority | Deterministic chronology |
> | One position | One position total; no pyramiding | Prior-trial engine |
> | Both directions | Allow sequential long and short on one day only after flat | Matches “first per direction” |
> | Busy-position cross | Consume the direction and record `position_busy`; do not reuse later crosses | Prevents cherry-picking |
> | Simultaneous crossings | Skip and consume both directions as `conflict_cross` | Intrabar order unknowable |
> | Cooldown | No extra minute cooldown; daily direction lock is the cooldown | Strategy structure |
> | Zero range | If prior range `< 1 tick`, skip the whole day | Doji/division guard |
> | Missing daily input | Any incomplete open/range/median day is data-invalid, not a no-trade day | Data-integrity rule |
> | Funding | Actual signed funding at 00/08/16; settle before processing that minute’s exits or new entries | Registry #19 |
> | Funding-at-entry | A position opened on the boundary minute does not receive/pay that boundary funding | Same ordering |
> | Statistical notional | `N_stat = 1,000 USDT` per trade; no compounding | Trial #1 starting scale plus L5 |
> | B2 reference capital | Reset `E_ref = 1,000 USDT`, `risk_pct = 1%` at every entry | Preserves B2 without compounding |
> | Execution notional | `budget/sl_dist`; statistical PnL later rescaled to `N_stat` | Reconciles B2 with L5 |
> | Leverage | Highest integer 10–30 passing both registry #5 liquidation gates | Registry #30 |
> | Runtime normalization | Quantity floor, then MIN_NOTIONAL recheck; runtime tick/step/brackets/fees | Constitution |
> | Skip denominator | First directional crosses on valid arm-days, before position, SL-band, and sizing gates | Clean opportunity denominator |
> | Skip reporting | Mutually exclusive first-failure counts: busy, conflict, late, SL-band, B2, normalization, missing input | Auditability |
> | G0 | Recommend Trial #1 rule: `n≥48` and `n/(1+4·max(ρ̂,0.15))≥30` | Registry #24 |
> | Bootstrap | UTC calendar-day blocks, empty days retained, 10,000 samples, 97.5% CI | Trial #1 |
> | Bootstrap seed | Recommend `SeedSequence((20260924,1))`, fixed child numbers by statistic | Registry #24 pattern |
> | P2 | Delay scheduled entry by exactly +1/+5 bars; keep day’s fixed bands and UTC close; delayed fill defines R | User decision plus registry #21 pattern |
> | P3 | Reverse direction only; mirror SL/TP/trail around entry using the original R distance | Registry #21 pattern |
> | P1 seed | `20260924`, PCG64 spawned into 1,000 draw streams | User decision |
> | P1 daily cadence | Preserve the canonical 0/1/2-trades-per-day count vector, randomly permute it over eligible UTC days, then randomize eligible minutes | Required adaptation |
> | P1 pairs | Resample `(sl_dist,h)` together; never separately | Trial #1 conventions |
> | P1 caps | At most one slot per direction/day, no overlap, all exits before 23:59 | Canonical geometry |
> | P1 failure | 1,000 placement attempts/slot; do not redraw pairs; >10 failed draws = DISCARD | Trial #1 conventions a–f |
> | P4 draw variable | Draw tick offset `q∼Uniform{1 tick,…,floor(R/tick)}`; set `k*=q/R` | Makes the null dimensionally valid |
> | P4 geometry | One `k*` per UTC day, shared symmetrically by upper/lower bands; all other rules unchanged | “Same band geometry” |
> | P4 seed | Recommend `SeedSequence((20260924,4)).spawn(200)[d]`; consume days in UTC order | Registry #22 pattern |
> | P4 evaluability | User must choose: recommend DISCARD if fewer than 190/200 draws have defined trade means | Prevents selective zero-draw removal |
> | P4 rejection | Canonical mean net bps `≤` random-level p95 means REJECT | Trial #1 rule |
> | Survival scope | Canonical Arm A in IS, OOS, and forward; B/placebos reported separately | Arm A is deployable strategy |
> | Liquidation gate | Count must equal zero; one modeled liquidation = REJECT on survival grounds | User decision |
> | Liquidation chronology | Bar open beyond liquidation counts immediately; otherwise adverse extreme with liquidation priority | Conservative precedent |
> | Funding and liquidation | Recompute isolated collateral/liquidation state after every funding settlement | Necessary survival accounting |
> | Kill-switch gate | Recommend zero activations of registry #11 daily-loss, consecutive-loss, and vanished-position rules | Constitution checklist |
> | B&H label | Preserve `ACCEPT — 수동(매수보유)을 이기지는 못함` | Trial #1 |
> | Verdicts | IS PASS only before OOS; ACCEPT after all gates; REJECT with power class; DISCARD for design/data/harness failure | Research protocol |
> | OOS | Trial #2 only; Trial #1 OOS remains permanently closed; exactly one opening after IS pass | Registry #25 |
> | Forward | Arm A only, 30 days; intermediate reports show survival/integrity, not performance | Prior protocol |
> 
> The two material user choices still requiring explicit approval are:
> 
> - Whether `[0.30%, 5.00%]` is the desired SL-distance band.
> - Whether P4 uses the new `(20260924,4)` namespace or literally reuses `(20260921,4)`.
> - Whether the A/B CI is secondary or an overall ACCEPT gate.
> 
> ## Q5 — Cost hurdle
> 
> The arithmetic break-even favorable movement is:
> 
> \[
> 14\text{ bps}+\text{signed funding}
> \]
> 
> If Trial #1’s economic threshold remains `θ = +10 bps`, the practical target is:
> 
> \[
> 24\text{ bps}+\text{signed funding}
> \]
> 
> That is the required post-entry movement.
> 
> The distance already traveled from today’s open to the breakout level is not earned by the strategy.
> 
> With a simplified `SL = 1R`, `TP = 2R` outcome:
> 
> \[
> E[gross]=(3p-1)R
> \]
> 
> Ignoring funding:
> 
> - At `R = 30 bps`, zero-net break-even needs about a 48.9% TP probability.
> - At `R = 30 bps`, a +10 bps net target needs about 60%.
> - At `R = 50 bps`, those figures are about 42.7% and 49.3%.
> 
> Trails and time exits change those exact probabilities.
> 
> A daily-range breakout can plausibly clear 14 bps because its risk and holding horizon are daily-scale.
> 
> But plausibility comes from scale only.
> 
> False breakouts, late entries, trails, and 23:59 exits can still realize moves below 14 bps.  
> The design therefore does not escape L4 merely by using a wide band.
> 
> ## Q6 — Current checklist failures
> 
> The following items are not yet satisfied:
> 
> - Non-overlap is not yet written as equations and executable invariants.
> - G0 planning values and B’s underpowered outcome handling are not frozen.
> - The 14 bps cost model needs its Trial #2 regime label.
> - P1 is registered conceptually but not defined for daily cadence.
> - P4 is registered but not dimensionally or statistically complete.
> - The Trial #2 Drive `createdTime` anchor does not yet exist.
> - Fixed-notional accounting is still ambiguous.
> - Cross, entry, exits, simultaneous events, and late signals are unspecified.
> - Median membership and missing-day handling are unspecified.
> - Kill-switch survival treatment is unspecified.
> - A/B’s estimand, sign, and gate status are unspecified.
> - Verdict thresholds and MDE classes have not been copied into Trial #2.
> - The canonical subprocess strategy and evaluator paths do not exist yet.
> - The evaluator must be committed and pushed before any run.
> - Trial #1 OOS closure must be stated explicitly in the Trial #2 draft.
> 
> Already satisfied at the decision level:
> 
> - IS/OOS calendar windows.
> - N = 2 and Bonferroni α = 0.025.
> - Flat and P1 benchmark requirements.
> - B&H reporting and label.
> - P2/P3/P4 families.
> - Fixed-notional principle.
> - 10–30x leverage policy.
> - Zero-liquidation survival rule.
> - Thirty-day forward-paper requirement.
> 
> BEFORE-PASS: PROCEED
> 
> Codex session ID: 01a0d0dd-883f-7d10-ba2c-0ca819413881
> Resume in Codex: codex resume 01a0d0dd-883f-7d10-ba2c-0ca819413881


## 2026-09-24 — 트라이얼 #2 초안 r1(334c0fa) **사후 검토(after-pass)** · advisor MERGE-after-fixes · Codex(task-mufaro9f-e1b4ci) **FIX-FIRST** → r2 반영
### Claude Code 항목별 입장(✅ 동의·반영 · ⚠️ 이견)
| 지적 | 출처 | 입장 · r2 반영 |
|---|---|---|
| 진입 기준가가 조용히 바뀜(`max(U, 다음 시가)` 누락) | Codex #1 HIGH | ⚠️ **의도적 이탈로 명시** — 전진·라이브 엔진은 결정 뒤 첫 mark에 체결하므로 다음 시가가 실제 기준(더 나쁜 가격 가정은 실행 경로와 어긋남) · §1 진입 행에 이유 기록 · Codex r2에서 수용 여부 확인 |
| 고정 명목 내부 모순(실행 명목 가변 · 통계 원장 없음) | Codex #2 HIGH | ✅ §1에 **실행 원장(E_ref 1,000 · B2)과 통계 원장(N_stat 1,000 × net_bps)** 분리 · flat·일별·A/B·매수보유 비교 식 명시 |
| 청산 판정 순서 불완전 | Codex #3 HIGH | ✅ §1 "청산 판정" 행(갭 포함 같은 봉 청산 · SL/TP보다 먼저 · 펀딩마다 재계산 · 손실 모델) |
| 게이트 순서 충돌(G3 대 G-B) | Codex #4 HIGH | ✅ §3 머리말: 헌법 순서 = 중요도 · 평가 순서 = IS(G0→G1→G2→G-B→생존→벤치→플라시보) → OOS → 전진 · §4-1·§7 일치 |
| 전진 판정 미정의 | Codex #5 HIGH | ✅ §7 단계별 판정표(IS PASS · OOS PASS · ACCEPT · 전진 실패 유형별) |
| P1 배치 유일하지 않음 | Codex #6 HIGH · advisor #2 | ✅ **advisor 단순안 채택**: 트라이얼 #1 (a)~(f) 그대로 + 적격 분에 "같은 UTC 일 · 청산 ≤ 23:58 · 완결성 만족 날" 제약 하나 · 일별 개수 순열·방향 캡 삭제(두 규칙 충돌·예측 가능한 폐기 제거) |
| P2 경계(23:59 동치 · 게이트 시점) | Codex #7 | ✅ `fill_ts ≥ 23:59:00 → dropped` · 결정 게이트는 지연된 결정 시각 상태로 |
| P4 시드 재현성(day_index · 분위수) | Codex #8 | ✅ `day_index = floor(open_ms / 86,400,000)` · numpy 선형 분위수 |
| 결손일 정책(2/3 대 엄격) | Codex #9 | ✅ **엄격 채택**(한 분이라도 없으면 그 암-일 데이터 무효) · 알려진 결손 2분의 영향(2024-08-13 · B 창) §5에 명시 |
| 검정력 라벨 충돌 | Codex #10 · advisor #7 | ✅ OOS G0 미달 = **"OOS 표본 부족"**(§7-2 MDE 분류와 다른 라벨) · IS G0 실패는 게이트 실패 + MDE 분류 병기 |
| 교차 술어 누락 | Codex #11 | ✅ 동치임을 §1에 명시 |
| 런타임 규약 일부 미정 | Codex #12 | ✅ §11 6·7·8(스냅샷 SHA · 반올림 · 시드 표 · 분위수 · 테스트 목록 · 산출물 스키마) |
| N 근거가 헌법 예와 반대 | advisor #1 HIGH | ✅ §0·§12-1을 **있는 그대로**: 헌법 기본 = 누적 N 4 · 제시한 근거는 헌법의 예와 맞지 않음 · 사용자 결정 N 2 |
| A/B 통계 두 개 | advisor #3 | ✅ CI는 **일별 정책 대비 하나** · 트레이드 평균 항등식·Σ 항등식은 해석용(§0) |
| SL 선택 미공개 | advisor #4 | ✅ §12-3 |
| G-B DSR 사실상 무의미 | advisor #5 | ✅ §3 G-B 행에 공시(규칙 유지) |
| 중앙값 창 문언 | advisor #6 | ✅ §12-5 |
| 시간 청산 = 재생 루프 훅 | advisor #8 | ✅ §1 시간 청산 행(그 봉 판정보다 먼저) · §11-1 `exit_at_bar_open` 프로토콜 |
| `sl_wrong_side` 건너뜀 사유 | advisor #9 | ✅ §1 결정 시점 게이트 · §7-3 |
| 00:00 기준 시각 특이성은 어떤 플라시보도 흔들지 않음 · mark 체결 근사 · P1이 날짜도 무작위화 | Codex Q7 | ✅ 한계로 공시(§0 · §2 · §4 끝) |

### advisor 원문(verbatim)
> You're in the after-pass; Codex is running on 334c0fa. This is the advisor half. Draft is close — findings below are text fixes, not redesign.
> 
> **Owning my before-pass deviations — the draft's choices are right, drop mine:**
> - Trail 1R (Codex) beats my ATR_15m: SL is day-scale, a 15m trail would repeat the "ATR 스케일 ≠ 실행 스케일" failure. Agree.
> - Last entry "fill < 23:59:00" (Codex) beats my 21:59 cutoff: one fewer arbitrary parameter; holding-time report catches the short holds. Agree.
> - P4 tick-grid q/R (Codex) + my per-day seed: correct and dimensionally clean. Agree.
> 
> **Findings (draft text, fix before anchor)**
> 
> 1. **HIGH — §0 N justification inverts the constitution's example.** §1 says N doesn't increase for "동일 가설의 전진 검증" — i.e. *same* hypothesis. Your reason ① "신호 가족이 다르다" is the case where N *should* rise: two new hypotheses tested on the same IS data → cumulative 4. Reasons ② ③ (closed trial, no result-driven values) are true but don't bear on the multiple-comparison count. Don't soften §12 — state plainly: "N = 2 is the user's decision; the constitution's default reading is cumulative N = 4 (α 0.0125); the stated 'N 무증가' reasons don't match the constitution's own example." Then the user rules with the tension visible.
> 
> 2. **MEDIUM — P1 (c) has two rules that collide.** `dir_k = rng.integers(0, 2)` per slot AND "방향마다 하루 1슬롯". A 2-slot day can draw LONG twice. An implementer resolves this three ways (redraw, complement, fail). Pre-commit one. Also: pairing (sl_dist, h) globally then assigning to days means two long-hold pairs can land on one day and not fit → placement failure → >10 → DISCARD. That's a *foreseeable* harness discard. Consider the simpler well-posed version: trial #1 (a)–(f) unchanged + one constraint "slot must lie within one UTC day, exit ≤ 23:58". Drop the count-vector permutation and per-direction cap — they don't change what P1 tests (exposure-matched random timing) and they add failure modes. Flag in §12 as a choice; Codex proposed the permutation, so let it weigh in.
> 
> 3. **MEDIUM — Two different "A/B" statistics.** §0 gives the per-trade mean identity `(n_e/n_A)(μ_e − μ_c)`; §3 defines the CI on daily fixed-notional `B_day − A_day`. Note that Σ(B_day − A_day) = −Σ(expansion-day A PnL) — say so. Pick one for the CI (the daily one is fine) and label the other as a derived identity, so the report can't be read two ways.
> 
> 4. **MEDIUM — SL choice not surfaced.** User offered two examples: "opposite side of the band" (= D_d, R_trade = 1.0·R_prev) or ATR multiple. You chose O_d (R_trade = 0.5·R_prev) with a stated source — defensible, but it halves R, doubles cap-skips' complement, and moves TP/trail geometry. Add to §12: "SL = O_d chosen over D_d; confirm."
> 
> 5. **LOW — G-B DSR is near-vacuous.** With B ⊂ A, SR̂_B ≈ SR̂_A → V[SR̂] ≈ 0 → SR* ≈ 0 (trial #1: 0.0012). The gate collapses to SR̂_A > 0. Disclose in §3 G-B row; keep the rule.
> 
> 6. **LOW — "previous 20 days" reading.** Draft uses R_{d−21}…R_{d−2} (Codex, excludes the tested day). User's wording ("prior day's range below the median of the previous 20 days") reads naturally as d−20…d−1, which *includes* the tested day. State the choice in §12.
> 
> 7. **LOW — §3 has two "검정력 부족" paths.** G3 on n < 48 (OOS) vs §7 MDE > 20 bps (IS). Label the OOS one "OOS 표본 부족" so reports distinguish them.
> 
> 8. **LOW — time exit is a replay-loop hook, not just an enum.** Exit must fire *before* `on_bar(23:59)` evaluates SL/TP on that bar, at its mark_open. Needs a `Strategy.exit_at_bar_open(bar) -> bool` protocol method (strategy logic stays in the strategy module, per 격리 실행). §11 item 1 should say this so the code step doesn't hard-code it in `replay()`.
> 
> 9. **LOW — add `sl_wrong_side`** to §7-1's mutually-exclusive skip list (cross bar closes below O_d for a long). Trial #1 had 0; record it anyway.
> 
> **Checks the draft passes:** every user field has a number or rule; look-ahead clean (O_d, R_{d−1}, median all from closed data at 00:00); §9 has the four testable invariants; L5 fixed notional; evaluator-before-run; P1 seed 20260924; survival gate verbatim; verdict classes copied.
> 
> **When Codex lands:** log both passes verbatim + per-point table (standing rule); apply the text fixes (1–4 minimum, 5–9 cheap); re-commit; then report **draft verbatim** + Codex verdict + §12 decision list with items 1, 2, 4, 6 added. Push of 98c8199/334c0fa/fixes is the user's call — ask.
> 
> **Advisor after-pass: MERGE after text fixes 1–4.** None require redesign; all are wording the user needs to see before anchoring.

### Codex 원문(verbatim · task-mufaro9f-e1b4ci)
> ## Numbered findings
> 
> 1. **HIGH — `docs/trials/trial_02_preregistration.md:36` — Entry reference changed silently.**  
>    Q4 required long `max(U_d, next_open)`, short `min(D_d, next_open)`. Draft uses the next open, including a retrace inside the band.  
>    **Fix:** freeze reference price first, then apply adverse 2 bps and tick.
> 
> 2. **HIGH — `docs/trials/trial_02_preregistration.md:50-51,90-91` — “Fixed notional” is internally inconsistent.**  
>    `budget/sl_dist` produces variable execution notional. Flat and A/B rows nevertheless call raw PnL “fixed-notional”; the promised `N_stat = 1,000` rescaling is absent.  
>    **Fix:** define separate execution and statistical ledgers, including exact daily/flat formulas.
> 
> 3. **HIGH — `docs/trials/trial_02_preregistration.md:44,89` — Liquidation chronology is incomplete.**  
>    Liquidation decides survival REJECT, but the Q4 rule—open beyond liquidation means immediate liquidation; otherwise adverse intrabar extreme—was not copied.  
>    **Fix:** state detection, fill price, gap treatment, and post-funding recalculation explicitly.
> 
> 4. **HIGH — `docs/trials/trial_02_preregistration.md:78-92,105-108` — Gate order conflicts.**  
>    §3 and constitution §2 place G3 before G-B; staging requires G-B during IS before OOS. This changes whether OOS is opened.  
>    **Fix:** choose one order and make §3, §4-1, §7 identical.
> 
> 5. **HIGH — `docs/trials/trial_02_preregistration.md:92,108,129-137` — Forward-test verdict is undefined.**  
>    Staging waits until the 30-day forward window, but ACCEPT omits G-F. “ACCEPT after G3” also leaves no explicit result for G3 pass followed by G-F failure.  
>    **Fix:** define `OOS PASS`, final ACCEPT conditions, and every G-F failure verdict.
> 
> 6. **HIGH — `docs/trials/trial_02_preregistration.md:100` — P1 placement is not uniquely implementable.**  
>    “Eligible days” is undefined; assignment of sampled slots to permuted day counts is unspecified; two independently sampled equal directions can conflict with the one-slot-per-direction cap.  
>    **Fix:** specify the date universe, zero-day handling, slot-to-date assignment, direction construction, and exact loop order.
> 
> 7. **MEDIUM — `docs/trials/trial_02_preregistration.md:101` — P2 has two boundary ambiguities.**  
>    “After 23:59” could allow a fill exactly at 23:59, contrary to §1. It also does not say when the decision-time and execution-time `sl_dist` gates are rerun.  
>    **Fix:** use `fill_ts >= 23:59:00 → dropped` and freeze both gate times.
> 
> 8. **MEDIUM — `docs/trials/trial_02_preregistration.md:103` — P4 seed is not fully reproducible.**  
>    `day_index = UTC day number` lacks an epoch/formula; p95 quantile convention is also unstated.  
>    **Fix:** define, for example, `floor(unix_ms/86_400_000)` and the percentile method.
> 
> 9. **MEDIUM — `docs/trials/trial_02_preregistration.md:30,47-48` — Missing-day policy departs from Q4.**  
>    Q4 required any incomplete daily input to be data-invalid. Draft accepts days with at least 2/3 of minutes while calling warm-up days “complete.”  
>    **Fix:** adopt strict completeness or record and justify the deliberate 2/3 override.
> 
> 10. **MEDIUM — `docs/trials/trial_02_preregistration.md:87,132-135` — Power classification can conflict.**  
>     G3 G0 failure is automatically called “검정력 부족,” while §7 reserves that label for MDE > 20 bps.  
>     **Fix:** state whether G0 failure overrides the MDE taxonomy or how both labels combine.
> 
> 11. **LOW — `docs/trials/trial_02_preregistration.md:33` — Q4’s prior-below crossing predicate is omitted.**  
>     `high ≥ U`/`low ≤ D` is deterministic and normally equivalent for the first touch because `O_d` starts inside fixed bands, but parity is incomplete.  
>     **Fix:** add the predicate or state the equivalence deliberately.
> 
> 12. **LOW — `docs/trials/trial_02_preregistration.md:50,55-56,169` — Runtime conventions remain partially deferred.**  
>     Exact filter snapshot, price/quantity rounding, bracket selection, bootstrap child mapping, and quantile conventions are not frozen.  
>     **Fix:** list them in the mandatory pre-PnL registry row.
> 
> ## Q1 — Planned vs done
> 
> Not every Q4 pre-commit was implemented.
> 
> - Cross predicate omitted: no stated deviation; practically equivalent under stated invariants.
> - Gap/retrace entry reference omitted: no reason; does not hold.
> - `[0.30%,5.00%] → [0.30%,2.00%]`: deliberate user override; reason holds.
> - Any-incomplete-day → 2/3 threshold: precedent is cited, but the deviation is not acknowledged; reason insufficient.
> - Funding excludes 00:00: deliberate because positions close at 23:59; reason holds.
> - `N_stat=1,000` rescaling omitted: ops log says fixed sizing capital is “the same meaning”; mathematically false for raw flat/daily PnL.
> - P4 spawned streams → per-day composite seeds: deliberate `#22` choice; acceptable after defining `day_index`.
> - Kill-switch moved from backtest recommendation to forward G-F: explicit deviation; reason holds, but final verdict must include G-F.
> - Liquidation chronology: incomplete, without stated reason.
> - Runtime normalization: partly deferred, without all required rules.
> 
> All other Q4 items are substantially represented.
> 
> ## Q2 — Numbers or rules
> 
> No literal TBD remains, but the draft is not ambiguity-free. Key ambiguous lines:
> 
> - Line 36: “다음 1m 봉 mark 시가 … 띠 너머 갭이면 그 시가에 체결.”
> - Line 100: “일별 슬롯 수 벡터 … 적격 일 위에 무작위 순열로 배치.”
> - Line 101: “지연된 체결이 23:59:00 이후면.”
> - Line 103: “day_index = UTC 일 번호.”
> - Lines 50-51 versus 90-91: variable execution notional versus “fixed-notional” PnL.
> - Lines 92/108/130: G-F exists, final judgment follows forward, but ACCEPT does not list G-F.
> 
> ## Q3 — Look-ahead/leakage
> 
> - `O_d`: clean; 00:00 mark open is known immediately.
> - `R_{d−1}`: clean; only prior closed UTC-day bars.
> - Median: clean; `d−1` is tested against `d−21…d−2`.
> - Warm-up: temporally clean; no warm-up trading. Completeness policy needs reconciliation.
> - P2: no inherent leakage if execution occurs only at the delayed bar; gate timing and 23:59 equality need freezing.
> - P4: clean; it uses only `O_d`, prior range, and tick information. Seed indexing is incomplete.
> - P1: full-sample `(sl_dist,h)` resampling is legitimate for a retrospective placebo, not a deployable strategy. Its daily placement algorithm remains underdefined.
> - Canonical P1 daily placement does not leak price outcomes merely by checking endpoint availability, but its eligible-date universe must be fixed.
> 
> ## Q4 — Gate/verdict logic
> 
> - Arm A judgment subject: consistent.
> - A/B reported, not gated: consistent.
> - Survival liquidation → REJECT: consistent in intent.
> - G3 on realized `n`: consistent for pass/fail; failure-class label conflicts with MDE §7.
> - P1/P4 unevaluable → DISCARD: consistent.
> - Undefined/conflicting paths:
>   - G-B timing: before versus after G3.
>   - G3 pass followed by G-F failure.
>   - Forward zero trades, missing data, or kill-switch activation.
>   - Whether “ACCEPT after G3” means immediately after G3 or only after forward completion.
> 
> ## Q5 — P1 and P4
> 
> - **P1:** not yet well-posed. The null concept is clear, but date eligibility and slot assignment admit multiple implementations.
> - **P4:** mathematical draw and null interpretation are well-posed. Full determinism still requires the `day_index` formula and percentile convention.
> 
> ## Q6 — Four user decisions
> 
> 1. **N**
>    - N=2: α=0.025, 97.5% CI; easier threshold, but the multiplicity-reset argument is contestable.
>    - N=4: α=0.0125, 98.75% CI and four-attempt SR*; more conservative and aligned with cumulative counting.
> 
> 2. **A/B role**
>    - Report-only B: clean Arm A hypothesis; B cannot rescue an A failure.
>    - B activation candidate: requires B-specific gates, OOS/forward policy, acceptance rule, and likely revised multiplicity.
> 
> 3. **TP**
>    - 2R: preserves parity and caps rare extreme winners.
>    - No TP: lets trail/time exit express continuation, increasing right-tail and duration exposure.
> 
> 4. **OOS split**
>    - ~85 days: preserves longer IS but has high G0-failure risk.
>    - ~175 days from 2026-04-01: improves OOS power but shortens IS and changes the frozen split before anchoring.
> 
> ## Q7 — Additional skeptical objections and registry timing
> 
> Additional objections:
> 
> - A new, different signal family does not normally justify resetting cumulative multiplicity; closure of Trial #1 prevents reuse but does not erase prior attempts.
> - UTC midnight specificity is not challenged by any placebo; P4 randomizes distance, not daily anchor time.
> - Mark-price fills are not directly executable market prices; the 2 bps model must be defended as sufficient execution approximation.
> - P1 randomizes regime/date exposure as well as timing, so its null is not perfectly exposure-conditional.
> - The short OOS is knowingly likely to answer “underpowered” rather than test G3.
> 
> Record **now, before anchoring**:
> 
> - Four user decisions.
> - Findings 1–10: fill, ledgers, liquidation, gate order, final verdict, P1/P2/P4, missing-day policy, power labels.
> - Final document hash, parameter hash, Drive `createdTime`, and Trial #1 OOS closure.
> 
> Record **at code time, before any real-data PnL**:
> 
> - TIME_EXIT engine path and enum.
> - Fixed-sizing-equity/statistical-ledger implementation.
> - Exact exchange-filter snapshot, rounding, bracket, and fee inputs.
> - Seed-child/statistic mapping and percentile method.
> - Canonical subprocess/CLI paths, artifact schema, commit/push evidence.
> - Tests for the four §9 invariants and liquidation/funding chronology.
> 
> VERDICT: FIX-FIRST — blockers: findings 1–6, plus deterministic resolution of 7–10.
> 
> Codex session ID: 01a0d2a0-fcb9-7b60-a5d0-7cc50a5fff11
> Resume in Codex: codex resume 01a0d2a0-fcb9-7b60-a5d0-7cc50a5fff11


## 2026-09-24 — 트라이얼 #2 초안 r2(cb99254) **사후 검토 2차** · Codex(task-mufb3b1r-2vidbx) FIX-FIRST → r3 반영
Codex: r1 지적 12개 중 9 CLOSED · 3 PARTIAL(#3 · #6 · #9) · **진입 기준가 의도적 이탈 수용**("실행 경로 일치가 더 나은 근거") · 새 지적 7개.
### Claude Code 항목별 입장
| 지적 | 입장 · r3 반영 |
|---|---|
| #1 HIGH 완결성이 거래일 자체를 빠뜨림 | ✅ 유효 암-일 = 그날 자체 + 전일 + (B) 20일 창 전부 1,440분 · 무효일은 표본에서 제외 · 알려진 결손 2분의 영향 날짜 명시(08-12·13 A·B · B 08-14~09-02) · 전진 결손은 G-F 실행 결함 |
| #2 HIGH 23:59 갭 청산 대 time_exit | ✅ 고정 순서: 시가가 청산가 너머면 청산(생존 사건) · 아니면 시가 time_exit · 23:59 봉 고저로는 판정 없음 · §11 테스트에 추가 · liquidationFee = 남은 명목 × fee |
| #3 MEDIUM G3 범위 · OOS 0건 라벨 | ✅ G3 = OOS G2 재현만 · OOS PASS = G3 ∧ OOS G0 ∧ OOS 생존 · §7 우선순위 1~4(0건 FAIL → 청산 → 표본 부족 → G3) |
| #4 MEDIUM P1 적격일 | ✅ 적격일 = `V_A`(IS Arm A 유효일) · 적격 분 없으면 난수 없이 추출 실패 |
| #5 MEDIUM 판정기 표본 정의 | ✅ §3-1 판정기 정의 블록(gross_bps · V_A/V_B · 무효일 제외 · A/B 날짜 = V_B, 비수축일 B_day = 0 · Sharpe 식 · 매수보유 달력 · P1/P4 p95 통계 · MDE 식) |
| #6 LOW G-B 문구 과장 | ✅ "상관이 높으면 근사적으로 줄어들 수 있다" · 실현 SR̂_A·SR̂_B·SR* 보고 |
| #7 MEDIUM §12 숨은 결정 | ✅ §12-7(P1 방식) · §12-8(엄격 완결성) · §12-9(진입 기준가) 추가 · OOS 개봉·전진 활성화는 "절차 게이트"로 분류 · 23:59 순서는 기술 규칙으로 고정 명시 |

### Codex 원문(verbatim · task-mufb3b1r-2vidbx)
> ## Numbered findings
> 
> 1. **HIGH — [lines 31, 124](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:31) — “Strict completeness” omits the trading day itself.**  
>    Line 31 requires the prior day, today’s 00:00 bar, and B’s history, while line 124 invalidates 2024-08-13 but not the incomplete 2024-08-12 replay day. Missing intraday bars can hide a cross or exit.  
>    **Fix:** require all 1,440 evaluation-day mark bars for historical arm-day validity; state separately that a forward-day gap is a G-F execution defect.
> 
> 2. **HIGH — [lines 45, 47, 185, 191](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:45) — 23:59 gap liquidation has two outcomes.**  
>    “23:59 봉에서는 다른 판정을 하지 않는다” gives `time_exit`, while “시가가 이미 청산가 너머여도 같은 봉에서 청산” gives liquidation. The test list only orders time exit before SL/TP, not liquidation.  
>    **Fix:** freeze liquidation-versus-time-exit priority at 23:59 and test it. Also replace ambiguous `N × liquidationFee` with `remaining_notional × liquidationFee`.
> 
> 3. **MEDIUM — [lines 95, 97, 144–145](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:95) — G3 and OOS-zero terminology still conflict.**  
>    Line 95 makes G3 include OOS G0 and survival; §§4-1/7 treat all three separately. OOS zero trades is both all-stage `FAIL` and `OOS 표본 부족`.  
>    **Fix:** define G3 as OOS G2 replication only; define `OOS PASS = G3 + OOS G0 + survival`; give zero-trade precedence.
> 
> 4. **MEDIUM — [line 104](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:104) — P1 eligibility is not fully singular.**  
>    “그날이 §1 데이터 완결성을 만족” can mean Arm-A validity, both-arm validity, or only decision inputs; this matters around the known gap. Empty `eligible_h` behavior is also unstated.  
>    **Fix:** say “Arm-A-valid full replay days,” define the exact date set, and make empty `eligible_h` an immediate failed extraction.
> 
> 5. **MEDIUM — [lines 54, 89, 93–94, 107](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:54) — Ledger formulas are improved, but evaluator populations remain ambiguous.**  
>    Flat is now exact. Still unresolved: data-invalid dates as zero versus excluded; B filter-off zero versus B-invalid; the A/B paired-date intersection; the B&H comparison calendar; exact Sharpe formula; and P4 p95’s underlying statistic. `gross_bps` is only recoverable indirectly from registry #19.  
>    **Fix:** add one evaluator-definition block covering date populations, invalid-day treatment, `gross_bps`, Sharpe formula, and “P4 p95 of per-draw mean net_bps.”
> 
> 6. **LOW — [line 91](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:91) — Advisor finding 5 is stated too strongly.**  
>    `B ⊂ A` does not guarantee `SR̂_B ≈ SR̂_A` or variance near zero; contraction-day performance may differ materially.  
>    **Fix:** change “사실상 줄어든다” to “높은 상관이면 근사적으로 줄어들 수 있다” and report realized dependence.
> 
> 7. **MEDIUM — [lines 104, 114, 143, 147, 194–200](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:194) — §12 omits decisions already delegated to defaults.**  
>    The simplified P1 design was adopted although the advisor explicitly recommended user confirmation. OOS opening and forward activation are also user approvals outside §12. Strict completeness and the entry-reference deviation are frozen defaults without explicit confirmation.  
>    **Fix:** add these as confirmations or clearly classify OOS/forward approvals as later procedural gates.
> 
> ## Answers
> 
> ### 1. Round-1 findings 1–12
> 
> | # | Status | r2 closure |
> |---|---|---|
> | 1 | **CLOSED** | [39](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:39): next-open rule and deliberate deviation stated. |
> | 2 | **CLOSED** | [53–54](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:53), [93–94](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:93): execution/statistical ledgers separated. |
> | 3 | **PARTIAL** | [47](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:47): chronology added, but 23:59 gap priority and exact gap accounting remain. |
> | 4 | **CLOSED** | [83–84](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:83), [111–115](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:111): IS-before-OOS staging fixed. |
> | 5 | **CLOSED** | [96](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:96), [143–152](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:143): OOS PASS, G-F failures, final ACCEPT defined. |
> | 6 | **PARTIAL** | [104](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:104): old count/direction collision removed; completeness/date eligibility remains ambiguous. |
> | 7 | **CLOSED** | [40](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:40), [105](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:105): equality drops and delayed decision gate fixed. |
> | 8 | **CLOSED** | [28](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:28), [107](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:107), [189](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:189): epoch, seed, quantile fixed. |
> | 9 | **PARTIAL** | [31](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:31), [124](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:124): strict inputs adopted, but current replay day is omitted. |
> | 10 | **CLOSED** | [95](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:95), [145](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:145), [155–158](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:155): OOS label separated from MDE taxonomy. |
> | 11 | **CLOSED** | [35](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:35): equivalence explicitly stated. |
> | 12 | **CLOSED** | [53, 56](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:53), [189–192](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:189): normalization, seed mapping, snapshot and pre-PnL registry requirements added. |
> 
> ### 2. Entry-reference deviation
> 
> **Acceptable.** A market order submitted after the decision should use the first observable execution-time reference plus the adverse-fill model. `max(U_d,next_open)`/`min(D_d,next_open)` invents an unobserved adverse fill when price retraces inside the band.
> 
> Acceptance is conditional on identical historical/paper/live treatment and the disclosed mark-versus-executable-price approximation in line 74. It is conservative to use worse-of, but execution-path consistency is the better justification here.
> 
> ### 3. Advisor findings 1–9
> 
> 1. Correctly applied.  
> 2. Core simplification is sound, but eligibility remains ambiguous and the requested user confirmation was omitted.  
> 3. Correctly applied.  
> 4. Correctly surfaced in §12.  
> 5. **Misapplied:** “near-vacuous” was converted into an unjustified factual claim.  
> 6. Correctly surfaced in §12.  
> 7. Label added, but OOS zero-trade still has competing labels.  
> 8. Hook added, but liquidation priority at 23:59 was not resolved or tested.  
> 9. Correctly applied.
> 
> ### 4. New ambiguities or contradictions
> 
> The material new issues are findings 1–6 above:
> 
> - Strict inputs versus incomplete current replay day.
> - Time exit versus gap liquidation at 23:59.
> - G3 composite versus separate-stage terminology.
> - OOS zero-trade verdict precedence.
> - P1 valid-day universe.
> - Statistical invalid-day/paired-date/B&H populations.
> - Overstated G-B near-vacuity.
> 
> ### 5. Single implementation?
> 
> **No.** Implementers can still choose differently on:
> 
> - Whether 2024-08-12 itself is valid.
> - Whether 23:59 gap crossing is liquidation or time exit.
> - Whether OOS zero trades is `FAIL` or `OOS 표본 부족`.
> - Whether G3 includes G0/survival.
> - Whether P1 requires A-valid or globally valid days.
> - Whether invalid dates are excluded or zero-filled in CI, Sharpe and A/B.
> - Whether B-invalid dates enter as `B_day=0`.
> - The exact P4 p95 statistic and daily Sharpe convention.
> 
> ### 6. Hidden user decisions
> 
> Yes:
> 
> - Simplified P1 placement versus the prior daily-count/direction-cap design.
> - Confirmation of strict full-day completeness and its treatment of the known gap.
> - Confirmation of the next-open entry deviation, if Q4 was treated as a prior commitment.
> - OOS opening after IS PASS and forward activation after OOS PASS—explicit in staging, but absent from §12.
> - The unresolved 23:59 liquidation/time-exit priority must become either a user decision or a fixed technical rule.
> 
> VERDICT: FIX-FIRST — blockers: full replay-day completeness; 23:59 liquidation/time-exit priority; OOS zero/G3 verdict precedence; deterministic P1 and statistical date populations.
> 
> Codex session ID: 01a0d2a9-431e-7543-ba8c-1342c35e5e2a
> Resume in Codex: codex resume 01a0d2a9-431e-7543-ba8c-1342c35e5e2a


## 2026-09-24 — 트라이얼 #2 초안 r3(ef6b658) **사후 검토 3차** · Codex(task-mufbbgme-g4ccmq) FIX-FIRST → r4 반영
Codex: r1 지적 11 CLOSED · 1 PARTIAL(#3 → §11 순서) · r2 지적 4 CLOSED · 3 PARTIAL · 새 지적 6개(정밀·우선순위).
### Claude Code 항목별 입장
| 지적 | 입장 · r4 반영 |
|---|---|
| #1 HIGH §11 구현 순서가 23:59 갭 청산을 건너뜀 | ✅ §11-1 = §1 순서 그대로(갭 청산 → time_exit → 고저 판정 없음 · `on_bar` 판정 호출 안 함) |
| #2 HIGH REJECT 대 폐기 · "데이터 부재" 중복 | ✅ §4-1: 평가 가능한 게이트 실패 = REJECT · 하네스/설계/필수 데이터셋 불가 = 폐기 · 완결성 제외 암-일 = 표본 제외 · §7 행 문구 일치 |
| #3 HIGH 전진 실패 우선순위 | ✅ 우선순위 1 생존(청산·킬스위치) → 2 실행 결함(폐기) → 3 0건 → 4 부호 |
| #4 MEDIUM 전진 사이징·부호 통계 | ✅ 전진 = 복리(L5) · 부호 = 트레이드당 평균 net_bps · §12-10 사용자 확인 |
| #5 MEDIUM 매수보유 라벨 창·끝점 | ✅ §3-1: 일 종가 정의 · 첫 수익률 · 결손 처리 · 라벨 창 = IS(OOS 보고) · §12-11 |
| #6 LOW P2/P3 0건 | ✅ 값 = 0 bps(flat) · P4 제외 규칙과 다른 이유 명시 |

### Codex 원문(verbatim · task-mufbbgme-g4ccmq)
> ## Numbered findings
> 
> 1. **HIGH — [§11 L195](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:195)** — The implementation rule directly calls `time_exit` before `on_bar`, without first performing §1’s 23:59 opening-price liquidation check. This can turn a survival liquidation into a time exit.  
>    **Fix:** specify `23:59 open-gap liquidation check → if alive, exit_at_bar_open/time_exit → never evaluate high/low`.
> 
> 2. **HIGH — [§4-1 L122](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:122), [§7 L149](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:149)** — “하나라도 실패면 REJECT” conflicts with P1/P4/data/design invalidity being `폐기`. “데이터 부재” also overlaps ordinary invalid arm-days excluded by the strict completeness rule.  
>    **Fix:** say evaluable gate failure → REJECT; harness/design/unavailable-required-dataset → 폐기; predefined incomplete arm-days → exclusion, not 폐기.
> 
> 3. **HIGH — [§7 L158–161](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:158)** — Forward failures have no precedence. A run with both a data gap and liquidation qualifies for both `REJECT(생존)` and `폐기(전진 실행 결함)`.  
>    **Fix:** add explicit forward priority, as already done for OOS.
> 
> 4. **MEDIUM — [§1 L53–54](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:53), [§3 L96](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:96), [§10 L188](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:188)** — Forward sizing and “순엣지” admit two implementations: fixed `E_ref=1,000` versus compounding, and equal-weight mean `net_bps` versus compounded wallet PnL.  
>    **Fix:** state the forward sizing capital and exact G-F sign statistic.
> 
> 5. **MEDIUM — [§3 L93](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:93), [§3-1 L106](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:106), [§7 L162](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:162)** — The final B&H label does not identify which stage/window supplies the comparison. The first close-to-close return and missing-kline treatment are also unstated.  
>    **Fix:** name the comparison window, endpoint convention, first return, and missing-kline outcome.
> 
> 6. **LOW — [§3-1 L107](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:107), [§4 L114–115](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:114)** — P2 or P3 producing zero trades leaves their mean `net_bps` and rejection comparison undefined.  
>    **Fix:** predefine zero-trade variant handling.
> 
> ## Answers
> 
> ### 1. Round-1 findings 1–12
> 
> Current r3 status; “r2” references historical `cb99254` lines.
> 
> | # | Status | Closure |
> |---|---|---|
> | 1 | **CLOSED** | r2 L39: deliberate next-open deviation stated. |
> | 2 | **CLOSED** | r2 L53–54, L93–94: execution/statistical ledgers separated. |
> | 3 | **PARTIAL** | r2 L47 added chronology; r3 L45/L47 fixes 23:59 semantics, but r3 L195 still omits the opening liquidation check. |
> | 4 | **CLOSED** | r2 L83–84, L111–115: IS → OOS → forward order. |
> | 5 | **CLOSED** | r2 L96, L143–152: OOS PASS, G-F failures and ACCEPT added. New precedence issues are findings 3–4 above. |
> | 6 | **CLOSED** | r2 L104 removed the collision; r3 L113 fixes `V_A`, empty eligibility and RNG behavior. |
> | 7 | **CLOSED** | r2 L40, L105: `≥23:59` drop and delayed gate time. |
> | 8 | **CLOSED** | r2 L28, L107, L189: epoch, seed and quantile. |
> | 9 | **CLOSED** | r2 L31/L124 were partial; r3 L31/L133 include the evaluation day and enumerate gap-affected dates. |
> | 10 | **CLOSED** | r2 L95, L145, L155–158; r3 L153–168 adds explicit OOS precedence. |
> | 11 | **CLOSED** | r2 L35: crossing-predicate equivalence. |
> | 12 | **CLOSED** | r2 L53/L56/L189–192: snapshot, normalization, seed mapping and pre-PnL registry row. |
> 
> ### 2. Entry-reference deviation
> 
> **Acceptable.** The first post-decision reference plus adverse-fill adjustment better matches the intended execution path; worse-of-band invents an unavailable fill after a retrace.
> 
> The justification should remain described as a model approximation, not an “actual fill”: next-minute mark open is not necessarily the first executable quote. §2’s disclosure and §12-9 confirmation cover this caveat.
> 
> ### 3. Advisor findings 1–9
> 
> 1. Correctly applied.  
> 2. Correctly applied in r3; P1 is now deterministic and surfaced in §12-7.  
> 3. Correctly applied.  
> 4. Correctly surfaced in §12-3.  
> 5. Corrected properly in r3 L91; the earlier overclaim is gone.  
> 6. Correctly surfaced in §12-5.  
> 7. Correctly applied with explicit OOS precedence.  
> 8. **Partial/misapplied:** the strategy hook exists, but §11 L195 can bypass the required 23:59 liquidation-first rule.  
> 9. Correctly applied.
> 
> ### 4. New ambiguities or contradictions
> 
> - §4-1 `하나라도 실패면 REJECT` versus §7 `폐기`.
> - Ordinary completeness exclusions versus undefined §7 “데이터 부재”.
> - §11 time-exit hook versus §1 liquidation-first ordering.
> - Forward simultaneous-failure precedence.
> - Forward compounding and exact net-edge statistic.
> - Final B&H comparison window/endpoints.
> - P2/P3 zero-trade handling.
> 
> P1 eligibility itself is now singular at L113. The known two-minute gap treatment is also explicit at L31/L133. Flat, daily, A/B and P1/P4 ledger populations are otherwise adequately fixed at L54 and L101–108.
> 
> ### 5. Single implementation?
> 
> **No.** Findings 1–6 still permit different results or verdict strings, particularly at 23:59, simultaneous forward failures, forward net-edge calculation, and the B&H label.
> 
> ### 6. Hidden user decisions
> 
> r3 now lists **nine**, not six. One material choice remains hidden: forward fixed-capital versus compounded sizing, together with which ledger determines G-F’s positive sign.
> 
> The B&H label’s comparison stage may also merit confirmation. Verdict precedence and zero-variant handling are technical rules, not user preference decisions.
> 
> ### 7. Round-2 findings 1–7
> 
> | # | Status |
> |---|---|
> | 1 | **CLOSED** — L31/L133. |
> | 2 | **PARTIAL** — semantic rule and test are fixed, but L195 still permits time exit before the gap-liquidation check. |
> | 3 | **CLOSED** — L95/L153–157. |
> | 4 | **CLOSED** — L113. |
> | 5 | **PARTIAL** — principal ledger populations are fixed; B&H endpoints/stage remain ambiguous. |
> | 6 | **CLOSED** — L91. |
> | 7 | **PARTIAL** — listed defaults are surfaced, but forward compounding/ledger remains hidden. |
> 
> VERDICT: FIX-FIRST — blockers: 23:59 implementation ordering; IS REJECT-versus-폐기 distinction; forward failure precedence; forward sizing/net-edge definition.
> 
> Codex session ID: 01a0d2af-114a-7952-bc07-acdcce0bf349
> Resume in Codex: codex resume 01a0d2af-114a-7952-bc07-acdcce0bf349


## 2026-09-24 — 트라이얼 #2 초안 r4(bd912e6) **사후 검토 4차** · Codex(task-mufbhifz-yvjbrb) FIX-FIRST → r5 반영
Codex: r1 11 CLOSED · 1 PARTIAL(#5 ← L97) · r3 5 CLOSED · 1 PARTIAL · advisor 1~9 "no finding materially misapplied" · 새 지적 5개.
| 지적 | 입장 · r5 반영 |
|---|---|
| #1 HIGH "모든 단계 즉시 FAIL" 대 전진 우선순위 | ✅ §3 행을 "트레이드 0건 · 겹칠 때는 §7 단계별 우선순위"로 |
| #2 HIGH G-B의 n 대상 · SR̂_B 미정의 | ✅ n_A ≥ 30 · SR̂_B 미정의면 SR* := 0 + 보고 · §12-12 확인 |
| #3 MEDIUM 전진 부분일 | ✅ UTC 00:00 정각 활성화 · 완전한 30일 · §12-13 확인 |
| #4 MEDIUM §12 R 기하가 체결가 의존 | ✅ "명목 거리"로 · 실제 R = |체결가 − SL| 명시 |
| #5 LOW 매수보유 창 수익률 식 · §7 부등호 | ✅ 창 수익률 = 마지막 종가/첫 종가 − 1 · §7에 IS 창 엄격 `<` |

### Codex 원문(verbatim · task-mufbhifz-yvjbrb)
> ## Numbered findings
> 
> 1. **HIGH — [L97, L159–162](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:97)** — “모든 단계 즉시 FAIL” makes zero trades first, but forward precedence puts survival and execution defects before zero trades.  
>    **Fix:** remove “즉시/모든 단계” or explicitly defer to §7’s stage-specific precedence.
> 
> 2. **HIGH — [L91](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:91)** — G-B’s `n ≥ 30` does not say A, B, or both; `SR̂_B` can be undefined with too few/zero-variance B trades. That leaves an IS gate without a verdict.  
>    **Fix:** define the sample requirement and the verdict for undefined `SR̂_B`/`SR*`.
> 
> 3. **MEDIUM — [L138](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:138)** — Forward starts at an arbitrary activation time, but the strategy is UTC-day based. A partial first day can be skipped, replayed, or entered after an earlier cross. The final partial day is likewise unclear.  
>    **Fix:** activate at 00:00 UTC, or define first/last partial-day treatment and cross-consumption bootstrap.
> 
> 4. **MEDIUM — [L42, L208](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:42)** — §12 says `SL=O_d` means `R=0.5·R_prev`, but actual `R=|fill−O_d|`; retraces and gaps make those unequal. The opposite-band alternative is similarly not exactly `1.0·R_prev`.  
>    **Fix:** call these nominal band distances and state the actual fill-dependent geometry.
> 
> 5. **LOW — [L93, L106–107, L163](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:93)** — B&H daily returns and label window are fixed, but “창 수익률” lacks an exact aggregate formula; L163’s “못 이기면” is less exact than L93’s strict `<`.  
>    **Fix:** define `last_close / first_close − 1` and copy the strict IS-Sharpe predicate into §7.
> 
> ## Answers
> 
> ### 1. Round-1 findings 1–12
> 
> 1. **CLOSED** — r2 `cb99254` L39; retained at [L39](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:39).
> 2. **CLOSED** — r2 L53–54, L93–94; retained at [L53–54](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:53), [L93–94](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:93).
> 3. **CLOSED** — r2 L47 was partial; r3 fixed semantics, r4 fixed implementation at [L45–47](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:45), [L196](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:196).
> 4. **CLOSED** — r2 L83–84, L111–115; current [L83–84](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:83), [L121–125](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:121).
> 5. **PARTIAL** — r2 L96, L143–152 supplied verdicts, but current L97 conflicts with forward precedence.
> 6. **CLOSED** — r2 L104 removed the original collision; r3 completed eligibility; current [L114](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:114).
> 7. **CLOSED** — r2 L40/L105; current [L40](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:40), [L115](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:115).
> 8. **CLOSED** — r2 L28/L107/L189; current [L28](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:28), [L117](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:117), [L200](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:200).
> 9. **CLOSED** — r2 L31/L124 were partial; r3/current [L31](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:31), [L134](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:134) complete it.
> 10. **CLOSED** — r2 L95/L145/L155–158; current [L95](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:95), [L154–158](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:154).
> 11. **CLOSED** — r2 L35; current [L35](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:35).
> 12. **CLOSED** — r2 L53/L56/L189–192; current [L53–56](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:53), [L195–203](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:195).
> 
> ### 2. Entry-reference deviation
> 
> **Acceptable.** Next-minute mark open plus adverse-fill adjustment matches the declared historical/paper path better than inventing a worse-of-band fill after retracement.
> 
> It remains a model approximation—not necessarily the first executable quote. §2 discloses that limitation, and §12-9 correctly requires user confirmation.
> 
> ### 3. Advisor findings 1–9
> 
> 1. Correctly applied.
> 2. Correctly applied; P1 is deterministic and §12-7 surfaces the choice.
> 3. Correctly applied.
> 4. Correctly surfaced in §12-3, subject to finding 4’s geometry correction.
> 5. Corrected properly; the overstatement is gone.
> 6. Correctly surfaced in §12-5.
> 7. Correctly applied with explicit OOS precedence.
> 8. Correctly applied in r4 at L196/L202.
> 9. Correctly applied.
> 
> No advisor finding is materially misapplied now. The remaining precedence problem arose from retaining generic L97 after adding forward-specific ordering.
> 
> ### 4. Ambiguities/contradictions
> 
> - §3/§4-1/§7 staging is aligned except L97 versus forward priority.
> - P1 eligibility is singular: same UTC day, exit by 23:58, and `V_A`.
> - Strict completeness and the known two-minute gap are consistent and explicitly enumerated.
> - Flat, daily statistical PnL, A/B dates, and P1/P4 statistics are fixed.
> - G-B’s `n` and undefined-B behavior remain open.
> - B&H label window is fixed; total window-return formula remains unstated.
> - 23:59 order is now unambiguous: gap liquidation, otherwise time exit, no high/low evaluation.
> 
> ### 5. Single implementation?
> 
> **No.** Different implementations remain possible for:
> 
> - Forward zero trades combined with a safety/data failure.
> - G-B’s sample requirement and undefined `SR̂_B`.
> - Forward partial first/last UTC days.
> - B&H aggregate window return.
> - §12’s fill-dependent R geometry description.
> 
> ### 6. Hidden user decisions
> 
> The current r4 lists **11**, not six, plus two later procedural approvals.
> 
> Two further design decisions should be surfaced:
> 
> - G-B behavior when B has insufficient or zero-variance trades.
> - Forward activation alignment and partial-day treatment.
> 
> The B&H aggregate formula and verdict-precedence correction are technical rules, not user preferences.
> 
> ### 7. Round-3 findings 1–6
> 
> 1. **CLOSED** — L196/L202.
> 2. **CLOSED** — L123/L150.
> 3. **PARTIAL** — L159–162 adds precedence, but L97 contradicts it.
> 4. **CLOSED** — L96/L189/L215.
> 5. **CLOSED** for the requested label window, endpoints, first return, and missing-day handling; finding 5 above is a smaller reporting-formula residue.
> 6. **CLOSED** — L108.
> 
> VERDICT: FIX-FIRST — blockers: zero-trade versus forward-failure precedence; undefined G-B sample/SR behavior; forward partial-day boundaries; correct §12’s fill-dependent R geometry.
> 
> Codex session ID: 01a0d2b3-602a-7e83-bf08-945da744b5fa
> Resume in Codex: codex resume 01a0d2b3-602a-7e83-bf08-945da744b5fa


## 2026-09-24 — 트라이얼 #2 초안 r5(b1a7b4e) **사후 검토 5차** · Codex(task-mufbo01w-ulm6vx) FIX-FIRST → r6 반영
Codex: r1 12개 전부 CLOSED · 새 지적 5개.
| 지적 | 입장 · r6 반영 |
|---|---|
| #1 HIGH CI 꼬리 미지정 | ✅ §3-1 "CI 정의": 가운데 97.5% 퍼센타일 부트스트랩 — 하한 1.25 · 상한 98.75 백분위(#19 ①과 같음) · 모든 게이트·§7-2 공통 |
| #2 HIGH IS 동시 실패 우선순위 | ✅ §7 IS 우선순위 0~5(데이터·설계 폐기 → 0건 → 생존 → 원판 게이트 → 플라시보 하네스 폐기 → 플라시보 기각) · 생존·원판 실패는 평가 가능한 사실이라 하네스 폐기보다 먼저 |
| #3 MEDIUM OOS 데이터 불가 | ✅ OOS 우선순위 0 = 폐기(OOS 데이터) · 확정 펀딩율 없는 날 = 데이터 무효일(§1 완결성에도 추가) |
| #4 MEDIUM 퇴화 통계 | ✅ §3-1: ρ̂ 미정의 → 0 · SR̂_A/PSR 미정의 → G-B 실패 · CI 미정의 → 게이트 실패 · MDE 미정의 → 검정력 부족 · Sharpe 미정의 → 라벨 없음 · 미정의를 통과로 읽지 않는다 |
| #5 LOW G-B 설명 부정확 | ✅ "겹침 때문에 실현 SR̂가 비슷할 가능성 · SR*는 실현 값으로만" |

### Codex 원문(verbatim · task-mufbo01w-ulm6vx)
> ## Numbered findings
> 
> 1. **HIGH — [L89–95](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:89), [L109](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:109)** — CI tail is not uniquely specified.  
>    “97.5% CI 하한” can mean percentile `q=.025` or central-97.5% `q=.0125`; MDE’s `z₀.₉₇₅` suggests the former. This changes G1/G2/G3/A-B verdicts.  
>    **Fix:** state percentile-bootstrap bounds explicitly, including upper bound used by §7-2.
> 
> 2. **HIGH — [L84](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:84), [L97](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:97), [L123](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:123), [L149–152](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:149)** — IS simultaneous-failure precedence remains open.  
>    Zero trades is explicitly first, but P1/P4 harness failure (`폐기`) plus liquidation (`REJECT(생존)`) has two outcomes. §3 evaluates survival before placebo; §7 lists discard first without declaring priority.  
>    **Fix:** number IS priorities as done for OOS/forward.
> 
> 3. **MEDIUM — [L123–125](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:123), [L150](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:150), [L154–158](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:154)** — OOS required-data unavailability has no terminal rule.  
>    §4-1 says unavailable required datasets cause discard, but §7 defines that only for IS. All OOS days excluded for missing data could instead become “OOS 트레이드 0” REJECT.  
>    **Fix:** add OOS data-unavailability precedence and distinguish individual invalid days from an unusable window, including missing funding history.
> 
> 4. **MEDIUM — [L88](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:88), [L91](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:91), [L106](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:106)** — Degenerate statistics remain undefined.  
>    r5 handles undefined `SR̂_B`, but not zero-variance A: `ρ̂`, `SR̂_A`, PSR and the final daily-Sharpe comparison can be undefined.  
>    **Fix:** freeze zero-variance/undefined behavior for each statistic and resulting verdict/label.
> 
> 5. **LOW — [L91](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:91)** — Advisor finding 5’s explanation is still imprecise.  
>    High A/B estimator correlation alone does not imply small cross-sectional `V[SR̂]`; similar realized Sharpe values do.  
>    **Fix:** say overlap makes similar realized SRs plausible, while reported realized SRs determine `SR*`.
> 
> ## Answers
> 
> ### 1. Round-1 findings 1–12
> 
> 1. **CLOSED** — r2 L39: deliberate next-open deviation.
> 2. **CLOSED** — r2 L53–54, L93–94: execution/statistical ledgers.
> 3. **CLOSED** — r2 L47 was partial; current L45–47 and L196 complete 23:59 chronology.
> 4. **CLOSED** — r2 L83–84, L111–115: IS → OOS → forward.
> 5. **CLOSED** — r2 L96, L143–152 defined verdicts; r5 L97, L159–163 removed the last forward conflict.
> 6. **CLOSED** — r2 L104 removed the placement collision; current L114 fixes eligibility.
> 7. **CLOSED** — r2 L40, L105: equality boundary and delayed gate time.
> 8. **CLOSED** — r2 L28, L107, L189: epoch, seed, quantile method.
> 9. **CLOSED** — r2 L31/L124 were partial; current L31/L134 include the replay day and exact gap dates.
> 10. **CLOSED** — r2 L95, L145, L155–158: OOS-zero/G0/MDE labels.
> 11. **CLOSED** — r2 L35: crossing-predicate equivalence.
> 12. **CLOSED** — r2 L53/L56/L189–192: snapshot, normalization, seeds and pre-PnL registry row.
> 
> ### 2. Entry-reference deviation
> 
> **Acceptable.** Next-bar mark open plus adverse-fill adjustment matches the declared historical/paper execution path better than inventing a band-price fill after retracement.
> 
> It remains a model approximation, not necessarily the first executable quote. §2 discloses that limitation and §12-9 requires confirmation.
> 
> ### 3. Advisor findings 1–9
> 
> No finding is materially misapplied. Findings 1–4 and 6–9 are correctly represented. Finding 5 has the LOW explanatory imprecision in finding 5 above, but the implemented rule and realized-value reporting are unambiguous.
> 
> ### 4. Requested ambiguity checks
> 
> - **§3/§4-1/§7:** forward precedence is fixed; IS collision and OOS unavailable-data handling remain open.
> - **P1:** singular at L114—same UTC day, exit no later than 23:58, day in `V_A`.
> - **Completeness/gap:** consistent at L31/L134; the known two-minute gap invalidates the enumerated A/B days.
> - **Ledgers:** flat, daily, A/B and B&H populations/formulas are fixed; CI tails and degenerate statistics remain open.
> - **23:59:** unambiguous at L45–47/L196—opening-price liquidation first, otherwise time exit, never high/low evaluation.
> 
> ### 5. Single implementation?
> 
> **No.** Findings 1–4 can still produce different numeric thresholds, labels, or terminal verdicts.
> 
> ### 6. Hidden user decisions
> 
> Current §12 lists **13**, not six.
> 
> Additional hidden statistical choice: one-sided 97.5% lower bound versus central 97.5% CI. Missing-funding/OOS-data treatment also needs confirmation or an explicit technical rule. IS precedence and zero-variance handling are technical rules, not preference decisions.
> 
> ### 7. Round-4 findings 1–5
> 
> 1. **CLOSED** — L97 defers zero trades to stage-specific precedence.
> 2. **CLOSED as scoped** — L91/L217 define `n_A` and undefined `SR̂_B`; undefined A is the new finding 4.
> 3. **CLOSED** — L138/L218 define 00:00 activation and 30 complete days.
> 4. **CLOSED** — L42/L208 distinguish nominal and fill-dependent R.
> 5. **CLOSED** — L106 gives the window-return formula; L163 gives the strict comparison.
> 
> VERDICT: FIX-FIRST — blockers: exact CI bounds, IS simultaneous-failure precedence, OOS unavailable-data verdict, and degenerate A-statistic rules.
> 
> Codex session ID: 01a0d2b7-febe-7f83-a1d2-ada9f46791ee
> Resume in Codex: codex resume 01a0d2b7-febe-7f83-a1d2-ada9f46791ee


## 2026-09-24 — 트라이얼 #2 초안 r6(de3f2cf) **사후 검토 6차** · Codex(task-mufbuwiv-40zoir) **MERGE** · 비차단 3건 반영
프롬프트 변경 공개: 6차부터 "차단(BLOCKER) = 충실한 두 구현이 다른 판정을 낼 수 있거나 결과를 새게/치우치게 하는 것만 · 다듬기는 NON-BLOCKING으로 따로" 기준을 명시했다(무한 반복 방지 · 모호성 기준은 낮추지 않음).
| 지적(비차단) | 반영 |
|---|---|
| #1 펀딩 완결성이 §12-8에 없음 | ✅ §12-8에 추가 |
| #2 P1의 N_A 미정의 | ✅ `rng.integers(0, n)`(N_A := n) |
| #3 MDE(z₀.₉₇₅)의 단측 해석 미명시 | ✅ 단측 α 0.025 · 검정력 0.80(트라이얼 #1 §7과 같음) · CI와 해석 차이 공시 |
사후 검토 결론: advisor(r1) MERGE-after-fixes → 반영 · Codex r1~r5 FIX-FIRST → r6 **MERGE**. 초안은 사용자 §12 결정 대기(앵커·코드 없음).

### Codex 원문(verbatim · task-mufbuwiv-40zoir)
> No blockers found. Three non-blocking clarifications remain.
> 
> ## Numbered findings
> 
> 1. **MEDIUM — NON-BLOCKING — [L31, L218](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:31)** — r6 requires both 08:00 and 16:00 funding records for every valid day, but §12-8 describes only mark-bar completeness. This is explicit for implementers but partly hidden from user confirmation.  
>    **Fix:** add funding completeness to §12-8.
> 
> 2. **LOW — NON-BLOCKING — [L116](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:116)** — P1 defines original count as `n` but samples with undefined `N_A`. Context makes `N_A = n`, so no realistic verdict split.  
>    **Fix:** replace `N_A` with `n`, or define `N_A := n`.
> 
> 3. **LOW — NON-BLOCKING — [L102, L110, L171](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:110)** — Gate CI is central 97.5%, while MDE uses `z₀.₉₇₅`. The formula is executable, but its one-sided interpretation is unstated.  
>    **Fix:** say “one-sided α=0.025 MDE” or change the quantile if MDE should mirror the central CI.
> 
> ## Answers
> 
> ### 1. Round-1 findings 1–12
> 
> 1. **CLOSED** — r2 L39: explicit next-open rule and deliberate deviation.
> 2. **CLOSED** — r2 L53–54, L93–94: execution and statistical ledgers separated.
> 3. **CLOSED** — r2 L47 was partial; current [L45–47, L201](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:45) completes liquidation/time-exit chronology.
> 4. **CLOSED** — r2 L83–84, L111–115: IS → OOS → forward staging.
> 5. **CLOSED** — r2 L96, L143–152 introduced verdicts; current L97 and L164–168 remove the later precedence conflict.
> 6. **CLOSED** — r2 L104 removed the placement collision; current [L116](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:116) fixes eligibility and failure behavior.
> 7. **CLOSED** — r2 L40, L105: `fill_ts ≥ 23:59` and delayed gate timing.
> 8. **CLOSED** — r2 L28, L107, L189: epoch, P4 seed and percentile convention.
> 9. **CLOSED** — r2 L31/L124 were partial; current [L31, L136](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:31) covers the replay day and exact gap effects.
> 10. **CLOSED** — r2 L95, L145, L155–158: OOS-zero, G0 and MDE labels.
> 11. **CLOSED** — r2 L35: prior-inside crossing equivalence.
> 12. **CLOSED** — r2 L53/L56/L189–192: normalization, snapshots, seeds and pre-PnL registry requirements.
> 
> ### 2. Entry-reference deviation
> 
> **Acceptable.** The next-bar mark open plus adverse-fill adjustment matches the declared historical/paper/live execution path better than inventing a band-price fill after a retracement.
> 
> It remains an execution approximation, not necessarily the first executable quote. §2 discloses that limitation, and §12-9 requires user confirmation.
> 
> ### 3. Advisor findings 1–9
> 
> All are correctly applied.
> 
> - #2 P1 is deterministic and surfaced in §12-7.
> - #4 SL geometry now distinguishes nominal band distance from fill-dependent actual R.
> - #5 now states only that similar realized Sharpes are plausible; it no longer asserts they must be similar.
> - #8 has identical 23:59 semantics in §1 and §11.
> 
> No advisor finding creates a new material ambiguity.
> 
> ### 4. Current ambiguities or contradictions
> 
> - **§3/§4-1/§7:** aligned. §3 gives evaluation order; §7 gives terminal-result precedence.
> - **P1:** singular: “same UTC day,” endpoint no later than 23:58, and day in `V_A`.
> - **Completeness/gap:** consistent. L31’s strict rule produces exactly the invalid dates listed at L136.
> - **Ledgers:** flat, trade, daily, A/B and B&H populations/formulas are fixed at L54 and L102–111.
> - **23:59:** unambiguous—opening-price liquidation first, otherwise time exit, never high/low evaluation.
> - Remaining issues are only the three non-blocking clarifications above.
> 
> ### 5. Single implementation
> 
> Yes for every verdict-affecting field. Two faithful implementations should produce the same trades, statistics and terminal verdicts.
> 
> The `N_A` alias and MDE-sidedness label merit cleanup but do not override their executable surrounding rules.
> 
> ### 6. Hidden user decisions
> 
> Current §12 lists **13**, not six, plus two later procedural approvals.
> 
> One newly added default should be surfaced more clearly: strict completeness now includes both daily funding records, but §12-8 mentions only mark bars. No other material user decision remains hidden.
> 
> If N=4 is chosen, the main CI and G-B formulas must be updated before anchoring; that is implementation of §12-1, not another decision.
> 
> ### 7. Round-5 findings 1–5
> 
> 1. **CLOSED** — exact central CI bounds at [L102](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:102).
> 2. **CLOSED** — numbered IS precedence at [L151–156](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:151).
> 3. **CLOSED** — OOS unavailable-data handling at [L31, L158](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:158).
> 4. **CLOSED** — degenerate-statistic rules at [L111](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:111).
> 5. **CLOSED** — corrected G-B explanation at [L91](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:91).
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0d2bc-e88a-7841-9456-7e841faf184f
> Resume in Codex: codex resume 01a0d2bc-e88a-7841-9456-7e841faf184f


## 2026-09-24 — 트라이얼 #2 사전등록 **사용자 §12 결정 → r7** · advisor 사후 MERGE(조건부) · Codex 좁은 확인(task-mufcn7s2-2a8viu) **MERGE**
- 사용자 결정(레지스트리 #32 · 정정 #33): **N = 4(누적)** · **sl_dist 천장 5.00%** · 나머지 12건 유지 · 생존 게이트·23:59 순서 재확인.
- r7 변경 요약: §0 N 문단 재작성 · α 0.0125 · CI 가운데 98.75%(0.625/99.375) 전 게이트 · G-B SR* = 네 실현 SR̂(트라이얼 #1 두 값 고정 · report.json SHA) · MDE z₀.₉₈₇₅ = 2.2414 · §7-2 α 0.0125 · sl_dist 띠 [0.30%, 5.00%] · §1-1 3/4/5% 행(20x/15x/12x) · §9 비용 배수 2~36배 · §12를 결정 기록으로 · 🔶 → 결정 표기.
### Claude Code 항목별 입장
| 지적 | 출처 | 입장 · 반영 |
|---|---|---|
| §12-12(SR̂_B 미정의 → SR* := 0)가 N = 4에서 뜻이 바뀜 — 세 값이 남아 SR*를 계산할 수 있고 > 0 · SR* := 0은 이제 덜 보수적 | advisor #1 · Codex #2 | ✅ 동의 — **고치지 않고 사용자 결정으로 다시 올림**(보고서) · 선택지 (a) SR* := 0 유지 · (b) SR* = expected_max_sr(정의된 세 값, n_trials = 4) — advisor는 (b) 권고 |
| sed로 "✅ 결정 대안"이 "채택된 대안"처럼 읽힘 | advisor #2 | ✅ "대안 …는 채택 안 함 — §12 기록" 등으로 |
| 트라이얼 #2 앵커 상수(N_TRIALS 4 · ALPHA 0.0125 · LEVEL 0.9875 · #1 SR̂)를 §11에 | advisor #3 | ✅ §11-5 "다중검정 상수" + #1 판정기 상수 import 금지 · report.json 대조 테스트 |
| §1-1은 롱 · 정규화 전 값 | Codex #1 | ✅ 표 머리에 "롱 · 수량 내림 전 예시 · 숏 거리 · 실제 명목 · 규칙은 §1이 정본" |
| 유지 개수 11 → 12 · 4.00% 행 누락 표기 | Codex #3 | ✅ 문서 수정 + 레지스트리 정정 #33 |

### advisor 원문(verbatim)
> You're at the r7 after-pass; Codex narrow check is running. This is the advisor half. I verified the propagation independently — it's complete — and found one place where the N=4 change silently altered the meaning of a rule the user "kept."
> 
> **Propagation check (passes)**
> - α 0.0125 in §0, §3-1 MDE, §7-2. CI 98.75% / 0.625 / 99.375 in §0, G1, G2, G3, A/B, §3-1. z₀.₉₈₇₅ = 2.2414 correct (`inv_cdf(0.9875)`). SR* over four with trial #1 values pinned and the report.json SHA cited. The only remaining "N = 2" is the user's quoted sentence at L214 — legitimate.
> - §1-1: I checked the 5.00% row by hand — at 13x, liq_dist ≈ 1/13 − 0.05% − MMR ≈ 7.2% < 7.5% (5%×1.5), so 12x is the highest passing L. Rows consistent with the #5 gate. §9 ratio 2~36× correct (5.00/0.14 = 35.7).
> 
> **Findings**
> 
> 1. **MEDIUM — §12-12 was kept under a premise N=4 removed.** The rule "SR̂_B undefined → SR* := 0" was written for N=2, where losing B leaves one value and V[SR̂] is uncomputable. With N=4, three realized SR̂ remain (#1A, #1B, #2A) and `expected_max_sr([…3 values…], 4)` is well-defined and **> 0** (trial #1's ≈ −0.24 vs any different SR̂_A gives positive variance). So SR* := 0 is now the *less* conservative branch, and its stated rationale ("두 번째 시도의 분산을 추정할 수 없다") is false — which is why you deleted that parenthetical. The rule as written is unambiguous (Codex-wise not a blocker), but it's a substantive change in gate stringency the user didn't see when they ticked "kept". Re-surface it as one line before anchoring: **(a) keep SR* := 0**, or **(b) SR* = expected_max_sr over the 3 defined values with n_trials = 4** (more conservative, uses the data that exists). Recommend (b); user decides. Codex Q2 covers this — cross-check when it lands.
> 
> 2. **LOW — sed artifact.** `🔶 대안 X는 §12-3` became `✅ 결정 대안 X는 §12-3` on the SL, TP and median rows (L40, L42, L49). Reads as "decided alternative." One-word fix: `대안 …는 §12-3에 기록(채택 안 함)`.
> 
> 3. **LOW — §11 code-time item missing.** Trial #2's anchor module needs `N_TRIALS = 4`, `ALPHA = 0.0125`, `LEVEL = 0.9875`, and the two pinned trial #1 SR̂ as constants, with a test asserting they match `report.json` (SHA `11c88452…`). Trial #1's `anchor.N_TRIALS = 2` / `evaluate.LEVEL = 0.975` must not be imported. Add to §11-5 now so it lands in the pre-P&L registry row.
> 
> **Process before you report**
> - Standing rule: log the user decision + r7 diff summary + this pass + Codex's narrow check verbatim in ops_log with per-point positions. Not yet done.
> - Report SHA `0683284571896064…` (post-sed, = c9b15cb). Note 11 commits `98c8199..c9b15cb` are unpushed — ask.
> 
> **Advisor after-pass: MERGE, conditional on #1 being surfaced to the user as a decision** (not fixed by you). #2–3 are wording/bookkeeping; apply and re-commit as r7 wording-only, no new round needed.

### Codex 원문(verbatim · task-mufcn7s2-2a8viu)
> 1. **NON-BLOCKING** — §1-1 is unlabeled long-side, pre-normalization arithmetic.  
>    New 3/4/5% rows correctly select L = 20/15/12, but displayed distances are LONG values.  
>    Snapshot SHORT distances are 4.532%/6.192%/7.852%; leverage choices remain identical.  
>    Quantity flooring makes actual notionals 302.8/227.1/151.4, not 333.3/250.0/200.0.  
>    The normative sizing rule remains unambiguous.
> 
> 2. **NON-BLOCKING** — Undefined B explicitly overrides four-SR `expected_max_sr` with SR* := 0.  
>    This ignores the available #1A, #1B, and #2A values, so it is no longer an expected maximum.  
>    It is nevertheless a clear, user-decided exception.
> 
> 3. **NON-BLOCKING** — §12 recordkeeping counts are inaccurate.  
>    “11 kept” lists §12-2 through §12-13: twelve prior decisions.  
>    It also says “3.00%·5.00% 행 추가,” omitting the added 4.00% row.
> 
> Q1. Yes. N = 4 is propagated to α = 0.0125, every CI, 0.625/99.375 percentiles, four-SR G-B with pinned #1 values, MDE `z₀.₉₈₇₅ = 2.2414`, §3-1, and §7-2. No stale N = 2, 97.5%, 1.25%, or 98.75%-upper-bound text remains.
> 
> Q2. The rule is computationally complete:
> 
> - A and B defined: calculate SR* from all four SR̂.
> - B undefined: explicit SR* := 0.
> - A undefined: §3-1 explicitly makes G-B fail.
> 
> Thus SR* cannot remain undefined or verdict-ambiguous. The methodological caveat is finding 2.
> 
> Q3. The new leverage choices are gate-consistent for both directions. At each row, L passes and L+1 fails. The displayed ancillary amounts are idealized before quantity flooring; see finding 1.
> 
> Q4. The operative band is consistently 0.30–5.00%. §9’s approximately 2–36× cost ratio is correct, §8 covers the band generically, and §7-3 separately reports below-floor and above-cap skips. Only §12’s omitted 4.00% mention remains.
> 
> Q5. No substantive rule was dropped. All former §12-2 through §12-13 choices remain represented in the body and decision record. Only the retained-item count is wrong.
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0d2d1-1095-7220-817a-c8d81d3ef7da
> Resume in Codex: codex resume 01a0d2d1-1095-7220-817a-c8d81d3ef7da


## 2026-09-24 — 트라이얼 #2 r8(§12-12 SR* 규칙) **Codex 좁은 확인**(task-mufdq43y-n8y7fe) **MERGE**
- 사용자 결정(레지스트리 #34): SR*는 항상 정의된 SR̂ 집합으로 expected_max_sr(n_trials = 4) · 정의된 값 < 2개면 G-B 실패.
- Codex: 모든 조합에서 단일값 · §3-1과 모순 없음 · `expected_max_sr`는 ddof = 1(문서와 일치) · "2개 미만" 가드는 트라이얼 #1 두 값이 고정이라 도달 불가지만 무해 · 비차단 1건("네 실현 SR̂" 요약 문구).
- Claude Code: ✅ 비차단 문구 4곳을 "정의된 SR̂(최대 네 개)"로 고침(규칙 변경 없음) → 이것이 앵커할 최종 r8.

### Codex 원문(verbatim · task-mufdq43y-n8y7fe)
> 1. **NON-BLOCKING** — Stale summary wording remains in §0, the G-B disclosure, and §12-1 (“네 실현 SR̂” / “네 값”). It should ideally say “up to four defined SR̂ values.” The operative G-B rule and §12-12 are nevertheless explicit, so implementations should not diverge.
> 
> Q1. Yes. With the two pinned trial-#1 constants, the defined subset always contains at least two values:
> 
> - A/B defined: use four values.
> - A defined, B undefined: use three values.
> - A undefined, B defined: compute from three values, but G-B fails under §3-1.
> - A/B undefined: compute from the two pinned values, but G-B fails because A is undefined.
> 
> There is no contradiction with §3-1 or the G-B conjunction. The “fewer than two” guard is unreachable while both pinned constants remain defined, but is harmless.
> 
> Q2. Yes. `expected_max_sr` uses `np.var(..., ddof=1)`, matching the text’s sample variance requirement. The defined values are the variance input; `n_trials` remains 4.
> 
> Q3. No operative text still assigns `SR* := 0`. That phrase remains only in explicitly superseded historical records: §12-12 describes it as discarded, registry #32 records the old rule, and #34 explicitly replaces it. Counts are consistent after the append-only correction: #33 corrects #32’s original 11 to 12 retained items; #34 changes one of those 12, leaving 11 retained and one changed, matching the r8 header and §12 record.
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0d2ec-c1c1-7222-bb18-90e2b75c4baf
> Resume in Codex: codex resume 01a0d2ec-c1c1-7222-bb18-90e2b75c4baf

## 2026-09-24 — 트라이얼 #2 **앵커**(레지스트리 #35)
- 업로드: `rclone copyto` → Drive `gdrive:BTC_Futures_E2E/trials/trial_02_preregistration.md`(바이트 그대로 · 변환 없음) · 2026-09-24 10:22:55 UTC(로컬 로그).
- **createdTime `2026-09-24T10:22:54.426Z`** — Drive 커넥터 `get_file_metadata`(id `1BYBrBNe1pDe00o979MujYPvMIq5ndlFe` · parent `14NZhku5Odij7BX_6nk2uPkqNiESTb8-2`) = rclone `lsjson --metadata` btime.
- modifiedTime `2026-09-24T10:20:46.466Z` = rclone이 옮긴 로컬 mtime(업로드 시각이 아니다) · 앵커는 createdTime.
- 무결성: Drive sha256 = 로컬 = 내려받은 사본 `d353f58695ea5e2878827af51675971fd237c34dc30d2757d3f5b712c2272dbf` · MD5 `12ee3f4dacfadd25a42ce78ddaef8b0c` · 43,513 bytes · `cmp` 동일.
- `bo_v1` = §1 표(25~53행 · LF + 끝 개행) SHA256 `1b8a41a8e6fe983b1982d9775451f93cb3f27b8d3f520102963c8913d1ba56f7`(앵커 직전 재계산 일치).
- `OOS_end = 2026-09-23T23:59:59.999Z`(createdTime 전 마지막 완전 UTC 일 · 기계적) · OOS 85일 · N = 4 · 시드 20260924 · 트라이얼 #1 OOS 영구 닫힘 재확인.
- 다음: 단계 2(하네스·전략 구현) before-pass(advisor + Codex) — 코드는 그 뒤.

## 2026-09-24 — 트라이얼 #2 **단계 2(하네스·전략 구현) before-pass**(advisor + Codex task-mufe4mmm-ehihrg · **FIX-PLAN-FIRST**)
- 계획 초안: 2a 앵커 모듈 · 2b 엔진/사이징(TIME_EXIT · Trail R배수 · E_ref · 레버리지 범위 · 시가 갭 청산) · 2c 재생 루프 23:59 훅 · 2d 유효일 · 2e 전략 · 2f 플라시보 · 2g 판정기(푸시 후 실행) · 2h 런타임 규칙 스냅샷 · 2i 구현 규약 행.
- 사전 확인: `paper/*.py`·`sizing/*.py`·`backtest/*.py`·`exchange/*.py`에 PROVENANCE 헤더 없음(복사 파일 아님 · 공유 계층 변경은 이 로그에 기록).

### 항목별 입장(Claude Code)
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 | ✅ 동의 | 진입마다 실행 지갑을 E_ref로 리셋 · Δ지갑 = 청산 후 − E_ref · 누적은 보고용 원장(Codex #1과 같음) |
| advisor | 2 | ✅ 동의 | "전역 지금 변경" 선택지 삭제 · 명시적 limits 범위(Codex #2 방식) |
| advisor | 3 | ✅ 동의 | `Trail.dist_r`(dist와 배타) · trail_r = \|체결 − SL\| 이미 설정됨(engine.py:448) · 상태 직렬화(276·295)에도 반영 |
| advisor | 4 | ✅ 확인 | 헤더 없음 — 위 사전 확인 |
| advisor | 5 | ✅ 동의 | 2i에서 삭제 · kline 종가로 구현·테스트(Codex #8) |
| advisor | 6 | ◐ 부분 | 주입 방식은 동의 · 실데이터 유효일 계산 **시점은 Codex #9 채택**(판정기 푸시 뒤) |
| advisor | 7 | ✅ 동의 | 판정기 푸시 = 사용자 체크포인트 |
| advisor | 8 | ◐ 부분 | Codex #7: 지금 캡처도 앵커 **뒤**라 문언과 다름 → 정정 문서 + 레지스트리 행 · 출처 하나만(대체 경로 없음) · **사용자 결정** |
| advisor | 9 | ✅ 동의 | Codex #4의 7단계 순서로 고정 |
| advisor | 10 | ✅ 동의 | `strategies/trial02/` 정적 검사(롤링 max/min·rolling·deque 극값) |
| Codex | 1 | ✅ 동의 | advisor 1과 동일 · 실패한 진입 시도는 리셋하지 않음 · 전진은 복리 그대로 |
| Codex | 2 | ✅ 동의 | RegimeSizing 생성 검사도 고침: 등록된 정책 대역(50–100 · 10–30) 중 하나에 포함 · size_entry에서 limits.leverage_range 포함 검사 · 기본 (50,100) |
| Codex | 3 | ✅ 동의 | P3용 `SlFromFill(anchor=O_d, mirror=True)` — SL′ = 2F − O_d · 사이징 전에 확정 · 결정 게이트는 원 방향 |
| Codex | 4 | ✅ 동의 | 23:59 봉 7단계(펀딩 → 대기 없음 단언 → 시가 갭 청산(경계 포함) → time_exit → bar_events → on_bar 생략 → on_minute_closed 호출) · 훅 없는 경로 불변 |
| Codex | 5 | ✅ 동의 | P2 큐 규칙(원 교차에서 소비·대기열 · i+k 마감 판정 · conflict → position_busy → 가격 게이트 · 원래 날에 묶임 · 체결 ≥ 23:59면 dropped) → 구현 규약 행 |
| Codex | 6 | ✅ 동의 | placebo 헬퍼를 명시 설정 객체로 · 트라이얼 #1 래퍼가 기존 기본값 유지 · #2 경로에 #1 앵커 import 없음 |
| Codex | 7 | ✅ 동의 | 정정 문서 + 행 · 출처 하나 · 원시 3종 SHA256 고정 · taker = 5 bps 단언(다르면 §2 정정) · **사용자 결정 대기** |
| Codex | 8 | ✅ 동의 | advisor 5와 같음 |
| Codex | 9 | ✅ 동의 | 실데이터 유효일 계산은 판정기 푸시 뒤 |
| Codex | 10 | ✅ 동의 | 트라이얼 #1 SR̂ 테스트는 커밋된 고정 파일(값 + report SHA) · 원 report 대조는 별도 감사 명령 |

### advisor 원문(verbatim)
> 1. **E_ref vs execution wallet is under-specified — blocks 2b design.** §1: "매 진입 E_ref = 1,000 · 복리 없음". If sizing uses E_ref but margin is drawn from a compounding wallet, a drawdown can make margin > wallet and the engine rejects entries → path-dependent eligibility the doc doesn't intend. Trial #1 P1 solved this with per-trade fixed capital (#19 ④; see `backtest/placebo_exec.py`). Recommend: reset the execution wallet to E_ref before each entry for Arm A/B too; report the compounding path only. Registry convention row + Codex question.
> 2. **Leverage "open item" is already decided.** §11-3: global changes at activation; backtest uses [10,30]. Per-`SizingLimits` override is right; drop "or change the global now" — don't reopen.
> 3. **Trail:** `arm_r * trail_r` already uses fill-R; only `dist` is absolute. Minimal change: `Trail.dist_r` alternative (exactly one of dist/dist_r), default path untouched. Verify in `_execute_entry`/`_post_fill` that `trail_r = |fill − sl|` is set when `tp_rule` is present — that's your R = |fill − O_d|.
> 4. **PROVENANCE check before touching `paper/engine.py`, `paper/types.py`, `sizing/*`.** If any carries the header, every change needs an `ops_log` entry (CLAUDE.md). Grep first.
> 5. **B&H close = kline close is explicit in §3-1** ("kline 종가"). Remove it from the 2i "open conventions" list.
> 6. **Day validity must be injected, never computed inside the strategy.** Validity of d depends on all 1,440 bars of d — unknowable at 00:00. §1 scopes it to backtest; 2d must feed `V_A/V_B` to the strategy as a set. Computing V_A on real bars before the evaluator push is not P&L and §5 pre-states the expected days — allowed, but log it as the only pre-push real-data touch, and if the enumeration differs from §5 that's a correction doc + registry row, not a silent fix.
> 7. **Evaluator push conflicts with "push only on explicit request".** §4-1 step 3 requires a push before any run. Treat it as a user checkpoint: request the push explicitly when 2g is ready; nothing runs until it lands.
> 8. **2h snapshot is time-bound.** §1/§11-6 say "앵커 시점 캡처". Anchor day is today UTC; capture after Codex returns (read-only GET, no funds). Check `.env` has the read-only key without printing it; if absent, fixture 2026-09-02 with a disclosure row.
> 9. **23:59 handling:** your "assert no pending entry" is sound (late_cross + P2 drop guarantee it). Still call `on_minute_closed` for the 23:59 bar so a cross there registers as `late_cross` for §7-3 counts; skip only `on_bar`. Set `ctx.bar_events` to the `close_now` events so the strategy sees the exit.
> 10. **§9 ③ test ("no rolling channel") — decide the mechanism now**, not during implementation: a static check on `strategies/trial02/` for rolling-window max/min over bars is the only enforceable form. Weak but pre-committed beats post-hoc.
> Sequence: 2a (anchor module + tests) → 2h → 2b/2c with Codex on the engine diff → 2d → 2e → 2f → 2g → after-pass → push request → 2i rows → IS run. No smoke run on real bars at any point before 2g is pushed — your plan says this; hold it.

### Codex 원문(verbatim · task-mufe4mmm-ehihrg)
> ## Findings
> 
> 1. **BLOCKER — `E_ref` needs a dual-ledger definition, not merely a sizing flag.**  
>    The anchor says every backtest entry uses fixed `E_ref = 1,000`, with no compounding, and defines `net_bps` from the trade’s wallet delta ([preregistration:52](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:52), [preregistration:53](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:53), [preregistration:197](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:197)). Currently the engine sizes from and mutates one cumulative wallet ([engine.py:395](/home/cms/project/BTC_Futures_E2E/paper/engine.py:395), [engine.py:441](/home/cms/project/BTC_Futures_E2E/paper/engine.py:441)), while replay records that cumulative value as the trade baseline ([engine_replay.py:71](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:71), [engine_replay.py:96](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:96)).
> 
>    Exact fix: for Trial #2 IS/OOS, reset the synthetic execution wallet to `E_ref` immediately before every accepted entry, then calculate `Δwallet = wallet_after − E_ref`. Accumulate trade results in a separate reporting/statistical ledger that never controls eligibility or size. Failed entry attempts must not reset it. Forward paper remains explicitly compounding under §3 ([preregistration:99](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:99)).
> 
>    This is the correct reading of §1 + §3. “Fixed sizing capital but cumulative execution wallet” is an alternative, but it contradicts “execution ledger / no compounding” and can create impossible margin states. A new engine per trade is economically equivalent but unnecessarily disrupts replay state. The dual-ledger/reset implementation is the faithful choice.
> 
> 2. **BLOCKER — the proposed leverage override cannot work as described.**  
>    `RegimeSizing(…, 10, 30)` is rejected during construction against the global `(50, 100)` range ([config.py:32](/home/cms/project/BTC_Futures_E2E/sizing/config.py:32)), before `SizingLimits` can affect anything. The sizing loop then reads the regime range directly ([position.py:184](/home/cms/project/BTC_Futures_E2E/sizing/position.py:184)). The plan’s “field on `SizingLimits`” alone is therefore incomplete.
> 
>    Exact fix:
> 
>    - Keep `PERMITTED_LEVERAGE == (50, 100)` unchanged.
>    - Add `SizingLimits.leverage_range`, defaulting to `(50, 100)`, with the only presently allowed override `(10, 30)`.
>    - Let `RegimeSizing` accept ranges contained within either registered policy band.
>    - At `size_entry`, require the regime range to be contained in `limits.leverage_range`.
>    - Trial #2 passes `(10, 30)` explicitly; bot and Trial #1 use defaults.
>    - Do not reopen registry #30’s activation decision ([trial_registry.md:38](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:38)).
> 
> 3. **BLOCKER — P3 cannot be implemented correctly through the current `EntryIntent`.**  
>    P3 requires the reversed SL and TP to be mirrored about the eventual fill ([preregistration:121](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:121)). But `EntryIntent.sl` is fixed before the next bar exists ([engine.py:110](/home/cms/project/BTC_Futures_E2E/paper/engine.py:110)), and `_execute_entry` uses that fixed SL for pre-fill checks and sizing ([engine.py:385](/home/cms/project/BTC_Futures_E2E/paper/engine.py:385), [engine.py:395](/home/cms/project/BTC_Futures_E2E/paper/engine.py:395)).
> 
>    Exact fix: add a mutually exclusive fill-derived SL rule, e.g. `SlFromFill(anchor=O_d, mirror=True)`. For the inverted fill `F`, resolve `SL′ = 2F − O_d`; then `R = |F − O_d|`, TP is `F ± 2R` in the inverted profit direction, and trail distance is `R`. Resolve it before sizing. Tests must cover both directions, adverse fill rounding, and the decision gate remaining in the original direction.
> 
> 4. **BLOCKER — the time-exit replay contract needs a fully specified call sequence.**  
>    Current replay always calls `on_bar`, then `on_minute_closed` ([engine_replay.py:65](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:65), [engine_replay.py:101](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:101)). “Skip `on_bar`” could accidentally also skip the 23:59 strategy callback, losing `late_cross` observations.
> 
>    Exact sequence for a hook-positive bar:
> 
>    1. Settle funding.
>    2. Assert there is no pending entry.
>    3. Test open-gap liquidation inclusively: long `open <= liq`, short `open >= liq`, timestamped at `open_ms`.
>    4. If alive, `close_now(open, open_ms, TIME_EXIT)`.
>    5. Put those close/liquidation events in `ctx.bar_events`.
>    6. Do not call `Engine.on_bar`.
>    7. Still call `strategy.on_minute_closed` for that 23:59 bar so crosses are consumed and counted as late.
> 
>    The hook-absent branch must remain the existing sequence byte-for-byte.
> 
> 5. **BLOCKER — P2 scheduling is not deterministic enough in the plan.**  
>    The anchor says consumption occurs at the original cross, while position/conflict state is evaluated at the delayed decision time ([preregistration:120](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:120)). The plan does not say whether a cross observed while busy is queued, how opposing queued signals are resolved, or whether a delayed candidate may roll into the next UTC day.
> 
>    Exact fix for the registry row:
> 
>    - Consume the direction and enqueue at the original cross regardless of current position.
>    - Candidate from bar index `i` is decided at close of `i+k`.
>    - At that delayed close, resolve opposing due candidates as `conflict_cross`, then check `position_busy`, then the decision-price gates.
>    - The candidate remains tied to its original UTC day.
>    - If its next-open fill timestamp is `>= original_day 23:59:00`, record P2 `dropped`; never carry it into the next day or switch to the next day’s `O_d/R`.
>    - Pin the mutually exclusive failure priority in a test and registry row.
> 
> 6. **BLOCKER — Trial #2 cannot safely reuse `backtest/placebo.py` as currently parameterized.**  
>    The shared module imports Trial #1’s anchor directly ([placebo.py:34](/home/cms/project/BTC_Futures_E2E/backtest/placebo.py:34)); its P1/P4 defaults are bound to those constants ([placebo.py:76](/home/cms/project/BTC_Futures_E2E/backtest/placebo.py:76), [placebo.py:231](/home/cms/project/BTC_Futures_E2E/backtest/placebo.py:231)). That conflicts with the explicit prohibition on importing Trial #1 anchor constants and risks silently using seed `20260921`.
> 
>    Exact fix: refactor generic placebo helpers to require an explicit seed/config object, with no Trial #1 import or default on the Trial #2 path. Keep a Trial #1 wrapper preserving its current defaults. Trial #2 must pass `20260924`, explicit draw counts, explicit `V_A`, and its same-day/23:58 eligibility predicate.
> 
> 7. **BLOCKER — the promised “anchor-time runtime snapshot” no longer exists.**  
>    The binding text requires an anchor-time snapshot ([preregistration:52](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:52), [preregistration:210](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:210)). Capturing it now is post-anchor; the 2026-09-02 fixture is pre-anchor. Neither is literally the registered rule.
> 
>    This requires a correction document plus append-only registry row before P&L. Select exactly one source prospectively—preferably a newly captured, timestamped post-anchor snapshot—and pin the raw `exchangeInfo`, `leverageBracket`, and `commissionRate` hashes. Do not retain a discretionary “new capture, else fixture” fallback. Also assert that the execution taker cost is exactly the preregistered 5 bps; otherwise §2 needs an explicit correction rather than silently using an account-specific fee.
> 
> 8. **BLOCKER — B&H close is not an open implementation convention.**  
>    The anchor explicitly requires the last 1m **kline close** ([preregistration:96](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:96), [preregistration:110](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:110)). Remove “mark-open vs kline” from 2i and implement/test the kline rule verbatim. It can change the eventual ACCEPT label, so leaving it open is verdict-relevant.
> 
> 9. **NON-BLOCKING — actual `V_A/V_B` computation should be moved after the evaluator push.**  
>    Computing validity is not P&L and is not statistical look-ahead; the eligibility rule expressly depends on whole-day completeness. Nevertheless, §4-1 says evaluator committed and pushed before “all runs” ([preregistration:126](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:126)). The clean ordering is: implement `days.py` and synthetic tests in 2d, commit evaluator and convention rows, push only on explicit user instruction, then execute the real-data validity pass. This avoids needing an exception to the literal staging text.
> 
> 10. **NON-BLOCKING — provenance and regression pinning need to be explicit.**  
>     The four proposed shared-layer files currently have no copied-module `PROVENANCE` header. Record that check and each shared change in `docs/ops_log.md`; do not invent a copied-file header. The Trial #1 report consistency test should not make the normal unit suite depend on `var/`: pin the two literal SR values and report SHA in a committed provenance fixture, with a separate audit command that verifies the original report when deliberately supplied.
> 
> ## Look-ahead assessment
> 
> There is no inherent look-ahead if these rules are pinned:
> 
> - `O_d`: take only the 00:00 bar’s `mark_open`; initialize before evaluating that same bar’s completed OHLC.
> - `R_{d−1}`: compute only from the 1,440 closed prior-day mark bars and freeze it for day `d`.
> - Arm B: median is exactly `R_{d−21}…R_{d−2}`; `R_{d−1}` is the comparison value and must not enter the median.
> - `V_A/V_B`: compute outside the strategy and inject immutable day eligibility. Whole-day availability is an explicitly preregistered ex-post sample rule, not a signal. Never apply that mechanism to forward execution, where a missing bar is G-F failure.
> - P4: derive `q` only from prior-day `R`, anchor snapshot tick, draw id, and UTC `day_index`. For `R < tick`, apply `no_range` before RNG consumption.
> - P2: delayed gates use only the close of bar `i+k`; fill uses `i+k+1` open. Nothing from that fill bar may enter the decision.
> 
> Tests should perturb current-day future highs/lows, `R_{d−1}`, each median member, invalid-day future gaps, P4 future bars, and P2’s eventual fill bar independently.
> 
> ## Tests that must pin default behavior
> 
> At minimum:
> 
> - Existing full suite and all Trial #1 replay/strategy tests.
> - Golden synthetic replay equality with no `exit_at_bar_open` hook.
> - Two sequential default-engine trades proving `E_ref=None` still compounds exactly as today.
> - Existing positional `Trail(arm_r, dist)` behavior, snapshot serialization/restoration, and fixed-distance results.
> - `dist`/`dist_r` XOR validation plus resolved `1R` distance.
> - Default `(50,100)` sizing decisions byte/value-identical; `(10,30)` works only with explicit limits.
> - Tick/bar liquidation priority, funding refresh, and wallet conservation unchanged.
> - 23:59 long/short gap liquidation, equality boundary, time exit at open, ignored high/low, callback still invoked.
> - Arm B contraction-day trades exactly equal Arm A trades in fill, quantity, leverage, exits, and `net_bps`.
> - Explicit `V_A/V_B` bootstrap sets: invalid days excluded, not zero-filled.
> - All §11-7 cases plus P2 queue/day-boundary cases, P3 fill mirroring, P4 `R<tick`, P4 exact RNG reproduction, P1 same-day/23:58/`V_A`.
> - Evaluator degeneracy, survival and staged precedence, P2/P3 zero trades = 0 bps, P4 `<190`, defined-SR subset with `n_trials=4`, A/B report-only status, MDE, and B&H kline close.
> 
> No files were changed, no `var/` content was read, and no market/backtest command was run.
> 
> VERDICT: FIX-PLAN-FIRST
> 
> Codex session ID: 01a0d2f7-17c9-77b2-8f8c-aba134907ef4
> Resume in Codex: codex resume 01a0d2f7-17c9-77b2-8f8c-aba134907ef4

## 2026-09-24 — 트라이얼 #2 단계 2h: 런타임 규칙 스냅샷 캡처(레지스트리 #36 · 정정 문서 01)
- 사용자 결정 (a): 앵커 뒤 같은 날 캡처 하나 · 대체 경로 없음.
- `scripts/capture_trial02_rules.py`(테스트 4개 먼저 — POST 없음 AST 검사 · 권한 거부 · taker 불일치 시 아무것도 안 씀) → 실행 2026-09-24T11:01:04Z.
- 키 권한 실측 = 읽기 전용(읽기 외 플래그 꺼짐) · GET 4회(exchangeInfo · leverageBracket · commissionRate · fundingInfo).
- taker 0.0005 = §2 5 bps · 파싱 값은 2026-09-02 fixture와 같다 · 파일에 키·서명 문자열 없음(grep 0).
- SHA256 4개는 레지스트리 #36 · 정정 문서 01.

## 2026-09-24 — 트라이얼 #2 단계 2 계획 r2 **Codex 좁은 재확인**(task-muffa66t-k348ve) **PROCEED**
- r2 = before-pass 반영(차단 1~8) · 2h 완료(#36). Codex: 차단 1~8 전부 CLOSED · 새 모호성 없음.
- 비차단 1건: 2i 목록은 예시일 뿐 — §11-8(산출물 스키마·격리 CLI 경로·커밋/푸시 증거)도 행에 기록 → ✅ 동의(2i에 포함).

### 계획 r2 원문
> # Trial #2 step 2 — revised plan r2 (after advisor + Codex before-pass FIX-PLAN-FIRST; ops_log 8bfbba8)
> 
> Unchanged: anchor #35; no real-data P&L and no real-data validity pass before the evaluator is committed + pushed (user checkpoint);
> OOS closed (no OOS data fetched/prepared). All development tests synthetic.
> DONE: 2h runtime rules = docs/trials/trial_02_rules_snapshot/ (registry #36, correction 01; captured 2026-09-24 post-anchor same day,
> single source, no fallback, taker 0.0005 asserted; fundingInfo included as parser-required input from the same capture).
> 
> 2a Anchor module strategies/trial02/anchor.py (own constants; imports nothing from trial01): createdTime, Drive id, doc SHA256, bo_v1,
>    OOS_END mechanical, N_TRIALS 4, ALPHA 0.0125, LEVEL 0.9875, SR_1A/SR_1B literals, seeds, rules snapshot dir + 4 SHA256.
>    Tests: recompute doc SHA256 + bo_v1 from file; snapshot SHA256s; SR_1A/1B equal a COMMITTED fixture (values + report.json SHA256
>    11c88452…) — no var/ dependency in the unit suite; a separate audit command checks the original report.json when present.
> 2b Shared layer (defaults byte-identical; each change logged in ops_log; Codex review of the diff):
>    - ExitReason.TIME_EXIT.
>    - Trail: dist XOR dist_r; dist_r resolved at fill as dist_r × trail_r (trail_r = |fill − SL| already set, engine.py:448);
>      position_state/restore_position serialize dist_r.
>    - SlFromFill(anchor, mirror) — mutually exclusive with fixed sl; for P3: SL′ = 2F − O_d resolved at fill BEFORE sizing;
>      R = |F − O_d|; TP = F ± 2R in the (inverted) profit direction via TpFromFill(level=None, fallback_r=2); trail dist 1R.
>      Pre-fill sl_crossed check uses the resolved SL. Decision gate stays in the original direction (strategy side).
>    - Fixed sizing capital: engine flag sizing_capital (None = current). When set: before every ACCEPTED entry the execution wallet is
>      reset to E_ref; Δwallet = wallet_after_close − E_ref; failed/refused attempts do not reset; a separate cumulative report ledger
>      sums trade PnL and never affects eligibility/size. Forward paper stays compounding (flag None).
>    - Leverage: PERMITTED_LEVERAGE (50,100) unchanged; registered policy bands = {(50,100),(10,30)}; RegimeSizing accepts a range
>      inside one registered band; SizingLimits.leverage_range default (50,100); size_entry requires regime range ⊆ limits range.
>      Trial #2 passes (10,30) explicitly; bot + trial #1 use defaults.
>    - Engine.liquidate_if_open_beyond(open_mark, ts=open_ms): long open ≤ liq, short open ≥ liq (inclusive) → LIQUIDATION.
> 2c Replay loop: optional Strategy.exit_at_bar_open(bar). Hook-positive bar sequence:
>    1 settle funding · 2 assert no pending entry · 3 gap liquidation at open (inclusive) · 4 else close_now(open, open_ms, TIME_EXIT)
>    · 5 ctx.bar_events = those events · 6 do NOT call Engine.on_bar · 7 still call strategy.on_minute_closed (late crosses consumed/counted).
>    Hook-absent branch byte-identical (golden synthetic replay equality test). Replay also supports fixed sizing capital
>    (trade record wallet_before = E_ref).
> 2d backtest/days.py (strategy-independent): V_A / V_B per §1 strict completeness; injected into strategy/evaluator as immutable sets;
>    never computed inside the strategy. Real-data execution only after the evaluator push; if the enumeration disagrees with §5's
>    stated invalid days → correction doc + registry row.
> 2e strategies/trial02/: O_d = 00:00 mark_open captured before that bar's OHLC is evaluated; R_{d−1} from the 1,440 closed prior-day
>    mark bars, frozen for d; Arm B median of R_{d−21}..R_{d−2} (R_{d−1} excluded); fixed bands; first cross per direction consumed;
>    conflict_cross; decision gate at cross close; late_cross (fill ≥ 23:59); position_busy; invalid day; exclusive first-failure counts.
>    P2 (registry convention row): consume + enqueue at the original cross regardless of position; decided at close of i+k;
>    at that close resolve opposing due candidates as conflict_cross → position_busy → price gates; candidate tied to its original UTC day;
>    fill ≥ original day 23:59:00 → dropped (never carried into next day). P3 via SlFromFill mirror. P4: R < tick → no_range before any
>    RNG; q = rng.integers(1, floor(R/tick)+1) once per day; k* = q·tick/R.
>    §9 ③: static check over strategies/trial02/ (no rolling max/min, .rolling(, deque-of-extremes, argmax/argmin over bar windows).
> 2f Placebo helpers refactored to take an explicit config (seed, draws, eligibility predicate, valid-day set, sizing) with NO default
>    from trial01's anchor on the trial #2 path; trial #1 wrapper keeps its current defaults (its tests unchanged). P1 = (a)–(f) +
>    same-day / t+h−1 ≤ 23:58 / V_A; E_ref sizing L ∈ [10,30]; seed 20260924 spawn(1000).
> 2g backtest/evaluate_t2.py (imports no strategy module): statistical ledger N_stat; V_A day blocks; CI 0.625/99.375; bootstrap
>    SeedSequence((20260924,1)).spawn(8)[k] fixed table; G0/G1/G2/G-B (defined SR̂ subset, n_trials 4, <2 → fail), flat, P1 gate,
>    P2/P3 (0 trades → 0 bps), P4 (<190 defined → 폐기), survival, B&H with kline close, A/B daily contrast on V_B, MDE, §7 staged
>    precedence incl. degenerate rules. Synthetic tests for every §7 row.
> 2i Implementation-convention registry rows before any real-data run (P2 queue, fixed-capital reset, SlFromFill, 23:59 sequence,
>    leverage bands, P4 q draw, bootstrap table, placebo config, static-check scope).
> Order: 2a → 2b+2c (Codex diff review) → 2d → 2e → 2f → 2g → after-pass (advisor + Codex) → push request (user) → real-data validity
> pass → IS run with all outputs opened together (one evaluator call). Standing rule before/after on each step.
> 
> Default-path pinning tests: full suite; trial #1 replay/strategy tests; golden no-hook replay; two sequential default trades compound
> as today; positional Trail(arm_r, dist) + snapshot round-trip; dist/dist_r XOR; default (50,100) sizing identical, (10,30) only with
> explicit limits; liquidation priority/funding refresh/wallet conservation; 23:59 long/short gap liq incl. equality, time exit at open,
> high/low ignored, callback invoked; Arm B contraction-day trades identical to A; invalid days excluded not zero-filled; §11-7 list;
> P2 queue/day boundary; P3 mirror both directions; P4 R<tick + RNG reproduction; P1 eligibility.

### Codex 원문(verbatim · task-muffa66t-k348ve)
> ## Blockers 1–8
> 
> The inline r2 plan has no stable line numbers, so I cite its section and exact line lead.
> 
> | # | Status | r2 closure |
> |---|---|---|
> | 1 | **CLOSED** | **2b, “Fixed sizing capital”** defines the per-accepted-entry `E_ref` reset, `wallet_after_close − E_ref`, separate non-controlling report ledger, no reset for failed/refused attempts, and compounding default for forward paper. This matches the exact requested fix in [ops_log.md:4441](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4441) and the fixed-capital requirement in [trial_02_preregistration.md:52](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:52). |
> | 2 | **CLOSED** | **2b, “Leverage”** keeps `(50,100)` as the default, registers `(10,30)`, permits `RegimeSizing` only within a registered band, enforces containment in `SizingLimits.leverage_range`, and makes Trial #2 explicit. This closes every item listed at [ops_log.md:4451](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4451). |
> | 3 | **CLOSED** | **2b, “SlFromFill(anchor, mirror)”** supplies the missing fill-derived SL contract: mutual exclusion, `SL′ = 2F − O_d`, resolution before sizing, `R = |F − O_d|`, inverted-direction `2R` TP, `1R` trail, resolved-SL pre-fill check, and original-direction decision gate. Both directions are pinned in tests. This satisfies [ops_log.md:4460](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4460) and P3 at [trial_02_preregistration.md:121](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:121). |
> | 4 | **CLOSED** | **2c, numbered hook-positive sequence 1–7** reproduces the required funding → pending assertion → inclusive gap liquidation → time exit → `ctx.bar_events` → no `on_bar` → still invoke `on_minute_closed` sequence. It also pins the hook-absent branch byte-identically. Compare [ops_log.md:4468](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4468) and [trial_02_preregistration.md:204](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:204). |
> | 5 | **CLOSED** | **2e, “P2 (registry convention row)”** pins enqueue/consumption at the original cross, `i+k` decision time, `conflict_cross → position_busy → price gates`, original-day ownership, and `fill ≥ 23:59` drop without rollover. This matches [ops_log.md:4483](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4483). |
> | 6 | **CLOSED** | **2f, “Placebo helpers refactored to take an explicit config”** removes Trial #1 defaults from the Trial #2 path while retaining a Trial #1 compatibility wrapper. Trial #2 explicitly supplies seed, draws, eligibility, `V_A`, sizing, and same-day/23:58 constraints, closing [ops_log.md:4492](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4492). |
> | 7 | **CLOSED** | Registry #36 and correction 01 select one post-anchor same-day capture, prohibit fallback, pin all four hashes, and assert taker `0.0005`. Evidence: [trial_02_correction_01.md:10](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_correction_01.md:10) and [trial_registry.md:44](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:44). |
> | 8 | **CLOSED** | **2g, “B&H with kline close”** removes the open choice and implements the binding kline-close rule from [trial_02_preregistration.md:96](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:96) and [trial_02_preregistration.md:110](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:110). |
> 
> ## New ambiguity/default-path check
> 
> No new verdict-changing ambiguity or default-engine regression is authorized by r2:
> 
> - Fixed-capital behavior is opt-in; `None` remains compounding.
> - `(50,100)` remains the default sizing policy.
> - Existing positional `Trail(arm_r, dist)` is explicitly preserved and regression-tested.
> - The replay hook-absent path must remain byte-identical.
> - P2/P3/P4 timing, RNG, degeneracy, and evaluator precedence are pinned.
> - Full-suite, Trial #1, golden replay, snapshot, liquidation, funding, and wallet-conservation tests are required.
> 
> One non-blocking completeness note: the **2i** parenthetical should not be treated as exhaustive. The binding text still requires the output schema, isolated CLI path, and commit/push evidence to be recorded under [trial_02_preregistration.md:212](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:212). The binding line resolves this; it does not permit divergent verdicts.
> 
> Read-only review only: no files changed, no tests or backtests run, and neither `var/` nor market data was read.
> 
> **VERDICT: PROCEED**
> 
> Codex session ID: 01a0d314-aa56-7871-9508-c44b389e570d
> Resume in Codex: codex resume 01a0d314-aa56-7871-9508-c44b389e570d

## 2026-09-24 — 트라이얼 #2 단계 2b·2c: 공유 계층 변경(엔진·사이징·재생 · 전부 기본 꺼짐)
- PROVENANCE 헤더 없는 파일(복사 아님) — 변경 기록은 이 항목.
- `sizing/config.py`: `REGISTERED_LEVERAGE_BANDS = ((50,100),(10,30))`(#30) · `RegimeSizing`은 등록 대역 하나 안에 · `SizingLimits.leverage_range` 기본 `PERMITTED_LEVERAGE`(50,100 — 불변) · 등록 대역만 허용.
- `sizing/position.py`: `size_entry`가 레짐 범위 ⊆ `limits.leverage_range`를 요구(아니면 ValueError — 설정 오류).
- `paper/types.py`: `ExitReason.TIME_EXIT`.
- `paper/engine.py`: `Trail.dist_r`(dist와 배타 · 체결 때 dist_r × R로 확정 — 스냅샷·TrailSet 형태 불변) · `SlFromFill(anchor, mirror)`(`sl == anchor` 요구 · mirror면 SL = 2 × 예상 체결가 − anchor · 사이징 전 확정 · 체결 전 검사도 해석된 SL) · `sizing_capital`(PAPER만 · 체결된 진입마다 지갑 → E_ref · `WalletResynced(source="fixed_capital")` · 거부 시도는 리셋 없음) · `liquidate_if_open_beyond`(PAPER만 · 경계 포함).
- `backtest/engine_replay.py`: `exit_at_bar_open` 훅 7단계 · `sizing_capital` → 트레이드 기준 지갑 = E_ref · `report_ledger_pnl`.
- 기본 경로 고정: 2b 이전 커밋(bdf0554) 트리로 만든 골든(`tests/fixtures/golden_replay_nohook.json` · 60 트레이드 · 120 이벤트)과 바이트 동일 · 전체 테스트·ruff·pyright 통과.

## 2026-09-24 — 트라이얼 #2 단계 2b·2c **after-pass**(advisor + Codex task-muffu31k-j8wgyr **FIX-FIRST**) → 수정
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 | ✅ 동의(Codex #1과 같음) | #2는 "명목×fee"만 적어 기준이 모호 · 앵커된 §1은 "수량 × 추정 청산가"로 구체적 → **§1 그대로 구현**(정정 문서 불필요) · 엔진 옵션 `liq_fee_on_liq_price`(PAPER만 · 기본 False = 봇·트라이얼 #1 불변) · 2i 규약 행 |
| advisor | 2 | ✅ 동의 | 훅 분 `on_minute_closed` 뒤에도 대기 진입 없음 단언 + 테스트 |
| advisor | 3 | ✅ 동의 | `request_entry`에서 레짐 ⊄ limits.leverage_range → `EntryRefused`(size_entry의 ValueError는 방어선으로 유지) |
| advisor | 4 | ✅ 동의 | 2g 판정기: 고정 자본 모드에서 `final_wallet`을 읽지 않는다(테스트) |
| advisor | 5 | ✅ 동의 | exit_ref = 갱신된 청산가 단언 · 골든 재생성 방법 docstring |
| Codex | 1 | ✅ 동의 | advisor 1과 같음 · 롱/숏 · 펀딩 뒤 손실식 테스트 |
| Codex | 2 | ✅ 동의 | `ReplayResult` 필드 원복(`report_ledger_pnl` 제거) · 보고 원장 = `report_ledger(trades)` 함수 · 필드 목록 테스트 |
| Codex | 3 | ◐ 부분 | 계산은 맞다는 판정 · XOR 대신 `sl == sl_rule.anchor`(자리표시) 유지 — Optional로 바꾸면 기본 경로 타입 14곳 변경 · **2i 규약 행으로 등록** |
| Codex | 4 | ✅ 동의 | 추가: 롱/숏 청산 손실(두 기준 · 펀딩 뒤) · 경계 청산 exit_ref(롱/숏) · 사이징 거부·0체결 비리셋 · DB 기록(TIME_EXIT · fixed_capital) · 결과 필드 불변 · LIVE 기본 경로 = 기존 LIVE 테스트 전부 무변경 통과 |
- Codex의 전체 테스트 167 오류는 읽기 전용 환경의 임시 디렉터리 부재(보고대로) — 로컬 전체 통과.

### advisor 원문(verbatim)
> **1. §1 liquidation-fee basis vs `_liquidate` — verify now, resolve before any P&L.**
> Prereg line 46: "PAPER 손실 = 남은 격리 지갑 + 청산 시점 남은 명목(**수량 × 추정 청산가**) × liquidationFee(#2·#4)". Engine `_liquidate` (unchanged by 2b): `n = qty × entry_price; loss = n/L − comm − funding + n × fee` — fee on **entry** notional. Difference = fee × qty × |entry − liq|; hits net_bps of every liquidated trade (Arm B, P1 draws — "청산은 엔진 판정 그대로(보고)"). Check what registry #2 actually says (`grep "^| 2 |" docs/trial_registry.md`). If #2 = entry notional → prereg text is the error → correction doc 02 + row "engine/#2 authoritative". If #2 = liquidation-price notional → engine has been off since trial #1 → do **not** touch the default path; needs a user decision. Either way: a row before the IS run. Doesn't block 2d.
> **2. Hook-bar guard is one-sided.** You assert `pending is None` at the 23:59 bar's *start*. An intent emitted at that bar's `on_minute_closed` fills at next-day 00:00 `on_bar` — no guard, silently a cross-day trade. Add after step 7: `assert eng.pending is None` (or `cancel_pending` + logged skip). One line, one test.
> **3. `RegimeSizing` loosening moved a misconfig from fail-fast to fail-mid-bar.** Before: `RegimeSizing(…,10,30)` raised at construction. Now it constructs; `size_entry` raises `ValueError` inside `_execute_entry` inside `on_bar` — for the bot that's an uncaught exception in the trading loop, not `EntryRefused`. Planned and PROCEEDed, but the consequence wasn't stated. Cheapest fix: duplicate the containment check in `request_entry` → `EntryRefused` (bot path handles it). Raise with Codex; log the position either way.
> **4. `final_wallet` is meaningless under `sizing_capital`** (= E_ref + last pnl). Note for 2g: evaluator reads `report_ledger_pnl` and per-trade net_bps only; assert it never touches `final_wallet` when fixed capital is set.
> **5. Minor test gaps:** gap-liquidation test doesn't assert `exit_ref == liq_price_est`; golden test should state in its docstring "regenerate by running this body against bdf0554" (your scratch generator isn't committed).
> **Procedure:** don't start 2d until Codex returns. Log this pass + Codex verbatim with per-point positions (one ops_log entry). If Codex FIX-FIRST → fix, re-run golden + full suite, narrow re-check before 2d. Item 1 goes into the 2i registry batch regardless of Codex's verdict — it's a text/code mismatch, not a Codex call.

### Codex 원문(verbatim · task-muffu31k-j8wgyr)
> 1. **BLOCKER — liquidation fee uses the wrong notional.** [paper/engine.py:603](/home/cms/project/BTC_Futures_E2E/paper/engine.py:603) calculates the fee as `qty × entry_price × liquidationFee`; the binding rule requires `qty × liq_price_est × liquidationFee`. [sizing/position.py:264](/home/cms/project/BTC_Futures_E2E/sizing/position.py:264) reports the same incorrect entry-notional loss. This overstates long liquidation losses and understates short losses, biasing `wallet_after`, `net_pnl`, `net_bps`, the report ledger, and especially P3 comparisons. Fixing it globally would change Trial #1/default behavior, so Trial #2 needs an explicit opt-in accounting policy unless the default-path constraint is formally revised.
> 
> 2. **BLOCKER — the no-hook golden does not actually prove byte-identical default behavior.** `ReplayResult` now always has `report_ledger_pnl`, including when `sizing_capital=None` ([engine_replay.py:61](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:61)). Thus full dataclass serialization/field enumeration differs from `bdf0554`. The golden test manually constructs a subset that omits this field ([test_replay_bar_open_exit.py:71](/home/cms/project/BTC_Futures_E2E/tests/test_replay_bar_open_exit.py:71)), hiding the schema change. Current Trial #1 writers happen to select fields individually, but the strict default-path promise is false at the public result-object boundary.
> 
> 3. **Contract mismatch — `SlFromFill` is not mutually exclusive with fixed SL as plan r2 specifies.** `EntryIntent.sl` remains mandatory while `sl_rule` is additional ([engine.py:129](/home/cms/project/BTC_Futures_E2E/paper/engine.py:129), [engine.py:136](/home/cms/project/BTC_Futures_E2E/paper/engine.py:136)); the engine requires `sl == anchor` as a placeholder ([engine.py:208](/home/cms/project/BTC_Futures_E2E/paper/engine.py:208)). A strategy following the stated XOR contract cannot construct the intended intent. The arithmetic thereafter is correct—quote-derived mirror SL is resolved before sizing, and TP/trail use fill-R—but this convention must either be aligned with r2 or explicitly registered before strategy implementation.
> 
> 4. **Missing tests.** The new liquidation tests assert only reason/timestamp ([test_engine_trial02_ext.py:200](/home/cms/project/BTC_Futures_E2E/tests/test_engine_trial02_ext.py:200), [test_replay_bar_open_exit.py:88](/home/cms/project/BTC_Futures_E2E/tests/test_replay_bar_open_exit.py:88)), which is why finding 1 passes. Add:
> 
>    - Long/short liquidation loss using `qty × liq_price_est`, including after funding.
>    - Replay equality-boundary liquidation and `exit_ref == refreshed liq_price_est`.
>    - Short 23:59 gap liquidation.
>    - Fixed-capital non-reset for sizing rejection, leverage refusal, and zero-fill send failure.
>    - DB persistence for `WalletResynced(source="fixed_capital")` and `PositionClosed(reason=TIME_EXIT)`.
>    - A complete default `ReplayResult` compatibility assertion or an explicitly approved schema change.
>    - A LIVE default-path call/event regression pin. Fixed-distance snapshot round-trip is already covered by the existing trailing tests.
> 
> The fixed-capital reset timing, replay `E_ref` baseline/report ledger, leverage bands, inclusive gap boundary, funding-first hook order, skipped `on_bar`, and continued `on_minute_closed` callback otherwise match r2.
> 
> Verification: targeted tests passed `27/27`; a focused default/Trial #1/LIVE/sizing/snapshot set passed `169/169`; `git diff --check` passed. The full suite reached `747 passed`, but 167 tests errored because the read-only environment provides no writable temporary directory, so a clean full-suite result could not be certified. No files were changed.
> 
> VERDICT: FIX-FIRST
> 
> Codex session ID: 01a0d322-d769-7740-a6ac-3a97f830c309
> Resume in Codex: codex resume 01a0d322-d769-7740-a6ac-3a97f830c309

## 2026-09-24 — 트라이얼 #2 2b·2c 좁은 재확인 r2(Codex task-mufgblck-kmknws **FIX-FIRST**) → 수정
| # | Codex | 입장 | 반영 |
|---|---|---|---|
| 1 | PARTIAL — `loss_at_liquidation_usdt`가 진입 명목 | ✅ 동의 | 옵션을 `SizingLimits.liq_fee_on_liq_price`로 옮김 — 사이징 추정과 PAPER 엔진 손실이 **한 설정** · 엔진 kwarg 제거 · PAPER 전용 검사 유지 |
| 2 | CLOSED | — | — |
| 3 | CLOSED(`sl == anchor` 규약 수용) | — | 2i 규약 행 |
| 4 | PARTIAL — 테스트 3개 부족 | ✅ 동의 | 레버리지 대역 거부 시 비리셋 · **LIVE 골든**(`tests/fixtures/live_golden_scenario.py` — 2b 이전 트리 bdf0554 출력 = 현재 · 롱 SL/숏 TP/트레일 · 이벤트 + 송신기 호출) · 재생 수준 수수료 기준 차이 = qty × (체결 − 청산가) × fee |

### Codex 원문(verbatim · task-mufgblck-kmknws)
> 1. Finding #1 — PARTIAL. Actual liquidation accounting is fixed via the default-off `liq_fee_on_liq_price` option, including long/short and funding tests. However, `SizingDecision.loss_at_liquidation_usdt` still records `margin + entry_notional × fee` at [sizing/position.py](/home/cms/project/BTC_Futures_E2E/sizing/position.py:264). That value is persisted to the decisions table, so Trial #2 would record a liquidation-loss estimate inconsistent with its actual `qty × liq_price_est` accounting. The selected basis must propagate into this field without changing the default path.
> 
> 2. Finding #2 — CLOSED. `ReplayResult` has its original four fields at [engine_replay.py](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:57); reporting accumulation moved to the additive `report_ledger()` helper. The field-list regression test confirms compatibility.
> 
> 3. Finding #3 — CLOSED. Keeping `sl == sl_rule.anchor` as the registered placeholder convention is acceptable. Equality is enforced, and the engine deterministically replaces it with the fill-derived SL before sizing. There is no discretionary path or verdict ambiguity.
> 
> 4. Finding #4 — PARTIAL. Most requested coverage was added: both liquidation directions/bases after funding, equality-boundary replay and refreshed exit reference, sizing-rejection/zero-fill non-reset, DB persistence, hook-bar guard, and result-schema compatibility. Still absent are:
> 
>    - An explicit fixed-capital wallet assertion for leverage-band refusal.
>    - The requested LIVE default-path call/event regression pin.
>    - A replay-level test proving `liq_fee_on_liq_price=True` reaches realized Trial #2 P&L.
> 
> No unintended valid default-path behavior change found. Defaults remain entry-notional liquidation fees, compounding wallet, unchanged `ReplayResult`, and no exit hook. The earlier leverage-band failure is intentionally moved to `EntryRefused`.
> 
> Verification: 39 changed-module tests and 114 sizing/paper-engine tests passed; focused Ruff and Pyright passed; `git diff --check` passed. The broader regression selection was blocked for five `tmp_path`-dependent tests because no writable temporary directory exists.
> 
> VERDICT: FIX-FIRST
> 
> Codex session ID: 01a0d32f-4e3a-77a3-9d1e-dd0e2bca19f9
> Resume in Codex: codex resume 01a0d32f-4e3a-77a3-9d1e-dd0e2bca19f9

## 2026-09-24 — 트라이얼 #2 2b·2c 재확인 r3(Codex task-mufjmufw-ir6w4u) **MERGE**
- #1·#4 CLOSED · 기본 경로 변경 없음(LIVE·무훅 골든 = 2b 이전 트리). 2b·2c 완료.

### Codex 원문(verbatim)
> | Finding | Status | Re-check |
> |---|---|---|
> | #1 | **CLOSED** | [SizingLimits](/home/cms/project/BTC_Futures_E2E/sizing/config.py:58) now supplies one fee-basis setting to the [sizing estimate](/home/cms/project/BTC_Futures_E2E/sizing/position.py:265) and [PAPER liquidation](/home/cms/project/BTC_Futures_E2E/paper/engine.py:613). The long/short, funding, and replay P&L checks passed. |
> | #4 | **CLOSED** | The leverage-refusal wallet check, LIVE call/event golden, and replay-level fee-difference check passed. The no-hook replay golden also passed. |
> 
> **Default path:** No behavioral change found. `liq_fee_on_liq_price` defaults to `False`, preserving entry-notional liquidation fees; the LIVE and no-hook goldens match the supplied pre-2b fixtures. `SizingLimits` gains a field, but default execution does not change.
> 
> The checks were run directly without pytest cache or temporary files; the full suite was not run. The worktree is clean, and `git diff --check` passed.
> 
> **VERDICT: MERGE**
> 
> Codex session ID: 01a0d384-3b34-7141-88f0-f951aa21c709
> Resume in Codex: codex resume 01a0d384-3b34-7141-88f0-f951aa21c709

## 2026-09-24 — 트라이얼 #2 단계 2d·2e **before-pass**(advisor + Codex task-mufjq08e-jiwk3t **FIX-PLAN-FIRST**) → 설계 r2
| 출처 | # | 입장 | 반영(설계 r2) |
|---|---|---|---|
| advisor | 1 | ✅ | C7 · 규약 7 |
| advisor | 2 | ✅ | C8 · 규약 12 |
| advisor | 3 | ✅ | C9 · 규약 13 |
| advisor | 4 | ◐ | C10 — Codex #1로 R은 유효성과 분리되므로 "무효일 X의 봉을 바꿔도 불변"은 X의 R을 통해서만 달라질 수 있다 · 그 경로만 허용하는 형태로 테스트 |
| advisor | 5 | ✅ | Q1~Q4 Codex와 같음 |
| advisor | 6 | ✅ 확인 | `intent.sl`을 읽는 다른 코드 없음(db/record · 재생 루프 grep) |
| advisor | 7 | ✅ | — |
| advisor | 과정 | ✅ | `docs/trials/trial_02_conventions_draft.md`(커밋) · 수수료 기준은 다음 보고에 공시 |
| Codex | 1 | ✅ | C1 — R 이력은 완전한 mark 격자 날마다 · 적격성과 분리 |
| Codex | 2 | ✅ | C2 — 정확한 1,440분 격자 |
| Codex | 3 | ✅ | C3 — 실행 전 데이터 점검(REST 구간 mark-only 분 = 0이어야 · 아니면 중단 → 정정) |
| Codex | 4 | ✅ | C4 — 23:59 봉 고저 미사용 · 23:58 첫 교차 = late_cross |
| Codex | Q1~Q4 | ✅ | C5(펀딩 경계당 정확히 1건) · 보고 순서 · Decimal 중앙값 · B = A + 날 필터 |
| Codex | 테스트 | ✅ | C6 |

### 설계 r1(원문)
> # Trial #2 steps 2d (day validity) + 2e (strategy) — design for the before-pass
> 
> Binding: docs/trials/trial_02_preregistration.md §1 (rows 27–53), §3-1 (V_A/V_B), §4 (P2/P3/P4), §5, §7-3, §9, §11-1/-7.
> Engine/replay (2b/2c): Trail(dist_r), SlFromFill(mirror), sizing_capital, SizingLimits(leverage_range=(10,30),
> liq_fee_on_liq_price=True), exit_at_bar_open hook. All tests synthetic; no real-data execution before the evaluator push.
> 
> ## 2d `backtest/days.py` (strategy-independent, pure)
> - Input: bars (window + 21 warm-up days), fundings. Output: `DayValidity` = {day_index: reasons} and immutable sets
>   V_A, V_B over window days only.
> - A-day d valid ⇔ 1,440 bars with all four mark fields for d AND d−1 AND funding records for d 08:00 and d 16:00.
>   B-day d valid ⇔ A-valid AND 1,440 mark bars on each of d−21..d−2.
> - Funding "present at boundary b" ⇔ exists record with b ≤ funding_ms < b + 60,000 (REST fundingTime can carry ms offsets; same
>   minute-bucket rule the replay uses to settle). CONVENTION ROW.
> - Reasons reported per excluded day: missing_bars_d, missing_bars_prev, missing_funding_08, missing_funding_16, missing_bars_window_B.
> - Days are UTC: day_index = open_ms // 86,400,000 (§1).
> - Tests: synthetic gaps at each position; the §5 example (gap on day X) invalidates X, X+1 (A,B) and B for X+2..X+21.
> 
> ## 2e `strategies/trial02/`
> Files: `anchor.py` (done), `config.py` (bo_v1 values as Decimal: K=0.5, SL_FLOOR=0.0030, SL_CEIL=0.0500, TRAIL_ARM_R=1,
> TRAIL_DIST_R=1, TP_R=2, RISK_PCT=0.01, L=(10,30), E_REF=1000, N_STAT=1000), `strategy.py`, `run.py` (isolated CLI later, 2f/2g).
> Imports nothing from strategies/trial01.
> 
> State per UTC day d (reset at the first bar of d, i.e. the 00:00 bar):
> - O_d = that bar's mark_open, captured BEFORE the bar's completed OHLC is used for crosses.
> - R_{d−1} = max(mark_high) − min(mark_low) over day d−1's bars, accumulated by a per-day accumulator (reset at day boundary);
>   frozen for d. History of daily R kept as dict day_index → R (only complete days are used — invalid days are skipped anyway).
> - Arm B contraction: R_{d−1} < median(R_{d−21}..R_{d−2}) (20 values; numpy-free exact Decimal median: mean of the two middle).
> - Bands U = O_d + k·R_{d−1}, D = O_d − k·R_{d−1} (k = 0.5, or P4 k*_d). Fixed all day.
> - Skip whole day (no crosses evaluated, no consumption bookkeeping beyond reasons): d ∉ V_arm → `invalid_day`(counted separately,
>   outside §7-3 denominator); R_{d−1} < tick → `no_range` (outside denominator); Arm B non-contraction day → `not_contraction`
>   (report only, outside denominator).
> - consumed = {LONG: False, SHORT: False}.
> 
> At each bar close (on_minute_closed; bar i of day d, minute-of-day mm):
> 1 new crosses: LONG if not consumed and mark_high ≥ U; SHORT if not consumed and mark_low ≤ D. Mark each crossing direction consumed.
> 2 both new in same bar → both `conflict_cross`. Else for the single new cross (dir):
> 3 exclusive first-failure order (CONVENTION ROW): `position_busy` (engine position or pending) → `late_cross`
>   (fill_ts = bar close + 1 ms = next open ≥ 23:59:00, i.e. mm ≥ 1438) → `sl_wrong_side` (sl_dist ≤ 0 with m = mark_close) →
>   `sl_dist_out_of_range` (floor / ceiling split) → emit EntryIntent.
>   Engine-side reasons (sl_crossed_before_fill, sizing_rejected, normalization) are read from EntrySkipped (engine SkipReason +
>   SizingDecision.reason: MIN_QTY/MIN_NOTIONAL/step → `normalization`, else `sizing_rejected`).
> - Intent: direction dir, sl = O_d, tp None, tp_rule TpFromFill(level=None, min_r=2, fallback_r=2), trail Trail(arm_r=1, dist_r=1),
>   regime RegimeSizing("trial02_<arm>", 0.01, 10, 30), decided_ms = bar close, decision_mark = m.
> - exit_at_bar_open(bar) ⇔ minute-of-day == 1439 (23:59). The 23:59 bar's on_minute_closed still runs → a first cross there is
>   consumed and recorded `late_cross`.
> - Denominator for §7-3 = first crosses per direction on valid, ranged (and for B: contraction) arm-days.
> 
> P2 (delay k ∈ {1, 5}) — CONVENTION ROW (Codex before-pass #5): at the cross bar i consume + enqueue (dir, i, day d) regardless of
> position; at close of bar i+k: resolve opposing due candidates → `conflict_cross`; then position_busy; then if next open ≥ day d
> 23:59:00 → `dropped` (never carried to next day; uses day d's O_d, R); then price gates with m = mark_close of bar i+k. If bar i+k
> lies beyond day d's 23:58 close the candidate is `dropped` at day d's 23:59 bar close (evaluated no later than that bar).
> P3 (invert): gates in the original direction; intent direction flipped; sl = O_d with sl_rule SlFromFill(O_d, mirror=True);
> tp_rule 2R, trail dist_r 1 (R = |F − O_d| by the mirror identity).
> P4 (draw d = 0..199): per valid, ranged day: rng = Generator(PCG64(SeedSequence([20260924, 4, d, day_index]))); q =
> rng.integers(1, floor(R/tick) + 1) (one call); k* = q·tick/R. no_range and invalid days consume no RNG. Same k* for both bands.
> 
> Invariants (§9) as tests: ① same (O_d, R_{d−1}) histories → same bands; ② perturbing day d's later highs/lows leaves bands unchanged;
> ③ static check over strategies/trial02/*.py: no `.rolling(`, no `deque`, no names containing donchian/channel, no max()/min() over
> bar-window slices (AST: max/min whose argument is a Subscript slice or a generator over a slice); the per-day accumulator is the
> only extreme tracker; ④ after a first cross the direction never triggers again that day.
> §11-7 tests: liquidation/funding order (via engine), 23:59 handling, first-cross consumption, simultaneous crosses, P2 drop at
> fill ≥ 23:59, P4 seed reproduction, B trades ≡ A trades on contraction days (fill, qty, leverage, exits, net_bps).
> Look-ahead tests: perturb d's future bars, R_{d−1}'s day (must change bands), each median member, invalid-day future gaps
> (validity is injected — strategy output for a valid day must not depend on other days' validity), P4 future bars, P2 fill bar.
> 
> Open questions for reviewers:
> Q1 exclusive-failure order position_busy → late_cross → price gates (vs §7-3 list order) — any verdict impact? (report-only)
> Q2 funding presence minute-bucket rule.
> Q3 median exact Decimal vs numpy float — choose Decimal (exact, strict < comparison).
> Q4 Arm B implemented as the same strategy with a day filter (B ⊂ A by construction) — acceptable?

### 설계 r2 변경
> # 2d/2e design r2 — changes vs r1 (after advisor + Codex before-pass)
> 
> C1 (Codex #1) Range history is independent of eligibility: R_d is recorded for EVERY day whose mark grid is complete (exact
>    1,440-minute grid, below), regardless of V_A/V_B, funding, contraction or warm-up. Eligibility (V_A/V_B, no_range, contraction)
>    is applied only when deciding whether day d trades. A day whose mark grid is incomplete has no R_d → the next day (needs R_{d−1})
>    and B days whose median window contains it are invalid — exactly the §1 rule, which already demands those days' grids.
>    Test: funding-only-invalid day X followed by valid X+1 → X+1 trades with R_X.
> C2 (Codex #2) Mark completeness = exactly one bar at each aligned minute start 00:00..23:59 of the UTC day (open_ms % 60,000 == 0,
>    no duplicates), all four mark fields present and finite Decimals. Tests: duplicate + gap (count 1,440), misaligned ts,
>    missing/non-finite mark field.
> C3 (Codex #3) Mark source independence: the prepared bar list is the union of archive rows and REST (kline ∩ mark). Pre-run data
>    check (run in the post-push validity pass, before any strategy run): for the window + warm-up, fetch-free comparison is not
>    possible for archive rows, so the check is: every archive row used has non-empty mark fields (load_archive already drops rows
>    without mark) AND for REST-filled ranges the count of mark-kline minutes lacking a last-price kline is reported; must be 0,
>    otherwise STOP → correction doc (mark-only minutes would need a mark-only bar path). Recorded in the validity report.
> C4 (Codex #4) 23:59 bar: the strategy does NOT inspect its high/low (no cross detection, no consumption, no late_cross). The last
>    evaluable cross bar is 23:58: its first cross is consumed and recorded late_cross (fill would be 23:59). Cross at 23:57 → fill
>    23:58 is the last legal entry. §7-3 denominator excludes 23:59 bars. (Replay still calls on_minute_closed for the hook bar;
>    the strategy returns None there.)
> C5 (Codex Q2) Funding validity per boundary b ∈ {08:00, 16:00} of d: exactly one record with b ≤ funding_ms < b+60,000 and
>    parseable rate & mark; zero or ≥2 → d invalid (missing_funding_* / duplicate_funding_*).
> C6 (Codex tests) EntrySkipped → §7-3 mapping via replay on_event (SizingDecision.reason: normalization set = MIN_QTY / MIN_NOTIONAL /
>    STEP-related RejectReasons; others sizing_rejected). Default replay decision records unchanged (no golden change).
>    Tick source = registry #36 snapshot only (strategies/trial02 loads rules from anchor.RULES_SNAPSHOT_DIR, verifying SHA256).
>    Added boundary tests: 23:57/23:58/23:59, 00:00 cross, opposite entry after same-day exit, busy-consumed, P2 simultaneous
>    sources and due ≥ 23:59 drop, P3 mirror both directions.
> C7 (advisor #1) conflict_cross only when both directions are unconsumed and first-cross in the same bar; convention row 7.
> C8 (advisor #2) warm-up days: R only, no intents, no denominator; O_d only from the day's 00:00 bar (else day already invalid).
> C9 (advisor #3) placebos P1–P4 run on Arm A only.
> C10 (advisor #4) invalid-day leak test: perturb bar contents of an invalid-for-trading day X (grid kept complete so R_X exists and IS
>    used, or grid incomplete so R_X absent) → assert valid days' outputs change only through R_X per C1, never through X's intraday
>    path otherwise.

### advisor 원문(verbatim)
> **1. One trade-affecting ambiguity the brief treats as settled — pin it.** §1 row 36 "한 봉에서 롱·숏 교차가 **동시에** 서면". Your rule: conflict only if *both* directions are fresh (unconsumed) in that bar; if LONG was already consumed, a wide bar hitting both bands yields a plain SHORT setup. The other reading (bar touches both bands → conflict regardless) kills more setups → different trades. Your reading follows row 35 ("방향별 첫 교차 하나만 셋업" — no setup, no conflict), but it's a convention row + test, not implicit. Raise with Codex.
> **2. Warm-up suppression is missing from the brief.** Strategy needs `trade_from_day_index`; warm-up days accumulate R (and feed B's median) but emit no intents and count in no denominator. Also state: O_d is defined only when the day's first bar *is* the 00:00 bar — otherwise the day is already invalid, but say so.
> **3. Placebos are Arm A only** (§4 "원판 = Arm A · IS"). P2/P3/P4 never run under the B filter. Say it.
> **4. Invalid-day test — rephrase to what you actually want:** perturb bar *contents* of an invalid day X (keep it invalid) → every valid arm-day's trades byte-identical. That's the property that makes "partial R_X never leaks" true.
> **5. Q1–Q4:** Q1 no verdict impact (order changes only the recorded reason; every gate must pass for an intent). Q2 minute-bucket rule = the replay's settlement rule — one row. Q3 Decimal, yes. Q4 yes, B ⊂ A structurally (fixed capital + no cross-day positions → each day independent); keep the separate B run *and* the equality test — the test is the deliverable. Equality set = days ∈ V_B ∧ contraction.
> **6. P3 placeholder check:** `sl = O_d` sits on the wrong side for the inverted direction. `request_entry` validates TP side only (confirmed), `_execute_entry` uses the resolved SL′ — fine, but grep `db/record.py` and `ReplayContext` for any SL-side assumption on `intent.sl` before relying on it.
> **7. Arithmetic spot-checks pass:** late_cross at mm ≥ 1438 (cross 23:57 → fill 23:58 is the last legal); §5's B-invalid range X+2..X+21 = 08-14..09-02 ✓; median strict `<` ✓; P4 `integers(1, ⌊R/tick⌋+1)` ✓; trail R under mirror = |F−(2F−O_d)| = R ✓.
> **Process:** start `scratchpad/2i_conventions.md` now (rows owed: fee basis, sl == anchor placeholder, P2 queue, item 1, funding bucket, failure order, P4 draw, Decimal median, warm-up, static-check scope, bootstrap table). Surface the fee-basis call to the user in the next status report as a disclosed decision (§1 row 46; #2 doesn't specify the basis). No blocker on the design itself.

### Codex 원문(verbatim · task-mufjq08e-jiwk3t)
> ## Before-pass findings
> 
> 1. **BLOCKER — range history is coupled to trading eligibility.** The design says invalid days are skipped, but a day can have all 1,440 mark bars and be invalid only because its funding record is missing. Its range is still required by the next A day and by later B median windows. Skipping that range can remove valid trades and change the verdict. **Fix:** accumulate and retain `R_d` for every complete mark day, independently of `V_A`, `V_B`, funding validity, and contraction. Apply eligibility only when deciding whether to trade on day `d`. Test a funding-only invalid day followed by a valid day. [Binding rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30)
> 
> 2. **BLOCKER — “1,440 bars” needs an exact UTC grid check.** A count of 1,440 can hide a duplicate minute and a missing minute. **Fix:** require exactly one bar at each aligned minute start from 00:00 through 23:59, with all four finite mark fields. Test duplicate-plus-gap, misaligned timestamps, and missing fields. This directly controls `V_A`, `V_B`, trades, and the statistical sample. [Binding rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30)
> 
> 3. **BLOCKER — the current data loader can make mark eligibility depend on kline availability.** REST loading keeps only timestamps present in *both* last-price klines and mark klines. A missing last-price kline could therefore make a complete mark day appear invalid, although §1 requires mark completeness. **Fix:** give `days.py` a mark-completeness source independent of that intersection, or establish and test that the prepared input preserves every available mark minute. [Loader](/home/cms/project/BTC_Futures_E2E/backtest/data.py:145) · [Binding rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30)
> 
> 4. **Binding-text conflict — 23:59 cross accounting.** The design evaluates that bar’s high/low to record a new `late_cross`; §1 and §11 say the 23:59 bar’s high/low are used for no judgment. This changes the §7-3 denominator, though it cannot create a trade. **Fix:** do not inspect 23:59 high/low for crosses. A first cross at 23:58 is consumed as `late_cross` because its next open is 23:59. Record this interpretation in the pre-run convention row. [§1 time exit](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:44) · [§11-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:204)
> 
> ## Look-ahead
> 
> The bands and contraction test use only completed prior days; the delayed P2 gate uses the delayed bar’s close; and the P4 draw uses prior range. I found no strategy-price look-ahead in those rules. Whole-day validity does use later completeness to exclude an earlier signal, but that retrospective eligibility is expressly required for the backtest; it must not be reused as a forward-paper decision rule. [§1 completeness](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30) · [§5 forward rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:143)
> 
> ## Q1–Q4
> 
> | Question | Review decision |
> |---|---|
> | **Q1 failure order** | Accept the proposed exclusive order as a **reporting convention**. It should not change execution. Pin one reason per first cross, including engine rejection at the next open. |
> | **Q2 funding bucket** | Accept the replay’s `[boundary, boundary + 60,000)` bucket, with **exactly one usable confirmed rate and mark per boundary**. Reject missing or conflicting duplicates rather than settling two records. The replay currently settles every record in a minute, so an existence-only validity test is insufficient. [Replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:75) |
> | **Q3 median** | Accept exact `Decimal` median of the middle two of 20 values and strict `<`. Pin equality and near-equality tests. [§1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:49) |
> | **Q4 B filter** | Accept one strategy with a B day filter, provided both arms use the same complete-day range history and B’s trades on eligible contraction days match A’s fills and outcomes. Use `V_B` for the A/B policy comparison. [§3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:107) |
> 
> ## Tests and convention rows to add
> 
> - Pin the base strategy’s 23:57, 23:58, and 23:59 boundary behavior; a 00:00 cross; opposite-direction entry after a same-day exit; and a first cross while busy that stays consumed.
> - Pin P2 simultaneous source crosses, delayed gates, and drops when the due bar is 23:59 or later. Pin P3’s mirrored SL, fill-derived R, TP, and trail in both directions.
> - Pin the `EntrySkipped` mapping. The replay decision record currently omits `SizingDecision.reason`, which is needed to distinguish `normalization` from other `sizing_rejected` cases; capture the event through `on_event` or preserve that reason in the replay record. [Replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:105) · [§7-3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:179)
> - Pin the tick’s source to registry #36’s single snapshot, with no fixture fallback. [Registry #36](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:44)
> 
> **VERDICT: FIX-PLAN-FIRST.** The range-history and mark-completeness issues can change trades and verdicts; the 23:59 rule also needs a binding-consistent convention before implementation.
> 
> Codex session ID: 01a0d386-741a-7341-8660-f30704b48ca0
> Resume in Codex: codex resume 01a0d386-741a-7341-8660-f30704b48ca0

## 2026-09-24 — 2d·2e 설계 r2 재확인(Codex task-mufjw1kz-dmtf39 **FIX-PLAN-FIRST**) → 설계 r3(원시 출처 감사)
- #1·#4 CLOSED · #2·#3 PARTIAL(로더가 병합·중복 제거·교집합 **뒤**만 보인다) · C5 새 항목(펀딩 중복 제거 전 검사 · 유한값) → ✅ 전부 동의 → C11~C13.

### 설계 r3 변경
> # 2d/2e design r3 — raw-source audit (Codex r2: #2 PARTIAL, #3 PARTIAL, C5 new)
> 
> C11 New additive module `backtest/source_audit.py` (no change to existing loaders or prepared files) that reads the RAW sources
>     **before** any merge/dedup/intersection, for window + 21 warm-up days:
>     - archive CSV rows in range: per open_ms count (duplicates), rows with empty/non-finite mark fields, misaligned timestamps;
>     - REST `klines` and `markPriceKlines` pages for the REST-filled ranges, kept separately: duplicate open_ms within each source,
>       mark-only minutes (mark present, kline absent), kline-only minutes, misaligned timestamps;
>     - REST `fundingRate` records: per funding_ms duplicates, per boundary-minute-bucket count, non-finite rate/mark.
>     Output = `source_audit.json` (counts + the offending timestamps), written in the post-push validity pass.
> C12 STOP rule (pre-registered here, before any data is read): if the audit reports ANY of — duplicate open_ms with differing
>     mark values, mark-only minutes in the window/warm-up, duplicate or conflicting funding at an 08:00/16:00 boundary of a window
>     day, non-finite mark/rate — then no strategy run starts; the finding goes to the user as a correction doc + registry row.
>     Exact duplicate rows (identical values) are reported and collapsed (not a stop). Kline-only minutes (mark absent) are reported
>     only — those minutes are mark-missing and already make the day invalid under C2.
> C13 `days.py` computes V_A/V_B from the prepared bars (C2 grid) AND the funding list, and additionally takes the audit's per-day
>     flags: a day touched by a (non-stop) exact-duplicate collapse stays valid; any day flagged by C12 cannot exist because the
>     run stops. Funding "exactly one" (C5) is evaluated on the RAW funding records from the audit, not the deduplicated list.
>     Finite = Decimal.is_finite() for rate and mark.
> Tests (synthetic, fake client + temp archive CSV): each C11 category detected, C12 stop conditions raise, exact duplicates collapse
> with report, audit never mutates inputs.

### Codex 원문(verbatim · task-mufjw1kz-dmtf39)
> | Before-pass blocker | Status | Narrow re-check |
> |---|---|---|
> | 1. Range history tied to eligibility | **CLOSED** | C1 retains `R_d` for every complete mark day, including a funding-invalid day, and tests its use on the next day. |
> | 2. Exact UTC mark grid | **PARTIAL** | C2 defines the right check, but the current loader removes duplicate timestamps before `days.py` can see them. A prepared 1,440-minute grid could therefore pass after conflicting source rows were collapsed. Check duplicates before that merge. [data.py](/home/cms/project/BTC_Futures_E2E/backtest/data.py:145) |
> | 3. Mark availability independent of kline availability | **PARTIAL** | C3’s stop rule is appropriate. The current REST loader discards mark-only minutes at the intersection, so the proposed post-push count cannot be recovered from prepared bars. Specify how the pre-intersection count is retained and checked before a strategy run. [data.py](/home/cms/project/BTC_Futures_E2E/backtest/data.py:145) |
> | 4. 23:59 cross accounting | **CLOSED** | C4 excludes that bar’s high/low and its crosses, while preserving `late_cross` at 23:58. This matches the time-exit rule. [preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:44) |
> 
> **New verdict-relevant issue in C5:** “Exactly one” funding record must be checked before `fetch_funding` deduplicates equal timestamps; otherwise conflicting records can become one apparently valid record. Require finite rate and mark values as well as parseable ones. [data.py](/home/cms/project/BTC_Futures_E2E/backtest/data.py:159)
> 
> The remaining C1–C10 changes raise no further verdict-relevant ambiguity in this narrow review. No market data or `var/` was accessed.
> 
> **VERDICT: FIX-PLAN-FIRST.** Pin the raw-source checks and their retained diagnostics before implementing the validity pass.
> 
> Codex session ID: 01a0d38a-c069-7f03-86c7-696b5773d05e
> Resume in Codex: codex resume 01a0d38a-c069-7f03-86c7-696b5773d05e

## 2026-09-24 — 2d·2e 설계 r3 재확인(Codex task-mufjysw7-3ni97c **FIX-PLAN-FIRST**) → 설계 r4(한 번 캡처 → 감사 → 빌드)
- #2·#3·C5 PARTIAL: 감사가 **실제 준비 입력**과 묶이지 않음 → ✅ 동의 → 트라이얼 #1 parquet 재사용 안 함 · 원시 캡처 하나에서 감사와 빌드를 순수 함수로 · 매니페스트 해시.

### 설계 r4 변경
> # 2d/2e design r4 — single capture → audit → build (replaces C11–C13's separate read)
> 
> C14 Trial #2 does NOT reuse trial #1's prepared parquet. New `backtest/prepare_t2.py`, one deterministic pipeline, run once in the
>     post-push validity pass (window = IS + 21 warm-up days; OOS never):
>     1 Read RAW archive rows for the range (every CSV row, unfiltered) → `raw/archive_rows.jsonl` (+ SHA256).
>     2 Fill ranges = every aligned minute in range with no archive row OR an archive row whose mark fields are empty/unparseable/
>       non-finite (Codex: include rows the old loader skipped). Recorded in `raw/fill_ranges.json`.
>     3 Fetch REST `klines` and `markPriceKlines` for exactly those fill ranges and `fundingRate` for the full range; store every
>       response page verbatim → `raw/rest_klines.jsonl`, `raw/rest_mark.jsonl`, `raw/funding.jsonl` (+ SHA256 each).
>     4 Audit = pure function of the raw files only → `source_audit.json`.
>     5 Build = pure function of the SAME raw files only → `bars_1m.parquet`, `funding.json`. No network in 4–5.
>     6 `manifest.json` = SHA256 of every raw file, audit, and prepared output + code commit. The strategy run and evaluator verify the
>       manifest hashes of the prepared inputs they read (mismatch → stop). Re-running 4–5 on the raw files must reproduce the
>       prepared hashes (test + a verify command).
> C15 Build rules (deterministic): per minute, archive row wins if its mark fields are valid and its kline fields present; else REST
>     (mark from markPriceKlines, kline from klines). A minute with valid mark but no kline in any source → C12 STOP (mark-only).
>     Exact duplicate rows collapse; differing duplicates → STOP. Funding list = raw funding records, one per funding_ms after exact
>     duplicate collapse; differing duplicates → STOP.
> C16 Value classification for mark/rate fields: `empty` (missing or ""), `unparseable` (Decimal() raises), `non_finite`
>     (NaN/Inf), `ok`. Only `ok` counts as present. Funding validity for boundary b of window day d = exactly one `ok` record
>     (rate and mark both ok) in [b, b+60,000); zero → day invalid (missing_funding); differing duplicates → STOP (C12).
> C12 (unchanged) stop list, now evaluated on the raw capture: differing duplicate bars or funding, mark-only minutes, non-ok mark in
>     a row that the build would select.
> Tests (synthetic raw files + fake client): capture writes pages verbatim; audit and build are pure and reproducible; every C12
> condition stops; archive rows with empty mark trigger REST fill; manifest mismatch stops a consumer.

### Codex 원문(verbatim · task-mufjysw7-3ni97c)
> | r2 item | r3 status | Reason |
> |---|---|---|
> | #2 Exact UTC mark grid | **PARTIAL** | C11 can see duplicates before the loaders collapse them, and C2 checks the prepared grid. The design does not yet establish that the audited rows are the rows used in the prepared bars. |
> | #3 Mark availability independent of klines | **PARTIAL** | Separate REST pages expose mark-only minutes before the [intersection](/home/cms/project/BTC_Futures_E2E/backtest/data.py:145). The audit still needs to cover the exact REST fill ranges used for preparation. |
> | C5 Funding cardinality and finite values | **PARTIAL** | Checking raw records fixes visibility lost at [funding deduplication](/home/cms/project/BTC_Futures_E2E/backtest/data.py:159). The plan still needs to bind those records to the funding list used by replay and classify empty or unparseable values explicitly; `Decimal.is_finite()` alone does not do that. |
> 
> **New verdict-relevant ambiguity in C11–C13:** C11 describes a separate post-push raw-source read, while the existing [preparation path](/home/cms/project/BTC_Futures_E2E/backtest/prepare.py:42) creates bars and funding through separate loader calls. A clean later audit could therefore approve a prepared artifact made from different REST responses. Pin how the audit verifies the *actual prepared input*: use the same captured raw responses, or compare the audit’s selected values, timestamps, and fill ranges against the prepared bars and funding, stopping on any mismatch. Fill ranges must include archive rows skipped for empty mark fields ([loader behavior](/home/cms/project/BTC_Futures_E2E/backtest/data.py:111)).
> 
> This is a design review only; I did not access `var/` or market data.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0d38c-b738-7cb1-b52b-7fd50f4970a7
> Resume in Codex: codex resume 01a0d38c-b738-7cb1-b52b-7fd50f4970a7

## 2026-09-24 — 2d·2e 설계 r4 재확인(Codex task-mufk28j6-yh83k0 **FIX-PLAN-FIRST**) → 설계 r5
- #2 CLOSED · #3 PARTIAL(archive mark 있음 + kline 없음 경로) · C5 PARTIAL(버킷 카디널리티) → ✅ 동의 → C17(분마다 출처 하나 · 혼합 없음) · C18(버킷 규칙).

### 설계 r5 변경
> # 2d/2e design r5 — fill ranges and funding buckets (Codex r4: #3 PARTIAL, C5 PARTIAL)
> 
> C17 (replaces C14 step 2 and C15's source rule) A minute's bar comes WHOLLY from one source — no archive/REST mixing.
>     "Complete usable archive bar" = exactly one archive row (after exact-duplicate collapse) whose 4 mark fields AND 4 kline OHLC
>     fields (+ volume fields) are all `ok`. Fill ranges = every aligned minute in range WITHOUT a complete usable archive bar.
>     For each fill minute the REST pair is used: kline from `klines`, mark from `markPriceKlines`, both `ok` required.
>     Outcomes per fill minute: both present+ok → REST bar; mark ok but kline absent/non-ok in REST → STOP (mark-only);
>     mark absent in REST (whatever the archive had) → minute missing (C2 makes its day invalid; the archive's mark-without-kline,
>     if any, is reported but never used). Tests: archive row with valid mark + empty kline → fetched; REST pair complete → REST bar;
>     REST mark-only → stop; nothing anywhere → missing.
> C18 (replaces C16's funding clause) Funding bucket = [b, b+60,000) for every minute b that contains ≥1 raw funding record (any time
>     of day). Raw cardinality is counted over ALL records in the bucket (ok or malformed) BEFORE any exclusion:
>     - 1 record, ok → one funding event;
>     - ≥2 records, all byte-identical (same fundingTime, rate, mark strings) → collapse to one event (reported);
>     - ≥2 records otherwise (different timestamps or values in one minute) → STOP;
>     - any record in the bucket not ok (rate or mark empty/unparseable/non-finite) → STOP.
>     `funding.json` = exactly the validated events (one per bucket, the record's own fundingTime/rate/mark). Replay settles only
>     these. Window day d is A-valid only if the buckets starting at d 08:00 and d 16:00 each yield one event (a bucket with no
>     record → day invalid, missing_funding_08/16).
> Tests: each bucket case above; replay receives only validated events.

### Codex 원문(verbatim · task-mufk28j6-yh83k0)
> | Item | r4 status | Finding |
> |---|---|---|
> | #2 Exact UTC mark grid | **CLOSED in the design** | Audit and build use the same raw capture; differing duplicate bars stop, and C2 checks the prepared grid. |
> | #3 Mark availability | **PARTIAL** | [C14](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4982) does not fetch REST when an archive row has valid mark fields but lacks kline fields. [C15](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4991) then calls for a stop if no kline exists *in any source*, although REST was never checked. Define fill ranges using complete usable archive bars, and pin whether an archive kline may pair with a REST mark. |
> | C5 Funding | **PARTIAL** | [C16](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4995) counts `ok` records but gives no outcome for two records at different timestamps in one boundary bucket, or one `ok` plus one malformed record. [C15](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4993) still puts raw records into `funding.json`; [replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:77) settles every record it encounters. Check bucket cardinality before excluding malformed values, and specify exactly which validated events reach replay. |
> 
> Add synthetic cases for those archive fallback and funding bucket combinations. This was a read-only design review; I accessed neither `var/` nor market data.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0d38f-2937-7d13-952d-468860c25eb5
> Resume in Codex: codex resume 01a0d38f-2937-7d13-952d-468860c25eb5

## 2026-09-24 — 2d·2e 설계 r5 재확인(Codex task-mufk4l7w-xcyeze **FIX-PLAN-FIRST**) → 설계 r6
- #3·C5 CLOSED · 새 고정 2건 → ✅ 동의 → C19(출처 품질 규칙 · mark-only 중단은 REST에만) · C20(08/16 격자 밖 펀딩 → 중단).

### 설계 r6 변경
> # 2d/2e design r6 — two pins (Codex r5)
> 
> C19 Source-quality rules, per aligned minute in range:
>     - Archive: a row that is not a complete usable bar (any mark or kline field not `ok`, or missing) is simply NOT USED → the
>       minute goes to REST fill. Archive mark-without-kline is reported, never used, never a stop.
>     - REST (fill minutes only): a row PRESENT in `klines` or `markPriceKlines` with any non-`ok` field → STOP (malformed exchange
>       response is not "absence"). Mark row ok + kline row absent → STOP (mark-only; C12's mark-only rule applies ONLY here).
>       Mark row absent → minute missing (day invalid under C2), whatever the archive had.
> C20 Funding events must lie on the 8h grid: every validated event's bucket must start at 00:00, 08:00 or 16:00 UTC. Any validated
>     event at another time → STOP (the preregistration §1 funding row covers only 08:00/16:00 while holding; 00:00 is never held
>     because every position exits at 23:59). Replay therefore can only ever settle 08:00/16:00 events; 00:00 events reach replay but
>     no position is open then (assert in the strategy run: no FundingSettled at 00:00).

### Codex 원문(verbatim · task-mufk4l7w-xcyeze)
> **r5 closes the two r4 findings in the design.** C17 fetches REST whenever the archive lacks a complete usable bar and keeps each minute’s bar within one source. C18 checks raw funding bucket cardinality before exclusion and sends only validated events to replay.
> 
> Two verdict-relevant rules still need to be pinned:
> 
> - **Archive mark-only outcome:** C17 says an archive mark without a kline becomes a missing minute if REST has no mark, while the retained C12 rule says mark-only minutes stop the run. Specify whether C12 applies only to REST fill pairs. Also state whether a REST mark row with non-`ok` fields counts as absent or causes a stop. [C12](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4998) · [C17](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:5025)
> - **Funding outside 08:00/16:00:** C18 validates buckets at any time and puts every validated event into the replay input. A 12:00 event would therefore settle during an open position, although the preregistered funding rule specifies 08:00 and 16:00. Specify whether such an event stops the run or is settled, and align the preregistration if settlement is intended. [C18](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:5033) · [preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:51)
> 
> Read-only design review; no `var/` or market data accessed.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0d390-d5c5-78c2-9522-a89dc6f38776
> Resume in Codex: codex resume 01a0d390-d5c5-78c2-9522-a89dc6f38776

## 2026-09-24 — 2d·2e 설계 r6 재확인(Codex task-mufk7a1b-k2gdge) **PROCEED**
- C19·C20 해결 · 전체 설계(r1 + C1~C20) 구현 준비 완료.
- 구현 메모(Codex): 재생이 `on_funding` 이벤트를 버린다 → ◐ 방법 변경: 기본 재생의 `on_event` 흐름을 바꾸면 무훅 골든이 깨지므로, 트라이얼 #2 실행에서 **23:59 청산 뒤 포지션 없음**을 매일 단언(펀딩은 포지션이 있을 때만 정산 → 00:00 정산 불가를 같은 강도로 보장).

### Codex 원문(verbatim · task-mufk7a1b-k2gdge)
> C19 resolves the source-quality pin: incomplete archive rows go to REST fill, while malformed REST rows stop the run. C20 resolves the funding pin: validated events outside the 00:00/08:00/16:00 UTC grid stop before replay. I found no new verdict-relevant ambiguity in either clause. The complete r1 + C1–C20 design is ready to implement.
> 
> One implementation detail needs care: [replay currently discards the events returned by `on_funding`](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:77). Expose or capture those events so C20’s “no `FundingSettled` at 00:00” assertion is meaningful.
> 
> VERDICT: PROCEED
> 
> Codex session ID: 01a0d392-bffd-7363-b069-2c996b308ba7
> Resume in Codex: codex resume 01a0d392-bffd-7363-b069-2c996b308ba7

## 2026-09-24 — 트라이얼 #2 단계 2d·2e 구현(3bf0705 · 이 커밋)
- 2d: `backtest/prepare_t2.py`(원시 캡처 → 순수 감사·빌드 → 매니페스트 · 중단 규칙 C12·C18~C20) · `backtest/days.py`(정확한 mark 격자 · V_A/V_B).
- 2e: `strategies/trial02/config.py`(bo_v1 값) · `strategy.py`(설계 r1 + C1~C20 · 규약 초안 7·8·10~14).
- **TDD 이탈(공개)**: `prepare_t2.py`는 테스트보다 먼저 썼다 → 보완으로 돌연변이 검사(규칙 5개를 하나씩 깨서 테스트가 모두 잡는지) — 5/5 잡음. `days.py`·전략은 테스트 먼저.
- 전략 돌연변이 검사: 10개 중 9개 잡음 · 1개(23:59 봉 관측)는 동등 돌연변이(그 봉은 앞에서 먼저 돌아간다) · 처음 놓친 2개(sl_dist 경계 · 중앙값 창)는 경계 테스트를 더해 잡음.
- 보고할 구조 사실: 기본 전략에서 `position_busy`는 생기지 않는다 — 반대 띠 교차는 O_d(= SL)를 지나므로 같은 봉 `on_bar`가 먼저 SL 청산(테스트로 고정) · P2 지연 결정에서만 가능.

## 2026-09-24 — 트라이얼 #2 2d·2e **after-pass**(advisor + Codex task-mufknjra-35c5c1 **FIX-FIRST**) → 수정
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 | ✅ | 새 날 첫 봉 가드(포지션·대기 진입) + 테스트(가드 없는 코드에서 실패 확인) |
| advisor | 2 | ✅ | 동등성 테스트 2개(합성 봉 · prepare_t2 빌드 경유) |
| advisor | 3 | ✅ | `strategies/trial02/harness.py` `run_t2` — §7-3 결합 + 규칙 해시 검증(Codex #1·#4와 같음) |
| advisor | 4·5·6 | ✅ | 규약 초안 17~24 · 2 공시 |
| advisor | 7 | ✅ | 이 단계 뒤 사용자 보고 |
| Codex | 1 | ✅ | `harness.load_rules` = #36 파일 4개 SHA256 대조(불일치 → 중단 · 대체 없음) · tick·limits·E_ref를 호출자가 줄 수 없게 `run_t2`에 고정 |
| Codex | 2 | ✅ | `verify_rebuild`(임시 디렉터리에서 원시로 다시 빌드 → 산출물 해시 대조 · 덮어쓰지 않음) · `load_prepared`가 호출 + `pinned_raw`(레지스트리에 고정할 원시 해시) · `expect_range`(IS + 21일만) · CLI `--rebuild-only` 삭제 → `--verify` · 이미 준비된 출력이면 재캡처 거부 · REST 어긋난 시각 보고 |
| Codex | 3 | ✅ | 전략 누적기: 중복 분 → ValueError(days.py와 같은 규칙) · days.funding_boundaries: 버킷 중복·비유한 → ValueError · 교차 모듈 테스트 |
| Codex | 4 | ✅ | C6 결합(`run_t2`) · 테스트: C10 경로 교란 · 중앙값 창 경계 · P2 체결 봉 교란 · C20(00:00 펀딩 무정산 · 08:00 정산) · 매핑 |
| Codex | C13 | ◐ | C13(감사 플래그를 days 입력으로)은 C14·C15의 중단 규칙으로 대체됨 — 중단 조건이 있으면 준비 산출물 자체가 없다 |

### advisor 원문(verbatim)
> **1. Strategy has no guard against a position surviving into a new day.** The only assert is at minute 1439. If a trade day's 23:59 bar were absent (impossible via V_A, but `trade_days` is an injected set — a wrong set is exactly the failure mode), the hook never fires, the position carries into d+1, and `_gate` silently reports `position_busy` all day. Pass `ctx` into `_new_day` and assert `ctx.engine.position is None and ctx.engine.pending is None`. One test: complete history + trade day with bar 1439 dropped, `trade_days={D0}` forced → must raise, not trade.
> **2. Codex asked "days.py vs strategy completeness — identical?" — answer it with a test, not prose.** Same synthetic bars (gap day, NaN-mark day, misaligned bar, funding-only-invalid day) → `set(strategy.ranges) == complete_mark_days(bars) − {last_day}`.
> **3. §7-3 exclusive reason is half-implemented and lives nowhere yet.** The join is run.py's job (C6). Write it into the 2f scope now. Same for tick source: run.py must load from `anchor.RULES_SNAPSHOT_DIR` and verify the four SHA256s.
> **4. Position_busy claim — agree, with the precise reason for the log:** opposite band D < O_d = initial SL, trail only tightens toward profit, engine order in `on_bar` is fill → liq → SL → TP, so any bar reaching the opposite band has already closed the position before `on_minute_closed`. Reachable in P2 (tested). `pending` in `has_position` is dead in the base path for the same reason. Say both in the convention row.
> **5. P3 disclosure for convention #2:** mirroring about the inverted fill makes R_inv = R_orig − 2·slippage (~4 bps). State it once.
> **6. Conventions draft is behind the design.** Add C2, C1, C4, C12/C15/C17/C19, C18/C20, items 4–5.
> **7. Status report to the user is overdue.** Include the fee-basis decision (§1 row 46 over #2's unspecified basis, opt-in flag, default path untouched), the TDD deviation on prepare_t2 with the mutation result, and what's next. Send it after Codex returns.
> **Procedure:** don't touch 2f until Codex returns. If FIX-FIRST → fix, full suite + goldens, narrow re-check, then 2f.

### Codex 원문(verbatim · task-mufknjra-35c5c1)
> ## Findings
> 
> 1. **BLOCKER — the runtime tick and rules are not pinned.** [Trial02](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:95) accepts any `tick`, and the [test fixture](/home/cms/project/BTC_Futures_E2E/tests/test_trial02_strategy.py:28) loads the snapshot without checking its SHA256; [the loader](/home/cms/project/BTC_Futures_E2E/exchange/loader.py:101) performs no hash check either. C6 and [§11-6](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:210) require the anchored snapshot. A different tick changes the no-range guard, P4 draws, bands, and trades. The fixed sizing capital is likewise a caller argument to [replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:65), not enforced by the strategy’s otherwise correct [intent fields](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:237). The later runner must pin and verify both before any run.
> 
> 2. **BLOCKER — raw-to-prepared verification is incomplete.** [verify_manifest](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:334) checks each file against hashes in the same mutable manifest; it does not rebuild from raw and compare prepared hashes. [`--rebuild-only`](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:349) overwrites the outputs and manifest instead of performing C14’s promised verification. A changed prepared bar plus an updated manifest can therefore pass while the raw capture is unchanged. The same CLI also accepts an arbitrary raw window in rebuild mode, bypassing C14’s [IS-only boundary](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4979). This is an audit/build divergence and a binding staging gap.
> 
> 3. **The two completeness definitions are not identical.** [days.py](/home/cms/project/BTC_Futures_E2E/backtest/days.py:33) rejects duplicate `open_ms`; the strategy’s [_DayAcc](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:63) puts duplicate minutes in a set and can include their highs and lows in `R_d`. [days.py’s funding check](/home/cms/project/BTC_Futures_E2E/backtest/days.py:49) also reduces events to a presence set, so it cannot itself enforce C5’s cardinality or finite values. The current prepared path collapses exact bar duplicates and validates funding first, which contains these differences **if every caller uses verified prepared input**. Add a cross-module test and make that dependency enforceable.
> 
> 4. **C6 reporting and several specified tests are missing.** The strategy [records an intent](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:237) but never reconciles it with `EntrySkipped`; [replay decisions](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:105) omit `SizingDecision.reason`. Thus §7-3 cannot distinguish `normalization` from other `sizing_rejected` cases as C6 requires. The permitted test files also lack the C10 invalid-day path perturbation, prior-range and each-median-member look-ahead checks, P2 fill-bar perturbation, and C20’s no-00:00-`FundingSettled` assertion. These are required coverage gaps; I found no price look-ahead in the implemented band, gate, or delay calculations.
> 
> ## C1–C20 check
> 
> | Clauses | Result |
> |---|---|
> | C1–C2 | Range is retained independently of trade eligibility at [day rollover](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:148); exact grids are checked in [days.py](/home/cms/project/BTC_Futures_E2E/backtest/days.py:33). Strategy duplicate handling differs as noted above. |
> | C3–C5 | Separate REST mark/kline capture and mark-only stop are in [prepare_t2](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:174); 23:59 crosses are excluded at [line 129](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:129); funding validation is in [_funding](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:217). |
> | C6–C10 | Fresh-only conflict, warm-up suppression through injected trade days, and A-only implemented variants are at [strategy lines 45–49](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:45), [158–160](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:158), and [190–207](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:190). C6 is incomplete; C10’s specified test is absent. |
> | C11–C16 | Superseded raw-capture rules are mainly implemented by [capture/analyze](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:166). C14 verification is incomplete. C13’s audit flags are not an input to [validity](/home/cms/project/BTC_Futures_E2E/backtest/days.py:68). REST rows outside an aligned fill timestamp are silently ignored at [_rest_rows](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:194), so C11’s misaligned REST timestamp category is not reported. |
> | C17–C20 | Single-source fill and REST stop rules are at [analyze](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:259); raw funding bucket cardinality and off-grid stop are at [_funding](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:227). C20’s replay assertion is absent. |
> 
> The disclosed **`position_busy` structural fact is correct for the base strategy**: an opposite-band cross passes the open-anchored SL, and replay processes that bar’s exit before the strategy checks the cross ([replay order](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:83), [gate](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:225)). P2 can reach `position_busy`, as its delayed candidate is checked later.
> 
> **Tests:** I attempted the three permitted files with the project virtualenv and cache disabled. Pytest could not start because the read-only environment has no writable temporary directory; no test result is claimed.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0d39e-552f-71d0-bb74-60cb2435c174
> Resume in Codex: codex resume 01a0d39e-552f-71d0-bb74-60cb2435c174

## 2026-09-24 — 2d·2e 재확인 r2(Codex task-mufl2dox-hk6p0f **FIX-FIRST**) → 수정
| # | Codex | 입장 | 반영 |
|---|---|---|---|
| 1 | CLOSED | — | — |
| 2 | PARTIAL — 판정 경로가 출처 고정을 강제하지 않음 | ✅ | `load_prepared`의 `pinned_raw`·`expect_range` 필수 · 판정 입구 `harness.run_prepared_is`(IS + 21일 고정 · 원시 해시 고정 필수 · 다시 빌드 대조 · V_A/V_B 계산) · 합성 캡처로 거부/통과 테스트 |
| 3 | CLOSED | — | — |
| 4 | PARTIAL — 중앙값 구성원 · C20 이벤트 | ✅ | 날마다 다른 범위로 중앙값 = 창 20개의 Decimal 중앙값(d−1·d−22 제외) · 엔진 `on_funding` 반환 이벤트를 직접 관찰 — 00:00 FundingSettled 없음 |
| C13 | 대체 수용 | — | — |
| 새 | 날 경계 가드가 00:00 봉 엔진 처리 뒤 | ✅ | 가드를 `exit_at_bar_open`(재생이 봉 처리 **전**에 부름)으로 이동 · 00:00 봉이 SL을 치는 경우 포함 테스트(이전 위치 코드에서 실패 확인) |

### Codex 원문(verbatim · task-mufl2dox-hk6p0f)
> ## Narrow re-check
> 
> | Item | Status | Result |
> |---|---|---|
> | 1. Rules, tick, and sizing pins | **CLOSED** | [The harness](/home/cms/project/BTC_Futures_E2E/strategies/trial02/harness.py:37) checks all four #36 snapshot hashes and fixes tick, limits, and `E_ref` for `run_t2`. |
> | 2. Raw-to-prepared verification | **PARTIAL** | Rebuilding and comparing prepared hashes closes the original divergence. But [the consumer loader](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:366) still makes the pinned raw hashes and IS range optional, and [the harness](/home/cms/project/BTC_Futures_E2E/strategies/trial02/harness.py:61) accepts arbitrary bars without using that loader. The verdict path does not yet enforce provenance. |
> | 3. Completeness and funding defenses | **CLOSED** | Duplicate valid minutes now raise in the strategy; funding buckets reject duplicates and non-finite values in [days.py](/home/cms/project/BTC_Futures_E2E/backtest/days.py:49). Cross-module tests were added. |
> | 4. C6 reporting and specified coverage | **PARTIAL** | The harness joins `EntrySkipped` to first crosses. The new median test changes a group of window members, not each member; the C20 test compares PnL but does not assert the absence of a 00:00 `FundingSettled` event. |
> | C13 | **Accept supersession** | [Preparation](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:281) stops before writing prepared outputs when an audit stop condition exists, so passing those flags into `days.py` is unnecessary. |
> 
> **New verdict-relevant issue:** The new day-boundary assertion runs in [the strategy callback](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:126), after replay has processed the 00:00 bar ([replay order](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:75)). In a read-only synthetic reproduction, a position carried past a missing 23:59 bar was stopped by the next day’s 00:00 bar; the assertion did not fire. Check for a carried position or pending entry before processing that bar.
> 
> Pytest could not start: the read-only sandbox has no writable temporary directory. The synthetic reproduction ran directly; no `var/` or market data was accessed.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0d3a8-e44f-7d92-8cb7-ff9d0b397668
> Resume in Codex: codex resume 01a0d3a8-e44f-7d92-8cb7-ff9d0b397668

## 2026-09-24 — 2d·2e 재확인 r3(Codex task-mufla90x-ut0ylo **FIX-FIRST**) → 수정
| # | Codex | 입장 | 반영 |
|---|---|---|---|
| 2 | CLOSED(실행 때 원시 해시는 레지스트리 고정값에서) | ✅ | 실행 규약: 캡처 직후 원시 해시를 레지스트리 행에 고정 → `run_prepared_is`에 그 값 |
| 4 | PARTIAL — 구성원 하나씩 아님 · 동어반복 단언 | ✅ | 20개 구성원을 하나씩 반대 극단으로 → 중앙값 = 기대값이고 바뀐다 · d−1 · d−22는 불변 |
| 가드 | 펀딩이 가드보다 먼저 | ✅ | 재생에 선택 훅 `before_minute(bar, engine)`(펀딩·엔진 처리 **전** · 없으면 기존 경로 그대로 — 골든 통과) · 전략 가드를 그리로 · 테스트가 00:00 FundingSettled 없음까지 확인(이전 코드에서 실패 확인) |

### Codex 원문(verbatim · task-mufla90x-ut0ylo)
> ## Narrow re-check
> 
> - **#2 — CLOSED at the consumer boundary.** `run_prepared_is` fixes the IS plus 21 day range, requires caller supplied raw hashes, and rebuilds the prepared inputs before replay ([harness.py](/home/cms/project/BTC_Futures_E2E/strategies/trial02/harness.py:90), [prepare_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:366)). At execution, those hashes must come from the independent registry pin.
> - **#4 — PARTIAL.** The new test checks one exact median, but does not perturb each of the 20 members. Its assertions that members are in the locally constructed window are tautological; replacing `d−2` with excluded `d−22` leaves this test’s median unchanged ([test_trial02_harness.py](/home/cms/project/BTC_Futures_E2E/tests/test_trial02_harness.py:213)). The direct event test does cover the normal 00:00 funding case.
> - **Day-boundary timing — still open.** Replay processes funding before calling `exit_at_bar_open` ([engine_replay.py](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:75)). With a missing 23:59 bar and a carried position, my read-only synthetic reproduction observed one 00:00 `FundingSettled` **before** the moved guard raised ([strategy.py](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:124)). Put the guard before the minute’s funding step and test that case.
> 
> The three added synthetic checks passed when run directly. I accessed neither `var/` nor market data.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0d3ae-7e9a-7113-bf83-5f9b2202d0a5
> Resume in Codex: codex resume 01a0d3ae-7e9a-7113-bf83-5f9b2202d0a5

## 2026-09-24 — 2d·2e 재확인 r4(Codex task-muflhuva-ebkqug) **MERGE** — 2d·2e 완료

### Codex 원문(verbatim)
> **Narrow r4 re-check: no verdict-relevant issue found.** The median test now changes each of the 20 window members individually and checks both excluded neighbors. The [day-boundary guard](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:123) runs through `before_minute` before funding; a synthetic carried position triggered that guard before a 00:00 settlement.
> 
> The revised median and boundary tests passed. Both the no-hook replay and live-engine results matched their unchanged golden fixtures. This was read-only; I accessed neither `var/` nor market data.
> 
> **VERDICT: MERGE**
> 
> Codex session ID: 01a0d3b3-e8ed-7de3-a821-61f3d5f750ab
> Resume in Codex: codex resume 01a0d3b3-e8ed-7de3-a821-61f3d5f750ab

## 2026-09-24 — 트라이얼 #2 단계 2f **before-pass**(advisor + Codex task-muflm2wp-51o5aj **FIX-PLAN-FIRST**) → 설계 r2
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 0 | ✅ | 상태 보고를 이 차례에 보냄 |
| advisor | 1 | ✅ | G7 |
| advisor | 2 | ◐ | G8 — 결정은 Codex에게(재확인에서) |
| advisor | 3 | ✅ | G9 |
| advisor | 4 | ✅ | P1 포화 위험 공시(상태 보고) |
| advisor | 5 | ✅ | G6 |
| advisor | 6 | ✅ | 테스트 목록 |
| advisor | 7 | ✅ | G2 |
| Codex | 1 | ✅ | G1 |
| Codex | 2 | ✅ | G2 |
| Codex | 3 | ✅ | G3 |
| Codex | 4 | ✅ | G4 |
| Codex | 5 | ✅ | G5 |
| Codex | Q1·Q2 | ✅ | G6 · 이탈 없음 |

### 설계 r1
> # Trial #2 step 2f — placebos + isolated run CLI + stage orchestrator (design for the before-pass)
> 
> Binding: prereg §4 (P1 (a)–(f) + same-day/23:58/V_A eligibility, seed 20260924 spawn(1000); P2 +1/+5; P3; P4 200 draws, <190 defined → 폐기),
> §4-1 staging, §10/§11-4/-8, §3-1 (P1/P4 p95 = numpy linear quantile of per-draw mean net_bps; P2/P3 0 trades → 0 bps).
> Merged pieces: harness.run_prepared_is (pins + rebuild + V_A/V_B), strategy variants, engine fixed capital, P1 executor
> backtest/placebo_exec.run_time_exit (canonical engine, restore_position, liquidation + funding only, time exit at t+h−1 mark close).
> 
> F1 `backtest/p1_core.py` — generic P1 machinery with NO trial import: SourceTrade, PlacedSlot, P1Draw, occupancy, `P1Config(master_seed,
>    draws, slot_attempts=1000, fail_limit=10)`, `p1_rng(cfg, d) = Generator(PCG64(SeedSequence(cfg.master_seed).spawn(cfg.draws)[d]))`,
>    `p1_draw_generic(d, cfg, source, eligible_for_h, sizing_ok)` implementing (c)(d)(e) exactly as trial #1 (slots all first: pair →
>    direction; placement h desc, slot no.; ≤1000 tries; empty eligible list → slot fails without RNG; pair never redrawn),
>    canonical JSON, `p95` (numpy linear). `backtest/placebo.py` keeps its public names as thin trial #1 wrappers over p1_core
>    (defaults from trial #1 anchor) — trial #1 behaviour pinned by a golden generated from the current tree before the refactor.
> F2 `backtest/p1_t2.py` — trial #2 eligibility: for h, eligible minutes = ascending concatenation over days d ∈ sorted(V_A) of
>    t = d·DAY + m·MIN, m ∈ [0, 1439 − h] (so t and t+h−1 same UTC day and t+h−1 ≤ 23:58; V_A days have all 1,440 minutes);
>    h ≥ 1440 → empty. Lazy indexable view (len = |V_A|·(1440−h)). sizing_ok = placebo_exec.sizing_decision with harness.LIMITS
>    ((10,30), liq fee on liq price), E_ref 1,000, RegimeSizing("trial02_P1", 0.01, 10, 30). Execution = run_time_exit with the same
>    limits/E_ref/regime (fixed capital per trade; fee basis flag reaches the engine via limits). Source = Arm A trades.jsonl
>    (trade_id, entry_ms, exit_ms, sl_dist = post-fill sl_dist); h = ceil((exit_ms − entry_ms)/MIN), min 1.
>    Output per successful draw: mean net_bps (Decimal string) + n; failed draws listed; summary counts only.
> F3 `strategies/trial02/run.py` — isolated entry (`python -m strategies.trial02.run --arm A|B [--delay k] [--invert] [--p4-draw d]
>    --prepared DIR --pins FILE --out DIR`): harness.run_prepared_is → writes trades.jsonl, crosses.jsonl (with final_reason),
>    days.jsonl (strategy day log), validity.json (V_A/V_B + reasons), meta.json (variant, manifest + pins + rules-snapshot hashes,
>    bo_v1 SHA, git HEAD, counts only). stdout = counts only. 🚫 no wallet/return aggregates.
> F4 `backtest/p1_t2_run.py` — P1 CLI (parts by draw range + merge that must cover 0..999 exactly once) reading only
>    (trade_id, entry_ms, exit_ms, sl_dist) from the A run; V_A recomputed from the pinned prepared input and asserted equal to A's
>    validity.json; stdout counts only.
> F5 `backtest/t2_stages.py` — orchestrator (isolated subprocesses via backtest.replay.run_isolated, verbatim records, resumable):
>    stages `prepare` (capture+build once; prints manifest), `A`, `base` (B, P2_delay1, P2_delay5, P3_invert), `p1` (parts) +
>    `p1-merge`, `p4` (P4_draw000..199). Never opens outputs. IS only; no OOS path exists.
> F6 Pins: after `prepare`, the raw hashes (manifest["raw"]) are committed to `strategies/trial02/data_pins.json` + registry row
>    BEFORE any strategy stage; run.py/p1_t2_run.py read only that committed file (test: registry row contains the same hashes).
> F7 Evaluator inputs (2g contract): A, B, P2×2, P3, P4×200 run dirs + P1 merged null; "defined P4 draw" = ≥1 trade.
> Tests: p1_core golden (trial #1 byte-identical); same-day eligibility view == brute-force list on small synthetic V_A; sizing/exec
> use (10,30) + liq-fee flag; P1 RNG reproduction for trial #2 seed; CLI outputs + no aggregates; merge coverage; pins file ↔ registry;
> orchestrator never imports strategies.trial02 (assert_not_imported).
> Cost estimate (disclosed): P1 = 1,000 draws × n_A trades × up to 1,439 engine minutes — hours; parallel parts.
> Open: Q1 is running_time_exit's use of `ExitReason.MANUAL` for the P1 time exit acceptable (placebo only; reason recorded as
> time_exit)? Q2 anything in F2 that departs from (a)–(f)?

### 설계 r2 변경
> # 2f design r2 — changes vs r1 (advisor + Codex before-pass)
> 
> G1 (Codex #1) Push preflight for EVERY stage incl. `prepare`: orchestrator takes `--evaluator-commit H`; refuses unless (i) H is an
>    ancestor of HEAD, (ii) H is contained in origin/main after `git fetch` (read-only), (iii) `backtest/evaluate_t2.py` (+ its
>    imports' files listed in a frozen tuple) is byte-identical at HEAD and at H, (iv) the working tree is clean. H is written in every
>    verbatim record. After `prepare`: `strategies/trial02/data_pins.json` (raw hashes + the three prepared hashes) + registry row are
>    committed, and stage A/base/p1/p4 additionally refuse unless that file is tracked, clean, and contained in origin/main (a second
>    push = user checkpoint; its commit hash is recorded in each record).
> G2 (Codex #2) P1 placement AND execution use `harness.load_rules()` (#36 snapshot, SHA256-verified) and
>    `P1Config(master_seed=20260924, draws=1000, slot_attempts=1000, fail_limit=10)` passed explicitly; no default.
>    (advisor #7) limits/regime come from `strategies/trial02/config.py` (LIMITS moves there; harness re-exports).
> G3 (Codex #3) Resume = a stage is "done" only if its record's command, variant, evaluator commit, pins commit, prepared manifest hash,
>    and EVERY recorded output hash match the current files (missing/changed → error, not rerun silently). `p1-merge` is its own
>    isolated recorded stage that verifies each part's record + output hashes and exact 0..999 coverage. The evaluator (2g) verifies
>    the same provenance for all inputs (A, B, P2×2, P3, P4×200, P1 merged).
> G4 (Codex #4) Variant whitelist enforced in `Variant.__post_init__`: at most one of {delay ∈ {1,5}, invert, p4_draw ∈ 0..199};
>    B has none. Run name ↔ variant is a fixed table in the orchestrator (A, B, P2_delay1, P2_delay5, P3_invert, P4_draw000..199);
>    meta.json stores the exact variant; evaluator rejects any name/meta mismatch.
> G5 (Codex #5) n_A = 0 → P1 writes `{"computable": false, "reason": "n_A=0"}` and no null; evaluator applies §7 priority (IS trade 0 →
>    REJECT first) without a P1 mean. 2g contract: all 200 P4 IDs exactly once; zero-trade P4 draws excluded (count reported);
>    < 190 defined → 폐기; P2/P3 zero trades → 0 bps.
> G6 (Codex Q1 · advisor #5) `run_time_exit(..., reason=ExitReason.MANUAL)` parameter (trial #1 default unchanged — golden); trial #2
>    passes TIME_EXIT; P1 output keeps per-draw counts of time_exit vs liquidation (report).
> G7 (advisor #1) run.py / p1_t2_run.py take no pins argument — they read only the committed `data_pins.json` (tracked + clean).
> G8 (advisor #2 — cost; for Codex to rule) Per-run rebuild of ~1.3M rows × ~210 runs is hours of overhead. Proposal: per-run check =
>    manifest hashes + prepared file hashes equal to `data_pins.json` (raw AND prepared hashes pinned); full rebuild-verify runs once
>    in a recorded `verify` stage right after `prepare` and once inside the evaluator. The chain raw→prepared stays proven.
> G9 (advisor #3) B&H input: the evaluator reads prepared bars via `load_prepared` (pins) and takes each UTC day's last 1m kline close
>    (§3-1); no strategy-run file needed.
> Tests added: h ∈ {1, 1438, 1439, 1440} eligible view vs brute force over non-adjacent V_A days; seeded P1 golden for 20260924;
> sizing refusal + exhausted attempts; P1 liquidation under trial #2 limits with liq-price fee; P1 funding + time_exit reason;
> n_A = 0; forbidden variant combos; resume tampering / missing files / stale pins / unpushed evaluator (git state faked via a
> temp repo); trial #1 placebo golden generated before the refactor.

### Codex 원문(verbatim · task-muflm2wp-51o5aj)
> ## Before-pass findings
> 
> The P1 eligibility formula in F2 is correct: `m ≤ 1439 − h` permits an exit close at 23:58 and excludes 23:59. The slot draw order, occupancy, 1,000 attempts, no-redraw rule, seed, and successful-draw p95 also match [§4](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:119) and the [trial #1 implementation](/home/cms/project/BTC_Futures_E2E/backtest/placebo.py:166). I found no specified change to P2, P3, or P4’s trading rules; the existing strategy implements their delay, mirror, and daily seed paths in [strategy.py](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:188).
> 
> **Fix these before making the 2f stages runnable:**
> 
> 1. **BLOCKER — evaluator push order.** F5 allows `prepare` without a stated preflight proving that the trial #2 evaluator was committed and pushed. The binding order puts that push before *every* run, and the project log explicitly defers the real-data validity pass until then ([§4-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:126), [§10](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:196)). Make every stage, including `prepare`, refuse to start until it verifies the pushed evaluator commit and records its hash. Freeze the evaluator’s decision rules before that push. After preparation, commit and push the raw hash pins and registry row before A or any placebo run; record those commit hashes too.
> 
> 2. **BLOCKER — P1’s rules source is unspecified.** F2 fixes the limits and capital but does not say where `sizing_decision` and `run_time_exit` get `RuntimeRules`. Copying [trial #1’s runner](/home/cms/project/BTC_Futures_E2E/backtest/p1_run.py:43) would load trial #1 rules and change accepted placements and returns. Require [trial #2 `harness.load_rules()`](/home/cms/project/BTC_Futures_E2E/strategies/trial02/harness.py:39), which verifies the four registered snapshot hashes, for both placement and execution. Instantiate P1Config explicitly with seed `20260924` and `draws=1000`.
> 
> 3. **BLOCKER — resumption and merge provenance.** “Verbatim records” alone do not define safe resumption. Trial #1’s [`done()`](/home/cms/project/BTC_Futures_E2E/backtest/step_e.py:38) checks only exit code; [`run_isolated()`](/home/cms/project/BTC_Futures_E2E/backtest/replay.py:53) hashes outputs when a run finishes, but does not verify them on resume. Require a resumed stage to match its command, pins, prepared manifest, relevant commit hashes, and every recorded output hash; fail on missing or changed files. Run and record `p1-merge` as an isolated stage, verify its part-file hashes and exact draw coverage, and have the evaluator verify the same provenance across **all** A/B/P2/P3/P4 inputs, not only P1’s `V_A`.
> 
> 4. **BLOCKER — permitted variant combinations.** F3’s flags and the current [`Variant` validation](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:38) allow an A run combining delay, inversion, and P4, or a delay other than 1 or 5. Such output could be mislabeled as a registered placebo. Accept only A, B, A+delay1, A+delay5, A+invert, or A+one P4 draw; store the exact variant in metadata and reject a mismatch between run name, arguments, and metadata.
> 
> 5. **BLOCKER — zero-trade and defined-draw contract.** With zero A source trades, trial #1’s draw loop produces empty “successful” draws, while [`p1_null_distribution()`](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:108) divides by zero. Specify an explicit non-computable P1 output for `n_A=0`; the evaluator must still apply the registered G0 failure in its priority order, without inventing a P1 mean. In the 2g contract, require all 200 P4 IDs exactly once, exclude zero-trade P4 draws, discard if fewer than 190 are defined, and assign **0 bps** to zero-trade P2/P3 runs ([§3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:112)).
> 
> **Q1.** `MANUAL` does not appear to change P1 PnL: the engine passes the reason through the same close path ([engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:621)). It is an inaccurate engine event for a registered time exit, and F2 does not yet retain the required liquidation-versus-time-exit report. Use `ExitReason.TIME_EXIT` for P1’s mark-close call, retain `time_exit`/`liquidation` counts, and test that prices and returns stay identical. The current call is in [placebo_exec.py](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:94).
> 
> **Q2.** F2’s same-day view and P1 (a)–(f) mechanics have no substantive departure. The unresolved rules source and exit reporting above are the departures that must be closed. P2/P3/P4 match the registered strategy paths, provided the CLI restricts variants as stated.
> 
> **Missing tests:** boundary minutes for `h=1`, `1439`, and `1440` across nonadjacent `V_A` days; seeded placement with sizing refusal and exhausted attempts; trial #2 snapshot use and liquidation-fee basis; P1 funding and time-exit reason; zero A trades; P4 defined counts at 189/190 and P2/P3 zero trades; exact p95 interpolation and equality rejection; forbidden flag combinations; and resume/merge tampering, missing files, stale pins, and an unpushed evaluator. Keep the trial #1 golden plus a trial #2 seeded golden. These are synthetic, read-only tests; I did not run market-data stages or read `var/`.
> 
> VERDICT: FIX-PLAN-FIRST.
> 
> Codex session ID: 01a0d3b6-ea93-78b0-8e88-d5e4e268373c
> Resume in Codex: codex resume 01a0d3b6-ea93-78b0-8e88-d5e4e268373c

### advisor 원문 요지(verbatim 항목 0~7)
> 0 status report now (fee basis, sl==anchor, 23:59 H/L, position_busy, TDD+mutation, pipeline; ask whether data_pins needs a push before stage A) · 1 F3 --pins contradicts F6 → committed tracked clean file only · 2 per-run rebuild cost → pin prepared hashes, rebuild once in verify stage + evaluator (Codex's call) · 3 F7 missing B&H input · 4 disclose P1 saturation risk · 5 Q1: reason param, TIME_EXIT · 6 tests: h ∈ {1,1438,1439,1440}, liquidation under LIMITS, seed reproduction, source reader · 7 limits/regime from config not harness.

## 2026-09-24 — 2f 설계 r2 재확인(Codex task-muflt7hh-km7whk **FIX-PLAN-FIRST**) → r3
- #1·#2·#4·#5·Q1 CLOSED · #3 PARTIAL(코드 동일성) · G8 수용 조건(verify 영수증 필수 · 해시 전용 로더) → ✅ 동의 → G10~G12.

### 설계 r3 변경
> # 2f design r3 — code identity + verify receipt (Codex r2: #3 PARTIAL, G8 conditions)
> 
> G10 Execution-code fingerprint = SHA256 over the sorted (path, file-SHA256) list of a frozen set: strategies/trial02/*.py,
>     backtest/{engine_replay,prepare_t2,days,p1_core,p1_t2,p1_t2_run,placebo_exec,returns,data,replay,t2_stages}.py, paper/*.py,
>     sizing/*.py, exchange/*.py (+ pyproject.toml, uv.lock). Every record stores the fingerprint + clean HEAD. A stage (or resume)
>     refuses if the current fingerprint differs from the verify receipt's fingerprint; the evaluator requires ONE fingerprint across
>     the receipt and all A/B/P2/P3/P4/P1 records (else 폐기 as a harness defect is NOT inferred — it refuses to evaluate and reports).
> G11 Verify receipt: stage `verify` (after `prepare` and after the pins commit is pushed) runs the full rebuild
>     (`verify_rebuild`, expect_range = IS+21d) and writes `_records/verify.json` with pins commit, manifest SHA256, raw + prepared
>     hashes, evaluator commit, fingerprint. A, base, p1, p1-merge, p4 refuse unless the receipt exists, its hashes equal
>     `data_pins.json` and the current prepared files, and its fingerprint/evaluator commit equal the current ones.
> G12 Hash-only run loader `prepare_t2.load_prepared_pinned(out, pins)`: `verify_manifest` + SHA256 of bars_1m.parquet, funding.json,
>     source_audit.json and every raw file equal to `pins` (no rebuild). `harness.run_prepared_is` uses it; `verify_rebuild` is used
>     only by the `verify` stage and by the evaluator.
> Tests: changed-code resume refused (fingerprint); missing / mismatched verify receipt refused; hash-only loader rejects a tampered
> prepared file; evaluator-side fingerprint uniformity (in 2g).

### Codex 원문(verbatim · task-muflt7hh-km7whk)
> This is a **design re-check**, not an implementation pass. I read the r2 plan and relevant code without accessing `var/` or market data.
> 
> | Before-pass item | Status | Ruling |
> |---|---|---|
> | 1. Evaluator push order | **CLOSED** | G1 requires the pushed evaluator before every stage, including `prepare`, and a pushed pins commit before strategy runs. |
> | 2. P1 rules source | **CLOSED** | G2 fixes the snapshot-verified rules and explicit P1 configuration for placement and execution. |
> | 3. Resume and merge provenance | **PARTIAL** | G3 fixes output hashes, merge coverage, and evaluator input checks, but does not require resumed or evaluated runs to use the same **strategy, harness, and preparation code**. Existing records contain `git_head`; r2 does not say to validate it or an equivalent source fingerprint. |
> | 4. Variant combinations | **CLOSED** | G4 defines the allowed variants and binds run names to metadata. |
> | 5. Zero-trade and defined-draw contract | **CLOSED** | G5 defines the `n_A=0` path, all 200 P4 IDs, the 190-draw threshold, and zero-trade P2/P3 values. |
> | Q1. P1 exit reason | **CLOSED** | G6 specifies `TIME_EXIT`, retains liquidation counts, and preserves Trial #1’s default. |
> 
> **G8:** A rebuild on every run is unnecessary for data provenance. Pinned raw and prepared hashes, a recorded raw-to-prepared rebuild, and a second rebuild in the evaluator can establish the chain. The plan still needs to make the `verify` receipt a mandatory prerequisite for A and every placebo run, bound to the same pins and manifest. It also needs to specify the hash-only run path: the current [`load_prepared`](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:366) rebuilds on every call.
> 
> Those two provenance requirements are verdict-relevant. Add the `verify` gate and a common execution-code identity check to G3/G8, then test a changed-code resume and a missing or mismatched `verify` receipt. The [r2 text](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:5299) currently leaves both paths open.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0d3bb-fd81-7a23-84e7-8c849f75e6bf
> Resume in Codex: codex resume 01a0d3bb-fd81-7a23-84e7-8c849f75e6bf

## 2026-09-24 — 2f 설계 r3 재확인(Codex task-muflwnbf-jhqw2v **FIX-PLAN-FIRST**) → r4
- G10·G12 CLOSED · G11 PARTIAL(영수증 ↔ 현재 매니페스트 해시 · 핀 커밋 대조 누락) → ✅ 동의 → G13.

### 설계 r4 변경
> # 2f design r4 — receipt ↔ manifest ↔ pins-commit binding (Codex r3: G11 PARTIAL)
> 
> G13 Every later stage, every resume, and the evaluator's input validation require, in addition to G11:
>     (i) SHA256(current `manifest.json`) == receipt.manifest_sha256, and
>     (ii) the commit that last changed `strategies/trial02/data_pins.json` (`git log -1 --format=%H -- <file>`) == receipt.pins_commit
>          == the pins commit stored in the run's own record.
>     Any mismatch → refuse (no rerun).
> Tests: manifest-only change (files untouched, manifest rewritten consistently) refused; pins-commit mismatch refused.

### Codex 원문(verbatim · task-muflwnbf-jhqw2v)
> G10 closes the r2 code identity gap: stages and evaluator records must share the execution-code fingerprint. G12 supplies the hash-only run path, with full rebuilds at verification and evaluation.
> 
> **G11 remains partial.** The verify receipt records a manifest SHA256 and pins commit, but the later-stage gate does not explicitly compare either value with the current `manifest.json` and pins commit. A manifest-only change can pass `verify_manifest`, which checks the files named *inside* the manifest, while leaving the receipt bound to an older manifest. This leaves the receipt-to-manifest link required by the r2 review unproven. See [G11](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:5364) and [verify_manifest](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:340).
> 
> Add those two equality checks for every later stage, resume, and evaluator input validation; test a manifest-only change and a pins-commit mismatch. This was a read-only design review; I ran no market-data stages.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0d3be-7064-71e0-ae0c-ea57ada29ffb
> Resume in Codex: codex resume 01a0d3be-7064-71e0-ae0c-ea57ada29ffb

## 2026-09-24 — 2f 설계 r4 재확인(Codex task-mufm01gd-k35w1g) **PROCEED** — 설계 r1 + G1~G13 확정

### Codex 원문(verbatim)
> G13 closes the G11 gap. It requires later stages, resumes, and evaluator input validation to match the current manifest’s SHA256 and the pins file’s last-changing commit against the verify receipt and run record. The two added tests cover the previously missing mismatch cases. I found no new verdict-relevant ambiguity in the full 2f design ([r1 and G1–G13](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:5247)).
> 
> This was a read-only design review; I did not run market-data stages or access `var/`.
> 
> VERDICT: PROCEED.
> 
> Codex session ID: 01a0d3c0-dad6-7423-94d3-ddf733f3016b
> Resume in Codex: codex resume 01a0d3c0-dad6-7423-94d3-ddf733f3016b

## 2026-09-24 — 2f F1: P1 공통 기계 분리(`backtest/p1_core.py` · 트라이얼 import 없음) + `run_time_exit(reason=)`(G6)
- `backtest/placebo.py`는 트라이얼 #1 래퍼(공개 이름·기본값 유지) · 골든 `tests/fixtures/golden_p1_trial01.json`은 **리팩터 전 트리**에서 생성 → 바이트 동일 · 기존 placebo 테스트 통과.

## 2026-09-24 — 트라이얼 #2 단계 2f 구현(설계 r1 + G1~G13)
- F2 `backtest/p1_t2.py`(같은 날 적격 보기 · #36 규칙 · config.LIMITS · E_ref · TIME_EXIT · CFG 20260924/1000/1000/10) · F3 `strategies/trial02/run.py`(변형 이름 고정 표 · 커밋·푸시된 data_pins만 · 집계 없음) · F4 `backtest/p1_t2_run.py`(쌍 입력만 · V_A 재계산 대조 · n_A=0 계산 불가 · 병합 = 조각 기록 해시 + 0..999 정확히 한 번) · F5 `backtest/t2_stages.py`(모든 단계 푸시 선행 · verify 영수증 문 · 검증된 이어 하기) · `backtest/t2_provenance.py`(G1·G7·G10~G13) · G4 변형 화이트리스트 · G12 해시 전용 로더(`load_prepared_pinned` · 범위 대조) · LIMITS/P1_REGIME을 config로.
- **TDD 이탈(공개)**: `t2_provenance.py`·`t2_stages.py`는 테스트보다 먼저 썼다 → 돌연변이 검사: provenance 6개 중 5개 잡음 → 놓친 1개(깨끗한 트리 검사)는 테스트를 더해 잡음 · stages 4/4 잡음.
- 테스트 격리 결함 발견·수정: 전체 실행 순서에서만 트라이얼 #1 P1 골든의 28번째 자리가 달라짐 — 앞선 테스트가 전역 10진 문맥을 바꿔 남김 → `conftest` 자동 픽스처로 테스트마다 기본 문맥 · 트라이얼 #2 CLI 두 개는 시작 때 기본 문맥 고정(결정론).

## 2026-09-24 — 트라이얼 #2 단계 2f **after-pass**(advisor + Codex task-mufmldej-t9bzsa **FIX-FIRST**) → 수정
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 0 | ◐ | 상태 보고는 이 차례 중간 텍스트로 사용자에게 두 번 나갔다(기록 정확) — 새 항목(10진 문맥 발견)은 다음 보고에 |
| advisor | 1 | ✅ | `fingerprint_at(H)` == `fingerprint(HEAD)` 선행 검사 · 판정기 파일을 지문 집합에 · 테스트(앵커 수정 커밋 → 거부 · 새 H → 통과) |
| advisor | 2 | ✅ | prepare/verify도 검증된 이어 하기(기록 있으면 대조 · 불일치 오류 · 덮어쓰지 않음) |
| advisor | 3 | ✅ | (a) 확인: trial01 run·p1_run·step_e·evaluate는 ccxt를 import하지 않는다 → **트라이얼 #1 기록 실행은 영향 없음** · (b) 2g 규약 |
| advisor | 4 | ✅ | 자식에 `T2_NO_FETCH=1` |
| advisor | 5 | ✅ | 2g 설계서로 이월 |
| Codex | 1 | ✅ | `check_record`가 모듈·인자·필수 출력 이름까지 대조 · 테스트(인자 변경 · 출력 누락 · 변조) |
| Codex | 2 | ✅ | 영수증은 성공한 verify 실행 기록(명령·출처·준비 파일 해시)과 함께만 · 건너뛴 이어 하기에서도 준비 파일 변경 거부 · 위조 영수증 테스트 |
| Codex | 3 | ✅ | p1-merge·prepare·verify 모두 done 검사 · 병합 기대값 불일치 오류 · 병합 변조 테스트 |
| Codex | 4 | ✅ | fetch 실패 → 오류(자식은 부모 성공 뒤 fetch 생략) · 테스트 |
| Codex | 5 | ✅ | meta.json에 매니페스트 해시·핀·HEAD·문 결과 · `load_pins`가 레지스트리에 핀 해시 전부 있는지 대조 · 직접 CLI도 `gate_cli`(영수증 판정기 커밋으로 선행 검사 + verify 기록·영수증) |
| Codex | 골든 | ✅ | 골든 세 개를 파싱 비교 → **문자열(바이트) 비교**로 |

### advisor 원문(verbatim 요지 항목 0~5)
> 0. The status report was logged as sent but never sent — do both: a correction line in ops_log and the report (fee basis; sl==anchor + R − 2·slippage; 23:59 H/L → 23:58 late_cross; position_busy unreachable; TDD deviations with mutation results; decimal-context finding; data pipeline; P1 saturation risk; ~25 unpushed commits; push checkpoint contents; data_pins second push before stage A).
> 1. require_evaluator_frozen freezes the wrong set (EVALUATOR_FILES only) — the evaluator imports anchor/config; preflight should require fingerprint at H == fingerprint(HEAD) (git show H:path per file). Test: commit + push, edit anchor, commit → refused.
> 2. Stages.prepare() has no done-guard — a second prepare overwrites the successful record with a failed one. Refuse if the record exists.
> 3. Decimal-context finding — scope it: (a) log whether trial #1's recorded runs could have been affected (grep: p1_run.main and trial01.run.main never construct CcxtRestClient) — "checked, not affected"; (b) convention row: every trial #2 P&L-touching process (run.py, p1_t2_run.py, evaluate_t2) starts with setcontext(Context()) — into the 2g brief.
> 4. 200 P4 subprocesses × git fetch — pass T2_NO_FETCH=1 to children (stale refs only cause false refusal, never false accept).
> 5. 2g brief must carry forward: G3 evaluator-side provenance over all records + receipt; G5 (P4 all 200 once, zero-trade excluded, <190 → 폐기; P2/P3 zero trades → 0 bps; P1 not-computable → §7 priority); fingerprint uniformity; 3(b); B&H daily close via load_prepared_pinned (G9); final_wallet never read.

### Codex 원문(verbatim · task-mufmldej-t9bzsa)
> ## After-pass findings
> 
> **The 2f implementation needs fixes before merge.** I reviewed `git diff ac23d03 HEAD` and the specified code, tests, log, and preregistration. I did not read `var/` or market data, edit files, or run tests.
> 
> 1. **BLOCKER — resume does not validate the command or complete output set.** [Stages.done](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:68) calls [check_record](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:112), which checks provenance fields and hashes *listed in the record*. It never compares `run.module` or `run.args` with the stage’s expected command, nor requires the expected output filenames. A record for a different command, or one with an output omitted from its hash list, can be accepted as done. This conflicts with **G3** and leaves the variant and output provenance needed for a verdict unproved.
> 
> 2. **BLOCKER — the verify receipt does not prove that verification ran.** [receipt_ok](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:56) accepts `verify_receipt.json` by comparing its fields with current pins and the manifest. It never checks the [verify run record](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:100), its command, exit status, or output hashes. It also does not hash the current prepared files when resuming a completed stage. Thus a fabricated receipt can satisfy the later-stage gate without a recorded rebuild, and changed prepared files can pass that gate when a run is skipped. This leaves **G8/G11**’s raw-to-prepared proof incomplete. The hash-only loader does check files when a subprocess actually runs ([prepare_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:353)).
> 
> 3. **BLOCKER — `p1-merge` silently reruns over an existing result.** [p1_merge](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:128) validates part records, then calls `run_one` without calling `done` for `P1_merge`. A missing or altered merged output is overwritten instead of causing the **G3** resume error. `prepare` and `verify` also bypass the common `done` check ([t2_stages.py](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:90)).
> 
> 4. **BLOCKER — the push check can use a stale remote reference.** [require_pushed](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:46) ignores a failed `git fetch`, then tests the locally cached `origin/main`. **G1** requires the check *after* a successful fetch. A network failure can therefore leave a formerly pushed evaluator or pins commit appearing valid.
> 
> 5. **Binding r1/F3 and F6 gaps.** [run.py’s `meta.json`](/home/cms/project/BTC_Futures_E2E/strategies/trial02/run.py:51) lacks the specified manifest hash, pins hashes, and git HEAD. The [pins gate](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:84) proves the file is tracked, clean, and pushed, but no 2f check establishes that the registry row contains the same hashes, as r1/F6 requires. The direct [strategy CLI](/home/cms/project/BTC_Futures_E2E/strategies/trial02/run.py:59) and [P1 CLI](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2_run.py:101) also lack an evaluator-commit or receipt gate; only the orchestrator enforces that staging order. These routes need to be closed or shown unable to enter the evaluator’s accepted input set.
> 
> ## Gate and P1 accounting
> 
> | Clause | Review result |
> |---|---|
> | G1 | **Partial:** orchestrator preflight exists at [t2_stages.py:52](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:52); failed fetch and direct CLI routes remain. |
> | G2 | **Implemented:** explicit P1 config, sizing limits, and regime at [p1_t2.py:23](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2.py:23); snapshot-verified rules are loaded at [p1_t2_run.py:44](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2_run.py:44). |
> | G3 | **Partial:** record and part checks exist at [t2_stages.py:68](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:68) and [t2_stages.py:128](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:128); findings 1 and 3 remain. Evaluator-side checks belong to 2g. |
> | G4 | **Implemented in 2f:** variant whitelist and fixed names at [strategy.py:45](/home/cms/project/BTC_Futures_E2E/strategies/trial02/strategy.py:45) and [run.py:24](/home/cms/project/BTC_Futures_E2E/strategies/trial02/run.py:24). Evaluator name/meta rejection remains for 2g. |
> | G5 | **Implemented for P1’s zero-trade output** at [p1_t2_run.py:53](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2_run.py:53); verdict priority and P2/P3/P4 defined-draw rules remain for 2g. |
> | G6–G7 | **Implemented:** TIME_EXIT and exit counts at [p1_t2.py:58](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2.py:58); committed pins are loaded at [run.py:68](/home/cms/project/BTC_Futures_E2E/strategies/trial02/run.py:68) and [p1_t2_run.py:124](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2_run.py:124). |
> | G8–G9 | **G8 partial** because of finding 2; G9’s buy-and-hold reader is a 2g evaluator contract, with no evaluator present in this diff. |
> | G10 | **Implemented for stage records:** fingerprint definition at [t2_provenance.py:20](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:20), storage at [t2_stages.py:79](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:79). Evaluator-wide equality remains for 2g. |
> | G11–G13 | Receipt, manifest SHA, and last-changing pins commit comparisons exist at [t2_provenance.py:98](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:98). **G11 remains partial** for finding 2; evaluator validation under G13 remains for 2g. |
> | P1 (a)–(f) | The reviewed mechanics match: duration and paired source values at [p1_core.py:33](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:33), RNG and slot/placement order at [p1_core.py:77](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:77), and same-day `V_A` eligibility through 23:58 at [p1_t2.py:28](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2.py:28). The Trial #1 wrapper retains its defaults at [placebo.py:49](/home/cms/project/BTC_Futures_E2E/backtest/placebo.py:49). |
> 
> The tests do not cover a changed recorded command, an omitted output hash, a fabricated receipt without a valid verify record, a changed prepared file during a skipped resume, a tampered existing P1 merge, or failed-fetch behavior. The [Trial #1 golden test](/home/cms/project/BTC_Futures_E2E/tests/test_p1_core.py:11) compares parsed JSON values, so it does not establish the claimed byte identity. The evaluator is intentionally scheduled for 2g; its absence is a remaining integration limit, not evidence that its verdict rules are correct.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0d3d0-0a96-7461-bf9a-d4abf22d644e
> Resume in Codex: codex resume 01a0d3d0-0a96-7461-bf9a-d4abf22d644e

## 2026-09-29 — 2f 재확인 r2(Codex task-mufmxg4e-ugtsag **FIX-FIRST**) → 수정
| # | Codex | 입장 | 반영 |
|---|---|---|---|
| 1 | PARTIAL — 조건부 p1_not_computable.json | ✅ | `check_record`: 출력 디렉터리의 파일 집합 = 기록된 출력 집합(기록 밖 파일·누락 모두 거부) · 테스트 |
| 2·3 | CLOSED | — | — |
| 4 | 직접 CLI의 T2_NO_FETCH | ✅ | 환경 변수 우회 삭제 — 직접 실행·자식 모두 항상 fetch(P4 200회 fetch 비용 수용 · advisor #4 방식 철회) |
| 5 | PARTIAL — 레지스트리 문자열 · 병합 직접 실행 | ✅ | 핀 해시는 **핀 커밋 시점**의 레지스트리(`git show <핀 커밋>:docs/trial_registry.md`)에 있어야 · 병합 CLI도 `--prepared` + `gate_cli` · 테스트 |
| 골든 | CLOSED | — | — |

### Codex 원문(verbatim · task-mufmxg4e-ugtsag)
> (세션 경계로 스크래치패드가 지워져 대화 기록에서 옮김 — 내용 원문 그대로)
> ## Narrow re-check
>
> **FIX-FIRST remains.** The fixes close much of the earlier review, but two verdict-relevant provenance gaps remain.
>
> | Point | Status | Finding |
> |---|---|---|
> | Blocker 1: command and output checks | **PARTIAL** | Module, arguments, required filenames, hashes, and exit status are checked. But `P1_OUTPUTS` omits the conditional `p1_not_computable.json`. Removing that file from a record’s hash list lets [check_record](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:142) accept a changed or unrecorded verdict input. Require the conditional file when `n_A=0`, or compare the complete output set. |
> | Blocker 2: verify receipt | **CLOSED** | [receipt_ok](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:63) now checks the successful verify record and current prepared-file hashes. |
> | Blocker 3: resume guards | **CLOSED** | Prepare, verify, and P1 merge check existing records before rerunning. |
> | Blocker 4: failed fetch | **CLOSED for orchestrated stages** | Fetch failure now raises. Direct CLIs still accept ambient `T2_NO_FETCH=1`, which can make their push check rely on a stale local remote reference. |
> | Blocker 5: pins and direct CLI | **PARTIAL** | Metadata and strategy/P1 range gates were added. [load_pins](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:107) checks only that pin hash strings occur *somewhere* in the registry text; it does not prove the trial #2 row is committed and pushed with the pins. The [direct P1 merge branch](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2_run.py:115) still returns before `gate_cli`. |
> | Advisor 1: fingerprint at evaluator commit | **CLOSED** | The preflight compares the evaluator commit’s execution-code fingerprint with the current one. |
> | Advisor 2: prepare guard | **CLOSED** | A recorded prepare is validated before being skipped. |
> | Golden identity | **CLOSED for current fixtures** | All three golden outputs matched their fixture bytes in read-only direct checks. The tests compare decoded strings; the current fixtures have LF endings. |
>
> Pytest could not start: this read-only environment has **no usable temporary directory**. I did not access `var/` or market data.
>
> **VERDICT: FIX-FIRST.**
>
> Codex session ID: 01a0d3d8-a34b-7152-9195-691eee8f95c2
> Resume in Codex: codex resume 01a0d3d8-a34b-7152-9195-691eee8f95c2

## 2026-09-29 — 2f 재확인 r3(Codex task-mum3dkkx-gd8u46 **FIX-FIRST**) → 수정
- #1·#4 CLOSED · #5 PARTIAL(해시가 레지스트리 어디에나 있으면 통과) → ✅ 동의 → 핀 커밋 시점 레지스트리에 `strategies/trial02/data_pins.json` 행이 정확히 하나 · 그 행에 `파일=해시` 전부 · 테스트(다른 행에만 있음 · 짝 불일치) · 규약 초안 25.

### Codex 원문(verbatim · task-mum3dkkx-gd8u46)
> **One provenance gap remains.** The r2 fixes close #1: recorded outputs must match the files in the output directory. They also close #4: direct CLIs now fetch, and P1 merge passes through the gate.
> 
> **#5 is still partial.** [load_pins](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:115) reads the registry at the pushed pins commit, but checks only whether each hash appears *anywhere* in its text. It does not establish that the Trial #2 data-pins row contains those hashes. The [test fixture](/home/cms/project/BTC_Futures_E2E/tests/test_t2_provenance.py:63) even uses an unrelated `| 99 |` row as a passing registry entry. Check the identified Trial #2 row and its named raw and prepared hashes, then test rejection when the hashes appear only in another row.
> 
> This was a read-only review of the requested diff and log. I did not access `var/` or market data or run tests.
> 
> VERDICT: FIX-FIRST.
> 
> Codex session ID: 01a0eb1e-0cee-7cb1-87c7-f9c2b08b2818
> Resume in Codex: codex resume 01a0eb1e-0cee-7cb1-87c7-f9c2b08b2818

## 2026-09-29 — 2f 재확인 r4(Codex task-mum3hmxz-c6kh2p **FIX-FIRST**) → 수정
- #5 PARTIAL(부분 문자열 대조 — `old_funding.json=<해시>`가 통과) → ✅ 동의 → 행에서 `이름=64자리 hex`를 정확히 파싱 · 같은 이름에 다른 해시 → 거부 · 파싱 결과가 data_pins와 **정확히 같은** 집합 · 테스트(접두 이름 · 충돌 중복).

### Codex 원문(verbatim · task-mum3hmxz-c6kh2p)
> **#5 remains PARTIAL.** [load_pins](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:118) now requires one path-bearing registry row at the pushed pins commit, but it checks each `file=hash` pair with substring matching. A row with `funding.json=<wrong hash>` and `old_funding.json=<correct hash>` passes the expected `funding.json=<correct hash>` check. The new [test](/home/cms/project/BTC_Futures_E2E/tests/test_t2_provenance.py:188) does not cover this case.
> 
> Parse and compare exact filename–hash entries, reject conflicting duplicates, and test the prefixed-name case. I reviewed the requested diff and log read-only, without accessing `var/` or market data. I did not run the test suite.
> 
> VERDICT: FIX-FIRST.
> 
> Codex session ID: 01a0eb20-eaed-7bd0-9d05-d7f7bbed7fcd
> Resume in Codex: codex resume 01a0eb20-eaed-7bd0-9d05-d7f7bbed7fcd

## 2026-09-29 — 2f 재확인 r5(Codex task-mum3kwid-tapkj1 **FIX-FIRST**) → 수정
- #5 PARTIAL(해시 뒤 잘못된 접미 통과) → ✅ 동의 → 필드 구분자(공백 · | · · · , · 백틱)로 토큰화 · 토큰 전체가 `이름=64hex`여야 · 핀 파일 이름으로 시작하는 잘못된 토큰 → 거부 · 테스트.

### Codex 원문(verbatim · task-mum3kwid-tapkj1)
> **#5 remains PARTIAL.** The new parser rejects `old_funding.json=<correct hash>`, closing the r4 example. But [load_pins](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:123) still accepts `funding.json=<64 correct hex characters>x` as a valid pair: its ending check excludes only another hex character. A read-only check with a complete synthetic pin row confirmed that the parsed map still equals `data_pins.json`.
> 
> Require a field delimiter or end of field after the hash, and add a malformed-suffix test. I found no separate new provenance hole in the requested diff. `git diff --check` passed; I did not run pytest or access `var/` or market data.
> 
> **TRIAL #2 2f is not ready to merge. VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0eb23-3e16-7992-9ec3-29f4f6a589a1
> Resume in Codex: codex resume 01a0eb23-3e16-7992-9ec3-29f4f6a589a1

## 2026-09-29 — 2f 재확인 r6(Codex task-mum3nqtb-3yr6i3) **MERGE** — 2f 완료

### Codex 원문(verbatim)
> The r5 issue is closed: the parser rejects a pinned `name=64-hex` token with an extra suffix, and the new test covers that case. The fix is recorded at the end of [ops_log.md](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md). I found no new provenance hole in the requested diff; `git diff --check` passed.
> 
> This was a read-only review. I did not run pytest or access `var/` or market data. On the requested r6 scope, TRIAL #2 2f is ready to merge.
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0eb25-43f2-7572-83ba-feef60bdaad3
> Resume in Codex: codex resume 01a0eb25-43f2-7572-83ba-feef60bdaad3

## 2026-09-29 — 트라이얼 #2 단계 2g(판정기) **before-pass**(advisor + Codex task-mum3pcwd-bpfiwz **FIX-PLAN-FIRST**) → 설계 r2
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 | ✅ | H1 |
| advisor | 2 | ✅ | H5 |
| advisor | 3 | ✅ | H8 |
| advisor | 4 | ✅ | H2 · H7 |
| advisor | 5 | ✅ | H9 |
| advisor | 6 | ✅ | H10 |
| advisor | 7 | ✅ | H11 |
| Codex | 1 | ✅ | H2(P1 두 출력 집합 · 병합 기대값 재계산) |
| Codex | 2 | ✅ | H2(독립 기대 목록 · git_head · meta 대조) |
| Codex | 3 | ✅ | H1 |
| Codex | 4 | ✅ | H3 |
| Codex | 5 | ✅ | H4 |
| Codex | 기타 | ✅ | H5 · H6 · H7 · H10 |

### 설계 r1
> # Trial #2 step 2g — evaluator `backtest/evaluate_t2.py` (design for the before-pass)
> 
> Binding: prereg §3 (gates, evaluation order), §3-1 (definitions, degenerate rules), §4 (placebo rejection rules), §4-1 (evaluator
> committed+pushed before any run; one evaluator call after all artifacts exist), §7 (staged precedence), §7-2 (classification),
> §7-3 (skip report), §11-4/-5. Carried forward from 2f reviews: G3/G5/G9/G10, advisor 3(b), final_wallet never read.
> Imports: strategies.trial02.anchor (constants only), backtest.{stats,t2_provenance,prepare_t2,days,replay}. NO strategy/harness/run
> import (test). Process starts with decimal.setcontext(Context()).
> 
> E0 Inputs + provenance (refuse to evaluate — no verdict — on any failure; report "evaluation refused: <reason>"):
>   - require_evaluator_frozen(ROOT, H) where H = receipt.evaluator_commit; fingerprint(HEAD) == receipt.fingerprint.
>   - verify record + receipt (same checks as Stages.receipt_ok) and ONE full `verify_rebuild` (raw → prepared hashes).
>   - Run records: A, B, P2_delay1, P2_delay5, P3_invert, P4_draw000..199 (exactly these 205 names), P1_part_* covering 0..999 + P1_merge:
>     check_record(module, args, exact output set, provenance {evaluator_commit, pins_commit, manifest_sha256, fingerprint, variant}).
>     meta.json variant_name == record name and meta.variant == run.variant_for(name) table (duplicated here as data, not imported).
>   - V_A/V_B recomputed from the pinned prepared input == every run's validity.json.
>   - Refuses if `evaluation/` already exists (one call).
> E1 Per-trade values (strings → Decimal → float only for numpy): net_bps, gross_bps, entry_ms, exit_reason, from trades.jsonl.
>   Statistical ledger PnL_i = N_stat·net_bps/1e4; daily stat PnL on V_A days (entry day; 0 on no-trade days); daily return = PnL/N_stat.
> E2 Gates (A; B computed and reported the same way over V_B):
>   G0: n ≥ 48 ∧ n/(1+4·max(ρ̂,0.15)) ≥ 30 · ρ̂ = lag-1 autocorr of net_bps in entry order; undefined (n<3 or var 0) → 0.
>   G1/G2: mean gross/net > 0 ∧ CI_lo > 0 · CI = day-block percentile bootstrap over V_A days (empty days kept; resamples with 0 trades
>     excluded and counted), 10,000 resamples, numpy linear quantiles at 0.625/99.375 %, streams SeedSequence((20260924,1)).spawn(8)[k]
>     k: 0 gross_A, 1 net_A, 2 gross_B, 3 net_B, 4 A/B daily. Undefined CI → gate fails.
>   G-B: SR̂ = mean/std(ddof=1) of per-trade net_bps, defined iff n ≥ 2 ∧ var > 0. SR* = expected_max_sr(defined subset of
>     {SR_1A, SR_1B, SR̂_A, SR̂_B}, n_trials=4); < 2 defined → fail. Pass ⇔ PSR_A(0) > 0.5 ∧ n_A ≥ 30 ∧ SR̂_A − SR* > 0;
>     SR̂_A or PSR_A undefined → fail. Report PSR_A(SR*) and which SR̂ were undefined.
>   flat: Σ PnL_i > 0 (≡ mean net > 0).
>   Survival: A liquidations (exit_reason == "liquidation") == 0.
> E3 Placebos (orig = A mean net_bps):
>   P1: computable ∧ failed draws ≤ 10 → p95 = numpy linear 0.95 quantile of successful draws' mean_net_bps; reject ⇔ orig ≤ p95.
>       failed > 10 → 폐기 (harness defect, priority 4). Not computable (n_A=0) cannot reach P1 (A trade 0 → priority 1).
>   P2: value = mean net_bps of the variant run (0 trades → 0) · reject ⇔ orig ≤ max(d1, d5).
>   P3: reject ⇔ orig ≤ inverted (0 trades → 0).
>   P4: defined draws = runs with ≥ 1 trade; < 190 defined → 폐기; p95 of defined draws' mean net; reject ⇔ p95 ≥ orig.
> E4 §7 IS precedence: 0 폐기 (V_A empty) → 1 REJECT(FAIL — 트레이드 0) → 2 REJECT(생존) → 3 REJECT (G0/G1/G2/G-B/flat) + §7-2 →
>    4 폐기 (P1 failures > 10 · P4 defined < 190) → 5 REJECT (P1..P4) + §7-2 → IS PASS.
>    §7-2: MDE = (z_{1−0.0125} + z_{0.8})·σ(net,ddof1)/√n_eff (NormalDist) · > 20 → 검정력 부족 · < 5 ∧ net CI_hi < 10 → 효과 부재 ·
>    else 결론 보류 · MDE undefined → 검정력 부족.
> E5 Reports (never gates): A/B daily contrast over V_B (B_day − A_day, mean + CI stream 4), B diagnostics vs non-contraction A trades,
>    B&H daily Sharpe (last 1m kline close per consecutive UTC IS day via load_prepared_pinned; first return = day2/day1) vs A daily
>    Sharpe over V_A (label "ACCEPT — 수동(매수보유)을 이기지는 못함" is recorded as the IS comparison for the eventual ACCEPT), window
>    B&H return; §7-3 skip ratios from crosses.jsonl final_reason (floor/ceiling split); holding-time distribution, exit reasons,
>    long/short, per year; P1 exit counts; MDE; CI details. final_wallet is never read (test).
> E6 OOS stage function (pure, pre-committed now, not callable without a separate user-approved OOS stage): OOS 0 폐기(data) → 1 trade 0 →
>    2 survival → 3 OOS G0 → "REJECT(OOS 표본 부족)" → 4 G3 (net mean>0 ∧ CI_lo>0) → OOS PASS. Forward G-F: out of scope (new registry
>    row at activation).
> E7 Output: `evaluation/report.json` (sorted keys) + `evaluation/verdict.txt` + SHA256s printed; stdout = verdict string only.
> Tests (synthetic): each gate boundary; degenerate rules; SR* subset rule; CI percentile + zero-trade resamples; seeded bootstrap
> reproduction; every §7 precedence row incl. ties/overlaps; placebo equality boundaries (≤, ≥); P4 189/190; P2/P3 zero-trade 0;
> provenance refusals (missing run, wrong variant meta, fingerprint mismatch, second call); no strategy import; final_wallet unread.

### 설계 r2 변경
> # 2g design r2 — changes vs r1 (advisor + Codex before-pass)
> 
> H1 (Codex #3 · advisor #1) New `backtest/stats_t2.py` (added to the fingerprint + evaluator-frozen sets): `valid_day_bootstrap_mean(
>    trades_by_day, days, rng)` — blocks = exactly the given day list (empty valid days kept, invalid days absent; a trade whose entry
>    day ∉ days → error), statistic = Σ resampled sums / Σ resampled counts, resamples with 0 trades excluded + counted, CI = numpy
>    linear quantiles at 0.625/99.375 %. `daily_diff_bootstrap(a_day, b_day, days, rng)` — A/B = mean over V_B of (B_day − A_day),
>    same resampled day indices. stats.block_bootstrap_mean / paired_block_bootstrap_diff are NOT used by trial #2 (test).
> H2 (Codex #1·#2 · advisor #4) Independent expected inventory, checked BEFORE opening any result file:
>    records = exactly {prepare, verify, A, B, P2_delay1, P2_delay5, P3_invert, P4_draw000..199, P1_part_* , P1_merge} (no extra record);
>    strategy run n: module strategies.trial02.run, args [--variant n, --prepared <prep>], output set exactly RUN_OUTPUTS;
>    P1 parts: args [--a-dir <runs/A>, --prepared <prep>, --draws lo-hi], ranges disjoint and covering 0..999, output set exactly
>    P1_OUTPUTS, or P1_OUTPUTS + p1_not_computable.json (then every part and the merge must be not-computable and A must have 0 trades);
>    merge: args fixed, `p1_merge_expect.json` recomputed from part records and equal to the file; merged draws 0..999 once, one null row
>    per successful draw with matching ids.
>    Each record: returncode 0, run.git_head == provenance.head (no "+dirty"), provenance {evaluator_commit H, pins_commit, manifest_sha256,
>    fingerprint, variant} uniform; meta.json: variant_name/variant == name table, pins == data_pins, manifest_sha256 == receipt,
>    n_trades / n_first_cross == line counts; every A trade's entry day ∈ V_A, every B trade's ∈ V_B.
> H3 (Codex #4) Dispositions: (i) verified prepared input with V_A empty → §7 priority 0 폐기; (ii) a prepare SourceStop never reaches the
>    evaluator — per C12 it goes to the user as a correction doc; a user-approved registry row declaring the dataset unobtainable is the
>    only path to "폐기(데이터)"; (iii) missing/changed/incomplete artifacts → evaluation refusal (no verdict, nothing written).
> H4 (Codex #5) ρ̂ implemented in stats_t2: lag-1 Pearson over (x[:-1], x[1:]); n < 3, either slice variance 0, or non-finite → ρ̂ := 0.
> H5 (Codex · advisor #2) B&H: for every UTC day in the IS window that has ≥ 1 kline bar, close = the 23:59 bar's kline close, else that
>    day's last available 1m bar close; days with no kline bar are skipped and the next return bridges the gap; returns start at the
>    window's second listed day; window return = last listed close / first listed close − 1. A daily Sharpe or B&H Sharpe undefined →
>    "비교 불가" and no suffix.
> H6 (Codex) B: statistics reported, no B gate (no B G-B/activation). Liquidation counts reported for B and every placebo run.
>    §7-3 from A crosses.jsonl: denominator = its first-cross rows, final_reason null = entered, reasons exclusive, sl_dist_out_of_range
>    split by side.
> H7 (Codex E7) stdout = the verdict string only; everything else in files. `evaluation/` is written only after every check and
>    calculation succeeded (temp dir then rename). `evaluation/record.json` = H, pins commit, fingerprint, receipt, SHA256 of every input
>    record and every file read, evaluator HEAD, report.json + verdict.txt SHA256 (the §11-8 one-call proof).
> H8 (advisor #3) Pure core `verdict_is(GateInputs) -> Verdict` (plain numbers/bools) + I/O shell. Truth-table tests for every §7 row and
>    every boundary (≤/≥, MDE exactly 5 and 20, P4 189/190, P1 failures 10/11, <2 defined SR̂, n_A 29/30, G0 47/48 and n_eff 30).
> H9 (advisor #5) MDE n_eff = G0's n/(1+4·max(ρ̂,0.15)). Numeric domain: every gate quantity computed from Decimal inputs converted to
>    float64 once (`float(Decimal)`), all comparisons in float64; P2/P3 zero-trade value = 0.0.
> H10 (Codex OOS · advisor #6) Pre-commit pure `verdict_oos(...)` and pure `verdict_forward(liq_or_killswitch, exec_defect, n_trades,
>    mean_net_bps, is_bh_label)` now; their loaders are later stages (OOS = user-approved, forward = activation registry row) that must keep
>    the frozen evaluator. OOS report also includes OOS A/B and B&H values.
> H11 (advisor #7) Endgame: 2g MERGE → whole-step-2 after-pass → 2i registry rows from the conventions draft → push request (evaluator
>    commit = H) → prepare → data_pins.json + registry row → second push → verify → A → base → p1 → p1-merge → p4 → evaluate once. Every
>    stage needs a clean tree: each stage's ops_log entry is committed before the next stage starts.

### advisor 원문(verbatim 요지)
> 1. stats.block_bootstrap_mean cannot be reused for G1/G2 — verdict-relevant (calendar-day blocks include invalid days; §3-1 excludes them); A/B contrast is the mean of daily differences over V_B, not stats.paired_block_bootstrap_diff's trade-weighted difference. Write fresh; keep a = (1−level)/2 quantiles.
> 2. B&H series under-specified: 23:59 kline close else last available bar; day with no kline skipped and the next return bridges. Test.
> 3. Split the evaluator into a pure verdict core and an I/O shell; truth-table tests for every §7 row and tie (≤/≥, MDE 5/20, P4 189/190, P1 10/11, <2 defined SR̂).
> 4. §11-8 evidence in evaluation/record.json (H, pins commit, fingerprint, receipt hashes, every input record SHA256, own HEAD, report SHA256); assert P1 computable ⇔ n_A > 0; every A/B trade entry day ∈ V_A/V_B.
> 5. Pins: MDE n_eff uses G0's max(ρ̂,0.15); one numeric domain for all ≤/≥ comparisons.
> 6. Pre-commit the OOS function and also a pure forward verdict function (liq/killswitch count, mismatch/data-gap flag, trade count, sign statistic, IS Sharpe label).
> 7. Endgame sequence in the log: 2g MERGE → whole-step-2 after-pass → 2i rows → push request → prepare → data_pins + registry → second push → verify → A → base → p1 → merge → p4 → evaluate once; every stage needs a clean tree, commit each ops_log entry before the next stage.
> No blocker in the design itself; item 1 changes a verdict if implemented by reuse.

### Codex 원문(verbatim · task-mum3pcwd-bpfiwz)
> **VERDICT: FIX-PLAN-FIRST.** The proposed gates mostly match the preregistration, but the artifact contract and several reporting paths still allow different implementations or leave required provenance unproved. This was a read-only review; I did not inspect `var/` or market data.
> 
> ### Blockers and exact fixes
> 
> 1. **The P1 artifact contract is incomplete.** E0 calls for an “exact output set,” but [p1_t2_run.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2_run.py:53) adds `p1_not_computable.json` when A has zero trades; the normal output set is only two files. Specify both exact sets, and let the zero-trade set reach §7 priority 1. For a computable P1, require draw IDs 0–999 exactly once, one null row per successful draw, matching IDs and counts, and a merged result consistent with the validated parts. Recompute `p1_merge_expect.json` from part records; it is currently a separate mutable input to the merge command ([t2_stages.py](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:156)).
> 
> 2. **E0 does not yet prove what ran.** [check_record](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:156) verifies hashes listed by a record and requires named outputs, but does not enforce an *exact expected* output set. Define expected module, arguments, and file set independently for each of the 205 strategy runs and each P1 part and merge; reject extra or missing records, overlapping P1 ranges, and any gap in 0–999. Check each record’s `run.git_head` against its recorded head and evaluator commit, and check `meta.json` pins, manifest, gate, code identity, and trade/cross counts against validated records. Otherwise a valid hash proves only that a file matches its record, not that the file belongs to the required run.
> 
> 3. **The valid-day bootstrap needs an explicit implementation rule.** E2 correctly says to sample `V_A` or `V_B`, including empty *valid* days. The existing [stats.block_bootstrap_mean](/home/cms/project/BTC_Futures_E2E/backtest/stats.py:55) samples every calendar day between two timestamps, including invalid days. Require a new valid-day-block calculation for G1/G2 and the paired `V_B` daily policy difference. State that this helper, rather than the existing calendar-range helper, supplies the gate CI. Sampling invalid days can change a verdict.
> 
> 4. **Data failure versus evaluation refusal needs a rule.** E0 refuses every missing or failed input without a verdict, while [§7 priority 0](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:154) requires **폐기** when the required dataset cannot be obtained. Specify how a documented prepare/source failure becomes that disposition, separately from a missing, changed, or incomplete run artifact, which should remain an evaluation refusal. Keep `V_A` empty as priority 0 when a verified prepared dataset exists.
> 
> 5. **Lag-one correlation has an unhandled degenerate case.** [lag1_autocorr](/home/cms/project/BTC_Futures_E2E/backtest/stats.py:118) checks variance of the full series, while either lagged slice can have zero variance and `np.corrcoef` then returns NaN. Specify `ρ̂ := 0` for any undefined/nonfinite correlation, consistent with [§3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:114), before calculating G0 or MDE.
> 
> ### Other departures and precision fixes
> 
> - E5 should say the buy-and-hold series uses **every UTC day in the IS window with a kline**, takes that day’s last available 1m kline close, and bridges a wholly missing day to the next available close. “Consecutive UTC IS day” can instead be read as dropping the bridged return. Undefined A or buy-and-hold Sharpe means “비교 불가” and no ACCEPT suffix ([§3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:110)).
> - “B computed and reported the same way” must not create a B G-B or activation gate. Report B’s applicable statistics; A alone decides ([§3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:85)).
> - E5 must explicitly report liquidation counts for B **and all placebo variants**, as [§3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:95) requires. Define §7-3 skip rates from **A** `crosses.jsonl`: denominator is its direction-specific first-cross rows, with `final_reason == null` counted as entered, and split `sl_dist_out_of_range` by `side` floor/ceiling ([§7-3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:179)).
> - E7 says both “SHA256s printed” and “stdout = verdict string only.” Put hashes in `report.json` or on stderr; reserve stdout for the single verdict string. Write `evaluation/` only after all checks and calculations succeed.
> - For the one-call rule, check the **complete expected artifact inventory before opening any result file**, following the [trial #1 evaluator precedent](/home/cms/project/BTC_Futures_E2E/backtest/evaluate.py:5). Record the evaluator call and its report/verdict hashes; `evaluation/` existence alone prevents a second write but is a weak audit trail.
> 
> ### OOS and tests
> 
> Pre-committing a **pure OOS verdict function now is right**: it fixes the OOS G0, survival, G3, and precedence rules before IS results are known. Keep its input loading and invocation behind the later user-approved OOS stage; that stage must preserve the frozen evaluator and report OOS A/B and buy-and-hold values required by [§3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:111) and [§4-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:129).
> 
> Add synthetic tests beyond those listed for: invalid days excluded from bootstrap while empty valid days remain; lagged-slice zero variance; P1’s alternate zero-trade file set and part/merge consistency; exact command/output/metadata checks and extra-record refusal; buy-and-hold missing-day bridging and undefined-Sharpe label; B and placebo liquidation reporting; and the distinction between certified source unavailability, empty `V_A`, and provenance refusal. The proposed boundary and precedence tests are otherwise appropriate.
> 
> Codex session ID: 01a0eb26-6a06-7023-b5d7-8cfacbcf9eb2
> Resume in Codex: codex resume 01a0eb26-6a06-7023-b5d7-8cfacbcf9eb2

## 2026-09-29 — 2g 설계 r2 재확인(Codex task-mum3ud68-heqeab **FIX-PLAN-FIRST**) → r3
- #3·#4·#5 CLOSED · #1·#2 PARTIAL(병합 내용 동일성 · 기록 종류별 출처) · 곁파일·meta·유효일 확장 → ✅ 동의 → H12~H15.

### 설계 r3 변경
> # 2g design r3 — artifact check pins (Codex r2)
> 
> H12 P1 merge content: merged p1_draws.json == concatenation of the validated parts' draws sorted by draw id (byte-equal after the same
>     canonical serialization), merged p1_null.jsonl rows == concatenation of parts' null rows sorted by draw id (row-equal). Only then is
>     p95 computed.
> H13 Provenance per record kind (independent table):
>     prepare: {evaluator_commit, fingerprint, variant="prepare"}; module backtest.prepare_t2, args [];
>     verify:  {evaluator_commit, fingerprint, pins_commit, variant="verify"}; module backtest.prepare_t2, args ["--verify"];
>     post-verify runs (A, B, P2×2, P3, P4×200, P1 parts, P1_merge): {evaluator_commit, fingerprint, pins_commit, manifest_sha256,
>     variant=<name>}. All: returncode 0, run.git_head == provenance.head, no "+dirty".
> H14 `_records/` inventory = run records (prepare, verify, 205 strategy runs, P1_part_*, P1_merge) + exactly two sidecars
>     (verify_receipt.json, p1_merge_expect.json); anything else → refusal. Sidecars are checked by content (receipt = recomputed;
>     expect = recomputed from part records).
> H15 meta.json checks for every strategy run: variant_name/variant (name table), pins == data_pins, pins_commit == record, manifest_sha256
>     == receipt, bo_v1_sha256 == anchor.BO_V1_SHA256, rules_snapshot_sha256 == anchor.RULES_SNAPSHOT_SHA256, git_head == record
>     provenance.head, gate == {evaluator_commit, pins_commit, manifest_sha256, fingerprint} of the receipt, n_trades / n_first_cross ==
>     line counts. Valid-day membership: every trade's entry day ∈ V_A for A, P2_delay1, P2_delay5, P3_invert, P4_draw*; ∈ V_B for B.

### Codex 원문(verbatim · task-mum3ud68-heqeab)
> **The r2 design is not ready to implement.** It resolves the statistical and disposition rules, but the artifact checks still have contradictions and leave one P1 result check unspecified.
> 
> | Before-pass blocker | Status | Re-check |
> |---|---|---|
> | 1. P1 artifact contract | **PARTIAL** | H2 covers both output sets, draw IDs and null-row counts. It does not explicitly require the merged draw and null values to equal the validated parts. Matching IDs alone would permit a different P1 p95. Require the merge to equal the parts’ concatenation, sorted by draw ID. |
> | 2. Proof of what ran | **PARTIAL** | H2 adds commands, exact output sets and metadata checks, but “each record” requires `pins_commit` and `manifest_sha256` even though the current `prepare` record has neither and `verify` lacks `manifest_sha256` ([stage code](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:106)). Define provenance requirements separately for prepare, verify and post-verify runs. |
> | 3. Valid-day bootstrap | **CLOSED** | H1 samples exactly the valid-day list, retains empty valid days and excludes invalid days. |
> | 4. Data failure versus refusal | **CLOSED** | H3 separates a verified empty `V_A`, documented source unavailability requiring a registry decision, and incomplete artifacts that receive no verdict. |
> | 5. Degenerate lag-one correlation | **CLOSED** | H4 checks both lagged slices and non-finite results before setting undefined ρ̂ to zero. |
> 
> **Other points:** H5–H11 address the earlier B&H, B-only reporting, liquidation, skip-rate, output, boundary-test, numeric-domain and later-stage concerns. Two artifact details still need to be pinned down:
> 
> - H2’s “no extra record” inventory must distinguish run records from the required `_records/verify_receipt.json` and `_records/p1_merge_expect.json` sidecars ([stage code](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:72), [merge code](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:172)).
> - Extend the metadata and valid-day checks to every verdict input: check `meta.json`’s `git_head`, `gate`, `pins_commit`, `bo_v1_sha256` and rules-snapshot hash against their pinned values ([emitted fields](/home/cms/project/BTC_Futures_E2E/strategies/trial02/run.py:53)); require P2, P3 and every P4 trade entry day to belong to `V_A`, as H2 already requires for A and B.
> 
> This was a read-only design review. I did not access `var/` or market data.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0eb29-fab2-7ea3-9e34-77edf0f8efde
> Resume in Codex: codex resume 01a0eb29-fab2-7ea3-9e34-77edf0f8efde

## 2026-09-29 — 2g 설계 r3 재확인(Codex task-mum3x6la-nng26h) **PROCEED** — 설계 r1 + H1~H15 확정

### Codex 원문(verbatim)
> **The full 2g design (r1 + H1–H15) is ready to implement.** H12 closes the P1 merge content gap by requiring the merged draws and null rows to match the validated parts before p95 is calculated. H13 resolves the prepare/verify provenance mismatch. H14 accounts for the two required sidecars, and H15 covers the remaining strategy metadata and valid-day checks. I found no new verdict-relevant ambiguity.
> 
> This was a read-only design review; I did not inspect `var/` or market data. The evaluator has not been implemented or tested by this review.
> 
> VERDICT: PROCEED
> 
> Codex session ID: 01a0eb2b-fc25-75e0-9d1e-b41d94a12246
> Resume in Codex: codex resume 01a0eb2b-fc25-75e0-9d1e-b41d94a12246

## 2026-09-29 — 트라이얼 #2 단계 2g 구현(판정기 · 설계 r1 + H1~H15)
- `backtest/stats_t2.py`(유효일 블록 부트스트랩 · 일별 대비 · ρ̂ 퇴화 0 · Sharpe 정의 규칙 · p95) · `backtest/verdict_t2.py`(순수 핵심: `verdict_is` · 사전확약 `verdict_oos` · `verdict_forward`) · `backtest/evaluate_t2.py`(껍데기: 문 → 결과 파일을 열기 전 독립 기대 목록 → 원시 재빌드 1회 → 메타·유효일·병합 내용 → 통계 → 핵심 → 임시 디렉터리 쓰기·이름 바꾸기 · 표준출력 = 판정 문자열만 · 한 번만).
- `t2_provenance`: 판정기 동결·지문 집합에 stats_t2 · verdict_t2 추가.
- 시험: 핵심 진리표·경계 32개 · 통계 10개 · **실제 `Stages` + 실제 출력 형식 가짜 러너로 205 실행 + P1 조각·병합 전체 합성 파이프라인** 위 판정·거부 16개.
- **TDD 이탈(공개)**: `evaluate_t2.py`는 시험보다 먼저 썼다(stats_t2·verdict_t2는 시험과 함께) → 돌연변이 검사 7개 중 6개 잡음 · 놓친 1개(일관되게 더러운 HEAD)는 시험을 격리해 잡음.
- 발견: 초안 픽스처의 SR̂_A 0.2는 SR*(0.259)보다 작아 G-B 실패 — §3 공시("SR̂가 #1과 멀수록 SR*가 커진다")의 실제 사례. 규칙 문제가 아니라 픽스처 값 문제로 고침(0.6).

## 2026-09-29 — 트라이얼 #2 단계 2g **after-pass**(advisor + Codex task-mum48p9v-aavz5n **FIX-FIRST**) → 수정
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| Codex | 1 | ✅ | `_f`가 유한하지 않거나 해석 불가한 값 → 거부 · 핵심 `verdict_is`도 유한하지 않은 입력 → 오류(0건 평균만 예외) · 시험(평가기 경로 + 핵심 6개 필드) |
| Codex | 2 | ✅ | prepare/verify 정확한 집합 = `T.PREP_OUTPUTS` 고정 · 시험(추가 산출물) |
| Codex | 3 | ✅ | 비수축 진단 = B `days.jsonl` 상태로 수축일 · C = V_B 비수축일 A 트레이드 · 차이 보고 · 트레이드/유효일 · 무효일 수 보고 · 시험 |
| advisor | 1·2 | ✅ | Codex 3·2와 같음 |
| advisor | 3 | ✅ | 판정 문자열 `REJECT(§7-2: <분류>)` · 시험 · 규약 26 |
| advisor | 4 | ✅ | NaN → null · `allow_nan=False` · 시험 |
| advisor | 5 | ✅ | 규약 27 |
| advisor | 6 | ✅ | 비출처 예외도 `Refusal`(판정 없음 · 아무것도 쓰지 않음) |
| advisor | 7 | ✅ | 시험: 우선순위 3 문자열 · 비교 불가 · 메타 불일치 4종 · P1 계산 가능 모순 · 변형 표 205개 교차 · V_A 빈 경우 우선순위 0 |
| advisor | 8 | ✅ | 끝 순서 기록(아래 단계 계획) |
- 빈 날 목록에서 부트스트랩이 경고를 내던 것 → 정의 안 됨으로 깨끗이 반환(시험).

### advisor 원문(verbatim 요지)
> 1. Report bug — B_vs_noncontraction_A is wrong (t not in tb always true; C = all A trades on V_B). Fix via B days.jsonl status; test n_C == n_A_on_V_B − n_B.
> 2. prepare/verify exact output set is self-referential — pin sets=[set(T.PREP_OUTPUTS)].
> 3. Verdict string format unpinned ("REJECT · 결론 보류형 REJECT") — decide format, test it, conventions row; same for 비교 불가 / suffix wording.
> 4. report.json can contain NaN — nan→None + allow_nan=False.
> 5. B&H source disclosure — prepared-bar closes (kline∩mark); convention row.
> 6. Wrap non-provenance exceptions (KeyError/FileNotFoundError/JSONDecodeError) into Refusal so "no verdict, nothing written" holds.
> 7. Tests: shell priority-3 classification string; 비교 불가; check_meta refusals (counts/validity/pins); p1_computable ≠ (n_A>0); E.VARIANTS == run table for all 205.
> 8. Endgame: fixes → narrow re-check → whole-step-2 after-pass → 2i rows → push request (H = last commit touching any fingerprint file) → prepare → data_pins + registry → second push → verify → A → base → p1 → merge → p4 → evaluate once; commit each stage's ops_log entry before the next stage.
> Items 1–2 blocking for MERGE; 3–7 fold into the same fix commit.

### Codex 원문(verbatim · task-mum48p9v-aavz5n)
> ## Findings
> 
> 1. **BLOCKER — a nonfinite placebo value can produce `IS PASS`.** [`_f()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:169) accepts `"NaN"` and `"Infinity"` in trade and P1 null values. [`p95()`](/home/cms/project/BTC_Futures_E2E/backtest/stats_t2.py:88) can then return `NaN`, while [`verdict_is()`](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:116) checks only for `None`. Comparisons with `NaN` are false, so a placebo can silently avoid rejection. I confirmed that valid passing gate inputs with `NaN` P1, P2, P3, and P4 values return `IS PASS` with all four placebo rejections false. Refuse nonfinite result values before calculating a verdict; add a regression test through the evaluator input path.
> 
> 2. **BLOCKER — the prepare output set is not checked independently.** [`check_inventory()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:95) takes the purported exact prepare output set from `prepare.json`, then validates that record against the same set. The `PREP_OUTPUTS` check requires only a subset. A record and directory containing an extra output therefore pass, contrary to H2’s exact output set requirement. Pin the expected set in the evaluator and test an extra recorded prepare output.
> 
> 3. **Binding report departures.** The required *B versus noncontraction A* diagnostic uses A trades on all `V_B` days, filtered by trade dictionary inequality with B ([`compute()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:282)). `V_B` denotes days with complete B inputs, not noncontraction days; the implementation does not use the recorded day status. The report also omits the explicit difference. Section 7-3 requires trades per day and a separate invalid-day count; [`trade_report()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:238) and the [`validity` report](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:284) provide neither. These are report requirements, not gates.
> 
> ## H1–H15 check
> 
> | Clause | Assessment and implementation |
> |---|---|
> | H1 | Implemented: valid-day trade bootstrap and paired daily bootstrap in [`stats_t2.py`](/home/cms/project/BTC_Futures_E2E/backtest/stats_t2.py:39); called with `V_A`/`V_B` in [`compute()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:255). |
> | H2 | **Partial:** run inventory, commands, hashes, P1 range coverage, and metadata checks are at [`check_inventory()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:71) and [`check_meta()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:121). Prepare’s output set is self-derived as described above. |
> | H3 | Implemented for this evaluator: existing output or missing receipt refuses at [`evaluate()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:306); empty verified `V_A` gets priority 0 at [`verdict_is()`](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:91). The SourceStop/registry process is outside this evaluator. |
> | H4 | Implemented at [`lag1_rho()`](/home/cms/project/BTC_Futures_E2E/backtest/stats_t2.py:66). |
> | H5 | Implemented at [`bh_series()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:195), with the undefined-Sharpe comparison at [line 280](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:280). |
> | H6 | **Partial:** B has no gate and liquidation and skip counts are reported at [lines 284–296](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:284); the noncontraction diagnostic is incorrect. |
> | H7 | Implemented for single-call refusal, temporary output, stdout, and output/input hashes at [lines 301–358](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:301). Raw-file hashes are carried in the receipt rather than `inputs_sha256`. |
> | H8 | Pure IS verdict implemented at [`verdict_is()`](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:91); boundary tests exist in [`test_verdict_t2.py`](/home/cms/project/BTC_Futures_E2E/tests/test_verdict_t2.py:25). Coverage gaps are below. |
> | H9 | G0’s effective sample size and MDE use the same formula at [`verdict_t2.py`](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:28). Decimal inputs reach float comparisons through [`_f()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:169); its missing finite check is verdict relevant. |
> | H10 | Pure OOS and forward functions are present at [lines 125–152](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:125). OOS loading and reporting remain a later stage under the approved design. |
> | H11 | This is the future execution sequence in [`ops_log.md`](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:5695); it cannot be established by this code diff. |
> | H12 | Implemented: canonical merged draws and null rows are compared with parts at [`check_meta()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:145). |
> | H13 | Required provenance by record kind is supplied at [`check_inventory()`](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:78). |
> | H14 | Exact record and sidecar names are checked at [lines 73–77](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:73). |
> | H15 | Strategy metadata, line counts, and valid-day membership are checked at [lines 125–144](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:125). |
> 
> The **G0, G1, G2, G-B, flat, survival, P1–P4 comparison boundaries, IS/OOS/forward precedence, and §7-2 MDE thresholds** otherwise match the cited preregistration rules in [`verdict_t2.py`](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:91). The main departure in verdict behavior is the nonfinite placebo path.
> 
> Missing targeted tests include nonfinite placebo inputs yielding a refusal, an extra recorded prepare output, a mixed contraction/noncontraction B diagnostic, trades-per-day and invalid-day reporting, and empty `V_A` at the full evaluator boundary. I could run the pure `NaN` verdict probe. Pytest could not start in this read-only environment because it could not create a temporary file; no files were changed.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0eb34-2f85-7de2-8d0e-324d702297bf
> Resume in Codex: codex resume 01a0eb34-2f85-7de2-8d0e-324d702297bf

## 2026-09-29 — 2g 재확인 r2(Codex task-mum4k69v-2rawav **FIX-FIRST**) → 수정
| # | Codex | 입장 | 반영 |
|---|---|---|---|
| 1 | OPEN — 1e400 → inf | ✅ | float 변환 뒤 유한성 검사 · 시험(평가기 경로) |
| 2 | CLOSED | — | — |
| 3 | PARTIAL — B 날 상태 파일 | ✅ | V_B 날마다 정확히 한 행(trading · not_contraction · no_range) · V_B 밖은 not_trade_day · B 트레이드는 trading 날만 · 시험 2개 |
| advisor 6 | PARTIAL — 영수증 해석·선행 검사 | ✅ | `evaluate` 전체를 감싸 모든 예외 → 거부 · 시험(깨진 영수증) |

### Codex 원문(verbatim · task-mum4k69v-2rawav)
> ## Narrow re-check
> 
> 1. **Finding 1: OPEN — verdict-relevant.** `_f()` rejects nonfinite Decimal inputs but does not check the result of `float(d)` ([evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:167)). I confirmed that `_f("1e400")` returns `inf`, while the 95th percentile of 199 values at −10 and one `inf` remains −10. A nonfinite P4 draw can therefore be included without reaching the new verdict-input guard. Check that the converted float is finite, and test this path through the evaluator.
> 
> 2. **Finding 2: CLOSED.** Prepare and verify now use the fixed `T.PREP_OUTPUTS` set, with an extra-output refusal test ([evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:95)).
> 
> 3. **Finding 3 / H6: PARTIAL.** The B diagnostic now reads day status, reports the mean difference, and adds trades per valid day and invalid-day counts ([evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:287)). The evaluator does not check that `days.jsonl` has one valid status per `V_B` day or that B trades occur only on `trading` days. An incomplete or inconsistent status file can still misstate the diagnostic.
> 
> **Advisor items:** 2–5 and 8 are closed in this diff. Item 1 remains partial with finding 3; item 7 has the requested targeted tests, but lacks the overflow case above. **Item 6 is partial:** receipt parsing and parts of preflight remain outside the new refusal handler, so malformed provenance can raise an uncaught exception ([evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:333)).
> 
> This was read-only. I did not inspect `var/` or market data. I ran the focused numeric probe; I did not run the file-writing pytest suite.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0eb3c-5a49-7780-8d6a-8793891a19b7
> Resume in Codex: codex resume 01a0eb3c-5a49-7780-8d6a-8793891a19b7

## 2026-09-29 — 2g 재확인 r3(Codex task-mum4rirf-a09b4w **FIX-FIRST**) → 수정
- r2 항목 CLOSED · 새 차단: 유한한 1e308 세 개의 평균 = inf → p95가 흡수 → ✅ 동의 → 변형 평균·P1/P4 p95 결과의 유한성 검사(거부) · `stats_t2.p95` 입력에 유한하지 않은 값 → 오류 · 시험 2개.

### Codex 원문(verbatim · task-mum4rirf-a09b4w)
> The three r2 items are **closed**: `_f()` rejects `1e400` after float conversion, B day statuses are checked against `V_B` and B trade days, and malformed receipts now become a `Refusal`.
> 
> I found one new verdict blocker. In [evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:195), three individually finite `1e308` P4 trade values make `np.mean` return `inf`. With 199 other draw means at −10, [p95()](/home/cms/project/BTC_Futures_E2E/backtest/stats_t2.py:92) still returns −10, so the [verdict input check](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:91) does not catch the invalid draw and an otherwise passing run can reach `IS PASS`. I reproduced the mean and percentile behavior with a read-only numeric probe. Validate each aggregate before the percentile and add an evaluator regression test.
> 
> `git diff --check` passed. I did not run the file-writing test suite or access `var/` or market data.
> 
> **2g is not ready to merge.**
> 
> VERDICT: FIX-FIRST
> 
> Codex session ID: 01a0eb41-954a-7722-864f-a081edf86244
> Resume in Codex: codex resume 01a0eb41-954a-7722-864f-a081edf86244

## 2026-09-29 — 2g 재확인 r4(Codex task-mum4zbf8-pxgads **FIX-FIRST**) → 수정
- r3 경로 CLOSED · 남은 경로: B Sharpe 분산 넘침(None으로 읽혀 SR*에서 빠짐) · 재표본 중간 합 넘침 · OOS/전진 함수의 inf → ✅ 동의 → **입력 경계에서 한 번에**: 판정기가 읽는 bps 값 하나의 절댓값 ≤ 10⁶(건전성 한도 · 판정 임계 아님 · 밖이면 거부 · 규약 29) + 방어선: 부트스트랩 합·재표본 평균 유한성 · Sharpe 분산 넘침 → 오류(정의 안 됨이 아님) · OOS/전진 유한성 검사 · 시험 4개.

### Codex 원문(verbatim · task-mum4zbf8-pxgads)
> The r3 fix closes the reported P4 path: run means and P1/P4 percentiles now receive finite checks. The full scan found remaining verdict paths:
> 
> 1. **B Sharpe overflow can change IS PASS.** Finite B returns alternating `1e200` and `2e200` overflow the standard deviation. [sharpe_or_none](/home/cms/project/BTC_Futures_E2E/backtest/stats_t2.py:81) returns `None`, so [G-B](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:102) omits B from `SR*`. A read-only probe changed a representative result from REJECT to IS PASS. Refuse overflow here rather than treating it as an undefined Sharpe.
> 
> 2. **Bootstrap overflow can hide behind finite CI endpoints.** [valid_day_bootstrap_mean](/home/cms/project/BTC_Futures_E2E/backtest/stats_t2.py:39) checks the resulting endpoints, but not each resampled sum. In a 10,000-resample probe, 34 sums overflowed while both CI endpoints stayed finite; [G1](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:107) can then proceed. Check intermediate aggregates before computing quantiles.
> 
> The preregistered OOS and forward verdict functions also accept infinite means as passing inputs ([OOS](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:129), [forward](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:145)); they are not called by the current IS evaluator.
> 
> `git diff --check` passed. This was read-only; I did not access `var/` or market data or run the file-writing test suite.
> 
> VERDICT: FIX-FIRST
> 
> Codex session ID: 01a0eb47-23e4-71d3-8a26-e18dec387896
> Resume in Codex: codex resume 01a0eb47-23e4-71d3-8a26-e18dec387896

## 2026-09-29 — 2g 재확인 r5(Codex task-mum57wn5-ge95fr **FIX-FIRST**) → 수정
- 한도 안 넘침 없음 · 한도는 판정 임계가 아님(Codex 확인) · 남은 2건 → ✅ 동의: 한도를 반올림 전 Decimal로 비교 · OOS/전진은 0건에서도 평균 유한성 검사(호출자가 0.0) · 시험.

### Codex 원문(verbatim · task-mum57wn5-ge95fr)
> The r4 overflow paths are closed for values that pass the float64 bound. Even summing roughly 10⁶ values of magnitude 10⁶ reaches only about 10¹²; a conservative variance accumulation is about 10¹⁸, far below float64 overflow. The new bound is a data sanity refusal, not a gate, so I found no binding-text conflict.
> 
> Two checks still need fixing:
> 
> - [_f()](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:180) compares the *rounded float* with the limit. The Decimal input `1000000.00000000001` is outside the stated bound but is accepted as `1000000.0`. Compare the Decimal value before conversion.
> - [OOS and forward verdicts](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:138) replace a nonfinite mean with `0.0` when the trade count is zero. Read-only probes confirmed that both functions then return a verdict for an `inf` mean, contrary to [convention 29](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions_draft.md:30). Validate the supplied mean even on the zero-trade branch.
> 
> The 52 focused stats and verdict tests passed; `git diff --check` passed. I accessed no `var/` or market data.
> 
> VERDICT: FIX-FIRST.
> 
> Codex session ID: 01a0eb4d-3fad-7ea1-9ae7-6059e672932d
> Resume in Codex: codex resume 01a0eb4d-3fad-7ea1-9ae7-6059e672932d

## 2026-09-29 — 2g 재확인 r6(Codex task-mum5f0r2-kh9onv) **MERGE** — 2g 완료 · 전체 시험 1,168 통과

### Codex 원문(verbatim)
> Both r5 findings are closed. [_f()](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:180) checks the Decimal against the bps limit before float rounding. The [OOS and forward verdicts](/home/cms/project/BTC_Futures_E2E/backtest/verdict_t2.py:135) reject nonfinite means even with zero trades. I found no new verdict-relevant issue in the requested diff.
> 
> The focused tests and boundary probes passed; `git diff --check` passed, and the working tree is clean. I did not access `var/` or market data. **2g is ready to merge.**
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0eb52-502a-7a41-8eaa-fb3cf6a90c52
> Resume in Codex: codex resume 01a0eb52-502a-7a41-8eaa-fb3cf6a90c52

## 2026-09-29 — 트라이얼 #2 **단계 2 전체 after-pass**(advisor + Codex task-mum5iv8a-59ghc1 **FIX-FIRST**) → 설계 변경 K1~K6
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| Codex | 차단 1 (매수보유 kline) | ✅ | K1·K2 |
| Codex | 차단 2 (유효성은 mark 기준) | ✅ | K1 — mark-only 분 중단 규칙 폐기(C12/C19 해당 부분 대체) · 이전 설계 리뷰가 만든 규칙이지만 사전등록 §1은 mark 기준이 맞다 |
| Codex | 2i 행 | ✅ | K5 |
| Codex | 수치 한도 | ✅ | K3 — #36 가격 필터에서 도출한 한도(규칙이 허용하지 않는 값 = 데이터 결함) |
| advisor | 1 | ✅ | K6 |
| advisor | 2 | ✅ | K4 |
| advisor | 3·4 | ✅ | K5 |
| advisor | 5·6 | ✅ | 푸시 요청 보고에 반영(비밀 스캔 · P1 포화 공시 · 두 번 푸시 · 실행 시간 추정 · 메모리/TMPDIR) |

### 요약 제출물
> # Trial #2 step 2 — done vs planned (for the whole-step-2 after-pass)
> 
> Planned (plan r2, ops_log 2026-09-24): 2a anchor · 2b/2c engine+replay · 2d validity · 2e strategy · 2f placebos+CLI+orchestrator ·
> 2g evaluator · 2h rules snapshot · 2i convention rows · evaluator pushed before any run.
> Done (all synthetic; no real-data P&L; no OOS data; 1,168 tests):
> - 2h rules snapshot (#36, correction 01) · 2a anchor module (bdf0554).
> - 2b/2c shared layer, all default-off, pinned by goldens from pre-2b tree (LIVE + replay), 3 Codex rounds.
> - 2d/2e data pipeline (single raw capture → pure audit/build → manifest; stop rules) + day validity + strategy; design 6 rounds, code 4.
> - 2f P1 core split (trial #1 golden byte-identical), trial #2 P1, run CLI, P1 CLI, orchestrator with push preflight, fingerprint,
>   verify receipt, verified resume, exact output sets, registry pin row parsing; design 4 rounds, code 6.
> - 2g evaluator: valid-day bootstrap, pure verdict core (+ pre-committed OOS/forward), provenance-checked shell, one-call atomic output,
>   finiteness + sanity bound; design 3 rounds, code 6.
> Deviations disclosed: TDD order for prepare_t2, t2_provenance, t2_stages, evaluate_t2 (mutation checks); decimal-context test leak found
> and fixed (trial #1 records unaffected); liquidation fee basis = §1 row 46 (qty × liq price) over #2's unspecified basis (opt-in).
> Not done yet (by design): 2i registry rows; evaluator push (user checkpoint); prepare/verify/runs/evaluate (after push).
> Registry items proposed for 2i (from docs/trials/trial_02_conventions_draft.md, 29 items): one append-only row #37 "trial #2
> implementation conventions (before any real-data run)" listing items 1–29 by short name with the draft file's SHA256 pinned, plus the
> §11-8 evidence (output schema = run outputs RUN_OUTPUTS/P1_OUTPUTS/PREP_OUTPUTS/evaluation files; isolated CLI paths; the evaluator
> commit H to be filled at push).
> Open question for reviewers: is pinning the draft's SHA256 in the row (instead of copying 29 items into the row) sufficient, given the
> draft is a committed file that must then never change?

### 설계 변경 K1~K6
> # Whole-step-2 after-pass fixes — design delta K1–K6 (supersedes parts of C15/C17/C19 and H5/convention 27/29)
> 
> K1 (Codex blocking #1·#2) Mark and kline become INDEPENDENT per-minute series in prepare_t2 (prereg §1 completeness is mark-based;
>    §3-1 B&H is kline-based):
>    - mark(minute): archive row with 4 ok mark fields → archive; else REST markPriceKlines row (malformed → STOP; absent → minute missing).
>    - kline(minute): archive row with ok OHLC+volume fields → archive; else REST klines row (malformed → STOP; absent → no kline).
>    - Fill ranges = minutes lacking an ok archive mark OR an ok archive kline; both REST series are fetched there.
>    - Replay bars (`bars_1m.parquet`) = every minute with a mark; kline fields come from that minute's kline if present, else empty
>      strings (no trial #2 path reads bar kline fields: strategy/engine/P1 use mark only — test asserts). A mark-only minute is no
>      longer a STOP (supersedes C12/C19 mark-only rule). Mixing sources across the two series is allowed: they are never combined.
>    - New pinned prepared output `kline_close_daily.json`: for every UTC day with ≥ 1 kline minute, {day, close of the 23:59 kline if
>      present else of the day's last kline minute, minute} — from the kline series only. PREPARED set / pins gain this 4th file.
>    - Duplicate/conflict/off-grid/funding rules unchanged.
> K2 (Codex #1) Evaluator B&H reads `kline_close_daily.json` (pinned; IS days only; bridging of missing days as §3-1); bars no longer
>    used for B&H. Convention 27 rewritten accordingly.
> K3 (Codex numeric rule) The per-value bound is DERIVED from the registered runtime rules (#36 PRICE_FILTER): every trade has
>    entry, exit ∈ [min_price, max_price] ⇒ gross gain ≤ (max/min − 1)·10⁴ bps (long), short gain ≤ 10⁴; losses are capped by
>    liquidation (≤ margin + fee < 10⁴ bps) plus at most two funding settlements per day (each |rate| ≤ adjustedFundingRateCap from the
>    same snapshot). Bound B = 10⁴·(max/min + 1 + 2·cap) computed at run time from the snapshot (no literal); P1 draw means are averages of
>    bounded values. |value| > B is impossible under the registered rules ⇒ refusal = data defect, not a verdict change. Within B no
>    aggregate over ≤ 10⁶ values overflows float64. Convention 29 rewritten with this derivation.
> K4 (advisor #2) `Stages.run_one` recomputes the fingerprint before each subprocess and refuses on change (long stages).
> K5 (advisor #3·#4 · Codex 2i spec) Conventions file finalized as `docs/trials/trial_02_conventions.md` ("확정 · 실데이터 실행 전"),
>    adding: variant whitelist (G4) · P1 not-computable (G5) · P1 TIME_EXIT + exit counts (G6) · provenance chain (G1/G3/G10–G13/H2/H13–H15)
>    · strategy arithmetic context (prec 34) · dispositions (H3) · item 16 filled (§11-8: exact output sets PREP/RUN/P1/sidecars/evaluation,
>    CLI entry points). Registry row #37 incorporates items 1–N by reference + file SHA256 + commit, and must NOT contain the literal
>    pins path (load_pins requires exactly one such row). Push evidence (H, remote/ref, verified contains) → row #38 after the push,
>    before prepare. The pins row (#39) and data_pins.json are generated by a script from manifest.json, and load_pins is tested against
>    the real registry in a temp clone before the second push.
> K6 (advisor #1) One correction entry in ops_log with the four advisor passes previously logged as "요지" copied verbatim.

### advisor 원문(verbatim)
> You're at the whole-step-2 after-pass (Codex running); this is the advisor half. Done-vs-planned checks out: 2a–2h built, 2i pending by design, one plan change (trial #1 parquet → `prepare_t2`) approved in design r4. Findings, numbered for the log:
> 
> **1. Audit-trail gap — fix before the push request.** The standing rule says both passes verbatim. Four advisor passes were logged as "verbatim 요지" (2f before, 2f after, 2g before, 2g after); the others are full text. You have the full texts in this conversation — append one correction entry with the four verbatim copies, and log *this* pass verbatim, not condensed.
> 
> **2. Provenance window during a stage.** Fingerprint is computed once at preflight; a 200-run P4 stage runs for hours. If code changes mid-stage, later subprocesses run different code under the same recorded fingerprint. Strategy runs are caught indirectly (`meta.git_head` vs record head), P1 parts are not. Cheap close: recompute `PV.fingerprint` in `run_one` before each subprocess and raise on mismatch with the preflight value. One test with a monkeypatched fingerprint that changes after the first call.
> 
> **3. Registry row trap — this would break `load_pins`.** It requires *exactly one* row containing the literal `strategies/trial02/data_pins.json`. Conventions item 25 contains that path; if row #37 reproduces it, the count becomes 2 → every stage after `prepare` refuses. Row #37 must not contain that path. The pins row itself needs exactly 8 `name=64hex` tokens (5 raw: archive_rows.jsonl, fill_ranges.json, rest_klines.jsonl, rest_mark.jsonl, funding.jsonl; 3 prepared) and nothing else that parses as `name=64hex` — no `manifest.json=…`. Generate both the row and `data_pins.json` from `manifest.json` with a script, and test `load_pins` against the real registry in a temp clone before the second push.
> 
> **4. The open question: pinning the draft's SHA alone is not sufficient.** The file says "초안 — 바뀔 수 있다". Finalize it (rename to `trial_02_conventions.md`, header "확정 · 실데이터 실행 전"), enumerate item short names in row #37, pin the SHA256, and state it's immutable (change ⇒ new row). Before finalizing, add what's implemented but unlisted: variant whitelist (G4); P1 not-computable when n_A = 0 (G5); P1 exit reason TIME_EXIT + exit counts (G6); the provenance chain (evaluator push preflight, fingerprint, verify receipt, exact output sets, verified resume — G1/G3/G10–G13) as the §11-8 evidence; strategy arithmetic context (prec 34) for bands/sl_dist/median; H3 dispositions (SourceStop → correction doc; V_A empty → 폐기; artifact mismatch → refusal). Fill item 16 (§11-8 schema/CLI paths; H recorded after push).
> 
> **5. Push-request report contents.** H = HEAD at push time; docs-only commits after H are fine, any fingerprint-file change means a new H. Count commits since 355968a. Secret scan of the whole unpushed range first (public repo). State plainly: P1 saturation (h up to 1438 ≈ one trade per V_A day) can end the trial at priority 4 폐기 regardless of gates — pre-registered, not changeable without a correction doc; that's the user's call before pushing. Two pushes: this one, then pins + registry row after `prepare`. Estimate run time from trial #1's `_records/*.json` wall_s (not P&L) rather than guessing.
> 
> **6. Operational, not verdict-relevant:** `prepare` holds ~1.3M raw rows in memory and `verify_rebuild` copies raw to `/tmp` twice (verify stage, evaluator) — check RAM/TMPDIR space on the WSL box; runs are local, not VPS.
> 
> **Sequence:** Codex verdict → log both verbatim (+ item 1 correction) → items 2–4 in one commit → narrow re-check if Codex is FIX-FIRST → row #37 → secret scan → push request, then stop.

### Codex 원문(verbatim · task-mum5iv8a-59ghc1)
> ## Whole Step 2 review
> 
> **Done versus planned.** The read-only source review supports the reported completion of 2a–2h, including the synthetic evaluator and staged provenance checks. I found no real-data run or OOS work in scope. **2i registry rows and the evaluator push remain planned**, as the stated sequence requires. The preparation pipeline and provenance checks grew beyond plan r2 through the logged design reviews; that expansion is disclosed. The new 10⁶ bps refusal limit is the substantive addition that needs a rule check. I did not rerun the reported 1,168 tests or inspect `var/` or market data.
> 
> **Blocking objection.** The anchored rule uses each day’s last available **kline** close for buy and hold, including days outside the strategy’s valid-day set ([preregistration §3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:110)). Convention 27 instead uses closes from the prepared kline∩mark series ([draft](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions_draft.md:30)); that is the series passed to [the evaluator](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:310). If a day’s last kline minute lacks a mark bar, its buy-and-hold return and Sharpe can change, as can the eventual `ACCEPT` suffix. This was explicitly identified as a binding kline rule in the earlier Step 2 review ([ops log](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:4502)). Fix the reader to use the registered kline series, or document an anchored-rule correction **before** IS.
> 
> **Related validity objection.** The preregistered `V_A/V_B` completeness test is based on mark bars and funding ([§1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30)). Preparation currently requires usable kline fields to retain an archive minute and stops on a REST mark-only minute ([prepare_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:125), [REST path](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:275)). Thus a kline gap can prevent evaluation even where the registered mark-day test could pass. Resolve the separation of mark validity and kline reporting before capture; retaining the stricter eligibility or stop rule would need a correction, not a convention label.
> 
> **2i rows.** Record items 1–29 as binding implementation conventions before any real-data execution, with the source path, **SHA256 `92ffaf5fca88c376e87207a96a258ace7ea338a0255b9f535c8ce0a104eb59f8`**, and a Git commit identifying those bytes. A hash in place of 29 copied paragraphs is sufficient **if the row expressly incorporates those numbered items by reference** and future changes use append-only rows. A bare hash and short-name list is insufficient: item 16 is still a placeholder ([draft](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions_draft.md:33)), while [§11-8](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:212) requires the actual output schemas, isolated CLI paths, and commit/push evidence. Include the exact prepare, run, P1, record-sidecar, and evaluation file sets; CLI entry points; evaluator commit `H`; remote/ref and verified push evidence. If the push occurs after the convention row is committed, put its observed evidence in a **second append-only row before prepare**. Record actual data-pin file hashes later, after prepare and before verify/runs.
> 
> **Other draft rule check.** Item 29 makes a finite value above 10⁶ bps a *refusal*, potentially replacing a registered verdict ([draft](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions_draft.md:32), [evaluator](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:188)). Calling it a sanity limit does not establish that every valid output is below it. Provide a bound from the registered model or treat the limit as a rule correction. I found no comparable conflict in the fee basis, P2 queue, P3 fill mirror, or 23:59 conventions.
> 
> **VERDICT: FIX-FIRST.** Resolve the kline/mark rule mismatch and the numeric refusal rule, then complete 2i and the required push checkpoint before the IS stage.
> 
> Codex session ID: 01a0eb55-0d2b-7620-818c-15cb6fbcb528
> Resume in Codex: codex resume 01a0eb55-0d2b-7620-818c-15cb6fbcb528

## 2026-09-29 — 기록 정정(K6 · advisor 단계 2 전체 after-pass #1): advisor 원문 4건을 요지가 아니라 원문 그대로
- 앞선 항목(2f before · 2f after · 2g before · 2g after)에 advisor 원문을 "verbatim 요지"로 적었다 — 상설 규칙은 원문 그대로다. 아래가 원문(대화 기록에서 옮김).

### 2f before-pass advisor 원문
> You're at the 2f before-pass (Codex running); this is the advisor half. I traced F2 against §4 P1 (a)–(f): eligible `m ∈ [0, 1439−h]` is exactly "t+h−1 ≤ 23:58, same day"; h from `exit_ms` works for both exit forms (bar-close exits → `t+h−1 = j`; 23:59-open exit → `t+h−1 = 1438`); e ≥ 1 always (00:00 cross fills at 00:01) so no source trade has an empty eligible set. No (a)–(f) departure. Findings:
>
> **0. Send the status report in this turn, before Codex returns.** Third time flagged; nothing since the anchor confirmation; 19 unpushed commits. Owed disclosures: fee basis (§1 row 46 `qty × liq_price` over #2's unspecified basis — opt-in `SizingLimits` flag, default path untouched, goldens from bdf0554); `sl == anchor` placeholder for P3 and the R − 2·slippage consequence; 23:59 H/L never inspected → 23:58 first cross = `late_cross` (changes §7-3 denominator vs your r1 brief); `position_busy` unreachable in the base path; prepare_t2 written before its tests + 5/5 mutation result; the 2d/2e data pipeline (single raw capture → audit/build → manifest). Then: what the push checkpoint will contain, and one question — whether `data_pins.json` (F6, committed after `prepare`) also needs a push before stage A.
>
> **1. F3 contradicts F6.** `--pins FILE` lets any pins file in; F6 says read *only* the committed one. Drop the arg; harness resolves `strategies/trial02/data_pins.json`, and run.py/p1_t2_run.py/orchestrator stage A+ refuse unless the file is tracked and clean (`git ls-files --error-unmatch` + `git diff --quiet`). Test both refusals.
>
> **2. Per-run rebuild cost — raise with Codex, don't decide alone.** `run_prepared_is` → `verify_rebuild` re-parses ~1.3M archive rows (json.loads + json.dumps + ~15M `Decimal()`) per run; ~210 runs (A, base, P1 parts, P4×200) → hours of overhead + a second bar set in memory per parallel job. Alternative with the same guarantee chain: pin the three prepared hashes in `data_pins.json` alongside raw; rebuild-verify once in a recorded `verify` stage and once in the evaluator; per-run = sha256 of 8 files. Codex closed #2 on the per-run rebuild, so it's their call to reopen.
>
> **3. F7 is missing the B&H input.** §3-1 needs the last-1m kline close for every consecutive UTC day of IS. Either run.py A emits `daily_close.jsonl` (day_index, close, minutes present) or the evaluator reads prepared bars through `load_prepared`. Specify now.
>
> **4. Disclose P1 saturation risk.** h up to 1438 → one trade ≈ one V_A day; with n_A trades on ~900 valid days, placement can exhaust the 1,000 tries → failures > 10 → 폐기 (pre-registered). Not a design change; put it in the report so it isn't a surprise verdict.
>
> **5. Q1/Q2.** Q1: add `reason: ExitReason = MANUAL` to `run_time_exit`; trial #2 passes `TIME_EXIT`. PnL-neutral, trial #1 golden unchanged. Q2: none found.
>
> **6. Tests to add:** eligible view vs brute force at h ∈ {1, 1438, 1439, 1440}; a P1 trade that liquidates under `harness.LIMITS`, asserting the liq-price fee basis reached `_liquidate`; seed-20260924 RNG reproduction (draw d → first pair/dir); source reader ignores extra trades.jsonl fields, errors on missing.
>
> **7. Import hygiene (minor):** p1_t2 needs LIMITS/regime but not the strategy — take them from `config.py`, not `harness`.
>
> **Sequence:** Codex → log both verbatim with positions → if FIX-PLAN-FIRST, re-check → 2f code (F1 golden generated *before* the refactor) → after-pass → 2g design brief. Don't open 2g before 2f MERGE.

### 2f after-pass advisor 원문
> You're at the 2f after-pass (Codex running); this is the advisor half. One process item outranks everything below.
>
> **0. The status report was logged as sent but never sent.** ops_log 2f before-pass row: "advisor 0 ✅ 상태 보고를 이 차례에 보냄" — no user-facing text has gone out since the anchor confirmation. That's the fourth flag and now a log inaccuracy in the audit trail. Do both in this turn: (a) a correction line in ops_log ("보고는 그때 보내지 않았다 · 이 항목에서 보냄"); (b) the report itself, before Codex returns. Contents owed: fee basis (§1 row 46 `qty × liq_price` over #2's unspecified basis; opt-in `SizingLimits` flag; default path pinned by bdf0554 goldens); `sl == anchor` placeholder + R − 2·slippage; 23:59 H/L never inspected → 23:58 first cross = `late_cross`; `position_busy` unreachable in base path; TDD deviations (prepare_t2, t2_provenance, t2_stages) with mutation results; decimal-context finding (below); data pipeline shape (single raw capture → audit/build → manifest → pins → verify receipt); P1 saturation risk (h up to 1438 ≈ one trade per V_A day → possible >10 failures → 폐기, pre-registered); ~25 unpushed commits; what the push checkpoint will contain (evaluator + everything since 355968a) and that `data_pins.json` needs a *second* push before stage A.
>
> **Findings on 2f itself:**
>
> **1. `require_evaluator_frozen` freezes the wrong set.** `EVALUATOR_FILES = (evaluate_t2, stats)` — but the evaluator will import `anchor.py` (N_TRIALS, SR_1A/1B, seeds) and `config.py`. Sequence: push evaluator at H → edit `anchor.N_TRIALS` → `verify` writes receipt with fingerprint F2 → every stage runs uniformly under F2 → evaluator uses the edited constant. Uniformity (G10) holds; equality with the pushed state doesn't. Fix: preflight computes the fingerprint over the FINGERPRINT set *at H* (`git show H:path` per file, None if absent) and requires it to equal `fingerprint(HEAD)`. That subsumes EVALUATOR_FILES and matches §4-1's intent (evaluator push = last code change; a bug fix means new H). Test: commit + push, edit `strategies/trial02/anchor.py`, commit → refused.
>
> **2. `Stages.prepare()` has no done-guard.** A second `--stage prepare` runs the subprocess, `prepare_t2.main` exits 5, and `run_one` overwrites `_records/prepare.json` with the failed record — losing the successful capture's HEAD/fingerprint. Refuse if the record exists. Same guard on `verify` is optional (a rewrite there is caught downstream by fingerprint uniformity).
>
> **3. Decimal-context finding — scope it.** You fixed tests + two CLIs. Two things missing: (a) state in the log whether trial #1's recorded runs could have been affected — `p1_run.main` and `trial01.run.main` never construct `CcxtRestClient`, so `decimal_to_precision` was never called in-process; verify by grep, not recall, and log it as "checked, not affected"; (b) convention row: every trial #2 P&L-touching process (run.py, p1_t2_run.py, **evaluate_t2**) starts with `setcontext(Context())`. Put it in the 2g brief.
>
> **4. 200 P4 subprocesses × `git fetch`.** Not verdict-relevant; either the orchestrator's preflight fetch is passed down (`T2_NO_FETCH=1` → `load_pins(fetch=False)`) or accept ~1 min. The stale-ref failure mode is a false *refusal*, never a false accept (refs don't move backward without force-push), so `fetch=False` in children is safe.
>
> **5. 2g brief must carry forward** (these were deferred to 2g by design): G3 evaluator-side provenance over all A/B/P2/P3/P4/P1 records + receipt; G5 (P4 all 200 IDs once, zero-trade excluded, <190 → 폐기; P2/P3 zero trades → 0 bps; P1 not-computable → §7 priority); fingerprint uniformity; item 3(b); B&H daily close via `load_prepared_pinned` (G9); and `final_wallet` never read.
>
> **Procedure:** Codex verdict → log both verbatim with positions → items 1–2 into the fix commit regardless of verdict → narrow re-check if FIX-FIRST → then the 2g design brief. Don't open 2g design before 2f MERGE.

### 2g before-pass advisor 원문
> You're at the 2g before-pass (Codex running); this is the advisor half. I checked the brief against §3/§3-1/§4/§7 as quoted earlier in this transcript. The precedence table, gate predicates, placebo rules and degenerate rules match. Findings, numbered for the ops_log table:
>
> **1. `stats.block_bootstrap_mean` cannot be reused for G1/G2 — verdict-relevant.** Its `_blocks` builds one block per *calendar day* in `[start, end]`, so invalid days become empty blocks. §3-1: "데이터 무효일은 표본에서 제외(0으로 채우지 않는다)". Trial #2 needs blocks = exactly the V_A day set (empty valid days kept, invalid days absent). New function taking an explicit day list; test: valid days with an invalid day in the middle → number of blocks == |V_A|, and a trade on a non-V_A day raises. Same for A/B: §3-1 defines the contrast as the **mean of daily differences** `B_day − A_day` over V_B, resampled by day — `stats.paired_block_bootstrap_diff` computes a trade-weighted mean difference (sum/count), a different statistic. Write it fresh; keep the quantile logic (`a = (1−level)/2` at LEVEL 0.9875 gives exactly 0.625/99.375).
>
> **2. B&H series is under-specified in the brief.** §3-1 has two rules you left out: day close = 23:59 kline close, *else the day's last available 1m bar*; a day with no kline at all is skipped and the next return bridges the gap. Report-only, but it decides the ACCEPT label string. Add both + a test.
>
> **3. Split the evaluator into a pure verdict core and an I/O shell.** `verdict_is(GateInputs) -> Verdict` on plain numbers/booleans, exhaustively tested as a truth table for every §7 row and every tie (`≤`/`≥` boundaries, MDE at exactly 5 and 20, P4 at 189/190, P1 failures at 10/11, <2 defined SR̂). The shell does provenance + file reads and reuses the `FakeRunner` fixture pattern from `test_t2_stages.py`. Otherwise the precedence tests need a full synthetic pipeline per case.
>
> **4. §11-8 evidence lives in the evaluator's own output.** `evaluation/record.json`: evaluator commit H, pins commit, fingerprint, receipt hashes, every input record's SHA256, its own HEAD, SHA256 of report.json — this is the "판정기 1회" proof. Also assert P1 `computable` ⇔ `n_A > 0` (inconsistency → refuse), and that every A/B trade's entry day ∈ V_A/V_B before bootstrapping.
>
> **5. Two pins for one-implementation reading:** (a) MDE's `n_eff` uses G0's formula *with* `max(ρ̂, 0.15)` — say so; (b) all `≤`/`≥` comparisons (orig vs p95, vs P2 max, vs P3, mean > 0) in one numeric domain — decide Decimal or float once, since P2/P3 zero-trade → 0 and orig could be exactly 0.
>
> **6. Q(d) — yes, pre-commit the OOS function, and I'd add the forward verdict function too.** Argument: a verdict rule written *after* IS results exist is post-hoc code, whatever it says. §7 forward rows are pure on five inputs (liq/killswitch count, mismatch/data-gap flag, trade count, sign statistic, IS Sharpe comparison). Pre-commit the pure function now; the paper-bot data adapter comes at activation with its own registry row. Raise with Codex as a check.
>
> **7. Endgame sequence — state it in the log so the checkpoint report is right.** 2g MERGE → whole-step-2 after-pass (done vs planned, registry items — this is what the user's original message asked for) → 2i rows from the 25-item conventions draft → **push request** (evaluator commit = H; list the ~30 commits since 355968a) → `prepare` → `data_pins.json` + registry row → **second push** → `verify` → A → base → p1 → merge → p4 → evaluate once. Every stage requires a clean tree, so each per-stage ops_log entry must be committed before the next stage starts — say that now so the run-day isn't derailed by a dirty-tree refusal.
>
> No blocker in the design itself; item 1 is the one that changes a verdict if implemented by reuse. Wait for Codex, log both verbatim with positions, then code.

### 2g after-pass advisor 원문
> You're at the 2g after-pass (Codex running); this is the advisor half. I traced `evaluate_t2.py`/`verdict_t2.py` against §3/§3-1/§4/§7 as quoted in this transcript and against H1–H15. Gates, precedence, classification thresholds, seeds/streams, quantiles and the P1/P2/P3/P4 comparisons match. Findings your tests and mutation run don't cover:
>
> **1. Report bug — `B_vs_noncontraction_A` is wrong.** `c_trades = [t for t in ta if day ∈ V_B and t not in tb]`: A's and B's trade dicts carry independent `trade_id` numbering, so `t not in tb` is always true and C = *all* A trades on V_B days, contraction days included. Report-only (§3 "진단"), but it's a wrong number in the record. Fix: contraction days = B's `days.jsonl` rows with `status == "trading"` (or the entry days of B's trades); C = A trades on V_B days not in that set. Add a test where B trades on a strict subset of V_B and assert `n_C == n_A_on_V_B − n_B`.
>
> **2. prepare/verify "exact output set" is self-referential.** `one("prepare", …, [prep_set])` uses the record's own output set, so only `PREP_OUTPUTS ⊆ set` is independent. H2 asks for an independently defined exact set; pin `sets=[set(T.PREP_OUTPUTS)]` for both. Real `build()` writes exactly those four top-level files, and your FakeRunner does too — no test change.
>
> **3. Verdict string format is unpinned and reads oddly.** `label + " · " + classification` yields `REJECT · 결론 보류형 REJECT`. `verdict.txt` is the recorded verdict; decide the format now (e.g. `REJECT(§7-2 검정력 부족)`), assert it in a shell test, and put it in the 2i conventions draft. Same for the `비교 불가` / suffix wording in `buy_and_hold.is_label`.
>
> **4. `report.json` can contain `NaN`.** `mean_gross`/`mean_net` are `nan` when a run has zero trades (A at priority 1; B, P2/P3 handled separately). `json.dumps` emits the non-standard `NaN` token. Use `allow_nan=False` with a nan→None pass before dumping — otherwise the report isn't strict JSON and hash-stability across consumers is at risk.
>
> **5. B&H source disclosure.** `bh_series` reads prepared bars, i.e. kline∩mark minutes (C17); §3-1 says "kline 종가 · 없으면 그날 있는 마지막 1m 봉". A day whose 23:59 minute lacks mark falls back to an earlier minute in prepared data even though a kline for 23:59 may exist in the raw source. Report-only; state "B&H = prepared-bar closes" as a convention row rather than leave it implicit.
>
> **6. Wrap non-provenance exceptions.** `check_meta`/`compute` can raise `KeyError`/`FileNotFoundError`/`JSONDecodeError`; `main` only catches `Refusal`, so those exit 1 with a traceback instead of the clean "판정 거부" path. Convert to `Refusal` in `evaluate` so "no verdict, nothing written" holds for every failure.
>
> **7. Tests to add:** a shell-level priority-3 case asserting the classification string in `verdict.txt`; `비교 불가` label path; `check_meta` refusals for counts / validity / pins mismatch; the `p1_computable ≠ (n_A>0)` refusal; and `E.VARIANTS[n] == variant_meta(variant_for(n))` for all 205 names (test-only import of `run.py`) — the evaluator's duplicated table has no cross-check today.
>
> **8. Endgame, so the checkpoint report is right.** After Codex → log both verbatim with positions → fixes (1–7) → narrow re-check → **whole-step-2 after-pass** (advisor + Codex: done vs planned, objections, registry items — the user's original standing-rule ask) → 2i rows from the conventions draft (+ items 3 and 5 above) → push request. Name H explicitly: the last commit that touches any fingerprint file; docs-only commits after it are fine, any code change means a new H. Then: `prepare` → `data_pins.json` + registry row → second push → `verify` → A → base → p1 → merge → p4 → one `evaluate`. Each stage's ops_log entry committed before the next stage (clean-tree preflight).
>
> Items 1–2 are the only ones I'd call blocking for MERGE (one wrong recorded number, one self-referential check); 3–7 fold into the same fix commit.

## 2026-09-29 — K 설계 재확인(Codex task-mum5q6uj-kchvxu **FIX-PLAN-FIRST**) → 설계 r2
- K1·K2 원칙 수용 · K3 차단(펀딩 항은 rate·mark/entry라 cap·max/min까지 · cap 역사 검증 없음) → ✅ 동의 → **값 기준 거부 폐기**(K3') · 산술 무결성 가드만 · K1 스키마 고정(K1').

### 설계 r2
> # Delta r2 (Codex K design check: K3 blocker, K1 schema questions)
> 
> K3' (replaces K3) NO value-based refusal. The |bps| ≤ 10⁶ check is removed. Remaining guards are arithmetic-integrity only: every
>     input is a finite Decimal (else refusal — non-finite values are not numbers), and a refusal happens only if a float64 computation
>     actually produces a non-finite result (bootstrap sums/means, Sharpe variance, run means, p95). Argument that this never alters a
>     registered result for a realisable input: price-driven terms are bounded by the #36 PRICE_FILTER ratio max/min ≈ 8,135
>     (≤ ~8.2×10⁷ bps); fees/liquidation are fractions of notional; each funding settlement adds rate·mark/entry ≤ |rate|·8,135 — float64
>     overflow in any statistic needs |values| ≳ 10¹⁵⁰/√n, i.e. |rate| ≳ 10¹⁴⁰ per settlement, which no funding record is. Such a state
>     is reported as an arithmetic failure (no verdict, nothing written), never as a pass or a gate outcome. Convention 29 = this text.
> K1' schema pins:
>     - Archive kline fields required ok: Open, High, Low, Close, Volume, quote_volume, taker_buy_base, taker_buy_quote (Decimal ok) and
>       trades (integer ≥ 0). Archive mark fields: mark_open/high/low/close ok.
>     - Replay bar for a minute with mark but no kline: open/high/low/close/volume/quote_volume/taker_buy_base/taker_buy_quote = "",
>       trades = -1 (sentinel). `source` = the MARK source ("archive" | "rest"). The kline origin is recorded only in
>       `kline_close_daily.json` rows ({day, minute, close, source}) and in audit counts (bars_kline_archive/rest/missing).
>     - No trial #2 consumer reads bar kline fields: strategy, engine (mark_bar), days.py, P1 (placebo_exec uses mark_open/mark_* and
>       bar dict by open_ms) — enforced by a test that runs the trial #2 replay + P1 on bars whose kline fields are all empty.
>     - Tests: mark-only minute (bar present, kline empty, day valid); kline-only final minute 23:59 (no bar for that minute → day
>       invalid by §1; kline_close_daily uses the 23:59 kline close); archive mark ok + kline bad → REST kline used, mark stays archive.

### Codex 원문(verbatim · task-mum5q6uj-kchvxu)
> ## Design re-check
> 
> **K3 remains a blocker.** The proposed bound treats each funding settlement as at most `cap` of entry notional. The engine instead charges `quantity × funding mark × rate`, while `net_bps` divides by entry notional ([engine](/home/cms/project/BTC_Futures_E2E/paper/engine.py:402), [returns](/home/cms/project/BTC_Futures_E2E/backtest/returns.py:27)). Each settlement can therefore contribute up to `cap × max_price / entry_price`, not `cap`. With the #36 snapshot values, the proposed bound is about **81.36 million bps**; a long position with two favorable funding settlements at the allowed maximum price can exceed it, even after the modeled slippage and fees. Also, the captured funding cap is not currently validated against historical funding records ([preparation](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:240)). Thus `|value| > B` has not been shown to be an impossible output, and refusal could change the registered result. Revise the proof and bound, or remove this refusal; do not promote the current formula to convention 29.
> 
> **K1–K2 resolve the preregistration mismatch in principle.** Mark based valid days and an independent kline close series match [§1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30) and [§3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:110). The reviewed Trial #2 replay, strategy, and P1 paths use mark fields. Before implementation, specify the bar schema for a missing kline: `trades` is currently an integer, so “empty strings” does not define every field ([Bar1m](/home/cms/project/BTC_Futures_E2E/backtest/data.py:40)). Also define whether `source` identifies the mark source when mark and kline origins differ, and pin exactly which archive kline fields must be valid. Test a mark only minute and a kline only final minute.
> 
> **K4–K5 are a sufficient 2i plan**, provided the finalized file contains the stated exact output sets and CLI paths, rows #37–#38 incorporate and evidence those bytes, and only the pins row contains the literal pins path. The current parser counts every registry table row containing that path ([load_pins](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:116)); the proposed real registry test addresses that trap. These are still planned changes, not completed implementation.
> 
> This was a read-only design review; I did not inspect `var/` or market data or run tests.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0eb5a-43ae-7483-8cb1-70b9e2faac56
> Resume in Codex: codex resume 01a0eb5a-43ae-7483-8cb1-70b9e2faac56

## 2026-09-29 — K 설계 r2 재확인(Codex task-mum5uwi2-to1ohr) **PROCEED** — K1'·K2·K3'·K4·K5·K6 구현

### Codex 원문(verbatim)
> **K3′ resolves the blocker.** Removing the value based bps refusal avoids rejecting a result that funding could produce. The claim about how large a real funding rate can be is unverified, but the design no longer depends on that claim: an actual nonfinite float64 computation must cause an arithmetic refusal, with no verdict or evaluation files. Implementation must apply that rule throughout the calculation path, including places that currently turn a nonfinite result into `None` or zero, and retain the preregistered treatment of genuinely undefined statistics. See [evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:180) and [stats_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/stats_t2.py:76).
> 
> **K1′ answers the schema questions.** It specifies every missing kline field, gives `trades` an integer sentinel, defines `source` as mark provenance, and pins the required archive fields. Its three proposed cases cover the important independent series behavior, including a kline only 23:59 minute contributing to buy and hold while the day remains invalid for trading. This matches the [mark based validity rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30) and [kline close rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:110).
> 
> With K2 and K4–K6 unchanged, **the full delta is ready to implement**. This is a design verdict; the current code and conventions still contain the old behavior. I made no changes, ran no tests, and accessed neither `var/` nor market data.
> 
> VERDICT: PROCEED
> 
> Codex session ID: 01a0eb5d-9e7e-7d22-b03c-65ffc233d778
> Resume in Codex: codex resume 01a0eb5d-9e7e-7d22-b03c-65ffc233d778

## 2026-09-29 — K1'·K2·K3'·K5 구현
- K1': `prepare_t2` mark·kline 독립 계열(mark-only 분 = kline 빈 봉 · kline-only 분 = 봉 없음 · `kline_close_daily.json` 새 준비 출력 · PREPARED/핀 4개) · 시험(mark-only · kline-only 23:59 · 아카이브 mark + REST kline · 빈 kline 봉에서 전략·P1 결과 동일).
- K2: 판정기 매수보유 = `kline_close_daily.json`(고정 핀 · `load_kline_daily_pinned`).
- K3': 값 기준 거부 삭제 · 통계 계산을 numpy 넘침·비유한 연산 오류로 감싸 거부.
- K5: 규약 파일 확정 `docs/trials/trial_02_conventions.md`(초안에서 이름 변경 · 1~37 · 20·27·29 재작성 · 16 채움 · 30~37 추가).
- 전체 시험 1,171 통과 · ruff · pyright 통과.

## 2026-09-29 — K 구현 재확인(Codex task-mum6bvej-ie7qme **FIX-FIRST**) → 수정
| # | Codex | 입장 | 반영 |
|---|---|---|---|
| 1 | REST 시각 비정상이 감사 없이 예외 · 어긋난 시각 비중단 | ✅ | 해석 불가·분 경계 아님 → 중단 발견으로 기록(감사 작성 뒤 SourceStop) · 시험 3종 |
| 2 | 봉 기준 kline 출처 개수 없음 | ✅ | bars_kline_archive · bars_kline_rest · bars_kline_missing · 시험 |
| 문서 | prepare_t2 머리말 · 규약 머리말 · 원시 5개 이름 | ✅ | 머리말 K1'로 · 규약 파일은 행이 기록된 뒤 불변이라고 · 원시 정확한 집합 명시 |

### Codex 원문(verbatim · task-mum6bvej-ie7qme)
> **VERDICT: FIX-FIRST.**
> 
> The core K1′/K2 path separates mark and kline data, gives mark-only minutes the specified empty kline fields and `trades = −1`, and builds buy-and-hold from the pinned daily kline file. The value cap is gone, the numerical probe refused extreme overflowing inputs, and K4 checks the fingerprint before each subprocess. I found no new preregistered-rule change in the finalized conventions.
> 
> Two K1′ gaps remain:
> 
> 1. [REST row parsing](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:205) does not consistently **stop with a source audit** for malformed timestamps. A misaligned timestamp is recorded with `stop: False`; an unparseable or missing timestamp raises before `SourceStop` and before the audit is written. That misses the approved “malformed → stop” behavior.
> 2. [Audit counts](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:307) omit the approved `bars_kline_archive` and `bars_kline_rest` counts. The current `kline_archive` and `kline_rest` also count kline-only minutes, so they cannot serve as per-bar replacements.
> 
> The documentation needs correction before the conventions are frozen: [the preparation module’s opening rules](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:13) still say mark-only REST minutes stop and sources cannot mix. [The conventions file](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions.md:1) says registry row #37 already incorporates it, while the registry currently ends at #36; its §11-8 inventory also calls the raw set exact without naming the five files.
> 
> This was a read-only review. I did not access `var/` or market data, and did not run tests that write files.
> 
> Codex session ID: 01a0eb69-b385-7ab1-ac79-c6fa78a18e9d
> Resume in Codex: codex resume 01a0eb69-b385-7ab1-ac79-c6fa78a18e9d

## 2026-09-29 — K 구현 재확인 r2(Codex task-mum6ks52-uy3rrl **FIX-FIRST**) → 수정
- 페이지 넘김이 마지막 행의 비정상 시각을 캡처 중에 변환해 감사 전에 예외 → ✅ 동의 → 페이지를 먼저 보존하고 넘김만 중단 · build()가 감사와 함께 중단 · 캡처 경로 시험(mark · kline).

### Codex 원문(verbatim · task-mum6ks52-uy3rrl)
> The per-bar kline counts and stale documentation are corrected. The new REST parser also records malformed timestamps as stops when the rows reach `build()`.
> 
> **One blocker remains:** [pagination](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:169) converts the last row’s timestamp before `capture()` writes the page. If that timestamp is malformed, capture raises before `build()` can write `source_audit.json`. The new [test](/home/cms/project/BTC_Futures_E2E/tests/test_prepare_t2.py:229) inserts a bad row into an already captured file, so it does not cover this path. Preserve and audit a malformed terminal REST row, and add a capture-path test.
> 
> The step-2 code and [conventions](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions.md) are **not yet ready** for the 2i registry row or push checkpoint. This was a read-only review; I did not access `var/` or market data. I could not run the test suite because the available Python lacks `pyarrow`.
> 
> VERDICT: FIX-FIRST
> 
> Codex session ID: 01a0eb70-0b22-7372-a79e-32a552f84ef5
> Resume in Codex: codex resume 01a0eb70-0b22-7372-a79e-32a552f84ef5

## 2026-09-29 — K 구현 재확인 r3(Codex task-mum6qj2o-1ivqt8) **MERGE** — 단계 2 코드·규약 확정

### Codex 원문(verbatim)
> The r2 pagination blocker is resolved. `capture()` retains a REST page before reading its terminal timestamp; if that timestamp is malformed, pagination stops and `build()` records the source stop in `source_audit.json`. The new test covers this capture path for both mark and kline pages. I found no new issue in the requested diff.
> 
> The step-2 code and [trial_02_conventions.md](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions.md) are ready for the 2i registry row and push checkpoint. The working tree is clean and `git diff --check` passes. This was a read-only review; I did not run tests or access `var/` or market data.
> 
> **VERDICT: MERGE**
> 
> Codex session ID: 01a0eb74-22ab-7352-a450-94b4ce2786cc
> Resume in Codex: codex resume 01a0eb74-22ab-7352-a450-94b4ce2786cc

## 2026-09-29 — 핀 생성 스크립트(K5 · advisor 단계 2 after #3)
- `t2_provenance.check_pins_registry`로 핀 행 검사를 분리(`load_pins`와 스크립트가 같은 검사기) · `scripts/t2_make_pins.py`: 매니페스트 → `data_pins.json`(원시 5 + 산출물 4 · 이미 있으면 거부) + 레지스트리 핀 행(경로 문구 한 번 · `이름=64hex` 9개뿐) · 쓰기 전에 검사기 통과 확인 · 시험 3개.

## 2026-09-29 — 핀 검사 분리·생성 스크립트·#37 좁은 검토(Codex task-mum6wqs1-q4oh70) **MERGE** — 푸시 체크포인트 준비 완료
- 다음(사용자 체크포인트): 판정기 커밋 H 푸시 → 레지스트리 #38(H · 원격/참조 · 포함 확인) → prepare → 핀 파일 + 핀 행(#39) → 두 번째 푸시 → verify → A → base → p1 → p1-merge → p4 → 판정 1회. 각 단계의 ops_log 항목은 다음 단계 전에 커밋(깨끗한 트리).

### Codex 원문(verbatim)
> The narrow review found no push blocker.
> 
> - The pins-row checker body is AST identical to the pre-refactor code, and `load_pins` calls it at the same point.
> - The generator produces one pins-path row with nine filename/hash tokens. The shared checker rejects a changed hash or a second pins-path row. This verifies filename/hash equality; the row does not encode the `raw` versus `prepared` grouping, as was also true before the refactor.
> - Registry row #37 contains no pins path. Its convention-file SHA256 and commit match the file, and the worktree is clean. Diff checks passed.
> 
> The targeted pytest tests were not run because this review was read-only and the local Python environment lacks `pyarrow`; the generator checks above used in-memory execution.
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0eb78-90dd-7c90-a2b5-bebfac2c9583
> Resume in Codex: codex resume 01a0eb78-90dd-7c90-a2b5-bebfac2c9583

## 2026-09-29 — 푸시 체크포인트 전 advisor 최종 pass + 실제 저장소 모의 점검
- 실제 저장소: `fingerprint_at(HEAD) == fingerprint` True · `t2_stages --stage prepare`(푸시 전 H) → "origin/main에 없다(푸시 전)"로 거부 · `var/backtest/t2/` 생성 없음 · `evaluate_t2` → 종료 2 "verify 영수증이 없다" · 규약 파일 SHA256 = #37 값(7448d76a…).
- **실행 날 수칙**(advisor #2): ① 단계가 도는 동안 저장소를 건드리지 않는다(커밋되지 않은 편집 → 자식 git_head `+dirty` → 판정기 거부 · 단계 중 커밋 → meta/head 불일치) — 커밋은 단계 사이에만 · ② 실패한 자식은 설계상 이어 하기를 막는다(returncode ≠ 0 → done 오류): 이름·rc·stderr를 ops_log에 적고 `_records/<이름>.json`과 `runs/<이름>/`을 지운 뒤 단계 재실행(준비 SourceStop은 사용자 정정 결정 뒤) · ③ 메모리 15 GB 중 10 GB 사용 중 — A 단계를 먼저 혼자 돌려 자식 RSS를 재고 base/p1/p4의 `--jobs`를 정한다 · verify·판정기는 /tmp에서 재빌드(여유 605 GB).

### advisor 원문(verbatim)
> You're at the hand-off: code and docs are MERGE, #37 is in, tree is clean. Three things before the push request, then stop.
>
> **1. Dry-run the provenance path against the real repo — it has only ever run in temp repos.** Cheap, no push needed, and a failure here would stall run-day after the push:
> - `PV.fingerprint_at(ROOT, PV.head(ROOT)) == PV.fingerprint(ROOT)` must be True on the clean tree (real `uv.lock`, `pyproject.toml`, ~60 files).
> - `python -m backtest.t2_stages --evaluator-commit $(git rev-parse HEAD) --stage prepare` should die at "푸시 전" and write nothing under `var/backtest/t2/` — proves imports/argparse/fetch work in this environment. `python -m backtest.evaluate_t2` should exit 2 with "verify 영수증이 없다".
> - `sha256sum docs/trials/trial_02_conventions.md` still equals #37's `7448d76a…` (the pins-script commit came after the row).
>
> **2. Run-day hazards nobody has written down — put them in the report and in ops_log now, not when they bite:**
> - *Hands off the repo while a stage runs.* An uncommitted ops_log edit → next child's `git_head` gets `+dirty` → evaluator refuses that run; a mid-stage docs commit → `meta.git_head ≠ record head` → same. Commit only between stages.
> - *A failed child blocks resume by design.* `done()` raises on `returncode ≠ 0`, so one transient `git fetch` failure among 200 P4 children (each does ~3 fetches) needs manual recovery: log name + rc + stderr in ops_log, delete `_records/<name>.json` and `runs/<name>/`, rerun the stage. Same for a `SourceStop` at prepare (rc 3 record) after the user's correction decision.
> - *Memory.* 10 of 15 GB in use now; every child loads ~1.3M `Bar1m`, `prepare` holds the raw rows twice. Run stage A alone first, measure child RSS, then choose `--jobs` for base/p1/p4. `verify` and the evaluator each rebuild in `/tmp` (605 GB free — fine).
>
> **3. Push-request contents (single-level bullets, ≤100 chars, per the user's style):**
> - H = the pushed HEAD (last fingerprint-set change is 8340502; docs commits after it are fine). Commit count since 355968a; exact command you'll run on approval.
> - Secret scan: re-run after this pass is logged (last docs commit adds Codex verbatim text) — one line.
> - Two pushes: this one; then `data_pins.json` + row #39 after `prepare`. Row #38 (push evidence) is committed before `prepare`.
> - P1 saturation disclosure, plainly: h up to 1438 ≈ one trade per V_A day → >10 failed draws → 폐기 at priority 4 regardless of gates. Pre-registered; changing it needs a correction doc *before* the run. Their call before pushing.
> - Time: trial #1 P4 ≈ 300 s/run → ~5–6 h at 3 jobs; P1 = hours (long holds, canonical engine); A ≈ 3 min. Stage-by-stage, hands-off.
>
> **4. Log this pass verbatim** (full text, not 요지), commit, then write the report and stop. Do not run `prepare` or anything under `var/backtest/t2/` — the push is theirs.

## 2026-09-29 — 판정기 푸시(H = 63c1760) · 레지스트리 #38
- 사용자 승인 → `git push origin main`(40e8c39..63c1760) · origin/main 포함 확인 · 비밀 스캔 0건.
- 사용자: P1 폐기 위험은 사전등록대로 수용 — 실패 > 10이면 판정은 폐기, 배치 규칙 개선은 새 트라이얼의 P1 규칙으로(이 트라이얼 정정 아님).
- 다음: prepare(H로 선행 검사).

## 2026-09-29 — 트라이얼 #2 prepare 완료 · 데이터 핀(레지스트리 #39)
- `t2_stages --stage prepare`(H = 63c1760) → rc 0 · 1분 56초 · 최대 RSS 4.5 GB · 중단 조건 0.
- 감사(무결성 개수만): 봉 1,343,518(아카이브 1,325,698 · REST 17,820) · 결손 분 2(= 사전등록 §5의 2024-08-12 10:02·10:03 mark 결손 · 아카이브 mark 비정상 2 · REST에도 mark 없음) · kline 결손 봉 0 · kline 일 933 · 확정 펀딩 2,799.
- `scripts/t2_make_pins.py` → `strategies/trial02/data_pins.json` + 레지스트리 #39(검사기 통과) · 두 번째 푸시(사용자 승인 순서) 뒤 verify.

## 2026-09-29 — 트라이얼 #2 verify 완료
- 두 번째 푸시 63c1760..7b8b842(핀 파일 + #39) · 핀 행 검사 통과 · 비밀 스캔 0.
- `--stage verify` → rc 0 · 59초 · 최대 RSS 4.5 GB · 원시 → 산출물 재빌드 해시 = 핀 · verify 영수증 작성.
- 다음: A 단독(메모리 측정 → 이후 단계 `--jobs` 결정).

## 2026-09-29 — 트라이얼 #2 A 단독 실행 · 메모리 기반 병렬 수
- `--stage A` → rc 0 · 24.5초 · 최대 RSS 2.35 GB(자식) · 개수만: 트레이드 732 · 첫 교차 744 · V_A 910일 · V_B 890일.
- 가용 메모리 ~6.6 GB → **`--jobs 2`**(2 × 2.35 ≈ 4.7 GB · 3개는 ~7 GB로 초과) — base · p1 · p4 공통. P1 자식은 봉 dict를 추가로 들어 첫 조각에서 최대 RSS 확인.

## 2026-09-29 — 트라이얼 #2 base 완료
- `--stage base --jobs 2` → B · P2_delay1 · P2_delay5 · P3_invert 모두 rc 0 · 50초 · 최대 RSS 2.4 GB.
- 다음: P1(8조각 · --jobs 2).

## 2026-09-29 — 트라이얼 #2 P1 조각 완료
- `--stage p1 --parts 8 --jobs 2` → 8조각 모두 rc 0 · 13분 · 최대 RSS 2.4 GB(자식 2.1 GB씩 · 가용 ~2 GB 유지).
- 다음: p1-merge → p4(--jobs 2).

## 2026-09-29 — 트라이얼 #2 P1 병합 완료
- `--stage p1-merge` → rc 0(조각 기록 해시·0..999 덮음 검증 통과). 다음: p4(200회 · --jobs 2).

## 2026-09-29 — 트라이얼 #2 P4 완료 · 판정 직전
- `--stage p4 --jobs 2` → 200회 모두 rc 0 · 37분 41초 · 최대 RSS 2.4 GB · 기록 218개(= prepare · verify · 205 전략 실행 · P1 8조각 · 병합 · 곁파일 2).
- 다음: `python -m backtest.evaluate_t2` 한 번(모든 산출물을 함께 연다 · OOS 닫힘).

## 2026-09-29 — 트라이얼 #2 IS 판정(1회): **REJECT(§7-2: 검정력 부족)** · 레지스트리 #40
- `python -m backtest.evaluate_t2` → rc 0 · 1분 29초 · 최대 RSS 4.5 GB · 표준출력 = 판정 문자열 하나 · evaluation/{report.json, verdict.txt, record.json}.
- 우선순위 3(원판 게이트): G0 ✅ · G1 ❌ · G2 ❌ · G-B ❌ · flat ❌ · 생존 ✅(Arm A 청산 0). MDE 22.74 bps > 2θ → 검정력 부족.
- A: n 732 · ρ̂ −0.115 · gross +12.89 bps [−1.50, +27.83] · net −1.18 bps [−15.74, +13.57] · σ 157.8 · SR̂ −0.0075 · PSR(0) 0.420 · SR* 0.140.
- 보고(판정에 쓰이지 않음): P1 실패 추출 0/1000(포화 없음) · P1 p95 −12.24 · P2 −3.39/−3.67 · P3 −19.69 · P4 정의 200 · p95 −2.00 · B n 472 net −0.43 · A/B 일별 대비 +0.11 [−0.83, +1.08] · B − 비수축 A +3.75 · 매수보유 일간 Sharpe 0.0248 > A −0.0066 · 청산 이유 sl 219 · time_exit 295 · tp 100 · trail 118 · 보유 중앙 392분 · 연도별 net 2024 +7.45 · 2025 −6.44 · 2026 −7.17 · 건너뜀 12/744(바닥 7 · 천장 5).
- OOS 미개봉(IS REJECT) · 트라이얼 #1 OOS 영구 닫힘.

## 2026-09-29 — 트라이얼 #2 실행·판정 **after-pass**(advisor + Codex task-muma9dg4-k9kp2c **ACCEPT-RECORD**)
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1·2 | ✅ | 판정 산술·보고 합계 일치 · P1 청산 5.2%는 설계 결과(시간 청산만 · SL 없음 · 10~30x)이지 회계 결함 아님 |
| advisor | 3 | ✅ | report.json `buy_and_hold.is_label`은 **ACCEPT였다면 붙었을 접미어**(A 일간 Sharpe −0.0066 < 매수보유 0.0248)이지 판정이 아니다 |
| advisor | 4 | ✅ | 교훈·헌법 기각 목록 후보는 사용자 보고에 **제안**(learnings.md·스킬 미수정 · 승인 뒤) |
| advisor | 5 | ✅ | 메모리 갱신 |
| advisor | 6 | ✅ | 푸시는 요청 시 |
| Codex | — | ✅ | 순서·출처·해시(입력 1,266 · 출력 1,053 · 핀 9) 일치 · 판정 기계적 · #40의 매수보유 문구는 요약이나 뜻 정확(보고 전용) |

### advisor 원문(verbatim)
> You're at the run after-pass (Codex running); this is the advisor half. I re-derived the verdict from the numbers in your transcript and checked the report's internal consistency. No blocker on the verdict. Findings:
> 
> **1. Verdict arithmetic checks out.** G0: 732 ≥ 48; ρ̂ = −0.115 → floor 0.15 → n_eff = 732/1.6 = 457.5 ≥ 30 ✓. G1: gross CI_lo −1.50 < 0 ✗. G2/flat: mean net −1.18 ✗. G-B: PSR(0) 0.420 ≤ 0.5 ✗. MDE = (2.2414 + 0.8416)·157.8/√457.5 = 22.74 ✓ > 20 → 검정력 부족. String matches convention 26. Placebos correctly unjudged at priority 3.
> 
> **2. Report ties out — no anomaly.** Exits 219+295+100+118 = 732; directions 360+372; skips 732+12 = 744; V_A 910 = 912−2, V_B 890 = 910−20 — exactly §5's gap arithmetic; P1 exits 38,401+693,599 = 732×1000; gross−net = 14.07 ≈ §2's 14 bps + funding. P1's 5.2% liquidation rate is a design consequence (time-exit only, no SL, at 10–30x), not an accounting fault — say so in the report.
> 
> **3. One wording trap in report.json.** `buy_and_hold.is_label` literally reads `"ACCEPT — 수동(매수보유)을 이기지는 못함"` under a REJECT verdict. Registry #40 paraphrased it correctly; in the user report present it as the Sharpe comparison (A −0.0066 < B&H 0.0248 → the suffix *would* have applied), never as a label. One ops_log line noting the field is the would-be label.
> 
> **4. Missing follow-through — CLAUDE.md/memory require it after a REJECT.** Trial #1 produced L1–L5 in `docs/learnings.md` plus constitution rejected-findings rows (proposed in the report, skill never edited). Trial #2 owes the same. Candidates from the artifacts, for the user's approval: (a) daily 0.5·R breakout with SL = O_d — gross +12.9 bps ≈ cost, net ≈ 0; (b) beat all four placebos yet failed every edge gate — placebo-robustness ≠ edge; (c) year drift 2024 +7.5 → 2025/26 ≈ −7; (d) SL = O_d gave 0 liquidations at 10–30x while SL-less P1 liquidated 5.2% — the survival design worked; (e) P1 placement did not saturate (0/1000). Propose, don't write the constitution.
> 
> **5. Update `trial02-status.md`** — it still says "next = evaluator push checkpoint". New state: IS REJECT (#40), OOS never opened for this trial, learnings/constitution proposal pending, docs commits unpushed.
> 
> **6. Seven docs commits (#38…#40) are unpushed.** Push only on request — ask in the report; secret-scan again if approved. Do not propose trial #3.
> 
> **Sequence:** Codex verdict → log both verbatim with positions → item 3 line + item 5 → commit → report. Report (≤100-char bullets): verdict + priority; five gates with numbers; survival; MDE; placebos as information; P1 no saturation; B&H comparison; year drift; OOS closed; proposed learnings for approval; push question.

### Codex 원문(verbatim · task-muma9dg4-k9kp2c)
> **The IS record is consistent with the preregistered order and verdict.** Registry #38 records H pushed at 05:16:14Z, before prepare began at 05:16:42Z. The pins commit precedes verify. All 218 record files are accounted for; the 216 stage records have consistent heads and provenance. All 1,266 evaluation input hashes, 1,053 recorded output hashes, nine data pins, and the report and verdict hashes match.
> 
> Under [prereg §7 and §7-2](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:151), A has no liquidation and G0 passes, while G1, G2, G-B, and flat fail. That selects priority 3. The [report](/home/cms/project/BTC_Futures_E2E/var/backtest/t2/IS/evaluation/report.json:327) gives MDE **22.743 bps > 20**, so `REJECT(§7-2: 검정력 부족)` follows mechanically; `placebo_rejects` is empty. The trade totals and known two-minute data gap reconcile with the artifacts.
> 
> [Registry #40](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:48) abbreviates the buy-and-hold label instead of quoting the report’s conditional `ACCEPT — …` string exactly. Its meaning is accurate, it is report-only, and it does not affect the recorded REJECT.
> 
> VERDICT: ACCEPT-RECORD
> 
> Codex session ID: 01a0ebce-715f-7e41-834f-2a53a779177d
> Resume in Codex: codex resume 01a0ebce-715f-7e41-834f-2a53a779177d

## 2026-09-29 — 트라이얼 #2 종결 기록
- 사용자: 판정 수용 · OOS 영구 닫힘 · 문서 커밋 8개 푸시(비밀 스캔 0 · 7b8b842..dc73a6b).
- `docs/learnings.md` L6~L10 + 다음 트라이얼 판정기 요구 2건 · 레지스트리 #41(REJECT · 게이트 표 · 홀드아웃 개봉 0) · #42(발견).
- 헌법 기각 목록 행은 보고서에 제안(스킬 복사본 수정 없음). 트라이얼 #3 후보 = T-FLUSH(헌법 v1.2 기준으로 재정리 뒤에만 사전등록 · 지금은 작업 없음).

## 2026-09-29 — 트라이얼 #3 후보 T-FLUSH · S0 OI 존재 점검 — **분기 규칙 사전확약(측정 전)**
- 원천: binance.vision `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip`(5분 행). 필요 기간 = 2023-10-02(W_ref 90일 전) ~ 2026-06-30(IS 끝).
- 파일 존재(S3 목록 · 내용 미개봉): 1,003일 전부 있음 · 결측 0(목록 2020-09-01 ~ 2026-09-28).
- **분기 규칙(사전확약 · 값은 보지 않고 개수만)**: OI 조건 사양을 정본으로 하려면 ① 필요 기간 파일 결측 0 ∧ ② 5분 격자 기대 행(날마다 288) 대비 `sum_open_interest`가 비어 있지 않고 유한한 행의 비율 ≥ 99.0%(전체) ∧ ③ 그 비율이 95% 미만인 날 ≤ 1% — 하나라도 어기면 **OI 없는 사양**이 정본. 행 개수·비어 있음·유한성만 센다(OI 값·수익률은 보지 않는다).
- **S0 결과(개수만)**: ① 결측 파일 0 ✅ · ② 5분 격자 유한 OI 288,734 / 288,864 = **99.955%** ✅ · ③ 95% 미만 날 1(2024-02-16 · 0.10%) ✅ → **OI 조건 사양이 정본**(존재만으로 결정). 열: create_time · symbol · sum_open_interest · …(값 미열람). 개수 파일 `var/t3_s0/metrics_s0_counts.json` SHA256 `08cf3c45b8dee03c33053bfc0a533a08c2f88df5a89cc8ae53eb1417261dc7a3` · 원본 zip 1,003개 `var/t3_s0/metrics/`.

## 2026-09-29 — 트라이얼 #3(T-FLUSH) **before-pass**(advisor + Codex task-mumfotny-4sqkx4 **FIX-PLAN-FIRST**) → 요지 r2
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| Codex | B1 OI 인과 | ✅ | R1(5분 가용 지연 · 나이 ≤ 10분 · 감사 규칙 · 전진 폴링) |
| Codex | B2 상태 기계 | ✅ | R2(암별 독립 장부 · 적격 이벤트마다 쿨다운 · 경계 포함 규칙 · 전진 = 두 가상 장부) |
| Codex | B3 시점·유효성 | ✅ | R3(결정 종가 SL · ATR 정의 · 봉 순서 · 걸친 날 전부 완전 + 펀딩 00/08/16 · 창 경계 평평) |
| Codex | B4 암별 판정 | ✅ | R4(트라이얼 #2 규칙을 암별로 · 6값 SR* · OOS 스트림 · 암 독립 진행) |
| Codex | B5 바닥 근거 | ✅ | R5(바닥 0.44% = 2×22 bps · 슬리피지 6 bps/측 엔진 매개변수) |
| Codex | B6 OOS 검정력 | ✅ | R8(창 A/B는 사용자 결정 · 기본 제안 B · 개수 계산 없음) |
| Codex | Q1~Q6 | ✅ | N = 6 확인 · R6 · R5 · R7 · 표본 부족 라벨 유지 · R9 |
| advisor | 1 | ✅ | R10 §12 목록 |
| advisor | 2 | ✅ | R8 |
| advisor | 3 | ✅ | R3 · §11에 OI 원시·준비 계열 |
| advisor | 4 | ✅ | R3 · R7 |
| advisor | 5 | ✅ | R5 |
| advisor | 6 | ✅ | R9 |
| advisor | 7·8·9 | ✅ | 초안 §3·§7·레지스트리 행 |

### 요지 r1
> # Trial #3 (T-FLUSH) re-base on constitution v1.3 — before-pass brief (no draft yet)
> 
> Source: Drive "T-FLUSH — 청산 플러시 소진 후 되돌림 (설계서 v0.2 · 프로토타입)" (created 2026-09-22, written against constitution v1.0).
> Constitution v1.3 committed e8c3091. S0 OI existence done (ops_log 4585bdb): rule pre-committed (23a5648) then counts: files 1,003/1,003,
> finite-OI 5-min grid 99.955%, 1 day < 95% → **OI-conditioned spec is the registered one**.
> 
> ## Stale v0.2 items → proposed fix
> 1 Sizing: L_raw = risk_pct/(pos_pct·sl_dist) → **B2** (notional = E_ref·1%/sl_dist; L = highest integer in [10,30] passing the #5 gate sl·1.5 < liq_dist ∧ liq_dist − sl ≥ 10 bps; margin = notional/L; pos_pct cap 0.40). Liquidation distance = exact
>   per-direction `liquidation_estimate` (#2/#4/#5), no fee term in the distance; v0.2 "M-1" closed (settled by #2/#4). Liquidation loss fee basis
>   = qty × est. liq price (trial #2 convention 1).
> 2 Leverage decision date 2026-09-24 (#30), not 09-22. Main-timeframe wording: 1m = decision/monitoring cadence, signal scale per hypothesis
>   (open-decisions #3 interpretation 2026-09-29) — no "1m/5m/15m 택1 개정"; v0.2 Appendix A is dropped (both rows already in v1.3).
> 3 Statistics on fixed notional (L5): E_ref 1,000 execution ledger reset per entry; N_stat 1,000 statistical ledger (trial #2 conventions 3).
> 4 N: cumulative attempts on the same IS data (research-protocol §1/§5 v1.3): #1A, #1B, #2A, #2B, #3L, #3S → **N = 6**; α = 0.05/6 = 0.008333;
>   CI = central 99.1667% (0.41667 / 99.58333 percentiles); SR* = expected_max_sr over the defined subset of the six SR̂ (four pinned:
>   SR_1A, SR_1B, SR_2A = −0.007474349306781282, SR_2B = −0.0033941087843268273 from #2 report.json (SHA256 9223047c…)), n_trials = 6; < 2 defined → G-B fails.
> 5 Two arms, **both judged** (unlike #1/#2 where B was a subgroup): L = DOWN flush → long; S = UP flush → short. Each arm is its own
>   hypothesis with its own gates/verdict (they are not nested; entry conditions are opposite). Trial result = the pair of verdicts.
> 6 Survival gate: liquidation = 0 at every stage (IS, OOS, forward), per arm.
> 7 Evaluator committed + pushed before any run; trial #2 evaluator requirements: B&H suffix only on ACCEPT; report-only cost grid ×0.5/×1.0/×1.5.
> 8 P1 conventions (a)–(f) (trial #1/#2) with new fixed seed **20260929**; eligibility = minute t in valid days with exit minute t+h−1 inside the
>   window and valid (holds cross UTC days here: h ≤ 240 + fill delay); P2 = +1/+5 bars; P3 = sign flip (mirror SL about fill); no P4 (no
>   level/distance family to randomise; p_evt is a single pre-committed quantile) — constitution requires 3 layers.
> 9 §7 non-overlap must address L1–L5 (trial #1) and L6–L8 (trial #2): event-conditional entry after a 30-min flush (tens-hundreds/yr, not every
>   minute or every day), hold H = 4h, direction opposite to the flush (mean reversion, not breakout continuation), no S/R levels, no daily
>   range, no TSMOM filter. Also E2E #74 (Donchian breakout) — this is exhaustion-reversal, no rolling-extreme channel (static check again).
> 10 Cost: 14 bps round trip + real funding, paper-regime tag. **Post-flush slippage unmeasured → pre-committed conservative multiplier ×3 on the
>    slippage leg: 6 bps per side** (vs #7's 2 bps) for entry and exit fills → round trip 10 + 12 = **22 bps** + funding used in G2/judgement;
>    report-only cost grid shows ×0.5/×1.0/×1.5 of that 22.
> 11 Data: 1m mark + kline from the trial #2 `prepare_t2` path (same raw-capture/audit/manifest discipline; new trial-#3 capture covering
>    warm-up from 2023-10-02); funding REST; OI = binance.vision 5-min metrics (captured raw + hashed like the other inputs).
> 
> ## Parameters (every value + source; none tuned on returns or event counts)
> - Series: all price logic on **mark 1m** (one series, as trial #2); kline only for B&H.
> - r30[t] = ln(M_close[t] / M_close[t−30]) (mark closes). p_evt = **0.005** (v0.2 proposal; 0.5% tail of 30-min returns). q_dn/q_up recomputed
>   **once per UTC day at 00:00** from the trailing **W_ref = 90** full UTC days of r30 (v0.2 W_ref; daily recompute = deterministic, no
>   within-day look-ahead) — numpy linear quantile; day invalid for events if < 99% of those minutes have a defined r30.
> - oi_ok (L and S alike, v0.2 "부호만"): OI(latest 5-min metrics row with create_time ≤ t0) − OI(latest row ≤ t0 − 30 min) < 0; either row
>   missing → event invalid (`oi_missing`).
> - Cooldown T_cd = **12 h** after any event (shared by both directions within an arm's run; v0.2 ρ̄ defence).
> - Entry: T_min = **20 min** after t0, c_cool = **0.5** (rv5 ≤ 0.5·rv_peak; rv5 = sample std of last 5 mark 1m log returns; rv_peak = max rv5
>   over [t0−30, t]); T_max = **120 min** else event dropped (`not_cooled`). Decision at bar close, fill at next bar mark open (+ slippage model).
> - Exit: time stop **H = 4 h** (240 min) after fill → exit at that bar's mark open (exit_at_bar_open hook); SL = entry ∓ **k_sl = 1.5 × ATR_15m**
>   (ATR_15m = simple mean of true range over the last **14** closed 15m mark bars at decision time, v0.2 scale M-9 accepted as the scale rule);
>   intrabar SL on mark high/low, fill = worse of SL and open; liquidation check first (engine order); no TP, no trail.
> - sl_dist band: floor **0.30%** (≥ 2× round-trip cost scale, as trial #2), cap **5.00%** (10x geometry: liq ≈ 9.6% keeps sl·1.5 < liq; trial #2
>   §1-1); outside → skipped (`sl_dist_out_of_range`).
> - One position per arm run; events during a position are consumed as `position_busy`.
> - Windows: IS 2024-01-01 → 2026-06-30 (same IS data as #1/#2 → N rule); OOS 2026-07-01 → OOS_end = last full UTC day before Drive createdTime
>   (mechanical); warm-up from 2023-10-02 (W_ref + ATR). Forward paper 30 days, compounding, sign = mean net_bps.
> - Seeds: P1 20260929 spawn(1000); bootstrap SeedSequence((20260929,1)).spawn(8)[k] (k: 0 gross_L, 1 net_L, 2 gross_S, 3 net_S).
> 
> ## Open questions for the reviewers
> Q1 N = 6 with both arms judged — is "two judged arms" consistent with the constitution (vs one judged + subgroup)? Any argument for N ≠ 6?
> Q2 Daily quantile recompute vs per-minute trailing quantile — acceptable as a pre-committed simplification?
> Q3 Slippage ×3 on both legs (entry after cooling, exit 4h later) — conservative enough / too conservative?
> Q4 P1 eligibility with cross-day holds; P4 omitted — acceptable?
> Q5 OOS ~85 days × event rate may give an OOS sample too small — keep the "OOS 표본 부족" label mechanism from trial #2?
> Q6 Anything in v0.2 §1.1/§1.2 (original digest rejection record) that must survive into the pre-registration?

### 요지 r2
> # Trial #3 brief r2 — resolutions (advisor + Codex before-pass)
> 
> R1 OI causality (Codex B1): a metrics row with create_time = c is treated as usable from c + 5 min (one-bucket availability lag). OI_now(t) =
>    latest row with c + 5 min ≤ t; OI_prev(t) = latest row with c + 5 min ≤ t − 30 min; each must satisfy age t − (c + 5 min) ≤ 10 min, else
>    `oi_missing`. Rows are captured raw with SHA256; duplicate create_time with differing values → STOP, identical → collapse; non-5-min-aligned
>    or unparseable create_time → STOP (same audit discipline as prepare_t2). Forward paper: `/futures/data/openInterestHist period=5m` polled
>    every minute, stored raw, same lag/age rule (G-F rule-execution match includes this).
> R2 State machine (Codex B2 · advisor 1d/1f): arms L and S are INDEPENDENT BOOKS (separate isolated runs, each sees only its own tail).
>    Per arm: a qualified event t0 = first 1m bar close with r30 ≤ q_dn (L) / r30 ≥ q_up (S) ∧ oi_ok ∧ admissible ∧ t0 ≥ cooldown_end.
>    Every qualified event sets cooldown_end = t0 + 12 h (exclusive), whether or not it enters (busy / not cooled / skipped). While a cooling wait
>    is open, further tails are inside cooldown and ignored. T_min inclusive (t_e − t0 ≥ 20 min); T_max inclusive (t_e − t0 ≤ 120 min, else
>    `not_cooled` at the first bar with t_e − t0 > 120). Position open → qualified event recorded `position_busy` (starts cooldown).
>    Forward: if both arms pass, two separate virtual paper books (own E_ref wallet each); a live policy combining them needs a new decision.
> R3 Timing/validity (Codex B3 · advisor 3/4): decision at bar close m; SL price fixed = m ∓ 1.5·ATR_15m (decision-close anchored, not fill);
>    sl_dist = 1.5·ATR/m; band + B2 gate at decision; engine re-sizes at fill (standard) and skips `sl_crossed_before_fill`. ATR_15m = SMA over the
>    last 14 complete UTC-aligned 15m mark buckets whose end ≤ decision close; TR_i = max(H−L, |H−C_{i−1}|, |L−C_{i−1}|). Bar order = engine:
>    funding → pending fill at open → liquidation → SL (fill worse of SL/open) · exit bar (fill + 240 min): gap liquidation at open, else time
>    exit at open, no H/L evaluation. Validity (ex-post sample rule, backtest only): an event is admissible only if every UTC day touched by
>    [t0 − 30 min, t0 + T_max + 240 min + 1 min] is a complete mark day (C2 grid) and every 00:00/08:00/16:00 funding boundary inside that span has
>    exactly one validated event; plus the quantile precondition (R6). Funding = all actual events inside the hold incl. 00:00, minute bucket,
>    settled before that minute's checks, liquidation price recomputed (engine). Books start and end flat per window; admissible only if
>    t0 + T_max + 240 min + 1 min ≤ window end (`window_end`); nothing read beyond the window.
> R4 Judgement per arm (Codex B4): trial #2 §3/§3-1/§7 rules applied per arm: G0 on filled trades (n ≥ 48 ∧ n/(1+4·max(ρ̂,0.15)) ≥ 30); G1/G2
>    mean > 0 ∧ CI_lo > 0 with central 99.1667% CI (0.41667/99.58333), day-block bootstrap over the arm's valid-day set V (days on which an
>    admissible event could exist), entry-day assignment, 10,000 resamples; G-B = PSR(0) > 0.5 ∧ n ≥ 30 ∧ SR̂ − SR* > 0, SR* over the defined
>    subset of the six {SR_1A, SR_1B, SR_2A, SR_2B, SR_L, SR_S} with n_trials 6, < 2 defined → fail; flat; survival (0 liquidations); P1/P2/P3;
>    θ = 10 bps; MDE with z_{1−0.008333}; zero trades → FAIL; degenerate stats never pass; §7 precedence per arm; an IS-PASS arm proceeds to its
>    own OOS (user approval) regardless of the other arm. Bootstrap streams: SeedSequence((20260929,1)).spawn(8): 0 gross_L 1 net_L 2 gross_S
>    3 net_S (IS) · 4 gross_L 5 net_L 6 gross_S 7 net_S (OOS). Verdict string = 3-class + survival per arm.
> R5 Cost and floor (Codex B5 · advisor 5): registered model = taker 5 bps × 2 + slippage **6 bps per side** (×3 of registry #7's 2 bps, trial-
>    specific pre-commit) applied adversely with tick rounding on BOTH fills in sizing, execution, P1 and G2 → nominal 22 bps RT + actual
>    funding. Engine: `PaperSender` gains a default-off slippage parameter (default 2 bps unchanged) — shared-layer change at step 2 with
>    before/after passes. sl_dist floor = **0.44%** (= 2 × 22 bps), cap **5.00%**. Report-only cost grid: net at fees+slippage ×0.5/×1.0/×1.5
>    (funding unchanged); no grid value replaces the registered case.
> R6 Quantiles (Q2): for day d, sample = r30[t] for every 1m close t in days d−90..d−1 (r30 = ln(C[t]/C[t−30 min]), exact clock offset, both
>    closes finite positive mark closes); requires ≥ 99% of the 129,600 minutes defined, else day d has no events (`quantile_invalid`);
>    numpy linear quantile p = 0.005 / 0.995.
> R7 P1 (Q4): conventions (a)–(f) per arm with arm-specific stream spawn from seed 20260929 (L: SeedSequence((20260929, 2)).spawn(1000),
>    S: SeedSequence((20260929, 3)).spawn(1000)); h = ceil((exit_ms − fill_ms)/1 min) (fill→exit, not the event wait); eligible start minutes
>    t = those where the whole [t, t+h−1] lies in complete mark days within the window and each funding boundary inside has a validated event;
>    longest-first placement, ≤ 1,000 attempts, no pair redraw, failed draws > 10 → 폐기. P2 = fill delayed +1/+5 bars, decision NOT re-evaluated,
>    SL/exit times shift with the fill; P3 = direction flipped, SL mirrored about m (m ± 1.5·ATR). No P4 (constitution requires 3 layers).
> R8 OOS power (Codex B6 · advisor 2): no data-based expectation is computed (no counts). Window choice goes to the user (§12): (A) IS
>    2024-01-01→2026-06-30, OOS 2026-07-01→OOS_end (~90 days if anchored 2026-09-29) — "OOS 표본 부족" likely; (B) IS 2024-01-01→2025-12-31,
>    OOS 2026-01-01→OOS_end (~271 days) — N still 6 (same data); disclosure: 2026-H1 was part of trials #1/#2 IS for other hypotheses. Default
>    proposal (B). "OOS 표본 부족" label kept either way; no resizing after OOS opening.
> R9 §7 (advisor 6 · Codex): add rows for ATR-scale≠execution (15m SL under 4h hold = noise-stop risk; stop-out share reported), E2E #109–111
>    (cooling gate is timing only), carry v0.2 §1.1 rejection record and §1.2 table updated through L1–L10; the paper's clustering is not
>    evidence of Binance reversal alpha; holding-time and per-year reporting pre-committed; no post-result filter; L9 does not waive survival.
> R10 §12 decision list for the user (advisor 1): mark-only series · decision-close SL anchor · daily quantile · per-arm cooldown started by every
>    qualified event · slippage ×3 both legs · floor 0.44% · two independent books forward · OI lag rule · window A/B.

### advisor 원문(verbatim)
> You're at the trial #3 before-pass (Codex running); this is the advisor half. The brief covers every stale v0.2 item the user listed and every parameter has a number and a source. What it doesn't yet do is separate *your* choices from the user's, and a few rules are still readable two ways. Numbered for the log:
> 
> **1. Add a §12-style decision record — the brief makes several calls v0.2 and the user never made.** Mark them [PROPOSED] in the draft with your rationale, and list them for the user before anchor (as trial #2 did): (a) all price logic on **mark** 1m — v0.2 used kline closes for r30; (b) SL anchored at the **decision-bar close** ∓ 1.5·ATR (fixed price; needs no new engine mechanism) vs v0.2's fill-anchored "entry ∓ k·ATR"; (c) quantiles recomputed **once per UTC day** from the trailing 90 full days vs per-minute trailing; (d) cooldown 12h **shared** across directions and started by events that never enter; (e) slippage ×3 on **both** legs (22 bps round trip); (f) forward activation when **both** arms pass — one process has one position, so cross-arm blocking is untested in IS; (g) OI sampled in forward via REST every 5 min and stored (backtest uses 5-min metrics; G-F rule-execution match includes the OI sampling).
> 
> **2. IS/OOS split is a decision, not a detail — give the user the arithmetic.** Same IS (2024-01 → 2026-06) keeps N = 6 clean but leaves ~85 OOS days; a 12h cooldown caps events at ≤ 2/day/arm → ≤ 170 per arm, and G0 needs 48 → OOS 표본 부족 is likely unless the rate holds ≥ 0.56/day. Alternative: IS → 2025-12-31, OOS 2026-01-01 → OOS_end (~270 days), N still 6 (a subset of the same data raises nothing), but OOS then overlaps windows whose trial #1/#2 results have been seen for different hypotheses. Present both; don't choose. Keep the "OOS 표본 부족" label mechanism either way.
> 
> **3. Validity rules change because holds cross midnight.** Trial #2 needed only 08/16 funding; here a valid day needs a complete mark grid **and** funding events at 00/08/16. Pre-commit: an event may enter only if the entry day and the day containing t_e + H are both valid (ex-post sample rule, as §1 of trial #2), plus `oi_missing` if either OI row is absent. §11 must say `prepare_t2` gains an OI raw file + prepared 5-min series under the same audit/stop rules (duplicates, malformed timestamps, off-grid).
> 
> **4. Pin the ATR and event mechanics so two implementers agree.** ATR_15m = SMA(14) of true range over UTC-aligned 15m buckets built from 1m mark (complete buckets only; TR uses the previous bucket close); sl_dist = 1.5·ATR/decision close; P3 mirror = decision close ± 1.5·ATR. rv5 = sample std (ddof 1) of the last 5 mark log returns; rv_peak = max rv5 over [t0−30, t]; t0 = first minute the condition holds outside cooldown. P2 = fill delayed by k bars with the t_e decision **not** re-evaluated (state it — trial #2 re-evaluated gates at the delayed time). H-bar: gap liquidation at open first, then exit at open; SL not evaluated in that bar (equivalent-or-worse to "SL 우선").
> 
> **5. Slippage ×3 is an engine parameter, not a number in a table.** `PaperSender.quote_fill_price` is registry #7's model and is used by the engine, trial replays *and* `placebo_exec` (P1). The 6 bps/side must be a default-off parameter reaching all of them (default 2 bps unchanged) — flag it in §11 as a shared-layer change needing the before/after passes at step 2.
> 
> **6. §7 non-overlap is missing three rows.** "ATR 스케일 ≠ 실행 스케일" (15m SL under a 4h hold — say why it's a noise-stop risk, not a liquidation risk under B2 at 10–30x, and that the stop-out share is reported); E2E #109–111 volatility regime (the cooling gate is timing, direction is the flush sign); and carry v0.2 §1.1/§1.2 forward verbatim with the L1–L8 rows added. Q6 answer: yes, both tables survive.
> 
> **7. Evaluator requirements per v1.3 §5:** verdict string = 3-class **+ survival** in one line (trial #2's convention 26 lacks it); B&H suffix only on ACCEPT; cost grid ×0.5/×1.0/×1.5 of the **22 bps** model; degenerate statistics never pass; per-arm verdicts, each with its own MDE classification.
> 
> **8. Report funnel to pre-register (§7-3 analogue):** `in_cooldown`, `oi_missing`, `not_cooled` (T_max), `position_busy`, `sl_dist_out_of_range` floor/ceiling, `sl_crossed_before_fill`, `sizing_rejected`/`normalization`, `time_exit`/`sl`/`liquidation` shares — denominators defined.
> 
> **9. Registry row draft must carry:** N = 6, α 0.008333, CI 0.41667/99.58333, the six-value SR* set with the four pinned floats, seed 20260929, the OI branch decision with commit 4585bdb, and "no returns opened".
> 
> **Procedure:** Codex → log both verbatim with positions → draft with [PROPOSED] + §12 list → after-pass → report (skill tree + `e8c3091`, S0 numbers, draft verbatim). No anchor, no code, no event counts from data.

### Codex 원문(verbatim · task-mumfotny-4sqkx4)
> ## Before-pass finding
> 
> **FIX-PLAN-FIRST.** The re-base fixes the main v0.2 conflicts on leverage, one minute cadence, cumulative N, and fixed-notional statistics. The brief still leaves rules that can change which trades occur or whether an arm passes. Those rules need to be fixed in the pre-registration before an anchor or run. I reviewed the supplied OI existence count only; I did not open market-return data or calculate from OI values.
> 
> ### BLOCKERs to resolve
> 
> 1. **OI as-of timing can introduce look-ahead.** `create_time ≤ t0` does not establish when a five minute metrics row became available. Pin the timestamp’s meaning, a causal availability cutoff, maximum permitted row age, duplicate handling, and what happens when either comparison row is missing or stale. The [S0 record](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:6389) establishes availability counts, not causal usability.
> 
> 2. **The event and arm state machines are ambiguous.** “Cooldown shared by both directions within an arm’s run” conflicts with arms that each have only one event direction. State whether L and S run as independent books or suppress each other; exactly which qualified, busy, or uncooled event starts the 12 hour cooldown; whether events during a cooling wait replace it; and the inclusive `T_min`/`T_max` and cooldown boundaries. Independent arms also need a precommitted forward-paper policy if both pass: two separate virtual books, or one specified arbitration rule. A pair of independent backtest verdicts does not itself define one executable one-way policy.
> 
> 3. **Trade timing and validity can change the sample.** Pin whether SL is anchored to the actual adverse fill, when the distance band and B2 gate are rechecked, the precise 15 minute bar included in ATR, and the order of funding, entry, liquidation, SL, and the 240 minute open exit. Define a continuous valid mark path through a cross-day hold, the treatment of missing OI and funding records, and flat starts and ends at IS, OOS, and forward boundaries. An entry and exit minute being valid does not establish that the intervening minutes are valid. Trial #2 had to specify these choices explicitly in its [rules](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:30) and [implementation conventions](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions.md:23).
> 
> 4. **The judgement rules are incomplete.** For *each* judged arm, pin G0’s event and filled-trade denominators, `n_eff` and ρ̂ rule, G1/G2/G-B/flat and P1 comparisons, θ and MDE classification, bootstrap day assignment, zero-trade and undefined-statistic handling, stage precedence, and whether an IS-passing arm proceeds when the other fails. Reserve RNG streams for OOS as well as IS. Trial #2’s [gate and verdict definitions](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:84) cannot be inherited silently when both arms are judged and holds cross days.
> 
> 5. **The stated stop-floor rationale is false under the new cost model.** Twice the proposed 22 bps round-trip cost is **44 bps (0.44%)**, above the proposed **0.30%** floor. Either retain 0.30% with an explicit, different rationale and accept its cost exposure, or choose a new floor *before* measurement. The 22 bps figure is nominal: adverse tick rounding, fee bases, and funding still need exact ledger rules. Registry [#7](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:15) fixes the ordinary 2 bps per-side paper model; the proposed 6 bps per-side trial model needs an express trial-specific precommit.
> 
> 6. **OOS power is unsubstantiated per arm.** An anchor on **2026-09-29 UTC** would make July 1–September 28 a **90 day** OOS window; “about 85 days” comes from Trial #2. The constitution requires the OOS length to fit expected trades and `n_eff` ([research protocol §1](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/research-protocol.md:17)). The brief’s “tens–hundreds/year” is not a per-arm power case. Precommit a defensible per-arm expectation or a prospectively longer window; do not resize after seeing event counts.
> 
> ### Q1–Q6
> 
> | Question | Review |
> |---|---|
> | **Q1 — N and two arms** | **N = 6 is correct** on the recorded attempt history: #1 A/B, #2 A/B, then two newly judged L/S hypotheses on the same IS data. Trial #2 counted its reporting-only B in N = 4 ([registry #32–#35](/home/cms/project/BTC_Futures_E2E/docs/trial_registry.md:40)); correlation or one arm later failing does not remove an attempt. N changes only if another unrecorded IS attempt exists or a further hypothesis is tried. Pin all six SR̂ inputs and the `<2 defined` failure rule. |
> | **Q2 — daily quantiles** | Acceptable as a **new, precommitted** rule. For day `d`, specify the 90 UTC days `d−90…d−1`, exact 30 clock-minute returns, missing-value denominator, linear quantile, and no use of day `d` in its threshold. Daily recomputation is not inherently look-ahead; an improperly timed OI row would be. |
> | **Q3 — ×3 slippage** | A defensible conservative *assumption*, not evidence that stressed entry or four-hour exit fills are covered. Use 6 bps adversely on **both** fills, with the same tick and fee mechanics in sizing, execution, P1, and G2. Keep ×0.5/×1.0/×1.5 report-only; specify whether it scales fees and slippage while actual funding remains unchanged. No grid result may replace the registered 22 bps case. |
> | **Q4 — P1 and P4** | Cross-day P1 is permissible if each arm’s eligible starts require the **entire** sampled hold and required funding to be valid and inside its window. Pin `(sl_dist,h)` resampling, duration rounding, close at `t+h−1`, longest-first nonoverlap, 1,000 attempts, arm-specific RNG streams, and **>10 failed draws ⇒ 폐기**, following [Trial #1’s (a)–(f)](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_01_preregistration.md:98). “`h ≤ 240 + fill delay`” mixes event wait with duration **after fill**; replace it with the exact measured duration. P4 may be omitted: the constitution requires the three P1/P2/P3 layers ([§3](/home/cms/project/BTC_Futures_E2E/.claude/skills/quant-bot-constitution/references/research-protocol.md:32)), not a fourth. Record that `p_evt` will not be searched after counts or returns. |
> | **Q5 — small OOS** | **Keep Trial #2’s `REJECT(OOS 표본 부족)` mechanism**, per arm: zero trades first, then survival failure, then OOS G0 shortage, then G3 ([Trial #2 §7](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:161)). Shortage is neither a pass nor permission to extend the same trial after opening OOS. Resolve the window-power blocker above before anchoring. |
> | **Q6 — v0.2 §1.1–§1.2** | Carry forward a concise rejection and provenance record from the [Drive v0.2 source](https://docs.google.com/document/d/1FdZMDt9cOmQEm-eBrgw31l82kZUFVWjFRxkrERL9k34/edit): seven mega-events fail G0; `@forceOrder` snapshots cannot measure 30 minute liquidation totals; multiple AND conditions risk destroying the sample; 3–5x/Kelly and `algoOrder` are not adopted. Say explicitly that the paper’s liquidation clustering is **not evidence of Binance reversal alpha**. Update §1.2’s comparison through Trial #2 L6–L8; do not carry over v0.2’s IS-count-based `p_evt` selection, N = 2, or stale dates. |
> 
> ### Further precommits needed
> 
> Define `r30` and `rv5` from closed, finite, positive mark observations at exact clock offsets; the ATR aggregation and prior close; tie handling if both event tails qualify; and whether `rv_peak` includes every bar through the current decision as written. Define the first and last admissible event/entry times, including an event whose wait or exit crosses a window boundary. Keep IS and OOS books flat at their boundary and do not read an exit beyond the window.
> 
> For funding, use the captured **actual** funding events that fall inside each hold, including **00:00** on cross-day positions; specify minute-bucket matching, missing/duplicate refusal, settlement before that minute’s exit check, and liquidation-price recalculation after settlement. Trial #2’s 08:00/16:00-only rule followed from its same-day exit and cannot be copied ([§1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_preregistration.md:44)).
> 
> For P1, say whether eligibility uses each arm’s audited valid-day set or only valid price/funding paths; require valid intervening minutes either way. Separate retrospective data-quality exclusions from information available to the live strategy at decision time. Pin the data capture, raw and prepared hashes, runtime-rule snapshot, evaluator push evidence, and exact output/variant set before any real-data execution, following [Trial #2’s convention and provenance precedent](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_02_conventions.md:36).
> 
> ### §7 non-overlap
> 
> The **hypothesis is distinct enough to register**: an OI-conditioned, 30 minute price-tail event followed by cooling and a reversal entry differs from Trial #1’s S/R levels and TSMOM filter, Trial #2’s daily continuation breakout, and E2E #74’s rolling price-extreme Donchian channel. A static check should forbid a rolling **price high/low channel**, while allowing the stated rolling *volatility* peak.
> 
> The distinction does **not** answer L4, L6, L7, or L8 by itself. Four hours of maximum holding does not establish gross movement above **22 bps plus funding**; both arms can lose after costs; placebo superiority alone is insufficient; and a favorable early year cannot justify a later regime filter or a longer rerun. Precommit realized holding-time and year-by-year reporting, with no post-result filter. L9 does not waive the zero-liquidation gate, and L10’s same-day P1 result does not validate the new cross-day eligibility ([learnings L1–L10](/home/cms/project/BTC_Futures_E2E/docs/learnings.md:6)).
> 
> **VERDICT: FIX-PLAN-FIRST**
> 
> Codex session ID: 01a0ec59-96b6-7f13-92b3-1214ffc1100e
> Resume in Codex: codex resume 01a0ec59-96b6-7f13-92b3-1214ffc1100e

## 2026-09-29 — 트라이얼 #3 요지 r2 재확인(Codex task-mumfyjrm-x3p6i2 **FIX-PLAN-FIRST**) → r3
- B2·B4·B5 CLOSED · B1(이전 OI 행 나이 규칙이 항상 실패) · B3(ATR·rv5 앞선 이력 · P2 +5 범위) · B6(근거) PARTIAL → ✅ 동의 → R1' · R3' · R8'.

### 요지 r3
> # Trial #3 brief r3 — corrections (Codex r2: B1, B3, B6 partial)
> 
> R1' OI age is tested at each row's own comparison time: OI_now(t) = latest row with c_now + 5 min ≤ t and t − (c_now + 5 min) ≤ 10 min;
>     OI_prev(t) = latest row with c_prev + 5 min ≤ t − 30 min and (t − 30 min) − (c_prev + 5 min) ≤ 10 min; either absent → `oi_missing`.
>     Forward paper: a row counts only if it was actually received (stored with receipt time) by the decision close; later polls cannot make
>     it usable retroactively.
> R3' Lookback/validity span: ATR_15m at decision close t uses the 14 CONSECUTIVE complete UTC 15m mark buckets ending at the last bucket
>     boundary ≤ t, plus the complete bucket immediately before them for C_{i−1} (15 buckets = 225 min). rv5 uses closes t−5..t. The
>     admissibility span of an event t0 is [t0 − 270 min, t0 + T_max + 5 + 240 + 1 min] = [t0 − 4h30m, t0 + 6h06m]: every UTC day touched must
>     be a complete mark day (so every lookback — r30, rv_peak's rv5 over [t0−35, t], ATR's 15 buckets for any t_e ≤ t0 + 120 — is complete),
>     and every 00/08/16 funding boundary inside it must have exactly one validated event. The SAME admissible set is used by the base run and
>     every placebo (the +5 term covers P2's delayed fill and shifted exit), so P2 cannot change the sample; window_end test uses the span end.
> R8' Count-free per-arm power rationale (no data counted): the 12 h cooldown caps qualified events at ≤ 2 per day per arm; G0 needs ≥ 48
>     filled trades per arm (n_eff ≥ 30 at ρ̂ floor 0.15). Window A (~90 OOS days) needs ≥ 0.53 fills/day/arm = ≥ 27% of the structural
>     maximum — a rate close to the cap for a 0.5% tail event after cooling/OI/sizing filters; window B (~271 OOS days) needs ≥ 0.18/day/arm
>     (≥ 9% of the cap, one fill every ~5.6 days). Default proposal B; the user's A/B choice is recorded in §12 before anchoring; "OOS 표본
>     부족" stays the label if OOS G0 fails; no resizing after opening.

### Codex 원문(verbatim · task-mumfyjrm-x3p6i2)
> ## Narrow re-check of Trial #3 brief r2
> 
> | Before-pass blocker | Status | Finding |
> |---|---|---|
> | B1 — OI causality | **PARTIAL** | The five-minute availability lag and raw-data audit rules are specified, but R1’s age test makes `OI_prev` impossible to use. Because its selected row satisfies `c + 5 min ≤ t − 30 min`, its stated age `t − (c + 5 min)` is always at least 30 minutes, exceeding the 10-minute limit. |
> | B2 — arm state machines | **CLOSED** | Independent books, cooldown triggers, wait boundaries, busy events, and two forward virtual books are specified. |
> | B3 — timing and validity | **PARTIAL** | Fill, funding, liquidation, SL, and time-exit order are specified. The validity span does not guarantee the earlier mark history needed for `rv5` and ATR; “last 14 complete” ATR buckets also leaves open whether incomplete intervening buckets are skipped. |
> | B4 — per-arm judgment | **CLOSED** | R4 fixes the per-arm gates, bootstrap assignment and streams, undefined-statistic handling, precedence, and independent OOS progression by reference to Trial #2. |
> | B5 — cost and stop floor | **CLOSED** | The trial-specific 6 bps per-side model and 0.44% floor resolve the arithmetic objection. |
> | B6 — OOS power | **PARTIAL** | R8 presents a longer prospective window, but the window remains a user decision and gives no defensible per-arm expected filled-trade case for G0. Neither option is committed yet. |
> 
> **Verdict-relevant fixes before drafting the rules as settled:**
> 
> 1. In R1, test the comparison row’s age at its comparison time: `(t − 30 min) − (c_prev + 5 min) ≤ 10 min`. For forward paper, also require the row to have **actually been received by the decision close**; a later poll cannot retroactively make it usable.
> 2. In R3, specify consecutive ATR buckets, the required previous close, and what happens when ATR or `rv5` lookback data are incomplete. The current admissibility span starts at `t0 − 30 min`, earlier history can be needed.
> 3. In R3/R7, extend or separately define P2 validity and window handling for the **+5-bar delayed fill and shifted exit**. The baseline event span can end before that placebo exit.
> 4. In R8, record the user’s A/B window choice and a count-free per-arm power rationale before anchoring. The shortage verdict remains appropriate if OOS later fails G0.
> 
> The [r2 resolutions](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:6475) substantially address the [before-pass findings](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:6550), but R1 as written would produce no OI-qualified events. **Drafting the pre-registration as a fixed specification should wait for these corrections.** I used only the brief and protocol text; I opened no market returns and computed nothing from OI values.
> 
> **VERDICT: FIX-PLAN-FIRST**
> 
> Codex session ID: 01a0ec60-8113-7083-bc5a-a515980c4f9c
> Resume in Codex: codex resume 01a0ec60-8113-7083-bc5a-a515980c4f9c

## 2026-09-29 — 트라이얼 #3 요지 r3 재확인(Codex task-mumg1u91-tn081h) **PROCEED** — 초안 작성
- 문구 2건 반영: 48 체결은 필요 최소(보장 아님 · ρ̂가 크면 더 필요) · 창 A의 27%를 "상한에 가깝다"고 쓰지 않는다.

### Codex 원문(verbatim)
> The r3 corrections close the three remaining r2 findings. **Drafting can proceed.**
> 
> | Finding | Re-check |
> |---|---|
> | B1 — OI causality | **Closed.** `OI_prev` is aged at `t − 30 min`, so the rule is usable. Forward rows also require receipt by the decision close. |
> | B3 — timing and validity | **Closed.** The span covers the consecutive ATR buckets, rv5 history, and P2’s latest delayed exit. The span end governs `window_end` for the base run and placebos. |
> | B6 — OOS power | **Closed for drafting.** The per-arm fill-rate thresholds make the A/B tradeoff reviewable without using event counts. The user’s choice still belongs in §12 **before anchoring**. |
> 
> Two wording points should be corrected in the draft: **48 fills is a necessary minimum, not a guarantee of G0**, because higher measured ρ̂ can require more; and A’s 27% of the structural maximum should not be described as “close to the cap.” Neither changes the specified gate or prevents drafting. See the [r3 brief](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:6603) and [r2 findings](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:6622).
> 
> **VERDICT: PROCEED**
> 
> Codex session ID: 01a0ec62-dab2-7800-b936-425e9a132005
> Resume in Codex: codex resume 01a0ec62-dab2-7800-b936-425e9a132005

## 2026-09-29 — 트라이얼 #3 초안 r1 **after-pass**(advisor + Codex task-mumg7yv8-tctfuz **FIX-FIRST**) → 초안 r2
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| Codex | 1 ATR 경계 | ✅ | 결정 시각 T = t_e 봉 마감 · 끝 경계 ≤ T 버킷부터 연속 14개(경계면 막 끝난 버킷 포함) |
| Codex | 2 창 이전 이력 | ✅ | 창 끝 이후만 금지 · 창 시작 전 가격·OI·펀딩 이력 입력 허용(IS 워밍업 · OOS 앞 90일) · §12-15 |
| Codex | 3 결정 시점 B2 | ✅ | 결정 시점 B2(m · SL 가격) + 체결 시점 재사이징 · 깔때기 두 사유 · §12-14 |
| Codex | 4 전진 OI 결손 | ✅ | 폴러 실패 = G-F 결손 · 폴링 성공인데 새 행 없음 = oi_missing · §12-9 엔드포인트·주기 · 깔때기 분모 정리(no_tail) |
| advisor | 1 | ✅ | mark 완전성 = 전체 구간 · 펀딩 = [t0, t0+6h06m] |
| advisor | 2 | ✅ | V = 완전한 mark 날 ∧ 분위수 유효(펀딩은 이벤트별) · 판정기가 다시 계산해 대조 |
| advisor | 3 | ✅ | oi_not_decreasing을 §1에 · 쿨다운 미시작 |
| advisor | 4 | ✅ | P2: 지연 봉 시가에 평평하면 체결 시도 · 포지션 있으면 position_busy |
| advisor | 5 | ✅ | §11 1-1 전진 OI 어댑터 |
| advisor | 6 | ✅ | G-B 상호 의존 공시 |
| advisor | 7 | ✅ | 확인만 |
| advisor | 8 | ✅ | #43 수정 없이 #44 추가 |
- 초안 r2 SHA256 `06bb0901fc91b68d29aa5545c653e5b286fc753134c41512d8e4eca9fadfa951`.

### advisor 원문(verbatim)
> You're at the trial #3 after-pass (Codex running); this is the advisor half. I read the draft against brief r1–r3 and against trial #2's precedent. R1'–R10 are all in the text; the §12 list covers every choice that was flagged. What the draft still leaves readable two ways, numbered for the log:
> 
> **1. The §1 table has one ambiguous cell — verify it before Codex flags it.** "판정 가능 구간" starts at t0 − 270 min, yet the funding-boundary requirement is stated over the *whole* span. R3' intended the mark-grid requirement over the whole span (lookbacks need bars) but funding only matters during a hold. As written, an event with a missing 00:00 funding record four hours *before* t0 becomes `not_admissible` even though no position exists then. Two implementers will read it differently. Fix: mark completeness over [t0 − 270, t0 + 366]; funding validity over [t0, t0 + 366] only. State the reason (funding is settled only while a position is open).
> 
> **2. The V day set definition (§3-1) and the admissibility span (§1) don't match, and V drives the bootstrap blocks.** V requires "그날 00/08/16 펀딩 3건" and the day's quantile validity, but a trade whose event-day funding is fine and whose *next-day* 00:00 funding is missing would be `not_admissible` (not in the sample) while its entry day is still in V (an empty block). That's fine — but the reverse case matters: a day in V whose 00:00 funding is missing has no admissible events and *is* a block. Say explicitly: V = days where an admissible event could exist under §1, computed from the same rules, and the evaluator recomputes V rather than reading it. Trial #2 had `validity.json` equality checks; carry that.
> 
> **3. `oi_not_decreasing` is in §7-3 but not in §1.** §1 defines `oi_ok` and `oi_missing`; the funnel names a third reason. Add it to the §1 row so the strategy records it (OI present, not decreasing → not a qualified event, no cooldown started). Also state whether a tail minute that fails `oi_ok` counts against anything — as written it doesn't start cooldown; say so.
> 
> **4. P2 mechanics have a gap the brief closed but the draft reopened.** §4 says "체결 = t_e + k + 1분 봉 시가" and "적격 집합은 기본 실행과 같다" — good — but the cooldown/`position_busy` interaction at the delayed time isn't stated. In trial #2, P2 re-evaluated busy at the delayed close; here R7 says decision *not* re-evaluated. Pin: P2 fills at the shifted bar unconditionally if the book is flat at that bar's open; if a position is open (from an earlier P2 fill), the event is `position_busy`. Otherwise two implementers can differ on whether the delayed fill checks the book.
> 
> **5. The forward G-F row lists "OI 폴링" as a rule-execution item but §11 has no adapter spec.** Fine for a pre-registration, but add one sentence to §11: forward OI rows are stored with receipt time and the strategy reads only rows received ≤ decision close — otherwise §1's "전진은 결정 시점까지 수신된 행만" has no implementation hook.
> 
> **6. §3 G-B disclosure needs one more line.** "각 암의 SR̂가 서로의 SR*에 들어간다" — correct, and it means the two arms' verdicts are not independent through SR*. Say that L's G-B depends on S's realised Sharpe and vice versa, and that this is accepted (N counting requires it). Codex will otherwise read "독립 장부" against this.
> 
> **7. Two arithmetic spot-checks pass:** z_{0.991667} = 2.3940 ✓; window-B floor 48/271 = 0.177/day ✓; window A 48/90 = 0.533 ✓. §1-1 rows reuse trial #2's snapshot geometry — correct since #36 is the same snapshot, but §11-7 says "앵커 시점 캡처" for a *new* snapshot; if the new capture changes brackets, §1-1 is an example only (it already says [DERIVED · 예시]) — no change needed.
> 
> **8. Registry row #43 says "before-pass … PROCEED" — accurate — but the after-pass verdict slot is missing.** Trial #2 appended a separate row per material revision (#31 → #32 → #34). Plan the same: don't edit #43; the after-pass outcome and any r2 draft get their own row.
> 
> **Sequence:** Codex verdict → log both verbatim with positions → fixes 1–6 in draft r2 → narrow re-check → report to the user with the three items they asked for (skill tree + e8c3091; S0 numbers; draft verbatim) plus the §12 list as the decisions they must make before anchor. No anchor, no code.

### Codex 원문(verbatim · task-mumg7yv8-tctfuz)
> ## After-pass findings
> 
> **VERDICT: FIX-FIRST.** Registry row #43 matches the draft’s SHA256, and the draft carries the main r1–r3 resolutions. The following rules still permit different trades or verdicts and need to be fixed before anchoring:
> 
> 1. **ATR boundary differs from approved r3.** The draft says the last 15-minute bucket ends at the boundary *before* `t_e` ([§1, line 29](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:29)); r3 specifies the last boundary **≤ `t_e`** ([ops log, r3](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:6609)). At a boundary, the two readings can use different ATRs, changing the SL, sizing, and fills. Specify the bar timestamp convention and inclusive boundary explicitly.
> 
> 2. **Window lookback conflicts with the no-outside-window rule.** Daily thresholds require 90 preceding days ([lines 23–24](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:23)), while [line 36](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:36) forbids reading outside each IS/OOS window. [Line 111](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:111) names only IS warmup. In particular, OOS could either use preceding IS days for thresholds or lose its first 90 days. State the permitted historical input for **each** window while keeping trading books flat.
> 
> 3. **Decision-time B2 gate is missing.** Approved r2 requires the distance band **and B2 gate at decision**, followed by engine resizing at fill ([ops log R3](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:6488)). The draft specifies the band at decision but mentions B2 only at execution ([lines 29–30, 38](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:29)). A setup rejected at decision could pass after a changed next open. State both checks and which distance each uses.
> 
> 4. **Forward OI absence has two possible dispositions.** An unavailable or stale comparison row is `oi_missing` ([line 25](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:25)); forward data loss is a G-F execution defect leading to **폐기** ([lines 35, 77, 140](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:140)). Define when a missed poll, missing metrics row, or stale row merely suppresses an event and when it counts toward “data 결손 > 0.” This can change a forward **REJECT** into **폐기**.
> 
> **Completeness checks:** The numeric parameters and cited sources are present; I found no TBD. §9 covers the original rejection record, L1–L10, and the required distinctions. §7 gives stage precedence and the three dispositions, subject to the forward OI ambiguity above. Every explicitly tagged **[PROPOSED]** choice appears in §12. For exact implementation, §12-9 should also repeat the forward OI endpoint and one-minute polling cadence already fixed in [§5](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:112). The [event funnel](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:149) also places `quantile_invalid` under a denominator requiring a defined tail threshold; clarify that reporting denominator, though it does not itself change a verdict.
> 
> This was a read-only document review. I did not open market returns or compute from OI values.
> 
> Codex session ID: 01a0ec67-3750-7b33-b0e0-ae8c82fe4e68
> Resume in Codex: codex resume 01a0ec67-3750-7b33-b0e0-ae8c82fe4e68

## 2026-09-29 — 트라이얼 #3 초안 r2 **좁은 재확인**(Codex task-mumge7kl-yvryzb **FIX-FIRST**) → 초안 r3
| # | 지적 | 입장 | 반영 |
|---|---|---|---|
| 1 | §3 "한 암의 결과는 다른 암 판정에 안 쓰인다" ↔ G-B 상호 의존 모순 | ✅ | §3 머리말: 장부·G0/G1/G2/flat/생존/P1~P3·OOS·전진은 독립, **G-B만 예외**(공시·수용) |
| 2 | §0 "중첩되지 않는다"가 시간상 포지션 비중첩으로 읽힘 | ✅ | 같은 이벤트가 두 암에 동시에 안 들어감 · 두 장부 포지션은 시간상 겹칠 수 있고 서로 막지 않음 |
- 이전 4건 + advisor 8건 전부 CLOSED(Codex). 초안 r3 SHA256 `9b8d2cdf3e40fde82914dea46cd633666584e2fbac7032996c03f7496b224d4b`.

### Codex 원문(verbatim · task-mumge7kl-yvryzb)
> The four findings from task-mumg7yv8-tctfuz are **CLOSED**: r2 fixes the ATR boundary, permits the required pre-window history, adds the decision-time B2 gate before fill-time resizing, and distinguishes a failed forward OI poll from a successful poll with no fresh row. The eight advisor items are also **CLOSED** in the draft or registry #44. I found no remaining PARTIAL item among them.
> 
> **New verdict-relevant ambiguity:** [§3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:63) says one arm’s result is never used in the other arm’s verdict, while the [G-B rule](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:71) explicitly uses each arm’s realised Sharpe in the other’s SR*. Amend §3 to distinguish independent books and OOS progression from the shared G-B calculation. [§0](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:13) should also avoid implying that opposite signals prevent positions from overlapping across time.
> 
> The draft is **not yet ready** to present as settled for the user’s §12 decisions and date confirmation. This was a read-only review; I opened no market returns and computed nothing from OI values. The anchor remains the user’s decision.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0ec6b-a8dc-7423-a788-1172b99ae524
> Resume in Codex: codex resume 01a0ec6b-a8dc-7423-a788-1172b99ae524

## 2026-09-29 — 트라이얼 #3 초안 r3 재확인(Codex task-mumggx8t-70d41v) **MERGE**
- 두 지적 CLOSED · 새 모호성 없음 · 초안 r3 SHA256 `9b8d2cdf3e40fde82914dea46cd633666584e2fbac7032996c03f7496b224d4b`(#45와 일치) · 입장: ✅ 동의. 다음: 사용자 §12 결정·날짜 확인 → 앵커(사용자). 앵커·코드 없음.

### Codex 원문(verbatim)
> Both prior findings are **closed**. [§3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:63) now states the shared G-B dependency while keeping each arm’s book and subsequent progression separate. [§0](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:13) explicitly allows the two positions to overlap in time. The edits introduce no new verdict-relevant ambiguity.
> 
> The draft matches registry #45’s SHA256 and is ready for the user’s §12 decisions and date confirmation. The anchor remains theirs. This was read-only; I opened no market returns and used no OI values.
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0ec6d-96fd-7d00-a207-63c204be27fd
> Resume in Codex: codex resume 01a0ec6d-96fd-7d00-a207-63c204be27fd

## 2026-09-29 — 트라이얼 #3 after-pass 마무리 advisor 노트(초안 불변 · 레지스트리 행 없음)
| # | 입장 | 조치 |
|---|---|---|
| 1 초안 재수정 금지 | ✅ | r3 SHA256 28798f49… 그대로 |
| 2 초안 원문 전달 | ✅ | 보고에 파일 전문 |
| 3 메모리 갱신 | ✅ | trial03-status 메모리 작성 · trial02 줄 정정 |
| 4 푸시는 보고만 | ✅ | 9커밋 목록 · 비밀 스캔 미실행 명시 · 요청 시 푸시 |
| 5 호스트 확인 | ✅ | 읽기 전용 확인: hostname ip-172-31-38-160 · btcfut-bot(user) active · digest 09-29 00:40:12 시작 → 00:40:13 Finished(텔레그램 수신 자체는 미확인) |

### advisor 원문(verbatim)
> You're at the report stage; Codex MERGE is logged (cce86f1, #46). The draft cycle is complete. Before you write the reply, five things your checks didn't cover:
> 
> **1. Don't touch the draft file again.** #45 and #46 both pin r3's SHA256 (28798f49…). Any edit — even fixing the status line to say "MERGE" — invalidates both rows. The MERGE status lives in #46 and ops_log, which is where it belongs.
> 
> **2. The deliverable is the draft text itself, not a description of it.** The user asked for it "verbatim as with #1/#2." `cat` the full 212 lines into the reply. Don't paraphrase §12 from the summary — the decision list must come from the file as committed so the user sees exactly what they'd be approving. Frame §12 as: these 15 are yours; window A/B defaults to B; anchor requires your date confirmation; nothing proceeds before both.
> 
> **3. Memory is now wrong.** `trial02-status.md` and its MEMORY.md line say "trial #3 = T-FLUSH, no work yet" and "re-base on constitution v1.2." Both are stale: constitution is v1.3 (e8c3091), and #3 is at draft r3 / Codex MERGE / awaiting §12 + date. Update that file (or write a `trial03-status.md` and fix the pointer) before the report — next session will otherwise resume from a false premise.
> 
> **4. Push state must be stated, not acted on.** 9 commits ahead (23a5648…cce86f1). Item #1's push (e8c3091, 72be305) was explicit; item #2 said "deliver," not "push." Under the standing constraint, list the 9 hashes and ask; don't push. Note the secret scan hasn't been run on these yet.
> 
> **5. Host item: don't report a negative you didn't observe.** "Report the digest only if it fails" means you checked. If this segment didn't actually verify delivery (read-only log/journal), say "not checked this session" rather than implying it was fine. Silent success is exactly the failure class CLAUDE.md warns about.
> 
> **Skill item facts to include:** tree as printed (1 folder, SKILL.md + 5 references, no Zone.Identifier), header `v1.3 (2026-09-29)` confirmed (grep count 1), commit e8c3091 pushed with 72be305. Note the wrapper folder described in the request didn't exist — say that plainly rather than reporting a move that didn't happen.
> 
> **Logging this pass:** the standing rule is verbatim for every advisor text. Log this one under the after-pass as the closing advisor note with your positions; no registry row (draft unchanged).
> 
> No blockers on the substance — Codex closed all 14 items across three passes and the draft is ready for the user's decisions. The items above are report-accuracy, not design.

## 2026-09-29 — 트라이얼 #3 업로드 전 해시 불일치 발견(정정 · 앵커 보류)
- 업로드 직전 대조: 파일 SHA256 = `9b8d2cdf…`(= #45·#46 · 커밋 4cd51b2) ≠ 사용자 승인 문구·#47의 `28798f49…`.
- 원인: `28798f49…`는 r3 문구 수정 뒤·상태줄(3행) 수정 **전**의 일시 해시. 보고에 그 값을 잘못 인용했고 advisor 노트·입장표(위 "r3 SHA256 28798f49… 그대로")도 그 값을 따랐다. 어느 커밋에도 없다.
- 내용: 사용자가 원문으로 읽은 텍스트와 Codex MERGE 대상 = `9b8d2cdf…` 파일. 정정 행 #49. 사용자 해시 재확인 전 업로드하지 않는다.
- 비차단 메모: rclone `gdrive:` 원격이 폐지 예정인 rclone 공유 client_id를 쓴다는 NOTICE(2026 중 중단) — 변경 없음, 사용자 보고.

## 2026-09-29 — 트라이얼 #3 앵커(레지스트리 #50)
- 사용자 해시 재확인("confirm 9b8d2cdf") → `rclone copyto`(바이트 그대로) 09:31:42Z~09:31:48Z · rc 0.
- **createdTime `2026-09-29T09:31:46.486Z`** — rclone `lsjson --metadata` btime = Drive 커넥터 `get_file_metadata` createdTime(일치) · id `1mMh8xPbPuXAjS1dli6QaRyE7H9MKxt8V` · 부모 `14NZhku5Odij7BX_6nk2uPkqNiESTb8-2`.
- 내려받은 사본 `cmp` = 커밋 4cd51b2 판 바이트 동일 · 36,450 bytes · SHA256 `9b8d2cdf…` · Drive md5 `4911a64e…` = 로컬.
- `OOS_end = 2026-09-28T23:59:59.999Z`(271일 · 기계적). tf_v1 = §1 표 20~39행 SHA256 `ae58c8a0…`.
- 다음: 단계 2 구현 before-pass(advisor + Codex) → 판정을 사용자에게 보고 → 사용자 확인 전 (a)~(f) 착수 없음.

## 2026-09-29 — 트라이얼 #3 **단계 2(구현) before-pass**(advisor + Codex task-mumhco26-r03krx FIX-PLAN-FIRST → r2 task-mumhj6mb-ud19lx FIX-PLAN-FIRST → r3 task-mumhn9pb-1xqso6 FIX-PLAN-FIRST → r4 task-mumhp9wv-inqqix **PROCEED**)
- 코드 없음 · 실데이터 없음. 계획 r1(요지)→r4 원문은 아래. 사용자가 판정을 본 뒤에만 (a)~(f) 착수.

### 항목별 입장(Claude Code)
| 출처 | # | 입장 | 반영(계획 r2~r4) |
|---|---|---|---|
| advisor | 1 비용 격자 기준 | ✅ | S4: net 분모의 scalable_cost_bps · net_k = net + (1−k)·cost · 청산 수수료·펀딩 불변 |
| advisor | 2 청산 다리 슬리피지 | ✅ 확인 | 청산 체결도 sender.send_market(engine.py:668) · (b) 첫 테스트 = 10 + 12 bps |
| advisor | 3 가져오기(수정 금지) | ✅ | S6: *_t2.py 무수정 · range 매개 함수만 import · ops_log 기록 |
| advisor | 4 OOS 가드 3면 | ✅ | S7: 범위 고정 · 로더 단언 · var/t3/ 전용 · t3_s0·var/backtest 입력 금지 |
| advisor | 5 구조적 사실(쿨다운 720 > 366) | ✅ | S2/S2': position_busy·entry_refused 0 단언 · 훅 술어 엄격 |
| advisor | 6 P3 방향 | ✅ | S11 |
| advisor | 7 비트맵 공유·주입 | ✅ | S10 |
| advisor | 8 누락 규약 | ✅ | S12 체크리스트에 전부 |
| advisor | 9 자정 넘는 펀딩 | ✅ | S9 테스트 3종 |
| advisor | 10 성능 | ✅ | 접두합 |
| advisor | 11 순서 | ✅ | 이 기록 → 사용자 보고 → 대기 |
| Codex | 1 단계 순서(판정기 푸시 전 실캡처 금지) | ✅ | S1 |
| Codex | 2 P2 사전 훅 | ◐ 부분 | 새 훅 대신 구조적 사실(advisor 5) + 전략의 명시 busy 검사 + 0 단언(S2') — Codex r2·r4 수용 |
| Codex | 3 트라이얼 #3 출처 사슬 | ✅ | S3 t3_provenance/t3_stages |
| Codex | 4 비용 격자 항등식 | ✅ | S4(advisor 1과 같음) |
| Codex | 5 OOS 진입점 분리 | ✅ | S7 · OOS 진입점은 날짜 있는 레지스트리 행 id 없이는 거부 |
| Codex | 6 시계·결정 시점 sl_dist | ✅ | S8 |
| Codex | 7 깔때기·적격 구분 | ✅ | S10 |
| Codex | 8 시간 청산 일정 | ✅ | S9 |
| Codex | 9 규약 행 | ✅ | S12 |
| Codex | 10 헤더 상태 | ✅ | S13 파일 무수정 · #50이 상태 권위 |
| Codex r2 | P1 튜플 시드 | ✅ | S6': p1_core 무수정 · SeedSequence 튜플 엔트로피 · 동일성 테스트 |
| Codex r3 | has_position은 속성 | ✅ | r4 |

### 계획 r1(브리프) 원문
> # Trial #3 (T-FLUSH) step 2 — implementation BEFORE-PASS brief (no code yet)
> 
> Anchored 2026-09-29: registry #50 (Drive createdTime 2026-09-29T09:31:46.486Z · doc SHA256 9b8d2cdf… · tf_v1 = §1 table lines 20–39 = ae58c8a0…),
> decisions #47 (+#49 hash correction), rules snapshot #48 (parsed values identical to #36). Window (B): IS 2024-01-01→2025-12-31, OOS 2026-01-01→2026-09-28 (CLOSED).
> Spec = docs/trials/trial_03_preregistration.md (§1 rules, §3/§3-1 gates+evaluator, §4 placebos, §4-1 staging, §5 data, §7 verdicts, §11 implementation list).
> User order: (a) data prep incl. OI · (b) PaperSender slippage parameter (shared layer, own before/after pass) · (c) time-exit hook at fill+240 ·
> (d) strategies/trial03 state machine + P2/P3 variants + rolling-channel static check · (e) P1 cross-day eligibility, per-arm streams ·
> (f) evaluator. Test-first, stop-and-report after each. Implementation-convention registry row before any P&L. Evaluator committed+pushed
> before any run. IS outputs opened together per arm. OOS closed.
> 
> ## Plan per step (what exists vs what is new)
> 0 anchor module strategies/trial03/anchor.py: own constants (createdTime, Drive id, doc SHA, tf_v1 SHA+line range, window B ms, OOS_end,
>   N=6, seed, pinned SR̂ #1A/#1B/#2A/#2B + report SHAs, rules-snapshot SHAs #48). Imports nothing from trial01/02 anchors. Test: file SHA
>   and tf_v1 SHA recomputed from the committed doc equal the constants.
> (a) backtest/prepare_t3.py (new; prepare_t2 imports the trial02 anchor so it cannot be reused as-is — factor or copy with PROVENANCE-style
>   note in ops_log): mark 1m + kline 1m + funding REST for [2023-10-02 00:00Z, 2025-12-31 23:59Z]; OI from binance.vision daily metrics zips
>   for the same range, raw kept + hashed; audit/stop rules §5 (duplicate create_time with different values → stop; identical → merge;
>   non-5-min boundary or unparsable → stop); manifest, data pins row, verify. HARD GUARD: no input row/bar/funding/OI ≥ 2026-01-01 00:00Z
>   is read (OOS closed). NOTE: var/t3_s0/metrics already holds zips through 2026-06-30 (S0 counts only) and var/backtest holds trial #2
>   mark data through 2026-06-30 — both contain OOS-period data for trial #3; prepare_t3 must capture fresh and must filter by range
>   before parsing values; the S0 directory is not an input.
> (b) PaperSender already has `slippage_rate` (default PAPER_SLIPPAGE_RATE 2 bps, #7). New: plumb an explicit keyword through
>   backtest/engine_replay.replay() and backtest/placebo_exec (sizing_decision, run_time_exit, p1_null_distribution); default = unchanged
>   2 bps; golden tests that trial #1/#2 paths are byte-identical; trial #3 passes Decimal("0.0006"). Own before/after pass.
> (c) Existing replay hook `exit_at_bar_open(bar)` (trial #2 23:59: funding → assert no pending entry → open-gap liquidation → TIME_EXIT at
>   open → bar_events → skip on_bar → call on_minute_closed). Trial #3 strategy returns True at fill_minute+240. Argument: no pending entry
>   can exist at that bar (one position per arm; events during a position are position_busy; T_min 20 means no intent at the hook minute).
>   Need: the strategy must know the fill minute (from ctx.bar_events FILL). Possibly zero engine change.
> (d) strategies/trial03/: per-arm state machine (§1): daily quantile at 00:00 from d−90..d−1 (99% of 129,600 defined), r30 on mark closes,
>   OI_now/OI_prev with +5 min availability and ≤10 min age, cooldown 12h per arm started by every qualified event, cooling (T_min 20, rv5
>   ddof1 ≤ 0.5·rv_peak over [t0−30, t_e], T_max 120), decision gate at t_e close: ATR_15m (14 complete 15-min buckets ending ≤ T), SL=m∓1.5ATR,
>   sl_dist band [0.44%, 5%], decision-time B2 gate via canonical size_entry(m, SL, E_ref) → EntryIntent(sl fixed price). Engine re-sizes at fill
>   (existing). Admissibility (future-dependent: complete mark days over [t0−270, t0+366], funding validity on [t0, t0+366]) is INJECTED by the
>   harness from the prepared validity (as trial #2 injected V), never computed from future bars inside the strategy. Variants whitelist:
>   base, P2(+1,+5: no re-decision; fill at t_e+k+1 open if book flat, else position_busy), P3 (reverse fill direction; SL = mirror about m).
>   Static check: no rolling price max/min channel in strategies/trial03 (rv_peak rolling volatility max explicitly allowed by name).
> (e) backtest/p1_t3.py: (a)–(f) conventions with cross-day eligibility: t eligible iff [t, t+h−1] lies in complete mark days inside the window
>   and every 00/08/16 funding boundary inside has a validated funding; streams L SeedSequence((20260929,2)).spawn(1000), S (20260929,3);
>   slippage 6 bps; time exit; failures >10 → 폐기.
> (f) backtest/evaluate_t3.py + verdict_t3.py: two arms; per arm G0/G1/G2/G-B/flat/survival/P1/P2/P3; CI 99.1667% (0.41667/99.58333);
>   bootstrap streams SeedSequence((20260929,1)).spawn(8) IS k0–3; SR* over defined of 6 values, n_trials 6; V recomputed from prepared inputs
>   and compared to each run's record; verdict string `L: … | S: …` with survival; B&H suffix ACCEPT-only; cost grid report-only.
>   Provenance chain reused from t2_provenance (push-first H, fingerprint, verify receipt, exact outputs).
> 
> ## Risks / questions for reviewers
> R1 P3 decision-time B2 gate: §4 says judgment in the original direction, fill direction reversed. Proposal: decision-time gate uses the
>    ORIGINAL direction+SL (it is part of 판정); fill-time re-sizing uses the mirrored SL and reversed side. Pre-commit as convention?
> R2 Cost grid formula (report-only): proposal — per trade record fee_bps and slippage_bps (entry+exit, vs mark) separately;
>    net_k = gross − k·(fee_bps + slip_bps) − funding_bps, k ∈ {0.5, 1.0, 1.5}; assert net_1.0 == recorded net_bps within Decimal exactness.
>    Liquidation trades: fee component = liquidation fee? Proposal: liquidation fee is NOT scaled (it is not fee+slippage of a fill).
> R3 gross_bps on liquidation = mark→estimated liquidation price (§3-1). Fine?
> R4 Admissibility injection: harness computes per-arm admissible t0 set? Admissibility depends only on t0 (not arm) → one set of
>    admissible minutes (bitmap) shared by both arms and all variants; strategy checks membership. OK?
> R5 OOS guard: how strong? Proposal: prepare_t3 refuses any range end > 2025-12-31T23:59:59.999Z; loaders assert max ts; evaluator refuses
>    OOS inputs (OOS functions pre-committed but not callable without a user-dated registry row id).
> R6 E_ref reset per entry + N_stat ledger (reuse trial #2 sizing_capital).
> R7 Performance: daily quantile over 129,600 floats × ~730 days; OI lookups; P1 1000 draws × 2 arms with cross-day eligibility (prefix sums
>    over complete-day and funding-valid masks). Memory: trial #2 used ~2.35 GB/child for ~2.5y+21d; trial #3 is ~2.25y + 91d warm-up.
> R8 Funding at boundary-minute fill: engine settles funding before fill in the same minute → a position filled in the boundary minute does
>    not pay (matches §1). Holds crossing 00:00 pay the 00:00 funding (trial #2 never held across midnight — first exercise of that path).
> R9 Two arms = two independent replays (separate engines) per variant — no shared state.
> R10 What must be pre-committed in the conventions row before any P&L (list candidates): quantile index convention (which minutes of d−90..d−1,
>    r30 at minute t uses t−30 of the previous day ok), OI parse (create_time format, timezone), rv5 window exact minutes, ATR bucket
>    alignment, admissible bitmap construction, P2 queue semantics, P3 gate direction (R1), cost grid (R2), liquidation gross (R3),
>    B&H series, output schema/CLI, provenance chain, V equality check, degenerate stats rules, overflow = refuse.
> R11 Reuse vs copy: prepare_t2/p1_t2/evaluate_t2/verdict_t2 are trial-#2-pinned artifacts (H = 63c1760). Proposal: do NOT modify them;
>    trial #3 modules are new files that import only generic helpers (stats_t2 functions, placebo_exec, engine_replay). Any shared-helper
>    change → golden test proving trial #2 outputs unchanged.

### advisor 원문(verbatim)
> This is the advisor half of the step-2 before-pass. I read the brief against the anchored r3 (`9b8d2cdf…`) and the code you inspected. Overall the plan is faithful; nothing in it contradicts the anchored text. Findings numbered for the log, blocking ones first.
> 
> **1. BLOCKER — R2 cost-grid formula will fail its own assertion; fix the basis before it becomes a convention.** `gross_bps` is mark→mark on the entry-bar mark basis; `net_bps` is Δwallet on the `qty × fill_entry` basis (§1 통계 원장). Those bases differ by the 6 bps fill offset, so `gross − (fee+slip) − funding ≠ net` exactly. Define the grid *from* net so ×1.0 reproduces it by construction: record per trade `cost_bps = fee_bps + slip_bps` on the net basis (qty × fill_entry), then `net_k = net_bps + (1 − k)·cost_bps`, k ∈ {0.5, 1.0, 1.5}; funding untouched. Liquidation trades: `cost_bps` = entry-leg fee+slip only (no exit fill, liquidation fee not scaled). Test: verdict object is bit-identical with the grid removed (report-only).
> 
> **2. BLOCKER — verify slippage reaches the exit legs, not just entry.** §2 says both fills. Confirm `Engine` routes SL fills (worse of SL/open) and `TIME_EXIT` through `PaperSender.quote_fill_price` with the same `slippage_rate`, and that liquidation does not. If any exit leg bypasses the sender, 22 bps is not what the engine charges. This is the first thing (b)'s test should assert: a synthetic round trip at 6 bps costs exactly 10 + 12 bps before funding.
> 
> **3. MAJOR — R11: import, don't factor.** `prepare_t2.py` is pinned under trial #2's H. Its functions that take explicit `(start_ms, end_ms)` (`capture`, `read_archive_rows`, `analyze(expect_range)`, `build(expect_range)`, `verify_manifest`) are reusable as-is; only `window_range()` reads the trial02 anchor. `prepare_t3.py` imports those and supplies its own range + the OI path. Zero edits to any `*_t2.py`. Same rule for `p1_t2`/`evaluate_t2`/`verdict_t2`: new files, import generic helpers (`stats_t2`, `placebo_exec`, `engine_replay`). Any shared-helper signature change (only `placebo_exec` for the slippage kwarg) needs a golden test that trial #2's committed outputs are byte-identical. Don't call this "PROVENANCE" — that header is for E2E copies; an ops_log entry is the right record.
> 
> **4. MAJOR — OOS guard has three surfaces, not one.** (i) `prepare_t3` refuses `end_ms > 2025-12-31T23:59:59.999Z` and its captures/filters are range-bounded before value parsing (you have this). (ii) Every loader (`load_prepared_pinned`, OI loader, funding loader) asserts `max(ts) ≤ IS_END` — a second independent check. (iii) `var/t3_s0/metrics` and `var/backtest` (trial #2 mark data) both hold 2026 data; make `prepare_t3` write to a new `var/t3/` and take the OI zips from a fresh range-limited capture, not from `var/t3_s0`. Record in the conventions row that S0's directory is not an input.
> 
> **5. Structural fact that simplifies (c) and P2 — assert it, don't implement around it.** Cooldown = 720 min starts at every qualified event; the longest possible span from t0 to exit is 120 + 1 + 240 = 361 min (P2+5: 366). So no qualified event can occur while a position is open: `position_busy` is unreachable in base, P2 and P3 alike, and no pending entry can exist at the fill+240 hook bar. Keep the spec's `position_busy` branch (it's anchored), but add a test that the count is 0 and a harness assertion that flags >0 as a bug. Your hook argument is airtight for the same reason. Make the hook predicate strictly `position_open ∧ bar.open_ms == fill_open_ms + 240·60_000` and test the SL-closed-early case returns False. Also assert `open_at_end is None` for every run (§1 span end ≤ window end guarantees it).
> 
> **6. R1 — agree: decision-time gate in the original direction, fill re-size reversed.** §4 "판정은 원 방향으로". Because SL is a fixed price about `m` in trial #3, P3 needs no `SlFromFill`: emit `EntryIntent(direction=reversed, sl=m ± 1.5·ATR)`. Simpler than trial #2 — say so in the conventions row so a reviewer doesn't look for the trial #2 mechanism.
> 
> **7. R4 — agree: one admissible-t0 bitmap shared by both arms and all variants.** Admissibility depends only on t0. The strategy checks membership; the harness computes it from prepared validity (complete-day mask + funding-boundary mask). Also inject the complete-day mask itself: V needs "d is a complete mark day", which is future-dependent within d. Quantile validity (99% of d−90..d−1 defined) is causal and stays inside the strategy. Convention: state which is injected and which is computed, and that the evaluator recomputes both from prepared inputs (counts of defined r30 only — no r30 values).
> 
> **8. Conventions the brief's R10 list is missing** (each is a two-implementer fork):
> - **CI percentiles exact**: code uses `α = 0.05/6`, `lo = α/2 = 1/240`, `hi = 1 − 1/240`; the spec's "0.41667 / 99.58333" are rounded displays. `stats_t2.valid_day_bootstrap_mean(level=1 − 0.05/6)`.
> - **SL price rounding**: `m ∓ 1.5·ATR` is not tick-aligned. Pre-commit: engine SL = HALF_UP to tick (§1 "가격 HALF_UP"); `sl_dist` for the band check = `1.5·ATR/m` as written (unrounded).
> - **r30/rv5 numeric path**: Decimal closes → float64 → `math.log`; quantile via `numpy.quantile(..., method="linear")`; tail compare in float64. ATR in Decimal (it produces a price).
> - **Quantile trigger**: computed when the 23:59 bar of d−1 closes (= 00:00 of d), before the first bar of d is judged; "≥ 99%" means `defined ≥ ceil(0.99 × 129,600) = 128,304`.
> - **OI row identity**: by `create_time` only, regardless of which daily file; duplicate rule applies across files; availability = `create_time + 5 min` (exact ms); age compared at bar-close ms.
> - **Warm-up**: strategy receives bars from 2023-10-02 for state only; no event, skip, or funnel entry before `IS_START`; funnel denominator = window bar closes only.
> - **Cooldown boundary**: `t ≥ cooldown_end` allowed (끝 제외).
> - **Funding source for admissibility**: the validated REST set from prepare; a boundary with no validated record → `not_admissible` for every t0 whose [t0, t0+366] contains it.
> - **Per-arm engines**: two `replay()` calls per variant, no shared object; 8 base/variant subprocesses + 2 P1.
> - **Output schema + CLI** per arm, exact-outputs set for provenance (as #37's item 16).
> 
> **9. R8 — agree, and name it as the first exercise of the across-midnight funding path.** Trial #2 never held past 23:59. Test: a synthetic hold across 00:00 pays exactly one funding at the 00:00 bar's step ①; a fill at the 08:00 bar's open pays nothing at 08:00; a time-exit at the 16:00 bar pays 16:00 before exiting.
> 
> **10. R7 — fine.** Prefix sums over the complete-day and funding-valid masks make P1 eligibility O(1) per candidate t; the 1,000-draw budget per slot is the trial #1 rule, keep it.
> 
> **11. Sequence after Codex lands:** log both verbatim with a positions table → if FIX-PLAN-FIRST, brief r2 + narrow re-check → PROCEED → commit → report to the user. The user's instruction is explicit: they must *see* the verdict before (a) starts. Report in this order: createdTime `2026-09-29T09:31:46.486Z` (two sources agree, bytes identical), pushed HEAD `8ca3b07`, the rclone shared-client_id notice (non-blocking), then the before-pass verdict and the conventions candidates. Then stop. No `prepare_t3.py`, no test file, until they reply.
> 
> Nothing here reopens an anchored value. Items 1–4 change what you build; 5–10 are conventions to pre-commit in the registry row before any P&L.

### Codex 원문(verbatim · task-mumhco26-r03krx)
> I verified the committed document SHA256 and the §1 table SHA256 against registry #50. This was a read-only review; I did not open market returns or OI values or run a backtest.
> 
> 1. **BLOCKER — The proposed data-prep order conflicts with the anchored staging order.** [§4-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:99) requires the evaluator to be committed and pushed **before data capture**. The brief puts data prep first. Implement and test `prepare_t3.py` first if desired, but move its real capture, audit, manifest, pins, and verify run after the complete evaluator and execution code are frozen and pushed. Record that distinction in the step plan.
> 
> 2. **BLOCKER — P2 cannot be implemented exactly through the current close-only strategy interface.** P2 must test whether the book is flat **at the delayed fill bar’s open**. [replay()](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:77) accepts an intent only after the preceding bar closes, while [Engine.request_entry()](/home/cms/project/BTC_Futures_E2E/paper/engine.py:204) refuses it if a position exists then. A position could close at the target open. Add a narrowly scoped pre-bar P2 hook that checks the book and submits the saved intent at that open, after funding and before the normal bar evaluation. Test that boundary case, plus occupied and empty target opens. Keep the original decision gate and fixed SL; only fill-time B2 is rerun.
> 
> 3. **BLOCKER — Trial #2 provenance cannot simply be “reused.”** [t2_provenance.py](/home/cms/project/BTC_Futures_E2E/backtest/t2_provenance.py:17) hardcodes Trial #2 pins, evaluator files, and fingerprint files; [t2_stages.py](/home/cms/project/BTC_Futures_E2E/backtest/t2_stages.py:32) hardcodes its runs and outputs. Create Trial #3 specific provenance and stage definitions, or parameterize the generic machinery while leaving the Trial #2 contract byte identical. Freeze the **full** Trial #3 dependency fingerprint, exact output inventory for both arms and their P1 parts, evaluator commit H, pushed pins, and verify receipt before results are opened. The brief names the chain but omits the required Trial #3 stage implementation.
> 
> 4. **MAJOR — The proposed cost-grid identity is generally false.** [gross_bps and net_bps](/home/cms/project/BTC_Futures_E2E/backtest/returns.py:27) have different entry denominators: mark open versus actual entry fill. Consequently `gross − fee − slip − funding` need not equal recorded net at ×1, even with exact Decimal arithmetic. Precommit an exact ledger decomposition, including the denominator residual, or define `net_k = recorded_net_1 + (1−k) × scalable_cost_bps` with scalable costs expressed on the recorded net denominator. Treat liquidation separately: it has no exit fill, and the liquidation fee remains unscaled. Assert the ×1 identity for normal and liquidated trades before P&L.
> 
> 5. **MAJOR — The OOS guard needs to separate today’s IS-only entrypoint from later authorized OOS use.** An unconditional `prepare_t3` refusal of every end date after 2025 would prevent the anchored OOS stage. Make the present capture and loaders IS-only, with exact range assertions and no route to existing Trial #2 or S0 files. Define a separate OOS entrypoint that remains gated until the user’s post-IS decision and a dated registry row. Select source files and bound REST requests by the permitted range **before parsing price or OI fields**; Trial #2’s archive reader currently opens broad year files and filters rows afterward ([prepare_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/prepare_t2.py:89), [data.py](/home/cms/project/BTC_Futures_E2E/backtest/data.py:103)). Tests should use synthetic fixtures.
> 
> 6. **MAJOR — Clock conventions and the P1 `sl_dist` source must be fixed before runs.** [§1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:23) distinguishes a bar’s open timestamp, its close decision time, and OI availability. [ReplayContext.now_ms](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:125) is the last millisecond of a bar, whereas the anchored decision time is the next exact minute boundary. Define one conversion and use that boundary consistently for r30, OI `c+5`, the 30-minute OI comparison, cooling, and intent timing. Also emit **decision-time** `sl_dist` explicitly: replay’s existing trade field is the [post-fill distance](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:101), which can differ and must not silently become P1’s source pair.
> 
> 7. **MAJOR — Preserve the anchored funnel and validity distinctions.** The first-failure order is `quantile_invalid → no_tail → not_admissible → in_cooldown → oi_missing → oi_not_decreasing`, followed by the entry funnel ([§7-3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:148)). Missing or nondecreasing OI must never start cooldown. A future-completeness bitmap may be injected into historical strategy runs because [§1 explicitly specifies it](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:35); do not derive it from future bars inside the strategy or use that historical rule for forward paper. Base, P2, and P3 share the event bitmap. **P1 has its distinct cross-day eligible-minute rule** in [§4](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:92).
> 
> 8. **MAJOR — Make time-exit scheduling conditional on a live filled position.** The existing hook skips `Engine.on_bar` and forbids a new intent on every hook bar ([engine_replay.py](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:87)). Track `EntryFilled`, schedule fill minute +240, and clear the schedule on any earlier `PositionClosed`. Test funding at 00:00, an open-gap liquidation, and a position stopped before its scheduled exit. The brief’s assertion that no pending entry can exist at a hook minute is insufficient without these state transitions.
> 
> 9. **MAJOR — Specify the remaining Trial #3 evaluation and source checks in the convention row.** Commit the exact 90-day sample indexing and 99% threshold; `rv5` and `rv_peak` behavior with undefined inputs; 15-minute ATR bucket alignment and 225-minute requirement; OI UTC parsing, deduplication, age and availability; bitmap endpoints; P1 cross-day minute ordering and funding checks; P2 queue behavior; P3 gate direction; cost-grid and liquidation decomposition; B&H daily series; zero-trade and degenerate statistics; both-arm output schema; and refusal on actual float64 overflow. The evaluator must independently recompute V, reject trades outside V and incomplete inventories, use the eight specified bootstrap streams, and apply [§7’s priority order](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:123). Register these conventions **before any real-data P&L**.
> 
> 10. **MINOR — The anchored file’s opening “draft” status is stale.** Its bytes correctly match registry #50; [the header](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:3) predates anchoring. Leave the anchored file untouched and cite registry #50 as the status authority.
> 
> ### R1–R11
> 
> | Question | Review answer |
> |---|---|
> | R1 | **Yes.** P3’s decision-time B2 gate uses the original direction and original SL; fill-time B2 uses the reversed direction and SL mirrored about decision mark `m`. Record this convention. |
> | R2 | **Revise.** The stated formula fails the ×1 identity because gross and net have different denominators. Use the exact decomposition in finding 4; do not scale liquidation fee. |
> | R3 | **Yes.** Liquidation gross uses mark entry to the estimated liquidation price, as [§3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:82) specifies. |
> | R4 | **Yes for base/P2/P3**, shared across arms because admissibility depends on `t0`. P1 uses its separate duration-dependent eligible-minute set. |
> | R5 | Use an IS-only guarded entrypoint now and a separately gated OOS entrypoint later. Refuse wrong ranges and out-of-range parsed inputs. |
> | R6 | **Yes.** Reset execution wallet on each successful fill using `sizing_capital`; keep the separate fixed `N_stat` ledger. [Engine already resets on fill](/home/cms/project/BTC_Futures_E2E/paper/engine.py:494). |
> | R7 | Cache each day’s quantile and OI lookup indices; use prefix counts for P1 eligibility. Profile only synthetic data before P&L. Memory estimates are planning assumptions, not a rule change. |
> | R8 | **Yes.** Replay settles boundary funding before that minute’s fill. Test a hold crossing 00:00 and a fill at 00:00. |
> | R9 | **Yes.** Use separate engine and wallet state for L and S in every variant; their G-B calculation alone shares realized Sharpe inputs. |
> | R10 | Finding 9 is the minimum convention-row checklist; include exact CLI, inventory, fingerprint and pins/receipt fields. |
> | R11 | **Yes.** Keep Trial #2 pinned modules unchanged. New Trial #3 modules may import generic helpers. Any shared-helper change needs a before/after Trial #1/#2 byte comparison; note that [p1_core’s RNG](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:77) presently accepts an integer seed, so Trial #3’s tuple streams require a Trial #3 wrapper or backward-compatible extension. |
> 
> **VERDICT: FIX-PLAN-FIRST.** The staging order, P2 execution point, Trial #3 provenance implementation, and exact cost-grid accounting need explicit corrections before Step 2 proceeds.
> 
> Codex session ID: 01a0ec84-313d-7583-a165-bbb366f96be1
> Resume in Codex: codex resume 01a0ec84-313d-7583-a165-bbb366f96be1

### 계획 r2 원문
> # Trial #3 step 2 — plan r2 (resolutions of the before-pass: advisor 1–11 + Codex task-mumhco26-r03krx 1–10, R1–R11)
> 
> S1 STAGING (Codex 1): code-and-test order (a)–(f) as the user listed, all on SYNTHETIC fixtures; then (g) trial-#3 provenance/stages;
>    then conventions registry row; then after-pass; then evaluator + all execution code frozen, committed, pushed (H) → ONLY THEN the real
>    capture/audit/manifest/pins/verify (§4-1 step 4) → IS runs → evaluator once. No real-data read of price/OI values before H is pushed.
> S2 P2 (Codex 2 vs advisor 5): no new pre-bar hook. Structural fact: cooldown 720 min starts at every qualified event; max t0→exit span is
>    120+1+240 = 361 min (P2+5: 366) < 720 ⇒ no qualified event can occur while a position is open or pending, and the book is always flat at
>    the delayed fill open. The P2 intent is submitted at the close of bar t_e+k (fills at t_e+k+1 open) through the normal path; the anchored
>    position_busy branch stays (as a recorded skip if request_entry refuses), plus a harness assertion: position_busy count > 0 in any run
>    ⇒ run fails as a bug. Tests: synthetic sequences proving position_busy = 0 under base/P2(+1,+5)/P3, and the refusal branch on a forced
>    fixture (cooldown shortened in a test-only config) records position_busy.
> S3 PROVENANCE (Codex 3): new backtest/t3_provenance.py + t3_stages.py (trial-#3 pins, evaluator file list, full dependency fingerprint,
>    exact output inventory for L and S × {base, P2+1, P2+5, P3} + P1 parts, verify receipt, H push preflight). t2_* files untouched.
> S4 COST GRID (advisor 1 = Codex 4): record per trade scalable_cost_bps = (entry fee + entry slippage + exit fee + exit slippage) in USDT
>    divided by (qty × fill_entry) × 1e4 (the net denominator); net_k = net_bps + (1 − k)·scalable_cost_bps, k ∈ {0.5, 1.0, 1.5}; funding and
>    liquidation fee never scaled; liquidation trades: entry leg only. Tests: ×1.0 reproduces recorded net exactly (normal + liquidated);
>    verdict object identical with the grid removed.
> S5 SLIPPAGE (advisor 2): exits already go through sender.send_market (engine.py:668). (b) test: synthetic round trip at 6 bps costs
>    exactly 10 bps fees + 12 bps slippage (± tick rounding) before funding; liquidation not via sender. Default 2 bps paths byte-identical
>    (trial #1/#2 golden). placebo_exec gets an explicit slippage kwarg, default unchanged.
> S6 IMPORT, DON'T FACTOR (advisor 3, Codex R11): prepare_t3 imports range-parameterised prepare_t2 functions only; no edits to *_t2.py;
>    p1_core RNG takes int seeds → trial-#3 wrapper builds Generators from SeedSequence tuples (no p1_core change). ops_log records reuse.
> S7 OOS GUARD (advisor 4, Codex 5): IS-only entrypoint now: range fixed to [2023-10-02 00:00Z, 2025-12-31 23:59:59.999Z]; file selection by
>    filename date and REST requests bounded BEFORE any field is parsed (no broad year files); every loader asserts min/max ts; output dir
>    var/t3/ only; var/t3_s0 and var/backtest are never inputs (asserted by path check). OOS entrypoint defined but refuses to run without a
>    user-dated registry row id argument that exists in trial_registry.md.
> S8 CLOCKS (Codex 6): T(bar) = open_ms + 60,000 exact for all causal comparisons (r30 pairing, OI c+5min availability and ≤10-min age,
>    30-min OI comparison at T−30min, cooling durations, cooldown_end, quantile trigger at 00:00 = close of d−1's 23:59 bar); never
>    ReplayContext.now_ms (last ms). Decision-time sl_dist and SL price recorded in the trade record; P1 source pairs use decision-time
>    sl_dist (never the post-fill distance field).
> S9 HOOK (Codex 8, advisor 5): time-exit schedule set on EntryFilled (fill_open_ms + 240 min), cleared on any earlier PositionClosed;
>    predicate = position open ∧ bar.open_ms == scheduled. Tests: hold across 00:00 pays 00:00 funding once; fill at 08:00 open pays nothing;
>    exit at 16:00 pays 16:00 first; open-gap liquidation on the hook bar; SL-closed-early ⇒ predicate False; open_at_end is None in every run.
> S10 FUNNELS / BITMAPS (Codex 7, advisor 7): injected = (i) admissible-t0 bitmap (complete mark days over [t0−270, t0+366] ∧ validated funding
>    at every boundary in [t0, t0+366]) shared by L/S and base/P2/P3, (ii) complete-day mask for V; computed causally in-strategy = quantile
>    validity, r30, OI, cooling, ATR. P1 uses its own duration-dependent eligible-minute rule (§4). Forward paper never uses the historical
>    bitmap. Funnel first-failure order exactly §7-3; oi_missing / oi_not_decreasing never start cooldown. Warm-up bars feed state only; no
>    event/skip/funnel entry before IS_START; funnel denominator = window bar closes.
> S11 P3 (R1 agreed): decision-time B2 gate original direction + original SL; fill-time: reversed side, SL mirrored about m. Trial #3 SL is a
>    fixed price, so no SlFromFill mechanism (trial #2's) is needed.
> S12 CONVENTIONS ROW CHECKLIST (advisor 8, Codex 9) — registered before any real-data P&L: CI exact α = 0.05/6, lo = 1/240, hi = 1 − 1/240
>    (0.41667/99.58333 are displays); SL price HALF_UP to tick, band sl_dist = 1.5·ATR/m unrounded; numeric path (Decimal closes → float64
>    log; numpy linear quantile; ATR in Decimal); quantile sample = r30 at every 1m close in days d−90..d−1 (r30 may reach into d−91);
>    defined ≥ ceil(0.99·129,600) = 128,304; rv5 undefined if any of its 6 closes missing → cooling condition false for that bar, rv_peak
>    over defined rv5 only (undefined inside the span cannot occur: span inside complete days); ATR buckets UTC-aligned 15-min, 14 TRs
>    need 15 complete buckets; OI identity by create_time across files, UTC parse, availability = create_time + 300,000 ms, age compared
>    at T; cooldown t ≥ cooldown_end allowed; funding source = validated REST set; P1 minute order ascending, funding check per boundary;
>    P2/P3 as S2/S11; cost grid S4; liquidation gross S4/R3; B&H daily kline close series; zero-trade/degenerate stats; float64 overflow
>    = refuse; per-arm output schema + CLI + exact inventory + fingerprint + pins/receipt fields; two replays per variant, no shared state;
>    evaluator recomputes V and the admissible bitmap counts, rejects trades outside V and incomplete inventories, uses the 8 streams, §7
>    priority order.
> S13 Header status line of the anchored file stays "초안 r3" (Codex 10) — registry #50 is the status authority; file untouched.

### Codex 원문(verbatim · task-mumhj6mb-ud19lx)
> ## Narrow re-check
> 
> | Before-pass finding | Status | Assessment of plan r2 |
> |---|---|---|
> | 1. Staging | **CLOSED** | S1 puts synthetic work, the conventions row, after-pass, and the pushed code freeze before real capture and IS execution. |
> | 2. P2 busy handling | **PARTIAL** | S2’s **no-pre-bar-hook conclusion is sound**, but its proposed `position_busy` recording path does not match the current replay code. |
> | 3. Provenance | **CLOSED** | S3 specifies trial-specific pins, fingerprints, inventory, receipt, and push checks. |
> | 4. Cost grid | **CLOSED** | S4 fixes the denominator, scaled components, liquidation treatment, and a ×1.0 reconciliation check. |
> | 5. OOS guard | **CLOSED** | S7 bounds the IS input and requires a user-dated registry authorization for OOS. |
> | 6. Clocks | **CLOSED** | S8 uses the exact bar close for causal comparisons and preserves decision-time SL data. |
> | 7. Funnels and validity | **CLOSED** | S10 separates the shared admissibility mask, V, and causal strategy checks; it also fixes the first-failure order. |
> | 8. Time-exit hook | **CLOSED** | S9 schedules from `EntryFilled`, clears on closure, and covers the funding and gap cases. |
> | 9. Conventions | **CLOSED** | S12 pins the previously open numeric, schema, evaluator, and output choices before real P&L. |
> | 10. Anchored header | **CLOSED** | S13 leaves the anchored file untouched and uses registry #50 for status. |
> 
> **S2 proof.** The anchored rules start a 720-minute cooldown at *every* qualified event, including a skipped one, and cap cooling at 120 minutes; P2+5 adds at most five bars before fill, followed by a 240-minute hold ([§1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:26), [§4](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:93)). Even the plan’s conservative 366-minute bound leaves 354 minutes before the next qualified event in that arm. The books are independent and start flat. The replay processes a pending entry at the next bar’s open, and the engine refuses an entry if either a position or pending entry exists ([replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:125), [engine](/home/cms/project/BTC_Futures_E2E/paper/engine.py:204)). Thus a valid run needs no new pre-bar hook for P2 busy detection.
> 
> The remaining S2 mismatch is specific: when `request_entry` raises `EntryRefused`, replay currently records **`entry_refused`**, not `position_busy` ([replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:127)). Pin an explicit strategy busy check or a narrowly typed refusal mapping so the forced fixture records the anchored reason. Do not map every refusal to busy.
> 
> **New verdict-relevant gap — S6 P1 streams.** The plan says a trial-#3 wrapper will build generators from tuple `SeedSequence`s without changing `p1_core`. The current `p1_draw_generic` accepts no generator: it creates its own through `p1_rng(cfg, draw)`, whose config declares an integer `master_seed` ([p1_core.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:25), [draw path](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:104)). Specify how the exact anchored L/S tuple streams reach that draw path, and test their identity. Otherwise P1’s random placements and rejection result can differ.
> 
> This was a read-only plan review; I did not read market data or run the backtest.
> 
> **VERDICT: FIX-PLAN-FIRST**
> 
> Codex session ID: 01a0ec88-d55d-7b03-a1ca-66e422e19d61
> Resume in Codex: codex resume 01a0ec88-d55d-7b03-a1ca-66e422e19d61

### 계획 r3 원문
> # Trial #3 step 2 — plan r3 (only the two items from re-check task-mumhj6mb-ud19lx; S1, S3–S13 unchanged from r2)
> 
> S2' P2/busy recording: the trial-#3 strategy performs an explicit busy check BEFORE emitting an intent: if ctx.has_position() (position
>    or pending entry, backtest/engine_replay.py:47) it records ctx.skip("position_busy") (cooldown already started by the qualified event)
>    and emits nothing. replay()'s generic `entry_refused` path is NOT remapped. Harness assertions per run: count(position_busy) == 0 and
>    count(entry_refused) == 0, else the run fails as a bug (structurally unreachable: 720-min cooldown > 366-min max span). Tests: forced
>    fixture with a test-only shortened cooldown records position_busy via the strategy check; a separate fixture proves entry_refused
>    is never produced on the trial-#3 path.
> S6' P1 streams: no edit to p1_core.py (trial #2 fingerprint). numpy's SeedSequence accepts a sequence of ints as entropy, so the trial-#3
>    wrapper builds P1Config(master_seed=(20260929, 2) for L / (20260929, 3) for S, draws=1000, slot_attempts=1000, fail_limit=10) and
>    p1_rng(cfg, d) = Generator(PCG64(SeedSequence((20260929, arm)).spawn(1000)[d])) exactly as §4(e) states. The annotation mismatch
>    (master_seed: int) is handled by a single typed cast in p1_t3.py with a comment citing this item. Tests: for d ∈ {0, 1, 999} and
>    both arms, the first 16 integers(0, 2**31) from p1_rng(cfg, d) equal those from an independently constructed
>    np.random.Generator(np.random.PCG64(np.random.SeedSequence((20260929, arm)).spawn(1000)[d])); L and S streams differ; the draw path
>    (p1_draw_generic) is exercised end-to-end on a synthetic source with a golden placement.

### Codex 원문(verbatim · task-mumhn9pb-1xqso6)
> **S6' closes the P1 stream gap.** `p1_rng` passes `master_seed` directly to `SeedSequence`, and NumPy accepts a sequence of nonnegative integers as entropy. The proposed tuples therefore produce the specified L and S streams without changing [p1_core.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:77). [NumPy SeedSequence documentation](https://numpy.org/doc/stable/reference/random/bit_generators/generated/numpy.random.SeedSequence.html).
> 
> **S2' has one implementation-breaking error as written:** `ReplayContext.has_position` is a property, so `ctx.has_position()` would raise a `TypeError` when the busy check is reached. Specify `if ctx.has_position:` in the strategy and forced fixture. With that correction, the explicit `position_busy` record and per-run zero-count assertions address the recording gap while leaving replay’s generic `entry_refused` path intact. See [engine_replay.py](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:46).
> 
> No other verdict-relevant gap found in this narrow, read-only check. No runs were performed.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0ec8b-bc9c-7621-bc96-7ac315823efc
> Resume in Codex: codex resume 01a0ec8b-bc9c-7621-bc96-7ac315823efc

### 계획 r4 원문
> # Trial #3 step 2 — plan r4 (= r3 with the property fix; the two items from re-check task-mumhj6mb-ud19lx; S1, S3–S13 unchanged from r2)
> 
> S2' P2/busy recording: the trial-#3 strategy performs an explicit busy check BEFORE emitting an intent: if ctx.has_position: (property, not a call — position
>    or pending entry, backtest/engine_replay.py:47) it records ctx.skip("position_busy") (cooldown already started by the qualified event)
>    and emits nothing. replay()'s generic `entry_refused` path is NOT remapped. Harness assertions per run: count(position_busy) == 0 and
>    count(entry_refused) == 0, else the run fails as a bug (structurally unreachable: 720-min cooldown > 366-min max span). Tests: forced
>    fixture with a test-only shortened cooldown records position_busy via the strategy check; a separate fixture proves entry_refused
>    is never produced on the trial-#3 path.
> S6' P1 streams: no edit to p1_core.py (trial #2 fingerprint). numpy's SeedSequence accepts a sequence of ints as entropy, so the trial-#3
>    wrapper builds P1Config(master_seed=(20260929, 2) for L / (20260929, 3) for S, draws=1000, slot_attempts=1000, fail_limit=10) and
>    p1_rng(cfg, d) = Generator(PCG64(SeedSequence((20260929, arm)).spawn(1000)[d])) exactly as §4(e) states. The annotation mismatch
>    (master_seed: int) is handled by a single typed cast in p1_t3.py with a comment citing this item. Tests: for d ∈ {0, 1, 999} and
>    both arms, the first 16 integers(0, 2**31) from p1_rng(cfg, d) equal those from an independently constructed
>    np.random.Generator(np.random.PCG64(np.random.SeedSequence((20260929, arm)).spawn(1000)[d])); L and S streams differ; the draw path
>    (p1_draw_generic) is exercised end-to-end on a synthetic source with a golden placement.

### Codex 원문(verbatim · task-mumhp9wv-inqqix)
> The r4 corrections check out. [`ReplayContext.has_position`](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:46) is a property covering both an open position and a pending entry, so `if ctx.has_position:` is correct. [`p1_rng`](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:77) passes the configured seed to `SeedSequence`; the proposed tuple produces the specified arm stream without changing `p1_core.py`. I also confirmed the first draw matches the independently constructed stream and differs between L and S.
> 
> This is a plan confirmation, not a confirmation that the proposed tests or trial #3 implementation have run.
> 
> **VERDICT: PROCEED**
> 
> Codex session ID: 01a0ec8d-290c-79b2-8077-7c1c23f9ad45
> Resume in Codex: codex resume 01a0ec8d-290c-79b2-8077-7c1c23f9ad45

## 2026-09-29 — 트라이얼 #3 단계 2 계획 r4 사용자 검토: 정정 1건(설명으로 해소) · 확인 4건 → 계획 r5 · (a) 착수
- 사용자: 앵커(#50) 수용 · 계획 변경 수용(비용 격자 · OOS 가드 · #2 무수정 · P1 튜플 시드) · rclone 원격 트라이얼 #3 동안 변경 금지 · **구현 선택 행 전문을 P&L 전에 사용자에게 보내고 회신 전 P&L 계산 금지**(단계 경계).
- **정정 요청(분위수)에 대한 답 — r3 문언은 모호하지 않다(§1 24행 원문)**: "날 d마다 00:00에 한 번 계산: 표본 = d−90 … d−1 날의 모든 1m 종가 t의 r30[t] · 129,600분 중 99% 이상 정의돼야 한다(아니면 그날 이벤트 없음 `quantile_invalid`) · numpy 선형 분위수 · `q_dn = Q(0.005)` · `q_up = Q(0.995)` · 그날 자신의 r30은 쓰지 않는다".
  - 128,304 = ceil(0.99 × 129,600)은 **정의된 표본 수의 하한**(유효성 조건)이지 꼬리 임계가 아니다(보고의 한 줄 표현이 오해를 낳았다).
  - 임계는 계획 r4부터 이미 **부호 있는 r30의 두 분위수**: 하한 `q_dn = Q(0.005)` · 상한 `q_up = Q(0.995)` · L은 r30 ≤ q_dn, S는 r30 ≥ q_up(|r30| 분위수 아님).
  - 보간: 사전등록 문언이 "numpy 선형 분위수"라서 **보간 없음(순위값)으로 바꾸지 않는다**(앵커된 규칙). 규약 = `numpy.quantile(x, p, method="linear")` · x = 그 90일 창의 **정의된** r30 값 n개(128,304 ≤ n ≤ 129,600) · 0-기준 위치 (n−1)·p · 인접 두 순서통계량 선형 보간. n = 129,600이면 하한 위치 647.995(1-기준 648·649번째 사이 · 649번째 가중 0.995) · 상한 128,951.005(1-기준 128,952·128,953번째 사이 · 128,953번째 가중 0.005) — 사용자가 적은 순위 648/128,952와 같은 자리. 비교는 경계 포함(≤ · ≥). 구현 선택 행에 이 문구로 고정.
- 확인 1(P2 포함 최대 구간): P2 지연 최대 **+5봉**. t0 → 냉각 결정 t_e ≤ t0 + 120 → 체결 t_e + k + 1분(k ≤ 5) → 시간 청산 봉 = 체결 + 240 → 최대 t0 + 366분(= §1 판정 가능 구간 끝). SL·청산은 더 이르다. 쿨다운 720분 → 여유 354분. 720을 넘는 경로 없음(P1은 쿨다운이 아니라 겹침 금지 배치 · P3는 기본과 같은 시각).
- 확인 2(워밍업): 정정 — IS 시작은 **2024-01-01**(창 B), 2023-10-02는 **워밍업 시작**이다. 2024-01-01의 분위수 표본 = 2023-10-03 … 2023-12-31(90일) · 그 첫 r30은 2023-10-02 23:30 종가가 필요 → 2023-10-02부터면 충분(2023-07-04 불필요). ATR_15m(14) 225분 · rv5/rv_peak 35분 · 판정 가능 구간 t0 − 270분도 워밍업 안. 이벤트·진입은 t0 ≥ 2024-01-01 00:00Z만(워밍업 봉은 상태만). OOS 가드: ≥ 2026-01-01 00:00Z 타임스탬프는 IS 경로 어디서나 거부.
- 확인 3(펀딩): 00:00·08:00·16:00 **세 경계 모두** — 보유 중 지나는 확정 펀딩 기록(그 시각의 REST 확정 fundingRate)을 그 분의 판정 전에 정산(엔진 `on_funding`). 테스트는 세 시각 각각(경계 가로지름 · 경계 분 체결은 미지불 · 경계 분 시간 청산은 지불 뒤 청산).
- 확인 4: f220e65 푸시(아래 커밋과 함께).

## 2026-09-29 — 트라이얼 #3 단계 2 (a) 데이터 준비 코드(합성 픽스처만 · 실데이터 캡처 없음)
- 새 파일: `strategies/trial03/anchor.py`(앵커 상수 · #47~#50 · tf_v1 20~39행 해시 · CI 정확 분수 1/240) · `backtest/prepare_t3.py` ·
  `tests/test_trial03_anchor.py`(8) · `tests/test_prepare_t3.py`(24) · `tests/fixtures/trial02_sr_pinned.json`(#40 report SHA256 9223047c…).
- 재사용: `prepare_t2`의 `analyze`·`fill_ranges`·`usable_archive`·`_pages`·`classify`·`write_bars`·`read_bars`·`_sha`·`_commit`를 **import만**
  (`prepare_t2.py`·`data.py` 무수정 · 계획 r5 S6).
- OOS 가드(S7): IS 경로 범위 한계 [2023-10-02, 2025-12-31 23:59:59.999Z](`OOSGuard`) · 아카이브는 타임스탬프 열만 먼저 읽고 끝 뒤 첫 행에서
  파일을 멈춤(2026 KST 파일은 앞 9시간만 필요 · 뒤 값 미파싱) · REST endTime ≤ 끝 · OI는 날짜 파일 이름으로 선택 · create_time 범위 밖 행은
  값 분류 전에 버림 · 적재기는 디렉터리(`var/t3/`만) · 고정값 · 범위 · 모든 타임스탬프 단언 · OOS 진입점은 "트라이얼 #3 OOS 개봉" 사용자 결정 행 없으면 거부 ·
  CLI 캡처는 판정기 커밋 H가 origin/main 조상이고 H에 `backtest/evaluate_t3.py`가 있을 때만(rc 6).
- **사용자 확인 필요(구현 선택 · 결정 전 규약 행에 [PROPOSED])**: OI 행의 `sum_open_interest`가 ok(유한 Decimal)가 아니면 **없는 행**으로 센다
  (중단 아님 → 그 시각의 비교는 `oi_missing` 또는 나이 10분 안의 이전 유효 행). 근거: §5 "해석 불가 → 중단"은 create_time과 5분 경계 문맥이고,
  §1 "어느 행이든 없으면 oi_missing"이 값 결손을 다룬다. 엄격한 읽기(값 결손도 중단)면 S0의 비유한 130슬롯(0.045%) 때문에 준비 자체가 중단될 수 있다.
  중복 판정 기준 = 같은 create_time의 `sum_open_interest` 문자열(다른 열은 비교하지 않음).
- 검사: ruff · pyright 0 · pytest 1216 passed.

## 2026-09-29 — 트라이얼 #3 (a) 보완: 사용자 결정 반영(분위수 정정 철회 · OI 사용 불가 값 = 관측 결손 · 0.5% 상한)
- 사용자: 분위수 정정 철회(128,304 = 정의된 표본 하한 · 부호 있는 r30 · q_dn = Q(0.005) · q_up = Q(0.995) · numpy linear · ≤/≥ 포함 — 문구 고정) ·
  확인 1~4 수용 · 펀딩 규약 3개(첫 처리 · 그 분 체결은 미지불 · 그 분 시간 청산은 지불 먼저) 규약 행에 고정 · **이제부터 단계마다 푸시**.
- **OI 결정(관대한 읽기)**: 빈 값·숫자 아님 = 관측 결손(§1 "어느 행이든 없으면 oi_missing") · §5 "해석 불가 → 중단"은 파일 무결성(체크섬 · 날 파일 · 시각 해석 · 격자 · 충돌 중복).
  조건: ① 규약 행에 두 읽기를 인용하고 S0 130슬롯(0.045%)을 "결과를 보지 않고 정했다"는 근거로 · ② 조회 규칙 그대로(나이 ≤ 10분의 가장 최근 유효 행, 아니면 oi_missing · 추가 역탐색 없음) ·
  ③ 준비가 날별·전체 사용 불가 슬롯 수를 기록 · 결과 보고는 사용 불가 값 때문에 oi_missing이 된 후보 플러시 수를 보통 oi_missing과 따로 · ④ **IS 5분 격자의 0.5% 초과 → 데이터 품질 중단**.
- 구현: `analyze_oi` 감사에 `unusable_slots`(유효 값이 하나도 없는 create_time · 유효 중복이 있으면 제외) · `unusable_per_day` · `unusable_total` · `unusable_is_slots` · `is_grid_slots` ·
  `oi_unusable_over_cap` 중단(IS 슬롯만 · 워밍업은 기록만) · 산출물 `oi_unusable.json`(PREPARED에 추가 · 적재기가 네 번째 값으로 반환 · 범위 단언). 테스트 26개 통과.

## 2026-09-29 — 트라이얼 #3 (b) 슬리피지 매개변수(공유 계층) **before-pass**(advisor + Codex task-mumjervv-nvo0zi **FIX-PLAN-FIRST**) → 계획 r2
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 트레이드 기록 필드 추가 금지 | ✅ | B1 |
| advisor | 2 회귀 검사 기계 | ◐ | 네트워크 없음·쓰기 금지 동의 · 지문만 우회하는 _evaluate 대신 계산 함수 직접 호출(Codex 2: 기록된 절대 경로·인벤토리 검사 때문에 우회 실행이 성립 안 함) |
| advisor | 3 우회 허용 · 워크트리 무의미 | ✅ | B3(진단으로 표기) |
| advisor | 4 순서 | ✅ | B4(기준선은 워크트리에서) |
| advisor | 5 Q3 기록 | ✅ | B7 |
| advisor | 6 정확한 등식 | ✅ | B5 T1 |
| advisor | 7 청산 경로 확인 | ✅ 확인 | `_liquidate`는 송신기를 거치지 않는다(engine.py:607) · T3는 Codex 3 방식 |
| advisor | 8 결정 시점 B2 견적 | ✅ | B6 · 규약 행 |
| advisor | 9 T6 문구 | ✅ | B5 |
| advisor | 10 Q2 | ✅ 확인 | replay.py·step_e.py는 Engine을 따로 만들지 않는다 |
| Codex | 1 표본 부족(BLOCKER) | ✅ | B2 전체 205 실행 + P1 1,000 + 병합 |
| Codex | 2 우회는 판정기 재실행이 아님 | ✅ | B3 진단 표기 · 정식 재실행은 하지 않는 이유 기록 |
| Codex | 3 T3 불변식 | ✅ | B5 T3 |
| Codex | 4 P1 두 지점 배선 | ✅ | B1 · B6 |
| Codex | 5 T1 기준 | ✅ | B5 T1 |

### 브리프 원문
> # Trial #3 step 2 (b) — PaperSender slippage parameter: shared-layer BEFORE-PASS brief (no code yet)
> 
> Spec: trial_03_preregistration.md §2 — registered cost 22 bps = taker 5×2 + slippage 6 bps × 2 + funding; "슬리피지는 체결 기준가 대비 불리 방향 +
> 불리 tick 반올림(레지스트리 #7 모델의 매개변수만 2 → 6 bps) — 진입·청산 두 체결 모두, 사이징·실행·P1·G2 전부 같은 모델". Plan r5 S5.
> 
> ## Current code (read)
> - paper/sender.py: `adverse_fill_estimate(side, ref_mark, tick, rate=PAPER_SLIPPAGE_RATE)`; `PaperSender(rules, *, slippage_rate=PAPER_SLIPPAGE_RATE)`
>   already exists (quote_fill_price and send_market use self.slippage_rate). LiveSender (sender.py:147) calls adverse_fill_estimate with the
>   default — bot/live sizing path; NOT touched.
> - Engine: entry fill quote via sender.quote_fill_price (engine.py:440) + send_market (466); exits (SL/TP/TIME_EXIT/close_now) via
>   sender.send_market (668). Liquidation does not go through the sender (verify in tests).
> - backtest/engine_replay.py:69 `Engine(rules, PaperSender(rules), ...)` — no way to pass a rate.
> - backtest/placebo_exec.py:45 sizing_decision → `PaperSender(rules).quote_fill_price`; :67 run_time_exit → `Engine(rules, PaperSender(rules))`;
>   p1_null_distribution → run_time_exit. Callers: backtest/p1_run.py (trial #1), backtest/p1_t2.py (trial #2).
> - ops/run_bot.py:382 bot engine `PaperSender(rules)` — NOT touched.
> 
> ## Proposed change (minimal, default-preserving)
> 1. engine_replay.replay(..., slippage_rate: Decimal = PAPER_SLIPPAGE_RATE) → PaperSender(rules, slippage_rate=slippage_rate).
> 2. placebo_exec.sizing_decision(..., slippage_rate=PAPER_SLIPPAGE_RATE); run_time_exit(..., slippage_rate=...) uses it for both the sizing
>    quote and the Engine's PaperSender; p1_null_distribution(..., slippage_rate=...) passes through. Keyword-only, default = #7 value.
> 3. No change to paper/sender.py, paper/engine.py, paper/config.py, ops/, sizing/, exchange/. Trial-#3 value 0.0006 lives in trial-#3 config
>    (step d), never as a default anywhere.
> 4. Trial #1/#2 callers unchanged (they pass nothing → 2 bps).
> 
> ## Tests (test-first)
> T1 synthetic round trip through replay() at slippage 0.0006: entry fill = mark_open×(1+0.0006) rounded adverse to tick; time exit fill =
>    mark_open×(1−0.0006) adverse tick (long); Δwallet = −(fees 2×5 bps on fills) − slippage cost; net_bps vs gross_bps difference = 10 + 12 bps
>    within tick rounding bound. Short symmetric.
> T2 SL exit and close_now exits carry the same rate (quote vs fill).
> T3 liquidation exit price is not moved by slippage (rate 0.0002 vs 0.0006 → identical liquidation fill/loss for identical path).
> T4 placebo_exec.run_time_exit at 0.0006: sizing quote and exit fill both at 6 bps; default call bit-identical to before (golden).
> T5 existing goldens unchanged: tests/fixtures/golden_replay_nohook.json, golden_p1_trial01.json, golden_live_engine.json; full suite.
> T6 a static check that no module under backtest/, paper/, ops/ other than tests and strategies/trial03 passes a non-default rate.
> 
> ## Trial #2 bit-identity (user requirement)
> Trial #2's provenance fingerprint (backtest/t2_provenance.py FINGERPRINT_*) includes paper/*.py, sizing/*.py, exchange/*.py,
> engine_replay.py, placebo_exec.py → after this change trial #2's GATED evaluator/stages refuse by design (fingerprint ≠ H 63c1760).
> Proposal: scripts/t2_regression_check.py (read-only on var/backtest/t2/IS; writes only to a temp dir):
>  (i) re-run trial #2 runs with the CURRENT code by calling strategies.trial02.run.execute(name, prepared, tmp, pins, pins_commit) directly
>      (gate bypassed, no provenance record written) for A, B, P2_delay1, P2_delay5, P3_invert, P4_draw000..004, and P1 part 000-124 via
>      backtest/p1_t2_run; compare SHA256 of trades.jsonl, crosses.jsonl, days.jsonl, validity.json (and P1 outputs) with the existing
>      var/backtest/t2/IS/runs files; meta.json compared with git_head/gate fields removed;
>  (ii) re-run the evaluator computation on a temp copy of var/backtest/t2/IS (evaluation/ excluded) with the fingerprint gate bypassed
>      inside the script only, and compare report.json SHA256 with 9223047c… (and verdict.txt).
>  Run the script BEFORE the change (baseline — must already match; proves the check reproduces) and AFTER the change; record both outputs
>  verbatim. The evaluator's import closure contains no engine/sender/placebo module, so (i) is the substantive proof and (ii) the user-asked
>  hash comparison.
> Q1 Is bypassing the gate inside a check script acceptable, or should (ii) run in a git worktree at H with only the run outputs copied?
> Q2 Any other consumer of PaperSender/engine_replay/placebo_exec that could change?
> Q3 Should the trial #2 fingerprint breakage be recorded as a registry note (trial #2 closed; its evaluator can no longer be re-run on main
>    without checking out H)?

### advisor 원문(verbatim)
> This is the advisor half of the (b) before-pass. The brief is faithful to §2 and correctly minimal (no `paper/*.py`, `ops/`, `sizing/`, `exchange/` edits). Findings, blocking first:
> 
> **1. BLOCKER — do not add fields to the trade record in (b), even though (f)'s cost grid will want them.** S4 needs entry fill, exit fill and commissions per trade, and `engine_replay`'s trade dict records `exit_ref` (the mark reference), not the exit fill. It is tempting to add fields now while touching the file — but your regression criterion is byte-identity of trial #2's `trades.jsonl`, and any new key breaks it. Trial #3 gets fill prices through the existing `replay(..., on_event=...)` callback (engine fill events already carry the fill and `raw.slippage_rate`). Verify before (d) that `EntryFilled`/`PositionClosed` events expose fill price and commission; if they do, no shared change is ever needed for S4.
> 
> **2. Regression check — mechanics that will bite:**
> - `var/backtest` is 11 GB. Don't `copytree`; build the temp base from **symlinks** to `prepared/`, `runs/`, `_records/`. `_evaluate` only reads those and writes `evaluation/` under the temp base; `verify_rebuild` copies `raw/` to its own tempdir. Check free disk before the rebuild copy.
> - Construct `Stages(..., fetch=False)` and call `_evaluate(..., fetch=False)` so the check never touches the network.
> - The bypass should be exactly one thing: `PV.fingerprint` returning the receipt's recorded fingerprint, inside the script, documented in its docstring. Don't monkeypatch `require_clean` or the pins/receipt checks — those should still pass.
> - Confirm `p1_t2_run` exposes a gate-free callable (like `run.execute`). If its only entry is `main()` with `gate_cli`, the script replicates main minus the gate; don't edit `p1_t2_run.py`.
> - `meta.json` diff: strip `git_head` and `gate` only; `pins_commit` must still match.
> 
> **3. Q1 — bypass is acceptable; the worktree alternative proves nothing.** A worktree at H runs old code. What you need is *new* code on *old* inputs. Conditions: the script lives in `scripts/` and is committed before the baseline run; it never writes under `var/backtest/t2`; both outputs (baseline and post-change) are logged verbatim with SHA256 per file.
> 
> **4. Order — the baseline is the first build action, not a pre-pass action.** Codex verdict → log both verbatim with positions → commit the check script → run baseline (must already match; if it doesn't, stop — something changed since 63c1760 that you haven't accounted for) → (b) edits test-first → re-run → after-pass → report. No `engine_replay`/`placebo_exec` edit before Codex lands.
> 
> **5. Q3 — yes, record it, with a hash.** After (b), trial #2's gated evaluator and stages refuse on `main` by design. Note in ops_log: "trial #2 provenance re-runs require checkout ≤ `a395667` (last commit with fingerprint = H 63c1760's set)". No registry row unless Codex asks; trial #2 is closed.
> 
> **6. T1 — assert exact equality, not a bound.** The engine is Decimal; the test should compute expected fills with `adverse_fill_estimate(side, mark, tick, Decimal("0.0006"))` and assert `==`. Then assert `Δwallet` decomposes exactly: entry commission + exit commission + (fill_entry − mark_open)·qty + (mark_ref − fill_exit)·qty for long, sign-flipped for short. "Within tick rounding" hides bugs.
> 
> **7. T3 — check the liquidation path before writing the assertion.** Grep `engine.py` for how liquidation closes. If it routes through `_exit` → `send_market`, slippage is being applied to a liquidation fill, which contradicts §1 ("손실 = 남은 격리 지갑 + 수량 × 추정 청산가 × liquidationFee"). T3 as designed would catch it — but if it fails, that's a spec finding to report, not a test to loosen. If liquidation is separate (likely), T3 passes and you've proved the claim.
> 
> **8. Convention for (d), surfaced now because it depends on this change:** the decision-time B2 gate must quote `m` through the same adverse model (`adverse_fill_estimate(side, m, tick, 0.0006)`), not use `m` raw — otherwise decision and fill gates use different price bases and §2's "사이징·실행 전부 같은 모델" is violated. Pin in the conventions row. Also: trial #3 tests should assert fill events carry `raw.slippage_rate == "0.0006"`.
> 
> **9. T6 — narrow the wording.** "No non-default `slippage_rate=` argument anywhere except `strategies/trial03/` and tests." Passthrough kwargs (`slippage_rate=slippage_rate`) in `placebo_exec`/`engine_replay` are the only other occurrences allowed.
> 
> **10. Q2 — `p1_run.py` (trial #1) calls `sizing_decision` positionally; a trailing keyword-only kwarg with default leaves it untouched. `backtest/replay.py` and `step_e.py` didn't appear in your grep for `PaperSender(` — confirm they don't construct an Engine another way.**
> 
> Nothing here changes the shared-layer scope: two files, two keyword-only parameters, defaults = #7. The P1 part rerun (~3 min) plus the evaluator rebuild (~1 min) is the whole cost of the proof.

### Codex 원문(verbatim · task-mumjervv-nvo0zi)
> ## BEFORE-PASS findings
> 
> 1. **BLOCKER — The proposed sample cannot prove Trial #2 bit identity.** It covers five of 200 P4 variants and 125 of 1,000 P1 draws. The evaluator requires the complete inventory and P1 coverage ([evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:45), [evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:108)). **Fix:** compare all 205 strategy runs, all P1 parts covering draws 0–999, and the merged P1 files before and after the change. Generate P1 from the newly reproduced A output. Compare every output byte; compare `meta.json` after removing only the expected `git_head` and `gate` fields. Reset the Decimal context as the Trial #2 CLIs do ([run.py](/home/cms/project/BTC_Futures_E2E/strategies/trial02/run.py:63), [p1_t2_run.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2_run.py:101)).
> 
> 2. **MAJOR — The proposed evaluator bypass is not an evaluator rerun.** Its preflight checks the frozen fingerprint and receipt; its inventory checks recorded commands containing absolute prepared paths and all outputs; its metadata checks the original gate ([evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:99), [evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:120), [evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:354)). Copying outputs to a temp directory and bypassing one fingerprint check does not satisfy those checks. **Fix:** label a gate-bypassed report recomputation as a *diagnostic* hash comparison. For an authoritative evaluator rerun, use clean code at H with the complete pinned inputs, records, and provenance, accounting for relocated paths. Do not replace or modify the closed Trial #2 evaluation.
> 
> 3. **MAJOR — T3 asserts an invariant the model does not have.** The sender is not called for liquidation, but a different entry slippage changes entry price, potentially quantity and leverage, estimated liquidation price, and loss. Liquidation has no fill price in its `PositionClosed` event ([engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:607)). **Fix:** restore an *identical* position into engines with 2 and 6 bps senders, trigger liquidation, and assert no sender order and identical liquidation events/loss. Separately test that a full replay may change its liquidation outcome through entry sizing.
> 
> 4. **MAJOR — Trial #3 P1 still needs explicit wiring at both decision and execution.** Trial #2’s P1 calls `sizing_decision` during placement and `run_time_exit` during execution ([p1_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2.py:45), [p1_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_t2.py:58)). **Fix:** add the proposed defaulted keyword through `sizing_decision`, `run_time_exit`, and `p1_null_distribution`; pass it to both sender instances. In Trial #3’s later P1 caller, pass its config rate to placement **and** execution, with an integration test showing both use 6 bps. The Step 2(b) shared API alone cannot establish §2’s P1 requirement ([preregistration](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:55)).
> 
> 5. **MINOR — T1’s “22 bps within tick rounding” assertion needs a precise basis.** `net_bps` divides wallet change by quantity × *entry fill*, while gross uses mark references ([engine_replay.py](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:112)). That denominator creates a small difference even with zero tick rounding. **Fix:** assert exact adverse rounded entry and exit prices and exact wallet arithmetic; treat 22 bps as the nominal cost, with a tolerance that includes both tick effects and the entry-fill denominator.
> 
> ## Q1–Q3
> 
> **Q1:** Direct function calls that skip Trial #2’s gate are acceptable for a clearly marked regression diagnostic, once the baseline reproduces the complete recorded output. A worktree at H is preferable for an **authoritative** rerun. Copying only run outputs into it is insufficient for the evaluator’s pinned inputs, records, paths, and receipt checks.
> 
> **Q2:** Other relevant consumers are Trial #1’s [run.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_run.py:53) and [strategy runner](/home/cms/project/BTC_Futures_E2E/strategies/trial01/run.py:72), Trial #2’s [harness.py](/home/cms/project/BTC_Futures_E2E/strategies/trial02/harness.py:72) and P1 caller, and the bot’s [PaperSender construction](/home/cms/project/BTC_Futures_E2E/ops/run_bot.py:382). `make_sender` also constructs a default PaperSender; LiveSender’s quote retains the default 2 bps. With the proposed default-preserving signatures and unchanged callers, these paths should retain their behavior; the full comparison must verify the Trial #2 claim.
> 
> **Q3:** Yes. Append a registry note, and record the before/after evidence in `docs/ops_log.md` as required by [CLAUDE.md](/home/cms/project/BTC_Futures_E2E/CLAUDE.md). State that Trial #2 remains closed under H and its original fingerprint, while the current main branch intentionally fails its provenance gate. Do not describe a bypassed diagnostic as a new Trial #2 evaluation.
> 
> **Does the proposed procedure prove Trial #2 is unaffected?** No. Its partial run coverage cannot establish bit identity, and its evaluator bypass cannot establish a valid gated rerun.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0ecb8-f39f-7290-b172-2c83fa8e5259
> Resume in Codex: codex resume 01a0ecb8-f39f-7290-b172-2c83fa8e5259

### 계획 r2 원문
> # Trial #3 (b) plan r2 — resolutions (advisor 1–10 + Codex task-mumjervv-nvo0zi 1–5, Q1–Q3)
> 
> B1 Scope unchanged: two files (backtest/engine_replay.py replay(); backtest/placebo_exec.py sizing_decision, run_time_exit,
>    p1_null_distribution) gain a keyword-only `slippage_rate: Decimal = PAPER_SLIPPAGE_RATE`; run_time_exit passes it to BOTH the sizing
>    quote and the Engine's PaperSender. No other shared file changes. NO new trade-record fields (advisor 1): trial #3 obtains fills and
>    commissions via replay's on_event callback (checked in (d)); byte-identity of trial #2 trades.jsonl is the criterion.
> B2 Regression = FULL coverage (Codex 1): scripts/t2_regression_check.py re-runs, with direct gate-free calls and decimal.setcontext as the
>    trial #2 CLIs do, ALL 205 strategy variants (A, B, P2_delay1, P2_delay5, P3_invert, P4_draw000..199) via strategies.trial02.run.execute,
>    ALL P1 draws 0..999 in the recorded 8 parts via backtest.p1_t2_run.run_range using the newly reproduced A output, and the P1 merge via
>    p1_t2_run.merge; writes only to a temp/scratch dir outside var/backtest/t2; compares SHA256 of every output file with the recorded
>    files in var/backtest/t2/IS/runs (meta.json compared after removing only git_head and gate). Parallel jobs = 3 (2.35 GB/child measured).
> B3 Evaluator comparison = DIAGNOSTIC, labelled as such (Codex 2, Q1): the script recomputes report.json with evaluate_t2's own functions
>    (load_prepared_pinned on the real prepared dir, DY.validity, compute, verdict_is, verdict_string, the same report dict and JSON dump
>    settings) WITHOUT the provenance/inventory/write steps, on (a) the recorded runs and (b) the re-run outputs; compares SHA256 with the
>    closed report 9223047c… and verdict.txt. Not a new trial #2 evaluation; the closed evaluation/ is never touched. An authoritative
>    gated rerun is not done: the evaluator is one-shot (evaluation/ exists) and after (b) main intentionally fails trial #2's fingerprint;
>    a rerun at H would execute H's code on H's inputs, i.e. reproduce the original evaluation, and says nothing about the new code.
> B4 Order (advisor 4): log before-pass → commit + push the check script → BASELINE run in a git worktree at that commit (pre-change code;
>    must already match — else stop) → (b) edits test-first in main → commit → AFTER run in main → after-pass → report.
> B5 Tests: T1 exact equality (advisor 6, Codex 5): expected fills = adverse_fill_estimate(side, mark, tick, 0.0006) ==; Δwallet decomposed
>    exactly (entry + exit commission, (fill_entry − mark_open)·qty, (mark_ref − fill_exit)·qty; short sign-flipped); 22 bps stated as nominal.
>    T2 SL and close_now exits at the same rate. T3 (Codex 3) restore an identical position into engines with 2 bps and 6 bps senders,
>    trigger liquidation, assert no sender order and identical liquidation event/loss; separately show a full replay's liquidation outcome
>    may differ via entry sizing (documented, not asserted equal). T4 run_time_exit at 6 bps uses 6 bps for sizing quote and exit fill;
>    default path bit-identical (golden). T5 existing goldens + full suite. T6 (advisor 9) static check: no non-default `slippage_rate=`
>    literal outside strategies/trial03 and tests; passthrough `slippage_rate=slippage_rate` in the two modules only.
> B6 Trial #3 P1 (Codex 4): the trial-#3 P1 caller (step e) passes the config rate to placement (sizing_decision) AND execution
>    (run_time_exit); integration test there. Decision-time B2 gate (step d) quotes m through adverse_fill_estimate(side, m, tick, 0.0006)
>    (advisor 8) — pinned in the conventions row; fill events asserted to carry raw.slippage_rate == "0.0006".
> B7 Q3: registry note + ops_log after (b): trial #2 stays closed under H 63c1760 and its fingerprint; main after (b) intentionally fails
>    trial #2's provenance gate; last main commit whose fingerprint set equals H's = the pre-(b) commit (recorded by hash).

## 2026-09-29 — 트라이얼 #3 (b) 계획 r2 Codex 좁은 재확인(task-mumjjokg-d1ptbn) **PROCEED**
- 입장: ✅ 전부 동의 · 워크트리 기준선은 본 저장소의 무시된 `var/backtest/t2/IS`를 `--t2-base`로 가리킨다 · `--skip-runs`는 회귀 증거가 아니다(진단 경로 점검 — 기록된 실행에서 report SHA256 9223047c… 재현 확인만).

### Codex 원문(verbatim)
> | Prior finding | r2 status | Re-check |
> |---|---|---|
> | 1. Incomplete Trial #2 coverage | **CLOSED** | B2 specifies all 205 variants, all 1,000 P1 draws, the merge, and an exact output-file inventory comparison. The [draft checker](/home/cms/project/BTC_Futures_E2E/scripts/t2_regression_check.py) implements those comparisons. |
> | 2. Evaluator bypass presented as a rerun | **CLOSED** | B3 calls the report recomputation a diagnostic and leaves the closed evaluation untouched. |
> | 3. Invalid liquidation invariant | **CLOSED** | T3 compares identical restored positions and allows full replays to differ through entry sizing. |
> | 4. Trial #3 P1 wiring | **CLOSED at plan level** | B6 requires 6 bps at placement and execution, with an integration test in step (e). That implementation remains future work. |
> | 5. Imprecise 22 bps assertion | **CLOSED** | T1 uses exact adverse fills and wallet arithmetic; 22 bps is described as nominal. |
> 
> **Q1–Q3:** The gate-free calls are suitable for a regression diagnostic; the default-preserving signatures cover the identified Trial #1, Trial #2, and bot callers; B7 correctly calls for a registry note and ops log evidence.
> 
> **B2+B3 do not yet prove Trial #2 is unaffected.** They define a sufficient check for *byte identity of the recorded Trial #2 IS outputs* if the full baseline and after runs pass. I found no recorded results, and ran nothing. The draft checker is currently untracked and has a `--skip-runs` mode, so that mode must not be used as regression evidence. The baseline worktree also needs access to the ignored `var/backtest/t2/IS` data; a checkout alone will not contain it.
> 
> B3’s reason for omitting an authoritative gated rerun is sound for this question: running H’s old code would not test the changed code, while the changed code intentionally fails H’s fingerprint. The one-shot rule prevents writing another evaluation in the closed location; it does not make a separate rerun at H impossible.
> 
> **VERDICT: PROCEED**
> 
> Codex session ID: 01a0ecbc-7185-75e2-9328-c2d6d4565f04
> Resume in Codex: codex resume 01a0ecbc-7185-75e2-9328-c2d6d4565f04

## 2026-09-29 — 트라이얼 #3 (b) 슬리피지 매개변수 **after-pass**(advisor + Codex task-mumm96nx-og920u **MERGE**)
- 커밋: 77cef80(회귀 검사 스크립트 · 기준선 전에 푸시) · dc23273(변경 + 테스트) · 이 커밋(증거 · 정적 검사 강화 · 기록).
- `git show --stat dc23273`:
   backtest/engine_replay.py    |   9 ++-
   backtest/placebo_exec.py     |  18 +++--
   tests/test_slippage_param.py | 174 +++++++++++++++++++++++++++++++++++++++++++
   3 files changed, 192 insertions(+), 9 deletions(-)
- 트라이얼 #2 회귀(전체 205 + P1 0..999 + 병합 · 1,043파일): 기준선(워크트리 77cef80 · 변경 전 코드 · 36:05 · 3.64 GB) · 변경 후(main dc23273 · 35:33 · 3.63 GB) **둘 다 identical · 불일치 0** · 두 재실행 트리 838개 비-meta 파일 SHA256 목록 바이트 동일 · 판정기 report 재계산 9223047c…(진단 · 새 판정 아님 · evaluation/ 무수정). 증거 `docs/trials/trial_03_step_b_regression/`. 기준선 워크트리는 제거·prune.
- 트라이얼 #2 지문: 77cef80 = `9416d9e2…`(기록된 gate 지문 · 마지막 일치 커밋) · main dc23273 = `1f08d389…` → 트라이얼 #2 문(단계·판정기)은 main에서 의도적으로 거부. 트라이얼 #2는 H 63c1760 · 지문 9416d9e2…로 닫힌 채.
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 B7 해시 확인 | ✅ | 위 지문 두 값 실측 |
| advisor | 2 증거 영구화 | ✅ | `docs/trials/trial_03_step_b_regression/` 커밋 |
| advisor | 3 워크트리 제거 | ✅ | remove + prune |
| advisor | 4 레지스트리 행 | ✅ | #51 |
| advisor | 5 보고 틀 | ✅ | 보고에 반영(펀딩 00/08/16 테스트 → (c) · P1 두 지점 + 통합 테스트 → (e) · 결정 시점 B2 견적 → (d) 규약 행) |
| advisor | 6 순서 | ✅ | 기록 → 커밋 → 푸시 → 보고 → 멈춤 |
| Codex | 1 B1 일치 | ✅ | — |
| Codex | 2 정적 검사가 두 모듈 제한을 강제하지 않음(MINOR) | ✅ | 전달은 engine_replay·placebo_exec에서만 허용하도록 강화 |
| Codex | 3 증거가 바이트 동일을 뒷받침 | ✅ | — |
| Codex | 4 B7 기록 | ✅ | #51 · 이 항목 |

### advisor 원문(verbatim)
> This is the advisor half of the (b) after-pass. The change matches plan r2 B1/B5 exactly: two files, keyword-only parameters, defaults = #7, no trade-record fields, both `PaperSender` instances in `run_time_exit` wired. The regression evidence is the strongest form available — full 205 + 1,000 + merge, baseline reproduced on pre-change code in an isolated worktree, after-run on the pushed commit, and a direct tree-to-tree cross-check. No substantive objection. What remains is record-keeping, and three items are gaps your checks didn't cover:
> 
> **1. B7 is still "to verify" in your own after-brief — close it with hashes before Codex lands.** In the worktree (still at 77cef80): `uv run python -c "from backtest import t2_provenance as PV; print(PV.fingerprint())"`; on main (dc23273): same command. Expected: worktree = `9416d9e2…` (the recorded gate fingerprint in `runs/A/meta.json`), main ≠. If the worktree value is *not* `9416d9e2…`, stop and find what changed the fingerprint set since 63c1760 before writing B7 — don't write "77cef80" as the last-matching commit on inference.
> 
> **2. The regression evidence exists only in scratchpad, which is wiped between sessions — that violates "nothing stays local-only."** Commit `t2reg_baseline/summary.json`, `t2reg_after/summary.json`, `h_base.txt`, `h_after.txt` (838 lines each) under `docs/trials/trial_03_step_b_regression/` with a one-paragraph README stating: what each is, that the evaluator hash is a diagnostic recomputation (B3), the commits each ran on, wall time and RSS. Then ops_log quotes both summary JSONs verbatim. Secret scan before push as usual — the summaries contain only paths and hashes.
> 
> **3. Remove the worktree after item 1.** `git worktree remove --force <path>` then `git worktree prune`. Otherwise `.git/worktrees/` keeps a stale entry pointing at a wiped directory, and the next `git status`/`git worktree list` in a future session will surprise you. Record in ops_log that the baseline ran there.
> 
> **4. Registry row — Codex before-pass Q3 asked for one, so write it (append-only):** shared-layer change (b): commits 77cef80/dc23273; the two signatures; trial #2 regression identical (1,043 files, report `9223047c…` before and after); main after dc23273 intentionally fails trial #2's provenance gate; last matching commit per item 1. Not a gate value; conventions row still pending before P&L.
> 
> **5. Report framing — three things the user will read for:**
> - Say plainly: "evaluator output bit-identical" is a *diagnostic recomputation* through the evaluator's own `compute → verdict → report` path with provenance/inventory/write steps removed; a gated rerun is one-shot and refuses on main by design. Give why that's the right proof (new code on old inputs; a rerun at H would test old code).
> - Diff stat from `git show --stat dc23273` (the +/− counts in your brief predate the ruff import reorder).
> - Carried items with their step: funding 00/08/16 tests → (c); trial #3 P1 passes the rate at placement *and* execution + integration test → (e); decision-time B2 gate quotes `m` through `adverse_fill_estimate(…, 0.0006)` → (d) conventions row. State them so the user doesn't read the funding tests as dropped.
> 
> **6. Sequence after Codex lands:** log advisor + Codex verbatim with positions → items 1–4 → commit → push → report → **stop**. The user's rule is explicit: report both passes and the diff summary before (c). Update `memory/trial03-status.md` to "(b) complete, after-pass MERGE, waiting on user before (c)" in the same commit.
> 
> One thing to watch when Codex returns: if it flags the `--skip-runs` mode again, the answer is already in the script docstring and both summaries show `"skip_runs": false` — cite that, don't remove the flag (it's a useful 30-second path-check).

### Codex 원문(verbatim · task-mumm96nx-og920u)
> 1. **B1 matches plan r2.** Commit `dc23273` adds a keyword-only rate through `replay`, sizing, time exit, and P1 passthrough. Both entry sizing and execution use the supplied rate. The default remains 2 bps; Trial #1 callers and the bot keep that default. No trade-record fields or other shared layers changed. [replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:70), [placebo_exec](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:43)
> 
> 2. **B5 has no blocking test gap.** The tests check exact adverse entry and exit fills in both directions, wallet arithmetic, SL exits, and liquidation with identical restored positions. The time-exit paths exercise `close_now`. The reported 1,228-pass suite, ruff, and pyright results were supplied; I did not rerun them. One minor weakness: the static test permits `slippage_rate=rate` anywhere it scans, so it does not enforce B5’s stated “two passthrough modules only” rule. There is no offending call in this diff. [tests](/home/cms/project/BTC_Futures_E2E/tests/test_slippage_param.py:80)
> 
> 3. **The regression evidence supports byte identity for Trial #2 IS outputs under the changed code.** Both summaries say `skip_runs=false`, 205 strategy runs, eight P1 parts, 1,043 files, and zero mismatches. I independently compared the saved baseline and after rerun trees: **all 1,043 files are byte-identical**, including metadata. Against the recorded runs, the only 205 differing files are `meta.json`, differing solely in `git_head` and `gate`, as the checker specifies. The recomputed report hash matches the closed report, but that recomputation is correctly labelled a diagnostic, not a new gated evaluation. [checker](/home/cms/project/BTC_Futures_E2E/scripts/t2_regression_check.py:51)
> 
> 4. **Record B7 before step (c).** Add an append-only registry note and an ops_log after-pass entry with the two commit hashes, summary hashes, coverage and comparison result, and the diagnostic-only evaluator qualification. State that Trial #2 remains closed under H `63c1760` and fingerprint `9416d9e2…`; `77cef80` is the last pre-change commit with that fingerprint. `dc23273` has fingerprint `1f08d389…`, so Trial #2’s gated stages intentionally refuse on current main. The evidence directory is currently untracked; include durable evidence when making the record. [plan B7](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:7312)
> 
> **VERDICT: MERGE.** The remaining work is the required record, not a code or regression blocker.
> 
> Codex session ID: 01a0ed01-dd3a-7470-890e-b9fbde97d06e
> Resume in Codex: codex resume 01a0ed01-dd3a-7470-890e-b9fbde97d06e

### 기준선 summary.json(verbatim)
```json
{
 "closed_report_expected": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "closed_report_sha256": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "files_compared": 1043,
 "head": "77cef80bda71418559f31f2517c91c9b530b1e45",
 "identical": true,
 "mismatches": [],
 "p1_parts": 8,
 "pins_commit": "7b8b842f1050ec9e7f68896cf3b2b9432aeb2e0d",
 "report_sha256_recorded_runs": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "report_sha256_rerun": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "skip_runs": false,
 "strategy_runs": 205,
 "t2_base": "/home/cms/project/BTC_Futures_E2E/var/backtest/t2/IS",
 "verdict_recorded_equal": true,
 "verdict_rerun_equal": true
}
```

### 변경 후 summary.json(verbatim)
```json
{
 "closed_report_expected": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "closed_report_sha256": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "files_compared": 1043,
 "head": "dc23273ae4c39c43208eee6ea3963d3fc58aa4fa",
 "identical": true,
 "mismatches": [],
 "p1_parts": 8,
 "pins_commit": "7b8b842f1050ec9e7f68896cf3b2b9432aeb2e0d",
 "report_sha256_recorded_runs": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "report_sha256_rerun": "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e",
 "skip_runs": false,
 "strategy_runs": 205,
 "t2_base": "/home/cms/project/BTC_Futures_E2E/var/backtest/t2/IS",
 "verdict_recorded_equal": true,
 "verdict_rerun_equal": true
}
```

## 2026-09-29 — 트라이얼 #3 (c) 시간 청산 훅 **before-pass**(advisor + Codex task-mumqvoi8-jz937g **FIX-PLAN-FIRST**) → 계획 r2 · **종료 봉 규칙은 사용자 결정 대기**
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 동치 주장 정확히 | ✅ | X2 |
| advisor | 2 누락 봉 가드 시점 | ✅ | X4(i) · before_minute는 펀딩 전 · 테스트로 확인 |
| advisor | 3 busy 기록은 메모리 | ✅ | X5 |
| advisor | 4 ms 산술·240봉 | ✅ | X3 |
| advisor | 5 경계 최대 1회 | ✅ | X6 |
| advisor | 6 Q3 | ✅ | X6 |
| advisor | 7 규약 문장 | ✅ | X2 |
| advisor | 8 공유 변경 확인 | ✅ | X8 |
| advisor | 9 순서 | ✅ | — |
| Codex | 1 종료 봉 규칙 미해결(BLOCKER) | ✅ | X1 — 사용자 결정(A/B/C) 전 코드 없음 |
| Codex | 2 동치 주장 범위 | ✅ | X2 · X7 |
| Codex | 3 입력 끝 누락 | ✅ | X4(ii) |
| Codex | 4 busy 기록 | ✅ | X5 |

### 계획 r1 원문
> # Trial #3 step (c) — time-exit hook at fill+240: BEFORE-PASS plan (no code yet)
> 
> Anchored r3 lines (verbatim):
> - §1 line 31 시간 청산: "체결 분 + **240분** 봉(`H = 4시간`)의 처리: ① 그 분의 펀딩 → ② 시가가 이미 추정 청산가 너머면 청산(`liquidation`) → ③ 아니면
>   **시가에 `time_exit`**(MARKET reduceOnly 전량) · 그 봉의 고가·저가로는 판정하지 않는다"
> - §1 line 32 봉 안 순서: "① 펀딩 정산(추정 청산가 재계산) → ② 대기 진입이 있으면 시가에 체결 → ③ 청산 판정 → SL(체결 기준 = SL과 시가 중 불리한 쪽) ·
>   TP·트레일 **없음**"
> - §1 line 35 판정 가능 구간: "[t0 − 270분, t0 + 120 + 5 + 240 + 1분] … 이 구간이 걸친 모든 UTC 날이 완전한 mark 날 … 전진 페이퍼의 결손은 이 규칙이 아니라 G-F 실행 결함"
> 
> ## User conventions (2026-09-29) and how they map to r3
> C1 Clock (user 1): exit bar = t_f + 240 min where t_f = fill bar open_ms; the exit order is placed at that bar's open and filled at its
>    mark open with the adverse-fill model (6 bps in trial #3, via replay(slippage_rate=…)); the hold covers the 240 bars t_f … t_f+239.
>    = r3 line 31. ✔
> C2 Same-minute priority (user 2) — CONFLICT with r3 line 31 in the exit bar. User text: funding → liquidation → stop-loss → time exit,
>    "a stop that triggers in the exit bar takes precedence". r3: in bar t_f+240 only ① funding → ② open-gap liquidation → ③ time_exit at the
>    open; that bar's high/low are NOT evaluated, so no SL check exists in that bar. Proposal: implement r3 (anchored; a different order would
>    need a correction document). Economic note: the only case the orders can differ is an open that gaps beyond SL but not beyond the
>    liquidation price; SL's fill basis would be worse-of(SL, open) = open — the same price and fill as time_exit at the open — so P&L is
>    identical and only the exit_reason label differs (time_exit per r3). In bars t_f … t_f+239 the existing engine path applies unchanged:
>    funding → (pending entry fill at open) → liquidation check on mark high/low → SL check intrabar on mark high/low with fill basis
>    worse-of(SL, open) (paper/engine.py on_bar: sl_ref = min(pos.sl, open) long / max short; _evaluate(low, high)). SL is intrabar, not close.
> C3 Funding tests (user 3) in this step: for each boundary 00:00/08:00/16:00: (a) crossed during the hold → paid exactly once, in that bar
>    before any evaluation; (b) fill in the boundary minute → not paid (replay settles funding before the fill in that minute and only if a
>    position exists); (c) time exit in the boundary minute → paid first, then exit. 9 tests via replay with the trial-#3 hook.
> C4 Position busy (user 4): an event arriving while a position (or pending entry) is open → the strategy records ctx.skip("position_busy")
>    (the anchored §7-3 reason) and raises PositionBusyError → the run fails. Synthetic test with a test-only short cooldown. (Plan r4 S2'
>    recorded + harness-asserted zero; the user now wants it to raise immediately — both satisfied: recorded, then raise.)
> C5 Missing bar at t_f+240 (user 5; "unless r3 says otherwise — quote r3"): r3 line 35 makes the exit bar part of every admissible event's
>    span and requires complete mark days, so in the backtest the exit bar cannot be missing; forward paper gaps are G-F execution defects
>    (line 35 last clause). Proposal (r3): no "next bar within 5 minutes" rule; a missing exit bar in any backtest run → MissingExitBar raised,
>    run fails (would indicate an admissibility bug). Implementation: the schedule detects a bar with open_ms > scheduled exit while a
>    position is still open → raise.
> C6 exit_reason (user 6): existing ExitReason.TIME_EXIT = "time_exit"; no new fields on trade records; no new enum value.
> 
> ## Implementation
> - No change to backtest/engine_replay.py or paper/ expected: the existing hook (exit_at_bar_open → assert no pending → funding already
>   settled → liquidate_if_open_beyond(open) → close_now(open, TIME_EXIT) → bar_events → skip on_bar → on_minute_closed) is exactly r3 line 31.
>   If a shared change turns out necessary → trial #2 regression re-run (user).
> - New strategies/trial03/exit_schedule.py (trial-#3 only): TimeExitSchedule — on EntryFilled in ctx.bar_events (bar t_f) sets due = t_f +
>   240·60,000; on PositionClosed clears; predicate exit_at_bar_open(bar) = due is not None ∧ bar.open_ms == due; guard(bar): due is not None ∧
>   bar.open_ms > due → MissingExitBar. H = 240 from trial-#3 config constant (tf_v1 value).
>   Wiring order inside the strategy (for (d)): replay calls exit_at_bar_open(b) BEFORE the bar's events; the schedule learns the fill from
>   ctx.bar_events in on_minute_closed of bar t_f (fill happens at t_f's open inside on_bar). Guard is called from before_minute (the
>   existing pre-hook) so a skipped exit bar is detected at the first later bar.
> - PositionBusyError helper for (d): busy_check(ctx) → ctx.skip("position_busy") then raise.
> - Tests (test-first, synthetic): predicate True exactly at t_f+240 and never otherwise; SL-closed-early clears the schedule (predicate False
>   at t_f+240, no TIME_EXIT); open-gap liquidation on the exit bar → LIQUIDATION not TIME_EXIT; gap beyond SL but not liq on the exit bar →
>   TIME_EXIT at open (r3), fill == adverse_fill_estimate(open, 6 bps); exit fill at 6 bps; hold = 240 bars (entry_ms and exit_ms differ by
>   240 min); missing exit bar → MissingExitBar; position busy raises; the 9 funding tests; open_at_end is None.
> 
> ## Questions
> Q1 Is implementing r3's exit-bar order (no SL check in bar t_f+240) correct given the user's convention 2, and is the "economically
>    identical, label differs" analysis right?
> Q2 C5: agree that r3 precludes a "next bar within 5 minutes" rule for the backtest?
> Q3 Any engine path where funding at the boundary minute could be settled after the fill (C3b) or not before the exit (C3c)?

### advisor 원문(verbatim)
> This is the advisor half of the (c) before-pass. The plan is right on the two conflicts — r3 line 31 governs the exit bar, and line 35 makes a missing exit bar an admissibility bug, not an execution rule. Flagging both rather than picking is correct. Findings, blocking first:
> 
> **1. BLOCKER — the "economically identical, label differs" claim in C2 is not exactly true; state the difference honestly.** In the gap-beyond-SL-not-beyond-liq case both exits fill at the open through the same 6 bps adverse model, so the fill price is identical. But `gross_bps` is not: the SL path's `ref_mark` is `min(SL, open)` = open for a long gap — same — so gross is identical too in that specific case. Where they *do* differ is one step earlier: if the open gaps beyond SL, the SL path would fire in the *non-hook* `on_bar` only if it were evaluated at all, and r3 says it isn't. So the real statement is: "P&L, fill, and gross are identical; only `exit_reason` differs (time_exit per r3, never sl)." Drop "economically identical" — say "identical wallet, fill and gross; different label." The user reads §7-3's exit-reason breakdown, so the label matters and the claim must be exact.
> 
> **2. MAJOR — C5's guard placement has a timing hole.** You put `MissingExitBar` detection in `before_minute`, which fires at the *first bar after* the missing one. But if the missing bar is t_f+240 and the next present bar is t_f+241, the position is still open at t_f+241's funding step and `on_bar` — the engine will evaluate SL/liquidation on that bar before your guard sees it. Move the guard so it runs before funding: `before_minute` is called first (engine_replay line ~79, before the funding loop), so that's fine — but verify by test that a synthetic gap at t_f+240 raises *before* any engine event at t_f+241 (assert no `PositionClosed` in the trade list and `MissingExitBar` raised). If `before_minute` isn't early enough, this needs a shared change, which triggers the trial #2 rerun.
> 
> **3. MAJOR — C4 raises after `ctx.skip("position_busy")` — check that `replay()` doesn't swallow the exception.** Line 127-128: `except EntryRefused as e: ctx.skip("entry_refused", …)`. A `PositionBusyError` raised inside `on_minute_closed` propagates (it's not `EntryRefused`), good. But the skip record is written to `ctx.decisions`, which lives in memory — when the exception propagates out of `replay()`, the caller gets nothing back. The "recorded, then raise" promise means the harness must catch `PositionBusyError`, persist what it has, then re-raise. That's (d)/(g) harness work; note it in the plan now so the test for (c) asserts only "raises" and the persistence test is deferred.
> 
> **4. C1 boundary — pin the ms arithmetic exactly.** "t_f + 240 min" = `fill_bar.open_ms + 240 · 60_000`. The fill event arrives in `ctx.bar_events` during `on_minute_closed` of bar t_f (fill executed in that bar's `on_bar` at its open). Convention: `due = bar.open_ms + 14_400_000` where `bar` is the one whose `bar_events` contains `EntryFilled`. Test: entry_ms in the trade record == t_f, exit_ms == t_f + 14_400_000 − 1 (close_ms) or == t_f + 14_400_000 (open) — check which `close_now`'s `ts_ms` is (replay passes `t`, the open) and pin it. The user said "240 bars" — assert the count, not just the timestamps.
> 
> **5. Funding C3 — one case the 9-test grid misses.** Fill at 00:00 open, exit at 08:00 open: pays 08:00 once. Fill at 23:59 close (decision) → fill at 00:00 open: pays nothing at 00:00. Both covered. Missing: a hold that crosses *two* boundaries (e.g. fill 07:00, exit 11:00 crosses only 08:00 — fine; but fill 23:00 → exit 03:00 crosses 00:00 only). With H = 240 min, at most one boundary can be crossed (boundaries are 480 min apart). Assert that as a test: no admissible hold pays funding twice. It's a structural fact worth pinning.
> 
> **6. Q3 — funding-before-fill is in the replay loop, not the engine.** Line 86-89: funding settles only if `eng.position is not None`; a pending entry is not a position, so a fill at the boundary minute pays nothing. Line 87-94 hook path: funding loop runs before `hook_bar` evaluation → exit-in-minute pays first. Both hold as written. The test should assert the funding event's `ts_ms` < the exit fill's `ts_ms` in the hook bar, and that `funding_paid_usdt` on `PositionClosed` equals exactly one settlement's amount.
> 
> **7. MINOR — C2 wording for the conventions row.** "SL is intrabar (mark high/low) with fill basis worse-of(SL, open), liquidation checked first on the same bar; the exit bar t_f+240 evaluates neither — funding → open-gap liquidation → time_exit at open." That's the full sentence to pin; the current plan splits it across two paragraphs.
> 
> **8. Zero shared change is the expected outcome — confirm with a diff before the after-pass.** If `git diff --stat dc23273 -- backtest/engine_replay.py paper/` is empty after (c), state that in the report and skip the trial #2 rerun per the user's rule. If it isn't empty, the rerun is mandatory before reporting.
> 
> **9. Sequence:** Codex → log both verbatim with positions → if FIX-PLAN-FIRST, revise and narrow re-check → PROCEED → build test-first (`strategies/trial03/exit_schedule.py` + `tests/test_trial03_exit_schedule.py`) → after-pass → push → report → stop before (d). In the report, lead with the two r3 conflicts and quote lines 31 and 35 — the user asked for exactly that on #5 and will want the same treatment on #2.
> 
> Nothing here changes what you build; items 1, 4, 7 change what you *write*, items 2, 3, 5 add tests.

### Codex 원문(verbatim · task-mumqvoi8-jz937g)
> 1. **BLOCKER — the exit-bar rule is unresolved.** The recorded Trial #3 preregistration says funding, then liquidation if the *open* crosses the liquidation price, then `time_exit` at the open; it explicitly excludes that bar’s high and low ([§1, line 31](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:31)). The replay hook implements exactly that ([engine_replay.py:92](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:92)). User convention 2 is a later explicit instruction, so the plan cannot silently discard it. **Fix:** reconcile the convention with the anchored rule before coding. If the intended SL check is only an open gap, specify that and document the resulting `sl` versus `time_exit` label rule. If “triggers in the exit bar” includes its high or low, the exit can no longer be unconditionally filled at that bar’s open; the execution rule and preregistration need a formal correction. The anchor recorded for this document is in [anchor.py:11](/home/cms/project/BTC_Futures_E2E/strategies/trial03/anchor.py:11).
> 
> 2. **MAJOR — the economic-equivalence claim is too broad.** For an **open already beyond SL but short of liquidation**, both paths use the open as the reference, so the adverse fill and P&L match; the exit reason differs. An SL reached later through the exit bar’s high or low is a different case, and using that later price to override an open fill would use future bar information. **Fix:** limit the equivalence claim to open-gap stops and add separate tests for an intrabar SL crossing and an intrabar liquidation crossing under the resolved rule. Exit-reason counts also change even in the equal-P&L case ([§7-3](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:151)).
> 
> 3. **MAJOR — the missing-bar guard misses an end-of-stream gap.** A guard that raises only when it sees `bar.open_ms > due` cannot detect a replay that ends before the scheduled exit. Replay currently returns such a position as `open_at_end` ([engine_replay.py:139](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:139)). **Fix:** have the Trial #3 harness check the schedule after replay and raise `MissingExitBar` when a due exit remains within the promised input window; test both a skipped exit bar followed by a later bar and one at the end of input.
> 
> 4. **MINOR — clarify the busy-event assertion.** `ctx.skip()` records in a replay context that is never returned when `PositionBusyError` is raised ([engine_replay.py:54](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:54)). **Fix:** test the exception and inspect a strategy-owned log if the recorded reason must be asserted. Keep the immediate failure explicitly an invariant check; the preregistration otherwise defines `position_busy` as a reported skip ([§1, line 34](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:34)).
> 
> **Q1:** Neither the plan’s silent choice of r3 nor a literal intrabar-SL override is ready to implement. The anchored r3 rule governs the registered trial as written; the later user convention governs what the reviewer must address. Reconcile them formally first. The plan’s equal-P&L analysis is correct only for an open-gap SL.
> 
> **Q2:** Yes. Complete mark days across the admissible span include the scheduled exit bar ([§1, line 35](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:35)). A “next bar within five minutes” backtest fill would change the rule. Fail on a missing required bar, including the terminal case above.
> 
> **Q3:** With a boundary funding record in the supplied minute, no: replay settles it before either entry or the exit hook ([engine_replay.py:84](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:84)). Thus a fill in that minute pays none, while a position exiting in that minute pays first. This depends on the admissibility check supplying exactly one verified record per boundary; replay itself does not enforce that input condition.
> 
> **VERDICT: FIX-PLAN-FIRST**
> 
> Codex session ID: 01a0ed78-6359-7b42-a3b7-77d2aba1b680
> Resume in Codex: codex resume 01a0ed78-6359-7b42-a3b7-77d2aba1b680

### 계획 r2 원문
> # Trial #3 (c) plan r2 — resolutions (advisor 1–9 + Codex task-mumqvoi8-jz937g 1–4); exit-bar rule held for the user (Codex 1)
> 
> X1 EXIT-BAR RULE — USER DECISION (Codex 1 BLOCKER). Options:
>    (A) r3 line 31 as anchored: bar t_f+240 = ① funding → ② liquidation iff the OPEN is beyond the estimated liquidation price →
>        ③ time_exit at the open; that bar's high/low are not evaluated; an open that gaps beyond SL but not beyond liquidation is
>        labelled time_exit. Existing replay hook already does exactly this; no document change.
>    (B) Same execution as (A), but an open gap beyond SL (not liq) is labelled `sl`. Fill, wallet and gross identical to (A)
>        (both reference the open: SL fill basis = worse-of(SL, open) = open); only exit_reason and the §7-3 exit-reason counts differ.
>        Changes §1 line 31 text → tf_v1 table hash changes → per §1 line 41 "값이 하나라도 바뀌면 새 버전·새 트라이얼".
>    (C) Literal intrabar SL in the exit bar (high/low) with precedence over time_exit: changes execution (exit not at the open) and
>        §1 lines 31–32 → new tf_v1 / new trial (N rises); also needs a formal correction before any code.
>    Recommendation: (A). (B)/(C) cannot be applied to the anchored trial #3 without a new version/trial.
> X2 Wording (advisor 1/7, Codex 2): equivalence claim limited to the open-gap-beyond-SL case: identical fill, wallet and gross; different
>    exit_reason label (and §7-3 counts). An SL/liquidation reached only through the exit bar's high/low is a different case and, under
>    (A), is not evaluated in that bar. Conventions-row sentence: "SL is intrabar (mark high/low) with fill basis worse-of(SL, open),
>    liquidation checked first on the same bar, in bars t_f … t_f+239; the exit bar t_f+240 evaluates neither — funding → open-gap
>    liquidation → time_exit at the open."
> X3 Clock (advisor 4): due = open_ms of the bar whose bar_events contain EntryFilled + 14,400,000; time_exit ts_ms = the exit bar's open_ms
>    (replay passes t to close_now); tests assert exit_ms − entry_ms == 14,400,000 AND that exactly 240 bars (t_f … t_f+239) were processed
>    with the position open.
> X4 Missing exit bar (Codex 3, advisor 2): (i) guard in before_minute — replay calls it before the funding loop — raises MissingExitBar at
>    the first bar with open_ms > due while scheduled (test asserts no PositionClosed and no funding settled on that later bar);
>    (ii) terminal case: the harness calls schedule.assert_no_due() after replay → MissingExitBar if a due exit remains (end of input).
>    No "next bar within 5 minutes" rule (r3 line 35: exit bar lies inside every admissible span; forward gaps are G-F defects).
> X5 Busy (Codex 4, advisor 3): strategy-owned log records position_busy, then raises PositionBusyError; (c) tests assert the raise and the
>    strategy-owned record; persisting logs on failure is harness work in (d)/(g). Stated as an invariant check (unreachable given 720 > 366).
> X6 Funding (advisor 5/6, Codex Q3): 9 tests (00/08/16 × crossed / fill-in-minute / exit-in-minute) + structural test: with H = 240 and
>    boundaries 480 min apart, a hold pays at most one funding; assert funding ts < exit fill ts in the hook bar and PositionClosed
>    funding_paid_usdt == exactly one settlement amount. Input condition (one verified record per boundary) is enforced by admissibility.
> X7 Additional tests (Codex 2): intrabar SL crossing in bar t_f+239 → sl; intrabar liquidation crossing in t_f+239 → liquidation; in the exit
>    bar, high/low beyond SL or liq but open not → time_exit at open (under (A)).
> X8 Shared-change check (advisor 8): expected zero change to backtest/engine_replay.py and paper/; `git diff --stat dc23273 -- backtest/engine_replay.py
>    paper/` reported; non-empty → trial #2 regression re-run before reporting.

## 2026-09-30 — 트라이얼 #3 (c) 계획 r3·r4: 사용자 결정 (A) · Codex 좁은 재확인
- 사용자(2026-09-30): **(A)** — r3 §1 31행 그대로(종료 봉 = 펀딩 → 시가 갭 청산 → 시가 time_exit · 고가·저가 미판정) · 관례 2 철회 · 문서·tf_v1 무변경. 진단 전용 추가: §7-3 보고에 time_exit 아래 "종료 봉 시가가 이미 SL 너머였던 time_exit" 부분 개수(기존 필드 exit_ref·sl에서 · (f)에서) — 앵커된 산출물 무관(Codex 확인). #5 처리 수용.
- Codex task-mumt2096-4im3qc: 1~4 CLOSED · 새 간극(X6 시각 순서) → 계획 r4 X6′(결과로 검증) · Codex task-mumt4hxr-lw4pht **PROCEED**. 입장: ✅ 전부 동의.

### 계획 r3 원문
> # Trial #3 (c) plan r3 = r2 + user decision (2026-09-30)
> X1 → (A): r3 §1 line 31 as anchored governs the exit bar t_f+240: ① funding → ② liquidation iff the open is already beyond the estimated
>    liquidation price → ③ otherwise time_exit at the open; no high/low evaluation on that bar; an open beyond SL (not liq) is time_exit.
>    User convention 2 withdrawn. No document change, no new code path, tf_v1 unchanged.
> X9 (new, diagnostic only, step f): §7-3 exit-reason report adds a sub-count under time_exit: "time_exit where the exit-bar open was already
>    past the stop-loss price" = time_exit trades with exit_ref ≤ sl (long) / exit_ref ≥ sl (short), from existing trade-record fields
>    (exit_ref = the exit bar's mark open for time_exit; sl = the fixed SL price). Report-only; no execution, record or tf_v1 change.
> X2–X8 unchanged from r2. Tests in (c): 9 funding (00/08/16 × crossed / fill-in-minute / exit-in-minute) + at-most-one-funding structural
>    + position_busy raises + 240-bar hold + exit-bar cases under (A) (open beyond liq → liquidation; open beyond SL only → time_exit at open
>    with adverse 6 bps fill; high/low beyond SL/liq but open not → time_exit) + intrabar SL/liq in t_f+239 + missing exit bar (gap and
>    end-of-input) + open_at_end None.

### Codex 원문(verbatim · task-mumt2096-4im3qc)
> **Narrow re-check:**
> 
> | Prior finding | Status | Reason |
> |---|---|---|
> | 1. Exit-bar rule | **CLOSED** | The user selected anchored option (A) and withdrew convention 2. The rule matches [§1 line 31](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:31) and the existing [replay hook](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:90). |
> | 2. Equivalence claim and intrabar cases | **CLOSED** | X2 limits the equal-fill and equal-P&L claim to an open already beyond SL; X7 covers high/low crossings separately. |
> | 3. Missing exit bar at end of input | **CLOSED** | X4 adds a post-replay schedule check and tests both a skipped bar followed by another bar and end of input. |
> | 4. Busy-event assertion | **CLOSED** | X5 calls for the immediate exception and a strategy-owned record, while assigning failure-log persistence to the later harness work. |
> 
> **X9** uses existing `exit_reason`, `direction`, `exit_ref`, and `sl` trade fields. As a sub-count within `time_exit`, it changes neither the anchored execution rule nor the trade record, `tf_v1`, or the existing [§7-3 exit-reason categories](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:151).
> 
> **New gap:** X6 asks a test to assert `funding.ts_ms < exit-fill.ts_ms` in the exit bar. At a funding boundary, both timestamps equal that bar’s open time: replay settles funding first, then passes the same `t` to `close_now` ([replay loop](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:84)). Replay also discards the `FundingSettled` return rather than passing it to `on_event`. Revise X6 to verify order through a test-only engine spy or the resulting wallet and `PositionClosed.funding_paid_usdt`; do not require strictly increasing timestamps or a shared-code change.
> 
> Read-only review; no tests or code were run.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0edb0-2643-7130-8338-3de532cf99a2
> Resume in Codex: codex resume 01a0edb0-2643-7130-8338-3de532cf99a2

### 계획 r4 원문
> # Trial #3 (c) plan r4 = r3 with X6 fixed (Codex task-mumt2096-4im3qc new gap)
> X6' Funding order in the exit bar is NOT tested by timestamps (funding and time_exit both carry the bar's open ms; replay discards the
>     FundingSettled return). Order is verified by outcome: exit in a boundary minute → PositionClosed.funding_paid_usdt == exactly one
>     settlement (signed_qty × mark × rate) and wallet_after == wallet_before − commissions − that funding + price P&L (exact); fill in a
>     boundary minute → funding_paid_usdt == 0; crossed → exactly one settlement. No shared-code change, no engine spy needed.

### Codex 원문(verbatim · task-mumt4hxr-lw4pht)
> X6′ closes the timestamp-ordering gap. Replay settles funding before the exit hook, while `PositionClosed` exposes the accumulated funding charge. The proposed boundary-minute cases can therefore verify the observable result without comparing timestamps or capturing `FundingSettled`.
> 
> For the wallet assertion, use the entry and exit commissions and fill-price P&L, with the single trade’s entry wallet as the baseline. The earlier findings 1–4 remain closed at the plan level. This is a read-only plan confirmation; the tests have not yet been implemented.
> 
> VERDICT: PROCEED
> 
> Codex session ID: 01a0edb1-ea8a-7353-a4ad-bf89dee21342
> Resume in Codex: codex resume 01a0edb1-ea8a-7353-a4ad-bf89dee21342

## 2026-09-30 — 트라이얼 #3 (c) **after-pass**(advisor + Codex task-mumteweu-o66k9s **FIX-FIRST**) → 테스트 보강
- 코드: 6653d3f(모듈 + 테스트 21) · 공유 코드 변경 없음(`git diff --stat dc23273 -- backtest/engine_replay.py backtest/placebo_exec.py paper/ sizing/ exchange/` 빈 출력) → 트라이얼 #2 재실행 불필요(사용자 규칙).
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 숏 미검증 | ✅ | 숏 테스트 5개(종료 봉 청산 갭 · SL 갭 → time_exit · 펀딩 가로지름 00/08/16 수취 −qty·mark·rate) |
| advisor | 2 (d) 배선 요구 | ✅ | (d) 계획·규약: before_minute에서 guard · 하네스가 replay 뒤 assert_no_due · on_minute_closed 첫 문장이 observe — 프로토콜 검사 + 테스트 |
| advisor | 3 busy 경로 쿨다운 | ✅ | (d): §1 34행대로 쿨다운 시작 → busy_check |
| advisor | 4 순서 증거 과장 금지 | ✅ | Codex 1과 함께: 테스트가 엔진 포지션의 funding_paid == 0을 직접 확인(가드 끈 변형은 0.174 USDT 정산 — 뮤테이션 확인) |
| advisor | 5 규약 문구 | ✅ | 구현 선택 행에 그대로 |
| advisor | 6 기록 | ✅ | 메모리 갱신 |
| Codex | 1 누락 봉 테스트가 '펀딩 전' 주장을 증명 못 함 | ✅ | 엔진 포지션 funding_paid == 0 단언 + 뮤테이션 확인 |
| Codex | 2 입력 끝 테스트 정밀도 | ✅ | 입력이 정확히 t_f+239에서 끝나게 · due == last+1분 |
| Codex | 3 이의 없음 · X9 입력 신뢰 가능 | ✅ | — |
- 검사: 1254 passed · ruff · pyright 0.

### advisor 원문(verbatim)
> This is the advisor half of the (c) after-pass. The implementation matches r3 §1 lines 31–35 and plan r4; the shared diff against `dc23273` is empty, so the user's no-rerun rule applies. Codex will likely confirm the mechanics. What your checks didn't cover:
> 
> **1. MAJOR — every replay test in this file is LONG-only, and arm S is a judged arm.** Three paths (c) claims to have verified are direction-dependent and untested for shorts:
> - `liquidate_if_open_beyond`: short branch is `open ≥ liq_price_est` (engine.py:292).
> - Funding sign: `PositionClosed.funding_paid_usdt` is "+ = 지불"; a short with positive rate *receives*, so the assertion is `== −qty·mark·rate`. Don't assume — assert it.
> - X9 input for shorts: `exit_ref ≥ sl`.
> Add: one short crossed-funding test, one short exit-bar liquidation-gap test, one short SL-gap → time_exit test (SL 60300, open 60350 — below the ~0.9% short liq distance at 100x). Test-only change, no module edit. Do it before the report; the user listed "9 funding" tests and will assume both arms.
> 
> **2. Wiring requirements the (c) module can't enforce — pin them for (d) now.** `guard` only runs if the strategy implements `before_minute`; `assert_no_due` only runs if the harness calls it after `replay()`; `observe` only sees a fill if it's the *first* statement in `on_minute_closed` (an early return before it would miss `EntryFilled`). Put all three in the conventions list and in the (d) plan as protocol checks with tests. Right now the guarantee lives only in a test fixture (`Scripted`).
> 
> **3. Busy-path cooldown.** §1 line 34: "포지션 중의 적격 이벤트 = `position_busy`(쿨다운은 시작)". `busy_check` raises immediately; in (d) the strategy must start the cooldown *before* calling it, or the forced-fixture test can't observe the anchored behaviour. Note for the (d) plan, not a (c) change.
> 
> **4. Ordering evidence — state it precisely in the report.** The gap test proves "no `PositionClosed`," not "no funding settled" (`FundingSettled` is discarded by replay). The guard-before-funding claim rests on code order (`pre_hook` line 79–80 precedes the funding loop at 86), not on a test. Say so; don't overclaim.
> 
> **5. Conventions to pin in the implementer-choices row (final wording, from what was built):**
> - Clock: `due = open_ms(bar with EntryFilled) + 14,400,000`; `time_exit.ts_ms` = exit bar `open_ms`; hold = bars t_f … t_f+239 (240 closes with position open).
> - Exit bar t_f+240: funding → liquidation iff open beyond est. liq (≤ long / ≥ short, boundary inclusive) → `time_exit` at open via `adverse_fill_estimate(…, 0.0006)`; high/low not evaluated. Bars t_f…t_f+239: liquidation then SL, intrabar mark high/low, SL fill basis worse-of(SL, open).
> - Missing exit bar: fail (gap → `MissingExitBar` at next bar before funding; end of input → after replay). No substitute bar.
> - `position_busy`: strategy-owned record, then `PositionBusyError`; invariant (720 > 366).
> - Funding order verified by outcome (`funding_paid_usdt`, exact wallet decomposition), not timestamps.
> - `exit_reason` = existing `time_exit`; no new trade fields.
> - X9 (f, report-only): count of `time_exit` rows with `Decimal(exit_ref) ≤ Decimal(sl)` (long) / `≥` (short), from trade-record strings.
> - `HOLD_MIN = 240` defined in `strategies/trial03/exit_schedule.py`; (d) config imports it.
> 
> **6. Records before the report:** `memory/trial03-status.md` still says "WAITING on user exit-bar decision" — update to "(c) done, after-pass MERGE, waiting before (d)". Log advisor + Codex verbatim with positions; report with the `git diff --stat dc23273 -- backtest/engine_replay.py backtest/placebo_exec.py paper/ sizing/ exchange/` output shown empty.
> 
> **Sequence:** Codex lands → log both → add the short tests (item 1) + any Codex fixes → full suite → commit → push → memory → report → stop before (d). Item 1 is the only thing that changes what ships; 2–5 change what you write.

### Codex 원문(verbatim · task-mumteweu-o66k9s)
> 1. **FIX-FIRST — the missing-bar test does not prove its “before funding” claim.** [The test](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_exit_schedule.py:156) supplies funding on the first bar after the gap, but asserts only that no `PositionClosed` event was emitted. [Replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:84) does not send funding events to `on_event`, so that assertion would still pass if funding settled before `MissingExitBar` was raised. Add an observable check that funding was not settled, as plan r4’s X4 requires. The current code order appears correct; the gap is in the test.
> 
> 2. **Minor test precision:** [The end-of-input case](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_exit_schedule.py:168) stops well before the due bar. It exercises `assert_no_due()`, but ending at `t_f+239` would directly test a missing scheduled exit bar.
> 
> 3. **No other objection found.** The schedule and replay hook match [r3 §1 lines 31–35](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:31) and [plan r4](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:7626). The boundary-minute fill test is meaningful: an incorrectly charged fill would make its zero-funding assertion fail. For X9, completed paper `time_exit` trade records reliably contain `exit_ref` from the exit bar’s mark open and the fixed `sl` from the entry decision. The commit and diff against `dc23273` show no shared-code changes.
> 
> I attempted the permitted test command, but `uv` could not create its cache lock on the read-only filesystem; I cannot confirm a passing test run here.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0edb9-5423-79c0-aa9e-327f5a2ab19a
> Resume in Codex: codex resume 01a0edb9-5423-79c0-aa9e-327f5a2ab19a

## 2026-09-30 — 트라이얼 #3 (c) after-pass 수정 확인(Codex task-mumtn07v-9i0by7) **MERGE**
- 입장: ✅ 동의. (c) 완료 — (d) 전 사용자 보고에서 멈춤.

### Codex 원문(verbatim)
> **CLOSED.** The missing-bar test now checks the engine position’s `funding_paid == 0` after `MissingExitBar`, so it observes whether funding settled. The end-of-input test ends at `t_f+239` and asserts that the due bar is exactly one minute later. The five short-side cases are present. [Review file](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_exit_schedule.py:160)
> 
> I confirmed these points from HEAD and the replay code. I could not rerun the tests here because `pytest` is unavailable; the reported 1254 passing tests, ruff, pyright, and mutation check remain locally reported results.
> 
> **VERDICT: MERGE**
> 
> Codex session ID: 01a0edbf-1948-7cf2-b8df-f0a69c86b42b
> Resume in Codex: codex resume 01a0edbf-1948-7cf2-b8df-f0a69c86b42b

## 2026-09-30 — 트라이얼 #3 (d) 상태 기계 **before-pass**(advisor + Codex task-mumulo1j-r9o5b4 FIX-PLAN-FIRST → r2 task-mumutx8d-6eco72 FIX-PLAN-FIRST → r3 task-mumuy2hq-8vadui **PROCEED**)
- **사용자 요구 7과 충돌(보고에 명시)**: "decision mark priced with the same 6 bps model"은 r3 §1 29행 "결정 시점 B2 게이트(기준가 m · SL 가격 · E_ref로 정본 size_entry)" · 30행 "엔진이 실행 시점에 B2 재사이징(예상 체결가 …)"과 모순 — 그 문구는 (b) advisor 8의 제안을 내가 (b) 보고에 옮긴 것. 앵커 문언을 따른다: 결정 = size_entry(m 그대로), 6 bps는 체결 시점만(D1). 사용자 요구 1의 이름 별칭은 §7-3 이름으로(cooling_timeout → not_cooled · sizing_gate_fail → sizing_rejected_{decision|fill} · quantile_invalid_day → quantile_invalid).
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 창 소속 한 칸 어긋남 | ✅ | D2(open 기준) |
| advisor | 2 결정 값 보관 위치 | ✅ | D7(intent 기록 · trades_t3) |
| advisor | 3 이벤트당 결정 하나 | ✅ | D5 |
| advisor | 4 window_end·r30_undefined 자리 | ✅ | D10 부사유 |
| advisor | 5 도달 불가 사유(0 기대) | ✅ | D11 · 테스트 전용 규칙 픽스처 |
| advisor | 6 RejectReason 매핑 | ✅ | D6 |
| advisor | 7 핀 | ✅ | D9·D9′(시각 구간은 닫힌 시각점 — Codex r2) |
| advisor | 8 추가 테스트 | ✅ | D12 |
| advisor | 9 Q2·Q3 | ✅ | — |
| advisor | 10 규약 문서·행 | ✅ | D13 |
| Codex | 1 결정 시점 B2 가격(BLOCKER) | ✅ | D1 — m 그대로(advisor (b) 8·사용자 요구 7과 달리 앵커 문언) |
| Codex | 2 창 한 칸 | ✅ | D2 → r3 D2′(구간 끝 ≤ IS_END) |
| Codex | 3 P2 ms | ✅ | D4 → r3 D4′(decided_ms = open + 59,999) |
| Codex | 4 워밍업 | ✅ | D3 |
| Codex | 5 결과 회계 | ✅ | D6 |
| Codex | 6 경계 순서 | ✅ | D8 |

### 계획 r1 원문
> # Trial #3 step (d) — strategy state machine + P2/P3 variants + harness: BEFORE-PASS plan (no code yet)
> 
> Spec: docs/trials/trial_03_preregistration.md §1 lines 22–39 (tf_v1), §4 (P2/P3), §7-3 (funnels); plan r5 S2'/S8/S10/S11/S12;
> (c) conventions; user (d) requirements 1–10 (2026-09-30). All on synthetic data; no real-data read.
> 
> ## Anchored lines that fix the requirements (verbatim)
> - line 24 quantile: "날 d마다 **00:00에 한 번** 계산: 표본 = d−90 … d−1 날의 모든 1m 종가 t의 r30[t] · 129,600분 중 **99% 이상** 정의돼야 한다(아니면 그날
>   이벤트 없음 `quantile_invalid`) · numpy 선형 분위수 · `q_dn = Q(0.005)` · `q_up = Q(0.995)` · 그날 자신의 r30은 쓰지 않는다"
> - line 25 OI: "metrics 행(create_time = c)은 **c + 5분부터 쓸 수 있다** · `OI_now(t)` = c + 5분 ≤ t인 최근 행 ∧ t − (c + 5분) ≤ 10분 · `OI_prev(t)` =
>   c + 5분 ≤ t − 30분인 최근 행 ∧ (t − 30분) − (c + 5분) ≤ 10분 · `oi_ok = sum_open_interest(OI_now) − sum_open_interest(OI_prev) < 0` · 어느 행이든
>   없으면 `oi_missing` · 둘 다 있고 감소가 아니면 `oi_not_decreasing` · 둘 다 **적격 이벤트가 아니고 쿨다운을 시작하지 않는다**"
> - line 26–27 event/cooldown: "1m 봉 마감 t에서 L: r30[t] ≤ q_dn / S: r30[t] ≥ q_up ∧ oi_ok ∧ 판정 가능 ∧ t ≥ cooldown_end" ·
>   "적격 이벤트마다(진입 여부와 무관 — 바쁨·식지 않음·건너뜀 포함) `cooldown_end = t0 + 12시간`(끝 제외) · 암별"
>   → an event at exactly t0 + 720 min IS allowed; t0 + 719 is in cooldown (user req. 9).
> - line 28 cooling: "t0 이후 봉 마감 t_e에서 `t_e − t0 ≥ 20분`(포함) ∧ `rv5[t_e] ≤ 0.5 × rv_peak` · rv5[t] = t−5…t mark 종가로 만든 1m 로그수익률 5개의
>   표본표준편차(ddof 1) · rv_peak = max(rv5[u] : t0 − 30분 ≤ u ≤ t_e)(현재 봉 포함) · `t_e − t0 > 120분`인 첫 봉에서 `not_cooled`(포함 경계: 120분까지 진입 가능)"
> - line 29 decision gate (ATR/SL/band/B2 at decision) and line 30 entry: "다음 1m 봉 mark 시가를 기준가로 · 엔진이 실행 시점에 B2 재사이징 … 결정·체결
>   두 번 모두 통과해야 체결 · 체결가 = 기준가 ± 6 bps 불리 + 불리 tick · 실행 시 SL이 이미 넘어가 있으면 `sl_crossed_before_fill`"
> - line 34: "포지션(또는 대기 진입)이 있는 동안의 적격 이벤트 = `position_busy`(쿨다운은 시작)"
> - line 38 B2 sizing; §7-3 funnel names (event funnel: quantile_invalid → no_tail → not_admissible → in_cooldown → oi_missing → oi_not_decreasing →
>   qualified; entry funnel: position_busy · not_cooled · sl_dist_out_of_range(floor/ceiling) · sizing_rejected(decision) · sl_crossed_before_fill ·
>   sizing_rejected(fill) · normalization → filled).
> 
> ## Clock (plan r5 S8, pinned)
> Bar k has open_ms o_k; its close/decision time T_k = o_k + 60,000. "1m 봉 마감 t" = T_k. r30[T_k] = ln(M_close[bar k] / M_close[bar with
> T = T_k − 30 min]) in float64 from Decimal strings; undefined if either close absent or non-positive. Day d's quantile sample = r30 at every
> T_k with o_k in day d−90 … d−1 (1440 per day; the first ones reach into d−91's last 30 closes); computed when the first bar of d is handled
> (before judging it); defined ≥ ceil(0.99 × 129,600) = 128,304 else the whole day is quantile_invalid. numpy.quantile(x, p, method="linear"),
> compare ≤ / ≥ inclusive. OI: rows = (create_time c, value) from oi_5m.json (valid only) + unusable slot list; t = T_k.
> OI_now = latest valid row with c + 300,000 ≤ T_k and T_k − (c + 300,000) ≤ 600,000; OI_prev same at T_k − 1,800,000. Missing → oi_missing,
> sub-reason `unusable` iff an unusable slot c' exists with c' + 300,000 ≤ t_ref and t_ref − (c' + 300,000) ≤ 600,000 for a missing side
> (no search beyond the age window), else `absent`. oi_ok ⇔ Decimal(now) − Decimal(prev) < 0.
> 
> ## State machine (user req. 1) — one instance per arm; engine/ledger per arm (separate replay() calls)
> States: IDLE → (tail ∧ admissible ∧ not in cooldown ∧ oi_ok) FLUSH_QUALIFIED(t0) [instant: cooldown_end = t0 + 720 min set HERE, before the
> busy check] → busy? (ctx.has_position) → record position_busy, raise PositionBusyError (run fails; invariant 720 > 366) → COOLING →
> per bar close t_e > t0: if t_e − t0 > 120 min → not_cooled → COOLDOWN; elif t_e − t0 ≥ 20 min ∧ rv5 ≤ 0.5·rv_peak → DECISION:
> ATR_15m, SL, band → sl_dist_out_of_range_floor | _ceiling → COOLDOWN; decision-time B2 (size_entry(adverse_fill_estimate(side, m, tick,
> 0.0006), SL_rounded, dir, E_ref, REGIME, rules, LIMITS)) → sizing_rejected_decision → COOLDOWN; pass → ENTRY_PENDING (intent emitted at
> t_e close; P2: emitted at close of t_e + k) → engine at next open: EntrySkipped(SL_CROSSED_BEFORE_FILL) → sl_crossed_before_fill →
> COOLDOWN; EntrySkipped(SIZING_REJECTED) → sizing_rejected_fill or normalization (Q1) → COOLDOWN; EntryFilled → IN_POSITION (exit schedule
> t_f + 240, (c)) → PositionClosed(sl | liquidation | time_exit) → COOLDOWN → first bar close with T_k ≥ cooldown_end → IDLE.
> COOLDOWN is always relative to t0 (not exit). Tail minutes during COOLING/ENTRY_PENDING/IN_POSITION/COOLDOWN fall in the event funnel as
> in_cooldown (they are before cooldown_end) — hence position_busy is unreachable.
> Event log (strategy-owned, JSONL-able, enumeration FIXED in the conventions row): per arm, every tail minute (r30 beyond its threshold) with
> its first-failure reason (not_admissible, in_cooldown, oi_missing{absent|unusable}, oi_not_decreasing, qualified) and every transition
> (qualified, position_busy, not_cooled, sl_dist_out_of_range{floor|ceiling}, sizing_rejected_decision, intent, sl_crossed_before_fill,
> sizing_rejected_fill, normalization, filled, exit{sl|liquidation|time_exit}, idle). Counts only (no per-minute rows) for quantile_invalid
> and no_tail. User aliases → anchored names: cooling_timeout → not_cooled; sizing_gate_fail → sizing_rejected_{decision|fill};
> quantile_invalid_day → quantile_invalid.
> Funnel denominator = window bar closes (T_k within [IS_START, IS_END]); warm-up bars update state only.
> 
> ## Decision details (user req. 5–7)
> - Cooling evaluated at each bar close t_e with t_e > t0; t_e − t0 ≥ 20 min inclusive; last allowed t_e = t0 + 120 min; fill at the NEXT
>   bar's open (line 30). rv5[t] from the 6 mark closes at T−5 … T (5 log returns, ddof 1); rv_peak over u ∈ [t0 − 30 min, t_e] (bar closes).
> - ATR_15m: buckets [b, b+15 min) UTC-aligned, bucket H = max mark_high, L = min mark_low, C = mark_close of its last minute; complete = 15 bars;
>   the 14 TRs of the last 14 complete buckets whose end b+15 ≤ T (15 buckets needed, contiguous), Decimal; simple mean.
> - m = t_e mark close; SL_raw = m ∓ 1.5·ATR; SL = normalize_price(SL_raw) (HALF_UP to the snapshot tick — not a literal); sl_dist (band) =
>   1.5·ATR/m unrounded; band [0.0044, 0.0500] inclusive; floor/ceiling separate reasons.
> - B2 via canonical size_entry + LIMITS = SizingLimits(leverage_range=(10, 30), liq_fee_on_liq_price=True) (trial #2's, same constitution
>   values; pos_pct_max default 0.40), REGIME risk 0.01, E_ref 1,000 (sizing_capital), rules from #48 snapshot only. Engine re-sizes at fill.
> - P2 (+1/+5): decision at t_e unchanged; intent emitted at close of t_e + k (fills t_e + k + 1 open); book flat check at emission
>   (busy → raise). P3: decision gate (band + B2) in the ORIGINAL direction with the original SL; intent direction reversed with SL mirrored
>   about m: SL' = normalize_price(m ± 1.5·ATR) (opposite side); engine re-sizes for the reversed direction.
> - (c) wiring: exit schedule observe() is the first statement of on_minute_closed; guard() in before_minute; harness calls
>   assert_no_due() after replay; per-run assertions: position_busy count 0 (raise), entry_refused 0, open_at_end None.
> 
> ## Harness (strategies/trial03/harness.py) — pure over prepared inputs
> - admissible(t0) bitmap: every UTC day touched by [t0 − 270 min, t0 + 366 min] is complete (1,440 aligned bars, finite mark OHLC) AND each
>   00/08/16 boundary in [t0, t0 + 366 min] has exactly one validated funding record; shared by L/S and base/P2/P3; t0 = T_k.
> - window: events only for t0 ≥ IS_START and t0 + 366 min ≤ IS_END (span end ≤ window end); V = window days that are complete ∧ quantile-valid
>   (recorded per run for the evaluator's recomputation).
> - run_arm(arm, variant) → replay(..., slippage_rate=0.0006, sizing_capital=E_ref, limits=LIMITS) → trades, event log, funnel counts.
> 
> ## Tests (user req. 8–9)
> Per transition and per abort reason, long (L) and short (S), synthetic bars/OI/funding: quantile_invalid day; no_tail; not_admissible;
> in_cooldown (event at t0+719 blocked, at t0+720 allowed — line 27 "끝 제외"); oi_missing absent and unusable; oi_not_decreasing (and
> neither starts cooldown); qualified → cooling → not_cooled at t0+121 (t0+120 still allowed); entry at ≥ 20 min with rv condition; sl_dist
> floor/ceiling; sizing_rejected_decision; sl_crossed_before_fill; sizing_rejected_fill; normalization; filled → exit sl / liquidation /
> time_exit → COOLDOWN → IDLE; position_busy forced (test-only short cooldown) records then raises and cooldown was started first; P2 +1/+5
> fill timing; P3 reversed direction + mirrored SL + original-direction decision gate. End-to-end per arm with a hand-computed expected
> ledger (entry/exit times, fills, qty, leverage, net). Determinism: two runs → identical SHA256 of trades and event logs. Quantile edge:
> exactly 128,304 defined → valid; 128,303 → invalid. Static check: no rolling price max/min channel in strategies/trial03 (rv_peak allowed).
> 
> ## Questions
> Q1 How to split engine EntrySkipped(SIZING_REJECTED) into sizing_rejected(fill) vs normalization (§7-3 lists both)? Proposal: normalization
>    iff the SizingDecision reason is the qty-floor/MIN_NOTIONAL failure category; otherwise sizing_rejected_fill. Needs the decision's reason code.
> Q2 Anything in the state machine that contradicts r3 (esp. COOLDOWN relative to t0; tail minutes during a position counted as in_cooldown)?
> Q3 Is a per-tail-minute event log (not per minute) sufficient for §7-3, with counts for quantile_invalid/no_tail?
> Q4 Implementer-choices row: which items beyond this plan must be in it before P&L?

### advisor 원문(verbatim)
> This is the advisor half of the (d) before-pass. The plan is faithful to r3 §1/§4/§7-3 where it quotes them; the clock, cooldown-at-qualification, and P2/P3 semantics are right. What follows are the two-implementer forks the plan leaves open — each is a line for the conventions doc — plus a few test-design facts. Blocking first.
> 
> **1. BLOCKER — window membership is off by one as written.** "Funnel denominator = window bar closes (T_k within [IS_START, IS_END])" excludes the last IS bar (open 23:59 Dec 31 2025, T = 2026-01-01 00:00:00.000 > IS_END) and *includes* the last warm-up bar (open 23:59 Dec 31 2023, T = IS_START), making it a legal t0 although its open is in the warm-up. Pin one rule for everything: a bar belongs to the day of its `open_ms` (line 22 `day_index`), and window membership, the denominator, the quantile that applies to it, and its sample membership all follow the open. Event t0 = T_k of a bar with open in the window. Then V (by day) and the denominator agree. State the resulting fact: the first bar the window can qualify is open 00:00 Jan 1 (T = 00:01).
> 
> **2. MAJOR — say where decision-time values live; the plan needs them and (b) forbade new trade fields.** Plan r5 S8 said decision-time `sl_dist`/SL are "recorded in the trade record"; (b) decided the shared trade dict is frozen. P1 (e) needs the decision-time `sl_dist = 1.5·ATR/m` per source trade, and X9 needs `sl` vs `exit_ref` (that one is already in the trade record via `decision.sl`). Pin: the strategy's `intent` event carries `t0, t_e, m, ATR_15m, SL_raw, SL_rounded, sl_dist, decision quote, decision qty/L, variant, decided_ms`; the harness writes a per-arm `trades_t3.jsonl` that joins replay trades to intents by `trade_id ↔ intent order` (one open intent at a time makes the join unambiguous — assert it). P1 reads that file, never the shared trade dict.
> 
> **3. MAJOR — one decision per event; aborts are terminal.** The plan says the first cooled bar triggers the decision but doesn't say what happens on a band/sizing abort — retry at the next cooled bar, or done? §7-3's entry funnel gives each qualified event exactly one terminal reason, so: the first bar satisfying the cooling condition is *the* decision bar; `sl_dist_out_of_range`, `sizing_rejected_decision`, `sl_crossed_before_fill`, `sizing_rejected_fill`, `normalization` end the event → COOLDOWN. Pin it and add the retry-would-have-passed test (second cooled bar passes the band; assert no entry).
> 
> **4. MAJOR — `window_end` (line 36) has no place in the §7-3 order.** Line 36 names it as a reason; §7-3 lists six. Pin: the admissible bitmap excludes t0 with t0 + 366 min > IS_END, and those tail minutes are counted as a sub-count `window_end` under `not_admissible` (report-only sub-count, same device as `oi_missing{unusable|absent}`). Same for `r30_undefined`: a window minute whose r30 is undefined (first 30 bars after an incomplete day) cannot be a tail → counted under `no_tail` with a sub-count. The six anchored names stay the top level.
> 
> **5. MAJOR — several abort reasons are unreachable under #48 at E_ref 1,000; design the tests accordingly.** With MIN_NOTIONAL 50 and the band [0.44%, 5%], notional is 200–2,273 USDT; the smallest floored qty at any plausible price stays ≥ 50 USDT; pos_pct peaks at ~7.6% vs the 40% cap; L = 12 passes at 5.00% (your §1-1 row). So `sizing_rejected_decision`, `sizing_rejected_fill` and `normalization` should be 0 in the real run. Tests must force them with a test-only rules fixture (larger MIN_NOTIONAL / step) — not by changing E_ref or the band — and the report and conventions doc should state the expected zeros. `sl_crossed_before_fill` and every other reason are reachable with synthetic bars.
> 
> **6. Q1 — map by `RejectReason`, and pin the decision/fill asymmetry.** `engine.py:450` shows `SizingDecision.reason` is an `exchange.normalize.RejectReason`. Grep its members; the MIN_NOTIONAL/qty-floor members → `normalization`, all others → `sizing_rejected_fill`. At decision time every rejection is `sizing_rejected_decision` — §7-3 lists `normalization` only after the fill position. Harness invariant: `LEVERAGE_NOT_CONFIRMED`, `SEND_FAILED`, `ENTRIES_BLOCKED` counts are 0 (PAPER can't produce them).
> 
> **7. Pins the plan states loosely — write them exactly:**
> - Quantile trigger: on day change, i.e. when the first handled bar has `day_index` > the current quantile day; the 23:59 bar of d−1 has already been added to d−1's bucket. A day whose 90-day sample has < 128,304 defined values is `quantile_invalid` for all its bars.
> - Admissibility endpoints: day set = `day_index(T − 60,000)` for every close T in [t0 − 270 min, t0 + 366 min]; funding boundaries by bucket minute `b = funding_ms − funding_ms % 60,000`, required for `t0 ≤ b ≤ t0 + 366 min` inclusive (the upper end matters — a boundary at the exit bar's minute is paid before the time exit).
> - P3: `SL' = normalize_price(m ± 1.5·ATR)` — round the mirrored raw price, not mirror the rounded SL. P2: `decided_ms` = close of bar t_e + k (the engine fills on `open_ms > decided_ms`); the original t_e stays in the event log.
> - State machine starts IDLE at the first window bar; warm-up bars feed only feature state (r30 buffers, quantile buckets, rv, ATR buckets, OI index); no cooldown or cooling can originate in the warm-up, so a flush straddling the window start has t0 = its first window minute.
> - Numeric paths: r30 and rv5 in float64 from Decimal strings (`math.log`, `statistics`/numpy ddof 1); ATR, m, SL, sl_dist in Decimal under the process default context (`decimal.setcontext(decimal.Context())` at CLI start, as the trial #2 CLIs do); `size_entry` uses its own exec context. Comparisons `≤ q_dn` / `≥ q_up` / `rv5 ≤ 0.5·rv_peak` / band inclusive.
> - `load_rules` for trial #3 asserts the four #48 SHA256s from `anchor.RULES_SNAPSHOT_SHA256` and `taker == 0.0005` before anything runs (trial #2's `RulesSnapshotMismatch` pattern).
> 
> **8. Tests to add beyond the per-reason list:**
> - Sum checks: per arm, event-funnel counts sum to the number of window bars; per arm, entry-funnel terminals + fills = qualified events; exit reasons = fills. These catch double counting in the state machine.
> - Cooldown boundary both ways at close times: event at T = t0 + 43,200,000 qualifies; T = t0 + 43,140,000 is `in_cooldown`.
> - P2 at the edge: t_e = t0 + 120, k = 5 → emission at t0 + 125, fill at t0 + 126, no `not_cooled` fired after the decision.
> - `not_cooled` needs volatile synthetic bars: on flat bars rv5 = rv_peak = 0 and the cooling condition is trivially true at t0 + 20.
> - Static checks: no `strategies.trial01/02` imports anywhere under `strategies/trial03/`; no rolling price max/min channel (rv_peak allowed by name).
> - Determinism across processes, not just calls: run the same synthetic input in two `spawn` subprocesses and compare hashes (that is how the IS run will execute).
> 
> **9. Q2 — no contradiction found.** COOLDOWN relative to t0 is line 27 verbatim; tail minutes during a position falling under `in_cooldown` follows from the §7-3 order plus 720 > 366; arms overlapping in time is §0 as amended in r3. Q3 — per-tail-minute records plus counts for `quantile_invalid`/`no_tail` are sufficient; the sum checks in item 8 make the counts auditable.
> 
> **10. Q4 / the step boundary the user set.** Mirror trial #2: write `docs/trials/trial_03_conventions.md` as a numbered list; registry row #52 references its SHA256 and commit (as #37 did). At the (d) report, send the full draft text (items from (a)–(d) plus the pins already made for (e)/(f): P1 rate at placement and execution, tuple seeds, cost grid, X9, CI exact fractions, the OI decision with both readings quoted and the 130-slot S0 count). Say plainly that (e)–(g) may append items, that any addition will be shown to them as a diff before the row is written, and that the row lands before the evaluator push — no P&L until then.
> 
> **Sequence:** Codex lands → log both verbatim with positions → plan r2 with items 1–7 → narrow re-check → PROCEED → build test-first in this order: `config.py` → `features.py` (pure calculators, tested in isolation) → `strategy.py` → `harness.py` → variants → static checks → determinism → after-pass → push → conventions draft + report → stop before (e). Zero shared-code change is the expectation; check `git diff --stat dc23273 -- backtest/engine_replay.py backtest/placebo_exec.py paper/ sizing/ exchange/` before the after-pass as you did for (c).

### Codex 원문(verbatim · task-mumulo1j-r9o5b4)
> ## BEFORE-PASS findings
> 
> 1. **BLOCKER — Decision-time B2 uses the wrong price.** The plan calls `size_entry` with an adverse-fill estimate. Anchored r3 specifies the decision reference as the mark close **`m`**, with the fixed SL; the adverse estimate belongs to execution-time resizing. This can change which events become intents. Change the decision call to `size_entry(m, SL_rounded, original_direction, E_ref, …)`. Keep the engine’s quoted fill price for its second check. The earlier suggestion to quote `m` in the ops log also conflicts with r3 and must not override it. [r3 §1](</home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:29>), [engine execution](</home/cms/project/BTC_Futures_E2E/paper/engine.py:433>)
> 
> 2. **MAJOR — The window-close rule is off by one bar.** Counting `T_k ∈ [IS_START, IS_END]` includes the final warm-up bar, whose close is `IS_START`, and excludes the IS final 23:59 bar, whose close is `IS_END + 1 ms`. Day ownership in r3 uses `open_ms`. Define the funnel population by bars whose **`open_ms` is in the window**, then use `T_k = open_ms + 60,000` for signal comparisons. Do not turn the warm-up bar’s boundary close into an IS event. Apply the same convention to V and count reconciliation. [r3 day and window rules](</home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:22>), [funnel denominator](</home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:148>)
> 
> 3. **MAJOR — P2 needs millisecond timestamps, not “+1 open” prose.** With the plan’s clock, the bar after a decision at close `T_e` **opens at `T_e`**. P2 `+k` emits after the bar closing at `T_e + k·60,000` and fills at that same boundary, if the next bar exists. Pin those open times for base, +1 and +5 in the plan and tests. Preserve the original `decision_mark`, SL, decision B2 result and decision-time `sl_dist` through the delay; only execution B2 is repeated. [r3 P2](</home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:93>), [replay timing](</home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:130>)
> 
> 4. **MAJOR — “Warm-up bars update state” is too broad.** Warm-up must build price, quantile, rv and ATR history without creating qualified events, cooldowns, pending intents or positions. Start each window with an idle, flat strategy book. Otherwise a pre-IS tail can suppress a registered IS event. Make this a harness assertion and test the bar immediately before and after `IS_START`. [r3 flat-window rule](</home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:36>), [plan r5 S10](</home/cms/project/BTC_Futures_E2E/docs/ops_log.md:7012>)
> 
> 5. **MAJOR — Close the intent-to-outcome accounting.** `replay()` returns `open_at_end` but does not expose `engine.pending`; it also reports generic `entry_refused` separately. For every emitted intent, require exactly one `EntryFilled` or `EntrySkipped`, no delayed P2 candidate left, no due exit, and no unmatched outcome. Treat unexpected engine skip reasons and `POST_FILL_GATE` as run failures rather than funnel categories. This makes the proposed zero-refusal assertion meaningful and prevents an unfilled final intent from passing unnoticed. [replay result and callbacks](</home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:63>), [engine outcomes](</home/cms/project/BTC_Futures_E2E/paper/engine.py:449>)
> 
> 6. **MINOR — Specify transition order at the cooldown boundary.** Before classifying a tail at `T_k = cooldown_end`, move `COOLDOWN → IDLE`; the event is eligible at that exact close. Keep `position_busy` recording after starting the new event’s cooldown in the forced fixture. This matches the proposed +719/+720 tests and r3’s excluded end. [r3 cooldown](</home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:27>), [(c) busy helper](</home/cms/project/BTC_Futures_E2E/strategies/trial03/exit_schedule.py:57>)
> 
> ## Q1–Q4
> 
> **Q1.** The proposed split is correct: for `EntrySkipped(SIZING_REJECTED)`, classify `BELOW_MIN_QTY` and `MIN_NOTIONAL` as `normalization`; classify other `SizingDecision.reason` values as `sizing_rejected_fill`. Read the enum, not the detail string. This matches Trial #2’s harness. `SL_CROSSED_BEFORE_FILL` stays separate. [Trial #2 mapping](</home/cms/project/BTC_Futures_E2E/strategies/trial02/harness.py:29>), [reason enum](</home/cms/project/BTC_Futures_E2E/exchange/normalize.py:23>)
> 
> **Q2.** Cooldown relative to `t0`, including skipped entries, matches r3. A tail while a position is open is normally counted as `in_cooldown`: the 720-minute cooldown exceeds the maximum 366-minute event span. `position_busy` remains a recorded invariant failure in a forced fixture. The decision-price conflict in finding 1 *does* contradict r3.
> 
> **Q3.** Yes. One record per tail close, plus exact counts for `quantile_invalid` and `no_tail`, is sufficient if the mutually exclusive event counts sum to the full window-bar denominator and every qualified event has exactly one final entry outcome. Keep transition records separate from event-funnel counts so `qualified` is not counted twice. [r3 funnels](</home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:148>)
> 
> **Q4.** Before real-data P&L, the append-only implementer-choices row must pin the fixes above and the remaining r5 S12 contract: numeric and undefined-input handling; OI parsing, deduplication and missing sub-reasons; exact bitmap and V recomputation; P1 cross-day eligibility and streams; P2 queue and P3 original-direction gate; (c)’s exit-bar, funding, missing-bar and busy conventions; cost-grid and liquidation accounting; zero-trade and degenerate statistics; float64 overflow refusal; complete per-arm outputs, provenance, and evaluator reconciliation. Register choices that fill gaps, without changing anchored r3. [plan r5 S12](</home/cms/project/BTC_Futures_E2E/docs/ops_log.md:7019>), [(c) conventions](</home/cms/project/BTC_Futures_E2E/docs/ops_log.md:7673>)
> 
> Read-only review; no market data was read and no code or tests were run.
> 
> **VERDICT: FIX-PLAN-FIRST.**
> 
> Codex session ID: 01a0edd7-c749-7591-9c63-d5ea9f7902d5
> Resume in Codex: codex resume 01a0edd7-c749-7591-9c63-d5ea9f7902d5

### 계획 r2 원문
> # Trial #3 (d) plan r2 — resolutions (advisor 1–10 + Codex task-mumulo1j-r9o5b4 1–6, Q1–Q4)
> 
> D1 DECISION-TIME B2 PRICE (Codex 1 BLOCKER): r3 line 29 "결정 시점 B2 게이트(기준가 m · SL 가격 · E_ref로 정본 size_entry)" and line 30 "엔진이 실행
>    시점에 B2 재사이징(예상 체결가 · 같은 SL 가격 …)" → decision call = size_entry(m, SL_rounded, ORIGINAL direction, E_ref, REGIME, rules,
>    LIMITS) with m RAW; the 6 bps adverse quote applies only at the engine's fill-time re-sizing. This REVERSES the earlier carry-forward note
>    ((b) advisor item 8, repeated in the (b) report and adopted as user (d) req. 7 "decision mark priced with the same 6 bps model"), which
>    contradicts line 29 — flagged to the user in the (d) report; anchored text governs (as with convention 2).
> D2 WINDOW MEMBERSHIP (advisor 1, Codex 2): a bar belongs to the UTC day of its open_ms (line 22). Window bars = bars with open_ms in
>    [IS_START, IS_END]; event-funnel denominator = those bars; t0 = T_k = open_ms + 60,000 of a window bar; V by open-day; the first window
>    bar that can qualify opens 00:00 Jan 1 2024 (T = 00:01). Events also need t0 + 366 min ≤ IS_END + 1 ms (span end inside the window —
>    span end is a close time); tail minutes failing only that are counted under not_admissible with sub-count `window_end` (line 36).
> D3 WARM-UP (Codex 4, advisor 7): bars with open_ms < IS_START feed feature state only (r30 buffers, quantile day buckets, rv, ATR buckets,
>    OI index); the state machine starts IDLE and the book flat at the first window bar; no cooldown/cooling/intent can originate before it.
>    Harness asserts IDLE+flat at the first window bar; tests for the bar just before and just after IS_START.
> D4 P2 / base TIMING in ms (Codex 3, advisor 7): decision bar t_e has open o_e, close T_e = o_e + 60,000. Base: intent emitted at T_e
>    (decided_ms = replay now_ms of bar t_e), fills at the bar opening at T_e. P2 +k: intent emitted at the close of the bar with open
>    o_e + k·60,000, fills at the bar opening at T_e + k·60,000 (= "t_e + k + 1분 봉 시가" with minute labels = opens). decision_mark, SL,
>    decision-B2 result and decision-time sl_dist are frozen at t_e; only fill-time B2 repeats. Edge test: t_e = t0 + 120, k = 5.
> D5 ONE DECISION PER EVENT (advisor 3): the first bar with t_e − t0 ≥ 20 min ∧ rv5 ≤ 0.5·rv_peak is THE decision bar; band / decision-B2 /
>    sl_crossed / fill-B2 / normalization aborts are terminal (→ COOLDOWN, no retry). Test: a later cooled bar that would pass is not used.
> D6 OUTCOME ACCOUNTING (Codex 5, advisor 6/8): every emitted intent gets exactly one EntryFilled or EntrySkipped; EntrySkipped reasons:
>    SL_CROSSED_BEFORE_FILL → sl_crossed_before_fill; SIZING_REJECTED with SizingDecision.reason ∈ {BELOW_MIN_QTY, MIN_NOTIONAL} →
>    normalization, other reasons → sizing_rejected_fill (enum, not detail string — as trial #2's harness); LEVERAGE_NOT_CONFIRMED /
>    SEND_FAILED / ENTRIES_BLOCKED, ExitReason.POST_FILL_GATE, replay `entry_refused`, a P2 candidate still delayed at the end, a due exit
>    (assert_no_due) or open_at_end ≠ None → run failure. Sum checks per arm: event-funnel counts = window bars; entry-funnel terminals +
>    fills = qualified; exit reasons = fills.
> D7 DECISION RECORDS (advisor 2): no shared trade-dict fields. The strategy's `intent` record carries t0, t_e, T_e, decided_ms, variant, m,
>    ATR_15m, SL_raw, SL_rounded, sl_dist (decision, unrounded 1.5·ATR/m), decision-B2 leverage/qty/notional; the harness writes per-arm
>    trades_t3.jsonl joining replay trades to intents in order (one open intent at a time — asserted). P1 (e) reads sl_dist from there.
> D8 BOUNDARY ORDER (Codex 6): at each close, COOLDOWN → IDLE happens first when T_k ≥ cooldown_end, then the tail is classified; event at
>    T = t0 + 43,200,000 qualifies, T = t0 + 43,140,000 is in_cooldown. Busy fixture: cooldown set before position_busy recording/raise.
> D9 PINS (advisor 7): quantile recomputed when the first bar of a new day_index is handled (previous day's 23:59 already bucketed);
>    admissibility day set = day_index(T − 60,000) for every close T in [t0 − 270 min, t0 + 366 min]; funding boundary bucket b = funding_ms −
>    funding_ms % 60,000 required for t0 ≤ b ≤ t0 + 366 min inclusive, exactly one validated record each; P3 SL' = normalize_price(m ± 1.5·ATR)
>    (round the mirrored raw price); numeric paths: r30/rv5 float64 from Decimal strings (math.log; ddof 1), ATR/m/SL/sl_dist Decimal under the
>    default context set at CLI start (decimal.setcontext(decimal.Context())); comparisons inclusive (≤ q_dn, ≥ q_up, rv5 ≤ 0.5·rv_peak, band);
>    trial-#3 load_rules asserts the four #48 SHA256s and taker == 0.0005 before anything runs.
> D10 SUB-COUNTS (advisor 4): top-level §7-3 names unchanged; report-only sub-counts: not_admissible{window_end|incomplete|funding},
>    no_tail{r30_undefined}, oi_missing{absent|unusable}, sl_dist_out_of_range{floor|ceiling}.
> D11 EXPECTED ZEROS (advisor 5): under #48 at E_ref 1,000 and the band, sizing_rejected_decision, sizing_rejected_fill and normalization
>    are expected 0 (notional 200–2,273 USDT ≥ MIN_NOTIONAL 50; pos_pct ≤ ~7.6% < 40%; L = 12 passes at 5%); tests force them with a
>    test-only rules fixture (larger MIN_NOTIONAL/step), never by changing E_ref or the band; stated in the conventions doc.
> D12 TESTS added (advisor 8): sum checks; cooldown boundary both ways; P2 edge; not_cooled on volatile synthetic bars (flat bars are
>    trivially cooled); static checks (no trial01/02 imports under strategies/trial03; no rolling price channel; rv_peak allowed);
>    determinism across two spawn subprocesses (hash compare).
> D13 CONVENTIONS (advisor 10, Codex Q4): docs/trials/trial_03_conventions.md (numbered, like trial #2's) covering (a)–(d) plus pins already
>    made for (e)/(f) (P1 rate at placement+execution, tuple seeds, cost grid, X9, CI fractions, OI decision with both readings quoted and the
>    130-slot S0 count, zero-trade/degenerate stats, overflow refusal, outputs/provenance). Full draft text sent to the user at the (d) report;
>    (e)–(g) additions shown as diffs; registry row lands before the evaluator push; no P&L before.
> Build order: config.py → features.py (pure, isolated tests) → strategy.py → harness.py → variants → static checks → determinism.
> Shared-code check before the after-pass: git diff --stat dc23273 -- backtest/engine_replay.py backtest/placebo_exec.py paper/ sizing/ exchange/.

### Codex 원문(verbatim · task-mumutx8d-6eco72)
> **VERDICT: FIX-PLAN-FIRST**
> 
> | Prior finding | Status | Re-check |
> |---|---|---|
> | 1 — decision B2 price | **CLOSED** | D1 uses raw decision mark `m` for `size_entry`; the 6 bps quote belongs to fill-time resizing. This matches [r3 §1 lines 29–30](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:29). |
> | 2 — window membership | **PARTIAL** | Open-time day membership is correct, but D2’s `span_end ≤ IS_END + 1 ms` admits an endpoint at 00:00 *after* the window. [r3 §1 line 36](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:36) requires the span end to be **within** the window. Use `span_end ≤ IS_END_MS` with the anchored end timestamp of 23:59:59.999. |
> | 3 — P2 timing | **PARTIAL** | The delayed fill bar is correct. The stated `decided_ms` equality is off by 1 ms: replay sets `ctx.now_ms = open_ms + 60,000 − 1`, then requests the intent; the next bar opens at `open_ms + 60,000` ([replay lines 130–136](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:130)). State that exact value in D4. |
> | 4 — warm-up | **CLOSED** | D3 keeps pre-window bars in feature state while starting the trading state IDLE and flat. |
> | 5 — outcome accounting | **CLOSED** | D6 accounts for emitted intents, distinguishes skip reasons by enum, and fails the run on unaccounted execution paths. |
> | 6 — boundary order | **CLOSED** | D8 specifies the cooldown transition before classification and covers both sides of the boundary. |
> 
> The D2 boundary is verdict relevant: an event at **2025-12-31 17:54 UTC** has `t0 + 366 min = 2026-01-01 00:00 UTC`. R2 admits it; r3 excludes it. D9 would also demand a funding record at that out-of-window midnight. Correct the inequality and add this exact edge fixture. The D4 correction is a timestamp wording fix; its specified replay sequence already fills on the intended bar.
> 
> The read-only shared-code diff from `dc23273` is empty. No harness or tests were run.
> 
> Codex session ID: 01a0eddd-a6f4-7b90-94f4-d9ae505689c2
> Resume in Codex: codex resume 01a0eddd-a6f4-7b90-94f4-d9ae505689c2

### 계획 r3 원문
> # Trial #3 (d) plan r3 = r2 with D2/D4/D9 corrected (Codex task-mumutx8d-6eco72)
> D2' Window end: an event needs t0 ≥ IS_START and span end t0 + 366 min ≤ IS_END_MS (2025-12-31 23:59:59.999Z) — r3 line 36 "구간 끝 ≤ 창 끝".
>     Edge: t0 = 2025-12-31 17:54Z → t0 + 366 min = 2026-01-01 00:00Z > IS_END → not_admissible{window_end}; t0 = 17:53Z admissible (fixture).
> D9' Span semantics = closed interval of TIME POINTS [t0 − 270 min, t0 + 366 min] (line 35): day set = day_index(t0 − 270 min) …
>     day_index(t0 + 366 min) inclusive (a span ending exactly at 00:00 of d+1 touches d+1 — conservative, literal); funding boundaries
>     required for every boundary b (00/08/16) with t0 ≤ b ≤ t0 + 366 min, exactly one validated record whose bucket minute
>     (funding_ms − funding_ms % 60,000) = b. Supersedes r2 D9's "day_index(T − 60,000) for every close" wording.
> D4' decided_ms (replay's now_ms) = open_ms + 60,000 − 1 of the emitting bar: base emits in bar t_e (decided_ms = o_e + 59,999, fill at the
>     bar opening o_e + 60,000); P2 +k emits in the bar with open o_e + k·60,000 (decided_ms = o_e + k·60,000 + 59,999, fill at the bar opening
>     o_e + (k+1)·60,000).
> Everything else as r2.

### Codex 원문(verbatim · task-mumuy2hq-8vadui)
> D2′ matches the window rule in [§1, line 36](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:36); the 17:53Z and 17:54Z edge cases are correct. D9′ follows the closed time-point span and funding boundaries in [line 35](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:35). D4′ matches the replay loop: it sets `now_ms` to the emitting bar’s `open_ms + 59,999` before calling the strategy, and processes a pending entry on the next bar ([engine_replay.py](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:130), [lines 5–7](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:5)).
> 
> VERDICT: PROCEED
> 
> Codex session ID: 01a0ede0-9a3b-7791-a5b8-415e65a1ab19
> Resume in Codex: codex resume 01a0ede0-9a3b-7791-a5b8-415e65a1ab19

## 2026-09-30 — 트라이얼 #3 (d) **after-pass**(advisor + Codex task-mumvi9y5-teeetv **FIX-FIRST**) → 수정
- 코드 497fc34 · 공유 코드 변경 없음(dc23273 대비 빈 diff) → 트라이얼 #2 재실행 불필요.
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 끝에서 끝 테스트 자기참조 | ✅ | tests/fixtures/golden_trial03_e2e.json(암마다 다이제스트·트레이드·의도·깔때기) · 교차 프로세스 결정론도 커밋된 다이제스트와 비교 |
| advisor | 2 기록 일관성 | ✅ | ENTRY_PENDING 시각 = 의도를 낸 봉 마감 · busy 기록에 kind·arm · 체결 봉 open 단언(fill_open) |
| advisor | 3 규약 추가 | ✅ | 규약 초안에(TF_V1 불변 테스트 · Decimal 문맥 · Admissibility 순서 · b = t0 펀딩 · 실패 시 기록 보존은 (g) 미결) |
| advisor | 4 보고 틀 | ✅ | 보고에 |
| advisor | 5 규약 초안 | ✅ | docs/trials/trial_03_conventions.md(초안) · 행 문안(추가 안 함) |
| advisor | 6 순서 | ✅ | — |
| Codex | 1 실행 경계에서 입력·규칙 고정 미강제(MAJOR) | ✅ | validate_inputs(중복·비정렬 분 · 펀딩 버킷 중복·격자 밖·비유한) · complete_days 중복 분 → 불완전 · run_arm(rules=None) → load_rules()(#48 단언) · rules 인자는 테스트 픽스처 전용 · 테스트 |
| Codex | 2 P2 상태 시각 역행 | ✅ | advisor 2와 같음 · P2 테스트가 상태 시각 오름차순 단언 |
| Codex | 3 창 끝 테스트 절반 | ✅ | 2025-12-31 완전한 날을 주고 17:53 None · 17:54 window_end |
- 검사: 전체 스위트 통과(아래 커밋) · ruff · pyright 0.

### 요약 원문
> # Trial #3 (d) AFTER-PASS — built vs plan r3
> Commit 497fc34 (pushed): strategies/trial03/{config,features,strategy,harness}.py; tests/test_trial03_features.py (12),
> tests/test_trial03_strategy.py (61), tests/fixtures/t3_scenario.py. Shared code: `git diff --stat dc23273 -- backtest/engine_replay.py
> backtest/placebo_exec.py paper/ sizing/ exchange/` empty → no trial #2 rerun. Suite 1327 passed; ruff; pyright 0.
> Design as plan r2/r3: per-arm Trial03 (IDLE/COOLING/DELAYED/ENTRY_PENDING/IN_POSITION/COOLDOWN; FLUSH_QUALIFIED is the instant
> 'qualified' tail record), on_minute_closed order: sched.observe → engine events → features (warm-up too) → [window only] COOLDOWN→IDLE
> if T ≥ cooldown_end → advance (cooling/decision/P2 emission) → classify (event funnel). Decision B2 = size_entry(m raw, SL normalized,
> original dir, E_ref) (r3 line 29; user req. 7's 6 bps decision quote NOT used — flagged). P3 intent SL = normalize_price(mirrored raw).
> Harness: Admissibility (closed time-point span, window_end → incomplete → funding), run_arm (replay 6 bps, sizing_capital E_ref,
> finish(), invariants, sum checks, trades_t3 join), load_rules (#48 SHAs + taker), v_days.
> Tests: e2e per arm with hand-checked ledger (decision/fill sizing, fills, exit ref, net); quantile_invalid; r30_undefined + incomplete;
> funding; window_end; cooldown 719/720; oi_missing absent/unusable (no cooldown); oi_not_decreasing then qualified; not_cooled at +121;
> decision exactly at +120 and one bar later not_cooled; sl_dist floor/ceiling; no retry after abort; sizing_rejected decision (rules fixture
> MIN_NOTIONAL 1e6); sl_crossed_before_fill; sizing_rejected_fill (fill open far → liq gate); normalization (MIN_NOTIONAL 1000 + favourable
> gap); exits sl/liquidation with full state sequence and IDLE at t0+720; position_busy (cooldown 25 min) records after cooldown start
> then raises; P2 +1/+5 timing and frozen decision; P2 edge (+120, k=5); P3; warm-up flush → nothing; flush straddling window start;
> admissibility real 17:53/17:54 edge, midnight day-set, 16:00 funding upper end; V days; load_rules; determinism in-process and in two
> subprocesses; static checks.
> Known test-scenario notes: the +120 cooling boundary uses arm-specific flush phase (S flush one bar later) because of alternating-noise
> parity. Questions: objections; gaps between plan r3 and code; anything for the conventions row.

### advisor 원문(verbatim)
> This is the advisor half of the (d) after-pass. The code matches plan r3 and the anchored lines it cites; the funnels are exhaustive and exclusive by construction and the harness sum checks enforce it; shared code is untouched (diff against `dc23273` empty). No blocker. Items your checks didn't cover, then the report shape the user asked for.
> 
> **1. MAJOR — the end-to-end "known ledger" test is partly tautological.** Its expected qty/leverage come from `size_entry(quote, …)` and expected fills from `adverse_fill_estimate(…)` — the same functions the engine calls. That proves wiring, not values; a future regression inside `size_entry` or the engine would pass it. Freeze a golden: write `tests/fixtures/golden_trial03_e2e.json` holding, per arm, the scenario digest (`S.digest`) plus the literal trade fields (entry_ms, exit_ms, entry_fill, qty, leverage, sl, exit_ref, net_bps) and the intent record. Test = equality with the file. That's the same device as trial #1/#2's `golden_*.json`, and it also makes the cross-process determinism test compare against a committed value rather than against itself.
> 
> **2. MINOR — three log/consistency fixes, all trial-3-only:**
> - `_emit` records `_to("ENTRY_PENDING", ev["t_e"])`; for P2 the transition actually happens at the emission bar. Use the emission bar's close (`ctx.now_ms + 1`) so the state log is chronological.
> - `busy_check` appends `{"ts_ms", "reason"}` — the only record without `kind`. Give it `"kind": "busy"` (and `arm`) so the JSONL is uniform for (g)/(f). It lives in `exit_schedule.py`; that's fine to touch — it's code under review, not an anchored artifact.
> - On `EntryFilled`, assert `bar.open_ms == expected fill open` (`o_e + (k+1)·60,000`, stored on `ev` at decision). Admissibility makes a mismatch impossible; the assert turns "impossible" into "checked," which is the trial's whole discipline.
> 
> **3. Conventions that only became visible from the code — add to the draft:**
> - Real runs use `TF_V1` unchanged; `TfParams` overrides exist for tests only. Add `assert TF_V1 == TfParams()` as a test and state that the (g) CLI accepts no params override.
> - Decimal context: strategy arithmetic (ATR, m, SL_raw, sl_dist) runs under the process default context; the (g) CLI must call `decimal.setcontext(decimal.Context())` first (trial #2 pattern). `size_entry` uses its own exec context. The intent record strings depend on this.
> - `Admissibility` first-failure order: `window_end → incomplete → funding` (your docstring has it; pin it).
> - Funding at exactly `b = t0` is required (literal `[t0, t0+366]`), even though no position can exist at t0 — conservative, say so.
> - On any run failure (`PositionBusyError`, `MissingExitBar`, `RunInvariantError`) the strategy's in-memory event log is lost because `replay()` doesn't return; (g) must catch, persist, re-raise. Already deferred — record it as an open item, not silently.
> 
> **4. Report shape — the user will read for these, in this order:**
> - **Requirement 7 conflict, quoted.** Line 29 "결정 시점 B2 게이트(기준가 m · SL 가격 · E_ref로 정본 size_entry)" and line 30 "엔진이 실행 시점에 B2 재사이징(예상 체결가 …)". Say plainly the 6 bps decision quote was my (b) suggestion carried into your report and then into their req 7, and that the anchored text governs — same resolution as convention 2. Effect: none on fills (fill-time quote unchanged); decision gate slightly less strict than the withdrawn wording.
> - **Name mappings.** User req 1 aliases → §7-3 names (`cooling_timeout`→`not_cooled`, `sizing_gate_fail`→`sizing_rejected_{decision|fill}`, `quantile_invalid_day`→`quantile_invalid`). User states → code states: FLUSH_QUALIFIED is the instantaneous `qualified` tail record; `DELAYED` (P2) and `ENTRY_PENDING` are added between COOLING and IN_POSITION.
> - **Expected zeros** (D11): `sizing_rejected_decision`, `sizing_rejected_fill`, `normalization` are structurally ~0 under #48 at E_ref 1,000; tests force them with rules fixtures. Say it so a zero in the real run isn't read as "untested."
> - **Cooldown test result**: +719 `in_cooldown`, +720 `qualified`, quoting line 27 "끝 제외".
> - The +120 boundary test's arm-specific flush phase is a synthetic-noise artifact; one sentence, so the reviewer doesn't wonder.
> 
> **5. The conventions deliverable.** Write `docs/trials/trial_03_conventions.md` with status **DRAFT** in its header, numbered items 1–N covering (a)–(d) plus the (e)/(f) pins already made (P1 rate at placement and execution, tuple seeds, decision-time `sl_dist` from `trades_t3`, cost grid, X9, CI fractions, the OI decision with both readings quoted and the S0 130-slot count, degenerate stats/overflow refusal). Commit it as a draft; draft the registry row text (mirroring #37: file SHA256 + commit, "이 행 뒤 파일 불변") but **do not append it** — the user said they review the full text as a step boundary. State explicitly: (e)–(g) will add items shown to them as diffs; the row lands with the final SHA before the evaluator push; no real-data P&L before that.
> 
> **6. Sequence:** Codex lands → log both verbatim with positions → items 1–2 (tests re-run: 1327 → +N) → commit → push → conventions draft + row text → memory (`(d) done, waiting on user: req-7 conflict acknowledgement + conventions review before (e)`) → report → stop. If Codex objects only to log-shape items, fold them into the same commit; if it finds a funnel gap, that's a FIX-FIRST loop before the report.

### Codex 원문(verbatim · task-mumvi9y5-teeetv)
> 1. **MAJOR — the harness does not enforce its input pins.** [run_arm](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:106) accepts arbitrary rules without calling `load_rules`; [complete_days](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:64) can treat a day with a duplicate minute as complete; and [Admissibility](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:80) counts a funding row without validating its rate or mark. The preparation path normally checks these inputs, but the callable harness does not guarantee plan r3’s “validated” inputs or pinned rules. **Fix:** enforce those checks at the production run boundary, with an explicit fixture-only rules path, and test duplicate minutes and malformed funding.
> 
> 2. **MAJOR — P2 records the wrong state-transition time.** A delayed intent is emitted at the later bar close, but [_emit](/home/cms/project/BTC_Futures_E2E/strategies/trial03/strategy.py:238) records `ENTRY_PENDING` at the original `t_e`. Its state history therefore moves backward in time. **Fix:** stamp that transition with the emitting bar’s close (`ctx.now_ms + 1`), and assert the state timestamp in the P2 timing tests.
> 
> 3. **MINOR — the stated window-edge test proves only half its claim.** [test_admissibility_real_window_end_edge](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_strategy.py:311) supplies no bars or funding, so 17:53 returns `incomplete`; it never proves that 17:53 is admissible. **Fix:** supply complete touched days and required funding, then assert `None` at 17:53 and `window_end` at 17:54.
> 
> The current event and entry control paths are mutually exclusive and their count checks reconcile. The 73 targeted tests passed in read-only mode. The diff from `dc23273` shows no shared-code changes. The conventions row should explicitly retain the raw-`m` decision B2 choice and the corrected P2 state timestamp.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0edee-fcfa-7dd3-a8d3-383283615e46
> Resume in Codex: codex resume 01a0edee-fcfa-7dd3-a8d3-383283615e46

## 2026-09-30 — 트라이얼 #3 (d) after-pass 수정 확인(Codex task-mumvte6e-2vretb FIX-FIRST → task-mumw0cth-coglo7 FIX-FIRST → task-mumw6pdc-0bcqix **MERGE**) · 구현 규약 초안
- 1(실행 경계 규칙 고정): run_arm 인자에서 rules·p·admissible 제거(항상 load_rules() + TF_V1) → 픽스처 경로 run_arm_with_fixture_rules는 호출자 파일이 tests/ 아래가 아니면 거부(실행 시점) + 저장소 전체 정적 검사(호출·import·속성). 입장: ✅ 동의(docstring 규약은 강제가 아니다).
- 2(P2 상태 시각)·3(창 끝 테스트): CLOSED.
- 구현 규약 초안 `docs/trials/trial_03_conventions.md`(DRAFT · 번호 1~44) 커밋 — 레지스트리 행은 **아직 추가하지 않는다**(사용자 검토 · (e)~(g) 추가는 차이로 보인 뒤 최종 SHA로 판정기 푸시 전에).

### Codex 원문(verbatim · codex_t3_d_after_r2_result.md)
> **TRIAL #3 STEP (d) after-pass review of `HEAD`:**
> 
> 1. **Input and rules pins — OPEN.** [run_arm](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:133) now validates bar order, funding buckets, rates, and marks, and its default path loads the pinned snapshot. But a caller can still pass arbitrary `rules` and bypass `load_rules()` at line 139. The “fixture only” restriction is a docstring convention, not an enforced run boundary. The new test checks the default and source text; it does not test rejection of an unpinned override. The input-validation portion is closed.
> 
> 2. **P2 `ENTRY_PENDING` timestamp — CLOSED.** [The transition](/home/cms/project/BTC_Futures_E2E/strategies/trial03/strategy.py:247) uses the emission bar’s close, and [the P2 test](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_strategy.py:284) checks the timestamp and state order.
> 
> 3. **Window-end test — CLOSED.** [The revised test](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_strategy.py:335) supplies a complete touched day and proves both 17:53 admissible and 17:54 `window_end`. No funding boundary falls in the 17:53 interval.
> 
> The added [golden fixture](/home/cms/project/BTC_Futures_E2E/tests/fixtures/golden_trial03_e2e.json) is compared with both arms’ trades, intents, funnels, and digests. The 11 focused tests passed in read-only mode.
> 
> **VERDICT: FIX-FIRST.** Enforce the fixture-only rules override at the callable run boundary, or make the production entrypoint reject it and test that rejection.
> 
> Codex session ID: 01a0edf6-e737-7010-8dc0-3d0425df4814
> Resume in Codex: codex resume 01a0edf6-e737-7010-8dc0-3d0425df4814

### Codex 원문(verbatim · codex_t3_d_after_r3_result.md)
> **Finding 1: OPEN.** `run_arm` now pins `load_rules()` and `TF_V1`, and the three focused tests pass. But [the fixture helper](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:139) remains publicly callable. [The AST test](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_strategy.py:378) checks direct calls in only four directories, so it does not enforce the stated rule against calls anywhere outside `tests/`.
> 
> VERDICT: FIX-FIRST.
> 
> Codex session ID: 01a0edfb-dc1a-7d43-88e1-5d0a610b18f2
> Resume in Codex: codex resume 01a0edfb-dc1a-7d43-88e1-5d0a610b18f2

### Codex 원문(verbatim · codex_t3_d_after_r4_result.md)
> **CLOSED.** The guard in [harness.py](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:140) raised `RulesSnapshotMismatch` in a read-only probe called from outside `tests/`. The static test in [test_trial03_strategy.py](/home/cms/project/BTC_Futures_E2E/tests/test_trial03_strategy.py:378) now scans the repository root for calls, from-imports, and attribute references. An independent scan found no matches across the 119 eligible Python files.
> 
> The test also excludes `harness.py` itself and `node_modules`; the latter is absent. Those exclusions do not leave a current production caller unscanned.
> 
> VERDICT: MERGE
> 
> Codex session ID: 01a0ee00-613d-7f12-a40d-c4f4be77a8df
> Resume in Codex: codex resume 01a0ee00-613d-7f12-a40d-c4f4be77a8df

## 2026-09-30 — 트라이얼 #3 구현 규약 초안 사용자 검토: 요구 7 철회 확인 · 청산 거리 (A) · 초안 수정 3건
- 요구 7: 확인 — 결정 시점 B2 = 기준가 m 그대로(§1 29~30행) · 6 bps는 체결 시점 재사이징만 · 항목 26 그대로.
- 항목 38 점검에서 발견: `liq_fee_on_liq_price`는 거리에 들어가지 않는다(sizing/position.py:265 청산 손실만) — 그러나 거리식에 **진입 taker 항**이 있다(sizing/position.py:124). 멈추고 보고 → 사용자 **(A)**: 레지스트리 #4(2026-09-15 확정 · 결과 본 뒤 변경 금지)가 정본 — `(1/L − taker − MMR_eff)/(1 ∓ MMR)` · liquidationFee는 거리에 없음(#2). r3 §1-1 예시 2.895%·7.915%가 #4 식 값과 일치. 헌법 SKILL.md 77행 "수수료 항 없음" 식은 #4와 어긋남 → 사용자가 헌법 v1.4에서 정정(저장소 사본 무수정 · 보고서의 헌법 정정 목록에 추가).
- 적용: 항목 38 문구 + #4 닫힌 식 테스트(L 30·10 · 롱·숏 · #48 1구간 MMR 0.004 · cum 0 · taker 0.0005: 2.8949/2.8718/9.5884/9.5120% · 엔진과 같은 34자리 문맥에서 정확히 같음) · 항목 34 pos_pct ∈ [~7.6%, ~16.7%] < 40% · 항목 1·15와 코드 이름: `DATA_START_MS`(2023-10-02 · 준비 경로·워밍업) · `WINDOW_START_MS`(2024-01-01 · 판정 가능한 첫 봉) · 옛 이름 `WARMUP_START_MS`·`IS_START_MS`(트라이얼 #3 앵커) 제거 테스트 · 동작 변경 없음(골든·전체 1338 통과).
- 미결(g 범위): 실행 중 실패 시 이벤트 기록 보존 — (g) 계획에 올린다.

## 2026-09-30 — 트라이얼 #3 (e) P1 **before-pass**(advisor + Codex task-mun6jc9z-43lve4 FIX-PLAN-FIRST → r2 task-mun6obzc-d2txmf **PROCEED**)
| 출처 | # | 입장 | 반영(계획 r2) |
|---|---|---|---|
| advisor | 1 체결 분 펀딩(오프셋 기록은 P1에서 정산됨) | ✅ | R1 — 공시가 아니라 r3 §1 펀딩 행대로 실행에서 제외(Codex 1과 같음) |
| advisor | 2 실행/픽스처 분리 | ✅ | R3 |
| advisor | 3 창 끝 | ✅ | R5 |
| advisor | 4 Q2·공시 | ✅ | R7 |
| advisor | 5 규약 45~50 | ✅ | R9(차이로 보고) |
| advisor | 6 테스트 | ✅ | R8 |
| advisor | 7 순서 | ✅ | — |
| Codex | 1 체결 분 펀딩 부과(BLOCKER) | ✅ | R1(호출자 쪽 필터 · 공유 무변경) |
| Codex | 2 run_time_exit가 reason 인자를 덮어씀 | ✅ | R2 공유 모듈 수정 + 트라이얼 #2 전체 회귀 재실행 |
| Codex | 3 병합 불변식 | ✅ | R6 |
| Codex | 4 입력 검사 순서 | ✅ | R4 |
| Codex r2 | 새 간극: 중복 분 테스트 위치 | ✅ | 적격 도우미에서 '불완전 날 제외' · 실행 경로에서 중복 입력 거부 — 따로 테스트 |

### 계획 r1 원문
> # Trial #3 step (e) — P1 random-timing placebo with cross-day eligibility: BEFORE-PASS plan (no code yet)
> 
> Spec: r3 §4 P1 row (line 92) verbatim: "(a) 진입 격자 = 창 안 1분 시작 시각 t · 진입가 = 분 t mark 시가 · (b) h = 원 트레이드의 체결→청산 지속시간을 분
> 단위로 올림(최소 1) · 점유 [t, t+h) · 청산 = 분 t+h−1 mark 종가 · 적격 분 = [t, t+h−1]이 창 안의 완전한 mark 날들에 있고 그 안의 모든 00/08/16 펀딩
> 경계에 검증된 확정 펀딩이 있는 t(보유가 자정을 넘을 수 있다 · 오름차순) · 적격 분 없음 → 난수 없이 그 추출 실패 · (c) 슬롯을 먼저 전부: n = 원판 암 IS
> 트레이드 수 · 원판을 진입 시각 오름차순(동률 id) · 슬롯 k마다 pair_k = integers(0, n) → dir_k = integers(0, 2)(0 LONG · 1 SHORT) · (sl_dist, h) 쌍 ·
> (d) 배치 = h 내림차순(동률 슬롯) · 슬롯마다 최대 1,000회 균등추출 → 겹침 없음 ∧ B2 사이징(E_ref 1,000 · L ∈ [10, 30]) 수락이면 배치 · 실패 → 추출 전체
> 실패 · 쌍 재추출 없음 · (e) RNG = L: SeedSequence((20260929, 2)).spawn(1000)[d] · S: SeedSequence((20260929, 3)).spawn(1000)[d] · 호출 순서 = 슬롯(쌍 →
> 방향) → 배치 · (f) 실패 추출 교체 없음 · 실패 > 10 → 폐기 · 비용 = §2(22 bps + 실펀딩) · 시간 청산(SL·TP 없음) · 청산은 엔진 판정(보고) · 원판 0건 → 계산 불가".
> Pinned already (conventions draft 39): 6 bps at placement AND execution; source (sl_dist, h) pairs from the base run's trades_t3 with the
> DECISION-time sl_dist (t3.sl_dist); tuple seeds passed unchanged to p1_core (no p1_core edit; identity test); per-arm streams.
> 
> ## Plan
> New backtest/p1_t3.py (imports p1_core, placebo_exec; no trial01/02 imports; no edits to p1_core/p1_t2/placebo_exec):
> E1 CONFIG per arm: P1Config(master_seed=A.P1_SEEDS[arm] (tuple, one typed cast), draws 1000, slot_attempts 1000, fail_limit 10).
> E2 SOURCE: SourceTrade(trade_id, entry_ms (fill bar open), exit_ms (engine exit ts: time_exit = exit bar open → h = 240; SL/liquidation =
>    bar close_ms → ceil gives k+1), sl_dist = Decimal(t3.sl_dist)); p1_core.SourceTrade.h = max(1, ceil((exit−entry)/60,000)) unchanged.
>    Zero source trades → not computable (write marker; no draws).
> E3 ELIGIBILITY (cross-day, lazy, no per-h materialization): "bad minutes" over the window minute grid [WINDOW_START, IS_END] open-minutes:
>    every minute of an incomplete day (harness.complete_days) and every 00/08/16 boundary minute b without exactly one validated funding
>    record (bucket = funding_ms − funding_ms % 60,000). Clean segments = maximal runs of window minutes without a bad minute. For h:
>    eligible t = every minute t with [t, t+h−1] inside one clean segment (so inside the window, inside complete days, and every boundary in
>    [t, t+h−1] — CLOSED, t itself included (literal, conservative; the engine does not settle a boundary at exactly t) — validated).
>    CrossDayEligible(segments, h): __len__ = Σ max(0, len_seg − h + 1); __getitem__(j) via bisect on cumulative counts; ascending ms.
>    Holds may cross midnight (segments span days).
> E4 SIZING_OK(t, dir, sl_dist): PX.sizing_decision(bars[t].mark_open, dir, sl_dist, rules(#48 via load_rules), LIMITS, E_ref 1,000,
>    REGIME, slippage_rate=0.0006).ok.
> E5 EXECUTION (null point): PX.run_time_exit(bars, fundings, entry_ms=t, h, direction, sl_dist, rules, LIMITS, E_ref, REGIME,
>    reason=ExitReason.TIME_EXIT, slippage_rate=0.0006) per placed slot; mean net_bps (Decimal string) per successful draw + exit-reason
>    counts (time_exit / liquidation); a placement-accepted sizing refused at execution → AssertionError (run failure).
> E6 RUN/MERGE (library functions; CLI + provenance in (g)): run_range(arm, source, bars, fundings, lo, hi) → (draws canonical JSON,
>    null rows); merge(parts) requires draws 0..999 exactly once; evaluable = failures ≤ 10.
> Tests (synthetic, both arms): CrossDayEligible matches a brute-force eligibility list (incl. midnight-crossing holds, an incomplete day,
> a missing 16:00 funding, window edges, b = t boundary); tuple-seed stream identity (first 16 integers for d ∈ {0,1,999}) and L ≠ S; p1_core
> draw path end-to-end on a synthetic source with golden placement; 6 bps at placement (sizing quote) and execution (exit fill) — integration
> test; zero-source → not computable; failure > 10 → not evaluable; merge coverage; determinism (canonical JSON hash, two processes).
> Questions: Q1 is the closed-interval boundary rule (b = t included) right for P1, given the engine does not settle a boundary at t?
> Q2 anything in E2's h definition (exit_ms = close_ms − ... for SL exits) that deviates from trial #1/#2 conventions? Q3 anything to add
> to the conventions draft (I will show the additions as a diff)?

### advisor 원문(verbatim)
> This is the advisor half of the (e) before-pass. The plan follows r3 §4 P1 (a)–(f) as quoted, reuses `p1_core`/`placebo_exec` without edits, and the segment-based eligibility is the right structure. Findings, blocking first.
> 
> **1. BLOCKER — Q1's premise is only half true; fix the wording before it becomes a convention.** The plan says "the engine does not settle a boundary at exactly t." That holds for a record whose `funding_ms` is exactly the bucket minute. But `run_time_exit` settles `entry_ms < f.funding_ms ≤ exit_ms` (placebo_exec.py:80) and the position is restored *before* the minute loop — so a bucket-`t` record with any ms offset (e.g. `t + 15`) **is** settled in P1. The strategy path never pays at the fill minute (replay settles only when `eng.position is not None`, and the entry is still pending). Two consequences: (i) the closed interval `[t, t+h−1]` with `b = t` included is *required* for P1, not merely conservative; (ii) P1 and the base run can differ at the fill-minute boundary when the record has an offset — inherited from trial #1/#2 (same code), not new, but it must be pinned as a disclosed P1 convention, not left implicit. Whether real records carry offsets you cannot know until capture; prepare's bucket rule `[b, b+60,000)` exists because they can. Pin the rule by code semantics now; note "offset count reported at capture."
> 
> **2. MAJOR — production/fixture split, same as `run_arm`.** Codex made you enforce it for (d); it will ask again. `p1_t3` run functions must load rules via the pinned loader with no `rules` argument; the fixture path is a separately named function with the same `tests/`-only runtime guard, and the repo-wide static scan is extended to its name. Also call `validate_inputs` at the P1 run boundary and reuse `harness.complete_days` (its duplicate-minute semantics just changed) so P1 eligibility and admissibility cannot disagree on what a complete day is.
> 
> **3. MAJOR — pin the exact window edge for `[t, t+h−1]`.** "Inside the window" means `t ≥ WINDOW_START_MS` and `t + (h−1)·60,000 ≤ IS_END_MS − 59,999` (last window open-minute). With the rename just done, use `WINDOW_START_MS`, not `DATA_START_MS`. Test both ends: `t = last open − (h−1)` eligible, one minute later not.
> 
> **4. Q2 — no deviation.** `SourceTrade.h` is `p1_core`'s unchanged property; time_exit and open-gap liquidation carry `ts_ms` = exit-bar open (h = 240), intrabar SL/liquidation carry `close_ms` (h = k+1). Trial #2 went through the identical path. Two things to *disclose*, not change: the placebo exits at `mark_close(t+h−1)` while the base exits at `mark_open(t+h)` — same instant, adjacent field, anchored in (b); and the placebo's exit minute *is* evaluated intrabar by `on_bar` before `close_now` (base exit bar is not) — also anchored in (b). And the source `sl_dist` is the decision-time value from `trades_t3`, whereas trial #2 read the post-fill field — say explicitly this is deliberate (r3 §1 defines `sl_dist = 1.5·ATR/m`; Codex (d) before #6).
> 
> **5. Q3 — conventions additions, numbered from 45 (show as `git diff` in the report):**
> - 45 Source: `SourceTrade(trade_id, entry_ms=fill open, exit_ms=PositionClosed.ts_ms, sl_dist=t3.sl_dist)` from the arm's **base** run; `h = max(1, ceil(Δ/60,000))`; zero source → not-computable marker, no draws.
> - 46 Eligibility: bad minutes = every minute of an incomplete day ∪ every 00/08/16 bucket without exactly one validated record; clean segments = maximal bad-free runs within window open-minutes; `eligible(h)` = `t` with `[t, t+h−1]` inside one segment; ascending; lazy indexable; brute-force equality test.
> - 47 P1 funding at the fill minute (item 1 above), and the two (b)-anchored exit differences from item 4.
> - 48 Placement `sizing_decision(mark_open[t], dir, sl_dist, #48 rules, LIMITS, E_ref, REGIME, slippage_rate=0.0006)`; execution `run_time_exit(…, reason=TIME_EXIT, slippage_rate=0.0006)`; placement-accepted-then-refused → run failure (`AssertionError` in `p1_null_distribution` is the existing behaviour — keep it).
> - 49 Per-arm `P1Config(master_seed=(20260929, arm_tag), 1000, 1000, 10)` via one typed cast; no `p1_core` edit; identity test.
> - 50 Outputs: `canonical_json` draws + null rows `{draw, n, mean_net_bps, exits{time_exit, liquidation}}`; merge requires draws 0..999 exactly once; `failed > 10` and `n_source = 0` are markers the evaluator turns into §7 verdicts (IS(4)/IS(1)); P1 does not use the admissibility bitmap.
> 
> **6. Tests the plan doesn't list yet:** midnight-crossing hold that is eligible (h = 240 spanning 00:00 with the record present) and ineligible (record absent); duplicate minute → day incomplete → excluded from P1 eligibility; execution-side 6 bps as a mutation (flat bars: mean net ≈ −22 bps at 0.0006, ≈ −14 at the default — assert the two differ, not just the first); a committed golden for a two-trade synthetic source (placements + mean net) so the draw path's values are frozen, as (d)'s golden does for the strategy; determinism in two spawned processes against that golden.
> 
> **7. Sequence:** Codex lands → log both verbatim with positions → fold items 1–3 into plan r2 (Codex will likely raise 1 and 2) → narrow re-check → PROCEED → build test-first (`backtest/p1_t3.py`, tests, golden) → shared-diff check (`git diff --stat dc23273 -- backtest/engine_replay.py backtest/placebo_exec.py backtest/p1_core.py paper/ sizing/ exchange/`, expected empty — note `p1_core.py` is now in that list) → after-pass → push → conventions diff → memory → report → stop before (f). Report leads with item 1's disclosure; the user will read that as the one thing they didn't already know.

### Codex 원문(verbatim · task-mun6jc9z-43lve4)
> ## Findings
> 
> 1. **BLOCKER — entry-boundary funding can be charged to a P1 trade.** A validated funding record may have a timestamp *inside* its 00/08/16 minute. [run_time_exit](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:80) includes any record with `funding_ms > entry_ms`, then settles it before processing that minute’s bar. If P1 enters at the boundary minute’s open, this charges funding that r3 §1 says an entry in that minute does not pay. **Fix:** keep `b = t` in the eligibility check, but exclude records whose *bucket* equals `entry_ms` from that slot’s execution input (or fix the shared executor to do so). Test a record at `t + 5 ms` and one at the next boundary.
> 
> 2. **MAJOR — the executor ignores the requested engine exit reason.** [run_time_exit](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:98) overwrites its `ExitReason.TIME_EXIT` argument with `"liquidation"` and passes that string to `Engine.close_now`. Its returned summary later says `"time_exit"`, masking the engine event’s wrong reason. **Fix:** use a separate variable for the outcome, pass the original `reason` argument to `close_now`, and derive or assert the reported reason from `PositionClosed.reason`. E5’s “no `placebo_exec` edit” constraint must change for this fix.
> 
> 3. **MAJOR — E6 does not yet specify a complete merge check.** Covering draw IDs 0–999 once does not establish that the null rows represent exactly the successful draws. **Fix:** require null-row draw IDs to equal the successful draw IDs exactly once; for each row require `n == source trade count` and `time_exit + liquidation == n`. Reject malformed parts before computing p95.
> 
> 4. **MINOR — make input validation explicit before constructing segments.** [complete_days](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:91) can identify complete mark days, but E3/E6 should say that P1 validates the original ordered bar sequence and funding records *before* converting bars to a dict or counting funding buckets. **Fix:** invoke the existing input checks on the sequence and use pinned, validated records for eligibility.
> 
> ## Q1–Q3
> 
> **Q1:** Yes. Include `b = t` in the **eligibility** interval. That is the literal r3 §4 closed interval, even though the entry-minute boundary is not charged. Keep eligibility and settlement as separate rules.
> 
> **Q2:** E2’s duration is correct. The replay records a scheduled time exit at the exit bar’s open, giving `h = 240`; an intrabar SL or liquidation uses that bar’s `close_ms`, so ceiling includes that bar. This follows [engine_replay](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:83) and [SourceTrade.h](/home/cms/project/BTC_Futures_E2E/backtest/p1_core.py:41). Preserve the raw `exit_ms`; do not round it before computing `h`.
> 
> **Q3:** Add conventions text for: (i) the closed funding-boundary **eligibility** test versus no **settlement** for the entry bucket, including offset timestamps; (ii) the E2 timestamp-to-`h` examples; and (iii) the draw/null-row merge invariants above. State that P1 checks original bar and funding inputs before building its minute grid.
> 
> The planned entry-bucket charge contradicts r3 §1’s funding rule. The cross-day segments and closed eligibility rule otherwise match r3 §4. This was a read-only review; I ran no tests or backtests.
> 
> **VERDICT: FIX-PLAN-FIRST**
> 
> Codex session ID: 01a0ef09-aace-7f80-9d41-92e842a2cffd
> Resume in Codex: codex resume 01a0ef09-aace-7f80-9d41-92e842a2cffd

### 계획 r2 원문
> # Trial #3 (e) plan r2 — resolutions (advisor 1–7 + Codex task-mun6jc9z-43lve4 1–4, Q1–Q3)
> 
> R1 ENTRY-MINUTE FUNDING (Codex 1 BLOCKER, advisor 1): eligibility keeps the closed interval [t, t+h−1] (b = t included — r3 §4
>    literal). SETTLEMENT follows r3 §1 funding row "경계 분에 체결된 포지션은 그 경계를 내지 않는다": the trial-#3 P1 executor passes
>    run_time_exit only the funding records whose bucket (funding_ms − funding_ms % 60,000) ≠ entry_ms, so a record inside the entry
>    minute (e.g. t + 5 ms) is never charged — same outcome as the base replay (funding settles only when a position exists; the entry is
>    pending then). Trial-#3 caller-side filter; no shared change for this. Tests: record at exactly t, at t + 5 ms (both not charged),
>    and at the next boundary inside the hold (charged once).
> R2 EXIT-REASON LABEL (Codex 2): placebo_exec.run_time_exit shadows its `reason` argument ("liquidation" string passed to close_now); P&L
>    and the returned TimeExitResult.reason are unaffected, only the engine PositionClosed label. Fix in the shared module: keep the argument,
>    use a separate outcome variable, pass `reason` to close_now, and assert the engine event's reason (TIME_EXIT / the caller's reason for
>    time exits, LIQUIDATION for engine liquidations) matches the returned outcome. SHARED CHANGE → full trial #2 regression re-run
>    (scripts/t2_regression_check.py, all 205 runs + P1 + merge + diagnostic evaluator hash) before the after-pass; trial #1 golden
>    (golden_p1_trial01) must stay byte-identical. Expected zero byte change (the label is not persisted in any trial output) — to be proven.
> R3 PRODUCTION / FIXTURE SPLIT (advisor 2): p1_t3 run functions take no `rules`/params: rules = harness.load_rules() (#48), TF_V1 constants;
>    a separately named fixture function with the same tests/-only runtime guard; the repo-wide static scan extended to its name.
> R4 INPUTS (Codex 4, advisor 2): P1 run boundary calls harness.validate_inputs(bars, fundings) on the ORIGINAL ordered sequences before
>    building dicts/segments, and uses harness.complete_days (same duplicate-minute semantics as admissibility).
> R5 WINDOW EDGES (advisor 3): t ≥ WINDOW_START_MS and t + (h−1)·60,000 ≤ IS_END_MS − 59,999 (last window open minute); tests at both ends.
> R6 MERGE INVARIANTS (Codex 3): draws 0..999 exactly once; null-row draw ids == successful draw ids exactly once; each row n == number of
>    source trades and time_exit + liquidation == n; zero-source → not-computable marker (no draws); failed > 10 → not evaluable marker;
>    malformed parts rejected before any p95.
> R7 DISCLOSURES (advisor 4): placebo exits at mark_close(t+h−1) (base: mark_open(t+h) — same instant, adjacent field, (b)-anchored); the
>    placebo's last minute is evaluated intrabar by on_bar before close_now (base exit bar is not) — (b)-anchored; source sl_dist is the
>    DECISION-time value (t3.sl_dist, r3 §1 sl_dist = 1.5·ATR/m), unlike trial #2 which read the post-fill field — deliberate.
> R8 TESTS (advisor 6): brute-force eligibility equality; midnight-crossing eligible (record present) / ineligible (record absent); duplicate
>    minute → day incomplete → excluded; 6 bps mutation (flat bars: ≈ −22 at 0.0006 vs ≈ −14 at default, assert both); committed golden for a
>    two-trade synthetic source (placements + mean net); determinism in two spawned processes against that golden; tuple-seed identity.
> R9 CONVENTIONS additions 45–50 (+ R1/R2/R7 text) shown to the user as a git diff.
> Shared-diff check before the after-pass: git diff --stat dc23273 -- backtest/engine_replay.py backtest/placebo_exec.py backtest/p1_core.py
> paper/ sizing/ exchange/ (placebo_exec will differ by R2 only).

### Codex 원문(verbatim · task-mun6obzc-d2txmf)
> **Plan-level re-check: findings 1–4 are CLOSED.**
> 
> | Finding | Status | Reason |
> |---|---|---|
> | 1 — entry-minute funding | **CLOSED** | R1 keeps the entry minute in the [P1 eligibility interval](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:92) but excludes that minute’s funding record from settlement. That matches [r3 §1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:37): replay processes funding before a pending entry fills. The current [executor filter](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:80) would otherwise charge a record at `t+5 ms`. |
> | 2 — exit-reason label | **CLOSED** | R2 fixes the shadowed `reason` at [placebo_exec.py:98](/home/cms/project/BTC_Futures_E2E/backtest/placebo_exec.py:98) while preserving the returned outcome. The proposed event assertion covers the caller’s time-exit label and engine liquidation label. |
> | 3 — merge invariants | **CLOSED** | R6 requires exact draw and null-row identity, trade and exit-count reconciliation, and rejection of malformed parts before p95. |
> | 4 — input validation | **CLOSED** | R3–R4 pin production rules and parameters and validate the original sequences before constructing lookup structures. |
> 
> R2 correctly treats the fix as a **shared change** and requires the full [trial #2 regression check](/home/cms/project/BTC_Futures_E2E/scripts/t2_regression_check.py:10): 205 strategy runs, P1 parts and merge, plus the diagnostic evaluator hash. The after-pass should use it **without `--skip-runs`** and report the trial #1 P1 golden comparison. Its `meta.json` comparison intentionally ignores `git_head` and `gate`, so describe the byte-identity claim with that exception.
> 
> **New gap to clarify in the test wording:** R8’s duplicate-minute case cannot reach production eligibility through R4: [validate_inputs](/home/cms/project/BTC_Futures_E2E/strategies/trial03/harness.py:47) rejects it first. Test “day incomplete → excluded” directly at the eligibility helper, and separately test that the production run rejects the duplicate input. This does not change the planned behavior.
> 
> This was a read-only plan review; no code or tests were run.
> 
> **VERDICT: PROCEED.**
> 
> Codex session ID: 01a0ef0d-3647-7cb0-a17d-6b4cc79ff97a
> Resume in Codex: codex resume 01a0ef0d-3647-7cb0-a17d-6b4cc79ff97a

## 2026-09-30 — 트라이얼 #3 (e) P1 **after-pass**(advisor + Codex task-mun81owl-d8flpb **FIX-FIRST**) → 테스트 보강
- 공유 변경: placebo_exec.run_time_exit 사유 덮어쓰기 수정(1d5f941) → 트라이얼 #2 전체 회귀(1d5f941): identical · 불일치 0 / 1,043파일 · report 9223047c… · 재실행 트리 = (b) 기준선 바이트 동일 · 30:41 · 3.67 GB · 증거 docs/trials/trial_03_step_e_regression/ · 트라이얼 #1 P1 골든 통과.
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 청산 쪽 펀딩 비대칭(기본은 종료 봉 분 지불 · P1은 [t, t+h)) | ✅ | 공시(둘 다 앵커) · 규약 47 문구 · 테스트(08:00 청산 순간 정각·+5 ms 미지불 · 07:00 돌연변이) · (f) 보고 개수(항목 44) |
| advisor | 2 47 문구 범위 | ✅ | 진입 쪽만 기본과 같다고 정정 |
| advisor | 3 보고 틀 | ✅ | 보고에 |
| advisor | 4 순서 | ✅ | — |
| Codex | 1 중복 분 적격 도우미 테스트 누락 | ✅ | build_segments에 중복 분 → 그 날 제외 테스트 추가(실행 경계 거부 테스트 유지) |
| Codex | 2 '한 번' 증명 안 됨 | ✅ | Engine.on_funding 호출을 세어 보유 중 경계 하나만 정확히 한 번 |
- 검사: 전체 통과(아래 커밋) · ruff · pyright 0.

### 요약 원문
> # Trial #3 (e) AFTER-PASS — built vs plan r2
> Commits: 1d5f941 (backtest/p1_t3.py; placebo_exec fix; tests/test_p1_t3.py 25; tests/fixtures/{t3_p1_fixture.py, golden_p1_trial03.json};
> static-check updates), then regression evidence + conventions 45–50. Shared diff since dc23273: backtest/placebo_exec.py only (R2).
> R1 entry-minute funding: null_point passes run_time_exit only records whose bucket ≠ entry_ms (tests: exact t and t+5 ms not charged;
> crossed boundary charged). R2: run_time_exit uses `outcome` for the returned reason, passes `reason` to close_now, asserts engine reason
> (TIME_EXIT/caller reason or LIQUIDATION); test spies close_now. Full trial #2 regression on 1d5f941: identical, 0 mismatches / 1,043 files,
> report 9223047c…, tree identical to the (b) baseline; trial #1 P1 golden passes. R3: run_range(arm, trades_t3, bars, fundings, lo, hi) has no
> rules/cfg args (load_rules + CFGS[arm] + WINDOW_START…IS_END); run_range_with_fixture_rules tests/-only (runtime guard + repo-wide AST scan).
> R4 validate_inputs first; complete_days reused. R5 window edges tested. R6 merge invariants tested (missing draw, null mismatch, n, exits,
> arm mismatch, zero source, >10 failures). R8 brute-force eligibility equality (4 h × 3 cases), midnight crossing with/without the 00:00
> record, tuple-seed identity, 6 bps mutation (≈−22 vs ≈−14), golden for a two-trade source (both arms), determinism in two subprocesses.
> Suite 1364 passed; ruff; pyright 0.
> Questions: objections; conventions 45–50 text (docs/trials/trial_03_conventions.md) accurate?

### advisor 원문(verbatim)
> This is the advisor half of the (e) after-pass. The build matches plan r2; the regression proof is the strongest available (full 205 + P1 + merge, tree byte-identical to the (b) baseline, trial #1 golden intact); the Codex blocker is closed on the caller side with no shared change. One blind spot your checks and Codex's questions didn't cover, then records.
> 
> **1. MAJOR — item 47 fixes the entry side of the funding asymmetry but misses the exit side, and the two don't cancel.** Base time exit: bar t_f+240 settles a funding whose bucket is that minute *before* the exit at its open (your (c) test `test_time_exit_in_boundary_minute_pays_first` proves it). P1: `run_time_exit` sets `exit_ms = entry + h·60,000 − 1`, so a record at bucket `t + h·60,000` — the same instant as the base exit — is **not** charged; r3 §4 (b)'s occupancy `[t, t+h)` and eligibility `[t, t+h−1]` also exclude that minute. Concretely: when a hold's exit lands on a 00/08/16 minute (~1/480 of trades), base pays and P1 doesn't. SL/liquidation exits are consistent (h = k+1, both charge bucket t+k). Both sides are anchored (§1 line 31 vs §4 (b)), so this is disclosure, not a change:
> - Add to item 47: "exit side: base pays a funding at the exit-bar minute; P1's occupancy ends at `t+h·60,000 − 1`, so a record at bucket `t+h` is not charged; time_exit / open-gap liquidation only."
> - Test: a placed slot with h = 240 whose exit instant is 08:00, record at 08:00 exact and at 08:00 + 5 ms → `mean_net_bps` equals the no-funding case (mutation: move the record to 07:00 → differs).
> - (f) report-only count: base trades whose `exit_ms` bucket is a boundary (both arms), so the size of the asymmetry is visible.
> 
> **2. MINOR — item 47's phrase "기본 재생과 같은 결과" is now too broad.** After item 1, say "entry side identical to base; exit side differs as disclosed."
> 
> **3. Report shape.** Lead with the Codex blocker (entry-minute funding would have been charged for offset records; fixed at the caller, r3 §1 quoted). Then the shared fix: what it was (label only, P&L and returned reason unaffected), why fixed anyway, regression identical with the numbers (1,043 / 0 / `9223047c…` / tree = (b) baseline / trial #1 golden). Then item 1 as the one thing they don't know yet. Then the test-rule change: the slippage static check now admits `TF_V1.slippage` in `backtest/*_t3.py`. Then the conventions diff — use `git diff 4f1f88b HEAD -- docs/trials/trial_03_conventions.md` so it covers everything since the draft they reviewed (items 1/15/34/38 edits and 45–50), and say the row is still not appended.
> 
> **4. Sequence:** Codex lands → log advisor + Codex verbatim with positions → item 1 (test + item 47 text) + any Codex fixes → full suite → commit → push → `memory/trial03-status.md` to "(e) done, waiting before (f); conventions 45–50 pending user review" → report → stop before (f). If Codex asks about `next_funding_ms` in the restored position after the filter, the answer is that replay-mode settlement is driven by explicit `on_funding` calls, not that field — verify by grep before asserting it.

### Codex 원문(verbatim · task-mun81owl-d8flpb)
> 1. **MINOR — the duplicate-minute eligibility case from plan r2 R8 is missing.** [test_p1_t3.py](/home/cms/project/BTC_Futures_E2E/tests/test_p1_t3.py:86) removes a minute to test helper exclusion, then tests duplicate rejection only at the run boundary. Add a separate `build_segments` test with a duplicated minute and assert that the affected day is excluded; keep the run-boundary rejection test.
> 
> 2. **MINOR — the crossed-boundary funding test does not prove “charged once.”** [test_p1_t3.py](/home/cms/project/BTC_Futures_E2E/tests/test_p1_t3.py:115) asserts only that the return falls. Assert one `on_funding` call for the crossed record, or compare the return with the exact single-charge result.
> 
> I found no implementation objection. Conventions [45–50](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_conventions.md:64) accurately describe the code and anchored P1 rule. The shared diff contains only the planned `placebo_exec` reason fix, and the committed regression hash list matches its baseline. In this read-only workspace, 24 P1 tests passed; the remaining test could not set up because `tmp_path` requires a writable temporary directory.
> 
> **VERDICT: FIX-FIRST** — close the two explicit plan r2 test gaps before merging.
> 
> Codex session ID: 01a0ef30-5b4d-72e1-bf17-ff083b861051
> Resume in Codex: codex resume 01a0ef30-5b4d-72e1-bf17-ff083b861051

## 2026-09-30 — 트라이얼 #3 (e) after-pass 수정 확인(Codex task-mun89nkv-aqw86v FIX-FIRST: 규약 47 문구) → 문구 정정
- 입장: ✅ 동의 — "time_exit 보유에서만" → "time_exit·시가 갭 청산 보유(종료 봉 분에서 끝나는 보유)에서만". 테스트 두 건은 CLOSED(Codex).

### Codex 원문(verbatim · task-mun89nkv-aqw86v)
> The two requested test gaps are closed: the duplicate-minute test excludes the affected day through `build_segments`, and the funding spy observes exactly one call for the crossed record. The exit-boundary test also passes for records at 08:00 and 08:00 + 5 ms. I ran those three tests directly; pytest could not start because this read-only environment has no usable temporary directory.
> 
> [Item 47](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_conventions.md:66) still needs one wording fix. It first says the asymmetry applies to both `time_exit` and open-gap liquidation, then says the difference occurs **only** for `time_exit` holds. Include open-gap liquidation in that latter clause. [Item 44](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_conventions.md:61) includes the requested report count.
> 
> **VERDICT: FIX-FIRST**
> 
> Codex session ID: 01a0ef36-06a9-70e0-831c-1a481ee2f446
> Resume in Codex: codex resume 01a0ef36-06a9-70e0-831c-1a481ee2f446

## 2026-09-30 — 트라이얼 #3 (e) 완료: Codex task-mun8bdsh-gnldae **MERGE**

### Codex 원문(verbatim)
> The HEAD diff fixes the wording identified in task-mun89nkv-aqw86v: item 47 now includes both `time_exit` and open-gap liquidation in the clause describing when the exit-side funding difference occurs. This was a read-only wording review; I did not rerun tests.
> 
> **VERDICT: MERGE**
> 
> Codex session ID: 01a0ef37-4027-7bb3-b034-3ad34cad4018
> Resume in Codex: codex resume 01a0ef37-4027-7bb3-b034-3ad34cad4018

## 2026-09-30 — 트라이얼 #3 (f) 판정기 **before-pass**(advisor + Codex task-munbd29z-9jaw3l FIX-PLAN-FIRST → r2 task-munbhled-4xt5ad FIX-PLAN-FIRST → r3 task-munbkkz8-ih5jfd **PROCEED**)
- 사용자 (e) 승인 + 항목 47 보고 추가(청산 분 경계 트레이드의 펀딩 합 USDT·E_ref bps · 암마다).
- 사용자 문구와 앵커 문언(보고에 인용): (a) 판정 문자열 = 87행 형식 그대로, "청산 k / 체결 n"은 보고에 · (b) INCONCLUSIVE 없음 — §7-2 세 분류 · (c) ACCEPT는 전진 단계에서만(IS는 IS PASS에서 끝) · (d) 접미어는 143행 문구 · (e) "IS PASS · 생존 통과".
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 진입일 ∈ V를 실행 시점에 | ✅ | V1 harness.assert_entries_in_v |
| advisor | 2 청산 항등식·정밀도 | ✅ | V2/V2′ |
| advisor | 3 G-B 두 암 먼저 | ✅ | V5 |
| advisor | 4 (g) 계약 동결 | ✅ | V4 |
| advisor | 5 문자열 규칙 | ✅ | V6 |
| advisor | 6 MDE n_eff·V 8기록 | ✅ | V7 |
| advisor | 7 기록(골든 재생성) | ✅ | ops_log · 골든 메타 |
| advisor | 8 테스트 | ✅ | V9 |
| advisor | 9 Q3 | ✅ | V2′ |
| Codex | 1 청산 지갑 항등식(BLOCKER) | ✅ | V2(엔진 값 · 전체 식) |
| Codex | 2 청산 거리 권한(BLOCKER) | ◐ | 이미 사용자 결정 (A)(2026-09-30)으로 해소 — 기록 인용(V3) · Codex r2 CLOSED |
| Codex | 3 입력 계약 | ✅ | V4 |
| Codex | 4 gross·net 정확 검증 | ✅ | V2 |
| Codex | 5 자료 없음 생존 문구 | ✅ | V6 |
| Codex r2 | 정밀도(28 vs 34자리)(BLOCKER) | ✅ | r3 V2′ — 지갑 34자리 · 수익률은 trade_return 28자리 재계산 · Codex r3가 골든에서 재현 |
- 구현 중 기록: 전략 filled/exit 기록에 엔진 원장 필드 추가(entry_ref · entry_commission · exit_price · exit_fills · realized_pnl · exit_commission · funding_paid · wallet_after · ts_ms) → `golden_trial03_e2e.json` 다이제스트만 재생성(트레이드·의도·깔때기 값 불변 · P1 골든 불변).

### 계획 r1 원문
> # Trial #3 step (f) — evaluator (backtest/evaluate_t3.py + verdict_t3.py): BEFORE-PASS plan (no code yet)
> 
> ## Anchored lines (verbatim, r3)
> - line 13: - 두 암은 **각각 독립 가설이자 독립 장부**다(진입 조건이 반대라 같은 이벤트가 두 암에 동시에 들어가지 않는다 · 단 두 장부의 포지션은 **시간상 겹칠 수 있고** 서로 막지 않는다 · 트라이얼 #1·#2의 "판정 A + 보고 B"와 다르다). 트라이얼 결과 = 두 암의 판정 쌍.
> - line 63: > 두 암(L·S)이 각각 판정 대상이다. 장부(트레이드·PnL)·G0/G1/G2/flat/생존/P1~P3·OOS 진행·전진은 암마다 독립이다(IS를 통과한 암은 다른 암과 무관하게 자기 OOS로 — 사용자 승인). **유일한 예외는 G-B**: N 규칙상 SR*가 두 암의 실현 SR̂를 모두 포함하므로 한 암의 G-B 결과는 다른 암의 실현 Sharpe에 의존한다(아래 G-B 행 · 공시·수용).
> - line 64: > 평가 순서(트라이얼 #2와 같은 운용): **IS 단계**(G0 → G1 → G2 → G-B → flat → 생존 → P1 → P2 → P3) → **OOS 단계**(G3 · OOS G0 · OOS 생존) → **전진 단계**(G-F). OOS는 IS 전부 통과한 암만, 한 번만.
> - line 87: - **판정 문자열(한 줄 · 헌법 v1.3)**: 암마다 `<ACCEPT|REJECT|폐기>(§7-2: <분류>) · 생존 <통과|실패>` · 트라이얼 문자열 = `L: … | S: …`.
> - §7 table lines 124–143:
>   | 단계 결과 | 판정 문자열 |
>   |---|---|
>   | IS(0): 필수 데이터셋을 구할 수 없음 · 또는 그 암의 V가 비었음 | **폐기** |
>   | IS(1): 트레이드 0건 | **REJECT(FAIL — 트레이드 0)** |
>   | IS(2): 청산 ≥ 1 | **REJECT(생존)** |
>   | IS(3): G0 · G1 · G2 · G-B · flat 중 실패 | **REJECT(§7-2: 분류)** |
>   | IS(4): P1 실패 추출 > 10 | **폐기**(플라시보 하네스 결함) |
>   | IS(5): P1 · P2 · P3 기각 | **REJECT(§7-2: 분류)** |
>   | IS 전부 통과 | **IS PASS** — OOS 개봉은 사용자 결정 |
>   | OOS(0): OOS 데이터 준비 불가 · OOS V 빈 경우 | **폐기(OOS 데이터)** |
>   | OOS(1): 트레이드 0건 | **REJECT(FAIL — OOS 트레이드 0)** |
>   | OOS(2): 청산 ≥ 1 | **REJECT(생존)** |
>   | OOS(3): OOS G0 미달 | **REJECT(OOS 표본 부족)** |
>   | OOS(4): G3 실패 | **REJECT(§7-2: 분류 · OOS 값)** |
>   | OOS PASS | **OOS PASS** — 전진 활성화는 사용자 결정 |
>   | 전진(1): 청산 ≥ 1 또는 킬스위치 ≥ 1 | **REJECT(생존 · 전진)** |
>   | 전진(2): 규칙-실행 불일치 · 데이터 결손 > 0 | **폐기(전진 실행 결함)** |
>   | 전진(3): 트레이드 0건 | **REJECT(FAIL — 전진 트레이드 0)** |
>   | 전진(4): 부호 ≤ 0 | **REJECT(전진 부호)** |
>   | 전진 전부 통과 | **ACCEPT** · IS 창에서 암 일간 Sharpe < 매수보유 일간 Sharpe면 `ACCEPT — 수동(매수보유)을 이기지는 못함` |
> - line 146 (§7-2): - **검정력 부족**: MDE(α 0.008333 · 검정력 0.8 · 관측 σ · G0 n_eff) > 2θ = 20 bps · **효과 부재**: MDE < 5 bps ∧ net CI 상한 < θ · 그 사이 **결론 보류형 REJECT**.
> 
> ## Reading of the anchored text (user req. 1)
> - Arms are judged separately (line 63); the ONLY trial-level statement is line 13 "트라이얼 결과 = 두 암의 판정 쌍" and line 87 "트라이얼 문자열 =
>   `L: … | S: …`" — a pair, no combined verdict. The one cross-arm dependency is G-B's SR* (line 63/71).
> - Verdict priority per arm = §7 table order (IS(0) 폐기 → IS(1) trades 0 → IS(2) liquidation ≥ 1 → IS(3) G0/G1/G2/G-B/flat → IS(4) P1
>   failures > 10 → IS(5) P1/P2/P3 → IS PASS). §7-2 classification only for IS(3)/IS(5) REJECTs.
> - Flags for the user (anchored wording wins, as before): (a) user req. 3's example "survival: 0 liquidations / N trades" — r3 line 87 fixes
>   the string as `<ACCEPT|REJECT|폐기>(§7-2: <분류>) · 생존 <통과|실패>`; proposal: keep the string exactly, put "청산 k / 체결 n" in the report
>   line beside it. (b) user req. 7 "INCONCLUSIVE" is not an r3 class — the §7-2 REJECT sub-classes are 검정력 부족 / 효과 부재 / 결론 보류형
>   REJECT; tests reach each. (c) ACCEPT exists only at the forward stage (§7 전진 rows) — the IS evaluator ends at IS PASS / REJECT / 폐기;
>   the OOS and forward verdict functions are pre-committed and tested with synthetic inputs (as trial #2). (d) the suffix text is r3's
>   "ACCEPT — 수동(매수보유)을 이기지는 못함" (line 143), only on ACCEPT (forward function). (e) IS PASS string: "IS PASS · 생존 통과".
> 
> ## Plan
> F1 verdict_t3.py (pure, float64, like verdict_t2): per-arm ISInputs → Verdict; constants from the trial-3 anchor (N_TRIALS 6, ALPHA 0.05/6,
>    LEVEL 1 − ALPHA, pinned SR̂ ×4); G0 n ≥ 48 ∧ n/(1 + 4·max(ρ̂, 0.15)) ≥ 30; G1/G2 mean > 0 ∧ CI lo > 0 (CI undefined → fail); G-B
>    PSR(0) > 0.5 ∧ n ≥ 30 ∧ SR̂ − SR* > 0 with SR* = expected_max_sr(defined {SR̂_1A, SR̂_1B, SR̂_2A, SR̂_2B, SR̂_L, SR̂_S}, n_trials 6),
>    < 2 defined → fail; flat mean net > 0; survival liquidations = 0; placebos: P1 orig ≤ p95 → reject, P2 orig ≤ max(+1, +5), P3 orig ≤
>    inverted; P1 failures > 10 or not computable → 폐기(IS(4)) only after IS(0–3); MDE (z_{1−α} + z_{0.8})·σ/√n_eff; classify as §7-2
>    (θ 10). Non-finite input → ValueError (refusal). verdict_oos / verdict_forward pre-committed (§7 rows). Strings per line 87.
> F2 evaluate_t3.py: compute per arm from run outputs: net/gross bootstrap on V days with streams SeedSequence((20260929,1)).spawn(8)[k]
>    (IS k: gross_L 0, net_L 1, gross_S 2, net_S 3), 10,000 resamples, level 1 − 0.05/6 (quantiles 1/240, 1 − 1/240); ρ̂ lag-1 of net in
>    entry order; SR̂ ddof 1; PSR(0); P1 p95 = numpy linear 0.95 quantile of successful draws' mean net; P2/P3 means (0 trades → 0).
> F3 Inputs/layout (the (g) stage runner will produce exactly this; evaluator checks the inventory): per arm × {base, P2_delay1, P2_delay5,
>    P3_invert}: trades_t3.jsonl, events.jsonl, summary.json (funnel, sub, entry, window_bars, q_valid days, V); per arm P1_merged
>    (merge() output); prepared: bars, funding, kline daily (pinned loaders). Full provenance (fingerprint, pins, verify receipt) wiring in (g).
> F4 V recomputation (item 31): evaluator recomputes complete days (harness.complete_days) and per-day quantile validity from defined-r30
>    COUNTS (bar presence/positivity only — no r30 values) over d−90..d−1 ≥ 128,304; must equal each run's recorded V; any trade with entry day
>    ∉ V → refuse.
> F5 Cost grid + exact ledger identity (item 42): the strategy's filled/exit records gain entry_commission, entry fill & reference mark,
>    exit fill (VWAP of fills), exit_commission, funding_paid (trial-3 code only; e2e golden regenerated with a note). Evaluator asserts per
>    trade wallet_after − wallet_before == −comm_in − comm_out − funding + (exit_fill − entry_fill)·qty·sign (Decimal, exact; liquidation:
>    == −loss per engine) and computes scalable_cost_bps = (comm_in + comm_out + slip_in + slip_out)/(qty × entry_fill)×1e4 (liquidation:
>    entry leg only), net_k = net + (1 − k)·cost, k ∈ {0.5, 1.0, 1.5}; ×1.0 == recorded net asserted. Report-only.
> F6 B&H (report): kline daily closes over WINDOW days, daily Sharpe, window return; arm daily Sharpe from the N_stat ledger (0 on V days
>    without entries); is_bh_beats feeds only verdict_forward.
> F7 Report: event funnel + sub-reasons, entry funnel, oi_missing{unusable} separately, X9 (time_exit with exit_ref beyond SL), boundary-exit
>    count + summed funding paid/received (USDT and bps of E_ref) per arm (user addition to item 47), per-year net, hold-time quantiles,
>    exit reasons, cost grid, B&H, P1 exits (time_exit/liquidation), degenerate resample counts.
> F8 Numerics (item 43): Decimal-string → float via finite check; np.errstate(over/invalid/divide = raise); undefined never passes.
> F9 Run-once (user req. 7): evaluate(base) refuses if base/evaluation exists; refuses unless the evaluator commit (receipt) is an ancestor
>    of origin/main and HEAD, evaluator files unchanged since it, working tree clean (as trial #2 G1); writes evaluation/ atomically (tmp +
>    rename) with report.json, verdict.txt, record.json (hashes of every input read). Fingerprint/pins/receipt checks = (g).
> F10 Tests: verdict core reaching every §7 IS row and every §7-2 class for L and S; G-B cross-arm dependence; OOS/forward functions incl.
>    ACCEPT with/without suffix; end-to-end compute on synthetic scenario runs (both arms, all variants, P1 fixture parts) → report; cost-grid
>    identity incl. a liquidation trade; V mismatch → refusal; trade outside V → refusal; run-once and not-on-origin refusals; report hash
>    determinism (twice + two processes).
> F11 No shared-code changes expected; if any → trial #2 regression.
> Q1 verdict-string handling (flag a); Q2 anything else the evaluator must pre-commit before any P&L; Q3 is the cost-grid identity (F5)
>    exact enough given engine rounding?

### advisor 원문(verbatim)
> This is the advisor half of the (f) before-pass. The plan's reading of §0/§3/§7 is right — per-arm verdicts, the pair is the only trial-level statement, G-B is the one coupling — and flags (a)–(e) are the correct way to handle the user's wording. Findings, blocking first.
> 
> **1. MAJOR — line 83's refusal can fire on real data; move the check to run time.** §3-1: "모든 체결의 진입일은 V 안이다 … 아니면 판정기 거부." Admissibility guarantees the entry day is *complete*, not that its quantile is *valid* — an event at 23:50 on day d fills on d+1, and d+1's 90-day sample is a different set. Rare, but if it happens the one-shot evaluator refuses after every run has finished. Add the check to `harness.run_arm` (entry day ∈ V, else `RunInvariantError`) so it fails during the IS runs, before any result is opened; keep the evaluator's check as the second line. Test both. Say in the report what an evaluator refusal means under the run-once rule (nothing written; retry is not a second evaluation).
> 
> **2. MAJOR — pin the liquidation identity and the precision it's checked at.** F5's `Δwallet == −comm_in − comm_out − funding + price P&L` holds only for fill exits. Liquidation has no exit fill: engine.py:607 gives `Δwallet == −(qty·entry_fill/L + fee_basis·liquidationFee)` from E_ref (funding already left the wallet at settlement, so it does not appear again). Assert that form for `exit_reason == liquidation`; `scalable_cost` = entry leg only. And compute every identity inside a 34-digit `localcontext` — the engine's exec context — or the trailing digits won't match (your #4 distance test needed exactly this). Also assert `wallet_before == E_ref` for every trade (L5).
> 
> **3. MAJOR — G-B needs both arms before either verdict; pin the undefined case.** Compute L and S stats first, then `SR* = expected_max_sr(defined ∪ {4 pinned}, n_trials = 6)` — if one arm has < 2 trades or zero variance its SR̂ is dropped, the other arm's SR* uses 5 values, `n_trials` stays 6 (line 71 "정의된 SR̂(최대 여섯)"). An arm at IS(1) still contributes "undefined" to the other's G-B. Test: L with 0 trades, S with 50 → S's G-B uses 4 pinned + SR̂_S.
> 
> **4. MAJOR — freeze the (g) interface now, or (g) will drift.** Write the inventory the evaluator refuses without, as constants in `evaluate_t3.py`: per arm × {base, P2_delay1, P2_delay5, P3_invert} → `trades_t3.jsonl`, `events.jsonl`, `summary.json` (fields: funnel, sub, entry, window_bars, q_valid, v_days, n_trades, variant, arm, params SHA); per arm `P1_merged/` → `p1_draws.json`, `p1_null.jsonl`, `p1_summary.json` (n_source, computable, failed, evaluable). (g) builds to this list; the evaluator's `check_inventory` is a frozen tuple, not discovery. P1 contradiction refusal as trial #2: `computable != (n_base > 0)`.
> 
> **5. Verdict-string rules — write them all, not just the happy path.** Line 87 format applied mechanically: label + `(§7-2: <분류>)` only when a classification exists (IS(3)/IS(5)); `REJECT(FAIL — 트레이드 0)`, `REJECT(생존)`, `폐기…` and `IS PASS` carry none; then ` · 생존 <통과|실패>` on every string, 통과 whenever `liquidations == 0` (including zero trades, including 폐기). Trial string `L: … | S: …`. Put "청산 k / 체결 n" in `report.json` next to the string, per flag (a).
> 
> **6. MINOR — two consistency items.** (i) MDE uses the same `n_eff` with the 0.15 floor as G0 — state it. (ii) The V comparison runs against all eight run records (both arms × four variants), not just base — trial #2's `check_meta` did this.
> 
> **7. Records.** F5's new strategy fields change `golden_trial03_e2e.json` — regenerate with an ops_log line saying why (pre-P&L, fields added, no behaviour change) and assert the P1 golden is unchanged (source fields untouched). The evaluator CLI exposes only the IS stage; OOS/forward verdict functions are pre-committed but unreachable without the registry-row gate already in `prepare_t3.oos_range` — say so in section G.
> 
> **8. Tests the plan should add:** verdict core reaching every §7 row *for each arm* with the other arm at each of {0 trades, defined SR̂}; end-to-end on the synthetic scenario (1 trade per arm → G0 fails → `REJECT(§7-2: 검정력 부족)`) as a report golden, plus report-hash determinism across two processes; cost-grid identity on the (d) liquidation fixture; entry-day-∉-V refusal at the harness and at the evaluator; run-once refusal; not-on-origin refusal via a temp repo.
> 
> **9. Q3 — yes, if item 2's precision rule is followed.** The (b) test proved the fill-exit decomposition exactly at 34 digits; the liquidation form is the engine's own formula; nothing is approximate.
> 
> **Sequence:** Codex lands → log both verbatim with positions → plan r2 with items 1–5 → narrow re-check → PROCEED → build in order: `verdict_t3.py` + tests → strategy record fields + golden regen → `evaluate_t3.compute` + report → wrapper (run-once, commit check, frozen inventory) → shared-diff check (expected empty) → after-pass → section G diff → push → memory → report → stop before (g). Lead the report with flags (a)–(c) quoted from lines 87/143/146, then item 1.

### Codex 원문(verbatim · task-munbd29z-9jaw3l)
> ## Findings
> 
> 1. **BLOCKER — F5’s liquidation wallet identity is wrong.** The engine resets the wallet to E_ref at entry, deducts entry commission and funding, then deducts the liquidation loss. Thus `wallet_after − wallet_before = −entry_commission − funding_paid − loss`, not `−loss`. The latter is only the close event’s debit. Fix F5 to capture `EntryFilled` and `PositionClosed` values and assert that full identity with `Decimal`. For ordinary exits, assert `Δwallet = signed_qty × (exit_fill − entry_fill) − entry_commission − exit_commission − funding_paid`. Recompute recorded `net_bps` from `Δwallet / (qty × entry_fill) × 10⁴`. [engine_replay.py](/home/cms/project/BTC_Futures_E2E/backtest/engine_replay.py:105), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:607), [returns.py](/home/cms/project/BTC_Futures_E2E/backtest/returns.py:27).
> 
> 2. **BLOCKER — an existing liquidation rule contradicts r3 and needs an explicit resolution before P&L.** R3 says the liquidation distance has no fee term; convention item 38 specifies an entry taker term, and the engine supplies that term to `liquidation_estimate`. F5 must not silently treat those as the same rule. Record which authority governs the already anchored trial and its effect on the evaluator’s liquidation checks before freezing the evaluator. Do not edit the anchored r3 text in place. [preregistration §1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:33), [conventions item 38](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_conventions.md:53), [engine.py](/home/cms/project/BTC_Futures_E2E/paper/engine.py:411).
> 
> 3. **MAJOR — F3/F9 leave part of the evaluator’s input contract to (g).** Before the evaluator is committed and pushed, specify the exact per-arm run and P1-part inventory, schemas, hashes, receipt fields, and which missing conditions mean §7 IS(0) `폐기` versus a **refusal** for a missing or malformed run artifact. Verify P1’s `n_source` against that arm’s base trades and its merged rows against the parts. This preserves the anchored “all outputs ready, evaluator once” sequence. [preregistration §4-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:99), [p1_t3.py](/home/cms/project/BTC_Futures_E2E/backtest/p1_t3.py:183), [evaluate_t2.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t2.py:71).
> 
> 4. **MAJOR — F5 should verify both statistics that enter G1/G2.** Wallet identity verifies net P&L, but F2 currently accepts recorded `gross_bps`. Add an exact `Decimal` check of gross from entry mark, exit reference mark, and direction, using the registered return definition; check the recorded net value the same way before conversion to float64. Derive slippage from actual reference and fill prices, including adverse tick rounding. For liquidation, scalable cost has the entry leg only; liquidation fee remains in net and is never scaled. [preregistration §3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:80), [conventions item 42](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_conventions.md:59), [returns.py](/home/cms/project/BTC_Futures_E2E/backtest/returns.py:27).
> 
> 5. **MINOR — define survival text for data-unavailable cases.** F1 should precommit how `생존 <통과|실패>` is printed when IS(0) or OOS(0) prevents observing trades, while retaining the exact §7 verdict label. Otherwise different implementations can print different one-line verdicts for the same input. [preregistration §3-1](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:87), [preregistration §7](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_preregistration.md:123).
> 
> ## Q1–Q3
> 
> **Q1.** Yes: use the r3 per-arm verdict string and `L: … | S: …`. Put `청산 k / 체결 n` beside it in the report, not inside the fixed string. `IS PASS` and `OOS PASS` are stage results; `ACCEPT` and its exact buy-and-hold suffix arise only after forward evaluation. There is no `INCONCLUSIVE` class; use the three §7-2 REJECT classifications.
> 
> **Q2.** Precommit the exact input/provenance contract in finding 3, the gross/net and cost checks in finding 4, and the data-unavailable survival rendering in finding 5. Keep both base-arm Sharpe inputs available for either arm’s G-B calculation, even if the other arm fails an earlier gate.
> 
> **Q3.** No. Engine rounding is compatible with exact `Decimal` checks when the checks use recorded fills and the same calculation context. The proposed liquidation equation omits entry commission and funding from the full wallet change. Fix that equation and compare the ×1.0 grid value to recorded `net_bps` through the exact return formula.
> 
> **VERDICT: FIX-PLAN-FIRST.** Read-only review; no evaluator, backtest, or tests were run.
> 
> Codex session ID: 01a0ef85-5711-7b92-af80-4c597e62c0e3
> Resume in Codex: codex resume 01a0ef85-5711-7b92-af80-4c597e62c0e3

### 계획 r2 원문
> # Trial #3 (f) plan r2 — resolutions (advisor 1–9 + Codex task-munbd29z-9jaw3l 1–5, Q1–Q3)
> 
> V1 ENTRY DAY ∈ V AT RUN TIME (advisor 1): harness.run_arm asserts every filled trade's entry day ∈ that run's V (complete ∧ quantile-valid)
>    → RunInvariantError during the IS runs (before any result is opened); the evaluator re-checks (refusal). Test both. Evaluator refusal
>    under run-once = nothing written; a retry is not a second evaluation.
> V2 LEDGER IDENTITIES (Codex 1+4, advisor 2) — Decimal inside a 34-digit localcontext, per trade, from the strategy's filled/exit records
>    (new trial-3 fields: entry_commission (EntryFilled.entry_commission), entry reference mark (fill bar mark_open), entry fill, exit fill
>    (qty-weighted VWAP of PositionClosed.fills), exit_commission_usdt, funding_paid_usdt, leverage, liquidation fee rate from #48):
>    · wallet_before == E_ref (L5);
>    · fill exits (sl/time_exit): Δwallet == sign·qty·(exit_fill − entry_fill) − comm_in − comm_out − funding;
>    · liquidation: Δwallet == −(qty·entry_fill/L + qty·liq_price_est·liquidationFee) (engine _liquidate with liq_fee_on_liq_price; equals
>      −comm_in − funding − loss_event) — liq_price_est recorded at exit;
>    · gross_bps == sign·(exit_ref − entry_mark)/entry_mark·1e4 (returns.py definition; exit_ref = SL fill basis / exit-bar open / est. liq);
>    · net_bps == Δwallet/(qty·entry_fill)·1e4 (recomputed, compared exactly to the recorded string before float conversion);
>    · slippage legs from reference vs fill incl. adverse tick: slip_in = sign·(entry_fill − entry_ref)·qty, slip_out = sign·(exit_ref − exit_fill)·qty;
>    · scalable_cost_bps = (comm_in + comm_out + slip_in + slip_out)/(qty·entry_fill)·1e4 (liquidation: comm_in + slip_in only);
>      net_k = net + (1 − k)·cost; ×1.0 == recorded net exactly. Any mismatch → refusal.
>    The golden_trial03_e2e.json is regenerated (fields added, no behaviour change) with an ops_log note; P1 golden asserted unchanged.
> V3 LIQUIDATION-DISTANCE AUTHORITY (Codex 2): already resolved — user decision 2026-09-30 (A), ops_log + conventions item 38: registry #4
>    (with the entry taker term) governs; r3 §1 line 33 cites "#2·#4·#5" and its "거리에 수수료 항 없음" is #2's liquidationFee exclusion;
>    r3 §1-1's example distances (2.895%, 7.915%) are #4 values; r3 text untouched. Evaluator does not recompute liquidation distances; it
>    uses engine-recorded liq_price_est only in the V2 identity. Stated again in section G.
> V4 FROZEN INPUT CONTRACT (Codex 3, advisor 4): constants in evaluate_t3.py:
>    RUNS = {arm × variant} for arm ∈ {L, S}, variant ∈ {base, P2_delay1, P2_delay5, P3_invert} → files (trades_t3.jsonl, events.jsonl,
>    summary.json{arm, variant, funnel, sub, entry, window_bars, q_valid, v_days, n_trades, tf_v1_sha256, rules_sha256}); P1 per arm:
>    P1_merged/{p1_draws.json, p1_null.jsonl, p1_summary.json{arm, n_source, computable, failed, evaluable, parts[{lo, hi, sha256}]}} +
>    the parts; prepared inputs via prepare_t3.load_prepared_pinned (+ kline daily). Missing/extra/malformed artifact or schema mismatch →
>    REFUSAL (no verdict). §7 IS(0) 폐기 only when the prepared dataset is unavailable (prepare stop) or that arm's V is empty. Cross-checks:
>    P1 n_source == that arm's base trade count; computable == (n_base > 0); merged rows re-derived from parts (merge()) == merged files;
>    V equal across all eight run records and to the evaluator's recomputation. Provenance (fingerprint, pins, verify receipt) completed in
>    (g) under this frozen list.
> V5 G-B BOTH ARMS FIRST (advisor 3, Codex Q2): compute both arms' stats before any verdict; SR* = expected_max_sr(4 pinned ∪ defined
>    {SR̂_L, SR̂_S}, n_trials 6); an arm at IS(1) (or zero variance) contributes "undefined"; test L 0 trades / S defined.
> V6 STRINGS (advisor 5, Codex 5): per arm `<label>[(§7-2: <분류>)] · 생존 <통과|실패>` — classification only for IS(3)/IS(5) REJECT and OOS(4);
>    생존 = 통과 iff observed liquidations == 0 (incl. zero trades and IS(0)/OOS(0) 폐기, where nothing was observed — pinned), 실패 otherwise;
>    IS PASS → "IS PASS · 생존 통과"; trial string "L: … | S: …"; report.json carries "청산 k / 체결 n" beside it. No INCONCLUSIVE class.
> V7 CONSISTENCY (advisor 6): MDE uses G0's n_eff (ρ floor 0.15); V compared over all eight run records.
> V8 SCOPE: CLI exposes the IS stage only; verdict_oos / verdict_forward pre-committed, unreachable without the registry-row gate
>    (prepare_t3.oos_range).
> V9 TESTS (advisor 8): verdict core — every §7 IS row for each arm with the other arm at {0 trades, defined SR̂}; §7-2 classes; OOS/forward
>    incl. ACCEPT ± suffix; end-to-end synthetic (1 trade per arm → G0 fail → REJECT(§7-2: 검정력 부족)) as a report golden + two-process
>    hash determinism; identities on normal, SL and liquidation fixtures; entry-day ∉ V at harness and evaluator; run-once refusal;
>    not-on-origin refusal via a temp git repo; inventory refusal (missing / extra file, bad schema, P1 n_source mismatch).

### Codex 원문(verbatim · task-munbhled-4xt5ad)
> ## Narrow re-check
> 
> | Prior finding | Status | Assessment |
> |---|---|---|
> | 1. Ledger identities | **PARTIAL** | The plan now specifies the event fields and wallet equations, but its exact bps checks use the wrong Decimal precision. |
> | 2. Liquidation-distance authority | **CLOSED** | The recorded user decision selects registry #4’s formula, including the entry taker term. [Ops log](/home/cms/project/BTC_Futures_E2E/docs/ops_log.md:8107) and [conventions item 38](/home/cms/project/BTC_Futures_E2E/docs/trials/trial_03_conventions.md:53) agree. This decision should not be reopened. |
> | 3. Frozen input contract | **CLOSED at plan level** | r2 fixes the eight runs, P1 inputs, schema checks, V cross-check, and refusal on incomplete inventory. Provenance implementation remains assigned to (g). |
> | 4. Cost and return identity | **PARTIAL** | The cost legs are specified, but the proposed exact comparison to recorded returns has the same precision defect as #1. |
> | 5. Verdict strings | **CLOSED at plan level** | r2 specifies the per-arm labels, classification cases, survival suffix, and combined string. |
> 
> **Blocking new gap:** [trade_return](/home/cms/project/BTC_Futures_E2E/backtest/returns.py:27) calculates recorded `gross_bps` and `net_bps` in the process’s 28 digit context, while r2 requires exact comparison with values recomputed in a 34 digit context. Both arms of the committed [Trial #3 golden](/home/cms/project/BTC_Futures_E2E/tests/fixtures/golden_trial03_e2e.json) fail that comparison. For example, L records net `-21.74572081250031703947691023`; the 34 digit calculation gives `-21.74572081250031703947691022625628`. Pin 34 digits for engine wallet identities and the recorded 28 digit operation order for exact return-string checks; test both against the golden.
> 
> This was a read-only plan review; no evaluator was run.
> 
> **VERDICT: FIX-PLAN-FIRST**
> 
> Codex session ID: 01a0ef88-90c8-7142-ae18-e7a41206aff1
> Resume in Codex: codex resume 01a0ef88-90c8-7142-ae18-e7a41206aff1

### 계획 r3 원문
> # Trial #3 (f) plan r3 = r2 with V2 precision pinned (Codex task-munbhled-4xt5ad blocking gap)
> V2' PRECISION: (i) wallet/ledger identities (Δwallet equations, slippage legs, scalable cost, net_k) are computed in a 34-digit
>     localcontext — the engine's exec context — and compared exactly with the engine-recorded Decimals (wallet_after, fills, commissions,
>     funding, liq_price_est); (ii) the RETURN strings are re-derived by calling backtest.returns.trade_return itself with the recorded
>     inputs (direction, entry_mark, exit_ref, qty, entry_fill, wallet_before, wallet_after) under the process default context set at CLI
>     start (decimal.setcontext(decimal.Context()) — 28 digits, the replay's own context and operation order) and compared as exact strings to
>     recorded gross_bps/net_bps; (iii) the ×1.0 cost-grid value equals the recorded net string exactly (net_k computed from the recorded
>     Decimal, (1 − 1)·cost = 0). Tests: both checks pass on the committed golden trades for L and S; a one-digit perturbation fails each.
> Everything else as r2.

### Codex 원문(verbatim · task-munbkkz8-ih5jfd)
> The r3 precision rule checks out. `paper/engine.py` runs its wallet operations in the 34-digit execution context; `backtest.returns.trade_return` runs in the caller’s default 28-digit context. Replaying the committed L and S scenarios reproduced both golden return strings exactly. The 34-digit wallet equations matched both recorded `wallet_after` values, the ×1.0 cost value preserved each recorded net string, and a one-digit wallet perturbation failed the comparisons.
> 
> The compact golden fixture omits some ledger inputs, so the planned fill, commission, funding, and liquidation comparisons must use replay events.
> 
> VERDICT: PROCEED
> 
> Codex session ID: 01a0ef8a-b173-7c63-b96b-ec364ea1a0e5
> Resume in Codex: codex resume 01a0ef8a-b173-7c63-b96b-ec364ea1a0e5

## 2026-09-30 — 트라이얼 #3 (f) 판정기 **after-pass**(advisor + Codex task-munc0vr0-0wztfu **FIX-FIRST**) → 수정
| 출처 | # | 입장 | 반영 |
|---|---|---|---|
| advisor | 1 봉 0개 창 날 → 거부 위험 | ✅ | 분위수 유효 정의역 = 봉 ≥ 1인 창 날 · zero_bar_window_days 보고 · 테스트(날 전체 제거 → 거부 없음) |
| advisor | 2 경계 청산 개수가 비대칭을 못 잼 | ✅ | 봉 시가 청산만(exit_ms % 60,000 = 0) 합산 · 봉 안 청산은 symmetric_intrabar_n · 테스트 |
| advisor | 3 보고 줄 | ✅ | v_cross_check · bh_beats_arm · constants |
| advisor | 4 (g)가 채울 것 | ✅ | 항목 58 · 보고 |
| advisor | 5 예상 질문 | ✅ | draws_total 정적 검사(tests/ 밖 호출 금지) · evaluate_with_fixture는 _evaluate 공유 |
| advisor | 6 보고 틀 | ✅ | 보고 |
| Codex | 1 동결 범위(BLOCKER) | ✅ | FREEZE_FILES + FREEZE_GLOBS(판정을 바꿀 수 있는 코드 전부 · 파일 집합·바이트) · 푸시된 앵커 변경 거부 테스트 |
| Codex | 2 트레이드↔이벤트 시각(BLOCKER) | ✅ | trade_id 순서 · entry_ms = fill_open · exit_ms = 청산 ts · entry_mark · 레버리지 · 사유 · 방향 · entry = decided+1 · V 안 이동 테스트 |
| Codex | 3 계약 필드 미검증 | ✅ | rules_sha256 = #48 · P1 조각 목록·해시 · 중첩 스키마 · 변조 테스트 셋 |
| Codex | 4 청산 사유 비율 | ✅ | 개수 + 비율 + n_trades |
- 보고서 골든 재생성(보고 필드 추가) · 공유 코드: (e)의 placebo_exec 수정뿐(dc23273 대비).

### 요약 원문
> # Trial #3 (f) AFTER-PASS — built vs plan r3
> Commits b4d1d8d (verdict_t3 + 63 tests; strategy ledger fields; harness.assert_entries_in_v; e2e golden digest regenerated — values unchanged)
> and e69587a (backtest/t3_outputs.py frozen contract; backtest/evaluate_t3.py; tests/test_evaluate_t3.py 15; tests/fixtures/t3_eval_fixture.py;
> golden_eval_trial03.json; conventions section G items 51–62). Shared diff since dc23273: only the (e) placebo_exec fix (regressed then).
> Evaluator: _compute(base, bars, kline_daily, p, window, liq_fee, p1_draws): inventory (t3_outputs.check_run_inventory + read_run per
> arm×variant) → recompute_v (complete days + defined-r30 counts) vs all 8 summaries + tf_v1 SHA + entry days ∈ V → ledger_check on every
> run (34-digit wallet identities incl. liquidation, VWAP/pnl/exit_ref/commission, gross/net via trade_return at 28 digits, cost grid, ×1.0 ==
> net, adverse entry slippage) → arm_stats (bootstrap streams per item 40) → P1 parts re-merged == merged files, n_source/computable checks,
> p95 → ArmInputs → verdict_is (both arms; G-B shared SR*) → report (item 59). compute() pins TF_V1/window/1000 draws; compute_with_fixture and
> evaluate_with_fixture are tests/-only (runtime guard). evaluate(): refuses if evaluation/ exists, commit not ancestor of HEAD and
> origin/main, evaluator files changed since the commit, dirty tree; errors → Refusal; atomic write (report.json, verdict.txt, record.json).
> Synthetic e2e: "L: REJECT(§7-2: 검정력 부족) · 생존 통과 | S: REJECT(§7-2: 검정력 부족) · 생존 통과"; report golden + two-process hash.
> Verdict core tests reach every §7 IS row for both arms with the other arm at {0 trades, defined SR̂}, all §7-2 classes, G-B coupling,
> OOS/forward incl. ACCEPT ± suffix. Suite 1446 passed; ruff; pyright 0.
> Known open for (g): pinned loaders (prepare_t3.load_prepared_pinned + kline daily), fingerprint/data pins/verify receipt, stage runner
> writing via t3_outputs, persisting strategy event logs on mid-run failure, CLI main.
> Questions: objections; does the evaluator match r3 §3/§4/§7 and plan r3; conventions 51–62 accurate?

### advisor 원문(verbatim)
> This is the advisor half of the (f) after-pass. The evaluator matches r3 §3/§4/§7 and plan r3: per-arm verdicts with the shared SR*, the §7 priority order, strings per line 87, ledger identities at the two pinned precisions, frozen input contract, run-once with commit checks. The synthetic end-to-end verdict is the right one for a one-trade arm. Items your checks didn't cover, blocking first.
> 
> **1. MAJOR — `recompute_v` can refuse on real data for a condition known at prepare time.** The strategy records `q_valid` only for window days on which it saw at least one bar (the day-change branch fires on a bar). `recompute_v` builds `q_valid` for *every* window day. A window day with zero mark bars — possible in principle after a REST-fill gap — yields a key the run never recorded, and the equality check refuses after all eight runs have completed. Same class as the before-pass item 1. Fix: define the recomputed `q_valid` domain as window days with ≥ 1 bar (mirror the strategy), and add `zero_bar_window_days` to the report. Add a synthetic test that drops an entire window day and confirms the evaluator does *not* refuse on that alone (V simply excludes the day). Pin it in item 56.
> 
> **2. MAJOR — the boundary-exit count doesn't measure what item 47 says.** `trade_report` counts every trade whose exit minute is a 00/08/16 bucket. But the asymmetry exists only for exits *at the bar open* (time_exit, open-gap liquidation); an intrabar SL or liquidation at a boundary minute is charged on both sides (P1's `h = k+1` covers that bucket). Split the count: asymmetric = `exit_ms % 60_000 == 0` (exit at open) and only those trades' funding is summed for the "size of the asymmetry" figure; the rest reported separately as symmetric boundary exits. Update `test_boundary_exit_report_counts_and_sums_funding` with an SL-at-boundary row that must land in the symmetric bucket. Item 59 wording follows.
> 
> **3. MINOR — three report lines the user asked for implicitly:**
> - An explicit V cross-check result (`"v_cross_check": {"runs_compared": 8, "match": true}`) — today it's implicit in "no refusal."
> - `bh_beats_arm: bool | None` per arm (arm daily Sharpe < B&H daily Sharpe, strict) — this is the pre-committed input `verdict_forward` will need; compute it once at IS and record it.
> - The pinned percentiles as numbers (`ci_quantiles: [1/240, 1 − 1/240]`, `alpha`, `n_trials: 6`) so the report is self-describing.
> 
> **4. State plainly what (g) still owes, so nobody reads `evaluate()` as complete.** `require_frozen` checks five evaluator files; trial #2's G1 checked the whole execution fingerprint. Until (g) lands: the fingerprint set (strategies/trial03/*, p1_t3, prepare_t3, t3_outputs, evaluate_t3, verdict_t3, engine_replay, placebo_exec, p1_core, paper/, sizing/, exchange/, pyproject, uv.lock), data pins, verify receipt, pinned loaders for bars/kline daily, and `record.json` carrying prepared-input hashes are absent. Put that list in item 58 as "(g)가 채운다" and in the report's carried-forward section.
> 
> **5. Two things Codex may raise — have the answer ready:**
> - `write_p1_merged(draws_total=…)` is a writer-side override. It's harmless because the evaluator re-merges with its own `draws_total` and refuses on mismatch — say that, and add the assertion that the (g) CLI never passes it (extend the repo-wide static scan to the keyword).
> - `evaluate_with_fixture` exists for the run-once tests. It shares `_evaluate` with production, so the one-shot and commit logic is the code under test, not a copy. Say that too.
> 
> **6. Report shape.** Lead with the anchored-wording flags quoted (line 87 string, no INCONCLUSIVE — §7-2's three classes, ACCEPT only at forward via line 143's exact suffix, "IS PASS · 생존 통과"). Then: every §7 IS row and §7-2 class is reached in tests for both arms with the other arm at 0 trades and at a defined SR̂; OOS/forward rows including ACCEPT ± suffix. Then item 1 as the one thing they don't know. Then the ledger identities in one paragraph: what is checked at 34 digits, what is re-derived at 28, and that a one-digit perturbation refuses. Then the section G diff (`git diff 6950070 HEAD -- docs/trials/trial_03_conventions.md`), and that the row is still not appended — it lands with the final SHA in (g) before the evaluator push.
> 
> **Sequence:** Codex lands → log both verbatim with positions → items 1–3 (+ any Codex fixes) → full suite → commit → push → memory (`(f) done, waiting before (g); conventions 51–62 pending user review`) → report → stop before (g). No shared-code change is expected from these fixes; confirm with the usual diff before the report.

### Codex 원문(verbatim · task-munc0vr0-0wztfu)
> 1. **BLOCKER — the evaluator freeze does not cover code that changes the verdict.** [evaluate_t3.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t3.py:43) checks only five files, while its calculations also depend on `anchor.py`, `returns.py`, `p1_t3.py`, `harness.py`, and their imports. A clean, pushed change to an anchor threshold or return calculation after the evaluator commit would pass [require_frozen](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t3.py:311). **Fix:** pin and compare a manifest of every decision-dependent code file against the committed evaluator version; add a test that changes `anchor.py` in a later pushed commit and expects refusal. This closes a code-freeze gap in plan r3/item 58, separate from the data pins assigned to (g).
> 
> 2. **BLOCKER — trade timestamps are not tied to their execution events.** [ledger_check](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t3.py:101) pairs records by list position but never checks `trade.entry_ms == filled.fill_open` or `trade.exit_ms == exit.ts_ms`. Moving an entry to another valid V day passes the current [V membership check](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t3.py:233) and changes the day-block bootstrap and daily Sharpe without changing a fill or wallet. **Fix:** verify those timestamps, entry mark/reference, leverage, exit reason, and sequential trade IDs against the paired events before computing statistics. Test a move between two valid V days, as well as a move outside V.
> 
> 3. **MAJOR — committed output-contract fields are accepted without verification.** The evaluator checks `tf_v1_sha256` but never checks each run’s `rules_sha256` against the anchored snapshot; it also ignores `p1_summary.parts`, including every recorded part SHA256 ([evaluate_t3.py](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t3.py:228), [t3_outputs.py](/home/cms/project/BTC_Futures_E2E/backtest/t3_outputs.py:117)). The readers check top-level keys, not nested value schemas. **Fix:** validate the anchored rules hashes, compare the P1 part manifest and hashes with the files read, and validate nested types and ranges. Add one tamper test for each.
> 
> 4. **MINOR — the report omits exit-reason proportions required by r3 §7-3.** [trade_report](/home/cms/project/BTC_Futures_E2E/backtest/evaluate_t3.py:199) reports counts only. **Fix:** report each reason’s count and fraction of filled trades, with a defined zero-trade representation.
> 
> The per-arm §7 priority, shared G-B SR*, P1 comparison, V recomputation, and precision split otherwise match plan r3 and conventions 51–62. Conventions 58 and 57 currently overstate the freeze and input validation; update them with the fixes. I could not run the two test files: `pytest` is unavailable, and `uv` could not create its cache lock in this read-only sandbox.
> 
> **VERDICT: FIX-FIRST.**
> 
> Codex session ID: 01a0ef96-4a43-79f2-b2d3-4d3c35a26424
> Resume in Codex: codex resume 01a0ef96-4a43-79f2-b2d3-4d3c35a26424
