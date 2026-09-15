"""직전 실행이 정상 종료했는가 — 봇 대장(`var/manifest.sqlite`의 `events`)만으로 판정한다(사용자 결정 2026-09-16).

SIGKILL·OOM·전원 차단은 `stop`도 `stop_dirty`도 남기지 않는다 → dirty-stop 검사가 **공짜로 통과**한다.
그래서 러너가 기동마다 `start`(source `bot`)를 남기고, 기동 때 마지막 종결 이벤트(`stop`·`stop_dirty`·`dirty_previous_run`)
뒤에 `start`나 `connect`가 있으면 직전 실행을 `dirty_previous_run`으로 기록한다(대장 + 봇 DB 운영 이벤트).
- 기록 자체가 종결 표시다 → 다음 기동은 같은 실행을 다시 세지 않는다.
- `stop_dirty`는 이미 기록된 dirty다(두 번 세지 않는다).
- 기동 알림(🟢)에 **한 줄 언급**(새로 판정한 기동에서만 · 사용자 2026-09-16) — 확정 사실 알림과 별개.
- 확정 사실 알림은 **한 번**: 상태 파일 `confirmed_facts`(최근 24시간의 `dirty_previous_run`, 키 = 기록 시각)를 health가 once 키로 보낸다
  (발송 성공 뒤에만 기록 — 텔레그램 실패 시 다음 주기 재시도).
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any

from data import manifest

RUN_EVENT_SOURCE = "bot"
TERMINAL_KINDS = ("stop", "stop_dirty", "dirty_previous_run")
OPENING_KINDS = ("start", "connect")
DIRTY_KIND = "dirty_previous_run"
FACT_WINDOW_S = 24 * 3600                   # 상태 파일에 남기는 기간 — health 5분 타이머가 한 번 보낼 여유


def previous_run_dirty() -> str | None:
    q_marks = ",".join("?" * len(TERMINAL_KINDS))
    with manifest.connect() as con:
        last = con.execute(f"SELECT max(id) FROM events WHERE kind IN ({q_marks})", TERMINAL_KINDS).fetchone()[0] or 0
        rows = con.execute("SELECT ts_utc, source, kind FROM events WHERE id>? AND kind IN (?,?) ORDER BY id",
                           (last, *OPENING_KINDS)).fetchall()
    if not rows:
        return None
    kinds = sorted({f"{s}:{k}" for _t, s, k in rows})
    return (f"직전 실행이 종료 기록 없이 끝났다 — {rows[0][0]} 이후 {len(rows)}개 이벤트({', '.join(kinds)}) 뒤 stop 없음 "
            "(SIGKILL·OOM·전원 차단 의심 · 마지막 shard 최대 60초 유실 가능)")


def mark_dirty(detail: str) -> None:
    manifest.log_event(RUN_EVENT_SOURCE, DIRTY_KIND, detail)


def log_start(detail: str) -> None:
    manifest.log_event(RUN_EVENT_SOURCE, "start", detail)


def recent_dirty_facts(*, now: float | None = None) -> list[dict[str, Any]]:
    now = time.time() if now is None else now
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now - FACT_WINDOW_S)) + "Z"
    with manifest.connect() as con:
        rows = con.execute("SELECT ts_utc, detail FROM events WHERE kind=? AND ts_utc>=? ORDER BY id", (DIRTY_KIND, since)).fetchall()
    return [{"kind": DIRTY_KIND, "id": ts, "daily": False, "date": dt.date.fromisoformat(ts[:10]).isoformat(), "text": d}
            for ts, d in rows]
