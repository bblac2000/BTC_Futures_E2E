from __future__ import annotations

import decimal
import json
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "snapshots"
SYMBOL = "BTCUSDT"


def load_snapshot(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def snap():
    """VolumeClockBot 캡처 스냅샷(2026-09-02 mainnet read-only) — tests/fixtures/snapshots/PROVENANCE.md."""
    return {n: load_snapshot(n) for n in ("exchangeInfo", "leverageBracket", "commissionRate",
                                          "fundingInfo", "positionSideDual", "multiAssetsMargin")}


@pytest.fixture(scope="session")
def rules(snap):
    from exchange.loader import rules_from_snapshots
    return rules_from_snapshots(snap, SYMBOL)


@pytest.fixture(autouse=True)
def _default_decimal_context():
    """테스트마다 파이썬 기본 10진 문맥에서 시작한다 — 한 테스트(ccxt 호출 등)가 전역 문맥을 바꿔 뒤 테스트의
    마지막 자릿수를 바꾸지 않게(단계 2f: P1 골든이 전체 실행 순서에서만 28번째 자리가 달라진 사례)."""
    decimal.setcontext(decimal.Context())
    yield
