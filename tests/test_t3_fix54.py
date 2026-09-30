"""트라이얼 #3 레지스트리 #54 수정 — 워밍업 빈 mark 펀딩 행 버림(prepare_t3 한정) · 동결 행 버전화(t3_provenance).

실데이터 없음 · 캡처 픽스처는 tests/test_prepare_t3 · 임시 저장소 사슬은 tests/test_t3_stages.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from backtest import prepare_t3 as P
from backtest import t3_provenance as PV
from strategies.trial03 import anchor as A
from tests import test_prepare_t3 as TP
from tests.test_t3_stages import _append_row, _commit, _git, build_chain

ROOT = Path(__file__).resolve().parent.parent
H8 = 8 * 3_600_000
W = A.WINDOW_START_MS


def row(ms: int, mark: Any = "", rate: str = "0.0001", **kw: Any) -> dict[str, Any]:
    r = {"symbol": "BTCUSDT", "fundingTime": ms, "fundingRate": rate, "markPrice": mark, "rateType": "Regular"} | kw
    if mark is KeyError:
        del r["markPrice"]
    return r


def write_funding(raw: Path, pages: list[list[dict[str, Any]]]) -> bytes:
    b = "".join(json.dumps({"page": p}) + "\n" for p in pages).encode()
    (raw / "funding.jsonl").write_bytes(b)
    return b


def captured(tmp: Path) -> Path:
    return TP.capture(tmp)


@pytest.fixture
def chain(tmp_path) -> dict[str, Any]:
    return build_chain(tmp_path)


WARM88 = [row(A.DATA_START_MS + i * H8) for i in range(88)]


# ── 버림 규칙 ────────────────────────────────────────────────────────────────
def test_88_warmup_empty_marks_are_dropped_and_audited(tmp_path):
    out = captured(tmp_path)
    raw_b = write_funding(out / "raw", [WARM88, []])
    m = P.build(out, (TP.START, TP.END))
    d = json.loads((out / "source_audit.json").read_text())["price"][P.DROP_KEY]
    assert d["count"] == 88 and d["first_ms"] == A.DATA_START_MS and d["last_ms"] == A.DATA_START_MS + 87 * H8
    assert d["funding_ms"] == [r["fundingTime"] for r in WARM88]
    line0 = raw_b.split(b"\n")[0]
    assert d["pages"] == [{"line": 0, "line_sha256": hashlib.sha256(line0).hexdigest(), "dropped": 88}]
    assert d["raw_file_sha256"] == hashlib.sha256(raw_b).hexdigest() == m["raw"]["funding.jsonl"]
    assert d["shared_bucket"] == {"n": 0, "funding_ms": []} and d["rate_not_ok"]["n"] == 0
    assert json.loads((out / "funding.json").read_text()) == []
    assert (out / "raw" / "funding.jsonl").read_bytes() == raw_b                  # 원시는 그대로
    assert P.verify_rebuild(out, (TP.START, TP.END)) == m


@pytest.mark.parametrize("ms", [W, W + H8])
def test_empty_mark_at_or_after_window_start_still_stops_and_the_stop_audit_keeps_the_drops(tmp_path, ms):
    out = captured(tmp_path)
    write_funding(out / "raw", [[row(A.DATA_START_MS), row(ms)]])
    with pytest.raises(P.SourceStop):
        P.build(out, (TP.START, TP.END))
    a = json.loads((out / "source_audit.json").read_text())["price"]
    assert [s["kind"] for s in a["stops"]] == ["funding_malformed"] and a["stops"][0]["bucket_ms"] == ms
    assert a[P.DROP_KEY]["count"] == 1 and a[P.DROP_KEY]["funding_ms"] == [A.DATA_START_MS]
    assert not (out / "manifest.json").exists()


@pytest.mark.parametrize("mark", [KeyError, None, "NaN", " "])
def test_only_the_exact_empty_string_counts_as_empty(tmp_path, mark):
    out = captured(tmp_path)
    write_funding(out / "raw", [[row(A.DATA_START_MS, mark=mark)]])
    with pytest.raises(P.SourceStop):
        P.build(out, (TP.START, TP.END))
    assert json.loads((out / "source_audit.json").read_text())["price"][P.DROP_KEY]["count"] == 0


def test_shared_bucket_and_bad_rate_rows_are_dropped_and_only_reported(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    t = A.DATA_START_MS
    b = write_funding(raw, [[row(t), row(t + 5, mark="100")], [], [row(t + H8, rate="abc"), row(W + H8, mark="100")]])
    view, d = P.funding_view(raw)
    assert d["count"] == 2 and d["funding_ms"] == [t, t + H8]
    assert d["shared_bucket"] == {"n": 1, "funding_ms": [t]} and d["rate_not_ok"] == {"n": 1, "funding_ms": [t + H8]}
    lines = b.split(b"\n")
    assert d["pages"] == [{"line": 0, "line_sha256": hashlib.sha256(lines[0]).hexdigest(), "dropped": 1},
                          {"line": 2, "line_sha256": hashlib.sha256(lines[2]).hexdigest(), "dropped": 1}]
    kept = [json.loads(x)["page"] for x in view.decode().splitlines()]
    assert kept == [[row(t + 5, mark="100")], [], [row(W + H8, mark="100")]]    # 쪽 수·순서 유지 · 빈 쪽 유지


def test_prepare_t2_is_not_modified_by_the_fix():
    r = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "305e664b15b93201ea0e5446a5df5f5e9b265fa8", "--",
                        "backtest/prepare_t2.py"])
    assert r.returncode == 0


# ── 동결 행 버전화 ────────────────────────────────────────────────────────────
def test_real_registry_parses_and_v1_is_305e664():
    fz = PV.freeze_versions((ROOT / PV.REGISTRY_REL).read_text())             # C3′ 뒤에도 통과(앞으로 호환)
    assert 1 in fz and fz[1]["H"] == "305e664b15b93201ea0e5446a5df5f5e9b265fa8"


def test_rows_without_freeze_keys_are_not_parsed():
    reg = (f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} |\n"
           "| x | 메모 t3_note=hello |\n| w | t3_freeze_H_v2 언급(등호 없음) |\n| y | t3_prepared/bars_1m.parquet=zz |")
    assert sorted(PV.freeze_versions(reg)) == [1]


def _code_change(r: Path) -> None:
    f = r / "backtest" / "prepare_t3.py"
    f.write_text(f.read_text() + "# fix\n")


def _v2(ch: dict[str, Any], *, auth: str | None = "H1", auth_in_h2: bool = True, push: bool = True) -> str:
    """C1′(코드) → C2′ = H′(승인 행) → C3′(목록 v2 + v2 행)."""
    r = ch["repo"]
    _code_change(r)
    _commit(r, "C1' code")
    val = ch["H"] if auth == "H1" else auth
    if auth is not None and auth_in_h2:
        _append_row(r, f"| 55 | 2026-09-30 | 수정 구현 · t3_freeze_auth_v2={val} |")
        h2 = _commit(r, "C2' = H'", push=False)
    else:
        h2 = _h_without_auth(r)
    man = PV.freeze_manifest(r, h2)
    (r / PV.manifest_rel(2)).write_text(json.dumps(man, sort_keys=True, indent=1) + "\n")
    msha = PV.sha_file(r / PV.manifest_rel(2))
    if auth is not None and not auth_in_h2:
        _append_row(r, f"| 55 | 2026-09-30 | 늦은 승인 · t3_freeze_auth_v2={val} |")
    _append_row(r, f"| 56 | 2026-09-30 | 동결 v2 · t3_freeze_H_v2={h2} · t3_freeze_manifest_v2={msha} · t3_fingerprint_v2={man['fingerprint']} |")
    _commit(r, "C3'", push=push)
    return h2


def _h_without_auth(r: Path) -> str:
    (r / "docs" / "note.md").write_text("H' without an authorization row\n")
    return _commit(r, "C2' = H' (no auth row)", push=False)


def test_v2_freeze_supersedes_v1(chain):
    h2 = _v2(chain)
    rows = PV.require_rows(chain["repo"], h2)
    assert rows["freeze_version"] == "2" and rows["fingerprint"] == PV.fingerprint(chain["repo"])
    with pytest.raises(PV.ProvenanceError):
        PV.require_rows(chain["repo"], chain["H"])                               # v1은 이력일 뿐
    PV.require_frozen(chain["repo"], h2, fetch_first=False)


def test_v2_without_authorization_row_refused(chain):
    h2 = _v2(chain, auth=None)
    with pytest.raises(PV.ProvenanceError, match="승인 행"):
        PV.require_rows(chain["repo"], h2)


def test_authorization_value_must_be_the_previous_h(chain):
    h2 = _v2(chain, auth=chain["C1"])
    with pytest.raises(PV.ProvenanceError, match="승인 행"):
        PV.require_rows(chain["repo"], h2)


def test_authorization_row_must_already_be_in_the_new_h_tree(chain):
    h2 = _v2(chain, auth_in_h2=False)
    with pytest.raises(PV.ProvenanceError, match="승인 행"):
        PV.require_rows(chain["repo"], h2)


def test_duplicate_v2_row_refused(chain):
    h2 = _v2(chain)
    r = chain["repo"]
    reg = (r / PV.REGISTRY_REL).read_text()
    _append_row(r, [ln for ln in reg.splitlines() if "t3_freeze_H_v2=" in ln][0].replace("| 56 |", "| 57 |"))
    _commit(r, "dup v2")
    with pytest.raises(PV.ProvenanceError, match="정확히 하나"):
        PV.require_rows(r, h2)


def test_history_manifest_tamper_refused(chain):
    h2 = _v2(chain)
    r = chain["repo"]
    m1 = r / PV.FREEZE_MANIFEST_REL
    m1.write_text(m1.read_text().replace('"H"', '"H" ', 1))
    _commit(r, "tamper v1 manifest")
    with pytest.raises(PV.ProvenanceError, match="v1"):
        PV.require_rows(r, h2)


def test_v1_row_missing_from_the_v2_h_tree_refused(chain):
    """H′를 #53 전(H1 바로 뒤)에서 갈라 만들면 v1 행·목록이 H′ 트리에 없다 → 거부."""
    r, h1 = chain["repo"], chain["H"]
    row53 = [ln for ln in (r / PV.REGISTRY_REL).read_text().splitlines() if "t3_freeze_H=" in ln][0]
    man1 = (r / PV.FREEZE_MANIFEST_REL).read_bytes()
    _git(r, "checkout", "-q", "-b", "alt", h1)
    _code_change(r)
    _append_row(r, f"| 55 | 2026-09-30 | 수정 · t3_freeze_auth_v2={h1} |")
    h2 = _commit(r, "H' off H1", push=False)
    (r / PV.FREEZE_MANIFEST_REL).write_bytes(man1)
    _append_row(r, row53)
    man = PV.freeze_manifest(r, h2)
    (r / PV.manifest_rel(2)).write_text(json.dumps(man, sort_keys=True, indent=1) + "\n")
    _append_row(r, f"| 56 | 2026-09-30 | v2 · t3_freeze_H_v2={h2} · t3_freeze_manifest_v2={PV.sha_file(r / PV.manifest_rel(2))} · "
                   f"t3_fingerprint_v2={man['fingerprint']} |")
    _commit(r, "C3' on alt", push=False)
    _git(r, "push", "-q", "-f", "origin", "alt:main")
    _git(r, "fetch", "-q", "origin")
    with pytest.raises(PV.ProvenanceError, match="v2 H 트리"):
        PV.require_rows(r, h2)


def test_v2_h_equal_to_v1_h_is_not_a_strict_step(chain):
    r, h1 = chain["repo"], chain["H"]
    man = PV.freeze_manifest(r, h1)
    (r / PV.manifest_rel(2)).write_text(json.dumps(man, sort_keys=True, indent=1) + "\n")
    _append_row(r, f"| 55 | x · t3_freeze_auth_v2={h1} |")
    _append_row(r, f"| 56 | x · t3_freeze_H_v2={h1} · t3_freeze_manifest_v2={PV.sha_file(r / PV.manifest_rel(2))} · "
                   f"t3_fingerprint_v2={man['fingerprint']} |")
    _commit(r, "v2 = v1")
    with pytest.raises(PV.ProvenanceError, match="엄격한 조상"):
        PV.require_rows(r, h1)


H40 = "a" * 40
H64 = "b" * 64


@pytest.mark.parametrize("line", [
    f"| x | t3_freeze_H_v02={H40} |", f"| x | t3_freeze_H_vx={H40} |", f"| x | t3_freeze_H_v1={H40} |",
    f"| x | t3_freeze_auth={H40} |", f"| x | t3_freeze_Hx={H40} |", f"| x | t3_fingerprints={H64} |",
])
def test_malformed_freeze_keys_refused(line):
    with pytest.raises(PV.ProvenanceError, match="형식"):
        PV.freeze_versions(line)


@pytest.mark.parametrize("reg", [
    f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} |",                                       # 부분 세트
    f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} · t3_freeze_auth_v2={H40} |",  # 섞임
    f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} |\n"
    f"| b | t3_freeze_H_v3={H40} · t3_freeze_manifest_v3={H64} · t3_fingerprint_v3={H64} |\n| c | t3_freeze_auth_v3={H40} |",  # v2 없음
    f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} |\n| c | t3_freeze_auth_v2={H40} |",  # 짝 없는 승인
    "| a | 동결 행 없음 |",
])
def test_version_structure_refusals(reg):
    with pytest.raises(PV.ProvenanceError):
        PV.freeze_versions(reg)


def test_v1_key_is_not_a_substring_match_for_v2_keys():
    reg = (f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} |\n"
           f"| b | t3_freeze_H_v2={'c' * 40} · t3_freeze_manifest_v2={H64} · t3_fingerprint_v2={H64} |\n| c | t3_freeze_auth_v2={H40} |")
    fz = PV.freeze_versions(reg)
    assert fz[1]["H"] == H40 and fz[2]["H"] == "c" * 40 and fz[2]["auth"] == H40


def test_build_verify_and_pinned_load_with_drops_and_a_retained_funding(tmp_path):
    """Codex A MINOR 1: 버린 워밍업 행 + 남는 정상 펀딩(창 안 16:00) → 빌드 · 다시 빌드 대조 · 고정 로더."""
    start = TP.END + 1 - 490 * TP.MIN                                             # 2025-12-31 15:50
    out = TP.capture(tmp_path, start=start)
    keep_ms = TP.END + 1 - 8 * 3_600_000                                         # 2025-12-31 16:00
    write_funding(out / "raw", [WARM88 + [row(keep_ms, mark="100")]])
    m = P.build(out, (start, TP.END))
    assert P.verify_rebuild(out, (start, TP.END)) == m
    pins = PV.make_pins(out)
    _, fundings, _, _ = P.load_prepared_pinned(out, pins, (start, TP.END), root=tmp_path)
    assert [f.funding_ms for f in fundings] == [keep_ms] and fundings[0].mark == "100"
    assert json.loads((out / "source_audit.json").read_text())["price"][P.DROP_KEY]["count"] == 88


def _next_version(ch: dict[str, Any], n: int, prev_h: str) -> str:
    r = ch["repo"]
    _code_change(r)
    _commit(r, f"code v{n}")
    _append_row(r, f"| a{n} | 승인 · t3_freeze_auth_v{n}={prev_h} |")
    h = _commit(r, f"H v{n}", push=False)
    man = PV.freeze_manifest(r, h)
    (r / PV.manifest_rel(n)).write_text(json.dumps(man, sort_keys=True, indent=1) + "\n")
    _append_row(r, f"| f{n} | 동결 · t3_freeze_H_v{n}={h} · t3_freeze_manifest_v{n}={PV.sha_file(r / PV.manifest_rel(n))} · "
                   f"t3_fingerprint_v{n}={man['fingerprint']} |")
    _commit(r, f"C3 v{n}")
    return h


def test_v3_chain_and_a_later_pins_row_pass(chain):
    """Codex A MINOR 2: v3까지의 사슬 · 뒤에 붙는 핀 행(t3_manifest · t3_raw_inventory · t3_prepared/...)이 관문을 깨지 않는다."""
    h2 = _v2(chain)
    h3 = _next_version(chain, 3, h2)
    r = chain["repo"]
    _append_row(r, f"| 57 | 데이터 핀 `{PV.PINS_REL}` · t3_manifest={H64} · t3_raw_inventory={H64} · t3_prepared/bars_1m.parquet={H64} |")
    _commit(r, "pins-like row")
    rows = PV.require_rows(r, h3)
    assert rows["freeze_version"] == "3"
    with pytest.raises(PV.ProvenanceError):
        PV.require_rows(r, h2)


def test_prose_freeze_mention_does_not_expose_other_malformed_tokens():
    """Codex A 재확인 MINOR: 동결을 산문으로 언급한 행의 다른 오타 토큰은 관문을 잠그지 않는다 · 동결 키 모양의 오타는 여전히 거부."""
    base = f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} |\n"
    assert sorted(PV.freeze_versions(base + "| p | t3_freeze v2 뒤 핀 · t3_prepared/bars_1m.parquet=zz · t3_note=x |")) == [1]
    with pytest.raises(PV.ProvenanceError, match="형식"):
        PV.freeze_versions(base + "| q | 인용 t3_freeze_H_v2=, |")


@pytest.mark.parametrize("dup", [
    f"| d | t3_freeze_H_v2 ={'c' * 40} |", f"| d | t3_freeze_H_v2 = {'c' * 40} |", f"| d | T3_FREEZE_H_V2={'c' * 40} |",
    f"| d | `t3_freeze_H_v2`={'c' * 40} |", f"| d | t3_freeze_H_v2 | ={'c' * 40} |", f"| d | t3_freeze_H_v2:={'c' * 40} |",
    f"| d | t3_freeze_auth_v2 = {H40} |", f"| d | T3_Fingerprint_v2={H64} |",
])
def test_near_miss_freeze_assignments_are_refused_not_skipped(dup):
    """Codex A 재확인 MAJOR: 둘째 v2·승인 행이 모양만 비틀려 조용히 건너뛰어지지 않는다."""
    reg = (f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} |\n"
           f"| b | t3_freeze_H_v2={'c' * 40} · t3_freeze_manifest_v2={H64} · t3_fingerprint_v2={H64} |\n"
           f"| c | t3_freeze_auth_v2={H40} |\n{dup}")
    with pytest.raises(PV.ProvenanceError, match="정규 토큰"):
        PV.freeze_versions(reg)


def test_prose_mentions_without_assignment_still_pass():
    reg = (f"| a | t3_freeze_H={H40} · t3_freeze_manifest={H64} · t3_fingerprint={H64} |\n"
           "| p | 키 이름 `t3_freeze_H_v2` · T3_FINGERPRINT 설명 · t3_freeze 절차 (등호 없는 산문) |")
    assert sorted(PV.freeze_versions(reg)) == [1]
