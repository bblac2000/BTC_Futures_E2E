"""트라이얼 #3 판정기(단계 2 (f) · 계획 r2/r3 · 사전등록 §3 · §3-1 · §4 · §7 · 규약 초안 31·40~44·47 · 섹션 G).

- 입력 계약 = `backtest.t3_outputs`(빠짐·남음·스키마 불일치 → 거부) + 준비 입력(봉 · 펀딩 · kline 일 종가 — (g) CLI가 고정 로더로 준다).
- 트레이드마다 원장 항등식(계획 V2′): 지갑·수수료·펀딩·체결은 **34자리**(엔진 실행 문맥)에서 엔진 기록값과 정확히 같아야 하고, gross/net
  문자열은 `returns.trade_return`을 **기본 28자리 문맥**에서 다시 불러 정확히 같아야 한다 · 비용 격자 ×1.0 = 기록된 net · 불일치 → 거부.
- V(항목 31): 완전한 날 ∧ 분위수 유효(정의된 r30 **개수**만 — 값 미사용)를 다시 계산해 여덟 실행 기록과 대조 · 진입일 ∉ V → 거부.
- 판정: `verdict_t3.verdict_is`(두 암 함께 · G-B SR* 공유) · 문자열 = §3-1 87행 · 보고에 "청산 k / 체결 n".
- 한 번만(사용자 (f) 요구 7): `evaluation/`이 있으면 거부 · 판정기 커밋이 HEAD와 origin/main의 조상이 아니거나 판정기 파일이 그 뒤 바뀌었거나
  작업 트리가 더러우면 거부 · 모든 실패 = 거부(아무것도 쓰지 않음 — 다시 시도해도 두 번째 판정이 아니다) · 결과는 임시 디렉터리 → 이름 바꾸기.
- OOS·전진 판정 함수는 `verdict_t3`에 사전확약 · 이 CLI는 IS만(OOS는 `prepare_t3.oos_range`의 레지스트리 행 관문 뒤).
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import inspect
import json
import math
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import numpy as np

from backtest import p1_t3 as P1
from backtest import stats as ST
from backtest import stats_t2 as S2
from backtest import t3_outputs as O
from backtest import verdict_t3 as V
from backtest.data import MINUTE_MS, Bar1m
from backtest.returns import trade_return
from exchange.orders import Direction
from strategies.trial03 import anchor as A
from strategies.trial03.config import TF_V1, TfParams
from strategies.trial03.harness import GRID, complete_days

ROOT = Path(__file__).resolve().parent.parent
DAY = A.DAY_MS
EVALUATOR_FILES = ("backtest/evaluate_t3.py", "backtest/verdict_t3.py", "backtest/t3_outputs.py", "backtest/stats.py",
                   "backtest/stats_t2.py")
#  판정을 바꿀 수 있는 코드 전부(Codex (f) after #1) — 판정기 커밋과 지금이 바이트 동일해야 한다(파일 집합도 같아야 한다)
FREEZE_FILES = EVALUATOR_FILES + tuple(f"backtest/{n}.py" for n in (
    "p1_t3", "p1_core", "placebo_exec", "engine_replay", "returns", "data", "replay", "prepare_t3", "prepare_t2")) + (
    "pyproject.toml", "uv.lock")
FREEZE_GLOBS = ("strategies/trial03/*.py", "paper/*.py", "sizing/*.py", "exchange/*.py")
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


# ── V 재계산(항목 31 · 개수만) ───────────────────────────────────────────────
def recompute_v(bars: Sequence[Bar1m], window: tuple[int, int], p: TfParams) -> tuple[set[int], dict[int, bool]]:
    def pos(v: str) -> bool:
        try:
            x = Decimal(v)
        except (decimal.InvalidOperation, ValueError):
            return False
        return x.is_finite() and x > 0

    closes = {b.open_ms: pos(b.mark_close) for b in bars}
    per_day: Counter[int] = Counter()
    for b in bars:
        if closes[b.open_ms] and closes.get(b.open_ms - p.r30_ms, False):
            per_day[b.open_ms // DAY] += 1
    full = complete_days(bars)
    #  정의역 = 봉이 1개 이상 있는 창 날(전략은 날의 첫 봉에서 분위수를 기록한다 — 봉 0개인 날은 기록이 없다 · advisor (f) after #1)
    seen = sorted({b.open_ms // DAY for b in bars if window[0] <= b.open_ms <= window[1]})
    q_valid: dict[int, bool] = {}
    for d in seen:
        q_valid[d] = sum(per_day[x] for x in range(d - p.w_ref_days, d)) >= p.quantile_min_defined
    v = {d for d, ok in q_valid.items() if ok and d in full}
    return v, q_valid


# ── 트레이드 원장 항등식(계획 V2′) ──────────────────────────────────────────
def ledger_check(trades: Sequence[dict[str, Any]], events: Sequence[dict[str, Any]], liq_fee: Decimal,
                 e_ref: Decimal) -> list[dict[str, Any]]:
    filled = [e for e in events if e["kind"] == "filled"]
    exits = [e for e in events if e["kind"] == "exit"]
    if not (len(filled) == len(exits) == len(trades)):
        raise Refusal(f"체결·청산 기록 {len(filled)}/{len(exits)} ≠ 트레이드 {len(trades)}")
    out = []
    for k, (t, fi, ex) in enumerate(zip(trades, filled, exits, strict=True)):
        if int(t["trade_id"]) != k or int(t["entry_ms"]) != int(fi["fill_open"]) or int(t["exit_ms"]) != int(ex["ts_ms"]) \
                or t["entry_mark"] != fi["entry_ref"] or int(t["leverage"]) != int(fi["leverage"]) or t["exit_reason"] != ex["reason"] \
                or t["direction"] != t["t3"]["intent_dir"] or int(t["entry_ms"]) != int(t["t3"]["decided_ms"]) + 1:
            raise Refusal(f"트레이드 {t.get('trade_id')}: 시각·기준가·레버리지·사유·방향이 엔진 기록과 다르다(Codex (f) after #2)")
        d = Direction(t["direction"])
        sign = Decimal(1) if d is Direction.LONG else Decimal(-1)
        qty, fill_in, w0, w1 = Decimal(t["qty"]), Decimal(t["entry_fill"]), Decimal(t["wallet_before"]), Decimal(t["wallet_after"])
        if w0 != e_ref:
            raise Refusal(f"트레이드 {t['trade_id']}: wallet_before {w0} ≠ E_ref {e_ref}(L5)")
        if Decimal(fi["qty"]) != qty or Decimal(fi["fill"]) != fill_in or Decimal(ex["wallet_after"]) != w1:
            raise Refusal(f"트레이드 {t['trade_id']}: 체결·청산 기록이 트레이드와 다르다")
        comm_in, comm_out = Decimal(fi["entry_commission"]), Decimal(ex["exit_commission"])
        funding, ref_in = Decimal(ex["funding_paid"]), Decimal(fi["entry_ref"])
        with localcontext() as c:
            c.prec = 34
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
            if not ok:
                raise Refusal(f"트레이드 {t['trade_id']}: 지갑 항등식 불일치")
            cost_bps = cost / (qty * fill_in) * BPS
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
        out.append({"trade_id": t["trade_id"], "cost_bps": cost_bps, "grid": grid, "funding": funding, "exit_ms": int(ex["ts_ms"])})
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
    return _fin(float(np.mean([_f(t["net_bps"]) for t in trades])), "mean_net") if trades else 0.0


def trade_report(trades: Sequence[dict[str, Any]], ledger: Sequence[dict[str, Any]], e_ref: Decimal) -> dict[str, Any]:
    hold = [(int(t["exit_ms"]) - int(t["entry_ms"])) / 60_000 for t in trades]
    years: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        years[str(dt.datetime.fromtimestamp(int(t["entry_ms"]) / 1000, dt.UTC).year)].append(_f(t["net_bps"]))
    x9 = sum(1 for t in trades if t["exit_reason"] == "time_exit"
             and ((Decimal(t["exit_ref"]) <= Decimal(t["sl"])) if t["direction"] == "LONG" else (Decimal(t["exit_ref"]) >= Decimal(t["sl"]))))
    bnd = [lg for lg in ledger if (lg["exit_ms"] - lg["exit_ms"] % MINUTE_MS) % DAY in GRID]
    asym = [lg for lg in bnd if lg["exit_ms"] % MINUTE_MS == 0]       # 봉 시가 청산(time_exit·시가 갭 청산) — 항목 47 비대칭
    sym = [lg for lg in bnd if lg["exit_ms"] % MINUTE_MS != 0]        # 봉 안 청산 — P1도 같은 경계를 낸다(h = k+1)
    fund_sum = sum((lg["funding"] for lg in asym), Decimal(0))
    grid = {k: float(np.mean([float(lg["grid"][k]) for lg in ledger])) if ledger else None for k in ("0.5", "1.0", "1.5")}
    return {"holding_min_quantiles": [float(q) for q in np.quantile(hold, [0.1, 0.25, 0.5, 0.75, 0.9])] if hold else None,
            "exit_reasons": {r: {"n": c, "share": c / len(trades)} for r, c in sorted(Counter(t["exit_reason"] for t in trades).items())},
            "n_trades": len(trades),
            "per_year": {y: {"n": len(v), "mean_net_bps": float(np.mean(v))} for y, v in sorted(years.items())},
            "x9_time_exit_open_past_sl": x9,
            "exit_at_funding_boundary": {"n": len(asym), "funding_paid_usdt": str(fund_sum),
                                         "funding_paid_bps_of_e_ref": str(fund_sum / e_ref * BPS),
                                         "symmetric_intrabar_n": len(sym)},
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


# ── 계산(순수 · 파일 읽기만) ─────────────────────────────────────────────────
def _compute(base: Path, bars: Sequence[Bar1m], kline_daily: Sequence[dict[str, Any]], *,
             p: TfParams, window: tuple[int, int], liq_fee: Decimal, p1_draws: int) -> tuple[dict[str, V.Verdict], dict[str, Any]]:
    O.check_run_inventory(base)
    v_set, q_valid = recompute_v(bars, window, p)
    v = sorted(v_set)
    runs = {(a, var): O.read_run(O.run_dir(base, a, var), a, var) for a in O.ARMS for var in O.VARIANTS}
    for (a, var), (trades, _, summ) in runs.items():
        if summ["v_days"] != v or {int(k): b for k, b in summ["q_valid"].items()} != q_valid:
            raise Refusal(f"{a}_{var}: 실행이 기록한 V·분위수 유효 날이 판정기 재계산과 다르다")
        if summ["tf_v1_sha256"] != A.TF_V1_SHA256:
            raise Refusal(f"{a}_{var}: tf_v1 SHA256 불일치")
        if summ["rules_sha256"] != A.RULES_SNAPSHOT_SHA256:
            raise Refusal(f"{a}_{var}: 규칙 스냅샷 SHA256이 #48과 다르다")
        if any(int(t["entry_ms"]) // DAY not in v_set for t in trades):
            raise Refusal(f"{a}_{var}: 진입일이 V 밖인 트레이드(§3-1 83행)")
    streams = A.BOOTSTRAP_STREAMS["IS"]
    stats, ledgers, p1s, inputs = {}, {}, {}, {}
    for a in O.ARMS:
        trades, events, summ = runs[(a, "base")]
        ledgers[a] = ledger_check(trades, events, liq_fee, p.e_ref)
        for var in O.VARIANTS[1:]:
            ledger_check(runs[(a, var)][0], runs[(a, var)][1], liq_fee, p.e_ref)
        stats[a] = arm_stats(trades, v, streams[f"gross_{a}"], streams[f"net_{a}"])
        parts = O.read_p1_parts(base, a)
        draws, null, psum = O.read_p1_merged(base, a)
        manifest = [{"lo": q.lo, "hi": q.hi, "sha256": O.sha(O.p1_parts_dir(base, a) / f"part_{q.lo:03d}_{q.hi:03d}" / O.P1_PART_FILE)}
                    for q in sorted(parts, key=lambda q: q.lo)]
        if psum["parts"] != manifest:
            raise Refusal(f"{a}: P1 조각 목록·해시가 p1_summary와 다르다")
        m = P1.merge(parts, draws_total=p1_draws)
        if m["draws"] != draws or m["null"] != null or {k: psum[k] for k in ("n_source", "computable", "failed", "evaluable")} != \
                {k: m[k] for k in ("n_source", "computable", "failed", "evaluable")}:
            raise Refusal(f"{a}: P1 병합 파일이 조각에서 다시 병합한 결과와 다르다")
        if m["n_source"] != len(trades) or m["computable"] != (len(trades) > 0):
            raise Refusal(f"{a}: P1 원판 수·계산 가능 여부가 기본 실행과 모순")
        null_means = [_f(r["mean_net_bps"]) for r in m["null"]]
        p1s[a] = {"computable": m["computable"], "failed": m["failed"], "successful": len(null_means),
                  "p95": _fin(S2.p95(null_means), "P1 p95") if null_means else None,
                  "exits": dict(sorted(sum((Counter(r["exits"]) for r in m["null"]), Counter()).items()))}
        s = stats[a]
        inputs[a] = V.ArmInputs(
            v_empty=not v, n=s["n"], liquidations=s["liquidations"], rho=s["rho"], mean_gross=s["mean_gross"],
            gross_ci_lo=s["gross_ci"][0] if s["gross_ci"] else None, mean_net=s["mean_net"],
            net_ci_lo=s["net_ci"][0] if s["net_ci"] else None, net_ci_hi=s["net_ci"][1] if s["net_ci"] else None,
            sd_net=s["sd_net"], sr=s["sr"], psr0=s["psr0"], p1_computable=m["computable"], p1_failures=m["failed"],
            p1_p95=p1s[a]["p95"], p2_d1=mean_net(runs[(a, "P2_delay1")][0]), p2_d5=mean_net(runs[(a, "P2_delay5")][0]),
            p3_inv=mean_net(runs[(a, "P3_invert")][0]))
    verdicts = V.verdict_is(inputs)
    first, last = window[0] // DAY, (window[1] + 1 - MINUTE_MS) // DAY
    bh = bh_series(kline_daily, first, last)
    window_days = list(range(window[0] // DAY, (window[1] + 1 - MINUTE_MS) // DAY + 1))
    report: dict[str, Any] = {
        "trial_verdict": V.trial_string(verdicts),
        "arms": {}, "v_days": len(v), "buy_and_hold": bh,
        "v_cross_check": {"runs_compared": len(runs), "match": True},
        "zero_bar_window_days": sum(1 for d in window_days if d not in q_valid),
        "constants": {"n_trials": A.N_TRIALS, "alpha": A.ALPHA, "ci_quantiles": [A.CI_LO_Q, A.CI_HI_Q],
                      "bootstrap_resamples": A.BOOTSTRAP_RESAMPLES, "bootstrap_seed": list(A.BOOTSTRAP_SEED)},
    }
    for a in O.ARMS:
        vd = verdicts[a]
        trades, events, summ = runs[(a, "base")]
        report["arms"][a] = {
            "verdict": vd.string, "survival": f"청산 {stats[a]['liquidations']} / 체결 {stats[a]['n']}", "priority": vd.priority,
            "classification": vd.classification, "gates": vd.gates, "placebo_rejects": vd.placebo_rejects, "sr_star": vd.sr_star,
            "sr_undefined": vd.sr_undefined, "mde": vd.mde, "stats": stats[a], "inputs": inputs[a].__dict__, "P1": p1s[a],
            "P2": {"delay1": inputs[a].p2_d1, "delay5": inputs[a].p2_d5}, "P3_invert": inputs[a].p3_inv,
            "event_funnel": summ["funnel"], "entry_funnel": summ["entry"], "sub_reasons": summ["sub"],
            "oi_missing_unusable": summ["sub"].get("oi_missing.unusable", 0), "window_bars": summ["window_bars"],
            "trades": trade_report(trades, ledgers[a], p.e_ref),
            "daily_sharpe": arm_daily_sharpe(trades, v, p.n_stat),
            "bh_beats_arm": _bh_beats(arm_daily_sharpe(trades, v, p.n_stat), bh["daily_sharpe"]),
            "variants": {var: {"n": runs[(a, var)][2]["n_trades"], "mean_net_bps": mean_net(runs[(a, var)][0])} for var in O.VARIANTS}}
    return verdicts, report


def compute(base: Path, bars: Sequence[Bar1m], kline_daily: Sequence[dict[str, Any]],
            liq_fee: Decimal) -> tuple[dict[str, V.Verdict], dict[str, Any]]:
    """실행 경로 — TF_V1 · 창 WINDOW_START … IS_END · P1 추출 1,000. 덮어쓸 인자가 없다."""
    return _compute(base, bars, kline_daily, p=TF_V1, window=(A.WINDOW_START_MS, A.IS_END_MS), liq_fee=liq_fee,
                    p1_draws=A.P1_DRAWS)


def _require_test_caller(depth: int = 2) -> None:
    caller = Path(inspect.stack()[depth].filename).resolve()
    if (ROOT / "tests") not in caller.parents:
        raise Refusal(f"픽스처 경로는 tests/ 전용이다(호출자 {caller})")


def compute_with_fixture(base: Path, bars: Sequence[Bar1m], kline_daily: Sequence[dict[str, Any]], liq_fee: Decimal, *,
                         p: TfParams, window: tuple[int, int], p1_draws: int) -> tuple[dict[str, V.Verdict], dict[str, Any]]:
    """**테스트 전용** — 호출자 파일이 tests/ 아래가 아니면 거부."""
    _require_test_caller()
    return _compute(base, bars, kline_daily, p=p, window=window, liq_fee=liq_fee, p1_draws=p1_draws)


# ── 한 번만 · 커밋 검사 · 쓰기 ────────────────────────────────────────────────
def _git(repo: Path, *a: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def freeze_set(repo: Path) -> set[str]:
    out = set(FREEZE_FILES)
    for g in FREEZE_GLOBS:
        out |= {str(p.relative_to(repo)) for p in repo.glob(g)}
    return out


def require_frozen(repo: Path, commit: str, *, fetch: bool = True) -> None:
    if fetch and _git(repo, "fetch", "--quiet", "origin").returncode != 0:
        raise Refusal("git fetch 실패")
    if _git(repo, "status", "--porcelain").stdout.strip():
        raise Refusal("작업 트리가 깨끗하지 않다")
    for ref in ("HEAD", "origin/main"):
        if _git(repo, "merge-base", "--is-ancestor", commit, ref).returncode != 0:
            raise Refusal(f"판정기 커밋 {commit}가 {ref}의 조상이 아니다(푸시 전 판정 금지)")
    now = freeze_set(repo)
    then_set = set(FREEZE_FILES)
    for g in FREEZE_GLOBS:
        d, pat = g.rsplit("/", 1)
        out = _git(repo, "ls-tree", "--name-only", f"{commit}:{d}").stdout.split()
        then_set |= {f"{d}/{n}" for n in out if Path(n).match(pat)}
    if now != then_set:
        raise Refusal(f"동결 파일 집합이 커밋 {commit}와 다르다: {sorted(now ^ then_set)[:5]}")
    for f in sorted(now):
        then = _git(repo, "show", f"{commit}:{f}")
        if then.returncode != 0 or then.stdout != (repo / f).read_text(encoding="utf-8"):
            raise Refusal(f"동결 파일 {f}가 판정기 커밋 {commit} 뒤에 바뀌었다")


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


def _evaluate(base: Path, repo: Path, evaluator_commit: str, fetch: bool,
              fn: Callable[[], tuple[dict[str, V.Verdict], dict[str, Any]]]) -> tuple[str, dict[str, Any]]:
    decimal.setcontext(decimal.Context())
    out = base / "evaluation"
    if out.exists():
        raise Refusal("판정은 한 번만 — evaluation/이 이미 있다")
    require_frozen(repo, evaluator_commit, fetch=fetch)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            _, report = fn()
    except Refusal:
        raise
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, FloatingPointError, O.ContractError, P1.P1Error) as e:
        raise Refusal(f"{type(e).__name__}: {e}") from e
    read = {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()}
    tmp = Path(tempfile.mkdtemp(prefix="evaluation_", dir=base))
    try:
        rb = report_bytes(report)
        (tmp / "report.json").write_bytes(rb)
        (tmp / "verdict.txt").write_text(report["trial_verdict"] + "\n")
        record = {"evaluator_commit": evaluator_commit, "inputs_sha256": read,
                  "report_sha256": hashlib.sha256(rb).hexdigest(),
                  "verdict_sha256": hashlib.sha256((tmp / "verdict.txt").read_bytes()).hexdigest()}
        (tmp / "record.json").write_text(json.dumps(record, sort_keys=True, indent=1) + "\n")
        tmp.rename(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return report["trial_verdict"], record


def evaluate(base: Path, repo: Path, *, evaluator_commit: str, bars: Sequence[Bar1m], kline_daily: Sequence[dict[str, Any]],
             liq_fee: Decimal, fetch: bool = True) -> tuple[str, dict[str, Any]]:
    """한 번만(실행 경로 · `compute`). 모든 실패 = 거부 — 아무것도 쓰지 않는다(다시 시도해도 두 번째 판정이 아니다)."""
    return _evaluate(base, repo, evaluator_commit, fetch, lambda: compute(base, bars, kline_daily, liq_fee))


def evaluate_with_fixture(base: Path, repo: Path, *, evaluator_commit: str, bars: Sequence[Bar1m],
                          kline_daily: Sequence[dict[str, Any]], liq_fee: Decimal, p: TfParams, window: tuple[int, int],
                          p1_draws: int, fetch: bool = False) -> tuple[str, dict[str, Any]]:
    """**테스트 전용** — 같은 한 번만·커밋 검사, 계산만 픽스처 매개변수."""
    _require_test_caller()
    return _evaluate(base, repo, evaluator_commit, fetch,
                     lambda: _compute(base, bars, kline_daily, p=p, window=window, liq_fee=liq_fee, p1_draws=p1_draws))
