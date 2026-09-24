"""트라이얼 #2 앵커 상수 — 앵커된 사전등록·레지스트리 #35·#36과 기계적으로 일치해야 한다(단계 2a)."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
from pathlib import Path

from strategies.trial02 import anchor as A

ROOT = Path(__file__).resolve().parent.parent


def _iso(ms: int) -> str:
    t = dt.datetime.fromtimestamp(ms / 1000, dt.UTC)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def test_anchored_document_unchanged_and_bo_v1_matches_its_table():
    doc = (ROOT / A.PREREG_PATH).read_bytes()
    assert hashlib.sha256(doc).hexdigest() == A.PREREG_SHA256
    lines = doc.decode("utf-8").splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith("| 항목 | 값(사전확약) |"))
    i1 = i0
    while i1 + 1 < len(lines) and lines[i1 + 1].startswith("|"):
        i1 += 1
    assert (i0 + 1, i1 + 1) == (25, 53)
    table = "\n".join(lines[i0:i1 + 1]) + "\n"
    assert hashlib.sha256(table.encode("utf-8")).hexdigest() == A.BO_V1_SHA256


def test_oos_end_is_derived_mechanically():
    assert _iso(A.OOS_END_MS) == "2026-09-23T23:59:59.999Z"
    assert _iso(A.oos_end_from_created("2026-09-24T00:00:00.000Z")) == "2026-09-23T23:59:59.999Z"
    assert (A.OOS_END_MS + 1 - A.OOS_START_MS) // 86_400_000 == 85


def test_windows_and_warmup():
    assert _iso(A.IS_START_MS) == "2024-01-01T00:00:00.000Z" and _iso(A.IS_END_MS) == "2026-06-30T23:59:59.999Z"
    assert A.OOS_START_MS == A.IS_END_MS + 1 and _iso(A.OOS_START_MS) == "2026-07-01T00:00:00.000Z"
    assert A.WARMUP_DAYS == 21


def test_multiple_testing_constants():
    assert A.N_TRIALS == 4 and A.ALPHA == 0.0125 and A.LEVEL == 0.9875
    assert (A.CI_LO_PCT, A.CI_HI_PCT) == (0.625, 99.375)
    from statistics import NormalDist
    assert round(NormalDist().inv_cdf(1 - A.ALPHA), 4) == 2.2414, "§3-1 z_0.9875"


def test_trial01_sr_hats_match_the_pinned_fixture():
    fx = json.loads((ROOT / "tests" / "fixtures" / "trial01_sr_pinned.json").read_text())
    assert fx["_meta"]["report_sha256"] == A.TRIAL01_REPORT_SHA256
    assert (A.SR_1A, A.SR_1B) == (fx["sr_A"], fx["sr_B"])


def test_rules_snapshot_hashes():
    for name, sha in A.RULES_SNAPSHOT_SHA256.items():
        assert hashlib.sha256((ROOT / A.RULES_SNAPSHOT_DIR / f"{name}.json").read_bytes()).hexdigest() == sha, name


def test_registry_rows_carry_the_same_values():
    reg = (ROOT / "docs" / "trial_registry.md").read_text(encoding="utf-8").splitlines()
    r35 = next(ln for ln in reg if ln.startswith("| 35 |"))
    for v in (A.ANCHOR_CREATED_TIME, A.ANCHOR_DRIVE_FILE_ID, A.PREREG_SHA256, A.BO_V1_SHA256, "2026-09-23T23:59:59.999Z",
              "N = 4", "20260924"):
        assert v in r35, v
    r36 = next(ln for ln in reg if ln.startswith("| 36 |"))
    for sha in A.RULES_SNAPSHOT_SHA256.values():
        assert sha in r36


def test_seeds():
    assert A.MASTER_SEED == 20260924 and A.P1_DRAWS == 1000 and A.P4_DRAWS == 200 and A.P4_MIN_DEFINED == 190
    assert A.P1_FAIL_MAX == 10 and A.BOOTSTRAP_SEED == (20260924, 1) and A.BOOTSTRAP_RESAMPLES == 10_000
    assert A.BOOTSTRAP_STREAMS == {"gross_A": 0, "net_A": 1, "gross_B": 2, "net_B": 3, "ab_daily": 4}


def test_does_not_import_trial01():
    tree = ast.parse((ROOT / "strategies" / "trial02" / "anchor.py").read_text(encoding="utf-8"))
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + \
           [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(m and "trial01" in m for m in mods)
