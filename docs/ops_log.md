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
