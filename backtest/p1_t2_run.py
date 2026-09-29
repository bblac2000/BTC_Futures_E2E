"""트라이얼 #2 P1 귀무분포 CLI(단계 2f F4) — 격리 실행용. 사전등록 §4 P1 행 · `backtest.p1_t2`.

    python -m backtest.p1_t2_run --a-dir DIR --prepared DIR --draws lo-hi --out DIR
    python -m backtest.p1_t2_run --merge --parts-root DIR --expect FILE --out DIR

- 원판 Arm A `trades.jsonl`에서 **쌍 입력만**(trade_id · entry_ms · exit_ms · sl_dist) · 수익 필드는 읽지도 쓰지도 않는다.
- V_A = 고정된 준비 입력(data_pins · 해시 전용 로더)으로 다시 계산해 A의 `validity.json`과 같아야 한다.
- 원판 0건 → `p1_not_computable.json`(귀무분포 없음 · G5). 추출 d의 난수는 d마다 독립이라 범위로 나눠도 바이트가 같다.
- merge: 조각 출력 해시가 `--expect`(오케스트레이터가 조각 기록에서 뽑은 해시)와 같고 0..999를 정확히 한 번씩 덮어야 한다.
- 표준출력 = 개수만.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtest import days as DY
from backtest import p1_core as C
from backtest import p1_t2 as P
from backtest import prepare_t2 as PT
from backtest.replay import read_jsonl, write_jsonl
from strategies.trial02 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
PAIR_FIELDS = ("trade_id", "entry_ms", "exit_ms", "sl_dist")


def source_trades(path: Path) -> list[C.SourceTrade]:
    out = []
    for r in read_jsonl(path):
        missing = [k for k in PAIR_FIELDS if k not in r]
        if missing:
            raise ValueError(f"trades.jsonl에 P1 입력 필드 {missing}가 없다")
        out.append(C.SourceTrade(int(r["trade_id"]), int(r["entry_ms"]), int(r["exit_ms"]), Decimal(r["sl_dist"])))
    return out


def run_range(a_dir: Path, prepared: Path, pins: dict[str, Any], lo: int, hi: int, out: Path, *,
              expect_range: tuple[int, int] | None = None, days: tuple[int, int] | None = None) -> dict[str, Any]:
    from strategies.trial02.harness import load_rules
    rng = expect_range or PT.window_range()
    first, last = days or (A.IS_START_MS // A.DAY_MS, A.IS_END_MS // A.DAY_MS)
    bars_l, fundings = PT.load_prepared_pinned(prepared, pins, rng)
    v = DY.validity(bars_l, fundings, first, last)
    a_valid = json.loads((a_dir / "validity.json").read_text())
    if sorted(v.v_a) != a_valid["v_a"]:
        raise ValueError("V_A가 원판 Arm A 실행의 validity.json과 다르다")
    src = source_trades(a_dir / "trades.jsonl")
    out.mkdir(parents=True, exist_ok=True)
    if not src:
        (out / "p1_not_computable.json").write_text(json.dumps({"computable": False, "reason": "n_A=0"}) + "\n")
        (out / "p1_draws.json").write_text("[]")
        write_jsonl(out / "p1_null.jsonl", [])
        return {"draws": 0, "failed": 0, "source_trades": 0, "computable": False}
    bars = {b.open_ms: b for b in bars_l}
    rules = load_rules()
    draws = [P.draw(d, src, sorted(v.v_a), bars, rules) for d in range(lo, hi + 1)]
    null = [P.null_point(dr, bars, fundings, rules) for dr in draws if dr.ok]
    (out / "p1_draws.json").write_text(C.canonical_json(draws))
    write_jsonl(out / "p1_null.jsonl", null)
    return {"draws": len(draws), "failed": sum(1 for d in draws if not d.ok), "source_trades": len(src), "computable": True}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def merge(parts_root: Path, expect: dict[str, dict[str, str]], out: Path) -> dict[str, Any]:
    """expect = {조각 이름: {파일명: SHA256}} — 조각 기록에서 뽑은 값."""
    draws: list[dict[str, Any]] = []
    null: list[dict[str, Any]] = []
    not_computable = False
    for name, files in sorted(expect.items()):
        d = parts_root / name
        for f, sha in files.items():
            if not (d / f).exists() or _sha(d / f) != sha:
                raise ValueError(f"조각 {name}/{f}가 기록과 다르다")
        not_computable |= (d / "p1_not_computable.json").exists()
        draws += json.loads((d / "p1_draws.json").read_text())
        null += read_jsonl(d / "p1_null.jsonl")
    out.mkdir(parents=True, exist_ok=True)
    if not_computable:
        (out / "p1_not_computable.json").write_text(json.dumps({"computable": False, "reason": "n_A=0"}) + "\n")
        (out / "p1_draws.json").write_text("[]")
        write_jsonl(out / "p1_null.jsonl", [])
        return {"draws": 0, "failed": 0, "computable": False}
    ids = sorted(d["draw"] for d in draws)
    if ids != list(range(A.P1_DRAWS)):
        raise ValueError(f"P1 조각이 0..{A.P1_DRAWS - 1}을 정확히 한 번씩 덮지 않는다(개수 {len(ids)})")
    draws.sort(key=lambda d: d["draw"])
    null.sort(key=lambda r: r["draw"])
    (out / "p1_draws.json").write_text(json.dumps(draws, sort_keys=True, separators=(",", ":")))
    write_jsonl(out / "p1_null.jsonl", null)
    return {"draws": len(draws), "failed": sum(1 for d in draws if not d["ok"]), "computable": True}


def main(argv: list[str] | None = None) -> int:
    import decimal
    decimal.setcontext(decimal.Context())          # 프로세스 문맥 = 파이썬 기본(28자리 HALF_EVEN) — import 부작용과 무관하게 결정론
    from backtest import t2_provenance as PV
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-dir")
    ap.add_argument("--prepared")
    ap.add_argument("--draws")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--parts-root")
    ap.add_argument("--expect")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from backtest.t2_stages import gate_cli
    if a.merge:
        if not (a.parts_root and a.expect and a.prepared):
            ap.error("--merge에는 --parts-root · --expect · --prepared")
        gate_cli(Path(a.prepared))                              # 병합 직접 실행도 같은 문(Codex 2f r2 #5)
        print(json.dumps(merge(Path(a.parts_root), json.loads(Path(a.expect).read_text()), Path(a.out))))
        return 0
    if not (a.a_dir and a.prepared and a.draws):
        ap.error("--a-dir · --prepared · --draws lo-hi")
    lo, hi = (int(x) for x in a.draws.split("-"))
    if not 0 <= lo <= hi < A.P1_DRAWS:
        ap.error(f"--draws 범위는 0..{A.P1_DRAWS - 1}")
    gate_cli(Path(a.prepared))                                  # 직접 실행도 같은 문(Codex 2f after #5)
    pins, _ = PV.load_pins(ROOT)
    print(json.dumps(run_range(Path(a.a_dir), Path(a.prepared), pins, lo, hi, Path(a.out))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
