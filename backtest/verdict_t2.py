"""트라이얼 #2 판정 순수 핵심(단계 2g H8~H10) — 사전등록 §3 게이트 · §3-1 퇴화 규칙 · §4 플라시보 기각 · §7 단계별 우선순위 · §7-2 분류.

입력은 이미 계산된 수(float64 · H9)와 bool뿐 — 파일·출처는 `evaluate_t2`(껍데기)가 다룬다. 비교는 모두 float64에서.
- G0: n ≥ 48 ∧ n / (1 + 4·max(ρ̂, 0.15)) ≥ 30 · G1/G2: 평균 > 0 ∧ CI 하한 > 0(CI 정의 안 됨 → 실패) · flat: 평균 net > 0 ·
  G-B: PSR_A(0) > 0.5 ∧ n_A ≥ 30 ∧ SR̂_A − SR* > 0 · SR* = expected_max_sr(정의된 {SR̂_#1A, SR̂_#1B, SR̂_A, SR̂_B}, n_trials = 4) ·
  정의된 값 < 2 또는 SR̂_A·PSR_A 정의 안 됨 → 실패.
- 플라시보: P1 orig ≤ p95 · P2 orig ≤ max(+1, +5) · P3 orig ≤ 반전 · P4 p95 ≥ orig → 기각 · P1 실패 > 10 · P4 정의 < 190 → 폐기.
- §7-2: MDE = (z_{1−α} + z_{0.8})·σ/√n_eff(G0의 n_eff · max(ρ̂, 0.15)) · > 20 → 검정력 부족 · < 5 ∧ CI 상한 < 10 → 효과 부재 ·
  그 사이 → 결론 보류형 REJECT · MDE 정의 안 됨 → 검정력 부족.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import NormalDist

from backtest.stats import expected_max_sr
from strategies.trial02 import anchor as A

_N = NormalDist()
THETA = 10.0
G0_MIN_N, G0_MIN_NEFF, RHO_FLOOR = 48, 30.0, 0.15
GB_MIN_N = 30
P1_FAIL_MAX, P4_MIN_DEFINED = A.P1_FAIL_MAX, A.P4_MIN_DEFINED


def n_eff(n: int, rho: float) -> float:
    return n / (1 + 4 * max(rho, RHO_FLOOR))


def g0(n: int, rho: float) -> bool:
    return n >= G0_MIN_N and n_eff(n, rho) >= G0_MIN_NEFF


def sr_star(defined: Sequence[float]) -> float | None:
    return expected_max_sr(list(defined), A.N_TRIALS) if len(defined) >= 2 else None


def mde(sd: float | None, n: int, rho: float) -> float | None:
    if sd is None or n <= 0 or not math.isfinite(sd):
        return None
    return (_N.inv_cdf(1 - A.ALPHA) + _N.inv_cdf(0.80)) * sd / math.sqrt(n_eff(n, rho))


def classify(mde_v: float | None, net_ci_hi: float | None) -> str:
    if mde_v is None or mde_v > 2 * THETA:
        return "검정력 부족"
    if mde_v < 0.5 * THETA and net_ci_hi is not None and net_ci_hi < THETA:
        return "효과 부재"
    return "결론 보류형 REJECT"


@dataclass(frozen=True)
class ISInputs:
    v_a_empty: bool
    n_a: int
    liquidations_a: int
    rho: float
    mean_gross: float
    gross_ci_lo: float | None
    mean_net: float
    net_ci_lo: float | None
    net_ci_hi: float | None
    sd_net: float | None
    sr_a: float | None
    sr_b: float | None
    psr0_a: float | None
    p1_computable: bool
    p1_failures: int
    p1_p95: float | None
    p2_d1: float
    p2_d5: float
    p3_inv: float
    p4_defined: int
    p4_p95: float | None


@dataclass
class Verdict:
    label: str
    priority: int | None
    classification: str | None = None
    gates: dict[str, bool] = field(default_factory=dict)
    placebo_rejects: dict[str, bool] = field(default_factory=dict)
    sr_star: float | None = None
    sr_undefined: list[str] = field(default_factory=list)
    mde: float | None = None


def verdict_is(x: ISInputs) -> Verdict:
    bad = [k for k, v in x.__dict__.items() if isinstance(v, float) and not math.isfinite(v)
           and not (k in ("mean_gross", "mean_net") and x.n_a == 0)]
    if bad:
        raise ValueError(f"유한하지 않은 판정 입력: {bad}")     # NaN은 ≤/≥를 조용히 거짓으로 만든다(Codex 2g after #1)
    if x.v_a_empty:
        return Verdict("폐기", 0)
    if x.n_a == 0:
        return Verdict("REJECT(FAIL — 트레이드 0)", 1)
    if x.liquidations_a > 0:
        return Verdict("REJECT(생존)", 2)
    cands = {"SR_1A": A.SR_1A, "SR_1B": A.SR_1B, "SR_A": x.sr_a, "SR_B": x.sr_b}
    undefined = [k for k, v in cands.items() if v is None]
    star = sr_star([v for v in cands.values() if v is not None])
    gates = {
        "G0": g0(x.n_a, x.rho),
        "G1": x.mean_gross > 0 and x.gross_ci_lo is not None and x.gross_ci_lo > 0,
        "G2": x.mean_net > 0 and x.net_ci_lo is not None and x.net_ci_lo > 0,
        "G-B": (x.psr0_a is not None and x.psr0_a > 0.5 and x.n_a >= GB_MIN_N and x.sr_a is not None and star is not None
                and x.sr_a - star > 0),
        "flat": x.mean_net > 0,
    }
    m = mde(x.sd_net, x.n_a, x.rho)

    def out(label: str, prio: int | None, cls: str | None = None, rej: dict[str, bool] | None = None) -> Verdict:
        return Verdict(label, prio, cls, gates, rej or {}, star, undefined, m)

    if not all(gates.values()):
        return out("REJECT", 3, classify(m, x.net_ci_hi))
    if x.p1_failures > P1_FAIL_MAX or not x.p1_computable or x.p4_defined < P4_MIN_DEFINED or x.p1_p95 is None or x.p4_p95 is None:
        return out("폐기", 4)
    orig = x.mean_net
    rej = {"P1": orig <= x.p1_p95, "P2": orig <= max(x.p2_d1, x.p2_d5), "P3": orig <= x.p3_inv, "P4": x.p4_p95 >= orig}
    if any(rej.values()):
        return out("REJECT", 5, classify(m, x.net_ci_hi), rej)
    return out("IS PASS", None, None, rej)


def _finite_or_raise(**kw: float | None) -> None:
    bad = [k for k, v in kw.items() if v is not None and not math.isfinite(v)]
    if bad:
        raise ValueError(f"유한하지 않은 판정 입력: {bad}")


def verdict_oos(*, data_unavailable: bool, n: int, liquidations: int, rho: float, mean_net: float, net_ci_lo: float | None,
                net_ci_hi: float | None, sd_net: float | None) -> Verdict:
    """§7 OOS 행(사전확약 — 개봉은 사용자 승인 뒤 별도 단계)."""
    _finite_or_raise(rho=rho, mean_net=mean_net if n else 0.0, net_ci_lo=net_ci_lo, net_ci_hi=net_ci_hi, sd_net=sd_net)
    if data_unavailable:
        return Verdict("폐기(OOS 데이터)", 0)
    if n == 0:
        return Verdict("REJECT(FAIL — OOS 트레이드 0)", 1)
    if liquidations > 0:
        return Verdict("REJECT(생존)", 2)
    if not g0(n, rho):
        return Verdict("REJECT(OOS 표본 부족)", 3)
    if not (mean_net > 0 and net_ci_lo is not None and net_ci_lo > 0):
        return Verdict("REJECT", 4, classify(mde(sd_net, n, rho), net_ci_hi))
    return Verdict("OOS PASS", None)


def verdict_forward(*, liq_or_killswitch: int, exec_defect: bool, n_trades: int, mean_net_bps: float,
                    is_bh_beats: bool) -> Verdict:
    """§7 전진 행(사전확약 — 입력 어댑터는 활성화 때 레지스트리 행). `is_bh_beats` = IS 창에서 A 일간 Sharpe < 매수보유(엄격)."""
    _finite_or_raise(mean_net_bps=mean_net_bps if n_trades else 0.0)
    if liq_or_killswitch > 0:
        return Verdict("REJECT(생존 · 전진)", 1)
    if exec_defect:
        return Verdict("폐기(전진 실행 결함)", 2)
    if n_trades == 0:
        return Verdict("REJECT(FAIL — 전진 트레이드 0)", 3)
    if not mean_net_bps > 0:
        return Verdict("REJECT(전진 부호)", 4)
    return Verdict("ACCEPT — 수동(매수보유)을 이기지는 못함" if is_bh_beats else "ACCEPT", None)
