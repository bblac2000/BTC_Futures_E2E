"""트라이얼 #2 정본 실행 진입점(단계 2f F3) — 격리 러너가 subprocess로 띄운다(`backtest.t2_stages`).

    python -m strategies.trial02.run --variant A|B|P2_delay1|P2_delay5|P3_invert|P4_drawNNN --prepared DIR --out DIR

- 입력: `prepare_t2` 산출물(DIR) + **커밋·푸시된** `strategies/trial02/data_pins.json`(G7 — 경로 인자 없음) → `harness.run_prepared_is`
  (해시 전용 로더 · IS + 21일 · V_A/V_B 계산 · #36 규칙 · 고정 limits·E_ref).
- 변형 이름 ↔ `Variant`는 고정 표(G4). 출력: trades.jsonl · crosses.jsonl(final_reason) · days.jsonl · validity.json · meta.json.
  🚫 지갑·수익 집계 없음 · 표준출력 = 개수만.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from backtest.replay import write_jsonl
from strategies.trial02 import anchor as A
from strategies.trial02 import harness as H
from strategies.trial02.strategy import Variant

ROOT = Path(__file__).resolve().parent.parent.parent
FIXED = {"A": Variant("A"), "B": Variant("B"), "P2_delay1": Variant("A", delay=1), "P2_delay5": Variant("A", delay=5),
         "P3_invert": Variant("A", invert=True)}


def variant_for(name: str) -> Variant:
    if name in FIXED:
        return FIXED[name]
    m = re.fullmatch(r"P4_draw(\d{3})", name)
    if m and 0 <= int(m.group(1)) < A.P4_DRAWS:
        return Variant("A", p4_draw=int(m.group(1)))
    raise ValueError(f"등록되지 않은 변형 이름 {name}")


def variant_meta(v: Variant) -> dict[str, Any]:
    return {"arm": v.arm, "delay": v.delay, "invert": v.invert, "p4_draw": v.p4_draw}


def execute(name: str, prepared: Path, out: Path, pins: dict[str, Any], pins_commit: str,
            gate: dict[str, Any] | None = None, head: str | None = None) -> dict[str, Any]:
    v = variant_for(name)
    run, validity = H.run_prepared_is(prepared, pins, v)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "trades.jsonl", run.result.trades)
    write_jsonl(out / "crosses.jsonl", run.crosses)
    write_jsonl(out / "days.jsonl", [x for x in run.strategy.log if x["event"] == "day"])
    (out / "validity.json").write_text(json.dumps(validity.as_dict(), sort_keys=True) + "\n")
    assert run.result.open_at_end is None, "창 끝 열린 포지션(23:59 청산 규칙 위반)"
    import hashlib
    meta = {"variant_name": name, "variant": variant_meta(v), "bo_v1_sha256": A.BO_V1_SHA256, "pins_commit": pins_commit,
            "pins": pins, "manifest_sha256": hashlib.sha256((prepared / "manifest.json").read_bytes()).hexdigest(),
            "git_head": head, "gate": gate,
            "rules_snapshot_sha256": A.RULES_SNAPSHOT_SHA256, "n_trades": len(run.result.trades),
            "n_first_cross": len(run.crosses), "reason_counts": dict(sorted(Counter(str(c["final_reason"]) for c in run.crosses).items())),
            "n_v_a": len(validity.v_a), "n_v_b": len(validity.v_b)}
    (out / "meta.json").write_text(json.dumps(meta, sort_keys=True, indent=1) + "\n")
    return meta


def main(argv: list[str] | None = None) -> int:
    import decimal
    decimal.setcontext(decimal.Context())          # 프로세스 문맥 = 파이썬 기본(28자리 HALF_EVEN) — import 부작용과 무관하게 결정론
    from backtest import t2_provenance as PV
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from backtest.t2_stages import gate_cli
    gate = gate_cli(Path(a.prepared))                          # 판정기 푸시 · 핀 · verify 기록·영수증 · 지문
    pins, pc = PV.load_pins(ROOT, fetch=os.environ.get("T2_NO_FETCH") != "1")
    meta = execute(a.variant, Path(a.prepared), Path(a.out), pins, pc, gate=gate, head=PV.head(ROOT))
    print(json.dumps({k: meta[k] for k in ("variant_name", "n_trades", "n_first_cross", "n_v_a", "n_v_b")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
