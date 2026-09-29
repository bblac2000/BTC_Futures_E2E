"""트라이얼 #2 데이터 핀 생성(K5 · advisor 단계 2 after #3) — `prepare` 단계 뒤 한 번.

    uv run python scripts/t2_make_pins.py --manifest var/backtest/t2/IS/prepared/manifest.json --row 39 --date YYYY-MM-DD

- `strategies/trial02/data_pins.json` = {"raw": 원시 5개, "prepared": 산출물 4개}(매니페스트 값 그대로 · 이미 있으면 거부).
- 레지스트리 핀 행(문자열)을 표준출력으로 낸다: 핀 파일 경로 문구 **정확히 한 번** · `이름=64hex` 토큰 9개뿐(매니페스트 해시 토큰 없음).
- 낸 행과 핀을 `t2_provenance.check_pins_registry`(= `load_pins`가 쓰는 검사기)로 확인한 뒤에만 쓴다 — 사람이 행을
  레지스트리에 붙이고 커밋·푸시(사용자 체크포인트)한 뒤 `verify` 단계.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtest import prepare_t2 as PT  # noqa: E402
from backtest import t2_provenance as PV  # noqa: E402


def make(manifest_path: Path, *, row_no: int, date: str) -> tuple[dict[str, Any], str]:
    m = json.loads(manifest_path.read_text())
    pins = {"raw": {n: m["raw"][n] for n in PT.RAW_FILES}, "prepared": {n: m[n] for n in PT.PREPARED}}
    toks = " · ".join(f"{n}={h}" for n, h in {**pins["raw"], **pins["prepared"]}.items())
    row = (f"| {row_no} | {date} | **트라이얼 #2 데이터 핀**(append-only · verify·실행 전) | `{PV.PINS_REL}` | {toks} | "
           f"원시 캡처 1회(IS + 워밍업 21일) · 산출물은 원시에서 순수 빌드 | 🔒 확정 — 이 행과 핀 파일은 한 커밋 · 푸시 뒤 verify | "
           f"✅ 사용자 체크포인트(두 번째 푸시) |")
    PV.check_pins_registry(row + "\n", pins)
    return pins, row


def write(pins: dict[str, Any], target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"{target}가 이미 있다 — 핀은 한 번만")
    target.write_text(json.dumps(pins, sort_keys=True, indent=1) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--date", required=True)
    a = ap.parse_args(argv)
    pins, row = make(Path(a.manifest), row_no=a.row, date=a.date)
    write(pins, ROOT / PV.PINS_REL)
    print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
