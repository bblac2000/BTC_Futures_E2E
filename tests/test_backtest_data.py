"""단계 2a 데이터 계층 — 합성 아카이브·가짜 REST만(실데이터 통계 계산 없음)."""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from backtest import data as BD
from exchange.client_types import Response

M = BD.MINUTE_MS
T0 = int(dt.datetime(2024, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
HEADER = ("timestamp,Open,High,Low,Close,Volume,quote_volume,trades,taker_buy_base,taker_buy_quote,funding_rate,"
          "mark_open,mark_high,mark_low,mark_close")


def _row(t: int, px: float, *, mark: bool = True) -> str:
    ts = dt.datetime.fromtimestamp(t / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M:%S")
    mk = f"{px},{px + 1},{px - 1},{px}" if mark else ",,,"
    return f"{ts},{px},{px + 2},{px - 2},{px + 0.5},1.5,{px * 1.5},10,0.7,{px * 0.7},0.0001,{mk}"


def _write(root: Path, name: str, rows: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(HEADER + "\n" + "\n".join(rows) + "\n")


class FakeRest:
    """REST klines·markPriceKlines·fundingRate — 1분 격자에서 결정론적 값."""

    def __init__(self, *, mark_gap: set[int] | None = None, fundings: list[int] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.mark_gap = mark_gap or set()
        self.fundings = fundings or []

    def get(self, path, params=None, *, signed=False):
        assert not signed
        p = dict(params or {})
        self.calls.append((path, p))
        if path in (BD.KLINES_PATH, BD.MARK_KLINES_PATH):
            t, end, lim = p["startTime"], p.get("endTime", p["startTime"]), p["limit"]
            rows = []
            while t <= end and len(rows) < lim:
                px = 100 + (t // M) % 7
                if path == BD.KLINES_PATH:
                    rows.append([t, f"{px}", f"{px + 2}", f"{px - 2}", f"{px + 0.5}", "1.5", t + M - 1, f"{px * 1.5}", 10,
                                 "0.7", f"{px * 0.7}", "0"])
                elif t not in self.mark_gap:
                    rows.append([t, f"{px}", f"{px + 1}", f"{px - 1}", f"{px}", "0", t + M - 1, "0", 0, "0", "0", "0"])
                t += M
            return Response(200, rows)
        if path == BD.FUNDING_PATH:
            t, end = p["startTime"], p["endTime"]
            rows = [{"fundingTime": f, "fundingRate": "0.00010000", "markPrice": "100.0"} for f in self.fundings if t <= f <= end]
            return Response(200, rows[: p["limit"]])
        raise AssertionError(path)


def test_archive_files_are_split_by_kst_year_and_filtered_by_utc_time(tmp_path):
    # KST 2024 파일은 UTC 2023-12-31 15:00부터 시작한다 — 연도 경계를 가정하면 이 행을 놓친다
    kst_start = T0 - 9 * 60 * M
    _write(tmp_path, "BTCUSDT_1m_2024.csv", [_row(kst_start + i * M, 100.0) for i in range(9 * 60 + 5)])
    bars = BD.load_archive(tmp_path, T0, T0 + 4 * M)
    assert [b.open_ms for b in bars] == [T0 + i * M for i in range(5)] and {b.source for b in bars} == {"archive"}
    assert bars[0].open == "100.0" and bars[0].mark_close == "100.0"


def test_bars_without_mark_are_dropped_and_show_up_as_missing(tmp_path):
    _write(tmp_path, "BTCUSDT_1m_2024.csv", [_row(T0 + i * M, 100.0, mark=(i != 2)) for i in range(4)])
    bars = BD.load_archive(tmp_path, T0, T0 + 3 * M)
    integ = BD.integrity(bars, T0, T0 + 4 * M - 1)
    assert integ.missing_ranges == [(T0 + 2 * M, T0 + 2 * M)] and not integ.ok


def test_rest_fills_only_the_minutes_the_archive_lacks_and_tags_the_source(tmp_path):
    _write(tmp_path, "BTCUSDT_1m_2024.csv", [_row(T0 + i * M, 100.0) for i in range(3)])
    rest = FakeRest()
    bars = BD.load_window(tmp_path, rest, T0, T0 + 6 * M - 1)
    assert [b.source for b in bars] == ["archive"] * 3 + ["rest"] * 3
    assert all(p["startTime"] >= T0 + 3 * M for _path, p in rest.calls), "아카이브에 있는 분은 REST로 다시 받지 않는다"
    integ = BD.integrity(bars, T0, T0 + 6 * M - 1)
    assert integ.ok and integ.by_source == {"archive": 3, "rest": 3} and integ.expected_minutes == 6


def test_rest_minutes_without_mark_are_not_used(tmp_path):
    rest = FakeRest(mark_gap={T0 + M})
    bars = BD.fetch_rest_bars(rest, T0, T0 + 3 * M - 1)
    assert [b.open_ms for b in bars] == [T0, T0 + 2 * M], "SL/TP는 mark로 판정한다 — mark 없는 분은 쓰지 않는다"


def test_rest_paging_crosses_the_page_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(BD, "REST_KLINES_LIMIT", 4)
    bars = BD.fetch_rest_bars(FakeRest(), T0, T0 + 10 * M - 1)
    assert [b.open_ms for b in bars] == [T0 + i * M for i in range(10)]


def test_integrity_detects_duplicates_non_monotone_and_gaps():
    b = BD.fetch_rest_bars(FakeRest(), T0, T0 + 4 * M - 1)
    messy = [b[0], b[2], b[1], b[1]]
    integ = BD.integrity(messy, T0, T0 + 4 * M - 1)
    assert integ.duplicates == 1 and not integ.monotone and integ.missing_ranges == [(T0 + 3 * M, T0 + 3 * M)]
    assert integ.as_dict()["ok"] is False


def test_funding_comes_from_the_settled_endpoint_and_is_deduplicated():
    fs = [T0, T0 + 480 * M, T0 + 960 * M]
    got = BD.fetch_funding(FakeRest(fundings=fs), T0, T0 + 1000 * M)
    assert [f.funding_ms for f in got] == fs and got[0].rate == "0.00010000" and got[0].mark == "100.0"


def test_utc_alignment_check_fails_loudly_on_a_shifted_label(tmp_path):
    rest = FakeRest()
    good = BD.fetch_rest_bars(rest, T0, T0 + 2 * M - 1)
    assert [r["match"] for r in BD.assert_utc_alignment(good, rest, [T0, T0 + M])] == [True, True]
    shifted = [BD.Bar1m(b.open_ms + 9 * 60 * M, *[getattr(b, f) for f in (
        "open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote",
        "mark_open", "mark_high", "mark_low", "mark_close", "source")]) for b in good]
    with pytest.raises(AssertionError):
        BD.assert_utc_alignment(shifted, rest, [shifted[0].open_ms])


def test_reconcile_against_the_bot_db_reports_overlap_and_mismatches(tmp_path):
    bars = BD.fetch_rest_bars(FakeRest(), T0, T0 + 3 * M - 1)
    db = tmp_path / "bot.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE bars_1m(mode TEXT, open_time_ms INTEGER, open TEXT, high TEXT, low TEXT, close TEXT, volume TEXT)")
    for b in bars[:2]:
        con.execute("INSERT INTO bars_1m VALUES('paper',?,?,?,?,?,?)", (b.open_ms, b.open, b.high, b.low, b.close, b.volume))
    con.execute("INSERT INTO bars_1m VALUES('paper',?,?,?,?,?,?)", (T0 + 99 * M, "1", "1", "1", "1", "1"))
    con.execute("UPDATE bars_1m SET close='999' WHERE open_time_ms=?", (bars[1].open_ms,))
    con.commit()
    con.close()
    r = BD.reconcile_with_bot_db(bars, db)
    assert r["db_rows"] == 3 and r["overlap"] == 2 and r["mismatch"] == 1 and r["first_mismatch_ms"] == [bars[1].open_ms]


def test_prepare_refuses_the_oos_window_without_an_explicit_opening(tmp_path, capsys):
    from backtest import prepare as PR
    assert PR.main(["--window", "OOS", "--var-dir", str(tmp_path)]) == 4
    assert "G3 개봉" in capsys.readouterr().err and not any(tmp_path.iterdir())


def test_prepare_writes_a_parquet_cache_that_round_trips_and_an_integrity_report(tmp_path, monkeypatch):
    from backtest import prepare as PR
    monkeypatch.setitem(PR.WINDOWS, "IS", (T0, T0 + 6 * M - 1))
    # 아카이브 값 = 가짜 REST 값(같은 분) — UTC 정렬 검사가 통과해야 한다
    _write(tmp_path / "arch", "BTCUSDT_1m_2024.csv", [_row(T0 + i * M, float(100 + ((T0 + i * M) // M) % 7)) for i in range(3)])
    rest = FakeRest(fundings=[T0 + 2 * M])
    rep = PR.prepare("IS", tmp_path / "out", rest, archive=tmp_path / "arch")
    assert rep["integrity"]["ok"] and rep["integrity"]["by_source"] == {"archive": 3, "rest": 3} and rep["funding_events"] == 1
    back = PR.read_bars(tmp_path / "out" / "IS" / "bars_1m.parquet")
    assert back == BD.load_window(tmp_path / "arch", FakeRest(), T0, T0 + 6 * M - 1)
