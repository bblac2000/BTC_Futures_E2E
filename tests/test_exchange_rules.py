"""런타임 규칙 해석 — 값은 응답에서만 온다. 없으면 멈춘다(fail-closed)."""
from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from exchange import rules as R
from exchange.errors import RulesError

SYMBOL = "BTCUSDT"


def test_btc_rules_parse_from_the_captured_exchange_info(rules):
    s = rules.symbol_rules
    #  기대값은 fixture(2026-09-02 캡처)의 값이다 — 런타임 코드에는 이 숫자가 없다.
    assert (s.tick_size, s.lot_step, s.market_step) == (Decimal("0.10"), Decimal("0.001"), Decimal("0.001"))
    assert (s.min_notional, s.market_max_qty, s.lot_max_qty) == (Decimal("50"), Decimal("120"), Decimal("1000"))
    assert s.liquidation_fee == Decimal("0.012500") and s.status == "TRADING"
    assert all(isinstance(v, Decimal) for v in (s.tick_size, s.min_notional, s.liquidation_fee))


def test_brackets_parse_float_json_without_float_error(rules):
    """VolumeClockBot 스냅샷은 `0.004`를 JSON float로 저장했다 — Decimal('0.004')여야지 0.00400000000000000008이 아니다."""
    b1 = rules.brackets[0]
    assert b1.maint_margin_ratio == Decimal("0.004") and str(b1.maint_margin_ratio) == "0.004"
    assert (b1.initial_leverage, b1.notional_cap) == (150, Decimal("300000"))
    assert rules.max_leverage == 150 and len(rules.brackets) == 12


def test_brackets_parse_string_form_too():
    resp = [{"symbol": SYMBOL, "brackets": [
        {"bracket": "1", "initialLeverage": "150", "notionalCap": "300000", "notionalFloor": "0",
         "maintMarginRatio": "0.004", "cum": "0.0"}]}]
    (b,) = R.parse_brackets(resp, SYMBOL)
    assert b.maint_margin_ratio == Decimal("0.004") and b.initial_leverage == 150


def test_bracket_lookup_by_notional(rules):
    assert rules.bracket_for_notional(Decimal("0")).bracket == 1
    assert rules.bracket_for_notional(Decimal("299999.99")).bracket == 1
    assert rules.bracket_for_notional(Decimal("300000")).bracket == 2
    with pytest.raises(RulesError):
        rules.bracket_for_notional(rules.brackets[-1].notional_cap + 1)


def test_non_contiguous_brackets_are_rejected():
    resp = [{"symbol": SYMBOL, "brackets": [
        {"bracket": 1, "initialLeverage": 150, "notionalCap": 300000, "notionalFloor": 0, "maintMarginRatio": 0.004, "cum": 0},
        {"bracket": 2, "initialLeverage": 100, "notionalCap": 800000, "notionalFloor": 310000, "maintMarginRatio": 0.005, "cum": 300}]}]
    with pytest.raises(RulesError, match="이어지지"):
        R.parse_brackets(resp, SYMBOL)


def test_missing_filter_is_fatal_not_defaulted(snap):
    ei = copy.deepcopy(snap["exchangeInfo"]["response"])
    btc = next(s for s in ei["symbols"] if s["symbol"] == SYMBOL)
    btc["filters"] = [f for f in btc["filters"] if f["filterType"] != "MIN_NOTIONAL"]
    with pytest.raises(RulesError, match="MIN_NOTIONAL"):
        R.parse_symbol_rules(ei, SYMBOL)


def test_unknown_symbol_is_fatal(snap):
    with pytest.raises(RulesError):
        R.parse_symbol_rules(snap["exchangeInfo"]["response"], "DOGEUSDT")


def test_rate_limits_come_from_exchange_info(rules):
    got = {(r.rate_limit_type, r.interval, r.interval_num): r.limit for r in rules.rate_limits}
    assert got == {("REQUEST_WEIGHT", "MINUTE", 1): 2400, ("ORDERS", "MINUTE", 1): 1200,
                   ("ORDERS", "SECOND", 10): 300}


def test_commission_and_funding(rules):
    assert rules.commission == R.Commission(Decimal("0.000200"), Decimal("0.000500"))
    assert rules.funding.present and rules.funding.cap == Decimal("0.00300")
    assert rules.funding.floor == Decimal("-0.00300") and rules.funding.interval_hours == 8


def test_symbol_absent_from_funding_info_is_marked_not_guessed():
    """v6 §6: fundingInfo에 없으면 거래소 기본 → 런타임 확정. 🚫 추정 cap을 넣지 않는다."""
    fi = R.parse_funding_info([{"symbol": "ETHUSDT", "adjustedFundingRateCap": "0.003",
                                "adjustedFundingRateFloor": "-0.003", "fundingIntervalHours": 8}], SYMBOL)
    assert fi == R.FundingInfo(present=False, cap=None, floor=None, interval_hours=None)


def test_account_modes_require_real_booleans():
    assert R.parse_account_modes({"dualSidePosition": False}, {"multiAssetsMargin": False}) == \
        R.AccountModes(False, False)
    with pytest.raises(RulesError):
        R.parse_account_modes({"dualSidePosition": "false"}, {"multiAssetsMargin": False})
