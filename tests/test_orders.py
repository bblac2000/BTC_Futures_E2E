"""주문 매트릭스(exchange-rules §2) — 원웨이·MARKET 전용·청산 reduceOnly·side는 BUY/SELL만."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from exchange import orders as O
from exchange.errors import OrderParamError
from exchange.orders import Direction, Intent, Side


@pytest.mark.parametrize(("direction", "intent", "side"), [
    (Direction.LONG, Intent.ENTRY, Side.BUY),
    (Direction.LONG, Intent.EXIT, Side.SELL),
    (Direction.SHORT, Intent.ENTRY, Side.SELL),
    (Direction.SHORT, Intent.EXIT, Side.BUY),
])
def test_order_matrix(direction, intent, side):
    assert O.side_for(direction, intent) is side


def test_public_builder_takes_direction_and_intent_not_side(rules):
    """🔴 `side=LONG`은 거부 또는 **반대 방향 체결** → 마진콜. 공개 생성기는 side를 받지 않는다 —
    (Direction, Intent)에서 side와 reduceOnly를 **함께** 도출한다."""
    s = rules.symbol_rules
    for bad_dir, bad_int in (("LONG", Intent.ENTRY), (Side.BUY, Intent.ENTRY), (Direction.LONG, "EXIT")):
        with pytest.raises(TypeError):
            O.market_order_params("BTCUSDT", bad_dir, bad_int, Decimal("0.001"), s)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Side("LONG")


def test_exit_intent_always_carries_reduce_only_and_entry_never_does(rules):
    """🔴 Codex Q4 — 예전 공개 API `reduce_only=False`로 **의미상 청산을 reduceOnly 없이** 만들 수 있었다.
    이제 reduceOnly는 Intent가 정한다. 호출자가 끌 방법이 없다."""
    s = rules.symbol_rules
    e = O.market_order_params("BTCUSDT", Direction.LONG, Intent.ENTRY, Decimal("0.001"), s)
    x = O.market_order_params("BTCUSDT", Direction.LONG, Intent.EXIT, Decimal("0.001"), s)
    assert e == {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001"}
    assert x == {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.001",
                 "reduceOnly": "true"}
    import inspect
    assert "reduce_only" not in inspect.signature(O.market_order_params).parameters


def test_quantity_off_step_or_above_market_max_is_refused(rules):
    s = rules.symbol_rules
    for q in (Decimal("0.0015"), s.market_max_qty + s.market_step, Decimal("0")):
        with pytest.raises(OrderParamError):
            O.market_order_params("BTCUSDT", Direction.LONG, Intent.ENTRY, q, s)


def test_close_side_comes_from_position_amt_sign(rules):
    s = rules.symbol_rules
    (long_close,) = O.close_position_orders(Decimal("0.004"), s)
    (short_close,) = O.close_position_orders(Decimal("-0.004"), s)
    assert (long_close["side"], long_close["reduceOnly"], long_close["quantity"]) == ("SELL", "true", "0.004")
    assert (short_close["side"], short_close["reduceOnly"], short_close["quantity"]) == ("BUY", "true", "0.004")


def test_close_splits_above_market_max_qty(rules):
    s = replace(rules.symbol_rules, market_max_qty=Decimal("0.003"))
    got = O.close_position_orders(Decimal("-0.007"), s)
    assert [g["quantity"] for g in got] == ["0.003", "0.003", "0.001"]
    assert all(g["side"] == "BUY" and g["reduceOnly"] == "true" for g in got)


def test_entry_orders_split_and_reject_below_min_notional(rules):
    s = replace(rules.symbol_rules, market_max_qty=Decimal("0.010"))
    got = O.entry_orders(Direction.SHORT, Decimal("0.021"), Decimal("60000"), s)
    assert [g["quantity"] for g in got] == ["0.010", "0.010", "0.001"]
    assert all(g["side"] == "SELL" and "reduceOnly" not in g for g in got)
    with pytest.raises(OrderParamError):
        O.entry_orders(Direction.LONG, Decimal("0.0005"), Decimal("60000"), s)


@pytest.mark.parametrize("key", ["stopPrice", "closePosition", "workingType", "priceProtect",
                                 "callbackRate", "price", "timeInForce", "activationPrice"])
def test_validator_rejects_removed_or_non_market_fields(key):
    p = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001", key: "x"}
    with pytest.raises(OrderParamError):
        O.validate_order_params(p)


@pytest.mark.parametrize("patch", [{"type": "LIMIT"}, {"type": "STOP_MARKET"}, {"side": "LONG"},
                                   {"positionSide": "LONG"}, {"reduceOnly": "false"}, {"reduceOnly": True}])
def test_validator_rejects_matrix_violations(patch):
    p = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001"} | patch
    with pytest.raises(OrderParamError):
        O.validate_order_params(p)


def test_validator_accepts_both_position_side():
    O.validate_order_params({"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.001",
                            "positionSide": "BOTH", "reduceOnly": "true"})
