"""`backtest/t2_provenance.py` — 푸시 선행(G1) · 지문(G10) · 핀(G7) · 영수증(G11·G13) · 기록(G3). 임시 git 저장소만."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from backtest import t2_provenance as PV


def git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(origin)], check=True)
    r = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(r)], check=True, capture_output=True)
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    for f in PV.EVALUATOR_FILES + ("strategies/trial02/strategy.py", "pyproject.toml"):
        (r / f).parent.mkdir(parents=True, exist_ok=True)
        (r / f).write_text(f"# {f}\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "evaluator")
    return r


def push(r: Path) -> None:
    git(r, "push", "-q", "origin", "HEAD:main")


def test_evaluator_must_be_pushed(repo):
    h = PV.head(repo)
    with pytest.raises(PV.ProvenanceError):
        PV.require_evaluator_frozen(repo, h)
    push(repo)
    PV.require_evaluator_frozen(repo, h)


def test_evaluator_file_changed_after_push_or_dirty_tree_refused(repo):
    h = PV.head(repo)
    push(repo)
    (repo / PV.EVALUATOR_FILES[0]).write_text("# changed\n")
    with pytest.raises(PV.ProvenanceError):
        PV.require_evaluator_frozen(repo, h)                      # 더러운 트리
    git(repo, "commit", "-qam", "edit evaluator")
    push(repo)
    with pytest.raises(PV.ProvenanceError):
        PV.require_evaluator_frozen(repo, h)                      # 푸시된 H 뒤에 판정기가 바뀜


def test_fingerprint_changes_with_execution_code(repo):
    a = PV.fingerprint(repo)
    (repo / "strategies/trial02/strategy.py").write_text("# other\n")
    assert PV.fingerprint(repo) != a


def pins_file(repo: Path, raw: str = "r") -> dict:
    pins = {"raw": {"archive_rows.jsonl": raw}, "prepared": {"bars_1m.parquet": "b", "funding.json": "f", "source_audit.json": "s"}}
    (repo / PV.PINS_REL).parent.mkdir(parents=True, exist_ok=True)
    (repo / PV.PINS_REL).write_text(json.dumps(pins))
    return pins


def test_pins_must_be_tracked_clean_and_pushed(repo):
    pins_file(repo)
    with pytest.raises(PV.ProvenanceError):
        PV.load_pins(repo)                                        # 추적 안 됨
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "pins")
    with pytest.raises(PV.ProvenanceError):
        PV.load_pins(repo)                                        # 푸시 전
    push(repo)
    p, c = PV.load_pins(repo)
    assert p["raw"] == {"archive_rows.jsonl": "r"} and c == PV.head(repo)
    pins_file(repo, raw="x")
    with pytest.raises(PV.ProvenanceError):
        PV.load_pins(repo)                                        # 커밋 안 된 변경


def test_receipt_binds_manifest_and_pins_commit(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    (prep / "manifest.json").write_text('{"a": 1}')
    pins = {"raw": {"x": "1"}, "prepared": {"y": "2"}}
    rec = PV.make_receipt(prep, pins, "C1", "E1", "F1")
    PV.check_receipt(rec, prepared=prep, pins=pins, pins_c="C1", evaluator_commit="E1", fp="F1")
    (prep / "manifest.json").write_text('{"a": 2}')                 # 매니페스트만 바뀜
    with pytest.raises(PV.ProvenanceError):
        PV.check_receipt(rec, prepared=prep, pins=pins, pins_c="C1", evaluator_commit="E1", fp="F1")
    (prep / "manifest.json").write_text('{"a": 1}')
    for kw in (dict(pins_c="C2"), dict(evaluator_commit="E2"), dict(fp="F2")):
        args = dict(pins_c="C1", evaluator_commit="E1", fp="F1") | kw
        with pytest.raises(PV.ProvenanceError):
            PV.check_receipt(rec, prepared=prep, pins=pins, **args)


def test_record_outputs_and_provenance(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "trades.jsonl").write_text("x\n")
    rec = {"run": {"returncode": 0, "outputs": {"trades.jsonl": PV.sha_file(out / "trades.jsonl")}},
           "provenance": {"fingerprint": "F", "variant": "A"}}
    PV.check_record(rec, out_dir=out, expect={"fingerprint": "F", "variant": "A"})
    with pytest.raises(PV.ProvenanceError):
        PV.check_record(rec, out_dir=out, expect={"fingerprint": "G", "variant": "A"})
    (out / "trades.jsonl").write_text("y\n")
    with pytest.raises(PV.ProvenanceError):
        PV.check_record(rec, out_dir=out, expect={"fingerprint": "F", "variant": "A"})
    (out / "trades.jsonl").unlink()
    with pytest.raises(PV.ProvenanceError):
        PV.check_record(rec, out_dir=out, expect={"fingerprint": "F", "variant": "A"})


def test_dirty_non_evaluator_file_refused(repo):
    h = PV.head(repo)
    push(repo)
    (repo / "strategies/trial02/strategy.py").write_text("# uncommitted\n")
    with pytest.raises(PV.ProvenanceError):
        PV.require_evaluator_frozen(repo, h)
