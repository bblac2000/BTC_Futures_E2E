"""트라이얼 #4 정본 실행 진입점((g) 전반 · 규약 F75~F77 · D55) — 격리 실행기(`backtest.t4_stages`)가 subprocess로 띄운다.

**복사**: `strategies/trial03/run.py` @ 478ecdd의 이름공간 이식 — 바꾼 것: 암 S · L · 변형 이름 · 고정 로더가 (봉 · 펀딩 · 인쇄)를 준다 · 표준출력 키.

    python -m strategies.trial04.run --arm L|S --variant base|P2_print1|P2_print3|P3_invert --prepared DIR --evaluator-commit H --out DIR

- 관문: `t4_provenance.child_gate`(동결 H + 레지스트리 규약 행·동결 행 · 실행기의 T4_STAGE_ORIGIN 또는 단독 fetch) → 데이터 핀(커밋·푸시·레지스트리 행)
  → verify 영수증(= 현재 핀·H·지문) → 고정 로더로 준비 입력 → `harness.run_arm`(#69 규칙 · TC_V3) → `t4_outputs.write_run`.
- 실패 보존: 재생·마무리 검사 중 실패(`RunFailure`) → out에 `_failure_events.jsonl` · `_failure_state.json` · `_failure_error.txt`, rc 7 ·
  전략이 생기기 전 실패(관문·입력·규칙) → `_failure_error.txt`, rc 8. 🚫 표준출력 = 개수만(손익·평균 없음).
"""
from __future__ import annotations

import argparse
import decimal
import json
from pathlib import Path

from strategies.trial04.strategy import Variant

ROOT = Path(__file__).resolve().parent.parent.parent
VARIANTS = {"base": Variant(), "P2_print1": Variant(delay=1), "P2_print3": Variant(delay=3), "P3_invert": Variant(invert=True)}


def _write_error(out: Path, e: BaseException) -> None:
    from backtest import t4_outputs as O
    O.write_error(out, e)


def main(argv: list[str] | None = None) -> int:
    decimal.setcontext(decimal.Context())          # 프로세스 문맥 = 파이썬 기본(28자리) — 트라이얼 #2 방식(규약 36)
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["S", "L"])
    ap.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--evaluator-commit", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out, prepared = Path(a.out), Path(a.prepared)
    try:
        from backtest import prepare_t4 as PT
        from backtest import t4_provenance as PV
        from strategies.trial04.harness import RunFailure, complete_days, run_arm, v_days
        repo = PV.stage_repo()
        PV.child_gate(repo, a.evaluator_commit)
        pins, pc = PV.load_pins(repo, fetch_first=False)
        receipt = json.loads((prepared.parent / "_records" / "verify_receipt.json").read_text())
        PV.check_receipt(receipt, prepared=prepared, pins=pins, pins_c=pc, commit=a.evaluator_commit, fp=PV.fingerprint(repo))
        bars, fundings, prints = PT.load_prepared_pinned(prepared, pins, PT.is_range(), root=repo)
    except BaseException as e:
        _write_error(out, e)
        print(json.dumps({"arm": a.arm, "variant": a.variant, "failure": "pre_strategy"}))
        return 8
    try:
        run = run_arm(bars, fundings, prints, a.arm, VARIANTS[a.variant])
    except RunFailure as f:
        from backtest import t4_outputs as O
        state = O.write_run_failure(out, f.strategy, f.__cause__ or f)
        print(json.dumps({"arm": a.arm, "variant": a.variant, "failure": "run", "window_prints": state["window_prints"]}))
        return 7
    except BaseException as e:
        _write_error(out, e)
        print(json.dumps({"arm": a.arm, "variant": a.variant, "failure": "pre_strategy"}))
        return 8
    from backtest import t4_outputs as O
    from strategies.trial04 import anchor as A
    O.write_run(out, run, v_days(run.strategy, complete_days(bars)), tc_v3_sha256=A.TC_V3_SHA256,
                rules_sha256=A.RULES_SNAPSHOT_SHA256)
    s = run.strategy
    print(json.dumps({"arm": a.arm, "variant": a.variant, "n_trades": len(run.trades), "window_prints": s.window_prints,
                      "candidates": s.funnel["candidate"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
