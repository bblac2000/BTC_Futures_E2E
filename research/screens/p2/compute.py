"""S-xs-carry-1 순수 계산(스펙 r6 §2 ~ §7) — 파일을 읽지 않는다."""
from __future__ import annotations

import bisect
import datetime
import math
from dataclasses import dataclass, field

import numpy as np

from research.screens.p2.loader import Series, Symbol

H = 3_600_000
DAY = 86_400_000
WEEK = 7 * DAY
TOL = 60_000
CADENCES = (1 * H, 2 * H, 4 * H, 8 * H)
AGE_MS = 28 * DAY
RESET_GAP_MS = 30 * DAY
MIN_N = 20
TAKER_BPS, MAKER_BPS = 10.0, 2.0


def month_of(ms: int) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).strftime("%Y-%m")


def months_between(lo: int, hi: int) -> set[str]:
    """[lo, hi)가 닿는 달."""
    out, t = set(), lo
    while t < hi:
        out.add(month_of(t))
        t += DAY
    out.add(month_of(hi - 1))
    return out


def _slice(s: Series, lo: int, hi: int, *, lo_incl: bool = True, hi_incl: bool = False) -> tuple[np.ndarray, np.ndarray]:
    a = int(np.searchsorted(s.ts, lo, side="left" if lo_incl else "right"))
    b = int(np.searchsorted(s.ts, hi, side="right" if hi_incl else "left"))
    return s.ts[a:b], s.val[a:b]


def cadence(ts_valid: np.ndarray) -> int | None:
    """유효 정산 간격의 중앙값 → {1, 2, 4, 8}시간 중 60초 안에 맞는 것(없으면 None)."""
    if ts_valid.size < 2:
        return None
    g = float(np.median(np.diff(ts_valid)))
    for c in CADENCES:
        if abs(g - c) <= TOL:
            return c
    return None


def grid(lo: int, hi: int, g: int, *, lo_incl: bool, hi_incl: bool) -> list[int]:
    """UTC 00:00 기준 g 배수 격자 중 구간 안의 점."""
    first = (lo // g) * g
    pts = []
    t = first
    while t <= hi:
        if (t > lo or (lo_incl and t == lo)) and (t < hi or (hi_incl and t == hi)):
            pts.append(t)
        t += g
    return pts


def signal_window(s: Series, lo: int, hi: int) -> float | None:
    """[lo, hi)의 완전성(§3-1) — 완전하면 정산 합, 아니면 None. 나쁜 레코드가 구간에 있으면 None."""
    ts, val = _slice(s, lo, hi)
    if np.isnan(val).any():
        return None
    g = cadence(ts)
    if g is None:
        return None
    pts = grid(lo, hi, g, lo_incl=True, hi_incl=False)
    used = np.zeros(ts.size, dtype=bool)
    total = 0.0
    for p in pts:
        m = np.nonzero(np.abs(ts - p) <= TOL)[0]
        if m.size != 1:
            return None
        used[m[0]] = True
        total += float(val[m[0]])
    if not used.all():                                                         # 격자 밖 유효 정산
        return None
    return total


def signal_cadence(s: Series, lo: int, hi: int) -> int | None:
    ts, val = _slice(s, lo, hi)
    return cadence(ts[~np.isnan(val)])


@dataclass
class HoldFunding:
    total: float
    missing: int
    collisions: int
    offgrid: int


def hold_funding(s: Series, t0: int, x: int, g: int) -> HoldFunding:
    """(T, X]의 예상 격자(§4-3) — 한 칸 유효 하나 = 더함 · 없음/나쁨 = 빠짐 · 둘 이상 = 충돌(빠짐) · 격자 밖 유효 = 더함."""
    if x <= t0:
        return HoldFunding(0.0, 0, 0, 0)
    ts, val = _slice(s, t0 - TOL, x + TOL, lo_incl=True, hi_incl=True)
    ok = ~np.isnan(val)
    tv, vv = ts[ok], val[ok]
    pts = grid(t0, x, g, lo_incl=False, hi_incl=True)
    total, missing, coll = 0.0, 0, 0
    near = np.zeros(tv.size, dtype=bool)
    full = grid(t0 - g, x + g, g, lo_incl=True, hi_incl=True)                  # 격자 밖 판단은 T 칸까지 포함한 전체 격자로
    for p in full:
        near |= np.abs(tv - p) <= TOL
    for p in pts:
        m = np.nonzero(np.abs(tv - p) <= TOL)[0]
        if m.size == 1:
            total += float(vv[m[0]])
        else:
            missing += 1
            coll += int(m.size >= 2)
    off = (~near) & (tv > t0) & (tv <= x)
    total += float(vv[off].sum())
    return HoldFunding(total, missing, coll, int(off.sum()))


def first_obs_run_start(s: Series, before: int) -> int | None:
    """`before` 이전 마지막 유효 정산이 속한 연속 구간(30일 넘는 공백으로 나뉨)의 시작."""
    ok = ~np.isnan(s.val)
    ts = s.ts[ok]
    i = int(np.searchsorted(ts, before, side="left")) - 1
    if i < 0:
        return None
    while i > 0 and ts[i] - ts[i - 1] <= RESET_GAP_MS:
        i -= 1
    return int(ts[i])


def bar_close(b: Series, open_time: int) -> float | None:
    i = int(np.searchsorted(b.ts, open_time))
    if i < b.ts.size and int(b.ts[i]) == open_time:
        v = float(b.val[i])
        return v if math.isfinite(v) and v > 0 else None
    return None


def bad_in(s: Series, lo: int, hi: int) -> bool:
    _, val = _slice(s, lo, hi)
    return bool(np.isnan(val).any())


@dataclass
class Entry:
    name: str
    s0: float
    s1: float | None
    p_entry: float
    g: int


def eligible(sym: Symbol, t0: int) -> Entry | None:
    """주 t(시작 T)의 적격(§3 · 진입 전 정보만)."""
    lo8 = t0 - 8 * DAY
    if months_between(t0 - WEEK, t0) & sym.unusable_funding:
        return None
    if bad_in(sym.funding, lo8, t0) or bad_in(sym.bars, lo8, t0):
        return None
    s0 = signal_window(sym.funding, t0 - WEEK, t0)
    if s0 is None:
        return None
    start = first_obs_run_start(sym.funding, t0)
    if start is None or start > t0 - WEEK - AGE_MS:
        return None
    p = bar_close(sym.bars, t0 - DAY)
    if p is None:
        return None
    g = signal_cadence(sym.funding, t0 - WEEK, t0)
    assert g is not None
    s1 = None
    if not (months_between(t0 - 2 * WEEK, t0 - WEEK) & sym.unusable_funding) and not bad_in(sym.funding, t0 - 2 * WEEK, t0 - WEEK):
        s1 = signal_window(sym.funding, t0 - 2 * WEEK, t0 - WEEK)
    return Entry(sym.name, s0, s1, p, g)


@dataclass
class Outcome:
    x: int
    p_exit: float
    forced: bool
    r: float
    f: HoldFunding


def outcome(sym: Symbol, e: Entry, t0: int) -> Outcome:
    """매일 점검(§4-3 · 인과): 시각 T + k일에 일봉(open_time T + (k−1)일)이 없거나 나쁘면 그때 마지막 알려진 종가로 청산."""
    last = e.p_entry
    for k in range(1, 8):
        c = bar_close(sym.bars, t0 + (k - 1) * DAY)
        if c is None:
            x = t0 + k * DAY
            return Outcome(x, last, True, last / e.p_entry - 1, hold_funding(sym.funding, t0, x, e.g))
        last = c
    x = t0 + WEEK
    return Outcome(x, last, False, last / e.p_entry - 1, hold_funding(sym.funding, t0, x, e.g))


def avg_rank(x: np.ndarray) -> np.ndarray:
    o = np.argsort(x, kind="mergesort")
    r = np.empty(x.size, dtype=float)
    r[o] = np.arange(1, x.size + 1, dtype=float)
    xs = x[o]
    i = 0
    while i < xs.size:
        j = i
        while j + 1 < xs.size and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            r[o[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return r


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size < 2:
        return None
    ra, rb = avg_rank(a), avg_rank(b)
    if bool(np.all(ra == ra[0])) or bool(np.all(rb == rb[0])):
        return None
    v = float(np.corrcoef(ra, rb)[0, 1])
    return v if math.isfinite(v) else None


def t_stat(ics: list[float]) -> float | None:
    if len(ics) < 3:
        return None
    a = np.array(ics)
    if bool(np.all(a == a[0])):                                                # 상수 — 값 비교(부동소수 잔차 회피)
        return None
    sd = float(np.std(a, ddof=1))
    v = float(a.mean() / sd * math.sqrt(a.size))
    return v if math.isfinite(v) else None


def lag1(values: np.ndarray) -> float:
    if values.size < 3:
        return 0.0
    a, b = values[:-1], values[1:]
    if bool(np.all(a == a[0])) or bool(np.all(b == b[0])):
        return 0.0
    r = float(np.corrcoef(a, b)[0, 1])
    return r if math.isfinite(r) else 0.0


def mde(values: np.ndarray) -> dict | None:
    if values.size < 2:
        return None
    rho = lag1(values)
    n_eff = values.size / (1 + 4 * max(rho, 0.15))
    sd = float(np.std(values, ddof=1))
    base = sd / math.sqrt(n_eff)
    m = 2.80 * base
    return {"uncorrected_2.80": m, "n64_4.00": 4.00 * base, "n64_two_sided_4.20": 4.20 * base, "n_eff": n_eff, "rho_lag1": rho,
            "power_label": "feasible" if m <= 20 else ("marginal" if m <= 40 else "infeasible")}


@dataclass
class Week:
    t0: int
    names: list[str]                       # 이름 순
    s0: np.ndarray
    s1: list[float | None]
    y: np.ndarray                          # 숏 수익(−r + F)
    r: np.ndarray
    f: np.ndarray
    forced: np.ndarray
    fund_deficit: np.ndarray
    missing: int = 0
    collisions: int = 0
    long: list[int] = field(default_factory=list)
    short: list[int] = field(default_factory=list)
    ratio: np.ndarray = field(default_factory=lambda: np.zeros(0))


def build_week(t0: int, entries: list[tuple[Entry, Outcome]]) -> Week:
    entries = sorted(entries, key=lambda eo: eo[0].name)
    n = len(entries)
    s0 = np.array([e.s0 for e, _ in entries])
    r = np.array([o.r for _, o in entries])
    f = np.array([o.f.total for _, o in entries])
    w = Week(t0, [e.name for e, _ in entries], s0, [e.s1 for e, _ in entries], -r + f, r, f,
             np.array([o.forced for _, o in entries]), np.array([o.f.missing > 0 for _, o in entries]),
             sum(o.f.missing for _, o in entries), sum(o.f.collisions for _, o in entries))
    w.ratio = np.array([o.p_exit / e.p_entry for e, o in entries])
    q = n // 10
    order = sorted(range(n), key=lambda i: (s0[i], w.names[i]))
    w.long, w.short = order[:q], order[n - q:]
    return w


def leg_returns(w: Week, keep: np.ndarray | None = None) -> tuple[float, float]:
    """(롱 다리 · 숏 다리) bps — keep으로 이름을 빼면 남은 이름의 평균(민감도 열)."""
    def mean(ix: list[int], vals: np.ndarray) -> float:
        ix = [i for i in ix if keep is None or keep[i]]
        return float(np.mean(vals[ix])) if ix else math.nan
    return 1e4 * mean(w.long, w.r - w.f), 1e4 * mean(w.short, -w.r + w.f)


def turnover(weeks: list[Week], holding: list[bool]) -> list[float]:
    """주마다 거래 명목(한 다리 명목 단위 · 두 다리 합 · §5)."""
    out = []
    prev: dict[tuple[str, str], float] = {}                                    # (다리, 이름) → 이월 명목
    for k, w in enumerate(weeks):
        if not holding[k]:
            out.append(0.0)
            prev = {}
            continue
        q = len(w.long)
        tgt = {("L", w.names[i]): 1.0 / q for i in w.long} | {("S", w.names[i]): 1.0 / q for i in w.short}
        traded = sum(abs(tgt.get(key, 0.0) - prev.get(key, 0.0)) for key in set(tgt) | set(prev))
        cur: dict[tuple[str, str], float] = {}
        for leg, ix in (("L", w.long), ("S", w.short)):
            for i in ix:
                val = (1.0 / q) * float(w.ratio[i])
                if w.forced[i]:
                    traded += val                                              # 강제 청산(주 끝 포함) — 한 번
                else:
                    cur[(leg, w.names[i])] = val
        if k + 1 >= len(weeks) or not holding[k + 1]:
            traded += sum(cur.values())                                         # 마지막 청산
            cur = {}
        out.append(traded)
        prev = cur
    return out


def shuffle_null(weeks: list[tuple[np.ndarray, np.ndarray]], seed: int, n_draw: int) -> list[float]:
    """주 오름차순 · 주 안 이름 순의 s에 rng.permutation → 주별 IC 평균(§6 ②)."""
    rng = np.random.default_rng(seed)
    rk = [(avg_rank(s), avg_rank(y)) for s, y in weeks]
    out = []
    for _ in range(n_draw):
        ics = []
        for rs, ry in rk:
            p = rs[rng.permutation(rs.size)]
            ics.append(float(np.corrcoef(p, ry)[0, 1]))
        out.append(float(np.mean(ics)))
    return out


def dtb3_weekly_bps(rates: list[tuple[str, float]], t0: int) -> float:
    days = [d for d, _ in rates]
    i = bisect.bisect_right(days, datetime.datetime.fromtimestamp(t0 / 1000, datetime.UTC).date().isoformat()) - 1
    if i < 0:
        raise ValueError("DTB3 관측 없음")
    return 1e4 * rates[i][1] / 100.0 * 7 / 365
