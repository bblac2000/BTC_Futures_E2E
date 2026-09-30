"""트라이얼 #3 실행 출처(단계 2 (g) HALF 1 · 계획 r2 K1~K5) — 동결 · 레지스트리 행 관문 · 데이터 핀 · verify 영수증.

- 동결 집합(판정을 바꿀 수 있는 코드 전부): `FREEZE_FILES` + `FREEZE_GLOBS` · 지문 = 정렬된 (경로, SHA256) 목록의 SHA256.
- `require_frozen(repo, H)`: 작업 트리 깨끗 · H ⊂ HEAD ∧ H ⊂ origin/main · 동결 파일 집합과 바이트가 H와 지금 같다.
- `require_rows(repo, H)`: origin/main의 레지스트리에 `t3_conventions=` 행(#52) 정확히 하나 = 규약 파일 SHA256(지금) · `t3_freeze_H=` 행(#53)
  정확히 하나 = H · `t3_freeze_manifest=` = 동결 목록 파일 SHA256(지금) · `t3_fingerprint=` = 지문(지금) = H 트리의 지문 · 목록 파일의
  파일별 해시 = 지금 · 규약 파일·목록 파일은 origin/main과 지금이 같다.
- 데이터 핀(`strategies/trial03/data_pins.json` · .json이라 동결 집합 밖): {manifest_sha256, raw_inventory_sha256, prepared{…},
  oi_unusable_total, oi_unusable_is_slots, is_grid_slots} · raw_inventory = UTF-8 `"".join(f"{name}={sha}\\n" for name in sorted(raw))`의 SHA256 ·
  `load_pins`: 추적·깨끗·푸시 · 핀 커밋의 레지스트리에 핀 경로를 담은 행 정확히 하나 · 그 행의 `t3_manifest=`·`t3_raw_inventory=`·
  `t3_prepared/<이름>=` 토큰 = 파일.
- verify 영수증: H · 지문 · 핀 커밋 · 매니페스트·원시 목록·산출물 해시 — 이후 모든 단계와 판정기가 대조한다.
- 레지스트리 #54 버전화: 동결 행 키 v1 = `t3_freeze_H`·`t3_freeze_manifest`·`t3_fingerprint` · v≥2 = `_v<n>` 접미어 + 승인 행
  `t3_freeze_auth_v<n>=<이전 H>` · 버전 1..N을 모두 각자의 H로 검사 · 최신 N만 판정기 커밋(`freeze_versions` · `_check_version`).
git 호출은 `repo`를 받는다(테스트는 임시 저장소) · 읽기 명령과 `fetch`만.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PINS_REL = "strategies/trial03/data_pins.json"
REGISTRY_REL = "docs/trial_registry.md"
CONVENTIONS_REL = "docs/trials/trial_03_conventions.md"
FREEZE_MANIFEST_REL = "docs/trials/trial_03_freeze_manifest.json"
EVALUATOR_FILE = "backtest/evaluate_t3.py"
FREEZE_FILES = tuple(f"backtest/{n}.py" for n in (
    "evaluate_t3", "verdict_t3", "t3_outputs", "t3_provenance", "t3_stages", "p1_t3", "p1_t3_run", "stats", "stats_t2", "p1_core",
    "placebo_exec", "engine_replay", "returns", "data", "replay", "prepare_t3", "prepare_t2")) + ("pyproject.toml", "uv.lock")
FREEZE_GLOBS = ("strategies/trial03/*.py", "paper/*.py", "sizing/*.py", "exchange/*.py")
PREPARED_PIN_FILES = ("bars_1m.parquet", "funding.json", "source_audit.json", "kline_close_daily.json", "oi_5m.json", "oi_unusable.json")


class ProvenanceError(RuntimeError):
    pass


def _git(repo: Path, *a: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    return _sha_bytes(p.read_bytes())


# ── 동결 ────────────────────────────────────────────────────────────────────
def freeze_set(repo: Path) -> set[str]:
    out = set(FREEZE_FILES)
    for g in FREEZE_GLOBS:
        out |= {str(p.relative_to(repo)) for p in repo.glob(g)}
    return out


def freeze_set_at(repo: Path, commit: str) -> set[str]:
    out = set(FREEZE_FILES)
    for g in FREEZE_GLOBS:
        d, pat = g.rsplit("/", 1)
        names = _git(repo, "ls-tree", "--name-only", f"{commit}:{d}").stdout.split()
        out |= {f"{d}/{n}" for n in names if Path(n).match(pat)}
    return out


def _fp(rows: list[list[Any]]) -> str:
    return _sha_bytes(json.dumps(rows, separators=(",", ":")).encode())


def file_hashes(repo: Path) -> dict[str, str | None]:
    return {f: (sha_file(repo / f) if (repo / f).exists() else None) for f in sorted(freeze_set(repo))}


def file_hashes_at(repo: Path, commit: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for f in sorted(freeze_set_at(repo, commit)):
        r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{f}"], capture_output=True)
        out[f] = _sha_bytes(r.stdout) if r.returncode == 0 else None
    return out


def fingerprint(repo: Path = ROOT) -> str:
    return _fp([[k, v] for k, v in file_hashes(repo).items()])


def fingerprint_at(repo: Path, commit: str) -> str:
    return _fp([[k, v] for k, v in file_hashes_at(repo, commit).items()])


def _all_present(files: dict[str, str | None], where: str) -> None:
    missing = [f for f, h in files.items() if h is None]
    if missing:
        raise ProvenanceError(f"동결 집합 파일이 {where}에 없다: {missing[:5]}")


def freeze_manifest(repo: Path, commit: str) -> dict[str, Any]:
    files = file_hashes_at(repo, commit)
    _all_present(files, f"커밋 {commit}")
    return {"H": commit, "files": files, "fingerprint": _fp([[k, v] for k, v in files.items()])}


def fetch(repo: Path) -> None:
    if _git(repo, "fetch", "--quiet", "origin").returncode != 0:
        raise ProvenanceError("git fetch 실패")


def require_frozen(repo: Path, commit: str, *, fetch_first: bool = True) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        raise ProvenanceError(f"판정기 커밋 형식: {commit!r}")
    if fetch_first:
        fetch(repo)
    if _git(repo, "status", "--porcelain").stdout.strip():
        raise ProvenanceError("작업 트리가 깨끗하지 않다")
    for ref in ("HEAD", "origin/main"):
        if _git(repo, "merge-base", "--is-ancestor", commit, ref).returncode != 0:
            raise ProvenanceError(f"판정기 커밋 {commit}가 {ref}의 조상이 아니다(푸시 전 실행 금지)")
    if _git(repo, "cat-file", "-e", f"{commit}:{EVALUATOR_FILE}").returncode != 0:
        raise ProvenanceError(f"커밋 {commit}에 {EVALUATOR_FILE}가 없다")
    now, then = file_hashes(repo), file_hashes_at(repo, commit)
    _all_present(now, "작업 트리")
    _all_present(then, f"커밋 {commit}")
    if set(now) != set(then):
        raise ProvenanceError(f"동결 파일 집합이 커밋 {commit}와 다르다: {sorted(set(now) ^ set(then))[:5]}")
    bad = [f for f in now if now[f] != then[f]]
    if bad:
        raise ProvenanceError(f"동결 파일 {bad[0]}가 판정기 커밋 {commit} 뒤에 바뀌었다")


# ── 레지스트리 행 관문(K2) ───────────────────────────────────────────────────
def _tokens(line: str) -> dict[str, str]:
    """`t3_<키>=<값>` 토큰 — 키는 값 검사 전에 모은다: 같은 키가 두 번 → 거부 · 값이 40/64자리 16진이 아님 → 거부(Codex (g) after 재확인)."""
    out: dict[str, str] = {}
    for tok in re.split(r"[\s|·,`]+", line):
        m = re.fullmatch(r"(t3_[\w./-]+)=(.*)", tok)
        if not m:
            continue
        k, v = m.groups()
        if k in out:
            raise ProvenanceError(f"행에 {k} 토큰이 둘 이상")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", v):
            raise ProvenanceError(f"행의 {k} 값 형식이 틀렸다")
        out[k] = v
    return out


def _one_row(reg: str, key: str) -> dict[str, str]:
    rows = [ln for ln in reg.splitlines() if ln.startswith("|") and f"{key}=" in ln]
    if len(rows) != 1:
        raise ProvenanceError(f"레지스트리에 `{key}=` 행이 정확히 하나가 아니다({len(rows)})")
    return _tokens(rows[0])


def _at(repo: Path, ref: str, rel: str) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{rel}"], capture_output=True)
    if r.returncode != 0:
        raise ProvenanceError(f"{ref}:{rel} 없음")
    return r.stdout


def require_rows(repo: Path, commit: str, *, ref: str = "origin/main") -> dict[str, str]:
    """계획 r3 K2′ + 레지스트리 #54 버전화 — #52 행은 H 트리에 이미 있고 origin/main의 행과 같다 · 규약 바이트는 C1 = H = origin/main = 지금 ·
    동결 행은 버전 1..N 전부를 각자의 H에 대해 온전히 검사(`_check_version`) · 사슬(엄격한 조상 · 이전 행·목록·승인 행이 다음 H 트리에) ·
    최신 버전 N의 H = 판정기 커밋 · 지금 파일 = H_N 트리."""
    reg_ref = _at(repo, ref, REGISTRY_REL).decode("utf-8")
    reg_h = _at(repo, commit, REGISTRY_REL).decode("utf-8")
    conv = _one_row(reg_ref, "t3_conventions")
    if _one_row(reg_h, "t3_conventions") != conv:
        raise ProvenanceError("규약 행(#52)이 H 트리의 행과 다르다")
    c1 = conv.get("t3_conventions_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", c1) or _git(repo, "merge-base", "--is-ancestor", c1, commit).returncode != 0:
        raise ProvenanceError("규약 행의 t3_conventions_commit가 H의 조상이 아니다")
    b_now = (repo / CONVENTIONS_REL).read_bytes()
    if any(_at(repo, x, CONVENTIONS_REL) != b_now for x in (c1, commit, ref)) or conv.get("t3_conventions") != _sha_bytes(b_now):
        raise ProvenanceError("규약 파일 바이트가 C1·H·origin/main·지금 중 하나와 다르거나 행의 SHA256과 다르다")
    fz = freeze_versions(reg_ref)
    n_top = max(fz)
    for k in sorted(fz):
        _check_version(repo, ref, fz[k], k)
    for k in range(1, n_top):                                      # 사슬: 엄격한 조상 · 이전 행·목록이 다음 H 트리에 그대로
        a, b = fz[k], fz[k + 1]
        if a["H"] == b["H"] or _git(repo, "merge-base", "--is-ancestor", a["H"], b["H"]).returncode != 0:
            raise ProvenanceError(f"동결 v{k} H가 v{k + 1} H의 엄격한 조상이 아니다")
        reg_next = _at(repo, b["H"], REGISTRY_REL).decode("utf-8")
        if a["line"] not in reg_next.splitlines() or _at(repo, b["H"], a["manifest_rel"]) != (repo / a["manifest_rel"]).read_bytes():
            raise ProvenanceError(f"동결 v{k} 행·목록이 v{k + 1} H 트리에 그대로 있지 않다")
        if b["auth"] != a["H"] or b["auth_line"] not in reg_next.splitlines():
            raise ProvenanceError(f"동결 v{k + 1} 승인 행(t3_freeze_auth_v{k + 1})이 v{k} H를 가리키지 않거나 v{k + 1} H 트리에 없다")
    top = fz[n_top]
    if top["H"] != commit or file_hashes(repo) != top["files"]:
        raise ProvenanceError(f"최신 동결(v{n_top})의 H가 판정기 커밋이 아니거나 지금 파일이 그 H와 다르다")
    return {"conventions_sha256": _sha_bytes(b_now), "conventions_commit": c1, "freeze_manifest_sha256": top["manifest_sha256"],
            "fingerprint": top["fingerprint"], "freeze_version": str(n_top)}


_FREEZE_KEY = re.compile(r"t3_(freeze_H|freeze_manifest|fingerprint|freeze_auth)(?:_v([1-9][0-9]*))?")
_TRIPLE = ("freeze_H", "freeze_manifest", "fingerprint")


def manifest_rel(k: int) -> str:
    return FREEZE_MANIFEST_REL if k == 1 else FREEZE_MANIFEST_REL.replace(".json", f"_v{k}.json")


def freeze_versions(reg: str) -> dict[int, dict[str, Any]]:
    """레지스트리 #54 관문 버전화: 표 행의 토큰(엄격 파싱)에서만 버전을 찾는다. 키 허용 목록 — v1 = `t3_freeze_H` ·
    `t3_freeze_manifest` · `t3_fingerprint`(접미어 없음) · v≥2 = 같은 이름 + `_v<n>` · 승인 `t3_freeze_auth_v<n>`(n ≥ 2) ·
    그 밖의 `t3_freeze*`·`t3_fingerprint*` 키 → 거부 · 행마다 동결 계열 토큰만 (엄격하게) 파싱한다(`_freeze_tokens`). 버전마다 세 토큰을 모두 가진 행 정확히 하나(부분 세트 거부) · 버전 = {1..N} ·
    n ≥ 2마다 승인 행 정확히 하나(그 행에는 다른 동결 키 없음) · 짝 없는 승인 거부."""
    trip: dict[int, list[tuple[str, dict[str, str]]]] = defaultdict(list)
    auth: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for ln in reg.splitlines():
        if not ln.startswith("|"):
            continue
        fam: dict[int, dict[str, str]] = defaultdict(dict)
        for key, val in _freeze_tokens(ln).items():
            m = _FREEZE_KEY.fullmatch(key)
            if not m or m.group(2) == "1" or (m.group(1) == "freeze_auth" and m.group(2) is None):
                raise ProvenanceError(f"동결 키 형식이 틀렸다: {key}")
            n = int(m.group(2)) if m.group(2) else 1
            fam[n][m.group(1)] = val
        for n, d in fam.items():
            if set(d) == {"freeze_auth"} and n >= 2 and len(fam) == 1:
                auth[n].append((ln, d["freeze_auth"]))
            elif set(d) == set(_TRIPLE) and len(fam) == 1:
                trip[n].append((ln, d))
            else:
                raise ProvenanceError(f"동결 행이 버전 {n}의 온전한 세 토큰(또는 승인 하나)이 아니다: {sorted(d)}")
    if not trip:
        raise ProvenanceError("레지스트리에 동결 행이 없다")
    n_top = max(trip)
    if sorted(trip) != list(range(1, n_top + 1)) or any(len(v) != 1 for v in trip.values()):
        raise ProvenanceError(f"동결 버전이 1..N으로 이어지지 않거나 버전마다 행이 정확히 하나가 아니다: {sorted((k, len(v)) for k, v in trip.items())}")
    if sorted(auth) != list(range(2, n_top + 1)) or any(len(v) != 1 for v in auth.values()):
        raise ProvenanceError(f"승인 행이 버전 2..N마다 정확히 하나가 아니다: {sorted((k, len(v)) for k, v in auth.items())}")
    out: dict[int, dict[str, Any]] = {}
    for n, [(ln, d)] in trip.items():
        a_line, a_val = auth[n][0] if n >= 2 else ("", "")
        out[n] = {"H": d["freeze_H"], "manifest_sha256": d["freeze_manifest"], "fingerprint": d["fingerprint"], "line": ln,
                  "manifest_rel": manifest_rel(n), "auth": a_val, "auth_line": a_line}
    return out


def _freeze_tokens(line: str) -> dict[str, str]:
    """동결 계열(`t3_freeze*`·`t3_fingerprint*`) 토큰만 골라 엄격하게(같은 키 두 번 · 40/64 hex 아님 → 거부) — 같은 행의 다른 t3 토큰은
    보지 않는다(Codex (fix) A 재확인 MINOR · 다른 행·다른 토큰의 오타가 관문을 잠그지 않게)."""
    out: dict[str, str] = {}
    for tok in re.split(r"[\s|·,`]+", line):
        m = re.fullmatch(r"(t3_[\w./-]+)=(.*)", tok)
        if not m or not m.group(1).startswith(("t3_freeze", "t3_fingerprint")):
            continue
        k, v = m.groups()
        if k in out:
            raise ProvenanceError(f"행에 {k} 토큰이 둘 이상")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", v):
            raise ProvenanceError(f"행의 {k} 값 형식이 틀렸다")
        out[k] = v
    return out


def _check_version(repo: Path, ref: str, v: dict[str, Any], k: int) -> None:
    """버전 k 행 하나를 그 H에 대해 온전히(K2′): 목록 바이트 지금 = ref · SHA256 = 토큰 · 목록.H = H_k · 목록.files = H_k 트리 해시(전부
    있음) · 경로 집합 = H_k에서 평가한 동결 집합 · 목록.fingerprint = 토큰 = H_k 트리 지문."""
    rel = v["manifest_rel"]
    p = repo / rel
    if not p.exists():
        raise ProvenanceError(f"동결 v{k} 목록 파일이 없다: {rel}")
    b = p.read_bytes()
    if _at(repo, ref, rel) != b or v["manifest_sha256"] != _sha_bytes(b):
        raise ProvenanceError(f"동결 v{k} 행의 목록 해시·origin/main 바이트가 다르다")
    man = json.loads(b)
    files_h = file_hashes_at(repo, v["H"])
    _all_present(files_h, f"동결 v{k} H")
    fp_h = _fp([[a, h] for a, h in files_h.items()])
    if man.get("H") != v["H"] or man.get("files") != files_h or set(files_h) != freeze_set_at(repo, v["H"]) \
            or man.get("fingerprint") != fp_h or v["fingerprint"] != fp_h:
        raise ProvenanceError(f"동결 v{k} 목록·지문·파일 집합이 그 H 트리와 다르다")
    v["files"] = files_h


def require_running_code(repo: Path) -> None:
    """검사 대상 저장소의 동결 코드 = 지금 실행 중인 코드(ROOT) 바이트(Codex (g) after #1) — 실행기·판정기 입구에서."""
    if repo.resolve() != ROOT.resolve() and file_hashes(repo) != file_hashes(ROOT):
        raise ProvenanceError("검사 대상 저장소의 동결 코드가 실행 중인 코드와 다르다")


def stage_repo() -> Path:
    """자식 CLI가 검사할 저장소: 실행기가 띄웠으면(T3_STAGE_ORIGIN과 T3_STAGE_REPO 둘 다) 그 저장소 — 단 그 저장소의 동결 코드가 지금
    실행 중인 코드(ROOT)와 바이트 동일해야 한다(다른 코드를 가리키는 우회 차단) · 아니면 ROOT."""
    import os
    r, o = os.environ.get("T3_STAGE_REPO"), os.environ.get("T3_STAGE_ORIGIN")
    if not (r and o):
        return ROOT
    repo = Path(r).resolve()
    require_running_code(repo)
    return repo


def child_gate(repo: Path, commit: str) -> dict[str, str]:
    """하위 CLI 관문(계획 r3 K3′): 실행기가 넘긴 T3_STAGE_ORIGIN(= 실행기가 fetch한 origin/main)과 지금 origin/main이 같으면 fetch 생략,
    환경 변수가 없으면(단독 실행) 먼저 fetch. 그다음 동결·행 관문."""
    import os
    r = os.environ.get("T3_STAGE_ORIGIN")
    if r:
        if _git(repo, "rev-parse", "origin/main").stdout.strip() != r:
            raise ProvenanceError("실행기가 fetch한 origin/main과 지금이 다르다")
        require_frozen(repo, commit, fetch_first=False)
    else:
        require_frozen(repo, commit, fetch_first=True)
    return require_rows(repo, commit)


# ── 데이터 핀(K4) ───────────────────────────────────────────────────────────
def raw_inventory(raw: dict[str, str]) -> str:
    return _sha_bytes("".join(f"{k}={raw[k]}\n" for k in sorted(raw)).encode("utf-8"))


def make_pins(prepared: Path) -> dict[str, Any]:
    m = json.loads((prepared / "manifest.json").read_text())
    audit = json.loads((prepared / "source_audit.json").read_text())["oi"]
    return {"manifest_sha256": sha_file(prepared / "manifest.json"), "raw_inventory_sha256": raw_inventory(m["raw"]),
            "prepared": {k: m[k] for k in PREPARED_PIN_FILES}, "oi_unusable_total": audit["unusable_total"],
            "oi_unusable_is_slots": audit["unusable_is_slots"], "is_grid_slots": audit["is_grid_slots"]}


def pins_row_tokens(pins: dict[str, Any]) -> dict[str, str]:
    return {"t3_manifest": pins["manifest_sha256"], "t3_raw_inventory": pins["raw_inventory_sha256"],
            **{f"t3_prepared/{k}": v for k, v in pins["prepared"].items()}}


def check_pins_against_prepared(prepared: Path, pins: dict[str, Any]) -> dict[str, Any]:
    """매니페스트 SHA256 · 원시 목록 · 산출물 해시 · OI 개수가 핀과 같아야 한다. 반환 = 매니페스트."""
    m = json.loads((prepared / "manifest.json").read_text())
    if sha_file(prepared / "manifest.json") != pins["manifest_sha256"] or raw_inventory(m["raw"]) != pins["raw_inventory_sha256"] \
            or {k: m[k] for k in PREPARED_PIN_FILES} != pins["prepared"]:
        raise ProvenanceError("준비 산출물이 데이터 핀과 다르다")
    if make_pins(prepared) != pins:
        raise ProvenanceError("데이터 핀의 OI 개수가 준비 감사와 다르다")
    return m


def pins_commit(repo: Path) -> str:
    c = _git(repo, "log", "-1", "--format=%H", "--", PINS_REL).stdout.strip()
    if not c:
        raise ProvenanceError(f"{PINS_REL}가 커밋되지 않았다")
    return c


def load_pins(repo: Path, *, fetch_first: bool = True) -> tuple[dict[str, Any], str]:
    if fetch_first:
        fetch(repo)
    if _git(repo, "ls-files", "--error-unmatch", PINS_REL).returncode != 0:
        raise ProvenanceError(f"{PINS_REL}가 추적되지 않는다")
    if _git(repo, "diff", "--quiet", "HEAD", "--", PINS_REL).returncode != 0:
        raise ProvenanceError(f"{PINS_REL}에 커밋되지 않은 변경")
    c = pins_commit(repo)
    if _git(repo, "merge-base", "--is-ancestor", c, "origin/main").returncode != 0:
        raise ProvenanceError("데이터 핀 커밋이 origin/main에 없다")
    c_ref = _git(repo, "log", "-1", "--format=%H", "origin/main", "--", PINS_REL).stdout.strip()
    b = (repo / PINS_REL).read_bytes()
    if c_ref != c or _at(repo, "origin/main", PINS_REL) != b:
        raise ProvenanceError("origin/main의 데이터 핀(파일·마지막 변경 커밋)이 지금과 다르다")
    pins = json.loads(b)
    reg = _at(repo, c, REGISTRY_REL).decode("utf-8")
    rows = [ln for ln in reg.splitlines() if ln.startswith("|") and PINS_REL in ln]
    if len(rows) != 1:
        raise ProvenanceError(f"핀 커밋의 레지스트리에 `{PINS_REL}` 행이 정확히 하나가 아니다({len(rows)})")
    toks = {k: v for k, v in _tokens(rows[0]).items() if k.startswith(("t3_manifest", "t3_raw_inventory", "t3_prepared/"))}
    if toks != pins_row_tokens(pins):
        raise ProvenanceError("데이터 핀 행의 토큰이 data_pins.json과 다르다")
    return pins, c


# ── verify 영수증(K5) ───────────────────────────────────────────────────────
def make_receipt(pins: dict[str, Any], pins_c: str, commit: str, fp: str) -> dict[str, Any]:
    return {"evaluator_commit": commit, "fingerprint": fp, "pins_commit": pins_c, "manifest_sha256": pins["manifest_sha256"],
            "raw_inventory_sha256": pins["raw_inventory_sha256"], "prepared": pins["prepared"]}


def check_receipt(receipt: dict[str, Any], *, prepared: Path, pins: dict[str, Any], pins_c: str, commit: str, fp: str) -> None:
    if receipt != make_receipt(pins, pins_c, commit, fp):
        raise ProvenanceError("verify 영수증이 현재 핀·H·지문과 다르다")
    check_pins_against_prepared(prepared, pins)
