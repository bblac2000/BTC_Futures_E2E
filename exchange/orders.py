"""주문 파라미터 — 원웨이 · MARKET 전용 · 청산 reduceOnly (exchange-rules §2).

| 목적 | side | reduceOnly |
|---|---|---|
| LONG 진입 | BUY | 없음 |
| LONG 청산 | SELL | "true" |
| SHORT 진입 | SELL | 없음 |
| SHORT 청산 | BUY | "true" |

🔴 `Direction`(LONG/SHORT)과 `Side`(BUY/SELL)는 **다른 타입**이다. `side`에 LONG/SHORT가 들어가면
   거부 또는 반대 방향 체결 → 마진콜. 그래서 파라미터 생성기는 `Side` 인스턴스만 받는다(문자열도 거부).
🚫 서버측 STOP/TP/TRAILING은 쓰지 않는다(2025-12 algoOrder 이관·구 엔드포인트 -4120). SL/TP는 봇 모니터링.

이 모듈은 **파라미터를 만들고 검사**할 뿐 전송하지 않는다. 전송은 layer 3의 모드 게이트 뒤에 있다.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from exchange.errors import OrderParamError
from exchange.normalize import exit_qty_from_position, normalize_entry_qty, split_market_qty
from exchange.rules import SymbolRules


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Intent(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


_MATRIX = {
    (Direction.LONG, Intent.ENTRY): Side.BUY,
    (Direction.LONG, Intent.EXIT): Side.SELL,
    (Direction.SHORT, Intent.ENTRY): Side.SELL,
    (Direction.SHORT, Intent.EXIT): Side.BUY,
}

#  `/fapi/v1/order`에서 제거됐거나(C2) MARKET 전용 정책에 맞지 않는 키
FORBIDDEN_KEYS = frozenset({"stopPrice", "closePosition", "workingType", "priceProtect", "callbackRate",
                            "activationPrice", "price", "timeInForce", "goodTillDate"})
ALLOWED_KEYS = frozenset({"symbol", "side", "type", "quantity", "reduceOnly", "positionSide",
                          "newClientOrderId", "newOrderRespType"})


def side_for(direction: Direction, intent: Intent) -> Side:
    if not isinstance(direction, Direction) or not isinstance(intent, Intent):
        raise TypeError("side_for(Direction, Intent)만 받는다")
    return _MATRIX[(direction, intent)]


def _fmt_qty(q: Decimal, r: SymbolRules) -> str:
    return format(q.quantize(r.market_step, rounding=ROUND_DOWN), "f")      # 이미 step 배수 — 내림은 명시만


def market_order_params(symbol: str, direction: Direction, intent: Intent, qty: Decimal,
                        rules: SymbolRules) -> dict[str, str]:
    """공개 생성기 — side와 reduceOnly를 **(Direction, Intent)에서 함께** 도출한다.

    🔴 Codex 검토(2026-09-15 Q4): 예전 서명 `(side, ..., reduce_only)`는 의미상 청산을
       `reduce_only=False`로 만들 수 있었다 → 반대 포지션을 **열 수** 있다. 호출자가 끌 수 있는 스위치를 없앴다.
    """
    if type(direction) is not Direction or type(intent) is not Intent:
        raise TypeError(f"(Direction, Intent)만 받는다 — 받은 값 {direction!r}, {intent!r}")
    return _params(symbol, side_for(direction, intent), qty, rules, reduce_only=intent is Intent.EXIT)


def _params(symbol: str, side: Side, qty: Decimal, rules: SymbolRules, *, reduce_only: bool) -> dict[str, str]:
    if type(side) is not Side:
        raise TypeError(f"side는 Side(BUY/SELL) 인스턴스여야 한다 — 받은 값 {side!r}")
    if symbol != rules.symbol:
        raise OrderParamError(f"심볼 불일치 {symbol} ≠ rules {rules.symbol}")
    if not isinstance(qty, Decimal) or qty <= 0:
        raise OrderParamError(f"수량은 양의 Decimal이어야 한다: {qty!r}")
    if qty % rules.market_step != 0:
        raise OrderParamError(f"수량 {qty}이 step {rules.market_step} 배수가 아니다 — normalize 먼저")
    if qty > rules.market_max_qty:
        raise OrderParamError(f"수량 {qty} > MARKET maxQty {rules.market_max_qty} — 분할 먼저")
    p = {"symbol": symbol, "side": side.value, "type": "MARKET", "quantity": _fmt_qty(qty, rules)}
    if reduce_only:
        p["reduceOnly"] = "true"
    validate_order_params(p)
    return p


def entry_orders(direction: Direction, qty: Decimal, ref_price: Decimal, rules: SymbolRules) -> list[dict[str, str]]:
    """신규 진입 주문들. 정규화 실패(MIN_NOTIONAL 등)는 `OrderParamError`로 올린다 — 사유는 호출자가 기록."""
    d = normalize_entry_qty(qty, ref_price, rules)
    if not d.ok:
        raise OrderParamError(f"진입 거부 {d.reason}: {d.detail}")
    return [market_order_params(rules.symbol, direction, Intent.ENTRY, c, rules)
            for c in split_market_qty(d.qty, rules, ref_price=ref_price, reduce_only=False)]


def close_position_orders(position_amt: Decimal, rules: SymbolRules) -> list[dict[str, str]]:
    """전량 청산 — side는 `positionAmt` 부호로 정한다(>0 SELL, <0 BUY), 수량 = abs, 전부 reduceOnly."""
    amt = exit_qty_from_position(position_amt, rules)
    held = Direction.LONG if position_amt > 0 else Direction.SHORT
    return [market_order_params(rules.symbol, held, Intent.EXIT, c, rules)
            for c in split_market_qty(amt, rules, ref_price=None, reduce_only=True)]


def validate_order_params(p: dict) -> None:
    """전송 직전 마지막 검사 — 헌법 매트릭스를 벗어나면 예외. 페이퍼·라이브 공통 경로에서 호출한다."""
    bad = FORBIDDEN_KEYS & p.keys()
    if bad:
        raise OrderParamError(f"금지 키 {sorted(bad)} — MARKET 전용·서버측 STOP/TP 미사용")
    unknown = p.keys() - ALLOWED_KEYS
    if unknown:
        raise OrderParamError(f"허용 목록에 없는 키 {sorted(unknown)}")
    if p.get("type") != "MARKET":
        raise OrderParamError(f"type={p.get('type')!r} — MARKET만 허용")
    if p.get("side") not in ("BUY", "SELL"):
        raise OrderParamError(f"side={p.get('side')!r} — BUY/SELL만(LONG/SHORT 절대 금지)")
    if "positionSide" in p and p["positionSide"] != "BOTH":
        raise OrderParamError(f"positionSide={p['positionSide']!r} — 원웨이는 BOTH(또는 생략)")
    if "reduceOnly" in p and p["reduceOnly"] != "true":
        raise OrderParamError(f"reduceOnly={p['reduceOnly']!r} — 청산이면 문자열 \"true\", 진입이면 키 생략")
    for k in ("symbol", "quantity"):
        if not isinstance(p.get(k), str) or not p[k]:
            raise OrderParamError(f"{k} 누락 또는 문자열 아님")
