"""트라이얼 #4 데이터 준비(단계 (a) · 계획 r3 C2~C4·C12~C14 · 사전등록 r3 §1·§5) — **원시 캡처 하나 → 감사 → 빌드 → 매니페스트**.

가격·펀딩은 공유 계층 `prepare_t2`를 import한다(수정하지 않는다). 트라이얼 #3 전용 도우미 둘(`read_archive_rows_bounded` · `funding_view`)은
**import하지 않고 복사**했다(출처: backtest/prepare_t3.py @ 177e7f7 · 바꾼 것: 앵커 import를 trial04로 · 감사 표지를 "trial #4 convention"으로 ·
`funding_view`의 보고 전용 필드 둘(shared_bucket · rate_not_ok) 제거 — 버림 규칙 자체는 같다).
새 원천(r3 §1 · 결정 9):
- **프리미엄 지수**: binance.vision `futures/um/monthly/premiumIndexKlines/BTCUSDT/1m` 월별 zip + CHECKSUM(원시 바이트와 해시를 캡처 시점에 고정 ·
  L12) · 범위의 달만 받는다(IS 경로 = 2023-10 … 2025-12 · 2026 달은 요청하지 않는다).
- **데이터 계약**: CSV 12열(`PREMIUM_HEADER`) · 머리 행은 선택(정확히 같을 때만 허용 · 다른 비수치 첫 칸 → 중단) · open_time 정수 ms · 60,000 배수 ·
  close_time = open_time + 59,999 · 범위 밖 행은 **값을 분류하기 전에** 버린다 · 같은 open_time이 두 번(파일·값 무관) → **데이터 품질 중단** ·
  close가 유한 Decimal이 아니면 그 분은 **없음**(475/480 계산에서 빠짐 · 달·분별 감사) · CHECKSUM 불일치 · 달 파일 없음 · zip 안 CSV ≠ 1개 → 중단.
- **인쇄 p_T**: 경계 T(00/08/16 UTC) · 분 = open_time ∈ [T − 8h, T − 1분](480개 · 종료가 (T − 8h, T]) · **유효 ⇔ ≥ 475분** · p_T = 쓸 수 있는 분의
  close **Decimal 합 ÷ 개수**(지역 `Context(prec=28, ROUND_HALF_EVEN)` · 문자열) — 이진 float 없음 · **T − 8h ≥ 시작 ∧ T ≤ IS 끝**만 내보낸다(IS 경로의
  마지막 인쇄 = 2025-12-31 16:00 · 2026-01-01 00:00 인쇄 없음) · 마지막 분(T − 1분)이 없으면 인쇄는 유효할 수 있어도 **결정 없음**(`final_minute_present`
  = false · 결정 규칙은 (d)).
- **펀딩 워밍업 빈 mark**: markPrice == "" ∧ fundingTime 정수 ∧ fundingTime < WINDOW_START인 행만 버린다(트라이얼 #4 구현 규약 · 트라이얼 #3 #54와 같은
  규칙의 복사) — 창 안 빈 mark는 여전히 중단.
🔒 OOS 가드: 범위는 [DATA_START, IS_END] 안 · 산출물은 `var/t4/` 아래만 · 모든 타임스탬프를 적재 때 다시 단언.
"""
from __future__ import annotations

import csv
import datetime as dt
import decimal
import hashlib
import io
import json
import re
import tempfile
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtest import data as BD
from backtest import prepare_t2 as T2
from strategies.trial04 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
MIN = BD.MINUTE_MS
PRICE_RAW = T2.RAW_FILES
PREMIUM_URL = "https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-{month}.zip"
PREMIUM_HEADER = ("open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
                  "taker_buy_volume", "taker_buy_quote_volume", "ignore")
PRINT_MINUTES = 480
PRINT_VALID_MIN = 475                                      # r3 결정 9
PREPARED = ("bars_1m.parquet", "funding.json", "source_audit.json", "kline_close_daily.json", "premium_prints.json")
DROP_KEY = "funding_warmup_empty_mark_dropped"
P_CONTEXT = decimal.Context(prec=28, rounding=decimal.ROUND_HALF_EVEN)
SourceStop = T2.SourceStop
PremiumFetch = Callable[[str], tuple[bytes, str]]


class OOSGuard(RuntimeError):
    """IS 경로가 IS 범위 밖(OOS 포함) 시각·경로를 만졌다."""


def is_range() -> tuple[int, int]:
    return A.DATA_START_MS, A.IS_END_MS


def check_is_bounds(start_ms: int, end_ms: int) -> None:
    if not (A.DATA_START_MS <= start_ms <= end_ms <= A.IS_END_MS):
        raise OOSGuard(f"범위 [{start_ms}, {end_ms}]가 IS 경로 한계 [{A.DATA_START_MS}, {A.IS_END_MS}] 밖")


def assert_in_range(ts: Iterable[int], start_ms: int, end_ms: int) -> None:
    bad = [t for t in ts if not start_ms <= t <= end_ms]
    if bad:
        raise OOSGuard(f"범위 밖 타임스탬프 {len(bad)}개(첫 {bad[0]})")


def months(start_ms: int, end_ms: int) -> list[str]:
    """범위가 걸친 달(YYYY-MM) — 범위 밖 달은 없다."""
    s = dt.datetime.fromtimestamp(start_ms / 1000, dt.UTC)
    e = dt.datetime.fromtimestamp(end_ms / 1000, dt.UTC)
    out, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# ── 1 캡처 ──────────────────────────────────────────────────────────────────
def read_archive_rows_bounded(archive: Path, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    """(복사 · prepare_t3 @ 177e7f7) 아카이브 행(문자열 그대로) — 타임스탬프만 먼저 읽고 시작 전 행은 건너뛰며 **끝 뒤 첫 행에서 그 파일을
    멈춘다**(끝 뒤 값 미파싱). 해석 불가 타임스탬프 행은 범위 안 위치에 있을 때만 남는다."""
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


def fetch_premium_http(month: str) -> tuple[bytes, str]:  # pragma: no cover — 네트워크(실행 경로만)
    import urllib.request
    url = PREMIUM_URL.format(month=month)
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    with urllib.request.urlopen(url + ".CHECKSUM", timeout=60) as r:
        chk = r.read().decode("utf-8")
    return data, chk


def capture(raw: Path, client: Any, archive: Path, fetch_premium: PremiumFetch, start_ms: int, end_ms: int) -> None:
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
    pdir = raw / "premium"
    pdir.mkdir(exist_ok=True)
    for mo in months(start_ms, end_ms):
        data, chk = fetch_premium(mo)
        (pdir / f"BTCUSDT-1m-{mo}.zip").write_bytes(data)
        (pdir / f"BTCUSDT-1m-{mo}.zip.CHECKSUM").write_text(chk)


# ── 2 분석(순수) ────────────────────────────────────────────────────────────
def _finite_decimal(s: str) -> Decimal | None:
    try:
        d = Decimal(s.strip())
    except (decimal.InvalidOperation, ValueError, AttributeError):
        return None
    return d if d.is_finite() else None


def analyze_premium(pdir: Path, start_ms: int, end_ms: int
                    ) -> tuple[dict[int, Decimal | None], dict[str, Any], list[dict[str, Any]]]:
    """반환 (open_time → close(Decimal) 또는 None(없음), 감사, 중단 목록). 중단이 있어도 감사는 채운다."""
    stops: list[dict[str, Any]] = []
    minutes: dict[int, Decimal | None] = {}
    absent_by_month: dict[str, int] = defaultdict(int)
    rows_in_range = 0
    files: dict[str, str] = {}
    for mo in months(start_ms, end_ms):
        zp = pdir / f"BTCUSDT-1m-{mo}.zip"
        cp = pdir / f"BTCUSDT-1m-{mo}.zip.CHECKSUM"
        if not zp.exists() or not cp.exists():
            stops.append({"kind": "premium_month_missing", "month": mo, "stop": True})
            continue
        data = zp.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        files[zp.name] = sha
        want = cp.read_text().split()[0] if cp.read_text().split() else ""
        if sha != want:
            stops.append({"kind": "premium_checksum_mismatch", "month": mo, "stop": True})
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if len(names) != 1:
                    stops.append({"kind": "premium_zip_members", "month": mo, "n": len(names), "stop": True})
                    continue
                text = z.read(names[0]).decode("utf-8")
        except (zipfile.BadZipFile, ValueError, UnicodeDecodeError, EOFError):
            stops.append({"kind": "premium_zip_unreadable", "month": mo, "stop": True})
            continue
        for i, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            f = next(csv.reader([line]))
            if i == 0 and not re.fullmatch(r"-?\d+", f[0].strip()):
                if tuple(x.strip() for x in f) != PREMIUM_HEADER:
                    stops.append({"kind": "premium_bad_header", "month": mo, "stop": True})
                    break
                continue
            if len(f) != len(PREMIUM_HEADER) or not re.fullmatch(r"\d+", f[0].strip()):
                stops.append({"kind": "premium_bad_row", "month": mo, "line": i, "stop": True})
                break
            t = int(f[0])
            if t < start_ms or t > end_ms:
                continue                                           # 범위 밖 — 값을 분류하기 전에 버린다
            if t in minutes:
                stops.append({"kind": "premium_duplicate_minute", "open_time": t, "stop": True})
                continue
            if t % MIN or not re.fullmatch(r"\d+", f[6].strip()) or int(f[6]) != t + MIN - 1:
                stops.append({"kind": "premium_time_defect", "open_time": t, "stop": True})
                minutes[t] = None
                continue
            rows_in_range += 1
            c = _finite_decimal(f[4])
            minutes[t] = c
            if c is None:
                absent_by_month[mo] += 1
    audit = {"months": months(start_ms, end_ms), "files_sha256": files, "rows_in_range": rows_in_range,
             "minutes_with_value": sum(v is not None for v in minutes.values()),
             "non_finite_close_by_month": dict(absent_by_month), "stops": stops}
    return minutes, audit, stops


def build_prints(minutes: dict[int, Decimal | None], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    """경계 T마다 한 행: {T, p(문자열 또는 None), n_minutes, valid, final_minute_present}. T − 8h ≥ 시작 ∧ T ≤ 끝만."""
    out = []
    first = start_ms + A.H8_MS
    first += (-first) % A.H8_MS                                    # 다음 00/08/16 UTC 경계(8h 격자는 epoch 기준)
    for T in range(first, end_ms + 1, A.H8_MS):
        vals = [minutes.get(t) for t in range(T - A.H8_MS, T, MIN)]
        use = [v for v in vals if v is not None]
        n = len(use)
        p = None
        if n:
            with decimal.localcontext(P_CONTEXT):                  # 합과 나눗셈 모두 지역 문맥(주변 정밀도 무관)
                p = str(sum(use, Decimal(0)) / Decimal(n))
        out.append({"T": T, "p": p, "n_minutes": n, "valid": n >= PRINT_VALID_MIN,
                    "final_minute_present": minutes.get(T - MIN) is not None})
    return out


def funding_view(raw: Path) -> tuple[bytes, dict[str, Any]]:
    """(복사 · prepare_t3 @ 177e7f7 · 앵커 = trial04) 트라이얼 #4 구현 규약: 원시 펀딩 행은 markPrice == "" ∧ fundingTime 정수 ∧
    fundingTime < WINDOW_START **일 때만** 버린다. 나머지(창 안 빈 mark 포함)는 T2 규칙대로(창 안 빈 mark → 중단). 원시 파일은 그대로."""
    data = (raw / "funding.jsonl").read_bytes()
    lines = [ln for ln in data.split(b"\n") if ln.strip()]
    recs = [json.loads(ln) for ln in lines]
    dropped: list[int] = []
    pages: list[dict[str, Any]] = []
    out: list[str] = []
    for i, (ln, rec) in enumerate(zip(lines, recs, strict=True)):
        keep, k = [], 0
        for r in rec["page"]:
            ft = r.get("fundingTime")
            if r.get("markPrice") == "" and T2._int_ok(ft) and int(ft) < A.WINDOW_START_MS:
                dropped.append(int(ft))
                k += 1
            else:
                keep.append(r)
        if k:
            pages.append({"line": i, "line_sha256": hashlib.sha256(ln).hexdigest(), "dropped": k})
        out.append(json.dumps(rec | {"page": keep}) + "\n")
    audit = {"rule": "trial #4 convention (copy of registry #54 rule)", "count": len(dropped),
             "first_ms": min(dropped) if dropped else None, "last_ms": max(dropped) if dropped else None,
             "funding_ms": sorted(dropped), "raw_file_sha256": hashlib.sha256(data).hexdigest(), "pages": pages}
    return "".join(out).encode(), audit


def _t2_analyze_view(raw: Path, expect_range: tuple[int, int], view: bytes) -> tuple[Any, ...]:
    with tempfile.TemporaryDirectory(prefix="t4_funding_view_") as td:
        v = Path(td)
        for n in PRICE_RAW:
            if n != "funding.jsonl":
                (v / n).symlink_to((raw / n).resolve())
        (v / "funding.jsonl").write_bytes(view)
        return T2.analyze(v, expect_range)


class _StopWithAudit(SourceStop):
    def __init__(self, findings: list[dict[str, Any]], audit: dict[str, Any]):
        super().__init__(findings)
        self.audit = audit


def analyze(raw: Path, expect_range: tuple[int, int]) -> tuple[list[BD.Bar1m], list[BD.Funding], dict[str, Any],
                                                             list[dict[str, Any]], list[dict[str, Any]]]:
    start, end = expect_range
    check_is_bounds(start, end)
    price_stop: SourceStop | None = None
    view, drop_audit = funding_view(raw)
    try:
        bars, fundings, price_audit, kline_daily = _t2_analyze_view(raw, expect_range, view)
    except T2._StopWithAudit as e:
        price_stop, price_audit = e, e.audit
        bars, fundings, kline_daily = [], [], []
    price_audit[DROP_KEY] = drop_audit
    minutes, prem_audit, prem_stops = analyze_premium(raw / "premium", start, end)
    prints = build_prints(minutes, start, end) if not prem_stops else []
    prem_audit |= {"prints": len(prints), "prints_invalid": sum(not p["valid"] for p in prints),
                   "prints_valid_final_minute_missing": sum(p["valid"] and not p["final_minute_present"] for p in prints)}
    audit = {"price": price_audit, "premium": prem_audit, "window": "IS+warmup · 2023-10-02 → 2025-12-31 · trial #4"}
    if price_stop is not None or prem_stops:
        raise _StopWithAudit((price_stop.findings if price_stop else []) + prem_stops, audit)
    assert_in_range([b.open_ms for b in bars], start, end)
    assert_in_range([f.funding_ms for f in fundings], start, end)
    assert_in_range([k["minute_ms"] for k in kline_daily], start, end)
    assert_in_range([p["T"] for p in prints], start, end)
    return bars, fundings, audit, kline_daily, prints


# ── 3 쓰기·매니페스트 ────────────────────────────────────────────────────────
def raw_files(raw: Path) -> list[str]:
    return list(PRICE_RAW) + sorted(f"premium/{p.name}" for p in (raw / "premium").iterdir())


def build(out: Path, expect_range: tuple[int, int]) -> dict[str, Any]:
    raw = out / "raw"
    try:
        bars, fundings, audit, kline_daily, prints = analyze(raw, expect_range)
    except _StopWithAudit as e:
        (out / "source_audit.json").write_text(json.dumps(e.audit, sort_keys=True, indent=1))
        raise
    (out / "source_audit.json").write_text(json.dumps(audit, sort_keys=True, indent=1))
    T2.write_bars(out / "bars_1m.parquet", bars)
    (out / "funding.json").write_text(json.dumps([f.__dict__ for f in fundings], sort_keys=True))
    (out / "kline_close_daily.json").write_text(json.dumps(kline_daily, sort_keys=True))
    (out / "premium_prints.json").write_text(json.dumps(prints, sort_keys=True))
    manifest = {"raw": {n: T2._sha(raw / n) for n in raw_files(raw)}, **{n: T2._sha(out / n) for n in PREPARED},
                "code_commit": T2._commit(), "window": "IS+warmup(2023-10-02) · trial #4"}
    if audit["price"][DROP_KEY]["raw_file_sha256"] != manifest["raw"]["funding.jsonl"]:
        raise ValueError("버린 펀딩 행 감사의 원시 해시가 매니페스트와 다르다")
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
    import shutil
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
    """산출물은 `<root>/var/t4/` 아래만 — 보정 디렉터리(`var/t4_calib`)·다른 트라이얼 디렉터리는 입력이 아니다."""
    o, base = out.resolve(), (root / "var" / "t4").resolve()
    if base != o and base not in o.parents:
        raise OOSGuard(f"{out}는 {base} 아래가 아니다")


def oos_range(registry: Path, row_id: int) -> tuple[int, int]:
    """OOS 진입점(정의만) — 레지스트리 행 `row_id`에 "트라이얼 #4 OOS 개봉"과 "사용자 결정"이 있어야 범위를 돌려준다."""
    pat = re.compile(rf"^\| {row_id} \| (\d{{4}}-\d{{2}}-\d{{2}}) \|")
    for line in registry.read_text(encoding="utf-8").splitlines():
        if pat.match(line) and "트라이얼 #4 OOS 개봉" in line and "사용자 결정" in line:
            return A.OOS_START_MS - 91 * A.DAY_MS, A.OOS_END_MS
    raise OOSGuard(f"레지스트리 행 #{row_id}에 트라이얼 #4 OOS 개봉 사용자 결정이 없다 — OOS는 닫혀 있다")
