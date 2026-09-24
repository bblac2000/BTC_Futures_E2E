"""`backtest/t2_stages.py` — 선행 검사(G1) · 영수증 문(G11·G13) · 검증된 이어 하기(G3) · P1 병합 기대값. 가짜 러너 + git 검사 대역."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from backtest import t2_provenance as PV
from backtest import t2_stages as T
from backtest.replay import RunRecord

ROOT = Path(__file__).resolve().parent.parent
PINS = {"raw": {"archive_rows.jsonl": "r"}, "prepared": {"bars_1m.parquet": "b", "funding.json": "f", "source_audit.json": "s"}}


class FakeRunner:
    def __init__(self):
        self.calls: list = []

    def __call__(self, module, args, out, timeout_s=0):
        self.calls.append((module, list(args), out))
        out.mkdir(parents=True, exist_ok=True)
        (out / "o.txt").write_text(f"{module} {args}\n")
        return RunRecord(module, list(args), 0, "ok", "", "t0", "t1", "HEAD", "3.12", "2",
                         {"o.txt": hashlib.sha256((out / "o.txt").read_bytes()).hexdigest()})


@pytest.fixture
def stages(tmp_path, monkeypatch):
    monkeypatch.setattr(PV, "require_evaluator_frozen", lambda repo, h, fetch=True: None)
    monkeypatch.setattr(PV, "fingerprint", lambda repo: "FP")
    monkeypatch.setattr(PV, "load_pins", lambda repo, fetch=True: (PINS, "PC"))
    monkeypatch.setattr(PV, "head", lambda repo: "HEAD")
    s = T.Stages("EV", base=tmp_path, repo=tmp_path, runner=FakeRunner(), fetch=False)
    s.prep.mkdir(parents=True)
    (s.prep / "manifest.json").write_text(json.dumps({"raw": PINS["raw"], **PINS["prepared"]}))
    return s


def receipt(s):
    s.records.mkdir(parents=True, exist_ok=True)
    (s.records / "verify_receipt.json").write_text(json.dumps(PV.make_receipt(s.prep, PINS, "PC", "EV", "FP")))


def test_every_stage_runs_the_push_preflight(stages, monkeypatch):
    def refuse(repo, h, fetch=True):
        raise PV.ProvenanceError("unpushed")
    monkeypatch.setattr(PV, "require_evaluator_frozen", refuse)
    for call in (stages.prepare, stages.verify, lambda: stages.arm(["A"], 1), lambda: stages.p1(2, 1), stages.p1_merge):
        with pytest.raises(PV.ProvenanceError):
            call()
    assert stages.runner.calls == []


def test_verify_writes_receipt_and_arms_need_it(stages):
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)                                                  # 영수증 없음
    stages.verify()
    assert (stages.records / "verify_receipt.json").exists()
    stages.arm(["A"], 1)
    assert stages.runner.calls[-1][0] == T.STRATEGY and stages.runner.calls[-1][1][:2] == ["--variant", "A"]


def test_verify_refuses_pins_not_matching_manifest(stages):
    (stages.prep / "manifest.json").write_text(json.dumps({"raw": {"archive_rows.jsonl": "x"}, **PINS["prepared"]}))
    with pytest.raises(PV.ProvenanceError):
        stages.verify()


def test_manifest_only_change_after_receipt_is_refused(stages):
    receipt(stages)
    (stages.prep / "manifest.json").write_text(json.dumps({"raw": PINS["raw"], **PINS["prepared"], "extra": 1}))
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_changed_fingerprint_after_receipt_is_refused(stages, monkeypatch):
    receipt(stages)
    monkeypatch.setattr(PV, "fingerprint", lambda repo: "FP2")
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_resume_skips_verified_and_refuses_tampered(stages):
    receipt(stages)
    stages.arm(["A"], 1)
    n = len(stages.runner.calls)
    stages.arm(["A"], 1)                                                      # 검증된 완료 → 다시 돌리지 않는다
    assert len(stages.runner.calls) == n
    (stages.runs / "A" / "o.txt").write_text("tampered\n")
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_base_and_p1_require_verified_a(stages):
    receipt(stages)
    with pytest.raises(PV.ProvenanceError):
        stages.arm(list(T.BASE_NAMES), 1)
    with pytest.raises(PV.ProvenanceError):
        stages.p1(4, 1)
    stages.arm(["A"], 1)
    stages.arm(list(T.BASE_NAMES), 2)
    assert {c[1][1] for c in stages.runner.calls if c[0] == T.STRATEGY} == {"A", *T.BASE_NAMES}


def test_p1_parts_cover_all_draws_and_merge_uses_record_hashes(stages):
    receipt(stages)
    stages.arm(["A"], 1)
    stages.p1(3, 1)
    ranges = [c[1][c[1].index("--draws") + 1] for c in stages.runner.calls if c[0] == T.P1_MODULE]
    covered = sorted(d for r in ranges for d in range(int(r.split("-")[0]), int(r.split("-")[1]) + 1))
    assert covered == list(range(1000))
    stages.p1_merge()
    exp = json.loads((stages.records / "p1_merge_expect.json").read_text())
    assert len(exp) == 3 and all("o.txt" in v for v in exp.values())
    assert stages.runner.calls[-1][1][0] == "--merge"


def test_p4_names():
    n = T.p4_names()
    assert len(n) == 200 and n[0] == "P4_draw000" and n[-1] == "P4_draw199"


def test_orchestrator_imports_no_strategy():
    src = (ROOT / "backtest" / "t2_stages.py").read_text(encoding="utf-8")
    mods = [n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)]
    assert not any(m and m.startswith("strategies") for m in mods)
