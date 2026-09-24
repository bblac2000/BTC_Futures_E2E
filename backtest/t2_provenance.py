"""트라이얼 #2 실행 출처(단계 2f G1·G3·G10~G13 · ops_log 2026-09-24 설계 r1 + G1~G13) — 모든 단계와 판정기가 쓰는 검사.

- G1 푸시 선행: 판정기 커밋 H가 HEAD의 조상 ∧ origin/main에 포함 ∧ 판정기 파일들이 H와 HEAD에서 바이트 동일 ∧ 작업 트리 깨끗.
- G10 코드 지문: 고정 파일 집합의 (경로, SHA256) 정렬 목록의 SHA256.
- G6/G7 핀: `strategies/trial02/data_pins.json`(git 추적 · 깨끗 · origin/main 포함)만 · 핀 커밋 = 그 파일을 마지막으로 바꾼 커밋.
- G11/G13 verify 영수증: 매니페스트 SHA256 · 핀 커밋 · 원시·산출물 해시 · 판정기 커밋 · 지문 — 이후 단계는 전부 현재 값과 같아야.
git 호출은 `repo` 경로를 받는다(테스트는 임시 저장소 · 읽기 전용 명령만 · `fetch`는 선택).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PINS_REL = "strategies/trial02/data_pins.json"
EVALUATOR_FILES = ("backtest/evaluate_t2.py", "backtest/stats.py")
FINGERPRINT_GLOBS = ("strategies/trial02/*.py", "paper/*.py", "sizing/*.py", "exchange/*.py")
FINGERPRINT_FILES = tuple(f"backtest/{n}.py" for n in (
    "engine_replay", "prepare_t2", "days", "p1_core", "p1_t2", "p1_t2_run", "placebo_exec", "returns", "data", "replay",
    "t2_stages", "t2_provenance", "evaluate_t2", "stats")) + ("pyproject.toml", "uv.lock")


class ProvenanceError(RuntimeError):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise ProvenanceError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p


def head(repo: Path = ROOT) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def require_clean(repo: Path = ROOT) -> None:
    if _git(repo, "status", "--porcelain").stdout.strip():
        raise ProvenanceError("작업 트리가 깨끗하지 않다")


def require_pushed(repo: Path, commit: str, *, remote_ref: str = "origin/main", fetch: bool = True) -> None:
    if fetch:
        _git(repo, "fetch", "--quiet", remote_ref.split("/")[0])        # 실패 → 오류(오래된 원격 참조로 통과하지 않는다)
    if _git(repo, "merge-base", "--is-ancestor", commit, "HEAD", check=False).returncode != 0:
        raise ProvenanceError(f"{commit}는 HEAD의 조상이 아니다")
    if _git(repo, "merge-base", "--is-ancestor", commit, remote_ref, check=False).returncode != 0:
        raise ProvenanceError(f"{commit}가 {remote_ref}에 없다(푸시 전)")


def require_evaluator_frozen(repo: Path, commit: str, *, remote_ref: str = "origin/main", fetch: bool = True) -> None:
    """G1: 판정기 커밋이 푸시됐고, 판정기 파일이 그 커밋과 지금 같다."""
    require_clean(repo)
    require_pushed(repo, commit, remote_ref=remote_ref, fetch=fetch)
    for f in EVALUATOR_FILES:
        then = _git(repo, "show", f"{commit}:{f}").stdout
        now = (repo / f).read_text(encoding="utf-8")
        if then != now:
            raise ProvenanceError(f"판정기 파일 {f}가 푸시된 커밋 {commit} 뒤에 바뀌었다")
    #  advisor 2f after #1: 판정기가 import하는 앵커·설정·실행 코드 전체가 푸시된 상태와 같아야 한다(§4-1 — 판정기 푸시 = 마지막 코드 변경)
    if fingerprint_at(repo, commit) != fingerprint(repo):
        raise ProvenanceError(f"실행 코드(지문 집합)가 푸시된 판정기 커밋 {commit} 뒤에 바뀌었다 — 새 판정기 커밋·푸시 필요")


def _fp_rows(rows: list[list[Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def fingerprint(repo: Path = ROOT) -> str:
    paths = set(FINGERPRINT_FILES)
    for g in FINGERPRINT_GLOBS:
        paths |= {str(p.relative_to(repo)) for p in repo.glob(g)}
    rows = []
    for rel in sorted(paths):
        p = repo / rel
        rows.append([rel, hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None])
    return _fp_rows(rows)


def fingerprint_at(repo: Path, commit: str) -> str:
    """커밋 시점 트리의 같은 파일 집합 지문(git show · 없으면 None)."""
    listed = _git(repo, "ls-tree", "-r", "--name-only", commit).stdout.split()
    import fnmatch
    paths = set(FINGERPRINT_FILES) | {p for p in listed for g in FINGERPRINT_GLOBS if fnmatch.fnmatch(p, g) and "/" not in
                                      p[len(g.split("*")[0]):]}
    rows = []
    for rel in sorted(paths):
        r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{rel}"], capture_output=True)
        rows.append([rel, hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else None])
    return _fp_rows(rows)


def pins_commit(repo: Path = ROOT) -> str:
    c = _git(repo, "log", "-1", "--format=%H", "--", PINS_REL).stdout.strip()
    if not c:
        raise ProvenanceError(f"{PINS_REL}가 커밋되지 않았다")
    return c


REGISTRY_REL = "docs/trial_registry.md"


def load_pins(repo: Path = ROOT, *, remote_ref: str = "origin/main", fetch: bool = True) -> tuple[dict[str, Any], str]:
    """G7·F6: 커밋·깨끗·푸시된 data_pins.json만 · 레지스트리 행에 같은 해시가 모두 적혀 있어야 한다."""
    _git(repo, "ls-files", "--error-unmatch", PINS_REL)
    if _git(repo, "diff", "--quiet", "HEAD", "--", PINS_REL, check=False).returncode != 0:
        raise ProvenanceError(f"{PINS_REL}에 커밋되지 않은 변경이 있다")
    c = pins_commit(repo)
    require_pushed(repo, c, remote_ref=remote_ref, fetch=fetch)
    pins = json.loads((repo / PINS_REL).read_text())
    reg = (repo / REGISTRY_REL).read_text(encoding="utf-8") if (repo / REGISTRY_REL).exists() else ""
    missing = [h for h in list(pins["raw"].values()) + list(pins["prepared"].values()) if h not in reg]
    if missing:
        raise ProvenanceError(f"레지스트리에 핀 해시가 없다: {missing[:3]}")
    return pins, c


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_receipt(prepared: Path, pins: dict[str, Any], pins_c: str, evaluator_commit: str, fp: str) -> dict[str, Any]:
    return {"manifest_sha256": sha_file(prepared / "manifest.json"), "pins_commit": pins_c, "raw": pins["raw"],
            "prepared": pins["prepared"], "evaluator_commit": evaluator_commit, "fingerprint": fp}


def check_receipt(receipt: dict[str, Any], *, prepared: Path, pins: dict[str, Any], pins_c: str, evaluator_commit: str,
                  fp: str) -> None:
    """G11·G13: 영수증 ↔ 현재 매니페스트 해시 · 핀 커밋 · 핀 값 · 판정기 커밋 · 지문."""
    want = make_receipt(prepared, pins, pins_c, evaluator_commit, fp)
    bad = [k for k in want if receipt.get(k) != want[k]]
    if bad:
        raise ProvenanceError(f"verify 영수증 불일치: {bad}")


def check_record(rec: dict[str, Any], *, out_dir: Path, expect: dict[str, Any], module: str | None = None,
                 args: list[str] | None = None, required: tuple[str, ...] = ()) -> None:
    """G3 이어 하기·판정기 입력: 명령(모듈·인자) · 출처 필드 · 필수 출력 파일 이름 · 기록된 모든 출력 해시가 지금과 같다."""
    prov = rec.get("provenance", {})
    bad = [k for k, v in expect.items() if prov.get(k) != v]
    if bad:
        raise ProvenanceError(f"실행 기록 출처 불일치: {bad}")
    if module is not None and rec["run"]["module"] != module:
        raise ProvenanceError(f"실행 기록 모듈 {rec['run']['module']} ≠ {module}")
    if args is not None and rec["run"]["args"] != args:
        raise ProvenanceError(f"실행 기록 인자 {rec['run']['args']} ≠ {args}")
    outs = rec["run"]["outputs"]
    if not outs:
        raise ProvenanceError("실행 기록에 출력이 없다")
    lacking = [f for f in required if f not in outs]
    if lacking:
        raise ProvenanceError(f"실행 기록에 필수 출력이 없다: {lacking}")
    for name, sha in outs.items():
        f = out_dir / name
        if not f.exists() or sha_file(f) != sha:
            raise ProvenanceError(f"출력 {name}이 없거나 바뀌었다")
    if rec["run"]["returncode"] != 0:
        raise ProvenanceError("실행이 실패했다(returncode ≠ 0)")
