"""S-carry-1 순수 계산(스펙 §3 · §4) — 파일을 읽지 않는다."""
from __future__ import annotations

import bisect
import datetime
import math

import numpy as np

from research.screens.p1.loader import Trade

COSTS = {"A": 10.0, "B": 17.5, "C": 25.0}                                          # 짝 왕복 전부 · bps(D7 · #105 — B가 주)
DAY_MS = 86_400_000
BLOCK_MS = 60 * DAY_MS
COEF_UNCORRECTED, COEF_N64 = 2.80, 4.00
SLIP_PAIR_RT_BPS = 8.0


def utc_date(ms: int) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).date().isoformat()


FIRST_OBS_SEED_BEFORE = "2021-01-04"                                             # 창 안 첫 관측(스펙 §2 첫 관측 규칙 · D4)


def rate_at(rates: list[tuple[str, float]], entry_ms: int) -> tuple[float, bool]:
    """(진입 날짜(UTC) 이하의 마지막 DTB3 관측 · 첫 관측 규칙을 썼는가). 진입일이 창 안 첫 관측(2021-01-04)보다 앞서면 그 첫 관측 —
    그 밖에 관측이 없으면 오류(앞 값 채우기 · 0 대체 없음)."""
    days = [d for d, _ in rates]
    day = utc_date(entry_ms)
    i = bisect.bisect_right(days, day) - 1
    if i >= 0:
        return rates[i][1], False
    if days and days[0] == FIRST_OBS_SEED_BEFORE and day < FIRST_OBS_SEED_BEFORE:
        return rates[0][1], True
    raise ValueError(f"진입 {day} 이전 DTB3 관측 없음")


def per_trade(t: Trade, rates: list[tuple[str, float]]) -> dict[str, float]:
    """거래 하나의 값(전부 그 거래 명목의 bps)."""
    k = 1e4 / t.notional
    gross = t.funding_collected + t.residual_delta_pnl
    r, seeded = rate_at(rates, t.entry_ms)
    dtb3 = t.locked * r / 100.0 * (t.exit_ms - t.entry_ms) / (365 * DAY_MS)
    out = {"seeded_rate": float(seeded), "gross": gross * k, "dtb3": dtb3 * k, "dgs2": t.opportunity_cost * k, "orig_net": t.net_pnl * k,
           "orig_cost": (t.fees + t.slippage) * k}
    for x, bps in COSTS.items():
        out[f"net_{x}"] = out["gross"] - bps
        out[f"net_{x}_dtb3"] = out[f"net_{x}"] - out["dtb3"]
    out["net_B_dgs2"] = out["net_B"] - out["dgs2"]
    out["net_B_slip_dtb3"] = out["net_B_dtb3"] - SLIP_PAIR_RT_BPS                  # 민감도: 원래 슬리피지(레그 · 방향마다 2 bps)
    return out


def block_of(entry_ms: int, start_ms: int) -> int:
    return (entry_ms - start_ms) // BLOCK_MS


def n_blocks(start_ms: int, end_ms: int) -> int:
    """[start, end]를 덮는 60일 블록 수(마지막 부분 블록 포함)."""
    return (end_ms - start_ms) // BLOCK_MS + 1


def block_boot(values: np.ndarray, blocks: np.ndarray, k: int, rng: np.random.Generator, n_draw: int) -> tuple[list[float], int]:
    """60일 날짜 블록 복원 추출(빈 블록 포함 k개) → 뽑힌 블록 거래 전부의 평균. 거래 0건인 추출은 다시 뽑는다(수 보고)."""
    by = [values[blocks == b] for b in range(k)]
    stats, redraws = [], 0
    while len(stats) < n_draw:
        pick = rng.integers(0, k, size=k)
        v = np.concatenate([by[b] for b in pick])
        if v.size == 0:
            redraws += 1
            continue
        stats.append(float(v.mean()))
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))], redraws


def iid_boot(values: np.ndarray, rng: np.random.Generator, n_draw: int) -> list[float]:
    stats = [float(values[rng.integers(0, values.size, size=values.size)].mean()) for _ in range(n_draw)]
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def lag1(values: np.ndarray) -> float:
    if values.size < 3 or float(np.std(values)) == 0.0:
        return float("nan")
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


def mde(values: np.ndarray, coef: float) -> tuple[float, float, float]:
    """(MDE bps, n_eff, ρ̂) — n_eff = n / (1 + 4 · max(ρ̂, 0.15))(프로토콜 §2)."""
    rho = lag1(values)
    n_eff = values.size / (1 + 4 * max(rho if math.isfinite(rho) else 0.0, 0.15))
    return coef * float(np.std(values, ddof=1)) / math.sqrt(n_eff), n_eff, rho


def power_label(m: float) -> str:
    return "feasible" if m <= 20 else ("marginal" if m <= 40 else "infeasible")
