"""단계 2b — 공유 계층 확장(트라이얼 #2 · 기본 경로 불변). 사전등록 §1 · 계획 r2(ops_log 2026-09-24).

- 레버리지 대역: 등록된 정책 대역 {(50,100) · (10,30)}(#30) · 기본 (50,100) · 트라이얼 #2는 `SizingLimits(leverage_range=(10,30))`를 명시.
- `Trail.dist_r`: 트레일 거리 = dist_r × R(R = |체결 − SL|) — 체결 때 가격 거리로 확정(스냅샷 형태 불변).
- `SlFromFill(anchor, mirror=True)`: SL′ = 2F − anchor(P3 거울상) · 사이징 전에 확정 · TP/트레일 R = |F − anchor|.
- `sizing_capital`(E_ref): 체결된 진입마다 실행 지갑을 E_ref로 리셋 · 거부된 시도는 리셋 없음 · PAPER만.
- `liquidate_if_open_beyond`: 시가가 추정 청산가 너머(경계 포함)면 청산(시각 = 봉 시작) · PAPER만.
- `ExitReason.TIME_EXIT`.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from exchange.gate import Mode
from exchange.orders import Direction
from paper.engine import Engine, EntryIntent, SlFromFill, TpFromFill, Trail
from paper.sender import PaperSender
from paper.types import (
    EntryFilled,
    EntrySkipped,
    ExitReason,
    MarkBar,
    PositionClosed,
    TrailSet,
    WalletResynced,
)
from sizing.config import PERMITTED_LEVERAGE, REGISTERED_LEVERAGE_BANDS, RegimeSizing, SizingLimits
from sizing.position import size_entry

D = Decimal
LONG, SHORT = Direction.LONG, Direction.SHORT
M = 60_000
T0 = 1_789_430_400_000
R2 = RegimeSizing("t2", D("0.01"), 10, 30)
L2 = SizingLimits(leverage_range=(10, 30))
TP2 = TpFromFill(level=None, min_r=D("2"), fallback_r=D("2"))


def bar(i: int, o, h, lo, c) -> MarkBar:
    return MarkBar(T0 + i * M, T0 + i * M + M - 1, D(o), D(h), D(lo), D(c))


E_REF = D("1000")


def eng(rules, *, capital: Decimal | None = E_REF, wallet: str = "1000") -> Engine:
    return Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D(wallet), limits=L2, sizing_capital=capital)


# ── 레버리지 대역 ─────────────────────────────────────────────────────────
def test_bands_and_default():
    assert PERMITTED_LEVERAGE == (50, 100)
    assert REGISTERED_LEVERAGE_BANDS == ((50, 100), (10, 30))
    assert SizingLimits().leverage_range == (50, 100)


def test_regime_must_sit_inside_one_registered_band():
    RegimeSizing("a", D("0.01"), 10, 30)
    RegimeSizing("b", D("0.01"), 12, 20)
    for lo, hi in ((20, 60), (5, 30), (10, 31), (30, 50)):
        with pytest.raises(ValueError):
            RegimeSizing("x", D("0.01"), lo, hi)


def test_limits_range_must_be_a_registered_band():
    with pytest.raises(ValueError):
        SizingLimits(leverage_range=(20, 40))


def test_size_entry_refuses_regime_outside_limits(rules):
    with pytest.raises(ValueError):
        size_entry(D("60000"), D("59700"), LONG, D("1000"), R2, rules, SizingLimits())
    with pytest.raises(ValueError):
        size_entry(D("60000"), D("59700"), LONG, D("1000"), RegimeSizing("t", D("0.01"), 50, 100), rules, L2)


def test_size_entry_with_10_30(rules):
    d = size_entry(D("60000"), D("58800"), LONG, D("1000"), R2, rules, L2)    # sl_dist 2.00% → §1-1 29x
    assert d.ok and d.leverage is not None and 10 <= d.leverage <= 30


# ── Trail.dist_r ─────────────────────────────────────────────────────────
def test_trail_dist_xor_validation(rules):
    e = eng(rules)
    for tr in (Trail(D("1")), Trail(D("1"), D("5"), D("1")), Trail(D("1"), dist_r=D("0"))):
        with pytest.raises(ValueError):
            e.request_entry(EntryIntent(LONG, D("59400"), None, R2, T0 - 1, D("60000"), trail=tr))


def test_trail_dist_r_resolves_to_one_r_at_fill(rules):
    e = eng(rules)
    e.request_entry(EntryIntent(LONG, D("59400"), None, R2, T0 - 1, D("60000"), trail=Trail(D("1"), dist_r=D("1")),
                                tp_rule=TP2))
    ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    pos = e.position
    assert pos is not None and pos.trail is not None
    r = abs(pos.entry_price - D("59400"))
    assert pos.trail.dist == r and pos.trail.dist_r is None and pos.trail_r == r
    ts = [x for x in ev if isinstance(x, TrailSet)]
    assert ts and ts[0].dist == r
    assert pos.tp == pos.entry_price + 2 * r
    assert set(e.position_state()["trail"]) == {"arm_r", "dist", "r", "armed", "moved"}  # type: ignore[index]


# ── SlFromFill(mirror) ───────────────────────────────────────────────────
@pytest.mark.parametrize("direction,anchor", [(LONG, "59400"), (SHORT, "60600")])
def test_mirror_sl_about_fill(rules, direction, anchor):
    """P3: 원 방향은 반대였다 — 반전 방향의 SL′ = 2F − O_d, R = |F − O_d|, TP = F ± 2R, 트레일 1R."""
    e = eng(rules)
    o_d = D(anchor)
    inv = SHORT if direction is LONG else LONG      # 원판 방향 `direction`(o_d가 그 SL) → 반전 방향으로 체결
    e.request_entry(EntryIntent(inv, o_d, None, R2, T0 - 1, D("60000"), sl_rule=SlFromFill(o_d, mirror=True),
                                tp_rule=TP2, trail=Trail(D("1"), dist_r=D("1"))))
    ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    assert [x for x in ev if isinstance(x, EntryFilled)]
    pos = e.position
    assert pos is not None
    f = pos.entry_price
    r = abs(f - o_d)
    assert pos.sl == 2 * f - o_d
    assert pos.tp == (f + 2 * r if inv is LONG else f - 2 * r)
    assert pos.trail_r == r and pos.trail is not None and pos.trail.dist == r


def test_non_mirror_sl_from_fill_equals_anchor(rules):
    e = eng(rules)
    e.request_entry(EntryIntent(LONG, D("59400"), None, R2, T0 - 1, D("60000"), sl_rule=SlFromFill(D("59400"), mirror=False)))
    e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    assert e.position is not None and e.position.sl == D("59400")


def test_sl_must_equal_sl_rule_anchor(rules):
    e = eng(rules)
    with pytest.raises(ValueError):
        e.request_entry(EntryIntent(LONG, D("59300"), None, R2, T0 - 1, D("60000"), sl_rule=SlFromFill(D("59400"), False)))


def test_mirror_sl_already_crossed_before_fill_is_skipped(rules):
    """해석된 SL′로 체결 전 검사 — R이 슬리피지보다 작아 SL′가 mark 너머면 sl_crossed_before_fill."""
    e = eng(rules)
    e.request_entry(EntryIntent(LONG, D("59999.9"), None, R2, T0 - 1, D("60000"), sl_rule=SlFromFill(D("59999.9"), mirror=True)))
    ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    assert e.position is None and [x for x in ev if isinstance(x, EntrySkipped)]


# ── sizing_capital(E_ref) ────────────────────────────────────────────────
def test_fixed_capital_resets_wallet_before_each_filled_entry(rules):
    e = eng(rules, wallet="700")                        # 누적 지갑이 무엇이든 진입 시 E_ref로
    e.request_entry(EntryIntent(LONG, D("59400"), None, R2, T0 - 1, D("60000")))
    ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    rs = [x for x in ev if isinstance(x, WalletResynced)]
    assert rs and rs[0].previous == D("700") and rs[0].wallet == D("1000")
    fill = [x for x in ev if isinstance(x, EntryFilled)][0]
    assert fill.decision.risk_budget_usdt == D("10.00")
    ev = e.on_bar(bar(1, "60000", "60000", "59000", "59100"))          # SL
    closed = [x for x in ev if isinstance(x, PositionClosed)][0]
    assert fill.entry_commission is not None
    assert closed.wallet_after - D("1000") == closed.realized_pnl_usdt - closed.exit_commission_usdt - fill.entry_commission
    w1 = e.wallet
    e.request_entry(EntryIntent(LONG, D("59400"), None, R2, T0 + M, D("60000")))
    ev = e.on_bar(bar(3, "60000", "60000", "60000", "60000"))
    assert [x for x in ev if isinstance(x, WalletResynced)][0].previous == w1
    assert [x for x in ev if isinstance(x, EntryFilled)][0].decision.risk_budget_usdt == D("10.00")


def test_fixed_capital_not_reset_on_refused_entry(rules):
    e = eng(rules, wallet="700")
    e.request_entry(EntryIntent(LONG, D("60010"), None, R2, T0 - 1, D("60000")))  # SL 이미 넘음 → 건너뜀
    ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    assert e.position is None and not [x for x in ev if isinstance(x, WalletResynced)] and e.wallet == D("700")


def test_default_engine_has_no_fixed_capital_and_compounds(rules):
    e = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("700"), limits=SizingLimits())
    assert e.sizing_capital is None
    e.request_entry(EntryIntent(LONG, D("59700"), None, RegimeSizing("t", D("0.01"), 50, 100), T0 - 1, D("60000")))
    ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    assert not [x for x in ev if isinstance(x, WalletResynced)]
    assert [x for x in ev if isinstance(x, EntryFilled)][0].decision.risk_budget_usdt == D("7.00")


def test_fixed_capital_is_paper_only(rules):
    with pytest.raises(ValueError):
        Engine(rules, PaperSender(rules), mode=Mode.LIVE, wallet=D("1000"), limits=L2, sizing_capital=D("1000"))


# ── 시가 갭 청산 · TIME_EXIT ──────────────────────────────────────────────
def _open(rules, direction):
    e = eng(rules)
    sl = D("58800") if direction is LONG else D("61200")
    e.request_entry(EntryIntent(direction, sl, None, R2, T0 - 1, D("60000")))
    e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    assert e.position is not None
    return e


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_gap_liquidation_at_open_inclusive(rules, direction):
    e = _open(rules, direction)
    pos = e.position
    assert pos is not None
    liq = pos.liq_price_est
    ev = e.liquidate_if_open_beyond(liq, ts_ms=T0 + 5 * M)                 # 경계 = 청산
    assert e.position is None
    c = [x for x in ev if isinstance(x, PositionClosed)][0]
    assert c.reason is ExitReason.LIQUIDATION and c.ts_ms == T0 + 5 * M


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_no_gap_liquidation_inside(rules, direction):
    e = _open(rules, direction)
    pos = e.position
    assert pos is not None
    tick = rules.symbol_rules.tick_size
    inside = pos.liq_price_est + tick if direction is LONG else pos.liq_price_est - tick
    assert e.liquidate_if_open_beyond(inside, ts_ms=T0 + 5 * M) == [] and e.position is not None


def test_time_exit_reason(rules):
    assert ExitReason.TIME_EXIT.value == "time_exit"
    e = _open(rules, LONG)
    ev = e.close_now(ref_mark=D("60100"), ts_ms=T0 + 9 * M, reason=ExitReason.TIME_EXIT)
    assert [x for x in ev if isinstance(x, PositionClosed)][0].reason is ExitReason.TIME_EXIT
