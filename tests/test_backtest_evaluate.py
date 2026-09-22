"""단계 e 판정기 — 합성 입력만(실데이터·실행 산출물은 읽지 않는다). 게이트마다 통과/실패 경계 · 판정 · 결정론 · 열기 전 거부."""
from __future__ import annotations

import json
import random
from decimal import Decimal
from typing import Any

import pytest

from backtest import evaluate as E
from backtest import placebo as PL
from backtest.data import MINUTE_MS
from strategies.trial01 import anchor as A

D = Decimal
DAY = 86_400_000
T0 = A.IS_START_MS
END = T0 + 200 * DAY - 1
RS = 400                                             # 테스트용 재표본 수(속도)


def trades(nets, *, gross_add=14.0, spacing_days=1.0, hold_min=90, seed=None, start=T0):
    out = []
    for i, x in enumerate(nets):
        t = int(start + i * spacing_days * DAY) + 3_600_000
        out.append(E.Trade(t, t + hold_min * MINUTE_MS, x + gross_add, x, D(str(round(x / 10, 6))), "tp" if x > 0 else "sl"))
    return out


def noisy(n, mean, sd, seed=1):
    r = random.Random(seed)
    return [r.gauss(mean, sd) for _ in range(n)]


# ── G0 ──────────────────────────────────────────────────────────────────────
def test_g0_needs_48_trades_and_uses_max_of_rho_and_plan():
    assert not E.g0(noisy(47, 5, 30))["pass"]
    g = E.g0(noisy(48, 5, 30))
    assert g["rho_used"] >= 0.15 and g["pass"] == (48 / (1 + 4 * g["rho_used"]) >= 30)
    trend = [float(i) for i in range(100)]                       # ρ̂ ≈ 1 → n_eff = 100/5 = 20 < 30
    g = E.g0(trend)
    assert g["rho_hat"] > 0.9 and not g["pass"]
    neg = [(-1.0) ** i for i in range(60)]                       # ρ̂ < 0는 0.15로(부풀리지 않는다)
    g = E.g0(neg)
    assert g["rho_hat"] < 0 and g["rho_used"] == 0.15 and g["n_eff"] == pytest.approx(60 / 1.6)


# ── G1·G2 ──────────────────────────────────────────────────────────────────
def test_g2_passes_on_a_clear_positive_edge_and_fails_when_ci_crosses_zero():
    good = trades(noisy(150, 25, 20))
    ci = E.ci_gate(E.mean_ci(good, "net_bps", "net_A", T0, END, RS))
    assert ci["pass"] and ci["lo"] > 0
    weak = trades(noisy(150, 1, 60))
    ci = E.ci_gate(E.mean_ci(weak, "net_bps", "net_A", T0, END, RS))
    assert not ci["pass"]


def test_bootstrap_uses_fixed_child_streams():
    t = trades(noisy(80, 5, 20))
    a = E.mean_ci(t, "net_bps", "net_A", T0, END, RS)
    b = E.mean_ci(t, "net_bps", "net_A", T0, END, RS)
    c = E.mean_ci(t, "net_bps", "net_B", T0, END, RS)
    assert a == b and (a.lo, a.hi) != (c.lo, c.hi)


# ── G-B · A/B ───────────────────────────────────────────────────────────────
def test_gate_b_requires_psr_n_and_shrunk_sharpe():
    a, b = noisy(120, 20, 30, 1), noisy(120, 0, 30, 2)
    g = E.gate_b(a, b)
    assert g["psr_0"] > 0.5 and g["dsr_shrunk"] == pytest.approx(g["sr_A"] - g["sr_star"]) and g["pass"]
    assert not E.gate_b(a[:29], b)["pass"]                                     # n < 30
    g = E.gate_b(noisy(120, -5, 30, 3), b)
    assert not g["pass"]


def test_ab_needs_b_power_and_positive_paired_ci():
    a = trades(noisy(150, 25, 20, 1))
    b = trades(noisy(150, 0, 20, 2), spacing_days=1.0)
    g0b = E.g0([t.net_bps for t in b])
    r = E.ab_compare(a, b, T0, END, g0b, RS)
    assert r["pass"] and r["mean_A"] > r["mean_B"] and r["lo"] > 0
    r = E.ab_compare(a, b, T0, END, g0b | {"pass": False}, RS)
    assert not r["pass"]                                                      # 전제 실패


# ── 플라시보 ────────────────────────────────────────────────────────────────
def test_placebo_rules_match_the_preregistration():
    p = E.placebos(20.0, [0.0] * 1000, 0, (5.0, 3.0), -20.0, [1.0] * 200)
    assert not any(p[k]["reject"] for k in ("P1", "P2", "P3", "P4"))
    assert E.placebos(20.0, [25.0] * 1000, 0, (5.0, 3.0), -20.0, [1.0] * 200)["P1"]["reject"]
    assert E.placebos(20.0, [0.0] * 1000, 0, (21.0, 3.0), -20.0, [1.0] * 200)["P2"]["reject"]
    assert E.placebos(20.0, [0.0] * 1000, 0, (5.0, 3.0), 20.0, [1.0] * 200)["P3"]["reject"]
    assert E.placebos(20.0, [0.0] * 1000, 0, (5.0, 3.0), -20.0, [20.0] * 200)["P4"]["reject"]
    p = E.placebos(20.0, [0.0] * 989, 11, (5.0, 3.0), -20.0, [1.0] * 200)
    assert not p["P1"]["evaluable"]


# ── 판정 · §7 ────────────────────────────────────────────────────────────────
def _bars_close(days, drift):
    out, px = [], D(60000)
    for d in range(days):
        px = px * (1 + D(str(drift)))
        out.append((T0 + d * DAY + 23 * 3_600_000, px))
    return out


def _eval(a, b, **kw):
    base: dict[str, Any] = dict(p2=(0.0, 0.0), p3=-10.0, p1_means=[0.0] * 1000, p1_failures=0, p4_means=[0.0] * 200,
                bars_close=_bars_close(200, "0.0001"), start_ms=T0, end_ms=END, equity0=D(1000), resamples=RS)
    return E.evaluate(a, b, **(base | kw))


def test_zero_trades_is_immediate_fail():
    assert _eval([], [])["verdict"]["is_verdict"].startswith("FAIL")


def test_all_pass_is_is_pass_never_accept_and_label_is_reported():
    a = trades(noisy(150, 25, 20, 1))
    b = trades(noisy(150, 0, 20, 2))
    g = _eval(a, b)
    assert g["verdict"]["is_verdict"].startswith("IS PASS") and "ACCEPT" not in g["verdict"]["is_verdict"]
    assert "label_if_accepted" in g["verdict"]


def test_p1_unevaluable_is_discard_not_reject():
    a = trades(noisy(150, 25, 20, 1))
    g = _eval(a, trades(noisy(150, 0, 20, 2)), p1_means=[0.0] * 980, p1_failures=20)
    assert g["verdict"]["is_verdict"].startswith("폐기")


def test_reject_carries_the_section7_classification():
    a = trades(noisy(150, 25, 20, 1))
    g = _eval(a, trades(noisy(150, 0, 20, 2)), p3=30.0)                     # P3 기각
    v = g["verdict"]
    assert v["is_verdict"] == "REJECT" and v["failed"] == ["P3"] and v["classification"]["kind"] in (
        "검정력 부족", "효과 부재", "결론 보류형 REJECT")


def test_classification_thresholds():
    assert E.classify_reject(noisy(40, 0, 200), 25.0, 50.0)["kind"] == "검정력 부족"
    assert E.classify_reject(noisy(20000, 0, 5), 12500.0, 3.0)["kind"] == "효과 부재"
    assert E.classify_reject(noisy(20000, 0, 5), 12500.0, 12.0)["kind"] == "결론 보류형 REJECT"   # CI가 θ를 배제 못 함


def test_evaluate_is_deterministic():
    a = trades(noisy(120, 10, 25, 1))
    b = trades(noisy(120, 2, 25, 2))
    assert json.dumps(_eval(a, b), sort_keys=True, default=str) == json.dumps(_eval(a, b), sort_keys=True, default=str)


# ── 보고 부록 ────────────────────────────────────────────────────────────────
def test_holding_skip_rates_and_benchmarks():
    h = E.holding(trades([1.0] * 10, hold_min=120))
    assert h["median"] == 120 and h["share_ge_60min"] == 1.0
    s = E.skip_rates({"candidates": 10, "decision_counts": {"sl_dist_out_of_range": 5, "no_sl_anchor": 1, "conflict_signal": 2}})
    assert (s["sl_dist_out_of_range"], s["no_sl_anchor"], s["conflict_signal"]) == (0.5, 0.1, 0.2)
    bh = E.buy_hold(_bars_close(10, "0.01"))
    assert bh["window_return"] == pytest.approx(1.01 ** 9 - 1)
    sd = E.strategy_daily(trades([10.0, -10.0]), D(1000), T0, T0 + 3 * DAY - 1)
    assert sd["days"] == 3 and D(sd["net_pnl_total"]) == 0


# ── 열기 전 거부 · 격리 ───────────────────────────────────────────────────────
def test_main_refuses_before_every_output_exists(tmp_path, capsys, monkeypatch):
    import sys
    monkeypatch.delitem(sys.modules, E.STRATEGY_MODULE, raising=False)      # 다른 테스트가 import했을 수 있다(격리 검사)
    (tmp_path / "A").mkdir()
    (tmp_path / "A" / "trades.jsonl").write_text("{}\n")
    assert E.main(["--step-e-dir", str(tmp_path)]) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["refused"] and out["missing"] == len(E.required_paths(tmp_path)) - 1
    assert not (tmp_path / "report.json").exists()


def test_required_outputs_cover_all_runs():
    names = {p.parent.name for p in E.required_paths(__import__("pathlib").Path("/x"))}
    assert {"A", "B", "P2_delay1", "P2_delay5", "P3_invert", "P1"} <= names
    assert sum(1 for n in names if n.startswith("P4_draw")) == 200


# ── P1 게으른 색인 = 원래 목록 ─────────────────────────────────────────────────
def test_eligible_index_equals_eligible_minutes_with_gaps():
    start = T0
    end = start + 3000 * MINUTE_MS - 1
    grid = [start + i * MINUTE_MS for i in range(3000) if i not in (5, 700, 701, 2990)]
    idx = PL.EligibleIndex(grid, start, end)
    for h in (1, 2, 3, 7, 60, 699, 1500, 2995, 3000, 3001):
        assert idx.get(h).tolist() == PL.eligible_minutes(grid, h, start, end), h


def test_p1_draw_with_index_is_byte_identical():
    start = T0
    end = start + 5000 * MINUTE_MS - 1
    grid = [start + i * MINUTE_MS for i in range(5000) if i not in (123, 124, 4000)]
    src = [PL.SourceTrade(i, start + i * 97 * MINUTE_MS, start + i * 97 * MINUTE_MS + (5 + i % 40) * MINUTE_MS, D("0.005"))
           for i in range(30)]

    def ok(t, d, s):
        return (t // MINUTE_MS) % 11 != 0

    for d in range(5):
        a = PL.p1_draw(d, src, grid, start, end, ok)
        b = PL.p1_draw(d, src, grid, start, end, ok, index=PL.EligibleIndex(grid, start, end))
        assert PL.p1_canonical_json([a]) == PL.p1_canonical_json([b])


def test_main_refuses_if_the_strategy_module_is_imported(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, E.STRATEGY_MODULE, object())
    with pytest.raises(AssertionError):
        E.main(["--step-e-dir", str(tmp_path)])
