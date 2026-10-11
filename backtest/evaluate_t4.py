"""트라이얼 #4 판정기 계산((f) · 규약 E59~E68 · 사전등록 r3 §3 · §3-1 · §4 · §7 · §7-3).

**복사**: `backtest/evaluate_t3.py` @ 75c3b6a에서 — 바꾼 것: 앵커 = trial04(N = 8 · 스트림 S 먼저) · V = 완전한 날 ∧ 그날 00:00 경계 앞의 유효
인쇄 ≥ 270(인쇄 입력에서 재계산) · `t4` 결정 기록 키 · **펀딩 독립 재계산**(펀딩 입력) · P1 슬롯 ↔ 원판 대조 · P1-timing은 보고 블록으로만 ·
보고 필드(r3 §7-3) · `evaluate()` = (g) 전반에서 동결·행·핀 관문과 연결.

- 입력 계약 = `backtest.t4_outputs`(빠짐·남음·스키마 불일치 → 거부) + 준비 입력(봉 · 펀딩 · 인쇄 · kline 일 종가 — (g) CLI가 고정 로더로 준다).
- 트레이드마다 원장 항등식(E63): 지갑·수수료·펀딩·체결은 **34자리**(엔진 실행 문맥)에서 엔진 기록값과 정확히 같아야 하고, gross/net
  문자열은 `returns.trade_return`을 **기본 28자리 문맥**에서 다시 불러 정확히 같아야 한다 · 비용 격자 ×1.0 = 기록된 net · 불일치 → 거부.
- gross(E59 [PROPOSED]) = 가격만(펀딩 전) — 공유 정의 그대로 · `gross_incl_funding_bps`는 보고 전용.
- 판정: `verdict_t4.verdict_is`(두 암 함께 · G-B SR* 공유) · **timing 블록은 판정 입력을 만든 뒤에만 읽는다**(E65).
- 한 번만(E67 · F78): `evaluation/`이나 시도 기록이 있으면 거부 · 모든 실패 = 거부(아무것도 쓰지 않음) · 결과는 임시 디렉터리 → 이름 바꾸기 ·
  실행 경로 `evaluate()`는 단계 관문(동결·행·핀·영수증·기록)을 모두 통과한 뒤에만 계산한다.
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import inspect
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import numpy as np

from backtest import p1_core as C
from backtest import p1_t4 as P1
from backtest import stats as ST
from backtest import stats_t2 as S2
from backtest import t4_outputs as O
from backtest import verdict_t4 as V
from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.returns import trade_return
from exchange.orders import Direction
from strategies.trial04 import anchor as A
from strategies.trial04.config import TC_V3, TcParams
from strategies.trial04.eligibility import complete_days
from strategies.trial04.exit_schedule import HOLD_MIN

ROOT = Path(__file__).resolve().parent.parent
DAY = A.DAY_MS
BPS = Decimal(10_000)


class Refusal(RuntimeError):
    """판정 거부 — 판정 없음 · 아무것도 쓰지 않는다."""


# ── 수치 ────────────────────────────────────────────────────────────────────
def _f(x: Any) -> float:
    try:
        d = Decimal(str(x))
    except (decimal.InvalidOperation, ValueError) as e:
        raise Refusal(f"수치 해석 불가: {x!r}") from e
    if not d.is_finite():
        raise Refusal(f"유한하지 않은 값: {x!r}")
    f = float(d)
    if not math.isfinite(f):
        raise Refusal(f"float64 범위 밖: {x!r}")
    return f


def _fin(v: float, what: str) -> float:
    if not math.isfinite(v):
        raise Refusal(f"집계값이 유한하지 않다({what}): {v}")
    return v


def _rng(k: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(A.BOOTSTRAP_SEED).spawn(A.BOOTSTRAP_SPAWN)[k]))


# ── V 재계산(E62 · 인쇄 입력만) ──────────────────────────────────────────────
def recompute_v(bars: Sequence[Bar1m], prints: Sequence[dict[str, Any]], window: tuple[int, int],
                p: TcParams) -> tuple[set[int], dict[int, bool]]:
    """V = 완전한 mark 날 ∧ 그날 00:00 경계에서 후행 분포 정의(T < 그 경계인 유효 인쇄 ≥ 270).
    정의역 = 전략이 분류한 00:00 경계(결정 시각 ≥ 창 시작 ∧ T ≤ 창 끝 ∧ T ≤ 마지막 봉)."""
    last = bars[-1].open_ms if bars else -1
    valid_before = 0
    dd: dict[int, bool] = {}
    for pr in sorted(prints, key=lambda x: x["T"]):
        t = int(pr["T"])
        if t % DAY == 0 and window[0] <= t + MINUTE_MS and t <= window[1] and t <= last:
            dd[t // DAY] = valid_before >= p.n_trail
        if pr["valid"]:
            valid_before += 1
    full = complete_days(bars)
    return {d for d, ok in dd.items() if ok and d in full}, dd


# ── 트레이드 원장 항등식(E63) ───────────────────────────────────────────────
def _funding_by_bucket(fundings: Sequence[Funding]) -> dict[int, list[Funding]]:
    out: dict[int, list[Funding]] = defaultdict(list)
    for f in sorted(fundings, key=lambda f: f.funding_ms):
        out[f.funding_ms - f.funding_ms % MINUTE_MS].append(f)
    return out


def ledger_check(trades: Sequence[dict[str, Any]], events: Sequence[dict[str, Any]], fundings: Sequence[Funding], liq_fee: Decimal,
                 e_ref: Decimal) -> list[dict[str, Any]]:
    filled = [e for e in events if e["kind"] == "filled"]
    exits = [e for e in events if e["kind"] == "exit"]
    if not (len(filled) == len(exits) == len(trades)):
        raise Refusal(f"체결·청산 기록 {len(filled)}/{len(exits)} ≠ 트레이드 {len(trades)}")
    fund = _funding_by_bucket(fundings)
    buckets = sorted(fund)
    out = []
    for k, (t, fi, ex) in enumerate(zip(trades, filled, exits, strict=True)):
        i4 = t["t4"]
        if int(t["trade_id"]) != k or int(t["entry_ms"]) != int(fi["fill_open"]) or int(t["exit_ms"]) != int(ex["ts_ms"]) \
                or t["entry_mark"] != fi["entry_ref"] or int(t["leverage"]) != int(fi["leverage"]) or t["exit_reason"] != ex["reason"] \
                or t["direction"] != i4["intent_dir"] or int(t["entry_ms"]) != int(i4["decided_ms"]) + 1 \
                or int(t["entry_ms"]) != int(i4["fill_open"]) or Decimal(t["sl"]) != Decimal(i4["intent_sl"]):
            raise Refusal(f"트레이드 {t.get('trade_id')}: 시각·기준가·레버리지·사유·방향·SL이 엔진·결정 기록과 다르다")
        d = Direction(t["direction"])
        sign = Decimal(1) if d is Direction.LONG else Decimal(-1)
        qty, fill_in, w0, w1 = Decimal(t["qty"]), Decimal(t["entry_fill"]), Decimal(t["wallet_before"]), Decimal(t["wallet_after"])
        if w0 != e_ref:
            raise Refusal(f"트레이드 {t['trade_id']}: wallet_before {w0} ≠ E_ref {e_ref}(L5)")
        if Decimal(fi["qty"]) != qty or Decimal(fi["fill"]) != fill_in or Decimal(ex["wallet_after"]) != w1:
            raise Refusal(f"트레이드 {t['trade_id']}: 체결·청산 기록이 트레이드와 다르다")
        comm_in, comm_out = Decimal(fi["entry_commission"]), Decimal(ex["exit_commission"])
        funding, ref_in = Decimal(ex["funding_paid"]), Decimal(fi["entry_ref"])
        entry_ms, exit_minute = int(t["entry_ms"]), int(ex["ts_ms"]) - int(ex["ts_ms"]) % MINUTE_MS
        counts = {"received": 0, "paid": 0, "zero": 0}
        price_pnl: Decimal | None = None
        with localcontext() as c:
            c.prec = 34
            #  펀딩 독립 재계산: 정산 버킷 ∈ (entry_ms, 청산 분] · 엔진과 같은 식(signed_qty × mark × rate)·같은 누적 순서
            paid_sum = Decimal(0)
            for b in buckets:
                if entry_ms < b <= exit_minute:
                    for f in fund[b]:
                        paid = sign * qty * Decimal(f.mark) * Decimal(f.rate)
                        paid_sum += paid
                        counts["received" if paid < 0 else "paid" if paid > 0 else "zero"] += 1
            if paid_sum != funding:
                raise Refusal(f"트레이드 {t['trade_id']}: 펀딩 재계산 {paid_sum} ≠ 기록 {funding}")
            if t["exit_reason"] == "liquidation":
                loss = qty * fill_in / Decimal(int(t["leverage"])) - comm_in - funding + qty * Decimal(t["exit_ref"]) * liq_fee
                ok = Decimal(ex["realized_pnl"]) == -loss and w1 == e_ref - comm_in - funding - loss
                slip_in = sign * (fill_in - ref_in) * qty
                cost = comm_in + slip_in
            else:
                fills = [(Decimal(p), Decimal(q)) for p, q, _, _ in ex["exit_fills"]]
                q_out = sum((q for _, q in fills), Decimal(0))
                px = sum((p * q for p, q in fills), Decimal(0)) / q_out
                pnl = (px - fill_in) * q_out if d is Direction.LONG else (fill_in - px) * q_out
                refs = {r for _, _, _, r in ex["exit_fills"]}
                if len(refs) != 1 or Decimal(ex["exit_price"]) != px or Decimal(ex["realized_pnl"]) != pnl or q_out != qty:
                    raise Refusal(f"트레이드 {t['trade_id']}: 청산 체결 기록 불일치")
                ok = w1 == e_ref - comm_in - funding + pnl - comm_out
                ref_out = Decimal(refs.pop())
                if ref_out != Decimal(t["exit_ref"]):
                    raise Refusal(f"트레이드 {t['trade_id']}: exit_ref 불일치")
                slip_in = sign * (fill_in - ref_in) * qty
                slip_out = sign * (ref_out - px) * qty
                cost = comm_in + comm_out + slip_in + slip_out
                price_pnl = pnl
            if not ok:
                raise Refusal(f"트레이드 {t['trade_id']}: 지갑 항등식 불일치")
            notional = qty * fill_in
            cost_bps = cost / notional * BPS
            funding_bps = -funding / notional * BPS
        r = trade_return(direction=d, entry_mark=Decimal(t["entry_mark"]), exit_ref=Decimal(t["exit_ref"]), qty=qty,
                         entry_fill=fill_in, wallet_before=w0, wallet_after=w1)          # 기본 28자리 문맥(재생과 같은 연산 순서)
        if str(r.gross_bps) != t["gross_bps"] or str(r.net_bps) != t["net_bps"]:
            raise Refusal(f"트레이드 {t['trade_id']}: gross/net 문자열 재계산 불일치")
        net = Decimal(t["net_bps"])
        grid = {str(k): net + (1 - Decimal(k)) * cost_bps for k in ("0.5", "1.0", "1.5")}
        if grid["1.0"] != net:
            raise Refusal(f"트레이드 {t['trade_id']}: 비용 격자 ×1.0 ≠ 기록 net")
        if slip_in < 0:
            raise Refusal(f"트레이드 {t['trade_id']}: 진입 슬리피지가 유리하다({slip_in})")
        out.append({"trade_id": t["trade_id"], "cost_bps": cost_bps, "grid": grid, "funding": funding, "funding_bps": funding_bps,
                    "price_pnl": price_pnl, "notional": notional, "settlements": counts,
                    "gross_incl_funding_bps": Decimal(t["gross_bps"]) + funding_bps})
    return out


# ── 암 통계 ─────────────────────────────────────────────────────────────────
def _by_day(trades: Sequence[dict[str, Any]], field: str) -> dict[int, list[float]]:
    out: dict[int, list[float]] = defaultdict(list)
    for t in trades:
        out[int(t["entry_ms"]) // DAY].append(_f(t[field]))
    return out


def psr0(x: Sequence[float]) -> float | None:
    if S2.sharpe_or_none(x) is None:
        return None
    v = ST.psr(list(x), 0.0)
    return v if math.isfinite(v) else None


def arm_stats(trades: Sequence[dict[str, Any]], days: Sequence[int], k_gross: int, k_net: int) -> dict[str, Any]:
    net = [_f(t["net_bps"]) for t in trades]
    g = S2.valid_day_bootstrap_mean(_by_day(trades, "gross_bps"), days, _rng(k_gross), resamples=A.BOOTSTRAP_RESAMPLES, level=A.LEVEL)
    n_ = S2.valid_day_bootstrap_mean(_by_day(trades, "net_bps"), days, _rng(k_net), resamples=A.BOOTSTRAP_RESAMPLES, level=A.LEVEL)
    sd = float(np.std(net, ddof=1)) if len(net) >= 2 else None
    return {"n": len(net), "rho": S2.lag1_rho(net), "mean_gross": g.mean if net else float("nan"),
            "gross_ci": [g.lo, g.hi] if g.defined else None, "mean_net": n_.mean if net else float("nan"),
            "net_ci": [n_.lo, n_.hi] if n_.defined else None, "sd_net": sd if sd and sd > 0 else None,
            "sr": S2.sharpe_or_none(net), "psr0": psr0(net), "degenerate_resamples": [g.degenerate, n_.degenerate],
            "liquidations": sum(1 for t in trades if t["exit_reason"] == "liquidation")}


def mean_net(trades: Sequence[dict[str, Any]]) -> float:
    """변형 실행의 평균 net — 트레이드 0건이면 0.0(E60)."""
    return _fin(float(np.mean([_f(t["net_bps"]) for t in trades])), "mean_net") if trades else 0.0


def trade_report(trades: Sequence[dict[str, Any]], ledger: Sequence[dict[str, Any]]) -> dict[str, Any]:
    hold = [(int(t["exit_ms"]) - int(t["entry_ms"])) / 60_000 for t in trades]
    years: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        years[str(dt.datetime.fromtimestamp(int(t["entry_ms"]) / 1000, dt.UTC).year)].append(_f(t["net_bps"]))
    x9 = sum(1 for t in trades if t["exit_reason"] == "time_exit"
             and ((Decimal(t["exit_ref"]) <= Decimal(t["sl"])) if t["direction"] == "LONG" else (Decimal(t["exit_ref"]) >= Decimal(t["sl"]))))
    p_sign = {"positive": 0, "negative": 0, "zero": 0}
    for t in trades:
        p = _f(t["t4"]["p"])
        p_sign["positive" if p > 0 else "negative" if p < 0 else "zero"] += 1
    settle: Counter[str] = Counter({"received": 0, "paid": 0, "zero": 0})
    for lg in ledger:
        settle.update(lg["settlements"])
    z = Decimal(0)
    timed = [lg for lg in ledger if lg["price_pnl"] is not None]
    fbps = [float(lg["funding_bps"]) for lg in ledger]
    grid = {k: float(np.mean([float(lg["grid"][k]) for lg in ledger])) if ledger else None for k in ("0.5", "1.0", "1.5")}
    return {"holding_min_quantiles": [float(q) for q in np.quantile(hold, [0.1, 0.25, 0.5, 0.75, 0.9])] if hold else None,
            "exit_reasons": {r: {"n": c, "share": c / len(trades)} for r, c in sorted(Counter(t["exit_reason"] for t in trades).items())},
            "n_trades": len(trades),
            "leverage_distribution": {str(k): v for k, v in sorted(Counter(int(t["leverage"]) for t in trades).items())},
            "p_sign_at_entry": p_sign,
            "funding_settlements": dict(settle),
            "price_vs_funding": {
                "price_pnl_usdt": str(sum((lg["price_pnl"] for lg in timed), z)),            # 시간 청산·SL 트레이드(체결가 기준)
                "funding_cf_usdt": str(sum((-lg["funding"] for lg in ledger), z)),            # = −Σ 지불(전 트레이드)
                "funding_cf_bps_of_notional_mean": float(np.mean(fbps)) if fbps else None,
                "mean_gross_incl_funding_bps": float(np.mean([float(lg["gross_incl_funding_bps"]) for lg in ledger])) if ledger else None,
                "liquidated_trades": len(ledger) - len(timed)},
            "per_year": {y: {"n": len(v), "mean_net_bps": float(np.mean(v))} for y, v in sorted(years.items())},
            "x9_time_exit_open_past_sl": x9,
            "cost_grid_mean_net_bps": grid}


def bh_series(daily: Sequence[dict[str, Any]], first_day: int, last_day: int) -> dict[str, Any]:
    rows = sorted((r for r in daily if first_day <= int(r["day"]) <= last_day), key=lambda r: int(r["day"]))
    c = [_f(r["close"]) for r in rows]
    rets = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
    return {"days": len(rows), "daily_sharpe": S2.sharpe_or_none(rets), "window_return": (c[-1] / c[0] - 1) if len(c) >= 2 else None}


def _bh_beats(arm_sharpe: float | None, bh_sharpe: float | None) -> bool | None:
    """`verdict_forward`의 사전확약 입력(암 일간 Sharpe < 매수보유 일간 Sharpe · 엄격) — 정의 안 되면 None(비교 불가)."""
    return None if arm_sharpe is None or bh_sharpe is None else arm_sharpe < bh_sharpe


def arm_daily_sharpe(trades: Sequence[dict[str, Any]], v: Sequence[int], n_stat: Decimal) -> float | None:
    day: dict[int, Decimal] = defaultdict(Decimal)
    for t in trades:
        day[int(t["entry_ms"]) // DAY] += n_stat * Decimal(t["net_bps"]) / BPS
    return S2.sharpe_or_none([float(day.get(d, Decimal(0))) / float(n_stat) for d in v])


# ── P1 대조(E64) ────────────────────────────────────────────────────────────
def _check_slots(arm: str, what: str, draws: Sequence[dict[str, Any]], src: Sequence[C.SourceTrade], direction: int | None) -> None:
    for dr in draws:
        for slot, pair, d, h, sl_dist, _entry in dr["placed"]:
            if h != HOLD_MIN or not 0 <= pair < len(src) or sl_dist != str(src[pair].sl_dist) or (direction is not None and d != direction):
                raise Refusal(f"{arm} P1 {what} 추출 {dr['draw']} 슬롯 {slot}: h·sl_dist·방향이 기본 실행의 원판과 다르다")


def _null_block(null: Sequence[dict[str, Any]], failed: int) -> dict[str, Any]:
    means = [_f(r["mean_net_bps"]) for r in null]
    liq = sum(1 for r in null if r["exits"]["liquidation"] > 0)
    return {"failed": failed, "successful": len(means), "p95": _fin(S2.p95(means), "P1 p95") if means else None,
            "exits": dict(sorted(sum((Counter(r["exits"]) for r in null), Counter()).items())),
            "liquidated_draw_ratio": liq / len(null) if null else None}


# ── 계산(순수 · 파일 읽기만) ─────────────────────────────────────────────────
def _compute(base: Path, bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]],
             kline_daily: Sequence[dict[str, Any]], *, p: TcParams, window: tuple[int, int], liq_fee: Decimal,
             p1_draws: int) -> tuple[dict[str, V.Verdict], dict[str, Any]]:
    O.check_run_inventory(base)
    v_set, dist_defined = recompute_v(bars, prints, window, p)
    v = sorted(v_set)
    runs = {(a, var): O.read_run(O.run_dir(base, a, var), a, var) for a in O.ARMS for var in O.VARIANTS}
    for (a, var), (trades, _, summ) in runs.items():
        if summ["v_days"] != v or {int(k): b for k, b in summ["dist_defined"].items()} != dist_defined:
            raise Refusal(f"{a}_{var}: 실행이 기록한 V·분포 정의 날이 판정기 재계산과 다르다")
        if summ["tc_v3_sha256"] != A.TC_V3_SHA256:
            raise Refusal(f"{a}_{var}: tc_v3 SHA256 불일치")
        if summ["rules_sha256"] != A.RULES_SNAPSHOT_SHA256:
            raise Refusal(f"{a}_{var}: 규칙 스냅샷 SHA256이 #69와 다르다")
        if summ["window_prints"] != sum(summ["funnel"].values()):
            raise Refusal(f"{a}_{var}: 인쇄 깔때기 합 ≠ window_prints")
        if any(int(t["entry_ms"]) // DAY not in v_set for t in trades):
            raise Refusal(f"{a}_{var}: 진입일이 V 밖인 트레이드(§3-1)")
    streams = A.BOOTSTRAP_STREAMS["IS"]
    stats, ledgers, p1s, inputs, merged = {}, {}, {}, {}, {}
    for a in O.ARMS:
        trades, events, summ = runs[(a, "base")]
        ledgers[a] = ledger_check(trades, events, fundings, liq_fee, p.e_ref)
        for var in O.VARIANTS[1:]:
            ledger_check(runs[(a, var)][0], runs[(a, var)][1], fundings, liq_fee, p.e_ref)
        stats[a] = arm_stats(trades, v, streams[f"gross_{a}"], streams[f"net_{a}"])
        parts = O.read_p1_parts(base, a)
        mf = O.read_p1_merged(base, a)
        psum = mf["summary"]
        manifest = [{"lo": q.lo, "hi": q.hi, "sha256": O.sha(O.p1_parts_dir(base, a) / f"part_{q.lo:03d}_{q.hi:03d}" / O.P1_PART_FILE)}
                    for q in sorted(parts, key=lambda q: q.lo)]
        if psum["parts"] != manifest:
            raise Refusal(f"{a}: P1 조각 목록·해시가 p1_summary와 다르다")
        m = P1.merge(parts, p1_draws)
        n_el, n_ok = O.eligible_counts(parts)
        if m["draws"] != mf["draws"] or m["null"] != mf["null"] or m["timing"]["draws"] != mf["timing_draws"] \
                or m["timing"]["null"] != mf["timing_null"] \
                or {k: psum[k] for k in ("n_source", "computable", "failed", "evaluable")} != \
                {k: m[k] for k in ("n_source", "computable", "failed", "evaluable")} \
                or psum["timing_failed"] != m["timing"]["failed"] or (psum["n_eligible"], psum["n_eligible_atr_prev_close_ok"]) != (n_el, n_ok):
            raise Refusal(f"{a}: P1 병합 파일이 조각에서 다시 병합한 결과와 다르다")
        if m["n_source"] != len(trades) or m["computable"] != (len(trades) > 0):
            raise Refusal(f"{a}: P1 원판 수·계산 가능 여부가 기본 실행과 모순")
        src = C.sort_source(P1.source_trades(trades))
        _check_slots(a, "게이트", m["draws"], src, None)
        _check_slots(a, "timing", m["timing"]["draws"], src, P1.ARM_DIRECTION[a])
        gate = _null_block(m["null"], m["failed"])
        p1s[a] = {"computable": m["computable"], **gate, "n_eligible": n_el, "n_eligible_atr_prev_close_ok": n_ok}
        merged[a] = m
        s = stats[a]
        inputs[a] = V.ArmInputs(
            v_empty=not v, n=s["n"], liquidations=s["liquidations"], rho=s["rho"], mean_gross=s["mean_gross"],
            gross_ci_lo=s["gross_ci"][0] if s["gross_ci"] else None, mean_net=s["mean_net"],
            net_ci_lo=s["net_ci"][0] if s["net_ci"] else None, net_ci_hi=s["net_ci"][1] if s["net_ci"] else None,
            sd_net=s["sd_net"], sr=s["sr"], psr0=s["psr0"], p1_computable=m["computable"], p1_failures=m["failed"],
            p1_p95=gate["p95"], p2_p1=mean_net(runs[(a, "P2_print1")][0]), p2_p3=mean_net(runs[(a, "P2_print3")][0]),
            p3_inv=mean_net(runs[(a, "P3_invert")][0]))
    verdicts = V.verdict_is(inputs)
    #  ── 여기부터 보고(판정 아님) — timing 블록은 여기서만 읽는다(E65) ──
    first, last = window[0] // DAY, (window[1] + 1 - MINUTE_MS) // DAY
    bh = bh_series(kline_daily, first, last)
    report: dict[str, Any] = {
        "trial_verdict": V.trial_string(verdicts),
        "arms": {}, "v_days": len(v), "buy_and_hold": bh,
        "v_cross_check": {"runs_compared": len(runs), "match": True},
        "constants": {"n_trials": A.N_TRIALS, "alpha": A.ALPHA, "ci_quantiles": [A.CI_LO_Q, A.CI_HI_Q],
                      "bootstrap_resamples": A.BOOTSTRAP_RESAMPLES, "bootstrap_seed": list(A.BOOTSTRAP_SEED),
                      "bootstrap_streams": dict(streams)},
    }
    for a in O.ARMS:
        vd = verdicts[a]
        trades, events, summ = runs[(a, "base")]
        sharpe = arm_daily_sharpe(trades, v, p.n_stat)
        report["arms"][a] = {
            "verdict": vd.string, "survival": f"청산 {stats[a]['liquidations']} / 체결 {stats[a]['n']}", "priority": vd.priority,
            "classification": vd.classification, "gates": vd.gates, "placebo_rejects": vd.placebo_rejects, "sr_star": vd.sr_star,
            "sr_undefined": vd.sr_undefined, "mde": vd.mde, "stats": stats[a], "inputs": inputs[a].__dict__, "P1": p1s[a],
            "P1_timing": _null_block(merged[a]["timing"]["null"], merged[a]["timing"]["failed"]),
            "P2": {"print1": inputs[a].p2_p1, "print3": inputs[a].p2_p3}, "P3_invert": inputs[a].p3_inv,
            "print_funnel": summ["funnel"], "entry_funnel": summ["entry"], "sub_reasons": summ["sub"],
            "window_prints": summ["window_prints"],
            "trades": trade_report(trades, ledgers[a]),
            "daily_sharpe": sharpe, "bh_beats_arm": _bh_beats(sharpe, bh["daily_sharpe"]),
            "variants": {var: {"n": runs[(a, var)][2]["n_trades"], "mean_net_bps": mean_net(runs[(a, var)][0])} for var in O.VARIANTS}}
    return verdicts, report


def compute(base: Path, bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]],
            kline_daily: Sequence[dict[str, Any]], liq_fee: Decimal) -> tuple[dict[str, V.Verdict], dict[str, Any]]:
    """실행 경로 — TC_V3 · 창 WINDOW_START … IS_END · P1 추출 1,000. 덮어쓸 인자가 없다."""
    return _compute(base, bars, fundings, prints, kline_daily, p=TC_V3, window=(A.WINDOW_START_MS, A.IS_END_MS), liq_fee=liq_fee,
                    p1_draws=A.P1_DRAWS)


def _require_test_caller(depth: int = 2) -> None:
    caller = Path(inspect.stack()[depth].filename).resolve()
    if (ROOT / "tests") not in caller.parents:
        raise Refusal(f"픽스처 경로는 tests/ 전용이다(호출자 {caller})")


def compute_with_fixture(base: Path, bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]],
                         kline_daily: Sequence[dict[str, Any]], liq_fee: Decimal, *, p: TcParams, window: tuple[int, int],
                         p1_draws: int) -> tuple[dict[str, V.Verdict], dict[str, Any]]:
    """**테스트 전용** — 호출자 파일이 tests/ 아래가 아니면 거부."""
    _require_test_caller()
    return _compute(base, bars, fundings, prints, kline_daily, p=p, window=window, liq_fee=liq_fee, p1_draws=p1_draws)


# ── 한 번만 · 쓰기(E67 · 관문 연결은 (g)) ───────────────────────────────────
def _finite_json(o: Any) -> Any:
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _finite_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite_json(v) for v in o]
    if isinstance(o, Decimal):
        return str(o)
    return o


def report_bytes(report: dict[str, Any]) -> bytes:
    return (json.dumps(_finite_json(report), sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


ATTEMPT = "evaluation_attempt.json"


def _input_hashes(base: Path) -> dict[str, str]:
    """판정 입력 해시(준비 원시는 매니페스트가 덮으므로 제외 · 판정 결과·시도 기록 제외)."""
    out = {}
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if not p.is_file() or rel.parts[0] == "evaluation" or rel.parts[0].startswith("evaluation_") \
                or (len(rel.parts) > 1 and rel.parts[:2] == ("prepared", "raw")) or rel.name == ATTEMPT:
            continue
        out[str(rel)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _claim_attempt(base: Path, commit: str) -> None:
    """시도 기록을 배타적으로 만든다(O_CREAT|O_EXCL · fsync) — 두 판정기가 함께 통과할 수 없다."""
    import os
    rec = base / "_records"
    rec.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(rec / ATTEMPT, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as e:
        raise Refusal("판정 시도 기록이 이미 있다 — 중단된 시도(레지스트리 행·검토·재동결 절차)") from e
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"evaluator_commit": commit, "started": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}) + "\n")
        f.flush()
        os.fsync(f.fileno())
    dfd = os.open(rec, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _run_once(base: Path, commit: str, before: dict[str, str], fn: Callable[[], tuple[dict[str, V.Verdict], dict[str, Any]]],
              extra: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    _claim_attempt(base, commit)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            _, report = fn()
    except Refusal:
        raise
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, FloatingPointError, O.ContractError, P1.P1Error, RuntimeError) as e:
        raise Refusal(f"{type(e).__name__}: {e}") from e
    if _input_hashes(base) != before:
        raise Refusal("판정 중 입력 파일이 바뀌었다")
    tmp = Path(tempfile.mkdtemp(prefix="evaluation_", dir=base))
    try:
        rb = report_bytes(report)
        (tmp / "report.json").write_bytes(rb)
        (tmp / "verdict.txt").write_text(report["trial_verdict"] + "\n")
        record = {"evaluator_commit": commit, "inputs_sha256": before, **extra,
                  "report_sha256": hashlib.sha256(rb).hexdigest(),
                  "verdict_sha256": hashlib.sha256((tmp / "verdict.txt").read_bytes()).hexdigest()}
        (tmp / "record.json").write_text(json.dumps(record, sort_keys=True, indent=1, default=str) + "\n")
        tmp.rename(base / "evaluation")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return report["trial_verdict"], record


def _preconditions(base: Path) -> None:
    decimal.setcontext(decimal.Context())
    if (base / "evaluation").exists():
        raise Refusal("판정은 한 번만 — evaluation/이 이미 있다")
    if (base / "_records" / ATTEMPT).exists():
        raise Refusal("판정 시도 기록이 이미 있다 — 중단된 시도(레지스트리 행·검토·재동결 절차)")


def evaluate(base: Path, repo: Path, *, evaluator_commit: str, fetch: bool = True) -> tuple[str, dict[str, Any]]:
    """한 번만(실행 경로 · F78). 데이터 인자가 없다 — 관문(동결·행·핀·verify 영수증·모든 실행/P1/병합 기록)을 여기서 다 통과한 뒤
    고정 로더로 봉·펀딩·인쇄·kline 일 종가를 읽고 청산 수수료는 #69 `load_rules()`. 모든 실패 = 거부(아무것도 쓰지 않음)."""
    from backtest import prepare_t4 as PT
    from backtest.t4_provenance import ProvenanceError, load_pins
    from backtest.t4_stages import StageFailed, Stages
    from strategies.trial04.harness import InputError, RulesSnapshotMismatch, load_rules
    _preconditions(base)
    st = Stages(evaluator_commit, base=base, repo=repo, fetch=fetch)
    try:
        prov = st.receipt_ok(st.begin())
        record_shas = st.check_all_records(prov)
        pins, pc = load_pins(repo, fetch_first=False)
        bars, fundings, prints = PT.load_prepared_pinned(st.prep, pins, PT.is_range(), root=repo)
        kd = PT.load_kline_daily_pinned(st.prep, pins, PT.is_range(), root=repo)
        liq_fee = load_rules().symbol_rules.liquidation_fee
    except (StageFailed, ProvenanceError, InputError, PT.OOSGuard, RulesSnapshotMismatch, OSError, ValueError, KeyError) as e:
        raise Refusal(f"{type(e).__name__}: {e}") from e
    receipt = json.loads((st.records / "verify_receipt.json").read_text())
    before = _input_hashes(base)
    extra = {"fingerprint": prov["fingerprint"], "rows": prov["rows"], "pins": pins, "pins_commit": pc, "verify_receipt": receipt,
             "stage_records_sha256": record_shas}
    return _run_once(base, evaluator_commit, before, lambda: compute(base, bars, fundings, prints, kd, liq_fee), extra)


def evaluate_with_fixture(base: Path, *, bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]],
                          kline_daily: Sequence[dict[str, Any]], liq_fee: Decimal, p: TcParams, window: tuple[int, int],
                          p1_draws: int) -> tuple[str, dict[str, Any]]:
    """**테스트 전용** — 한 번만 틀(사전조건 · 시도 기록 · 입력 재해시 · 원자적 쓰기)만 검사한다. 동결·행·핀·기록 관문은 없다((g))."""
    _require_test_caller()
    _preconditions(base)
    before = _input_hashes(base)
    return _run_once(base, "fixture", before,
                     lambda: _compute(base, bars, fundings, prints, kline_daily, p=p, window=window, liq_fee=liq_fee,
                                      p1_draws=p1_draws), {})
