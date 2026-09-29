"""`scripts/t2_make_pins.py` — 매니페스트에서 data_pins.json과 레지스트리 핀 행을 만들고, `load_pins`와 같은 검사기로 확인한다."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from backtest import prepare_t2 as PT
from backtest import t2_provenance as PV

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("t2_make_pins", ROOT / "scripts" / "t2_make_pins.py")
assert spec and spec.loader
MP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MP)


def manifest(tmp: Path) -> Path:
    m = {"raw": {n: f"{i:x}" * 64 for i, n in enumerate(PT.RAW_FILES, 1)},
         **{n: f"{i:x}" * 64 for i, n in enumerate(PT.PREPARED, 7)}, "code_commit": "c", "window": "IS+warmup21"}
    p = tmp / "manifest.json"
    p.write_text(json.dumps(m))
    return p


def test_pins_and_row_pass_the_shared_checker(tmp_path):
    pins, row = MP.make(manifest(tmp_path), row_no=38, date="2026-09-29")
    assert set(pins) == {"raw", "prepared"} and set(pins["prepared"]) == set(PT.PREPARED) and set(pins["raw"]) == set(PT.RAW_FILES)
    reg = "| 37 | 다른 행 |\n" + row + "\n"
    PV.check_pins_registry(reg, pins)
    assert row.count(PV.PINS_REL) == 1 and "manifest.json=" not in row


def test_checker_rejects_second_pins_row(tmp_path):
    pins, row = MP.make(manifest(tmp_path), row_no=38, date="2026-09-29")
    with pytest.raises(PV.ProvenanceError):
        PV.check_pins_registry(row + "\n" + row + "\n", pins)


def test_write_refuses_existing_pins_file(tmp_path):
    pins, row = MP.make(manifest(tmp_path), row_no=38, date="2026-09-29")
    target = tmp_path / "data_pins.json"
    MP.write(pins, target)
    with pytest.raises(FileExistsError):
        MP.write(pins, target)
