"""트라이얼 #4 P1 무작위 타이밍((e) · 규약 D43~D53 · 사전등록 r3 §4 · 계획 r4 C1″·C9″) — h = 7,200분 고정 · 암별 스트림.

- 원판 쌍(D43): 그 암 **기본 실행**의 트레이드 → (trade_id · entry_ms · 결정 시점 sl_dist) · 모든 슬롯 h = 7,200분(원판이 일찍 끝났어도).
- 적격 분(D44): 판정 가능 술어 `Eligibility(...)(t)`를 창 분 격자에 한 번씩 — 게이트와 timing이 같은 목록 · 점유 [t, t + 7,200분).
  `atr_prev_close`(전략 쪽 ATR 전제)는 적용하지 않는다(D45 · 공시 · 개수만 보고).
- 게이트 P1(D46): `p1_core.p1_draw_generic` 그대로(쌍 → 방향 → 배치) · `SeedSequence(P1_SEEDS[arm]).spawn(1000)[d]`.
- 보고 전용 P1-timing(D47): 방향 추출만 없앤 구조 복사 · 방향 = 암의 방향 · `spawn(2000)[1000 + d]` · 판정은 읽지 않는다.
- 실행기(D49): 6 bps 예상 체결가에서 사이징 → `Engine.restore_position`(닿지 않는 SL) → 지갑 = E_ref − 진입 수수료 → 체결 분 버킷의 펀딩
  제외 → 분 t … t + 7,199: 펀딩 → `on_bar` → 종료 분 t + 7,200: 펀딩 → 시가 갭 청산 → 시가에 TIME_EXIT. 구간 안 봉 누락 = `P1Error`.
  트라이얼 #1~#3의 `placebo_exec.run_time_exit`는 쓰지 않는다(종료 의미가 다르다). 원판 재현 시험(D50)이 두 번째 체결 모델이 없음을 보인다.
- 실행 경로(`run_range`)에는 규칙·설정 인자가 없다(#69 `load_rules` · 앵커 설정) · 픽스처 경로는 tests/ 전용.
"""
from __future__ import annotations

import bisect
import inspect
import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import numpy as np

from backtest import p1_core as C
from backtest import placebo_exec as PX
from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.returns import TradeReturn, trade_return
from exchange.gate import Mode
from exchange.orders import Direction
from exchange.rules import RuntimeRules
from paper.engine import Engine
from paper.sender import PaperSender
from paper.types import ExitReason, PositionClosed
from strategies.trial04 import anchor as A
from strategies.trial04.config import LIMITS, REGIME, TC_V3
from strategies.trial04.eligibility import Eligibility
from strategies.trial04.exit_schedule import EVAL_SPAN_MIN, HOLD_MIN
from strategies.trial04.harness import load_rules, validate_inputs

ROOT = Path(__file__).resolve().parent.parent
DAY = A.DAY_MS
H_MS = HOLD_MIN * MINUTE_MS
ARMS = ("S", "L")
ARM_DIRECTION = {"S": C.SHORT, "L": C.LONG}                 # p1_core: 0 LONG · 1 SHORT
CFGS = {arm: C.P1Config(master_seed=cast(int, A.P1_SEEDS[arm]),     # 튜플 엔트로피 그대로 — SeedSequence가 받는다(p1_core 무수정)
                        draws=A.P1_DRAWS, slot_attempts=A.P1_SLOT_ATTEMPTS, fail_limit=A.P1_FAIL_MAX) for arm in ARMS}
NULL_KEYS = {"draw", "n", "mean_net_bps", "exits", "price_pnl_sum", "funding_cf_sum", "commission_sum", "liquidated_net_sum"}


class P1Error(RuntimeError):
    pass


class P1Failure(RuntimeError):
    """P1 조각 실행 중 실패 — 끝난 추출과 귀무 행을 담아 CLI가 보존한다(원인은 __cause__)."""

    def __init__(self, draws: list[C.P1Draw], null: list[dict[str, Any]], tdraws: list[C.P1Draw], tnull: list[dict[str, Any]]):
        super().__init__(f"P1 실패 — 게이트 추출 {len(draws)} · 귀무 행 {len(null)} · timing 추출 {len(tdraws)} · 행 {len(tnull)}")
        self.draws, self.null, self.timing_draws, self.timing_null = draws, null, tdraws, tnull


# ── 원판 쌍 · 적격 분 ────────────────────────────────────────────────────────
def source_trades(trades: Sequence[dict[str, Any]]) -> list[C.SourceTrade]:
    """h는 모든 슬롯 7,200분(D43): exit_ms = entry_ms + 7,200분으로 넣는다 — 원판의 실현 보유 시간은 쓰지 않는다."""
    return [C.SourceTrade(int(t["trade_id"]), int(t["entry_ms"]), int(t["entry_ms"]) + H_MS, Decimal(t["t4"]["sl_dist"]))
            for t in trades]


def eligible_minutes(elig: Eligibility, window: tuple[int, int]) -> list[int]:
    """창 분 격자에서 판정 가능 술어가 통과하는 분(오름차순) — 술어는 하나(B15 · D44)."""
    first = window[0] + (-window[0]) % MINUTE_MS
    last = window[1] - EVAL_SPAN_MIN * MINUTE_MS                 # 그 뒤는 전부 window_end
    return [t for t in range(first, last + 1, MINUTE_MS) if elig(t) is None]


def _pos(v: Any) -> bool:
    try:
        x = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return False
    return x.is_finite() and x > 0


def count_atr_prev_close_ok(mins: Sequence[int], bars: dict[int, Bar1m]) -> int:
    """보고 전용(D45): 적격 분 가운데 day(t) − 15의 23:59 봉 mark 종가가 있는 분의 수(원판이 추가로 요구하는 조건)."""
    ok: dict[int, bool] = {}
    n = 0
    for t in mins:
        d = t // DAY
        if d not in ok:
            b = bars.get((d - 15) * DAY + DAY - MINUTE_MS)
            ok[d] = b is not None and _pos(b.mark_close)
        n += ok[d]
    return n


def eligible_for_factory(mins: Sequence[int]) -> C.EligibleFor:
    def eligible_for(h: int) -> Sequence[int]:
        if h != HOLD_MIN:
            raise P1Error(f"h {h} ≠ {HOLD_MIN} — 원판 쌍 구성 오류")
        return mins
    return eligible_for


# ── 스트림 · 추출 ────────────────────────────────────────────────────────────
def rng_gate(cfg: C.P1Config, d: int) -> np.random.Generator:
    """스트림 동일성 시험용 — 실행 경로의 게이트는 `p1_core.p1_draw_generic` 안에서 `p1_core.p1_rng`를 직접 쓴다(같은 스트림)."""
    return C.p1_rng(cfg, d)


def rng_timing(cfg: C.P1Config, d: int) -> np.random.Generator:
    """보고 전용: `SeedSequence(seed).spawn(2000)[1000 + d]`(게이트 자식 0~999 바로 다음 1,000개)."""
    return C.p1_rng(replace(cfg, draws=A.P1_DRAWS + A.P1_TIMING_CHILD_OFFSET), A.P1_TIMING_CHILD_OFFSET + d)


def _sizing_ok(bars: dict[int, Bar1m], rules: RuntimeRules) -> C.SizingOk:
    def sizing_ok(t: int, direction: int, sl_dist: Decimal) -> bool:
        _, dec = PX.sizing_decision(bars[t].d("mark_open"), direction, sl_dist, rules, LIMITS, TC_V3.e_ref, REGIME,
                                    slippage_rate=TC_V3.slippage)
        return bool(dec.ok)
    return sizing_ok


def draw(d: int, cfg: C.P1Config, source: Sequence[C.SourceTrade], mins: Sequence[int], bars: dict[int, Bar1m],
         rules: RuntimeRules) -> C.P1Draw:
    """게이트 P1(D46) — `p1_core.p1_draw_generic` 그대로(난수 = `p1_core.p1_rng(cfg, d)`)."""
    return C.p1_draw_generic(d, cfg, source, eligible_for_factory(mins), _sizing_ok(bars, rules))


def draw_timing(d: int, cfg: C.P1Config, source: Sequence[C.SourceTrade], mins: Sequence[int], bars: dict[int, Bar1m],
                rules: RuntimeRules, arm: str) -> C.P1Draw:
    """보고 전용 P1-timing(D47) — `p1_core.p1_draw_generic` @ 0405c00의 **구조 복사**에서 방향 추출(`integers(0, 2)`)만 뺐다:
    슬롯 전부 먼저(쌍만) → h 내림차순(전부 7,200이라 슬롯 순서) → 슬롯마다 최대 `slot_attempts`회 균등추출."""
    eligible_for, sizing_ok = eligible_for_factory(mins), _sizing_ok(bars, rules)
    direction = ARM_DIRECTION[arm]
    src = C.sort_source(source)
    n = len(src)
    rng = rng_timing(cfg, d)
    slots = []
    for k in range(n):
        pair = int(rng.integers(0, n))
        slots.append((k, pair, direction, src[pair].h, src[pair].sl_dist))
    order = sorted(slots, key=lambda s: (-s[3], s[0]))
    occ = C.Occupancy()
    placed: list[C.PlacedSlot] = []
    for k, pair, dir_k, h, sl_dist in order:
        elig = eligible_for(h)
        ok = False
        if len(elig):
            for _ in range(cfg.slot_attempts):
                t = elig[int(rng.integers(0, len(elig)))]
                if occ.free(t, t + h * MINUTE_MS) and sizing_ok(t, dir_k, sl_dist):
                    occ.add(t, t + h * MINUTE_MS)
                    placed.append(C.PlacedSlot(k, pair, dir_k, h, sl_dist, t))
                    ok = True
                    break
        if not ok:
            return C.P1Draw(d, False, tuple(placed), failed_slot=k)
    return C.P1Draw(d, True, tuple(sorted(placed, key=lambda p: p.slot)))


# ── 로컬 실행기(D49) ─────────────────────────────────────────────────────────
class FundingIndex:
    def __init__(self, fundings: Sequence[Funding]):
        self.fs = sorted(fundings, key=lambda f: f.funding_ms)
        self.ms = [f.funding_ms for f in self.fs]

    def start_after_minute(self, t: int) -> int:
        """분 t의 버킷(t ≤ funding_ms < t + 1분)과 그 앞을 모두 건너뛴 첫 색인 — 체결 분의 정산은 내지 않는다(결정 17)."""
        return bisect.bisect_left(self.ms, t + MINUTE_MS)


@dataclass(frozen=True)
class SlotResult:
    ok: bool
    reason: str                                # "time_exit" · "liquidation" · "sizing_refused"
    ret: TradeReturn | None = None
    wallet_after: Decimal | None = None
    exit_ts: int | None = None
    funding_paid: Decimal | None = None
    qty: Decimal | None = None
    fill: Decimal | None = None
    leverage: int | None = None
    liq_price_est: Decimal | None = None       # 청산 시점의 추정 청산가(청산일 때)
    exit_fill: Decimal | None = None
    price_pnl: Decimal | None = None           # 시간 청산일 때만(체결가 기준 · 슬리피지 포함)
    funding_cf: Decimal | None = None          # = −Σ 지불
    commission: Decimal | None = None          # 진입 + 청산(시간 청산일 때)


def execute(bars: dict[int, Bar1m], fidx: FundingIndex, *, entry_ms: int, direction: int, sl_dist: Decimal,
            rules: RuntimeRules) -> SlotResult:
    first = bars.get(entry_ms)
    if first is None:
        raise P1Error(f"슬롯 시작 봉 {entry_ms}이 없다")
    fill, dec = PX.sizing_decision(first.d("mark_open"), direction, sl_dist, rules, LIMITS, TC_V3.e_ref, REGIME,
                                   slippage_rate=TC_V3.slippage)
    if not dec.ok or dec.leverage is None:
        return SlotResult(False, "sizing_refused")
    d = Direction.LONG if direction == C.LONG else Direction.SHORT
    commission = dec.qty * fill * rules.commission.taker
    eng = Engine(rules, PaperSender(rules, slippage_rate=TC_V3.slippage), mode=Mode.PAPER, wallet=TC_V3.e_ref, limits=LIMITS)
    i = fidx.start_after_minute(entry_ms)
    nf = fidx.ms[i] if i < len(fidx.ms) else entry_ms + A.H8_MS
    eng.restore_position({
        "direction": d.value, "qty": str(dec.qty), "entry_price": str(fill), "leverage": dec.leverage,
        "sl": "0" if d is Direction.LONG else str(PX.UNREACHABLE_SHORT_SL), "tp": None,
        "liq_price_est": str(dec.liq_price_est), "entry_commission": str(commission), "funding_paid": "0",
        "opened_ms": entry_ms, "liq_alerted": False, "next_funding_ms": nf}, ts_ms=entry_ms, detail="p1_t4")
    eng.wallet = TC_V3.e_ref - commission
    due = entry_ms + H_MS
    closed: PositionClosed | None = None
    exit_ref = liq_at_exit = Decimal(0)

    def settle(t: int) -> None:
        nonlocal i
        while i < len(fidx.ms) and fidx.ms[i] < t + MINUTE_MS:
            f = fidx.fs[i]
            eng.on_funding(ts_ms=f.funding_ms, rate=Decimal(f.rate), mark=Decimal(f.mark))
            i += 1

    t = entry_ms
    while t < due and closed is None:
        settle(t)
        b = bars.get(t)
        if b is None:
            raise P1Error(f"슬롯 {entry_ms}: 구간 안 봉 {t}이 없다(판정 가능 술어 위반)")
        assert eng.position is not None
        liq_now = eng.position.liq_price_est
        for ev in eng.on_bar(PX.mark_bar(b)):
            if isinstance(ev, PositionClosed):
                closed, exit_ref, liq_at_exit = ev, liq_now, liq_now
        t += MINUTE_MS
    outcome = "liquidation"
    if closed is None:
        settle(due)
        b = bars.get(due)
        if b is None:
            raise P1Error(f"슬롯 {entry_ms}: 종료 봉 {due}이 없다(판정 가능 술어 위반)")
        o = b.d("mark_open")
        assert eng.position is not None
        liq_now = eng.position.liq_price_est
        evs = eng.liquidate_if_open_beyond(o, ts_ms=due)
        if eng.position is not None:
            evs = eng.close_now(ref_mark=o, ts_ms=due, reason=ExitReason.TIME_EXIT)
            outcome, exit_ref = "time_exit", o
        else:
            exit_ref = liq_at_exit = liq_now
        for ev in evs:
            if isinstance(ev, PositionClosed):
                closed = ev
    assert closed is not None
    expected = ExitReason.TIME_EXIT if outcome == "time_exit" else ExitReason.LIQUIDATION
    if closed.reason != expected:
        raise AssertionError(f"엔진 청산 사유 {closed.reason} ≠ 기대 {expected}")
    ret = trade_return(direction=d, entry_mark=first.d("mark_open"), exit_ref=exit_ref, qty=dec.qty, entry_fill=fill,
                       wallet_before=TC_V3.e_ref, wallet_after=closed.wallet_after)
    base = {"ret": ret, "wallet_after": closed.wallet_after, "exit_ts": closed.ts_ms, "funding_paid": closed.funding_paid_usdt,
            "qty": dec.qty, "fill": fill, "leverage": dec.leverage, "funding_cf": -closed.funding_paid_usdt}
    if outcome == "liquidation":
        return SlotResult(True, outcome, liq_price_est=liq_at_exit, **base)
    sign = Decimal(1) if d is Direction.LONG else Decimal(-1)
    exit_fill = closed.exit_price
    assert exit_fill is not None
    return SlotResult(True, outcome, exit_fill=exit_fill, price_pnl=sign * dec.qty * (exit_fill - fill),
                      commission=commission + closed.exit_commission_usdt, **base)


def null_point(dr: C.P1Draw, bars: dict[int, Bar1m], fidx: FundingIndex, rules: RuntimeRules) -> dict[str, Any]:
    """성공한 추출 하나 → 트레이드당 평균 net_bps(Decimal 문자열) + 청산 사유 개수 + 보고 전용 합계(D52)."""
    if not dr.ok:
        raise P1Error(f"실패한 추출 {dr.draw}의 귀무 점")
    nets: list[Decimal] = []
    reasons = {"time_exit": 0, "liquidation": 0}
    z = Decimal(0)
    price, fcf, comm, liq_net = z, z, z, z
    for p in dr.placed:
        r = execute(bars, fidx, entry_ms=p.entry_ms, direction=p.direction, sl_dist=p.sl_dist, rules=rules)
        if not r.ok or r.ret is None or r.funding_cf is None:
            raise AssertionError(f"추출 {dr.draw} 슬롯 {p.slot}: 배치 때 수락된 사이징이 실행에서 거부됐다")
        nets.append(r.ret.net_bps)
        reasons[r.reason] += 1
        fcf += r.funding_cf
        if r.reason == "time_exit":
            assert r.price_pnl is not None and r.commission is not None
            price, comm = price + r.price_pnl, comm + r.commission
        else:
            liq_net += r.ret.net_pnl
    return {"draw": dr.draw, "n": len(nets), "mean_net_bps": str(sum(nets, z) / len(nets)), "exits": reasons,
            "price_pnl_sum": str(price), "funding_cf_sum": str(fcf), "commission_sum": str(comm), "liquidated_net_sum": str(liq_net)}


# ── 조각 실행 · 병합 ─────────────────────────────────────────────────────────
@dataclass
class P1Part:
    arm: str
    lo: int
    hi: int
    n_source: int
    computable: bool
    draws_json: str                       # 게이트 · p1_core.canonical_json
    null: list[dict[str, Any]]
    timing_draws_json: str = "[]"         # 보고 전용
    timing_null: list[dict[str, Any]] = field(default_factory=list)
    n_eligible: int = 0
    n_eligible_atr_prev_close_ok: int = 0



def _run_range(arm: str, trades: Sequence[dict[str, Any]], bars: Sequence[Bar1m], fundings: Sequence[Funding], lo: int, hi: int,
               *, rules: RuntimeRules, cfg: C.P1Config, window: tuple[int, int]) -> P1Part:
    if arm not in ARMS or not 0 <= lo <= hi < cfg.draws:
        raise P1Error(f"arm {arm} · 범위 {lo}-{hi}")
    validate_inputs(bars, fundings)
    src = source_trades(trades)
    if not src:
        return P1Part(arm, lo, hi, 0, False, "[]", [])
    by_t = {b.open_ms: b for b in bars}
    mins = eligible_minutes(Eligibility(bars, fundings, window_start=window[0], window_end=window[1]), window)
    fidx = FundingIndex(fundings)
    draws: list[C.P1Draw] = []
    null: list[dict[str, Any]] = []
    tdraws: list[C.P1Draw] = []
    tnull: list[dict[str, Any]] = []
    try:
        for d in range(lo, hi + 1):
            dr = draw(d, cfg, src, mins, by_t, rules)
            draws.append(dr)
            if dr.ok:
                null.append(null_point(dr, by_t, fidx, rules))
            td = draw_timing(d, cfg, src, mins, by_t, rules, arm)
            tdraws.append(td)
            if td.ok:
                tnull.append(null_point(td, by_t, fidx, rules))
    except BaseException as e:
        raise P1Failure(draws, null, tdraws, tnull) from e
    return P1Part(arm, lo, hi, len(src), True, C.canonical_json(draws), null, C.canonical_json(tdraws), tnull, len(mins),
                  count_atr_prev_close_ok(mins, by_t))


def run_range(arm: str, trades: Sequence[dict[str, Any]], bars: Sequence[Bar1m], fundings: Sequence[Funding],
              lo: int, hi: int) -> P1Part:
    """실행 경로 — 규칙 = `load_rules()`(#69) · 설정 = 앵커(`CFGS[arm]`) · 창 = WINDOW_START … IS_END. 덮어쓸 인자가 없다."""
    return _run_range(arm, trades, bars, fundings, lo, hi, rules=load_rules(), cfg=CFGS[arm],
                      window=(A.WINDOW_START_MS, A.IS_END_MS))


def run_range_with_fixture_rules(arm: str, trades: Sequence[dict[str, Any]], bars: Sequence[Bar1m], fundings: Sequence[Funding],
                                 lo: int, hi: int, *, rules: RuntimeRules, window: tuple[int, int],
                                 cfg: C.P1Config | None = None) -> P1Part:
    """**테스트 전용** — 호출자 파일이 tests/ 아래가 아니면 거부."""
    caller = Path(inspect.stack()[1].filename).resolve()
    if (ROOT / "tests") not in caller.parents:
        raise P1Error(f"픽스처 경로는 tests/ 전용이다(호출자 {caller})")
    if arm not in ARMS:
        raise P1Error(f"arm {arm}")
    return _run_range(arm, trades, bars, fundings, lo, hi, rules=rules, cfg=cfg or CFGS[arm], window=window)


def _check_block(name: str, draws: list[dict[str, Any]], null: list[dict[str, Any]], n: int, draws_total: int) -> int:
    ids = sorted(d["draw"] for d in draws)
    if ids != list(range(draws_total)):
        raise P1Error(f"{name}: 추출 0..{draws_total - 1}을 정확히 한 번씩 덮지 않는다(개수 {len(ids)})")
    ok_ids = sorted(d["draw"] for d in draws if d["ok"])
    if sorted(r["draw"] for r in null) != ok_ids:
        raise P1Error(f"{name}: 귀무 행의 추출이 성공한 추출과 다르다")
    for r in null:
        if set(r) != NULL_KEYS or r["n"] != n or sum(r["exits"].values()) != n or set(r["exits"]) != {"time_exit", "liquidation"}:
            raise P1Error(f"{name} 귀무 행 {r['draw']}: 모양·n·청산 사유 합이 원판 수 {n}과 맞지 않는다")
    return draws_total - len(ok_ids)


def merge(parts: Sequence[P1Part], draws_total: int = A.P1_DRAWS) -> dict[str, Any]:
    """조각 병합 + 불변식. 게이트: computable · draws · null · failed · evaluable(실패 > 10 → 거짓).
    `timing`은 **보고 전용 별도 블록**(draws · null · failed) — 판정은 읽지 않는다(D47)."""
    if not parts:
        raise P1Error("조각 없음")
    arms = {p.arm for p in parts}
    n_src = {p.n_source for p in parts}
    comp = {p.computable for p in parts}
    if len(arms) != 1 or len(n_src) != 1 or len(comp) != 1:
        raise P1Error(f"조각 불일치: arm {arms} · n_source {n_src} · computable {comp}")
    ranges = sorted((p.lo, p.hi) for p in parts)
    covered = [d for lo, hi in ranges for d in range(lo, hi + 1)]
    if covered != list(range(draws_total)):
        raise P1Error(f"조각 범위가 0..{draws_total - 1}을 정확히 한 번씩 덮지 않는다")
    arm = arms.pop()
    if not comp.pop():
        if any(p.draws_json != "[]" or p.null or p.timing_draws_json != "[]" or p.timing_null for p in parts):
            raise P1Error("계산 불가 조각에 추출이 있다")
        return {"arm": arm, "computable": False, "n_source": 0, "draws": [], "null": [], "failed": 0, "evaluable": False,
                "timing": {"draws": [], "null": [], "failed": 0}}
    n = n_src.pop()
    draws = [d for p in parts for d in json.loads(p.draws_json)]
    null = [r for p in parts for r in p.null]
    failed = _check_block("게이트", draws, null, n, draws_total)
    tdraws = [d for p in parts for d in json.loads(p.timing_draws_json)]
    tnull = [r for p in parts for r in p.timing_null]
    tfailed = _check_block("timing", tdraws, tnull, n, draws_total)
    key = lambda x: x["draw"]                                # noqa: E731
    return {"arm": arm, "computable": True, "n_source": n, "draws": sorted(draws, key=key), "null": sorted(null, key=key),
            "failed": failed, "evaluable": failed <= A.P1_FAIL_MAX,
            "timing": {"draws": sorted(tdraws, key=key), "null": sorted(tnull, key=key), "failed": tfailed}}
