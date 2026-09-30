"""트라이얼 #4 두 번째 보정(사용자 2026-09-30 · r1 철회 뒤) — **IS 이전 자료만**(2022-01-01 → 2023-12-31 · 워밍업 2021-10부터).
트라이얼 코드가 아니다(backtest/·strategies/ 밖 · 테스트 없음 · 트라이얼 모듈이 import하지 않는다).

    uv run python docs/trials/trial_04_calibration/calibrate_r2.py --listing    # A: binance.vision 목록(파일 이름만 · 2024+ 내용 미개봉)
    uv run python docs/trials/trial_04_calibration/calibrate_r2.py --fetch      # A: 2021-10 … 2023-12 1m premiumIndexKlines zip + CHECKSUM
    uv run python docs/trials/trial_04_calibration/calibrate_r2.py              # A·B 표 계산

A. 프리미엄 지수: 펀딩 = P + clamp(I − P, −0.05%, +0.05%)(I = 0.01%/8h) 이므로 P(8시간 평균 프리미엄)가 클램프 없는 쏠림 척도다.
   P_b = 경계 b 직전 8시간 [b − 8h, b)의 1m 프리미엄 지수 **종가 평균**(바이낸스는 5초 표본 평균 — 1m 종가 평균은 근사 · 공시).
B. 고정 보유(3·5·10일 · 2022~2023의 매 00:00 UTC 진입 · mark)의 불리 이동 분포와 B2 L(#4 식 · v1.5 [3, 30]).
가드: 내려받는 zip은 2021-10 … 2023-12만 · 행 시각 ≤ PRE_IS_END 단언 · 1m 아카이브는 2021·2022·2023 파일만(2024 파일 미개봉).
원시 zip은 var/t4_calib/(git 밖 · 크기) · 파일별 SHA256·CHECKSUM 대조는 premium_fetch.json에 커밋.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import statistics
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
VAR = ROOT / "var" / "t4_calib" / "premium_1m"
UTC = dt.UTC
PRE_IS_END = int(dt.datetime(2023, 12, 31, 23, 59, 59, 999000, tzinfo=UTC).timestamp() * 1000)
CAL_START = int(dt.datetime(2022, 1, 1, tzinfo=UTC).timestamp() * 1000)
DAY, H8, MIN = 86_400_000, 8 * 3_600_000, 60_000
BASE = "https://data.binance.vision/"
LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix="
PREFIX = "data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/"
MONTHS = [f"{y}-{m:02d}" for y in (2021, 2022, 2023) for m in range(1, 13) if (y, m) >= (2021, 10)]
ARCHIVE = Path("/home/cms/project/data/BTCUSDT/1m")
ARCHIVE_FILES = ("BTCUSDT_1m_2021.csv", "BTCUSDT_1m_2022.csv", "BTCUSDT_1m_2023.csv")
TAKER, MMR = 0.0005, 0.004                                                 # #48 tier1 (헌법 v1.5 §1 예시와 같음)


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def listing() -> None:
    """파일 이름만(2024+ 내용은 열지 않는다)."""
    keys: list[str] = []
    marker = ""
    while True:
        t = _get(LIST + PREFIX + (f"&marker={marker}" if marker else "")).decode()
        ks = re.findall(r"<Key>([^<]*)</Key>", t)
        keys += ks
        if "<IsTruncated>true</IsTruncated>" not in t or not ks:
            break
        marker = ks[-1]
    zips = sorted(k.rsplit("/", 1)[1] for k in keys if k.endswith(".zip"))
    chk = {k.rsplit("/", 1)[1][:-9] for k in keys if k.endswith(".CHECKSUM")}
    avail = {}
    for y in (2022, 2023, 2024, 2025):
        want = [f"BTCUSDT-1m-{y}-{m:02d}.zip" for m in range(1, 13)]
        avail[str(y)] = {"months_present": sum(w in zips for w in want), "with_checksum": sum(w in chk for w in want),
                         "missing": [w for w in want if w not in zips]}
    out = {"listed_utc": dt.datetime.now(UTC).isoformat(timespec="seconds"), "prefix": PREFIX, "zip_files": len(zips),
           "first": zips[0], "last": zips[-1], "availability": avail,
           "note": "2024~2025는 목록(이름)만 확인 · 내용 미개봉"}
    (HERE / "premium_listing.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


def fetch() -> None:
    VAR.mkdir(parents=True, exist_ok=True)
    rec = []
    for mo in MONTHS:
        name = f"BTCUSDT-1m-{mo}.zip"
        data = _get(BASE + PREFIX + name)
        chk = _get(BASE + PREFIX + name + ".CHECKSUM").decode().split()[0]
        sha = hashlib.sha256(data).hexdigest()
        assert sha == chk, f"CHECKSUM 불일치 {name}"
        (VAR / name).write_bytes(data)
        rec.append({"file": name, "sha256": sha, "bytes": len(data)})
    meta = {"fetched_utc": dt.datetime.now(UTC).isoformat(timespec="seconds"), "files": rec,
            "inventory_sha256": hashlib.sha256("".join(f"{r['file']}={r['sha256']}\n" for r in rec).encode()).hexdigest()}
    (HERE / "premium_fetch.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps({k: v for k, v in meta.items() if k != "files"} | {"n": len(rec)}))


def premium_minutes() -> dict[int, float]:
    out: dict[int, float] = {}
    meta = json.loads((HERE / "premium_fetch.json").read_text())
    for r in meta["files"]:
        data = (VAR / r["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == r["sha256"]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            [csvname] = z.namelist()
            for row in csv.reader(io.TextIOWrapper(z.open(csvname))):
                if not row or not row[0].isdigit():
                    continue                                              # 머리글
                t = int(row[0])
                assert t <= PRE_IS_END, "IS 행"
                out[t] = float(row[4])                                    # close
    return out


def table_a() -> dict:
    pm = premium_minutes()
    first_b = min(pm) - min(pm) % H8 + H8
    rows = []                                                             # (b, P_b, 분 수)
    for b in range(first_b, PRE_IS_END + 1, H8):
        xs = [pm[t] for t in range(b - H8, b, MIN) if t in pm]
        if len(xs) >= 0.99 * 480:
            rows.append((b, statistics.fmean(xs), len(xs)))
    ts = [b for b, _, _ in rows]
    ps = [p for _, p, _ in rows]
    res: dict[str, object] = {"prints": len(rows), "first": ts[0], "last": ts[-1],
                              "min_coverage_minutes": min(n for _, _, n in rows),
                              "definition": "P_b = [b−8h, b) 1m 프리미엄 지수 종가 평균(분 ≥ 99% · 475/480) · 펀딩 공식의 P 근사"}
    cal = np.asarray([p for b, p in zip(ts, ps, strict=True) if b >= CAL_START])
    res["distribution_pct_of_P"] = {str(q): round(float(np.quantile(cal, q / 100)) * 100, 5) for q in (1, 5, 25, 50, 75, 95, 99)}
    res["share_clamped_zone"] = {"|I−P| ≤ 0.05% ⇒ funding = 0.01%": round(float(np.mean(np.abs(0.0001 - cal) <= 0.0005)), 4)}
    per: dict[str, dict[str, int]] = defaultdict(lambda: {"prints": 0, "gt_Q95": 0, "lt_Q05": 0})
    qhi, qlo = [], []
    for i, (b, p) in enumerate(zip(ts, ps, strict=True)):
        if b < CAL_START or i < 270:
            continue
        w = np.asarray(ps[i - 270:i])                                     # 엄격히 앞선 270개
        lo, hi = float(np.quantile(w, 0.05)), float(np.quantile(w, 0.95))
        qhi.append(hi)
        qlo.append(lo)
        y = str(dt.datetime.fromtimestamp(b / 1000, UTC).year)
        per[y]["prints"] += 1
        per[y]["gt_Q95"] += p > hi
        per[y]["lt_Q05"] += p < lo
    res["beyond_trailing_90d"] = dict(per)
    res["trailing_Q95_pct"] = {"min": round(min(qhi) * 100, 5), "median": round(float(np.median(qhi)) * 100, 5), "max": round(max(qhi) * 100, 5),
                               "distinct_values": len(set(qhi))}
    res["trailing_Q05_pct"] = {"min": round(min(qlo) * 100, 5), "median": round(float(np.median(qlo)) * 100, 5), "max": round(max(qlo) * 100, 5),
                               "distinct_values": len(set(qlo))}
    return res


def daily_mark() -> dict[int, list[float]]:
    day: dict[int, list[float]] = {}
    for name in ARCHIVE_FILES:
        with (ARCHIVE / name).open() as fh:
            for r in csv.DictReader(fh):
                t = int(dt.datetime.fromisoformat(r["timestamp"]).replace(tzinfo=UTC).timestamp() * 1000)
                assert t <= PRE_IS_END, "IS 행"
                if not (r["mark_open"] and r["mark_high"] and r["mark_low"] and r["mark_close"]):
                    continue
                d = t // DAY
                o, h, lo, c = (float(r[k]) for k in ("mark_open", "mark_high", "mark_low", "mark_close"))
                if d not in day:
                    day[d] = [o, h, lo, c, t, t, 1]
                else:
                    x = day[d]
                    x[1], x[2] = max(x[1], h), min(x[2], lo)
                    if t < x[4]:
                        x[0], x[4] = o, t
                    if t >= x[5]:
                        x[3], x[5] = c, t
                    x[6] += 1
    last_full = PRE_IS_END // DAY - 1                                     # 2023-12-31은 2024 파일에 걸침 → 제외
    return {d: v for d, v in day.items() if d <= last_full and v[6] == 1440}


def atr_pct(day: dict[int, list[float]]) -> dict[int, float]:
    """ATR_1d(14) 단순 평균 · 결정일 d의 값 = d−14 … d−1의 TR(전날까지 완전한 날) / d−1 종가."""
    tr = {d: max(v[1] - v[2], abs(v[1] - day[d - 1][3]), abs(v[2] - day[d - 1][3])) for d, v in day.items() if d - 1 in day}
    out = {}
    for d in sorted(day):
        ks = [d - k for k in range(1, 15)]
        if all(k in tr for k in ks) and d - 1 in day:
            out[d] = statistics.fmean(tr[k] for k in ks) / day[d - 1][3]
    return out


def liq(lev: int, long: bool) -> float:
    return (1 / lev - TAKER - MMR) / ((1 - MMR) if long else (1 + MMR))


def b2_lev(sl: float, long: bool) -> int | None:
    ok = [lev for lev in range(3, 31) if sl * 1.5 < liq(lev, long) and liq(lev, long) - sl >= 0.001]
    return max(ok) if ok else None


def table_b() -> dict:
    day = daily_mark()
    atr = atr_pct(day)
    days = sorted(d for d in day if d * DAY >= CAL_START)
    xs = (4, 6, 8, 10, 12)
    res: dict[str, object] = {"days_complete_2022_2023": len(days)}
    holds = {}
    for H in (3, 5, 10):
        n = 0
        cnt = {"long": dict.fromkeys(xs, 0), "short": dict.fromkeys(xs, 0)}
        for d in days:
            span = [d + k for k in range(H)]
            if not all(k in day for k in span):
                continue
            n += 1
            entry = day[d][0]
            lo, hi = min(day[k][2] for k in span), max(day[k][1] for k in span)
            for x in xs:
                cnt["long"][x] += (entry - lo) / entry > x / 100
                cnt["short"][x] += (hi - entry) / entry > x / 100
        holds[f"{H}d"] = {"holds": n, **{side: {f">{x}%": round(c[x] / n, 4) for x in xs} for side, c in cnt.items()}}
    res["adverse_excursion_share"] = holds
    res["adverse_definition"] = "진입 = 날 d 00:00 mark 시가 · 보유 = 날 d … d+H−1 완전한 날 · 롱 불리 = (진입 − 최저 mark)/진입 · 숏 = (최고 − 진입)/진입"
    lev = {}
    for k in (1.5, 2.0, 2.5):
        bins = {"long": defaultdict(int), "short": defaultdict(int)}
        m = 0
        for d in days:
            if d not in atr:
                continue
            m += 1
            sl = k * atr[d]
            for side, is_long in (("long", True), ("short", False)):
                L = b2_lev(sl, is_long)
                key = "none" if L is None else "3–4" if L < 5 else "5–7" if L < 8 else "8–9" if L < 10 else "≥10"
                bins[side][key] += 1
        lev[f"k={k}"] = {"days": m, **{s: {b: round(bins[s][b] / m, 4) for b in ("3–4", "5–7", "8–9", "≥10", "none")} for s in bins}}
    res["b2_leverage_share"] = lev
    res["b2_definition"] = ("sl_dist = k × ATR_1d(14)/전날 종가 · L = [3, 30] 중 1.5·sl < liq(L) ∧ liq(L) − sl ≥ 10bp를 통과하는 최댓값 · "
                            "liq = (1/L − taker − MMR)/(1 ∓ MMR) · 구간 3–4 = {3,4} · 5–7 = {5,6,7} · 8–9 = {8,9} · ≥10")
    res["atr_pct_median"] = round(float(np.median([atr[d] for d in days if d in atr])) * 100, 3)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listing", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    if a.listing:
        listing()
        return 0
    if a.fetch:
        fetch()
        return 0
    res = {"A_premium": table_a(), "B_hold_vs_leverage": table_b()}
    (HERE / "calibration_r2.json").write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
