"""로컬 shard 정리 — **Drive에 확실히 올라간 것만** 지운다(E2E `ops/prune_local.py` 규칙 이식 · 설계_prune확장 v2).

🔴 삭제 코드 — Codex 검토 대상. 안전장치(전부 테스트로 잠근다):
1. **allowlist store만**(`ops.data_stores.prunable`) · sqlite·대장·백업은 구조적으로 대상이 아니다.
2. **파일 단위 검증**: `rclone check --checksum --combined -`의 `=`만 삭제 후보. 그날에 `-`(원격 없음)·`*`(다름)·`!`(오류)가
   하나라도 있으면 **그날 전체 보류**(반쪽 디렉터리를 만들지 않는다).
3. 원격은 **읽기만**(check·lsf) — 원격 쓰기/삭제 명령이 이 파일에 없다.
4. 보존 창 `retention_days`(30) 안은 무조건 보존 · 한 번에 최대 `--max-days`일.
5. **기본 dry-run** — `--apply` 없이는 아무것도 지우지 않는다.
6. 삭제 **전에** 원격 md5(`rclone lsf --format hp`)를 받아 대장(`mark_pruned`)에 크기·md5와 함께 남긴다.
   **대장에 기록된 수 ≠ 지운 수**면 성공이 아니다(E2E #131 stage 0) → 마커 갱신 안 함 · 종료 코드 1.
7. 경로 봉쇄: 날짜 디렉터리는 store 루트(봇 `var/` 안)의 직속 자식 · 지우는 파일은 `.parquet`만 · 심볼릭 링크는 따라가지 않는다.
8. 0건 삭제·전부 보류면 `LAST_PRUNE.txt`를 갱신하지 않는다 → health의 prune 정체 경보(E2E DR03-A1).

사용: python -m ops.prune [--apply] [--max-days 7] [--var-dir var]   (원격 = env BTCFUT_DRIVE_REMOTE)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from data import manifest
from ops.data_stores import StoreConfigError, StoreSpec, prunable, remote_root, stores

ROOT = Path(__file__).resolve().parent.parent
MARKER = "LAST_PRUNE.txt"
Runner = Callable[..., Any]


def day_dirs(spec: StoreSpec) -> list[dt.date]:
    root = spec.local_path
    if not root.is_dir() or root.is_symlink():
        return []
    out = []
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.is_symlink():
            continue
        try:
            out.append(dt.date.fromisoformat(p.name))
        except ValueError:
            continue
    return out


def verified_files(spec: StoreSpec, day: dt.date, remote: str, *, runner: Runner, timeout_s: int = 900) -> tuple[set[str], dict]:
    src = spec.local_path / day.isoformat()
    dst = f"{remote}/{spec.remote_subpath}/{day.isoformat()}"
    cmd = ["rclone", "check", str(src), dst, "--checksum", "--combined", "-", "--checkers", "8"]
    try:
        r = runner(cmd, capture_output=True, text=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError) as e:
        return set(), {"error": f"rclone check 실패 {type(e).__name__}"}
    same: set[str] = set()
    stats: dict[str, Any] = {"=": 0, "-": 0, "+": 0, "*": 0, "!": 0}
    for line in (r.stdout or "").splitlines():
        if len(line) < 3 or line[1] != " ":
            continue
        mark, rel = line[0], line[2:]
        if mark in stats:
            stats[mark] += 1
        if mark == "=":
            same.add(rel)
    stats["rclone_rc"] = r.returncode
    if r.returncode not in (0, 1):                      # 1 = 차이 있음(정상 판정), 그 외 = 오류
        stats["error"] = (r.stderr or "")[-200:] or f"rc={r.returncode}"
    return same, stats


def remote_hashes(spec: StoreSpec, day: dt.date, remote: str, *, runner: Runner, timeout_s: int = 300) -> dict[str, str]:
    cmd = ["rclone", "lsf", "--format", "hp", "--files-only", "-R", f"{remote}/{spec.remote_subpath}/{day.isoformat()}"]
    try:
        r = runner(cmd, capture_output=True, text=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    if r.returncode != 0:
        return {}
    out = {}
    for ln in (r.stdout or "").splitlines():
        h, _, rel = ln.partition(";")
        if h and rel:
            out[rel.strip()] = h.strip()
    return out


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def prune_day(spec: StoreSpec, day: dt.date, remote: str, *, apply: bool, runner: Runner,
              mark_pruned: Callable[..., int] = manifest.mark_pruned) -> dict[str, Any]:
    src = spec.local_path / day.isoformat()
    res: dict[str, Any] = {"store": spec.id, "day": day.isoformat()}
    if src.is_symlink() or not _inside(src, spec.local_path) or src.parent.resolve() != spec.local_path.resolve():
        return res | {"skipped": "경로 봉쇄 위반"}
    same, stats = verified_files(spec, day, remote, runner=runner)
    if stats.get("error"):
        return res | {"skipped": f"검증 실패: {stats['error']}", "stats": stats}
    if stats.get("-", 0) or stats.get("*", 0) or stats.get("!", 0):
        return res | {"skipped": f"미검증 파일(없음 {stats['-']}·다름 {stats['*']}·오류 {stats['!']}) — 그날 전체 보류",
                      "stats": stats}
    targets = []
    for rel in sorted(same):
        f = src / rel
        if f.suffix != ".parquet" or f.is_symlink() or not f.is_file() or not _inside(f, src):
            continue
        targets.append((rel, f))
    if not targets:
        return res | {"skipped": "검증된 parquet 0"}
    rhash = remote_hashes(spec, day, remote, runner=runner) if apply else {}
    sizes: dict[str, int] = {}
    md5s: dict[str, str] = {}
    gone: list[Path] = []
    freed = 0
    for rel, f in targets:
        sz = f.stat().st_size
        freed += sz
        if apply:
            sizes[str(f)] = sz
            if rel in rhash:
                md5s[str(f)] = rhash[rel]
            f.unlink()
            gone.append(f)
    marked = mark_pruned(gone, f"pruned_verified_checksum:{manifest.utcnow()}", sizes, md5s) if gone else 0
    if apply:
        for d in sorted(src.rglob("*"), reverse=True):
            if d.is_dir() and not d.is_symlink() and not any(d.iterdir()):
                d.rmdir()
        if src.is_dir() and not any(src.iterdir()):
            src.rmdir()
    return res | {"deleted": len(gone) if apply else len(targets), "freed_bytes": freed, "verified": len(same),
                  "applied": apply, "manifest_marked": marked, "ledger_gap": (len(gone) - marked) if apply else 0,
                  "remote_md5_recorded": len(md5s)}


def run_prune(var_dir: Path, remote: str, *, apply: bool, max_days: int, today: dt.date, runner: Runner,
              mark_pruned: Callable[..., int] = manifest.mark_pruned) -> tuple[int, list[dict[str, Any]]]:
    var_dir = Path(var_dir).resolve()
    results: list[dict[str, Any]] = []
    eligible = 0
    for spec in prunable(stores(var_dir)):
        if not _inside(spec.local_path, var_dir):
            results.append({"store": spec.id, "skipped": "store 루트가 var 밖"})
            continue
        cutoff = today - dt.timedelta(days=spec.retention_days)
        days = [d for d in day_dirs(spec) if d < cutoff][:max_days]
        eligible += len(days)
        for day in days:
            results.append(prune_day(spec, day, remote, apply=apply, runner=runner, mark_pruned=mark_pruned))
    skipped = [r for r in results if "skipped" in r]
    gapped = [r for r in results if r.get("ledger_gap")]
    deleted = sum(r.get("deleted", 0) for r in results)
    healthy = eligible == 0 or (deleted > 0 and not skipped and not gapped)
    if apply:
        manifest.log_event("prune", "run", f"eligible={eligible} deleted={deleted} skipped={len(skipped)} "
                                           f"ledger_gap={sum(r['ledger_gap'] for r in gapped)} healthy={healthy}")
        if healthy:
            marker = var_dir / "markers" / MARKER
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} prune ok · 대상 {eligible}일 · "
                              f"삭제 {deleted}\n")
            return 0, results
        return 1, results
    return 0, results


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Drive 검증된 옛 shard만 로컬에서 정리(기본 dry-run)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-days", type=int, default=7)
    ap.add_argument("--var-dir", default=str(ROOT / "var"))
    a = ap.parse_args(argv)
    try:
        remote = remote_root(os.environ if env is None else env)
    except StoreConfigError as e:
        print(f"설정 오류: {e}", file=sys.stderr)
        return 2
    var_dir = Path(a.var_dir).resolve()
    manifest.MANIFEST_DB = var_dir / "manifest.sqlite"
    code, results = run_prune(var_dir, remote, apply=a.apply, max_days=a.max_days,
                              today=dt.datetime.now(dt.UTC).date(), runner=subprocess.run)
    print(f"[prune] {'APPLY' if a.apply else 'DRY-RUN'} · 결과 {len(results)}일 · 종료 코드 {code}")
    for r in results:
        print(f"  {r}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
