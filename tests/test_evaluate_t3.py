"""트라이얼 #3 (f) 판정기 — 끝에서 끝(합성) · 보고 골든·결정론 · 거부 경로(V · 진입일 · 원장 · 계약 · P1) · 한 번만·커밋 검사(계획 r2/r3)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from backtest import evaluate_t3 as E
from backtest import p1_t3 as P1
from backtest import t3_outputs as O
from tests.fixtures import t3_eval_fixture as F
from tests.fixtures import t3_scenario as S

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "fixtures" / "golden_eval_trial03.json"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("t3eval")
    bars, kd = F.build(base)
    return base, bars, kd


def fresh(built, tmp_path) -> Path:
    base = tmp_path / "base"
    shutil.copytree(built[0], base)
    return base


def test_end_to_end_verdicts_and_report_golden(built):
    base, bars, kd = built
    _, report = F.compute(base, bars, kd)
    assert report["trial_verdict"] == "L: REJECT(§7-2: 검정력 부족) · 생존 통과 | S: REJECT(§7-2: 검정력 부족) · 생존 통과"
    for a in ("L", "S"):
        x = report["arms"][a]
        assert x["survival"] == "청산 0 / 체결 1" and x["gates"]["G0"] is False and x["priority"] == 3
        g = x["trades"]["cost_grid_mean_net_bps"]
        assert g["0.5"] > g["1.0"] > g["1.5"] and g["1.0"] == x["stats"]["mean_net"]
        assert x["P1"]["computable"] and x["P1"]["successful"] + x["P1"]["failed"] == F.P1_DRAWS
    h = hashlib.sha256(E.report_bytes(report)).hexdigest()
    assert h == json.loads(GOLDEN.read_text())["report_sha256"]


def test_report_hash_is_deterministic_across_processes():
    want = json.loads(GOLDEN.read_text())["report_sha256"]
    outs = {subprocess.run([sys.executable, "-m", "tests.fixtures.t3_eval_fixture"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.strip() for _ in range(2)}
    assert outs == {want}


# ── 거부 경로 ────────────────────────────────────────────────────────────────
def _edit_summary(base: Path, arm: str, var: str, **kv):
    p = O.run_dir(base, arm, var) / "summary.json"
    s = json.loads(p.read_text())
    s.update(kv)
    p.write_text(json.dumps(s))


def test_v_mismatch_refused(built, tmp_path):
    base = fresh(built, tmp_path)
    _edit_summary(base, "S", "P2_delay5", v_days=[])
    with pytest.raises(E.Refusal):
        F.compute(base, built[1], built[2])


def test_entry_day_outside_v_refused(built, tmp_path):
    base = fresh(built, tmp_path)
    p = O.run_dir(base, "L", "base") / "trades_t3.jsonl"
    t = json.loads(p.read_text().splitlines()[0])
    t["entry_ms"] = S.DAY0 + 60_000                                       # 워밍업 날
    p.write_text(json.dumps(t) + "\n")
    with pytest.raises(E.Refusal, match="V 밖"):
        F.compute(base, built[1], built[2])


@pytest.mark.parametrize("field", ["wallet_after", "net_bps", "gross_bps"])
def test_ledger_tamper_refused(built, tmp_path, field):
    base = fresh(built, tmp_path)
    p = O.run_dir(base, "S", "base") / "trades_t3.jsonl"
    t = json.loads(p.read_text().splitlines()[0])
    t[field] = str(D(t[field]) + D("1e-20"))
    p.write_text(json.dumps(t) + "\n")
    with pytest.raises(E.Refusal):
        F.compute(base, built[1], built[2])


def test_liquidation_ledger_identity_and_tamper():
    base_r = S.run(S.Scenario(arm="L"))
    i = base_r.trades[0]["t3"]
    idx = (i["t_e"] - S.DAY0) // 60_000 + 1
    r = S.run(S.Scenario(arm="L", over={idx: {"low": float(D(i["m"])) * 0.9}}))
    assert r.trades[0]["exit_reason"] == "liquidation"
    rows = E.ledger_check(r.trades, r.strategy.events, F.LIQ_FEE, D(1000))
    assert rows[0]["grid"]["1.0"] == D(r.trades[0]["net_bps"])
    ev = [dict(e) for e in r.strategy.events]
    ex = next(e for e in ev if e["kind"] == "exit")
    ex["realized_pnl"] = str(D(ex["realized_pnl"]) + D("1e-20"))
    with pytest.raises(E.Refusal):
        E.ledger_check(r.trades, ev, F.LIQ_FEE, D(1000))


def test_inventory_missing_or_extra_refused(built, tmp_path):
    base = fresh(built, tmp_path)
    (O.run_dir(base, "L", "P3_invert") / "events.jsonl").unlink()
    with pytest.raises(O.ContractError):
        F.compute(base, built[1], built[2])
    base2 = tmp_path / "b2"
    shutil.copytree(built[0], base2)
    (base2 / "runs" / "L_extra").mkdir()
    with pytest.raises(O.ContractError):
        F.compute(base2, built[1], built[2])


def test_p1_merged_must_equal_remerge_and_source_count(built, tmp_path):
    base = fresh(built, tmp_path)
    p = O.p1_merged_dir(base, "S") / "p1_summary.json"
    s = json.loads(p.read_text())
    s["failed"] = s["failed"] + 1
    p.write_text(json.dumps(s))
    with pytest.raises(E.Refusal, match="병합"):
        F.compute(base, built[1], built[2])
    base2 = tmp_path / "b2"
    shutil.copytree(built[0], base2)
    sc = S.Scenario(arm="L", flushes=[S.F_DEFAULT, S.F_DEFAULT + 715])
    two = S.run(sc)
    shutil.rmtree(O.p1_parts_dir(base2, "L"))
    shutil.rmtree(O.p1_merged_dir(base2, "L"))
    parts = [P1.run_range_with_fixture_rules("L", two.trades, sc.bars(), sc.fundings(), lo, hi, rules=S.RULES, window=S.WINDOW)
             for lo, hi in ((0, 19), (20, 39))]
    for q in parts:
        O.write_p1_part(base2, q)
    O.write_p1_merged(base2, "L", parts, draws_total=F.P1_DRAWS)
    with pytest.raises(E.Refusal, match="원판 수"):
        F.compute(base2, built[1], built[2])


def test_boundary_exit_report_counts_and_sums_funding():
    b16 = S.DAY0 + S.DAY + 16 * 3_600_000
    trades = [{"entry_ms": b16 - 240 * 60_000, "exit_ms": b16, "exit_reason": "time_exit", "direction": "LONG", "net_bps": "-20",
               "exit_ref": "60000", "sl": "59700"},
              {"entry_ms": b16 - 300 * 60_000, "exit_ms": b16 - 60 * 60_000, "exit_reason": "time_exit", "direction": "LONG",
               "net_bps": "-21", "exit_ref": "59600", "sl": "59700"}]
    trades.append({"entry_ms": b16 - 30 * 60_000, "exit_ms": b16 + 59_999, "exit_reason": "sl", "direction": "LONG", "net_bps": "-30",
                   "exit_ref": "59700", "sl": "59700"})
    g = {"0.5": D(-9), "1.0": D(-20), "1.5": D(-31)}
    ledger = [{"exit_ms": b16, "funding": D("0.12"), "grid": g},
              {"exit_ms": b16 - 3_600_000, "funding": D("0.5"), "grid": g},
              {"exit_ms": b16 + 59_999, "funding": D("0.3"), "grid": g}]                # 경계 분 봉 안 SL — 대칭(P1도 냄)
    rep = E.trade_report(trades, ledger, D(1000))
    b = rep["exit_at_funding_boundary"]
    assert b["n"] == 1 and D(b["funding_paid_usdt"]) == D("0.12") and D(b["funding_paid_bps_of_e_ref"]) == D("1.2")
    assert b["symmetric_intrabar_n"] == 1
    assert rep["x9_time_exit_open_past_sl"] == 1


def test_fixture_compute_refuses_callers_outside_tests(tmp_path, built):
    caller = tmp_path / "evil.py"
    caller.write_text("from backtest.evaluate_t3 import compute_with_fixture\n"
                      "def go(*a, **k):\n    return compute_with_fixture(*a, **k)\n")
    import importlib.util
    spec = importlib.util.spec_from_file_location("evil_eval", caller)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(E.Refusal):
        mod.go(built[0], built[1], built[2], F.LIQ_FEE, p=S.P, window=S.WINDOW, p1_draws=F.P1_DRAWS)


# ── 한 번만 · 커밋 검사(임시 git 저장소) ─────────────────────────────────────
def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path) -> tuple[Path, str]:
    r = tmp_path / "repo"
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    for f in sorted(E.freeze_set(ROOT)):
        (r / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, r / f)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "evaluator")
    _git(r, "remote", "add", "origin", str(origin))
    _git(r, "push", "-q", "origin", "main")
    _git(r, "fetch", "-q", "origin")
    return r, _git(r, "rev-parse", "HEAD")


def _eval(base: Path, repo: Path, commit: str, built):
    return E.evaluate_with_fixture(base, repo, evaluator_commit=commit, bars=built[1], kline_daily=built[2], liq_fee=F.LIQ_FEE,
                                   p=S.P, window=S.WINDOW, p1_draws=F.P1_DRAWS)


def test_run_once_and_record(built, tmp_path, repo):
    base = fresh(built, tmp_path)
    r, commit = repo
    verdict, record = _eval(base, r, commit, built)
    assert verdict.startswith("L: REJECT") and (base / "evaluation" / "report.json").exists()
    assert record["report_sha256"] == json.loads(GOLDEN.read_text())["report_sha256"]
    assert (base / "evaluation" / "verdict.txt").read_text() == verdict + "\n"
    with pytest.raises(E.Refusal, match="한 번만"):
        _eval(base, r, commit, built)


def test_unpushed_or_changed_evaluator_refused(built, tmp_path, repo):
    r, commit = repo
    (r / "backtest" / "evaluate_t3.py").write_text((r / "backtest" / "evaluate_t3.py").read_text() + "# x\n")
    _git(r, "commit", "-qam", "local only")
    local = _git(r, "rev-parse", "HEAD")
    with pytest.raises(E.Refusal, match="origin/main"):
        _eval(fresh(built, tmp_path), r, local, built)
    with pytest.raises(E.Refusal, match="바뀌었다"):
        _eval(fresh(built, tmp_path / "x"), r, commit, built)


def test_dirty_tree_refused_and_nothing_written(built, tmp_path, repo):
    r, commit = repo
    (r / "stray.txt").write_text("x")
    base = fresh(built, tmp_path)
    with pytest.raises(E.Refusal, match="깨끗"):
        _eval(base, r, commit, built)
    assert not (base / "evaluation").exists()


def test_zero_bar_window_day_is_not_a_refusal(tmp_path):
    """봉이 0개인 창 날은 V에서 빠질 뿐 거부 사유가 아니다(advisor (f) after #1)."""
    drop = set(range(2 * 1440, 3 * 1440))                               # 날 2 전체(창 안)
    scs = {"L": S.Scenario(arm="L", drop=drop), "S": S.Scenario(arm="S", drop=drop)}
    bars, kd = F.build(tmp_path, scs)
    _, report = F.compute(tmp_path, bars, kd)
    assert report["zero_bar_window_days"] == 1 and report["v_days"] == 1 and report["v_cross_check"]["match"]


def test_report_is_self_describing(built):
    _, report = F.compute(*built)
    c = report["constants"]
    assert c["n_trials"] == 6 and c["ci_quantiles"] == [1 / 240, 1 - 1 / 240] and c["bootstrap_resamples"] == 10_000
    assert all("bh_beats_arm" in report["arms"][a] for a in ("L", "S"))


def test_later_pushed_anchor_change_is_refused(built, tmp_path, repo):
    """동결 집합은 판정기 파일만이 아니다 — 앵커 문턱을 바꾼 뒤 푸시해도 거부(Codex (f) after #1)."""
    r, commit = repo
    a = r / "strategies" / "trial03" / "anchor.py"
    a.write_text(a.read_text().replace("P1_FAIL_MAX = 10", "P1_FAIL_MAX = 11"))
    _git(r, "commit", "-qam", "loosen")
    _git(r, "push", "-q", "origin", "main")
    with pytest.raises(E.Refusal, match="anchor.py"):
        _eval(fresh(built, tmp_path), r, commit, built)


def test_entry_moved_between_valid_v_days_is_refused(built, tmp_path):
    base = fresh(built, tmp_path)
    p = O.run_dir(base, "L", "base") / "trades_t3.jsonl"
    t = json.loads(p.read_text().splitlines()[0])
    t["entry_ms"] = int(t["entry_ms"]) + S.DAY                             # 날 1 → 날 2(둘 다 V)
    p.write_text(json.dumps(t) + "\n")
    with pytest.raises(E.Refusal, match="엔진 기록"):
        F.compute(base, built[1], built[2])


def test_rules_sha_and_p1_manifest_and_nested_schema_tampers_refused(built, tmp_path):
    base = fresh(built, tmp_path)
    _edit_summary(base, "L", "base", rules_sha256={"exchangeInfo": "0" * 64})
    with pytest.raises(E.Refusal, match="#48"):
        F.compute(base, built[1], built[2])
    base2 = tmp_path / "b2"
    shutil.copytree(built[0], base2)
    p = O.p1_merged_dir(base2, "S") / "p1_summary.json"
    s = json.loads(p.read_text())
    s["parts"][0]["sha256"] = "0" * 64
    p.write_text(json.dumps(s))
    with pytest.raises(E.Refusal, match="조각 목록"):
        F.compute(base2, built[1], built[2])
    base3 = tmp_path / "b3"
    shutil.copytree(built[0], base3)
    _edit_summary(base3, "S", "base", funnel={"no_tail": -1})
    with pytest.raises(O.ContractError, match="중첩"):
        F.compute(base3, built[1], built[2])


def test_exit_reason_shares(built):
    _, report = F.compute(*built)
    t = report["arms"]["L"]["trades"]
    assert t["exit_reasons"] == {"time_exit": {"n": 1, "share": 1.0}} and t["n_trades"] == 1
