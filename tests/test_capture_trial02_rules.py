"""`scripts/capture_trial02_rules.py` — 네트워크 없이: POST 없음 · 권한 거부 · 네 파일 · taker 5 bps 단언 · 실패 시 아무것도 안 씀."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from exchange.client import Response

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "capture_trial02_rules.py"
FIX = ROOT / "tests" / "fixtures" / "snapshots"


def _load():
    spec = importlib.util.spec_from_file_location("capture_trial02_rules", SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CAP = _load()
READ_ONLY = {"enableReading": True, "enableFutures": False, "enableSpotAndMarginTrading": False,
             "enableWithdrawals": False, "enableInternalTransfer": False, "permitsUniversalTransfer": False,
             "enableMargin": False, "enableVanillaOptions": False, "enablePortfolioMarginTrading": False,
             "enableFixApiTrade": False, "enableFixReadOnly": False, "ipRestrict": True}


class Fake:
    """고정 응답 = 커밋된 2026-09-02 fixture의 response(형식 검증용 · 값 자체는 테스트 대상 아님)."""

    def __init__(self, perms: dict, taker: str | None = None):
        self.perms, self.taker, self.calls = perms, taker, []
        self.resp = {n: json.loads((FIX / f"{n}.json").read_text())["response"]
                     for n in ("exchangeInfo", "leverageBracket", "commissionRate", "fundingInfo")}

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        self.calls.append((path, params, signed))
        if path == "/sapi/v1/account/apiRestrictions":
            return Response(200, self.perms, {})
        name = {"/fapi/v1/exchangeInfo": "exchangeInfo", "/fapi/v1/leverageBracket": "leverageBracket",
                "/fapi/v1/commissionRate": "commissionRate", "/fapi/v1/fundingInfo": "fundingInfo"}[path]
        data: Any = self.resp[name]
        if name in ("leverageBracket", "commissionRate"):              # fixture는 심볼 키 dict · 실제 per-symbol 응답 형태로
            data = data["BTCUSDT"]
        if name == "commissionRate" and self.taker is not None:
            data = dict(data, takerCommissionRate=self.taker)
        return Response(200, data, {})

    def post(self, *_a: Any, **_k: Any) -> Response:  # pragma: no cover — ReadOnlyClient가 막는다
        raise AssertionError("POST")


def test_source_has_no_post_and_no_mutating_endpoint():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "post"]
    consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for bad in ("/fapi/v1/order", "/fapi/v1/leverage", "/fapi/v1/marginType", "/fapi/v1/positionMargin"):
        assert not any(bad in c for c in consts), bad


def test_writes_four_files_all_get_and_pins_sha(tmp_path):
    f = Fake(READ_ONLY)
    s = CAP.capture(f, tmp_path, clock_ms=lambda: 1_790_000_000_000)
    assert sorted(p.name for p in tmp_path.glob("*.json")) == [
        "commissionRate.json", "exchangeInfo.json", "fundingInfo.json", "leverageBracket.json"]
    for name, sha in s["sha256"].items():
        assert hashlib.sha256((tmp_path / f"{name}.json").read_bytes()).hexdigest() == sha
    assert s["taker"] == "0.0005"
    assert f.calls[0][0] == "/sapi/v1/account/apiRestrictions"       # 권한 실측이 먼저
    assert {c[0] for c in f.calls[1:]} == {"/fapi/v1/exchangeInfo", "/fapi/v1/leverageBracket",
                                            "/fapi/v1/commissionRate", "/fapi/v1/fundingInfo"}
    assert CAP.load(tmp_path).commission.taker == Decimal("0.0005")


def test_taker_not_5bps_raises_and_writes_nothing(tmp_path):
    with pytest.raises(CAP.TakerMismatch):
        CAP.capture(Fake(READ_ONLY, taker="0.000450"), tmp_path, clock_ms=lambda: 0)
    assert list(tmp_path.iterdir()) == []


def test_non_read_key_refused_and_writes_nothing(tmp_path):
    with pytest.raises(CAP.NotReadOnlyKey):
        CAP.capture(Fake(READ_ONLY | {"enableFutures": True}), tmp_path, clock_ms=lambda: 0)
    assert list(tmp_path.iterdir()) == []
