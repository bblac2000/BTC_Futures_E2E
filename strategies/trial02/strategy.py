"""트라이얼 #2 전략 — 일간 변동성 돌파(사전등록 §1 · 설계 r1 + C1~C20 · 구현 규약 초안 `docs/trials/trial_02_conventions_draft.md`).

재생 루프(`backtest.engine_replay.replay`)의 `on_minute_closed` + `exit_at_bar_open`만 구현한다. 날 적격성(V_A/V_B)은 **주입**된다.
- 날 경계(그날 첫 봉): 전날이 완전한 mark 날(정렬 분 1,440개 · mark 유한)이면 R_전날 = 그날 mark 고가 최대 − 저가 최소를 기록(C1 —
  적격성과 무관). O_d = 그날 00:00 봉 mark 시가(00:00 봉이 없으면 그날은 거래일일 수 없다).
- 거래일 = 주입된 집합 ∩ R_{d−1} ≥ tick(아니면 `no_range`) ∩ (Arm B) R_{d−1} < median(R_{d−21..d−2})(아니면 `not_contraction`).
- 띠 U/D = O_d ± k·R_{d−1}(P4: ± q·tick) — 00:00 고정. 교차: 롱 mark_high ≥ U · 숏 mark_low ≤ D · 23:59 봉은 보지 않는다(C4).
- 방향별 첫 교차만 · 소비 · 두 방향이 같은 봉에서 **함께 처음** 교차 → 둘 다 `conflict_cross`(규약 7).
- 첫 실패 순서(규약 8): conflict_cross → position_busy → late_cross(P2: dropped) → sl_wrong_side → sl_dist_out_of_range.
- P2(delay k): 원 교차에서 소비·대기열 → i+k 마감에서 판정(원래 날의 O_d·R) · 23:58 마감에 남은 후보는 dropped.
- P3(invert): 판정은 원 방향 · 의도 방향만 반대 · SL = SlFromFill(O_d, mirror) · TP 2R · 트레일 1R.
- P4(draw d): 거래일마다 q = integers(1, ⌊R/tick⌋+1) 1회 · SeedSequence([20260924, 4, d, day_index]).
플라시보 변형은 Arm A만(§4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Context, Decimal, localcontext
from typing import Any

import numpy as np

from backtest.data import Bar1m
from backtest.engine_replay import ReplayContext
from exchange.orders import Direction
from paper.engine import EntryIntent, SlFromFill, TpFromFill, Trail
from sizing.config import RegimeSizing
from strategies.trial02 import anchor as A
from strategies.trial02.config import BO_V1, BoParams

MIN = 60_000
DAY = A.DAY_MS
CTX = Context(prec=34)                                 # 전략 산술 문맥(ROUND_HALF_EVEN 기본) — 띠·sl_dist·중앙값
LONG, SHORT = Direction.LONG, Direction.SHORT
MARK = ("mark_open", "mark_high", "mark_low", "mark_close")


@dataclass(frozen=True)
class Variant:
    arm: str                                           # "A" | "B"
    delay: int = 0                                     # P2
    invert: bool = False                               # P3
    p4_draw: int | None = None                         # P4

    def __post_init__(self):
        if self.arm not in ("A", "B"):
            raise ValueError(f"arm {self.arm}")
        if self.arm == "B" and (self.delay or self.invert or self.p4_draw is not None):
            raise ValueError("플라시보 변형은 Arm A만(§4 원판 = Arm A)")
        if self.delay < 0 or (self.p4_draw is not None and not 0 <= self.p4_draw < A.P4_DRAWS):
            raise ValueError(f"잘못된 변형 {self}")


@dataclass
class _DayAcc:
    """한 UTC 날의 mark 극값 누적기(날마다 새로 · 채널이 아니다)."""
    day: int
    hi: Decimal | None = None
    lo: Decimal | None = None
    minutes: set[int] = field(default_factory=set)
    bad: bool = False

    def add(self, b: Bar1m) -> None:
        if b.open_ms % MIN:
            self.bad = True
            return
        try:
            vals = [Decimal(getattr(b, k)) for k in MARK]
        except ArithmeticError:
            self.bad = True
            return
        if not all(v.is_finite() for v in vals):
            self.bad = True
            return
        h, lo = vals[1], vals[2]
        mm = (b.open_ms % DAY) // MIN
        if mm in self.minutes:
            raise ValueError(f"중복 분 {b.open_ms} — 준비 단계에서 없어져야 한다(days.py와 같은 규칙)")
        self.minutes.add(mm)
        if self.hi is None or h > self.hi:
            self.hi = h
        if self.lo is None or lo < self.lo:
            self.lo = lo

    def range(self) -> Decimal | None:
        if self.bad or len(self.minutes) != 1440 or self.hi is None or self.lo is None:
            return None
        return self.hi - self.lo


@dataclass
class _Cand:
    direction: Direction
    cross_minute: int
    due_minute: int


class Trial02:
    def __init__(self, *, tick: Decimal, trade_days: set[int], variant: Variant, params: BoParams = BO_V1):
        self.tick, self.trade_days, self.v, self.p = tick, frozenset(trade_days), variant, params
        self.regime = RegimeSizing(f"trial02_{variant.arm}", params.risk_pct, params.l_min, params.l_max)
        self.ranges: dict[int, Decimal] = {}
        self.log: list[dict[str, Any]] = []
        self._acc: _DayAcc | None = None
        self._day: int | None = None
        self._active = False
        self._o = self._r = self._u = self._d = Decimal(0)
        self._consumed: dict[Direction, bool] = {LONG: False, SHORT: False}
        self._queue: list[_Cand] = []

    # ── 도우미(테스트가 직접 부른다) ─────────────────────────────────────
    @staticmethod
    def median(vals: list[Decimal]) -> Decimal:
        with localcontext(CTX):
            s = sorted(vals)
            n = len(s)
            return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    def contraction(self, r_prev: Decimal, window: list[Decimal]) -> bool:
        return r_prev < self.median(window)

    # ── 재생 루프 훅 ────────────────────────────────────────────────────
    def before_minute(self, bar: Bar1m, engine: Any) -> None:
        """재생 루프가 그 분의 **펀딩·엔진 처리 전에** 부른다 — 날 경계 가드(Codex 2d·2e r2·r3: 콜백·시가 훅은 00:00 펀딩과
        00:00 봉 on_bar 뒤라 늦다). 23:59 청산이 없던 날의 포지션이 다음 날로 넘어오면 멈춘다."""
        if bar.open_ms // DAY != self._day and self._day is not None:
            assert engine.position is None and engine.pending is None, \
                f"날 {bar.open_ms // DAY} 첫 분 처리 전에 포지션/대기 진입이 남아 있다(23:59 청산이 없던 날)"

    def exit_at_bar_open(self, bar: Bar1m) -> bool:
        return (bar.open_ms % DAY) // MIN == self.p.exit_minute

    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        di, mm = bar.open_ms // DAY, (bar.open_ms % DAY) // MIN
        if di != self._day:
            self._new_day(di, bar)
        assert self._acc is not None
        self._acc.add(bar)
        if mm == self.p.exit_minute:
            assert ctx.engine.position is None, "23:59 time_exit 뒤 포지션이 남았다"
            assert not self._queue, "23:59에 P2 후보가 남았다"
            return None
        if not self._active:
            return None
        intent: EntryIntent | None = None
        if mm <= self.p.last_cross_minute + 1:           # 23:58까지 교차를 본다(23:58은 late_cross)
            intent = self._crosses(bar, mm, ctx)
        if self.v.delay:
            got = self._due(bar, mm, ctx)
            intent = intent or got
            if mm == self.p.last_cross_minute + 1:       # 23:58 마감: 남은 후보는 체결이 23:59 이후 → dropped
                for c in self._queue:
                    self._record(c.direction, c.cross_minute, "skipped", "dropped", decided_minute=None)
                self._queue.clear()
        return intent

    # ── 내부 ────────────────────────────────────────────────────────────
    def _new_day(self, di: int, bar: Bar1m) -> None:
        if self._acc is not None:
            r = self._acc.range()
            if r is not None:
                self.ranges[self._acc.day] = r
        assert not self._queue
        self._day, self._acc = di, _DayAcc(di)
        self._consumed = {LONG: False, SHORT: False}
        self._active = False
        rec: dict[str, Any] = {"event": "day", "day": di}
        if di not in self.trade_days:
            self.log.append(rec | {"status": "not_trade_day"})
            return
        assert (bar.open_ms % DAY) == 0, f"거래일 {di}의 첫 봉이 00:00이 아니다"
        r_prev = self.ranges.get(di - 1)
        assert r_prev is not None, f"거래일 {di}에 R_(d−1)이 없다(주입된 적격성과 모순)"
        o = Decimal(bar.mark_open)
        rec |= {"O_d": str(o), "R_prev": str(r_prev)}
        if r_prev < self.tick:
            self.log.append(rec | {"status": "no_range"})
            return
        if self.v.arm == "B":
            window = [self.ranges.get(di - j) for j in range(2, 2 + self.p.b_median_days)]
            assert all(w is not None for w in window), f"B 거래일 {di}의 중앙값 창이 불완전"
            med = self.median([w for w in window if w is not None])
            rec["median"] = str(med)
            if not r_prev < med:
                self.log.append(rec | {"status": "not_contraction"})
                return
        with localcontext(CTX):
            if self.v.p4_draw is not None:
                rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([A.MASTER_SEED, A.P4_SEED_TAG, self.v.p4_draw, di])))
                q = int(rng.integers(1, int(r_prev / self.tick) + 1))
                off = Decimal(q) * self.tick
                rec["k"] = str(off / r_prev)
            else:
                off = self.p.k * r_prev
                rec["k"] = str(self.p.k)
            self._o, self._r, self._u, self._d = o, r_prev, o + off, o - off
        self._active = True
        self.log.append(rec | {"status": "trading", "U": str(self._u), "D": str(self._d)})

    def _crosses(self, bar: Bar1m, mm: int, ctx: ReplayContext) -> EntryIntent | None:
        new = []
        if not self._consumed[LONG] and Decimal(bar.mark_high) >= self._u:
            new.append(LONG)
        if not self._consumed[SHORT] and Decimal(bar.mark_low) <= self._d:
            new.append(SHORT)
        for d in new:
            self._consumed[d] = True
        if not new:
            return None
        if self.v.delay:
            self._queue += [_Cand(d, mm, mm + self.v.delay) for d in new]
            return None
        if len(new) == 2:
            for d in new:
                self._record(d, mm, "skipped", "conflict_cross")
            return None
        return self._gate(new[0], mm, mm, bar, ctx)

    def _due(self, bar: Bar1m, mm: int, ctx: ReplayContext) -> EntryIntent | None:
        due = [c for c in self._queue if c.due_minute == mm]
        if not due:
            return None
        self._queue = [c for c in self._queue if c.due_minute != mm]
        if len({c.direction for c in due}) == 2:
            for c in due:
                self._record(c.direction, c.cross_minute, "skipped", "conflict_cross", decided_minute=mm)
            return None
        c = due[0]
        return self._gate(c.direction, c.cross_minute, mm, bar, ctx)

    def _gate(self, d: Direction, cross_minute: int, mm: int, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        kw: dict[str, Any] = {"decided_minute": mm} if self.v.delay else {}
        m = Decimal(bar.mark_close)
        kw["m"] = str(m)
        if ctx.has_position:
            return self._record(d, cross_minute, "skipped", "position_busy", **kw)
        if mm > self.p.last_cross_minute:
            return self._record(d, cross_minute, "skipped", "dropped" if self.v.delay else "late_cross", **kw)
        with localcontext(CTX):
            sl_dist = (m - self._o) / m if d is LONG else (self._o - m) / m
        kw["sl_dist"] = str(sl_dist)
        if sl_dist <= 0:
            return self._record(d, cross_minute, "skipped", "sl_wrong_side", **kw)
        if sl_dist < self.p.sl_floor or sl_dist > self.p.sl_ceiling:
            side = "floor" if sl_dist < self.p.sl_floor else "ceiling"
            return self._record(d, cross_minute, "skipped", "sl_dist_out_of_range", side=side, **kw)
        self._record(d, cross_minute, "intent", None, **kw)
        exec_dir = (SHORT if d is LONG else LONG) if self.v.invert else d
        return EntryIntent(exec_dir, self._o, None, self.regime, decided_ms=ctx.now_ms, decision_mark=m,
                           trail=Trail(self.p.trail_arm_r, dist_r=self.p.trail_dist_r),
                           tp_rule=TpFromFill(level=None, min_r=self.p.tp_r, fallback_r=self.p.tp_r),
                           sl_rule=SlFromFill(self._o, mirror=True) if self.v.invert else None)

    def _record(self, d: Direction, cross_minute: int, outcome: str, reason: str | None, **kw: Any) -> None:
        rec = {"event": "first_cross", "day": self._day, "minute": cross_minute, "direction": d.value, "outcome": outcome}
        if reason is not None:
            rec["reason"] = reason
        self.log.append(rec | kw)
