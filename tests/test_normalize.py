"""정규화 순서(exchange-rules §3): floor qty → **내림 후** MIN_NOTIONAL 재확인 → tick은 Decimal."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from exchange import normalize as N
from exchange.errors import RulesError
from exchange.normalize import RejectReason


def test_floor_never_rounds_up(rules):
    s = rules.symbol_rules
    d = N.normalize_entry_qty(Decimal("0.0019999"), Decimal("60000"), s)
    assert d.ok and d.qty == Decimal("0.001")


def test_floor_can_push_notional_below_min_and_that_is_rechecked(rules):
    """🔴 전형 함정: 내림 전 명목은 통과, 내림 후 미달 → -4164. 내림 **후** 다시 본다."""
    s = rules.symbol_rules
    price = Decimal("49999")                   # 0.0010999 × 49999 ≈ 54.99 ≥ 50 (내림 전)
    d = N.normalize_entry_qty(Decimal("0.0010999"), price, s)
    assert not d.ok and d.reason is RejectReason.MIN_NOTIONAL
    assert d.qty == Decimal("0.001") and d.notional == Decimal("49.999")


def test_step_up_only_within_the_callers_notional_budget(rules):
    s = rules.symbol_rules
    price = Decimal("49999")
    ok = N.normalize_entry_qty(Decimal("0.0010999"), price, s, max_notional=Decimal("100"))
    assert ok.ok and ok.stepped_up and ok.qty == Decimal("0.002")
    no = N.normalize_entry_qty(Decimal("0.0010999"), price, s, max_notional=Decimal("99"))
    assert not no.ok and no.reason is RejectReason.MIN_NOTIONAL, "여유 없으면 포기(추격 금지)"


def test_below_min_qty_rejected(rules):
    d = N.normalize_entry_qty(Decimal("0.0009"), Decimal("1000000"), rules.symbol_rules)
    assert not d.ok and d.reason is RejectReason.BELOW_MIN_QTY


def test_price_uses_decimal_not_float_division(rules):
    """v6 §2: float `price/tick`는 99999.95 → 99999.9 같은 오계산을 만든다. HALF_UP → 100000.0."""
    s = rules.symbol_rules
    assert N.normalize_price(Decimal("99999.95"), s) == Decimal("100000.0")
    assert N.normalize_price(Decimal("99999.94"), s) == Decimal("99999.9")
    with pytest.raises(TypeError):
        N.normalize_price(99999.95, s)                    # type: ignore[arg-type]


def test_price_outside_filter_range_rejected(rules):
    s = rules.symbol_rules
    with pytest.raises(RulesError):
        N.normalize_price(s.min_price - 1, s)


def test_market_max_qty_splits_entries_and_keeps_every_chunk_above_min_notional(rules):
    s = replace(rules.symbol_rules, market_max_qty=Decimal("0.010"))      # 분할을 1,000 USDT 규모로 강제
    price = Decimal("60000")
    chunks = N.split_market_qty(Decimal("0.0215"), s, ref_price=price, reduce_only=False)
    assert sum(chunks) == Decimal("0.021") and all(c <= s.market_max_qty for c in chunks)
    assert all(c * price >= s.min_notional for c in chunks), chunks   # 잔량 0.001×60000=60 OK
    #  0.020을 max 0.019로 나누면 잔량 0.001×30000=30 < 50 → 앞 조각에서 떼어 잔량을 올린다
    tight = N.split_market_qty(Decimal("0.0200001"), replace(s, market_max_qty=Decimal("0.019")),
                               ref_price=Decimal("30000"), reduce_only=False)
    assert tight == [Decimal("0.018"), Decimal("0.002")], tight
    assert all(c * Decimal("30000") >= s.min_notional for c in tight), tight


def test_reduce_only_split_is_exempt_from_min_notional(rules):
    s = replace(rules.symbol_rules, market_max_qty=Decimal("0.010"))
    chunks = N.split_market_qty(Decimal("0.011"), s, ref_price=None, reduce_only=True)
    assert chunks == [Decimal("0.010"), Decimal("0.001")]


def test_exit_qty_is_abs_position_and_must_be_on_step(rules):
    s = rules.symbol_rules
    assert N.exit_qty_from_position(Decimal("-0.003"), s) == Decimal("0.003")
    with pytest.raises(RulesError):
        N.exit_qty_from_position(Decimal("0.0035"), s)
    with pytest.raises(RulesError):
        N.exit_qty_from_position(Decimal("0"), s)


@settings(max_examples=300, deadline=None)
@given(raw=st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("5"), places=7),
       price=st.decimals(min_value=Decimal("1000"), max_value=Decimal("300000"), places=1))
def test_property_normalized_entry_is_on_step_not_above_raw_and_notional_checked(rules, raw, price):
    s = rules.symbol_rules
    d = N.normalize_entry_qty(raw, price, s)
    assert d.qty <= raw
    assert d.qty % s.market_step == 0 and d.qty % s.lot_step == 0
    assert d.notional == d.qty * price
    if d.ok:
        assert d.qty >= s.market_min_qty and d.notional >= s.min_notional
    else:
        assert d.reason in (RejectReason.MIN_NOTIONAL, RejectReason.BELOW_MIN_QTY)
