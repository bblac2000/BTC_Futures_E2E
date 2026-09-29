"""트라이얼 #3 데이터 준비(단계 2 (a) · 계획 r5 S1·S6·S7 · 사전등록 §5) — **원시 캡처 하나 → 감사 → 빌드 → 매니페스트**.

    uv run python -m backtest.prepare_t3 --out var/t3/IS --evaluator-commit <H>   # 판정기가 origin/main에 푸시된 뒤에만 · 한 번만
    uv run python -m backtest.prepare_t3 --out var/t3/IS --verify                 # 원시에서 다시 빌드해 대조(덮어쓰지 않음)

가격·펀딩은 트라이얼 #2 준비 함수를 **그대로 import**한다(`prepare_t2`는 수정하지 않는다 · 계획 r5 S6):
`analyze`(순수 · 범위 인자) · `fill_ranges` · `usable_archive` · `_pages`. 다른 것은 이 파일에 있다:
- 🔒 OOS 가드(S7): IS 경로의 범위는 [2023-10-02 00:00Z, 2025-12-31 23:59:59.999Z] 안이어야 한다(`OOSGuard`).
  아카이브는 줄마다 **타임스탬프만** 먼저 읽고 끝 뒤 첫 행에서 파일을 멈춘다(값 필드를 파싱하지 않는다) · REST 요청은 endTime ≤ 끝 ·
  OI zip은 파일 이름 날짜로 고르고 행은 create_time이 범위 밖이면 **값을 분류하기 전에** 버린다 · 적재기는 모든 타임스탬프를 다시 단언한다 ·
  산출물 디렉터리는 `var/t3/` 아래만(`var/t3_s0`·`var/backtest`는 입력이 아니다).
- OI(§5 · binance.vision `futures/um/daily/metrics/BTCUSDT` 5분 행 `sum_open_interest`): zip + CHECKSUM을 원시로 보관·해시 ·
  CHECKSUM 불일치 → 중단 · 필요한 날 파일 없음 → 중단 · create_time 해석 불가 → 중단 · 5분 경계 아님 → 중단 ·
  같은 create_time(파일과 무관)의 `sum_open_interest` 문자열이 다르면 중단, 같으면 합침 ·
  값이 ok(유한 Decimal)가 아닌 행은 **없는 행**(관측 결손)으로 센다 — 중단 아님(사용자 결정 2026-09-29 · 구현 선택 행) ·
  그런 슬롯(유효 값이 하나도 없는 create_time)은 날별·전체 개수와 목록(`oi_unusable.json`)으로 남긴다(결과 보고의 oi_missing 사유 구분) ·
  **IS 창의 5분 격자 중 사용 불가 슬롯 > 0.5%면 데이터 품질 중단**(`oi_unusable_over_cap` · 워밍업 슬롯은 기록만).
- OOS 진입점(`oos_range`)은 정의만 한다 — 레지스트리에 "트라이얼 #3 OOS 개봉" + 사용자 결정 행이 있어야 범위를 돌려준다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from backtest import data as BD
from backtest import prepare_t2 as T2
from strategies.trial03 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
MIN = BD.MINUTE_MS
OI_STEP = 300_000
OI_URL = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-{day}.zip"
PRICE_RAW = T2.RAW_FILES
PREPARED = ("bars_1m.parquet", "funding.json", "source_audit.json", "kline_close_daily.json", "oi_5m.json", "oi_unusable.json")
OI_UNUSABLE_CAP = 0.005                                   # 사용 불가 OI 슬롯 / IS 창 5분 격자 > 0.5% → 중단(사용자 결정 2026-09-29)
SourceStop = T2.SourceStop
OIFetch = Callable[[str], tuple[bytes, str]]              # 날짜(YYYY-MM-DD) → (zip 바이트, CHECKSUM 텍스트)


class OOSGuard(RuntimeError):
    """IS 경로가 창 밖(특히 ≥ 2026-01-01 00:00Z)이나 다른 트라이얼의 디렉터리에 닿으려 할 때."""


def is_range() -> tuple[int, int]:
    return A.DATA_START_MS, A.IS_END_MS


def check_is_bounds(start_ms: int, end_ms: int) -> None:
    if not (A.DATA_START_MS <= start_ms <= end_ms <= A.IS_END_MS):
        raise OOSGuard(f"범위 [{start_ms}, {end_ms}]가 IS 경로 한계 [{A.DATA_START_MS}, {A.IS_END_MS}] 밖")


def assert_in_range(ts: Iterable[int], start_ms: int, end_ms: int) -> None:
    bad = [t for t in ts if not start_ms <= t <= end_ms]
    if bad:
        raise OOSGuard(f"범위 밖 타임스탬프 {len(bad)}개(첫 {bad[0]})")


def _day(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%d")


def oi_days(start_ms: int, end_ms: int) -> list[str]:
    return [_day(d * A.DAY_MS) for d in range(start_ms // A.DAY_MS, end_ms // A.DAY_MS + 1)]


# ── 1 캡처 ──────────────────────────────────────────────────────────────────
def read_archive_rows_bounded(archive: Path, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    """아카이브 행(문자열 그대로) — 타임스탬프(첫 열)만 먼저 읽는다. 시작 전 행은 건너뛰고 **끝 뒤 첫 행에서 그 파일을 멈춘다**
    (끝 뒤 행의 값은 파싱하지 않는다). 해석 불가 타임스탬프 행은 범위 안 위치에 있을 때만 남는다(트라이얼 #2 감사와 같은 발견)."""
    out: list[dict[str, Any]] = []
    for path in BD.archive_files(archive, start_ms, end_ms):
        with path.open(newline="") as f:
            header = next(csv.reader([f.readline()]))
            for line in f:
                if not line.strip():
                    continue
                head = line.split(",", 1)[0]
                try:
                    t: int | None = BD._parse_utc(head)
                except ValueError:
                    t = None
                if t is not None and t < start_ms:
                    continue
                if t is not None and t > end_ms:
                    break
                row = dict(zip(header, next(csv.reader([line])), strict=False))
                out.append({"file": path.name, "ts_ms": t, "row": row})
    return out


def fetch_oi_http(day: str) -> tuple[bytes, str]:  # pragma: no cover — 네트워크(실행 경로만)
    import urllib.request
    url = OI_URL.format(day=day)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    with urllib.request.urlopen(url + ".CHECKSUM", timeout=60) as r:
        chk = r.read().decode("utf-8")
    return data, chk


def capture(raw: Path, client: Any, archive: Path, fetch_oi: OIFetch, start_ms: int, end_ms: int) -> None:
    check_is_bounds(start_ms, end_ms)
    raw.mkdir(parents=True, exist_ok=True)
    rows = read_archive_rows_bounded(archive, start_ms, end_ms)
    (raw / "archive_rows.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in rows))
    usable, _ = T2.usable_archive(rows)
    fr = T2.fill_ranges(usable, start_ms, end_ms)
    (raw / "fill_ranges.json").write_text(json.dumps({"start_ms": start_ms, "end_ms": end_ms, "ranges": fr}))
    kl = {"symbol": BD.SYMBOL, "interval": "1m"}
    with (raw / "rest_klines.jsonl").open("w") as fk, (raw / "rest_mark.jsonl").open("w") as fm:
        for a, b in fr:
            for page in T2._pages(client, BD.KLINES_PATH, kl, a, b, ts_key=0, step=MIN, limit=BD.REST_KLINES_LIMIT):
                fk.write(json.dumps({"range": [a, b], "page": page}) + "\n")
            for page in T2._pages(client, BD.MARK_KLINES_PATH, kl, a, b, ts_key=0, step=MIN, limit=BD.REST_KLINES_LIMIT):
                fm.write(json.dumps({"range": [a, b], "page": page}) + "\n")
    with (raw / "funding.jsonl").open("w") as ff:
        for page in T2._pages(client, BD.FUNDING_PATH, {"symbol": BD.SYMBOL}, start_ms, end_ms, ts_key="fundingTime",
                              step=1, limit=BD.REST_FUNDING_LIMIT):
            ff.write(json.dumps({"page": page}) + "\n")
    oi = raw / "oi"
    oi.mkdir(exist_ok=True)
    for day in oi_days(start_ms, end_ms):
        data, chk = fetch_oi(day)
        (oi / f"BTCUSDT-metrics-{day}.zip").write_bytes(data)
        (oi / f"BTCUSDT-metrics-{day}.zip.CHECKSUM").write_text(chk)


# ── 2 분석(순수) ────────────────────────────────────────────────────────────
def _parse_oi_time(s: str) -> int:
    return int(dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.UTC).timestamp() * 1000)


def analyze_oi(oi_dir: Path, start_ms: int, end_ms: int) -> tuple[list[list[Any]], dict[str, Any], list[dict[str, Any]]]:
    """OI 5분 계열 [[create_time_ms, sum_open_interest 문자열], …](오름차순) · 감사 · 중단 발견."""
    stops: list[dict[str, Any]] = []
    by: dict[int, set[str]] = defaultdict(set)
    bad_slots: set[int] = set()
    rows_in = dups = outside = not_ok = 0
    seen: dict[int, int] = defaultdict(int)
    for day in oi_days(start_ms, end_ms):
        zp = oi_dir / f"BTCUSDT-metrics-{day}.zip"
        cp = oi_dir / f"BTCUSDT-metrics-{day}.zip.CHECKSUM"
        if not zp.exists() or not cp.exists():
            stops.append({"kind": "oi_day_file_missing", "day": day, "stop": True})
            continue
        data = zp.read_bytes()
        want = (cp.read_text().split() or [""])[0].lower()
        if hashlib.sha256(data).hexdigest() != want:
            stops.append({"kind": "oi_checksum_mismatch", "day": day, "stop": True})
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n.endswith(".csv")]
            if len(names) != 1:
                stops.append({"kind": "oi_zip_members", "day": day, "n": len(names), "stop": True})
                continue
            text = z.read(names[0]).decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        if "create_time" not in header or "sum_open_interest" not in header:
            stops.append({"kind": "oi_missing_columns", "day": day, "stop": True})
            continue
        ic, iv = header.index("create_time"), header.index("sum_open_interest")
        for r in reader:
            if not r:
                continue
            try:
                t = _parse_oi_time(r[ic])
            except (ValueError, IndexError):
                stops.append({"kind": "oi_unparseable_time", "day": day, "stop": True})
                continue
            if t % OI_STEP:
                stops.append({"kind": "oi_off_grid", "ts_ms": t, "stop": True})
                continue
            if not start_ms <= t <= end_ms:
                outside += 1                               # 🔒 값은 보지 않는다(OOS 가드)
                continue
            rows_in += 1
            v = r[iv] if iv < len(r) else ""
            if T2.classify(v) != "ok":
                not_ok += 1                                # 없는 행으로 센다(중단 아님)
                bad_slots.add(t)
                continue
            seen[t] += 1
            by[t].add(v)
    for t in sorted(by):
        if len(by[t]) > 1:
            stops.append({"kind": "oi_conflicting_duplicate", "ts_ms": t, "stop": True})
        elif seen[t] > 1:
            dups += seen[t] - 1
    series = [[t, next(iter(by[t]))] for t in sorted(by) if len(by[t]) == 1]
    unusable = sorted(bad_slots - by.keys())               # 유효 값이 있는 중복이 있으면 사용 가능
    per_day: dict[str, int] = defaultdict(int)
    for t in unusable:
        per_day[_day(t)] += 1
    lo, hi = max(start_ms, A.WINDOW_START_MS), min(end_ms, A.IS_END_MS)
    is_grid = 0 if hi < lo else (hi - (lo + (-lo) % OI_STEP)) // OI_STEP + 1
    is_bad = sum(A.WINDOW_START_MS <= t <= A.IS_END_MS for t in unusable)
    if is_grid and is_bad > OI_UNUSABLE_CAP * is_grid:
        stops.append({"kind": "oi_unusable_over_cap", "unusable": is_bad, "grid": is_grid, "stop": True})
    audit = {"start_ms": start_ms, "end_ms": end_ms, "days": len(oi_days(start_ms, end_ms)), "rows_in_range": rows_in,
             "rows_outside_range": outside, "value_not_ok": not_ok, "exact_duplicates": dups, "series_rows": len(series),
             "unusable_slots": unusable, "unusable_per_day": dict(sorted(per_day.items())), "unusable_total": len(unusable),
             "unusable_is_slots": is_bad, "is_grid_slots": is_grid, "unusable_cap": OI_UNUSABLE_CAP,
             "stops": stops}
    return series, audit, stops


def analyze(raw: Path, expect_range: tuple[int, int]) -> tuple[list[BD.Bar1m], list[BD.Funding], dict[str, Any],
                                                             list[dict[str, Any]], list[list[Any]]]:
    start, end = expect_range
    check_is_bounds(start, end)
    price_stop: SourceStop | None = None
    try:
        bars, fundings, price_audit, kline_daily = T2.analyze(raw, expect_range)
    except T2._StopWithAudit as e:
        price_stop, price_audit = e, e.audit
        bars, fundings, kline_daily = [], [], []
    oi, oi_audit, oi_stops = analyze_oi(raw / "oi", start, end)
    audit = {"price": price_audit, "oi": oi_audit, "window": "IS+warmup · window B(#47) · 2023-10-02 → 2025-12-31"}
    if price_stop is not None or oi_stops:
        raise _StopWithAudit((price_stop.findings if price_stop else []) + oi_stops, audit)
    assert_in_range([b.open_ms for b in bars], start, end)
    assert_in_range([f.funding_ms for f in fundings], start, end)
    assert_in_range([k["minute_ms"] for k in kline_daily], start, end)
    assert_in_range([t for t, _ in oi], start, end)
    return bars, fundings, audit, kline_daily, oi


class _StopWithAudit(SourceStop):
    def __init__(self, findings: list[dict[str, Any]], audit: dict[str, Any]):
        super().__init__(findings)
        self.audit = audit


# ── 3 쓰기·매니페스트 ────────────────────────────────────────────────────────
def raw_files(raw: Path) -> list[str]:
    return list(PRICE_RAW) + sorted(f"oi/{p.name}" for p in (raw / "oi").iterdir())


def build(out: Path, expect_range: tuple[int, int]) -> dict[str, Any]:
    raw = out / "raw"
    try:
        bars, fundings, audit, kline_daily, oi = analyze(raw, expect_range)
    except _StopWithAudit as e:
        (out / "source_audit.json").write_text(json.dumps(e.audit, sort_keys=True, indent=1))
        raise
    (out / "source_audit.json").write_text(json.dumps(audit, sort_keys=True, indent=1))
    T2.write_bars(out / "bars_1m.parquet", bars)
    (out / "funding.json").write_text(json.dumps([f.__dict__ for f in fundings], sort_keys=True))
    (out / "kline_close_daily.json").write_text(json.dumps(kline_daily, sort_keys=True))
    (out / "oi_5m.json").write_text(json.dumps(oi))
    (out / "oi_unusable.json").write_text(json.dumps(audit["oi"]["unusable_slots"]))
    manifest = {"raw": {n: T2._sha(raw / n) for n in raw_files(raw)}, **{n: T2._sha(out / n) for n in PREPARED},
                "code_commit": T2._commit(), "window": "IS+warmup(2023-10-02) · window B"}
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=1))
    return manifest


def verify_manifest(out: Path) -> dict[str, Any]:
    m = json.loads((out / "manifest.json").read_text())
    bad = [n for n in PREPARED if T2._sha(out / n) != m[n]]
    bad += [f"raw/{n}" for n in m["raw"] if T2._sha(out / "raw" / n) != m["raw"][n]]
    if sorted(m["raw"]) != sorted(raw_files(out / "raw")):
        bad.append("raw/<inventory>")
    if bad:
        raise ValueError(f"매니페스트 불일치: {bad}")
    return m


def verify_rebuild(out: Path, expect_range: tuple[int, int]) -> dict[str, Any]:
    """원시에서 **다시 빌드**해 산출물 해시가 매니페스트와 같은지(덮어쓰지 않는다 · 임시 디렉터리)."""
    m = verify_manifest(out)
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        shutil.copytree(out / "raw", t / "raw")
        m2 = build(t, expect_range)
    bad = [n for n in PREPARED if m2[n] != m[n]]
    if bad:
        raise ValueError(f"원시에서 다시 빌드한 산출물이 다르다: {bad}")
    return m


def check_out_dir(out: Path, root: Path = ROOT) -> None:
    """산출물은 `<root>/var/t3/` 아래만 — 트라이얼 #3 S0(`var/t3_s0`)·트라이얼 #2(`var/backtest`)는 입력이 아니다."""
    o, base = out.resolve(), (root / "var" / "t3").resolve()
    if base != o and base not in o.parents:
        raise OOSGuard(f"{out}는 {base} 아래가 아니다")


def load_prepared_pinned(out: Path, pins: dict[str, Any], expect_range: tuple[int, int], *, root: Path = ROOT
                         ) -> tuple[list[BD.Bar1m], list[BD.Funding], list[list[Any]], list[int]]:
    """실행 경로(해시만 · 다시 빌드하지 않음): 디렉터리 · 매니페스트 · 고정값(data_pins) · 범위 · 타임스탬프를 모두 단언."""
    check_out_dir(out, root)
    start, end = expect_range
    check_is_bounds(start, end)
    m = verify_manifest(out)
    if m["raw"] != pins["raw"] or {k: m[k] for k in PREPARED} != pins["prepared"]:
        raise ValueError("준비 산출물·원시 해시가 고정값(data_pins)과 다르다")
    meta = json.loads((out / "raw" / "fill_ranges.json").read_text())
    if (meta["start_ms"], meta["end_ms"]) != expect_range:
        raise ValueError(f"캡처 범위 {(meta['start_ms'], meta['end_ms'])} ≠ 기대 {expect_range}")
    bars = T2.read_bars(out / "bars_1m.parquet")
    fundings = [BD.Funding(**f) for f in json.loads((out / "funding.json").read_text())]
    oi = json.loads((out / "oi_5m.json").read_text())
    unusable = json.loads((out / "oi_unusable.json").read_text())
    assert_in_range(unusable, start, end)
    assert_in_range([b.open_ms for b in bars], start, end)
    assert_in_range([f.funding_ms for f in fundings], start, end)
    assert_in_range([t for t, _ in oi], start, end)
    return bars, fundings, oi, unusable


# ── OOS 진입점(정의만 · 사용자 결정 전 거부) ─────────────────────────────────
def oos_range(registry: Path, row_id: int) -> tuple[int, int]:
    """레지스트리 행 `row_id`가 "트라이얼 #3 OOS 개봉"과 "사용자 결정"을 담고 있어야 한다. 범위 = OOS 앞 91일(분위수 90일 +
    r30 워밍업 · 거래 없음) ~ OOS_END."""
    pat = re.compile(rf"^\| {row_id} \| (\d{{4}}-\d{{2}}-\d{{2}}) \|")
    for line in registry.read_text(encoding="utf-8").splitlines():
        if pat.match(line) and "트라이얼 #3 OOS 개봉" in line and "사용자 결정" in line:
            return A.OOS_START_MS - 91 * A.DAY_MS, A.OOS_END_MS
    raise OOSGuard(f"레지스트리 행 #{row_id}에 트라이얼 #3 OOS 개봉 사용자 결정이 없다 — OOS는 닫혀 있다")


# ── CLI ─────────────────────────────────────────────────────────────────────
EVALUATOR_FILE = "backtest/evaluate_t3.py"


def evaluator_pushed(commit: str | None) -> bool:
    """판정기 커밋 H가 origin/main의 조상이고 H에 트라이얼 #3 판정기 파일이 있어야 한다(§4-1 3 → 4)."""
    if not commit or not re.fullmatch(r"[0-9a-f]{40}", commit):
        return False

    def git(*a: str) -> int:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True).returncode

    return git("merge-base", "--is-ancestor", commit, "origin/main") == 0 and git("cat-file", "-e", f"{commit}:{EVALUATOR_FILE}") == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="트라이얼 #3 IS 데이터 준비(원시 캡처 → 감사 → 빌드) · 창 (B)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true", help="캡처·덮어쓰기 없이 raw/에서 다시 빌드해 대조")
    ap.add_argument("--evaluator-commit", help="origin/main에 푸시된 판정기 커밋 H(캡처 전 필수)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    rng = is_range()
    if a.verify:
        check_out_dir(out)
        m = verify_rebuild(out, rng)
        print(json.dumps({"verified": True} | m, sort_keys=True, indent=1))
        return 0
    if not evaluator_pushed(a.evaluator_commit):
        print("🚫 판정기가 origin/main에 푸시되기 전에는 실데이터를 캡처하지 않는다(§4-1 · 계획 r5 S1)", file=sys.stderr)
        return 6
    check_out_dir(out)
    if (out / "manifest.json").exists():
        print("🚫 이미 준비된 출력이 있다 — 다시 캡처하지 않는다(--verify로 대조만)", file=sys.stderr)
        return 5
    from exchange.ccxt_rest import CcxtRestClient
    from exchange.client import ReadOnlyClient
    capture(out / "raw", ReadOnlyClient(CcxtRestClient()), BD.ARCHIVE_DIR, fetch_oi_http, *rng)
    try:
        m = build(out, rng)
    except SourceStop as e:
        print(f"🚫 {e}", file=sys.stderr)
        return 3
    print(json.dumps(m, sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
