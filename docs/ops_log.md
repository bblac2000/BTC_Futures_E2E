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

