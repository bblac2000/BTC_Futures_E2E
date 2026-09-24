"""트라이얼 #2 데이터 준비(단계 2d · 설계 C14~C20 · ops_log 2026-09-24) — **원시 캡처 하나 → 감사 → 빌드 → 매니페스트**.

    uv run python -m backtest.prepare_t2 --out var/backtest/t2/IS            # 판정기 푸시 뒤에만(사용자 체크포인트) · 한 번만
    uv run python -m backtest.prepare_t2 --out var/backtest/t2/IS --verify   # 원시에서 다시 빌드해 대조(덮어쓰지 않음)

1 캡처(`capture`): 창 + 워밍업 21일의 아카이브 CSV 행을 **거르지 않고** `raw/archive_rows.jsonl`로 · 완전한 아카이브 봉이 없는
  모든 정렬 분 = 보충 분(`raw/fill_ranges.json`) → REST `klines`·`markPriceKlines`를 그 구간만 · `fundingRate`는 전 구간 —
  응답 페이지를 그대로 `raw/*.jsonl`로.
2 분석(`analyze` — 순수 함수 · 네트워크 없음): 같은 원시 파일에서 감사(`source_audit.json`)와 빌드(`bars_1m.parquet`,
  `funding.json`)를 함께 만든다. 중단 조건(C12·C18·C19·C20)이 하나라도 있으면 `SourceStop` — 준비 산출물을 쓰지 않는다.
3 매니페스트: 원시·감사·산출물 SHA256 + 코드 커밋. 소비자(전략 실행·판정기)는 `verify_manifest`로 확인한다.

규칙:
- 분마다 출처 **하나**(혼합 없음). 아카이브: mark 4 · kline OHLC·거래량 필드가 전부 `ok`이고 행이 하나(동일 행 중복은 합침)면 사용,
  아니면 쓰지 않고 REST 보충. 아카이브의 다른 중복(값이 다름) → 중단.
- REST(보충 분만): 행이 있는데 필드가 `ok`가 아니면 중단 · mark ok + kline 없음 → 중단(mark-only) · mark 없음 → 결손 분.
  같은 openTime의 다른 행 → 중단(동일 행은 합침).
- 펀딩 버킷 = 기록이 있는 분 [b, b+60,000): 기록 1개 ok → 이벤트 · 전부 바이트 동일 → 합침 · 그 밖의 2개 이상 → 중단 ·
  ok가 아닌 기록 → 중단 · 이벤트 버킷이 00:00·08:00·16:00 UTC가 아니면 중단(사전등록 §1 펀딩 행).
- 값 분류: `empty`(없음·"") · `unparseable`(Decimal 실패) · `non_finite`(NaN·Inf) · `ok`.
🔒 OOS는 준비하지 않는다(창 인자는 IS만 받는다).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from backtest import data as BD
from strategies.trial02 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
MIN = BD.MINUTE_MS
DAY = A.DAY_MS
GRID_HOURS = (0, 8, 16)
ARCH_MARK = ("mark_open", "mark_high", "mark_low", "mark_close")
ARCH_KLINE = ("Open", "High", "Low", "Close", "Volume", "quote_volume", "taker_buy_base", "taker_buy_quote")
REST_KLINE_IDX = (1, 2, 3, 4, 5, 7, 9, 10)          # open high low close volume quoteVolume takerBuyBase takerBuyQuote
REST_MARK_IDX = (1, 2, 3, 4)
BAR_COLS = ("open_ms", "open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote",
            "mark_open", "mark_high", "mark_low", "mark_close", "source")   # backtest.prepare와 같은 열(그 모듈은 트라이얼 #1 앵커를 import)
RAW_FILES = ("archive_rows.jsonl", "fill_ranges.json", "rest_klines.jsonl", "rest_mark.jsonl", "funding.jsonl")


class SourceStop(RuntimeError):
    """사전확약 중단 조건(C12·C18·C19·C20) — 전략 실행을 시작하지 않고 사용자에게 정정 문서로 올린다."""

    def __init__(self, findings: list[dict[str, Any]]):
        super().__init__(f"원시 출처 중단 조건 {len(findings)}건: {findings[:5]}")
        self.findings = findings


def classify(v: Any) -> str:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return "empty"
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return "unparseable"
    return "ok" if d.is_finite() else "non_finite"


def _int_ok(v: Any) -> bool:
    try:
        return int(str(v)) >= 0
    except ValueError:
        return False


def window_range() -> tuple[int, int]:
    """IS 창 + 워밍업 21일(§1 · §5)."""
    return A.IS_START_MS - A.WARMUP_DAYS * DAY, A.IS_END_MS


# ── 1 캡처 ──────────────────────────────────────────────────────────────────
def read_archive_rows(archive: Path, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    """거르지 않은 원시 행(문자열 그대로) + 파싱한 시각. 범위 밖 행만 뺀다."""
    out: list[dict[str, Any]] = []
    for path in BD.archive_files(archive, start_ms, end_ms):
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                try:
                    t = BD._parse_utc(r["timestamp"])
                except (ValueError, KeyError):
                    out.append({"file": path.name, "ts_ms": None, "row": dict(r)})
                    continue
                if start_ms <= t <= end_ms:
                    out.append({"file": path.name, "ts_ms": t, "row": dict(r)})
    return out


def usable_archive(rows: list[dict[str, Any]]) -> tuple[dict[int, dict[str, str]], list[dict[str, Any]]]:
    """정렬 분 → 완전한 아카이브 행. 반환 두 번째 = 발견 목록(보고/중단)."""
    by: dict[int, list[dict[str, str]]] = defaultdict(list)
    findings: list[dict[str, Any]] = []
    for x in rows:
        t = x["ts_ms"]
        if t is None:
            findings.append({"kind": "archive_unparseable_ts", "file": x["file"], "stop": False})
            continue
        if t % MIN:
            findings.append({"kind": "archive_misaligned_ts", "ts_ms": t, "stop": False})
            continue
        by[t].append(x["row"])
    usable: dict[int, dict[str, str]] = {}
    for t, rs in by.items():
        uniq = {json.dumps(r, sort_keys=True) for r in rs}
        if len(uniq) > 1:
            findings.append({"kind": "archive_conflicting_duplicate", "ts_ms": t, "stop": True})
            continue
        if len(rs) > 1:
            findings.append({"kind": "archive_exact_duplicate", "ts_ms": t, "stop": False})
        r = rs[0]
        mark_ok = all(classify(r.get(k)) == "ok" for k in ARCH_MARK)
        kline_ok = all(classify(r.get(k)) == "ok" for k in ARCH_KLINE) and _int_ok(r.get("trades", ""))
        if mark_ok and kline_ok:
            usable[t] = r
        elif mark_ok:
            findings.append({"kind": "archive_mark_without_kline", "ts_ms": t, "stop": False})
        else:
            findings.append({"kind": "archive_mark_not_ok", "ts_ms": t, "stop": False})
    return usable, findings


def fill_ranges(usable: Iterable[int], start_ms: int, end_ms: int) -> list[list[int]]:
    have = set(usable)
    out: list[list[int]] = []
    t = start_ms - start_ms % MIN + (MIN if start_ms % MIN else 0)
    while t <= end_ms:
        if t not in have:
            if out and out[-1][1] == t - MIN:
                out[-1][1] = t
            else:
                out.append([t, t])
        t += MIN
    return out


def _pages(client: Any, path: str, params: dict[str, Any], start_ms: int, end_ms: int, *, ts_key: Any,
           step: int, limit: int) -> list[Any]:
    pages: list[Any] = []
    t = start_ms
    while t <= end_ms:
        page = client.get(path, params | {"startTime": t, "endTime": end_ms, "limit": limit}, signed=False).data
        if not page:
            break
        pages.append(page)
        last = page[-1][ts_key]
        nxt = int(last) + step
        if nxt <= t:
            break
        t = nxt
    return pages


def capture(raw: Path, client: Any, archive: Path, start_ms: int, end_ms: int) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    rows = read_archive_rows(archive, start_ms, end_ms)
    (raw / "archive_rows.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in rows))
    usable, _ = usable_archive(rows)
    fr = fill_ranges(usable, start_ms, end_ms)
    (raw / "fill_ranges.json").write_text(json.dumps({"start_ms": start_ms, "end_ms": end_ms, "ranges": fr}))
    kl = {"symbol": BD.SYMBOL, "interval": "1m"}
    with (raw / "rest_klines.jsonl").open("w") as fk, (raw / "rest_mark.jsonl").open("w") as fm:
        for a, b in fr:
            for page in _pages(client, BD.KLINES_PATH, kl, a, b, ts_key=0, step=MIN, limit=BD.REST_KLINES_LIMIT):
                fk.write(json.dumps({"range": [a, b], "page": page}) + "\n")
            for page in _pages(client, BD.MARK_KLINES_PATH, kl, a, b, ts_key=0, step=MIN, limit=BD.REST_KLINES_LIMIT):
                fm.write(json.dumps({"range": [a, b], "page": page}) + "\n")
    with (raw / "funding.jsonl").open("w") as ff:
        for page in _pages(client, BD.FUNDING_PATH, {"symbol": BD.SYMBOL}, start_ms, end_ms, ts_key="fundingTime", step=1,
                           limit=BD.REST_FUNDING_LIMIT):
            ff.write(json.dumps({"page": page}) + "\n")


# ── 2 분석(순수) ────────────────────────────────────────────────────────────
def _jsonl(p: Path) -> list[Any]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def _rest_rows(raw: Path, name: str, fill: set[int], idx: tuple[int, ...], kind: str,
               findings: list[dict[str, Any]]) -> dict[int, list[Any]]:
    by: dict[int, list[list[Any]]] = defaultdict(list)
    for rec in _jsonl(raw / name):
        for r in rec["page"]:
            t = int(r[0])
            if t % MIN:
                findings.append({"kind": f"rest_{kind}_misaligned_ts", "ts_ms": t, "stop": False})
                continue
            if t in fill:
                by[t].append(r)
    out: dict[int, list[Any]] = {}
    for t, rs in by.items():
        if len({json.dumps(r) for r in rs}) > 1:
            findings.append({"kind": f"rest_{kind}_conflicting_duplicate", "ts_ms": t, "stop": True})
            continue
        if len(rs) > 1:
            findings.append({"kind": f"rest_{kind}_exact_duplicate", "ts_ms": t, "stop": False})
        r = rs[0]
        bad = [i for i in idx if i >= len(r) or classify(r[i]) != "ok"]
        if kind == "kline" and (len(r) <= 8 or not _int_ok(r[8])):
            bad.append(8)
        if bad:
            findings.append({"kind": f"rest_{kind}_malformed", "ts_ms": t, "fields": bad, "stop": True})
            continue
        out[t] = r
    return out


def _funding(raw: Path, findings: list[dict[str, Any]]) -> list[BD.Funding]:
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for rec in _jsonl(raw / "funding.jsonl"):
        for r in rec["page"]:
            ft = r.get("fundingTime")
            if not _int_ok(ft):
                findings.append({"kind": "funding_bad_time", "record": r, "stop": True})
                continue
            buckets[int(ft) - int(ft) % MIN].append(r)
    events: list[BD.Funding] = []
    for b in sorted(buckets):
        rs = buckets[b]
        keyed = {json.dumps({k: str(r.get(k)) for k in ("fundingTime", "fundingRate", "markPrice")}, sort_keys=True) for r in rs}
        if len(keyed) > 1:
            findings.append({"kind": "funding_bucket_multiple", "bucket_ms": b, "n": len(rs), "stop": True})
            continue
        if len(rs) > 1:
            findings.append({"kind": "funding_exact_duplicate", "bucket_ms": b, "stop": False})
        r = rs[0]
        if classify(r.get("fundingRate")) != "ok" or classify(r.get("markPrice")) != "ok":
            findings.append({"kind": "funding_malformed", "bucket_ms": b, "stop": True})
            continue
        if (b % DAY) not in {h * 3_600_000 for h in GRID_HOURS}:
            findings.append({"kind": "funding_off_grid", "bucket_ms": b, "stop": True})
            continue
        events.append(BD.Funding(int(r["fundingTime"]), str(r["fundingRate"]), str(r["markPrice"])))
    return events


def analyze(raw: Path, expect_range: tuple[int, int] | None = None) -> tuple[list[BD.Bar1m], list[BD.Funding], dict[str, Any]]:
    """원시 파일만 읽는다. 중단 조건이 있으면 감사와 함께 `SourceStop`."""
    meta = json.loads((raw / "fill_ranges.json").read_text())
    start, end = meta["start_ms"], meta["end_ms"]
    if expect_range is not None and (start, end) != expect_range:
        raise ValueError(f"원시 캡처 범위 {(start, end)} ≠ 기대 {expect_range}(IS + 워밍업 21일만)")
    usable, findings = usable_archive(_jsonl(raw / "archive_rows.jsonl"))
    fr = fill_ranges(usable, start, end)
    if fr != meta["ranges"]:
        findings.append({"kind": "fill_ranges_mismatch", "stop": True})
    fill = {t for a, b in fr for t in range(a, b + 1, MIN)}
    kl = _rest_rows(raw, "rest_klines.jsonl", fill, REST_KLINE_IDX, "kline", findings)
    mk = _rest_rows(raw, "rest_mark.jsonl", fill, REST_MARK_IDX, "mark", findings)
    bars: list[BD.Bar1m] = []
    missing = 0
    for t in range(start - start % MIN + (MIN if start % MIN else 0), end + 1, MIN):
        if t in usable:
            r = usable[t]
            bars.append(BD.Bar1m(t, r["Open"], r["High"], r["Low"], r["Close"], r["Volume"], r["quote_volume"], int(r["trades"]),
                                 r["taker_buy_base"], r["taker_buy_quote"], r["mark_open"], r["mark_high"], r["mark_low"],
                                 r["mark_close"], "archive"))
        elif t in mk and t in kl:
            k, m = kl[t], mk[t]
            bars.append(BD.Bar1m(t, str(k[1]), str(k[2]), str(k[3]), str(k[4]), str(k[5]), str(k[7]), int(k[8]), str(k[9]),
                                 str(k[10]), str(m[1]), str(m[2]), str(m[3]), str(m[4]), "rest"))
        elif t in mk:
            findings.append({"kind": "rest_mark_only", "ts_ms": t, "stop": True})
        else:
            missing += 1
            if t in kl:
                findings.append({"kind": "rest_kline_only", "ts_ms": t, "stop": False})
    fundings = _funding(raw, findings)
    kinds: dict[str, int] = defaultdict(int)
    for f in findings:
        kinds[f["kind"]] += 1
    stops = [f for f in findings if f["stop"]]
    audit = {"start_ms": start, "end_ms": end, "minutes_missing": missing, "bars": len(bars),
             "bars_archive": sum(b.source == "archive" for b in bars), "bars_rest": sum(b.source == "rest" for b in bars),
             "fill_minutes": len(fill), "funding_events": len(fundings), "finding_counts": dict(sorted(kinds.items())),
             "stops": stops, "findings_nonstop": [f for f in findings if not f["stop"]][:1000]}
    if stops:
        raise _StopWithAudit(stops, audit)
    return bars, fundings, audit


class _StopWithAudit(SourceStop):
    def __init__(self, findings: list[dict[str, Any]], audit: dict[str, Any]):
        super().__init__(findings)
        self.audit = audit


# ── 3 쓰기·매니페스트 ────────────────────────────────────────────────────────
def write_bars(path: Path, bars: list[BD.Bar1m]) -> None:
    pq.write_table(pa.table({c: [getattr(b, c) for b in bars] for c in BAR_COLS}), path)


def read_bars(path: Path) -> list[BD.Bar1m]:
    t = pq.read_table(path).to_pydict()
    return [BD.Bar1m(*(t[c][i] for c in BAR_COLS)) for i in range(len(t["open_ms"]))]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build(out: Path, expect_range: tuple[int, int] | None = None) -> dict[str, Any]:
    """`out/raw`의 원시 파일 → 감사·산출물·매니페스트. 중단이면 감사만 쓰고 SourceStop을 다시 던진다."""
    raw = out / "raw"
    try:
        bars, fundings, audit = analyze(raw, expect_range)
    except _StopWithAudit as e:
        (out / "source_audit.json").write_text(json.dumps(e.audit, sort_keys=True, indent=1))
        raise
    (out / "source_audit.json").write_text(json.dumps(audit, sort_keys=True, indent=1))
    write_bars(out / "bars_1m.parquet", bars)
    (out / "funding.json").write_text(json.dumps([f.__dict__ for f in fundings], sort_keys=True))
    manifest = {"raw": {n: _sha(raw / n) for n in RAW_FILES}, "source_audit.json": _sha(out / "source_audit.json"),
                "bars_1m.parquet": _sha(out / "bars_1m.parquet"), "funding.json": _sha(out / "funding.json"),
                "code_commit": _commit(), "window": "IS+warmup21"}
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=1))
    return manifest


def verify_manifest(out: Path) -> dict[str, Any]:
    """소비자 쪽 검사 — 산출물·원시 해시가 매니페스트와 다르면 ValueError."""
    m = json.loads((out / "manifest.json").read_text())
    bad = [n for n in ("source_audit.json", "bars_1m.parquet", "funding.json") if _sha(out / n) != m[n]]
    bad += [f"raw/{n}" for n in RAW_FILES if _sha(out / "raw" / n) != m["raw"][n]]
    if bad:
        raise ValueError(f"매니페스트 불일치: {bad}")
    return m


PREPARED = ("bars_1m.parquet", "funding.json", "source_audit.json")


def load_prepared_pinned(out: Path, pins: dict[str, Any],
                         expect_range: tuple[int, int]) -> tuple[list[BD.Bar1m], list[BD.Funding]]:
    """실행 경로(G12 · 해시만 · 다시 빌드하지 않음): 매니페스트 해시 + 원시·산출물 해시가 `pins`(커밋된 data_pins.json)와 같아야 한다.
    원시 → 산출물의 재현은 `verify` 단계 영수증과 판정기가 따로 증명한다."""
    m = verify_manifest(out)
    if m["raw"] != pins["raw"] or {k: m[k] for k in PREPARED} != pins["prepared"]:
        raise ValueError("준비 산출물·원시 해시가 고정값(data_pins)과 다르다")
    meta = json.loads((out / "raw" / "fill_ranges.json").read_text())
    if (meta["start_ms"], meta["end_ms"]) != expect_range:
        raise ValueError(f"캡처 범위 {(meta['start_ms'], meta['end_ms'])} ≠ 기대 {expect_range}")
    return read_bars(out / "bars_1m.parquet"), [BD.Funding(**f) for f in json.loads((out / "funding.json").read_text())]


def verify_rebuild(out: Path, expect_range: tuple[int, int] | None = None) -> dict[str, Any]:
    """원시 파일에서 **다시 빌드**해 산출물 해시가 매니페스트와 같은지 확인한다(덮어쓰지 않는다 · 임시 디렉터리).
    매니페스트 자체의 원시 해시는 캡처 직후 레지스트리 행에 고정된 값과 호출자가 대조한다(`pinned_raw`)."""
    import shutil
    import tempfile
    m = verify_manifest(out)
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        shutil.copytree(out / "raw", t / "raw")
        m2 = build(t, expect_range)
    bad = [n for n in ("source_audit.json", "bars_1m.parquet", "funding.json") if m2[n] != m[n]]
    if bad:
        raise ValueError(f"원시에서 다시 빌드한 산출물이 다르다: {bad}")
    return m


def load_prepared(out: Path, *, pinned_raw: dict[str, str],
                  expect_range: tuple[int, int]) -> tuple[list[BD.Bar1m], list[BD.Funding]]:
    """소비자 입구(필수 고정): 매니페스트 해시 + 원시에서 다시 빌드한 해시 일치 + 고정된 원시 해시 일치 + 범위 일치."""
    m = verify_rebuild(out, expect_range)
    if m["raw"] != pinned_raw:
        raise ValueError("원시 해시가 레지스트리에 고정된 값과 다르다")
    return read_bars(out / "bars_1m.parquet"), [BD.Funding(**f) for f in json.loads((out / "funding.json").read_text())]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="트라이얼 #2 IS 데이터 준비(원시 캡처 → 감사 → 빌드)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true", help="캡처·덮어쓰기 없이 raw/에서 다시 빌드해 산출물 해시를 대조")
    a = ap.parse_args(argv)
    out = Path(a.out)
    rng = window_range()
    if a.verify:
        m = verify_rebuild(out, rng)
        print(json.dumps({"verified": True} | m, sort_keys=True, indent=1))
        return 0
    if (out / "manifest.json").exists():
        print("🚫 이미 준비된 출력이 있다 — 다시 캡처하지 않는다(--verify로 대조만)", file=sys.stderr)
        return 5
    from exchange.ccxt_rest import CcxtRestClient
    from exchange.client import ReadOnlyClient
    capture(out / "raw", ReadOnlyClient(CcxtRestClient()), BD.ARCHIVE_DIR, *rng)
    try:
        m = build(out, rng)
    except SourceStop as e:
        print(f"🚫 {e}", file=sys.stderr)
        return 3
    print(json.dumps(m, sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
