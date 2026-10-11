"""트라이얼 #5(C1 · T-SETTLE · 브리프 r2) IS 이전 보정 — **2022-01-01 → 2023-12-31만** · 레지스트리 #88 ①③ · #93.
⛔ **실행하지 않았다** — 프로젝트 종료(#93)로 작성만 하고 멈췄다. 산출물 없음 · 기록용으로만 보존.
트라이얼 코드가 아니다(backtest/·strategies/ 밖 · 테스트 없음). 2024 파일은 열지 않는다(assert).

    uv run python docs/trials/trial_05_calibration/calibrate_ts.py

🔒 출력 규율(advisor before-pass 4): 암마다 **개수 · 깔때기 · 사이징 불가 비율 · net 표준편차 · 투영 MDE**만 계산해 적는다.
   평균 · 부호 · 승률 · 트레이드별 값은 계산하지 않고, 출력하지 않고, 어디에도 쓰지 않는다. 한 번만 실행한다(출력 파일이 있으면 거부).

규칙(브리프 r2 · 자료를 보기 전에 고정 — 사용자 결정 #91·#93):
- 정산 시각 B ∈ {00, 08, 16 UTC} · 결정 시각 D = B − 240분.
- P̄ = 시작 시각이 [B − 480분, D)인 1m premiumIndexKlines 봉 240개의 종가 평균(전부 있어야 발화 · [DERIVED] — 거래소의 시간 가중 평균의 대용).
- 예상 펀딩 F̂ = P̄ + clamp(I − P̄, −0.05%, +0.05%) · I = 0.01%/8h([DOC] v6 715·702행).
- S: F̂ ≥ +0.05% → 숏 / L: F̂ ≤ −0.05% → 롱(사용자 결정: 절대 문턱 0.05%).
- 체결 = D + 1분 봉 mark 시가 · 시간 청산 = 체결 + 235분 봉 시가(= B − 4분 · 정산을 넘기지 않는다 → 펀딩 없음).
- SL = 체결가 × (1 ∓ sl_dist) · sl_dist = 1.5 × ATR_15m(14) / 체결가 · ATR = 끝 경계 ≤ D인 완전한 15분 mark 봉 14개의 TR 단순 평균(트라이얼 #3 정의).
단순화(공시 · 표준편차 추정용): SL은 봉 안 mark가 닿으면 SL 가격에 청산(봉 시가가 이미 넘었으면 시가) · 비용 = 22 bps 고정 · tick·수량 내림·청산가 미반영 ·
사이징 가능성: 명목 = 10 USDT ÷ sl_dist · 마진 = 명목 ÷ 30 > 400 USDT(40% 캡)이면 `infeasible_margin` · 수량 = 명목 ÷ 체결가 < 0.001이면 `infeasible_minqty`
(E_ref 1,000 · 리스크 1% · L 상한 30 · 최소 수량 0.001 — 고정된 규칙 스냅샷 값의 근사).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import sys
import zipfile
from pathlib import Path
from statistics import NormalDist

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
T4 = ROOT / "docs" / "trials" / "trial_04_calibration"
PREMIUM_DIR = ROOT / "var" / "t4_calib" / "premium_1m"
ARCHIVE = Path("/home/cms/project/data/BTCUSDT/1m")
ARCHIVE_FILES = ("BTCUSDT_1m_2022.csv", "BTCUSDT_1m_2023.csv")
OUT = HERE / "calibration_ts.json"
UTC = dt.UTC
MIN, H8 = 60_000, 8 * 3_600_000
CAL_START = int(dt.datetime(2022, 1, 1, tzinfo=UTC).timestamp() * 1000)
PRE_IS_END = int(dt.datetime(2023, 12, 31, 23, 59, 59, 999000, tzinfo=UTC).timestamp() * 1000)
LEAD_MIN, HOLD_MIN, N_PREM = 240, 235, 240
INTEREST, CLAMP, TAU = 0.0001, 0.0005, 0.0005
K_SL, ATR_N, ATR_W = 1.5, 14, 15
COST_BPS = 22.0
RISK_USDT, L_MAX, MARGIN_CAP_USDT, MIN_QTY = 10.0, 30, 400.0, 0.001
N_TRIALS, ALPHA_FAMILY, POWER, RHO_FLOOR, THETA = 10, 0.05, 0.80, 0.15, 20.0


def load_mark() -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    t0 = CAL_START - 2 * 1440 * MIN
    n = (PRE_IS_END + 1 - t0) // MIN
    o, h, lo, c = (np.full(n, np.nan) for _ in range(4))
    for name in ARCHIVE_FILES:
        with (ARCHIVE / name).open() as fh:
            for r in csv.DictReader(fh):
                t = int(dt.datetime.fromisoformat(r["timestamp"]).replace(tzinfo=UTC).timestamp() * 1000)
                assert t <= PRE_IS_END, "IS 창 자료를 읽으려 했다"
                i = (t - t0) // MIN
                if 0 <= i < n and r["mark_open"] and r["mark_high"] and r["mark_low"] and r["mark_close"]:
                    o[i], h[i], lo[i], c[i] = (float(r[k]) for k in ("mark_open", "mark_high", "mark_low", "mark_close"))
    return t0, o, h, lo, c


def load_premium() -> tuple[dict[int, float], list[dict]]:
    out: dict[int, float] = {}
    used = []
    for r in json.loads((T4 / "premium_fetch.json").read_text())["files"]:
        if r["file"] < "BTCUSDT-1m-2021-12.zip":
            continue
        data = (PREMIUM_DIR / r["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == r["sha256"]
        used.append({"file": r["file"], "sha256": r["sha256"]})
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            [name] = z.namelist()
            for row in csv.reader(io.TextIOWrapper(z.open(name))):
                if not row or not row[0].isdigit():
                    continue
                t = int(row[0])
                assert t <= PRE_IS_END, "IS 창 자료를 읽으려 했다"
                if t in out:
                    raise RuntimeError(f"중복 분 {t} — 데이터 품질 중단")
                out[t] = float(row[4])
    return out, used


def atr15(t0: int, h: np.ndarray, lo: np.ndarray, c: np.ndarray, d_ms: int) -> float | None:
    w = ATR_W * MIN
    end = d_ms - d_ms % w
    bars = []
    for j in range(ATR_N + 1, 0, -1):
        i = (end - w * j - t0) // MIN
        if i < 0:
            return None
        hh, ll, cc = h[i:i + ATR_W], lo[i:i + ATR_W], c[i:i + ATR_W]
        if len(hh) != ATR_W or np.isnan(hh).any() or np.isnan(ll).any() or np.isnan(cc).any():
            return None
        bars.append((hh.max(), ll.min(), cc[-1]))
    trs = [max(bars[i][0] - bars[i][1], abs(bars[i][0] - bars[i - 1][2]), abs(bars[i][1] - bars[i - 1][2])) for i in range(1, ATR_N + 1)]
    return float(sum(trs) / ATR_N)


def main() -> int:
    if OUT.exists():
        print(f"거부: {OUT.name}이 이미 있다 — 보정은 한 번만", file=sys.stderr)
        return 2
    t0, o, h, lo, c = load_mark()
    prem, used = load_premium()
    arms = {a: {"fired": 0, "by_year": {"2022": 0, "2023": 0}, "atr_undefined": 0, "data_gap": 0, "infeasible_margin": 0,
                "infeasible_minqty": 0, "n": 0, "exit_sl": 0, "exit_time": 0, "_net": []} for a in ("S", "L")}
    grid = valid = 0
    b = CAL_START - CAL_START % H8
    while b <= PRE_IS_END:
        d = b - LEAD_MIN * MIN
        b_cur, b = b, b + H8
        if d < CAL_START or b_cur > PRE_IS_END:
            continue
        grid += 1
        xs = [prem.get(d - (k + 1) * MIN) for k in range(N_PREM)]
        if any(x is None for x in xs):
            continue
        valid += 1
        p = float(np.mean(xs))                                              # type: ignore[arg-type]
        f = p + min(max(INTEREST - p, -CLAMP), CLAMP)
        arm = "S" if f >= TAU else "L" if f <= -TAU else None
        if arm is None:
            continue
        a = arms[arm]
        a["fired"] += 1
        a["by_year"][str(dt.datetime.fromtimestamp(d / 1000, UTC).year)] += 1
        atr = atr15(t0, h, lo, c, d)
        i0 = (d + MIN - t0) // MIN
        if atr is None:
            a["atr_undefined"] += 1
            continue
        seg_o, seg_h, seg_l = o[i0:i0 + HOLD_MIN + 1], h[i0:i0 + HOLD_MIN + 1], lo[i0:i0 + HOLD_MIN + 1]
        if len(seg_o) != HOLD_MIN + 1 or np.isnan(seg_o).any() or np.isnan(seg_h).any() or np.isnan(seg_l).any():
            a["data_gap"] += 1
            continue
        entry = float(seg_o[0])
        sl_dist = K_SL * atr / entry
        notional = RISK_USDT / sl_dist
        if notional / L_MAX > MARGIN_CAP_USDT:
            a["infeasible_margin"] += 1
            continue
        if notional / entry < MIN_QTY:
            a["infeasible_minqty"] += 1
            continue
        sign = -1.0 if arm == "S" else 1.0
        sl = entry * (1 - sign * sl_dist)
        exit_px, how = float(seg_o[HOLD_MIN]), "exit_time"
        for j in range(HOLD_MIN):
            hit_open = seg_o[j] <= sl if sign > 0 else seg_o[j] >= sl
            hit = seg_l[j] <= sl if sign > 0 else seg_h[j] >= sl
            if j > 0 and hit_open:
                exit_px, how = float(seg_o[j]), "exit_sl"
                break
            if hit:
                exit_px, how = sl, "exit_sl"
                break
        a["n"] += 1
        a[how] += 1
        a["_net"].append(sign * (exit_px - entry) / entry * 1e4 - COST_BPS)
    nd = NormalDist()
    k = nd.inv_cdf(1 - ALPHA_FAMILY / N_TRIALS) + nd.inv_cdf(POWER)
    res = {"window": "2022-01-01 → 2023-12-31(결정 시각 기준)", "grid_decisions": grid, "valid_prints": valid, "k_mde": k,
           "gate_mde_bps": 2 * THETA, "inputs": {"premium": used, "archive": list(ARCHIVE_FILES)}, "arms": {}}
    for name, a in arms.items():
        nets = a.pop("_net")
        sd = float(np.std(nets, ddof=1)) if len(nets) >= 2 else None
        n_eff = a["n"] / (1 + 4 * RHO_FLOOR)
        mde = k * sd / math.sqrt(n_eff) if sd is not None and n_eff > 0 else None
        a.update(sd_net_bps=sd, n_eff_floor=n_eff, projected_mde_bps=mde,
                 n_required_for_gate=(math.ceil((1 + 4 * RHO_FLOOR) * (k * sd / (2 * THETA)) ** 2) if sd is not None else None),
                 gate_pass=bool(mde is not None and mde <= 2 * THETA))
        del nets
        res["arms"][name] = a
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({n: {x: a[x] for x in ("fired", "n", "sd_net_bps", "projected_mde_bps", "gate_pass")} for n, a in res["arms"].items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
