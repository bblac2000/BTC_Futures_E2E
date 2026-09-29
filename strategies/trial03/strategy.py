"""트라이얼 #3 전략 — 암 하나(L 또는 S)의 상태 기계(단계 2 (d) · 계획 r2/r3 · 사전등록 §1 22~39행 · §4 P2/P3 · §7-3).

상태: IDLE → (적격 이벤트 t0) FLUSH_QUALIFIED[즉시 · 쿨다운 시작 → busy 검사] → COOLING → (결정 봉 t_e) ENTRY_PENDING
(P2는 DELAYED 뒤) → IN_POSITION → COOLDOWN(항상 t0 + 12시간까지) → IDLE. 결정 봉은 **하나**(첫 냉각 봉)이고 중단은 전부 종결이다.

시계(r3 22행 · 계획 D2): 봉 k는 open_ms가 속한 날에 속한다 · 마감 T_k = open_ms + 60,000 = "1m 봉 마감 t" · 창 봉 = open_ms ∈ [IS_START, IS_END] ·
워밍업 봉(open_ms < IS_START)은 특징 상태(r30 · 분위수 날 버킷 · rv · ATR 버킷)만 채운다.

이벤트 깔때기(창 봉마다 첫 실패 사유 · 서로 배타 · §7-3): quantile_invalid → no_tail{r30_undefined} → not_admissible{window_end|incomplete|funding}
→ in_cooldown → oi_missing{absent|unusable} → oi_not_decreasing → qualified. 꼬리 분(no_tail 뒤)은 이벤트 기록에 한 줄씩, 앞 둘은 개수만.
진입 깔때기(적격 이벤트마다 종결 하나): position_busy(실행 실패) · not_cooled · sl_dist_out_of_range{floor|ceiling} · sizing_rejected_decision ·
sl_crossed_before_fill · sizing_rejected_fill · normalization · filled(→ exit{sl|liquidation|time_exit}).

(c) 배선: `on_minute_closed`의 첫 문장이 청산 일정 `observe` · `before_minute`에서 `guard` · 하네스가 재생 뒤 `assert_no_due`.
결정 시점 B2 = size_entry(**기준가 m** · 반올림 SL · 원 방향 · E_ref)(§1 29행) · 체결 시점 재사이징(6 bps 예상 체결가)은 엔진.
P2(+k): 결정 값은 t_e에 고정 · 봉 o_e + k·60,000 마감에 의도를 낸다(체결 = 봉 o_e + (k+1)·60,000 시가). P3: 결정 게이트는 원 방향 · 의도는
반대 방향 · SL′ = normalize_price(m ± 1.5·ATR)(거울상 원값을 반올림).
"""
from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable
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
from strategies.trial03 import anchor as A
from strategies.trial03.config import LIMITS, REGIME, TF_V1, TfParams
from strategies.trial03.exit_schedule import PositionBusyError, TimeExitSchedule, busy_check
from strategies.trial03.features import AtrBuckets, OiIndex, QuantileBook, r30, rv5

DAY = A.DAY_MS
ARM_DIRECTION = {"L": Direction.LONG, "S": Direction.SHORT}
NORMALIZATION = {RejectReason.BELOW_MIN_QTY, RejectReason.MIN_NOTIONAL}


class RunInvariantError(RuntimeError):
    """PAPER 재생에서 나올 수 없는 경로(송신 실패 · 레버리지 미확인 · POST_FILL_GATE · 결정 봉 ATR 없음 등) — 실행 실패."""


@dataclass(frozen=True)
class Variant:
    delay: int = 0                  # P2: 1 또는 5
    invert: bool = False            # P3

    def __post_init__(self):
        if self.delay not in (0, 1, 5) or (self.delay and self.invert):
            raise ValueError(f"등록되지 않은 변형 {self}")

    @property
    def name(self) -> str:
        return "P3_invert" if self.invert else (f"P2_delay{self.delay}" if self.delay else "base")


BASE = Variant()

Admissible = Callable[[int], str | None]           # t0 → None(판정 가능) | "window_end" | "incomplete" | "funding"


class Trial03:
    def __init__(self, arm: str, *, rules: RuntimeRules, oi: OiIndex, admissible: Admissible,
                 variant: Variant = BASE, p: TfParams = TF_V1,
                 window: tuple[int, int] = (A.WINDOW_START_MS, A.IS_END_MS)):
        if arm not in ARM_DIRECTION:
            raise ValueError(f"arm {arm}")
        self.arm, self.dir, self.rules, self.oi, self.admissible = arm, ARM_DIRECTION[arm], rules, oi, admissible
        self.variant, self.p, self.window = variant, p, window
        self.sched = TimeExitSchedule(p.hold_min)
        self.book = QuantileBook(p)
        self.atr = AtrBuckets(p)
        self.closes: dict[int, str] = {}                              # open_ms → mark_close(최근 ~40분)
        self.rv_hist: deque[tuple[int, float | None]] = deque()      # (T, rv5) 최근 31분
        self.q_day: int | None = None
        self.q: tuple[float, float] | None = None
        self.state = "IDLE"
        self.cooldown_end = -1
        self.ev: dict[str, Any] | None = None                        # 진행 중 적격 이벤트
        self.events: list[dict[str, Any]] = []                        # 전략 소유 이벤트 기록(JSONL)
        self.funnel: Counter[str] = Counter()                         # 이벤트 깔때기(창 봉 전부)
        self.sub: Counter[str] = Counter()                            # 보고 전용 부사유
        self.entry: Counter[str] = Counter()                          # 진입 깔때기 종결 + 청산 사유
        self.intents: list[dict[str, Any]] = []                       # 낸 의도(체결과 순서로 짝지음)
        self.filled_intents: list[dict[str, Any]] = []                # 체결된 의도(트레이드와 순서로 짝)
        self.q_valid: dict[int, bool] = {}                            # 창 날 → 분위수 유효(V 재계산 대조용)
        self.window_bars = 0
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
        t_close = bar.open_ms + MINUTE_MS
        r = self._features(bar, t_close)
        in_window = self.window[0] <= bar.open_ms <= self.window[1]
        if not in_window:
            return None
        self.window_bars += 1
        if self.state == "COOLDOWN" and t_close >= self.cooldown_end:
            self._to("IDLE", t_close)
        intent = self._advance(bar, t_close, ctx)
        self._classify(bar, t_close, r, ctx)
        return intent

    # ── 특징(워밍업 포함 · 인과적) ───────────────────────────────────────
    def _features(self, bar: Bar1m, t_close: int) -> float | None:
        day = bar.open_ms // DAY
        if day != self.q_day:
            self.q_day, self.q = day, self.book.quantiles(day)
            self.book.prune(day - self.p.w_ref_days - 1)
            if self.window[0] <= bar.open_ms <= self.window[1]:
                self.q_valid[day] = self.q is not None
        self.closes[bar.open_ms] = bar.mark_close
        for k in [k for k in self.closes if k < bar.open_ms - 40 * MINUTE_MS]:
            del self.closes[k]
        rv = r30(bar.mark_close, self.closes.get(bar.open_ms - self.p.r30_ms))
        self.book.add(day, rv)
        self.atr.add(bar)
        six = [self.closes.get(bar.open_ms - i * MINUTE_MS) for i in range(self.p.rv_n, -1, -1)]
        self.rv_hist.append((t_close, rv5(six)))
        while self.rv_hist and self.rv_hist[0][0] < t_close - self.p.rv_peak_lookback_ms:
            self.rv_hist.popleft()
        return rv

    # ── 이벤트 깔때기 ────────────────────────────────────────────────────
    def _classify(self, bar: Bar1m, t: int, r: float | None, ctx: ReplayContext) -> None:
        if self.q is None:
            self.funnel["quantile_invalid"] += 1
            return
        if r is None:
            self.funnel["no_tail"] += 1
            self.sub["no_tail.r30_undefined"] += 1
            return
        tail = r <= self.q[0] if self.dir is Direction.LONG else r >= self.q[1]
        if not tail:
            self.funnel["no_tail"] += 1
            return
        rec: dict[str, Any] = {"t": t, "r30": r, "q": self.q[0] if self.dir is Direction.LONG else self.q[1]}
        adm = self.admissible(t)
        if adm is not None:
            self._tail(rec, "not_admissible", adm)
            return
        if t < self.cooldown_end:
            self._tail(rec, "in_cooldown")
            return
        st, sub = self.oi.status(t)
        if st == "missing":
            self._tail(rec, "oi_missing", sub)
            return
        if st == "not_decreasing":
            self._tail(rec, "oi_not_decreasing")
            return
        self._tail(rec, "qualified")
        self.cooldown_end = t + self.p.cooldown_ms                     # §1 34행: 바쁨이어도 쿨다운은 시작
        busy_check(ctx, self.events, t, arm=self.arm)                   # 포지션·대기 진입 → 기록 후 PositionBusyError
        peak = [v for (u, v) in self.rv_hist if u >= t - self.p.rv_peak_lookback_ms and v is not None]
        self.ev = {"t0": t, "rv_peak": max(peak) if peak else None}
        self._to("COOLING", t)

    def _tail(self, rec: dict[str, Any], reason: str, sub: str | None = None) -> None:
        self.funnel[reason] += 1
        if sub:
            self.sub[f"{reason}.{sub}"] += 1
        self.events.append({"kind": "tail", "arm": self.arm, **rec, "reason": reason, "sub": sub})

    # ── 냉각 · 결정 · 지연 ───────────────────────────────────────────────
    def _advance(self, bar: Bar1m, t: int, ctx: ReplayContext) -> EntryIntent | None:
        if self.state == "COOLING":
            assert self.ev is not None
            t0 = self.ev["t0"]
            cur = self.rv_hist[-1][1]
            if cur is not None:
                self.ev["rv_peak"] = cur if self.ev["rv_peak"] is None else max(self.ev["rv_peak"], cur)
            if t - t0 > self.p.t_max_ms:
                return self._abort("not_cooled", t)
            peak = self.ev["rv_peak"]
            if t - t0 >= self.p.t_min_ms and cur is not None and peak is not None and cur <= self.p.c_cool * peak:
                return self._decide(bar, t, ctx)
            return None
        if self.state == "DELAYED":
            assert self.ev is not None
            if bar.open_ms > self.ev["emit_open"]:
                raise RunInvariantError(f"P2 지연 의도의 봉 {self.ev['emit_open']}이 없다")
            if bar.open_ms == self.ev["emit_open"]:
                busy_check(ctx, self.events, t, arm=self.arm)
                return self._emit(ctx)
        return None

    def _decide(self, bar: Bar1m, t: int, ctx: ReplayContext) -> EntryIntent | None:
        assert self.ev is not None
        atr = self.atr.atr(t)
        if atr is None:
            raise RunInvariantError(f"결정 봉 {t}에 ATR_15m이 없다(판정 가능 구간 위반)")
        m = bar.d("mark_close")
        k = self.p.k_sl
        long_ = self.dir is Direction.LONG
        sl_raw = m - k * atr if long_ else m + k * atr
        sl_dist = k * atr / m
        self.ev |= {"t_e": t, "o_e": bar.open_ms, "m": str(m), "atr": str(atr), "sl_raw": str(sl_raw), "sl_dist": str(sl_dist)}
        if sl_dist < self.p.sl_floor:
            return self._abort("sl_dist_out_of_range", t, "floor")
        if sl_dist > self.p.sl_ceiling:
            return self._abort("sl_dist_out_of_range", t, "ceiling")
        sl = normalize_price(sl_raw, self.rules.symbol_rules)
        d = size_entry(m, sl, self.dir, self.p.e_ref, REGIME, self.rules, LIMITS)
        self.ev |= {"sl": str(sl), "decision_ok": d.ok, "decision_reason": None if d.reason is None else str(d.reason),
                    "decision_leverage": d.leverage, "decision_qty": str(d.qty), "decision_notional": str(d.notional)}
        if not d.ok:
            return self._abort("sizing_rejected_decision", t)
        if self.variant.invert:
            self.ev["intent_dir"] = (Direction.SHORT if long_ else Direction.LONG).value
            self.ev["intent_sl"] = str(normalize_price(m + k * atr if long_ else m - k * atr, self.rules.symbol_rules))
        else:
            self.ev["intent_dir"], self.ev["intent_sl"] = self.dir.value, str(sl)
        self.ev["fill_open"] = bar.open_ms + (self.variant.delay + 1) * MINUTE_MS     # 체결 봉 open(계획 D4′)
        if self.variant.delay:
            self.ev["emit_open"] = bar.open_ms + self.variant.delay * MINUTE_MS
            self._to("DELAYED", t)
            return None
        return self._emit(ctx)

    def _emit(self, ctx: ReplayContext) -> EntryIntent:
        assert self.ev is not None
        ev = self.ev
        rec = {"kind": "intent", "arm": self.arm, "variant": self.variant.name, "decided_ms": ctx.now_ms,
               **{k: ev.get(k) for k in ("t0", "t_e", "o_e", "m", "atr", "sl_raw", "sl", "sl_dist", "decision_leverage",
                                          "decision_qty", "decision_notional", "intent_dir", "intent_sl")}}
        self.events.append(rec)
        self.intents.append(rec)
        self._to("ENTRY_PENDING", ctx.now_ms + 1)                     # 의도를 낸 봉의 마감(P2는 지연된 봉)
        return EntryIntent(Direction(ev["intent_dir"]), Decimal(ev["intent_sl"]), None, REGIME, decided_ms=ctx.now_ms,
                           decision_mark=Decimal(ev["m"]))

    def _abort(self, reason: str, t: int, sub: str | None = None) -> None:
        self.entry[reason] += 1
        if sub:
            self.sub[f"{reason}.{sub}"] += 1
        self.events.append({"kind": "abort", "arm": self.arm, "t": t, "t0": None if self.ev is None else self.ev["t0"],
                            "reason": reason, "sub": sub})
        self.ev = None
        self._to("COOLDOWN", t)
        return None

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
                self._abort(reason, t)
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
                self._to("COOLDOWN", t)

    def _to(self, state: str, t: int) -> None:
        self.state = state
        self.events.append({"kind": "state", "arm": self.arm, "t": t, "state": state})

    # ── 실행 끝 검사(하네스) ─────────────────────────────────────────────
    def finish(self) -> None:
        self.sched.assert_no_due()
        if self.state in ("COOLING", "DELAYED", "ENTRY_PENDING", "IN_POSITION"):
            raise RunInvariantError(f"창 끝에 미완 상태 {self.state}")


__all__ = ["BASE", "Admissible", "PositionBusyError", "RunInvariantError", "Trial03", "Variant"]
