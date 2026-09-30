"""레버리지 대역 (3, 30) 추가(트라이얼 #4 단계 (b) · 레지스트리 #65 · 헌법 v1.5) — 추가 전용 · 기본 (50, 100)과 기존 대역 불변.

#69 스냅샷 규칙(tick 0.10 · step 0.001 · MIN_NOTIONAL 50 · tier1 MMR 0.004 · taker 0.0005)으로 경계 사이징을 확인한다.
"""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

import pytest

from exchange.loader import rules_from_snapshot_dir
from exchange.orders import Direction
from sizing.config import PERMITTED_LEVERAGE, REGISTERED_LEVERAGE_BANDS, RegimeSizing, SizingLimits
from sizing.position import size_entry

ROOT = Path(__file__).resolve().parent.parent
RULES = rules_from_snapshot_dir(ROOT / "docs" / "trials" / "trial_04_rules_snapshot", "BTCUSDT")
R330 = RegimeSizing("t4", D("0.01"), 3, 30)
L330 = SizingLimits(leverage_range=(3, 30), liq_fee_on_liq_price=True)


def test_band_appended_default_and_old_bands_unchanged():
    assert REGISTERED_LEVERAGE_BANDS == ((50, 100), (10, 30), (3, 30))
    assert PERMITTED_LEVERAGE == (50, 100) and SizingLimits().leverage_range == (50, 100)
    SizingLimits(leverage_range=(10, 30))
    RegimeSizing("old", D("0.01"), 10, 30)


@pytest.mark.parametrize("rng", [(20, 40), (3, 31), (2, 30), (1, 30)])
def test_unregistered_limits_still_rejected(rng):
    with pytest.raises(ValueError):
        SizingLimits(leverage_range=rng)


@pytest.mark.parametrize("lo,hi", [(2, 30), (3, 31), (20, 60), (1, 3)])
def test_regimes_outside_every_band_still_rejected(lo, hi):
    with pytest.raises(ValueError):
        RegimeSizing("x", D("0.01"), lo, hi)


def test_widened_regimes_construct_but_must_fit_the_limits():
    """공시: (3,30) 등록으로 [5,30]·[3,3] 같은 부분 구간 레짐도 생성된다 — 하지만 size_entry는 레짐 ⊂ limits를 따로 요구한다."""
    r530 = RegimeSizing("w", D("0.01"), 5, 30)
    RegimeSizing("w3", D("0.01"), 3, 3)
    with pytest.raises(ValueError):
        size_entry(D("50000.0"), D("47500.0"), Direction.LONG, D("1000"), r530, RULES, SizingLimits(leverage_range=(10, 30)))
    with pytest.raises(ValueError):                                     # 기본 limits(50,100)는 3~30 레짐을 거부
        size_entry(D("50000.0"), D("47500.0"), Direction.LONG, D("1000"), R330, RULES, SizingLimits())


def test_boundary_sizing_under_snapshot_rules():
    """sl_dist 20% at 50,000 → 목표 명목 50 = 0.001 × 50,000(유효 step) → L = 3 · 1% → L = 30."""
    d20 = size_entry(D("50000.0"), D("40000.0"), Direction.LONG, D("1000"), R330, RULES, L330)
    assert d20.ok and d20.leverage == 3, d20
    d1 = size_entry(D("50000.0"), D("49500.0"), Direction.LONG, D("1000"), R330, RULES, L330)
    assert d1.ok and d1.leverage == 30, d1


def test_short_above_the_l3_gate_is_refused():
    """숏 L = 3 한계 sl < 21.835% — 21.9%는 어떤 L도 게이트를 통과하지 못한다."""
    d = size_entry(D("50000.0"), D("60950.0"), Direction.SHORT, D("1000"), R330, RULES, L330)
    assert not d.ok and d.leverage is None, d
