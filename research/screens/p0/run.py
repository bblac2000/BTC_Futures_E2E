"""M-1 실행기(스펙 r6 §3~§6) — 한 번만 돈다(결과 파일이 있으면 거부).

    uv run python -m research.screens.p0.run
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict

import numpy as np

from research.screens.p0 import loader, sample, sim
from research.screens.p0 import span as SP
from research.screens.window import write_result

OUT_JSON = SP.ROOT / "research" / "screens" / "p0" / "results" / "M-1.json"
OUT_MD = SP.ROOT / "research" / "screens" / "p0" / "results" / "M-1.md"
QUALITY = SP.RESTORE / "l2-2026-10-10.json"
W = {"prox": 30 / 1440, "other": 1410 / 1440}
DONOR_SEED, BOOT_SEED, N_BOOT, N_DONOR = 20261016, 20261015, 1000, 20
KILL_BPS = 2.0
DAY = 86_400_000


def _d0(date: str) -> int:
    return int(dt.datetime.fromisoformat(date).replace(tzinfo=dt.UTC).timestamp() * 1000)


def quality_fail_intervals() -> list[tuple[int, int]]:
    """품질 보고서의 FAIL 구간(스펙 §2-2 4 — gaps 표에 없을 때 더한다). 보고서가 없으면 빈 목록(공시)."""
    if not QUALITY.exists():
        return []
    q = json.loads(QUALITY.read_text(encoding="utf-8"))
    out = []
    for g in q.get("gaps", []) or q.get("depth100ms_gaps", {}).get("gaps", []) or []:
        s, e = g.get("start_ms") or g.get("start"), g.get("end_ms") or g.get("end")
        if isinstance(s, int) and isinstance(e, int):
            out.append((s, e))
    return out


def head(rows: list[dict], key: str) -> float | None:
    by = defaultdict(list)
    for r in rows:
        by[r["stratum"]].append(r[key])
    if not by.get("prox") or not by.get("other"):
        return None
    return sum(W[s] * float(np.mean(by[s])) for s in W)


def boot_ci(rows: list[dict], key: str, rng: np.random.Generator) -> list[float] | None:
    days = sorted({r["date"] for r in rows})
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["date"]].append(r)
    stats = []
    for _ in range(N_BOOT):
        pick = rng.choice(len(days), size=len(days), replace=True)
        rs = [r for i in pick for r in by_day[days[i]]]
        h = head(rs, key)
        if h is not None:
            stats.append(h)
    if len(stats) < N_BOOT:
        return None
    return [float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))]


def main() -> int:
    if OUT_JSON.exists():
        print("거부: M-1.json이 이미 있다 — 측정은 한 번만", file=sys.stderr)
        return 2
    try:
        loader.restore_record()
    except RuntimeError as e:
        print(f"거부: {e}", file=sys.stderr)
        return 3
    draws = sample.draw()
    qfail = quality_fail_intervals()
    bad = loader.bad_intervals(qfail)
    days = list(SP.DATES)
    # B_d(§4-3)
    pooled_r, pooled_t, per_day = [], [], {}
    for date in days:
        lo, hi = max(_d0(date), SP.EXPOSED_START_MS), min(_d0(date) + DAY - 1, SP.EXPOSED_END_MS)
        ag = loader._read("aggtrade", lo, hi, ["recv_ms", "transact_time"])
        per_day[date] = (ag["recv_ms"].astype(np.int64), ag["transact_time"].astype(np.int64))
        pooled_r.append(per_day[date][0])
        pooled_t.append(per_day[date][1])
    pooled = (np.concatenate(pooled_r), np.concatenate(pooled_t))
    bd = {d: sim.b_bound(*per_day[d], pooled=pooled) for d in days}
    del per_day, pooled_r, pooled_t, pooled
    # 기증 후보(대조 ②) — 결정마다 20개 · d′ ≠ d · 균등
    rng_d = np.random.default_rng(DONOR_SEED)
    by_date: dict[str, list[int]] = defaultdict(list)
    dec = []
    for i, (t0, buy, st) in enumerate(draws):
        date = dt.datetime.fromtimestamp(t0 / 1000, dt.UTC).date().isoformat()
        others = [d for d in days if d != date]
        cands = [others[int(k)] for k in rng_d.integers(0, len(others), size=N_DONOR)]
        dec.append({"i": i, "t0": t0, "buy": buy, "stratum": st, "date": date, "cands": cands})
        by_date[date].append(i)
    cand_on: dict[str, list[tuple[int, int]]] = defaultdict(list)          # 기증 날 → (결정, 후보 순번)
    for d in dec:
        for k, c in enumerate(d["cands"]):
            cand_on[c].append((d["i"], k))
    placed: dict[int, sim.Placed] = {}
    rows: dict[str, list[dict]] = {"main": [], "flip": []}
    inelig: Counter = Counter()
    flip_inelig: Counter = Counter()
    donor_ok: dict[tuple[int, int], tuple[int, int]] = {}                  # (결정, 순번) → (기증 p′ 틱, 기증 날 시작)
    for date in days:                                                        # 1차: 주 장부 · 방향 뒤집기 · 기증 적격
        bk = loader.book(_d0(date) - 10_000, _d0(date) + DAY + 130_000, bad)
        b_ms = bd[date]
        for i in by_date[date]:
            d = dec[i]
            if b_ms > sim.B_MAX_MS:
                inelig["b_bound"] += 1
                continue
            pl = sim.place(bk, d["t0"], d["buy"])
            if isinstance(pl, str):
                inelig[pl] += 1
                continue
            placed[i] = pl
            tape = sim.tape_of(bk, d["t0"] - sim.PRE_MS, d["t0"] + sim.DELTA_MS + sim.POST_MS)
            rows["main"].append({**_row(d, pl, tape, b_ms), "i": i})
            fl = sim.place(bk, d["t0"], not d["buy"])
            if isinstance(fl, str):
                flip_inelig[fl] += 1
            else:
                rows["flip"].append({**_row(d, fl, tape, b_ms), "pair": i})
        for i, k in cand_on[date]:                                          # 이 날이 기증 후보인 (결정, 순번)
            d = dec[i]
            t1 = _d0(date) + (d["t0"] - _d0(d["date"]))
            if bd[date] > sim.B_MAX_MS or sim.continuity_ok(bk, t1 - sim.PRE_MS, t1 + sim.DELTA_MS + sim.POST_MS):
                continue
            q = sim.quote(bk, t1 + sim.DELTA_MS)
            if q is None:
                continue
            (bid, _bq, ask, _aq), _dp = q
            donor_ok[(i, k)] = (int(sim.ticks(bid if d["buy"] else ask)), _d0(date))
        del bk
    chosen: dict[str, list[tuple[int, int, int]]] = defaultdict(list)       # 기증 날 → (결정, p′ 틱, 기증 날 시작)
    donor_fail = 0
    for i in placed:
        d = dec[i]
        pick = next(((d["cands"][k],) + donor_ok[(i, k)] for k in range(N_DONOR) if (i, k) in donor_ok), None)
        if pick is None:
            donor_fail += 1
        else:
            chosen[pick[0]].append((i, pick[1], pick[2]))
    rows["donor"] = []
    for date in days:                                                        # 2차: 대조 ② 테이프
        if not chosen[date]:
            continue
        bk = loader.book(_d0(date) - 10_000, _d0(date) + DAY + 130_000, bad)
        for i, pprime, d0p in chosen[date]:
            d, pl = dec[i], placed[i]
            shift = d0p - _d0(d["date"])
            t1 = d["t0"] + shift
            tape = sim.tape_of(bk, t1 - sim.PRE_MS, t1 + sim.DELTA_MS + sim.POST_MS, shift_ms=shift, tick_shift=pl.p_tick - pprime)
            rows["donor"].append({**_row(d, pl, tape, bd[date]), "pair": i})
        del bk
    res = summarize(rows, inelig, flip_inelig, donor_fail, bd, qfail, len(draws))
    write_result(OUT_JSON, res)
    OUT_MD.write_text(markdown(res), encoding="utf-8")
    print(json.dumps({"verdict": res["verdict"], "best_T": res["best_T"], "head_bps": res["head_bps_best"]}, ensure_ascii=False))
    return 0


def _row(d: dict, pl: sim.Placed, tape: sim.Tape, b_ms: int) -> dict:
    r = {"date": d["date"], "stratum": d["stratum"], "buy": pl.buy, "imb": pl.imbalance, "reject": pl.reject}
    for t_ms in sim.TS:
        path, px, mk = sim.outcome(pl, tape, b_ms, t_ms)
        r[f"path_{t_ms}"] = path
        r[f"imp_{t_ms}"] = sim.improvement(pl, px, mk)
        r[f"bnb_{t_ms}"] = sim.improvement(pl, px, mk, "bnb")
        for name, b in (("b0", 0), ("b6000", 6_000)):
            _p2, px2, mk2 = sim.outcome(pl, tape, b, t_ms)
            r[f"{name}_{t_ms}"] = sim.improvement(pl, px2, mk2)
        r[f"late_{t_ms}"] = bool(path == "timeout" and sim.late_conflict(pl, tape, b_ms, t_ms))
    fb = pl.x_reject if pl.reject and pl.x_reject is not None else pl.x_fallback[120_000]
    r["fallback_only_120000"] = sim.improvement(pl, fb, False)
    return r


def summarize(rows, inelig, flip_inelig, donor_fail, bd, qfail, n_draw) -> dict:
    main = rows["main"]
    rng = np.random.default_rng(BOOT_SEED)
    per_t = {}
    for t_ms in sim.TS:
        k = f"imp_{t_ms}"
        per_t[str(t_ms // 1000)] = {
            "head_bps": head(main, k), "ci95": boot_ci(main, k, rng),
            "stratum_mean": {s: float(np.mean([r[k] for r in main if r["stratum"] == s])) for s in W if any(r["stratum"] == s for r in main)},
            "median": float(np.median([r[k] for r in main])) if main else None,
            "maker_rate": float(np.mean([r[f"path_{t_ms}"] == "maker" for r in main])) if main else None,
            "reject_rate": float(np.mean([r["reject"] for r in main])) if main else None,
            "late_conflicts": int(sum(r[f"late_{t_ms}"] for r in main)),
            "sens_bnb_head": head(main, f"bnb_{t_ms}"), "sens_B0_head": head(main, f"b0_{t_ms}"), "sens_B6000_head": head(main, f"b6000_{t_ms}")}
    heads = {t: v["head_bps"] for t, v in per_t.items() if v["head_bps"] is not None}
    best = min((t for t in heads if heads[t] == max(heads.values())), key=int) if heads else None
    verdict = "판정 불능" if best is None else ("KILL(stay taker)" if heads[best] < KILL_BPS else "NOT-KILLED")
    terc = {}
    if main and best:
        imb = np.array([r["imb"] for r in main])
        e1, e2 = np.quantile(imb, [1 / 3, 2 / 3])
        k = f"imp_{int(best) * 1000}"
        for name, m in (("low", imb <= e1), ("mid", (imb > e1) & (imb <= e2)), ("high", imb > e2)):
            sub = [r for r, f in zip(main, m, strict=True) if f]
            terc[name] = {"n": len(sub), "head_bps": head(sub, k), "mean_bps": float(np.mean([r[k] for r in sub])) if sub else None}
        terc["edges"] = [float(e1), float(e2)]
    controls = {}
    for name in ("flip", "donor"):
        rs = rows[name]
        pairs = {r["pair"] for r in rs}
        controls[name] = {"n": len(rs)}
        if best:
            k = f"imp_{int(best) * 1000}"
            paired_main = [r for r in main if r["i"] in pairs]                  # 짝지은 모집단에서 주 장부를 다시 계산(스펙 §6)
            controls[name].update(head_bps=head(rs, k), main_head_bps_same_population=head(paired_main, k),
                                  maker_rate=float(np.mean([r[f"path_{int(best) * 1000}"] == "maker" for r in rs])) if rs else None,
                                  dropped_from_main=len(main) - len(paired_main))
    controls["fallback_only_head_bps_T120"] = head(main, "fallback_only_120000")
    return {"id": "M-1", "spec_sha256": "13643e669eadfa246f28a51c8bb0eee1cfbd0bda63a422cc889ce146cab234ff",
            "protocol_sha256": "367a04ba63d4c93ec22d1f11440eb9a57aa6dfd7a2311a6308bc97436459f787",
            "n_draw": n_draw, "n_eligible": len(main), "ineligible": dict(inelig), "flip_ineligible": dict(flip_inelig),
            "donor_fail": donor_fail, "B_d_ms": bd, "quality_fail_intervals": qfail, "per_T": per_t, "best_T": best,
            "head_bps_best": heads.get(best) if best else None, "kill_bps": KILL_BPS, "verdict": verdict, "imbalance_terciles": terc,
            "controls": controls, "range": [SP.EXPOSED_START_MS, SP.EXPOSED_END_MS],
            "weights": W, "note": "단일 장세 파일럿 · 매매 근거 아님 · 대조와 민감도는 보고 전용",
            "quality_note": ("매니페스트 gaps 표에 2026-10-10 06:16~07:42Z 공백 행이 없다(수집기가 OOM으로 죽어 기록하지 못함). "
                             "품질 보고서 l2-2026-10-10.json은 스트림별 최대 무수신 길이(depth100ms 5,062.5초)만 있고 시작·끝 시각이 없어 "
                             "구간으로 옮길 수 없다 — 그 구간은 §4-1 2의 스트림 연속성 검사(depth 수신 간격 ≤ 1초)가 제외한다.")}


def markdown(res: dict) -> str:
    lines = [f"# M-1 결과 — {res['verdict']} (최선 T = {res['best_T']}초 · 머리 통계 {res['head_bps_best']})", "",
             "| T(초) | 머리 통계(bps) | 95% CI | 근접 층 | 그 밖 층 | 중앙값 | 메이커 체결률 | 거부율 | 늦은 체결 충돌 | BNB | B=0 | B=6000 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda x: "—" if x is None else f"{x:.3f}"                         # noqa: E731
    for t, v in res["per_T"].items():
        ci = v["ci95"] or [None, None]
        sm = v["stratum_mean"]
        lines.append(f"| {t} | {f(v['head_bps'])} | [{f(ci[0])}, {f(ci[1])}] | {f(sm.get('prox'))} | {f(sm.get('other'))} | {f(v['median'])} | "
                     f"{f(v['maker_rate'])} | {f(v['reject_rate'])} | {v['late_conflicts']} | {f(v['sens_bnb_head'])} | {f(v['sens_B0_head'])} | "
                     f"{f(v['sens_B6000_head'])} |")
    lines += ["", f"적격 {res['n_eligible']} / 뽑음 {res['n_draw']} · 부적격 {res['ineligible']}", "",
              f"대조(보고 전용): {json.dumps(res['controls'], ensure_ascii=False)}", "",
              f"불균형 3분위(최선 T): {json.dumps(res['imbalance_terciles'], ensure_ascii=False)}", "",
              "단일 장세 파일럿 · 매매 근거 아님."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
