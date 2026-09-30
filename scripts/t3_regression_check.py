"""트라이얼 #3 회귀 검사(트라이얼 #4 단계 (b) · 사용자 GO 2026-09-30) — **현재 코드**로 트라이얼 #3 IS 실행 8개와 P1 조각 16개·병합 2개를
다시 계산해 `docs/trials/trial_03/records/`에 기록된 출력 SHA256과 바이트 대조한다.

    uv run python scripts/t3_regression_check.py --out <스크래치 디렉터리>

- 진단 도구다: 트라이얼 #3 관문(`stage_repo` · `child_gate` · 핀 커밋 · 영수증 · 단계 기록)을 거치지 않고 정본 함수를 직접 부른다
  (트라이얼 #3 판정 문은 이 커밋부터 설계상 거부한다 — 닫힌 트라이얼 · 한 번만). `var/t3/IS`는 읽기만 · 스크래치 디렉터리에만 쓴다.
- 준비 입력 = `prepare_t3.load_prepared_pinned(var/t3/IS/prepared, strategies/trial03/data_pins.json, is_range())`(핀 대조 + 원시 재해시).
- 실행: `strategies.trial03.run`과 같은 문맥(`decimal.setcontext(decimal.Context())`)·같은 함수(`harness.run_arm` → `t3_outputs.write_run`).
- P1: **다시 돌린** 기본 실행의 트레이드를 원판으로 `p1_t3.run_range`(기록된 분할 그대로) → `write_p1_part_to` · 병합 `write_p1_merged`.
- 트라이얼 #3 파일은 수정하지 않는다(읽기 전용 import).
"""
from __future__ import annotations

import argparse
import decimal
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

T3_BASE = ROOT / "var" / "t3" / "IS"
RECORDS = ROOT / "docs" / "trials" / "trial_03" / "records"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_out(out: Path) -> None:
    """스크래치 출력은 저장소 밖 · 아직 없는 경로여야 한다(Codex (b) before MAJOR 2) — 디렉터리를 만들기 전에 거부."""
    root = ROOT.resolve()
    if out == root or root in out.parents or out.exists():
        raise SystemExit(f"--out {out}: 저장소 안이거나 이미 있다 — 저장소 밖의 새 스크래치 경로만")


def compare(d: Path, want: dict[str, str]) -> dict[str, object]:
    have = {p.name: sha(p) for p in sorted(d.iterdir()) if p.is_file()}
    return {"files": len(want), "names_equal": sorted(have) == sorted(want),
            "mismatches": sorted(n for n in want if have.get(n) != want[n]) + sorted(set(have) - set(want))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    decimal.setcontext(decimal.Context())
    from backtest import p1_t3 as P1
    from backtest import prepare_t3 as PT
    from backtest import t3_outputs as O
    from strategies.trial03 import anchor as A
    from strategies.trial03.harness import complete_days, run_arm, v_days
    from strategies.trial03.run import VARIANTS
    out = Path(a.out).resolve()
    check_out(out)
    base = out / "t3_rerun"
    base.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    pins = json.loads((ROOT / "strategies" / "trial03" / "data_pins.json").read_text())
    bars, fundings, oi, unusable = PT.load_prepared_pinned(T3_BASE / "prepared", pins, PT.is_range(), root=ROOT)
    res: dict[str, object] = {"runs": {}, "p1_parts": {}, "p1_merged": {}}
    for arm in ("L", "S"):
        for var, v in VARIANTS.items():
            run = run_arm(bars, fundings, oi, unusable, arm, v)
            d = O.run_dir(base, arm, var)
            O.write_run(d, run, v_days(run.strategy, complete_days(bars)), tf_v1_sha256=A.TF_V1_SHA256,
                        rules_sha256=A.RULES_SNAPSHOT_SHA256)
            want = json.loads((RECORDS / "runs" / f"{arm}_{var}.json").read_text())["run"]["outputs"]
            res["runs"][f"{arm}_{var}"] = compare(d, want)                                  # type: ignore[index]
    partition = json.loads((RECORDS / "p1" / "p1_partition.json").read_text())
    for arm in ("L", "S"):
        trades, _, _ = O.read_run(O.run_dir(base, arm, "base"), arm, "base")          # 다시 돌린 원판
        for lo, hi in partition:
            part = P1.run_range(arm, trades, bars, fundings, lo, hi)
            d = O.p1_parts_dir(base, arm) / f"part_{lo:03d}_{hi:03d}"
            O.write_p1_part_to(d, part)
            want = json.loads((RECORDS / "p1" / f"P1_{arm}_{lo:03d}_{hi:03d}.json").read_text())["run"]["outputs"]
            res["p1_parts"][f"P1_{arm}_{lo:03d}_{hi:03d}"] = compare(d, want)              # type: ignore[index]
        O.write_p1_merged(base, arm, O.read_p1_parts(base, arm))
        want = json.loads((RECORDS / "p1" / f"P1_merge_{arm}.json").read_text())["outputs"]
        res["p1_merged"][arm] = compare(base / "runs" / f"{arm}_P1_merged", want)          # type: ignore[index]
    groups = [res["runs"], res["p1_parts"], res["p1_merged"]]
    files = sum(r["files"] for g in groups for r in g.values())                             # type: ignore[union-attr]
    mism = sum(len(r["mismatches"]) for g in groups for r in g.values())                   # type: ignore[union-attr]
    res |= {"files_compared": files, "mismatches": mism, "identical": mism == 0 and all(
        r["names_equal"] for g in groups for r in g.values()), "wall_s": round(time.time() - t0, 1)}   # type: ignore[union-attr]
    (out / "summary.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    lst = sorted(p for p in base.rglob("*") if p.is_file())
    (out / "rerun_sha256.txt").write_text("".join(f"{sha(p)}  {p.relative_to(base)}\n" for p in lst))
    print(json.dumps({k: res[k] for k in ("files_compared", "mismatches", "identical", "wall_s")}))
    return 0 if res["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
