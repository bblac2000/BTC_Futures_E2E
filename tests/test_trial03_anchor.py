"""트라이얼 #3 앵커 상수 — 앵커된 사전등록 r3·레지스트리 #47~#50과 기계적으로 일치해야 한다(단계 2 · 계획 r5)."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np

from strategies.trial03 import anchor as A

ROOT = Path(__file__).resolve().parent.parent


def _iso(ms: int) -> str:
    t = dt.datetime.fromtimestamp(ms / 1000, dt.UTC)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def test_anchored_document_unchanged_and_tf_v1_is_lines_20_to_39():
    doc = (ROOT / A.PREREG_PATH).read_bytes()
    assert hashlib.sha256(doc).hexdigest() == A.PREREG_SHA256
    assert len(doc) == 36_450
    lines = doc.decode("utf-8").splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith("| 항목 | 값(사전확약) |"))
    i1 = i0
    while i1 + 1 < len(lines) and lines[i1 + 1].startswith("|"):
        i1 += 1
    assert (i0 + 1, i1 + 1) == A.TF_V1_LINES == (20, 39)
    table = "\n".join(lines[i0:i1 + 1]) + "\n"
    assert hashlib.sha256(table.encode("utf-8")).hexdigest() == A.TF_V1_SHA256


def test_anchor_identity():
    assert A.ANCHOR_CREATED_TIME == "2026-09-29T09:31:46.486Z"
    assert A.ANCHOR_DRIVE_FILE_ID == "1mMh8xPbPuXAjS1dli6QaRyE7H9MKxt8V"


def test_window_b_and_oos_end_mechanical():
    assert _iso(A.WARMUP_START_MS) == "2023-10-02T00:00:00.000Z"
    assert _iso(A.IS_START_MS) == "2024-01-01T00:00:00.000Z"
    assert _iso(A.IS_END_MS) == "2025-12-31T23:59:59.999Z"
    assert A.OOS_START_MS == A.IS_END_MS + 1
    assert _iso(A.OOS_END_MS) == "2026-09-28T23:59:59.999Z"
    assert (A.OOS_END_MS + 1 - A.OOS_START_MS) // A.DAY_MS == 271
    assert (A.IS_START_MS - A.WARMUP_START_MS) // A.DAY_MS == 91          # 90일 분위수 표본 + r30 30분 전(2023-10-02 23:30)


def test_multiple_testing_constants_exact():
    assert A.N_TRIALS == 6
    assert A.ALPHA == 0.05 / 6 and A.LEVEL == 1 - 0.05 / 6
    assert A.CI_LO_Q == A.ALPHA / 2 and A.CI_HI_Q == 1 - A.ALPHA / 2
    assert round(A.CI_LO_Q * 100, 5) == 0.41667 and round(A.CI_HI_Q * 100, 5) == 99.58333   # §0 표시값
    from statistics import NormalDist
    assert round(NormalDist().inv_cdf(1 - A.ALPHA), 4) == 2.3940, "§3-1 z_0.991667"


def test_pinned_sr_hats():
    f1 = json.loads((ROOT / "tests" / "fixtures" / "trial01_sr_pinned.json").read_text())
    f2 = json.loads((ROOT / "tests" / "fixtures" / "trial02_sr_pinned.json").read_text())
    assert f1["_meta"]["report_sha256"] == A.TRIAL01_REPORT_SHA256
    assert f2["_meta"]["report_sha256"] == A.TRIAL02_REPORT_SHA256
    assert (A.SR_1A, A.SR_1B, A.SR_2A, A.SR_2B) == (f1["sr_A"], f1["sr_B"], f2["sr_A"], f2["sr_B"])
    assert A.PINNED_SR == (A.SR_1A, A.SR_1B, A.SR_2A, A.SR_2B)


def test_seeds_and_streams():
    assert A.MASTER_SEED == 20260929
    assert A.BOOTSTRAP_SEED == (20260929, 1) and A.BOOTSTRAP_SPAWN == 8
    assert A.BOOTSTRAP_STREAMS == {"IS": {"gross_L": 0, "net_L": 1, "gross_S": 2, "net_S": 3},
                                   "OOS": {"gross_L": 4, "net_L": 5, "gross_S": 6, "net_S": 7}}
    assert A.P1_SEEDS == {"L": (20260929, 2), "S": (20260929, 3)}
    assert (A.P1_DRAWS, A.P1_SLOT_ATTEMPTS, A.P1_FAIL_MAX) == (1000, 1000, 10)
    assert A.BOOTSTRAP_RESAMPLES == 10_000
    a = np.random.SeedSequence(A.P1_SEEDS["L"]).spawn(A.P1_DRAWS)[0].generate_state(4)
    b = np.random.SeedSequence(A.P1_SEEDS["S"]).spawn(A.P1_DRAWS)[0].generate_state(4)
    assert (a != b).any()


def test_rules_snapshot_hashes():
    for name, sha in A.RULES_SNAPSHOT_SHA256.items():
        assert hashlib.sha256((ROOT / A.RULES_SNAPSHOT_DIR / f"{name}.json").read_bytes()).hexdigest() == sha, name


def test_no_other_trial_anchor_imported():
    tree = ast.parse((ROOT / "strategies" / "trial03" / "anchor.py").read_text(encoding="utf-8"))
    mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [m for m in mods if "trial01" in m or "trial02" in m]
