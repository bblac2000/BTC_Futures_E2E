"""layer 8 기동 러너 — 전체 경로 재생(피드 → 엔진 → DB → 텔레그램) · 설정 거부 · 인스턴스 락 · 재기동 복원.

소켓·HTTP 없음: 공개 REST는 스냅샷을 돌려주는 가짜, 피드는 재생, 텔레그램은 호출을 기록하는 가짜 API.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from data import manifest
from data.feed import KlineEvent
from exchange.client_types import Response
from exchange.errors import BinanceAPIError
from exchange.gate import Mode
from exchange.loader import ENDPOINTS
from ops import run_bot as RB
from ops.telegram_link import TelegramLink
from paper.types import MarkTick
from tests.conftest import FIX, load_snapshot
from tests.test_paper_engine import next_funding

D = Decimal
T0 = 1_789_430_400_000
OWNER = 111


class FakePublic:
    """공개 GET만 — POST가 오면 테스트 실패(러너는 ReadOnlyClient 경로)."""

    def __init__(self, now_ms: int):
        self.now_ms, self.calls = now_ms, []

    def get(self, path, params=None, *, signed=False):
        assert not signed, "러너는 서명 요청을 하지 않는다"
        self.calls.append(path)
        if path == "/fapi/v1/exchangeInfo":
            return Response(200, load_snapshot("exchangeInfo")["response"])
        if path == "/fapi/v1/fundingInfo":
            return Response(200, load_snapshot("fundingInfo")["response"])
        if path == "/fapi/v1/klines":
            assert params is not None
            start = params["startTime"]
            rows = []
            t = (start // 60_000 + (1 if start % 60_000 else 0)) * 60_000
            while t + 59_999 < self.now_ms and len(rows) < params["limit"]:
                rows.append([t, "60000", "60010", "59990", "60000", "1.5", t + 59_999, "90000", 42, "0.7", "42000", "0"])
                t += 60_000
            return Response(200, rows)
        raise AssertionError(path)

    def post(self, *a, **k):
        raise AssertionError("POST 금지")


READ_ONLY = {"ipRestrict": True, "enableReading": True, "enableFutures": False, "enableWithdrawals": False,
             "enableSpotAndMarginTrading": False, "enableMargin": False, "enableInternalTransfer": False,
             "permitsUniversalTransfer": False, "enableVanillaOptions": False, "enablePortfolioMarginTrading": False,
             "enableFixApiTrade": False}
KEYS = {"BINANCE_API_KEY": "dummy-key-AAAA", "BINANCE_API_SECRET": "dummy-secret-BBBB"}
BY_PATH = {spec.path: name for name, spec in ENDPOINTS.items()}


class FakeSigned:
    """키가 있는 읽기 전용 클라이언트(가짜) — 권한 조회 + 런타임 규칙 6종. POST가 오면 실패."""

    def __init__(self, perms=None, fail: str | None = None):
        self.perms, self.fail, self.calls = READ_ONLY if perms is None else perms, fail, []

    def get(self, path, params=None, *, signed=False):
        self.calls.append((path, signed))
        if path == "/sapi/v1/account/apiRestrictions":
            assert signed
            return Response(200, self.perms)
        name = BY_PATH[path]
        assert signed == ENDPOINTS[name].signed
        if name == self.fail:
            raise BinanceAPIError(401, -2015, "Invalid API-key, IP, or permissions for action.", path)
        return Response(200, load_snapshot(name)["response"])

    def post(self, *a, **k):
        raise AssertionError("POST 금지")


class FakeTelegram:
    def __init__(self):
        self.calls: list[tuple] = []
        self.lock = threading.Lock()

    def _rec(self, *c):
        with self.lock:
            self.calls.append(c)

    def get_updates(self, *, offset, timeout_s, allowed_updates=None):
        time.sleep(0.01)
        return []

    def send_message(self, chat_id, text, reply_markup=None):
        self._rec("send", chat_id, text)
        return {"message_id": len(self.calls), "chat": {"id": chat_id}}

    def answer_callback_query(self, qid, text=None):
        self._rec("answer", qid, text)

    def set_my_commands(self, commands):
        self._rec("set_my_commands", len(commands))

    def set_chat_menu_button(self, chat_id=None, menu_button=None):
        self._rec("menu", menu_button)

    def texts(self):
        with self.lock:
            return [c[2] for c in self.calls if c[0] == "send"]


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class ReplayFeed:
    """1초 간격 mark 틱 + 분 마감 kline을 재생하고 끝나면 stop."""

    def __init__(self, counter, rt, clock, *, start, seconds):
        self.counter, self.rt, self.clock, self.start, self.seconds = counter, rt, clock, start, seconds

    async def run(self, stop):
        for i in range(self.seconds):
            t = self.start + i * 1000
            self.clock.t = t
            self.counter.observe("markprice", t)
            self.counter.observe("kline1m_update", t)
            self.rt.on_mark(MarkTick(t, D("60000"), D("0.0001"), next_funding(t)))
            if t % 60_000 == 59_000:
                self.counter.observe("kline1m_close", t + 999)
                c = D("60000")
                self.rt.on_kline(KlineEvent(t + 999, t - 59_000, t + 999, c, c, c, c, D("1"), c, 5, D("0.5"), c / 2, True))
            await asyncio.sleep(0)
        await asyncio.sleep(0.05)                                   # 발송 스레드가 비울 시간
        stop.set()


def config(tmp_path: Path, **kw) -> RB.RunConfig:
    import dataclasses
    base = RB.RunConfig(mode=Mode.PAPER, db_path=tmp_path / "bot.sqlite", snapshot_dir=FIX, capital=D("1000"),
                        var_dir=tmp_path / "var", backfill_minutes=10)
    return dataclasses.replace(base, **kw)


def run(cfg, *, clock, tg=None, seconds=125, env=None, public=None, signed=None, feed=None):
    env = {"TELEGRAM_OWNER_IDS": str(OWNER), "TELEGRAM_BOT_TOKEN": "x"} | KEYS if env is None else env
    signed = FakeSigned() if signed is None and "BINANCE_API_KEY" in env else signed

    def factory(counter, rt, recorder):
        return (feed or ReplayFeed)(counter, rt, clock, start=clock.t, seconds=seconds)

    async def fast_sleep(_s):
        await asyncio.sleep(0)

    return asyncio.run(RB.run(cfg, env=env, clock_ms=clock, public_client=public or FakePublic(clock.t),
                              feed_factory=factory, telegram_api=tg, sleep=fast_sleep, signed_client=signed))


@pytest.fixture(autouse=True)
def _manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(manifest, "MANIFEST_DB", tmp_path / "var" / "manifest.sqlite")


def test_full_paper_replay_through_the_runner_records_bars_rules_snapshots_and_talks_to_telegram(tmp_path):
    clock = Clock(T0 + 10 * 60_000 + 1000)
    tg = FakeTelegram()
    cfg = config(tmp_path)
    assert run(cfg, clock=clock, tg=tg) == RB.EXIT_CLEAN
    con = sqlite3.connect(cfg.db_path)
    by_source = dict(con.execute("SELECT source, count(*) FROM bars_1m GROUP BY source").fetchall())
    assert by_source["rest"] == 9 and by_source["ws"] == 2           # 시작이 T0+1s라 첫 완결 분은 T0+60s
    assert {r[0] for r in con.execute("SELECT endpoint FROM runtime_rules")} == set(ENDPOINTS), "런타임 조회 6종(서명 포함)"
    assert {r[0] for r in con.execute("SELECT source FROM runtime_rules")} == {RB.RULES_SOURCE_RUNTIME}
    assert con.execute("SELECT count(*) FROM account_snapshots WHERE source='engine'").fetchone()[0] >= 3
    assert con.execute("SELECT kind FROM engine_events WHERE kind='Backfill'").fetchall() == [("Backfill",)]
    status = json.loads(cfg.status_path.read_text())
    assert status["shutdown"] == "stop" and status["exit_code"] == 0 and status["counts"]["bars"] == 2
    assert status["delivered"] == status["sent"] == len(tg.texts()) >= 2, "정지 알림 배달까지 센 뒤 상태를 쓴다"
    texts = tg.texts()
    assert any(t.startswith("🟢 기동 [paper]") and "exchangeInfo=rest" in t and "leverageBracket=rest:signed" in t
               for t in texts)
    assert "rules_from_snapshot" not in status["blockers"] and status["entries_allowed"]
    assert any(t.startswith("⚪ 정지 [paper] stop") for t in texts)
    assert ("set_my_commands", 8) in tg.calls
    assert not cfg.lock_path.exists() or cfg.lock_path.read_text()                  # 락 파일은 남아도 잠금은 풀렸다
    ev = sqlite3.connect(tmp_path / "var" / "manifest.sqlite").execute("SELECT kind FROM events").fetchall()
    assert ("stop",) in ev


def test_restart_with_an_open_row_but_no_position_snapshot_starts_flat_and_pauses(tmp_path):
    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    con = sqlite3.connect(cfg.db_path)
    con.execute("INSERT INTO account_snapshots(mode, symbol, ts_ms, source, wallet_balance) "
                "VALUES('paper','BTCUSDT',1,'engine','987.65')")
    con.execute("INSERT INTO positions(mode, symbol, ts_ms, event, direction, qty, entry_price) "
                "VALUES('paper','BTCUSDT',1,'open','LONG','0.01','60000')")
    con.execute("UPDATE positions SET position_id=id")
    con.commit()
    tg = FakeTelegram()
    clock.t += 3_600_000
    assert run(cfg, clock=clock, tg=tg, seconds=5) == 0
    texts = tg.texts()
    assert any("지갑 987.65" in t for t in texts)
    assert any("포지션 복원하지 않음" in t and "DB: LONG 0.01" in t for t in texts)
    status = json.loads(cfg.status_path.read_text())
    assert "paused:system:restart_position_mismatch" in status["blockers"] and status["position"] is None


class EntryFeed(ReplayFeed):
    """재생 도중 한 번 진입 의도를 낸다(러너가 만든 BotRuntime의 진입 게이트 경로)."""

    done = False

    async def run(self, stop):
        from tests.test_paper_engine import intent
        orig = self.rt.on_mark

        def on_mark(t):
            orig(t)
            if self.rt.engine.position is None and self.rt.engine.pending is None and not self.rt.entry_blockers() \
                    and not self.done:
                self.done = True
                self.rt.submit_entry(intent(decided_ms=t.ts_ms, mark="60000"))
        self.rt.on_mark = on_mark
        await super().run(stop)


def test_restart_after_stop_with_an_open_position_restores_it_and_entries_resume(tmp_path):
    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=70, feed=EntryFeed) == 0
    status = json.loads(cfg.status_path.read_text())
    assert status["position"] is not None, "첫 실행이 포지션을 연 채 끝났다"
    tg = FakeTelegram()
    clock.t += 5000
    assert run(cfg, clock=clock, tg=tg, seconds=70) == 0
    status = json.loads(cfg.status_path.read_text())
    assert status["position"] is not None and status["blockers"] == [] and status["entries_allowed"]
    assert any(t.startswith("♻️ 재기동: 포지션 복원 LONG") for t in tg.texts())
    con = sqlite3.connect(cfg.db_path)
    assert con.execute("SELECT count(*) FROM positions WHERE event='open'").fetchone()[0] == 1, "root open 행은 하나"
    assert con.execute("SELECT kind FROM engine_events WHERE kind IN ('PositionRestored','RestartRestore') ORDER BY id")\
        .fetchall() == [("PositionRestored",), ("RestartRestore",)]


# ── 런타임 규칙 출처(사용자 결정 2026-09-16 (ii)) ─────────────────────────────────
def test_missing_key_falls_back_to_the_snapshot_and_blocks_entries_with_rules_from_snapshot(tmp_path):
    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    tg = FakeTelegram()
    assert run(cfg, clock=clock, tg=tg, seconds=70, env={"TELEGRAM_OWNER_IDS": str(OWNER), "TELEGRAM_BOT_TOKEN": "x"}) == 0
    status = json.loads(cfg.status_path.read_text())
    assert "rules_from_snapshot" in status["blockers"] and not status["entries_allowed"]
    assert any("rules_from_snapshot" in t and "BINANCE_API_KEY" in t for t in tg.texts())
    con = sqlite3.connect(cfg.db_path)
    assert {r[0] for r in con.execute("SELECT source FROM runtime_rules")} == {RB.RULES_SOURCE_FALLBACK}


def test_signed_lookup_failure_falls_back_and_blocks_entries(tmp_path):
    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    tg = FakeTelegram()
    assert run(cfg, clock=clock, tg=tg, seconds=70, signed=FakeSigned(fail="leverageBracket")) == 0
    status = json.loads(cfg.status_path.read_text())
    assert "rules_from_snapshot" in status["blockers"]
    assert any("rules_from_snapshot" in t and "-2015" in t for t in tg.texts())


def test_a_key_with_any_non_read_permission_is_refused_and_never_printed(tmp_path, capsys):
    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    tg = FakeTelegram()
    perms = READ_ONLY | {"enableFutures": True}
    assert run(cfg, clock=clock, tg=tg, seconds=5, signed=FakeSigned(perms=perms)) == RB.EXIT_CONFIG
    out = capsys.readouterr()
    assert "enableFutures" in out.err
    for v in KEYS.values():
        assert v not in out.out + out.err + " ".join(tg.texts())


def test_live_mode_and_missing_owner_ids_are_refused_before_anything_starts(tmp_path, capsys):
    clock = Clock(T0)
    assert run(config(tmp_path, mode=Mode.LIVE), clock=clock) == RB.EXIT_CONFIG
    assert "LIVE" in capsys.readouterr().err
    assert run(config(tmp_path), clock=clock, env={"TELEGRAM_BOT_TOKEN": "x"}) == RB.EXIT_CONFIG
    assert not (tmp_path / "bot.sqlite").exists()


def test_a_second_instance_is_refused_by_the_lock(tmp_path):
    cfg = config(tmp_path)
    with RB.instance_lock(cfg.lock_path) as ok:
        assert ok
        assert run(cfg, clock=Clock(T0), tg=FakeTelegram()) == RB.EXIT_LOCKED


def test_env_file_parser_reads_keys_without_printing(tmp_path, capsys):
    p = tmp_path / ".env"
    p.write_text("# c\nTELEGRAM_BOT_TOKEN=secret-value\nTELEGRAM_OWNER_IDS=1,2\n\nBAD\n")
    assert RB.load_env_file(p) == {"TELEGRAM_BOT_TOKEN": "secret-value", "TELEGRAM_OWNER_IDS": "1,2"}
    assert "secret-value" not in capsys.readouterr().out
    assert RB.load_env_file(tmp_path / "none") == {}


# ── 텔레그램 링크 스레드 ─────────────────────────────────────────────────────
class LinkPoller:
    def __init__(self, script):
        self.script, self.executed, self.send_errors, self.handler_errors = list(script), [], 0, 0
        self.fast_seen = []

    def fetch(self, *, fast):
        self.fast_seen.append(fast)
        if not self.script:
            time.sleep(0.01)
            return []
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def execute(self, actions):
        self.executed += actions
        return [{"message_id": 7}]


def test_link_poll_thread_backs_off_on_errors_and_only_queues_updates():
    import queue
    sleeps = []
    p = LinkPoller([RuntimeError("409 Conflict"), RuntimeError("down"), [{"update_id": 1}], [{"update_id": 2}]])
    inbox, outbox = queue.SimpleQueue(), queue.SimpleQueue()
    link = TelegramLink(p, inbox, outbox, fast=lambda: True, sleep=lambda s: sleeps.append(s))
    outbox.put("a1")
    link.start()
    deadline = time.monotonic() + 2
    while inbox.qsize() < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    link.stop(flush_timeout_s=1)
    assert [inbox.get_nowait()["update_id"] for _ in range(2)] == [1, 2]
    assert sleeps[:2] == [1.0, 2.0] and link.poll_errors == 2 and "down" in (link.last_poll_error or "")
    assert p.executed == ["a1"] and link.stats()["sent"] == 1 and p.fast_seen[0] is True
    assert link.stats()["delivered"] == 1 and link.stats()["last_message_id"] == 7


def test_restart_with_a_breadcrumb_restores_the_trip_pauses_entries_and_persists_it(tmp_path):
    cfg = config(tmp_path)
    crumb = cfg.var_dir / "run" / "safety_unsaved.json"
    crumb.parent.mkdir(parents=True, exist_ok=True)
    state = {"paused_by": None, "reconcile": {"blocker": None, "sticky": False},
             "kill_switch": {"tripped": {"ts_ms": T0, "reason": "daily_loss", "detail": "x"}, "consecutive_losses": 0,
                             "liquidations": 0, "vanished": 0, "last_flat_wallet": "1000", "day": "2026-09-15",
                             "day_start_equity": "1000", "resumed_by": None}}
    crumb.write_text(json.dumps({"ts_ms": T0, "safety_gate": state,
                                 "ops": [{"kind": "KillSwitchTripped", "detail": "x", "ts_ms": T0, "payload": {"reason": "daily_loss"}}]}))
    tg = FakeTelegram()
    clock = Clock(T0 + 10 * 60_000 + 1000)
    assert run(cfg, clock=clock, tg=tg, seconds=5) == 0
    con = sqlite3.connect(cfg.db_path)
    (latest,) = con.execute("SELECT state_json FROM safety_state ORDER BY id DESC LIMIT 1").fetchone()
    body = json.loads(latest)
    assert body["kill_switch"]["tripped"]["reason"] == "daily_loss" and body["paused_by"] == "system:restart_with_unsaved_safety_state"
    assert con.execute("SELECT count(*) FROM engine_events WHERE kind='KillSwitchTripped'").fetchone()[0] == 1
    assert not crumb.exists() and any("저장되지 않은 안전 상태" in t for t in tg.texts())


def test_unreadable_breadcrumb_fails_closed(tmp_path):
    cfg = config(tmp_path)
    crumb = cfg.var_dir / "run" / "safety_unsaved.json"
    crumb.parent.mkdir(parents=True, exist_ok=True)
    crumb.write_text("{broken")
    tg = FakeTelegram()
    assert run(cfg, clock=Clock(T0 + 10 * 60_000 + 1000), tg=tg, seconds=5) == 0
    body = json.loads(sqlite3.connect(cfg.db_path).execute(
        "SELECT state_json FROM safety_state ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert body["paused_by"] == "system:restart_with_unsaved_safety_state" and crumb.exists(), "해석 못 한 파일은 사람이 본다"


def _gate_state(*, tripped=None, paused_by=None):
    return {"paused_by": paused_by, "reconcile": {"blocker": None, "sticky": False},
            "kill_switch": {"tripped": tripped, "consecutive_losses": 0, "liquidations": 0, "vanished": 0,
                            "last_flat_wallet": "1000", "day": None, "day_start_equity": None, "resumed_by": None}}


def _db_with_state_rows(tmp_path):
    cfg = config(tmp_path)
    clock = Clock(T0 + 10 * 60_000 + 1000)
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=65) == 0          # DB에 safety_state 행이 생긴다
    con = sqlite3.connect(cfg.db_path)
    (last_id, last_ts) = con.execute("SELECT max(id), max(ts_ms) FROM safety_state").fetchone()
    return cfg, clock, con, last_id, last_ts


def test_a_breadcrumb_superseded_by_a_later_durable_save_is_quarantined_not_restored(tmp_path):
    """신선도는 **행 id**로 판정한다(시각 도메인이 섞이면 틀린다 · Codex L8 재검토 #3). 기준 id 뒤에 저장된 행이 있고
    breadcrumb에 DB에 없는 트립도 없으면 오래된 것."""
    cfg, clock, con, last_id, last_ts = _db_with_state_rows(tmp_path)
    crumb = cfg.var_dir / "run" / "safety_unsaved.json"
    crumb.write_text(json.dumps({"ts_ms": last_ts + 999_999, "base_state_id": last_id - 1,
                                 "safety_gate": _gate_state(paused_by="telegram:old"), "ops": []}))
    tg = FakeTelegram()
    clock.t += 60_000
    assert run(cfg, clock=clock, tg=tg, seconds=5) == 0
    body = json.loads(con.execute("SELECT state_json FROM safety_state ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert body["paused_by"] == "system:restart_with_unsaved_safety_state", "격리해도 진입은 멈춘다"
    assert not crumb.exists() and list((cfg.var_dir / "run").glob("safety_unsaved.stale-*.json"))
    assert any("오래된" in t for t in tg.texts())


def test_a_breadcrumb_trip_missing_from_the_db_is_always_restored(tmp_path):
    cfg, clock, con, last_id, last_ts = _db_with_state_rows(tmp_path)
    crumb = cfg.var_dir / "run" / "safety_unsaved.json"
    trip = {"ts_ms": 1, "reason": "liquidation", "detail": "unsaved"}
    crumb.write_text(json.dumps({"ts_ms": 1, "base_state_id": last_id - 1, "safety_gate": _gate_state(tripped=trip),
                                 "ops": []}))
    clock.t += 60_000
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    body = json.loads(con.execute("SELECT state_json FROM safety_state ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert body["kill_switch"]["tripped"]["reason"] == "liquidation", "트립은 fail-closed로 복원"


def test_codex_mixed_clock_scenario_a_newer_breadcrumb_with_an_older_event_ts_is_restored(tmp_path):
    """DB 최신 행은 벽시계(늦은 시각), breadcrumb는 시장 이벤트 시각(이른 시각) — 기준 id가 최신이면 복원."""
    cfg, clock, con, last_id, last_ts = _db_with_state_rows(tmp_path)
    crumb = cfg.var_dir / "run" / "safety_unsaved.json"
    trip = {"ts_ms": last_ts - 5000, "reason": "daily_loss", "detail": "db outage"}
    crumb.write_text(json.dumps({"ts_ms": last_ts - 5000, "base_state_id": last_id, "safety_gate": _gate_state(tripped=trip),
                                 "ops": []}))
    clock.t += 60_000
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    body = json.loads(con.execute("SELECT state_json FROM safety_state ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert body["kill_switch"]["tripped"]["reason"] == "daily_loss" and not crumb.exists()


def test_breadcrumb_replay_does_not_duplicate_events_already_in_the_db(tmp_path):
    cfg = config(tmp_path)
    clock = Clock(T0 + 10 * 60_000 + 1000)
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    con = sqlite3.connect(cfg.db_path)
    from db import record as R
    R.record_ops_event(con, "KillSwitchTripped", "x", ts_ms=T0, mode="paper", symbol="BTCUSDT",
                       payload={"reason": "daily_loss"}, op_id="op-1")                # 삽입 뒤 breadcrumb 갱신 전에 죽었다
    con.commit()
    state = json.loads(con.execute("SELECT state_json FROM safety_state ORDER BY id DESC LIMIT 1").fetchone()[0])
    crumb = cfg.var_dir / "run" / "safety_unsaved.json"
    crumb.write_text(json.dumps({"ts_ms": clock.t + 10_000, "safety_gate": state, "ops": [
        {"kind": "KillSwitchTripped", "detail": "x", "ts_ms": T0, "payload": {"reason": "daily_loss"}, "op_id": "op-1"}]}))
    clock.t += 60_000
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    assert con.execute("SELECT count(*) FROM engine_events WHERE kind='KillSwitchTripped'").fetchone()[0] == 1
    assert not crumb.exists()


def test_error_text_shown_to_humans_never_carries_signed_request_material():
    """Codex L8b #3: ccxt 네트워크 예외는 전체 URL(쿼리의 signature·timestamp·recvWindow)을 담는다."""
    e = RuntimeError("binanceusdm GET https://fapi.binance.com/fapi/v1/leverageBracket?symbol=BTCUSDT&timestamp=1789&"
                     "recvWindow=5000&signature=abcdef0123 headers {'X-MBX-APIKEY': 'dummy-key-AAAA'} dummy-secret-BBBB")
    text = RB.safe_error(e, secrets=list(KEYS.values()))
    for bad in ("signature", "abcdef0123", "timestamp=", "recvWindow", "dummy-key-AAAA", "dummy-secret-BBBB", "?symbol"):
        assert bad not in text, bad
    assert text.startswith("RuntimeError") and "fapi.binance.com/fapi/v1/leverageBracket" in text


def test_signed_client_checks_permissions_before_any_other_keyed_request():
    """Codex L8b #4: 키를 실은 클라이언트의 첫 요청은 apiRestrictions — 시각 동기화는 키 없는 클라이언트로."""
    log: list[tuple] = []

    class FakeCcxt:
        def __init__(self, *, api_key=None, secret=None, **kw):
            self.keyed = api_key is not None
            self.ex = SimpleNamespace(options={})
            log.append(("init", self.keyed))

        def sync_time(self):
            log.append(("sync_time", self.keyed))
            self.ex.options["timeDifference"] = 7
            return 7

        def get(self, path, params=None, *, signed=False):
            log.append(("get", self.keyed, path))
            if path == "/sapi/v1/account/apiRestrictions":
                return Response(200, READ_ONLY | {"enableFutures": True})
            raise AssertionError(f"권한 확인 전 요청 {path}")

    import pytest as _pytest
    with _pytest.raises(RB.NotReadOnlyKey):
        client = RB.signed_client_from_keys(KEYS["BINANCE_API_KEY"], KEYS["BINANCE_API_SECRET"], client_cls=FakeCcxt)
        RB.check_permissions(client)
    keyed = [c for c in log if c[0] != "init" and c[1]]
    assert keyed == [("get", True, "/sapi/v1/account/apiRestrictions")]
    assert ("sync_time", False) in log


def test_signed_lookup_transport_error_alert_and_status_are_sanitised(tmp_path, capsys):
    from exchange.errors import TransportError

    class Leaky(FakeSigned):
        def get(self, path, params=None, *, signed=False):
            if path == "/fapi/v1/leverageBracket":
                raise TransportError(f"GET {path}: RequestTimeout: binanceusdm GET https://fapi.binance.com{path}?"
                                     f"timestamp=1&recvWindow=5000&signature=deadbeef {KEYS['BINANCE_API_KEY']}")
            return super().get(path, params, signed=signed)

    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    tg = FakeTelegram()
    assert run(cfg, clock=clock, tg=tg, seconds=5, signed=Leaky()) == 0
    blob = cfg.status_path.read_text() + " ".join(tg.texts()) + "".join(capsys.readouterr())
    assert "rules_from_snapshot" in blob
    for bad in ("deadbeef", "signature", KEYS["BINANCE_API_KEY"]):
        assert bad not in blob, bad


def test_dryrun_harness_strips_binance_keys_from_child_environments_unless_asked():
    import importlib
    H = importlib.import_module("scripts.dryrun_restart_restore")
    base = {"PATH": "/bin", **KEYS, "TELEGRAM_BOT_TOKEN": "t"}
    assert set(H.child_env(base, use_key=False)) == {"PATH", "TELEGRAM_BOT_TOKEN"}
    assert H.child_env(base, use_key=True) == base


@pytest.mark.parametrize("message", [
    '{"signature":"deadbeef","timestamp":1789,"recvWindow":5000}',
    "{'signature': 'deadbeef', 'timestamp': 1789, 'recvWindow': 5000}",
    "signature: deadbeef timestamp: 1789 recvwindow: 5000",
    "GET /fapi/v1/leverageBracket?timestamp=1789&recvWindow=5000&signature=deadbeef",
    "x-mbx-apikey: dummy-key-AAAA signature=deadbeef",
])
def test_safe_error_also_strips_json_colon_and_schemeless_signed_fields(message):
    """Codex L8b 재검토 #3 PARTIAL: JSON·콜론 형식 · 스킴 없는 경로의 쿼리."""
    text = RB.safe_error(RuntimeError(message), secrets=list(KEYS.values()))
    for bad in ("deadbeef", "1789", "5000", "dummy-key-AAAA"):
        assert bad not in text, (message, text)


@pytest.mark.parametrize("junk", ["/" * 40_000, "a/" * 20_000, "/a" * 20_000 + "?", "signature=" * 10_000])
def test_safe_error_stays_linear_on_pathological_text(junk):
    """Codex L8b 재검토 #2: 스킴 없는 경로 정규식이 긴 `/` 문자열에서 초선형이었다."""
    t = time.perf_counter()
    RB.safe_error(RuntimeError(junk + " signature=deadbeef"), secrets=list(KEYS.values()))
    assert time.perf_counter() - t < 0.2


# ── 직전 실행 비정상 종료(사용자 2026-09-16) ───────────────────────────────────────
def _dirty_events(var: Path) -> list[tuple]:
    con = sqlite3.connect(var / "manifest.sqlite")
    return con.execute("SELECT source, kind FROM events WHERE kind IN ('start','stop','stop_dirty','dirty_previous_run') "
                       "ORDER BY id").fetchall()


def test_a_previous_run_with_start_or_connect_but_no_stop_is_recorded_as_dirty_exactly_once(tmp_path):
    """SIGKILL은 대장에 `stop`도 `stop_dirty`도 남기지 않는다 — dirty-stop 검사가 공짜로 통과하면 안 된다."""
    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    status = json.loads(cfg.status_path.read_text())
    assert status["confirmed_facts"] == [], "첫 실행(대장 비어 있음)과 깨끗한 직전 실행은 dirty가 아니다"
    manifest.log_event(RB.RUN_EVENT_SOURCE, "start", "run 2 (SIGKILL 흉내)")
    manifest.log_event("feed", "connect", "wss://… (SIGKILL 흉내)")
    clock.t += 60_000
    tg = FakeTelegram()
    assert run(cfg, clock=clock, tg=tg, seconds=5) == 0
    starts = [t for t in tg.texts() if t.startswith("🟢 기동")]
    assert len(starts) == 1 and "dirty_previous_run" in starts[0], "사용자 2026-09-16: 기동 알림에 한 줄 언급(health 알림과 별개)"
    assert not [t for t in tg.texts() if "dirty_previous_run" in t and not t.startswith("🟢 기동")], "봇이 따로 보내지 않는다"
    status = json.loads(cfg.status_path.read_text())
    facts = [f for f in status["confirmed_facts"] if f["kind"] == "dirty_previous_run"]
    assert len(facts) == 1 and facts[0]["daily"] is False and facts[0]["date"]
    con = sqlite3.connect(cfg.db_path)
    assert con.execute("SELECT count(*) FROM engine_events WHERE kind='DirtyPreviousRun'").fetchone()[0] == 1
    clock.t += 60_000
    tg3 = FakeTelegram()
    assert run(cfg, clock=clock, tg=tg3, seconds=5) == 0
    assert not any("dirty_previous_run" in t for t in tg3.texts() if t.startswith("🟢 기동")), "새로 판정한 기동에서만 언급"
    kinds = [k for _s, k in _dirty_events(cfg.var_dir)]
    assert kinds.count("dirty_previous_run") == 1, "표시한 뒤의 재기동은 다시 dirty로 세지 않는다"
    assert kinds[-2:] == ["start", "stop"]
    status = json.loads(cfg.status_path.read_text())
    assert [f["id"] for f in status["confirmed_facts"]] == [facts[0]["id"]], "24시간 안에는 같은 키로 남는다(health가 한 번만 보낸다)"


def test_a_previous_stop_dirty_is_not_double_counted(tmp_path):
    clock = Clock(T0 + 10 * 60_000 + 1000)
    cfg = config(tmp_path)
    manifest.log_event(RB.RUN_EVENT_SOURCE, "start", "x")
    manifest.log_event("feed", "stop_dirty", "writer 제한 시간 내 미완료")
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    assert "dirty_previous_run" not in [k for _s, k in _dirty_events(cfg.var_dir)], "stop_dirty는 이미 기록된 dirty다"


def test_ops_events_in_a_superseded_breadcrumb_are_still_replayed(tmp_path):
    """Codex 배포 전 재검토 #1: 게이트 상태가 오래돼 격리하는 breadcrumb라도 그 안의 **운영 이벤트**(예: NoticeAcknowledged)는
    op_id 멱등으로 재생한다 — 상태만 오래됐지 이벤트는 사실이다."""
    cfg, clock, con, last_id, last_ts = _db_with_state_rows(tmp_path)
    crumb = cfg.var_dir / "run" / "safety_unsaved.json"
    op = {"kind": "NoticeAcknowledged", "detail": "restart_unrestored 7 (telegram:111)", "ts_ms": last_ts,
          "payload": {"kind": "restart_unrestored", "id": "7", "actor": "telegram:111"}, "op_id": "ack-7"}
    crumb.write_text(json.dumps({"ts_ms": last_ts, "base_state_id": last_id - 1, "safety_gate": _gate_state(), "ops": [op]}))
    clock.t += 60_000
    assert run(cfg, clock=clock, tg=FakeTelegram(), seconds=5) == 0
    assert list((cfg.var_dir / "run").glob("safety_unsaved.stale-*.json")), "상태는 여전히 격리"
    rows = con.execute("SELECT payload_json FROM engine_events WHERE kind='NoticeAcknowledged'").fetchall()
    assert len(rows) == 1 and json.loads(rows[0][0])["id"] == "7"
