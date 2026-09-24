"""`backtest/prepare_t2.py` — 원시 캡처 → 감사 → 빌드(설계 C14~C20). 합성 아카이브 CSV + 가짜 REST만(실데이터 없음)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from backtest import prepare_t2 as P
from exchange.client import Response

MIN = 60_000
DAY = 86_400_000
T0 = int(dt.datetime(2024, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
HDR = ("timestamp,Open,High,Low,Close,Volume,quote_volume,trades,taker_buy_base,taker_buy_quote,funding_rate,"
       "mark_open,mark_high,mark_low,mark_close")


def ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d %H:%M:%S")


def arow(ms: int, p: str = "100", mark: str | None = None, kline: bool = True) -> str:
    m = p if mark is None else mark
    k = f"{p},{p},{p},{p},1,100,5,0.5,50" if kline else ",,,,,,,,"
    return f"{ts(ms)},{k},,{m},{m},{m},{m}"


def write_archive(d: Path, rows: list[str]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "BTCUSDT_1m_2024.csv").write_text(HDR + "\n" + "\n".join(rows) + "\n")
    return d


def kline(ms: int, p: str = "200") -> list[Any]:
    return [ms, p, p, p, p, "1", ms + MIN - 1, "200", 7, "0.5", "100", "0"]


def mark(ms: int, p: str = "200") -> list[Any]:
    return [ms, p, p, p, p, "0", ms + MIN - 1, "0", 0, "0", "0", "0"]


class FakeRest:
    def __init__(self, kl: dict[int, list] | None = None, mk: dict[int, list] | None = None, fund: list[dict] | None = None):
        self.kl, self.mk, self.fund = kl or {}, mk or {}, fund or []
        self.calls: list = []

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        assert params is not None
        self.calls.append((path, params["startTime"], params["endTime"]))
        a, b = params["startTime"], params["endTime"]
        if path.endswith("fundingRate"):
            return Response(200, [f for f in self.fund if a <= f["fundingTime"] <= b][: params["limit"]], {})
        src = self.kl if path.endswith("/klines") else self.mk
        return Response(200, [src[t] for t in sorted(src) if a <= t <= b][: params["limit"]], {})


def fund(ms: int, rate: str = "0.0001", mp: str = "100") -> dict[str, Any]:
    return {"symbol": "BTCUSDT", "fundingTime": ms, "fundingRate": rate, "markPrice": mp}


def run(tmp: Path, rows: list[str], rest: FakeRest, start: int = T0, end: int = T0 + 9 * MIN):
    arch = write_archive(tmp / "arch", rows)
    out = tmp / "out"
    P.capture(out / "raw", rest, arch, start, end)
    return out


def test_classify():
    assert [P.classify(v) for v in (None, "", " ", "x", "NaN", "Infinity", "1.5", 0)] == \
        ["empty", "empty", "empty", "unparseable", "non_finite", "non_finite", "ok", "ok"]


def test_complete_archive_needs_no_rest_and_builds_identically(tmp_path):
    rest = FakeRest(fund=[fund(T0)])
    out = run(tmp_path, [arow(T0 + i * MIN) for i in range(10)], rest)
    assert json.loads((out / "raw" / "fill_ranges.json").read_text())["ranges"] == []
    assert not [c for c in rest.calls if "lines" in c[0] or "Klines" in c[0]]
    m = P.build(out)
    bars, fundings = P.load_prepared(out)
    assert len(bars) == 10 and {b.source for b in bars} == {"archive"} and len(fundings) == 1
    m2 = P.build(out)                                           # 재현: 같은 원시 → 같은 해시
    assert {k: m[k] for k in ("bars_1m.parquet", "funding.json", "source_audit.json")} == \
           {k: m2[k] for k in ("bars_1m.parquet", "funding.json", "source_audit.json")}


def test_archive_row_with_mark_but_empty_kline_is_filled_from_rest(tmp_path):
    rows = [arow(T0 + i * MIN) for i in range(10)]
    rows[3] = arow(T0 + 3 * MIN, kline=False)
    rest = FakeRest({T0 + 3 * MIN: kline(T0 + 3 * MIN)}, {T0 + 3 * MIN: mark(T0 + 3 * MIN)})
    out = run(tmp_path, rows, rest)
    assert json.loads((out / "raw" / "fill_ranges.json").read_text())["ranges"] == [[T0 + 3 * MIN, T0 + 3 * MIN]]
    P.build(out)
    bars, _ = P.load_prepared(out)
    b3 = [b for b in bars if b.open_ms == T0 + 3 * MIN][0]
    assert b3.source == "rest" and b3.mark_open == "200" and b3.open == "200"   # 분 하나 = 출처 하나(혼합 없음)
    audit = json.loads((out / "source_audit.json").read_text())
    assert audit["finding_counts"]["archive_mark_without_kline"] == 1


def test_archive_row_with_bad_mark_is_filled(tmp_path):
    rows = [arow(T0 + i * MIN) for i in range(10)]
    rows[2] = arow(T0 + 2 * MIN, mark="NaN")
    rest = FakeRest({T0 + 2 * MIN: kline(T0 + 2 * MIN)}, {T0 + 2 * MIN: mark(T0 + 2 * MIN)})
    P.build(run(tmp_path, rows, rest))


def test_rest_mark_only_stops(tmp_path):
    rows = [arow(T0 + i * MIN) for i in range(10) if i != 4]
    out = run(tmp_path, rows, FakeRest({}, {T0 + 4 * MIN: mark(T0 + 4 * MIN)}))
    with pytest.raises(P.SourceStop) as e:
        P.build(out)
    assert e.value.findings[0]["kind"] == "rest_mark_only"
    assert not (out / "bars_1m.parquet").exists() and (out / "source_audit.json").exists()


def test_nothing_anywhere_is_a_missing_minute(tmp_path):
    rows = [arow(T0 + i * MIN) for i in range(10) if i != 4]
    out = run(tmp_path, rows, FakeRest({T0 + 4 * MIN: kline(T0 + 4 * MIN)}, {}))
    P.build(out)
    bars, _ = P.load_prepared(out)
    assert len(bars) == 9 and json.loads((out / "source_audit.json").read_text())["minutes_missing"] == 1


def test_rest_malformed_row_stops(tmp_path):
    rows = [arow(T0 + i * MIN) for i in range(10) if i != 4]
    bad = mark(T0 + 4 * MIN)
    bad[2] = ""
    with pytest.raises(P.SourceStop):
        P.build(run(tmp_path, rows, FakeRest({T0 + 4 * MIN: kline(T0 + 4 * MIN)}, {T0 + 4 * MIN: bad})))


def test_archive_duplicates(tmp_path):
    rows = [arow(T0 + i * MIN) for i in range(10)]
    P.build(run(tmp_path / "a", rows + [arow(T0 + 5 * MIN)], FakeRest()))                     # 동일 → 합침
    with pytest.raises(P.SourceStop):
        P.build(run(tmp_path / "b", rows + [arow(T0 + 5 * MIN, p="101")], FakeRest()))        # 값이 다름 → 중단


def test_duplicate_plus_gap_does_not_look_complete(tmp_path):
    """1,440개처럼 보이는 중복 + 결손: 중복은 합쳐지고 결손 분은 결손으로 남는다(격자 검사는 days.py)."""
    rows = [arow(T0 + i * MIN) for i in range(10) if i != 7] + [arow(T0 + 3 * MIN)]
    out = run(tmp_path, rows, FakeRest())
    P.build(out)
    bars, _ = P.load_prepared(out)
    assert sorted(b.open_ms for b in bars) == [T0 + i * MIN for i in range(10) if i != 7]


def test_misaligned_archive_timestamp_is_not_used(tmp_path):
    rows = [arow(T0 + i * MIN) for i in range(10) if i != 6]
    arch = write_archive(tmp_path / "arch", rows)
    (arch / "BTCUSDT_1m_2024.csv").write_text((arch / "BTCUSDT_1m_2024.csv").read_text()
                                              + arow(T0 + 6 * MIN).replace(ts(T0 + 6 * MIN), ts(T0 + 6 * MIN + 30_000)) + "\n")
    out = tmp_path / "out"
    P.capture(out / "raw", FakeRest(), arch, T0, T0 + 9 * MIN)
    P.build(out)
    bars, _ = P.load_prepared(out)
    assert T0 + 6 * MIN not in {b.open_ms for b in bars}


@pytest.mark.parametrize("records,ok", [
    ([fund(T0 + 8 * 3_600_000)], True),
    ([fund(T0 + 8 * 3_600_000), fund(T0 + 8 * 3_600_000)], True),                       # 바이트 동일 → 합침
    ([fund(T0 + 8 * 3_600_000), fund(T0 + 8 * 3_600_000 + 5)], False),                   # 한 분에 다른 시각 둘
    ([fund(T0 + 8 * 3_600_000), fund(T0 + 8 * 3_600_000, rate="0.0002")], False),        # 값이 다름
    ([fund(T0 + 8 * 3_600_000, mp="")], False),                                          # ok 아님
    ([fund(T0 + 8 * 3_600_000, rate="NaN")], False),
    ([fund(T0 + 12 * 3_600_000)], False),                                                # 8h 격자 밖
])
def test_funding_bucket_rules(tmp_path, records, ok):
    rows = [arow(T0 + i * MIN) for i in range(10)]
    arch = write_archive(tmp_path / "arch", rows)
    out = tmp_path / "out"
    P.capture(out / "raw", FakeRest(fund=records), arch, T0, T0 + 9 * MIN)
    #  펀딩은 창 전체 범위를 받는다 — 합성 창(10분) 밖 시각이라도 raw에 들어가도록 캡처 범위를 넓힌 파일로 교체
    (out / "raw" / "funding.jsonl").write_text(json.dumps({"page": records}) + "\n")
    if ok:
        P.build(out)
        _, f = P.load_prepared(out)
        assert len(f) == 1
    else:
        with pytest.raises(P.SourceStop):
            P.build(out)


def test_manifest_mismatch_stops_consumer(tmp_path):
    out = run(tmp_path, [arow(T0 + i * MIN) for i in range(10)], FakeRest())
    P.build(out)
    (out / "funding.json").write_text("[]\n")
    with pytest.raises(ValueError):
        P.load_prepared(out)


def test_window_is_is_plus_21_day_warmup_only():
    a, b = P.window_range()
    from strategies.trial02 import anchor as A
    assert a == A.IS_START_MS - 21 * DAY and b == A.IS_END_MS and b < A.OOS_START_MS


def test_does_not_import_trial01():
    import ast
    src = Path(P.__file__).read_text(encoding="utf-8")
    mods = [n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)]
    assert not any(m and ("trial01" in m or m == "backtest.prepare" or m.endswith(".prepare")) for m in mods)
