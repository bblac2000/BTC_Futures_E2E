"""봉 단위 재생 루프(단계 2a) — **전략 프로세스 안에서** 돈다(격리 실행의 하위 절반). 체결은 정본 `paper/engine.py` + `PaperSender`.

분 m(open_ms t)마다 순서(백테스트 근사 · 사전등록 §1 "SL/TP 판정 가격 = mark 1m 시계열"):
1. 분 m 안의 확정 펀딩(`t ≤ funding_ms < t+1분`)을 `Engine.on_funding`으로 정산(포지션이 있을 때만).
2. `Engine.on_bar(mark 봉 m)` — 직전 분에 낸 진입 의도는 **분 m의 mark 시가**에 체결된다("다음 1m 봉 첫 mark 틱"의 봉 근사) ·
   같은 봉에서 청산 > SL > TP 우선순위 · SL 체결 기준 = SL과 시가 중 불리한 쪽(엔진 규칙 그대로).
3. 분 m **마감 뒤** 전략이 판단한다(분 m 종가까지의 정보만) → 진입 의도는 `decided_ms = 분 m 마감`으로 낸다.
전략은 `on_minute_closed(bar, ctx) -> EntryIntent | None`만 구현하면 된다. 결정·건너뜀 사유는 전략이 `ctx.skip(reason)`으로 남긴다.
`ctx.bar_events` = 그 분 `on_bar`의 엔진 이벤트(전략이 청산 시각을 알아 쿨다운을 건다).
창 끝에 열린 포지션은 **트레이드로 세지 않고** `open_at_end`로 따로 보고한다(사전등록이 정하지 않았다 — 단계 d Codex 질문).

트라이얼 #2 확장(단계 2c · 기본 꺼짐 — 훅 없는 전략은 기존 경로 그대로 · 골든 테스트):
- 전략에 `exit_at_bar_open(bar) -> bool`이 있고 참이면 그 분은: 1 펀딩 → 2 대기 진입 없음 단언 → 3 시가 갭 청산(경계 포함) →
  4 살아 있으면 시가에 `TIME_EXIT` → 5 `ctx.bar_events` = 그 이벤트 → 6 `Engine.on_bar`를 부르지 않는다 → 7 `on_minute_closed`는 부른다.
- `sizing_capital`(E_ref): 엔진이 체결된 진입마다 실행 지갑을 E_ref로 리셋 → 트레이드 기준 지갑 = E_ref ·
  보고 원장 = `report_ledger(trades)`(트레이드 순손익 누적 · 사이징·적격성에 쓰이지 않는다 · `final_wallet`은 이 모드에서 의미 없음).
- 훅 분에는 `on_minute_closed` 뒤에도 대기 진입이 없어야 한다(날을 넘는 진입 금지 — late_cross가 막아야 한다).
- 청산 수수료 기준은 `limits.liq_fee_on_liq_price`(트라이얼 #2 §1)로 엔진·사이징에 함께 들어간다.
- 전략에 `before_minute(bar, engine)`이 있으면 그 분의 **펀딩·엔진 처리 전에** 부른다(검사 전용 — 트라이얼 #2 날 경계 가드).

트라이얼 #3 (b)(계획 r2 B1 · 기본 = 레지스트리 #7 2 bps — 트라이얼 #1·#2·봇 경로 불변): `slippage_rate`는 이 재생의 `PaperSender`
불리 체결 모델 매개변수다(진입 견적·진입·모든 청산 체결 · 청산(liquidation)은 송신기를 거치지 않는다). 트라이얼 #3 = 0.0006(§2).
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
from paper.config import PAPER_SLIPPAGE_RATE
from paper.engine import Engine, EntryIntent, EntryRefused
from paper.sender import PaperSender
from paper.types import EntryFilled, EntrySkipped, ExitReason, PositionClosed
from sizing.config import SizingLimits


@dataclass
class ReplayContext:
    engine: Engine
    decisions: list[dict[str, Any]] = field(default_factory=list)
    now_ms: int = 0
    bar_events: list[object] = field(default_factory=list)     # 이번 분 `on_bar`가 낸 엔진 이벤트(체결·청산 — 쿨다운 등)

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
           limits: SizingLimits, equity: Decimal, on_event: Callable[[object], None] | None = None,
           sizing_capital: Decimal | None = None, slippage_rate: Decimal = PAPER_SLIPPAGE_RATE) -> ReplayResult:
    eng = Engine(rules, PaperSender(rules, slippage_rate=slippage_rate), mode=Mode.PAPER, wallet=equity, limits=limits,
                 sizing_capital=sizing_capital)
    exit_hook: Callable[[Bar1m], bool] | None = getattr(strategy, "exit_at_bar_open", None)
    pre_hook: Callable[[Bar1m, Engine], None] | None = getattr(strategy, "before_minute", None)
    ctx = ReplayContext(eng)
    trades: list[dict[str, Any]] = []
    open_trade: dict[str, Any] | None = None
    fi = 0
    fs = sorted(fundings, key=lambda f: f.funding_ms)
    for b in bars:
        t = b.open_ms
        if pre_hook is not None:
            pre_hook(b, eng)
        while fi < len(fs) and fs[fi].funding_ms < t + MINUTE_MS:
            if fs[fi].funding_ms >= t and eng.position is not None:
                eng.on_funding(ts_ms=fs[fi].funding_ms, rate=Decimal(fs[fi].rate), mark=Decimal(fs[fi].mark))
            fi += 1
        wallet_before = eng.wallet
        liq_now = eng.position.liq_price_est if eng.position is not None else None   # 이 봉에서 청산되면 gross 기준가
        hook_bar = exit_hook is not None and exit_hook(b)
        if hook_bar:
            #  봉 시가 청산(트라이얼 #2 §1 23:59): 대기 진입이 있으면 규칙 위반(late_cross · P2 drop이 막아야 한다)
            assert eng.pending is None, f"봉 시가 청산 분 {t}에 대기 진입이 있다"
            o = b.d("mark_open")
            ctx.bar_events = eng.liquidate_if_open_beyond(o, ts_ms=t)
            if eng.position is not None:
                ctx.bar_events += eng.close_now(ref_mark=o, ts_ms=t, reason=ExitReason.TIME_EXIT)
        else:
            ctx.bar_events = eng.on_bar(mark_bar(b))
        for ev in ctx.bar_events:
            if on_event is not None:
                on_event(ev)
            if isinstance(ev, EntryFilled):
                open_trade = {"trade_id": len(trades), "entry_ms": t, "direction": ev.decision.direction.value,
                              "entry_mark": str(b.d("mark_open")), "entry_fill": str(ev.post_fill.entry_price),
                              "qty": str(ev.post_fill.qty), "leverage": ev.leverage, "sl": str(ev.decision.sl),
                              "tp": None if eng.last_entry_tp is None else str(eng.last_entry_tp),
                              "sl_dist": str(ev.post_fill.sl_dist_pct),
                              "wallet_before": str(wallet_before if sizing_capital is None else sizing_capital)}
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
        if hook_bar:
            assert eng.pending is None, f"봉 시가 청산 분 {t}의 전략 판단이 진입을 냈다(다음 날로 넘어가는 진입)"
    return ReplayResult(trades, ctx.decisions, eng.wallet, open_trade)


def report_ledger(trades: Sequence[dict[str, Any]]) -> Decimal:
    """고정 사이징 자본 모드의 보고 원장 — 트레이드 순손익(`net_pnl`)의 누적 합(판정·사이징에 쓰이지 않는다)."""
    return sum((Decimal(t["net_pnl"]) for t in trades), Decimal(0))
