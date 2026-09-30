"""`backtest/prepare_t4.py` — 트라이얼 #4 데이터 준비(단계 (a)). 합성 아카이브 + 가짜 REST + 가짜 프리미엄 zip만(실데이터 없음).

시각은 IS 끝 하루(2025-12-31 00:00 ~ 23:59:59.999Z)에 둔다 — 인쇄 경계(마지막 IS 인쇄 16:00 · 2026-01-01 00:00 없음)를 직접 시험한다.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from backtest import prepare_t4 as P
from strategies.trial04 import anchor as A
from tests import test_prepare_t3 as TP

ROOT = Path(__file__).resolve().parent.parent
MIN = 60_000
H8 = A.H8_MS
END = A.IS_END_MS
DAY0 = END + 1 - A.DAY_MS                                  # 2025-12-31 00:00Z
HDR = ",".join(P.PREMIUM_HEADER)


def prow(t: int, close: str = "0.0001") -> str:
    return f"{t},0,0,0,{close},0,{t + MIN - 1},0,12,0,0,0"


def pzip(lines: list[str], header: bool = True, members: int = 1, hdr: str = HDR) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k in range(members):
            z.writestr(f"BTCUSDT-1m-x{k}.csv", ((hdr + "\n") if header else "") + "\n".join(lines) + "\n")
    return buf.getvalue()


def chk(data: bytes) -> str:
    return f"{hashlib.sha256(data).hexdigest()}  f.zip\n"


def day_rows(close: dict[int, str] | None = None, drop: set[int] | None = None) -> list[str]:
    close, drop = close or {}, drop or set()
    return [prow(DAY0 + i * MIN, close.get(i, "0.0001")) for i in range(1440) if i not in drop]


def pdir_with(tmp: Path, files: dict[str, bytes], checksums: dict[str, str] | None = None) -> Path:
    d = tmp / "premium"
    d.mkdir(parents=True, exist_ok=True)
    for mo, data in files.items():
        (d / f"BTCUSDT-1m-{mo}.zip").write_bytes(data)
        (d / f"BTCUSDT-1m-{mo}.zip.CHECKSUM").write_text((checksums or {}).get(mo, chk(data)))
    return d


def prints_of(tmp: Path, rows: list[str], **kw) -> list[dict]:
    d = pdir_with(tmp, {"2025-12": pzip(rows, **kw)})
    minutes, audit, stops = P.analyze_premium(d, DAY0, END)
    assert not stops, stops
    return P.build_prints(minutes, DAY0, END)


# ── 인쇄 규칙 ────────────────────────────────────────────────────────────────
def test_print_window_is_t_minus_8h_to_t_minus_1m_and_no_2026_print(tmp_path):
    rows = day_rows(close={0: "0.0481", 480: "9.9"})                 # 00:00(T=08:00 창의 첫 분) · 08:00(T=08:00 창 밖)
    pr = prints_of(tmp_path, rows)
    assert [p["T"] for p in pr] == [DAY0 + H8, DAY0 + 2 * H8]         # 08:00 · 16:00 — 2026-01-01 00:00 없음
    assert max(p["T"] for p in pr) <= END
    p08 = pr[0]
    assert p08["n_minutes"] == 480 and p08["valid"] and p08["complete"]
    assert Decimal(p08["p"]) == (Decimal("0.0481") + Decimal("0.0001") * 479) / 480
    assert Decimal(pr[1]["p"]) != Decimal("0.0001")                  # 08:00 분(9.9)은 T=16:00 창의 첫 분


@pytest.mark.parametrize("missing,valid", [(5, True), (6, False)])
def test_475_of_480_rule(tmp_path, missing, valid):
    pr = prints_of(tmp_path, day_rows(drop=set(range(10, 10 + missing))))
    assert pr[0]["n_minutes"] == 480 - missing and pr[0]["valid"] is valid


@pytest.mark.parametrize("drop,valid,complete", [(set(), True, True), ({479}, True, False), ({0}, True, False),
                                                ({10, 11, 12, 13, 14}, True, False), (set(range(6)), False, False)])
def test_distribution_membership_475_but_trigger_needs_all_480(tmp_path, drop, valid, complete):
    """사용자 결정 2026-09-30: 분포 소속 = 유효(≥ 475) · 방아쇠 = 480분 전부(아니면 print_incomplete — 결정은 (d))."""
    pr = prints_of(tmp_path, day_rows(drop=drop))[0]
    assert (pr["valid"], pr["complete"]) == (valid, complete)


def test_non_finite_close_is_an_absent_minute_not_a_stop(tmp_path):
    d = pdir_with(tmp_path, {"2025-12": pzip(day_rows(close={3: "NaN", 4: "abc", 5: "Infinity"}))})
    minutes, audit, stops = P.analyze_premium(d, DAY0, END)
    assert not stops and audit["non_finite_close_by_month"] == {"2025-12": 3}
    assert P.build_prints(minutes, DAY0, END)[0]["n_minutes"] == 477


def test_decimal_mean_is_exact_and_context_local(tmp_path):
    import decimal
    closes = {i: ("0.00012345" if i % 2 else "0.00067891") for i in range(480)}     # 합 0.1925664(유효숫자 7) > prec 5
    ref = prints_of(tmp_path / "ref", day_rows(close=closes))[0]["p"]
    decimal.getcontext().prec = 5                                    # 주변 문맥이 합·나눗셈을 바꾸지 않는다
    try:
        got = prints_of(tmp_path / "low", day_rows(close=closes))[0]["p"]
    finally:
        decimal.getcontext().prec = 28
    assert got == ref
    assert Decimal(ref) == (Decimal("0.00012345") * 240 + Decimal("0.00067891") * 240) / 480


def test_header_optional_but_exact(tmp_path):
    assert prints_of(tmp_path / "a", day_rows(), header=False)[0]["valid"]
    bad = pzip(day_rows(), hdr=HDR.replace("open_time", "openTime"))
    minutes, audit, stops = P.analyze_premium(pdir_with(tmp_path / "b", {"2025-12": bad}), DAY0, END)
    assert [s["kind"] for s in stops] == ["premium_bad_header"]


# ── 중단 조건 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dup", ["identical", "different", "one_nan"])
def test_duplicate_minute_same_file_stops_before_value_check(tmp_path, dup):
    rows = day_rows()
    second = {"identical": rows[7], "different": prow(DAY0 + 7 * MIN, "0.5"), "one_nan": prow(DAY0 + 7 * MIN, "NaN")}[dup]
    d = pdir_with(tmp_path, {"2025-12": pzip(rows + [second])})
    _, _, stops = P.analyze_premium(d, DAY0, END)
    assert [s["kind"] for s in stops] == ["premium_duplicate_minute"] and stops[0]["open_time"] == DAY0 + 7 * MIN


def test_duplicate_minute_across_files_stops(tmp_path):
    start = DAY0 - 31 * A.DAY_MS                                     # 11월과 12월에 걸친 범위
    nov = pzip([prow(DAY0 + 3 * MIN)])                               # 12월의 분이 11월 파일에도 있다
    d = pdir_with(tmp_path, {"2025-11": nov, "2025-12": pzip(day_rows())})
    _, _, stops = P.analyze_premium(d, start, END)
    assert [s["kind"] for s in stops] == ["premium_duplicate_minute"]


def test_checksum_missing_month_members_and_time_defects_stop(tmp_path):
    good = pzip(day_rows())
    assert P.analyze_premium(pdir_with(tmp_path / "c", {"2025-12": good}, {"2025-12": "0" * 64}), DAY0, END)[2][0]["kind"] \
        == "premium_checksum_mismatch"
    assert P.analyze_premium(pdir_with(tmp_path / "m", {}), DAY0, END)[2][0]["kind"] == "premium_month_missing"
    assert P.analyze_premium(pdir_with(tmp_path / "z", {"2025-12": pzip(day_rows(), members=2)}), DAY0, END)[2][0]["kind"] \
        == "premium_zip_members"
    off = pzip(day_rows() + [f"{DAY0 + 30_000},0,0,0,1,0,{DAY0 + 89_999},0,12,0,0,0"])
    assert P.analyze_premium(pdir_with(tmp_path / "o", {"2025-12": off}), DAY0, END)[2][0]["kind"] == "premium_time_defect"
    assert P.analyze_premium(pdir_with(tmp_path / "u", {"2025-12": b"not a zip"}), DAY0, END)[2][0]["kind"] \
        == "premium_zip_unreadable"
    badc = pzip([f"{DAY0},0,0,0,1,0,{DAY0 + 1},0,12,0,0,0"])
    assert P.analyze_premium(pdir_with(tmp_path / "k", {"2025-12": badc}), DAY0, END)[2][0]["kind"] == "premium_time_defect"


def test_out_of_range_rows_are_dropped_before_their_values_are_read(tmp_path):
    before = [f"{DAY0 - MIN},x,x,x,garbage,x,notatime,x,x,x,x,x"]    # 범위 앞 · 값·close_time 모두 이상
    d = pdir_with(tmp_path, {"2025-12": pzip(before + day_rows())})
    minutes, audit, stops = P.analyze_premium(d, DAY0, END)
    assert not stops and audit["rows_in_range"] == 1440 and DAY0 - MIN not in minutes


# ── 범위·가드 ────────────────────────────────────────────────────────────────
def test_is_months_end_at_2025_12_and_guards():
    ms = P.months(*P.is_range())
    assert ms[0] == "2023-10" and ms[-1] == "2025-12" and len(ms) == 27 and not [m for m in ms if m.startswith("2026")]
    for s, e in ((A.DATA_START_MS - MIN, END), (DAY0, END + 1), (A.OOS_START_MS, A.OOS_START_MS + MIN)):
        with pytest.raises(P.OOSGuard):
            P.check_is_bounds(s, e)
    for bad in ("var/t4_calib/x", "var/t3/IS", "elsewhere"):
        with pytest.raises(P.OOSGuard):
            P.check_out_dir(ROOT / bad)
    P.check_out_dir(ROOT / "var" / "t4" / "IS" / "prepared")


def test_oos_entry_point_requires_a_user_dated_row(tmp_path):
    reg = tmp_path / "r.md"
    reg.write_text("| 70 | 2026-09-30 | 전략 트라이얼 #4 (사전등록 · 앵커됨) | … |\n")
    with pytest.raises(P.OOSGuard):
        P.oos_range(reg, 70)


def test_warmup_empty_mark_funding_drop_is_trial04_bound(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    w = A.WINDOW_START_MS
    rows = [{"symbol": "BTCUSDT", "fundingTime": w - H8, "fundingRate": "0.0001", "markPrice": ""},
            {"symbol": "BTCUSDT", "fundingTime": w + H8, "fundingRate": "0.0001", "markPrice": ""}]
    (raw / "funding.jsonl").write_text(json.dumps({"page": rows}) + "\n")
    view, audit = P.funding_view(raw)
    kept = json.loads(view.decode().splitlines()[0])["page"]
    assert audit["count"] == 1 and audit["funding_ms"] == [w - H8] and [r["fundingTime"] for r in kept] == [w + H8]
    assert "trial #4" in audit["rule"]


# ── 캡처 → 빌드 → verify(합성 끝에서 끝) ──────────────────────────────────────
def test_capture_build_verify_roundtrip(tmp_path):
    arch = TP.write_archive(tmp_path / "arch", [TP.arow(DAY0 + i * MIN) for i in range(0, 1440, 60)], [])
    asked: list[str] = []

    def fetch(mo: str) -> tuple[bytes, str]:
        asked.append(mo)
        data = pzip(day_rows())
        return data, chk(data)
    rest = TP.FakeRest()
    out = tmp_path / "var" / "t4" / "IS" / "prepared"
    P.capture(out / "raw", rest, arch, fetch, DAY0, END, root=tmp_path)
    assert asked == ["2025-12"] and all(e <= END for _, _, e in rest.calls)
    m = P.build(out, (DAY0, END), root=tmp_path)
    assert set(P.PREPARED) <= set(m) and "premium/BTCUSDT-1m-2025-12.zip" in m["raw"]
    prints = json.loads((out / "premium_prints.json").read_text())
    assert [p["T"] for p in prints] == [DAY0 + H8, DAY0 + 2 * H8] and all(p["valid"] for p in prints)
    assert P.verify_rebuild(out, (DAY0, END), root=tmp_path) == m
    (out / "raw" / "premium" / "BTCUSDT-1m-2025-12.zip").write_bytes(b"x")
    with pytest.raises(ValueError):
        P.verify_manifest(out)


def test_no_other_trial_import_in_any_trial04_file():
    """strategies/trial04/*.py · backtest/*_t4.py 전부 — 다른 트라이얼 모듈 import 금지(허용: strategies.trial03.exit_schedule — 단계 (c))."""
    allowed = {"strategies.trial03.exit_schedule"}
    files = sorted((ROOT / "strategies" / "trial04").glob("*.py")) + sorted((ROOT / "backtest").glob("*_t4.py"))
    assert (ROOT / "backtest" / "prepare_t4.py") in files
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        froms = [(n.module or "", a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names]
        bad = [m for m in mods if m not in allowed and any(k in m for k in ("trial01", "trial02", "trial03", "_t3", "_t2"))]
        bad += [f"{m}.{a}" for m, a in froms if a in {"prepare_t3", "prepare_t2"} and m == "backtest" and a != "prepare_t2"]
        assert not bad, (f.name, bad)


def test_capture_build_verify_refuse_paths_outside_var_t4(tmp_path):
    arch = TP.write_archive(tmp_path / "arch", [], [])
    for bad in ("var/t4_calib/prepared", "var/t3/IS/prepared", "elsewhere/prepared"):
        with pytest.raises(P.OOSGuard):
            P.capture(tmp_path / bad / "raw", TP.FakeRest(), arch, lambda mo: (b"", ""), DAY0, END, root=tmp_path)
        assert not (tmp_path / bad).exists()
        with pytest.raises(P.OOSGuard):
            P.build(tmp_path / bad, (DAY0, END), root=tmp_path)
        with pytest.raises(P.OOSGuard):
            P.verify_rebuild(tmp_path / bad, (DAY0, END), root=tmp_path)


def test_funding_response_past_the_range_stops_before_persisting(tmp_path):
    arch = TP.write_archive(tmp_path / "arch", [], [])
    over = TP.FakeRest([{"symbol": "BTCUSDT", "fundingTime": END + 1, "fundingRate": "BOOM", "markPrice": "x"}])
    over.get = (lambda orig: (lambda path, params=None, *, signed=False:                 # 창 밖 행을 되돌려 주는 끝점
                TP.Response(200, [{"symbol": "BTCUSDT", "fundingTime": END + 1, "fundingRate": "BOOM", "markPrice": "x"}], {})
                if path.endswith("fundingRate") else orig(path, params, signed=signed)))(over.get)
    raw = tmp_path / "var" / "t4" / "IS" / "prepared" / "raw"
    with pytest.raises(P.OOSGuard):
        P.capture(raw, over, arch, lambda mo: (b"", ""), DAY0, END, root=tmp_path)
    assert not (raw / "funding.jsonl").exists()


def test_single_non_csv_member_stops(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BTCUSDT-1m-2025-12.txt", "\n".join(day_rows()) + "\n")
    assert P.analyze_premium(pdir_with(tmp_path / "t", {"2025-12": buf.getvalue()}), DAY0, END)[2][0]["kind"] \
        == "premium_zip_members"


def test_oos_bootstrap_streams_mapping():
    assert A.BOOTSTRAP_STREAMS["OOS"] == {"gross_S": 4, "net_S": 5, "gross_L": 6, "net_L": 7}


def test_raw_symlink_escaping_var_t4_is_refused(tmp_path):
    outside = tmp_path / "elsewhere" / "raw"
    outside.mkdir(parents=True)
    prep = tmp_path / "var" / "t4" / "IS" / "prepared"
    prep.mkdir(parents=True)
    (prep / "raw").symlink_to(outside)
    arch = TP.write_archive(tmp_path / "arch", [], [])
    with pytest.raises(P.OOSGuard):
        P.capture(prep / "raw", TP.FakeRest(), arch, lambda mo: (b"", ""), DAY0, END, root=tmp_path)
    assert not any(outside.iterdir())
    with pytest.raises(P.OOSGuard):
        P.build(prep, (DAY0, END), root=tmp_path)
    with pytest.raises(P.OOSGuard):
        P.verify_rebuild(prep, (DAY0, END), root=tmp_path)


def test_public_build_has_no_guard_bypass():
    import inspect
    assert "None" not in str(inspect.signature(P.build).parameters["root"].annotation)
