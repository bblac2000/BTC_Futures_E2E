"""트라이얼 #3 P1 조각 실행 진입점(단계 2 (g) · 계획 r3 K3′·K7·K9·K11) — 격리 실행기가 subprocess로 띄운다.

    python -m backtest.p1_t3_run --arm L|S --lo LO --hi HI --prepared DIR --evaluator-commit H --out runs/<arm>_P1/part_<lo>_<hi>

- 관문(동결·행·핀·영수증)은 `strategies.trial03.run`과 같다 · 원판 = 그 암 기본 실행 산출물(`t3_outputs.read_run`) · `p1_t3.run_range`(실행 경로).
- 실패 보존: `P1Failure` → out에 `_failure_draws.json`(끝난 추출) · `_failure_null.jsonl` · `_failure_error.txt`, rc 7 · 그 전 실패 → rc 8.
  🚫 표준출력 = 개수만.
"""
from __future__ import annotations

import argparse
import decimal
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _write_error(out: Path, e: BaseException) -> None:
    from backtest import t3_outputs as O
    O.write_error(out, e)


def main(argv: list[str] | None = None) -> int:
    decimal.setcontext(decimal.Context())
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["L", "S"])
    ap.add_argument("--lo", required=True, type=int)
    ap.add_argument("--hi", required=True, type=int)
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--evaluator-commit", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out, prepared = Path(a.out), Path(a.prepared)
    try:
        from backtest import p1_t3 as P1
        from backtest import prepare_t3 as PT
        from backtest import t3_outputs as O
        from backtest import t3_provenance as PV
        repo = PV.stage_repo()
        PV.child_gate(repo, a.evaluator_commit)
        pins, pc = PV.load_pins(repo, fetch_first=False)
        base = prepared.parent
        receipt = json.loads((base / "_records" / "verify_receipt.json").read_text())
        fp = PV.fingerprint(repo)
        PV.check_receipt(receipt, prepared=prepared, pins=pins, pins_c=pc, commit=a.evaluator_commit, fp=fp)
        if prepared.resolve() != (base / "prepared").resolve():
            raise O.ContractError(f"--prepared {prepared} ≠ {base / 'prepared'}")
        want = O.p1_parts_dir(base, a.arm) / f"part_{a.lo:03d}_{a.hi:03d}"
        if out.resolve() != want.resolve():
            raise O.ContractError(f"--out {out} ≠ {want}")
        from backtest.t3_stages import Stages
        st = Stages(a.evaluator_commit, base=base, repo=repo, fetch=False)
        expect = {"evaluator_commit": a.evaluator_commit, "fingerprint": fp, "pins_commit": pc,
                  "manifest_sha256": pins["manifest_sha256"], "variant": f"{a.arm}_base"}

        def base_ok() -> None:                                   # 원판 = 성공 기록과 해시가 같은 기본 실행(Codex (g) after #3)
            st.check_record(f"{a.arm}_base", st.run_job(a.arm, "base"), expect)
        base_ok()
        trades, _, _ = O.read_run(O.run_dir(base, a.arm, "base"), a.arm, "base")
        bars, fundings, _, _ = PT.load_prepared_pinned(prepared, pins, PT.is_range(), root=repo)
    except BaseException as e:
        _write_error(out, e)
        print(json.dumps({"arm": a.arm, "lo": a.lo, "hi": a.hi, "failure": "pre_run"}))
        return 8
    try:
        part = P1.run_range(a.arm, trades, bars, fundings, a.lo, a.hi)
    except P1.P1Failure as f:
        O.write_p1_failure(out, f.draws, f.null, f.__cause__ or f)
        print(json.dumps({"arm": a.arm, "lo": a.lo, "hi": a.hi, "failure": "p1", "draws_done": len(f.draws)}))
        return 7
    except BaseException as e:
        _write_error(out, e)
        print(json.dumps({"arm": a.arm, "lo": a.lo, "hi": a.hi, "failure": "pre_run"}))
        return 8
    try:
        base_ok()                                                # 계산 뒤 쓰기 전에 다시
    except BaseException as e:
        _write_error(out, e)
        print(json.dumps({"arm": a.arm, "lo": a.lo, "hi": a.hi, "failure": "base_changed"}))
        return 8
    O.write_p1_part_to(out, part)
    ok = sum(1 for d in json.loads(part.draws_json) if d["ok"])
    print(json.dumps({"arm": a.arm, "lo": a.lo, "hi": a.hi, "n_source": part.n_source, "draws": a.hi - a.lo + 1, "ok": ok},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
