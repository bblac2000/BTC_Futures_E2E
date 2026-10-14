"""M-1 표본(스펙 r6 §3) — 시드 20261014 하나 · 날짜 오름차순 → 근접 층 → 시간 0~23 · 정렬 뒤 방향."""
from __future__ import annotations

import datetime as dt

import numpy as np

from research.screens.p0 import span as SP

SEED = 20261014
DAY_MS, H_MS = 86_400_000, 3_600_000
PROX_S = 300
N_PROX = 100
N_HOUR = tuple([13] * 12 + [12] * 12)                       # 합 300


def _prox(sec_ms: np.ndarray) -> np.ndarray:
    """정산 근접: 범위 안 정산 시각 B(00 · 08 · 16 UTC)의 [B − 300초, B + 300초)."""
    rel = (sec_ms + PROX_S * 1000) % (8 * H_MS)
    return rel < 2 * PROX_S * 1000


def draw() -> list[tuple[int, bool, str]]:
    """(t0 ms, BUY 여부, 층) 목록 — 층 = 'prox' | 'other'."""
    rng = np.random.default_rng(SEED)
    out: list[tuple[int, bool, str]] = []
    for date in SP.DATES:
        d0 = int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.UTC).timestamp() * 1000)
        secs = np.arange(d0, d0 + DAY_MS, 1000, dtype=np.int64)
        secs = secs[(secs >= SP.EXPOSED_START_MS) & (secs <= SP.EXPOSED_END_MS)]
        pm = _prox(secs)
        picks: list[tuple[int, str]] = []
        prox = secs[pm]
        k = int(np.floor(N_PROX * len(prox) / 1800))
        if k:
            picks += [(int(x), "prox") for x in rng.choice(prox, size=k, replace=False)]
        for h in range(24):
            full = np.arange(d0 + h * H_MS, d0 + (h + 1) * H_MS, 1000, dtype=np.int64)
            full_other = int((~_prox(full)).sum())
            avail = secs[(~pm) & (secs >= d0 + h * H_MS) & (secs < d0 + (h + 1) * H_MS)]
            k = int(np.floor(N_HOUR[h] * len(avail) / full_other)) if full_other else 0
            if k:
                picks += [(int(x), "other") for x in rng.choice(avail, size=k, replace=False)]
        picks.sort()
        dirs = rng.integers(0, 2, size=len(picks))
        out += [(t, bool(dv == 0), st) for (t, st), dv in zip(picks, dirs, strict=True)]
    return out
