"""트라이얼 #4(T-CARRY) 사전 보정 — **IS 이전 자료만**(2022-01-01 → 2023-12-31 · 창 워밍업은 2021-06부터). 트라이얼 코드가 아니다
(backtest/·strategies/ 밖 · 테스트 없음 · 트라이얼 모듈이 import하지 않는다). 증거 산출용.

    uv run python docs/trials/trial_04_calibration/calibrate.py --capture   # 펀딩 REST 읽기 1회(endTime ≤ 2023-12-31 23:59:59.999Z)
    uv run python docs/trials/trial_04_calibration/calibrate.py             # 저장된 원시 + 1m 아카이브(2021·2022·2023 파일만)로 계산

가드: 요청 endTime = PRE_IS_END · 받은 모든 fundingTime ≤ PRE_IS_END 단언 · 아카이브는 2024 파일을 열지 않는다(그 파일의 첫 9시간은 IS 전이지만
IS 행과 섞여 있어 통째로 건너뛴다 → 2023-12-31 UTC 하루는 ATR 표에서 빠진다) · 읽은 1m 행도 시각 ≤ PRE_IS_END 단언.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT))

UTC = dt.UTC
PRE_IS_END = int(dt.datetime(2023, 12, 31, 23, 59, 59, 999000, tzinfo=UTC).timestamp() * 1000)
FETCH_START = int(dt.datetime(2021, 6, 1, tzinfo=UTC).timestamp() * 1000)
CAL_START = int(dt.datetime(2022, 1, 1, tzinfo=UTC).timestamp() * 1000)
H8 = 8 * 3_600_000
DAY = 86_400_000
ARCHIVE = Path("/home/cms/project/data/BTCUSDT/1m")
ARCHIVE_FILES = ("BTCUSDT_1m_2021.csv", "BTCUSDT_1m_2022.csv", "BTCUSDT_1m_2023.csv")
RAW = HERE / "raw_funding.jsonl"


def capture() -> None:
    from backtest import data as BD
    from backtest import prepare_t2 as T2
    from exchange.ccxt_rest import CcxtRestClient
    from exchange.client import ReadOnlyClient
    pages = T2._pages(ReadOnlyClient(CcxtRestClient()), BD.FUNDING_PATH, {"symbol": BD.SYMBOL}, FETCH_START, PRE_IS_END,
                      ts_key="fundingTime", step=1, limit=BD.REST_FUNDING_LIMIT)
    for p in pages:
        assert all(int(r["fundingTime"]) <= PRE_IS_END for r in p), "IS 행이 응답에 있다"
    RAW.write_text("".join(json.dumps({"page": p}) + "\n" for p in pages))
    meta = {"captured_utc": dt.datetime.now(UTC).isoformat(timespec="seconds"), "startTime": FETCH_START, "endTime": PRE_IS_END,
            "pages": len(pages), "rows": sum(len(p) for p in pages), "file_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(),
            "line_sha256": [hashlib.sha256(ln).hexdigest() for ln in RAW.read_bytes().split(b"\n") if ln]}
    (HERE / "raw_funding.meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps({k: v for k, v in meta.items() if k != "line_sha256"}))


def prints() -> list[tuple[int, float]]:
    rows = [r for ln in RAW.read_text().splitlines() if ln.strip() for r in json.loads(ln)["page"]]
    out: dict[int, float] = {}
    for r in rows:
        t = int(r["fundingTime"])
        assert t <= PRE_IS_END
        b = t - t % 60_000
        assert b not in out, f"중복 버킷 {b}"
        out[b] = float(r["fundingRate"])
    return sorted(out.items())


def trailing(xs: list[float], i: int, w: int) -> np.ndarray | None:
    return None if i < w else np.asarray(xs[i - w:i])                    # f_i보다 **엄격히 앞선** w개


def simulate(ts: list[int], fs: list[float], w: int, q_lo: float, q_hi: float, cap_days: int = 10, strict: bool = False
             ) -> dict[str, list[dict]]:
    """점유 근사(SL 무시): 암마다 IDLE(자격) → 극단 인쇄에서 진입 → 정상화 인쇄(중앙값 넘어섬) 또는 10일 상한에서 청산 →
    청산 **뒤** 인쇄 중 띠 [Q_lo, Q_hi] 안 인쇄가 하나 나올 때까지 WAIT(히스테리시스) → IDLE. 진입·청산 시각 = 인쇄 시각(분 단위 차이 무시)."""
    out: dict[str, list[dict]] = {"S": [], "L": []}
    for arm in ("S", "L"):
        state, pos = "IDLE", None
        for i, (t, f) in enumerate(zip(ts, fs, strict=True)):
            win = trailing(fs, i, w)
            if win is None or t < CAL_START:
                continue
            lo, hi, med = (float(np.quantile(win, q)) for q in (q_lo, q_hi, 0.5))
            if state == "POS":
                assert pos is not None
                norm = f <= med if arm == "S" else f >= med
                if t - pos["entry"] >= cap_days * DAY:
                    pos |= {"exit": pos["entry"] + cap_days * DAY, "reason": "cap"}
                elif norm:
                    pos |= {"exit": t, "reason": "norm"}
                if "exit" in pos:
                    out[arm].append(pos)
                    state, pos = "WAIT", None
                    if lo <= f <= hi and t > out[arm][-1]["exit"]:
                        state = "IDLE"
                    continue
            if state == "WAIT":
                if lo <= f <= hi:
                    state = "IDLE"
                continue
            ext = (f > hi if strict else f >= hi) if arm == "S" else (f < lo if strict else f <= lo)
            if state == "IDLE" and ext:
                state, pos = "POS", {"entry": t, "f": f}
        if pos is not None:
            out[arm].append(pos | {"exit": None, "reason": "open_at_end"})
    return out


def atr_table() -> dict[str, object]:
    day: dict[int, list[float]] = {}
    for name in ARCHIVE_FILES:
        with (ARCHIVE / name).open() as fh:
            for r in csv.DictReader(fh):
                t = int(dt.datetime.fromisoformat(r["timestamp"]).replace(tzinfo=UTC).timestamp() * 1000)
                assert t <= PRE_IS_END, "IS 행"
                if not (r["mark_high"] and r["mark_low"] and r["mark_close"]):
                    continue
                d = t // DAY
                h, lo, c = float(r["mark_high"]), float(r["mark_low"]), float(r["mark_close"])
                if d not in day:
                    day[d] = [h, lo, c, t]
                else:
                    x = day[d]
                    x[0], x[1] = max(x[0], h), min(x[1], lo)
                    if t >= x[3]:
                        x[2], x[3] = c, t
    days = sorted(day)
    last_full = PRE_IS_END // DAY - 1                                    # 2023-12-31은 2024 파일에 걸쳐 있어 제외
    days = [d for d in days if d <= last_full]
    tr = {}
    for a, b in zip(days, days[1:], strict=False):
        if b != a + 1:
            continue
        h, lo, _, _ = day[b]
        pc = day[a][2]
        tr[b] = max(h - lo, abs(h - pc), abs(lo - pc))
    atr_pct: dict[int, float] = {}
    for d in sorted(tr):
        prev = [tr.get(d - k) for k in range(14)]
        if None in prev:
            continue
        atr_pct[d] = statistics.fmean(x for x in prev if x is not None) / day[d][2]                  # 단순 14일 평균(자유 선택 · 초안에서 명시)
    cal = {d: v for d, v in atr_pct.items() if d * DAY >= CAL_START}
    v = np.asarray(list(cal.values()))
    pct = {str(p): round(float(np.quantile(v, p / 100)) * 100, 3) for p in (5, 25, 50, 75, 95, 99)}
    frac = {f"k={k}": {"over_6.0%": round(float(np.mean(k * v > 0.06)), 4), "under_1.0%": round(float(np.mean(k * v < 0.01)), 4)}
            for k in (1.5, 2.0, 2.5)}
    by_year: dict[str, dict] = {}
    for y in (2022, 2023):
        vy = np.asarray([x for d, x in cal.items() if dt.datetime.fromtimestamp(d * DAY / 1000, UTC).year == y])
        by_year[str(y)] = {"n_days": len(vy), "median_pct": round(float(np.median(vy)) * 100, 3),
                           **{f"k={k}_over_6%": round(float(np.mean(k * vy > 0.06)), 4) for k in (1.5, 2.0, 2.5)}}
    return {"_by_day": atr_pct, "n_days": len(v), "atr_pct_percentiles": pct, "fraction_of_days": frac, "by_year": by_year,
            "definition": "ATR_1d(14) = 14일 단순 평균 TR(UTC 날 · mark H/L/C) / 그날 mark 종가 · 2022-01-01 ~ 2023-12-30"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", action="store_true")
    if ap.parse_args().capture:
        capture()
        return 0
    pr = prints()
    ts, fs = [t for t, _ in pr], [f for _, f in pr]
    gaps = [(a, b) for a, b in zip(ts, ts[1:], strict=False) if b - a != H8]
    per_year: dict[str, int] = defaultdict(int)
    for t in ts:
        per_year[str(dt.datetime.fromtimestamp(t / 1000, UTC).year)] += 1
    res: dict[str, object] = {"prints": {"n": len(ts), "first": ts[0], "last": ts[-1], "per_year": dict(per_year),
                                         "gaps_not_8h": len(gaps), "gaps": gaps[:10]}}
    sims = {}
    atr = res_atr = atr_table()
    atr_by_day = atr.pop("_by_day")
    for w, qs, strict in ((270, (0.05, 0.95), False), (540, (0.05, 0.95), False), (270, (0.10, 0.90), False),
                          (270, (0.05, 0.95), True), (540, (0.05, 0.95), True)):
        s = simulate(ts, fs, w, *qs, strict=strict)
        key = f"w{w}_q{qs[0]:.2f}-{qs[1]:.2f}" + ("_strict" if strict else "")
        arm_out = {}
        for arm, tr in s.items():
            by_y: dict[str, int] = defaultdict(int)
            holds = []
            for p in tr:
                by_y[str(dt.datetime.fromtimestamp(p["entry"] / 1000, UTC).year)] += 1
                if p["exit"] is not None:
                    holds.append((p["exit"] - p["entry"]) / DAY)
            reasons: dict[str, int] = defaultdict(int)
            for p in tr:
                reasons[p["reason"]] += 1
            band = {}
            for k in (1.5, 2.0, 2.5):
                ok = [p for p in tr if (a := atr_by_day.get(p["entry"] // DAY - 1)) is not None and 0.01 <= k * a <= 0.06]
                band[f"k={k}"] = len(ok)
            arm_out[arm] = {"entries_per_year": dict(by_y), "entries_total": len(tr), "exit_reasons": dict(reasons),
                            "entries_with_sl_in_[1%,6%]_prev_day_atr": band,
                            "hold_days_q": [round(float(np.quantile(holds, q)), 2) for q in (0.1, 0.25, 0.5, 0.75, 0.9)] if holds else []}
        # 자격 인쇄(히스테리시스 전): 매 인쇄가 극단인지
        raw_q = {"S": defaultdict(int), "L": defaultdict(int)}
        qhi, qlo = [], []
        for i, (t, f) in enumerate(zip(ts, fs, strict=True)):
            win = trailing(fs, i, w)
            if win is None or t < CAL_START:
                continue
            lo, hi = float(np.quantile(win, qs[0])), float(np.quantile(win, qs[1]))
            qhi.append(hi)
            qlo.append(lo)
            y = str(dt.datetime.fromtimestamp(t / 1000, UTC).year)
            raw_q["S"][y] += f >= hi
            raw_q["L"][y] += f <= lo
        stab = {"Q_hi": {"min": min(qhi), "median": float(np.median(qhi)), "max": max(qhi),
                         "median_abs_step": float(np.median(np.abs(np.diff(qhi))))},
                "Q_lo": {"min": min(qlo), "median": float(np.median(qlo)), "max": max(qlo),
                         "median_abs_step": float(np.median(np.abs(np.diff(qlo))))}}
        sims[key] = {"qualifying_prints_per_year": {a: dict(v) for a, v in raw_q.items()}, "arms": arm_out, "threshold_stability": stab}
    res["occupancy_approximation"] = sims
    res["occupancy_note"] = ("SL 무시 · 진입·청산 = 인쇄 시각 · 청산 인쇄는 히스테리시스 띠 판정에 쓰지 않음(청산 뒤 인쇄만) · "
                             "SL 청산은 보유를 줄이지만 극단 레짐에서 띠 복귀 전 재진입을 막으므로 진입 수 방향은 불확정 — 대략의 크기만")
    res["funding_rate_pct"] = {str(p): float(np.quantile([f for t, f in pr if t >= CAL_START], p / 100)) for p in (1, 5, 50, 95, 99)}
    res["atr"] = res_atr
    g = np.asarray([f for t, f in pr if t >= CAL_START])
    res["funding_discreteness"] = {str(y): {"n": int(len(gy)), "eq_0.0001": int((gy == 0.0001).sum()), "gt_0.0001": int((gy > 0.0001).sum()),
                                            "between_0_and_0.0001": int(((gy > 0) & (gy < 0.0001)).sum()), "le_0": int((gy <= 0).sum())}
                                   for y, gy in (("2022", np.asarray([f for t, f in pr if CAL_START <= t < CAL_START + 365 * DAY])),
                                                 ("2023", np.asarray([f for t, f in pr if t >= CAL_START + 365 * DAY])), ("all", g))}
    (HERE / "calibration.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps(res, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
