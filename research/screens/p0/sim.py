"""M-1 체결 재생(스펙 r6 §3~§6) — 순수 함수. 입력은 하루치(여유 포함) 배열, 출력은 결정별 결과.

재생 원칙(§2-3): 호가는 `recv_ms ≤ 기준 시각`의 마지막 값 · 체결은 (수신 상한 ∧ 거래소 시각 하한).
가격 닿음 = 체결 금지 — 같은 가격의 우리 쪽 공격 체결 누적이 Q + 0.001에 닿을 때만 메이커 체결(§4-3).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
_RULES = json.loads((ROOT / "docs" / "trials" / "trial_04_rules_snapshot" / "exchangeInfo.json").read_text(encoding="utf-8"))
_F = {f["filterType"]: f for f in next(s for s in _RULES["response"]["symbols"] if s["symbol"] == "BTCUSDT")["filters"]}
TICK = float(_F["PRICE_FILTER"]["tickSize"])
QTY = float(_F["LOT_SIZE"]["minQty"])                      # 0.001 BTC — 주문 크기
MIN_NOTIONAL = float(_F["MIN_NOTIONAL"]["notional"])
LEVELS = 20
DELTA_MS = 200
TS = (30_000, 60_000, 120_000)
PRE_MS, POST_MS = 5_000, 125_000                           # 적격 창 [t0 − 5초, t0 + δ + 125초]
FRESH_MS = 1_000
BT_GAP_MS, DP_GAP_MS = 5_000, 1_000
LATE_RECV_MS = 5_000
B_MAX_MS = 2_000
EPS = 1e-12
FEES = {"primary": (0.0002, 0.0005), "bnb": (0.00015, 0.000375)}       # (메이커, 테이커)


def ticks(px: np.ndarray | float) -> np.ndarray:
    return np.rint(np.asarray(px, dtype=float) / TICK).astype(np.int64)


@dataclass
class Book:
    """하루치(여유 포함) 배열 — 모두 수신 시각 오름차순."""
    bt_recv: np.ndarray
    bt: np.ndarray                    # (n, 4): bid, bid_qty, ask, ask_qty
    dp_recv: np.ndarray
    dp: np.ndarray                    # (n, 80): b p1 q1 … p20 q20, a p1 q1 … p20 q20
    ag_recv: np.ndarray
    ag_id: np.ndarray
    ag_tick: np.ndarray
    ag_qty: np.ndarray
    ag_tt: np.ndarray
    ag_bm: np.ndarray                 # is_buyer_maker
    lo_ms: int                        # 이 배열이 담고 있는(범위 안) 구간
    hi_ms: int
    bad: list[tuple[int, int]] = field(default_factory=list)       # gaps · clock_skew · 제외 파일 구간


def _last(recv: np.ndarray, t: int) -> int:
    return int(np.searchsorted(recv, t, side="right")) - 1


def quote(bk: Book, t: int):
    """t 직전(수신 ≤ t) bookticker와 depth — 둘 다 1초 안이고 원천끼리 교차하지 않을 때만."""
    i, j = _last(bk.bt_recv, t), _last(bk.dp_recv, t)
    if i < 0 or j < 0 or t - bk.bt_recv[i] > FRESH_MS or t - bk.dp_recv[j] > FRESH_MS:
        return None
    bid, bq, ask, aq = bk.bt[i]
    d = bk.dp[j]
    bp1, ap1 = d[0], d[2 * LEVELS]
    if not (bid < ask and bp1 < ask and ap1 > bid):
        return None
    return bk.bt[i], d


def x_price(bk: Book, t: int, buy: bool) -> float | None:
    """실행 가능 테이커 가격 X(t, 방향) — 표시 수량이 모자라면 depth 반대쪽을 먹은 평균가 · 20단계로도 모자라면 None."""
    q = quote(bk, t)
    if q is None:
        return None
    (bid, bq, ask, aq), d = q
    top, topq = (ask, aq) if buy else (bid, bq)
    if topq >= QTY - EPS:
        return float(top)
    off = 2 * LEVELS if buy else 0
    need, cost = QTY, 0.0
    for k in range(LEVELS):
        px, qq = d[off + 2 * k], d[off + 2 * k + 1]
        take = min(need, qq)
        cost += take * px
        need -= take
        if need <= EPS:
            return cost / QTY
    return None


def continuity_ok(bk: Book, a: int, b: int) -> str | None:
    """적격 창의 연속성(§4-1 1 · 2 · 7) — 문제가 있으면 사유, 없으면 None."""
    if a < bk.lo_ms or b > bk.hi_ms:
        return "span"
    if any(s < b and e > a for s, e in bk.bad):
        return "gap_or_skew"
    for recv, lim, name in ((bk.dp_recv, DP_GAP_MS, "depth_gap"), (bk.bt_recv, BT_GAP_MS, "bookticker_gap")):
        i0, i1 = _last(recv, a), int(np.searchsorted(recv, b, side="right"))
        if i0 < 0:                                                               # 창 앞에 자료가 없다
            return name
        seg = np.concatenate((recv[i0:i1], [b]))                                 # a를 덮는 마지막 값부터 b까지
        if np.max(np.diff(seg)) > lim:
            return name
    lo, hi = np.searchsorted(bk.ag_recv, a, side="left"), np.searchsorted(bk.ag_recv, b, side="right")
    ids = bk.ag_id[lo:hi]
    if len(ids):
        u, first = np.unique(ids, return_index=True)
        if len(u) != len(ids):                                                  # 중복 id — 내용이 같아야 한다
            for k in u[np.bincount(np.searchsorted(u, ids)) > 1]:
                m = np.nonzero(ids == k)[0] + lo
                cols = (bk.ag_tick[m], bk.ag_qty[m], bk.ag_tt[m], bk.ag_bm[m])
                if any(len(set(np.asarray(c).tolist())) > 1 for c in cols):
                    return "dup_conflict"
        if int(u[-1]) - int(u[0]) + 1 != len(u):
            return "aggtrade_id_gap"
    return None


def _dedup(idx: np.ndarray, bk: Book) -> np.ndarray:
    """같은 agg_trade_id는 수신이 가장 이른 하나만(배열은 수신 순이므로 첫 등장)."""
    _, first = np.unique(bk.ag_id[idx], return_index=True)
    return idx[np.sort(first)]


@dataclass
class Tape:
    """체결 테이프(주 장부 = 그날 그대로 · 대조 ② = 기증 날을 옮긴 것)."""
    recv: np.ndarray
    tick: np.ndarray
    qty: np.ndarray
    tt: np.ndarray
    bm: np.ndarray
    order: np.ndarray                 # (transact_time, id) 정렬 순서용 id


def tape_of(bk: Book, a: int, b: int, *, shift_ms: int = 0, tick_shift: int = 0) -> Tape:
    lo, hi = np.searchsorted(bk.ag_recv, a, side="left"), np.searchsorted(bk.ag_recv, b, side="right")
    idx = _dedup(np.arange(lo, hi), bk)
    return Tape(bk.ag_recv[idx] - shift_ms, bk.ag_tick[idx] + tick_shift, bk.ag_qty[idx], bk.ag_tt[idx] - shift_ms, bk.ag_bm[idx],
                bk.ag_id[idx])


def filled(tape: Tape, *, buy: bool, p_tick: int, q_ahead: float, t_place: int, b_ms: int, t_ms: int, late: bool = False) -> bool:
    """같은 가격 p의 우리 쪽 공격 체결(BUY 주문 ← 매도 공격 = is_buyer_maker)만 · tt > t_place + B · 수신 ≤ t_place + T.
    late=True: 늦은 체결 충돌 진단(tt ≤ t_place + T + B · 수신 ≤ t_place + T + 5초)."""
    side = tape.bm if buy else ~tape.bm
    m = side & (tape.tick == p_tick) & (tape.tt > t_place + b_ms)
    if late:
        m &= (tape.tt <= t_place + t_ms + b_ms) & (tape.recv <= t_place + t_ms + LATE_RECV_MS)
    else:
        m &= tape.recv <= t_place + t_ms
    if not m.any():
        return False
    o = np.lexsort((tape.order[m], tape.tt[m]))
    return bool(np.cumsum(tape.qty[m][o])[-1] >= q_ahead + QTY - EPS)


@dataclass
class Placed:
    """결정 하나의 책 쪽 상태(대조 ②가 다른 날 테이프와 짝지을 때 그대로 쓴다)."""
    t0: int
    buy: bool
    mid0: float
    b0: float
    t_place: int
    p: float
    p_tick: int
    q_ahead: float
    reject: bool
    x_reject: float | None
    x_fallback: dict[int, float]
    imbalance: float


def place(bk: Book, t0: int, buy: bool) -> Placed | str:
    """§4-1 적격 · §4-2 배치 — 부적격이면 사유 문자열."""
    a, b = t0 - PRE_MS, t0 + DELTA_MS + POST_MS
    why = continuity_ok(bk, a, b)
    if why:
        return why
    q0 = quote(bk, t0)
    if q0 is None:
        return "baseline_quote"
    (bid0, bq0, ask0, aq0), _ = q0
    mid0 = (bid0 + ask0) / 2
    if QTY * mid0 < MIN_NOTIONAL:
        return "min_notional"
    b0 = x_price(bk, t0, buy)
    if b0 is None:
        return "baseline_depth"
    tp = t0 + DELTA_MS
    qp = quote(bk, tp)
    if qp is None:
        return "placement_quote"
    (bid, bq, ask, aq), d = qp
    p = float(bid if buy else ask)
    reject = bool(ask <= p) if buy else bool(bid >= p)
    x_rej = x_price(bk, tp, buy) if reject else None
    if reject and x_rej is None:
        return "reject_depth"
    off = 0 if buy else 2 * LEVELS
    lv = [k for k in range(LEVELS) if ticks(d[off + 2 * k]) == ticks(p)]
    q_ahead = float(d[off + 2 * lv[0] + 1]) if lv else float(bq if buy else aq)
    xf = {}
    for t_ms in TS:
        x = x_price(bk, tp + t_ms, buy)
        if x is None:
            return "fallback_quote"
        xf[t_ms] = x
    imb = (bq0 - aq0) / (bq0 + aq0) if bq0 + aq0 > 0 else 0.0
    return Placed(t0, buy, float(mid0), float(b0), tp, p, int(ticks(p)), q_ahead, reject, x_rej, xf, float(imb if buy else -imb))


def improvement(pl: Placed, exec_px: float, maker: bool, fees: str = "primary") -> float:
    fm, ft = FEES[fees]
    f = fm if maker else ft
    if pl.buy:
        return (pl.b0 * (1 + ft) - exec_px * (1 + f)) / pl.mid0 * 1e4
    return (exec_px * (1 - f) - pl.b0 * (1 - ft)) / pl.mid0 * 1e4


def outcome(pl: Placed, tape: Tape, b_ms: int, t_ms: int) -> tuple[str, float, bool]:
    """(경로, 실행가, 메이커 여부) — 경로 = reject | maker | timeout."""
    if pl.reject:
        assert pl.x_reject is not None
        return "reject", pl.x_reject, False
    if filled(tape, buy=pl.buy, p_tick=pl.p_tick, q_ahead=pl.q_ahead, t_place=pl.t_place, b_ms=b_ms, t_ms=t_ms):
        return "maker", pl.p, True
    return "timeout", pl.x_fallback[t_ms], False


def late_conflict(pl: Placed, tape: Tape, b_ms: int, t_ms: int) -> bool:
    return filled(tape, buy=pl.buy, p_tick=pl.p_tick, q_ahead=pl.q_ahead, t_place=pl.t_place, b_ms=b_ms, t_ms=t_ms, late=True)


def b_bound(recv: np.ndarray, tt: np.ndarray, pooled: tuple[np.ndarray, np.ndarray] | None = None) -> int:
    """B_d = 2 × max(0, p99.9(recv − transact)) · 체결 10,000개 미만이면 합친 값(§4-3)."""
    if len(recv) < 10_000 and pooled is not None:
        recv, tt = pooled
    if len(recv) == 0:
        return 10**9
    return int(np.ceil(2 * max(0.0, float(np.quantile(recv - tt, 0.999)))))
