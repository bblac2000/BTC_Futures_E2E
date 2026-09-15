"""봇 기동 — `python -m ops.run_bot --mode paper ...` (systemd `btcfut-bot.service`가 부른다).

순서: 인스턴스 락 → DB 마이그레이션 → 런타임 규칙(+ `runtime_rules` 기록) → 지갑 복원(마지막 엔진 스냅샷) →
안전 상태 복원(`safety_state`) → **포지션 복원(DB 열린 행 + 마지막 엔진 스냅샷이 일치할 때만, `ops.restore`)** →
텔레그램(명령·알림) → **직전 실행 종료 판정(`ops.run_events` — stop 없는 start/connect → `dirty_previous_run`, 기동 알림에 한 줄) ·
대장 `start`** → 기동 알림 → REST 백필(마감 봉 · 공개 GET) → shard 기록기 → 피드 + 1초 안전 틱.
종료(SIGTERM/SIGINT/`--duration-s`): 피드 정지 → 기록기 종료 기록(clean/dirty) → 스냅샷·상태 저장 → 텔레그램 정지 알림.

🔒 **LIVE는 이 러너로 기동하지 않는다** — 라이브 체크리스트(설계서 §10)·사용자 승인 전에는 `LiveSender`를 만드는 경로 자체가
여기 없다(`--mode live` → 종료 코드 4).

런타임 규칙(사용자 결정 2026-09-16 (ii) — PAPER·LIVE 같은 조회 경로):
- `.env`의 `BINANCE_API_KEY`/`BINANCE_API_SECRET`(**읽기 전용 키**) → `ReadOnlyClient(CcxtRestClient)` · 먼저 키 권한을 실측
  (`exchange.permissions.check_permissions`) — 읽기 외 권한이 하나라도 켜져 있으면 **기동 거부(종료 코드 4)**.
- 통과하면 `load_runtime_rules`(서명 GET 포함 6종) → `runtime_rules`(source `runtime:signed`).
- 키 없음·권한 조회 실패·서명 조회 실패 → **캡처 스냅샷 fallback**(서명 엔드포인트만 스냅샷, 나머지 공개 GET · 공개도 실패하면 전부
  스냅샷) + 진입 차단 사유 `rules_from_snapshot`. 규칙은 기동 때만 읽으므로 이 차단은 **/start로 풀리지 않는다** — 원인 해결 후 재기동.
- 키·시크릿 값은 출력하지 않는다(오류 문구에서도 가린다).

종료 코드: 0 clean · 1 기록기 dirty · 2 피드 실패 · 3 다른 인스턴스 실행 중 · 4 설정 오류.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import json
import logging
import re
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
from exchange.loader import (
    ENDPOINTS,
    REQUIRED,
    build_rules,
    load_runtime_rules,
    rules_from_snapshots,
    utc_iso,
)
from exchange.loader_types import RawFetch
from exchange.permissions import NotReadOnlyKey, check_permissions
from exchange.rules import RuntimeRules
from notify import config as NK
from notify.bot import CommandBot
from notify.poller import TelegramPoller
from notify.telegram_api import TelegramApi
from ops import run_events
from ops.delivery_counter import DeliveryCounter
from ops.restore import apply_restore, decide_paper_restore
from ops.runtime import BotRuntime
from ops.telegram_link import TelegramLink
from paper.engine import Engine
from paper.sender import PaperSender
from safety.config import REGISTERED_KILL_SWITCH
from safety.gate import STATE_NAME as SAFETY_GATE_STATE
from safety.gate import SafetyGate
from safety.stale import StaleDataGuard
from sizing.config import SizingLimits

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("btcfut")
SYMBOL = "BTCUSDT"
SAFETY_TICK_S = 1.0
EXIT_CLEAN, EXIT_DIRTY, EXIT_FEED, EXIT_LOCKED, EXIT_CONFIG = 0, 1, 2, 3, 4
KEY_ENV, SECRET_ENV = "BINANCE_API_KEY", "BINANCE_API_SECRET"
RULES_SOURCE_RUNTIME = "runtime:signed"
RULES_SOURCE_FALLBACK = "fallback:public+snapshot"
RULES_SOURCE_SNAPSHOT_ONLY = "fallback:snapshot"
RUN_EVENT_SOURCE = run_events.RUN_EVENT_SOURCE
RULES_FROM_SNAPSHOT = "rules_from_snapshot"          # 사용자 결정 2026-09-16 (ii) — 진입 차단 사유 문자열 그대로


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
    def breadcrumb_path(self) -> Path:
        return self.var_dir / "run" / "safety_unsaved.json"

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


@dataclass(frozen=True)
class RulesLoad:
    rules: RuntimeRules
    fetches: list[RawFetch]
    sources: list[str]
    db_source: str
    fallback_reason: str | None                    # None = 런타임 조회 성공


#  스킴이 있든 없든 경로 뒤 쿼리 전체(`https://h/p?…` · `/fapi/v1/p?…`)
#  경로 조각은 `/` + 한 글자 이상 — `/`만 반복되는 입력에서 시작점마다 되짚지 않게(Codex L8b 재검토 #2 초선형) · 입력은 먼저 자른다
_URL_QUERY = re.compile(r"((?:https?://[^\s?'\"/]+(?:/[A-Za-z0-9_.-]+)*)|(?:(?<![\w/])(?:/[A-Za-z0-9_.-]+)+))\?[^\s'\"]*")
SAFE_ERROR_SCAN_CHARS = 2000
_APIKEY_HEADER = re.compile(r"(?i)['\"]?x-mbx-apikey['\"]?\s*[:=]\s*['\"]?[^'\"\s,}]*['\"]?")
#  서명 재료: `k=v`(쿼리) · `"k":v` / `'k': 'v'` / `k: v`(JSON·dict·헤더식) — 대소문자 무시
_SIGNED_PARAM = re.compile(r"(?i)['\"]?\b(signature|timestamp|recvwindow)\b['\"]?\s*[:=]\s*['\"]?[^&\s'\",}]*['\"]?&?")


def safe_error(e: BaseException, *, secrets: list[str]) -> str:
    """사람에게 보이는 오류 문구(알림·상태 파일·stderr) — 서명 요청 재료를 구조적으로 지운다(Codex L8b #3):
    URL 쿼리 전체 · API 키 헤더 · signature/timestamp/recvWindow 파라미터 · 키·시크릿 값 그 자체. 300자로 자른다."""
    text = f"{type(e).__name__}: {e}"
    for s in secrets:                                               # 값 그대로 먼저(자르기 전에 — 잘린 조각이 남지 않게)
        if s:
            text = text.replace(s, "<redacted>")
    text = text[:SAFE_ERROR_SCAN_CHARS]
    text = _URL_QUERY.sub(r"\1", text)
    text = _APIKEY_HEADER.sub("<apikey-header>", text)
    text = _SIGNED_PARAM.sub("<signed>", text)
    for s in secrets:
        if s:
            text = text.replace(s, "<redacted>")
    return text[:300]


def signed_client_from_keys(key: str, secret: str, *, client_cls: Any = None) -> Any:
    """키를 실은 클라이언트의 **첫 요청이 권한 조회**가 되게 만든다(Codex L8b #4): 시각 오프셋은 키 없는 클라이언트로 받아 옮긴다."""
    if client_cls is None:
        from exchange.ccxt_rest import CcxtRestClient
        client_cls = CcxtRestClient
    offset = client_cls().sync_time()
    inner = client_cls(api_key=key, secret=secret)
    inner.ex.options["timeDifference"] = offset
    return ReadOnlyClient(inner)                                         # 키가 있어도 POST 구조적 불가


def _snapshot_fetches(snapshot_dir: Path, symbol: str) -> list[RawFetch]:
    out = []
    for name in REQUIRED:
        doc = json.loads((snapshot_dir / f"{name}.json").read_text(encoding="utf-8"))
        meta = doc.get("_meta", {})
        out.append(RawFetch(name, ENDPOINTS[name].path, symbol, str(meta.get("captured_at_utc") or "unknown"), doc["response"]))
    return out


def load_rules(cfg: RunConfig, *, env: Mapping[str, str], public_client: Any, signed_client: Any) -> RulesLoad:
    """런타임 조회(읽기 전용 키) → 실패하면 스냅샷 fallback. `NotReadOnlyKey`는 삼키지 않는다(호출자가 기동 거부)."""
    key, secret = env.get(KEY_ENV, ""), env.get(SECRET_ENV, "")
    hide = [key, secret]
    reason: str | None = None
    if signed_client is None:
        if key and secret:
            try:
                signed_client = signed_client_from_keys(key, secret)
            except Exception as e:  # noqa: BLE001 — 준비 실패는 fallback 사유
                reason = f"키 클라이언트 준비 실패 {safe_error(e, secrets=hide)}"
        else:
            reason = f"{KEY_ENV}/{SECRET_ENV} 없음"
    if signed_client is not None:
        try:
            check_permissions(signed_client)
            rules, fetches = load_runtime_rules(signed_client, cfg.symbol)
            sources = [f"{f.endpoint}=rest:signed" if ENDPOINTS[f.endpoint].signed else f"{f.endpoint}=rest" for f in fetches]
            return RulesLoad(rules, fetches, sources, RULES_SOURCE_RUNTIME, None)
        except NotReadOnlyKey:
            raise
        except Exception as e:  # noqa: BLE001 — 조회 실패는 fallback + 진입 차단
            reason = f"런타임 조회 실패 {safe_error(e, secrets=hide)}"
    assert reason is not None
    try:
        rules, fetches, sources = load_rules_public_plus_snapshot(public_client, cfg.snapshot_dir, cfg.symbol)
        return RulesLoad(rules, fetches, sources, RULES_SOURCE_FALLBACK, reason)
    except Exception as e:  # noqa: BLE001 — 공개 GET도 실패하면 전부 스냅샷(진입은 어차피 막힌다 · 청산 규칙은 필요)
        fetches = _snapshot_fetches(cfg.snapshot_dir, cfg.symbol)
        rules = rules_from_snapshots({f.endpoint: {"_meta": {"captured_at_utc": f.fetched_at_utc}, "response": f.payload}
                                      for f in fetches}, cfg.symbol)
        return RulesLoad(rules, fetches, [f"{f.endpoint}=snapshot" for f in fetches], RULES_SOURCE_SNAPSHOT_ONLY,
                         f"{reason} · 공개 GET도 실패 {safe_error(e, secrets=hide)}")


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
              telegram_api: Any = None, sleep: Callable[[float], Any] = asyncio.sleep, signed_client: Any = None) -> int:
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
        return await _run_locked(cfg, env=env, owners=owners, token=token, clock_ms=clock_ms, public_client=public_client,
                                 feed_factory=feed_factory, telegram_api=telegram_api, sleep=sleep,
                                 signed_client=signed_client)


async def _run_locked(cfg: RunConfig, *, env: Mapping[str, str], owners: frozenset[int] | None, token: str,
                      clock_ms: Callable[[], int], public_client: Any, feed_factory: FeedFactory, telegram_api: Any,
                      sleep: Callable[[float], Any], signed_client: Any) -> int:
    manifest.MANIFEST_DB = cfg.var_dir / "manifest.sqlite"
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cfg.db_path)
    con.execute("PRAGMA journal_mode=WAL")
    M.migrate(con)
    if public_client is None:
        from exchange.ccxt_rest import CcxtRestClient
        public_client = ReadOnlyClient(CcxtRestClient())                 # 키 없음 · POST 구조적 불가
    try:
        loaded = load_rules(cfg, env=env, public_client=public_client, signed_client=signed_client)
    except NotReadOnlyKey as e:
        print(f"🚫 설정 오류: {KEY_ENV}가 읽기 전용 키가 아니다 — 기동 거부: {e}", file=sys.stderr)
        con.close()
        return EXIT_CONFIG
    except Exception as e:  # noqa: BLE001 — 규칙 없이는 기동하지 않는다
        msg = safe_error(e, secrets=[env.get(KEY_ENV, ""), env.get(SECRET_ENV, "")])
        print(f"런타임 규칙 로드 실패: {msg}", file=sys.stderr)
        con.close()
        return EXIT_CONFIG
    rules, sources = loaded.rules, loaded.sources
    store.persist_fetches(con, loaded.fetches, mode=cfg.mode.value, source=loaded.db_source)

    now = clock_ms()
    wallet = last_engine_wallet(con, cfg.mode) or cfg.capital
    counter = DeliveryCounter(FED_STREAMS, start_ms=now)
    gate = SafetyGate.load(con, REGISTERED_KILL_SWITCH, StaleDataGuard(counter), mode=cfg.mode.value, wallet=wallet)
    crumb_ops: list[tuple[str, str, int, dict[str, Any] | None, str]] = []
    crumb_note: str | None = None
    keep_crumb = False
    if cfg.breadcrumb_path.exists():
        #  Codex L8 재검토 #1·#2·#3: 지난 실행이 DB에 못 쓴 안전 상태. 신선도 = **행 id**(시각 아님):
        #  breadcrumb의 기준 id(`base_state_id`) 뒤에 durable 저장이 있었고 **breadcrumb에만 있는 트립이 없으면** 오래된 것 → 격리.
        #  그 밖(기준 id가 최신 · id 없음(옛 형식) · DB에 없는 트립을 가짐)은 복원한다. 어느 경우든 진입을 멈춘다(해제는 사람의 /start).
        try:
            crumb = json.loads(cfg.breadcrumb_path.read_text())
            crumb_ts = int(crumb["ts_ms"])
            base_id = crumb.get("base_state_id")
            latest_id = R.latest_safety_state_id(con, SAFETY_GATE_STATE, mode=cfg.mode.value)
            crumb_trip = (crumb["safety_gate"].get("kill_switch") or {}).get("tripped")
            trip_only_in_crumb = crumb_trip is not None and gate.kill_switch.tripped is None
            if isinstance(base_id, int) and latest_id is not None and latest_id > base_id and not trip_only_in_crumb:
                stale = cfg.breadcrumb_path.with_name(f"safety_unsaved.stale-{crumb_ts}.json")
                cfg.breadcrumb_path.replace(stale)
                crumb_note = f"오래된 breadcrumb(기준 행 {base_id} < DB 최신 {latest_id}) — 복원 안 함 · {stale.name}로 격리"
            else:
                gate = SafetyGate.from_state(crumb["safety_gate"], REGISTERED_KILL_SWITCH, StaleDataGuard(counter),
                                             wallet=wallet)
                crumb_ops = [(str(o["kind"]), str(o["detail"]), int(o["ts_ms"]), o.get("payload"),
                              str(o.get("op_id") or f"crumb:{crumb_ts}:{i}")) for i, o in enumerate(crumb.get("ops") or [])]
                crumb_note = f"복원(ops {len(crumb_ops)}건)"
        except (OSError, ValueError, KeyError, TypeError) as e:
            keep_crumb = True
            crumb_note = f"해석 불가({type(e).__name__}) — 파일 보존, 사람 확인"
        gate.pause("system:restart_with_unsaved_safety_state")
    engine = Engine(rules, PaperSender(rules), mode=cfg.mode, wallet=wallet, limits=SizingLimits())
    rt = BotRuntime(engine=engine, gate=gate, con=con, symbol=cfg.symbol, clock_ms=clock_ms, status_path=cfg.status_path)
    rt.saved_state_id = R.latest_safety_state_id(con, SAFETY_GATE_STATE, mode=cfg.mode.value)
    if loaded.fallback_reason is not None:
        rt.rules_blocker = RULES_FROM_SNAPSHOT
    rt.rules_source = {"source": loaded.db_source, "fallback_reason": loaded.fallback_reason}
    if not keep_crumb:
        rt.breadcrumb_path = cfg.breadcrumb_path                         # 해석 못 한 breadcrumb는 경로를 주지 않아 지우지 않는다
    if crumb_note is not None:
        rt.unrecorded_ops = list(crumb_ops)                              # 멱등 op_id로 재생 — 이미 들어간 것은 건너뛴다
        rt.save_state(now)
        rt._retry_unrecorded(now)
        rt.record_ops("RestartWithUnsavedSafetyState", crumb_note, now)
    restore_msgs = apply_restore(rt, decide_paper_restore(con, mode=cfg.mode.value, symbol=cfg.symbol), now)

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
        link = TelegramLink(rt.poller, rt.inbox, rt.outbox, fast=rt.fast_poll.is_set)   # 봇 상태가 아니라 루프가 세운 플래그
        link.start()
        rt.status_extra = link.stats

    dirty: str | None = None
    try:
        #  기동 알림보다 먼저 판정한다 — 새로 판정한 dirty는 기동 알림에 한 줄(사용자 2026-09-16) · 확정 사실 알림은 health가 한 번
        dirty = run_events.previous_run_dirty()
        if dirty is not None:
            run_events.mark_dirty(dirty)
            rt.record_ops("DirtyPreviousRun", dirty, now, {"source": "manifest.events"})
        rt.run_facts = run_events.recent_dirty_facts()
        run_events.log_start(f"mode={cfg.mode.value} symbol={cfg.symbol} rules={loaded.db_source}")
    except Exception as e:  # noqa: BLE001 — 대장 조회 실패는 알리고 계속(수집·안전 경로와 무관)
        rt.alert(f"⚠️ 직전 실행 종료 판정 실패(대장): {type(e).__name__}: {e}", important=True)
    if crumb_note is not None:
        rt.alert(f"🛑 재기동: 지난 실행의 저장되지 않은 안전 상태 breadcrumb {crumb_note} · 신규 진입 일시정지 — 확인 후 /start",
                 important=True)
    rt.alert(f"🟢 기동 [{cfg.mode.value}] {cfg.symbol} · 지갑 {wallet} · 규칙 {', '.join(sources)} · "
             f"킬스위치 {'발동 ' + gate.kill_switch.tripped.reason if gate.kill_switch.tripped else '정상'}"
             + ("" if dirty is None else "\n📌 dirty_previous_run: 직전 실행이 종료 기록 없이 끝났다(상세 /status)"))
    if loaded.fallback_reason is not None:
        rt.alert(f"⚠️ 런타임 규칙 조회 실패 → 캡처 스냅샷으로 기동 · 신규 진입 금지({RULES_FROM_SNAPSHOT}) · "
                 f"/start로 풀리지 않음(규칙은 기동 때만 읽는다) — 원인 해결 후 재기동\n원인: {loaded.fallback_reason}",
                 important=True)
    for m in restore_msgs:
        rt.alert(m, important=True)
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
                    help="런타임 조회 실패 시 fallback 캡처 스냅샷 디렉터리(진입 차단 rules_from_snapshot)")
    ap.add_argument("--capital", default="1000")
    ap.add_argument("--var-dir", default=str(ROOT / "var"))
    ap.add_argument("--duration-s", type=float, default=None, help="정해진 시간 뒤 정상 종료(드라이런)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--backfill-minutes", type=int, default=180)
    a = ap.parse_args(argv)
    #  경로는 절대경로로 — shard 대장(manifest)의 path가 prune의 대조 키다(상대경로면 작업 디렉터리에 따라 어긋난다)
    return RunConfig(mode=Mode(a.mode), db_path=Path(a.db).resolve(), snapshot_dir=Path(a.snapshot_dir).resolve(),
                     capital=Decimal(a.capital), var_dir=Path(a.var_dir).resolve(), duration_s=a.duration_s, telegram=not a.no_telegram,
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
