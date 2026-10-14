"""M-1 복원(스펙 §2-2) — 매니페스트와 Drive 목록을 짝짓고, 짝지어진 shard만 내려받아 검증한다.

    uv run python -m research.screens.p0.restore plan     # 3: 짝짓기 · 99% 검사(내려받기 없음)
    uv run python -m research.screens.p0.restore fetch    # 5: 짝지어진 파일 내려받기
    uv run python -m research.screens.p0.restore verify   # 6 · 7: Drive MD5 · footer 행 수 · 제외 뒤 보유율 → M-1_restore.json

시장 값은 읽지 않는다(검증은 바이트 해시와 parquet footer 메타데이터만).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys

from research.screens.p0 import span as SP

PLAN = SP.RESTORE / "M-1_plan.json"
OUT = SP.ROOT / "research" / "screens" / "p0" / "results" / "M-1_restore.json"
FLOOR = 0.99


def _rel(path: str) -> str | None:
    """매니페스트 경로 → `<날짜>/<스트림>/<파일>`(범위 밖이면 None)."""
    parts = path.replace("\\", "/").split("/")
    if len(parts) < 3:
        return None
    date, stream, name = parts[-3], parts[-2], parts[-1]
    return f"{date}/{stream}/{name}" if date in SP.DATES and stream in SP.STREAMS else None


def expected() -> dict[str, dict]:
    con = sqlite3.connect(f"file:{SP.RESTORE / 'manifest.sqlite'}?mode=ro", uri=True)
    out: dict[str, dict] = {}
    for stream, src in SP.SOURCES.items():
        for path, rows, rmd5 in con.execute("SELECT COALESCE(parquet_path, path), parquet_rows, remote_md5 FROM files WHERE source=?", (src,)):
            r = _rel(path)
            if r is not None:
                out[r] = {"stream": stream, "parquet_rows": rows, "remote_md5": rmd5}
    return out


def drive_listing() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for date in SP.DATES:
        for stream in SP.STREAMS:
            res = subprocess.run(["rclone", "lsjson", "--hash", "--files-only", f"{SP.REMOTE}/l2live/BTCUSDT/{date}/{stream}/"],
                                 capture_output=True, text=True, check=True)
            for e in json.loads(res.stdout or "[]"):
                out[f"{date}/{stream}/{e['Name']}"] = {"size": e["Size"], "md5": (e.get("Hashes") or {}).get("md5")}
    return out


def plan() -> int:
    exp, drv = expected(), drive_listing()
    by = {}
    for s in SP.STREAMS:
        e = [k for k, v in exp.items() if v["stream"] == s]
        m = [k for k in e if k in drv]
        orphans = [k for k in drv if k.split("/")[1] == s and k not in exp]
        by[s] = {"expected": len(e), "matched": len(m), "ratio": len(m) / len(e) if e else 0.0, "drive_orphans": len(orphans),
                 "missing_on_drive": sorted(set(e) - set(m))[:200], "remote_md5_present": sum(1 for k in e if exp[k]["remote_md5"])}
    ok = all(v["ratio"] >= FLOOR for v in by.values())
    matched = {k: {**exp[k], **drv[k]} for k in exp if k in drv}
    PLAN.write_text(json.dumps({"by_stream": by, "floor": FLOOR, "ok": ok, "matched": matched}, indent=1, sort_keys=True))
    print(json.dumps({s: {k: v for k, v in d.items() if k != "missing_on_drive"} for s, d in by.items()}, indent=1), "ok", ok)
    return 0 if ok else 4


def fetch() -> int:
    p = json.loads(PLAN.read_text())
    if not p["ok"]:
        print("plan이 99% 문턱을 넘지 못했다 — 내려받지 않는다", file=sys.stderr)
        return 4
    # 디렉터리 단위(날짜 × 스트림 75개) — 파일별 조회(--files-from)는 Drive에서 10만 번의 조회가 되어 느리다.
    # 짝지어진 집합 = 그 디렉터리의 Drive 파일 전체(plan의 drive_orphans = 0이 전제 — 아니면 거부). 보조 구간 날짜는 목록에 없다.
    if any(v["drive_orphans"] for v in p["by_stream"].values()):
        print("Drive 고아 파일이 있다 — 디렉터리 단위 복사를 쓰지 않는다", file=sys.stderr)
        return 4
    rc = 0
    for date in SP.DATES:
        for stream in SP.STREAMS:
            r = subprocess.run(["rclone", "copy", f"{SP.REMOTE}/l2live/BTCUSDT/{date}/{stream}/",
                                str(SP.RESTORE / "BTCUSDT" / date / stream), "--transfers", "16", "--checkers", "16"])
            print(date, stream, "rc", r.returncode, flush=True)
            rc = rc or r.returncode
    return rc


def verify() -> int:
    import pyarrow.parquet as pq
    p = json.loads(PLAN.read_text())
    excluded: list[dict] = []
    kept: dict[str, int] = {s: 0 for s in SP.STREAMS}
    h = hashlib.sha256()
    for rel, meta in sorted(p["matched"].items()):
        f = SP.RESTORE / "BTCUSDT" / rel
        if not f.exists():
            excluded.append({"file": rel, "why": "not downloaded"})
            continue
        data = f.read_bytes()
        md5 = hashlib.md5(data).hexdigest()
        why = []
        if meta.get("md5") and md5 != meta["md5"]:
            why.append("drive md5 mismatch")
        if meta.get("remote_md5") and md5 != meta["remote_md5"]:
            why.append("manifest remote_md5 mismatch")
        try:
            n = pq.ParquetFile(f).metadata.num_rows                          # footer 메타데이터만
        except Exception as e:                                                # noqa: BLE001
            why.append(f"footer unreadable: {type(e).__name__}")
            n = None
        if meta.get("parquet_rows") is not None and n is not None and n != meta["parquet_rows"]:
            why.append(f"rows {n} != manifest {meta['parquet_rows']}")
        if why:
            excluded.append({"file": rel, "why": "; ".join(why)})
            continue
        kept[meta["stream"]] += 1
        h.update(f"{rel} {hashlib.sha256(data).hexdigest()}\n".encode())
    by = p["by_stream"]
    retained = {s: {"expected": by[s]["expected"], "kept": kept[s], "ratio": kept[s] / by[s]["expected"]} for s in SP.STREAMS}
    ok = all(v["ratio"] >= FLOOR for v in retained.values())
    res = {"plan_by_stream": {s: {k: v for k, v in d.items() if k != "missing_on_drive"} for s, d in by.items()},
           "missing_on_drive_sample": {s: by[s]["missing_on_drive"] for s in SP.STREAMS}, "retained": retained, "floor": FLOOR,
           "ok": ok, "excluded": excluded, "restore_sha256_of_list": h.hexdigest(),
           "evidence": "drive md5 (server) vs local md5 · manifest remote_md5 where present · parquet footer rows vs manifest parquet_rows"}
    from research.screens.window import write_result
    write_result(OUT, res)
    print(json.dumps({"retained": retained, "excluded": len(excluded), "ok": ok}, indent=1))
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit({"plan": plan, "fetch": fetch, "verify": verify}[sys.argv[1]]())
