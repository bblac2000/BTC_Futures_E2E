"""트라이얼 #4 (g) 단계 시험용 준비 입력 — 합성 아카이브(IS 마지막 날 1,440분) + 가짜 REST + 가짜 프리미엄 zip. 실데이터 없음.

`tests/test_prepare_t4.py`의 도우미와 같은 모양(그 파일은 고치지 않는다 — 여기에는 단계 실행기·고정 로더 시험이 쓰는 것만 둔다).
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from backtest import prepare_t4 as P
from strategies.trial04 import anchor as A
from tests import test_prepare_t3 as TP3

MIN = 60_000
END = A.IS_END_MS
DAY0 = END + 1 - A.DAY_MS                                  # 2025-12-31 00:00Z
RANGE = (DAY0, END)
HDR = ",".join(P.PREMIUM_HEADER)


def prow(t: int, close: str = "0.0001") -> str:
    return f"{t},0,0,0,{close},0,{t + MIN - 1},0,12,0,0,0"


def pzip(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BTCUSDT-1m-x0.csv", HDR + "\n" + "\n".join(lines) + "\n")
    return buf.getvalue()


def fetch_premium(month: str) -> tuple[bytes, str]:
    data = pzip([prow(DAY0 + i * MIN) for i in range(1440)])
    return data, f"{hashlib.sha256(data).hexdigest()}  f.zip\n"


def capture_build(out: Path, root: Path, arch_dir: Path, drop_minutes: frozenset[int] = frozenset()) -> dict:
    """`out` = `<root>/var/t4/IS/prepared` — 합성 하루를 캡처하고 빌드한다(범위 = RANGE)."""
    arch = TP3.write_archive(arch_dir, [TP3.arow(DAY0 + i * MIN) for i in range(1440) if i not in drop_minutes], [])
    P.capture(out / "raw", TP3.FakeRest(), arch, fetch_premium, DAY0, END, root=root)
    return P.build(out, RANGE, root=root)
