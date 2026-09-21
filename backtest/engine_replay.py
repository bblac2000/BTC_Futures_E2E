"""봉 단위 재생 루프(단계 2a) — **전략 프로세스 안에서** 돈다(격리 실행의 하위 절반). 체결은 정본 `paper/engine.py` + `PaperSender`.

분 m(open_ms t)마다 순서(백테스트 근사 · 사전등록 §1 "SL/TP 판정 가격 = mark 1m 시계열"):
1. 분 m 안의 확정 펀딩(`t ≤ funding_ms < t+1분`)을 `Engine.on_funding`으로 정산(포지션이 있을 때만).
2. `Engine.on_bar(mark 봉 m)` — 직전 분에 낸 진입 의도는 **분 m의 mark 시가**에 체결된다("다음 1m 봉 첫 mark 틱"의 봉 근사) ·
   같은 봉에서 청산 > SL > TP 우선순위 · SL 체결 기준 = SL과 시가 중 불리한 쪽(엔진 규칙 그대로).
3. 분 m **마감 뒤** 전략이 판단한다(분 m 종가까지의 정보만) → 진입 의도는 `decided_ms = 분 m 마감`으로 낸다.
전략은 `on_minute_closed(bar, ctx) -> EntryIntent | None`만 구현하면 된다. 결정·건너뜀 사유는 전략이 `ctx.skip(reason)`으로 남긴다.
창 끝에 열린 포지션은 **트레이드로 세지 않고** `open_at_end`로 따로 보고한다(사전등록이 정하지 않았다 — 단계 d Codex 질문).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.placebo_exec import mark_bar
from backtest.returns import trade_return
from exchange.gate import Mode
from exchange.rules import RuntimeRules
from paper.engine import Engine, EntryIntent, EntryRefused
from paper.sender import PaperSender
from paper.types import EntryFilled, EntrySkipped, PositionClosed
from sizing.config import SizingLimits


@dataclass
class ReplayContext:
    engine: Engine
    decisions: list[dict[str, Any]] = field(default_factory=list)
    now_ms: int = 0

    @property
    def has_position(self) -> bool:
        return self.engine.position is not None or self.engine.pending is not None

    def skip(self, reason: str, **detail: Any) -> None:
        self.decisions.append({"ts_ms": self.now_ms, "outcome": "skipped", "reason": reason, **detail})


class Strategy(Protocol):
    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None: ...


@dataclass
class ReplayResult:
    trades: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    final_wallet: Decimal
    open_at_end: dict[str, Any] | None = None     # 창 끝에 열린 포지션 — 트레이드로 세지 않고 따로 보고(사전등록에 규칙 없음 · Codex 검토)


def replay(bars: Sequence[Bar1m], fundings: Sequence[Funding], strategy: Strategy, *, rules: RuntimeRules,
           limits: SizingLimits, equity: Decimal, on_event: Callable[[object], None] | None = None) -> ReplayResult:
    eng = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=equity, limits=limits)
    ctx = ReplayContext(eng)
    trades: list[dict[str, Any]] = []
    open_trade: dict[str, Any] | None = None
    fi = 0
    fs = sorted(fundings, key=lambda f: f.funding_ms)
    for b in bars:
        t = b.open_ms
        while fi < len(fs) and fs[fi].funding_ms < t + MINUTE_MS:
            if fs[fi].funding_ms >= t and eng.position is not None:
                eng.on_funding(ts_ms=fs[fi].funding_ms, rate=Decimal(fs[fi].rate), mark=Decimal(fs[fi].mark))
            fi += 1
        wallet_before = eng.wallet
        liq_now = eng.position.liq_price_est if eng.position is not None else None   # 이 봉에서 청산되면 gross 기준가
        for ev in eng.on_bar(mark_bar(b)):
            if on_event is not None:
                on_event(ev)
            if isinstance(ev, EntryFilled):
                open_trade = {"trade_id": len(trades), "entry_ms": t, "direction": ev.decision.direction.value,
                              "entry_mark": str(b.d("mark_open")), "entry_fill": str(ev.post_fill.entry_price),
                              "qty": str(ev.post_fill.qty), "leverage": ev.leverage, "sl": str(ev.decision.sl),
                              "sl_dist": str(ev.post_fill.sl_dist_pct), "wallet_before": str(wallet_before)}
                ctx.decisions.append({"ts_ms": t, "outcome": "entered", "trade_id": open_trade["trade_id"]})
                liq_now = ev.post_fill.liq_price_est             # 같은 봉에서 바로 청산되는 경우의 gross 기준가
            elif isinstance(ev, EntrySkipped):
                ctx.decisions.append({"ts_ms": t, "outcome": "skipped", "reason": str(ev.reason), "detail": ev.detail})
            elif isinstance(ev, PositionClosed) and open_trade is not None:
                #  gross는 mark 기준(슬리피지 전 · returns.py 정의): 한 청산의 체결들은 같은 `ref_mark`(SL 기준가·TP·mark 종가)를 갖는다.
                #  체결가(exit_price)는 레지스트리 #7 불리 모델이 들어간 값이라 쓰지 않는다. 청산(liquidation)은 체결이 없어 추정 청산가.
                refs = {f.ref_mark for f in ev.fills if f.ref_mark is not None}
                if len(refs) > 1:
                    raise AssertionError(f"한 청산의 체결 ref_mark가 여럿: {refs}")
                ref = refs.pop() if refs else (liq_now if liq_now is not None else Decimal(open_trade["sl"]))
                r = trade_return(direction=ev.direction, entry_mark=Decimal(open_trade["entry_mark"]), exit_ref=ref,
                                 qty=Decimal(open_trade["qty"]), entry_fill=Decimal(open_trade["entry_fill"]),
                                 wallet_before=Decimal(open_trade["wallet_before"]), wallet_after=ev.wallet_after)
                trades.append(open_trade | {"exit_ms": ev.ts_ms, "exit_reason": str(ev.reason), "exit_ref": str(ref),
                                            "wallet_after": str(ev.wallet_after), "gross_bps": str(r.gross_bps),
                                            "net_bps": str(r.net_bps), "net_pnl": str(r.net_pnl)})
                open_trade = None
        ctx.now_ms = t + MINUTE_MS - 1
        intent = strategy.on_minute_closed(b, ctx)
        if intent is not None:
            try:
                eng.request_entry(intent)
            except EntryRefused as e:
                ctx.skip("entry_refused", detail=str(e))
    return ReplayResult(trades, ctx.decisions, eng.wallet, open_trade)
