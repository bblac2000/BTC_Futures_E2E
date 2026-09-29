"""트라이얼 #3 (f) 판정 순수 핵심 — §7 IS 행마다(두 암 각각 · 다른 암 {0건, SR̂ 정의}) · §7-2 분류 · G-B 두 암 결합 · OOS·전진 · 문자열(합성 수만)."""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pytest

from backtest import verdict_t3 as V
from backtest.stats import expected_max_sr
from strategies.trial03 import anchor as A

PASSING = V.ArmInputs(v_empty=False, n=400, liquidations=0, rho=0.0, mean_gross=40.0, gross_ci_lo=20.0, mean_net=18.0, net_ci_lo=6.0,
                      net_ci_hi=30.0, sd_net=40.0, sr=0.45, psr0=0.99, p1_computable=True, p1_failures=0, p1_p95=5.0,
                      p2_d1=2.0, p2_d5=1.0, p3_inv=-20.0)
ZERO = replace(PASSING, n=0, mean_gross=math.nan, mean_net=math.nan, gross_ci_lo=None, net_ci_lo=None, net_ci_hi=None, sd_net=None,
               sr=None, psr0=None, p1_computable=False, p1_p95=None)
OTHERS = {"zero": ZERO, "defined": replace(PASSING, sr=0.1)}


def run(arm: str, x: V.ArmInputs, other: str = "defined") -> V.Verdict:
    o = "S" if arm == "L" else "L"
    return V.verdict_is({arm: x, o: OTHERS[other]})[arm]


@pytest.mark.parametrize("arm", ["L", "S"])
@pytest.mark.parametrize("other", ["zero", "defined"])
@pytest.mark.parametrize("x,label,prio,cls", [
    (replace(PASSING, v_empty=True), "폐기", 0, None),
    (ZERO, "REJECT(FAIL — 트레이드 0)", 1, None),
    (replace(PASSING, liquidations=1), "REJECT(생존)", 2, None),
    (replace(PASSING, n=40), "REJECT", 3, "검정력 부족"),                             # G0 실패(n < 48 · MDE ≈ 25.9 > 20)
    (replace(PASSING, gross_ci_lo=-1.0), "REJECT", 3, "결론 보류형 REJECT"),           # G1
    (replace(PASSING, net_ci_lo=None), "REJECT", 3, "결론 보류형 REJECT"),             # G2(CI 정의 안 됨)
    (replace(PASSING, psr0=None), "REJECT", 3, "결론 보류형 REJECT"),                  # G-B 정의 안 됨
    (replace(PASSING, p1_failures=11), "폐기", 4, None),
    (replace(PASSING, p1_computable=False), "폐기", 4, None),
    (replace(PASSING, p1_p95=18.0), "REJECT", 5, "결론 보류형 REJECT"),                # P1 경계 포함(≤)
    (replace(PASSING, p2_d5=18.0), "REJECT", 5, "결론 보류형 REJECT"),                 # P2
    (replace(PASSING, p3_inv=18.0), "REJECT", 5, "결론 보류형 REJECT"),                # P3
    (PASSING, "IS PASS", None, None),
])
def test_every_section7_is_row_per_arm(arm, other, x, label, prio, cls):
    v = run(arm, x, other)
    assert (v.label, v.priority, v.classification) == (label, prio, cls)


@pytest.mark.parametrize("sd,hi,cls", [(200.0, 30.0, "검정력 부족"), (None, 30.0, "검정력 부족"),
                                       (5.0, 8.0, "효과 부재"), (5.0, 12.0, "결론 보류형 REJECT"), (40.0, 30.0, "결론 보류형 REJECT")])
def test_section7_2_classes(sd, hi, cls):
    v = run("L", replace(PASSING, net_ci_lo=-1.0, sd_net=sd, net_ci_hi=hi))
    assert v.label == "REJECT" and v.classification == cls


def test_gb_uses_both_arms_and_drops_undefined():
    v = V.verdict_is({"L": ZERO, "S": PASSING})
    pinned = [A.SR_1A, A.SR_1B, A.SR_2A, A.SR_2B]
    assert v["S"].sr_star == expected_max_sr(pinned + [0.45], 6) and v["S"].sr_undefined == ["SR_L"]
    both = V.verdict_is({"L": replace(PASSING, sr=0.3), "S": PASSING})
    assert both["S"].sr_star == expected_max_sr(pinned + [0.3, 0.45], 6)
    hi = V.verdict_is({"L": replace(PASSING, sr=5.0), "S": PASSING})           # L의 SR̂가 S의 G-B를 떨어뜨린다(공시된 의존)
    assert hi["S"].gates["G-B"] is False and hi["S"].label == "REJECT"


def test_strings():
    v = V.verdict_is({"L": replace(PASSING, n=40), "S": PASSING})
    assert v["L"].string == "REJECT(§7-2: 검정력 부족) · 생존 통과" and v["S"].string == "IS PASS · 생존 통과"
    assert V.trial_string(v) == "L: REJECT(§7-2: 검정력 부족) · 생존 통과 | S: IS PASS · 생존 통과"
    liq = V.verdict_is({"L": replace(PASSING, liquidations=2), "S": replace(PASSING, v_empty=True)})
    assert liq["L"].string == "REJECT(생존) · 생존 실패" and liq["S"].string == "폐기 · 생존 통과"
    assert "INCONCLUSIVE" not in V.trial_string(liq)


def test_nonfinite_input_is_refused():
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


def test_mde_uses_g0_neff_with_floor():
    assert V.mde(40.0, 400, 0.0) == pytest.approx((2.3940 + 0.8416) * 40.0 / math.sqrt(400 / 1.6), rel=1e-3)
