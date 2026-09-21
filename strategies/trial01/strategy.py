"""트라이얼 #1 전략 플러그인(단계 2c) — 4h TSMOM 방향 필터(Arm A만) × 1m S/R 되돌림 진입. 사전등록 §1 · `sr_v1`.

`backtest.engine_replay.Strategy`를 구현한다(`on_minute_closed(bar, ctx) -> EntryIntent | None`). 체결·SL/TP·트레일링은 엔진.

## 규칙 사슬(사용자 2026-09-21 순서 · 건너뜀 사유는 전부 `decisions`에)
touch → confirmation(도지 가드) → [conflict_signal] → filter(Arm A만) → cooldown → one_position
→ (여기까지 통과 = skip_rate 분모 `candidate=True`) → 결합 레벨의 SL 앵커(no_sl_anchor) → sl_dist 범위(sl_dist_out_of_range)
→ TP → 진입 의도(엔진이 실행 mark에서 B2 사이징 게이트를 다시 돈다 — 거부는 엔진의 `EntrySkipped`로 기록).

## 구현 규약(사전등록이 정하지 않은 선택 — 단계 d Codex 질문 · 레지스트리 #21 후보)
- ⓐ **터치·확인·후보 분류는 mark 1m 봉**(§1 "진입 타이밍 = 1m(밴드·mark 틱 감시)" · "kline last는 레벨·ATR·VP 계산에만").
  레벨(스윙·VP)·ATR은 kline last로 만든 피처. 도지 가드 = mark range < 1 tick.
- ⓑ 터치 봉의 레벨 집합은 **봉 시작 시점** 기준: 기준 mark = 그 봉 `mark_open` · 스윙 = 봉 시작 시각에 유효 ·
  VP = 그 봉을 뺀 직전 1,440봉(= 결정 봉 제외 규칙과 같은 값) · 밴드 폭 = 봉 시작 시점 ATR_1m. 밴드는 터치 때 고정.
- ⓒ 터치 = 극값(롱 mark 저가 · 숏 mark 고가)이 **밴드 안**(`L − w ≤ 극값 ≤ L + w`) — 밴드를 뚫고 지나간 봉은 터치가 아니다(문언).
- ⓓ 방향마다 대기 셋업은 하나 — **새 터치가 이전 셋업을 대체**한다(가장 최근 터치가 5봉 창을 연다). 터치 봉 자신도 확인할 수 있다.
- ⓔ 확인: 롱 = mark 종가 > L + w 이고 (종가 − 저가) ≥ 0.4 × range · 숏 = 종가 < L − w 이고 (고가 − 종가) ≥ 0.4 × range.
- ⓕ `conflict_signal` = 같은 봉에서 롱·숏 확인이 **둘 다** 섬 → 필터 **전**에 둘 다 건너뜀(Arm A에서도).
- ⓖ 쿨다운 레벨 신원: 스윙 = level_id · VP(POC·VAH·VAL) = 가격. 청산 시각(봉 마감)부터 60분 동안 그 레벨의 결정(봉 마감 시각)을 막는다.
- ⓗ SL 앵커·TP 레벨·sl_dist는 **결정 봉 마감** 기준: 스윙 = 마감 시각에 유효 · 기준가 m = 결정 봉 `mark_close` ·
  sl_dist = |m − SL| / m. 엔진은 다음 봉 `mark_open`에서 다시 사이징한다(두 번째 게이트 — 거부는 엔진 사유로 따로 센다).
- ⓘ TP 레벨 후보 = 그 시각 유효한 레벨 **전부**(가까운 3개 제한 없음) 중 이익 방향으로 m보다 **엄격히** 먼 것 중 가장 가까운 것.
  **R은 체결가 기준 하나**(사용자 2026-09-21 · 레지스트리 #21): 레벨까지 거리 ≥ 1.5R 판정과 2R 폴백은 엔진이 체결 뒤
  `TpFromFill`로 정한다(R = |체결 진입가 − SL| — 트레일링과 같은 R · P1의 실현 sl_dist와 같은 기준).
- ⓙ 트레일링 거리 = 결정 시점 ATR_15m × 1.0으로 **진입 때 고정**(엔진은 ATR을 모른다) · 무장·조임은 `paper/engine.py`.
- ⓚ P2 `--delay k`: 확인 신호를 k봉 뒤 봉 마감에서 처리(필터·쿨다운·단일 포지션·SL·TP를 **그 시각** 상태로 다시 판정 ·
  conflict 판정은 원래 확인 봉) · P3 `--invert`: 모든 판정은 원 방향으로 하고 마지막에 방향을 뒤집되 SL·TP를 m 기준으로
  **거울상**(같은 sl_dist·같은 R — 방향만 뒤집으면 SL이 잘못된 쪽이라 전부 사이징 거부된다).
"""
from __future__ import annotations

import decimal
from collections import Counter, deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol

from backtest.data import MINUTE_MS, Bar1m
from backtest.engine_replay import ReplayContext
from exchange.orders import Direction
from paper.engine import EntryIntent, TpFromFill, Trail
from paper.types import EntryFilled, EntrySkipped, PositionClosed
from sizing.config import RegimeSizing
from strategies.trial01.config import SR_V1_PARAMS, Trial01Params
from strategies.trial01.features import DECIMAL_CTX, VP, FeatureEngine, SwingLevel

LONG, SHORT = Direction.LONG, Direction.SHORT
Arm = Literal["A", "B"]
LevelKey = tuple[str, str]


@dataclass(frozen=True)
class Level:
    key: LevelKey                 # ("swing", level_id) · ("vp", 가격)
    kind: str                     # swing_high · swing_low · poc · vah · val
    price: Decimal


@dataclass(frozen=True)
class Snapshot:
    """봉 하나를 넣은 뒤의 피처 — 터치용(봉 시작 기준)과 결정용(봉 마감 기준)을 나눠 담는다."""
    atr1_open: Decimal | None                 # 이 봉 전 ATR_1m(밴드 폭)
    vp: VP | None                             # 이 봉을 뺀 직전 1,440봉
    swings_open: tuple[SwingLevel, ...]       # 봉 시작 시각에 유효
    swings_close: tuple[SwingLevel, ...]      # 봉 마감 시각에 유효(SL 앵커·TP)
    atr15: Decimal | None                     # 봉 마감 시점
    tsmom: int | None                         # 봉 마감 시점(4h 마감에만 갱신)


class FeatureFeed(Protocol):
    def step(self, bar: Bar1m) -> Snapshot: ...


class EngineFeed:
    """`features.FeatureEngine`(2b 정본 피처)을 봉마다 한 번 돌린다."""

    def __init__(self, fe: FeatureEngine):
        self.fe = fe
        self.last_row: dict[str, Decimal | None] = {}          # 2b 정본 피처 행(대조 테스트용)

    def step(self, bar: Bar1m) -> Snapshot:
        a1 = self.fe.atr1.value
        row = self.last_row = self.fe.step(bar).values
        poc, vah, val = row["vp_poc"], row["vp_vah"], row["vp_val"]
        vp = VP(poc, vah, val) if poc is not None and vah is not None and val is not None else None
        close_ms = bar.open_ms + MINUTE_MS - 1
        levels = self.fe.swings.levels
        return Snapshot(a1, vp, tuple(lv for lv in levels if lv.active(bar.open_ms)),
                        tuple(lv for lv in levels if lv.active(close_ms)), self.fe.atr15.value, self.fe.tsmom.value)


@dataclass(frozen=True)
class Setup:
    direction: Direction
    level: Level
    band: Decimal
    touch_idx: int
    touch_ms: int


@dataclass(frozen=True)
class Signal:
    setup: Setup
    confirm_ms: int
    emit_idx: int


def swing_level(lv: SwingLevel) -> Level:
    return Level(("swing", str(lv.level_id)), lv.kind, lv.price)


def vp_levels(vp: VP | None) -> list[Level]:
    if vp is None:
        return []
    return [Level(("vp", str(p)), k, p) for k, p in (("poc", vp.poc), ("vah", vp.vah), ("val", vp.val))]


class Trial01:
    def __init__(self, feed: FeatureFeed, tick: Decimal, *, arm: Arm, params: Trial01Params = SR_V1_PARAMS,
                 delay: int = 0, invert: bool = False):
        if arm not in ("A", "B"):
            raise ValueError(f"arm은 A 또는 B: {arm!r}")
        if delay < 0:
            raise ValueError("delay ≥ 0")
        self.feed, self.tick, self.arm, self.p = feed, tick, arm, params
        self.delay, self.invert = delay, invert
        self.regime = RegimeSizing(f"trial01_{arm}", params.risk_pct, params.l_min, params.l_max)
        self.idx = -1
        self.pending: dict[Direction, Setup] = {}
        self.queue: deque[Signal] = deque()
        self.cooldown_until: dict[LevelKey, int] = {}
        self.active_key: LevelKey | None = None      # 낸 의도 / 열린 포지션의 결합 레벨
        self.counts: Counter[str] = Counter()

    # ── 워밍업: 피처만(트레이드 없음 · 레지스트리 #20 ②) ──────────────────────────
    def warm(self, bar: Bar1m) -> None:
        self.feed.step(bar)

    # ── 봉 마감 ─────────────────────────────────────────────────────────────
    def on_minute_closed(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        with decimal.localcontext(DECIMAL_CTX):                   # 정본 10진 문맥(features.DECIMAL_CTX 참고)
            return self._on_minute_closed(bar, ctx)

    def _on_minute_closed(self, bar: Bar1m, ctx: ReplayContext) -> EntryIntent | None:
        self.idx += 1
        self._track_engine(ctx)
        snap = self.feed.step(bar)
        self._touch(bar, snap)
        confirmed = self._confirm(bar)
        close_ms = bar.open_ms + MINUTE_MS - 1
        if len(confirmed) == 2:
            for s in confirmed:
                ctx.skip("conflict_signal", candidate=False, **self._base(s, close_ms))
            self.counts["conflict_signal"] += 1
        elif confirmed:
            self.queue.append(Signal(confirmed[0], close_ms, self.idx + self.delay))
        intent: EntryIntent | None = None
        while self.queue and self.queue[0].emit_idx <= self.idx:
            sig = self.queue.popleft()
            got = self._gate(sig, bar, snap, ctx, submitted=intent is not None)
            intent = intent or got
        return intent

    def _track_engine(self, ctx: ReplayContext) -> None:
        for ev in ctx.bar_events:
            if isinstance(ev, EntrySkipped):
                self.active_key = None
            elif isinstance(ev, EntryFilled):
                self.counts["filled"] += 1
            elif isinstance(ev, PositionClosed) and self.active_key is not None:
                self.cooldown_until[self.active_key] = ev.ts_ms + self.p.cooldown_ms
                self.active_key = None

    # ── 터치 ────────────────────────────────────────────────────────────────
    def _touch(self, bar: Bar1m, snap: Snapshot) -> None:
        if snap.atr1_open is None or snap.vp is None:
            return
        ref = bar.d("mark_open")
        levels = [swing_level(lv) for lv in snap.swings_open] + vp_levels(snap.vp)
        w = self.p.band_m * snap.atr1_open
        for d in (LONG, SHORT):
            long_ = d is LONG
            cands = sorted((lv for lv in levels if (lv.price <= ref if long_ else lv.price >= ref)),
                           key=lambda lv: (abs(ref - lv.price), lv.price, lv.key))[:self.p.n_nearest]
            ext = bar.d("mark_low") if long_ else bar.d("mark_high")
            touched = [lv for lv in cands if lv.price - w <= ext <= lv.price + w]
            if touched:
                binding = min(touched, key=lambda lv: (abs(ext - lv.price), lv.price, lv.key))
                self.pending[d] = Setup(d, binding, w, self.idx, bar.open_ms)
                self.counts[f"touch_{d.value}"] += 1

    # ── 거부 확인(도지 가드) ───────────────────────────────────────────────────
    def _confirm(self, bar: Bar1m) -> list[Setup]:
        hi, lo, c = bar.d("mark_high"), bar.d("mark_low"), bar.d("mark_close")
        rng = hi - lo
        doji = rng < self.tick
        need = (1 - self.p.confirm_frac) * rng
        out: list[Setup] = []
        for d in (LONG, SHORT):
            s = self.pending.get(d)
            if s is None:
                continue
            L, w = s.level.price, s.band
            ok = False
            if doji:
                self.counts["doji"] += 1
            elif d is LONG:
                ok = c > L + w and c - lo >= need
            else:
                ok = c < L - w and hi - c >= need
            if ok:
                out.append(s)
                del self.pending[d]
                self.counts[f"confirm_{d.value}"] += 1
            elif self.idx - s.touch_idx >= self.p.confirm_bars - 1:
                del self.pending[d]
                self.counts["expired"] += 1
        return out

    # ── 필터 → 쿨다운 → 단일 포지션 → SL 앵커 → sl_dist → TP ─────────────────────
    def _base(self, s: Setup, now_ms: int) -> dict[str, Any]:
        return {"direction": s.direction.value, "level_key": list(s.level.key), "level_kind": s.level.kind,
                "level_price": str(s.level.price), "band": str(s.band), "touch_ms": s.touch_ms, "decision_ms": now_ms}

    def _gate(self, sig: Signal, bar: Bar1m, snap: Snapshot, ctx: ReplayContext, *,
              submitted: bool) -> EntryIntent | None:
        s = sig.setup
        d, long_ = s.direction, s.direction is LONG
        t = bar.open_ms + MINUTE_MS - 1
        base = self._base(s, t) | {"confirm_ms": sig.confirm_ms}
        if self.arm == "A":
            want = 1 if long_ else -1
            if snap.tsmom != want:
                ctx.skip("filter", candidate=False, tsmom=snap.tsmom, **base)
                return None
        until = self.cooldown_until.get(s.level.key)
        if until is not None and t < until:
            ctx.skip("cooldown", candidate=False, until_ms=until, **base)
            return None
        if ctx.has_position or submitted:
            ctx.skip("one_position", candidate=False, **base)
            return None
        self.counts["candidate"] += 1
        anchor = self._sl_anchor(d, s.level.price, snap.swings_close)
        if anchor is None or snap.atr15 is None:
            ctx.skip("no_sl_anchor", candidate=True, atr15=None if snap.atr15 is None else str(snap.atr15), **base)
            return None
        m = bar.d("mark_close")
        off = self.p.sl_atr_mult * snap.atr15
        sl = anchor.price - off if long_ else anchor.price + off
        sl_dist = (m - sl) / m if long_ else (sl - m) / m
        if not self.p.sl_min <= sl_dist <= self.p.sl_max:
            ctx.skip("sl_dist_out_of_range", candidate=True, sl_dist=str(sl_dist), sl=str(sl),
                     sl_anchor=list(swing_level(anchor).key), **base)
            return None
        levels = [swing_level(lv) for lv in snap.swings_close] + vp_levels(snap.vp)
        ahead = [lv for lv in levels if (lv.price > m if long_ else lv.price < m)]
        lv = min(ahead, key=lambda x: (abs(x.price - m), x.price, x.key)) if ahead else None
        tp_level = None if lv is None else lv.price
        direction = d
        if self.invert:
            direction, sl = (SHORT if long_ else LONG), 2 * m - sl
            tp_level = None if tp_level is None else 2 * m - tp_level
        #  TP는 엔진이 체결 뒤 정한다 — R = |체결 진입가 − SL|(트레일링과 같은 R · 레지스트리 #21)
        tp_rule = TpFromFill(tp_level, self.p.tp_min_r, self.p.tp_fallback_r)
        trail = Trail(self.p.trail_arm_r, self.p.trail_atr_mult * snap.atr15) if self.p.trailing else None
        ctx.decisions.append({"ts_ms": t, "outcome": "intent", "candidate": True, **base,
                              "entry_direction": direction.value, "decision_mark": str(m), "sl": str(sl),
                              "sl_anchor": list(swing_level(anchor).key), "sl_dist": str(sl_dist),
                              "tp_level": None if tp_level is None else str(tp_level),
                              "tp_level_kind": None if lv is None else lv.kind, "atr15": str(snap.atr15),
                              "tsmom": snap.tsmom, "trail_dist": None if trail is None else str(trail.dist)})
        self.counts["intent"] += 1
        self.active_key = s.level.key
        return EntryIntent(direction, sl, None, self.regime, decided_ms=t, decision_mark=m, trail=trail,
                           tp_rule=tp_rule)

    @staticmethod
    def _sl_anchor(d: Direction, level: Decimal, swings: tuple[SwingLevel, ...]) -> SwingLevel | None:
        """롱 = 결합 레벨 **이하**에서 가장 가까운 스윙 저점 · 숏 = 이상에서 가장 가까운 스윙 고점."""
        if d is LONG:
            c = [lv for lv in swings if lv.kind == "swing_low" and lv.price <= level]
            return max(c, key=lambda lv: (lv.price, -lv.level_id)) if c else None
        c = [lv for lv in swings if lv.kind == "swing_high" and lv.price >= level]
        return min(c, key=lambda lv: (lv.price, lv.level_id)) if c else None
