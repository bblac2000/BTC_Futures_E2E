"""수량·가격 정규화 — 순서가 곧 규칙이다(exchange-rules §3, v6 §2 "정규화 *순서*").

1. 수량 = step으로 **내림**(올림 금지 → -1111/-1013)
2. **내림 후** `qty × price ≥ MIN_NOTIONAL` 재확인(내림이 명목을 하한 아래로 민다 → -4164).
   미달이면 호출자가 준 명목 예산 안에서만 한 step 올리고, 아니면 **포기**(추격 금지).
3. 가격 = tick 배수, `Decimal` quantize(HALF_UP). 🚫 float 나눗셈.
4. MARKET 1주문 상한 = **MARKET_LOT_SIZE.maxQty** → 초과분은 분할.
reduceOnly 청산은 MIN_NOTIONAL 면제 — 잔여 청산이 막히지 않는다.

모든 한계값은 `SymbolRules`(런타임 조회)에서 온다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import StrEnum

from exchange.errors import RulesError
from exchange.rules import SymbolRules


class RejectReason(StrEnum):
    """`decisions.rejection_reason`에 그대로 기록되는 값(layer 4)."""
    BELOW_MIN_QTY = "below_min_qty"
    MIN_NOTIONAL = "min_notional"
    #  layer 2 사이징 거부 사유 — 같은 enum을 쓴다(decisions 테이블에 사유 종류가 두 곳에서 갈라지지 않게)
    SL_WRONG_SIDE = "sl_wrong_side"
    LIQ_DISTANCE = "liq_distance"
    LEVERAGE_INFEASIBLE = "leverage_infeasible"


@dataclass(frozen=True)
class QtyDecision:
    ok: bool
    qty: Decimal
    notional: Decimal
    reason: RejectReason | None
    stepped_up: bool
    detail: str


def _require_decimal(x: object, what: str) -> Decimal:
    if not isinstance(x, Decimal):
        raise TypeError(f"{what}는 Decimal이어야 한다(float 금지): {type(x).__name__}")
    return x


def floor_to_step(x: Decimal, step: Decimal) -> Decimal:
    return (x / step).to_integral_value(rounding=ROUND_FLOOR) * step


def ceil_to_step(x: Decimal, step: Decimal) -> Decimal:
    return (x / step).to_integral_value(rounding=ROUND_CEILING) * step


def _entry_step(r: SymbolRules) -> Decimal:
    """MARKET 주문은 MARKET_LOT_SIZE step이 기준. LOT_SIZE step과 어긋나면 둘 다 만족하는 값이 보장 안 된다."""
    if r.market_step % r.lot_step != 0:
        raise RulesError(f"{r.symbol}: MARKET step {r.market_step}이 LOT step {r.lot_step}의 배수가 아니다")
    return r.market_step


def normalize_price(price: Decimal, rules: SymbolRules) -> Decimal:
    price = _require_decimal(price, "price")
    q = (price / rules.tick_size).to_integral_value(rounding=ROUND_HALF_UP) * rules.tick_size
    q = q.quantize(rules.tick_size)
    if not rules.min_price <= q <= rules.max_price:
        raise RulesError(f"{rules.symbol}: 가격 {q}이 PRICE_FILTER [{rules.min_price}, {rules.max_price}] 밖")
    return q


def normalize_entry_qty(raw_qty: Decimal, ref_price: Decimal, rules: SymbolRules, *,
                        max_notional: Decimal | None = None) -> QtyDecision:
    """신규 진입 수량. `ref_price`는 명목 확인용 기준가(보통 mark). 분할은 `split_market_qty`."""
    raw_qty = _require_decimal(raw_qty, "raw_qty")
    ref_price = _require_decimal(ref_price, "ref_price")
    if raw_qty <= 0 or ref_price <= 0:
        raise ValueError(f"수량·가격은 양수여야 한다: qty={raw_qty} price={ref_price}")
    step = _entry_step(rules)
    q = floor_to_step(raw_qty, step)
    notional = q * ref_price
    if q < rules.market_min_qty or q < rules.lot_min_qty:
        return QtyDecision(False, q, notional, RejectReason.BELOW_MIN_QTY, False,
                           f"floor {q} < minQty {max(rules.market_min_qty, rules.lot_min_qty)}")
    if notional >= rules.min_notional:
        return QtyDecision(True, q, notional, None, False, "")
    up = q + step
    up_notional = up * ref_price
    if max_notional is not None and up_notional >= rules.min_notional and up_notional <= max_notional:
        return QtyDecision(True, up, up_notional, None, True,
                           f"floor {q}×{ref_price}={notional} < {rules.min_notional} → +1 step (예산 {max_notional})")
    return QtyDecision(False, q, notional, RejectReason.MIN_NOTIONAL, False,
                       f"floor 후 명목 {notional} < MIN_NOTIONAL {rules.min_notional}")


def split_market_qty(qty: Decimal, rules: SymbolRules, *, ref_price: Decimal | None,
                     reduce_only: bool) -> list[Decimal]:
    """MARKET_LOT_SIZE.maxQty 단위로 분할. 진입이면 **모든 조각**이 MIN_NOTIONAL을 넘도록 잔량을 보정한다."""
    qty = floor_to_step(_require_decimal(qty, "qty"), _entry_step(rules))
    mx = floor_to_step(rules.market_max_qty, rules.market_step)
    if qty <= 0:
        return []
    chunks: list[Decimal] = []
    left = qty
    while left > mx:
        chunks.append(mx)
        left -= mx
    chunks.append(left)
    if reduce_only or len(chunks) == 1:
        return chunks
    if ref_price is None:
        raise ValueError("진입 분할은 MIN_NOTIONAL 확인용 ref_price가 필요하다")
    need = max(ceil_to_step(rules.min_notional / ref_price, rules.market_step), rules.market_min_qty)
    if chunks[-1] < need:
        move = need - chunks[-1]
        if chunks[-2] - move < need:
            raise RulesError(f"{rules.symbol}: 분할 잔량을 MIN_NOTIONAL 위로 보정할 수 없다(qty={qty}, max={mx})")
        chunks[-2] -= move
        chunks[-1] += move
    return chunks


def exit_qty_from_position(position_amt: Decimal, rules: SymbolRules) -> Decimal:
    """전량 청산 수량 = `abs(positionAmt)`. step 배수가 아니면 대사 결함이므로 멈춘다(반올림으로 가리지 않는다)."""
    amt = abs(_require_decimal(position_amt, "position_amt"))
    if amt == 0:
        raise RulesError("포지션 0 — 청산할 수량이 없다")
    if amt % rules.market_step != 0:
        raise RulesError(f"{rules.symbol}: positionAmt {amt}이 step {rules.market_step} 배수가 아니다 — 대사 확인")
    return amt
