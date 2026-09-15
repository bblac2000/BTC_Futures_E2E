from __future__ import annotations

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
