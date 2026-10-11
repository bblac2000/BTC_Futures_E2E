"""트라이얼 #4 (f) 판정 순수 핵심 — §7 IS 행마다(두 암 각각) · §7-2 부호 우선 분류 · G-B 두 암 결합(N = 8) · OOS·전진 · 문자열(규약 E57·E58·E65). 합성 수만."""
from __future__ import annotations

import dataclasses
import math
from dataclasses import replace
from typing import Any

import pytest

from backtest import verdict_t4 as V
from backtest.stats import expected_max_sr
from strategies.trial04 import anchor as A

PASSING = V.ArmInputs(v_empty=False, n=400, liquidations=0, rho=0.0, mean_gross=40.0, gross_ci_lo=20.0, mean_net=18.0, net_ci_lo=6.0,
                      net_ci_hi=30.0, sd_net=40.0, sr=0.45, psr0=0.99, p1_computable=True, p1_failures=0, p1_p95=5.0,
                      p2_p1=2.0, p2_p3=1.0, p3_inv=-20.0)
ZERO = replace(PASSING, n=0, mean_gross=math.nan, mean_net=math.nan, gross_ci_lo=None, net_ci_lo=None, net_ci_hi=None, sd_net=None,
               sr=None, psr0=None, p1_computable=False, p1_p95=None)
OTHERS = {"zero": ZERO, "defined": replace(PASSING, sr=0.1)}


def run(arm: str, x: V.ArmInputs, other: str = "defined") -> V.Verdict:
    o = "S" if arm == "L" else "L"
    return V.verdict_is({arm: x, o: OTHERS[other]})[arm]


def test_constants_and_arm_order():
    assert V.ARMS == ("S", "L") and (V.G0_MIN_N, V.G0_MIN_NEFF, V.RHO_FLOOR, V.GB_MIN_N, V.THETA) == (48, 30.0, 0.15, 30, 10.0)
    assert A.N_TRIALS == 8 and A.ALPHA == 0.00625 and A.P1_FAIL_MAX == 10


def test_arm_inputs_have_no_timing_field():
    names = {f.name for f in dataclasses.fields(V.ArmInputs)}
    assert not [n for n in names if "timing" in n] and {"p1_p95", "p1_failures", "p1_computable", "p2_p1", "p2_p3", "p3_inv"} <= names


@pytest.mark.parametrize("arm", ["S", "L"])
@pytest.mark.parametrize("other", ["zero", "defined"])
@pytest.mark.parametrize("x,label,prio,cls", [
    (replace(PASSING, v_empty=True), "폐기", 0, None),
    (ZERO, "REJECT(FAIL — 트레이드 0)", 1, None),
    (replace(PASSING, liquidations=1), "REJECT(생존)", 2, None),
    (replace(PASSING, n=40), "REJECT", 3, "검정력 부족"),                             # G0 실패(n < 48 · MDE > 20)
    (replace(PASSING, gross_ci_lo=-1.0), "REJECT", 3, "결론 보류형 REJECT"),           # G1
    (replace(PASSING, net_ci_lo=None), "REJECT", 3, "결론 보류형 REJECT"),             # G2(CI 하한 없음 · 상한 30 → ① 아님)
    (replace(PASSING, psr0=None), "REJECT", 3, "결론 보류형 REJECT"),                  # G-B 정의 안 됨
    (replace(PASSING, p1_failures=11), "폐기", 4, None),
    (replace(PASSING, p1_failures=10), "IS PASS", None, None),                        # 실패 10은 허용(> 10만 폐기)
    (replace(PASSING, p1_computable=False), "폐기", 4, None),
    (replace(PASSING, p1_p95=18.0), "REJECT", 5, "결론 보류형 REJECT"),                # P1 경계 포함(≤)
    (replace(PASSING, p2_p1=18.0), "REJECT", 5, "결론 보류형 REJECT"),                 # P2 +1 인쇄
    (replace(PASSING, p2_p3=18.0), "REJECT", 5, "결론 보류형 REJECT"),                 # P2 +3 인쇄(max)
    (replace(PASSING, p3_inv=18.0), "REJECT", 5, "결론 보류형 REJECT"),                # P3
    (PASSING, "IS PASS", None, None),
])
def test_every_section7_is_row_per_arm(arm, other, x, label, prio, cls):
    v = run(arm, x, other)
    assert (v.label, v.priority, v.classification) == (label, prio, cls)


def test_priority_order_survival_before_gates_and_gates_before_placebo():
    assert run("S", replace(PASSING, liquidations=1, n=40, p1_failures=11)).priority == 2
    assert run("S", replace(PASSING, n=40, p1_failures=11)).priority == 3
    assert run("S", replace(PASSING, p1_failures=11, p3_inv=99.0)).priority == 4


@pytest.mark.parametrize("lo,hi,sd,cls", [
    (-30.0, -2.0, 200.0, "효과 부재(음의 효과)"),          # ① 부호 우선: MDE가 커도(검정력 부족 조건) CI 전부 음수면 음의 효과
    (-30.0, -2.0, 5.0, "효과 부재(음의 효과)"),            # ① 이 ③보다 먼저
    (-30.0, -2.0, None, "효과 부재(음의 효과)"),           # ① MDE 정의 안 됨이어도(sd = 0 퇴화)
    (-30.0, 0.0, 200.0, "검정력 부족"),                    # 상한 = 0은 "전부 0 아래"가 아니다(엄격)
    (-1.0, 30.0, 200.0, "검정력 부족"), (-1.0, 30.0, None, "검정력 부족"),
    (-1.0, 8.0, 5.0, "효과 부재"), (-1.0, 12.0, 5.0, "결론 보류형 REJECT"), (-1.0, 30.0, 40.0, "결론 보류형 REJECT"),
])
def test_section7_2_sign_first_classes(lo, hi, sd, cls):
    v = run("L", replace(PASSING, net_ci_lo=lo, net_ci_hi=hi, sd_net=sd, mean_net=1.0))
    assert v.label == "REJECT" and v.priority == 3 and v.classification == cls


def test_sign_first_is_skipped_when_the_ci_is_undefined():
    v = run("L", replace(PASSING, net_ci_lo=None, net_ci_hi=None, sd_net=200.0, mean_net=-5.0, mean_gross=-1.0))
    assert v.classification == "검정력 부족"
    assert V.classify(None, None) == "검정력 부족" and V.classify(3.0, None) == "결론 보류형 REJECT"
    assert {V.classify(1.0, -1.0), V.classify(30.0, 5.0), V.classify(1.0, 5.0), V.classify(10.0, 5.0)} == \
        {"효과 부재(음의 효과)", "검정력 부족", "효과 부재", "결론 보류형 REJECT"}


def test_gb_uses_six_pinned_and_both_arms_with_n_trials_8():
    pinned = list(A.PINNED_SR)
    assert len(pinned) == 6
    v = V.verdict_is({"L": ZERO, "S": PASSING})
    assert v["S"].sr_star == expected_max_sr(pinned + [0.45], 8) and v["S"].sr_undefined == ["SR_L"]
    both = V.verdict_is({"S": PASSING, "L": replace(PASSING, sr=0.3)})
    assert both["S"].sr_star == expected_max_sr(pinned + [0.45, 0.3], 8) == both["L"].sr_star
    hi = V.verdict_is({"L": replace(PASSING, sr=5.0), "S": PASSING})           # L의 SR̂가 S의 G-B를 떨어뜨린다(공시된 의존)
    assert hi["S"].gates["G-B"] is False and hi["S"].label == "REJECT"
    assert run("S", replace(PASSING, n=29, rho=-1.0)).gates["G-B"] is False     # n ≥ 30


def test_strings_are_s_first():
    v = V.verdict_is({"L": replace(PASSING, n=40), "S": PASSING})
    assert v["L"].string == "REJECT(§7-2: 검정력 부족) · 생존 통과" and v["S"].string == "IS PASS · 생존 통과"
    assert V.trial_string(v) == "S: IS PASS · 생존 통과 | L: REJECT(§7-2: 검정력 부족) · 생존 통과"
    liq = V.verdict_is({"L": replace(PASSING, liquidations=2), "S": replace(PASSING, v_empty=True)})
    assert liq["L"].string == "REJECT(생존) · 생존 실패" and liq["S"].string == "폐기 · 생존 통과"
    neg = V.verdict_is({"S": replace(PASSING, net_ci_lo=-9.0, net_ci_hi=-1.0, mean_net=-5.0), "L": PASSING})
    assert neg["S"].string == "REJECT(§7-2: 효과 부재(음의 효과)) · 생존 통과"
    assert "INCONCLUSIVE" not in V.trial_string(liq)


def test_nonfinite_input_is_refused_and_both_arms_are_required():
    with pytest.raises(ValueError):
        run("L", replace(PASSING, mean_net=math.inf))
    with pytest.raises(ValueError):
        V.verdict_is({"L": PASSING})


def _oos(**over: Any) -> V.Verdict:
    kw: dict[str, Any] = dict(data_unavailable=False, v_empty=False, n=60, liquidations=0, rho=0.0, mean_net=10.0, net_ci_lo=1.0,
                              net_ci_hi=20.0, sd_net=30.0)
    kw.update(over)
    return V.verdict_oos(**kw)


def test_oos_rows():
    assert _oos().string == "OOS PASS · 생존 통과"
    assert _oos(data_unavailable=True).label == "폐기(OOS 데이터)"
    assert _oos(n=0).label == "REJECT(FAIL — OOS 트레이드 0)"
    assert _oos(liquidations=1).string == "REJECT(생존) · 생존 실패"
    assert _oos(n=40).label == "REJECT(OOS 표본 부족)"
    assert _oos(net_ci_lo=-1.0).label == "REJECT"
    assert _oos(net_ci_lo=-9.0, net_ci_hi=-1.0, mean_net=-5.0).classification == "효과 부재(음의 효과)"


def _fwd(**over: Any) -> V.Verdict:
    kw: dict[str, Any] = dict(liquidations=0, killswitch=0, exec_defect=False, n_trades=20, mean_net_bps=5.0, is_bh_beats=False)
    kw.update(over)
    return V.verdict_forward(**kw)


def test_forward_rows_and_bh_suffix_only_on_accept():
    assert _fwd().label == "ACCEPT"
    assert _fwd(is_bh_beats=True).label == "ACCEPT — 수동(매수보유)을 이기지는 못함"
    assert _fwd(killswitch=1, is_bh_beats=True).label == "REJECT(생존 · 전진)"
    assert _fwd(exec_defect=True).label == "폐기(전진 실행 결함)"
    assert _fwd(n_trades=0).label == "REJECT(FAIL — 전진 트레이드 0)"
    assert _fwd(mean_net_bps=0.0, is_bh_beats=True).label == "REJECT(전진 부호)"


def test_mde_uses_g0_neff_with_floor_and_alpha_over_8():
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - 0.05 / 8) + NormalDist().inv_cdf(0.80)
    assert V.mde(40.0, 400, 0.0) == pytest.approx(z * 40.0 / math.sqrt(400 / 1.6), rel=1e-12)
    assert V.mde(None, 400, 0.0) is None and V.n_eff(48, 0.0) == 30.0 and V.g0(48, 0.15) and not V.g0(47, 0.0) and not V.g0(48, 0.16)
