"""트라이얼 #1 앵커 상수 — 사전등록 문서·레지스트리 #18과 기계적으로 일치해야 한다."""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from strategies.trial01 import anchor as A

ROOT = Path(__file__).resolve().parent.parent


def _iso(ms: int) -> str:
    t = dt.datetime.fromtimestamp(ms / 1000, dt.UTC)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def test_oos_end_is_derived_from_created_time_not_typed():
    assert _iso(A.OOS_END_MS) == "2026-09-20T23:59:59.999Z"
    assert A.oos_end_from_created("2026-09-19T01:30:00.000Z") == A.oos_end_from_created("2026-09-19T00:00:00.000Z")
    assert _iso(A.oos_end_from_created("2026-09-19T01:30:00.000Z")) == "2026-09-18T23:59:59.999Z", "사전등록 §5의 예시"


def test_windows_match_the_preregistration():
    assert _iso(A.IS_START_MS) == "2024-01-01T00:00:00.000Z" and _iso(A.IS_END_MS) == "2026-06-30T23:59:59.999Z"
    assert _iso(A.OOS_START_MS) == "2026-07-01T00:00:00.000Z" and A.OOS_START_MS == A.IS_END_MS + 1


def test_the_anchored_document_is_unchanged_and_sr_v1_matches_its_table():
    doc = (ROOT / A.PREREG_PATH).read_bytes()
    assert hashlib.sha256(doc).hexdigest() == A.PREREG_SHA256, "앵커된 사전등록 문서는 바뀌면 안 된다"
    lines = doc.decode("utf-8").splitlines()
    i0 = lines.index("| 항목 | 값(사전확약) |")
    i1 = i0
    while i1 + 1 < len(lines) and lines[i1 + 1].startswith("|"):
        i1 += 1
    table = "\n".join(lines[i0:i1 + 1]) + "\n"
    assert (i0 + 1, i1 + 1) == (17, 45)
    assert hashlib.sha256(table.encode("utf-8")).hexdigest() == A.SR_V1_SHA256


def test_registry_row_18_carries_the_same_anchor_values():
    reg = (ROOT / "docs" / "trial_registry.md").read_text(encoding="utf-8")
    row = [ln for ln in reg.splitlines() if ln.startswith("| 18 |")][0]
    for v in (A.ANCHOR_CREATED_TIME, A.PREREG_SHA256, A.SR_V1_SHA256, "20260921", "2026-09-20T23:59:59.999Z", A.ANCHOR_DRIVE_FILE_ID):
        assert v in row, v
    assert A.N_TRIALS == 2 and A.P1_MASTER_SEED == 20260921 and A.P1_DRAWS == 1000
