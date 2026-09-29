"""트라이얼 #3 P1 무작위 타이밍(단계 2 (e) · 계획 r2 · 사전등록 §4 92행 · 규약 초안 39·45~50) — 날을 넘는 적격 분 · 암별 스트림.

- 원판 쌍: 그 암 **기본 실행**의 `trades_t3` → `SourceTrade(trade_id, entry_ms = 체결 봉 open, exit_ms = 엔진 청산 ts, sl_dist = 결정 시점
  sl_dist(t3))` · h = `p1_core.SourceTrade.h`(max(1, ceil(Δ/60,000))) · 원판 0건 → 계산 불가 표지(추출 없음).
- 적격 분(§4 (b)): 창 open 분 격자 위 "나쁜 분" = 완전하지 않은 날(`harness.complete_days`)의 모든 분 ∪ 검증된 확정 펀딩이 정확히 1건이 아닌
  00/08/16 경계 분 · 깨끗한 구간 = 나쁜 분 없는 최대 연속 분(날을 넘을 수 있다) · h의 적격 t = [t, t+h−1]이 한 구간 안(닫힌 구간 · b = t 포함) ·
  창 = t ≥ WINDOW_START ∧ t + (h−1)·60,000 ≤ IS_END + 1 − 60,000(마지막 창 open 분) · 게으른 오름차순 보기(`CrossDayEligible`).
- 배치 사이징 = `placebo_exec.sizing_decision(mark_open[t], 방향, sl_dist, #48 규칙, LIMITS, E_ref, REGIME, slippage_rate=0.0006)` ·
  실행 = `run_time_exit(…, reason=TIME_EXIT, slippage_rate=0.0006)` — 둘 다 6 bps(§2).
- **체결 분 펀딩(§1 펀딩 행 "경계 분에 체결된 포지션은 그 경계를 내지 않는다")**: 적격성은 b = t를 요구하지만, 실행에는 버킷 = 진입 분인 펀딩
  기록을 넘기지 않는다(t + 5 ms 같은 기록도) — 기본 재생과 같은 결과(Codex (e) before #1).
- 실행 경로(`run_range`)에는 규칙·설정 인자가 없다(#48 `load_rules` · 앵커 설정) · 픽스처 경로는 `run_range_with_fixture_rules`(tests/ 전용).
- 병합(`merge`): 추출 0..999 정확히 한 번 · 귀무 행의 추출 = 성공한 추출 정확히 한 번 · 행마다 n = 원판 수 · time_exit + liquidation = n.
"""
from __future__ import annotations

import bisect
import inspect
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import numpy as np

from backtest import p1_core as C
from backtest import placebo_exec as PX
from backtest.data import MINUTE_MS, Bar1m, Funding
from exchange.rules import RuntimeRules
from paper.types import ExitReason
from strategies.trial03 import anchor as A
from strategies.trial03.config import LIMITS, REGIME, TF_V1
from strategies.trial03.harness import GRID, complete_days, load_rules, validate_inputs

ROOT = Path(__file__).resolve().parent.parent
DAY = A.DAY_MS
ARMS = ("L", "S")
CFGS = {arm: C.P1Config(master_seed=cast(int, A.P1_SEEDS[arm]),     # 튜플 엔트로피 그대로 — SeedSequence가 받는다(p1_core 무수정)
                        draws=A.P1_DRAWS, slot_attempts=A.P1_SLOT_ATTEMPTS, fail_limit=A.P1_FAIL_MAX) for arm in ARMS}


class P1Error(RuntimeError):
    pass


def source_trades(trades_t3: Sequence[dict[str, Any]]) -> list[C.SourceTrade]:
    return [C.SourceTrade(int(t["trade_id"]), int(t["entry_ms"]), int(t["exit_ms"]), Decimal(t["t3"]["sl_dist"])) for t in trades_t3]


def _bucket(ms: int) -> int:
    return ms - ms % MINUTE_MS


def build_segments(bars: Sequence[Bar1m], fundings: Sequence[Funding],
                   window: tuple[int, int] = (A.WINDOW_START_MS, A.IS_END_MS)) -> list[tuple[int, int]]:
    """깨끗한 구간 [a, b](open 분 ms · 양끝 포함 · 오름차순 · 연속 날 병합)."""
    days = complete_days(bars)
    fund = Counter(_bucket(f.funding_ms) for f in fundings)
    first, last_open = window[0], window[1] + 1 - MINUTE_MS
    segs: list[list[int]] = []
    for d in range(first // DAY, last_open // DAY + 1):
        if d not in days:
            continue
        lo, hi = max(first, d * DAY), min(last_open, d * DAY + DAY - MINUTE_MS)
        cuts = sorted(d * DAY + g for g in GRID if lo <= d * DAY + g <= hi and fund[d * DAY + g] != 1)
        start = lo
        for c in cuts + [hi + MINUTE_MS]:
            end = c - MINUTE_MS
            if start <= end:
                if segs and segs[-1][1] + MINUTE_MS == start:
                    segs[-1][1] = end
                else:
                    segs.append([start, end])
            start = c + MINUTE_MS
    return [(a, b) for a, b in segs]


class CrossDayEligible:
    """h의 적격 진입 분(오름차순) — 구간마다 t ∈ [a, b − (h−1)·60,000]."""

    def __init__(self, segments: Sequence[tuple[int, int]], h: int):
        self.starts = [a for a, _ in segments]
        counts = [max(0, (b - a) // MINUTE_MS + 1 - h + 1) for a, b in segments]
        self.cum = list(np.cumsum(counts, dtype=np.int64)) if counts else []
        self.n = int(self.cum[-1]) if self.cum else 0

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, j: int) -> int:
        if not 0 <= j < self.n:
            raise IndexError(j)
        i = bisect.bisect_right(self.cum, j)
        before = int(self.cum[i - 1]) if i else 0
        return self.starts[i] + (j - before) * MINUTE_MS


def draw(d: int, cfg: C.P1Config, source: Sequence[C.SourceTrade], segments: Sequence[tuple[int, int]],
         bars: dict[int, Bar1m], rules: RuntimeRules) -> C.P1Draw:
    cache: dict[int, CrossDayEligible] = {}

    def eligible_for(h: int) -> CrossDayEligible:
        if h not in cache:
            cache.clear()                                   # h 내림차순 배치 — 최근 h 하나만
            cache[h] = CrossDayEligible(segments, h)
        return cache[h]

    def sizing_ok(t: int, direction: int, sl_dist: Decimal) -> bool:
        _, dec = PX.sizing_decision(bars[t].d("mark_open"), direction, sl_dist, rules, LIMITS, TF_V1.e_ref, REGIME,
                                    slippage_rate=TF_V1.slippage)
        return bool(dec.ok)

    return C.p1_draw_generic(d, cfg, source, eligible_for, sizing_ok)


def null_point(dr: C.P1Draw, bars: dict[int, Bar1m], fundings: Sequence[Funding], rules: RuntimeRules) -> dict[str, Any]:
    """성공한 추출 하나 → 트레이드당 평균 net_bps(Decimal 문자열) + 청산 사유 개수. 체결 분 버킷의 펀딩 기록은 넘기지 않는다."""
    if not dr.ok:
        raise P1Error(f"실패한 추출 {dr.draw}의 귀무 점")
    nets: list[Decimal] = []
    reasons = {"time_exit": 0, "liquidation": 0}
    by_bucket: dict[int, list[Funding]] = {}
    for f in fundings:
        by_bucket.setdefault(_bucket(f.funding_ms), []).append(f)
    for p in dr.placed:
        fs = fundings if p.entry_ms not in by_bucket else [f for f in fundings if _bucket(f.funding_ms) != p.entry_ms]
        r = PX.run_time_exit(bars, fs, entry_ms=p.entry_ms, h=p.h, direction=p.direction, sl_dist=p.sl_dist, rules=rules,
                             limits=LIMITS, equity=TF_V1.e_ref, regime=REGIME, reason=ExitReason.TIME_EXIT,
                             slippage_rate=TF_V1.slippage)
        if not r.ok or r.ret is None:
            raise AssertionError(f"추출 {dr.draw} 슬롯 {p.slot}: 배치 때 수락된 사이징이 실행에서 거부됐다")
        nets.append(r.ret.net_bps)
        reasons[r.reason] += 1
    return {"draw": dr.draw, "n": len(nets), "mean_net_bps": str(sum(nets, Decimal()) / len(nets)), "exits": reasons}


@dataclass
class P1Part:
    arm: str
    lo: int
    hi: int
    n_source: int
    computable: bool
    draws_json: str                       # p1_core.canonical_json
    null: list[dict[str, Any]]


def _run_range(arm: str, trades_t3: Sequence[dict[str, Any]], bars: Sequence[Bar1m], fundings: Sequence[Funding], lo: int, hi: int,
               *, rules: RuntimeRules, cfg: C.P1Config, window: tuple[int, int]) -> P1Part:
    if arm not in ARMS or not 0 <= lo <= hi < cfg.draws:
        raise P1Error(f"arm {arm} · 범위 {lo}-{hi}")
    validate_inputs(bars, fundings)                              # 원래 순서의 입력을 먼저(Codex (e) before #4)
    src = source_trades(trades_t3)
    if not src:
        return P1Part(arm, lo, hi, 0, False, "[]", [])
    segs = build_segments(bars, fundings, window)
    by_t = {b.open_ms: b for b in bars}
    draws = [draw(d, cfg, src, segs, by_t, rules) for d in range(lo, hi + 1)]
    null = [null_point(dr, by_t, fundings, rules) for dr in draws if dr.ok]
    return P1Part(arm, lo, hi, len(src), True, C.canonical_json(draws), null)


def run_range(arm: str, trades_t3: Sequence[dict[str, Any]], bars: Sequence[Bar1m], fundings: Sequence[Funding],
              lo: int, hi: int) -> P1Part:
    """실행 경로 — 규칙 = `load_rules()`(#48) · 설정 = 앵커(`CFGS[arm]`) · 창 = WINDOW_START … IS_END. 덮어쓸 인자가 없다."""
    return _run_range(arm, trades_t3, bars, fundings, lo, hi, rules=load_rules(), cfg=CFGS[arm],
                      window=(A.WINDOW_START_MS, A.IS_END_MS))


def run_range_with_fixture_rules(arm: str, trades_t3: Sequence[dict[str, Any]], bars: Sequence[Bar1m], fundings: Sequence[Funding],
                                 lo: int, hi: int, *, rules: RuntimeRules, window: tuple[int, int],
                                 cfg: C.P1Config | None = None) -> P1Part:
    """**테스트 전용** — 호출자 파일이 tests/ 아래가 아니면 거부."""
    caller = Path(inspect.stack()[1].filename).resolve()
    if (ROOT / "tests") not in caller.parents:
        raise P1Error(f"픽스처 경로는 tests/ 전용이다(호출자 {caller})")
    return _run_range(arm, trades_t3, bars, fundings, lo, hi, rules=rules, cfg=cfg or CFGS[arm], window=window)


def merge(parts: Sequence[P1Part], draws_total: int = A.P1_DRAWS) -> dict[str, Any]:
    """조각 병합 + 불변식(Codex (e) before #3). 반환: computable · draws(정렬) · null(정렬) · failed · evaluable."""
    if not parts:
        raise P1Error("조각 없음")
    arms = {p.arm for p in parts}
    n_src = {p.n_source for p in parts}
    comp = {p.computable for p in parts}
    if len(arms) != 1 or len(n_src) != 1 or len(comp) != 1:
        raise P1Error(f"조각 불일치: arm {arms} · n_source {n_src} · computable {comp}")
    if not comp.pop():
        if any(p.draws_json != "[]" or p.null for p in parts):
            raise P1Error("계산 불가 조각에 추출이 있다")
        return {"arm": arms.pop(), "computable": False, "n_source": 0, "draws": [], "null": [], "failed": 0, "evaluable": False}
    draws = [d for p in parts for d in json.loads(p.draws_json)]
    ids = sorted(d["draw"] for d in draws)
    if ids != list(range(draws_total)):
        raise P1Error(f"추출 0..{draws_total - 1}을 정확히 한 번씩 덮지 않는다(개수 {len(ids)})")
    ok_ids = sorted(d["draw"] for d in draws if d["ok"])
    null = [r for p in parts for r in p.null]
    if sorted(r["draw"] for r in null) != ok_ids:
        raise P1Error("귀무 행의 추출이 성공한 추출과 다르다")
    n = n_src.pop()
    for r in null:
        if r["n"] != n or sum(r["exits"].values()) != n or set(r["exits"]) != {"time_exit", "liquidation"}:
            raise P1Error(f"귀무 행 {r['draw']}: n 또는 청산 사유 합이 원판 수 {n}과 다르다")
    failed = draws_total - len(ok_ids)
    return {"arm": arms.pop(), "computable": True, "n_source": n, "draws": sorted(draws, key=lambda d: d["draw"]),
            "null": sorted(null, key=lambda r: r["draw"]), "failed": failed, "evaluable": failed <= A.P1_FAIL_MAX}
