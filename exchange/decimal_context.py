"""10진 문맥 고정 — 호출자(스레드 전역) 문맥의 rounding·트랩을 물려받지 않는다.

ccxt `decimal_to_precision`은 호출되면 전역 문맥을 rounding=HALF_UP · Underflow 트랩 켬으로 **바꿔 놓고 되돌리지 않는다**.
봇 프로세스는 ccxt를 쓰므로, 고정하지 않으면 사이징·정규화 결과가 ccxt 호출 이력에 따라 마지막 자리에서 달라진다(단계 2c 발견).
- 산술 rounding = HALF_EVEN(파이썬 기본값 — 기본 문맥에서의 기존 결과가 그대로다) · 트랩 = 파이썬 기본(InvalidOperation·DivisionByZero·Overflow).
- 정밀도는 인자로 주면 그 값, 아니면 호출자 값(ccxt는 정밀도를 바꾸지 않는다 · 사이징은 34자리로 감싸고 그 안에서 정규화를 부른다).
- 수량·가격 **양자화**는 여기와 별개로 호출마다 rounding을 명시한다(수량 내림 · 가격 HALF_UP — 헌법 exchange-rules §정규화).
"""
from __future__ import annotations

import decimal
import functools
from collections.abc import Callable
from contextlib import AbstractContextManager

ARITH_ROUNDING = decimal.ROUND_HALF_EVEN
_TRAPS = (decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow)

def pinned(prec: int | None = None) -> AbstractContextManager[decimal.Context]:
    c = decimal.getcontext()
    ctx = decimal.Context(prec=c.prec if prec is None else prec, rounding=ARITH_ROUNDING, Emin=c.Emin, Emax=c.Emax,
                          capitals=c.capitals, clamp=c.clamp, flags=[], traps=list(_TRAPS))
    return decimal.localcontext(ctx)


def pinned_rounding[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """함수 본문을 `pinned()`(호출자 정밀도 · 고정 rounding·트랩)으로 감싼다."""
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with pinned():
            return fn(*args, **kwargs)
    return wrapper
