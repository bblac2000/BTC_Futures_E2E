"""layer 8 런타임 — 피드 → 엔진 → DB → 안전 게이트 → 텔레그램(사용자 2026-09-16 · 레지스트리 #11·#12·#13).

실제 소켓·HTTP 없이 가짜 틱·봉·가짜 LIVE 송신기로 한 소유자 루프의 규칙을 잠근다:
- 진입 게이트 하나(엔진 ∪ 안전 ∪ DB) · 게이트가 닫히면 대기 진입 취소 기록
- stale grace 초과 → STALE_DATA 청산(PAPER는 마지막 mark) · 청산마다 알림 · 정지 동안 진입 금지
- 봉마다 기록·대사·equity·스냅샷 · 상태는 바뀔 때만 저장
- LIVE 거래소 flat → 주문 없이 vanish → 거래소 지갑 재동기화 + flat 지갑 이동 · 부분 청산 뒤 대사가 스스로 맞는다
- 컨트롤러: /pause · /start(일일 손실 날 무변경 문구) · /close · /status(모든 차단 사유)
"""
from __future__ import annotations

import dataclasses as dc
import json
import sqlite3
from decimal import Decimal

import pytest

from data.feed import KlineEvent
from db import migrate as M
from db import record as R
from exchange.gate import Mode
from exchange.orders import Side
from notify.bot import CommandBot, Send
from ops.delivery_counter import DeliveryCounter
from ops.runtime import BotRuntime, ExchangeAccount
from paper.engine import Engine, EntryRefused
from paper.sender import PaperSender
from paper.types import ExitReason, MarkTick, PositionRisk
from safety import config as SC
from safety.gate import SafetyGate
from safety.killswitch import KillSwitch
from safety.reconcile import ReconcileGuard
from safety.stale import StaleDataGuard
from sizing.config import SizingLimits
from sizing.position import size_entry
from tests.test_paper_engine import FlakyLive, SpySender, intent, next_funding

D = Decimal
DAY0 = 1_789_430_400_000
H = 3_600_000
STREAMS = ("kline1m_update", "kline1m_close", "markprice")
OWNER = 111


class Clock:
    def __init__(self, t: int):
        self.t = t

    def __call__(self) -> int:
        return self.t


def tick(ts: int, mark: str = "60000") -> MarkTick:
    return MarkTick(ts, D(mark), D("0.0001"), next_funding(ts))


def kline(open_ms: int, *, close="60000", closed=True) -> KlineEvent:
    c = D(close)
    return KlineEvent(open_ms + 59_999, open_ms, open_ms + 59_999, c, c, c, c, D("1"), c, 10, D("0.5"), c / 2, closed)


def build(rules, *, mode=Mode.PAPER, sender=None, exchange=None, limits=SC.REGISTERED_KILL_SWITCH, t0=DAY0, tmp=None):
    con = sqlite3.connect(":memory:")
    M.migrate(con)
    counter = DeliveryCounter(STREAMS, start_ms=t0)
    engine = Engine(rules, sender or PaperSender(rules), mode=mode, wallet=D("1000"), limits=SizingLimits())
    gate = SafetyGate(KillSwitch(limits, wallet=D("1000")), StaleDataGuard(counter), ReconcileGuard())
    clock = Clock(t0)
    rt = BotRuntime(engine=engine, gate=gate, con=con, symbol="BTCUSDT", clock_ms=clock, exchange=exchange,
                    status_path=None if tmp is None else tmp / "status.json")
    return rt, counter, clock


def feed(rt: BotRuntime, counter: DeliveryCounter, clock: Clock, t0: int, t1: int, mark="60000", *, bars=True):
    """[t0, t1) 1초마다 mark 틱 + kline push · 분 경계에서 마감 봉 · safety_tick."""
    for t in range(t0, t1, 1000):
        clock.t = t
        counter.observe("markprice", t)
        counter.observe("kline1m_update", t)
        rt.on_mark(tick(t, mark))
        if bars and t % 60_000 == 59_000:
            counter.observe("kline1m_close", t + 999)
            rt.on_kline(kline(t - 59_000, close=mark))
        rt.safety_tick(t)


def texts(rt: BotRuntime) -> list[str]:
    out = []
    while not rt.outbox.empty():
        a = rt.outbox.get_nowait()
        if isinstance(a, Send):
            out.append(a.text)
    return out


def attach_bot(rt: BotRuntime, clock: Clock) -> CommandBot:
    from notify.poller import TelegramPoller
    nonces = iter(f"{i:016x}" for i in range(1, 100))
    rt.bot = CommandBot(rt, owner_ids=frozenset({OWNER}), started_ms=DAY0, nonce=lambda: next(nonces))
    rt.poller = TelegramPoller(None, rt.bot, clock_ms=clock)
    return rt.bot


def rows(rt: BotRuntime, sql: str) -> list[tuple]:
    return rt.con.execute(sql).fetchall()


# ── 기본 흐름 ────────────────────────────────────────────────────────────────
def test_ticks_bars_and_an_entry_flow_into_the_db_with_snapshots_and_alerts(rules):
    rt, counter, clock = build(rules)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    assert rt.entry_blockers() == [], "피드가 건강하면 진입 허용"
    rt.submit_entry(intent(decided_ms=DAY0 + 60_000))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 121_000)
    assert rt.engine.position is not None
    assert rows(rt, "SELECT count(*) FROM positions WHERE event='open'") == [(1,)]
    assert rows(rt, "SELECT source, count(*) FROM bars_1m GROUP BY source") == [("ws", 2)]
    reasons = [json.loads(r[0])["reason"] for r in rows(rt, "SELECT raw_json FROM account_snapshots WHERE source='engine'")]
    assert reasons.count("bar") == 2 and "EntryFilled" in reasons
    assert any(t.startswith("📈 진입") for t in texts(rt))
    assert rt.gate.reconcile.blocker is None and rt.last_reconcile_detail is not None


def test_entry_gate_is_the_union_of_engine_safety_and_db_blockers(rules):
    rt, counter, clock = build(rules)
    feed(rt, counter, clock, DAY0, DAY0 + 5000)
    rt.engine._block(DAY0, "주문 결과 불명")
    rt.gate.pause("telegram:111")
    rt.unrecorded.append(([], None))
    b = rt.entry_blockers()
    assert b[0] == "engine:주문 결과 불명" and "paused:telegram:111" in b and any(x.startswith("db:") for x in b)
    with pytest.raises(EntryRefused) as ei:
        rt.submit_entry(intent(decided_ms=DAY0 + 5000))
    assert "engine:" in str(ei.value) and "paused" in str(ei.value)


def test_pending_entry_is_cancelled_and_recorded_when_the_gate_closes_before_execution(rules):
    rt, counter, clock = build(rules)
    feed(rt, counter, clock, DAY0, DAY0 + 5000)
    rt.submit_entry(intent(decided_ms=DAY0 + 5000))
    rt.pause_entries("telegram:111")
    assert rt.engine.pending is None
    assert rows(rt, "SELECT outcome, skip_reason FROM decisions") == [("skipped", "entries_blocked")]


# ── stale (레지스트리 #12) ─────────────────────────────────────────────────────
def test_stale_past_grace_closes_the_position_at_the_last_mark_alerts_and_blocks_until_healthy(rules):
    rt, counter, clock = build(rules)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(intent(decided_ms=DAY0 + 60_000))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 63_000, mark="60050")
    assert rt.engine.position is not None
    texts(rt)
    last = DAY0 + 62_000
    counter.observe("kline1m_close", last)                          # 세 스트림 모두 같은 시각에 끊긴 것으로
    for t in range(last + 1000, last + 120_001, 1000):             # 무수신 — 나이 ≤ 120초: 진입 금지만
        clock.t = t
        rt.safety_tick(t)
    assert rt.engine.position is not None and any(b.startswith("stale") for b in rt.entry_blockers())
    clock.t = last + 120_001
    rt.safety_tick(last + 120_001)                                  # grace 초과 → 청산
    assert rt.engine.position is None and rt.counts["stale_closes"] == 1
    (reason, exit_px) = rows(rt, "SELECT reason, exit_price FROM positions WHERE event='close'")[0]
    (ref,) = rows(rt, "SELECT ref_mark FROM orders WHERE intent='exit'")[0]
    assert reason == "stale_data" and ref == "60050", "PAPER stale 청산 기준가 = 마지막으로 받은 mark"
    msgs = texts(rt)
    assert any("stale 청산" in m and "레지스트리 #12" in m for m in msgs)
    assert rows(rt, "SELECT kind FROM engine_events WHERE kind='StaleClose'") == [("StaleClose",)]
    assert any(b.startswith("stale") for b in rt.entry_blockers()), "청산 뒤에도 피드가 회복될 때까지 진입 금지"


def test_stale_close_failure_retries_every_tick_and_alerts_once_per_distinct_failure(rules):
    s = SpySender(PaperSender(rules))
    rt, counter, clock = build(rules, sender=s)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(intent(decided_ms=DAY0 + 60_000))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 63_000)
    texts(rt)
    sends = len([c for c in s.calls if c[0] == "send"])
    s.unknown_on_send = sends + 1
    base = DAY0 + 62_000 + 120_001
    for i in range(3):
        clock.t = base + i * 1000
        if i == 1:
            s.unknown_on_send = sends + 2                          # 같은 문구의 실패 반복
        if i == 2:
            s.unknown_on_send = None
        rt.safety_tick(clock.t)
    assert rt.engine.position is None and rt.counts["stale_closes"] == 3
    fails = [m for m in texts(rt) if "stale 청산 실패" in m]
    assert len(fails) == 1


# ── 봉마다 · 킬스위치 · 상태 저장 ──────────────────────────────────────────────
def test_daily_loss_at_bar_close_trips_records_alerts_and_persists_once(rules):
    rt, counter, clock = build(rules)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    saved = rows(rt, "SELECT count(*) FROM safety_state")[0][0]
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 181_000)
    assert rows(rt, "SELECT count(*) FROM safety_state")[0][0] == saved, "상태가 안 바뀌면 저장하지 않는다"
    rt.engine.wallet = D("949")                                     # 5% 손실(레지스트리 #11)
    feed(rt, counter, clock, DAY0 + 181_000, DAY0 + 241_000)
    assert rt.gate.kill_switch.tripped is not None and rt.gate.kill_switch.tripped.reason == "daily_loss"
    assert rows(rt, "SELECT kind FROM engine_events WHERE kind='KillSwitchTripped'") == [("KillSwitchTripped",)]
    assert any("킬스위치 발동" in m for m in texts(rt))
    back = SafetyGate.load(rt.con, SC.REGISTERED_KILL_SWITCH, StaleDataGuard(counter), mode="paper", wallet=D("1"))
    assert back.kill_switch.tripped is not None


def test_start_on_the_daily_loss_day_changes_nothing_and_says_so(rules):
    rt, counter, clock = build(rules)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.pause_entries("telegram:111")
    rt.engine._block(DAY0, "대사 필요")
    rt.engine.wallet = D("900")
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 121_000)
    before = rt.entry_blockers()
    clock.t = DAY0 + 2 * H
    text = rt.resume("telegram:111")
    assert "blocked by daily-loss limit until 00:00 UTC" in text and rt.entry_blockers() == before
    clock.t = DAY0 + 24 * H + 5
    text = rt.resume("telegram:111")
    assert "엔진 차단 해제: 대사 필요" in text and rt.engine.entries_blocked == [] and rt.gate.paused_by is None
    assert rt.gate.kill_switch.tripped is None


def test_status_lists_every_active_blocker_with_its_reason(rules):
    rt, counter, clock = build(rules)
    feed(rt, counter, clock, DAY0, DAY0 + 5000)
    rt.engine._block(DAY0, "펀딩 경계 정산 불가")
    rt.gate.pause("telegram:111")
    rt.gate.kill_switch.trip(DAY0, "liquidation", "청산 1회")
    text = rt.status_text()
    for b in ("engine:펀딩 경계 정산 불가", "paused:telegram:111", "kill_switch:liquidation"):
        assert b in text
    assert "신규 진입 금지" in text


# ── LIVE: 소실 · 지갑 재동기화 · 부분 청산 뒤 대사 ────────────────────────────
class FakeReader:
    def __init__(self, sender, wallet="1000"):
        self.sender, self.wallet, self.fail_account = sender, D(wallet), False

    def position_risk(self) -> PositionRisk:
        return PositionRisk(self.sender.exchange_amt or D("0"), self.sender.exchange_entry, D("0"))

    def account(self) -> ExchangeAccount:
        if self.fail_account:
            raise TimeoutError("account timeout")
        return ExchangeAccount(self.wallet, self.wallet, self.wallet, D("0"), D("0"), {"assets": [{"asset": "USDT"}]})


def test_live_exchange_flat_under_an_open_position_vanishes_without_orders_and_resyncs_the_wallet(rules):
    s = FlakyLive(PaperSender(rules), mode=Mode.LIVE)
    reader = FakeReader(s)
    rt, counter, clock = build(rules, mode=Mode.LIVE, sender=s, exchange=reader)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    q = size_entry(PaperSender(rules).quote_fill_price(Side.BUY, D("60000")), intent().sl, intent().direction, D("1000"),
                   intent().regime, rules, SizingLimits()).qty
    s.exchange_amt = q
    rt.submit_entry(intent(decided_ms=DAY0 + 60_000))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 121_000)
    assert rt.engine.position is not None and rt.gate.reconcile.blocker is None
    sends = len([c for c in s.calls if c[0] == "send"])
    s.exchange_amt = D("0")                                          # 거래소가 청산했다
    reader.wallet = D("962.5")
    reader.fail_account = True
    feed(rt, counter, clock, DAY0 + 121_000, DAY0 + 181_000)
    assert rt.engine.position is None and len([c for c in s.calls if c[0] == "send"]) == sends, "주문 없음"
    assert rt.gate.kill_switch.tripped is not None and rt.gate.kill_switch.tripped.reason == "position_vanished"
    assert "exchange:wallet_resync_due" in rt.entry_blockers(), "지갑 조회 실패 → 다음 봉 재시도 · 진입 금지"
    reader.fail_account = False
    feed(rt, counter, clock, DAY0 + 181_000, DAY0 + 241_000)
    assert rt.engine.wallet == D("962.5") and rt.gate.kill_switch.last_flat_wallet == D("962.5")
    assert "exchange:wallet_resync_due" not in rt.entry_blockers()
    assert rows(rt, "SELECT reason FROM positions WHERE event='close'") == [("vanished",)]
    assert rows(rt, "SELECT kind FROM engine_events WHERE kind='WalletResynced'") == [("WalletResynced",)]
    assert rows(rt, "SELECT count(*) FROM account_snapshots WHERE source='exchange'")[0][0] >= 1
    assert rt.gate.reconcile.blocker is None, "vanish가 대사 전에 내부를 0으로 — 수량 불일치 sticky가 남지 않는다"


def test_partial_close_lets_reconcile_clear_on_its_own(rules):
    r2 = dc.replace(rules, symbol_rules=dc.replace(rules.symbol_rules, market_max_qty=D("0.010")))
    s = SpySender(PaperSender(r2))
    rt, counter, clock = build(r2, sender=s)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(intent(sl="59820", risk="0.02", decided_ms=DAY0 + 60_000))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 62_000)
    s.unknown_on_send = len([c for c in s.calls if c[0] == "send"]) + 2
    clock.t = DAY0 + 62_500
    text = rt.close_all("telegram:111")
    assert "청산 실패" in text and rt.engine.position is not None
    feed(rt, counter, clock, DAY0 + 63_000, DAY0 + 121_000)
    assert rt.gate.reconcile.blocker is None, "DB 남은 수량 = 엔진 잔량 → 사람 없이 대사 일치"
    assert any(b.startswith("engine:") for b in rt.entry_blockers()), "주문 결과 불명 차단은 사람이 푼다"


# ── DB 실패 · 텔레그램 · 상태 파일 ────────────────────────────────────────────
def test_db_write_failure_blocks_entries_keeps_events_and_retries(rules):
    rt, counter, clock = build(rules)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(intent(decided_ms=DAY0 + 60_000))
    real = rt.con
    broken = sqlite3.connect(":memory:")                              # 표 없음 → OperationalError
    rt.con = broken
    clock.t = DAY0 + 61_000
    counter.observe("markprice", clock.t)
    rt.on_mark(tick(clock.t))
    assert rt.engine.position is not None and rt.unrecorded and any(b.startswith("db:") for b in rt.entry_blockers())
    assert any("DB 기록 실패" in m for m in texts(rt))
    rt.con = real
    rt.safety_tick(clock.t)
    assert not rt.unrecorded and rows(rt, "SELECT count(*) FROM positions WHERE event='open'") == [(1,)]


def test_telegram_close_confirm_runs_on_the_loop_thread_via_the_inbox(rules):
    from tests.test_notify_bot import cb, msg
    rt, counter, clock = build(rules)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(intent(decided_ms=DAY0 + 60_000))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 63_000)
    texts(rt)
    rt.inbox.put(msg("/close", user=OWNER, uid=1))
    rt.safety_tick(clock.t)
    assert rt.bot is not None and rt.bot.pending is not None and rt.engine.position is not None
    rt.inbox.put(cb(f"cf:{rt.bot.pending.nonce}:y", user=OWNER, uid=2))
    clock.t += 1000
    rt.safety_tick(clock.t)
    assert rt.engine.position is None
    assert any(t.startswith("청산 완료") for t in texts(rt))
    assert rows(rt, "SELECT reason FROM positions WHERE event='close'") == [("manual",)]


def test_status_file_is_written_atomically_with_blockers_and_delivery(rules, tmp_path):
    rt, counter, clock = build(rules, tmp=tmp_path)
    feed(rt, counter, clock, DAY0, DAY0 + 3000)
    body = json.loads((tmp_path / "status.json").read_text())
    assert body["mode"] == "paper" and body["entries_allowed"] is True and set(body["delivery"]) == set(STREAMS)
    assert body["counts"]["ticks"] == 3 and not (tmp_path / "status.tmp").exists()


def test_paper_runtime_refuses_an_exchange_reader_and_live_requires_one(rules):
    with pytest.raises(ValueError):
        build(rules, exchange=FakeReader(None))
    with pytest.raises(ValueError):
        build(rules, mode=Mode.LIVE, sender=FlakyLive(PaperSender(rules), mode=Mode.LIVE))


def test_bar_conflicts_are_alerted_not_overwritten(rules):
    rt, counter, clock = build(rules)
    attach_bot(rt, clock)
    rt.on_kline(kline(DAY0, close="60000"))
    rt.on_kline(kline(DAY0, close="60001"))
    assert rt.bar_conflicts == 1 and any("값 충돌" in m for m in texts(rt))
    assert rows(rt, "SELECT close FROM bars_1m") == [("60000",)]


def test_stale_data_reason_value_is_the_registry_12_tag():
    assert ExitReason.STALE_DATA.value == "stale_data" and R.MODES == ("paper", "live")


# ── Codex L8 #1: 킬스위치·운영 이벤트·안전 상태 저장도 DB 실패에서 살아남아야 한다 ──────────────
def test_kill_switch_trip_during_a_db_outage_is_retried_and_blocks_until_durable(rules):
    rt, counter, clock = build(rules)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    real = rt.con
    rt.con = sqlite3.connect(":memory:")                               # 표 없음 → 모든 쓰기 실패
    rt.engine.wallet = D("900")
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 121_000)
    assert rt.gate.kill_switch.tripped is not None
    b = rt.entry_blockers()
    assert "db:unsaved_safety_state" in b and any(x.startswith("db:unrecorded_ops") for x in b) and "db:read_failed" in b
    rt.con = real
    clock.t += 1000
    rt.safety_tick(clock.t)
    assert rt.entry_blockers().count("db:read_failed") == 1 and not rt.unrecorded_ops and not rt.state_save_failed
    feed(rt, counter, clock, DAY0 + 121_000, DAY0 + 181_000)            # 다음 봉에서 읽기 성공 → 해제
    assert not any(x.startswith("db:") for x in rt.entry_blockers())
    back = SafetyGate.load(real, SC.REGISTERED_KILL_SWITCH, StaleDataGuard(counter), mode="paper", wallet=D("1"))
    assert back.kill_switch.tripped is not None and back.kill_switch.tripped.reason == "daily_loss"
    assert rows(rt, "SELECT kind FROM engine_events WHERE kind='KillSwitchTripped'") == [("KillSwitchTripped",)]


# ── Codex L8 #4: 폴 스레드는 봇 상태를 읽지 않는다 — 루프 스레드가 세우는 플래그만 ─────────────────
def test_fast_poll_flag_is_owned_by_the_loop_thread(rules):
    from tests.test_notify_bot import msg
    rt, counter, clock = build(rules)
    attach_bot(rt, clock)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(intent(decided_ms=DAY0 + 60_000))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 62_000)
    assert not rt.fast_poll.is_set()
    rt.inbox.put(msg("/close", user=OWNER, uid=1))
    rt.safety_tick(clock.t)
    assert rt.fast_poll.is_set(), "확인 대기 중 → 빠른 폴링"
    for t in range(clock.t + 1000, clock.t + 14_000, 1000):
        clock.t = t
        rt.safety_tick(t)
    assert rt.bot is not None and rt.bot.pending is None and not rt.fast_poll.is_set()


# ── Codex L8 재검토 #1 잔여: DB가 안 되는 채로 재기동해도 트립을 잃지 않는다(DB 밖 breadcrumb) ─────────
def test_unsaved_safety_state_leaves_a_breadcrumb_outside_the_db_until_durable(rules, tmp_path):
    rt, counter, clock = build(rules, tmp=tmp_path)
    crumb_path = rt.breadcrumb_path = tmp_path / "safety_unsaved.json"
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    real = rt.con
    rt.con = sqlite3.connect(":memory:")
    rt.engine.wallet = D("900")
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 121_000)
    crumb = json.loads(crumb_path.read_text())
    assert crumb["safety_gate"]["kill_switch"]["tripped"]["reason"] == "daily_loss"
    assert [o["kind"] for o in crumb["ops"]] == ["KillSwitchTripped"]
    assert crumb["base_state_id"] == real.execute("SELECT max(id) FROM safety_state").fetchone()[0], "마지막 durable 행 id"
    rt.con = real
    clock.t += 1000
    rt.safety_tick(clock.t)
    assert not crumb_path.exists(), "DB에 저장된 뒤에만 지운다"
