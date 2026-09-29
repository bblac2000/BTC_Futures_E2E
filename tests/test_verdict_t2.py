"""트라이얼 #2 판정 순수 핵심(단계 2g H8~H10 · 사전등록 §3 · §3-1 · §4 · §7 · §7-2) — 진리표·경계 시험."""
from __future__ import annotations

from dataclasses import replace

import pytest

from backtest import verdict_t2 as V

SR1A, SR1B = -0.23802981743207333, -0.23471514010093758


def good() -> V.ISInputs:
    return V.ISInputs(v_a_empty=False, n_a=400, liquidations_a=0, rho=0.05, mean_gross=40.0, gross_ci_lo=10.0,
                      mean_net=25.0, net_ci_lo=5.0, net_ci_hi=45.0, sd_net=120.0, sr_a=0.6, sr_b=0.55, psr0_a=0.99,
                      p1_computable=True, p1_failures=0, p1_p95=3.0, p2_d1=1.0, p2_d5=-2.0, p3_inv=-20.0,
                      p4_defined=200, p4_p95=8.0)


def test_all_pass_is_is_pass():
    v = V.verdict_is(good())
    assert v.label == "IS PASS" and v.priority is None and v.classification is None


@pytest.mark.parametrize("kw,label,prio", [
    (dict(v_a_empty=True, n_a=0), "폐기", 0),
    (dict(n_a=0), "REJECT(FAIL — 트레이드 0)", 1),
    (dict(liquidations_a=1), "REJECT(생존)", 2),
    (dict(liquidations_a=1, mean_net=-5.0), "REJECT(생존)", 2),                    # 생존이 게이트 실패보다 먼저
    (dict(mean_net=-1.0, net_ci_lo=-10.0), "REJECT", 3),
    (dict(p1_failures=11), "폐기", 4),
    (dict(p1_failures=11, mean_net=-1.0, net_ci_lo=-9.0), "REJECT", 3),          # 원판 게이트 실패가 하네스 결함보다 먼저
    (dict(p4_defined=189), "폐기", 4),
    (dict(p1_p95=25.0), "REJECT", 5),
])
def test_precedence_rows(kw, label, prio):
    v = V.verdict_is(replace(good(), **kw))
    assert (v.label, v.priority) == (label, prio)


def test_boundaries_inclusive_as_registered():
    assert V.verdict_is(replace(good(), p1_failures=10)).label == "IS PASS"
    assert V.verdict_is(replace(good(), p4_defined=190)).label == "IS PASS"
    assert V.verdict_is(replace(good(), p1_p95=25.0)).priority == 5                     # orig ≤ p95(같음) → 기각
    assert V.verdict_is(replace(good(), p2_d5=25.0)).priority == 5                      # orig ≤ max(+1,+5)
    assert V.verdict_is(replace(good(), p3_inv=25.0)).priority == 5
    assert V.verdict_is(replace(good(), p4_p95=25.0)).priority == 5                     # p95 ≥ orig
    assert V.verdict_is(replace(good(), p4_p95=24.999)).label == "IS PASS"


def test_g0_boundaries():
    assert V.g0(48, 0.0) and not V.g0(47, 0.0)                                           # 48/1.6 = 30
    assert V.g0(90, 0.5) and not V.g0(89, 0.5)                                           # 90/3 = 30
    assert V.g0(48, -0.9)                                                                # 음수 ρ̂ → 0.15


def test_gb_rules():
    assert V.sr_star([SR1A, SR1B, 0.6, 0.55]) is not None
    v = V.verdict_is(replace(good(), sr_a=0.2, sr_b=0.18))
    assert v.gates["G-B"] is False                                                      # SR̂_A − SR* < 0(분산이 SR*를 키운다 · §3 공시)
    assert V.sr_star([0.2]) is None                                                      # 정의된 값 < 2 → G-B 실패
    v = V.verdict_is(replace(good(), n_a=29, rho=0.0))
    assert v.gates["G-B"] is False
    v = V.verdict_is(replace(good(), sr_a=None, psr0_a=None))
    assert v.gates["G-B"] is False and v.priority == 3
    v = V.verdict_is(replace(good(), sr_b=None))
    assert v.sr_undefined == ["SR_B"] and v.sr_star == V.sr_star([SR1A, SR1B, 0.6])       # 세 값으로 계산                         # 세 값으로 계산


def test_ci_undefined_fails_gate():
    v = V.verdict_is(replace(good(), gross_ci_lo=None))
    assert v.gates["G1"] is False and v.priority == 3


@pytest.mark.parametrize("sd,ci_hi,expect", [(None, 5.0, "검정력 부족"), (1e9, 5.0, "검정력 부족"),
                                             (1e-6, 5.0, "효과 부재"), (1e-6, 15.0, "결론 보류형 REJECT")])
def test_classification(sd, ci_hi, expect):
    v = V.verdict_is(replace(good(), mean_net=-1.0, net_ci_lo=-3.0, net_ci_hi=ci_hi, sd_net=sd))
    assert v.classification == expect


def test_mde_exact_thresholds():
    assert V.classify(20.0, 100.0) == "결론 보류형 REJECT"            # MDE = 20 → "> 20"이 아니다
    assert V.classify(20.0001, 100.0) == "검정력 부족"
    assert V.classify(5.0, 1.0) == "결론 보류형 REJECT"               # MDE = 5 → "< 5"가 아니다
    assert V.classify(4.9999, 9.9999) == "효과 부재"
    assert V.classify(4.9999, 10.0) == "결론 보류형 REJECT"           # CI 상한 < θ 엄격


def test_mde_uses_g0_neff_with_floor():
    m = V.mde(100.0, 400, -0.5)
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - 0.0125) + NormalDist().inv_cdf(0.8)
    assert m == pytest.approx(z * 100.0 / (400 / (1 + 4 * 0.15)) ** 0.5)


@pytest.mark.parametrize("kw,label", [
    (dict(data_unavailable=True), "폐기(OOS 데이터)"), (dict(n=0), "REJECT(FAIL — OOS 트레이드 0)"),
    (dict(liquidations=1), "REJECT(생존)"), (dict(n=40), "REJECT(OOS 표본 부족)"),
    (dict(net_ci_lo=-1.0), "REJECT"), (dict(), "OOS PASS")])
def test_oos_function(kw, label):
    base = dict(data_unavailable=False, n=60, liquidations=0, rho=0.0, mean_net=10.0, net_ci_lo=1.0, net_ci_hi=20.0, sd_net=50.0)
    assert V.verdict_oos(**(base | kw)).label == label


@pytest.mark.parametrize("kw,label", [
    (dict(liq_or_killswitch=1, exec_defect=True), "REJECT(생존 · 전진)"), (dict(exec_defect=True), "폐기(전진 실행 결함)"),
    (dict(n_trades=0), "REJECT(FAIL — 전진 트레이드 0)"), (dict(mean_net_bps=0.0), "REJECT(전진 부호)"),
    (dict(), "ACCEPT"), (dict(is_bh_beats=True), "ACCEPT — 수동(매수보유)을 이기지는 못함")])
def test_forward_function(kw, label):
    base = dict(liq_or_killswitch=0, exec_defect=False, n_trades=5, mean_net_bps=3.0, is_bh_beats=False)
    assert V.verdict_forward(**(base | kw)).label == label
