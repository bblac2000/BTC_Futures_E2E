"""트라이얼 #4 r2 규칙의 IS 이전 트레이드 수(사용자 2026-09-30 항목 11) — **2022-01-01 → 2023-12-31만** · 손익 없음(개수·간격·흡수만).
트라이얼 코드가 아니다(backtest/·strategies/ 밖 · 테스트 없음). 원시 = calibrate_r2.py가 CHECKSUM 대조로 받은 premiumIndexKlines zip(2021-10 …
2023-12) + 1m 아카이브 2021·2022·2023 파일(2024 파일 미개봉).

    uv run python docs/trials/trial_04_calibration/count_r2.py

점유 재현(1m mark · 단순화 · 공시):
- 인쇄 p_T = 종료 시각이 (T − 8h, T]인 1m 프리미엄 지수 봉(= 시작 T − 8h … T − 1분 · 480개)의 종가 평균 · 분 ≥ 99% 아니면 인쇄 없음.
- 후행 분포 = p_T보다 엄격히 앞선 유효 인쇄 270개 · numpy 선형 · 비교는 `≥ Q0.95`(S) / `≤ Q0.05`(L)(규칙 1 · 변형은 인자).
- 결정 = T 분 봉(시작 T)의 마감 T + 1분 [PROPOSED 가용 규칙] · 진입 = T + 1분 봉 mark 시가(6 bps는 개수에 영향 없음 · SL 기준가는 시가).
- SL = 진입 ∓ 2.0 × ATR_1d(14)(진입일 전날까지 완전한 14일 · 단순 평균) · sl_dist ∉ [1.0%, 22.0%] → abort(상태는 IDLE 유지 · 공시).
- 청산 = 체결 분 + 7,200분 봉 시가(시간) · 그 전에 봉 안 mark가 SL을 건드리면 SL(청산 게이트는 B2가 SL보다 먼 L을 고르므로 여기서는 SL이 먼저).
- 히스테리시스 = 청산 체결 **뒤** 인쇄 중 하나가 (Q0.05, Q0.95) **안(엄격)** 에 들 때까지 WAIT · 포지션 중 극단 인쇄 = position_busy(정상 상태).
- mark 결손 분이 보유 구간에 있으면 그 진입은 `data_gap`으로 세고 건너뜀(IS 규칙은 초안에서 정한다).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import calibrate_r2 as C  # noqa: E402

MIN, H8, DAY = C.MIN, C.H8, C.DAY
HOLD = 7_200
UTC = dt.UTC


def minute_mark() -> tuple[int, np.ndarray, np.ndarray, np.ndarray]:
    t0 = C.CAL_START - 20 * DAY
    n = (C.PRE_IS_END + 1 - t0) // MIN
    o, h, lo = (np.full(n, np.nan) for _ in range(3))
    for name in C.ARCHIVE_FILES[1:]:                                       # 2022·2023 파일(2021-12-31 15:00Z부터 포함)
        with (C.ARCHIVE / name).open() as fh:
            for r in csv.DictReader(fh):
                t = int(dt.datetime.fromisoformat(r["timestamp"]).replace(tzinfo=UTC).timestamp() * 1000)
                assert t <= C.PRE_IS_END
                i = (t - t0) // MIN
                if 0 <= i < n and r["mark_open"] and r["mark_high"] and r["mark_low"]:
                    o[i], h[i], lo[i] = float(r["mark_open"]), float(r["mark_high"]), float(r["mark_low"])
    return t0, o, h, lo


def premium_minutes_checked() -> dict[int, float]:
    """r3 결정 9: 중복 분 = 데이터 품질 중단(같은 open_ms가 두 번 나오면 예외)."""
    import hashlib
    import io
    import zipfile
    out: dict[int, float] = {}
    for r in json.loads((HERE / "premium_fetch.json").read_text())["files"]:
        data = (C.VAR / r["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == r["sha256"]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            [name] = z.namelist()
            for row in csv.reader(io.TextIOWrapper(z.open(name))):
                if not row or not row[0].isdigit():
                    continue
                t = int(row[0])
                assert t <= C.PRE_IS_END
                if t in out:
                    raise RuntimeError(f"중복 분 {t} — 데이터 품질 중단")
                out[t] = float(row[4])
    return out


def funding_buckets() -> set[int]:
    """1차 보정의 펀딩 REST 원시(2021-06 … 2023-12) — 분 버킷에 확정 펀딩이 정확히 1건인 경계."""
    n: dict[int, int] = defaultdict(int)
    for ln in (HERE / "raw_funding.jsonl").read_text().splitlines():
        for r in json.loads(ln)["page"]:
            t = int(r["fundingTime"])
            n[t - t % MIN] += 1
    return {b for b, k in n.items() if k == 1}


def prints() -> list[tuple[int, float]]:
    pm = premium_minutes_checked()                                         # open_ms → close
    first = min(pm) - min(pm) % H8 + H8
    out = []
    for T in range(first, C.PRE_IS_END + 1, H8):
        xs = [pm[t] for t in range(T - H8, T, MIN) if t in pm]             # 시작 T−8h … T−1분 = 종료 (T−8h, T]
        if len(xs) >= 475:                                                 # r3 결정 9: ≥ 475/480(Codex r3 재확인: 0.99×480은 476을 요구했다)
            out.append((T, statistics.fmean(xs)))
    return out


def run(pr, mk, atr, arm: str, q_lo: float, q_hi: float, sign: bool, hold: int = HOLD, hyst: bool = True,
        band_top: float = 0.22, fund: set[int] | None = None) -> dict:
    t0, o, h, lo = mk
    ts = [t for t, _ in pr]
    ps = [p for _, p in pr]
    state, pos = "IDLE", None
    trades, cnt = [], defaultdict(int)
    wait_since = None
    for i, (T, p) in enumerate(zip(ts, ps, strict=True)):
        if i < 270:
            continue
        w = np.asarray(ps[i - 270:i])
        ql, qh = float(np.quantile(w, q_lo)), float(np.quantile(w, q_hi))
        if T < C.CAL_START:
            continue
        ext = (p >= qh and (not sign or p > 0)) if arm == "S" else (p <= ql and (not sign or p < 0))
        if pos is not None and T >= pos["exit_ms"]:                        # 청산은 이미 끝남 → WAIT(히스테리시스 끄면 IDLE)
            trades.append(pos)
            pos, state, wait_since = None, ("WAIT" if hyst else "IDLE"), trades[-1]["exit_ms"]
        if state == "POS":
            cnt["extreme_absorbed_position_busy"] += ext
            continue
        if state == "WAIT":
            if T > wait_since and ql < p < qh:
                state = "IDLE"
            else:
                cnt["extreme_absorbed_hysteresis"] += ext
                continue
        if not ext:
            continue
        cnt["extreme_qualified"] += 1
        fill = T + MIN                                                     # 결정 = T 분 봉 마감 · 체결 = T+1분 봉 시가
        d = fill // DAY
        a = atr.get(d)
        fi = (fill - t0) // MIN
        end = fi + hold
        if a is None or end >= len(o) or np.isnan(o[fi]):
            cnt["abort_no_data"] += 1
            continue
        sl_dist = 2.0 * a
        if not 0.01 <= sl_dist <= band_top:
            cnt["abort_sl_dist_out_of_range"] += 1
            continue
        seg_h, seg_l = h[fi:end], lo[fi:end]
        if np.isnan(seg_h).any() or np.isnan(o[end]):
            cnt["abort_data_gap"] += 1
            continue
        if fund is not None:                                               # r3 결정 7: 15개 경계마다 검증된 확정 펀딩
            bs = [b for b in range(T + H8, fill + hold * MIN + 1, H8)]
            if len(bs) != hold * MIN // H8 or any(b not in fund for b in bs):
                cnt["abort_funding_unvalidated"] += 1
                continue
        e = o[fi]
        sl = e * (1 - sl_dist) if arm == "L" else e * (1 + sl_dist)
        hit = np.nonzero(seg_l <= sl)[0] if arm == "L" else np.nonzero(seg_h >= sl)[0]
        k = int(hit[0]) if len(hit) else None
        exit_ms = t0 + (fi + (k + 1 if k is not None else hold)) * MIN        # SL = 그 봉 안 · 다음 분부터 평평 / 시간 = 7,200분 봉 시가
        lev = C.b2_lev(sl_dist, arm == "L")
        pos = {"entry_ms": fill, "exit_ms": exit_ms, "reason": "sl" if k is not None else "time", "sl_dist": sl_dist, "L": lev}
        state = "POS"
    if pos is not None:
        trades.append(pos)
    by_y = defaultdict(int)
    for t in trades:
        by_y[str(dt.datetime.fromtimestamp(t["entry_ms"] / 1000, UTC).year)] += 1
    gaps = [(b["entry_ms"] - a["exit_ms"]) / DAY for a, b in zip(trades, trades[1:], strict=False)]
    ent_gaps = [(b["entry_ms"] - a["entry_ms"]) / DAY for a, b in zip(trades, trades[1:], strict=False)]
    reasons = defaultdict(int)
    lev = defaultdict(int)
    for t in trades:
        reasons[t["reason"]] += 1
        L = t["L"]
        lev["none" if L is None else "3–4" if L < 5 else "5–7" if L < 8 else "8–9" if L < 10 else "≥10"] += 1
    return {"trades_per_year": dict(by_y), "trades": len(trades), "exit_reasons": dict(reasons),
            "median_days_entry_to_entry": round(statistics.median(ent_gaps), 2) if ent_gaps else None,
            "median_days_exit_to_next_entry": round(statistics.median(gaps), 2) if gaps else None,
            "median_sl_dist_pct": round(statistics.median(t["sl_dist"] for t in trades) * 100, 2) if trades else None,
            "L_bins": dict(lev), "counts": dict(cnt)}


def main() -> int:
    pr = prints()
    day = C.daily_mark()
    atr = C.atr_pct(day)
    mk = minute_mark()
    res: dict[str, object] = {"prints_used": len(pr)}
    variants = {"r2_rules(Q.05/.95 ≥≤)": (0.05, 0.95, False), "with_sign(S p>0 · L p<0)": (0.05, 0.95, True),
                "Q.10/.90": (0.10, 0.90, False), "Q.10/.90_with_sign": (0.10, 0.90, True)}
    for name, (ql, qh, sign) in variants.items():
        res[name] = {arm: run(pr, mk, atr, arm, ql, qh, sign) for arm in ("S", "L")}
    fund = funding_buckets()
    r3 = {arm: run(pr, mk, atr, arm, 0.10, 0.90, False, band_top=0.20, fund=fund) for arm in ("S", "L")}
    res["r3_decisions(Q.10/.90 · band 1–20% · 15 funding validated)"] = r3
    one_knob = {"hold_3d": dict(hold=3 * 1440), "no_hysteresis": dict(hyst=False), "hold_3d_no_hysteresis": dict(hold=3 * 1440, hyst=False)}
    for name, kw in one_knob.items():
        res[name] = {arm: run(pr, mk, atr, arm, 0.05, 0.95, False, **kw) for arm in ("S", "L")}
    (HERE / "count_r2.json").write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
