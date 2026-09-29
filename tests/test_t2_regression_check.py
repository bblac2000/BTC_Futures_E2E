"""`scripts/t2_regression_check.py` — 비교·경로 가드만(실행 재현은 실데이터라 스크립트 실행 기록으로 남긴다)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("t2_regression_check", ROOT / "scripts" / "t2_regression_check.py")
assert spec and spec.loader
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def test_refuses_output_inside_trial02_tree():
    with pytest.raises(SystemExit):
        R.check_out(R.T2_BASE / "scratch")
    with pytest.raises(SystemExit):
        R.check_out(R.T2_BASE.parent)
    R.check_out(ROOT / "var" / "t3_regress")


def test_compare_dirs_bytes_and_meta(tmp_path):
    a, b = tmp_path / "rec" / "A", tmp_path / "new" / "A"
    for d in (a, b):
        d.mkdir(parents=True)
        (d / "trades.jsonl").write_text("x\n")
    (a / "meta.json").write_text(json.dumps({"n": 1, "git_head": "a", "gate": {"x": 1}}))
    (b / "meta.json").write_text(json.dumps({"n": 1, "git_head": "b", "gate": None}))
    assert R.compare_dirs(a, b) == []
    (b / "trades.jsonl").write_text("y\n")
    (b / "extra.json").write_text("{}")
    (b / "meta.json").write_text(json.dumps({"n": 2}))
    whys = {(m["file"], m["why"]) for m in R.compare_dirs(a, b)}
    assert whys == {("trades.jsonl", "sha_differs"), ("extra.json", "only_in_rerun"), ("meta.json", "meta_differs")}
