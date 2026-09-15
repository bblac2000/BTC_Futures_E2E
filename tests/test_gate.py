"""기동 게이트(exchange-rules §4 · v6 §0.4 B2).

LIVE: 격리 확정 못 하면 **기동 중단**(진입 금지·청산만). PAPER: 계정 SET **0회**, WARNING만.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from exchange.client import Response
from exchange.errors import BinanceAPIError, CredentialsMissing, StartupAbort
from exchange.gate import Mode, run_startup_gate


@dataclass
class FakeAccount:
    """거래소 계정 상태를 흉내 내는 가짜 클라이언트 — 모든 호출을 기록한다."""
    margin_type: str = "cross"
    position_amt: str = "0"
    open_orders: list = field(default_factory=list)
    dual: bool = False
    multi: bool = False
    leverage: int = 5
    ignore_margin_change: bool = False          # POST는 성공했다고 답하지만 상태가 안 바뀜
    leverage_echo: int | None = None            # 거래소가 다른 레버리지로 답하는 경우
    credentials: bool = True
    hedge_long_amt: str = "0"
    hedge_short_amt: str = "0"
    other_rows: list = field(default_factory=list)          # 다른 심볼 positionRisk 행
    other_open_orders: list = field(default_factory=list)   # 다른 심볼 미체결
    open_algo_orders: list = field(default_factory=list)          # BTCUSDT 조건부(algo) 미체결
    other_open_algo_orders: list = field(default_factory=list)    # 다른 심볼 조건부(algo) 미체결
    bad_leverage_response: bool = False
    calls: list = field(default_factory=list)

    def _chk(self, signed):
        if signed and not self.credentials:
            raise CredentialsMissing("no key")

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        self.calls.append(("GET", path, dict(params or {})))
        self._chk(signed)
        data: Any
        if path == "/fapi/v2/positionRisk":
            base = {"symbol": "BTCUSDT", "marginType": self.margin_type, "leverage": str(self.leverage)}
            if self.dual:
                #  🔴 헤지 모드의 실제 모양: BOTH 행이 없고 LONG·SHORT 두 행이 온다
                data = [base | {"positionSide": "LONG", "positionAmt": self.hedge_long_amt},
                        base | {"positionSide": "SHORT", "positionAmt": self.hedge_short_amt}]
            else:
                data = [base | {"positionSide": "BOTH", "positionAmt": self.position_amt}]
            #  심볼 인자가 없으면 실제 API처럼 **계정 전체** 행을 돌려준다
            if not (params or {}).get("symbol"):
                data = data + list(self.other_rows)
        elif path == "/fapi/v1/openOrders":
            data = list(self.open_orders)
            if not (params or {}).get("symbol"):
                data = data + list(self.other_open_orders)
        elif path == "/fapi/v1/openAlgoOrders":
            #  공식 문서(2026-09-15 확인): symbol 선택 — 없으면 전 심볼 배열
            data = list(self.open_algo_orders)
            if not (params or {}).get("symbol"):
                data = data + list(self.other_open_algo_orders)
        elif path == "/fapi/v1/positionSide/dual":
            data = {"dualSidePosition": self.dual}
        elif path == "/fapi/v1/multiAssetsMargin":
            data = {"multiAssetsMargin": self.multi}
        else:
            raise AssertionError(f"unexpected GET {path}")
        return Response(200, data, {})

    def post(self, path: str, params: dict | None = None, *, signed: bool = True) -> Response:
        p = dict(params or {})
        self.calls.append(("POST", path, p))
        self._chk(signed)
        if path == "/fapi/v1/marginType":
            if self.margin_type == "isolated":
                raise BinanceAPIError(400, -4046, "No need to change margin type.", path)
            if not self.ignore_margin_change:
                self.margin_type = p["marginType"].lower()
            return Response(200, {"code": 200, "msg": "success"}, {})
        if path == "/fapi/v1/leverage":
            self.leverage = int(p["leverage"])
            if self.bad_leverage_response:
                return Response(200, {"symbol": p["symbol"], "note": "unexpected shape"}, {})
            return Response(200, {"leverage": self.leverage_echo or self.leverage, "symbol": p["symbol"],
                                  "maxNotionalValue": "1000000"}, {})
        if path == "/fapi/v1/positionSide/dual":
            self.dual = p["dualSidePosition"] == "true"
            return Response(200, {"code": 200, "msg": "success"}, {})
        raise AssertionError(f"unexpected POST {path}")

    @property
    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


# ── PAPER ────────────────────────────────────────────────────────────────
def test_paper_never_posts_even_when_everything_is_wrong(rules):
    acct = FakeAccount(margin_type="cross", dual=True, multi=True, position_amt="0.01")
    res = run_startup_gate(acct, rules, Mode.PAPER, leverage=75)
    assert acct.posts == [], "PAPER는 계정 SET 금지"
    assert res.entries_allowed and res.exits_allowed
    joined = " | ".join(res.warnings)
    assert "cross" in joined and "dualSidePosition" in joined and "multiAssetsMargin" in joined


def test_paper_also_refuses_posts_at_the_client_layer(rules):
    """게이트 코드가 실수로 POST를 부르더라도 PAPER 클라이언트 래퍼에서 막힌다(이중 방어)."""
    from exchange.client import ReadOnlyClient
    from exchange.errors import ReadOnlyViolation
    ro = ReadOnlyClient(FakeAccount())
    with pytest.raises(ReadOnlyViolation):
        ro.post("/fapi/v1/leverage", {"symbol": "BTCUSDT", "leverage": "75"})


def test_paper_without_credentials_warns_and_continues(rules):
    acct = FakeAccount(credentials=False)
    res = run_startup_gate(acct, rules, Mode.PAPER, leverage=75)
    assert res.entries_allowed and acct.posts == []
    assert any("읽을 수 없" in w for w in res.warnings)


# ── LIVE 성공 경로 ───────────────────────────────────────────────────────
def test_live_switches_cross_to_isolated_confirms_by_reread_and_sets_leverage(rules):
    acct = FakeAccount(margin_type="cross", leverage=5)
    res = run_startup_gate(acct, rules, Mode.LIVE, leverage=75)
    assert res.isolated_confirmed and res.leverage_set == 75
    assert res.entries_allowed and res.exits_allowed
    posts = [(c[1], c[2]) for c in acct.posts]
    assert posts == [("/fapi/v1/marginType", {"symbol": "BTCUSDT", "marginType": "ISOLATED"}),
                     ("/fapi/v1/leverage", {"symbol": "BTCUSDT", "leverage": "75"})]
    #  확정은 POST 응답이 아니라 **재조회**로 한다
    gets = [c[1] for c in acct.calls]
    i_post = gets.index("/fapi/v1/marginType")
    assert "/fapi/v2/positionRisk" in gets[i_post + 1:]


def test_live_already_isolated_does_not_post_margin_type(rules):
    acct = FakeAccount(margin_type="isolated")
    res = run_startup_gate(acct, rules, Mode.LIVE, leverage=50)
    assert [c[1] for c in acct.posts] == ["/fapi/v1/leverage"] and res.isolated_confirmed


def test_live_4046_no_need_to_change_is_not_a_failure_if_reread_confirms(rules):
    acct = FakeAccount(margin_type="cross")
    acct.ignore_margin_change = True

    def post(path, params=None, *, signed=True):
        if path == "/fapi/v1/marginType":
            acct.calls.append(("POST", path, dict(params or {})))
            acct.margin_type = "isolated"       # 경합으로 이미 바뀐 상태
            raise BinanceAPIError(400, -4046, "No need to change margin type.", path)
        return FakeAccount.post(acct, path, params, signed=signed)
    acct.post = post                            # type: ignore[method-assign]
    res = run_startup_gate(acct, rules, Mode.LIVE, leverage=50)
    assert res.isolated_confirmed


def test_live_turns_hedge_mode_off_and_confirms(rules):
    acct = FakeAccount(margin_type="isolated", dual=True)
    res = run_startup_gate(acct, rules, Mode.LIVE, leverage=50)
    assert acct.dual is False and res.dual_side_position is False
    assert ("POST", "/fapi/v1/positionSide/dual", {"dualSidePosition": "false"}) in acct.calls


def test_live_hedge_switch_preflight_is_account_wide_not_just_btc(rules):
    """🔴 Codex Q3 — 포지션 모드는 **계정 전 심볼** 설정이다. BTC가 flat이어도 ETH 포지션·미체결이 있으면 POST 전에 중단."""
    eth = {"symbol": "ETHUSDT", "positionSide": "LONG", "positionAmt": "0.5", "marginType": "cross"}
    acct = FakeAccount(margin_type="isolated", dual=True, other_rows=[eth])
    with pytest.raises(StartupAbort) as e:
        run_startup_gate(acct, rules, Mode.LIVE, leverage=50)
    assert "ETHUSDT" in e.value.reason and acct.posts == []
    acct2 = FakeAccount(margin_type="isolated", dual=True, other_open_orders=[{"symbol": "XRPUSDT", "orderId": 9}])
    with pytest.raises(StartupAbort):
        run_startup_gate(acct2, rules, Mode.LIVE, leverage=50)
    assert acct2.posts == []


def test_live_hedge_switch_preflight_sees_algo_open_orders_on_any_symbol(rules):
    """🔴 Codex 재검토 F1-b — 일반 openOrders는 조건부(algo) 주문을 보여주지 않는다.
    공식 문서 `GET /fapi/v1/openAlgoOrders`(symbol 생략 = 전 심볼)로 POST 전에 본다(-4067 거부에 기대지 않는다)."""
    algo = {"algoId": 1, "symbol": "ETHUSDT", "algoType": "CONDITIONAL", "algoStatus": "NEW"}
    acct = FakeAccount(margin_type="isolated", dual=True, other_open_algo_orders=[algo])
    e = _abort(acct, rules)
    assert acct.posts == [] and "algo" in e.reason and "ETHUSDT" in e.reason
    assert ("GET", "/fapi/v1/openAlgoOrders", {}) in acct.calls, "계정 전역 조회는 symbol 없이"


def test_live_margin_switch_preflight_sees_btc_algo_open_orders(rules):
    algo = {"algoId": 2, "symbol": "BTCUSDT", "algoType": "CONDITIONAL", "algoStatus": "NEW"}
    acct = FakeAccount(margin_type="cross", open_algo_orders=[algo])
    _abort(acct, rules)
    assert acct.posts == []
    assert ("GET", "/fapi/v1/openAlgoOrders", {"symbol": "BTCUSDT"}) in acct.calls


def test_live_account_preflight_row_without_position_amt_aborts_before_post(rules):
    """🔴 Codex 재검토 F1 — 행에 positionAmt가 없으면 0으로 치지 않는다. 계정 전역 POST 전에 중단."""
    broken = {"symbol": "ETHUSDT", "positionSide": "LONG", "marginType": "cross"}      # positionAmt 없음
    acct = FakeAccount(margin_type="isolated", dual=True, other_rows=[broken])
    _abort(acct, rules)
    assert acct.posts == []


def test_live_margin_switch_row_without_position_amt_aborts_before_post(rules):
    class NoAmt(FakeAccount):
        def get(self, path, params=None, *, signed=False):
            r = super().get(path, params, signed=signed)
            if path == "/fapi/v2/positionRisk":
                return Response(200, [{k: v for k, v in row.items() if k != "positionAmt"} for row in r.data], {})
            return r
    acct = NoAmt(margin_type="cross")
    _abort(acct, rules)
    assert acct.posts == []


def test_live_transport_failure_after_a_mutating_post_is_a_startup_abort(rules):
    """🔴 Codex 재검토 F3 — POST가 거래소에 닿아 상태를 바꾼 뒤 타임아웃이 나면 결과를 **모른다**.
    그래도 결말은 항상 StartupAbort(진입 금지·청산 허용)이고 사유에 '상태 불명'이 남아야 한다."""
    from exchange.errors import TransportError

    class Flaky(FakeAccount):
        def post(self, path, params=None, *, signed=True):
            r = super().post(path, params, signed=signed)          # 상태는 바뀌었다
            if path == "/fapi/v1/leverage":
                raise TransportError("POST /fapi/v1/leverage: TimeoutError: read timed out")
            return r
    e = _abort(Flaky(margin_type="cross"), rules)
    assert "상태 불명" in e.reason
    #  raw OSError를 던지는 다른 클라이언트 구현이어도 새어 나가지 않는다
    class RawOS(FakeAccount):
        def post(self, path, params=None, *, signed=True):
            raise TimeoutError("read timed out")
    _abort(RawOS(margin_type="cross"), rules)


def test_paper_bad_position_amt_is_a_warning_not_a_crash(rules):
    """Codex 재검토 신규 — PAPER의 포지션 다리 스캔이 try 밖에서 InvalidOperation을 던졌다."""
    acct = FakeAccount(margin_type="isolated", position_amt="not-a-number")
    res = run_startup_gate(acct, rules, Mode.PAPER, leverage=50)
    assert res.entries_allowed and acct.posts == []
    assert any("읽을 수 없" in w for w in res.warnings)


def test_live_unexpected_response_shape_is_a_startup_abort_not_a_bare_exception(rules):
    """🔴 Codex Q5 — 응답 모양이 어긋나도 결과는 항상 StartupAbort(진입 금지·청산 허용)여야 한다."""
    acct = FakeAccount(margin_type="isolated", bad_leverage_response=True)
    e = _abort(acct, rules, leverage=50)
    assert "응답" in e.reason

    class Weird(FakeAccount):
        def get(self, path, params=None, *, signed=False):
            if path == "/fapi/v1/multiAssetsMargin":
                return Response(200, {"unexpected": 1}, {})
            return super().get(path, params, signed=signed)
    _abort(Weird(margin_type="isolated"), rules)


def test_live_hedge_mode_with_a_short_leg_open_aborts_without_posting(rules):
    """헤지 모드 flat 판정은 LONG·SHORT **두 행을 모두** 본다 — 한쪽만 보면 열린 다리를 놓친다."""
    acct = FakeAccount(margin_type="isolated", dual=True, hedge_short_amt="-0.002")
    with pytest.raises(StartupAbort) as e:
        run_startup_gate(acct, rules, Mode.LIVE, leverage=50)
    assert "헤지" in e.value.reason and acct.posts == []


def test_paper_reads_hedge_mode_rows_without_crashing(rules):
    acct = FakeAccount(margin_type="cross", dual=True)
    res = run_startup_gate(acct, rules, Mode.PAPER, leverage=50)
    assert acct.posts == [] and any("dualSidePosition" in w for w in res.warnings)
    assert not any("읽을 수 없" in w for w in res.warnings), "헤지 행 모양을 조회 실패로 오분류하면 안 된다"


# ── LIVE 중단 경로 — 진입 금지·청산 허용 ─────────────────────────────────
def _abort(acct, rules, leverage=50):
    with pytest.raises(StartupAbort) as e:
        run_startup_gate(acct, rules, Mode.LIVE, leverage=leverage)
    r = e.value.result
    assert r.entries_allowed is False and r.exits_allowed is True
    return e.value


def test_live_aborts_when_reread_is_not_isolated(rules):
    e = _abort(FakeAccount(margin_type="cross", ignore_margin_change=True), rules)
    assert "ISOLATED" in e.reason and e.result.isolated_confirmed is False


def test_live_aborts_instead_of_switching_with_an_open_position(rules):
    acct = FakeAccount(margin_type="cross", position_amt="-0.002")
    _abort(acct, rules)
    assert not any(c[1] == "/fapi/v1/marginType" for c in acct.posts)


def test_live_aborts_instead_of_switching_with_open_orders(rules):
    acct = FakeAccount(margin_type="cross", open_orders=[{"orderId": 1}])
    _abort(acct, rules)
    assert acct.posts == []


def test_live_aborts_on_multi_assets_margin(rules):
    acct = FakeAccount(margin_type="isolated", multi=True)
    e = _abort(acct, rules)
    assert "multiAssetsMargin" in e.reason and acct.posts == []


def test_live_aborts_when_leverage_echo_differs(rules):
    e = _abort(FakeAccount(margin_type="isolated", leverage_echo=20), rules, leverage=75)
    assert "레버리지" in e.reason


@pytest.mark.parametrize("lev", [0, 151])
def test_live_aborts_on_leverage_outside_bracket_range_without_posting(rules, lev):
    """상한은 **브라켓 조회값**(fixture 150x)에서 온다 — 리터럴이 아니다."""
    acct = FakeAccount(margin_type="isolated")
    _abort(acct, rules, leverage=lev)
    assert acct.posts == []


def test_live_aborts_without_credentials(rules):
    _abort(FakeAccount(credentials=False), rules)


def test_live_aborts_when_symbol_not_trading(rules):
    from dataclasses import replace
    halted = replace(rules, symbol_rules=replace(rules.symbol_rules, status="SETTLING"))
    acct = FakeAccount(margin_type="isolated")
    _abort(acct, halted)
    assert acct.posts == []
