"""저장소 표 — sync·prune·health가 **같은 표를 읽는다**(E2E 설계_prune확장 v2 · #131의 대칭 구멍을 구조로 막는다).

- 🔒 **삭제는 allowlist**: `deletion_mode == "drive_verified_prune"`인 store만 prune 대상. denylist를 두지 않는다
  (새 store가 생기면 기본이 "삭제 안 함"이다).
- sqlite(봇 DB·manifest)는 **절대 삭제 대상이 아니다** — 백업(`sqlite3` 온라인 백업 API → 원격 사본)만.
- 원격 루트는 이 봇 전용 환경변수 `BTCFUT_DRIVE_REMOTE`(`<rclone remote>:<폴더>`). E2E 폴더(`E2E_Hybrid_Bot`)를 가리키면
  거부한다 — 이 봇의 사본 검증이 수집기의 사본과 섞이면 틀린 초록불이 켜진다. 모든 로컬 경로는 봇 사용자의 `var/` 안.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REMOTE_ENV = "BTCFUT_DRIVE_REMOTE"
FORBIDDEN_REMOTE_PARTS = ("e2e_hybrid_bot",)
RETENTION_DAYS = 30                        # E2E와 같은 보존 창 — prune·verify가 같은 값을 읽는다(#128 상보 설계)


class StoreConfigError(ValueError):
    pass


@dataclass(frozen=True)
class StoreSpec:
    id: str
    local_path: Path                       # 디렉터리(shard) 또는 파일(sqlite)
    remote_subpath: str                    # 원격 루트 아래 경로
    kind: Literal["shards_day_kind", "sqlite"]
    deletion_mode: Literal["drive_verified_prune", "never"]
    manifest_source_prefix: str | None = None
    retention_days: int = RETENTION_DAYS


def stores(var_dir: Path, symbol: str = "BTCUSDT") -> tuple[StoreSpec, ...]:
    var_dir = Path(var_dir).resolve()
    return (
        #  layer 5 shard: <root>/<YYYY-MM-DD>/<kind>/<HHMMSS_mmm>.parquet · 대장 source "live_<kind>"
        StoreSpec("raw_live", var_dir / "raw" / "live" / symbol, f"raw/live/{symbol}", "shards_day_kind",
                  "drive_verified_prune", manifest_source_prefix="live_"),
        StoreSpec("bot_db", var_dir / "bot.sqlite", "db/bot.sqlite", "sqlite", "never"),
        StoreSpec("manifest", var_dir / "manifest.sqlite", "db/manifest.sqlite", "sqlite", "never"),
    )


def prunable(specs: tuple[StoreSpec, ...]) -> tuple[StoreSpec, ...]:
    """allowlist — 삭제 가능한 store만. sqlite는 여기 올 수 없다(표 검증)."""
    out = tuple(s for s in specs if s.deletion_mode == "drive_verified_prune")
    for s in out:
        if s.kind != "shards_day_kind":
            raise StoreConfigError(f"{s.id}: {s.kind}는 삭제 대상이 될 수 없다")
    return out


def remote_root(env: Mapping[str, str]) -> str:
    r = (env.get(REMOTE_ENV) or "").strip().rstrip("/")
    name, sep, path = r.partition(":")
    if not r or not sep or not name or not path.strip("/"):
        raise StoreConfigError(f"{REMOTE_ENV}는 '<remote>:<이 봇 전용 폴더>' 형식이어야 한다")
    if any(part in r.lower() for part in FORBIDDEN_REMOTE_PARTS):
        raise StoreConfigError(f"{REMOTE_ENV}가 E2E 수집기 폴더를 가리킨다 — 이 봇 전용 폴더만")
    return r
