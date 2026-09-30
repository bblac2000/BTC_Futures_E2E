"""트라이얼 #3 (g) — 출처(행·핀·영수증) · 단계 실행기(스케줄러·기록·분할) · 자식 CLI 실패 보존 · 표준출력 위생 · 끝에서 끝까지(판정 한 번).

임시 git 저장소에 계획 r3의 커밋 사슬(C1 규약 → C2 = H 행 #52 → C3 동결 목록 + 행 #53)을 그대로 만든다. 실데이터 없음.
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from backtest import evaluate_t3 as E
from backtest import p1_t3 as P1
from backtest import prepare_t3 as PT
from backtest import t3_outputs as O
from backtest import t3_provenance as PV
from backtest import t3_stages as T
from backtest.replay import RunRecord
from strategies.trial03 import anchor as A
from strategies.trial03 import harness as H
from strategies.trial03.harness import complete_days, v_days
from tests import test_prepare_t3 as TP
from tests.fixtures import t3_eval_fixture as F
from tests.fixtures import t3_scenario as S

ROOT = Path(__file__).resolve().parent.parent
M = 60_000
FORBIDDEN = re.compile(r"net|pnl|wallet|sharpe|mean|gross|return|price|funding_paid|psr", re.I)


# ── 임시 저장소: 계획 r3 커밋 사슬 ───────────────────────────────────────────
def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo: Path, msg: str, push: bool = True) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    if push:
        _git(repo, "push", "-q", "origin", "main")
        _git(repo, "fetch", "-q", "origin")
    return _git(repo, "rev-parse", "HEAD")


def _append_row(repo: Path, row: str) -> None:
    reg = repo / PV.REGISTRY_REL
    reg.write_text(reg.read_text() + row + "\n")


@pytest.fixture
def chain(tmp_path) -> dict[str, Any]:
    """C1(규약 최종) → C2 = H(행 #52) → C3(동결 목록 + 행 #53) · 푸시."""
    r, origin = tmp_path / "repo", tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    _git(r, "remote", "add", "origin", str(origin))
    for f in sorted(PV.freeze_set(ROOT)):
        (r / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, r / f)
    (r / ".gitignore").write_text("var/\n__pycache__/\n")
    (r / PV.CONVENTIONS_REL).parent.mkdir(parents=True, exist_ok=True)
    (r / PV.CONVENTIONS_REL).write_text("# 규약(시험)\n")
    (r / PV.REGISTRY_REL).write_text("| # | 날짜 | 무엇 |\n|---|---|---|\n")
    c1 = _commit(r, "C1 conventions final")
    conv = PV.sha_file(r / PV.CONVENTIONS_REL)
    _append_row(r, f"| 52 | 2026-09-30 | 규약 동결 · t3_conventions={conv} · t3_conventions_commit={c1} |")
    h = _commit(r, "C2 row 52")
    man = PV.freeze_manifest(r, h)
    (r / PV.FREEZE_MANIFEST_REL).write_text(json.dumps(man, sort_keys=True, indent=1) + "\n")
    msha = PV.sha_file(r / PV.FREEZE_MANIFEST_REL)
    _append_row(r, f"| 53 | 2026-09-30 | 코드 동결 · t3_freeze_H={h} · t3_freeze_manifest={msha} · t3_fingerprint={man['fingerprint']} |")
    c3 = _commit(r, "C3 freeze manifest + row 53")
    return {"repo": r, "H": h, "C1": c1, "C3": c3, "base": r / "var" / "t3" / "IS", "tmp": tmp_path}


def test_rows_gate_passes_on_the_r3_chain(chain):
    rows = PV.require_rows(chain["repo"], chain["H"])
    assert rows["conventions_commit"] == chain["C1"] and rows["fingerprint"] == PV.fingerprint(chain["repo"])
    PV.require_frozen(chain["repo"], chain["H"], fetch_first=False)


def test_rows_gate_refuses_changed_conventions_manifest_or_code(chain):
    r, h = chain["repo"], chain["H"]
    conv = r / PV.CONVENTIONS_REL
    conv.write_text(conv.read_text() + "x\n")
    _commit(r, "edit conventions after #52")
    with pytest.raises(PV.ProvenanceError, match="규약 파일"):
        PV.require_rows(r, h)
    _git(r, "reset", "-q", "--hard", chain["C3"])
    _git(r, "push", "-q", "-f", "origin", "main")
    _git(r, "fetch", "-q", "origin")
    man = r / PV.FREEZE_MANIFEST_REL
    man.write_text(man.read_text().replace('"H"', '"H" ', 1))
    _commit(r, "touch manifest")
    with pytest.raises(PV.ProvenanceError, match="동결 행"):
        PV.require_rows(r, h)
    _git(r, "reset", "-q", "--hard", chain["C3"])
    _git(r, "push", "-q", "-f", "origin", "main")
    _git(r, "fetch", "-q", "origin")
    f = r / "strategies" / "trial03" / "config.py"
    f.write_text(f.read_text() + "# x\n")
    _commit(r, "code change after H")
    with pytest.raises(PV.ProvenanceError, match="바뀌었다"):
        PV.require_frozen(r, h, fetch_first=False)
    with pytest.raises(PV.ProvenanceError, match="동결 목록"):
        PV.require_rows(r, h)


def test_rows_gate_refuses_row_52_edited_only_on_origin(chain):
    r = chain["repo"]
    reg = r / PV.REGISTRY_REL
    reg.write_text(reg.read_text().replace("규약 동결", "규약 동결(고침)"))
    _commit(r, "rewrite #52 in place")
    # 토큰이 같으면 행 문구 변경은 통과한다(토큰이 계약) — 토큰을 바꾸면 거부
    PV.require_rows(r, chain["H"])
    reg.write_text(reg.read_text().replace(f"t3_conventions_commit={chain['C1']}", f"t3_conventions_commit={chain['H']}"))
    _commit(r, "move C1 token")
    with pytest.raises(PV.ProvenanceError, match="H 트리"):
        PV.require_rows(r, chain["H"])


def test_gate_check_cli_rc0_and_rc6(chain, monkeypatch):
    r, h = chain["repo"], chain["H"]
    monkeypatch.setenv("T3_STAGE_REPO", str(r))
    monkeypatch.setenv("T3_STAGE_ORIGIN", _git(r, "rev-parse", "origin/main"))
    out = str(chain["base"] / "prepared")
    assert PT.main(["--out", out, "--gate-check", "--evaluator-commit", h]) == 0
    assert PT.main(["--out", out, "--gate-check", "--evaluator-commit", chain["C1"]]) == 6
    monkeypatch.setenv("T3_STAGE_ORIGIN", chain["C1"])
    assert PT.main(["--out", out, "--gate-check", "--evaluator-commit", h]) == 6
    assert not (chain["base"] / "prepared" / "raw").exists()


def test_stage_repo_refuses_a_repo_with_different_frozen_code(chain, monkeypatch):
    r = chain["repo"]
    f = r / "backtest" / "stats.py"
    f.write_text(f.read_text() + "# drift\n")
    monkeypatch.setenv("T3_STAGE_REPO", str(r))
    monkeypatch.setenv("T3_STAGE_ORIGIN", "x")
    with pytest.raises(PV.ProvenanceError, match="실행 중인 코드"):
        PV.stage_repo()


# ── 가짜 실행기(격리 subprocess 대신 · 같은 출력 계약) ────────────────────────
SCS = {"L": S.Scenario(arm="L"), "S": S.Scenario(arm="S")}


def _base_run(arm: str):
    return S.run(SCS[arm], F.VARIANTS["base"])


class FakeRunner:
    def __init__(self, fail: set[str] | None = None):
        self.fail, self.calls = fail or set(), []

    def __call__(self, module: str, args: list[str], out: Path, *, timeout_s: float, env: dict[str, str]) -> RunRecord:
        a = dict(zip(args[::2], args[1::2], strict=False))
        self.calls.append((module, args))
        assert env["T3_STAGE_ORIGIN"] and env["T3_STAGE_REPO"]
        out.mkdir(parents=True, exist_ok=True)
        rc = 0
        if module == T.PREP_MODULE and "--verify" in args:
            PT.verify_rebuild(out, (TP.START, TP.END))
        elif module == T.PREP_MODULE:
            arch = TP.write_archive(out.parent / "arch_src", [], TP.full_archive())
            PT.capture(out / "raw", TP.FakeRest(), arch, TP.std_oi(), TP.START, TP.END)
            PT.build(out, (TP.START, TP.END))
        elif module == T.STRATEGY:
            key = f"{a['--arm']}_{a['--variant']}"
            if key in self.fail:
                (out / "_failure_error.txt").write_text("boom\n")
                (out / "_failure_events.jsonl").write_text("{}\n")
                rc = 7
            else:
                sc = SCS[a["--arm"]]
                run = S.run(sc, F.VARIANTS[a["--variant"]])
                O.write_run(out, run, v_days(run.strategy, complete_days(sc.bars())), tf_v1_sha256=A.TF_V1_SHA256,
                            rules_sha256=A.RULES_SNAPSHOT_SHA256)
        elif module == T.P1_MODULE:
            arm, lo, hi = a["--arm"], int(a["--lo"]), int(a["--hi"])
            sc = SCS[arm]
            part = P1.run_range_with_fixture_rules(arm, _base_run(arm).trades, sc.bars(), sc.fundings(), lo, hi, rules=S.RULES,
                                                   window=S.WINDOW)
            O.write_p1_part_to(out, part)
        outputs = {p.name: PV.sha_file(p) for p in sorted(out.iterdir()) if p.is_file()}
        return RunRecord(module, list(args), rc, "", "", "s", "e", "h", platform.python_version(), "np", outputs)


def _stages(chain, runner=None) -> T.Stages:
    return T.Stages(chain["H"], base=chain["base"], repo=chain["repo"], runner=runner or FakeRunner(), fetch=False)


def _pin(chain, st: T.Stages) -> None:
    pins = st.stage_pins()
    toks = " · ".join(f"{k}={v}" for k, v in PV.pins_row_tokens(pins).items())
    _append_row(chain["repo"], f"| 54 | 2026-09-30 | 데이터 핀 `{PV.PINS_REL}` · {toks} |")
    _commit(chain["repo"], "pins + row 54")


def _prepared(chain, runner=None) -> T.Stages:
    st = _stages(chain, runner)
    st.stage_prepare()
    _pin(chain, st)
    st.stage_verify()
    return st


def test_pins_and_receipt_tamper_refused(chain):
    st = _prepared(chain)
    r = chain["repo"]
    pins, pc = PV.load_pins(r, fetch_first=False)
    rec = json.loads((st.records / "verify_receipt.json").read_text())
    PV.check_receipt(rec, prepared=st.prep, pins=pins, pins_c=pc, commit=chain["H"], fp=PV.fingerprint(r))
    with pytest.raises(PV.ProvenanceError, match="영수증"):
        PV.check_receipt(rec | {"pins_commit": chain["C1"]}, prepared=st.prep, pins=pins, pins_c=pc, commit=chain["H"],
                         fp=PV.fingerprint(r))
    pf = r / PV.PINS_REL
    good = pf.read_text()
    pf.write_text(good.replace(pins["manifest_sha256"], "0" * 64))
    with pytest.raises(PV.ProvenanceError, match="커밋되지 않은"):
        PV.load_pins(r, fetch_first=False)
    _commit(r, "pins changed without a new row")
    with pytest.raises(PV.ProvenanceError, match="토큰"):
        PV.load_pins(r, fetch_first=False)
    pf.write_text(good)
    _commit(r, "pins restored (bytes equal the #54 row)")
    assert PV.load_pins(r, fetch_first=False)[0] == pins


def test_pins_without_a_registry_row_refused(chain):
    st = _stages(chain)
    st.stage_prepare()
    st.stage_pins()
    _commit(chain["repo"], "pins, no row")
    with pytest.raises(PV.ProvenanceError, match="정확히 하나"):
        PV.load_pins(chain["repo"], fetch_first=False)
    with pytest.raises(PV.ProvenanceError, match="정확히 하나"):
        st.stage_verify()


def test_runs_refuse_without_verify_receipt(chain):
    st = _stages(chain)
    st.stage_prepare()
    _pin(chain, st)
    with pytest.raises(T.StageFailed, match="verify"):
        st.stage_runs(1)


def test_scheduler_stops_after_first_failure_and_failed_record_is_not_rerun(chain):
    runner = FakeRunner(fail={"L_P2_delay1"})
    st = _prepared(chain, runner)
    n_before = len(runner.calls)
    with pytest.raises(T.StageFailed, match="L_P2_delay1"):
        st.stage_runs(1)
    ran = [a[3] for m, a in runner.calls[n_before:]]
    assert ran == ["base", "P2_delay1"]                                  # 실패 뒤 새 제출 없음
    assert sorted(p.name for p in (st.records / "failures" / "L_P2_delay1").iterdir()) == ["_failure_error.txt",
                                                                                          "_failure_events.jsonl"]
    runner.fail.clear()
    with pytest.raises(T.StageFailed, match="실패 기록"):
        st.stage_runs(1)
    assert len(runner.calls) == n_before + 2


def test_partial_output_without_record_is_refused(chain):
    st = _prepared(chain)
    d = st.runs / "L_base"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("")
    with pytest.raises(T.StageFailed, match="기록 없는"):
        st.stage_runs(1)


def test_output_tamper_after_record_is_refused(chain):
    st = _prepared(chain)
    st.stage_runs(2, only="L_base")
    f = st.runs / "L_base" / "summary.json"
    f.write_text(f.read_text() + " ")
    with pytest.raises(T.StageFailed, match="해시"):
        st.stage_runs(1, only="L_base")


def test_stage_code_drift_between_begin_and_run_is_refused(chain):
    st = _prepared(chain)
    prov = st.receipt_ok(st.begin())
    f = chain["repo"] / "backtest" / "stats.py"
    f.write_text(f.read_text() + "# drift\n")
    with pytest.raises(T.StageFailed, match="지문"):
        st.run_one("L_base", st.run_job("L", "base"), prov | {"variant": "L_base"})


def test_partition_is_recorded_once_and_cannot_change():
    assert T.partition(8)[0] == [0, 124] and T.partition(8)[-1] == [875, 999]
    assert T.partition(3) == [[0, 333], [334, 667], [668, 999]]
    with pytest.raises(T.StageFailed):
        T.partition(0)


# ── 끝에서 끝까지: prepare → pins → verify → runs → p1 → merge → evaluate(한 번) ─
def _patch_eval_inputs(monkeypatch):
    bars = SCS["L"].bars()
    kd = F.kline_daily(bars)
    monkeypatch.setattr(PT, "load_prepared_pinned", lambda *a, **k: (bars, [], [], []))
    monkeypatch.setattr(PT, "load_kline_daily_pinned", lambda *a, **k: kd)
    monkeypatch.setattr(E, "compute", lambda base, b, k, liq: E.compute_with_fixture(base, b, k, F.LIQ_FEE, p=S.P, window=S.WINDOW,
                                                                                    p1_draws=T.P1_DRAWS))


def test_end_to_end_stages_then_evaluate_once(chain, monkeypatch):
    st = _prepared(chain)
    with pytest.raises(T.StageFailed, match="기본 실행"):
        st.stage_p1(4, 2)
    assert len(st.stage_runs(3)) == 8
    assert st.stage_runs(3) == []                                         # 이어 하기: 전부 완료
    assert st.stage_p1(4, 1, only="P1_L_000_249") == [("P1_L_000_249", 0)]
    st.stage_p1(4, 2)
    with pytest.raises(T.StageFailed, match="분할"):
        st.stage_p1(8, 2)
    assert [n for n, _ in st.stage_p1_merge()] == ["P1_merge_L", "P1_merge_S"]
    assert st.stage_p1_merge() == []
    _patch_eval_inputs(monkeypatch)
    verdict, record = E.evaluate(st.base, chain["repo"], evaluator_commit=chain["H"], fetch=False)
    assert verdict.startswith("L: ") and "S: " in verdict
    assert record["pins_commit"] == PV.pins_commit(chain["repo"]) and record["fingerprint"] == PV.fingerprint(chain["repo"])
    assert "P1_merge_L.json" in record["stage_records_sha256"] and "verify_receipt.json" in record["stage_records_sha256"]
    assert any(k.startswith("runs/L_base/") for k in record["inputs_sha256"])
    assert not any(k.startswith("prepared/raw/") for k in record["inputs_sha256"])
    with pytest.raises(E.Refusal, match="한 번만"):
        E.evaluate(st.base, chain["repo"], evaluator_commit=chain["H"], fetch=False)


def test_evaluate_refuses_missing_records_and_leftover_attempt(chain, monkeypatch):
    st = _prepared(chain)
    st.stage_runs(3)
    _patch_eval_inputs(monkeypatch)
    with pytest.raises(E.Refusal, match="P1"):
        E.evaluate(st.base, chain["repo"], evaluator_commit=chain["H"], fetch=False)
    assert not (st.base / "evaluation").exists() and not (st.records / E.ATTEMPT).exists()
    st.stage_p1(2, 2)
    st.stage_p1_merge()
    (st.records / E.ATTEMPT).write_text("{}\n")                           # 중단된 시도
    with pytest.raises(E.Refusal, match="시도 기록"):
        E.evaluate(st.base, chain["repo"], evaluator_commit=chain["H"], fetch=False)
    assert not (st.base / "evaluation").exists()


# ── 자식 CLI: 실패 보존 · rc · 표준출력 위생 ──────────────────────────────────
def _child_gate_off(monkeypatch, tmp_path: Path) -> Path:
    base = tmp_path / "var" / "t3" / "IS"
    (base / "_records").mkdir(parents=True)
    (base / "_records" / "verify_receipt.json").write_text("{}\n")
    monkeypatch.setattr(PV, "stage_repo", lambda: ROOT)
    monkeypatch.setattr(PV, "child_gate", lambda *a, **k: {})
    monkeypatch.setattr(PV, "load_pins", lambda *a, **k: ({"manifest_sha256": "0" * 64}, "c"))
    monkeypatch.setattr(PV, "check_receipt", lambda *a, **k: None)
    sc = SCS["L"]
    rows, bad = sc.oi_rows()
    monkeypatch.setattr(PT, "load_prepared_pinned", lambda *a, **k: (sc.bars(), sc.fundings(), rows, bad))
    return base


def _stdout_clean(s: str) -> dict[str, Any]:
    body = json.loads(s.strip().splitlines()[-1])
    assert not [k for k in body if FORBIDDEN.search(k)], body
    return body


def test_run_cli_preserves_the_event_log_on_mid_run_failure(monkeypatch, tmp_path, capsys):
    from strategies.trial03 import run as R
    base = _child_gate_off(monkeypatch, tmp_path)
    busy = replace(S.P, cooldown_ms=25 * M)                                # 쿨다운 < 보유 → 포지션 중 적격 → PositionBusyError

    def failing(bars, fundings, oi, unusable, arm, variant, **k):
        return H.run_arm_with_fixture_rules(bars, fundings, oi, unusable, arm, variant, rules=S.RULES, p=busy, window=S.WINDOW)
    monkeypatch.setattr(H, "run_arm", failing)
    out = base / "runs" / "L_base"
    rc = R.main(["--arm", "L", "--variant", "base", "--prepared", str(base / "prepared"), "--evaluator-commit", "0" * 40,
                 "--out", str(out)])
    assert rc == 7
    assert sorted(p.name for p in out.iterdir()) == sorted(O.FAILURE_FILES)
    events = [json.loads(ln) for ln in (out / "_failure_events.jsonl").read_text().splitlines()]
    assert events and events[-1]["kind"] == "busy"
    state = json.loads((out / "_failure_state.json").read_text())
    assert state["n_events"] == len(events) and state["arm"] == "L" and state["window_bars"] > 0
    assert "PositionBusyError" in (out / "_failure_error.txt").read_text()
    assert _stdout_clean(capsys.readouterr().out)["failure"] == "run"
    with pytest.raises(O.ContractError):
        O.read_run(out, "L", "base")


def test_run_cli_success_stdout_is_counts_only(monkeypatch, tmp_path, capsys):
    from strategies.trial03 import run as R
    base = _child_gate_off(monkeypatch, tmp_path)
    monkeypatch.setattr(H, "run_arm", lambda bars, f, oi, un, arm, var, **k: H.run_arm_with_fixture_rules(
        bars, f, oi, un, arm, var, rules=S.RULES, p=S.P, window=S.WINDOW))
    rc = R.main(["--arm", "L", "--variant", "base", "--prepared", str(base / "prepared"), "--evaluator-commit", "0" * 40,
                 "--out", str(base / "runs" / "L_base")])
    assert rc == 0
    assert set(_stdout_clean(capsys.readouterr().out)) == {"arm", "variant", "n_trades", "window_bars", "qualified"}


def test_run_cli_gate_failure_is_rc8_with_the_error_only(chain, monkeypatch, capsys):
    from strategies.trial03 import run as R
    monkeypatch.setenv("T3_STAGE_REPO", str(chain["repo"]))
    monkeypatch.setenv("T3_STAGE_ORIGIN", chain["C1"])                     # 실행기가 fetch한 origin과 다르다
    out = chain["base"] / "runs" / "L_base"
    rc = R.main(["--arm", "L", "--variant", "base", "--prepared", str(chain["base"] / "prepared"), "--evaluator-commit", chain["H"],
                 "--out", str(out)])
    assert rc == 8 and [p.name for p in out.iterdir()] == ["_failure_error.txt"]
    assert "ProvenanceError" in (out / "_failure_error.txt").read_text()
    assert _stdout_clean(capsys.readouterr().out)["failure"] == "pre_strategy"


def _p1_base(base: Path) -> None:
    run = _base_run("L")
    O.write_run(O.run_dir(base, "L", "base"), run, v_days(run.strategy, complete_days(SCS["L"].bars())),
                tf_v1_sha256=A.TF_V1_SHA256, rules_sha256=A.RULES_SNAPSHOT_SHA256)


def test_p1_cli_preserves_completed_draws_on_failure_and_success_is_counts_only(monkeypatch, tmp_path, capsys):
    from backtest import p1_t3_run as PR
    base = _child_gate_off(monkeypatch, tmp_path)
    _p1_base(base)
    monkeypatch.setattr(T.Stages, "check_record", lambda *a, **k: None)
    sc = SCS["L"]
    real_draw = P1.draw

    def flaky(d, *a, **k):
        if d == 3:
            raise ZeroDivisionError("draw 3")
        return real_draw(d, *a, **k)
    monkeypatch.setattr(P1, "draw", flaky)
    monkeypatch.setattr(P1, "run_range", lambda arm, tr, b, f, lo, hi: P1.run_range_with_fixture_rules(
        arm, tr, sc.bars(), sc.fundings(), lo, hi, rules=S.RULES, window=S.WINDOW))
    out = O.p1_parts_dir(base, "L") / "part_000_009"
    args = ["--arm", "L", "--lo", "0", "--hi", "9", "--prepared", str(base / "prepared"), "--evaluator-commit", "0" * 40,
            "--out", str(out)]
    assert PR.main(args) == 7
    assert sorted(p.name for p in out.iterdir()) == ["_failure_draws.json", "_failure_error.txt", "_failure_null.jsonl"]
    assert [d["draw"] for d in json.loads((out / "_failure_draws.json").read_text())] == [0, 1, 2]
    assert "ZeroDivisionError" in (out / "_failure_error.txt").read_text()
    assert _stdout_clean(capsys.readouterr().out)["draws_done"] == 3
    monkeypatch.setattr(P1, "draw", real_draw)
    out2 = O.p1_parts_dir(base, "L") / "part_010_019"
    assert PR.main(args[:2] + ["--lo", "10", "--hi", "19"] + args[6:-1] + [str(out2)]) == 0
    assert set(_stdout_clean(capsys.readouterr().out)) == {"arm", "lo", "hi", "n_source", "draws", "ok"}
    wrong = O.p1_parts_dir(base, "L") / "elsewhere"
    assert PR.main(args[:-1] + [str(wrong)]) == 8


def test_zero_source_merge_still_requires_exact_range_coverage():
    sc = S.Scenario()
    z = P1.run_range_with_fixture_rules("L", [], sc.bars(), sc.fundings(), 0, 19, rules=S.RULES, window=S.WINDOW)
    with pytest.raises(P1.P1Error):
        P1.merge([z], draws_total=40)
    assert not P1.merge([z, replace(z, lo=20, hi=39)], draws_total=40)["computable"]


def test_p1_cli_requires_the_base_run_record(monkeypatch, tmp_path, capsys):
    from backtest import p1_t3_run as PR
    base = _child_gate_off(monkeypatch, tmp_path)
    _p1_base(base)
    out = O.p1_parts_dir(base, "L") / "part_000_009"
    args = ["--arm", "L", "--lo", "0", "--hi", "9", "--prepared", str(base / "prepared"), "--evaluator-commit", "0" * 40,
            "--out", str(out)]
    assert PR.main(args) == 8                                               # 기본 실행 기록 없음
    assert "L_base" in (out / "_failure_error.txt").read_text()
    capsys.readouterr()


# ── Codex (g) after-pass 보강 ────────────────────────────────────────────────
def test_real_isolated_child_meets_the_runner_contract(chain, monkeypatch):
    """가짜 실행기 없이: run_isolated(--out 덧붙임 · cwd · env) → 실제 자식 CLI가 관문·핀·영수증을 통과하고 캡처 범위에서 rc 8."""
    from backtest.replay import run_isolated
    for m in ("strategies.trial03.run", "backtest.p1_t3_run"):
        monkeypatch.delitem(sys.modules, m, raising=False)
    st = _prepared(chain)
    st.runner = run_isolated
    prov = st.receipt_ok(st.begin())
    assert st.run_one("L_base", st.run_job("L", "base"), prov | {"variant": "L_base"}) == 8
    body = json.loads((st.records / "L_base.json").read_text())
    assert body["run"]["returncode"] == 8 and body["children_max_rss_kb"] > 0
    err = (st.records / "failures" / "L_base" / "_failure_error.txt").read_text()
    assert "캡처 범위" in err and "ProvenanceError" not in err                # 관문은 통과했다
    assert json.loads(body["run"]["stdout"].strip()) == {"arm": "L", "variant": "base", "failure": "pre_strategy"}
    with pytest.raises(T.StageFailed, match="실패 기록"):
        st.stage_runs(1, only="L_base")


def test_child_timeout_is_a_recorded_failure_and_not_rerun(chain):
    class Slow(FakeRunner):
        def __call__(self, module, args, out, *, timeout_s, env):
            if module == T.STRATEGY:
                out.mkdir(parents=True, exist_ok=True)
                raise subprocess.TimeoutExpired(["x"], timeout_s)
            return super().__call__(module, args, out, timeout_s=timeout_s, env=env)
    st = _prepared(chain, Slow())
    with pytest.raises(T.StageFailed, match="L_base"):
        st.stage_runs(1, only="L_base")
    body = json.loads((st.records / "L_base.json").read_text())
    assert body["run"]["returncode"] == -1 and "TimeoutExpired" in body["run"]["stderr"]
    with pytest.raises(T.StageFailed, match="실패 기록"):
        st.stage_runs(1, only="L_base")


def test_crashed_run_leaves_an_empty_dir_that_is_refused(chain):
    st = _prepared(chain)
    (st.runs / "L_base").mkdir(parents=True)
    with pytest.raises(T.StageFailed, match="기록 없는"):
        st.stage_runs(1, only="L_base")


def test_prepare_with_partial_raw_and_no_record_is_refused(chain):
    st = _stages(chain)
    (st.prep / "raw").mkdir(parents=True)
    (st.prep / "raw" / "funding.jsonl").write_text("")
    with pytest.raises(T.StageFailed, match="기록 없는"):
        st.stage_prepare()


def test_newer_pins_on_origin_are_detected(chain):
    st = _prepared(chain)
    r = chain["repo"]
    _git(r, "checkout", "-q", "-b", "other")
    pf = r / PV.PINS_REL
    pf.write_text(pf.read_text().replace('"is_grid_slots"', '"is_grid_slots" ', 1))
    _git(r, "commit", "-qam", "newer pins elsewhere")
    _git(r, "push", "-q", "origin", "other:main")
    _git(r, "checkout", "-q", "main")
    _git(r, "fetch", "-q", "origin")
    with pytest.raises(PV.ProvenanceError, match="origin/main의 데이터 핀"):
        PV.load_pins(r, fetch_first=False)
    assert st  # 준비 기록은 그대로


def test_parent_refuses_a_repo_whose_code_differs_from_the_running_code(chain):
    f = chain["repo"] / "backtest" / "returns.py"
    f.write_text(f.read_text() + "# drift\n")
    with pytest.raises(PV.ProvenanceError, match="실행 중인 코드"):
        _stages(chain).begin()
    with pytest.raises(E.Refusal, match="실행 중인 코드"):
        E.evaluate(chain["base"], chain["repo"], evaluator_commit=chain["H"], fetch=False)


def test_repeated_row_token_is_refused_even_with_equal_values():
    h = "a" * 64
    with pytest.raises(PV.ProvenanceError, match="둘 이상"):
        PV._tokens(f"| t3_conventions={h} · t3_conventions={h} |")
    with pytest.raises(PV.ProvenanceError, match="둘 이상"):
        PV._tokens(f"| t3_conventions={h} · t3_conventions=oops |")
    with pytest.raises(PV.ProvenanceError, match="형식"):
        PV._tokens(f"| t3_freeze_H={h[:40]}) |")
    with pytest.raises(PV.ProvenanceError, match="형식"):
        PV._tokens(f"| t3_freeze_H=`{h[:40]}` |")                        # 키와 값 사이 기호 없음
    assert PV._tokens(f"| `t3_freeze_H={h[:40]}` · 기타 |") == {"t3_freeze_H": h[:40]}


def test_merge_record_requires_success_and_the_three_outputs(chain, monkeypatch):
    st = _prepared(chain)
    st.stage_runs(3)
    st.stage_p1(1, 1)
    st.stage_p1_merge()
    prov = st.receipt_ok(st.begin())
    rec = st.records / "P1_merge_L.json"
    body = json.loads(rec.read_text())
    rec.write_text(json.dumps(body | {"returncode": 1}))
    with pytest.raises(T.StageFailed, match="병합 기록"):
        st.check_merge_record("L", prov)
