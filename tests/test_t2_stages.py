"""`backtest/t2_stages.py` — 선행 검사(G1) · verify 기록 + 영수증 문(G11·G13) · 검증된 이어 하기(G3: 명령 · 필수 출력 · 해시) ·
P1 병합 · 직접 CLI 문. 가짜 러너(실제 출력 파일 이름을 쓴다) + git 검사 대역."""
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
FILES = {T.PREP_MODULE: T.PREP_OUTPUTS, T.STRATEGY: T.RUN_OUTPUTS, T.P1_MODULE: T.P1_OUTPUTS}


class FakeRunner:
    def __init__(self, omit: str | None = None, rc: int = 0):
        self.calls: list = []
        self.env = None
        self.omit, self.rc = omit, rc

    def __call__(self, module, args, out, timeout_s=0, env=None):
        self.calls.append((module, list(args), out))
        self.env = env
        out.mkdir(parents=True, exist_ok=True)
        for f in FILES[module]:
            if f == "manifest.json" and (out / f).exists():
                continue                                              # 준비 매니페스트는 픽스처가 만든 것 유지
            if f != self.omit:
                (out / f).write_text(f"{module} {args} {f}\n")
        outs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
        return RunRecord(module, list(args), self.rc, "ok", "", "t0", "t1", "HEAD", "3.12", "2", outs)


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


def ready(s):
    s.prepare()
    s.verify()


def test_every_stage_runs_the_push_preflight(stages, monkeypatch):
    def refuse(repo, h, fetch=True):
        raise PV.ProvenanceError("unpushed")
    monkeypatch.setattr(PV, "require_evaluator_frozen", refuse)
    for call in (stages.prepare, stages.verify, lambda: stages.arm(["A"], 1), lambda: stages.p1(2, 1), stages.p1_merge):
        with pytest.raises(PV.ProvenanceError):
            call()
    assert stages.runner.calls == []


def test_prepare_is_idempotent_and_verified(stages):
    stages.prepare()
    n = len(stages.runner.calls)
    assert stages.prepare() == [] and len(stages.runner.calls) == n          # 검증된 완료 → 다시 캡처하지 않는다
    (stages.prep / "funding.json").write_text("changed\n")
    with pytest.raises(PV.ProvenanceError):
        stages.prepare()                                                     # 기록과 다른 산출물 → 오류(덮어쓰지 않는다)


def test_verify_requires_prepare_and_writes_receipt(stages):
    with pytest.raises(PV.ProvenanceError):
        stages.verify()
    ready(stages)
    assert (stages.records / "verify_receipt.json").exists()
    stages.arm(["A"], 1)
    assert stages.runner.calls[-1][0] == T.STRATEGY and stages.runner.calls[-1][1][:2] == ["--variant", "A"]


def test_fabricated_receipt_without_verify_record_is_refused(stages):
    stages.prepare()
    stages.records.mkdir(parents=True, exist_ok=True)
    (stages.records / "verify_receipt.json").write_text(json.dumps(PV.make_receipt(stages.prep, PINS, "PC", "EV", "FP")))
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_prepared_file_change_after_verify_is_refused_even_when_skipping(stages):
    ready(stages)
    stages.arm(["A"], 1)
    (stages.prep / "bars_1m.parquet").write_text("tampered\n")
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)                                                 # A는 건너뛸 차례지만 준비 파일 변경을 잡는다


def test_manifest_only_change_after_receipt_is_refused(stages):
    ready(stages)
    (stages.prep / "manifest.json").write_text(json.dumps({"raw": PINS["raw"], **PINS["prepared"], "extra": 1}))
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_changed_fingerprint_after_receipt_is_refused(stages, monkeypatch):
    ready(stages)
    monkeypatch.setattr(PV, "fingerprint", lambda repo: "FP2")
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_resume_refuses_tampered_output_changed_command_or_missing_required(stages):
    ready(stages)
    stages.arm(["A"], 1)
    n = len(stages.runner.calls)
    stages.arm(["A"], 1)
    assert len(stages.runner.calls) == n
    rec_path = stages.records / "A.json"
    rec = json.loads(rec_path.read_text())
    bad_cmd = json.loads(json.dumps(rec))
    bad_cmd["run"]["args"] = ["--variant", "B", "--prepared", str(stages.prep)]
    rec_path.write_text(json.dumps(bad_cmd))
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)
    omitted = json.loads(json.dumps(rec))
    del omitted["run"]["outputs"]["meta.json"]
    rec_path.write_text(json.dumps(omitted))
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)
    rec_path.write_text(json.dumps(rec))
    (stages.runs / "A" / "trades.jsonl").write_text("tampered\n")
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_base_and_p1_require_verified_a(stages):
    ready(stages)
    with pytest.raises(PV.ProvenanceError):
        stages.arm(list(T.BASE_NAMES), 1)
    with pytest.raises(PV.ProvenanceError):
        stages.p1(4, 1)
    stages.arm(["A"], 1)
    stages.arm(list(T.BASE_NAMES), 2)
    assert {c[1][1] for c in stages.runner.calls if c[0] == T.STRATEGY} == {"A", *T.BASE_NAMES}


def test_p1_parts_cover_all_draws_merge_is_verified_and_not_rerun(stages):
    ready(stages)
    stages.arm(["A"], 1)
    stages.p1(3, 1)
    ranges = [c[1][c[1].index("--draws") + 1] for c in stages.runner.calls if c[0] == T.P1_MODULE]
    covered = sorted(d for r in ranges for d in range(int(r.split("-")[0]), int(r.split("-")[1]) + 1))
    assert covered == list(range(1000))
    stages.p1_merge()
    exp = json.loads((stages.records / "p1_merge_expect.json").read_text())
    assert len(exp) == 3 and all("p1_draws.json" in v for v in exp.values())
    n = len(stages.runner.calls)
    assert stages.p1_merge() == [] and len(stages.runner.calls) == n
    (stages.runs / "P1_merged" / "p1_null.jsonl").write_text("tampered\n")
    with pytest.raises(PV.ProvenanceError):
        stages.p1_merge()


def test_unrecorded_extra_output_file_is_refused(stages):
    """출력 디렉터리 파일 집합 = 기록 — 조건부 파일(p1_not_computable.json 등)을 기록에서 빼는 변조를 잡는다."""
    ready(stages)
    stages.arm(["A"], 1)
    (stages.runs / "A" / "p1_not_computable.json").write_text("{}\n")
    with pytest.raises(PV.ProvenanceError):
        stages.arm(["A"], 1)


def test_cli_gate_requires_receipt_and_verify_record(stages, monkeypatch):
    with pytest.raises(PV.ProvenanceError):
        T.gate_cli(stages.prep, repo=stages.repo)
    ready(stages)
    g = T.gate_cli(stages.prep, repo=stages.repo)
    assert g["evaluator_commit"] == "EV" and g["pins_commit"] == "PC"
    (stages.records / "verify.json").unlink()
    with pytest.raises(PV.ProvenanceError):
        T.gate_cli(stages.prep, repo=stages.repo)


def test_p4_names():
    n = T.p4_names()
    assert len(n) == 200 and n[0] == "P4_draw000" and n[-1] == "P4_draw199"


def test_orchestrator_imports_no_strategy():
    src = (ROOT / "backtest" / "t2_stages.py").read_text(encoding="utf-8")
    mods = [n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)]
    assert not any(m and m.startswith("strategies") for m in mods)


def test_code_change_mid_stage_is_refused(stages, monkeypatch):
    """K4: 긴 단계 도중 코드가 바뀌면(지문 변경) 다음 하위 프로세스 전에 멈춘다."""
    ready(stages)
    stages.arm(["A"], 1)
    calls = {"n": 0}

    def fp(repo):
        calls["n"] += 1
        return "FP" if calls["n"] <= 2 else "FP_CHANGED"             # 선행 검사 · 첫 실행 뒤 바뀜
    monkeypatch.setattr(PV, "fingerprint", fp)
    with pytest.raises(PV.ProvenanceError):
        stages.arm(list(T.BASE_NAMES), 1)
    assert len([c for c in stages.runner.calls if c[0] == T.STRATEGY]) < 1 + len(T.BASE_NAMES)
