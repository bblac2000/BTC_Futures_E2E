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

import pytest

from data import manifest
from data.feed import KlineEvent
from exchange.client_types import Response
from exchange.gate import Mode
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


def run(cfg, *, clock, tg=None, seconds=125, env=None, public=None):
    env = {"TELEGRAM_OWNER_IDS": str(OWNER), "TELEGRAM_BOT_TOKEN": "x"} if env is None else env

    def factory(counter, rt, recorder):
        return ReplayFeed(counter, rt, clock, start=clock.t, seconds=seconds)

    async def fast_sleep(_s):
        await asyncio.sleep(0)

    return asyncio.run(RB.run(cfg, env=env, clock_ms=clock, public_client=public or FakePublic(clock.t),
                              feed_factory=factory, telegram_api=tg, sleep=fast_sleep))


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
    assert {r[0] for r in con.execute("SELECT endpoint FROM runtime_rules")} == set(RB.REQUIRED)
    assert con.execute("SELECT count(*) FROM account_snapshots WHERE source='engine'").fetchone()[0] >= 3
    assert con.execute("SELECT kind FROM engine_events WHERE kind='Backfill'").fetchall() == [("Backfill",)]
    status = json.loads(cfg.status_path.read_text())
    assert status["shutdown"] == "stop" and status["exit_code"] == 0 and status["counts"]["bars"] == 2
    texts = tg.texts()
    assert any(t.startswith("🟢 기동 [paper]") and "exchangeInfo=rest" in t and "leverageBracket=snapshot" in t
               for t in texts)
    assert any(t.startswith("⚪ 정지 [paper] stop") for t in texts)
    assert ("set_my_commands", 8) in tg.calls
    assert not cfg.lock_path.exists() or cfg.lock_path.read_text()                  # 락 파일은 남아도 잠금은 풀렸다
    ev = sqlite3.connect(tmp_path / "var" / "manifest.sqlite").execute("SELECT kind FROM events").fetchall()
    assert ("stop",) in ev


def test_restart_restores_the_wallet_and_flags_an_unrestored_open_position(tmp_path):
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
    assert any("재기동: DB에 열린 포지션 LONG 0.01" in t for t in texts)


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
