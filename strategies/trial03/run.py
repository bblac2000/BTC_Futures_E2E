"""트라이얼 #3 정본 실행 진입점(단계 2 (g) · 계획 r3 K3′·K7·K11) — 격리 실행기(`backtest.t3_stages`)가 subprocess로 띄운다.

    python -m strategies.trial03.run --arm L|S --variant base|P2_delay1|P2_delay5|P3_invert --prepared DIR --evaluator-commit H --out DIR

- 관문: `t3_provenance.child_gate`(동결 H + 레지스트리 행 #52·#53 · 실행기의 T3_STAGE_ORIGIN 또는 단독 fetch) → 데이터 핀(커밋·푸시·레지스트리 행)
  → verify 영수증(= 현재 핀·H·지문) → 고정 로더로 준비 입력 → `harness.run_arm`(#48 규칙 · TF_V1) → `t3_outputs.write_run`.
- 실패 보존: 재생·마무리 검사 중 실패(`RunFailure`) → out에 `_failure_events.jsonl` · `_failure_state.json` · `_failure_error.txt`, rc 7 ·
  전략이 생기기 전 실패(관문·입력·규칙) → `_failure_error.txt`, rc 8. 🚫 표준출력 = 개수만(손익·평균 없음).
"""
from __future__ import annotations

import argparse
import decimal
import json
from pathlib import Path

from strategies.trial03.strategy import Variant

ROOT = Path(__file__).resolve().parent.parent.parent
VARIANTS = {"base": Variant(), "P2_delay1": Variant(delay=1), "P2_delay5": Variant(delay=5), "P3_invert": Variant(invert=True)}


def _write_error(out: Path, e: BaseException) -> None:
    from backtest import t3_outputs as O
    O.write_error(out, e)


def main(argv: list[str] | None = None) -> int:
    decimal.setcontext(decimal.Context())          # 프로세스 문맥 = 파이썬 기본(28자리) — 트라이얼 #2 방식(규약 36)
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["L", "S"])
    ap.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--evaluator-commit", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out, prepared = Path(a.out), Path(a.prepared)
    try:
        from backtest import prepare_t3 as PT
        from backtest import t3_provenance as PV
        from strategies.trial03.harness import RunFailure, complete_days, run_arm, v_days
        repo = PV.stage_repo()
        PV.child_gate(repo, a.evaluator_commit)
        pins, pc = PV.load_pins(repo, fetch_first=False)
        receipt = json.loads((prepared.parent / "_records" / "verify_receipt.json").read_text())
        PV.check_receipt(receipt, prepared=prepared, pins=pins, pins_c=pc, commit=a.evaluator_commit, fp=PV.fingerprint(repo))
        bars, fundings, oi, unusable = PT.load_prepared_pinned(prepared, pins, PT.is_range(), root=repo)
    except BaseException as e:
        _write_error(out, e)
        print(json.dumps({"arm": a.arm, "variant": a.variant, "failure": "pre_strategy"}))
        return 8
    try:
        run = run_arm(bars, fundings, oi, unusable, a.arm, VARIANTS[a.variant])
    except RunFailure as f:
        from backtest import t3_outputs as O
        state = O.write_run_failure(out, f.strategy, f.__cause__ or f)
        print(json.dumps({"arm": a.arm, "variant": a.variant, "failure": "run", "window_bars": state["window_bars"]}))
        return 7
    except BaseException as e:
        _write_error(out, e)
        print(json.dumps({"arm": a.arm, "variant": a.variant, "failure": "pre_strategy"}))
        return 8
    from backtest import t3_outputs as O
    from strategies.trial03 import anchor as A
    O.write_run(out, run, v_days(run.strategy, complete_days(bars)), tf_v1_sha256=A.TF_V1_SHA256,
                rules_sha256=A.RULES_SNAPSHOT_SHA256)
    s = run.strategy
    print(json.dumps({"arm": a.arm, "variant": a.variant, "n_trades": len(run.trades), "window_bars": s.window_bars,
                      "qualified": s.funnel["qualified"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
