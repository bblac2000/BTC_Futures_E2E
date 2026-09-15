"""`scripts/capture_account_snapshot.py` — 네트워크 없이 검증: POST 없음 · 권한 거부 · 기록 형식 · isolated 판정."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from exchange.client import Response
from exchange.errors import BinanceAPIError

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "capture_account_snapshot.py"


def _load():
    spec = importlib.util.spec_from_file_location("capture_account_snapshot", SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CAP = _load()


def test_script_source_has_no_post_call_and_no_mutating_endpoint():
    """🔴 주문·레버리지·마진·포지션모드 **변경** 경로가 코드에 없다. `.post(` 호출도 없다."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    posts = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "post"]
    assert posts == [], f".post() at lines {posts}"
    consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for bad in ("/fapi/v1/order", "/fapi/v1/batchOrders", "/fapi/v1/leverage", "/fapi/v1/marginType",
                "/fapi/v1/positionMargin", "/fapi/v1/allOpenOrders", "/fapi/v1/algoOrder"):
        assert not any(bad in c for c in consts), bad


class FakeBinance:
    def __init__(self, perms: dict, *, v3: bool = True, isolated_field: bool = False):
        self.perms, self.v3, self.isolated_field = perms, v3, isolated_field
        self.calls: list = []

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        self.calls.append(("GET", path, params, signed))
        row: dict[str, Any] = {"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0.000",
                               "marginType": "cross"}
        if self.isolated_field:
            row["isolated"] = False
        data: Any = {
            "/sapi/v1/account/apiRestrictions": self.perms,
            "/fapi/v1/positionSide/dual": {"dualSidePosition": False},
            "/fapi/v1/multiAssetsMargin": {"multiAssetsMargin": False},
            "/fapi/v2/positionRisk": [row],
        }.get(path)
        if path == "/fapi/v3/positionRisk":
            if not self.v3:
                raise BinanceAPIError(404, None, "Not Found", path)
            data = [{k: v for k, v in row.items() if k != "marginType"}]
        if data is None:
            raise AssertionError(f"unexpected GET {path}")
        return Response(200, data, {})

    def post(self, *a, **k):
        raise AssertionError("capture must never POST")


READ_ONLY = {"enableReading": True, "enableFutures": False, "enableWithdrawals": False,
             "enableSpotAndMarginTrading": False, "ipRestrict": True, "createTime": 1}


def _run(tmp_path, fake, **kw):
    return CAP.capture(fake, fake, tmp_path, clock_ms=lambda: 1_789_000_000_123, server_ms=1_789_000_000_100, **kw)


def test_read_only_key_writes_all_files_and_provenance(tmp_path):
    (tmp_path / "PROVENANCE.md").write_text("# Snapshot fixtures — provenance\n\nexisting table\n", encoding="utf-8")
    fake = FakeBinance(READ_ONLY)
    s = _run(tmp_path, fake)
    assert sorted(s["written"]) == ["multiAssetsMargin.json", "positionRisk_v2.json",
                                    "positionRisk_v3.json", "positionSideDual.json"]
    doc = json.loads((tmp_path / "positionRisk_v2.json").read_text())
    assert doc["_meta"]["synthetic"] is False and doc["_meta"]["read_only"] is True
    assert doc["_meta"]["params"] == {"symbol": "BTCUSDT"} and doc["_meta"]["captured_at_utc"].endswith("Z")
    assert all(c[0] == "GET" for c in fake.calls)
    prov = (tmp_path / "PROVENANCE.md").read_text()
    assert "existing table" in prov and CAP.PROV_START in prov and "has_isolated=**False**" in prov
    #  다시 돌리면 블록을 교체한다(중복 누적 없음)
    _run(tmp_path, FakeBinance(READ_ONLY, isolated_field=True))
    prov2 = (tmp_path / "PROVENANCE.md").read_text()
    assert prov2.count(CAP.PROV_START) == 1 and "has_isolated=**True**" in prov2


@pytest.mark.parametrize("flag", ["enableFutures", "enableWithdrawals", "enableSpotAndMarginTrading",
                                  "permitsUniversalTransfer"])
def test_key_with_any_non_read_permission_is_refused_before_writing(tmp_path, flag):
    fake = FakeBinance(READ_ONLY | {flag: True})
    with pytest.raises(CAP.NotReadOnlyKey):
        _run(tmp_path, fake)
    assert list(tmp_path.iterdir()) == []
    assert [c[1] for c in fake.calls] == ["/sapi/v1/account/apiRestrictions"], "권한 확인 전에 계정을 읽지 않는다"


def test_key_without_reading_permission_is_refused(tmp_path):
    with pytest.raises(CAP.NotReadOnlyKey):
        _run(tmp_path, FakeBinance(READ_ONLY | {"enableReading": False}))


def test_v3_unavailable_is_recorded_not_fatal(tmp_path):
    s = _run(tmp_path, FakeBinance(READ_ONLY, v3=False))
    assert "positionRisk_v3.json" not in s["written"] and "positionRisk_v3" in s["unavailable"]
    assert "unavailable" in (tmp_path / "PROVENANCE.md").read_text()


def test_dry_run_writes_nothing(tmp_path):
    s = _run(tmp_path, FakeBinance(READ_ONLY), dry_run=True)
    assert s["written"] == [] and list(tmp_path.iterdir()) == []
    assert s["positionRisk_v2"]["has_isolated"] is False


def test_captured_mode_files_still_load_as_runtime_rules(tmp_path, snap):
    """캡처가 합성 fixture를 대체해도 로더가 그대로 읽는다(파일 이름·형식 호환)."""
    from exchange.loader import rules_from_snapshots
    _run(tmp_path, FakeBinance(READ_ONLY))
    merged = dict(snap) | {n: json.loads((tmp_path / f"{n}.json").read_text())
                          for n in ("positionSideDual", "multiAssetsMargin")}
    r = rules_from_snapshots(merged, "BTCUSDT")
    assert r.account_modes is not None and r.account_modes.dual_side_position is False


def test_main_uses_the_ccxt_transport_read_only_and_never_posts(tmp_path, monkeypatch):
    """레지스트리 #8: 캡처 스크립트도 ccxt 전송. 키는 가짜 env, 네트워크·POST 없음."""
    made: list = []

    class FakeCcxt(FakeBinance):
        def __init__(self, **kw):
            super().__init__(READ_ONLY)
            self.kw = kw
            made.append(self)

        def sync_time(self):
            return 42

    monkeypatch.setattr(CAP, "CcxtRestClient", FakeCcxt)
    monkeypatch.setattr(CAP, "load_env", lambda path: {"BINANCE_API_KEY": "K", "BINANCE_API_SECRET": "S"})
    assert CAP.main(["--dry-run", "--out", str(tmp_path)]) == 0
    assert len(made) == 1 and made[0].kw["api_key"] == "K"
    assert all(c[0] == "GET" for c in made[0].calls) and list(tmp_path.iterdir()) == []
