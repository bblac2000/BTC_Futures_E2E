"""트라이얼 #4 (f) 판정기 계산 — 산출물 계약 · V 재계산 · 원장 항등식(펀딩 독립 재계산) · P1 대조 · timing 미열람 · 보고 · 한 번만(규약 E59~E68). 합성만."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from backtest import evaluate_t4 as E
from backtest import t4_outputs as O
from backtest.replay import read_jsonl, write_jsonl
from tests.fixtures import t4_eval_fixture as FX
from tests.fixtures import t4_scenario as S

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("t4eval")
    return base, FX.build(base)


@pytest.fixture
def work(built, tmp_path):
    base, x = built
    dst = tmp_path / "IS"
    shutil.copytree(base, dst)
    return dst, x


def rewrite(p: Path, fn) -> None:
    rows = read_jsonl(p)
    fn(rows)
    write_jsonl(p, rows)


def summary(base: Path, arm: str, var: str = "base") -> dict:
    return json.loads((O.run_dir(base, arm, var) / "summary.json").read_text())


# ── 정상 경로 · 보고 ─────────────────────────────────────────────────────────
def test_compute_gives_a_verdict_per_arm_and_the_report_fields(built):
    base, x = built
    verdicts, rep = FX.compute(base, x)
    assert set(verdicts) == {"S", "L"} and rep["trial_verdict"].startswith("S: REJECT") and " | L: REJECT" in rep["trial_verdict"]
    assert rep["constants"] == {"n_trials": 8, "alpha": 0.00625, "ci_quantiles": [1 / 320, 1 - 1 / 320], "bootstrap_resamples": 10000,
                                "bootstrap_seed": [20260930, 1], "bootstrap_streams": {"gross_S": 0, "net_S": 1, "gross_L": 2, "net_L": 3}}
    assert rep["v_days"] == 30 and rep["v_cross_check"] == {"runs_compared": 8, "match": True}
    for arm, sign in (("S", -1), ("L", 1)):
        a = rep["arms"][arm]
        assert a["priority"] == 3 and a["gates"]["G0"] is False and a["stats"]["n"] == 1 and a["survival"] == "청산 0 / 체결 1"
        assert a["print_funnel"] == summary(base, arm)["funnel"] == {"candidate": 1, "not_extreme": 89} and a["window_prints"] == 90
        assert a["entry_funnel"] == {"exit.time_exit": 1, "filled": 1}
        t = a["trades"]
        assert t["leverage_distribution"] == {"10": 1} and t["exit_reasons"] == {"time_exit": {"n": 1, "share": 1.0}}
        assert t["p_sign_at_entry"] == ({"positive": 1, "negative": 0, "zero": 0} if arm == "S" else {"positive": 0, "negative": 1, "zero": 0})
        assert t["funding_settlements"] == ({"received": 15, "paid": 0, "zero": 0} if arm == "S" else {"received": 0, "paid": 15, "zero": 0})
        assert t["per_year"]["2024"]["n"] == 1 and set(t["cost_grid_mean_net_bps"]) == {"0.5", "1.0", "1.5"}
        assert t["cost_grid_mean_net_bps"]["1.0"] == pytest.approx(a["stats"]["mean_net"])
        pf = t["price_vs_funding"]
        assert D(pf["funding_cf_usdt"]) == D(-sign) * 15 * D("0.002") * D("60000") * D("0.0001") and pf["liquidated_trades"] == 0
        assert pf["mean_gross_incl_funding_bps"] == pytest.approx(a["stats"]["mean_gross"] + float(pf["funding_cf_bps_of_notional_mean"]))
        assert set(a["P1"]) == {"computable", "failed", "successful", "p95", "exits", "liquidated_draw_ratio", "n_eligible",
                                "n_eligible_atr_prev_close_ok"}
        assert set(a["P1_timing"]) == {"failed", "successful", "p95", "exits", "liquidated_draw_ratio"}
        assert a["P1"]["successful"] == 40 and a["P1"]["n_eligible"] == 10 * 1440 and a["P1"]["n_eligible_atr_prev_close_ok"] == 9 * 1440
        assert a["variants"] == {v: {"n": 1, "mean_net_bps": pytest.approx(a["variants"][v]["mean_net_bps"])} for v in O.VARIANTS}
        assert "p1_timing" not in json.dumps(a["inputs"]).lower() and "timing" not in a["inputs"]
    assert rep["buy_and_hold"]["days"] == 30


def test_report_is_deterministic_in_and_across_processes(built):
    base, x = built
    h = hashlib.sha256(E.report_bytes(FX.compute(base, x)[1])).hexdigest()
    assert hashlib.sha256(E.report_bytes(FX.compute(base, x)[1])).hexdigest() == h
    out = subprocess.run([sys.executable, "-m", "tests.fixtures.t4_eval_fixture"], capture_output=True, text=True, cwd=ROOT, check=True)
    assert out.stdout.strip() == h


# ── 거부: 계약 · 해시 · V ────────────────────────────────────────────────────
def test_extra_or_missing_files_are_refused(work):
    base, x = work
    (O.run_dir(base, "S", "base") / "extra.txt").write_text("x")
    with pytest.raises(O.ContractError):
        FX.compute(base, x)
    (O.run_dir(base, "S", "base") / "extra.txt").unlink()
    shutil.rmtree(O.run_dir(base, "L", "P3_invert"))
    with pytest.raises(O.ContractError):
        FX.compute(base, x)


@pytest.mark.parametrize("key,val", [("tc_v3_sha256", "0" * 64), ("v_days", []), ("window_prints", 89)])
def test_summary_tampering_is_refused(work, key, val):
    base, x = work
    p = O.run_dir(base, "L", "P2_print1") / "summary.json"
    s = json.loads(p.read_text())
    s[key] = val
    p.write_text(json.dumps(s))
    with pytest.raises((E.Refusal, O.ContractError)):
        FX.compute(base, x)


def test_v_is_recomputed_from_the_prints_input(work):
    base, x = work
    prints = [dict(p) for p in x["prints"]]
    for p in prints[:40]:                                           # 앞 40개를 무효로 → 창 초반 날의 분포가 정의되지 않는다(기록과 다름)
        p.update(p=None, n_minutes=474, valid=False, complete=False)
    with pytest.raises(E.Refusal, match="V"):
        FX.compute(base, x | {"prints": prints})
    v, dd = E.recompute_v(x["bars"], x["prints"], x["window"], FX.TC_V3)
    assert len(v) == 30 and all(dd.values()) and E.recompute_v(x["bars"], prints, x["window"], FX.TC_V3)[1][S.D0 // S.DAY] is False


# ── 거부: 원장 항등식 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("field,val", [("wallet_after", "1000.5"), ("net_bps", "1.0"), ("gross_bps", "1.0"), ("qty", "0.003"),
                                       ("leverage", 11), ("entry_ms", S.T_E), ("direction", "LONG")])
def test_trade_tampering_is_refused(work, field, val):
    base, x = work
    rewrite(O.run_dir(base, "S", "base") / "trades_t4.jsonl", lambda rows: rows[0].__setitem__(field, val))
    with pytest.raises(E.Refusal):
        FX.compute(base, x)


def test_funding_is_recomputed_independently_from_the_funding_input(work):
    base, x = work
    inside = S.T_E + 2 * S.H8
    with pytest.raises(E.Refusal, match="펀딩"):
        FX.compute(base, x | {"fundings": [f for f in x["fundings"] if f.funding_ms != inside]})
    def tamper(rows):
        for e in rows:
            if e["kind"] == "exit":
                e["funding_paid"] = "0"
    rewrite(O.run_dir(base, "L", "base") / "events.jsonl", tamper)
    with pytest.raises(E.Refusal):
        FX.compute(base, x)


def test_liquidation_trade_passes_the_c26_identity(tmp_path):
    due = S.T_E + S.M + 7200 * S.M
    base = tmp_path / "IS"
    x = FX.build(base, bar_over={due: S.bar(due, o="90000")})         # S: 종료 봉 시가 갭 청산 · L: 시가에 시간 청산
    verdicts, rep = FX.compute(base, x)
    assert rep["arms"]["S"]["priority"] == 2 and verdicts["S"].string == "REJECT(생존) · 생존 실패"
    assert rep["arms"]["S"]["trades"]["price_vs_funding"]["liquidated_trades"] == 1 and rep["arms"]["L"]["priority"] == 3


# ── P1 대조 · timing 미열람 ──────────────────────────────────────────────────
def test_gate_null_tampering_is_refused(work):
    base, x = work
    rewrite(O.p1_merged_dir(base, "S") / "p1_null.jsonl", lambda rows: rows[0].__setitem__("mean_net_bps", "999"))
    with pytest.raises(E.Refusal, match="P1"):
        FX.compute(base, x)


def _retime(base: Path, arm: str, mutate) -> None:
    """timing 귀무 값을 조각과 병합 파일에서 **일관되게** 바꾼다(계약으로 다시 써서 재병합 대조를 통과시킨다)."""
    parts = O.read_p1_parts(base, arm)
    for p in parts:
        for r in p.timing_null:
            mutate(r)
        O.write_p1_part(base, p)
    O.write_p1_merged(base, arm, parts, draws_total=FX.P1_DRAWS)


def test_verdict_never_reads_the_timing_block(work, built):
    base, x = work
    v0, r0 = FX.compute(built[0], built[1])
    _retime(base, "S", lambda r: r.__setitem__("mean_net_bps", "12345.5"))
    v1, r1 = FX.compute(base, x)
    assert r1["trial_verdict"] == r0["trial_verdict"] and v1["S"].string == v0["S"].string
    assert r1["arms"]["S"]["inputs"] == r0["arms"]["S"]["inputs"] and r1["arms"]["S"]["P1"] == r0["arms"]["S"]["P1"]
    assert r1["arms"]["S"]["P1_timing"]["p95"] == 12345.5 != r0["arms"]["S"]["P1_timing"]["p95"]


def test_p1_slots_must_match_the_base_source(work):
    base, x = work
    parts = O.read_p1_parts(base, "L")
    for p in parts:
        d = json.loads(p.draws_json)
        for dr in d:
            for pl in dr["placed"]:
                pl[4] = "0.07"                                      # 낡은 원판의 sl_dist
        p.draws_json = json.dumps(d, sort_keys=True, separators=(",", ":"))
        O.write_p1_part(base, p)
    O.write_p1_merged(base, "L", parts, draws_total=FX.P1_DRAWS)
    with pytest.raises(E.Refusal, match="원판"):
        FX.compute(base, x)


def test_parts_must_agree_on_the_eligible_counts(work):
    base, _ = work
    parts = O.read_p1_parts(base, "S")
    parts[1].n_eligible += 1
    with pytest.raises(O.ContractError):
        O.write_p1_merged(base, "S", parts, draws_total=FX.P1_DRAWS)


def test_variant_with_zero_trades_neither_crashes_nor_rejects(tmp_path):
    f = S.T_E + S.H8 + S.M
    base = tmp_path / "IS"
    x = FX.build(base, bar_over={f: S.bar(f, o="64000")})             # S의 P2 +1 인쇄: 체결 전 SL 넘음 → 0건
    _, rep = FX.compute(base, x)
    assert rep["arms"]["S"]["variants"]["P2_print1"] == {"n": 0, "mean_net_bps": 0.0}
    assert rep["arms"]["S"]["inputs"]["p2_p1"] == 0.0


# ── 한 번만 ──────────────────────────────────────────────────────────────────
def test_run_once_writes_evaluation_and_refuses_a_second_time(work):
    base, x = work
    verdict, rec = E.evaluate_with_fixture(base, bars=x["bars"], fundings=x["fundings"], prints=x["prints"], kline_daily=x["kd"],
                                           liq_fee=FX.LIQ_FEE, p=FX.TC_V3, window=x["window"], p1_draws=FX.P1_DRAWS)
    ev = base / "evaluation"
    assert sorted(p.name for p in ev.iterdir()) == ["record.json", "report.json", "verdict.txt"]
    assert (ev / "verdict.txt").read_text() == verdict + "\n" and rec["report_sha256"] == hashlib.sha256((ev / "report.json").read_bytes()).hexdigest()
    for _ in range(2):
        with pytest.raises(E.Refusal):
            E.evaluate_with_fixture(base, bars=x["bars"], fundings=x["fundings"], prints=x["prints"], kline_daily=x["kd"],
                                    liq_fee=FX.LIQ_FEE, p=FX.TC_V3, window=x["window"], p1_draws=FX.P1_DRAWS)


def test_a_refused_attempt_writes_nothing_but_leaves_the_attempt_record(work):
    base, x = work
    rewrite(O.run_dir(base, "S", "base") / "trades_t4.jsonl", lambda rows: rows[0].__setitem__("wallet_after", "1"))
    with pytest.raises(E.Refusal):
        E.evaluate_with_fixture(base, bars=x["bars"], fundings=x["fundings"], prints=x["prints"], kline_daily=x["kd"],
                                liq_fee=FX.LIQ_FEE, p=FX.TC_V3, window=x["window"], p1_draws=FX.P1_DRAWS)
    assert not (base / "evaluation").exists() and (base / "_records" / E.ATTEMPT).exists()
    assert not [p for p in base.iterdir() if p.name.startswith("evaluation_")]


def test_the_execution_path_refuses_on_the_real_repo_without_freeze_rows(work):
    """(g) 전반: 실행 경로는 단계 관문과 연결됐다 — 동결 행이 없는 지금의 저장소에서는 관문에서 거부하고 아무것도 쓰지 않는다."""
    with pytest.raises(E.Refusal, match="ProvenanceError"):
        E.evaluate(work[0], ROOT, evaluator_commit="0" * 40, fetch=False)
    assert not (work[0] / "evaluation").exists() and not (work[0] / "_records" / E.ATTEMPT).exists()


def test_v_needs_exactly_270_prior_valid_prints():
    d0 = S.D0 // S.DAY
    for prior, first_defined in ((270, d0), (269, d0 + 1), (264, d0 + 2)):
        sc = S.Scenario(prior=prior, over={})
        _, dd = E.recompute_v(sc.bars(), sc.prints(), sc.window, FX.TC_V3)
        assert min(d for d, ok in dd.items() if ok) == first_defined, prior


def test_a_funding_record_in_the_entry_minute_is_not_part_of_the_trade(built):
    """펀딩 재계산 구간은 (entry_ms, 청산 분] — 체결 분 버킷의 기록(오프셋 시각)은 세지 않는다(결정 17 · E63)."""
    from backtest.data import Funding
    base, x = built
    extra = [*x["fundings"], Funding(S.T_E + S.M + 5, "0.01", "60000")]
    _, rep = FX.compute(base, x | {"fundings": extra})
    assert rep["arms"]["S"]["trades"]["funding_settlements"] == {"received": 15, "paid": 0, "zero": 0}


def test_no_keyword_override_of_the_draw_count_in_trial4_modules():
    """추출 수는 위치 인자로만 넘긴다 — 트라이얼 #3의 저장소 전체 정적 검사(`draws_total=` 키워드 · 픽스처 경로 호출 금지)가
    트라이얼 #4 모듈에도 그대로 걸린다(그 시험은 고치지 않는다)."""
    import ast
    for mod in ("backtest/p1_t4.py", "backtest/evaluate_t4.py", "backtest/t4_outputs.py", "strategies/trial04/harness.py"):
        tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Call) and any(k.arg == "draws_total" for k in n.keywords)], mod
        calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(tree)
                 if isinstance(n, ast.Call)}
        assert not calls & {"run_arm_with_fixture_rules", "run_range_with_fixture_rules", "compute_with_fixture", "evaluate_with_fixture"}
