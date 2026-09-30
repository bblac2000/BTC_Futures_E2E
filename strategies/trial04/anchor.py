"""트라이얼 #4 앵커 상수 — **이 파일만** 앵커·창·시드·다중검정 상수를 적는다(레지스트리 #69·#70 · 사전등록 r3).

다른 트라이얼 #4 모듈은 이 값을 import한다. 다른 트라이얼의 앵커는 import하지 않는다.
`OOS_END_MS`는 createdTime에서 **기계적으로** 도출한다(createdTime 전에 완전히 마감된 마지막 UTC 일의 끝).
🔒 IS 2024-01-01 → 2025-12-31 · OOS 2026-01-01 → OOS_END(봉인 — 사용자 결정 행 전 열지 않는다).
"""
from __future__ import annotations

import datetime as dt

ANCHOR_CREATED_TIME = "2026-09-30T10:17:47.203Z"          # Drive createdTime(rclone btime = 커넥터 · #70)
ANCHOR_DRIVE_FILE_ID = "1hqUPOXg3LKarOjbhiyE1DYYOeAdDZvGc"
PREREG_PATH = "docs/trials/trial_04_preregistration_r3.md"
PREREG_SHA256 = "0fde1da977001c1526f5844786af67a2adb7c6b887f74288aea93a2429ba1cf0"
PREREG_MD5 = "b3b206c898af9a9610b3f0030d89deee"
PREREG_SIZE = 28_828
TC_V3_LINES = (16, 39)                                     # §1 표(1-기준 · 양끝 포함 · LF · 끝 개행 · 24행 · 5,548 bytes)
TC_V3_SHA256 = "389f036e44ba907329d08a0d697dc16b504863b04d7d2f17bcfede19ac121580"

#  다중검정(r3 §0 · §3 · N = 8 누적) — 퍼센타일은 정확한 분수(0.3125 / 99.6875는 표시값)
N_TRIALS = 8
ALPHA = 0.05 / N_TRIALS
LEVEL = 1 - ALPHA
CI_LO_Q = ALPHA / 2                                        # = 1/320
CI_HI_Q = 1 - ALPHA / 2
TRIAL01_REPORT_SHA256 = "11c8845295823c24b107ab6ddd3b4d60c695eff5898b0a1cc89d05869b935e0d"
TRIAL02_REPORT_SHA256 = "9223047cf7d7698de41e16ca2e2beb42d8461db29d8431cd8195a6c0757ecf2e"
TRIAL03_REPORT_SHA256 = "41f789fc21fa2e545ea3e09263475f11bd8dc103b8e463ccabf58394a183cec5"
SR_1A = -0.23802981743207333                               # #25
SR_1B = -0.23471514010093758                               # #25
SR_2A = -0.007474349306781282                              # #40
SR_2B = -0.0033941087843268273                             # #40
SR_3L = -0.23689701015198752                               # #58
SR_3S = -0.19165332011747566                               # #58
PINNED_SR = (SR_1A, SR_1B, SR_2A, SR_2B, SR_3L, SR_3S)     # SR* = expected_max_sr(정의된 {이 여섯 + SR̂_S + SR̂_L}, n_trials = 8)

#  🎲 시드(r3 §3-1 · §4) — ⚠️ 순서가 트라이얼 #3과 **반대**다(S가 먼저 · S = k2 · L = k3). 사전등록 문구 그대로이니 "고치지" 않는다.
MASTER_SEED = 20260930
BOOTSTRAP_SEED = (MASTER_SEED, 1)                          # SeedSequence(BOOTSTRAP_SEED).spawn(8)[k]
BOOTSTRAP_SPAWN = 8
BOOTSTRAP_STREAMS = {"IS": {"gross_S": 0, "net_S": 1, "gross_L": 2, "net_L": 3},
                     "OOS": {"gross_S": 4, "net_S": 5, "gross_L": 6, "net_L": 7}}
BOOTSTRAP_RESAMPLES = 10_000
P1_SEEDS = {"S": (MASTER_SEED, 2), "L": (MASTER_SEED, 3)}  # 게이트 P1: SeedSequence(P1_SEEDS[arm]).spawn(1000)[d]
P1_DRAWS = 1000
P1_TIMING_CHILD_OFFSET = 1000                              # 보고 전용 P1-timing: SeedSequence(P1_SEEDS[arm]).spawn(2000)[1000 + d]
P1_SLOT_ATTEMPTS = 1000
P1_FAIL_MAX = 10                                           # 실패 > 10 → 폐기

#  런타임 규칙(#69 — 앵커 날 · 업로드 직전 캡처 하나) · 파일의 `_meta.purpose` 문구는 트라이얼 #3 스크립트에서 물려받은 것(정정 행) — 로더는 `response`만 읽는다
RULES_SNAPSHOT_DIR = "docs/trials/trial_04_rules_snapshot"
RULES_SNAPSHOT_SHA256 = {
    "exchangeInfo": "b2be7194f66a041f45e54af4d6cdb8a05639c6f1eba8910ddc54166481e11c18",
    "leverageBracket": "6fcb2351eccce67ad1ea520a937041488ee5c764317c3dc88e30602541e66dcb",
    "commissionRate": "5b5899288c5d28b6b2f357251568698d9924836082d8c7ff5b96a10c681c7a53",
    "fundingInfo": "46387f446a08a8abeadfcc48b13ef05aea1104442fc6625a5ee62df0d1a8606e",
}

DAY_MS = 86_400_000
H8_MS = 8 * 3_600_000


def _ms(y: int, m: int, d: int) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.UTC).timestamp() * 1000)


def oos_end_from_created(created: str) -> int:
    """createdTime의 UTC 날짜 시작 − 1 ms(= 그 전 UTC 일의 23:59:59.999)."""
    c = dt.datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.UTC)
    return int(c.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000) - 1


DATA_START_MS = _ms(2023, 10, 2)                           # 데이터 시작(프리미엄 270 인쇄 + ATR 워밍업 · r3 §5)
WINDOW_START_MS = _ms(2024, 1, 1)                          # 창 시작
IS_END_MS = _ms(2026, 1, 1) - 1                            # 2025-12-31 23:59:59.999Z
OOS_START_MS = _ms(2026, 1, 1)
OOS_END_MS = oos_end_from_created(ANCHOR_CREATED_TIME)    # 2026-09-29 23:59:59.999Z(272일)
