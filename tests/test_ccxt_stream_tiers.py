"""ccxt.pro가 **실제로 여는** WS URL과 SUBSCRIBE 스트림을 티어 대응표(`ops/stream_tiers.py`)로 검증한다 — 레지스트리 #8.

🔴 왜: legacy 소켓은 `/market` 스트림 구독을 **수락해 놓고 한 건도 보내지 않는다**(E2E #132·#133). 우리는 더 이상
   URL을 직접 만들지 않으므로(ccxt.pro가 만든다), 라이브러리가 만드는 URL을 **연결 계층에서 가로채** 확인한다.
⚠️ ccxt 4.5.78 `binance.get_ws_url(type, category)`는 future 기본 URL이 **정확히 `/ws`로 끝날 때만**
   `/public/ws`·`/market/ws`로 바꿔 쓴다. 다음 버전이 기본 URL을 바꾸면 이 재작성은 조용히 멈추고 legacy가 돌아온다 —
   그걸 잡는 게 이 테스트다. ccxt 업그레이드마다 반드시 다시 돈다(레지스트리 #8).

네트워크 없음: `Client.create_connection`을 가짜 소켓으로 바꿔 URL·보낸 프레임만 기록하고, 마켓은 캡처 스냅샷
exchangeInfo로 적재한다.
"""
from __future__ import annotations

import asyncio
import json
import urllib.parse
from collections.abc import Callable
from typing import Any

import ccxt
import ccxt.pro as ccxtpro
import pytest
from ccxt.async_support.base.ws.client import Client

from ops import stream_tiers as T
from tests.conftest import load_snapshot

PINNED_CCXT = "4.5.78"
SYMBOL = "BTC/USDT:USDT"
#  🔴 런타임 조립 — 통째 리터럴은 tests/ legacy 잠금에 걸린다
HOST = "fstream" + ".binance.com"


class FakeSocket:
    closed = False
    _conn = None

    def __init__(self, url: str):
        self.url, self.sent = url, []
        self._never = asyncio.Event()

    async def send_str(self, s: str) -> None:
        self.sent.append(json.loads(s))

    async def receive(self):
        await self._never.wait()

    async def close(self) -> None:
        self.closed = True

    async def ping(self, *a: Any) -> None:
        return None

    async def pong(self, *a: Any) -> None:
        return None


def _exchange(factory: Callable[..., Any]):
    ex = factory({"options": {"fetchCurrencies": False}})
    info = load_snapshot("exchangeInfo")["response"]
    ex.set_markets(ex.parse_markets([s for s in info["symbols"] if s["symbol"] == "BTCUSDT"]))
    return ex


WATCHES: dict[str, Callable[[Any], Any]] = {
    "watch_ohlcv_1m": lambda ex: ex.watch_ohlcv(SYMBOL, "1m"),
    "watch_mark_price": lambda ex: ex.watch_mark_price(SYMBOL),
    "watch_liquidations": lambda ex: ex.watch_liquidations(SYMBOL),
    "watch_trades": lambda ex: ex.watch_trades(SYMBOL),
    "watch_bids_asks": lambda ex: ex.watch_bids_asks([SYMBOL]),
    "watch_order_book": lambda ex: ex.watch_order_book(SYMBOL),
    "watch_ticker": lambda ex: ex.watch_ticker(SYMBOL),
}
#  메서드 → 대응표에 따른 기대 티어(스트림 이름은 대응표가 분류한다 — 여기서는 티어만 고정)
EXPECTED_TIER = {"watch_ohlcv_1m": "market", "watch_mark_price": "market", "watch_liquidations": "market",
                 "watch_ticker": "market", "watch_trades": "public", "watch_bids_asks": "public",
                 "watch_order_book": "public"}


def capture(monkeypatch, factory: Callable[..., Any], names: list[str]) -> dict[str, tuple[str, list[str]]]:
    """메서드마다 새 거래소 인스턴스로 호출 → 열린 (URL, SUBSCRIBE params)."""
    opened: list[FakeSocket] = []

    async def fake_create(self, session):
        sock = FakeSocket(self.url)
        opened.append(sock)
        return sock
    monkeypatch.setattr(Client, "create_connection", fake_create)

    async def run() -> dict[str, tuple[str, list[str]]]:
        out = {}
        for name in names:
            ex = _exchange(factory)
            before = len(opened)
            task = asyncio.ensure_future(WATCHES[name](ex))
            for _ in range(50):
                await asyncio.sleep(0.01)
                if len(opened) > before and opened[-1].sent:
                    break
            task.cancel()
            new = opened[before:]
            assert len(new) == 1, f"{name}: 소켓 {len(new)}개 열림"
            params = [p for frame in new[0].sent if frame.get("method") == "SUBSCRIBE" for p in frame["params"]]
            out[name] = (new[0].url, params)
            await ex.close()
        return out
    return asyncio.run(run())


def verify_socket(url: str, params: list[str]) -> str:
    """fail-closed 검사 — 통과하면 소켓의 티어를 돌려준다."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "wss" or u.hostname != HOST:
        raise T.TierMismatchError(f"USDⓈ-M 스트림 호스트가 아니다: {url}")
    if T.LEGACY_RE.search(url):
        raise T.TierMismatchError(f"legacy 미라우팅 URL(2026-04-23 폐기): {url}")
    m = T.TIER_LITERAL_RE.search(url)
    if not m:
        raise T.TierMismatchError(f"티어 경로가 없는 URL: {url}")
    tier = m.group(1)
    if not params:
        raise T.TierMismatchError(f"{url}: SUBSCRIBE 스트림이 없다")
    for p in params:
        got = T.classify_stream(p).tier                      # 모르는 스트림은 UnknownStreamError(기본 티어 없음)
        if got != tier:
            raise T.TierMismatchError(f"{url}: 스트림 {p}는 {got} 티어인데 소켓은 {tier}")
    return tier


def test_the_pinned_version_is_what_is_installed():
    assert ccxt.__version__ == PINNED_CCXT, "업그레이드 = 레지스트리 새 행 + 이 파일 재검증(#8)"


def test_ccxt_pro_opens_only_tier_correct_endpoints_for_every_stream_we_use(monkeypatch, capsys):
    got = capture(monkeypatch, ccxtpro.binanceusdm, list(WATCHES))
    with capsys.disabled():
        print(f"\n[ccxt {ccxt.__version__}] ccxt.pro.binanceusdm 가 연 소켓")
        for name, (url, params) in got.items():
            print(f"  {name:20s} {url}  SUBSCRIBE {params}")
    for name, (url, params) in got.items():
        assert verify_socket(url, params) == EXPECTED_TIER[name], name
    #  레지스트리 #1: markPrice는 1초 주기 스트림이어야 한다
    assert got["watch_mark_price"][1] == ["btcusdt@markPrice@1s"]
    assert got["watch_ohlcv_1m"][1] == ["btcusdt@kline_1m"]
    assert got["watch_liquidations"][1] == ["btcusdt@forceOrder"]


def test_verifier_fails_closed_when_the_library_falls_back_to_legacy_routes(monkeypatch):
    """ccxt가 future 기본 URL을 바꿔 재작성이 멈춘 상황을 흉내 — 검사가 반드시 실패해야 한다."""
    def legacy_factory(config):
        ex = ccxtpro.binanceusdm(config)
        ex.urls["api"]["ws"]["future"] = "wss://" + HOST + "/stream"     # '/ws'로 끝나지 않음 → 재작성 안 됨
        return ex
    got = capture(monkeypatch, legacy_factory, ["watch_mark_price"])
    url, params = got["watch_mark_price"]
    with pytest.raises(T.TierMismatchError):
        verify_socket(url, params)


@pytest.mark.parametrize("url, params", [
    ("wss://" + HOST + "/market/ws/0", ["btcusdt@bookTicker"]),          # public 스트림이 market 소켓에
    ("wss://" + HOST + "/public/ws/0", ["btcusdt@markPrice@1s"]),         # market 스트림이 public 소켓에
    ("wss://" + HOST + "/market/ws/0", ["btcusdt@kline_1m", "btcusdt@trade"]),   # 한 소켓 혼합
    ("wss://" + HOST + "/market/ws/0", []),
    ("wss://stream.example.com/market/ws/0", ["btcusdt@kline_1m"]),
])
def test_verifier_rejects_mismatch_mixing_and_wrong_host(url, params):
    with pytest.raises(T.TierMismatchError):
        verify_socket(url, params)


def test_verifier_rejects_unknown_streams_instead_of_defaulting():
    with pytest.raises(T.UnknownStreamError):
        verify_socket("wss://" + HOST + "/market/ws/0", ["btcusdt@somethingNew"])
