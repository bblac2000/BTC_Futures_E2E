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
    gate = SafetyGate.load(con, SC.REGISTERED_KILL_SWITCH, StaleDataGuard(counter), mode="paper", wallet=D(wallet))
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
    {"entry_commission": "0.01"}, {"qty": "0.001"}, {"entry_price": "59999"}, {"leverage": 1}, {"sl": "1"}, {"tp": "99999"},
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


def test_liquidation_estimate_is_recomputed_from_current_rules_not_taken_from_the_snapshot(rules, tmp_path):
    """Codex L8b #2: 스냅샷의 추정 청산가는 믿지 않는다 — 복원 때 진입가·수량·레버리지·누적 펀딩·현재 규칙으로 다시 계산."""
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    con = sqlite3.connect(db)
    (true_liq,) = con.execute("SELECT liq_price_est FROM positions WHERE event='open'").fetchone()
    con.close()
    _tamper_snapshot(db, liq_price_est="1")
    rt, _c, _k, decision, msgs = restart(rules, db, t0=t + 5000)
    assert decision.action == "restore" and rt.engine.position is not None
    assert rt.engine.position.liq_price_est == D(true_liq), "펀딩 0이면 진입 때 추정과 같다"
    assert any("추정 청산가 재계산" in m for m in msgs)


def test_a_funding_missed_engine_block_survives_a_second_restart_until_a_human_start(rules, tmp_path):
    """Codex L8b #1: 엔진 차단 사유는 메모리에만 있으면 두 번째 재기동이 지운다 → safety_state에 함께 저장·복원."""
    db = tmp_path / "bot.sqlite"
    open_then_crash(rules, db)
    t = DAY0 + 9 * H                                                 # 08:00 경계를 내려가 있는 동안 지남
    rt, counter, clock, decision, _m = restart(rules, db, t0=t)
    assert decision.action == "restore"
    feed(rt, counter, clock, t, t + 61_000)
    blocked = [b for b in rt.entry_blockers() if b.startswith("engine:")]
    assert blocked and "펀딩" in blocked[0]
    rt.con.close()                                                   # 두 번째 SIGKILL
    rt2, counter2, clock2, decision2, _m2 = restart(rules, db, t0=t + 70_000)
    assert decision2.action == "restore"
    feed(rt2, counter2, clock2, t + 70_000, t + 131_000)
    assert [b for b in rt2.entry_blockers() if b.startswith("engine:")] == blocked, "차단이 재기동을 넘어 남는다"
    rt2.resume("telegram:111")
    assert rt2.entry_blockers() == []
    rt2.con.close()
    rt3, counter3, clock3, _d3, _m3 = restart(rules, db, t0=t + 140_000)
    feed(rt3, counter3, clock3, t + 140_000, t + 201_000)
    assert rt3.entry_blockers() == [], "사람의 /start 해제도 저장된다"


def test_restart_unrestored_stays_in_status_until_start_and_survives_a_restart(rules, tmp_path):
    """사용자 2026-09-16: 고아 포지션 close(`restart_unrestored`)는 확정 사실 — /status·상태 파일에 사람이 /start로 확인할 때까지."""
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    _tamper_snapshot(db, qty="0.001")
    rt, _c, _k, decision, _m = restart(rules, db, t0=t + 5000)
    assert decision.action == "mismatch"
    facts = rt.status(t + 5000)["confirmed_facts"]
    assert [(f["kind"], f["daily"]) for f in facts] == [("restart_unrestored", True)] and facts[0]["id"] == "1"
    assert "restart_unrestored" in rt.status_text()
    rt.con.close()                                                   # 확인 전에 다시 죽는다
    rt2, _c2, _k2, decision2, _m2 = restart(rules, db, t0=t + 20_000)
    assert decision2.action == "none", "고아 행은 이미 닫혔다"
    assert [f["kind"] for f in rt2.status(t + 20_000)["confirmed_facts"]] == ["restart_unrestored"], "safety_state에 남는다"
    rt2.resume("telegram:111")
    assert rt2.status(t + 21_000)["confirmed_facts"] == [] and "restart_unrestored" not in rt2.status_text()
    rt2.con.close()
    rt3, _c3, _k3, _d3, _m3 = restart(rules, db, t0=t + 30_000)
    assert rt3.status(t + 30_000)["confirmed_facts"] == [], "확인도 저장된다"


def test_notice_is_rebuilt_from_the_orphan_close_row_if_the_process_died_before_saving_it(rules, tmp_path):
    """Codex 배포 전 #1: close 행은 들어갔는데 notice·safety_state 저장 전에 죽으면 확인 요청이 사라졌다 → DB close 행에서 복원."""
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    _tamper_snapshot(db, qty="0.001")
    rt, _c, _k, decision, _m = restart(rules, db, t0=t + 5000)
    assert decision.action == "mismatch"
    rt.con.execute("DELETE FROM safety_state")                       # notice 저장 전 SIGKILL과 같은 DB
    rt.con.commit()
    rt.con.close()
    rt2, _c2, _k2, decision2, _m2 = restart(rules, db, t0=t + 20_000)
    assert decision2.action == "none"
    assert [(f["kind"], f["id"]) for f in rt2.status(t + 20_000)["confirmed_facts"]] == [("restart_unrestored", "1")]
    rt2.resume("telegram:111")
    assert rt2.con.execute("SELECT count(*) FROM engine_events WHERE kind='NoticeAcknowledged'").fetchone()[0] == 1
    rt2.con.execute("DELETE FROM safety_state")                      # 확인 뒤 상태 저장이 없어도 확인 이벤트로 끝난다
    rt2.con.commit()
    rt2.con.close()
    rt3, _c3, _k3, _d3, _m3 = restart(rules, db, t0=t + 30_000)
    assert rt3.status(t + 30_000)["confirmed_facts"] == []


def test_daily_loss_refused_start_does_not_acknowledge_the_notice(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    _tamper_snapshot(db, qty="0.001")
    rt, _c, _k, _d, _m = restart(rules, db, t0=t + 5000)
    rt.gate.kill_switch.trip(t + 5000, "daily_loss", "test")
    rt.resume("telegram:111")
    assert [f["kind"] for f in rt.confirmed_facts()] == ["restart_unrestored"]
    assert rt.con.execute("SELECT count(*) FROM engine_events WHERE kind='NoticeAcknowledged'").fetchone()[0] == 0


def test_a_failed_ack_write_followed_by_a_durable_save_keeps_the_breadcrumb_base_id_current(rules, tmp_path, monkeypatch):
    """Codex 배포 전 재검토 #1: ack 기록 실패 → breadcrumb(옛 base id) → 상태 저장 성공 → breadcrumb가 새 base id를 가져야 한다."""
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    _tamper_snapshot(db, qty="0.001")
    rt, _c, _k, _d, _m = restart(rules, db, t0=t + 5000)
    crumb_path = tmp_path / "run" / "safety_unsaved.json"
    rt.breadcrumb_path = crumb_path
    from db import record as R
    real = R.record_ops_event

    def flaky(con, kind, *a, **k):
        if kind == "NoticeAcknowledged":
            raise sqlite3.OperationalError("database is locked")
        return real(con, kind, *a, **k)
    monkeypatch.setattr(R, "record_ops_event", flaky)
    rt.resume("telegram:111")
    assert rt.unrecorded_ops and crumb_path.exists()
    crumb = json.loads(crumb_path.read_text())
    assert crumb["base_state_id"] == rt.saved_state_id, "뒤따른 저장이 성공했으면 breadcrumb 기준 id도 갱신"
    assert [o["kind"] for o in crumb["ops"]] == ["NoticeAcknowledged", "Resumed"], "순서 보존 — 앞선 실패 뒤에 붙는다"


# ── 트레일링·체결 뒤 TP(기본 꺼짐) — 런타임 → DB → 재기동(Codex 단계 d #3·#4·#5) ─────────────────
def open_trail_then_crash(rules, db: Path, *, t0: int = DAY0, ratchet: bool = True) -> tuple[int, dict]:
    from dataclasses import replace

    from paper.engine import TpFromFill, Trail
    rt, counter, clock = build_file(rules, db, t0=t0)
    feed(rt, counter, clock, t0, t0 + 61_000)
    it = replace(intent(sl="59700", decided_ms=t0 + 60_000), trail=Trail(D(1), D(100)),
                 tp_rule=TpFromFill(D("61000"), D("1.5"), D("2")))
    rt.submit_entry(it)
    feed(rt, counter, clock, t0 + 61_000, t0 + 121_000)
    if ratchet:
        feed(rt, counter, clock, t0 + 121_000, t0 + 181_000, mark="60500")      # +1R(≈312) 넘김 → 무장·SL 60400
    pos = rt.engine.position
    assert pos is not None
    state = rt.engine.position_state()
    assert state is not None
    rt.con.close()
    return t0 + 181_000, state


def test_trailed_sl_and_resolved_tp_survive_a_restart(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t, before = open_trail_then_crash(rules, db)
    assert before["sl"] == "60400" and before["tp"] == "61000" and before["trail"]["moved"] is True
    con = sqlite3.connect(db)
    assert con.execute("SELECT tp FROM positions WHERE event='open'").fetchone()[0] == "61000"      # 체결 뒤 TP가 DB에
    kinds = [k for (k,) in con.execute("SELECT kind FROM engine_events WHERE kind IN ('TrailSet','TrailArmed','StopTrailed') "
                                        "ORDER BY id")]
    assert kinds[:3] == ["TrailSet", "TrailArmed", "StopTrailed"]
    con.close()
    rt, counter, clock, decision, msgs = restart(rules, db, t0=t + 5000)
    assert decision.action == "restore", decision.detail
    p = rt.engine.position
    assert p is not None and p.sl == D("60400") and p.tp == D("61000") and p.trail_armed and p.trail_moved
    assert rt.engine.position_state() == before | {"next_funding_ms": rt.engine.position_state()["next_funding_ms"]}  # type: ignore[index]


def test_armed_but_unmoved_trail_restores(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t, before = open_trail_then_crash(rules, db, ratchet=False)
    assert before["trail"] == {"arm_r": "1", "dist": "100", "r": before["trail"]["r"], "armed": False, "moved": False}
    _, _, _, decision, _ = restart(rules, db, t0=t + 5000)
    assert decision.action == "restore", decision.detail


def test_missing_trail_rows_are_a_mismatch(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t, _ = open_trail_then_crash(rules, db)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM engine_events WHERE kind='StopTrailed'")
    con.commit()
    con.close()
    _, _, _, decision, _ = restart(rules, db, t0=t + 5000)
    assert decision.action == "mismatch" and "sl" in decision.detail


def test_untrailed_position_has_no_trail_rows_and_restores_as_before(rules, tmp_path):
    db = tmp_path / "bot.sqlite"
    t = open_then_crash(rules, db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM engine_events WHERE kind IN ('TrailSet','TrailArmed','StopTrailed')").fetchone()[0] == 0
    con.close()
    _, _, _, decision, _ = restart(rules, db, t0=t + 5000)
    assert decision.action == "restore" and decision.db is not None and decision.db["trail"] is None


def test_post_fill_gate_exit_records_resolved_tp(rules, tmp_path, monkeypatch):
    """체결 직후 #5 게이트 청산(POST_FILL_GATE)이어도 open 행에는 엔진이 정한 TP가 남는다."""
    from dataclasses import replace

    from paper.engine import TpFromFill
    rt, counter, clock = build_file(rules, tmp_path / "bot.sqlite", t0=DAY0)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(replace(intent(sl="59700", decided_ms=DAY0 + 60_000), tp_rule=TpFromFill(None, D("1.5"), D("2"))))
    real = rt.engine._post_fill
    monkeypatch.setattr(rt.engine, "_post_fill", lambda *a: replace(real(*a), gate_ok=False))   # 실제 체결 재검증 실패를 강제
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 63_000)
    assert rt.engine.position is None
    tp, entry = rt.con.execute("SELECT tp, entry_price FROM positions WHERE event='open'").fetchone()
    (reason,) = rt.con.execute("SELECT reason FROM positions WHERE event='close'").fetchone()
    assert reason == "post_fill_gate" and D(tp) == D(entry) + 2 * (D(entry) - D("59700"))
