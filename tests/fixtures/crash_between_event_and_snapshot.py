"""장애 주입(Codex 단계 d 후속 #1 · 사용자: 실제로 죽인다) — 트레일 SL 이동 이벤트 행을 **쓴 직후, 스냅샷 행을 쓰기 직전**에
프로세스를 `os._exit(137)`로 죽인다(파일 편집 흉내가 아니라 그 지점의 실제 종료). 같은 트랜잭션이므로 sqlite가 둘 다 되돌려야 한다.

    python -m tests.fixtures.crash_between_event_and_snapshot DB_PATH MARKER_PATH
"""
from __future__ import annotations

import os
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from db import record as R
from exchange.loader import rules_from_snapshot_dir
from paper.engine import Trail
from tests.test_ops_restore import DAY0, build_file
from tests.test_ops_runtime import feed
from tests.test_paper_engine import intent

FIX = Path(__file__).resolve().parent / "snapshots"


def main() -> None:
    db, marker = Path(sys.argv[1]), Path(sys.argv[2])
    rules = rules_from_snapshot_dir(FIX, "BTCUSDT")
    rt, counter, clock = build_file(rules, db, t0=DAY0)
    feed(rt, counter, clock, DAY0, DAY0 + 61_000)
    rt.submit_entry(replace(intent(sl="59700", decided_ms=DAY0 + 60_000), trail=Trail(Decimal(1), Decimal(100))))
    feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 121_000)                  # 체결 + 봉 스냅샷(SL 59700)
    real_rows, real_snap = R._record_event_rows, R._snapshot_row

    def rows_then_mark(con, events, *a, **k):
        real_rows(con, events, *a, **k)
        if any(type(e).__name__ == "StopTrailed" for e in events):
            marker.write_text("stoptrailed_rows_inserted")               # 이벤트 행은 (커밋 전) 들어갔다

    def die_before_snapshot(con, **k):
        if marker.exists():
            os._exit(137)                                                # ← 이벤트 쓰기와 스냅샷 쓰기 사이의 실제 종료
        real_snap(con, **k)

    R._record_event_rows = rows_then_mark                                # type: ignore[assignment]
    R._snapshot_row = die_before_snapshot                                # type: ignore[assignment]
    feed(rt, counter, clock, DAY0 + 121_000, DAY0 + 181_000, mark="60500")  # +1R → StopTrailed → 여기서 죽는다
    sys.exit(3)                                                          # 도달하면 주입 실패


if __name__ == "__main__":
    main()
