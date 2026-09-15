"""layer 6 설정 — 확인 흐름 값은 **사용자 확정**(open-decisions #9 · strategy-modules §6, 2026-09-12)이다. 바꾸려면 사용자 결정.

주인 ID는 리터럴이 아니라 환경변수 `TELEGRAM_OWNER_IDS`(쉼표 구분 정수) — 비어 있으면 명령 봇을 띄우지 않는다.
"""
from __future__ import annotations

from collections.abc import Mapping

CONFIRM_RESEND_INTERVAL_MS = 3_000      # 무응답이면 3초 간격으로
CONFIRM_RESENDS = 3                     # 3회 재전송 → 그래도 무응답이면 취소 + "청산 안 됨"
CALLBACK_TTL_MS = 60_000                # 버튼 콜백 토큰 만료(오래된 버튼이 나중에 눌려 청산되지 않게)
LONG_POLL_TIMEOUT_S = 30                # getUpdates 롱폴링(운영 값 · Bot API: 양수 권장)
FAST_POLL_TIMEOUT_S = 1                 # 확인·알림 대기 중 — tick이 3초 재전송보다 촘촘히 돌게
ALLOWED_UPDATES = ("message", "callback_query")
OWNER_ENV = "TELEGRAM_OWNER_IDS"


def owner_ids_from_env(env: Mapping[str, str]) -> frozenset[int]:
    raw = (env.get(OWNER_ENV) or "").strip()
    if not raw:
        raise ValueError(f"{OWNER_ENV} 비어 있음 — 주인 ID 화이트리스트 없이는 명령을 받지 않는다")
    try:
        ids = frozenset(int(x.strip()) for x in raw.split(",") if x.strip())
    except ValueError as e:
        raise ValueError(f"{OWNER_ENV}는 쉼표로 구분한 정수 ID") from e
    if not ids:
        raise ValueError(f"{OWNER_ENV} 비어 있음")
    return ids
