"""감사 명령(단위 테스트 밖) — 트라이얼 #2가 고정한 트라이얼 #1 SR̂ 두 값이 원 report.json과 같은지 확인한다.

    uv run python scripts/audit_trial01_sr.py [report.json 경로]

기본 경로 `var/backtest/IS/step_e/report.json`(git 밖). 파일 SHA256이 앵커 값과 같고 GB.sr_A·sr_B가 상수와 같으면 exit 0.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from strategies.trial02 import anchor as A  # noqa: E402


def main(argv: list[str]) -> int:
    p = Path(argv[0]) if argv else ROOT / "var" / "backtest" / "IS" / "step_e" / "report.json"
    raw = p.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    gb = json.loads(raw)["GB"]
    ok = sha == A.TRIAL01_REPORT_SHA256 and gb["sr_A"] == A.SR_1A and gb["sr_B"] == A.SR_1B
    print(json.dumps({"path": str(p), "sha256_ok": sha == A.TRIAL01_REPORT_SHA256,
                      "sr_A_ok": gb["sr_A"] == A.SR_1A, "sr_B_ok": gb["sr_B"] == A.SR_1B}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
