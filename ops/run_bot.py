"""봇 기동 — `python -m ops.run_bot --mode paper ...` (systemd `btcfut-bot.service`가 부른다).

순서: 인스턴스 락 → DB 마이그레이션 → 런타임 규칙(+ `runtime_rules` 기록) → 지갑 복원(마지막 엔진 스냅샷) →
안전 상태 복원(`safety_state`) → REST 백필(마감 봉 · 공개 GET) → shard 기록기 → 텔레그램(명령·알림) → 피드 + 1초 안전 틱.
종료(SIGTERM/SIGINT/`--duration-s`): 피드 정지 → 기록기 종료 기록(clean/dirty) → 스냅샷·상태 저장 → 텔레그램 정지 알림.

🔒 **LIVE는 이 러너로 기동하지 않는다** — 라이브 체크리스트(설계서 §10)·사용자 승인 전에는 `LiveSender`를 만드는 경로 자체가
여기 없다(`--mode live` → 종료 코드 4). PAPER 규칙 조회는 서명 없는 공개 GET만 쓴다: 서명 엔드포인트(leverageBracket·
commissionRate)는 **캡처 스냅샷**에서 읽는다(`--rules public+snapshot`) — 키를 쓰지 않는다.

종료 코드: 0 clean · 1 기록기 dirty · 2 피드 실패 · 3 다른 인스턴스 실행 중 · 4 설정 오류.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import json
import logging
import signal
import sqlite3
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from data import manifest
from data.backfill import fetch_closed_klines
from data.config import KLINES_PAGE_LIMIT
from data.feed import FED_STREAMS, MarketFeed
from data.shards import Recorder
from db import migrate as M
from db import record as R
from exchange import store
from exchange.client import ReadOnlyClient
from exchange.gate import Mode
from exchange.loader import ENDPOINTS, REQUIRED, build_rules, utc_iso
from exchange.loader_types import RawFetch
from exchange.rules import RuntimeRules
from notify import config as NK
from notify.bot import CommandBot
from notify.poller import TelegramPoller
from notify.telegram_api import TelegramApi
from ops.delivery_counter import DeliveryCounter
from ops.runtime import BotRuntime
from ops.telegram_link import TelegramLink
from paper.engine import Engine
from paper.sender import PaperSender
from safety.config import REGISTERED_KILL_SWITCH
from safety.gate import SafetyGate
from safety.stale import StaleDataGuard
from sizing.config import SizingLimits

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("btcfut")
SYMBOL = "BTCUSDT"
SAFETY_TICK_S = 1.0
EXIT_CLEAN, EXIT_DIRTY, EXIT_FEED, EXIT_LOCKED, EXIT_CONFIG = 0, 1, 2, 3, 4


@dataclass(frozen=True)
class RunConfig:
    mode: Mode
    db_path: Path
    snapshot_dir: Path
    capital: Decimal
    var_dir: Path
    duration_s: float | None = None
    telegram: bool = True
    backfill_minutes: int = 180
    symbol: str = SYMBOL

    @property
    def status_path(self) -> Path:
        return self.var_dir / "run" / "status.json"

    @property
    def lock_path(self) -> Path:
        return self.var_dir / "run" / "bot.lock"

    @property
    def raw_root(self) -> Path:
        return self.var_dir / "raw" / "live" / self.symbol


def wall_ms() -> int:
    return int(time.time() * 1000)


def load_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE 줄만 — 값은 출력하지 않는다. 없으면 빈 dict(systemd는 EnvironmentFile로 넘긴다)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@contextlib.contextmanager
def instance_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open("a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        yield False
        return
    try:
        f.seek(0)
        f.truncate()
        f.write(f"{wall_ms()}\n")
        f.flush()
        yield True
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def load_rules_public_plus_snapshot(public: Any, snapshot_dir: Path, symbol: str) -> tuple[RuntimeRules, list[RawFetch], list[str]]:
    """서명 없는 엔드포인트는 지금 공개 GET, 서명 엔드포인트는 캡처 스냅샷 — 출처를 fetch마다 남긴다."""
    fetches: list[RawFetch] = []
    sources: list[str] = []
    for name, spec in ENDPOINTS.items():
        if name not in REQUIRED:
            continue
        if spec.signed:
            doc = json.loads((snapshot_dir / f"{name}.json").read_text(encoding="utf-8"))
            meta = doc.get("_meta", {})
            fetches.append(RawFetch(name, spec.path, symbol, str(meta.get("captured_at_utc") or "unknown"), doc["response"]))
            sources.append(f"{name}=snapshot")
        else:
            fetches.append(RawFetch(name, spec.path, symbol, utc_iso(), public.get(spec.path).data))
            sources.append(f"{name}=rest")
    rules = build_rules({f.endpoint: f.payload for f in fetches}, symbol, {f.endpoint: f.fetched_at_utc for f in fetches})
    return rules, fetches, sources


def last_engine_wallet(con: sqlite3.Connection, mode: Mode) -> Decimal | None:
    row = con.execute("SELECT wallet_balance FROM account_snapshots WHERE mode=? AND source='engine' "
                      "AND wallet_balance IS NOT NULL ORDER BY id DESC LIMIT 1", (mode.value,)).fetchone()
    return None if row is None else Decimal(row[0])


def backfill(rt: BotRuntime, public: Any, *, now_ms: int, minutes: int) -> dict[str, int]:
    """마지막 DB 봉 다음 분부터(최대 `minutes`분 전) 지금까지의 마감 봉 → bars_1m(source rest)."""
    last = rt.con.execute("SELECT max(open_time_ms) FROM bars_1m WHERE mode=? AND symbol=?",
                          (rt.mode.value, rt.symbol)).fetchone()[0]
    start = max(now_ms - minutes * 60_000, (last + 60_000) if last is not None else 0)
    out = {"inserted": 0, "duplicate": 0, "enriched": 0, "conflict": 0, "failed": 0}
    if start >= now_ms:
        return out
    for b in fetch_closed_klines(public, rt.symbol, start_ms=start, end_ms=now_ms, page_limit=KLINES_PAGE_LIMIT,
                                 now_ms=now_ms):
        res = rt.record_bar(R.BarRow(b.open_ms, b.close_ms, b.open, b.high, b.low, b.close, b.volume, b.quote_volume,
                                     b.trades, b.taker_buy_base, b.taker_buy_quote), source="rest")
        out[res or "failed"] += 1
    return out


FeedFactory = Callable[[DeliveryCounter, BotRuntime, Recorder], Any]


def _default_feed(counter: DeliveryCounter, rt: BotRuntime, recorder: Recorder) -> Any:
    return MarketFeed(rt.symbol, counter, on_kline=rt.on_kline, on_mark=rt.on_mark, recorder=recorder)


async def run(cfg: RunConfig, *, env: Mapping[str, str], clock_ms: Callable[[], int] = wall_ms,
              public_client: Any = None, feed_factory: FeedFactory = _default_feed,
              telegram_api: Any = None, sleep: Callable[[float], Any] = asyncio.sleep) -> int:
    if cfg.mode is not Mode.PAPER:
        print("🔒 LIVE 기동은 이 러너에 없다 — 라이브 체크리스트(설계서 §10)·사용자 승인 후 별도 배선", file=sys.stderr)
        return EXIT_CONFIG
    owners: frozenset[int] | None = None
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if cfg.telegram:
        try:
            owners = NK.owner_ids_from_env(env)
        except ValueError as e:
            print(f"설정 오류: {e}", file=sys.stderr)
            return EXIT_CONFIG
        if not token and telegram_api is None:
            print("설정 오류: TELEGRAM_BOT_TOKEN 없음", file=sys.stderr)
            return EXIT_CONFIG
    with instance_lock(cfg.lock_path) as locked:
        if not locked:
            print(f"다른 인스턴스가 실행 중(락 {cfg.lock_path})", file=sys.stderr)
            return EXIT_LOCKED
        return await _run_locked(cfg, owners=owners, token=token, clock_ms=clock_ms, public_client=public_client,
                                 feed_factory=feed_factory, telegram_api=telegram_api, sleep=sleep)


async def _run_locked(cfg: RunConfig, *, owners: frozenset[int] | None, token: str, clock_ms: Callable[[], int],
                      public_client: Any, feed_factory: FeedFactory, telegram_api: Any,
                      sleep: Callable[[float], Any]) -> int:
    manifest.MANIFEST_DB = cfg.var_dir / "manifest.sqlite"
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cfg.db_path)
    con.execute("PRAGMA journal_mode=WAL")
    M.migrate(con)
    if public_client is None:
        from exchange.ccxt_rest import CcxtRestClient
        public_client = ReadOnlyClient(CcxtRestClient())                 # 키 없음 · POST 구조적 불가
    try:
        rules, fetches, sources = load_rules_public_plus_snapshot(public_client, cfg.snapshot_dir, cfg.symbol)
    except Exception as e:  # noqa: BLE001 — 규칙 없이는 기동하지 않는다
        print(f"런타임 규칙 로드 실패: {type(e).__name__}: {e}", file=sys.stderr)
        con.close()
        return EXIT_CONFIG
    store.persist_fetches(con, fetches, mode=cfg.mode.value, source=f"public+snapshot:{cfg.snapshot_dir}")

    now = clock_ms()
    wallet = last_engine_wallet(con, cfg.mode) or cfg.capital
    counter = DeliveryCounter(FED_STREAMS, start_ms=now)
    gate = SafetyGate.load(con, REGISTERED_KILL_SWITCH, StaleDataGuard(counter), mode=cfg.mode.value, wallet=wallet)
    engine = Engine(rules, PaperSender(rules), mode=cfg.mode, wallet=wallet, limits=SizingLimits())
    rt = BotRuntime(engine=engine, gate=gate, con=con, symbol=cfg.symbol, clock_ms=clock_ms, status_path=cfg.status_path)

    link: TelegramLink | None = None
    if cfg.telegram:
        assert owners is not None
        api = telegram_api or TelegramApi(token)
        rt.bot = CommandBot(rt, owner_ids=owners, started_ms=now)
        rt.poller = TelegramPoller(api, rt.bot, clock_ms=clock_ms)
        try:
            rt.poller.setup()
        except Exception as e:  # noqa: BLE001 — 메뉴 등록 실패는 기동을 막지 않는다(알림은 계속)
            logger.warning("텔레그램 setup 실패: %s", e)
        bot = rt.bot
        link = TelegramLink(rt.poller, rt.inbox, rt.outbox, fast=lambda: bot.pending is not None or bool(bot.alerts))
        link.start()
        rt.status_extra = link.stats

    db_open = R.open_position_state(con, mode=cfg.mode.value, symbol=cfg.symbol)
    rt.alert(f"🟢 기동 [{cfg.mode.value}] {cfg.symbol} · 지갑 {wallet} · 규칙 {', '.join(sources)} · "
             f"킬스위치 {'발동 ' + gate.kill_switch.tripped.reason if gate.kill_switch.tripped else '정상'}")
    if db_open is not None:
        rt.alert(f"⚠️ 재기동: DB에 열린 포지션 {db_open.direction} {db_open.remaining_qty} — 엔진은 복원하지 않는다 · "
                 "대사 불일치로 진입 금지 · 사람 확인 필요", important=True)
    try:
        bf = backfill(rt, public_client, now_ms=now, minutes=cfg.backfill_minutes)
        rt.record_ops("Backfill", json.dumps(bf), now, bf)
    except Exception as e:  # noqa: BLE001 — 백필 실패는 알리고 계속(실시간 봉은 WS로 쌓인다)
        rt.alert(f"⚠️ REST 백필 실패: {type(e).__name__}: {e}")

    recorder = Recorder(cfg.raw_root, cfg.symbol)
    recorder.start()
    feed = feed_factory(counter, rt, recorder)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop.set)
    if cfg.duration_s is not None:
        loop.call_later(cfg.duration_s, stop.set)

    async def safety_loop() -> None:
        while not stop.is_set():
            rt.safety_tick(clock_ms())
            await sleep(SAFETY_TICK_S)

    code = EXIT_CLEAN
    safety = asyncio.ensure_future(safety_loop())
    try:
        await feed.run(stop)
    except Exception as e:  # noqa: BLE001 — 피드 실패는 알리고 종료 코드로(systemd가 재시작)
        code = EXIT_FEED
        rt.alert(f"🔴 피드 실패 — 종료: {type(e).__name__}: {e}", important=True)
    finally:
        stop.set()
        safety.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await safety
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(sig)
        kind, detail = recorder.stop()
        end = clock_ms()
        rt.snapshot(end, "shutdown")
        rt.save_state(end)
        if code == EXIT_CLEAN and kind == "stop_dirty":
            code = EXIT_DIRTY
        rt.alert(f"{'⚪' if code == EXIT_CLEAN else '🔴'} 정지 [{cfg.mode.value}] {kind} · {detail} · 종료 코드 {code}")
        if link is not None:
            link.stop()                                   # 정지 알림까지 비운 뒤 상태를 쓴다(배달 수가 최종값)
        rt.write_status(end, {"shutdown": kind, "shutdown_detail": detail, "exit_code": code})
        con.close()
    return code


def parse_args(argv: list[str] | None = None) -> RunConfig:
    ap = argparse.ArgumentParser(description="BTCUSDT 봇 기동(PAPER)")
    ap.add_argument("--mode", default="paper", choices=[m.value for m in Mode])
    ap.add_argument("--db", default=str(ROOT / "var" / "bot.sqlite"))
    ap.add_argument("--snapshot-dir", default=str(ROOT / "tests" / "fixtures" / "snapshots"),
                    help="서명 엔드포인트(leverageBracket·commissionRate) 캡처 스냅샷 디렉터리")
    ap.add_argument("--capital", default="1000")
    ap.add_argument("--var-dir", default=str(ROOT / "var"))
    ap.add_argument("--duration-s", type=float, default=None, help="정해진 시간 뒤 정상 종료(드라이런)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--backfill-minutes", type=int, default=180)
    a = ap.parse_args(argv)
    return RunConfig(mode=Mode(a.mode), db_path=Path(a.db), snapshot_dir=Path(a.snapshot_dir), capital=Decimal(a.capital),
                     var_dir=Path(a.var_dir), duration_s=a.duration_s, telegram=not a.no_telegram,
                     backfill_minutes=a.backfill_minutes)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.Formatter.converter = time.gmtime
    cfg = parse_args(argv)
    import os
    env = load_env_file(ROOT / ".env") | dict(os.environ)
    return asyncio.run(run(cfg, env=env))


if __name__ == "__main__":
    raise SystemExit(main())
