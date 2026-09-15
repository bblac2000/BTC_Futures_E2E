"""Drive 복제 — 시간당(`btcfut-sync.timer`). **원격에 복사만** 한다(원격 삭제 명령 없음 · `rclone sync` 금지).

- shard store: `rclone copy --checksum --min-age 90s --exclude *.tmp`(롤 중인 shard 제외 · E2E vps_sync.sh와 같은 규칙)
- sqlite store: 라이브 WAL 파일을 직접 올리지 않는다 → `sqlite3` 온라인 백업 API로 스냅샷 → `rclone copyto --checksum`
- 하나라도 실패하면 종료 코드 1이고 **성공 마커를 갱신하지 않는다**(`var/markers/LAST_SYNC.txt`) → health의 sync 정체 경보.
  prune은 Drive 검증분만 지우므로 sync가 멈추면 prune도 0건이 되고 디스크가 찬다 — 둘 다 health가 본다.

사용: python -m ops.drive_sync [--var-dir var]   (원격 = env BTCFUT_DRIVE_REMOTE)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ops.data_stores import StoreConfigError, remote_root, stores

ROOT = Path(__file__).resolve().parent.parent
Runner = Callable[..., Any]
MARKER = "LAST_SYNC.txt"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sqlite_backup(src: Path, dst: Path) -> None:
    """온라인 백업 API — 쓰기 중인 WAL DB의 일관된 스냅샷. tmp에 쓰고 rename."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    try:
        d = sqlite3.connect(tmp)
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()
    os.replace(tmp, dst)


def sync(var_dir: Path, remote: str, *, runner: Runner = subprocess.run, timeout_s: int = 1800) -> tuple[int, list[str]]:
    var_dir = Path(var_dir).resolve()
    lines: list[str] = []
    failed = False
    for s in stores(var_dir):
        dst = f"{remote}/{s.remote_subpath}"
        if s.kind == "shards_day_kind":
            if not s.local_path.is_dir():
                lines.append(f"{s.id}: 로컬 없음(건너뜀)")
                continue
            cmd = ["rclone", "copy", str(s.local_path), dst, "--checksum", "--min-age", "90s", "--exclude", "*.tmp",
                   "--transfers", "4", "--checkers", "8"]
        else:
            if not s.local_path.is_file():
                lines.append(f"{s.id}: 로컬 없음(건너뜀)")
                continue
            snap = var_dir / "backup" / s.local_path.name
            try:
                sqlite_backup(s.local_path, snap)
            except sqlite3.Error as e:
                failed = True
                lines.append(f"🔴 {s.id}: sqlite 백업 실패 {e}")
                continue
            cmd = ["rclone", "copyto", str(snap), dst, "--checksum"]
        try:
            r = runner(cmd, capture_output=True, text=True, timeout=timeout_s)
            rc = r.returncode
            err = (r.stderr or "")[-300:]
        except (subprocess.TimeoutExpired, OSError) as e:
            rc, err = -1, f"{type(e).__name__}: {e}"
        if rc != 0:
            failed = True
            lines.append(f"🔴 {s.id}: rclone rc={rc} {err}")
        else:
            lines.append(f"{s.id}: ok")
    if not failed:
        marker = var_dir / "markers" / MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{_utc()} sync ok · {' · '.join(lines)}\n")
    return (1 if failed else 0), lines


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="봇 데이터 → Drive 복사(원격 삭제 없음)")
    ap.add_argument("--var-dir", default=str(ROOT / "var"))
    a = ap.parse_args(argv)
    try:
        remote = remote_root(os.environ if env is None else env)
    except StoreConfigError as e:
        print(f"설정 오류: {e}", file=sys.stderr)
        return 2
    code, lines = sync(Path(a.var_dir), remote)
    for ln in lines:
        print(f"[sync] {ln}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
