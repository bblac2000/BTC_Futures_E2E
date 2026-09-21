"""플라시보 생성기(단계 2a) — 사전등록 §4. 전략과 무관한 부분만: P1 추출(규약 a~f)·P4 무작위 레벨.

P2(지연)·P3(부호 반전)은 **같은 전략 코드에 플래그**를 넘겨 다시 돌리는 결정론적 대조군이라 여기 없다(러너가 인자로 넘긴다).

## P1 — 규약 (a)~(f)가 유일한 정의다(사전등록 P1 행)
- (a) 진입 격자 = 평가 창 안 mark 관측이 있는 1분 시작 시각.
- (b) `h` = 원 트레이드 지속시간을 분 단위로 올림(최소 1) · 점유 `[t, t+h)` · 청산 = 분 `t+h−1`의 mark 종가 ·
  적격 진입 분 = `t`와 `t+h−1`이 모두 창 안이고 둘 다 mark 관측이 있는 분(오름차순).
- (c) 슬롯 k = 1…n을 **먼저 전부** 뽑는다: `pair_k = rng.integers(0, N_A)` → `dir_k = rng.integers(0, 2)`(0 = LONG · 1 = SHORT).
  Arm A 트레이드는 진입 시각 오름차순(동률 트레이드 id).
- (d) 배치 = `h` 내림차순(동률 슬롯 번호 오름차순) · 슬롯마다 최대 1,000회 `t = eligible[rng.integers(0, len(eligible))]` ·
  겹치지 않고 사이징이 수락하면 배치 · 1,000회 실패 → **그 추출 전체 실패** · **쌍은 다시 뽑지 않는다**.
- (e) `Generator(PCG64(SeedSequence(20260921).spawn(1000)[d]))` · 호출 순서 = 슬롯 전부(쌍 → 방향) → 배치 순서대로 진입 시도.
- (f) 실패 추출은 교체하지 않는다 · p95는 성공 추출만 · 실패 > 10(>1%) → 평가 불가 → 트라이얼 **폐기**.
구현 메모: 적격 목록이 비어 있으면(창보다 긴 `h`) 난수를 소비하지 않고 그 슬롯이 실패한다 — `rng.integers(0, 0)`은 정의되지 않는다.

## P4 — 무작위 레벨(시드는 사전등록 밖의 구현 규약: `anchor.P4_SEED` 스트림)
원 레벨 하나당 무작위 레벨 하나(개수·유효기간 동일) · 가격 = 레벨의 **유효 시작 시각 기준 직전 24시간 마감 1m** 고가~저가에서
tick 격자 균등추출(결정 시점 정보만 · Codex #6).
"""
from __future__ import annotations

import bisect
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from backtest.data import MINUTE_MS
from strategies.trial01 import anchor as A

P1_SLOT_ATTEMPTS = 1000
P1_FAIL_LIMIT = 10                        # > 10 실패(>1%) → 평가 불가
LONG, SHORT = 0, 1


@dataclass(frozen=True)
class SourceTrade:
    """원판 Arm A 트레이드 — P1이 쓰는 기하(쌍)만."""
    trade_id: int
    entry_ms: int
    exit_ms: int
    sl_dist: Decimal

    @property
    def h(self) -> int:
        return max(1, math.ceil((self.exit_ms - self.entry_ms) / MINUTE_MS))


@dataclass(frozen=True)
class PlacedSlot:
    slot: int
    pair: int                              # 정렬된 원판 트레이드 인덱스
    direction: int                         # 0 LONG · 1 SHORT
    h: int
    sl_dist: Decimal
    entry_ms: int

    @property
    def exit_minute_ms(self) -> int:
        return self.entry_ms + (self.h - 1) * MINUTE_MS


@dataclass(frozen=True)
class P1Draw:
    draw: int
    ok: bool
    placed: tuple[PlacedSlot, ...]
    failed_slot: int | None = None


def p1_rng(draw: int, *, master: int = A.P1_MASTER_SEED, draws: int = A.P1_DRAWS) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(master).spawn(draws)[draw]))


def sort_source(trades: Sequence[SourceTrade]) -> list[SourceTrade]:
    return sorted(trades, key=lambda t: (t.entry_ms, t.trade_id))


def eligible_minutes(grid: Sequence[int], h: int, start_ms: int, end_ms: int) -> list[int]:
    """(b) `t`와 `t+h−1` 모두 창 안이고 mark 관측이 있는 분(오름차순)."""
    have = set(grid)
    return [t for t in sorted(grid)
            if start_ms <= t and t + (h - 1) * MINUTE_MS <= end_ms and (t + (h - 1) * MINUTE_MS) in have]


class _Occupancy:
    """배치된 반열린 구간 `[t, t+h)`(ms)의 겹침 검사."""

    def __init__(self) -> None:
        self.starts: list[int] = []
        self.ends: list[int] = []

    def free(self, a: int, b: int) -> bool:
        i = bisect.bisect_right(self.starts, a)
        if i > 0 and self.ends[i - 1] > a:
            return False
        return not (i < len(self.starts) and self.starts[i] < b)

    def add(self, a: int, b: int) -> None:
        i = bisect.bisect_right(self.starts, a)
        self.starts.insert(i, a)
        self.ends.insert(i, b)


SizingOk = Callable[[int, int, Decimal], bool]      # (entry_ms, direction, sl_dist) → B2 사이징 수락?


def p1_draw(draw: int, source: Sequence[SourceTrade], grid: Sequence[int], start_ms: int, end_ms: int,
            sizing_ok: SizingOk) -> P1Draw:
    src = sort_source(source)
    n = len(src)
    rng = p1_rng(draw)
    slots = []
    for k in range(n):                                   # (c) 슬롯 전부 먼저: 쌍 → 방향
        pair = int(rng.integers(0, n))
        direction = int(rng.integers(0, 2))
        slots.append((k, pair, direction, src[pair].h, src[pair].sl_dist))
    order = sorted(slots, key=lambda s: (-s[3], s[0]))  # (d) h 내림차순 · 동률 슬롯 번호
    elig_cache: dict[int, list[int]] = {}
    occ = _Occupancy()
    placed: list[PlacedSlot] = []
    for k, pair, direction, h, sl_dist in order:
        elig = elig_cache.setdefault(h, eligible_minutes(grid, h, start_ms, end_ms))
        ok = False
        if elig:
            for _ in range(P1_SLOT_ATTEMPTS):
                t = elig[int(rng.integers(0, len(elig)))]
                if occ.free(t, t + h * MINUTE_MS) and sizing_ok(t, direction, sl_dist):
                    occ.add(t, t + h * MINUTE_MS)
                    placed.append(PlacedSlot(k, pair, direction, h, sl_dist, t))
                    ok = True
                    break
        if not ok:
            return P1Draw(draw, False, tuple(placed), failed_slot=k)
    return P1Draw(draw, True, tuple(sorted(placed, key=lambda p: p.slot)))


def p1_all(source: Sequence[SourceTrade], grid: Sequence[int], start_ms: int, end_ms: int, sizing_ok: SizingOk,
           *, draws: int = A.P1_DRAWS) -> list[P1Draw]:
    return [p1_draw(d, source, grid, start_ms, end_ms, sizing_ok) for d in range(draws)]


def p1_evaluable(results: Sequence[P1Draw]) -> bool:
    """(f) 실패 > 10 → 평가 불가(트라이얼 폐기)."""
    return sum(1 for r in results if not r.ok) <= P1_FAIL_LIMIT


def p1_canonical_json(results: Sequence[P1Draw]) -> str:
    """결정론 검사용 정본 직렬화(바이트 비교)."""
    return json.dumps([{"draw": r.draw, "ok": r.ok, "failed_slot": r.failed_slot,
                        "placed": [[p.slot, p.pair, p.direction, p.h, str(p.sl_dist), p.entry_ms] for p in r.placed]}
                       for r in results], sort_keys=True, separators=(",", ":"))


def p95(values: Sequence[float]) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), 0.95))


# ── P4 ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Level:
    level_id: int
    kind: str                     # "swing_high" · "swing_low" · "poc" · "vah" · "val"
    valid_from_ms: int
    valid_to_ms: int              # 포함
    price: Decimal


RangeAt = Callable[[int], tuple[Decimal, Decimal]]   # t → 직전 24h 마감 1m (저가, 고가)


def p4_rng(draw: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(list(A.P4_SEED)).spawn(A.P4_DRAWS)[draw]))


def tick_uniform(rng: np.random.Generator, lo: Decimal, hi: Decimal, tick: Decimal) -> Decimal:
    """[lo, hi] 안 tick 격자(lo 기준)에서 균등추출 — 난수 1회."""
    if hi < lo:
        raise ValueError("범위 역전")
    n_ticks = int((hi - lo) / tick)
    return lo + tick * int(rng.integers(0, n_ticks + 1))


def p4_levels(draw: int, levels: Sequence[Level], range_at: RangeAt, tick: Decimal) -> list[Level]:
    """원 레벨과 1:1 · 같은 종류·유효기간 · 가격만 결정 시점 범위에서 tick 격자 균등추출."""
    rng = p4_rng(draw)
    out = []
    for lv in sorted(levels, key=lambda x: (x.valid_from_ms, x.level_id)):
        lo, hi = range_at(lv.valid_from_ms)
        price = tick_uniform(rng, lo, hi, tick)
        out.append(Level(lv.level_id, lv.kind, lv.valid_from_ms, lv.valid_to_ms, price))
    return out


# ── P2·P3 변형 인자 + 기각 규칙(사전등록 §4 표 그대로) ────────────────────────────
P2_DELAYS = (1, 5)                               # 확인 신호 +1봉 · +5봉 지연(결정론적 대조군 2개)


def variant_args() -> dict[str, list[str]]:
    """같은 정본 전략을 플래그만 바꿔 다시 돌린다(격리 러너 인자)."""
    return {"P2_delay1": ["--delay", "1"], "P2_delay5": ["--delay", "5"], "P3_invert": ["--invert"]}


def p4_args() -> dict[str, list[str]]:
    """P4 무작위 레벨 200회 — 같은 정본 전략·엔진에 `--p4-draw d`(레지스트리 #22 · `strategies/trial01/p4.py`)."""
    return {f"P4_draw{d:03d}": ["--p4-draw", str(d)] for d in range(A.P4_DRAWS)}


def p1_rejects(original: float, null: Sequence[float]) -> bool:
    """P1: 전략 순엣지 ≤ 플라시보 분포 p95 → 기각."""
    return original <= p95(null)


def p2_rejects(original: float, delay1: float, delay5: float) -> bool:
    """P2: 원판 순엣지 ≤ max(지연+1, 지연+5) → 기각."""
    return original <= max(delay1, delay5)


def p3_rejects(original: float, inverted: float) -> bool:
    """P3: 원판 순엣지 ≤ 반전판 → 기각."""
    return original <= inverted


def p4_rejects(original: float, null: Sequence[float]) -> bool:
    """P4: 무작위 레벨판 순엣지 분포 p95 ≥ 원판 → 기각."""
    return p95(null) >= original
