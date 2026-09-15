"""API 키 권한 실측 — `GET /sapi/v1/account/apiRestrictions`(서명 GET). 읽기 외 권한이 하나라도 켜져 있으면 거부.

사용처: `scripts/capture_account_snapshot.py`(캡처 전) · `ops/run_bot.py`(PAPER 런타임 규칙 조회 전 — 사용자 결정 2026-09-16 (ii)).
PAPER는 이미 `ReadOnlyClient`라 POST가 구조적으로 불가능하지만, 거래 권한 키가 VPS에 있는 것 자체가 잘못된 배포다 → 기동 거부.
🚫 키·시크릿 값은 어디에도 출력하지 않는다(권한 bool 플래그만 다룬다).
"""
from __future__ import annotations

from exchange.client_types import RestClient

API_RESTRICTIONS_PATH = "/sapi/v1/account/apiRestrictions"
#  읽기 외 권한 — 하나라도 true면 거부
NON_READ_PERMISSIONS = ("enableFutures", "enableSpotAndMarginTrading", "enableMargin", "enableWithdrawals",
                        "enableInternalTransfer", "permitsUniversalTransfer", "enableVanillaOptions",
                        "enablePortfolioMarginTrading", "enableFixApiTrade")


class NotReadOnlyKey(RuntimeError):
    pass


def check_permissions(sapi: RestClient) -> dict[str, bool]:
    data = sapi.get(API_RESTRICTIONS_PATH, signed=True).data
    if not isinstance(data, dict):
        raise NotReadOnlyKey(f"apiRestrictions 응답 해석 불가: {type(data).__name__}")
    flags = {k: v for k, v in data.items() if isinstance(v, bool)}
    if flags.get("enableReading") is not True:
        raise NotReadOnlyKey("enableReading이 true가 아니다 — 읽기 권한 키가 아니다")
    on = [k for k in NON_READ_PERMISSIONS if flags.get(k) is True]
    if on:
        raise NotReadOnlyKey(f"읽기 외 권한이 켜져 있다: {on}")
    return flags
