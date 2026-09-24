"""P1 무작위 타이밍 — 트라이얼과 무관한 공통 부분(단계 2f F1 · 트라이얼 import 없음 · 기본값 없음).

규약 (c)~(f)의 기계(두 트라이얼 사전등록 §4 P1 행이 같은 규약을 쓴다): 슬롯을 먼저 전부(쌍 → 방향) · 배치 = h 내림차순(동률 슬롯) ·
슬롯마다 최대 `slot_attempts`회 균등추출 · 겹침·사이징 거부면 재시도 · 실패 → 그 추출 전체 실패 · 쌍은 다시 뽑지 않는다 ·
적격 목록이 비면 난수를 쓰지 않고 실패 · 추출 d의 난수 = `SeedSequence(master_seed).spawn(draws)[d]`.
적격 분 정의((a)(b))와 사이징 수락은 호출자가 준다(트라이얼마다 다르다).
"""
from __future__ import annotations

import bisect
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import numpy as np

from backtest.data import MINUTE_MS

LONG, SHORT = 0, 1


@dataclass(frozen=True)
class P1Config:
    master_seed: int
    draws: int
    slot_attempts: int
    fail_limit: int                        # 실패 > fail_limit → 평가 불가(폐기)


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


class Indexable(Protocol):
    def __len__(self) -> int: ...
    def __getitem__(self, j: int, /) -> int: ...


SizingOk = Callable[[int, int, Decimal], bool]      # (entry_ms, direction, sl_dist) → 사이징 수락?
EligibleFor = Callable[[int], Indexable]            # h → 오름차순 적격 진입 분


def p1_rng(cfg: P1Config, draw: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(cfg.master_seed).spawn(cfg.draws)[draw]))


def sort_source(trades: Sequence[SourceTrade]) -> list[SourceTrade]:
    return sorted(trades, key=lambda t: (t.entry_ms, t.trade_id))


class Occupancy:
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


def p1_draw_generic(draw: int, cfg: P1Config, source: Sequence[SourceTrade], eligible_for: EligibleFor,
                    sizing_ok: SizingOk) -> P1Draw:
    src = sort_source(source)
    n = len(src)
    rng = p1_rng(cfg, draw)
    slots = []
    for k in range(n):                                   # (c) 슬롯 전부 먼저: 쌍 → 방향
        pair = int(rng.integers(0, n))
        direction = int(rng.integers(0, 2))
        slots.append((k, pair, direction, src[pair].h, src[pair].sl_dist))
    order = sorted(slots, key=lambda s: (-s[3], s[0]))  # (d) h 내림차순 · 동률 슬롯 번호
    occ = Occupancy()
    placed: list[PlacedSlot] = []
    for k, pair, direction, h, sl_dist in order:
        elig = eligible_for(h)
        ok = False
        if len(elig):
            for _ in range(cfg.slot_attempts):
                t = elig[int(rng.integers(0, len(elig)))]
                if occ.free(t, t + h * MINUTE_MS) and sizing_ok(t, direction, sl_dist):
                    occ.add(t, t + h * MINUTE_MS)
                    placed.append(PlacedSlot(k, pair, direction, h, sl_dist, t))
                    ok = True
                    break
        if not ok:
            return P1Draw(draw, False, tuple(placed), failed_slot=k)
    return P1Draw(draw, True, tuple(sorted(placed, key=lambda p: p.slot)))


def evaluable(cfg: P1Config, results: Sequence[P1Draw]) -> bool:
    """(f) 실패 > fail_limit → 평가 불가."""
    return sum(1 for r in results if not r.ok) <= cfg.fail_limit


def canonical_json(results: Sequence[P1Draw]) -> str:
    """결정론 검사용 정본 직렬화(바이트 비교)."""
    return json.dumps([{"draw": r.draw, "ok": r.ok, "failed_slot": r.failed_slot,
                        "placed": [[p.slot, p.pair, p.direction, p.h, str(p.sl_dist), p.entry_ms] for p in r.placed]}
                       for r in results], sort_keys=True, separators=(",", ":"))


def p95(values: Sequence[float]) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), 0.95))
