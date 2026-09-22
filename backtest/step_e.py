"""단계 e 실행기 — 모든 실행을 **격리 subprocess**로(`backtest.replay.run_isolated`) · 실행마다 verbatim 기록 · 이어 하기 가능.

    python -m backtest.step_e --stage A                 # 전체 IS Arm A 하나(벽시계·최대 RSS 실측 → 병렬 수 결정)
    python -m backtest.step_e --stage base --jobs 2     # B · P2(+1·+5) · P3
    python -m backtest.step_e --stage p1 --parts 8 --jobs 4
    python -m backtest.step_e --stage p4 --jobs 3       # P4 200회(로컬 전용 · VPS 금지)
    python -m backtest.evaluate --step-e-dir var/backtest/IS/step_e   # 모든 산출물이 갖춰진 뒤 한 번

- 산출물: `var/backtest/IS/step_e/<실행 이름>/` · 기록: `step_e/_records/<실행 이름>.json`(명령·종료 코드·stdout/stderr·출력 SHA256·git HEAD).
- 이 실행기는 **산출물을 열지 않는다** — stdout(개수만)과 종료 코드만 본다. 판정은 `backtest.evaluate` 한 번.
- 이어 하기: 기록의 종료 코드가 0인 실행은 건너뛴다(긴 P4를 끊었다 다시 돌려도 같은 결과 — 실행은 결정론적).
- OOS는 없다(`--window IS` 고정).
"""
from __future__ import annotations

import argparse
import json
import resource
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backtest import placebo as PL
from backtest.replay import record_verbatim, run_isolated
from strategies.trial01 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
STEP_E = ROOT / "var" / "backtest" / "IS" / "step_e"
STRATEGY = "strategies.trial01.run"
BASE = {"A": ["--window", "IS", "--arm", "A"], "B": ["--window", "IS", "--arm", "B"]}
BASE |= {k: ["--window", "IS", "--arm", "A", *v] for k, v in PL.variant_args().items()}      # P2_delay1·P2_delay5·P3_invert(원판 = Arm A)


def p4_jobs() -> dict[str, list[str]]:
    return {k: ["--window", "IS", "--arm", "A", *v] for k, v in PL.p4_args().items()}


def done(name: str) -> bool:
    rec = STEP_E / "_records" / f"{name}.json"
    return rec.exists() and json.loads(rec.read_text())["run"]["returncode"] == 0


def run_one(name: str, module: str, args: list[str], out: Path) -> dict[str, object]:
    t0 = time.time()
    rec = run_isolated(module, args, out, timeout_s=12 * 3600)
    (STEP_E / "_records").mkdir(parents=True, exist_ok=True)
    sha = record_verbatim(STEP_E / "_records" / f"{name}.json", rec, {"wall_s": round(time.time() - t0, 1)})
    return {"name": name, "returncode": rec.returncode, "wall_s": round(time.time() - t0, 1), "record_sha256": sha,
            "stdout": rec.stdout.strip()[-300:]}


def run_many(jobs: dict[str, tuple[str, list[str], Path]], n_jobs: int) -> list[dict[str, object]]:
    todo = {k: v for k, v in jobs.items() if not done(k)}
    with ThreadPoolExecutor(max(1, n_jobs)) as ex:
        res = list(ex.map(lambda kv: run_one(kv[0], *kv[1]), todo.items()))
    for r in res:
        print(json.dumps(r, ensure_ascii=False), flush=True)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["A", "base", "p1", "p1-merge", "p4"], required=True)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--parts", type=int, default=4)
    a = ap.parse_args(argv)
    STEP_E.mkdir(parents=True, exist_ok=True)
    if a.stage == "A":
        res = run_many({"A": (STRATEGY, BASE["A"], STEP_E / "A")}, 1)
    elif a.stage == "base":
        res = run_many({k: (STRATEGY, v, STEP_E / k) for k, v in BASE.items() if k != "A"}, a.jobs)
    elif a.stage == "p1":
        if not done("A"):
            raise SystemExit("P1은 원판 Arm A 실행이 끝난 뒤에만(쌍 입력)")
        step = -(-A.P1_DRAWS // a.parts)
        jobs = {}
        for lo in range(0, A.P1_DRAWS, step):
            hi = min(A.P1_DRAWS - 1, lo + step - 1)
            name = f"P1_part_{lo:03d}_{hi:03d}"
            jobs[name] = ("backtest.p1_run", ["--step-e-dir", str(STEP_E), "--draws", f"{lo}-{hi}"],
                          STEP_E / "P1" / f"part_{lo:03d}_{hi:03d}")
        res = run_many(jobs, a.jobs)
    elif a.stage == "p1-merge":
        from backtest.p1_run import merge
        print(json.dumps(merge(STEP_E)))
        return 0
    else:
        res = run_many({k: (STRATEGY, v, STEP_E / "P4" / k) for k, v in p4_jobs().items()}, a.jobs)
    peak_mb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024
    print(json.dumps({"stage": a.stage, "runs": len(res), "failed": [r["name"] for r in res if r["returncode"] != 0],
                      "max_child_rss_mb": peak_mb}), flush=True)
    return 0 if all(r["returncode"] == 0 for r in res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
