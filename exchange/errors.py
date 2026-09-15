"""exchange 계층 예외 — 조용한 기본값 대신 이름 있는 실패."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exchange.gate import GateResult


class RulesError(ValueError):
    """거래소 규칙이 없거나 해석할 수 없다. 🚫 추정값으로 메우지 않는다(fail-closed)."""


class OrderParamError(ValueError):
    """주문 파라미터가 헌법 주문 매트릭스(원웨이·MARKET 전용·청산 reduceOnly)를 벗어났다."""


class BinanceAPIError(RuntimeError):
    """거래소가 에러 JSON(`code`/`msg`)으로 답했다. 원문 code·msg를 그대로 보존한다."""

    def __init__(self, status: int, code: int | None, msg: str, path: str):
        super().__init__(f"HTTP {status} code={code} msg={msg!r} path={path}")
        self.status, self.code, self.msg, self.path = status, code, msg, path


class ReadOnlyViolation(RuntimeError):
    """PAPER(읽기 전용) 클라이언트로 계정 변경 요청을 보내려 했다."""


class TransportError(RuntimeError):
    """HTTP 응답을 받지 못한 전송 실패(타임아웃·연결 끊김·DNS). 🔴 **요청이 거래소에 닿아 처리됐는지 모른다** —
    POST였다면 계정 상태가 바뀌었을 수 있으므로 호출자는 재조회 전까지 상태를 '불명'으로 다룬다."""


class CredentialsMissing(RuntimeError):
    """서명 요청에 필요한 API 키/시크릿이 없다."""


class StartupAbort(RuntimeError):
    """LIVE 기동 게이트 실패 — 진입 금지·청산만 허용(exchange-rules §4)."""

    def __init__(self, reason: str, result: GateResult):
        super().__init__(reason)
        self.reason, self.result = reason, result
