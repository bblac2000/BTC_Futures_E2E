"""트라이얼 #2 회귀 검사(트라이얼 #3 (b) 계획 r2 B2·B3) — **현재 코드**로 트라이얼 #2 실행 전부를 다시 돌려 기록된 산출물과 바이트 대조.

    uv run python scripts/t2_regression_check.py --out <스크래치 디렉터리> [--jobs 3] [--t2-base <트라이얼 #2 IS 디렉터리>]

- `--t2-base`: 기준선을 git 워크트리(변경 전 코드)에서 돌릴 때 본 저장소의 `var/backtest/t2/IS`(git 무시 데이터)를 가리킨다.
- `--skip-runs`는 판정기 계산 경로 점검용일 뿐 **회귀 증거가 아니다**(Codex (b) r2).

- 진단 도구다: 트라이얼 #2 문(`gate_cli` · 판정기 지문)을 거치지 않고 정본 함수를 직접 부른다 — 출처 기록을 쓰지 않고,
  `var/backtest/t2/IS` 아래에는 아무것도 쓰지 않는다(읽기만). 닫힌 판정(`evaluation/`)은 건드리지 않는다.
- B2: 205개 전략 실행(A · B · P2_delay1 · P2_delay5 · P3_invert · P4_draw000..199)을 `strategies.trial02.run.execute`로,
  P1 추출 0..999를 기록된 8조각 그대로 `backtest.p1_t2_run.run_range`로(**다시 돌린 A**를 입력으로), 병합을 `merge`로.
  각 자식 프로세스는 트라이얼 #2 CLI처럼 `decimal.setcontext(decimal.Context())`. 모든 산출 파일의 SHA256을 기록 파일과 대조
  (`meta.json`은 `git_head`·`gate`만 빼고 대조).
- B3(진단 · 새 판정 아님): `evaluate_t2`의 계산 함수(`compute` → `verdict_is` → 같은 보고 dict · 같은 JSON 설정)로 report.json을
  (a) 기록된 실행 (b) 다시 돌린 실행에서 다시 계산해 닫힌 report(SHA256 9223047c…)·verdict.txt와 대조한다. 출처·인벤토리·쓰기 단계는 없다.
"""
from __future__ import annotations

import argparse
import decimal
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

T2_BASE = ROOT / "var" / "backtest" / "t2" / "IS"
CLOSED_REPORT_SHA256 = "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e"
META_IGNORED = ("git_head", "gate")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_out(out: Path) -> None:
    o, t2 = out.resolve(), T2_BASE.parent.resolve()
    if T2_BASE.resolve() != (ROOT / "var" / "backtest" / "t2" / "IS").resolve():
        t2_default = (ROOT / "var" / "backtest" / "t2").resolve()
        if o == t2_default or t2_default in o.parents:
            raise SystemExit(f"🚫 {out}는 트라이얼 #2 디렉터리 안이다 — 스크래치만")
    if o == t2 or t2 in o.parents:
        raise SystemExit(f"🚫 {out}는 트라이얼 #2 디렉터리 안이다 — 스크래치만")


def compare_dirs(recorded: Path, rerun: Path) -> list[dict[str, Any]]:
    """기록 디렉터리의 파일마다 SHA256 대조(meta.json은 git_head·gate 제외) · 한쪽에만 있는 파일도 불일치."""
    bad: list[dict[str, Any]] = []
    rec = {p.name for p in recorded.iterdir() if p.is_file()}
    new = {p.name for p in rerun.iterdir() if p.is_file()} if rerun.exists() else set()
    for n in sorted(rec ^ new):
        bad.append({"dir": recorded.name, "file": n, "why": "only_in_" + ("recorded" if n in rec else "rerun")})
    for n in sorted(rec & new):
        if n == "meta.json":
            a, b = (json.loads((d / n).read_text()) for d in (recorded, rerun))
            for k in META_IGNORED:
                a.pop(k, None)
                b.pop(k, None)
            if a != b:
                bad.append({"dir": recorded.name, "file": n, "why": "meta_differs"})
        elif sha(recorded / n) != sha(rerun / n):
            bad.append({"dir": recorded.name, "file": n, "why": "sha_differs"})
    return bad


def _strategy(args: tuple[str, str, str, dict[str, Any], str]) -> str:
    decimal.setcontext(decimal.Context())
    from strategies.trial02 import run as R
    name, prepared, out, pins, pc = args
    R.execute(name, Path(prepared), Path(out), pins, pc, gate=None, head=None)
    return name


def _p1(args: tuple[str, str, dict[str, Any], int, int, str]) -> str:
    decimal.setcontext(decimal.Context())
    from backtest import p1_t2_run as P
    a_dir, prepared, pins, lo, hi, out = args
    P.run_range(Path(a_dir), Path(prepared), pins, lo, hi, Path(out))
    return out


def evaluator_report(base: Path) -> tuple[str, str]:
    """B3 진단: 판정기의 계산 경로로 report.json·verdict.txt 바이트를 다시 만든다(출처·인벤토리·쓰기 없음)."""
    import numpy as np

    from backtest import days as DY
    from backtest import evaluate_t2 as E
    from backtest import prepare_t2 as PT
    from backtest import t2_provenance as PV
    from backtest import t2_stages as T
    from backtest import verdict_t2 as V
    from strategies.trial02 import anchor as A
    decimal.setcontext(decimal.Context())
    receipt = json.loads((T2_BASE / "_records" / "verify_receipt.json").read_text())
    st = T.Stages(receipt["evaluator_commit"], base=base, fetch=False)
    pins, _ = PV.load_pins(ROOT, fetch=False)
    rng = PT.window_range()
    first, last = A.IS_START_MS // A.DAY_MS, A.IS_END_MS // A.DAY_MS
    bars, fundings = PT.load_prepared_pinned(st.prep, pins, rng)
    validity = DY.validity(bars, fundings, first, last)
    kline_daily = PT.load_kline_daily_pinned(st.prep, pins, rng)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        x, report = E.compute(st, validity, kline_daily, first, last)
    v = V.verdict_is(x)
    verdict = E.verdict_string(v)
    report = {"verdict": verdict, "priority": v.priority, "classification": v.classification, "gates": v.gates,
              "placebo_rejects": v.placebo_rejects, "sr_star": v.sr_star, "sr_undefined": v.sr_undefined, "mde": v.mde,
              "inputs": x.__dict__, **report}
    text = json.dumps(E._finite(report), sort_keys=True, indent=1, ensure_ascii=False, default=str, allow_nan=False) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), verdict + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--skip-runs", action="store_true", help="실행 재현 없이 B3(기록된 실행)만 — 회귀 증거 아님")
    ap.add_argument("--t2-base", help="트라이얼 #2 IS 디렉터리(기본: 이 저장소의 var/backtest/t2/IS)")
    a = ap.parse_args(argv)
    global T2_BASE
    if a.t2_base:
        T2_BASE = Path(a.t2_base).resolve()
    out = Path(a.out)
    check_out(out)
    from backtest import evaluate_t2 as E
    from backtest import t2_provenance as PV
    pins, pc = PV.load_pins(ROOT, fetch=False)
    prepared = T2_BASE / "prepared"
    rec_runs = T2_BASE / "runs"
    new_runs = out / "runs"
    summary: dict[str, Any] = {"head": PV.head(ROOT), "pins_commit": pc, "t2_base": str(T2_BASE), "skip_runs": a.skip_runs}
    if not a.skip_runs:
        names = list(E.STRATEGY_RUNS)
        ctx = get_context("spawn")
        with ProcessPoolExecutor(max_workers=a.jobs, mp_context=ctx) as ex:
            list(ex.map(_strategy, [(n, str(prepared), str(new_runs / n), pins, pc) for n in names]))
            parts = sorted(p.name for p in (rec_runs / "P1").iterdir() if p.is_dir())
            jobs = []
            for part in parts:
                lo, hi = (int(x) for x in part.removeprefix("part_").split("_"))
                jobs.append((str(new_runs / "A"), str(prepared), pins, lo, hi, str(new_runs / "P1" / part)))
            list(ex.map(_p1, jobs))
        from backtest import p1_t2_run as P
        from backtest.t2_stages import P1_OUTPUTS
        decimal.setcontext(decimal.Context())
        expect = {p: {f: sha(new_runs / "P1" / p / f) for f in P1_OUTPUTS if (new_runs / "P1" / p / f).exists()} for p in parts}
        P.merge(new_runs / "P1", expect, new_runs / "P1_merged")
        mism: list[dict[str, Any]] = []
        dirs = [rec_runs / n for n in names] + [rec_runs / "P1" / p for p in parts] + [rec_runs / "P1_merged"]
        for d in dirs:
            mism += compare_dirs(d, new_runs / d.relative_to(rec_runs))
        files = sum(1 for d in dirs for p in d.iterdir() if p.is_file())
        summary |= {"strategy_runs": len(names), "p1_parts": len(parts), "files_compared": files, "mismatches": mism}
        base = out / "base"
        base.mkdir(parents=True, exist_ok=True)
        for link, target in (("prepared", prepared), ("runs", new_runs)):
            if not (base / link).exists():
                (base / link).symlink_to(target)
        summary["report_sha256_rerun"], v_new = evaluator_report(base)
        summary["verdict_rerun_equal"] = v_new == (T2_BASE / "evaluation" / "verdict.txt").read_text()
    summary["report_sha256_recorded_runs"], v_rec = evaluator_report(T2_BASE)
    summary["verdict_recorded_equal"] = v_rec == (T2_BASE / "evaluation" / "verdict.txt").read_text()
    summary["closed_report_sha256"] = sha(T2_BASE / "evaluation" / "report.json")
    summary["closed_report_expected"] = CLOSED_REPORT_SHA256
    ok = (summary["closed_report_sha256"] == CLOSED_REPORT_SHA256
          and summary["report_sha256_recorded_runs"] == CLOSED_REPORT_SHA256 and summary["verdict_recorded_equal"]
          and (a.skip_runs or (not summary["mismatches"] and summary["report_sha256_rerun"] == CLOSED_REPORT_SHA256
                               and summary["verdict_rerun_equal"])))
    summary["identical"] = ok
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "mismatches"} | {"n_mismatches": len(summary.get("mismatches", []))},
                     sort_keys=True, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
