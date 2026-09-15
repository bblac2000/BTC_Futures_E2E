"""PAPER 재기동 복원(사용자 결정 2026-09-16 (a)).

- DB의 열린 root 포지션 + **마지막 엔진 스냅샷**이 일치할 때만 엔진에 복원한다 → 진입은 다시 허용된다.
- 하나라도 다르면(스냅샷 없음·더 오래됨·수량/가격/레버리지/SL/TP/펀딩 불일치·한쪽만 포지션) flat으로 시작 · 진입 금지
  (`system:restart_position_mismatch`, 사람의 /start) · 알림 · DB의 고아 포지션은 `restart_unrestored` close 행으로 닫는다
  (그래야 대사가 영구히 sticky로 남지 않는다 — 손익은 추정하지 않는다).
- 판단 모양은 LIVE 채택과 같다: 출처를 대조하고 일치할 때만 채택, 아니면 flat + 차단 + 알림.
- 내려가 있던 동안 펀딩 경계를 지났으면 율을 모른다 → 첫 틱에서 `FundingMissed` + 진입 차단(피드 공백과 같은 규칙).
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from db import migrate as M
from exchange.gate import Mode
from ops import restore as RS
from ops.delivery_counter import DeliveryCounter
from ops.runtime import BotRuntime
from paper.engine import Engine, EntryRefused
from paper.sender import PaperSender
from paper.types import FundingMissed, PositionRestored
from safety import config as SC
from safety.gate import SafetyGate
from safety.killswitch import KillSwitch
from safety.reconcile import ReconcileGuard
from safety.stale import StaleDataGuard
from sizing.config import SizingLimits
from tests.test_ops_runtime import STREAMS, Clock, attach_bot, feed, texts, tick
from tests.test_paper_engine import intent, next_funding

D = Decimal
DAY0 = 1_789_430_400_000
H = 3_600_000


def build_file(rules, db: Path, *, t0: int, wallet: str = "1000"):
    con = sqlite3.connect(db)
    M.migrate(con)
    counter = DeliveryCounter(STREAMS, start_ms=t0)
    engine = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D(wallet), limits=SizingLimits())
    gate = SafetyGate(KillSwitch(SC.REGISTERED_KILL_SWITCH, wallet=D(wallet)), StaleDataGuard(counter), ReconcileGuard())
    clock = Clock(t0)
    rt = BotRuntime(engine=engine, gate=gate, con=con, symbol="BTCUSDT", clock_ms=clock)
    return rt, counter, clock


def open_then_crash(rules, db: Path, *, t0: int = DAY0) -> int:
    """진입 체결 → 봉 1개 더 → **정지 절차 없이** 연결만 닫는다(SIGKILL과 같은 DB 상태). 마지막 시각을 돌려준다."""
    rt, counter, clock = build_file(rules, db, t0=t0)
    feed(rt, counter, clock, t0, t0 + 61_000)
    rt.submit_entry(intent(decided_ms=t0 + 60_000))
    feed(rt, counter, clock, t0 + 61_000, t0 + 121_000)
    assert rt.engine.position is not None
    rt.con.close()
    return t0 + 121_000


def restart(rules, db: Path, *, t0: int):
    rt, counter, clock = build_file(rules, db, t0=t0)
    attach_bot(rt, clock)
    decision = RS.decide_paper_restore(rt.con, mode="paper", symbol="BTCUSDT")
    msgs = RS.apply_restore(rt, decision, t0)
    return rt, counter, clock, decision, msgs


def last_snapshot_raw(con: sqlite3.Connection) -> tuple[int, dict]:
    sid, raw = con.execute("SELECT id, raw_json FROM account_snapshots WHERE source='engine' ORDER BY id DESC LIMIT 1").fetchone()
    return sid, json.loads(raw)


# ── 엔진 ────────────────────────────────────────────────────────────────────
def test_engine_position_state_round_trips_and_restore_refuses_when_occupied(rules):
    e = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    assert e.position_state() is None
    e.request_entry(intent(decided_ms=DAY0))
    e.on_tick(tick(DAY0 + 1000))
    st = e.position_state()
    assert st is not None and st["direction"] == "LONG" and st["next_funding_ms"] == next_funding(DAY0 + 1000)
    assert json.loads(json.dumps(st)) == st, "스냅샷 raw_json에 그대로 들어간다(문자열·정수만)"
    with pytest.raises(EntryRefused):
        e.restore_position(st, ts_ms=DAY0 + 2000, detail="x")
    f = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    ev = f.restore_position(st, ts_ms=DAY0 + 2000, detail="db+snapshot")
    assert isinstance(ev[0], PositionRestored) and f.position is not None and f.position_state() == st
    p, q = e.position, f.position
    assert p is not None and q is not None
    assert (q.qty, q.entry_price, q.leverage, q.sl, q.tp, q.liq_price_est, q.entry_commission, q.funding_paid, q.opened_ms) == \
        (p.qty, p.entry_price, p.leverage, p.sl, p.tp, p.liq_price_est, p.entry_commission, p.funding_paid, p.opened_ms)


def test_a_funding_boundary_crossed_while_down_is_missed_and_blocks_entries(rules):
    e = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    e.request_entry(intent(decided_ms=DAY0))
    e.on_tick(tick(DAY0 + 1000))
    st = e.position_state()
    assert st is not None
    f = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    f.restore_position(st, ts_ms=DAY0 + 9 * H, detail="x")
    wallet = f.wallet
    ev = f.on_tick(tick(DAY0 + 9 * H))                              # 08:00 경계를 내려가 있는 동안 지났다
    missed = [x for x in ev if isinstance(x, FundingMissed)]
    assert missed and missed[0].boundaries_ms == (next_funding(DAY0 + 1000),)
    assert f.entries_blocked and f.wallet == wallet, "율을 모르면 정산하지 않는다(추정 금지) · 진입 차단"
    g = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    g.restore_position(st, ts_ms=DAY0 + 60_000, detail="x")
    assert not [x for x in g.on_tick(tick(DAY0 + 60_000)) if isinstance(x, FundingMissed)] and not g.entries_blocked


# ── 판단 + 적용 ─────────────────────────────────────────────────────────────
def test_agreeing_db_row_and_snapshot_restore_the_position_and_entries_resume(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    rt, counter, clock, decision, msgs = restart(rules, db, t0=t + 5000)
    assert decision.action == "restore", decision.detail
    assert rt.engine.position is not None and decision.position is not None
    assert str(rt.engine.position.qty) == decision.position["qty"]
    assert any("포지션 복원" in m for m in msgs)
    root = rt.con.execute("SELECT id FROM positions WHERE event='open'").fetchone()[0]
    assert rt.con.execute("SELECT kind FROM engine_events WHERE kind='PositionRestored'").fetchall() == [("PositionRestored",)]
    feed(rt, counter, clock, t + 5000, t + 125_000)
    assert rt.entry_blockers() == [], "복원이 일치하면 대사도 맞고 진입이 다시 허용된다"
    assert rt.gate.reconcile.blocker is None
    rt.close_all("telegram:111")
    assert rt.engine.position is None
    assert rt.con.execute("SELECT position_id, reason FROM positions WHERE event='close'").fetchall() == [(root, "manual")]


def _tamper_snapshot(db: Path, **changes) -> None:
    con = sqlite3.connect(db)
    sid, raw = last_snapshot_raw(con)
    raw["position"] |= changes
    con.execute("UPDATE account_snapshots SET raw_json=? WHERE id=?", (json.dumps(raw), sid))
    con.commit()
    con.close()


@pytest.mark.parametrize("change", [
    {"qty": "0.001"}, {"entry_price": "59999"}, {"leverage": 1}, {"sl": "1"}, {"tp": "99999"},
    {"funding_paid": "0.5"}, {"opened_ms": 1}, {"direction": "SHORT"}, {"next_funding_ms": None},
])
def test_any_disagreement_starts_flat_pauses_entries_alerts_and_closes_the_orphan_row(rules, tmp_path, change):
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    _tamper_snapshot(db, **change)
    rt, counter, clock, decision, msgs = restart(rules, db, t0=t + 5000)
    assert decision.action == "mismatch", change
    assert rt.engine.position is None
    assert f"paused:{RS.MISMATCH_PAUSE}" in rt.gate.entry_blockers()
    assert any("복원하지 않음" in m for m in msgs)
    root = rt.con.execute("SELECT id FROM positions WHERE event='open'").fetchone()[0]
    assert rt.con.execute("SELECT position_id, reason, realized_pnl_usdt FROM positions WHERE event='close'").fetchall() == \
        [(root, RS.UNRESTORED_REASON, None)], "손익은 추정하지 않는다"
    ks = rt.gate.kill_switch
    assert (ks.vanished, ks.liquidations, ks.consecutive_losses, ks.tripped) == (0, 0, 0, None), "봇 재기동은 거래 결과가 아니다"
    feed(rt, counter, clock, t + 5000, t + 125_000)
    assert rt.gate.reconcile.blocker is None, "고아 행을 닫았으므로 대사는 flat끼리 맞는다"
    assert rt.entry_blockers() == [f"paused:{RS.MISMATCH_PAUSE}"], "남는 차단은 사람의 /start 하나"
    rt.resume("telegram:111")
    assert rt.entry_blockers() == []


def test_snapshot_older_than_the_open_row_or_missing_is_a_mismatch(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    con = sqlite3.connect(db)
    root_ts = con.execute("SELECT ts_ms FROM positions WHERE event='open'").fetchone()[0]
    con.execute("DELETE FROM account_snapshots WHERE ts_ms >= ?", (root_ts,))
    con.commit()
    con.close()
    assert RS.decide_paper_restore(sqlite3.connect(db), mode="paper", symbol="BTCUSDT").action == "mismatch"
    con = sqlite3.connect(db)
    con.execute("DELETE FROM account_snapshots")
    con.commit()
    d = RS.decide_paper_restore(con, mode="paper", symbol="BTCUSDT")
    assert d.action == "mismatch" and "스냅샷 없음" in d.detail
    assert t


def test_snapshot_position_with_a_flat_db_starts_flat_and_pauses(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM positions")
    con.commit()
    con.close()
    rt, _counter, _clock, decision, msgs = restart(rules, db, t0=t + 5000)
    assert decision.action == "mismatch" and rt.engine.position is None
    assert f"paused:{RS.MISMATCH_PAUSE}" in rt.gate.entry_blockers()
    assert rt.con.execute("SELECT count(*) FROM positions").fetchone()[0] == 0
    assert msgs


def test_both_flat_is_a_no_op(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    rt, counter, clock = build_file(rules, db, t0=DAY0)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.con.close()
    rt, _c, _k, decision, msgs = restart(rules, db, t0=DAY0 + 70_000)
    assert decision.action == "none" and msgs == [] and rt.gate.entry_blockers() == ["stale:not_evaluated"]


def test_restore_mark_missing_stale_alert_is_sent_once_not_every_second(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    rt, counter, clock, decision, _msgs = restart(rules, db, t0=t)
    assert decision.action == "restore"
    texts(rt)
    for s in range(121, 140):                                     # mark 한 번도 없음 · grace 초과 → 청산 필요하나 기준가 없음
        clock.t = t + s * 1000
        rt.safety_tick(clock.t)
    assert len([m for m in texts(rt) if "받은 mark가 없다" in m]) == 1
    assert rt.engine.position is not None
