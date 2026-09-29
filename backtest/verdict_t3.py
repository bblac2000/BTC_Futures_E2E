"""트라이얼 #3 판정 순수 핵심(단계 2 (f) · 계획 r2 · 사전등록 §3 · §3-1 · §4 · §7 · §7-2) — 암마다 따로, 판정은 두 암의 쌍(§0 13행).

입력은 이미 계산된 float64 수와 bool뿐 — 파일·출처는 `evaluate_t3`(껍데기)가 다룬다.
- G0: n ≥ 48 ∧ n / (1 + 4·max(ρ̂, 0.15)) ≥ 30 · G1/G2: 평균 > 0 ∧ CI 하한 > 0(CI 정의 안 됨 → 실패) · flat: 평균 net > 0.
- G-B(§3 71행 · 두 암이 함께): PSR(0) > 0.5 ∧ n ≥ 30 ∧ SR̂ − SR* > 0 · SR* = expected_max_sr(정의된 {SR̂_#1A, #1B, #2A, #2B, SR̂_L, SR̂_S},
  n_trials = 6) · 정의된 값 < 2 또는 그 암의 SR̂·PSR 정의 안 됨 → 실패.
- 플라시보(§4): P1 orig ≤ p95 · P2 orig ≤ max(+1, +5) · P3 orig ≤ 반전 → 기각 · P1 실패 > 10 또는 계산 불가 → 폐기(IS(4)).
- §7 우선순위: IS(0) 폐기 → IS(1) 트레이드 0 → IS(2) 청산 ≥ 1 → IS(3) G0·G1·G2·G-B·flat → IS(4) P1 폐기 → IS(5) P1·P2·P3 기각 → IS PASS.
- §7-2(IS(3)·IS(5) REJECT에만): MDE = (z_{1−α} + z_{0.8})·σ/√n_eff(G0와 같은 n_eff · ρ 바닥 0.15) · > 20 → 검정력 부족 ·
  < 5 ∧ net CI 상한 < 10 → 효과 부재 · 그 사이 → 결론 보류형 REJECT · MDE 정의 안 됨 → 검정력 부족.
- 판정 문자열(§3-1 87행): `<라벨>[(§7-2: <분류>)] · 생존 <통과|실패>` — 생존 통과 ⇔ 관측된 청산 0(0건·IS(0)/OOS(0) 폐기 포함 · 계획 V6) ·
  트라이얼 문자열 `L: … | S: …` · INCONCLUSIVE 분류는 없다 · ACCEPT(와 접미어 "ACCEPT — 수동(매수보유)을 이기지는 못함")는 전진 단계에서만.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from statistics import NormalDist

from backtest.stats import expected_max_sr
from strategies.trial03 import anchor as A

_N = NormalDist()
THETA = 10.0
G0_MIN_N, G0_MIN_NEFF, RHO_FLOOR = 48, 30.0, 0.15
GB_MIN_N = 30
ARMS = ("L", "S")


def n_eff(n: int, rho: float) -> float:
    return n / (1 + 4 * max(rho, RHO_FLOOR))


def g0(n: int, rho: float) -> bool:
    return n >= G0_MIN_N and n_eff(n, rho) >= G0_MIN_NEFF


def sr_star(sr_by_arm: Mapping[str, float | None]) -> tuple[float | None, list[str]]:
    """SR* = expected_max_sr(고정 4 + 정의된 두 암, n_trials = 6) · 정의된 값 < 2 → None. 반환 둘째 = 정의 안 된 이름."""
    cands: dict[str, float | None] = {"SR_1A": A.SR_1A, "SR_1B": A.SR_1B, "SR_2A": A.SR_2A, "SR_2B": A.SR_2B,
                                      **{f"SR_{a}": sr_by_arm.get(a) for a in ARMS}}
    defined = [v for v in cands.values() if v is not None]
    undefined = [k for k, v in cands.items() if v is None]
    return (expected_max_sr(defined, A.N_TRIALS) if len(defined) >= 2 else None), undefined


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
class ArmInputs:
    v_empty: bool
    n: int
    liquidations: int
    rho: float
    mean_gross: float
    gross_ci_lo: float | None
    mean_net: float
    net_ci_lo: float | None
    net_ci_hi: float | None
    sd_net: float | None
    sr: float | None
    psr0: float | None
    p1_computable: bool
    p1_failures: int
    p1_p95: float | None
    p2_d1: float
    p2_d5: float
    p3_inv: float


@dataclass
class Verdict:
    label: str
    priority: int | None
    classification: str | None = None
    liquidations: int = 0
    gates: dict[str, bool] = field(default_factory=dict)
    placebo_rejects: dict[str, bool] = field(default_factory=dict)
    sr_star: float | None = None
    sr_undefined: list[str] = field(default_factory=list)
    mde: float | None = None

    @property
    def string(self) -> str:
        body = f"{self.label}(§7-2: {self.classification})" if self.classification else self.label
        return f"{body} · 생존 {'통과' if self.liquidations == 0 else '실패'}"


def _finite(x: ArmInputs) -> None:
    bad = [k for k, v in x.__dict__.items() if isinstance(v, float) and not math.isfinite(v)
           and not (k in ("mean_gross", "mean_net") and x.n == 0)]
    if bad:
        raise ValueError(f"유한하지 않은 판정 입력: {bad}")         # NaN은 비교를 조용히 거짓으로 만든다


def verdict_is(arms: Mapping[str, ArmInputs]) -> dict[str, Verdict]:
    """두 암을 함께 받는다(G-B의 SR*가 두 암의 SR̂를 쓴다 · §3 63·71행). 반환: 암 → Verdict."""
    if set(arms) != set(ARMS):
        raise ValueError(f"두 암이 모두 필요하다: {sorted(arms)}")
    for x in arms.values():
        _finite(x)
    star, undefined = sr_star({a: arms[a].sr for a in ARMS})
    return {a: _verdict_arm(arms[a], star, undefined) for a in ARMS}


def _verdict_arm(x: ArmInputs, star: float | None, undefined: list[str]) -> Verdict:
    if x.v_empty:
        return Verdict("폐기", 0, liquidations=x.liquidations)
    if x.n == 0:
        return Verdict("REJECT(FAIL — 트레이드 0)", 1, liquidations=x.liquidations)
    if x.liquidations > 0:
        return Verdict("REJECT(생존)", 2, liquidations=x.liquidations)
    gates = {
        "G0": g0(x.n, x.rho),
        "G1": x.mean_gross > 0 and x.gross_ci_lo is not None and x.gross_ci_lo > 0,
        "G2": x.mean_net > 0 and x.net_ci_lo is not None and x.net_ci_lo > 0,
        "G-B": (x.psr0 is not None and x.psr0 > 0.5 and x.n >= GB_MIN_N and x.sr is not None and star is not None
                and x.sr - star > 0),
        "flat": x.mean_net > 0,
    }
    m = mde(x.sd_net, x.n, x.rho)

    def out(label: str, prio: int | None, cls: str | None = None, rej: dict[str, bool] | None = None) -> Verdict:
        return Verdict(label, prio, cls, x.liquidations, gates, rej or {}, star, list(undefined), m)

    if not all(gates.values()):
        return out("REJECT", 3, classify(m, x.net_ci_hi))
    if x.p1_failures > A.P1_FAIL_MAX or not x.p1_computable or x.p1_p95 is None:
        return out("폐기", 4)
    orig = x.mean_net
    rej = {"P1": orig <= x.p1_p95, "P2": orig <= max(x.p2_d1, x.p2_d5), "P3": orig <= x.p3_inv}
    if any(rej.values()):
        return out("REJECT", 5, classify(m, x.net_ci_hi), rej)
    return out("IS PASS", None, None, rej)


def trial_string(v: Mapping[str, Verdict]) -> str:
    return " | ".join(f"{a}: {v[a].string}" for a in ARMS)


def _finite_or_raise(**kw: float | None) -> None:
    bad = [k for k, v in kw.items() if v is not None and not math.isfinite(v)]
    if bad:
        raise ValueError(f"유한하지 않은 판정 입력: {bad}")


def verdict_oos(*, data_unavailable: bool, v_empty: bool, n: int, liquidations: int, rho: float, mean_net: float,
                net_ci_lo: float | None, net_ci_hi: float | None, sd_net: float | None) -> Verdict:
    """§7 OOS 행(사전확약 — 개봉은 사용자 결정 레지스트리 행 뒤 · `prepare_t3.oos_range`)."""
    _finite_or_raise(rho=rho, mean_net=mean_net, net_ci_lo=net_ci_lo, net_ci_hi=net_ci_hi, sd_net=sd_net)
    if data_unavailable or v_empty:
        return Verdict("폐기(OOS 데이터)", 0, liquidations=liquidations)
    if n == 0:
        return Verdict("REJECT(FAIL — OOS 트레이드 0)", 1, liquidations=liquidations)
    if liquidations > 0:
        return Verdict("REJECT(생존)", 2, liquidations=liquidations)
    if not g0(n, rho):
        return Verdict("REJECT(OOS 표본 부족)", 3, liquidations=liquidations)
    if not (mean_net > 0 and net_ci_lo is not None and net_ci_lo > 0):
        return Verdict("REJECT", 4, classify(mde(sd_net, n, rho), net_ci_hi), liquidations=liquidations)
    return Verdict("OOS PASS", None, liquidations=liquidations)


def verdict_forward(*, liquidations: int, killswitch: int, exec_defect: bool, n_trades: int, mean_net_bps: float,
                    is_bh_beats: bool) -> Verdict:
    """§7 전진 행(사전확약). `is_bh_beats` = IS 창에서 암 일간 Sharpe < 매수보유 일간 Sharpe(엄격) — 접미어는 ACCEPT일 때만(143행)."""
    _finite_or_raise(mean_net_bps=mean_net_bps)
    if liquidations > 0 or killswitch > 0:
        return Verdict("REJECT(생존 · 전진)", 1, liquidations=liquidations)
    if exec_defect:
        return Verdict("폐기(전진 실행 결함)", 2, liquidations=liquidations)
    if n_trades == 0:
        return Verdict("REJECT(FAIL — 전진 트레이드 0)", 3, liquidations=liquidations)
    if not mean_net_bps > 0:
        return Verdict("REJECT(전진 부호)", 4, liquidations=liquidations)
    return Verdict("ACCEPT — 수동(매수보유)을 이기지는 못함" if is_bh_beats else "ACCEPT", None, liquidations=liquidations)


__all__ = ["ArmInputs", "Verdict", "classify", "g0", "mde", "n_eff", "sr_star", "trial_string", "verdict_forward", "verdict_is",
           "verdict_oos"]
