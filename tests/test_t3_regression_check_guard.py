"""`scripts/t3_regression_check.py` 출력 관문 — 저장소 안 · 이미 있는 경로는 디렉터리를 만들기 전에 거부(트라이얼 #4 (b) · Codex MAJOR 2)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("t3_regression_check", ROOT / "scripts" / "t3_regression_check.py")
assert spec and spec.loader
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


@pytest.mark.parametrize("rel", ["docs/trials/trial_03/records/x", "var/t3/IS/x", "tmp_scratch_inside_repo"])
def test_output_inside_repo_is_refused_before_creation(rel):
    out = (ROOT / rel).resolve()
    with pytest.raises(SystemExit):
        M.check_out(out)
    assert not out.exists()


def test_existing_output_outside_repo_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        M.check_out(tmp_path.resolve())
    M.check_out((tmp_path / "new").resolve())
