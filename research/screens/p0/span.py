"""M-1의 자료 범위(스펙 §2-1) — 이 상수 밖의 시장 값은 해석하지 않는다."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

EXPOSED_START_MS = int(dt.datetime(2026, 9, 17, tzinfo=dt.UTC).timestamp() * 1000)
EXPOSED_END_MS = int(dt.datetime(2026, 10, 11, 6, 22, 15, tzinfo=dt.UTC).timestamp() * 1000)
DATES = tuple((dt.date(2026, 9, 17) + dt.timedelta(days=i)).isoformat() for i in range(25))      # 09-17 … 10-11
STREAMS = ("depth100ms", "bookticker", "aggtrade")
SOURCES = {s: f"l2live_{s}" for s in STREAMS}
ROOT = Path(__file__).resolve().parents[3]
RESTORE = ROOT / "var" / "p0_restore"
REMOTE = "gdrive:E2E_Hybrid_Bot"
