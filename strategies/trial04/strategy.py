"""트라이얼 #4 전략 — 암 하나(S 또는 L)의 상태 기계((d) · 규약 C24~C36 · 사전등록 r3 §1 · §4 P2/P3 · §7-3).

상태: IDLE → (극단 인쇄 T · 결정 = 시작 T 봉 마감) ENTRY_PENDING(P2는 DELAYED 뒤) → IN_POSITION → WAIT(히스테리시스) → IDLE.
인쇄 처리: 시작 T인 mark 봉의 마감(= T + 1분 = 체결 봉 시가와 같은 시각)에서 한 번 · 창 안 경계 T마다 사유 정확히 하나(C29 · 고정 순서):
decision_bar_missing → print_invalid → distribution_undefined → print_incomplete → not_extreme → position_busy → wait_absorbed →
not_evaluable{…} → sl_dist_out_of_range{floor|ceiling} → sizing_rejected_decision → candidate.
후보의 진입 종결: filled(→ exit{sl|liquidation|time_exit}) · sl_crossed_before_fill · sizing_rejected_fill · normalization.

- 분포 편입은 시각 기준(C28): T ≤ 지금 봉 시작인 유효 인쇄는 자기 분류 **뒤에** 후행 분포에 들어간다 · 창 전 인쇄는 편입만.
- SL 기준가(C25 [PROPOSED]) = 체결 봉(T + 1분) mark 시가 — 결정 시각 = 체결 시각(r3 결정 4). 엔진에는 고정 SL을 준다.
- 포지션 중 극단 인쇄 = 정상 기록 `position_busy`(실행 실패 아님 — 결정 단계 관문 `busy_check`는 쓰지 않는다 · B14).
- 히스테리시스(C32): 청산 → WAIT · **T > 청산 체결 시각**인 인쇄가 (Q0.10, Q0.90) 안(엄격)이면 IDLE · 불완전 인쇄는 해제하지 않는다.
- `on_minute_closed` 순서(C33): 일정 observe → 엔진 이벤트 → 진행(P2 지연 의도) → 분류.
- P2(+k 인쇄): 결정 값은 T에 고정 · 의도는 시작 T + k·8h 봉 마감에. P3: 판정은 암의 방향 · 의도는 반대 · SL′ = 기준가에 대한 거울상.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backtest.data import MINUTE_MS, Bar1m
from backtest.engine_replay import ReplayContext
from exchange.normalize import RejectReason, normalize_price
from exchange.orders import Direction
from exchange.rules import RuntimeRules
from paper.engine import EntryIntent
from paper.types import EntryFilled, EntrySkipped, ExitReason, PositionClosed, SkipReason
from sizing.position import size_entry
from strategies.trial04 import anchor as A
from strategies.trial04.config import LIMITS, REGIME, TC_V3, TcParams
from strategies.trial04.exit_schedule import schedule
from strategies.trial04.features import DailyAtr, TrailingPrints

DAY = 86_400_000
H8 = A.H8_MS
ARM_DIRECTION = {"S": Direction.SHORT, "L": Direction.LONG}
NORMALIZATION = {RejectReason.BELOW_MIN_QTY, RejectReason.MIN_NOTIONAL}
BUSY_STATES = ("ENTRY_PENDING", "DELAYED", "IN_POSITION")


class RunInvariantError(RuntimeError):
    """PAPER 재생에서 나올 수 없는 경로(대기 의도 없는 체결 · 술어 통과 뒤 ATR 없음 · P2 의도 봉 없음 등) — 실행 실패."""


@dataclass(frozen=True)
class Variant:
    delay: int = 0                  # P2: 1 또는 3(인쇄)
    invert: bool = False            # P3

    def __post_init__(self):
        if self.delay not in (0, *TC_V3.p2_delays) or (self.delay and self.invert):
            raise ValueError(f"등록되지 않은 변형 {self}")

    @property
    def name(self) -> str:
        return "P3_invert" if self.invert else (f"P2_print{self.delay}" if self.delay else "base")


BASE = Variant()

Eligible = Callable[[int], str | None]             # 체결 봉 t → None(판정 가능) | 사유
FillReference = Callable[[int, int], Decimal]      # (체결 봉 t, 결정 중인 T) → 그 봉의 mark 시가(T + 1분 키만)


class Trial04:
    def __init__(self, arm: str, *, rules: RuntimeRules, prints: Sequence[dict[str, Any]], eligible: Eligible,
                 fill_ref: FillReference, variant: Variant = BASE, p: TcParams = TC_V3,
                 window: tuple[int, int] = (A.WINDOW_START_MS, A.IS_END_MS)):
        if arm not in ARM_DIRECTION:
            raise ValueError(f"arm {arm}")
        self.arm, self.dir, self.rules, self.eligible, self.fill_ref = arm, ARM_DIRECTION[arm], rules, eligible, fill_ref
        self.variant, self.p, self.window = variant, p, window
        self.prints = list(prints)
        self.pi = 0                                                   # 다음에 처리할 인쇄
        self.sched = schedule()
        self.trail = TrailingPrints(p)
        self.atr = DailyAtr(p)
        self.state = "IDLE"
        self.exit_ts: int | None = None                               # 마지막 청산 체결 시각(WAIT)
        self.ev: dict[str, Any] | None = None                         # 진행 중 후보
        self.events: list[dict[str, Any]] = []                        # 전략 소유 기록(JSONL)
        self.funnel: Counter[str] = Counter()                         # 인쇄 깔때기(창 안 경계 전부)
        self.sub: Counter[str] = Counter()                            # 보고 전용 부사유
        self.entry: Counter[str] = Counter()                          # 진입 종결 + 청산 사유
        self.intents: list[dict[str, Any]] = []
        self.filled_intents: list[dict[str, Any]] = []
        self.dist_defined: dict[int, bool] = {}                       # 창 날 → 00:00 경계에서 분포 정의(V · C35)
        self.window_prints = 0
        self.ingested = 0
        self.started = False

    # ── 재생 훅 ──────────────────────────────────────────────────────────
    def before_minute(self, bar: Bar1m, engine: Any) -> None:
        self.sched.guard(bar)
        if bar.open_ms >= self.window[0] and not self.started:
            if engine.position is not None or engine.pending is not None or self.state != "IDLE":
                raise RunInvariantError("창 첫 봉에서 장부가 평평하지 않다")
            self.started = True

    def exit_at_bar_open(self, bar: Bar1m) -> bool:
        return self.sched.exit_at_bar_open(bar)

    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        self.sched.observe(bar, ctx.bar_events)
        self._engine_events(bar, ctx.bar_events)
        self.atr.add(bar)
        intent = self._advance(bar, ctx)
        decided = self._prints_upto(bar, ctx)
        if intent is not None and decided is not None:
            raise RunInvariantError(f"한 봉 {bar.open_ms}에서 의도 둘")
        return intent if intent is not None else decided

    # ── 인쇄(시각 기준 편입 · 창 안은 분류) ──────────────────────────────
    def _prints_upto(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        intent: EntryIntent | None = None
        while self.pi < len(self.prints) and self.prints[self.pi]["T"] <= bar.open_ms:
            pr = self.prints[self.pi]
            self.pi += 1
            t_print = int(pr["T"])
            if self.window[0] <= t_print + MINUTE_MS and t_print <= self.window[1]:
                self.window_prints += 1
                q = self.trail.quantiles()
                if t_print % DAY == 0:
                    self.dist_defined[t_print // DAY] = q is not None
                got = self._classify(pr, t_print, q, bar, ctx)
                if got is not None:
                    if intent is not None:
                        raise RunInvariantError(f"한 봉 {bar.open_ms}에서 후보 둘")
                    intent = got
            if pr["valid"]:
                self.trail.add(float(pr["p"]))                         # 자기 분류 뒤 편입("엄격히 앞선")
                self.ingested += 1
        return intent

    def _note(self, pr: dict[str, Any], q: tuple[float, float] | None, reason: str, sub: str | None = None) -> None:
        self.funnel[reason] += 1
        if sub:
            self.sub[f"{reason}.{sub}"] += 1
        self.events.append({"kind": "print", "arm": self.arm, "T": pr["T"], "p": pr["p"], "n_minutes": pr["n_minutes"],
                            "q10": None if q is None else q[0], "q90": None if q is None else q[1], "reason": reason,
                            "sub": sub, "state": self.state})

    def _classify(self, pr: dict[str, Any], t_print: int, q: tuple[float, float] | None, bar: Bar1m,
                  ctx: ReplayContext) -> EntryIntent | None:
        if bar.open_ms != t_print:
            return self._note(pr, q, "decision_bar_missing")
        if not pr["valid"]:
            return self._note(pr, q, "print_invalid")
        if q is None:
            return self._note(pr, q, "distribution_undefined")
        if not pr["complete"]:
            return self._note(pr, q, "print_incomplete")
        p = float(pr["p"])
        extreme = p >= q[1] if self.dir is Direction.SHORT else p <= q[0]
        if not extreme:
            self._note(pr, q, "not_extreme")
            if self.state == "WAIT" and self.exit_ts is not None and t_print > self.exit_ts and q[0] < p < q[1]:
                self._to("IDLE", t_print + MINUTE_MS)
            return None
        if self.state in BUSY_STATES:
            return self._note(pr, q, "position_busy")
        if self.state == "WAIT":
            return self._note(pr, q, "wait_absorbed")
        t = t_print + MINUTE_MS                                        # 체결 봉 시작 = 결정 시각
        why = self.eligible(t)
        if why is not None:
            return self._note(pr, q, "not_evaluable", why)
        atr, miss = self.atr.atr(t // DAY)
        if atr is None:
            if miss == "prev_close":
                return self._note(pr, q, "not_evaluable", "atr_prev_close")
            raise RunInvariantError(f"결정 {t}: 술어는 통과했는데 ATR_1d가 없다({miss})")
        ref = self.fill_ref(t, t_print)
        k = self.p.k_sl
        short = self.dir is Direction.SHORT
        sl_raw = ref + k * atr if short else ref - k * atr
        sl_dist = k * atr / ref
        ev: dict[str, Any] = {"T": t_print, "t": t, "p": pr["p"], "q10": q[0], "q90": q[1], "ref": str(ref), "atr": str(atr),
                              "sl_raw": str(sl_raw), "sl_dist": str(sl_dist)}
        if sl_dist < self.p.sl_floor:
            return self._note(pr, q, "sl_dist_out_of_range", "floor")
        if sl_dist > self.p.sl_ceiling:
            return self._note(pr, q, "sl_dist_out_of_range", "ceiling")
        sl = normalize_price(sl_raw, self.rules.symbol_rules)
        d = size_entry(ref, sl, self.dir, self.p.e_ref, REGIME, self.rules, LIMITS)
        ev |= {"sl": str(sl), "decision_leverage": d.leverage, "decision_qty": str(d.qty), "decision_notional": str(d.notional)}
        if not d.ok:
            return self._note(pr, q, "sizing_rejected_decision", None if d.reason is None else str(d.reason))
        if self.variant.invert:
            ev["intent_dir"] = (Direction.LONG if short else Direction.SHORT).value
            ev["intent_sl"] = str(normalize_price(ref - k * atr if short else ref + k * atr, self.rules.symbol_rules))
        else:
            ev["intent_dir"], ev["intent_sl"] = self.dir.value, str(sl)
        ev["fill_open"] = t + self.variant.delay * H8
        self._note(pr, q, "candidate")
        self.ev = ev
        if self.variant.delay:
            ev["emit_open"] = t_print + self.variant.delay * H8
            self._to("DELAYED", t)
            return None
        return self._emit(bar, ctx)

    # ── P2 지연 의도 ─────────────────────────────────────────────────────
    def _advance(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        if self.state != "DELAYED":
            return None
        assert self.ev is not None
        if bar.open_ms > self.ev["emit_open"]:
            raise RunInvariantError(f"P2 지연 의도의 봉 {self.ev['emit_open']}이 없다")
        return self._emit(bar, ctx) if bar.open_ms == self.ev["emit_open"] else None

    def _emit(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent:
        assert self.ev is not None
        ev = self.ev
        rec = {"kind": "intent", "arm": self.arm, "variant": self.variant.name, "decided_ms": ctx.now_ms,
               **{k: ev.get(k) for k in ("T", "t", "p", "q10", "q90", "ref", "atr", "sl_raw", "sl", "sl_dist", "decision_leverage",
                                          "decision_qty", "decision_notional", "intent_dir", "intent_sl", "fill_open")}}
        self.events.append(rec)
        self.intents.append(rec)
        self._to("ENTRY_PENDING", ctx.now_ms + 1)
        return EntryIntent(Direction(ev["intent_dir"]), Decimal(ev["intent_sl"]), None, REGIME, decided_ms=ctx.now_ms,
                           decision_mark=bar.d("mark_close"))

    def _unfilled(self, reason: str, t: int) -> None:
        self.entry[reason] += 1
        self.events.append({"kind": "abort", "arm": self.arm, "t": t, "T": None if self.ev is None else self.ev["T"],
                            "reason": reason})
        self.ev = None
        self._to("IDLE", t)                                            # 체결 실패 종결도 IDLE 유지(C31)

    # ── 엔진 결과 ────────────────────────────────────────────────────────
    def _engine_events(self, bar: Bar1m, events: list[object]) -> None:
        t = bar.open_ms + MINUTE_MS
        for e in events:
            if isinstance(e, EntryFilled):
                if self.state != "ENTRY_PENDING":
                    raise RunInvariantError(f"대기 의도 없이 체결 {bar.open_ms}")
                if self.ev is None or bar.open_ms != self.ev["fill_open"]:
                    raise RunInvariantError(f"체결 봉 {bar.open_ms} ≠ 기대 {None if self.ev is None else self.ev['fill_open']}")
                self.entry["filled"] += 1
                self.filled_intents.append(self.intents[-1])
                comm = e.entry_commission if e.entry_commission is not None else sum((f.commission for f in e.fills), Decimal(0))
                self.events.append({"kind": "filled", "arm": self.arm, "t": t, "fill_open": bar.open_ms,
                                    "leverage": e.leverage, "qty": str(e.post_fill.qty), "fill": str(e.post_fill.entry_price),
                                    "entry_ref": str(bar.d("mark_open")), "entry_commission": str(comm)})
                self._to("IN_POSITION", t)
            elif isinstance(e, EntrySkipped):
                if self.state != "ENTRY_PENDING":
                    raise RunInvariantError(f"대기 의도 없이 건너뜀 {bar.open_ms}")
                if e.reason is SkipReason.SL_CROSSED_BEFORE_FILL:
                    reason = "sl_crossed_before_fill"
                elif e.reason is SkipReason.SIZING_REJECTED:
                    reason = ("normalization" if e.decision is not None and e.decision.reason in NORMALIZATION
                              else "sizing_rejected_fill")
                else:
                    raise RunInvariantError(f"PAPER에서 나올 수 없는 건너뜀 {e.reason}")
                self._unfilled(reason, t)
            elif isinstance(e, PositionClosed):
                if self.state != "IN_POSITION":
                    raise RunInvariantError(f"포지션 없이 청산 {bar.open_ms}")
                if e.reason not in (ExitReason.SL, ExitReason.LIQUIDATION, ExitReason.TIME_EXIT):
                    raise RunInvariantError(f"등록되지 않은 청산 사유 {e.reason}")
                self.entry[f"exit.{e.reason}"] += 1
                self.events.append({"kind": "exit", "arm": self.arm, "t": t, "reason": str(e.reason), "ts_ms": e.ts_ms,
                                    "exit_price": None if e.exit_price is None else str(e.exit_price),
                                    "exit_fills": [[str(f.price), str(f.qty), str(f.commission), None if f.ref_mark is None
                                                    else str(f.ref_mark)] for f in e.fills],
                                    "realized_pnl": str(e.realized_pnl_usdt), "exit_commission": str(e.exit_commission_usdt),
                                    "funding_paid": str(e.funding_paid_usdt), "wallet_after": str(e.wallet_after)})
                self.ev = None
                self.exit_ts = e.ts_ms
                self._to("WAIT", t)

    def _to(self, state: str, t: int) -> None:
        self.state = state
        self.events.append({"kind": "state", "arm": self.arm, "t": t, "state": state})

    # ── 실행 끝 검사(하네스) ─────────────────────────────────────────────
    def finish(self) -> None:
        self.sched.assert_no_due()
        if self.state in BUSY_STATES:
            raise RunInvariantError(f"창 끝에 미완 상태 {self.state}")


__all__ = ["BASE", "Eligible", "FillReference", "RunInvariantError", "Trial04", "Variant"]
