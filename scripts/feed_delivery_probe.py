"""읽기 전용 전달 프로브 — ccxt.pro가 연 **실제** 소켓에서 스트림별 메시지가 오는지 센다(레지스트리 #8 · 구독 수락 ≠ 전달).

사용: uv run python scripts/feed_delivery_probe.py [초=150]
- 키 없음 · 공개 WS + 공개 REST(exchangeInfo)만 · 주문·계정 경로 없음
- 결과: 스트림별 건수 · 첫/마지막 이벤트 시각 · DeliveryCounter.stalled() · 연 URL(ccxt 클라이언트 목록)
ccxt 업그레이드마다 오프라인 티어 테스트와 함께 돌린다.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ccxt  # noqa: E402

from data.feed import MarketFeed  # noqa: E402
from ops.delivery_counter import DeliveryCounter  # noqa: E402


async def main(seconds: int) -> int:
    start = int(time.time() * 1000)
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=start)
    seen: dict[str, list[int]] = {"kline": [], "kline_closed": [], "markprice": [], "forceOrder": []}

    def on_kline(k):
        seen["kline"].append(k.event_ms)
        if k.closed:
            seen["kline_closed"].append(k.event_ms)
    feed = MarketFeed(symbol_id="BTCUSDT", counter=counter, on_kline=on_kline,
                      on_mark=lambda t: seen["markprice"].append(t.ts_ms),
                      on_liquidation=lambda e: seen["forceOrder"].append(e.event_ms))
    stop = asyncio.Event()
    task = asyncio.ensure_future(feed.run(stop))
    await asyncio.sleep(seconds)
    urls = sorted(feed.exchange.clients.keys()) if feed.exchange is not None else []
    stop.set()
    await task
    now = int(time.time() * 1000)
    print(json.dumps({
        "ccxt": ccxt.__version__, "seconds": seconds, "urls_opened": urls,
        "counts": {k: len(v) for k, v in seen.items()},
        "first_last_event_ms": {k: (v[0], v[-1]) if v else None for k, v in seen.items()},
        "stalled": counter.stalled(now), "parse_errors": [str(e) for e in feed.errors],
        "reconnects": feed.reconnects,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)))
