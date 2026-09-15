"""layer 5 실시간 피드 — ccxt.pro(`binanceusdm`)가 소켓·구독·재연결을 맡고, **원시 메시지는 우리가 해석**한다(레지스트리 #8).

## 왜 `watch_*`의 반환값을 쓰지 않나
ccxt 4.5.78 `handle_ohlcv`는 kline을 `[t, o, h, l, c, v]` **float**으로 줄이고 `E`(이벤트 시각)·`x`(봉 마감)를 버린다.
레지스트리 #1은 `kline1m_update` = 모든 push의 `E`, `kline1m_close` = `x=true`의 `E`를 센다 → 원시 메시지가 필요하다.
또 watch 퓨처는 합쳐진다 — 소비가 늦으면 **한 번뿐인 `x=true` push를 놓칠 수 있다.**
그래서 `TeeBinanceUsdm`이 핸들러에서 원시 메시지를 **먼저** 넘기고 `super()`를 부른다(ccxt 상태·퓨처는 그대로).
소켓 URL은 ccxt.pro가 만들고 `tests/test_ccxt_stream_tiers.py`가 이 하위 클래스로도 티어를 검증한다.

## 규칙
- 가격·수량은 원시 문자열 → `Decimal`. 모양이 틀린 메시지는 `FeedMessageError`로 기록하고 **세지 않는다**(0이 보이게).
- `DeliveryCounter.observe(kind, E)` — 수신 시각이 아니라 이벤트 시각(레지스트리 #1). 관측이 콜백보다 먼저다.
- 콜백(엔진) 예외는 삼키지 않는다 → `run()`이 `FeedFailure`로 끝난다. ccxt 수신 루프 안에서 예외가 새면
  수신 루프가 조용히 멈추므로, 여기서 잡아 저장하고 `run()`이 올린다.
- watch 오류는 백오프 후 재시도하고 `reconnects`에 남긴다. 멈춤 판정은 카운터가 한다(`safety/` 입력).
- 이 봇의 스트림은 `@kline_1m`·`@markPrice@1s`(둘 다 `/market` 티어). ccxt는 구독마다 소켓을 따로 연다 —
  **사용자 수락(2026-09-15)**: 스트림마다 `/market` 소켓 1개. 스트림별 감시라 한쪽 침묵이 다른 쪽에 가려지지 않는다.

## 소켓 수명 (사용자 결정 2 · E2E `RECONNECT_PROACTIVE_SEC` 이식)
- 소켓마다 connect / disconnect / reconnect를 `recorder.event`로 남긴다(대장 쓰기는 writer 스레드 — `data.shards`).
  훅은 ccxt `on_connected`·`on_error`·`on_close`. 훅·기록 실패는 세고 삼킨다(ccxt 수신 루프를 멈추지 않게).
- **23h 선제 재연결은 소켓마다**: 연결 시각(`client.connectionEstablished`)이 23h를 넘은 소켓만 `client.on_error(ProactiveRefresh)`
  → 그 watch가 오류로 끝나고 백오프 없이 다시 watch → ccxt가 새 소켓·SUBSCRIBE. 비용 = 23h마다 소켓 수만큼 재연결.
- 기록: 해석에 성공한 메시지만 `recorder.put(kind, row)`(kline1m_update 전부 · kline1m_close x=true · markprice).
- watch 루프 태스크가 stop 전에 끝나면(취소 포함) `FeedFailure` — 스트림 하나가 조용히 죽지 않게.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import ccxt
import ccxt.pro as ccxtpro

from data.shards import kline_row, markprice_row
from ops.delivery_counter import DeliveryCounter
from paper.types import MarkTick

UNIFIED_SYMBOL = {"BTCUSDT": "BTC/USDT:USDT"}
INTERVAL = "1m"
RECONNECT_PROACTIVE_SEC = 23 * 3600      # Binance 24h 연결 상한 선제 대응(E2E l2_collector 동일 값)
REFRESH_CHECK_SEC = 30.0


class ProactiveRefresh(ccxt.NetworkError):
    """23h 선제 재연결 — 이 소켓의 watch만 끝내고 즉시 다시 연결시킨다."""


class FeedMessageError(ValueError):
    """원시 메시지 모양·값이 기대와 다르다 — 세지 않고 기록한다."""


class FeedFailure(RuntimeError):
    """콜백이 실패했다 — 피드를 멈춘다(조용히 계속하지 않는다)."""


@dataclass(frozen=True)
class KlineEvent:
    event_ms: int
    open_ms: int
    close_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int
    taker_buy_base: Decimal
    taker_buy_quote: Decimal
    closed: bool


@dataclass(frozen=True)
class LiquidationEvent:
    event_ms: int
    trade_ms: int
    side: str
    qty: Decimal
    price: Decimal
    avg_price: Decimal
    status: str


def _dec(d: dict, key: str) -> Decimal:
    try:
        v = Decimal(str(d[key]))
    except (KeyError, InvalidOperation, TypeError) as e:
        raise FeedMessageError(f"{key}: {d.get(key)!r}") from e
    if not v.is_finite():
        raise FeedMessageError(f"{key}: 유한수가 아니다 {v}")
    return v


def _int(d: dict, key: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise FeedMessageError(f"{key}: 정수가 아니다 {v!r}")
    return v


def parse_kline(msg: Any, *, symbol_id: str) -> KlineEvent:
    if not isinstance(msg, dict) or msg.get("e") != "kline" or not isinstance(msg.get("k"), dict):
        raise FeedMessageError(f"kline 메시지가 아니다: {msg!r}")
    k = msg["k"]
    if msg.get("s") != symbol_id or k.get("s") != symbol_id or k.get("i") != INTERVAL:
        raise FeedMessageError(f"심볼·간격 불일치: s={msg.get('s')} k.s={k.get('s')} i={k.get('i')}")
    if not isinstance(k.get("x"), bool):
        raise FeedMessageError(f"x가 bool이 아니다: {k.get('x')!r}")
    return KlineEvent(event_ms=_int(msg, "E"), open_ms=_int(k, "t"), close_ms=_int(k, "T"), open=_dec(k, "o"),
                      high=_dec(k, "h"), low=_dec(k, "l"), close=_dec(k, "c"), volume=_dec(k, "v"),
                      quote_volume=_dec(k, "q"), trades=_int(k, "n"), taker_buy_base=_dec(k, "V"),
                      taker_buy_quote=_dec(k, "Q"), closed=k["x"])


def parse_mark_price(msg: Any, *, symbol_id: str) -> MarkTick:
    if not isinstance(msg, dict) or msg.get("e") != "markPriceUpdate" or msg.get("s") != symbol_id:
        raise FeedMessageError(f"{symbol_id} markPriceUpdate가 아니다: {msg!r}")
    mark = _dec(msg, "p")
    if mark <= 0:
        raise FeedMessageError(f"mark {mark} ≤ 0")
    return MarkTick(ts_ms=_int(msg, "E"), mark=mark, funding_rate=_dec(msg, "r"), next_funding_ms=_int(msg, "T"))


def parse_force_order(msg: Any, *, symbol_id: str) -> LiquidationEvent:
    if not isinstance(msg, dict) or msg.get("e") != "forceOrder" or not isinstance(msg.get("o"), dict):
        raise FeedMessageError(f"forceOrder가 아니다: {msg!r}")
    o = msg["o"]
    if o.get("s") != symbol_id:
        raise FeedMessageError(f"심볼 불일치 {o.get('s')}")
    return LiquidationEvent(event_ms=_int(msg, "E"), trade_ms=_int(o, "T"), side=str(o.get("S")), qty=_dec(o, "q"),
                            price=_dec(o, "p"), avg_price=_dec(o, "ap"), status=str(o.get("X")))


Sink = Callable[[str, Any], None]


SocketHook = Callable[[str, str], None]


class TeeBinanceUsdm(ccxtpro.binanceusdm):
    """원시 메시지를 먼저 `sink(kind, message)`로 넘기고 ccxt 핸들러를 그대로 돈다. 소켓 수명은 `socket_hook(kind, detail)`."""

    def __init__(self, config: Any = None, *, sink: Sink | None = None):
        super().__init__(config or {})
        self._tee_sink = sink
        self.socket_hook: SocketHook | None = None

    def _socket(self, kind: str, client: Any, why: str) -> None:
        if self.socket_hook is None:
            return
        subs = sorted(str(k) for k in (getattr(client, "subscriptions", None) or {}))
        self.socket_hook(kind, f"{getattr(client, 'url', '?')} subs={subs}" + (f" {why}" if why else ""))

    def on_connected(self, client, message=None):
        self._socket("connect", client, "")
        return super().on_connected(client, message)

    def on_error(self, client, error):
        self._socket("disconnect", client, f"error {type(error).__name__}: {error}")
        return super().on_error(client, error)

    def on_close(self, client, error):
        self._socket("disconnect", client, f"close {error}")
        return super().on_close(client, error)

    def _tee(self, kind: str, message: Any) -> None:
        if self._tee_sink is not None:
            self._tee_sink(kind, message)

    def handle_ohlcv(self, client, message):
        self._tee("kline", message)
        return super().handle_ohlcv(client, message)

    def handle_mark_prices(self, client, message):
        self._tee("markPrice", message)
        return super().handle_mark_prices(client, message)

    def handle_liquidation(self, client, message):
        self._tee("forceOrder", message)
        return super().handle_liquidation(client, message)


def _default_factory(config: Any, sink: Sink) -> TeeBinanceUsdm:
    return TeeBinanceUsdm(config, sink=sink)


@dataclass
class MarketFeed:
    symbol_id: str
    counter: DeliveryCounter
    on_kline: Callable[[KlineEvent], None]
    on_mark: Callable[[MarkTick], None]
    on_liquidation: Callable[[LiquidationEvent], None] | None = None
    exchange_factory: Callable[[Any, Sink], Any] = _default_factory
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    backoff_s: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)
    errors: list[Exception] = field(default_factory=list)
    reconnects: list[dict] = field(default_factory=list)
    exchange: Any = None
    recorder: Any = None                                   # `data.shards.Recorder`(put·event) — 없으면 기록 안 함
    now_ms: Callable[[], int] = field(default=ccxt.Exchange.milliseconds)
    refresh_after_s: float = RECONNECT_PROACTIVE_SEC
    refresh_check_s: float = REFRESH_CHECK_SEC
    event_errors: int = 0
    _failure: BaseException | None = None

    def _event(self, kind: str, detail: str) -> None:
        """소켓 수명 이벤트 → recorder. ccxt 콜백 안에서 불린다 — 던지지 않는다(센다)."""
        try:
            if self.recorder is not None:
                self.recorder.event(kind, detail)
        except Exception:  # noqa: BLE001
            self.event_errors += 1

    def _record(self, kind: str, row: tuple) -> None:
        try:
            if self.recorder is not None:
                self.recorder.put(kind, row)
        except Exception as e:  # noqa: BLE001 — 기록 실패는 피드를 멈추지 않지만 드러난다
            self.errors.append(e)

    def sink(self, kind: str, message: Any) -> None:
        """ccxt 수신 루프 안에서 불린다 — 여기서 예외를 밖으로 내보내지 않는다."""
        items = message if isinstance(message, list) else [message]
        for m in items:
            try:
                if kind == "kline":
                    k = parse_kline(m, symbol_id=self.symbol_id)
                    self.counter.observe("kline1m_update", k.event_ms)
                    row = kline_row(k, recv_ms=self.now_ms())
                    self._record("kline1m_update", row)
                    if k.closed:
                        self.counter.observe("kline1m_close", k.event_ms)
                        self._record("kline1m_close", row)
                    event: Any = k
                    callback: Any = self.on_kline
                elif kind == "markPrice":
                    if isinstance(m, dict) and m.get("s") not in (None, self.symbol_id):
                        continue                      # @arr 형태의 다른 심볼
                    event = parse_mark_price(m, symbol_id=self.symbol_id)
                    self.counter.observe("markprice", event.ts_ms)
                    self._record("markprice", markprice_row(event, m, recv_ms=self.now_ms()))
                    callback = self.on_mark
                elif kind == "forceOrder":
                    event = parse_force_order(m, symbol_id=self.symbol_id)
                    callback = self.on_liquidation
                else:
                    raise FeedMessageError(f"모르는 kind {kind}")
            except FeedMessageError as e:
                self.errors.append(e)
                continue
            if callback is None:
                continue
            try:
                callback(event)
            except Exception as e:  # noqa: BLE001 — 수신 루프 밖으로 새면 ccxt 수신 루프가 조용히 멈춘다
                self._failure = e

    async def _loop(self, name: str, watch: Callable[[], Awaitable[Any]], stop: asyncio.Event) -> None:
        attempt = 0
        while not stop.is_set():
            try:
                await watch()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except ProactiveRefresh as e:
                self.reconnects.append({"stream": name, "error": f"{type(e).__name__}: {e}", "delay_s": 0})
                attempt = 0                           # 선제 재연결 — 백오프 없이 바로 다시 watch
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                delay = self.backoff_s[min(attempt, len(self.backoff_s) - 1)]
                self.reconnects.append({"stream": name, "error": f"{type(e).__name__}: {e}", "delay_s": delay})
                self._event("reconnect", f"{name} after {type(e).__name__}: {e} delay_s={delay}")
                attempt += 1
                await self.sleep(delay)

    async def _refresh_loop(self, ex: Any, stop: asyncio.Event) -> None:
        """소켓마다 연결 시각을 따로 잰다 — 23h를 넘은 소켓만 끊어 다시 연결시킨다(E2E consume의 선제 재연결)."""
        while not stop.is_set():
            now = self.now_ms()
            for url, client in list((getattr(ex, "clients", None) or {}).items()):
                est = getattr(client, "connectionEstablished", None)
                if not isinstance(est, int) or getattr(client, "error", None) is not None:
                    continue
                age_s = (now - est) / 1000
                if age_s >= self.refresh_after_s:
                    self._event("reconnect", f"{url} proactive {self.refresh_after_s / 3600:g}h refresh age_s={age_s:.0f}")
                    client.on_error(ProactiveRefresh(f"proactive refresh after {age_s:.0f}s"))
            await asyncio.sleep(self.refresh_check_s)

    async def run(self, stop: asyncio.Event, *, config: Any = None) -> None:
        symbol = UNIFIED_SYMBOL[self.symbol_id]
        ex = self.exchange = self.exchange_factory(config or {}, self.sink)
        if hasattr(ex, "socket_hook"):
            ex.socket_hook = self._event
        if not ex.markets:
            await ex.load_markets()
        tasks = [
            asyncio.ensure_future(self._loop("kline1m_update", lambda: ex.watch_ohlcv(symbol, INTERVAL), stop)),
            asyncio.ensure_future(self._loop("markprice", lambda: ex.watch_mark_price(symbol), stop)),
        ]
        if self.on_liquidation is not None:
            tasks.append(asyncio.ensure_future(self._loop("forceOrder", lambda: ex.watch_liquidations(symbol), stop)))
        tasks.append(asyncio.ensure_future(self._refresh_loop(ex, stop)))
        try:
            while not stop.is_set():
                if self._failure is not None:
                    raise FeedFailure(f"피드 콜백 실패: {type(self._failure).__name__}: {self._failure}") from self._failure
                for t in tasks:
                    if not t.done() or stop.is_set():
                        continue
                    #  🔴 stop 전에 끝난 루프는 취소든 예외든 정상 종료든 실패다 — 스트림 하나가 조용히 죽지 않게
                    if t.cancelled():
                        raise FeedFailure("watch 루프가 취소로 끝났다(ccxt가 퓨처를 취소?)")
                    exc = t.exception()
                    raise FeedFailure(f"watch 루프 종료: {exc!r}") from exc
                await asyncio.sleep(0.01)
            if self._failure is not None:
                raise FeedFailure(f"피드 콜백 실패: {self._failure}") from self._failure
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await ex.close()
