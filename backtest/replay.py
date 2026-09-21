"""격리 실행 러너 + verbatim 기록기(단계 2a · 프로토콜 §5 "정본 전략 코드를 subprocess로 그대로 실행").

- 러너는 전략 모듈을 **import하지 않는다** — `python -m <module> <args>`로 띄우고, 전략이 쓴 파일(JSONL·JSON)만 읽는다.
  `assert_not_imported`가 이를 검사한다(측정용 재구현·함수 직접 호출로 새는 것을 막는다).
- 기록기는 명령·종료 코드·stdout/stderr·출력 파일 SHA256·git HEAD·파이썬/numpy 버전을 **그대로** 남긴다.
  재구성된 출력(에이전트가 결과를 요약해 다시 쓴 것)은 하드 실패 — 기록기는 원본 파일의 해시로만 결과를 가리킨다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class RunRecord:
    module: str
    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    started_utc: str
    ended_utc: str
    git_head: str
    python: str
    numpy: str
    outputs: dict[str, str] = field(default_factory=dict)      # 파일명 → SHA256


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _git_head() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    return r.stdout.strip() + ("+dirty" if dirty else "")


def assert_not_imported(module: str) -> None:
    if module in sys.modules:
        raise AssertionError(f"러너 프로세스가 전략 모듈 {module}을 import했다 — 격리 실행 위반")


def run_isolated(module: str, args: list[str], out_dir: Path, *, timeout_s: float = 6 * 3600,
                 env: dict[str, str] | None = None) -> RunRecord:
    assert_not_imported(module)
    out_dir.mkdir(parents=True, exist_ok=True)
    import numpy
    started = _now()
    p = subprocess.run([sys.executable, "-m", module, *args, "--out", str(out_dir)], cwd=ROOT, capture_output=True,
                       text=True, timeout=timeout_s, env=env)
    rec = RunRecord(module, list(args), p.returncode, p.stdout, p.stderr, started, _now(), _git_head(),
                    platform.python_version(), numpy.__version__)
    for f in sorted(out_dir.iterdir()):
        if f.is_file():
            rec.outputs[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    assert_not_imported(module)
    return rec


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows))


def record_verbatim(path: Path, record: RunRecord, results: dict[str, Any]) -> str:
    """실행 기록 + 결과를 한 JSON으로(정렬 키 · 결정론적). 그 파일의 SHA256을 돌려준다."""
    body = json.dumps({"run": asdict(record), "results": results}, sort_keys=True, indent=1, ensure_ascii=False)
    path.write_text(body + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()
