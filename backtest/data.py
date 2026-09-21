"""백테스트 데이터 — 1m kline + mark 1m + 확정 펀딩. **전략과 무관**(단계 2a 하네스).

출처(2026-09-21 실측 · 2a 보고):
- 로컬 아카이브 `/home/cms/project/data/BTCUSDT/1m/BTCUSDT_1m_<연도>.csv`(재수집 금지). **타임스탬프는 UTC 봉 시작**이다 —
  REST `klines`·`markPriceKlines`와 OHLCV·mark가 정확히 일치함을 확인(2024-12-31 15:00Z). 파일은 **KST 연도**로 나뉜다
  (`_2024.csv`의 첫 행이 `2023-12-31 15:00:00`). 그래서 연도 경계를 가정하지 않고 필요한 파일을 넉넉히 읽어 시각으로 거른다.
- 아카이브는 **2026-06-18 14:59 UTC에서 끝난다** → 그 뒤(IS 끝 12일 + OOS 전부)는 REST `klines` + `markPriceKlines`로 채운다.
  봉마다 `source`(`archive`/`rest`)를 남긴다.
- 아카이브의 `funding_rate` 열은 **분마다 앞값 채움**이라 확정 펀딩이 아니다 → 펀딩은 **REST `/fapi/v1/fundingRate`**(확정율 +
  정산 시점 mark)만 쓴다(사전등록 §2 "실제 펀딩율 · 추정·평균값 금지").

저장소: 봇 DB(`bars_1m`)와 섞지 않는다 — 백테스트 전용 parquet(`var/backtest/`). 가격·수량은 **정확한 10진 문자열**로 보관한다.
"""
from __future__ import annotations

import csv
import datetime as dt
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

MINUTE_MS = 60_000
ARCHIVE_DIR = Path("/home/cms/project/data/BTCUSDT/1m")
KLINES_PATH = "/fapi/v1/klines"
MARK_KLINES_PATH = "/fapi/v1/markPriceKlines"
FUNDING_PATH = "/fapi/v1/fundingRate"
REST_KLINES_LIMIT = 1500
REST_FUNDING_LIMIT = 1000
SYMBOL = "BTCUSDT"

PRICE_FIELDS = ("open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base", "taker_buy_quote",
                "mark_open", "mark_high", "mark_low", "mark_close")


@dataclass(frozen=True)
class Bar1m:
    """1m 봉 하나 — last(kline) + mark OHLC. 값은 정확한 10진 문자열."""
    open_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    quote_volume: str
    trades: int
    taker_buy_base: str
    taker_buy_quote: str
    mark_open: str
    mark_high: str
    mark_low: str
    mark_close: str
    source: str                                     # "archive" | "rest"

    def d(self, name: str) -> Decimal:
        return Decimal(getattr(self, name))


@dataclass(frozen=True)
class Funding:
    """확정 펀딩(REST fundingRate) — 정산 시각·율·정산 시점 mark."""
    funding_ms: int
    rate: str
    mark: str


@dataclass
class DataIntegrity:
    """창 하나의 무결성 — IS 보고서에 그대로(verbatim) 붙인다."""
    start_ms: int
    end_ms: int
    expected_minutes: int
    actual_minutes: int
    missing_ranges: list[tuple[int, int]] = field(default_factory=list)   # [시작, 끝] 포함 구간(분 시작 ms)
    duplicates: int = 0
    monotone: bool = True
    by_source: dict[str, int] = field(default_factory=dict)
    mark_missing: int = 0

    @property
    def missing_minutes(self) -> int:
        return sum((b - a) // MINUTE_MS + 1 for a, b in self.missing_ranges)

    @property
    def ok(self) -> bool:
        return self.missing_minutes == 0 and self.duplicates == 0 and self.monotone and self.mark_missing == 0

    def as_dict(self) -> dict[str, Any]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms, "expected_minutes": self.expected_minutes,
                "actual_minutes": self.actual_minutes, "missing_minutes": self.missing_minutes,
                "missing_ranges": [list(r) for r in self.missing_ranges], "duplicates": self.duplicates,
                "monotone": self.monotone, "by_source": dict(sorted(self.by_source.items())),
                "mark_missing": self.mark_missing, "ok": self.ok}


# ── 아카이브 ────────────────────────────────────────────────────────────────
def _parse_utc(ts: str) -> int:
    return int(dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.UTC).timestamp() * 1000)


def archive_files(root: Path, start_ms: int, end_ms: int) -> list[Path]:
    """KST 연도 파일 — 창의 UTC 연도 ±1을 읽고 시각으로 거른다(연도 경계를 가정하지 않는다)."""
    y0 = dt.datetime.fromtimestamp(start_ms / 1000, dt.UTC).year
    y1 = dt.datetime.fromtimestamp(end_ms / 1000, dt.UTC).year
    out = [root / f"BTCUSDT_1m_{y}.csv" for y in range(y0 - 1, y1 + 2)]
    return [p for p in out if p.exists()]


def load_archive(root: Path, start_ms: int, end_ms: int) -> list[Bar1m]:
    bars: list[Bar1m] = []
    for path in archive_files(root, start_ms, end_ms):
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                t = _parse_utc(r["timestamp"])
                if t < start_ms or t > end_ms:
                    continue
                if not all(r[k] for k in ("mark_open", "mark_high", "mark_low", "mark_close")):
                    continue                            # mark 없는 봉은 쓰지 않는다 — 무결성에서 결손으로 잡힌다
                bars.append(Bar1m(t, r["Open"], r["High"], r["Low"], r["Close"], r["Volume"], r["quote_volume"],
                                  int(r["trades"]), r["taker_buy_base"], r["taker_buy_quote"], r["mark_open"],
                                  r["mark_high"], r["mark_low"], r["mark_close"], "archive"))
    bars.sort(key=lambda b: b.open_ms)
    return bars


# ── REST 보충 ───────────────────────────────────────────────────────────────
def _paged(client: Any, path: str, start_ms: int, end_ms: int) -> list[list[Any]]:
    rows: list[list[Any]] = []
    t = start_ms
    while t <= end_ms:
        page = client.get(path, {"symbol": SYMBOL, "interval": "1m", "startTime": t, "endTime": end_ms,
                                 "limit": REST_KLINES_LIMIT}, signed=False).data
        if not page:
            break
        rows.extend(page)
        nxt = int(page[-1][0]) + MINUTE_MS
        if nxt <= t:
            break
        t = nxt
    return rows


def fetch_rest_bars(client: Any, start_ms: int, end_ms: int) -> list[Bar1m]:
    """REST `klines` + `markPriceKlines`를 분 시작 시각으로 합친다. 한쪽만 있는 분은 쓰지 않는다(무결성 결손)."""
    last = {int(r[0]): r for r in _paged(client, KLINES_PATH, start_ms, end_ms)}
    mark = {int(r[0]): r for r in _paged(client, MARK_KLINES_PATH, start_ms, end_ms)}
    out = []
    for t in sorted(last.keys() & mark.keys()):
        k, m = last[t], mark[t]
        if not (start_ms <= t <= end_ms):
            continue
        out.append(Bar1m(t, str(k[1]), str(k[2]), str(k[3]), str(k[4]), str(k[5]), str(k[7]), int(k[8]),
                         str(k[9]), str(k[10]), str(m[1]), str(m[2]), str(m[3]), str(m[4]), "rest"))
    return out


def fetch_funding(client: Any, start_ms: int, end_ms: int) -> list[Funding]:
    out: list[Funding] = []
    t = start_ms
    while t <= end_ms:
        page = client.get(FUNDING_PATH, {"symbol": SYMBOL, "startTime": t, "endTime": end_ms,
                                         "limit": REST_FUNDING_LIMIT}, signed=False).data
        if not page:
            break
        out.extend(Funding(int(r["fundingTime"]), str(r["fundingRate"]), str(r["markPrice"])) for r in page)
        nxt = int(page[-1]["fundingTime"]) + 1
        if nxt <= t:
            break
        t = nxt
    dedup = {f.funding_ms: f for f in out}
    return [dedup[k] for k in sorted(dedup)]


def merge_sources(*parts: Iterable[Bar1m]) -> list[Bar1m]:
    """먼저 온 출처를 우선한다(아카이브 → REST 순으로 넘긴다). 같은 분이 두 출처에 있으면 앞의 것."""
    seen: dict[int, Bar1m] = {}
    for part in parts:
        for b in part:
            seen.setdefault(b.open_ms, b)
    return [seen[k] for k in sorted(seen)]


def load_window(root: Path, client: Any, start_ms: int, end_ms: int) -> list[Bar1m]:
    """아카이브 우선 + 아카이브가 없는 분만 REST로 채운다."""
    arch = load_archive(root, start_ms, end_ms)
    have = {b.open_ms for b in arch}
    rest: list[Bar1m] = []
    for a, b in _missing_ranges(have, start_ms, end_ms):
        rest.extend(fetch_rest_bars(client, a, b + MINUTE_MS - 1))
    return merge_sources(arch, rest)


# ── 무결성 ──────────────────────────────────────────────────────────────────
def _missing_ranges(have: set[int], start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    run: int | None = None
    t = -(-start_ms // MINUTE_MS) * MINUTE_MS                   # 창 시작을 분 경계로 올림
    while t <= end_ms:
        if t not in have:
            run = t if run is None else run
        elif run is not None:
            out.append((run, t - MINUTE_MS))
            run = None
        t += MINUTE_MS
    if run is not None:
        out.append((run, t - MINUTE_MS))
    return out


def integrity(bars: list[Bar1m], start_ms: int, end_ms: int) -> DataIntegrity:
    times = [b.open_ms for b in bars]
    expected = (end_ms - start_ms + 1) // MINUTE_MS
    by_source: dict[str, int] = {}
    for b in bars:
        by_source[b.source] = by_source.get(b.source, 0) + 1
    return DataIntegrity(
        start_ms=start_ms, end_ms=end_ms, expected_minutes=expected, actual_minutes=len(set(times)),
        missing_ranges=_missing_ranges(set(times), start_ms, end_ms), duplicates=len(times) - len(set(times)),
        monotone=all(a < b for a, b in zip(times, times[1:], strict=False)), by_source=by_source,
        mark_missing=sum(1 for b in bars if not (b.mark_open and b.mark_close)))


def assert_utc_alignment(bars: list[Bar1m], client: Any, sample_ms: Iterable[int]) -> list[dict[str, Any]]:
    """표본 분의 아카이브 봉을 REST와 대조 — 라벨이 UTC 봉 시작이 아니면 즉시 실패(주석이 아니라 검사)."""
    by_t = {b.open_ms: b for b in bars}
    out = []
    for t in sample_ms:
        b = by_t.get(t)
        if b is None:
            continue
        k = client.get(KLINES_PATH, {"symbol": SYMBOL, "interval": "1m", "startTime": t, "limit": 1}, signed=False).data[0]
        m = client.get(MARK_KLINES_PATH, {"symbol": SYMBOL, "interval": "1m", "startTime": t, "limit": 1}, signed=False).data[0]
        same = (int(k[0]) == t and Decimal(str(k[1])) == b.d("open") and Decimal(str(k[4])) == b.d("close")
                and Decimal(str(k[5])) == b.d("volume") and Decimal(str(m[1])) == b.d("mark_open")
                and Decimal(str(m[4])) == b.d("mark_close"))
        out.append({"open_ms": t, "match": same})
        if not same:
            raise AssertionError(f"아카이브 봉 {t}가 REST와 다르다 — 타임스탬프 기준(UTC 봉 시작) 또는 값 불일치")
    return out


def reconcile_with_bot_db(bars: list[Bar1m], db_path: Path, *, mode: str = "paper") -> dict[str, Any]:
    """봇 DB `bars_1m`와 겹치는 분만 대조한다(겹침이 얇다는 사실 자체를 보고한다)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT open_time_ms, open, high, low, close, volume FROM bars_1m WHERE mode=? ORDER BY open_time_ms",
                           (mode,)).fetchall()
    finally:
        con.close()
    by_t = {b.open_ms: b for b in bars}
    overlap = mismatch = 0
    first_mismatch: list[int] = []
    for t, o, h, lo, c, v in rows:
        b = by_t.get(int(t))
        if b is None:
            continue
        overlap += 1
        if (Decimal(o), Decimal(h), Decimal(lo), Decimal(c), Decimal(v)) != (b.d("open"), b.d("high"), b.d("low"),
                                                                                b.d("close"), b.d("volume")):
            mismatch += 1
            if len(first_mismatch) < 5:
                first_mismatch.append(int(t))
    return {"db": str(db_path), "db_rows": len(rows), "overlap": overlap, "mismatch": mismatch,
            "first_mismatch_ms": first_mismatch}


def iter_bars(bars: list[Bar1m], start_ms: int, end_ms: int) -> Iterator[Bar1m]:
    for b in bars:
        if start_ms <= b.open_ms <= end_ms:
            yield b
