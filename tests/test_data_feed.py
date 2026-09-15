"""layer 5 피드 — ccxt.pro가 전송하고, **원시 메시지**를 우리가 해석한다(레지스트리 #8).

- ccxt `watch_ohlcv`는 `[t,o,h,l,c,v]` float만 남기고 `E`(이벤트 시각)·`x`(봉 마감)를 버린다(4.5.78 소스 확인).
  레지스트리 #1의 `kline1m_update`(모든 push의 E)·`kline1m_close`(x=true의 E)를 세려면 원시 메시지가 필요하다 →
  `TeeBinanceUsdm`이 `handle_ohlcv`·`handle_mark_prices`·`handle_liquidation`에서 원시 메시지를 먼저 넘기고 `super()`를 부른다.
- `DeliveryCounter.observe`는 **이벤트 시각 E**로 센다(수신 시각 아님) · 해석 실패 메시지는 세지 않는다(0이 보이게).
- 가격·수량은 원시 문자열 → Decimal(ccxt float 사용 금지).
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import aiohttp
import ccxt
import pytest
from ccxt.async_support.base.ws.client import Client

from data.feed import (
    FeedFailure,
    FeedMessageError,
    KlineEvent,
    LiquidationEvent,
    MarketFeed,
    TeeBinanceUsdm,
    parse_force_order,
    parse_kline,
    parse_mark_price,
)
from ops.delivery_counter import DeliveryCounter
from paper.types import MarkTick
from tests.conftest import load_snapshot

D = Decimal
E0 = 1_789_430_400_123


def kline_msg(E: int, *, closed: bool, t: int = 1_789_430_400_000, i: str = "1m", s: str = "BTCUSDT", c: str = "60010.5"):
    return {"e": "kline", "E": E, "s": s, "k": {"t": t, "T": t + 59_999, "s": s, "i": i, "f": 1, "L": 9,
                                              "o": "60000.1", "c": c, "h": "60020.0", "l": "59990.2", "v": "12.345",
                                              "n": 77, "x": closed, "q": "740000.5", "V": "6.1", "Q": "366000.2", "B": "0"}}


def mark_msg(E: int, *, p: str = "60001.2", r: str = "0.00010000", T: int = 1_789_459_200_000, s: str = "BTCUSDT"):
    return {"e": "markPriceUpdate", "E": E, "s": s, "p": p, "ap": "60000.9", "P": "60002.0", "i": "60003.4",
            "r": r, "T": T}


def force_msg(E: int):
    return {"e": "forceOrder", "E": E, "o": {"s": "BTCUSDT", "S": "SELL", "o": "LIMIT", "f": "IOC", "q": "0.500",
                                             "p": "59000.0", "ap": "59010.5", "X": "FILLED", "l": "0.500", "z": "0.500",
                                             "T": E - 2}}


# ── 순수 해석 ────────────────────────────────────────────────────────────────
def test_parse_kline_keeps_event_time_close_flag_and_decimals():
    k = parse_kline(kline_msg(E0, closed=True), symbol_id="BTCUSDT")
    assert isinstance(k, KlineEvent)
    assert k.event_ms == E0 and k.closed is True and k.open_ms == 1_789_430_400_000 and k.close_ms == 1_789_430_459_999
    assert (k.open, k.high, k.low, k.close) == (D("60000.1"), D("60020.0"), D("59990.2"), D("60010.5"))
    assert k.volume == D("12.345") and k.quote_volume == D("740000.5") and k.trades == 77
    assert k.taker_buy_base == D("6.1") and k.taker_buy_quote == D("366000.2")
    assert all(isinstance(x, Decimal) for x in (k.open, k.volume))


@pytest.mark.parametrize("msg", [
    kline_msg(E0, closed=False, i="5m"), kline_msg(E0, closed=False, s="ETHUSDT"),
    {"e": "markPrice_kline", "E": E0, "k": {}}, {"e": "kline", "E": "x", "k": {}}, {"e": "kline", "E": E0},
    kline_msg(E0, closed=False, c="abc"), {**kline_msg(E0, closed=False), "k": {**kline_msg(E0, closed=False)["k"], "x": "false"}},
])
def test_parse_kline_rejects_wrong_or_malformed_messages(msg):
    with pytest.raises(FeedMessageError):
        parse_kline(msg, symbol_id="BTCUSDT")


def test_parse_mark_price_builds_the_engine_tick():
    t = parse_mark_price(mark_msg(E0), symbol_id="BTCUSDT")
    assert t == MarkTick(ts_ms=E0, mark=D("60001.2"), funding_rate=D("0.00010000"), next_funding_ms=1_789_459_200_000)


@pytest.mark.parametrize("msg", [mark_msg(E0, s="ETHUSDT"), {k: v for k, v in mark_msg(E0).items() if k != "r"},
                                 mark_msg(E0, p="nan?"), {"e": "24hrMiniTicker", "E": E0, "s": "BTCUSDT"}])
def test_parse_mark_price_rejects_wrong_or_malformed(msg):
    with pytest.raises(FeedMessageError):
        parse_mark_price(msg, symbol_id="BTCUSDT")


def test_parse_force_order():
    liq = parse_force_order(force_msg(E0), symbol_id="BTCUSDT")
    assert isinstance(liq, LiquidationEvent)
    assert liq.event_ms == E0 and liq.side == "SELL" and liq.qty == D("0.500") and liq.avg_price == D("59010.5")


# ── ccxt.pro 위에서 end-to-end (네트워크 없음) ─────────────────────────────────
class PushSocket:
    closed = False
    _conn = None

    def __init__(self, url: str):
        self.url = url
        self.sent: list[dict] = []
        self.inbox: asyncio.Queue = asyncio.Queue()

    async def send_str(self, s: str) -> None:
        self.sent.append(json.loads(s))

    async def receive(self):
        return await self.inbox.get()

    def push(self, obj: Any) -> None:
        self.inbox.put_nowait(aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, json.dumps(obj), None))

    async def close(self) -> None:
        self.closed = True

    async def ping(self, *a: Any) -> None:
        return None

    async def pong(self, *a: Any) -> None:
        return None


@pytest.fixture
def sockets(monkeypatch):
    opened: list[PushSocket] = []

    async def fake_create(self, session):
        s = PushSocket(self.url)
        opened.append(s)
        return s
    monkeypatch.setattr(Client, "create_connection", fake_create)
    return opened


def tee_factory(config, sink):
    ex = TeeBinanceUsdm(config, sink=sink)
    info = load_snapshot("exchangeInfo")["response"]
    ex.set_markets(ex.parse_markets([s for s in info["symbols"] if s["symbol"] == "BTCUSDT"]))
    return ex


async def _wait(cond, timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("조건 대기 시간 초과")


def socket_for(opened: list[PushSocket], stream: str) -> PushSocket:
    hits = [s for s in opened if any(stream in p for f in s.sent for p in f.get("params", []))]
    assert len(hits) == 1, [s.sent for s in opened]
    return hits[0]


def test_feed_counts_delivery_by_event_time_and_hands_decimal_events_to_callbacks(sockets):
    klines: list[KlineEvent] = []
    marks: list[MarkTick] = []
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=E0 - 1000)
    feed = MarketFeed(symbol_id="BTCUSDT", counter=counter, on_kline=klines.append, on_mark=marks.append,
                      exchange_factory=tee_factory)

    async def run():
        stop = asyncio.Event()
        task = asyncio.ensure_future(feed.run(stop))
        await _wait(lambda: len(sockets) == 2 and all(s.sent for s in sockets))
        k, m = socket_for(sockets, "@kline_1m"), socket_for(sockets, "@markPrice@1s")
        k.push(kline_msg(E0, closed=False))
        k.push(kline_msg(E0 + 250, closed=False))
        k.push(kline_msg(E0 + 59_876, closed=True))
        m.push(mark_msg(E0 + 1000))
        m.push(mark_msg(E0 + 2000, p="60005.0"))
        await _wait(lambda: len(klines) == 3 and len(marks) == 2)
        ex = feed.exchange
        assert ex is not None and ex.ohlcvs["BTC/USDT:USDT"]["1m"], "super().handle_ohlcv도 돌았다(ccxt 캐시)"
        stop.set()
        await asyncio.wait_for(task, 5)
    asyncio.run(run())

    assert [k.closed for k in klines] == [False, False, True]
    assert marks[1].mark == D("60005.0") and marks[0].ts_ms == E0 + 1000
    snap = counter.snapshot(E0 + 60_000)
    assert counter._b["kline1m_update"].count + counter._b["kline1m_update"].prev_count == 3
    assert counter._b["kline1m_close"].count + counter._b["kline1m_close"].prev_count == 1
    assert counter._b["markprice"].last_seen_ms == E0 + 2000, "수신 시각이 아니라 이벤트 시각"
    assert snap["markprice"]["last_seen_age_sec"] == 58.0
    assert feed.errors == []


def test_malformed_message_is_recorded_not_counted_and_the_feed_keeps_going(sockets):
    marks: list[MarkTick] = []
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=E0 - 1000)
    feed = MarketFeed(symbol_id="BTCUSDT", counter=counter, on_kline=lambda k: None, on_mark=marks.append,
                      exchange_factory=tee_factory)

    async def run():
        stop = asyncio.Event()
        task = asyncio.ensure_future(feed.run(stop))
        await _wait(lambda: len(sockets) == 2 and all(s.sent for s in sockets))
        m = socket_for(sockets, "@markPrice@1s")
        m.push(mark_msg(E0, p="not-a-number"))
        m.push(mark_msg(E0 + 1000))
        await _wait(lambda: len(marks) == 1)
        stop.set()
        await asyncio.wait_for(task, 5)
    asyncio.run(run())
    assert len(feed.errors) == 1 and isinstance(feed.errors[0], FeedMessageError)
    assert counter._b["markprice"].last_seen_ms == E0 + 1000 and counter._b["markprice"].count == 1


def test_callback_failure_stops_the_feed_loudly(sockets):
    def boom(t):
        raise RuntimeError("engine rejected tick")
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=E0 - 1000)
    feed = MarketFeed(symbol_id="BTCUSDT", counter=counter, on_kline=lambda k: None, on_mark=boom,
                      exchange_factory=tee_factory)

    async def run():
        stop = asyncio.Event()
        task = asyncio.ensure_future(feed.run(stop))
        await _wait(lambda: len(sockets) == 2 and all(s.sent for s in sockets))
        socket_for(sockets, "@markPrice@1s").push(mark_msg(E0))
        with pytest.raises(FeedFailure):
            await asyncio.wait_for(task, 5)
    asyncio.run(run())


def test_watch_errors_reconnect_with_backoff_and_are_recorded(monkeypatch):
    attempts = {"n": 0}
    sleeps: list[float] = []

    class Flaky(TeeBinanceUsdm):
        async def watch_mark_price(self, symbol, params={}):  # type: ignore[override]  # noqa: B006
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise ccxt.NetworkError("socket closed")
            await asyncio.sleep(3600)

        async def watch_ohlcv(self, symbol, timeframe="1m", since=None, limit=None, params={}):  # type: ignore[override]  # noqa: B006
            await asyncio.sleep(3600)

    def factory(config, sink):
        ex = Flaky(config, sink=sink)
        info = load_snapshot("exchangeInfo")["response"]
        ex.set_markets(ex.parse_markets([s for s in info["symbols"] if s["symbol"] == "BTCUSDT"]))
        return ex

    async def fake_sleep(s):
        sleeps.append(s)
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=E0)
    feed = MarketFeed(symbol_id="BTCUSDT", counter=counter, on_kline=lambda k: None, on_mark=lambda t: None,
                      exchange_factory=factory, sleep=fake_sleep, backoff_s=(1.0, 2.0, 4.0))

    async def run():
        stop = asyncio.Event()
        task = asyncio.ensure_future(feed.run(stop))
        await _wait(lambda: attempts["n"] >= 3)
        stop.set()
        await asyncio.wait_for(task, 5)
    asyncio.run(run())
    assert sleeps[:2] == [1.0, 2.0]
    assert [r["stream"] for r in feed.reconnects] == ["markprice", "markprice"]


def test_feed_stall_is_visible_through_the_counter_when_one_stream_goes_silent():
    """E2E #132 형태: kline은 흐르는데 markPrice만 0 — 스트림별 판정이라 보인다."""
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=E0)
    feed = MarketFeed(symbol_id="BTCUSDT", counter=counter, on_kline=lambda k: None, on_mark=lambda t: None)
    for i in range(0, 200_000, 250):
        feed.sink("kline", kline_msg(E0 + i, closed=(i % 60_000 == 59_750)))
    assert "markprice" in counter.stalled(E0 + 200_000) and "kline1m_update" not in counter.stalled(E0 + 200_000)
