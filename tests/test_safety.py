"""layer 7 `safety/` — strategy-modules §6.

- 킬스위치: 일일 손실 한도(equity x%) · 연속 손실 n회 · 청산 1회 → 신규 진입 중단 + 알림 · 재개는 **사람의 /start만**.
  x·n은 사전확약 값 → **기본값 없음**(레지스트리 PENDING 행) · 트립 상태는 DB에 남아 재시작이 풀지 않는다
- stale-data kill: 레지스트리 #1 `DeliveryCounter.stalled()` → 진입 금지 · 포지션은 보유 + 알림(자동 청산 안 함)
- 대사: 봇 내부 ↔ positionRisk(LIVE만, #6) ↔ DB positions — 불일치 → 진입 금지 + 알림
- rate-limit: 사용량 ≥ 80% → 폴링 완화 신호
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from db import migrate as M
from db import record as R
from exchange.gate import Mode
from exchange.orders import Direction
from exchange.ratelimit import RateLimitCounter
from exchange.rules import RateLimit
from ops.delivery_counter import DeliveryCounter
from paper.types import ExitReason, PositionClosed, PositionRisk
from safety import config as SC
from safety.gate import SafetyGate
from safety.killswitch import KillSwitch, KillSwitchTripped
from safety.rate_guard import RateLimitGuard
from safety.reconcile import DbPosition, ReconcileGuard, reconcile
from safety.stale import StaleDataGuard

D = Decimal
DAY0 = 1_789_430_400_000          # 2026-09-15 00:00 UTC
H = 3_600_000
LIMITS = SC.KillSwitchLimits(daily_loss_pct=D("0.05"), max_consecutive_losses=3)


def closed(wallet_after, *, ts=DAY0 + H, reason=ExitReason.SL, direction=Direction.LONG):
    return PositionClosed(ts, direction, reason, D("0.01"), D("60000"), D("59900"), (), D("-1"), D("0.3"), D("0"),
                          D(wallet_after))


# ── 킬스위치 ─────────────────────────────────────────────────────────────────
def test_limits_have_no_defaults_and_are_validated():
    with pytest.raises(TypeError):
        SC.KillSwitchLimits()  # type: ignore[call-arg]
    for bad in ({"daily_loss_pct": D("0"), "max_consecutive_losses": 3}, {"daily_loss_pct": D("1"), "max_consecutive_losses": 3},
                {"daily_loss_pct": 0.05, "max_consecutive_losses": 3}, {"daily_loss_pct": D("0.05"), "max_consecutive_losses": 0}):
        with pytest.raises((ValueError, TypeError)):
            SC.KillSwitchLimits(**bad)
    assert SC.MAX_LIQUIDATIONS == 1 and SC.RATE_LIMIT_RELAX_AT == D("0.8")


def test_consecutive_net_losses_trip_and_a_win_resets_the_count():
    """손익은 직전 flat 지갑 대비(진입 수수료·펀딩 포함) — 이벤트의 실현손익만 보면 진입 수수료가 빠진다."""
    ks = KillSwitch(LIMITS, wallet=D("1000"))
    assert ks.observe([closed("990")], DAY0 + H) == [] and ks.consecutive_losses == 1
    assert ks.observe([closed("1001")], DAY0 + 2 * H) == [] and ks.consecutive_losses == 0
    ks.observe([closed("1000.9")], DAY0 + 3 * H)                             # 0.1 손실(수수료가 이익을 먹음)도 손실
    ks.observe([closed("995")], DAY0 + 4 * H)
    (trip,) = ks.observe([closed("994")], DAY0 + 5 * H)
    assert isinstance(trip, KillSwitchTripped) and trip.reason == "consecutive_losses" and not ks.entries_allowed


def test_one_liquidation_trips():
    ks = KillSwitch(LIMITS, wallet=D("1000"))
    (trip,) = ks.observe([closed("980", reason=ExitReason.LIQUIDATION)], DAY0 + H)
    assert trip.reason == "liquidation" and not ks.entries_allowed


def test_daily_loss_on_equity_from_the_utc_day_start():
    ks = KillSwitch(LIMITS, wallet=D("1000"))
    assert ks.observe_equity(DAY0 + 60_000, D("1000")) == []
    assert ks.observe_equity(DAY0 + 2 * H, D("950.01")) == []
    (trip,) = ks.observe_equity(DAY0 + 3 * H, D("950"))                     # 5% 정확히 = 발동
    assert trip.reason == "daily_loss" and "1000" in trip.detail
    #  다음 UTC 날짜에도 트립은 자동으로 풀리지 않는다
    assert ks.observe_equity(DAY0 + 25 * H, D("950")) == [] and not ks.entries_allowed


def test_new_utc_day_rebases_the_daily_start():
    ks = KillSwitch(LIMITS, wallet=D("1000"))
    ks.observe_equity(DAY0 + H, D("1000"))
    ks.observe_equity(DAY0 + 23 * H, D("960"))
    assert ks.observe_equity(DAY0 + 24 * H + 1, D("960")) == [] and ks.day_start_equity == D("960")
    assert ks.observe_equity(DAY0 + 30 * H, D("912.01")) == []               # 새 기준 960 × 0.95 = 912
    assert ks.observe_equity(DAY0 + 31 * H, D("912")) != []
    assert ks.tripped is not None and ks.tripped.reason == "daily_loss"


def test_only_a_human_resume_clears_a_trip_and_it_trips_once():
    ks = KillSwitch(LIMITS, wallet=D("1000"))
    ks.observe([closed("980", reason=ExitReason.LIQUIDATION)], DAY0 + H)
    assert ks.observe([closed("970", reason=ExitReason.LIQUIDATION)], DAY0 + 2 * H) == [], "이미 발동 — 중복 이벤트 없음"
    with pytest.raises(ValueError):
        ks.resume(DAY0 + 3 * H, actor="")
    msg = ks.resume(DAY0 + 3 * H, actor="telegram:111")
    assert ks.entries_allowed and ks.liquidations == 0 and ks.consecutive_losses == 0 and "telegram:111" in msg


def test_state_round_trips_through_the_db_so_a_restart_does_not_clear_a_trip():
    con = sqlite3.connect(":memory:")
    M.migrate(con)
    ks = KillSwitch(LIMITS, wallet=D("1000"))
    ks.observe_equity(DAY0 + H, D("1000"))
    ks.observe([closed("990")], DAY0 + H)
    ks.observe([closed("980", reason=ExitReason.LIQUIDATION)], DAY0 + 2 * H)
    ks.save(con, ts_ms=DAY0 + 2 * H, mode="paper")
    back = KillSwitch.load(con, LIMITS, mode="paper", wallet=D("5"))
    assert back.to_state() == ks.to_state() and not back.entries_allowed and back.last_flat_wallet == D("980")
    fresh = KillSwitch.load(con, LIMITS, mode="live", wallet=D("5"))
    assert fresh.entries_allowed and fresh.last_flat_wallet == D("5")


# ── stale-data ───────────────────────────────────────────────────────────────
def test_stale_guard_uses_the_registry_1_counter_and_alerts_only_on_change():
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=DAY0)
    g = StaleDataGuard(counter)
    for t in range(0, 130_000, 1000):
        counter.observe("markprice", DAY0 + t)
        counter.observe("kline1m_update", DAY0 + t)
    counter.observe("kline1m_close", DAY0 + 59_999)
    counter.observe("kline1m_close", DAY0 + 119_999)
    v, changes = g.update(DAY0 + 130_000, has_position=True)
    assert v.entries_allowed and v.stalled == () and changes == []
    v, changes = g.update(DAY0 + 260_000, has_position=True)                # 130초 무수신 > grace 120
    assert not v.entries_allowed and "markprice" in v.stalled and v.position_action == "hold_and_alert"
    assert len(changes) == 1 and changes[0].stalled == v.stalled
    assert g.update(DAY0 + 261_000, has_position=True)[1] == [], "같은 상태는 다시 알리지 않는다"
    assert g.update(DAY0 + 261_000, has_position=False)[0].position_action == "none"


# ── 대사 ────────────────────────────────────────────────────────────────────
def test_live_three_way_match_and_each_kind_of_mismatch():
    pr = PositionRisk(D("0.010"), D("60000"), D("59000"))
    ok = reconcile(Mode.LIVE, internal_signed=D("0.010"), exchange=pr, exchange_error=None,
                   db=DbPosition(Direction.LONG, D("0.010")))
    assert ok.ok and ok.mismatches == ()
    r = reconcile(Mode.LIVE, internal_signed=D("0.010"), exchange=PositionRisk(D("0.012"), D("60000"), D("0")),
                  exchange_error=None, db=DbPosition(Direction.LONG, D("0.010")))
    assert not r.ok and r.mismatches == ("internal_vs_exchange",) and r.sticky
    r = reconcile(Mode.LIVE, internal_signed=D("-0.010"), exchange=PositionRisk(D("-0.010"), D("1"), D("0")),
                  exchange_error=None, db=None)
    assert r.mismatches == ("internal_vs_db",)
    r = reconcile(Mode.LIVE, internal_signed=D("0"), exchange=None, exchange_error="TransportError: timeout", db=None)
    assert r.mismatches == ("exchange_unavailable",) and not r.sticky


def test_paper_never_reads_the_exchange_and_compares_internal_with_db_only():
    with pytest.raises(ValueError):
        reconcile(Mode.PAPER, internal_signed=D("0"), exchange=PositionRisk(D("0"), D("0"), D("0")), exchange_error=None,
                  db=None)
    assert reconcile(Mode.PAPER, internal_signed=D("0"), exchange=None, exchange_error=None, db=None).ok
    r = reconcile(Mode.PAPER, internal_signed=D("0.01"), exchange=None, exchange_error=None,
                  db=DbPosition(Direction.SHORT, D("0.01")))
    assert r.mismatches == ("internal_vs_db",)


def test_db_open_position_state_is_open_minus_closes(rules):
    from tests.test_db import run_engine
    con = sqlite3.connect(":memory:")
    M.migrate(con)
    assert R.open_position_state(con, mode="paper", symbol="BTCUSDT") is None
    e, ev = run_engine(rules)
    R.record_events(con, ev, mode="paper", symbol="BTCUSDT")
    assert e.position is not None
    st = R.open_position_state(con, mode="paper", symbol="BTCUSDT")
    assert st is not None and st.direction is Direction.LONG and st.remaining_qty == e.position.qty
    assert st.signed == e.position.signed_qty
    R.record_events(con, e.close_now(ref_mark=D("60010"), ts_ms=DAY0 + 9000), mode="paper", symbol="BTCUSDT")
    assert R.open_position_state(con, mode="paper", symbol="BTCUSDT") is None


def test_reconcile_guard_sticky_mismatch_needs_a_human_but_unavailable_clears_itself():
    g = ReconcileGuard()
    bad = reconcile(Mode.LIVE, internal_signed=D("0.01"), exchange=PositionRisk(D("0"), D("0"), D("0")),
                    exchange_error=None, db=DbPosition(Direction.LONG, D("0.01")))
    good = reconcile(Mode.LIVE, internal_signed=D("0"), exchange=PositionRisk(D("0"), D("0"), D("0")),
                     exchange_error=None, db=None)
    down = reconcile(Mode.LIVE, internal_signed=D("0"), exchange=None, exchange_error="timeout", db=None)
    assert g.update(down) and g.blocker is not None
    assert g.update(good) and g.blocker is None, "조회 실패는 다음 성공으로 풀린다"
    assert g.update(bad) and g.blocker is not None
    assert g.update(good) == [] and g.blocker is not None, "수량 불일치는 사람이 확인할 때까지 유지"
    g.resume(actor="telegram:111")
    assert g.blocker is None


# ── rate limit ──────────────────────────────────────────────────────────────
def test_rate_guard_relaxes_polling_at_80_percent_of_any_limit():
    counter = RateLimitCounter([RateLimit("REQUEST_WEIGHT", "MINUTE", 1, 2400), RateLimit("ORDERS", "SECOND", 10, 300)])
    g = RateLimitGuard(counter)
    now = DAY0 + 30_000
    counter.observe_headers({"X-MBX-USED-WEIGHT-1M": "1919"}, now)
    assert not g.check(now).relax_polling
    counter.observe_headers({"X-MBX-USED-WEIGHT-1M": "1920"}, now)                 # 정확히 80%
    d = g.check(now)
    assert d.relax_polling and d.over == ("REQUEST_WEIGHT/MINUTE/1",)
    assert not g.check(now + 60_000).relax_polling                                  # 창이 넘어가면 해제


# ── 종합 게이트 ──────────────────────────────────────────────────────────────
def test_gate_lists_every_blocker_and_resume_clears_only_human_clearable_ones():
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=DAY0)
    gate = SafetyGate(KillSwitch(LIMITS, wallet=D("1000")), StaleDataGuard(counter), ReconcileGuard())
    assert gate.entry_blockers() == ["stale:not_evaluated"], "피드를 한 번도 평가하지 않았으면 진입 금지"
    gate.pause("telegram:111")
    gate.kill_switch.observe([closed("980", reason=ExitReason.LIQUIDATION)], DAY0 + H)
    gate.stale.update(DAY0 + 200_000, has_position=False)                           # 전부 무수신
    blockers = gate.entry_blockers()
    assert any(b.startswith("paused") for b in blockers) and any(b.startswith("kill_switch") for b in blockers)
    assert any(b.startswith("stale") for b in blockers) and not gate.entries_allowed
    text = gate.resume("telegram:111")
    remaining = gate.entry_blockers()
    assert not any(b.startswith(("paused", "kill_switch")) for b in remaining)
    assert any(b.startswith("stale") for b in remaining) and "stale" in text, "피드 정지는 사람이 풀 수 없다 — 알려준다"


def test_gate_pause_and_kill_switch_persist_together():
    con = sqlite3.connect(":memory:")
    M.migrate(con)
    counter = DeliveryCounter(("kline1m_update", "kline1m_close", "markprice"), start_ms=DAY0)
    gate = SafetyGate(KillSwitch(LIMITS, wallet=D("1000")), StaleDataGuard(counter), ReconcileGuard())
    gate.pause("telegram:111")
    gate.save(con, ts_ms=DAY0, mode="live")
    back = SafetyGate.load(con, LIMITS, StaleDataGuard(counter), mode="live", wallet=D("1000"))
    assert back.paused_by == "telegram:111" and any(b.startswith("paused") for b in back.entry_blockers())


def test_a_persisting_mismatch_with_changing_numbers_alerts_once():
    g = ReconcileGuard()
    for amt in ("0.011", "0.012", "0.013"):
        r = reconcile(Mode.LIVE, internal_signed=D("0.01"), exchange=PositionRisk(D(amt), D("0"), D("0")),
                      exchange_error=None, db=DbPosition(Direction.LONG, D("0.01")))
        g.update(r)
    assert g.alerts_sent == 1 and g.blocker == "reconcile:internal_vs_exchange"
    down = reconcile(Mode.LIVE, internal_signed=D("0.01"), exchange=None, exchange_error="timeout",
                     db=DbPosition(Direction.LONG, D("0.01")))
    assert g.update(down) == [] and g.blocker == "reconcile:internal_vs_exchange", "조회 실패가 sticky 사유를 덮지 않는다"
