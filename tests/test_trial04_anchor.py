"""트라이얼 #4 앵커 상수 — 앵커된 사전등록 r3·레지스트리 #69·#70과 기계적으로 일치해야 한다(단계 (a))."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np

from strategies.trial04 import anchor as A

ROOT = Path(__file__).resolve().parent.parent


def _iso(ms: int) -> str:
    t = dt.datetime.fromtimestamp(ms / 1000, dt.UTC)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def test_anchored_document_bytes_and_tc_v3_span():
    doc = (ROOT / A.PREREG_PATH).read_bytes()
    assert hashlib.sha256(doc).hexdigest() == A.PREREG_SHA256
    assert hashlib.md5(doc).hexdigest() == A.PREREG_MD5
    assert len(doc) == A.PREREG_SIZE == 28_828
    lines = doc.decode("utf-8").splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith("| 항목 | 값 | 근거 |"))
    i1 = i0
    while i1 + 1 < len(lines) and lines[i1 + 1].startswith("|"):
        i1 += 1
    assert (i0 + 1, i1 + 1) == A.TC_V3_LINES == (16, 39)
    table = ("\n".join(lines[i0:i1 + 1]) + "\n").encode("utf-8")
    assert len(table) == 5_548
    assert hashlib.sha256(table).hexdigest() == A.TC_V3_SHA256


def test_anchor_identity_and_registry_row():
    assert A.ANCHOR_CREATED_TIME == "2026-09-30T10:17:47.203Z"
    assert A.ANCHOR_DRIVE_FILE_ID == "1hqUPOXg3LKarOjbhiyE1DYYOeAdDZvGc"
    row = next(ln for ln in (ROOT / "docs" / "trial_registry.md").read_text().splitlines() if ln.startswith("| 70 |"))
    for v in (A.PREREG_SHA256, A.PREREG_MD5, A.TC_V3_SHA256, A.ANCHOR_CREATED_TIME, A.ANCHOR_DRIVE_FILE_ID):
        assert v in row


def test_windows_and_oos_end_mechanical():
    assert _iso(A.DATA_START_MS) == "2023-10-02T00:00:00.000Z"
    assert _iso(A.WINDOW_START_MS) == "2024-01-01T00:00:00.000Z"
    assert _iso(A.IS_END_MS) == "2025-12-31T23:59:59.999Z"
    assert A.OOS_START_MS == A.IS_END_MS + 1
    assert _iso(A.OOS_END_MS) == "2026-09-29T23:59:59.999Z"
    assert (A.OOS_END_MS + 1 - A.OOS_START_MS) // A.DAY_MS == 272
    assert A.OOS_END_MS == A.oos_end_from_created(A.ANCHOR_CREATED_TIME)


def test_multiple_testing_constants_exact():
    assert A.N_TRIALS == 8
    assert A.ALPHA == 0.05 / 8 == 0.00625 and A.LEVEL == 1 - 0.00625
    assert A.CI_LO_Q == A.ALPHA / 2 == 1 / 320 and A.CI_HI_Q == 1 - 1 / 320
    assert round(A.CI_LO_Q * 100, 4) == 0.3125 and round(A.CI_HI_Q * 100, 4) == 99.6875


def test_pinned_sr_hats_from_three_reports():
    fx = {k: json.loads((ROOT / "tests" / "fixtures" / f"trial0{k}_sr_pinned.json").read_text()) for k in (1, 2, 3)}
    assert fx[1]["_meta"]["report_sha256"] == A.TRIAL01_REPORT_SHA256
    assert fx[2]["_meta"]["report_sha256"] == A.TRIAL02_REPORT_SHA256
    assert fx[3]["_meta"]["report_sha256"] == A.TRIAL03_REPORT_SHA256
    rep3 = (ROOT / "docs" / "trials" / "trial_03" / "records" / "evaluation" / "report.json").read_bytes()
    assert hashlib.sha256(rep3).hexdigest() == A.TRIAL03_REPORT_SHA256
    r3 = json.loads(rep3)
    assert (r3["arms"]["L"]["stats"]["sr"], r3["arms"]["S"]["stats"]["sr"]) == (fx[3]["sr_L"], fx[3]["sr_S"]) == (A.SR_3L, A.SR_3S)
    assert (A.SR_1A, A.SR_1B, A.SR_2A, A.SR_2B) == (fx[1]["sr_A"], fx[1]["sr_B"], fx[2]["sr_A"], fx[2]["sr_B"])
    assert A.PINNED_SR == (A.SR_1A, A.SR_1B, A.SR_2A, A.SR_2B, A.SR_3L, A.SR_3S)


def test_seeds_streams_and_timing_prefix_property():
    assert A.MASTER_SEED == 20260930
    assert A.BOOTSTRAP_SEED == (20260930, 1) and A.BOOTSTRAP_SPAWN == 8 and A.BOOTSTRAP_RESAMPLES == 10_000
    assert A.BOOTSTRAP_STREAMS["IS"] == {"gross_S": 0, "net_S": 1, "gross_L": 2, "net_L": 3}     # r3 §3-1 — S가 먼저
    assert A.P1_SEEDS == {"S": (20260930, 2), "L": (20260930, 3)}                            # r3 §4(e)
    assert (A.P1_DRAWS, A.P1_TIMING_CHILD_OFFSET, A.P1_SLOT_ATTEMPTS, A.P1_FAIL_MAX) == (1000, 1000, 1000, 10)
    for arm in ("S", "L"):
        gate = np.random.SeedSequence(A.P1_SEEDS[arm]).spawn(1000)
        both = np.random.SeedSequence(A.P1_SEEDS[arm]).spawn(2000)
        for d in (0, 999):                                         # 보고 전용 실행이 게이트 자식을 바꾸지 않는다
            assert (gate[d].generate_state(4) == both[d].generate_state(4)).all()
        timing = [both[A.P1_TIMING_CHILD_OFFSET + d].generate_state(4) for d in (0, 999)]
        assert all((t != gate[0].generate_state(4)).any() for t in timing)
    s = np.random.SeedSequence(A.P1_SEEDS["S"]).spawn(1)[0].generate_state(4)
    l_ = np.random.SeedSequence(A.P1_SEEDS["L"]).spawn(1)[0].generate_state(4)
    assert (s != l_).any()


def test_rules_snapshot_hashes_and_meta_label_is_not_read():
    for name, sha in A.RULES_SNAPSHOT_SHA256.items():
        b = (ROOT / A.RULES_SNAPSHOT_DIR / f"{name}.json").read_bytes()
        assert hashlib.sha256(b).hexdigest() == sha, name
        meta = json.loads(b)["_meta"]
        assert meta["captured_at_utc"].startswith("2026-09-30T10:16:")                     # #69 캡처 · #48(2026-09-29)과 다름
    from exchange.loader import rules_from_snapshot_dir
    rules = rules_from_snapshot_dir(ROOT / A.RULES_SNAPSHOT_DIR, "BTCUSDT")
    from decimal import Decimal
    assert rules.commission.taker == Decimal("0.0005")                                       # r3 §2 taker 5 bps
    assert rules.symbol_rules.min_notional == Decimal("50")                                  # r3 결정 3의 20% 천장 근거
    b1 = rules.brackets[0]
    assert b1.maint_margin_ratio == Decimal("0.004") and b1.cum == Decimal("0") and b1.initial_leverage >= 30


def test_no_other_trial_anchor_imported():
    tree = ast.parse((ROOT / "strategies" / "trial04" / "anchor.py").read_text(encoding="utf-8"))
    mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [m for m in mods if any(f"trial0{k}" in m for k in (1, 2, 3))]
