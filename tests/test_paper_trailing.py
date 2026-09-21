"""트레일링 스톱(단계 2c · 사전등록 §1 "트레일링" 행) — `EntryIntent.trail`이 있을 때만 켜진다(기본 None = 꺼짐).

- 무장: 유리한 극값(롱 = mark 고가 · 숏 = mark 저가)이 진입가 ± `arm_r × R`에 닿으면(R = 체결 진입가와 초기 SL의 거리).
- 무장 뒤 SL = 극값 ∓ `dist`로 **조이기만** 한다(느슨하게 되돌리지 않는다). 봉에서 갱신한 SL은 **다음 봉부터** 판정한다
  (봉 안 고가·저가 순서를 모르므로 같은 봉에 적용하지 않는다 — 보수적 봉 근사).
- 옮겨진 SL에서 나가면 `ExitReason.TRAIL`. 체결 기준은 SL과 똑같이 min(SL, 시가)(롱).
- **trail = None이면 동작·이벤트·스냅샷 키가 기존과 완전히 같다** — 돌고 있는 페이퍼 봇 경로는 바뀌지 않는다.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from exchange.gate import Mode
from exchange.orders import Direction
from paper.engine import Engine, EntryIntent, Trail
from paper.sender import PaperSender
from paper.types import EntryFilled, ExitReason, MarkBar, MarkTick, PositionClosed, StopTrailed
from sizing.config import RegimeSizing, SizingLimits

D = Decimal
LONG, SHORT = Direction.LONG, Direction.SHORT
M = 60_000
T0 = 1_789_430_400_000
REGIME = RegimeSizing("t", D("0.01"), 50, 100)


def eng(rules) -> Engine:
    return Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())


def bar(i: int, o, h, lo, c) -> MarkBar:
    return MarkBar(T0 + i * M, T0 + i * M + M - 1, D(o), D(h), D(lo), D(c))


def opened(rules, direction=LONG, trail: Trail | None = None) -> tuple[Engine, list[object]]:
    e = eng(rules)
    sl = D("59700") if direction is LONG else D("60300")
    e.request_entry(EntryIntent(direction, sl, None, REGIME, T0 - 1, D("60000"), trail=trail))
    ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
    assert [x for x in ev if isinstance(x, EntryFilled)]
    return e, ev


def r_of(e: Engine) -> Decimal:
    pos = e.position
    assert pos is not None
    return abs(pos.entry_price - pos.sl)


def test_default_is_off_sl_never_moves_through_a_3r_run(rules):
    e, _ = opened(rules)
    sl0 = e.position.sl if e.position else None
    r = r_of(e)
    entry = e.position.entry_price if e.position else D(0)
    top = entry + 3 * r
    ev = e.on_bar(bar(1, entry, top, entry, top))
    ev += e.on_bar(bar(2, top, top, entry + r / 2, entry + r / 2))
    assert e.position is not None and e.position.sl == sl0
    assert not [x for x in ev if isinstance(x, StopTrailed)]


def test_default_snapshot_keys_are_unchanged(rules):
    e, _ = opened(rules)
    st = e.position_state()
    assert st is not None and set(st) == {"direction", "qty", "entry_price", "leverage", "sl", "tp", "liq_price_est",
                                          "entry_commission", "funding_paid", "opened_ms", "liq_alerted",
                                          "next_funding_ms"}


def test_default_path_events_identical_to_explicit_none(rules):
    seq = [("60000", "60400", "59990", "60350"), ("60350", "61000", "60300", "60900"), ("60900", "60950", "59680", "59690")]
    runs = []
    for tr in (None, "default"):
        e = eng(rules)
        kw = {} if tr == "default" else {"trail": None}
        e.request_entry(EntryIntent(LONG, D("59700"), None, REGIME, T0 - 1, D("60000"), **kw))
        ev = e.on_bar(bar(0, "60000", "60000", "60000", "60000"))
        for i, (o, h, lo, c) in enumerate(seq, 1):
            ev += e.on_bar(bar(i, o, h, lo, c))
        runs.append(ev)
    assert runs[0] == runs[1]
    (c,) = [x for x in runs[0] if isinstance(x, PositionClosed)]
    assert c.reason is ExitReason.SL


def test_not_armed_below_1r(rules):
    e, _ = opened(rules, trail=Trail(arm_r=D(1), dist=D("100")))
    r = r_of(e)
    assert e.position is not None
    entry, sl0 = e.position.entry_price, e.position.sl
    ev = e.on_bar(bar(1, entry, entry + r - D("0.1"), entry, entry))
    assert e.position.sl == sl0 and not e.position.trail_armed and not [x for x in ev if isinstance(x, StopTrailed)]


def test_arms_at_1r_and_ratchets_from_the_extreme_but_never_loosens(rules):
    e, _ = opened(rules, trail=Trail(arm_r=D(1), dist=D("100")))
    r = r_of(e)
    pos = e.position
    assert pos is not None
    entry = pos.entry_price
    hi1 = entry + r + 50
    ev = e.on_bar(bar(1, entry, hi1, entry, hi1 - 10))
    assert pos.trail_armed and pos.sl == hi1 - 100
    (st,) = [x for x in ev if isinstance(x, StopTrailed)]
    assert st.new_sl == hi1 - 100 and st.old_sl == D("59700")
    ev = e.on_bar(bar(2, hi1 - 10, hi1 - 20, hi1 - 60, hi1 - 50))     # 더 낮은 고가 → 그대로
    assert pos.sl == hi1 - 100 and not [x for x in ev if isinstance(x, StopTrailed)]
    hi3 = hi1 + 300
    e.on_bar(bar(3, hi1 - 50, hi3, hi1 - 55, hi3))
    assert pos.sl == hi3 - 100


def test_trail_set_on_a_bar_is_not_judged_in_the_same_bar(rules):
    """같은 봉에서 +1R 고가 뒤 저가가 옮긴 SL 아래로 내려가도 이 봉에서는 청산하지 않는다(봉 안 순서 불명)."""
    e, _ = opened(rules, trail=Trail(arm_r=D(1), dist=D("100")))
    r = r_of(e)
    assert e.position is not None
    entry = e.position.entry_price
    ev = e.on_bar(bar(1, entry, entry + 2 * r, entry, entry + r))
    assert e.position is not None and not [x for x in ev if isinstance(x, PositionClosed)]
    new_sl = entry + 2 * r - 100
    ev = e.on_bar(bar(2, entry + r, entry + r, entry, entry))
    (c,) = [x for x in ev if isinstance(x, PositionClosed)]
    assert c.reason is ExitReason.TRAIL
    assert c.exit_price is not None and c.fills[0].ref_mark == min(new_sl, entry + r)


def test_short_is_symmetric(rules):
    e, _ = opened(rules, SHORT, trail=Trail(arm_r=D(1), dist=D("100")))
    r = r_of(e)
    pos = e.position
    assert pos is not None
    entry = pos.entry_price
    lo1 = entry - r - 40
    e.on_bar(bar(1, entry, entry, lo1, lo1 + 5))
    assert pos.trail_armed and pos.sl == lo1 + 100
    ev = e.on_bar(bar(2, lo1 + 5, lo1 + 150, lo1, lo1 + 120))
    (c,) = [x for x in ev if isinstance(x, PositionClosed)]
    assert c.reason is ExitReason.TRAIL and c.fills[0].ref_mark == max(lo1 + 100, lo1 + 5)


def test_untrailed_stop_still_exits_as_sl_when_trail_configured(rules):
    e, _ = opened(rules, trail=Trail(arm_r=D(1), dist=D("100")))
    ev = e.on_bar(bar(1, "59990", "60000", "59600", "59650"))
    (c,) = [x for x in ev if isinstance(x, PositionClosed)]
    assert c.reason is ExitReason.SL


def test_tick_path_trails_on_mark(rules):
    e = eng(rules)
    e.request_entry(EntryIntent(LONG, D("59700"), None, REGIME, T0 - 1, D("60000"), trail=Trail(D(1), D("100"))))
    nf = (T0 // (8 * 3_600_000) + 1) * 8 * 3_600_000
    e.on_tick(MarkTick(T0, D("60000"), D("0.0001"), nf))
    pos = e.position
    assert pos is not None
    r = abs(pos.entry_price - pos.sl)
    e.on_tick(MarkTick(T0 + 1000, pos.entry_price + r + 10, D("0.0001"), nf))
    assert pos.trail_armed and pos.sl == pos.entry_price + r + 10 - 100
    ev = e.on_tick(MarkTick(T0 + 2000, pos.entry_price + r - 95, D("0.0001"), nf))
    (c,) = [x for x in ev if isinstance(x, PositionClosed)]
    assert c.reason is ExitReason.TRAIL


def test_snapshot_round_trip_keeps_trail(rules):
    e, _ = opened(rules, trail=Trail(arm_r=D(1), dist=D("100")))
    r = r_of(e)
    assert e.position is not None
    entry = e.position.entry_price
    e.on_bar(bar(1, entry, entry + r + 50, entry, entry + r))
    st = e.position_state()
    assert st is not None and st["trail"] == {"arm_r": "1", "dist": "100", "r": str(r), "armed": True, "moved": True}
    f = eng(rules)
    f.restore_position(replace_nf(st), ts_ms=T0 + 3 * M, detail="t")
    p = f.position
    assert p is not None and p.trail == Trail(D(1), D("100")) and p.trail_armed and p.trail_moved and p.trail_r == r
    assert p.sl == e.position.sl


def replace_nf(st: dict) -> dict:
    return dict(st) | {"next_funding_ms": st["next_funding_ms"] or (T0 // (8 * 3_600_000) + 1) * 8 * 3_600_000}


def test_intent_trail_validation(rules):
    import pytest
    for bad in (Trail(D(0), D("100")), Trail(D(1), D(0)), Trail(D(1), D(-1))):
        e = eng(rules)
        with pytest.raises(ValueError):
            e.request_entry(EntryIntent(LONG, D("59700"), None, REGIME, T0 - 1, D("60000"), trail=bad))
    assert replace(Trail(D(1), D(2)), dist=D(3)).dist == D(3)
