"""layer 5 설정 — 문서로 확인한 REST 한도와 우리가 고른 운영 값.

## klines 페이지 크기 (공식 레퍼런스를 **렌더링**해 확인 · 2026-09-15 · ops_log)
`https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#kline-candlestick-data`
`GET /fapi/v1/klines`·`GET /fapi/v1/markPriceKlines` — `limit` integer · int64 · **max: 1500** · Default: 500.
IP weight(LIMIT): [1,100) → 1 · [100,500) → 2 · [500,1000] → 5 · >1000 → 10.
→ 운영 값 1000 = 가중치 5인 최대 크기(1500은 가중치 10 · 봉당 비용 1.33배). 30일 1m = 44페이지 × 5 = 220 weight.
"""
from __future__ import annotations

KLINES_MAX_LIMIT = 1500
KLINES_PAGE_LIMIT = 1000
