"""`backtest/prepare_t3.py` — 트라이얼 #3 데이터 준비(단계 2 (a) · 계획 r5 S1·S6·S7). 합성 아카이브 CSV + 가짜 REST + 가짜 OI zip만.

시각은 IS 끝(2025-12-31 23:50 ~ 23:59:59.999Z)에 둔다 — OOS 가드(≥ 2026-01-01 00:00Z는 값을 읽지 않는다)를 직접 시험한다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from backtest import prepare_t3 as P
from backtest import t3_provenance as PV
from exchange.client import Response
from strategies.trial03 import anchor as A

MIN = 60_000
END = A.IS_END_MS                                   # 2025-12-31 23:59:59.999Z
START = END + 1 - 10 * MIN                          # 2025-12-31 23:50:00.000Z
OOS0 = A.OOS_START_MS                               # 2026-01-01 00:00:00.000Z
HDR = ("timestamp,Open,High,Low,Close,Volume,quote_volume,trades,taker_buy_base,taker_buy_quote,funding_rate,"
       "mark_open,mark_high,mark_low,mark_close")
OI_HDR = ("create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
          "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio")


def ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M:%S")


def arow(ms: int, p: str = "100") -> str:
    return f"{ts(ms)},{p},{p},{p},{p},1,100,5,0.5,50,,{p},{p},{p},{p}"


def write_archive(d: Path, rows_2025: list[str], rows_2026: list[str]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "BTCUSDT_1m_2025.csv").write_text(HDR + "\n" + "\n".join(rows_2025) + ("\n" if rows_2025 else ""))
    (d / "BTCUSDT_1m_2026.csv").write_text(HDR + "\n" + "\n".join(rows_2026) + ("\n" if rows_2026 else ""))
    return d


class FakeRest:
    def __init__(self, fund: list[dict] | None = None):
        self.fund = fund or []
        self.calls: list = []

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        assert params is not None
        self.calls.append((path, params["startTime"], params["endTime"]))
        a, b = params["startTime"], params["endTime"]
        if path.endswith("fundingRate"):
            return Response(200, [f for f in self.fund if a <= f["fundingTime"] <= b][: params["limit"]], {})
        return Response(200, [], {})


def fund(ms: int, rate: str = "0.0001") -> dict[str, Any]:
    return {"symbol": "BTCUSDT", "fundingTime": ms, "fundingRate": rate, "markPrice": "100"}


def oi_zip(day: str, rows: list[str]) -> tuple[bytes, str]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"BTCUSDT-metrics-{day}.csv", OI_HDR + "\n" + "\n".join(rows) + "\n")
    data = buf.getvalue()
    return data, f"{hashlib.sha256(data).hexdigest()}  BTCUSDT-metrics-{day}.zip\n"


def oi_row(ms: int, v: str = "80000.5") -> str:
    return f"{ts(ms)},BTCUSDT,{v},1,1,1,1,1"


class FakeOI:
    def __init__(self, files: dict[str, tuple[bytes, str]]):
        self.files, self.asked = files, []

    def __call__(self, day: str) -> tuple[bytes, str]:
        self.asked.append(day)
        return self.files[day]


def full_archive() -> list[str]:
    return [arow(START + i * MIN) for i in range(10)]


def std_oi() -> FakeOI:
    return FakeOI({"2025-12-31": oi_zip("2025-12-31", [oi_row(START), oi_row(START + 5 * MIN), oi_row(OOS0, "BOOM")])})


def capture(tmp: Path, rows26: list[str] | None = None, oi: FakeOI | None = None, rest: FakeRest | None = None,
            start: int = START, end: int = END) -> Path:
    arch = write_archive(tmp / "arch", [], full_archive() if rows26 is None else rows26)
    out = tmp / "var" / "t3" / "IS"
    P.capture(out / "raw", rest or FakeRest(), arch, oi or std_oi(), start, end)
    return out


# ── OOS 가드 · 범위 ─────────────────────────────────────────────────────────
def test_is_range_is_warmup_to_is_end():
    assert P.is_range() == (A.DATA_START_MS, A.IS_END_MS)


@pytest.mark.parametrize("start,end", [(START, END + 1), (START, OOS0 + 5 * MIN), (A.DATA_START_MS - MIN, END)])
def test_capture_refuses_ranges_outside_is(tmp_path, start, end):
    with pytest.raises(P.OOSGuard):
        capture(tmp_path, start=start, end=end)
    assert not (tmp_path / "var" / "t3" / "IS" / "raw").exists()


def test_bounded_reader_stops_at_first_row_past_end_without_reading_it(tmp_path):
    rows = full_archive() + [arow(OOS0, "999"), "garbage-after-end,1,2", arow(OOS0 + MIN, "998")]
    arch = write_archive(tmp_path / "arch", [arow(START - 5 * MIN)], rows)
    got = P.read_archive_rows_bounded(arch, START, END)
    assert [x["ts_ms"] for x in got] == [START + i * MIN for i in range(10)]
    assert all(x["ts_ms"] is not None and x["ts_ms"] <= END for x in got)     # 끝 뒤 쓰레기 행은 보이지도 않는다


def test_bounded_reader_keeps_unparseable_rows_inside_the_range(tmp_path):
    rows = [arow(START), "not-a-time,1,2,3", arow(START + MIN)]
    arch = write_archive(tmp_path / "arch", [], rows)
    got = P.read_archive_rows_bounded(arch, START, START + MIN)
    assert [x["ts_ms"] for x in got] == [START, None, START + MIN]


def test_capture_requests_are_bounded_and_oi_days_are_in_range(tmp_path):
    rest = FakeRest(fund=[fund(OOS0)])                  # 끝 뒤 펀딩은 요청 범위 밖이라 오지 않는다
    oi = std_oi()
    out = capture(tmp_path, rest=rest, oi=oi)
    assert rest.calls and all(e <= END for _, _, e in rest.calls)
    assert oi.asked == ["2025-12-31"]
    assert "fundingTime" not in (out / "raw" / "funding.jsonl").read_text()
    assert sorted(p.name for p in (out / "raw" / "oi").iterdir()) == [
        "BTCUSDT-metrics-2025-12-31.zip", "BTCUSDT-metrics-2025-12-31.zip.CHECKSUM"]


# ── OI 분석(§5 중단 규칙 · 계획 r5) ────────────────────────────────────────
def _oi_dir(tmp: Path, files: dict[str, tuple[bytes, str]]) -> Path:
    d = tmp / "oi"
    d.mkdir(parents=True)
    for day, (data, chk) in files.items():
        (d / f"BTCUSDT-metrics-{day}.zip").write_bytes(data)
        (d / f"BTCUSDT-metrics-{day}.zip.CHECKSUM").write_text(chk)
    return d


def test_oi_rows_after_end_are_dropped_before_their_value_is_read(tmp_path):
    d = _oi_dir(tmp_path, {"2025-12-31": oi_zip("2025-12-31", [oi_row(START), oi_row(OOS0, "BOOM")])})
    series, audit, stops = P.analyze_oi(d, START, END)
    assert series == [[START, "80000.5"]] and not stops
    assert audit["rows_outside_range"] == 1 and audit["value_not_ok"] == 0      # "BOOM"은 분류되지 않았다


def test_oi_identical_duplicates_merge_conflicting_stop(tmp_path):
    same = _oi_dir(tmp_path / "a", {"2025-12-31": oi_zip("2025-12-31", [oi_row(START), oi_row(START)])})
    s, audit, stops = P.analyze_oi(same, START, END)
    assert s == [[START, "80000.5"]] and not stops and audit["exact_duplicates"] == 1
    diff = _oi_dir(tmp_path / "b", {"2025-12-31": oi_zip("2025-12-31", [oi_row(START), oi_row(START, "80000.6")])})
    _, _, stops = P.analyze_oi(diff, START, END)
    assert [x["kind"] for x in stops] == ["oi_conflicting_duplicate"]


def test_oi_duplicate_identity_is_create_time_across_files(tmp_path):
    d = _oi_dir(tmp_path, {"2025-12-30": oi_zip("2025-12-30", [oi_row(START, "1")]),
                           "2025-12-31": oi_zip("2025-12-31", [oi_row(START, "2")])})
    _, _, stops = P.analyze_oi(d, START - 86_400_000, END)
    assert [x["kind"] for x in stops] == ["oi_conflicting_duplicate"]


@pytest.mark.parametrize("row,kind", [("2025-12-31 23:51:00,BTCUSDT,1,1,1,1,1,1", "oi_off_grid"),
                                      ("31/12/2025 23:50,BTCUSDT,1,1,1,1,1,1", "oi_unparseable_time")])
def test_oi_time_defects_stop(tmp_path, row, kind):
    d = _oi_dir(tmp_path, {"2025-12-31": oi_zip("2025-12-31", [row])})
    _, _, stops = P.analyze_oi(d, START, END)
    assert [x["kind"] for x in stops] == [kind]


DAY0 = END + 1 - 86_400_000                         # 2025-12-31 00:00Z — 하루 288슬롯(0.5% 상한 = 1.44슬롯)


@pytest.mark.parametrize("v", ["", "NaN", "abc"])
def test_oi_unusable_value_is_absent_not_a_stop(tmp_path, v):
    d = _oi_dir(tmp_path, {"2025-12-31": oi_zip("2025-12-31", [oi_row(START, v), oi_row(START + 5 * MIN)])})
    s, audit, stops = P.analyze_oi(d, DAY0, END)
    assert s == [[START + 5 * MIN, "80000.5"]] and not stops and audit["value_not_ok"] == 1
    assert audit["unusable_slots"] == [START] and audit["unusable_per_day"] == {"2025-12-31": 1}
    assert audit["unusable_total"] == 1 and audit["unusable_is_slots"] == 1 and audit["is_grid_slots"] == 288


def test_oi_unusable_slot_with_an_ok_duplicate_is_usable(tmp_path):
    d = _oi_dir(tmp_path, {"2025-12-31": oi_zip("2025-12-31", [oi_row(START, ""), oi_row(START)])})
    s, audit, stops = P.analyze_oi(d, DAY0, END)
    assert s == [[START, "80000.5"]] and not stops and audit["unusable_slots"] == []


def test_oi_unusable_over_half_percent_of_is_grid_stops(tmp_path):
    d = _oi_dir(tmp_path, {"2025-12-31": oi_zip("2025-12-31", [oi_row(START, ""), oi_row(START + 5 * MIN, "")])})
    _, audit, stops = P.analyze_oi(d, DAY0, END)                # 2/288 = 0.69% > 0.5%
    assert [x["kind"] for x in stops] == ["oi_unusable_over_cap"] and audit["unusable_is_slots"] == 2
    assert P.OI_UNUSABLE_CAP == 0.005


def test_oi_unusable_in_warmup_is_logged_not_capped(tmp_path):
    w = A.WINDOW_START_MS - 86_400_000                               # 2023-12-31(워밍업)
    d = _oi_dir(tmp_path, {"2023-12-31": oi_zip("2023-12-31", [oi_row(w + i * 5 * MIN, "") for i in range(5)])})
    _, audit, stops = P.analyze_oi(d, w, A.WINDOW_START_MS - 1)
    assert not stops and audit["unusable_total"] == 5 and audit["unusable_is_slots"] == 0 and audit["is_grid_slots"] == 0


def test_oi_checksum_mismatch_and_missing_columns_stop(tmp_path):
    data, _ = oi_zip("2025-12-31", [oi_row(START)])
    d = _oi_dir(tmp_path / "a", {"2025-12-31": (data, "0" * 64 + "  x.zip\n")})
    assert [x["kind"] for x in P.analyze_oi(d, START, END)[2]] == ["oi_checksum_mismatch"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", "create_time,symbol\n2025-12-31 23:50:00,BTCUSDT\n")
    raw = buf.getvalue()
    d2 = _oi_dir(tmp_path / "b", {"2025-12-31": (raw, hashlib.sha256(raw).hexdigest() + "  x.zip\n")})
    assert [x["kind"] for x in P.analyze_oi(d2, START, END)[2]] == ["oi_missing_columns"]


def test_oi_missing_day_file_stops(tmp_path):
    d = _oi_dir(tmp_path, {"2025-12-31": oi_zip("2025-12-31", [oi_row(START)])})
    _, _, stops = P.analyze_oi(d, START - 86_400_000, END)
    assert [x["kind"] for x in stops] == ["oi_day_file_missing"]


# ── 빌드 · 매니페스트 · 다시 빌드 · 적재 ─────────────────────────────────────
def test_build_verify_and_load_roundtrip(tmp_path):
    out = capture(tmp_path)
    m = P.build(out, (START, END))
    assert set(m) >= {"raw", "bars_1m.parquet", "funding.json", "source_audit.json", "kline_close_daily.json",
                      "oi_5m.json", "code_commit", "window"}
    assert "oi/BTCUSDT-metrics-2025-12-31.zip" in m["raw"]
    pins = PV.make_pins(out)
    bars, fundings, oi, unusable = P.load_prepared_pinned(out, pins, (START, END), root=tmp_path)
    kd = P.load_kline_daily_pinned(out, pins, (START, END), root=tmp_path)
    assert [r["day"] for r in kd] == [START // A.DAY_MS]
    assert unusable == []
    assert len(bars) == 10 and fundings == []
    assert oi == [[START, "80000.5"], [START + 5 * MIN, "80000.5"]]
    assert json.loads((out / "oi_unusable.json").read_text()) == []
    assert P.verify_rebuild(out, (START, END)) == m


def test_build_stops_on_oi_defect_and_writes_audit_only(tmp_path):
    oi = FakeOI({"2025-12-31": oi_zip("2025-12-31", [oi_row(START), oi_row(START, "1")])})
    out = capture(tmp_path, oi=oi)
    with pytest.raises(P.SourceStop):
        P.build(out, (START, END))
    assert (out / "source_audit.json").exists() and not (out / "manifest.json").exists()


def test_loader_refuses_other_trials_directories_and_wrong_pins(tmp_path):
    out = capture(tmp_path)
    P.build(out, (START, END))
    pins = PV.make_pins(out)
    for bad in ("var/t3_s0/IS", "var/backtest/t2/IS", "elsewhere/IS"):
        with pytest.raises(P.OOSGuard):
            P.load_prepared_pinned(tmp_path / bad, pins, (START, END), root=tmp_path)
    with pytest.raises((ValueError, PV.ProvenanceError)):
        P.load_prepared_pinned(out, pins | {"prepared": pins["prepared"] | {"oi_5m.json": "0" * 64}}, (START, END),
                               root=tmp_path)


def test_in_range_assertion():
    P.assert_in_range([START, END], START, END)
    with pytest.raises(P.OOSGuard):
        P.assert_in_range([START, OOS0], START, END)


# ── OOS 진입점 · CLI ─────────────────────────────────────────────────────────
def test_oos_range_requires_a_user_dated_registry_row(tmp_path):
    reg = tmp_path / "trial_registry.md"
    reg.write_text("| 50 | 2026-09-29 | 전략 트라이얼 #3 (사전등록 · 앵커됨) | … |\n")
    with pytest.raises(P.OOSGuard):
        P.oos_range(reg, 50)
    with pytest.raises(P.OOSGuard):
        P.oos_range(reg, 99)
    reg.write_text(reg.read_text() + "| 60 | 2026-10-20 | **트라이얼 #3 OOS 개봉** | … | ✅ 사용자 결정 2026-10-20 |\n")
    a, b = P.oos_range(reg, 60)
    assert b == A.OOS_END_MS and a < A.OOS_START_MS


def test_cli_refuses_capture_and_gate_check_without_a_frozen_commit(tmp_path):
    for extra in ([], ["--evaluator-commit", "0" * 40], ["--gate-check", "--evaluator-commit", "0" * 40]):
        rc = P.main(["--out", str(tmp_path / "var" / "t3" / "IS"), *extra])
        assert rc == 6 and not (tmp_path / "var" / "t3" / "IS" / "raw").exists()


def test_loader_refuses_tampered_manifest_and_raw_inventory(tmp_path):
    out = capture(tmp_path)
    P.build(out, (START, END))
    pins = PV.make_pins(out)
    for bad in (pins | {"manifest_sha256": "0" * 64}, pins | {"raw_inventory_sha256": "0" * 64}, pins | {"oi_unusable_total": 7}):
        with pytest.raises((ValueError, PV.ProvenanceError)):
            P.load_prepared_pinned(out, bad, (START, END), root=tmp_path)
    raw = out / "raw" / "funding.jsonl"
    raw.write_text(raw.read_text() + " ")
    with pytest.raises((ValueError, PV.ProvenanceError)):
        P.load_prepared_pinned(out, pins, (START, END), root=tmp_path)
