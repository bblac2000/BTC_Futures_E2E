"""`scripts/testnet_fee_probe.py` — 네트워크 없이 검증.

- 🔴 호스트 허용 목록: 메인넷(`fapi.binance.com`)·임의 호스트는 **요청마다** 거부(네트워크 도달 전)
- 설계서 §11 해석 규칙(사전확약)을 판정 함수가 그대로 구현하는가
- 두 다리(LONG→SHORT) 모두 청산·flat 확인, 실패 시 레지스트리에 쓰지 않는다
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from exchange.client import Response
from exchange.errors import BinanceAPIError
from exchange.orders import Direction
from sizing.position import liquidation_estimate

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "testnet_fee_probe.py"
TESTNET = "https://demo-fapi.binance.com"


def _load():
    spec = importlib.util.spec_from_file_location("testnet_fee_probe", SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


P = _load()


# ── 호스트 가드 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", ["https://fapi.binance.com", "https://fapi.binance.com/fapi/v1/order",
                                 "https://papi.binance.com", "http://demo-fapi.binance.com",
                                 "https://demo-fapi.binance.com.evil.example", "https://evil.example/demo-fapi.binance.com",
                                 "", "demo-fapi.binance.com"])
def test_non_testnet_urls_are_refused(url):
    with pytest.raises(P.NotTestnet):
        P.require_testnet(url)


@pytest.mark.parametrize("url", ["https://demo-fapi.binance.com", "https://demo-fapi.binance.com/fapi/v1/order?x=1",
                                 "https://testnet.binancefuture.com"])
def test_testnet_urls_are_accepted(url):
    P.require_testnet(url)


def test_client_for_mainnet_is_refused_before_any_network_call():
    calls: list = []
    with pytest.raises(P.NotTestnet):
        P.make_client("https://fapi.binance.com", "k", "s", opener=lambda *a, **k: calls.append(a))
    assert calls == []


def test_every_request_is_rechecked_even_if_base_url_is_changed_later():
    """생성 시 1회 검사만으로는 부족하다 — 실제로 나가는 URL을 요청마다 본다."""
    calls: list = []
    c = P.make_client(TESTNET, "k", "s", opener=lambda *a, **k: calls.append(a))
    c.base_url = "https://fapi.binance.com"
    with pytest.raises(P.NotTestnet):
        c.post("/fapi/v1/order", {"symbol": "BTCUSDT"})
    with pytest.raises(P.NotTestnet):
        c.get("/fapi/v1/premiumIndex", {"symbol": "BTCUSDT"})
    assert calls == []


def test_guarded_opener_passes_testnet_requests_through():
    seen: list = []

    class R:
        status = 200
        headers: dict = {}

        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout):
        seen.append(req.full_url)
        return R()

    c = P.make_client(TESTNET, "k", "s", opener=opener)
    assert c.get("/fapi/v1/time").data == {"ok": True}
    assert seen == [f"{TESTNET}/fapi/v1/time"]
    assert c._open is not urllib.request.urlopen


# ── main: 환경 변수 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("env", [
    {},
    {"BINANCE_TESTNET_BASE_URL": TESTNET},
    {"BINANCE_TESTNET_BASE_URL": "https://fapi.binance.com", "BINANCE_TESTNET_API_KEY": "KEYVAL-9f3",
     "BINANCE_TESTNET_API_SECRET": "SECVAL-7c1"},
    #  메인넷 키를 테스트넷 칸에 넣은 경우 — 같은 값이면 거부
    {"BINANCE_TESTNET_BASE_URL": TESTNET, "BINANCE_TESTNET_API_KEY": "KEYVAL-9f3",
     "BINANCE_TESTNET_API_SECRET": "SECVAL-7c1", "BINANCE_API_KEY": "KEYVAL-9f3"},
    #  메인넷 변수로 대체하지 않는다
    {"BINANCE_TESTNET_BASE_URL": TESTNET, "BINANCE_API_KEY": "mk", "BINANCE_API_SECRET": "ms"},
])
def test_main_refuses_bad_environment_without_network(env, capsys):
    assert P.main([], env=env, client_factory=_no_network) == 2
    out = capsys.readouterr()
    assert "KEYVAL-9f3" not in out.out + out.err and "SECVAL-7c1" not in out.out + out.err, "키 값을 출력하지 않는다"


def _no_network(*a, **k):
    raise AssertionError("환경 검사 실패 시 클라이언트를 만들지 않는다")


# ── 가짜 테스트넷 ─────────────────────────────────────────────────────────────
SNAP_PATHS = {"/fapi/v1/exchangeInfo": "exchangeInfo", "/fapi/v1/leverageBracket": "leverageBracket",
              "/fapi/v1/commissionRate": "commissionRate", "/fapi/v1/fundingInfo": "fundingInfo"}


@dataclass
class FakeTestnet:
    snap: dict
    rules: Any
    model: str = "fee"                      # fee | no_fee | neither
    mark: Decimal = Decimal("60000")
    commission_asset: str = "USDT"
    leverage_row: int | None = None         # positionRisk가 다른 레버리지를 보고하는 경우
    liq_zero: bool = False
    ignore_close: bool = False
    trades_delay: int = 0                   # userTrades가 비어 있는 조회 횟수
    fail_v3: bool = False
    amt: Decimal = Decimal("0")
    entry: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    leverage: int = 5
    margin_type: str = "isolated"
    next_id: int = 1
    trades: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)

    def _row(self) -> dict:
        base = {"symbol": "BTCUSDT", "positionSide": "BOTH", "marginType": self.margin_type,
                "leverage": str(self.leverage_row or self.leverage), "markPrice": str(self.mark)}
        if self.amt == 0:
            return base | {"positionAmt": "0.000", "entryPrice": "0.0", "isolatedWallet": "0",
                           "isolatedMargin": "0.00000000", "unRealizedProfit": "0.00000000", "liquidationPrice": "0"}
        q = abs(self.amt)
        n = q * self.entry
        L = Decimal(self.leverage)
        wallet = {"fee": n / L - self.commission, "no_fee": n / L, "neither": n / L - self.commission / 2}[self.model]
        d = Direction.LONG if self.amt > 0 else Direction.SHORT
        rate = self.commission / n if self.model == "fee" else Decimal("0")
        est = liquidation_estimate(d, self.entry, n, self.leverage, self.rules, taker=rate)
        tick = self.rules.symbol_rules.tick_size
        liq = (est.price / tick).to_integral_value() * tick
        return base | {"positionAmt": str(self.amt), "entryPrice": str(self.entry),
                       "isolatedWallet": str(wallet.quantize(Decimal("0.00000001"))),
                       "isolatedMargin": str(wallet.quantize(Decimal("0.00000001"))),
                       "unRealizedProfit": "0.00000000", "liquidationPrice": "0" if self.liq_zero else str(liq)}

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        self.calls.append(("GET", path, dict(params or {})))
        data: Any
        if path in SNAP_PATHS:
            data = self.snap[SNAP_PATHS[path]]
        elif path == "/fapi/v1/premiumIndex":
            data = {"symbol": "BTCUSDT", "markPrice": str(self.mark)}
        elif path == "/fapi/v1/positionSide/dual":
            data = {"dualSidePosition": False}
        elif path == "/fapi/v1/multiAssetsMargin":
            data = {"multiAssetsMargin": False}
        elif path == "/fapi/v2/positionRisk":
            data = [self._row()]
        elif path == "/fapi/v3/positionRisk":
            if self.fail_v3:
                raise BinanceAPIError(404, None, "Not Found", path)
            data = [self._row()]
        elif path in ("/fapi/v1/openOrders", "/fapi/v1/openAlgoOrders"):
            data = []
        elif path == "/fapi/v1/userTrades":
            if self.trades_delay > 0:
                self.trades_delay -= 1
                data = []
            else:
                data = self.trades.get(int(params["orderId"]), []) if params else []
        else:
            raise AssertionError(f"unexpected GET {path}")
        return Response(200, data, {})

    def post(self, path: str, params: dict | None = None, *, signed: bool = True) -> Response:
        p = dict(params or {})
        self.calls.append(("POST", path, p))
        if path == "/fapi/v1/leverage":
            self.leverage = int(p["leverage"])
            return Response(200, {"symbol": "BTCUSDT", "leverage": self.leverage}, {})
        if path == "/fapi/v1/marginType":
            self.margin_type = "isolated"
            return Response(200, {"code": 200}, {})
        if path == "/fapi/v1/order":
            assert p["type"] == "MARKET"
            q = Decimal(p["quantity"])
            signed_q = q if p["side"] == "BUY" else -q
            oid = self.next_id
            self.next_id += 1
            fee = q * self.mark * self.rules.commission.taker
            if p.get("reduceOnly") == "true":
                if not self.ignore_close:
                    self.amt += signed_q
                    if self.amt == 0:
                        self.entry, self.commission = Decimal("0"), Decimal("0")
            else:
                self.amt += signed_q
                self.entry = self.mark
                self.commission += fee
            self.trades[oid] = [{"orderId": oid, "qty": str(q), "price": str(self.mark),
                                 "commission": str(fee), "commissionAsset": self.commission_asset}]
            return Response(200, {"orderId": oid, "status": "FILLED", "avgPrice": str(self.mark),
                                  "executedQty": str(q)}, {})
        raise AssertionError(f"unexpected POST {path}")

    @property
    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


@pytest.fixture
def fake_factory(snap, rules):
    def make(**kw) -> FakeTestnet:
        #  세션 fixture를 변형하지 않게 깊은 복사
        return FakeTestnet(copy.deepcopy({k: v["response"] for k, v in snap.items()}), rules, **kw)
    return make


def _run(fake):
    return P.run_probe(fake, sleep=lambda s: None)


def test_fee_model_exchange_gives_confirmed_fee_and_both_legs_end_flat(fake_factory):
    f = fake_factory(model="fee")
    r = _run(f)
    assert r["verdict"] == "CONFIRMED_FEE"
    assert [leg["direction"] for leg in r["legs"]] == ["LONG", "SHORT"]
    assert all(leg["A"] == "FEE" and leg["B"] == "fee" and leg["verdict"] == "FEE" for leg in r["legs"])
    assert all(leg["closed_flat"] for leg in r["legs"]) and f.amt == 0
    #  테스트넷 값은 메커니즘 전용이라는 표시가 결과에 남는다
    assert "mechanism" in r["scope"]


def test_no_fee_model_exchange_gives_confirmed_no_fee(fake_factory):
    r = _run(fake_factory(model="no_fee"))
    assert r["verdict"] == "CONFIRMED_NO_FEE"
    assert all(leg["A"] == "NO_FEE" and leg["B"] == "no_fee" for leg in r["legs"])


def test_wallet_matching_neither_model_is_inconclusive(fake_factory):
    r = _run(fake_factory(model="neither"))
    assert r["verdict"] == "INCONCLUSIVE"
    assert all(leg["A"] == "A_NEITHER" and leg["verdict"] == "INCONCLUSIVE" for leg in r["legs"])


def test_only_allowlisted_posts_with_exits_reduce_only_and_leverage_100(fake_factory):
    f = fake_factory()
    _run(f)
    assert {c[1] for c in f.posts} <= {"/fapi/v1/leverage", "/fapi/v1/order"}
    lev = [c[2] for c in f.posts if c[1] == "/fapi/v1/leverage"]
    assert lev == [{"symbol": "BTCUSDT", "leverage": "100"}]
    orders = [c[2] for c in f.posts if c[1] == "/fapi/v1/order"]
    assert [(o["side"], o.get("reduceOnly")) for o in orders] == [("BUY", None), ("SELL", "true"),
                                                                  ("SELL", None), ("BUY", "true")]
    #  수량 = ceil_to_step(MIN_NOTIONAL × 1.1 / mark) — fixture BTC MIN_NOTIONAL 50: 50×1.1/60000 = 0.000917 → 0.001
    assert {o["quantity"] for o in orders} == {"0.001"}


def test_leverage_below_100_on_testnet_brackets_aborts_without_posting(fake_factory):
    f = fake_factory()
    lb = f.snap["leverageBracket"]
    for b in lb["BTCUSDT"][0]["brackets"]:
        b["initialLeverage"] = min(b["initialLeverage"], 75)
    with pytest.raises(P.ProbeAbort):
        _run(f)
    assert f.posts == []


def test_close_failure_raises_and_reports_position(fake_factory):
    f = fake_factory(ignore_close=True)
    with pytest.raises(P.CloseFailed) as e:
        _run(f)
    assert "positionAmt" in str(e.value)


def test_close_is_attempted_even_if_evaluation_crashes(fake_factory, monkeypatch):
    f = fake_factory()

    def boom(*a, **k):
        raise RuntimeError("evaluation bug")
    monkeypatch.setattr(P, "evaluate_leg", boom)
    r = _run(f)
    assert f.amt == 0
    assert r["verdict"] == "INCONCLUSIVE" and all("evaluation bug" in leg["error"] for leg in r["legs"])


def test_user_trades_retry_then_succeed(fake_factory):
    r = _run(fake_factory(trades_delay=3))
    assert r["verdict"] == "CONFIRMED_FEE"


def test_user_trades_never_arrive_is_inconclusive(fake_factory):
    r = _run(fake_factory(trades_delay=10_000))
    assert r["verdict"] == "INCONCLUSIVE"
    assert all(leg["verdict"] == "INCONCLUSIVE" for leg in r["legs"])


def test_v3_unavailable_is_recorded_not_fatal(fake_factory):
    r = _run(fake_factory(fail_v3=True))
    assert r["verdict"] == "CONFIRMED_FEE"
    assert all(leg["position_v3"] is None and "v3_error" in leg for leg in r["legs"])


# ── 판정 함수 — 설계서 §11 조항별 ──────────────────────────────────────────────
def _leg_inputs(fake_factory, **kw):
    f = fake_factory(**kw)
    f.leverage = 100
    f.post("/fapi/v1/order", {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.002"})
    return f, f._row(), f.trades[1]


@pytest.mark.parametrize("kw, expect_a, expect_leg", [
    ({"model": "fee"}, "FEE", "FEE"),
    ({"model": "no_fee"}, "NO_FEE", "NO_FEE"),
    ({"model": "neither"}, "A_NEITHER", "INCONCLUSIVE"),
])
def test_evaluate_leg_primary_rule(fake_factory, rules, kw, expect_a, expect_leg):
    f, row, trades = _leg_inputs(fake_factory, **kw)
    ev = P.evaluate_leg(Direction.LONG, row, trades, rules, gate_leverage=100)
    assert ev["A"] == expect_a and ev["verdict"] == expect_leg
    assert Decimal(ev["tol"]) == Decimal("0.002") * rules.symbol_rules.tick_size / 100 + Decimal("0.00000002")


def test_commission_not_in_usdt_is_inconclusive(fake_factory, rules):
    _f, row, trades = _leg_inputs(fake_factory, commission_asset="BNB")
    assert P.evaluate_leg(Direction.LONG, row, trades, rules, gate_leverage=100)["verdict"] == "INCONCLUSIVE"


def test_row_leverage_differs_from_gate_echo_is_inconclusive(fake_factory, rules):
    _f, row, trades = _leg_inputs(fake_factory)
    assert P.evaluate_leg(Direction.LONG, row, trades, rules, gate_leverage=75)["verdict"] == "INCONCLUSIVE"


def test_uncomputable_liquidation_price_makes_the_leg_inconclusive(fake_factory, rules):
    """§11 보충: B를 계산할 수 없으면 'B≠no_fee'를 충족하지 않은 것으로 본다."""
    _f, row, trades = _leg_inputs(fake_factory, liq_zero=True)
    ev = P.evaluate_leg(Direction.LONG, row, trades, rules, gate_leverage=100)
    assert ev["A"] == "FEE" and ev["B"] is None and ev["verdict"] == "INCONCLUSIVE"


def test_a_fee_but_b_no_fee_is_inconclusive(fake_factory, rules):
    _f, row, trades = _leg_inputs(fake_factory, model="no_fee")
    n = Decimal(row["entryPrice"]) * abs(Decimal(row["positionAmt"]))
    c = sum(Decimal(t["commission"]) for t in trades)
    row = row | {"isolatedWallet": str(n / 100 - c)}          # A는 FEE, 청산가는 no_fee 모델 그대로
    ev = P.evaluate_leg(Direction.LONG, row, trades, rules, gate_leverage=100)
    assert ev["A"] == "FEE" and ev["B"] == "no_fee" and ev["verdict"] == "INCONCLUSIVE"


def test_models_not_separable_is_inconclusive(fake_factory, rules):
    _f, row, trades = _leg_inputs(fake_factory)
    trades = [t | {"commission": "0.000001"} for t in trades]      # C ≤ 2×tol
    assert P.evaluate_leg(Direction.LONG, row, trades, rules, gate_leverage=100)["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("legs, verdict", [
    (["FEE", "FEE"], "CONFIRMED_FEE"), (["NO_FEE", "NO_FEE"], "CONFIRMED_NO_FEE"),
    (["FEE", "NO_FEE"], "INCONCLUSIVE"), (["FEE", "INCONCLUSIVE"], "INCONCLUSIVE"), (["FEE"], "INCONCLUSIVE"),
])
def test_overall_verdict(legs, verdict):
    assert P.overall_verdict([{"verdict": v} for v in legs]) == verdict


# ── 레지스트리 기록 ────────────────────────────────────────────────────────────
def test_registry_row_is_appended_with_the_next_number(fake_factory, tmp_path):
    reg = tmp_path / "trial_registry.md"
    reg.write_text((ROOT / "docs" / "trial_registry.md").read_text(encoding="utf-8"), encoding="utf-8")
    before = reg.read_text(encoding="utf-8")
    last = max(int(line.split("|")[1]) for line in before.splitlines() if line.startswith("| ") and line.split("|")[1].strip().isdigit())
    r = _run(fake_factory())
    n = P.append_registry(reg, r)
    after = reg.read_text(encoding="utf-8")
    assert n == last + 1 and after.startswith(before)
    new = after[len(before):].strip().splitlines()
    assert len(new) == 1 and new[0].startswith(f"| {n} |") and "CONFIRMED_FEE" in new[0] and "§11" in new[0]


def test_registry_is_not_written_when_a_leg_did_not_close(fake_factory, tmp_path, monkeypatch):
    reg = tmp_path / "trial_registry.md"
    reg.write_text("| # |\n|---|\n| 1 | x |\n", encoding="utf-8")
    f = fake_factory(ignore_close=True)
    monkeypatch.setattr(P, "REGISTRY", reg)
    monkeypatch.setattr(P, "OUT_DIR", tmp_path / "out")
    rc = P.main([], env={"BINANCE_TESTNET_BASE_URL": TESTNET, "BINANCE_TESTNET_API_KEY": "tk",
                         "BINANCE_TESTNET_API_SECRET": "ts"},
                client_factory=lambda *a, **k: f, sleep=lambda s: None)
    assert rc == 3
    assert reg.read_text(encoding="utf-8") == "| # |\n|---|\n| 1 | x |\n"


def test_main_happy_path_writes_json_and_registry(fake_factory, tmp_path, monkeypatch):
    reg = tmp_path / "trial_registry.md"
    reg.write_text("| # |\n|---|\n| 6 | x |\n", encoding="utf-8")
    monkeypatch.setattr(P, "REGISTRY", reg)
    monkeypatch.setattr(P, "OUT_DIR", tmp_path / "out")
    f = fake_factory()
    rc = P.main([], env={"BINANCE_TESTNET_BASE_URL": TESTNET, "BINANCE_TESTNET_API_KEY": "tk",
                         "BINANCE_TESTNET_API_SECRET": "ts"},
                client_factory=lambda *a, **k: f, sleep=lambda s: None)
    assert rc == 0
    assert "| 7 |" in reg.read_text(encoding="utf-8")
    assert len(list((tmp_path / "out").glob("*.json"))) == 1


# ── 소스 가드 ─────────────────────────────────────────────────────────────────
def test_source_posts_only_to_allowlisted_endpoints():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for bad in ("/fapi/v1/batchOrders", "/fapi/v1/algoOrder", "/fapi/v1/positionMargin", "/fapi/v1/allOpenOrders",
                "/sapi/", "/fapi/v1/listenKey"):
        assert not any(bad in c for c in consts), bad
    post_args = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "post":
            a = n.args[0]
            post_args.append(a.id if isinstance(a, ast.Name) else ast.dump(a))
    assert post_args and set(post_args) <= {"ORDER"}, post_args
    assert P.ORDER == "/fapi/v1/order"
    assert P.TESTNET_HOSTS == frozenset({"demo-fapi.binance.com", "testnet.binancefuture.com"})
    assert "fapi.binance.com" not in P.TESTNET_HOSTS


# ── Codex 검토(task-mu2ajp02-0vqtbd) FIX FIRST 항목 ─────────────────────────────
@pytest.mark.parametrize("url", ["https://demo-fapi.binance.com:8443", "https://demo-fapi.binance.com.:443",
                                 "https://demo-fapi.binance.com.", "https://user@demo-fapi.binance.com",
                                 "https://demo-fapi.binance.com@fapi.binance.com", "https://u:p@demo-fapi.binance.com"])
def test_ports_userinfo_and_trailing_dot_are_refused(url):
    with pytest.raises(P.NotTestnet):
        P.require_testnet(url)


def test_uppercase_testnet_host_is_the_same_host():
    P.require_testnet("https://DEMO-FAPI.binance.com/fapi/v1/time")


@pytest.mark.parametrize("target", ["https://fapi.binance.com/fapi/v1/order", "https://demo-fapi.binance.com/fapi/v1/order"])
def test_redirects_are_refused_even_to_testnet(target):
    """Q1: urllib 기본 opener는 3xx를 따라간다 → 우리 opener는 **모든** 리다이렉트를 거부한다(주문 POST가 다른 곳으로 가지 않게)."""
    h = P.RefuseRedirects()
    req = urllib.request.Request("https://demo-fapi.binance.com/fapi/v1/order", method="POST")
    with pytest.raises(P.NotTestnet):
        h.redirect_request(req, None, 307, "Temporary Redirect", {}, target)


def test_default_opener_is_built_with_the_redirect_refusal_and_no_default_redirect_handler():
    handlers = P.DEFAULT_OPENER.handlers
    assert any(isinstance(h, P.RefuseRedirects) for h in handlers)
    assert not any(type(h) is urllib.request.HTTPRedirectHandler for h in handlers)


def _orders(f):
    return [c[2] for c in f.posts if c[1] == "/fapi/v1/order"]


def test_existing_position_on_an_already_isolated_account_aborts_before_any_order(fake_factory):
    """Q3 추가 결함: 이미 ISOLATED면 게이트가 flat을 보지 않는다 → 프로브가 첫 다리 전에 무조건 확인."""
    f = fake_factory()
    f.amt, f.entry, f.leverage = Decimal("0.005"), Decimal("59000"), 100
    with pytest.raises(P.ProbeAbort):
        _run(f)
    assert _orders(f) == []


def test_existing_open_order_aborts_before_any_order(fake_factory, monkeypatch):
    f = fake_factory()
    real_get = f.get

    def get(path, params=None, *, signed=False):
        if path == "/fapi/v1/openOrders":
            return Response(200, [{"symbol": "BTCUSDT", "orderId": 1}], {})
        return real_get(path, params, signed=signed)
    monkeypatch.setattr(f, "get", get)
    with pytest.raises(P.ProbeAbort):
        _run(f)
    assert _orders(f) == []


def test_entry_transport_error_still_closes_and_is_not_a_verdict(fake_factory, monkeypatch):
    """전송 불명 — 실제로는 체결됐을 수 있다. finally가 재조회·청산하고 판정 미도달로 남긴다."""
    from exchange.errors import TransportError
    f = fake_factory()
    real_post = f.post
    state = {"n": 0}

    def post(path, params=None, *, signed=True):
        r = real_post(path, params, signed=signed)
        if path == "/fapi/v1/order" and params and "reduceOnly" not in params and state["n"] == 0:
            state["n"] += 1
            raise TransportError("POST /fapi/v1/order: read timed out")      # 체결은 됐는데 응답을 못 받음
        return r
    monkeypatch.setattr(f, "post", post)
    r = _run(f)
    assert f.amt == 0 and r["verdict_reached"] is False
    assert "TransportError" in r["legs"][0]["error"] and r["legs"][0]["closed_flat"]


def test_close_post_transport_error_is_retried_until_flat(fake_factory, monkeypatch):
    from exchange.errors import TransportError
    f = fake_factory()
    real_post = f.post
    state = {"fails": 1}

    def post(path, params=None, *, signed=True):
        if path == "/fapi/v1/order" and params and params.get("reduceOnly") == "true" and state["fails"] > 0:
            state["fails"] -= 1
            raise TransportError("POST /fapi/v1/order: connection reset")   # 전송 안 됨
        return real_post(path, params, signed=signed)
    monkeypatch.setattr(f, "post", post)
    r = _run(f)
    assert f.amt == 0 and r["verdict"] == "CONFIRMED_FEE" and r["verdict_reached"]


def test_no_short_leg_after_long_close_failure(fake_factory):
    f = fake_factory(ignore_close=True)
    with pytest.raises(P.CloseFailed):
        _run(f)
    entries = [o for o in _orders(f) if "reduceOnly" not in o]
    assert [o["side"] for o in entries] == ["BUY"], "LONG이 flat이 아니면 SHORT 진입은 없다"
    assert len([o for o in _orders(f) if o.get("reduceOnly") == "true"]) == P.CLOSE_ATTEMPTS


def test_non_filled_entry_response_is_an_error_and_closes(fake_factory, monkeypatch):
    f = fake_factory()
    real_post = f.post

    def post(path, params=None, *, signed=True):
        r = real_post(path, params, signed=signed)
        if path == "/fapi/v1/order" and params and "reduceOnly" not in params:
            return Response(200, r.data | {"status": "PARTIALLY_FILLED"}, {})
        return r
    monkeypatch.setattr(f, "post", post)
    r = _run(f)
    assert r["verdict_reached"] is False and all("FILLED" in leg["error"] for leg in r["legs"]) and f.amt == 0


def test_trades_not_matching_the_order_are_an_error(fake_factory, monkeypatch):
    f = fake_factory()
    real_get = f.get

    def get(path, params=None, *, signed=False):
        r = real_get(path, params, signed=signed)
        if path == "/fapi/v1/userTrades" and r.data:
            return Response(200, [t | {"qty": "0.500"} for t in r.data], {})
        return r
    monkeypatch.setattr(f, "get", get)
    r = _run(f)
    assert r["verdict_reached"] is False and all("userTrades" in leg["error"] for leg in r["legs"])


def test_b_tie_counts_as_not_contradicting(fake_factory, rules, monkeypatch):
    """§11: 'A=FEE 이고 B≠no_fee' — tie는 no_fee가 아니므로 FEE(Codex Q4 확인)."""
    _f, row, trades = _leg_inputs(fake_factory)
    real = P.liquidation_estimate

    def same_price(direction, entry, notional, leverage, rules_, *, taker=None):
        return real(direction, entry, notional, leverage, rules_, taker=Decimal(0))
    monkeypatch.setattr(P, "liquidation_estimate", same_price)
    ev = P.evaluate_leg(Direction.LONG, row, trades, rules, gate_leverage=100)
    assert ev["B"] == "tie" and ev["A"] == "FEE" and ev["verdict"] == "FEE"


def test_append_registry_refuses_a_result_without_a_reached_verdict(fake_factory, tmp_path):
    reg = tmp_path / "r.md"
    reg.write_text("| 1 | x |", encoding="utf-8")                 # 마지막 줄바꿈 없음
    r = _run(fake_factory())
    with pytest.raises(ValueError):
        P.append_registry(reg, r | {"verdict_reached": False})
    assert reg.read_text(encoding="utf-8") == "| 1 | x |"
    P.append_registry(reg, r)
    lines = reg.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "| 1 | x |" and lines[1].startswith("| 2 |")
