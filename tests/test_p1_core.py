"""단계 2f F1 — P1 공통 기계를 트라이얼 import 없이 분리해도 트라이얼 #1 결과가 바이트 단위로 같다(리팩터 전 트리에서 만든 골든)."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_trial01_p1_matches_pre_refactor_golden():
    from tests.fixtures.p1_golden_scenario import run
    gold = (ROOT / "tests" / "fixtures" / "golden_p1_trial01.json").read_text()
    assert json.dumps(run(), sort_keys=True) + "\n" == gold                  # 바이트(문자열) 동일


def test_p1_core_imports_no_trial():
    src = (ROOT / "backtest" / "p1_core.py").read_text(encoding="utf-8")
    mods = [n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)]
    assert not any(m and "strategies" in m for m in mods)
