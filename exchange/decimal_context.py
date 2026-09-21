"""실행 경로의 **이름 붙은 고정 10진 문맥** `EXEC_CTX` — exchange/·sizing/·paper/(엔진 전체)가 이 문맥 하나로 계산한다.

ccxt `decimal_to_precision`은 호출되면 스레드 전역 문맥을 rounding=HALF_UP · Underflow 트랩 켬으로 **바꿔 놓고 되돌리지 않는다**.
봇 프로세스는 ccxt를 쓰므로, 호출자 문맥을 물려받으면 사이징·정규화·체결 후 게이트·TP·트레일 경계가 ccxt 호출 이력에 따라
달라진다(단계 2c 발견 · Codex 단계 d #7·#8). 그래서 **정밀도까지 포함해 문맥 전체를 고정**한다(호출자 값을 하나도 쓰지 않는다):
- 정밀도 34(사이징이 쓰던 값) · 산술 rounding HALF_EVEN(파이썬 기본) · 트랩 = 파이썬 기본(InvalidOperation·DivisionByZero·Overflow) ·
  지수 범위·capitals·clamp = 파이썬 기본. 레지스트리 #22.
- 수량·가격 **양자화**는 호출마다 rounding을 명시한다(수량 내림 · 가격 HALF_UP — 헌법 exchange-rules §정규화).
- 적용: `exec_context()`(with 블록) · `@in_exec_context`(함수) — 엔진 공개 메서드 전부 · 정규화 함수 · 사이징 · 체결가 추정.
"""
from __future__ import annotations

import decimal
import functools
from collections.abc import Callable
from contextlib import AbstractContextManager

EXEC_PREC = 34
#  산술 버전 태그 — 엔진 스냅샷(`account_snapshots.raw_json.arith`)에 남고, 복원은 **같은 태그의 스냅샷만** 대조한다
#  (Codex 단계 d 후속 #3 · 28자리 시절 스냅샷과 34자리 DB 값을 섞어 비교하지 않는다). 문맥을 바꾸면 이 값도 바꾼다.
ARITH_VERSION = "exec_ctx/v1/prec34/half_even"
EXEC_CTX = decimal.Context(prec=EXEC_PREC, rounding=decimal.ROUND_HALF_EVEN, Emin=decimal.MIN_EMIN, Emax=decimal.MAX_EMAX,
                           capitals=1, clamp=0, flags=[],
                           traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow])


def exec_context() -> AbstractContextManager[decimal.Context]:
    return decimal.localcontext(EXEC_CTX)


def in_exec_context[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """함수 본문을 `EXEC_CTX`로 감싼다(중첩돼도 같은 문맥 — 결과가 호출 경로와 무관)."""
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with decimal.localcontext(EXEC_CTX):
            return fn(*args, **kwargs)
    return wrapper
