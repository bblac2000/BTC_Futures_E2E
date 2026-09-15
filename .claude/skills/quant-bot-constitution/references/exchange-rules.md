# 영역 A — 바이낸스 USDⓈ-M 게임룰 체크리스트

정본: 저장소 `docs/바이낸스문서API_2026_v6.md`(v6, 2026-06-19 전수 실측). 이 파일은 v6를 대체하지 않는다 — "코드 리뷰·설계 시 v6의 어느 §를 열고 무엇을 확인하는가"의 지도다. 값에 `[LIVE-ONLY]`가 붙은 것은 런타임 조회가 진리원이고 아래 숫자는 드리프트 기준선일 뿐이다.

## 목차
1. 우선순위와 위상 (v6 §0)
2. 주문 매트릭스 (v6 CRITICAL 블록, §7)
3. 정규화 순서 (v6 §2)
4. 기동 게이트 (v6 §0.4, §3, §12.3)
5. 사이징·청산·마진 (v6 §3, §4)
6. 비용·펀딩 (v6 §5, §6, §0.6)
7. 심볼별 실측표 (v6 §1.0)
8. 비-가격 데이터·청산 스트림 (v6 §10 부록)
8-1. 웹소켓 엔드포인트 티어 (2026-04-23 이후 필수)
9. 코드 리뷰 체크리스트
10. v6 정정 대기 항목

---

## 1. 우선순위와 위상
- v6 §0이 본문 §1~§18보다 우선한다. §0과 충돌하는 본문 서술은 폐기다.
- 문서 = 검증된 참조 + 드리프트 감지 기준선. 봇 파라미터는 기동·주기 조회 또는 `snapshots/*.json` 로드. **숫자 리터럴 = 헌법 위반.**
- 값 신뢰도 범례: `[DOC]` 구조·규칙·의미 / `[LIVE-ONLY]` 런타임 조회 필수 / `[DERIVED]` 파생식.
- 순간값(markPrice·indexPrice·lastFundingRate·interestRate·nextFundingTime)은 시세이지 기준선이 아니다. 드리프트 하네스 비교에서 제외(B1).

## 2. 주문 매트릭스 (원웨이 · 격리 · MARKET 전용)

| 목적 | side | positionSide | reduceOnly |
|---|---|---|---|
| LONG 진입 | `BUY` | `BOTH`(생략 가능) | 없음 |
| LONG 청산 | `SELL` | `BOTH` | `"true"` 필수 |
| SHORT 진입 | `SELL` | `BOTH` | 없음 |
| SHORT 청산 | `BUY` | `BOTH` | `"true"` 필수 |

- `side`에 `LONG`/`SHORT`를 넣으면 주문 거부 또는 **반대 방향 체결** → 마진콜. 내부 direction 변수를 API에 그대로 전달하는 코드는 즉시 반려.
- 전량 청산은 `positionAmt` 부호로 side를 정한다: `>0 → SELL`, `<0 → BUY`, `quantity=abs(positionAmt)`.
- Hedge 모드는 쓰지 않는다. 계정 실측 `dualSidePosition=False`(원웨이). 참고로 Hedge에서 `BUY+positionSide=SHORT`는 유효한 SHORT 청산이다(구 문서 "불가" 표기는 오류).
- 서버측 STOP/STOP_MARKET/TAKE_PROFIT/TRAILING은 2025-12-09 `/fapi/v1/algoOrder`로 이관, 구 엔드포인트 `-4120` 거부. 이 봇은 어차피 쓰지 않는다 — SL/TP는 봇 모니터링 후 MARKET reduceOnly.
- `stopPrice/closePosition/workingType/priceProtect/callbackRate`는 `/fapi/v1/order` 요청에서 제거됨(C2).

## 3. 정규화 순서 (틀리면 "전략 OK인데 주문 거부")
1. 수량 = stepSize로 **내림(floor)**. 올림 금지(-1111/-1013). 자릿수 = `quantityPrecision`.
2. **내림 후** `qty × price ≥ MIN_NOTIONAL` 재확인. 내림이 명목을 하한 아래로 밀 수 있다(XRP step 0.1·MIN_NOTIONAL 5·가격 0.5 → 9.x→9.0이면 명목 4.5 → `-4164`). 미달이면 한 step 올리거나(여유 자본 시) 포기. 추격 금지. 신규 진입만 해당 — reduceOnly/closePosition 청산은 MIN_NOTIONAL 면제(잔여 청산이 막히지 않는다).
3. 가격 = tickSize 배수, `Decimal(str(price)).quantize(tick, ROUND_HALF_UP)`. float 나눗셈(`price/tick`)은 99999.95→99999.9 같은 오계산을 만든다.
4. MARKET 1주문 상한은 LOT_SIZE가 아니라 **MARKET_LOT_SIZE.maxQty**(BTC 120·ETH 2,000·XRP 2,000,000 `[LIVE-ONLY]`). 초과 시 분할.
5. LIMIT을 쓴다면 PERCENT_PRICE(mark ±5%)·triggerProtect(±5%) 안으로 클리핑. 이 봇은 MARKET 전용이라 해당 없음.
6. 모든 값은 심볼별 런타임 조회값.

```python
def size_ok(qty, price, step, min_notional):
    q = math.floor(qty / step) * step
    return q, (q * price >= min_notional)
```

에러코드(-4164/-1111/-1013/-1015/-4120)는 대표값이다. 거부 시 응답의 실제 `code`/`msg`를 로깅해 대조한다.

## 4. 기동 게이트
`_setup()`은 LIVE에서 반드시:
1. `GET /fapi/v2/positionRisk` → `marginType` 확인.
2. `ISOLATED`가 아니면 포지션·미체결 0 확인 후 `POST /fapi/v1/marginType {marginType:"ISOLATED"}`.
3. 재조회로 `isolated=true` 확정. **실패 시 기동 중단**(진입 금지, 청산만 허용).
4. `POST /fapi/v1/leverage`로 config 레버리지 명시 설정. 미설정 시 계정 기본 **5x·cross**로 매매된다(2026-06-19 실측).
5. `dualSidePosition` 확인, true면 false로.

PAPER는 계정 SET 금지(읽기만), WARNING 로그 후 기동 계속. 격리 전환 전 첫 드리프트 하네스가 마진에서 BREAKING을 내는 것은 정상.

## 5. 사이징·청산·마진
- `IM = 명목/레버리지`, `MM = 명목×MMR − cumB`. MMR·cumB는 `/fapi/v1/leverageBracket` 런타임 조회. `positionRisk.maxNotionalValue`(예 480,000,000)는 현재 레버리지 기준 한도이지 브라켓 `notionalCap`이 아니다(B3) — 절대 섞지 않는다.
- 격리·원웨이 청산가 근사: LONG `Entry×(1−1/L+MMR)`, SHORT `Entry×(1+1/L−MMR)`. 실제 트리거는 **Mark Price**가 `liquidationPrice`에 도달할 때. 봇은 `positionRisk.liquidationPrice`를 쓴다.
- liquidationFee는 청산가 유효 MMR에 가산. 심볼별(SOL 1.5%, 그 외 1.25% `[LIVE-ONLY]`).
- 파산가 LONG `Entry×(1−1/L)`, SHORT `Entry×(1+1/L)`. 청산~파산 사이 잔여 마진은 보험기금으로.
- 브라켓 `[LIVE-ONLY]`(2026-06-14~19 실측): BTC·ETH 최대 150x·12단·tier1 0~300k/0.40%, XRP 100x·11단·tier1 0~40k/0.50%, SOL 100x·10단, BNB 75x·10단. 봇은 3~7x 사용(v6 §3 서술). 사이징은 SL 거리에서 레버리지를 도출한다(sizing v2, learnings 참조).

## 6. 비용·펀딩
- VIP0 maker 0.0200% / taker 0.0500%(BNB 납부 시 taker 0.045%). 3~5심볼 동일, 봇 config 일치. 라이브는 실체결 수수료 사용.
- 50~1,000 USDT 규모 실측(E2E Phase 1-A, 2026-08 레짐): 왕복 슬리피지 0.016 bps, 왕복비용 가정 10.02 bps. 계절 꼬리표 필수, 재보정 대상.
- 펀딩 8h(00/08/16 UTC), 5심볼 동일. cap/floor BTC·ETH ±0.30%, XRP·SOL·BNB ±0.375% `[LIVE-ONLY]`. 2025-05-02 이후 cap/floor 도달 시 1h 주기 자동 전환, 2025-09-18 이후 비율을 `(8/N)`으로 정규화. `fundingInfo`에 심볼이 없으면 거래소 기본 → 런타임 확정, 추정 금지.
- BTCUSDT 펀딩 중앙값 ~0.005~0.006%/8h(2024~2026) — 펀딩 단독은 비용 미달, 군중 포지셔닝 정보로만.
- 청산 수수료 = 명목 × liquidationFee.

## 7. 심볼별 실측표 (2026-06-19, 전부 `[LIVE-ONLY]`)

| 필드 | ETHUSDT | XRPUSDT | BTCUSDT | SOLUSDT | BNBUSDT |
|---|---|---|---|---|---|
| 최대 레버 | 150x | 100x | 150x | 100x | 75x |
| MIN_NOTIONAL | 20 | 5 | 50 | 5 | 5 |
| tickSize | 0.01 | 0.0001 | 0.10 | 0.01 | 0.01 |
| stepSize/minQty | 0.001 | 0.1 | 0.001 | 0.01 | 0.01 |
| MARKET maxQty | 2,000 | 2,000,000 | 120 | 80,000 | 2,000 |
| liquidationFee | 1.25% | 1.25% | 1.25% | **1.5%** | 1.25% |
| 펀딩 cap | ±0.30% | ±0.375% | ±0.30% | ±0.375% | ±0.375% |

전역: rate limit REQUEST_WEIGHT 2400/분·ORDERS 1200/분·300/10초(폴링·주문 빈도 가드). MAX_NUM_ORDERS 200. marketTakeBound 5%. POSITION_RISK_CONTROL NONE. 24/7. 미표기 심볼(xsect 유니버스 등)은 매매 전 exchangeInfo/leverageBracket/fundingInfo 조회 필수.

## 8. 비-가격 데이터·청산 스트림
| 데이터 | 경로 | 제약 |
|---|---|---|
| OI | `GET /fapi/v1/openInterest` / `/futures/data/openInterestHist` | 이력 최근 30일만 |
| 롱숏 비율(상위·전체·taker) | `/futures/data/*LongShort*` | 30일 |
| 청산 | WS `<symbol>@forceOrder`, `!forceOrder@arr` | **1초 창 심볼당 가장 큰(largest) 1건 스냅샷** — 총량 아님 |
| 과거 L2·청산 | Binance 미제공 → Tardis.dev(월 1일 무료) | binance.vision에 USDⓈ-M 청산 아카이브 없음, `allForceOrders` 유지중단 |

forceOrder `side`: SELL=롱 청산, BUY=숏 청산. 저장 시 "snapshot, max 1/sec/symbol, largest per window — not a volume series" 꼬리표를 manifest에 함께 둔다. 페이로드에 `ps`(pair)·`st`가 추가로 온다. Tardis 청산 데이터도 초당 1~2건 천장이 있으므로 Tardis 대조는 "수집 충실도"이지 "진짜 미달"이 아니다.

## 8-1. 웹소켓 엔드포인트 티어 (2026-04-23 이후 필수 — 2026-09-12 도쿄 VPS 실측)

바이낸스는 2026-03-06 공지로 USDⓈ-M 웹소켓을 세 갈래로 분리했고 레거시 URL(`wss://fstream.binance.com/ws`, `/stream?streams=`)은 **2026-04-23 폐기**. 폐기 후 레거시 연결은 `/public` 티어만 전달하고 다른 티어 채널은 **구독을 정상 수락(`{"result":null}`)한 뒤 조용히 0건**이다. 에러도 경고도 없다.

| 티어 | 엔드포인트 | 스트림 (실측 확정 ✔ / 공지 기준) |
|---|---|---|
| public | `wss://fstream.binance.com/public/ws` (`/public/stream?streams=`) | `@trade` ✔ · `@bookTicker` ✔ · `@depth*` ✔ · `!bookTicker` |
| market | `wss://fstream.binance.com/market/ws` (`/market/stream?streams=`) | `@aggTrade` ✔ · `@markPrice`(기본 3s, `@1s` 옵션) ✔ · `@forceOrder` ✔ · `!forceOrder@arr` ✔ · `@kline_*` · `@continuousKline_*` · `@ticker` · `@miniTicker` · `@compositeIndex` · `!contractInfo` · `@assetIndex` |
| private | `wss://fstream.binance.com/private/ws` | listenKey 유저 데이터(주문·포지션 업데이트) |

규칙:
- **소켓은 한 티어에 묶인다.** 한 연결에 티어를 섞어 구독하면 한쪽은 조용히 0건. 티어별로 연결을 나누고, 구독 시 스트림명→티어 매핑을 검사하는 테스트를 둔다.
- **0건을 보고할 때 대조군은 같은 소켓이 아니라 같은 티어여야 한다.** `@trade`가 오는 것은 `@forceOrder`에 대해 아무것도 증명하지 않는다. 관측 길이는 사건 빈도로 정당화한다(BTC 단일 청산 ~58초당 1건 → 전 시장 `!forceOrder@arr` 300초 이상).
- 기능 플래그가 "준비됨"으로 문서화돼 있어도 마지막 업스트림 변경 이후 실제 전달을 확인하지 않았으면 준비된 게 아니다(E2E_COLLECT_DERIVS 사례 — 레거시 URL에 market 티어 3종을 얹어 켜도 아무것도 안 모음).
- REST 폴백이 웹소켓 장애를 가릴 수 있다(E2E markPrice REST 1s는 라우팅 변경 3개월 뒤에 만들어져 원인을 덮고 있었다). 폴백을 넣을 때는 원인 항목을 레지스트리에 남긴다.
- 봇·수집기 기동 시 각 소켓의 티어별 첫 프레임 도착을 로그하고, 특정 스트림이 T초 이상 0건이면 stale-data 경보(§strategy-modules §6).
- 출처: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Important-WebSocket-Change-Notice

## 9. 코드 리뷰 체크리스트 (반려 사유가 되는 것)
- [ ] `side`에 direction 변수를 그대로 넘기는가
- [ ] 청산 주문에 `reduceOnly="true"`가 빠졌는가
- [ ] tick/step/MIN_NOTIONAL/MMR/수수료/펀딩 cap이 리터럴인가
- [ ] 내림 후 MIN_NOTIONAL 재확인이 없는가
- [ ] 가격 정규화에 float 나눗셈을 쓰는가
- [ ] BTC 값을 ETH/XRP에 차용하는가
- [ ] `maxNotionalValue`를 브라켓 cap으로 쓰는가
- [ ] LIVE `_setup()`에 격리 확정·레버리지 설정·실패 시 중단이 없는가
- [ ] PAPER에서 계정 SET을 호출하는가
- [ ] markPrice류 순간값을 드리프트 기준선 표에 넣는가
- [ ] 청산 스트림을 총량 지표로 쓰는가
- [ ] 웹소켓 URL이 레거시(`/ws`, `/stream`)인가, 한 소켓에 티어가 섞였는가, 스트림별 전달 확인 로그가 있는가
- [ ] 실주문 금지 저장소(E2E)에서 주문·서명·거래 SDK import가 나타나는가(`ops/scan_order_path.py`)

## 10. v6 정정 이력·대기 항목
- ✅ §10 forceOrder 행 "최신 1건" → "가장 큰(largest) 1건" 정정 삽입(E2E f89af0d, 2026-09-12, change log 2026-04-10 항목 근거).
- 대기: §10 forceOrder 행에 `/market/ws` 필수·2026-04-23 폐기일·`ps`/`st` 필드 추가. §10 웹소켓 절(`wss://fstream.binance.com/ws/<stream>` 예시)에 티어 표(§8-1) 반영 — 원문 유지·추가 방식.
- §1 BTC 표의 `MAX_LEVERAGE = 125` 등 §12.1 RL 상수 블록은 v5 갱신(150x) 전 값이 남아 있음 — 어차피 리터럴 금지라 봇 영향 없으나 문서 내 불일치로 표기.
