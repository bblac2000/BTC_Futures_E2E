"""트라이얼 #1 앵커 상수 — **이 파일만** 앵커·창·시드를 적는다(레지스트리 #18 · 사전등록 SHA256 e4442ff4…).

다른 모듈은 이 값을 import한다 — 날짜·시드를 다시 손으로 쓰지 않는다. `OOS_END_MS`는 createdTime 문자열에서 **기계적으로** 도출한다
(사전등록 §5: Drive createdTime 이전에 완전히 마감된 마지막 UTC 일의 끝).
"""
from __future__ import annotations

import datetime as dt

ANCHOR_CREATED_TIME = "2026-09-21T09:51:14.150Z"          # Drive createdTime(커넥터 + rclone btime 일치)
ANCHOR_DRIVE_FILE_ID = "1GfKcglht-f5O_CCWnU0coS7J_3ybREOR"
PREREG_SHA256 = "e4442ff4fdd2983713eb664f3075c978e0704649f4a5ea6ca4f41dcb8ecdd7ef"
PREREG_PATH = "docs/trials/trial_01_preregistration.md"
SR_V1_SHA256 = "b02d1a1668261e0adb617e575154f19d1279017ec500f3b51a0354234c3fbce6"   # §1 표(17~45행) — 별도 필드, 시드 출처 아님
N_TRIALS = 2                                               # Arm A · Arm B (Bonferroni α = 0.05/2)
ALPHA = 0.05 / N_TRIALS

#  🎲 시드: P1은 사전등록 규약 (e)의 20260921. 사전등록이 정하지 않은 난수 소비처(부트스트랩·P4)는 **같은 마스터에서 갈라진
#     독립 스트림**을 쓴다 — 구현 규약이며 사전등록 값이 아니다(2a 보고에 명시).
P1_MASTER_SEED = 20260921
P1_DRAWS = 1000
BOOTSTRAP_SEED = (20260921, 1)                             # SeedSequence 엔트로피 튜플
P4_SEED = (20260921, 4)
P4_DRAWS = 200
BOOTSTRAP_RESAMPLES = 10_000


def _ms(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> int:
    return int(dt.datetime(y, m, d, hh, mm, tzinfo=dt.UTC).timestamp() * 1000)


def oos_end_from_created(created: str) -> int:
    """createdTime의 UTC 날짜 시작 − 1 ms(= 그 전 UTC 일의 23:59:59.999)."""
    c = dt.datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.UTC)
    start = c.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000) - 1


IS_START_MS = _ms(2024, 1, 1)
IS_END_MS = _ms(2026, 7, 1) - 1                            # 2026-06-30 23:59:59.999Z
OOS_START_MS = _ms(2026, 7, 1)
OOS_END_MS = oos_end_from_created(ANCHOR_CREATED_TIME)
