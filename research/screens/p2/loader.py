"""S-xs-carry-1 로더(스펙 r6 §1 · §3) — 창 가드 읽기만. 펀딩 · 일봉 zip은 `bounded_zip_csv`, DTB3는 `bounded_benchmark_csv`."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from research.screens.window import (
    ReserveError,
    assert_within,
    bounded_benchmark_csv,
    bounded_csv_file,
    bounded_zip_csv,
    refuse_reserved_archive,
    zip_has_header,
)

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "var" / "p2_archive" / "data" / "futures" / "um" / "monthly"
DTB3 = Path(__file__).resolve().parent / "data" / "DTB3_2020-12-01_2026-06-30.csv"
HEADER_TS = frozenset({"calc_time", "fundingTime", "funding_time", "open_time"})   # 알려진 머리줄의 시각 칸 이름
ASCII_USDT = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


@dataclass
class Series:
    """시각(ms · 오름차순 · 중복 정리 뒤)과 값(나쁜 레코드 = nan)."""
    ts: np.ndarray
    val: np.ndarray


@dataclass
class Symbol:
    name: str
    funding: Series
    bars: Series                      # 일봉 open_time → 종가
    unusable_funding: frozenset[str]  # 'YYYY-MM'
    unusable_bars: frozenset[str]


def _num(cell: str) -> float:
    try:
        v = float(cell)
    except ValueError:
        return math.nan
    return v if math.isfinite(v) else math.nan


def _funding_row(line: str) -> tuple[int, float]:
    c = line.rstrip("\r\n").split(",")
    return int(c[0]), _num(c[-1])                                                # 첫 칸 = 시각(가드가 검사) · 마지막 칸 = 펀딩률


def _bar_row(line: str) -> tuple[int, float]:
    c = line.rstrip("\r\n").split(",")
    return int(c[0]), _num(c[4])                                                 # open_time · close


def dedup(rows: list[tuple[int, float]]) -> Series:
    """같은 시각: 값이 같으면 하나 · 다르면(또는 하나라도 nan) nan(나쁜 레코드)."""
    by: dict[int, list[float]] = {}
    for t, v in rows:
        by.setdefault(t, []).append(v)
    ts = sorted(by)
    val = []
    for t in ts:
        vs = by[t]
        same = all(not math.isnan(v) for v in vs) and len(set(vs)) == 1
        val.append(vs[0] if same else math.nan)
    return Series(np.array(ts, dtype=np.int64), np.array(val, dtype=float))


def _read_dir(d: Path, row) -> tuple[list[tuple[int, float]], frozenset[str]]:  # noqa: ANN001
    """표시 파일(.unusable)이 있는 달은 zip을 읽지 않는다 · 열기/읽기 실패한 zip = 쓸 수 없음(그 파일의 행은 버림) ·
    시각 칸 오류와 예약 구간은 `ReserveError`로 멈춘다."""
    rows: list[tuple[int, float]] = []
    bad: set[str] = set()
    if not d.exists():
        return rows, frozenset()
    for p in sorted(d.glob("*.zip.unusable")):
        refuse_reserved_archive(p.name)                                           # 표시 파일도 예약 구간 이름이면 멈춘다
        bad.add(p.name.removesuffix(".zip.unusable")[-7:])
    for p in sorted(d.glob("*.zip")):
        refuse_reserved_archive(p.name)
        month = p.name.removesuffix(".zip")[-7:]
        if month in bad:
            continue
        try:
            part = list(bounded_zip_csv(p, row, header=zip_has_header(p, names=HEADER_TS)))
        except ReserveError:
            raise
        except Exception:                                                         # noqa: BLE001 — 열기·읽기 실패
            bad.add(month)
            continue
        rows.extend(part)
    return rows, frozenset(bad)


def symbols() -> list[str]:
    names = sorted({p.name for p in (ARCHIVE / "fundingRate").glob("*")} | {p.name for p in (ARCHIVE / "klines").glob("*")})
    return [n for n in names if n.endswith("USDT") and set(n) <= ASCII_USDT]


def read_symbol(name: str) -> Symbol:
    f, uf = _read_dir(ARCHIVE / "fundingRate" / name, _funding_row)
    b, ub = _read_dir(ARCHIVE / "klines" / name / "1d", _bar_row)
    sym = Symbol(name, dedup(f), dedup(b), uf, ub)
    for ser in (sym.funding, sym.bars):
        if ser.ts.size:
            assert_within([int(ser.ts[0]), int(ser.ts[-1])])
    return sym


MANIFEST = Path(__file__).resolve().parent / "data" / "fetch_manifest.csv"


def _manifest_row(line: str) -> tuple[str, str, str]:
    _, key, status, sha = line.rstrip("\r\n").split(",")
    return key, status, sha


def manifest(path: Path = MANIFEST) -> list[tuple[str, str, str]]:
    """내려받기 목록(키 · 상태 · SHA256) — 첫 칸 = 그 파일 달의 시작(ms)이라 창 가드로 읽는다."""
    return list(bounded_csv_file(path, _manifest_row, header=True))


def _rate(line: str) -> tuple[str, float | None]:
    d, v = line.rstrip("\r\n").split(",")
    return d, (None if v.strip() in ("", ".") else float(v))


def dtb3(path: Path = DTB3) -> list[tuple[str, float]]:
    return [(d, v) for d, v in bounded_benchmark_csv(path, _rate) if v is not None]
