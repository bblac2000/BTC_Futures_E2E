"""트라이얼 #3 앵커 상수 — **이 파일만** 앵커·창·시드·다중검정 상수를 적는다(레지스트리 #47~#50 · 계획 r5).

다른 트라이얼 #3 모듈은 이 값을 import한다. 트라이얼 #1·#2 앵커는 import하지 않는다.
`OOS_END_MS`는 createdTime에서 **기계적으로** 도출한다(사전등록 §5: createdTime 전에 완전히 마감된 마지막 UTC 일의 끝).
🔒 창 (B)(#47): IS 2024-01-01 → 2025-12-31 · OOS 2026-01-01 → OOS_END(닫힘 — 사용자 결정 전 열지 않는다).
"""
from __future__ import annotations

import datetime as dt

ANCHOR_CREATED_TIME = "2026-09-29T09:31:46.486Z"          # Drive createdTime(rclone btime = 커넥터 · #50)
ANCHOR_DRIVE_FILE_ID = "1mMh8xPbPuXAjS1dli6QaRyE7H9MKxt8V"
PREREG_PATH = "docs/trials/trial_03_preregistration.md"
PREREG_SHA256 = "9b8d2cdf3e40fde82914dea46cd633666584e2fbac7032996c03f7496b224d4b"
TF_V1_LINES = (20, 39)                                     # §1 표(1-기준 · 양끝 포함 · LF · 끝 개행)
TF_V1_SHA256 = "ae58c8a099cbc3174e46a5d2c12d2998d15994943db4e4d381a03232f196b830"

#  다중검정(§0 · §3 · §3-1 · N = 6 누적) — 퍼센타일은 정확한 분수(0.41667/99.58333은 표시값)
N_TRIALS = 6
ALPHA = 0.05 / N_TRIALS
LEVEL = 1 - ALPHA
CI_LO_Q = ALPHA / 2                                        # = 1/240
CI_HI_Q = 1 - ALPHA / 2
TRIAL01_REPORT_SHA256 = "11c8845295823c24b107ab6ddd3b4d60c695eff5898b0a1cc89d05869b935e0d"
TRIAL02_REPORT_SHA256 = "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e"
SR_1A = -0.23802981743207333                               # #25
SR_1B = -0.23471514010093758                               # #25
SR_2A = -0.007474349306781282                              # #40
SR_2B = -0.0033941087843268273                             # #40
PINNED_SR = (SR_1A, SR_1B, SR_2A, SR_2B)                   # SR* = expected_max_sr(정의된 {이 넷 + SR̂_L + SR̂_S}, n_trials = 6)

#  🎲 시드(§3-1 · §4)
MASTER_SEED = 20260929
BOOTSTRAP_SEED = (MASTER_SEED, 1)                          # SeedSequence(BOOTSTRAP_SEED).spawn(8)[k]
BOOTSTRAP_SPAWN = 8
BOOTSTRAP_STREAMS = {"IS": {"gross_L": 0, "net_L": 1, "gross_S": 2, "net_S": 3},
                     "OOS": {"gross_L": 4, "net_L": 5, "gross_S": 6, "net_S": 7}}
BOOTSTRAP_RESAMPLES = 10_000
P1_SEEDS = {"L": (MASTER_SEED, 2), "S": (MASTER_SEED, 3)}  # SeedSequence(P1_SEEDS[arm]).spawn(1000)[d]
P1_DRAWS = 1000
P1_SLOT_ATTEMPTS = 1000
P1_FAIL_MAX = 10                                           # 실패 > 10 → 폐기

#  런타임 규칙(#48 — 앵커 날 · 업로드 직전 캡처 하나 · 대체 경로 없음)
RULES_SNAPSHOT_DIR = "docs/trials/trial_03_rules_snapshot"
RULES_SNAPSHOT_SHA256 = {
    "exchangeInfo": "12bf7e95c83680b6e3dadd10743479fc20e720a5670c1bfa7cdec55e2432950e",
    "leverageBracket": "0c851db1f27ab3f87a977fc69ed572ff010b6c5e0b5652cfa580aedc26bfc664",
    "commissionRate": "9fd329a8ea90fa7acca0eea122c721e8d9ac4ca1475b8d7047e5a2ac1ce8f051",
    "fundingInfo": "52a83edaded71501cf3bcab15714377e5b025d285145200542fd83676f6cd6d1",
}

DAY_MS = 86_400_000


def _ms(y: int, m: int, d: int) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.UTC).timestamp() * 1000)


def oos_end_from_created(created: str) -> int:
    """createdTime의 UTC 날짜 시작 − 1 ms(= 그 전 UTC 일의 23:59:59.999)."""
    c = dt.datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.UTC)
    return int(c.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000) - 1


DATA_START_MS = _ms(2023, 10, 2)                           # 데이터 시작(준비 경로 하한 · 워밍업 첫 봉) · §5 워밍업(분위수 90일 + r30 · ATR · rv · 판정 가능 구간 앞쪽)
WINDOW_START_MS = _ms(2024, 1, 1)                          # 창 시작(판정 가능한 첫 봉 · 이벤트 깔때기 분모의 시작)
IS_END_MS = _ms(2026, 1, 1) - 1                            # 2025-12-31 23:59:59.999Z
OOS_START_MS = _ms(2026, 1, 1)
OOS_END_MS = oos_end_from_created(ANCHOR_CREATED_TIME)    # 2026-09-28 23:59:59.999Z(271일)
