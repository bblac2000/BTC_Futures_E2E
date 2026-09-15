"""런타임 규칙 로더 — REST 조회 → RuntimeRules + `runtime_rules` 테이블(조회 시각 포함)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from exchange import loader as LD
from exchange import store
from exchange.client import Response
from exchange.errors import CredentialsMissing, RulesError


class SnapClient:
    """스냅샷 응답을 돌려주는 가짜 REST — 호출 경로·서명 여부를 기록한다."""

    def __init__(self, snap, credentials=True):
        self.snap, self.credentials, self.calls = snap, credentials, []

    def get(self, path: str, params: dict | None = None, *, signed: bool = False) -> Response:
        self.calls.append((path, dict(params or {}), signed))
        if signed and not self.credentials:
            raise CredentialsMissing("no key")
        name = {v.path: k for k, v in LD.ENDPOINTS.items()}[path]
        data: Any = self.snap[name]["response"]
        if name == "leverageBracket":
            data = data[params["symbol"]] if params else data         # 실제 API는 리스트
        if name == "commissionRate":
            data = data[params["symbol"]] if params else data
        return Response(200, data, {})

    def post(self, *a, **k):
        raise AssertionError("loader must never POST")


def test_rest_load_hits_every_endpoint_with_correct_signing(snap):
    c = SnapClient(snap)
    rules, fetches = LD.load_runtime_rules(c, "BTCUSDT")
    got = {p: s for p, _q, s in c.calls}
    assert got == {"/fapi/v1/exchangeInfo": False, "/fapi/v1/leverageBracket": True,
                   "/fapi/v1/commissionRate": True, "/fapi/v1/fundingInfo": False,
                   "/fapi/v1/positionSide/dual": True, "/fapi/v1/multiAssetsMargin": True}
    assert rules.account_modes is not None and rules.account_modes.dual_side_position is False
    assert {f.endpoint for f in fetches} == set(LD.ENDPOINTS)
    assert set(rules.fetched_at_utc) == set(LD.ENDPOINTS)


def test_rest_load_without_credentials_is_explicit_about_what_is_missing(snap):
    """서명 조회가 불가능하면 조용히 넘어가지 않는다 — 브라켓·수수료 없이 사이징할 수 없다."""
    with pytest.raises(CredentialsMissing):
        LD.load_runtime_rules(SnapClient(snap, credentials=False), "BTCUSDT")


def test_snapshot_rules_equal_rest_rules(snap, rules):
    rest, _ = LD.load_runtime_rules(SnapClient(snap), "BTCUSDT")
    assert rest.symbol_rules == rules.symbol_rules and rest.brackets == rules.brackets
    assert rest.commission == rules.commission and rest.funding == rules.funding


def test_snapshot_missing_endpoint_is_fatal(snap):
    partial = {k: v for k, v in snap.items() if k != "leverageBracket"}
    with pytest.raises(RulesError, match="leverageBracket"):
        LD.rules_from_snapshots(partial, "BTCUSDT")


def test_persist_writes_one_row_per_endpoint_with_fetch_time_and_hash(snap, tmp_path):
    _, fetches = LD.load_runtime_rules(SnapClient(snap), "BTCUSDT")
    con = sqlite3.connect(tmp_path / "bot.sqlite")
    load_id = store.persist_fetches(con, fetches, mode="paper", source="rest")
    rows = con.execute("SELECT load_id, endpoint, symbol, mode, source, fetched_at_utc, payload_json, payload_sha256 "
                       "FROM runtime_rules ORDER BY endpoint").fetchall()
    assert len(rows) == len(LD.ENDPOINTS) and {r[0] for r in rows} == {load_id}
    for _lid, _ep, sym, mode, source, fetched, payload, sha in rows:
        assert sym == "BTCUSDT" and mode == "paper" and source == "rest" and fetched.endswith("Z")
        import hashlib
        assert hashlib.sha256(payload.encode()).hexdigest() == sha
        json.loads(payload)
    latest = store.latest_payload(con, "commissionRate", "BTCUSDT")
    assert latest is not None and latest["symbol"] == "BTCUSDT"


def test_mode_column_is_constrained(snap, tmp_path):
    _, fetches = LD.load_runtime_rules(SnapClient(snap), "BTCUSDT")
    con = sqlite3.connect(tmp_path / "bot.sqlite")
    with pytest.raises(ValueError):
        store.persist_fetches(con, fetches, mode="demo", source="rest")


def test_capture_then_reload_round_trips(snap, tmp_path):
    out = LD.capture_snapshots(SnapClient(snap), "BTCUSDT", tmp_path)
    assert {p.stem for p in out} == set(LD.ENDPOINTS)
    again = LD.rules_from_snapshot_dir(tmp_path, "BTCUSDT")
    base = LD.rules_from_snapshots(snap, "BTCUSDT")
    assert again.symbol_rules == base.symbol_rules and again.brackets == base.brackets
    meta = json.loads((tmp_path / "exchangeInfo.json").read_text())["_meta"]
    assert meta["read_only"] is True and meta["endpoint"] == "/fapi/v1/exchangeInfo"
