"""P1 시간 청산 실행기 — **정본 엔진 경로를 그대로 쓴다**(두 번째 체결 모델을 만들지 않는다 · 사전등록 §11).

한 플라시보 트레이드 = 분 `t` mark 시가 진입 → 분 `t+h−1` mark 종가 시간 청산(SL·TP 없음). 절차:
1. 진입 체결가 = `PaperSender.quote_fill_price`(레지스트리 #7 불리 모델) · 사이징 = 정본 `size_entry`(B2)에
   `sl = 체결가 × (1 ∓ sl_dist)`를 넣어 수량·레버리지를 얻는다(엔진 `_execute_entry`와 같은 호출).
2. 그 포지션을 `Engine.restore_position`으로 엔진에 넣는다 — **SL은 닿을 수 없는 값**(롱 0 · 숏 매우 큼), TP 없음 →
   엔진의 **청산(liquidation) 판정·펀딩 정산·청산 체결**만 작동한다. 추정 청산가는 엔진이 현재 규칙으로 다시 계산한다.
3. 분마다: 그 분에 든 확정 펀딩(진입 뒤 · 청산 시각 이하)을 `on_funding`으로 정산 → `on_bar`(mark 봉)로 청산 판정.
   **내부 결손 분**(mark 봉 없음 — 규약 b는 진입·청산 분만 요구)은 펀딩만 정산하고 판정 없이 넘긴다(Codex 단계 d #1).
4. 마지막 분: `close_now(ref_mark = mark 종가)`.
진입 수수료는 엔진 `_execute_entry`처럼 지갑에서 뺀다(복원 경로는 빼지 않으므로 여기서).
**equity**: 플라시보 트레이드는 **초기 자본 고정**으로 각각 사이징한다(구현 규약 — 트레이드당 수익률은 명목 대비 bps라 규모와 무관).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.returns import TradeReturn, trade_return
from exchange.gate import Mode
from exchange.orders import Direction, Intent, side_for
from exchange.rules import RuntimeRules
from paper.engine import Engine
from paper.sender import PaperSender
from paper.types import ExitReason, MarkBar, PositionClosed
from sizing.config import RegimeSizing, SizingLimits
from sizing.position import size_entry

UNREACHABLE_SHORT_SL = Decimal("1e12")


def _dir(direction: int) -> Direction:
    return Direction.LONG if direction == 0 else Direction.SHORT


def mark_bar(b: Bar1m) -> MarkBar:
    return MarkBar(b.open_ms, b.open_ms + MINUTE_MS - 1, b.d("mark_open"), b.d("mark_high"), b.d("mark_low"), b.d("mark_close"))


def sizing_decision(entry_mark: Decimal, direction: int, sl_dist: Decimal, rules: RuntimeRules, limits: SizingLimits,
                    equity: Decimal, regime: RegimeSizing):
    d = _dir(direction)
    fill = PaperSender(rules).quote_fill_price(side_for(d, Intent.ENTRY), entry_mark)
    sl = fill * (1 - sl_dist) if d is Direction.LONG else fill * (1 + sl_dist)
    return fill, size_entry(fill, sl, d, equity, regime, rules, limits)


@dataclass(frozen=True)
class TimeExitResult:
    ok: bool
    reason: str                                # "time_exit" · "liquidation" · "sizing_refused"
    ret: TradeReturn | None


def run_time_exit(bars: dict[int, Bar1m], fundings: Sequence[Funding], *, entry_ms: int, h: int, direction: int,
                  sl_dist: Decimal, rules: RuntimeRules, limits: SizingLimits, equity: Decimal,
                  regime: RegimeSizing) -> TimeExitResult:
    first = bars[entry_ms]
    fill, dec = sizing_decision(first.d("mark_open"), direction, sl_dist, rules, limits, equity, regime)
    if not dec.ok or dec.leverage is None:
        return TimeExitResult(False, "sizing_refused", None)
    d = _dir(direction)
    commission = dec.qty * fill * rules.commission.taker
    eng = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=equity, limits=limits)
    nf = min((f.funding_ms for f in fundings if f.funding_ms > entry_ms), default=entry_ms + 8 * 3_600_000)
    eng.restore_position({
        "direction": d.value, "qty": str(dec.qty), "entry_price": str(fill), "leverage": dec.leverage,
        "sl": "0" if d is Direction.LONG else str(UNREACHABLE_SHORT_SL), "tp": None,
        "liq_price_est": str(dec.liq_price_est), "entry_commission": str(commission), "funding_paid": "0",
        "opened_ms": entry_ms, "liq_alerted": False, "next_funding_ms": nf}, ts_ms=entry_ms, detail="p1_placebo")
    eng.wallet = equity - commission
    exit_minute = entry_ms + (h - 1) * MINUTE_MS
    exit_ms = exit_minute + MINUTE_MS - 1
    pending = sorted((f for f in fundings if entry_ms < f.funding_ms <= exit_ms), key=lambda f: f.funding_ms)
    closed: PositionClosed | None = None
    exit_ref = Decimal(0)
    t = entry_ms
    while t <= exit_minute and closed is None:
        while pending and pending[0].funding_ms < t + MINUTE_MS:
            f = pending.pop(0)
            eng.on_funding(ts_ms=f.funding_ms, rate=Decimal(f.rate), mark=Decimal(f.mark))
        b = bars.get(t)
        if b is None:                                        # 내부 결손 분(규약 b는 양 끝 분의 mark만 요구) — 판정 없이 넘긴다
            t += MINUTE_MS
            continue
        assert eng.position is not None
        liq_now = eng.position.liq_price_est                 # 이 봉에서 청산되면 gross 기준가(펀딩으로 갱신된 값)
        for ev in eng.on_bar(mark_bar(b)):
            if isinstance(ev, PositionClosed):
                closed, exit_ref = ev, liq_now
        t += MINUTE_MS
    reason = "liquidation"
    if closed is None:
        last = bars[exit_minute]
        exit_ref = last.d("mark_close")
        for ev in eng.close_now(ref_mark=exit_ref, ts_ms=exit_ms, reason=ExitReason.MANUAL):
            if isinstance(ev, PositionClosed):
                closed = ev
        reason = "time_exit"
    assert closed is not None
    return TimeExitResult(True, reason, trade_return(direction=d, entry_mark=first.d("mark_open"), exit_ref=exit_ref,
                                                     qty=dec.qty, entry_fill=fill, wallet_before=equity,
                                                     wallet_after=closed.wallet_after))


def p1_null_distribution(draws, bars: dict[int, Bar1m], fundings: Sequence[Funding], *, rules: RuntimeRules,
                         limits: SizingLimits, equity: Decimal, regime: RegimeSizing) -> list[dict[str, str | int]]:
    """성공한 추출마다 **트레이드당 평균 net_bps**(P1 귀무분포의 한 점). 실패 추출은 넣지 않는다(규약 f).
    각 배치 슬롯은 `run_time_exit`로 정본 엔진을 거친다. 결과는 Decimal 문자열 — 바이트 비교 가능."""
    out: list[dict[str, str | int]] = []
    for dr in draws:
        if not dr.ok:
            continue
        nets = []
        for p in dr.placed:
            r = run_time_exit(bars, fundings, entry_ms=p.entry_ms, h=p.h, direction=p.direction, sl_dist=p.sl_dist,
                              rules=rules, limits=limits, equity=equity, regime=regime)
            if not r.ok or r.ret is None:
                raise AssertionError(f"추출 {dr.draw} 슬롯 {p.slot}: 배치 때 수락된 사이징이 실행에서 거부됐다")
            nets.append(r.ret.net_bps)
        out.append({"draw": dr.draw, "n": len(nets), "mean_net_bps": str(sum(nets, Decimal()) / len(nets))})
    return out
