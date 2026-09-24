"""단계 2c — 재생 루프의 `exit_at_bar_open` 훅(트라이얼 #2 §1 23:59 봉 · §11-1) + 고정 사이징 자본. 합성 봉만.

훅이 참인 봉의 순서(계획 r2 · Codex before-pass #4):
1 펀딩 정산 → 2 대기 진입 없음 단언 → 3 시가 갭 청산(경계 포함) → 4 아니면 시가에 time_exit → 5 ctx.bar_events = 그 이벤트
→ 6 `Engine.on_bar`를 부르지 않는다(그 봉 고가·저가로 아무것도 판정하지 않는다) → 7 `on_minute_closed`는 부른다.
훅이 없는 전략은 기존 경로와 바이트 단위로 같다(단계 2b 전 코드로 만든 골든).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.engine_replay import ReplayContext, ReplayResult, replay, report_ledger
from exchange.loader import rules_from_snapshot_dir
from exchange.orders import Direction
from paper.engine import EntryIntent
from paper.types import PositionClosed
from sizing.config import RegimeSizing, SizingLimits
from tests.fixtures.dummy_replay_strategy import FIX, T0, Every30, bars

D = Decimal
ROOT = Path(__file__).resolve().parent.parent
R2 = RegimeSizing("t2", D("0.01"), 10, 30)
L2 = SizingLimits(leverage_range=(10, 30))


def flat(n: int, p: str = "60000", overrides: dict[int, tuple[str, str, str, str]] | None = None) -> list[Bar1m]:
    out = []
    for i in range(n):
        o, h, lo, c = (overrides or {}).get(i, (p, p, p, p))
        out.append(Bar1m(T0 + i * MINUTE_MS, o, h, lo, c, "1", c, 1, "0", "0", o, h, lo, c, "archive"))
    return out


class EnterThenExitAt:
    """분 `enter_at` 마감에 롱(SL `sl`)을 내고 분 `exit_at` 시가에 시간 청산을 요청한다."""

    def __init__(self, enter_at: int, exit_at: int, sl: str = "58800"):
        self.enter_at, self.exit_at, self.sl = enter_at, exit_at, D(sl)
        self.seen: list[int] = []
        self.events_at_exit: list[object] = []

    def exit_at_bar_open(self, bar: Bar1m) -> bool:
        return (bar.open_ms - T0) // MINUTE_MS == self.exit_at

    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext):
        i = (bar.open_ms - T0) // MINUTE_MS
        self.seen.append(i)
        if i == self.exit_at:
            self.events_at_exit = list(ctx.bar_events)
        if i == self.enter_at:
            m = bar.d("mark_close")
            return EntryIntent(Direction.LONG, self.sl, None, R2, decided_ms=ctx.now_ms, decision_mark=m)
        return None


def rules():
    return rules_from_snapshot_dir(FIX, "BTCUSDT")


def test_no_hook_path_matches_pre_2b_golden():
    """골든 = 이 본문을 2b 이전 트리(bdf0554)에서 실행한 출력(`tests/fixtures/golden_replay_nohook.json`).
    다시 만들려면 `git archive bdf0554`로 푼 트리에서 같은 호출을 돌린다 — 기본 경로를 바꾸는 변경은 골든을 고치지 않는다."""
    gold = json.loads((ROOT / "tests" / "fixtures" / "golden_replay_nohook.json").read_text())
    evs: list[list] = []
    r = replay(bars(2400), [Funding(T0 + 480 * MINUTE_MS, "0.0001", "60000"), Funding(T0 + 960 * MINUTE_MS, "-0.0002", "60100"),
                            Funding(T0 + 1440 * MINUTE_MS, "0.0003", "59900")], Every30(), rules=rules(),
               limits=SizingLimits(), equity=D("1000"), on_event=lambda e: evs.append([type(e).__name__, getattr(e, "ts_ms", None)]))
    got = json.loads(json.dumps({"trades": r.trades, "decisions": r.decisions, "final_wallet": str(r.final_wallet),
                                 "open_at_end": r.open_at_end, "events": evs}, sort_keys=True, default=str))
    assert got == gold


def test_time_exit_at_open_ignores_that_bars_high_low_and_still_calls_strategy():
    #  분 5: 시가 60,100 · 저가가 SL(58,800) 아래 — on_bar였다면 SL. 훅이므로 시가 time_exit만.
    b = flat(8, overrides={5: ("60100", "60200", "58000", "60000")})
    s = EnterThenExitAt(1, 5)
    r = replay(b, [], s, rules=rules(), limits=L2, equity=D("1000"))
    assert len(r.trades) == 1
    t = r.trades[0]
    assert t["exit_reason"] == "time_exit" and t["exit_ms"] == T0 + 5 * MINUTE_MS and t["exit_ref"] == "60100"
    assert 5 in s.seen                                               # 7: 23:59 봉도 전략이 본다(late_cross 집계)
    assert [type(e) for e in s.events_at_exit] == [PositionClosed]    # 5: 그 봉의 이벤트 = time_exit


def test_gap_liquidation_at_open_takes_precedence():
    b = flat(8, overrides={5: ("40000", "40000", "40000", "40000")})
    r = replay(b, [], EnterThenExitAt(1, 5), rules=rules(), limits=L2, equity=D("1000"))
    t = r.trades[0]
    assert t["exit_reason"] == "liquidation" and t["exit_ms"] == T0 + 5 * MINUTE_MS


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
def test_gap_liquidation_boundary_exit_ref_is_refreshed_liq_price(direction):
    """경계(시가 == 펀딩 뒤 갱신된 추정 청산가)도 청산 · exit_ref = 그 청산가 · 숏도."""
    sl = "58800" if direction is Direction.LONG else "61200"

    class S(EnterThenExitAt):
        def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext):
            i = (bar.open_ms - T0) // MINUTE_MS
            if i == 1:
                return EntryIntent(direction, D(sl), None, R2, decided_ms=ctx.now_ms, decision_mark=bar.d("mark_close"))
            if i == 3 and ctx.engine.position is not None:
                self.liq = ctx.engine.position.liq_price_est
            return None

    probe = S(1, 99)
    replay(flat(6), [Funding(T0 + 3 * MINUTE_MS, "0.002", "60000")], probe, rules=rules(), limits=L2, equity=D("1000"))
    liq = probe.liq
    b = flat(8, overrides={5: (str(liq), str(liq), str(liq), str(liq))})
    r = replay(b, [Funding(T0 + 3 * MINUTE_MS, "0.002", "60000")], S(1, 5), rules=rules(), limits=L2, equity=D("1000"))
    t = r.trades[0]
    assert t["exit_reason"] == "liquidation" and D(t["exit_ref"]) == liq


def test_replay_liq_fee_option_reaches_realized_pnl():
    """재생 수준: 같은 갭 청산에서 두 기준의 순손익 차이 = 수량 × (진입 체결가 − 추정 청산가) × liquidationFee(롱)."""
    b = flat(8, overrides={5: ("40000", "40000", "40000", "40000")})
    rs = {}
    for on in (False, True):
        lim = SizingLimits(leverage_range=(10, 30), liq_fee_on_liq_price=on)
        rs[on] = replay(b, [], EnterThenExitAt(1, 5), rules=rules(), limits=lim, equity=D("1000"),
                        sizing_capital=D("1000")).trades[0]
    t0, t1 = rs[False], rs[True]
    assert t0["exit_reason"] == t1["exit_reason"] == "liquidation" and t0["exit_ref"] == t1["exit_ref"]
    fee = rules().symbol_rules.liquidation_fee
    diff = D(t1["net_pnl"]) - D(t0["net_pnl"])                # net_pnl 문자열은 28자리 문맥에서 만들어진다 → 1e-20 USDT 허용
    assert abs(diff - D(t0["qty"]) * (D(t0["entry_fill"]) - D(t0["exit_ref"])) * fee) < D("1e-20") and diff > 0


def test_intent_emitted_on_the_hook_bar_is_an_error():
    class Late(EnterThenExitAt):
        def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext):
            if (bar.open_ms - T0) // MINUTE_MS == 5:
                return EntryIntent(Direction.LONG, D("58800"), None, R2, decided_ms=ctx.now_ms, decision_mark=bar.d("mark_close"))
            return None

    with pytest.raises(AssertionError):
        replay(flat(8), [], Late(0, 5), rules=rules(), limits=L2, equity=D("1000"))


def test_replay_result_fields_unchanged():
    assert [f for f in ReplayResult.__dataclass_fields__] == ["trades", "decisions", "final_wallet", "open_at_end"]


def test_funding_in_the_hook_minute_is_settled_before_the_exit():
    base = replay(flat(8), [], EnterThenExitAt(1, 5), rules=rules(), limits=L2, equity=D("1000")).trades[0]
    t = replay(flat(8), [Funding(T0 + 5 * MINUTE_MS, "0.001", "60000")], EnterThenExitAt(1, 5), rules=rules(), limits=L2,
               equity=D("1000")).trades[0]
    assert t["exit_reason"] == base["exit_reason"] == "time_exit"
    assert D(base["net_pnl"]) - D(t["net_pnl"]) == D(t["qty"]) * D("60000") * D("0.001")


def test_pending_entry_at_hook_bar_is_an_error():
    with pytest.raises(AssertionError):
        replay(flat(8), [], EnterThenExitAt(4, 5), rules=rules(), limits=L2, equity=D("1000"))


def test_fixed_capital_trade_baseline_is_e_ref():
    b = flat(20, overrides={5: ("60100", "60100", "60100", "60100"), 15: ("59000", "59000", "59000", "59000")})

    class Two(EnterThenExitAt):
        def exit_at_bar_open(self, bar: Bar1m) -> bool:
            return (bar.open_ms - T0) // MINUTE_MS in (5, 15)

        def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext):
            i = (bar.open_ms - T0) // MINUTE_MS
            if i in (1, 11):
                return EntryIntent(Direction.LONG, D("58800"), None, R2, decided_ms=ctx.now_ms, decision_mark=bar.d("mark_close"))
            return None

    r = replay(b, [], Two(0, 0), rules=rules(), limits=L2, equity=D("1000"), sizing_capital=D("1000"))
    assert len(r.trades) == 2
    for t in r.trades:
        assert t["wallet_before"] == "1000"
    #  두 번째 트레이드의 사이징·기준 = E_ref(누적 지갑이 아니다) · 보고 원장 = net_pnl 합
    assert D(r.trades[1]["wallet_after"]) - D("1000") == D(r.trades[1]["net_pnl"])
    assert report_ledger(r.trades) == D(r.trades[0]["net_pnl"]) + D(r.trades[1]["net_pnl"])
