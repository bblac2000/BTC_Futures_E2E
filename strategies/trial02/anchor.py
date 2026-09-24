"""트라이얼 #2 앵커 상수 — **이 파일만** 앵커·창·시드·다중검정 상수를 적는다(레지스트리 #35 · #36).

다른 트라이얼 #2 모듈은 이 값을 import한다. 트라이얼 #1(`strategies.trial01.anchor`)은 import하지 않는다(사전등록 §11-5).
`OOS_END_MS`는 createdTime에서 **기계적으로** 도출한다(사전등록 §5: createdTime 이전에 완전히 마감된 마지막 UTC 일의 끝).
"""
from __future__ import annotations

import datetime as dt

ANCHOR_CREATED_TIME = "2026-09-24T10:22:54.426Z"          # Drive createdTime(커넥터 + rclone btime 일치 · #35)
ANCHOR_DRIVE_FILE_ID = "1BYBrBNe1pDe00o979MujYPvMIq5ndlFe"
PREREG_PATH = "docs/trials/trial_02_preregistration.md"
PREREG_SHA256 = "d353f58695ea5e2878827af51675971fd237c34dc30d2757d3f5b712c2272dbf"
BO_V1_SHA256 = "1b8a41a8e6fe983b1982d9775451f93cb3f27b8d3f520102963c8913d1ba56f7"   # §1 표(25~53행)

#  다중검정(§0 · §3 · §3-1 · N = 4 누적)
N_TRIALS = 4
ALPHA = 0.0125
LEVEL = 0.9875
CI_LO_PCT, CI_HI_PCT = 0.625, 99.375                       # 가운데 98.75% 퍼센타일 구간
TRIAL01_REPORT_SHA256 = "11c8845295823c24b107ab6ddd3b4d60c695eff5898b0a1cc89d05869b935e0d"
SR_1A = -0.23802981743207333                               # 트라이얼 #1 Arm A SR̂(#25 · 고정)
SR_1B = -0.23471514010093758                               # 트라이얼 #1 Arm B SR̂(#25 · 고정)

#  🎲 시드(§4 · §11-5)
MASTER_SEED = 20260924
P1_DRAWS = 1000
P1_FAIL_MAX = 10                                           # 실패 > 10 → 폐기
P4_DRAWS = 200
P4_MIN_DEFINED = 190                                       # 정의된 추출 < 190 → 폐기
P4_SEED_TAG = 4                                            # SeedSequence([MASTER_SEED, 4, d, day_index])
BOOTSTRAP_SEED = (MASTER_SEED, 1)                          # SeedSequence(BOOTSTRAP_SEED).spawn(8)[k]
BOOTSTRAP_SPAWN = 8
BOOTSTRAP_STREAMS = {"gross_A": 0, "net_A": 1, "gross_B": 2, "net_B": 3, "ab_daily": 4}
BOOTSTRAP_RESAMPLES = 10_000

#  런타임 규칙(정정 01 · #36 — 앵커 뒤 같은 날 캡처 하나 · 대체 경로 없음)
RULES_SNAPSHOT_DIR = "docs/trials/trial_02_rules_snapshot"
RULES_SNAPSHOT_SHA256 = {
    "exchangeInfo": "e549134cdf804ad3b8554656a4ac9fa61c1ce66cb9f28a1e3e39883f997bf5c5",
    "leverageBracket": "65aa79460e4347c4ad71420018e8671389b409072da119249bb7e7d096067636",
    "commissionRate": "b8a89d16882d74d7520b305114d56cb58aea7a50cd09e1137b3f2068d1b3cdad",
    "fundingInfo": "9db101c8ed362f5803aa170330da0dd037ac93b091fcd7fcb773daccc1149187",
}

WARMUP_DAYS = 21                                           # §1 워밍업 · §5
DAY_MS = 86_400_000


def _ms(y: int, m: int, d: int) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.UTC).timestamp() * 1000)


def oos_end_from_created(created: str) -> int:
    """createdTime의 UTC 날짜 시작 − 1 ms(= 그 전 UTC 일의 23:59:59.999)."""
    c = dt.datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.UTC)
    return int(c.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000) - 1


IS_START_MS = _ms(2024, 1, 1)
IS_END_MS = _ms(2026, 7, 1) - 1                            # 2026-06-30 23:59:59.999Z
OOS_START_MS = _ms(2026, 7, 1)
OOS_END_MS = oos_end_from_created(ANCHOR_CREATED_TIME)    # 2026-09-23 23:59:59.999Z(85일)
