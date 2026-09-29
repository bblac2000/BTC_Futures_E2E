"""트라이얼 #2 판정기(단계 2g · 설계 r1 + H1~H15 · 사전등록 §3 · §3-1 · §4 · §7) — 모든 산출물이 갖춰진 뒤 **한 번**.

    uv run python -m backtest.evaluate_t2          # 표준출력 = 판정 문자열 하나 · 나머지는 var/backtest/t2/IS/evaluation/

순서: ① 문(영수증의 판정기 커밋 H가 푸시·동결 · 지문 = 영수증 · verify 기록·영수증 · 원시→산출물 전체 재빌드 1회) →
② **결과 파일을 열기 전에** 독립 기대 목록 전체 대조(H2·H13·H14 — 기록 종류별 출처 · 명령 · 정확한 출력 집합 · git_head) →
③ 메타·유효일·병합 내용 대조(H12·H15) → ④ 통계(H1·H4·H5·H9) → ⑤ 순수 핵심 `verdict_t2.verdict_is` → ⑥ 임시 디렉터리에 쓰고 이름 바꾸기.
어느 단계든 실패하면 **판정 없음**(거부 · 아무것도 쓰지 않음). 전략·하니스·실행 모듈을 import하지 않는다(앵커 상수만).
`final_wallet`은 읽지 않는다(고정 사이징 자본 모드에서 의미 없음 · 보고 원장은 트레이드 net).
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import math
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from backtest import days as DY
from backtest import prepare_t2 as PT
from backtest import stats as ST
from backtest import stats_t2 as S2
from backtest import t2_provenance as PV
from backtest import t2_stages as T
from backtest import verdict_t2 as V
from backtest.data import Bar1m, Funding
from strategies.trial02 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
DAY = A.DAY_MS
N_STAT = Decimal(1000)
#  K3'(규약 29): 값 기준 거부는 없다. 산술 무결성만 — 입력은 유한한 Decimal, float64 계산이 실제로 넘치면(비유한 결과) 판정 거부.
SIDECARS = ("verify_receipt.json", "p1_merge_expect.json")
NOT_COMPUTABLE = "p1_not_computable.json"
P4 = [f"P4_draw{d:03d}" for d in range(A.P4_DRAWS)]
STRATEGY_RUNS = ["A", "B", "P2_delay1", "P2_delay5", "P3_invert", *P4]
VARIANTS: dict[str, dict[str, Any]] = {"A": {"arm": "A", "delay": 0, "invert": False, "p4_draw": None},
                                       "B": {"arm": "B", "delay": 0, "invert": False, "p4_draw": None},
                                       "P2_delay1": {"arm": "A", "delay": 1, "invert": False, "p4_draw": None},
                                       "P2_delay5": {"arm": "A", "delay": 5, "invert": False, "p4_draw": None},
                                       "P3_invert": {"arm": "A", "delay": 0, "invert": True, "p4_draw": None},
                                       **{n: {"arm": "A", "delay": 0, "invert": False, "p4_draw": i} for i, n in enumerate(P4)}}


class Refusal(RuntimeError):
    """판정 거부 — 판정 문자열 없음(H3 iii)."""


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _jsonl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def _rng(k: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(A.BOOTSTRAP_SEED).spawn(A.BOOTSTRAP_SPAWN)[k]))


# ── ② 독립 기대 목록 ────────────────────────────────────────────────────────
def check_inventory(st: T.Stages, prov: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """기록 이름 → 기록. 결과 파일은 해시로만 본다(내용은 열지 않는다)."""
    files = {p.name for p in st.records.iterdir() if p.is_file()} if st.records.exists() else set()
    part_names = sorted(n[:-5] for n in files if re.fullmatch(r"P1_part_\d{3}_\d{3}\.json", n))
    expected = {f"{n}.json" for n in ["prepare", "verify", *STRATEGY_RUNS, "P1_merge", *part_names]} | set(SIDECARS)
    if files != expected:
        raise Refusal(f"기록 목록 불일치: 없음 {sorted(expected - files)[:5]} · 기대 밖 {sorted(files - expected)[:5]}")
    base = {"evaluator_commit": prov["evaluator_commit"], "fingerprint": prov["fingerprint"]}
    post = prov
    recs: dict[str, dict[str, Any]] = {}

    def one(name: str, kind_prov: dict[str, Any], module: str, args: list[str], out: Path, sets: list[set[str]]) -> None:
        rec = json.loads((st.records / f"{name}.json").read_text())
        try:
            PV.check_record(rec, out_dir=out, expect=kind_prov | {"variant": name}, module=module, args=args)
        except PV.ProvenanceError as e:
            raise Refusal(f"{name}: {e}") from e
        head = rec["provenance"].get("head")
        if rec["run"]["git_head"] != head or "+dirty" in str(rec["run"]["git_head"]):
            raise Refusal(f"{name}: git_head {rec['run']['git_head']} ≠ 기록 head {head} 또는 더러운 트리")
        if set(rec["run"]["outputs"]) not in sets:
            raise Refusal(f"{name}: 출력 집합 {sorted(rec['run']['outputs'])}이 기대와 다르다")
        recs[name] = rec

    prep_set = set(T.PREP_OUTPUTS)                           # 독립적으로 고정한 정확한 집합(Codex 2g after #2 · advisor #2)
    one("prepare", base, T.PREP_MODULE, [], st.prep, [prep_set])
    one("verify", base | {"pins_commit": prov["pins_commit"]}, T.PREP_MODULE, ["--verify"], st.prep, [prep_set])
    for n in STRATEGY_RUNS:
        one(n, post, T.STRATEGY, ["--variant", n, "--prepared", str(st.prep)], st.runs / n, [set(T.RUN_OUTPUTS)])
    p1_sets = [set(T.P1_OUTPUTS), set(T.P1_OUTPUTS) | {NOT_COMPUTABLE}]
    covered: list[int] = []
    for n in part_names:
        lo, hi = (int(x) for x in n.removeprefix("P1_part_").split("_"))
        args = ["--a-dir", str(st.runs / "A"), "--prepared", str(st.prep), "--draws", f"{lo}-{hi}"]
        one(n, post, T.P1_MODULE, args, st.runs / "P1" / n.removeprefix("P1_"), p1_sets)
        covered += range(lo, hi + 1)
    if sorted(covered) != list(range(A.P1_DRAWS)):
        raise Refusal("P1 조각이 0..999를 정확히 한 번씩 덮지 않는다(겹침·틈)")
    ef = st.records / "p1_merge_expect.json"
    expect = {n.removeprefix("P1_"): recs[n]["run"]["outputs"] for n in part_names}
    if json.loads(ef.read_text()) != expect:
        raise Refusal("p1_merge_expect.json이 조각 기록에서 다시 만든 값과 다르다")
    one("P1_merge", post, T.P1_MODULE, ["--merge", "--parts-root", str(st.runs / "P1"), "--expect", str(ef),
                                        "--prepared", str(st.prep)], st.runs / "P1_merged", p1_sets)
    return recs


# ── ③ 메타·유효일·병합 내용 ──────────────────────────────────────────────────
def check_meta(st: T.Stages, recs: dict[str, dict[str, Any]], pins: dict[str, Any], prov: dict[str, Any],
               validity: DY.Validity) -> None:
    vdict = json.loads(json.dumps(validity.as_dict(), sort_keys=True))
    gate = {k: prov[k] for k in ("evaluator_commit", "pins_commit", "manifest_sha256", "fingerprint")}
    for n in STRATEGY_RUNS:
        d = st.runs / n
        meta = json.loads((d / "meta.json").read_text())
        want = {"variant_name": n, "variant": VARIANTS[n], "pins": pins, "pins_commit": prov["pins_commit"],
                "manifest_sha256": prov["manifest_sha256"], "bo_v1_sha256": A.BO_V1_SHA256,
                "rules_snapshot_sha256": A.RULES_SNAPSHOT_SHA256, "git_head": recs[n]["provenance"]["head"]}
        bad = [k for k, v in want.items() if meta.get(k) != v]
        g = meta.get("gate") or {}
        if any(g.get(k) != v for k, v in gate.items()):
            bad.append("gate")
        trades, crosses = _jsonl(d / "trades.jsonl"), _jsonl(d / "crosses.jsonl")
        if meta.get("n_trades") != len(trades) or meta.get("n_first_cross") != len(crosses):
            bad.append("counts")
        if json.loads((d / "validity.json").read_text()) != vdict:
            bad.append("validity")
        days = validity.v_b if n == "B" else validity.v_a
        if any(int(t["entry_ms"]) // DAY not in days for t in trades):
            bad.append("trade_day_outside_valid_set")
        if n == "B":                                          # 날 상태 기록이 V_B와 일대일 · B 트레이드는 수축(trading)일에만
            rows = _jsonl(d / "days.jsonl")
            st_b: dict[int, list[str]] = defaultdict(list)
            for r in rows:
                st_b[int(r["day"])].append(str(r.get("status")))
            vb_ok = all(len(st_b.get(x, [])) == 1 and st_b[x][0] in ("trading", "not_contraction", "no_range") for x in validity.v_b)
            others_ok = all(v == ["not_trade_day"] for k, v in st_b.items() if k not in validity.v_b)
            trading = {k for k, v in st_b.items() if v == ["trading"]}
            if not (vb_ok and others_ok) or any(int(t["entry_ms"]) // DAY not in trading for t in trades):
                bad.append("b_day_status")
        if bad:
            raise Refusal(f"{n}: 메타/유효일 불일치 {bad}")
    parts = sorted((st.runs / "P1").glob("part_*"))
    draws: list[dict[str, Any]] = []
    nulls: list[dict[str, Any]] = []
    nc = {(p / NOT_COMPUTABLE).exists() for p in parts} | {(st.runs / "P1_merged" / NOT_COMPUTABLE).exists()}
    if len(nc) != 1:
        raise Refusal("P1 계산 가능 여부가 조각·병합 사이에 섞였다")
    for p in parts:
        draws += json.loads((p / "p1_draws.json").read_text())
        nulls += _jsonl(p / "p1_null.jsonl")
    m = st.runs / "P1_merged"
    want_draws = json.dumps(sorted(draws, key=lambda x: x["draw"]), sort_keys=True, separators=(",", ":"))
    want_null = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in sorted(nulls, key=lambda r: r["draw"]))
    if (m / "p1_draws.json").read_text() != want_draws or (m / "p1_null.jsonl").read_text() != want_null:
        raise Refusal("P1 병합 내용이 조각들의 정렬 연결과 다르다(H12)")
    if not nc.pop():
        merged = json.loads(want_draws)
        if [x["draw"] for x in merged] != list(range(A.P1_DRAWS)):
            raise Refusal("P1 병합 추출 번호가 0..999가 아니다")
        ok_ids = [x["draw"] for x in merged if x["ok"]]
        if [r["draw"] for r in json.loads("[" + ",".join(want_null.splitlines()) + "]")] != ok_ids:
            raise Refusal("P1 귀무 행이 성공 추출과 일대일이 아니다")


# ── ④ 통계 ─────────────────────────────────────────────────────────────────
def _f(x: Any) -> float:
    """Decimal 문자열 → float64 한 번(H9). 유한하지 않거나 해석 불가 → 거부(NaN이 ≤/≥ 비교를 조용히 거짓으로 만드는 경로 차단)."""
    try:
        d = Decimal(str(x))
    except (decimal.InvalidOperation, ValueError) as e:
        raise Refusal(f"수치 해석 불가: {x!r}") from e
    if not d.is_finite():
        raise Refusal(f"유한하지 않은 값: {x!r}")
    f = float(d)
    if not math.isfinite(f):
        raise Refusal(f"float64 범위 밖 값: {x!r}")                  # 1e400 → inf(Codex 2g r2 #1)
    return f


def trades_of(st: T.Stages, name: str) -> list[dict[str, Any]]:
    return sorted(_jsonl(st.runs / name / "trades.jsonl"), key=lambda t: (int(t["entry_ms"]), int(t["trade_id"])))


def _fin(v: float, what: str) -> float:
    if not math.isfinite(v):
        raise Refusal(f"집계값이 유한하지 않다({what}): {v}")      # 유한한 값들의 합이 넘치는 경로(Codex 2g r3)
    return v


def mean_net(trades: Sequence[dict[str, Any]]) -> float:
    if not trades:
        return 0.0                                            # 0건 → 0 bps(§3-1 P2·P3)
    return _fin(float(np.mean([_f(t["net_bps"]) for t in trades])), "mean_net")


def daily_stat_pnl(trades: Sequence[dict[str, Any]]) -> dict[int, float]:
    out: dict[int, Decimal] = defaultdict(Decimal)
    for t in trades:
        out[int(t["entry_ms"]) // DAY] += N_STAT * Decimal(str(t["net_bps"])) / Decimal(10_000)
    return {k: float(v) for k, v in out.items()}


def by_day(trades: Sequence[dict[str, Any]], field: str) -> dict[int, list[float]]:
    out: dict[int, list[float]] = defaultdict(list)
    for t in trades:
        out[int(t["entry_ms"]) // DAY].append(_f(t[field]))
    return out


def bh_series(daily: Sequence[dict[str, Any]], first_day: int, last_day: int) -> dict[str, Any]:
    """H5·K2: kline 일 종가(`kline_close_daily.json` — 23:59 kline 종가, 없으면 그날 마지막 kline 분) · IS 창 날만 ·
    kline 없는 날은 목록에 없고 다음 수익률이 잇는다 · mark 계열과 무관."""
    rows = sorted((r for r in daily if first_day <= int(r["day"]) <= last_day), key=lambda r: int(r["day"]))
    ds = [int(r["day"]) for r in rows]
    c = [_f(r["close"]) for r in rows]
    rets = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
    return {"days": len(ds), "daily_sharpe": S2.sharpe_or_none(rets), "window_return": (c[-1] / c[0] - 1) if len(c) >= 2 else None}


def psr0(x: Sequence[float]) -> float | None:
    if S2.sharpe_or_none(x) is None:
        return None
    v = ST.psr(list(x), 0.0)
    return v if math.isfinite(v) else None


def arm_stats(trades: Sequence[dict[str, Any]], days: Sequence[int], k_gross: int, k_net: int) -> dict[str, Any]:
    net = [_f(t["net_bps"]) for t in trades]
    g = S2.valid_day_bootstrap_mean(by_day(trades, "gross_bps"), days, _rng(k_gross), resamples=A.BOOTSTRAP_RESAMPLES, level=A.LEVEL)
    n_ = S2.valid_day_bootstrap_mean(by_day(trades, "net_bps"), days, _rng(k_net), resamples=A.BOOTSTRAP_RESAMPLES, level=A.LEVEL)
    sd = float(np.std(net, ddof=1)) if len(net) >= 2 else None
    return {"n": len(net), "rho": S2.lag1_rho(net), "mean_gross": g.mean if net else float("nan"),
            "gross_ci": [g.lo, g.hi] if g.defined else None, "mean_net": n_.mean if net else float("nan"),
            "net_ci": [n_.lo, n_.hi] if n_.defined else None, "sd_net": sd if sd and sd > 0 else None,
            "sr": S2.sharpe_or_none(net), "psr0": psr0(net), "degenerate_resamples": [g.degenerate, n_.degenerate],
            "liquidations": sum(1 for t in trades if t.get("exit_reason") == "liquidation")}


def skip_report(crosses: Sequence[dict[str, Any]]) -> dict[str, Any]:
    c = Counter()
    for x in crosses:
        r = x.get("final_reason") or "entered"
        if r == "sl_dist_out_of_range":
            r += "_" + str(x.get("side"))
        c[r] += 1
    n = len(crosses)
    return {"denominator": n, "counts": dict(sorted(c.items())), "ratios": {k: v / n for k, v in sorted(c.items())} if n else {}}


def trade_report(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    hold = [(int(t["exit_ms"]) - int(t["entry_ms"])) / 60_000 for t in trades]
    years: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        years[str(dt.datetime.fromtimestamp(int(t["entry_ms"]) / 1000, dt.UTC).year)].append(_f(t["net_bps"]))
    return {"holding_min_quantiles": [float(q) for q in np.quantile(hold, [0.1, 0.25, 0.5, 0.75, 0.9])] if hold else None,
            "share_ge_60": float(np.mean([h >= 60 for h in hold])) if hold else None,
            "share_ge_240": float(np.mean([h >= 240 for h in hold])) if hold else None,
            "exit_reasons": dict(sorted(Counter(t["exit_reason"] for t in trades).items())),
            "direction": dict(sorted(Counter(t["direction"] for t in trades).items())),
            "per_year": {y: {"n": len(v), "mean_net_bps": float(np.mean(v))} for y, v in sorted(years.items())}}


def compute(st: T.Stages, validity: DY.Validity, kline_daily: Sequence[dict[str, Any]], first_day: int, last_day: int
            ) -> tuple[V.ISInputs, dict[str, Any]]:
    va, vb = sorted(validity.v_a), sorted(validity.v_b)
    ta, tb = trades_of(st, "A"), trades_of(st, "B")
    sa = arm_stats(ta, va, A.BOOTSTRAP_STREAMS["gross_A"], A.BOOTSTRAP_STREAMS["net_A"])
    sb = arm_stats(tb, vb, A.BOOTSTRAP_STREAMS["gross_B"], A.BOOTSTRAP_STREAMS["net_B"])
    merged = st.runs / "P1_merged"
    p1_comp = not (merged / NOT_COMPUTABLE).exists()
    draws = json.loads((merged / "p1_draws.json").read_text())
    p1_null = [_f(r["mean_net_bps"]) for r in _jsonl(merged / "p1_null.jsonl")]
    p1_fail = sum(1 for d in draws if not d["ok"])
    if p1_comp != (len(ta) > 0):
        raise Refusal("P1 계산 가능 여부가 원판 트레이드 수와 모순")
    p4_runs = {n: trades_of(st, n) for n in P4}
    p4_means = [mean_net(t) for t in p4_runs.values() if t]
    p2 = {n: mean_net(trades_of(st, n)) for n in ("P2_delay1", "P2_delay5")}
    p3 = mean_net(trades_of(st, "P3_invert"))
    x = V.ISInputs(v_a_empty=not va, n_a=len(ta), liquidations_a=sa["liquidations"], rho=sa["rho"],
                   mean_gross=sa["mean_gross"], gross_ci_lo=sa["gross_ci"][0] if sa["gross_ci"] else None,
                   mean_net=sa["mean_net"], net_ci_lo=sa["net_ci"][0] if sa["net_ci"] else None,
                   net_ci_hi=sa["net_ci"][1] if sa["net_ci"] else None, sd_net=sa["sd_net"], sr_a=sa["sr"], sr_b=sb["sr"],
                   psr0_a=sa["psr0"], p1_computable=p1_comp, p1_failures=p1_fail,
                   p1_p95=_fin(S2.p95(p1_null), "P1 p95") if p1_null else None, p2_d1=p2["P2_delay1"], p2_d5=p2["P2_delay5"], p3_inv=p3,
                   p4_defined=len(p4_means), p4_p95=_fin(S2.p95(p4_means), "P4 p95") if p4_means else None)
    a_day, b_day = daily_stat_pnl(ta), daily_stat_pnl(tb)
    ab = S2.daily_diff_bootstrap({d: a_day.get(d, 0.0) for d in vb}, {d: b_day.get(d, 0.0) for d in vb}, vb,
                                 _rng(A.BOOTSTRAP_STREAMS["ab_daily"]), resamples=A.BOOTSTRAP_RESAMPLES, level=A.LEVEL)
    a_sharpe = S2.sharpe_or_none([a_day.get(d, 0.0) / float(N_STAT) for d in va])
    bh = bh_series(kline_daily, first_day, last_day)
    label = ("비교 불가" if a_sharpe is None or bh["daily_sharpe"] is None
             else ("ACCEPT — 수동(매수보유)을 이기지는 못함" if a_sharpe < bh["daily_sharpe"] else "ACCEPT"))
    contraction = {int(x["day"]) for x in _jsonl(st.runs / "B" / "days.jsonl") if x.get("status") == "trading"}
    c_trades = [t for t in ta if int(t["entry_ms"]) // DAY in set(vb) - contraction]          # 비수축일(V_B) A 트레이드
    report = {"A": sa, "B": sb, "validity": {"n_v_a": len(va), "n_v_b": len(vb), "reasons": validity.as_dict()["reasons"],
                                             "reasons_b": validity.as_dict()["reasons_b"]},
              "P1": {"computable": p1_comp, "failed_draws": p1_fail, "successful_draws": len(p1_null), "p95": x.p1_p95,
                     "exits": dict(sorted(sum((Counter(r.get("exits", {})) for r in _jsonl(merged / "p1_null.jsonl")),
                                              Counter()).items()))},
              "P2": p2, "P3_invert": p3,
              "P4": {"defined": len(p4_means), "zero_trade_draws": A.P4_DRAWS - len(p4_means), "p95": x.p4_p95},
              "liquidations": {n: sum(1 for t in trades_of(st, n) if t.get("exit_reason") == "liquidation") for n in STRATEGY_RUNS},
              "AB_daily_contrast": {"mean": ab.mean, "ci": [ab.lo, ab.hi], "days": len(vb)},
              "B_vs_noncontraction_A": {"mean_B": sb["mean_net"] if tb else None, "mean_C": mean_net(c_trades) if c_trades else None,
                                        "n_B": len(tb), "n_C": len(c_trades), "contraction_days": len(contraction),
                                        "diff_B_minus_C": (sb["mean_net"] - mean_net(c_trades)) if tb and c_trades else None},
              "buy_and_hold": bh | {"A_daily_sharpe": a_sharpe, "is_label": label},
              "skips_A": skip_report(_jsonl(st.runs / "A" / "crosses.jsonl")) | {
                  "invalid_days_A": len(validity.reasons), "invalid_days_B": len(validity.reasons) + len(validity.reasons_b)},
              "trades_A": trade_report(ta) | {"trades_per_valid_day": len(ta) / len(va) if va else None}}
    return x, report


# ── ⑤⑥ 실행 ────────────────────────────────────────────────────────────────
def verdict_string(v: V.Verdict) -> str:
    """판정 문자열 형식(규약 · advisor 2g after #3): 분류가 있으면 `REJECT(§7-2: <분류>)` · 없으면 라벨 그대로."""
    return f"{v.label}(§7-2: {v.classification})" if v.classification else v.label


def _finite(o: Any) -> Any:
    """보고서 JSON은 엄격 — NaN·Inf → None(advisor #4)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [_finite(v) for v in o]
    return o


def evaluate(base: Path = T.BASE_DIR, repo: Path = ROOT, **kw: Any) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """모든 실패 = 판정 거부(판정 없음 · 아무것도 쓰지 않음) — 영수증 해석·선행 검사 포함(Codex 2g r2 · advisor #6)."""
    try:
        return _evaluate(base, repo, **kw)
    except Refusal:
        raise
    except Exception as e:  # noqa: BLE001 — 어떤 예외도 판정으로 새지 않는다
        raise Refusal(f"{type(e).__name__}: {e}") from e


def _evaluate(base: Path, repo: Path, *, fetch: bool = True,
              load_prepared: Callable[..., tuple[list[Bar1m], list[Funding]]] = PT.load_prepared_pinned,
              load_kline: Callable[..., list[dict[str, Any]]] = PT.load_kline_daily_pinned,
              rebuild: Callable[..., Any] = PT.verify_rebuild, window: tuple[int, int] | None = None,
              days: tuple[int, int] | None = None) -> tuple[str, dict[str, Any], dict[str, Any]]:
    decimal.setcontext(decimal.Context())
    out = base / "evaluation"
    if out.exists():
        raise Refusal("판정은 한 번만 — evaluation/이 이미 있다")
    rf = base / "_records" / "verify_receipt.json"
    if not rf.exists():
        raise Refusal("verify 영수증이 없다")
    receipt = json.loads(rf.read_text())
    st = T.Stages(receipt["evaluator_commit"], base=base, repo=repo, fetch=fetch)
    try:
        fp = st.preflight()
        prov = st.receipt_ok(fp)
        pins, _ = PV.load_pins(repo, fetch=fetch)
    except PV.ProvenanceError as e:
        raise Refusal(str(e)) from e
    rng = window or PT.window_range()
    first, last = days or (A.IS_START_MS // DAY, A.IS_END_MS // DAY)
    try:
        recs = check_inventory(st, prov)                    # 결과 파일 내용을 열기 전
        rebuild(st.prep, rng)                               # 원시 → 산출물 재빌드 1회(H2 · G8)
        bars, fundings = load_prepared(st.prep, pins, rng)
        validity = DY.validity(bars, fundings, first, last)
        check_meta(st, recs, pins, prov, validity)
        kline_daily = load_kline(st.prep, pins, rng)
        with np.errstate(over="raise", invalid="raise", divide="raise"):   # K3': 실제 넘침·비유한 연산 → 거부
            x, report = compute(st, validity, kline_daily, first, last)
        v = V.verdict_is(x)
    except Refusal:
        raise
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, FloatingPointError,
            PV.ProvenanceError) as e:                                                            # advisor #6: 판정 없음
        raise Refusal(f"{type(e).__name__}: {e}") from e
    verdict = verdict_string(v)
    report = {"verdict": verdict, "priority": v.priority, "classification": v.classification, "gates": v.gates,
              "placebo_rejects": v.placebo_rejects, "sr_star": v.sr_star, "sr_undefined": v.sr_undefined, "mde": v.mde,
              "inputs": x.__dict__, **report}
    read = {str(p.relative_to(base)): _sha(p) for p in sorted(base.rglob("*")) if p.is_file() and "evaluation" not in p.parts
            and "raw" not in p.parts}
    record = {"evaluator_commit": st.h, "pins_commit": prov["pins_commit"], "fingerprint": fp, "receipt": receipt,
              "evaluator_head": PV.head(repo), "inputs_sha256": read}
    tmp = Path(tempfile.mkdtemp(prefix="evaluation_", dir=base))
    try:
        (tmp / "report.json").write_text(json.dumps(_finite(report), sort_keys=True, indent=1, ensure_ascii=False, default=str,
                                                    allow_nan=False) + "\n")
        (tmp / "verdict.txt").write_text(verdict + "\n")
        record |= {"report_sha256": _sha(tmp / "report.json"), "verdict_sha256": _sha(tmp / "verdict.txt")}
        (tmp / "record.json").write_text(json.dumps(record, sort_keys=True, indent=1, ensure_ascii=False) + "\n")
        tmp.rename(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return verdict, report, record


def main(argv: list[str] | None = None) -> int:
    try:
        verdict, _, _ = evaluate()
    except Refusal as e:
        import sys
        print(f"판정 거부: {e}", file=sys.stderr)
        return 2
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
