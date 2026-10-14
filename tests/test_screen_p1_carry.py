"""S-carry-1 — 합성 자료로(실제 장부 계산 전 · 스펙 §6)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from research.screens import window as W
from research.screens.p1 import loader, reprice
from research.screens.p1.loader import Trade


def ms(*a: int) -> int:
    return int(dt.datetime(*a, tzinfo=dt.UTC).timestamp() * 1000)


def _ledger(tmp_path, rows):
    p = tmp_path / "ledger.csv"
    p.write_text(",".join(loader.LEDGER_COLS) + "\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


def test_trades_closing_in_the_reserve_are_dropped_without_parsing(tmp_path):
    ok = f"{ms(2026, 6, 30, 16)},{ms(2026, 5, 1)},v2_primary,190.0,304.0,1.0,0.0,0.1,0.57,0.152,0.5,0.0,10,regime_exit,0"
    late = f"{ms(2026, 7, 31)},{ms(2026, 6, 1)},v2_primary,NOT_A_NUMBER,x,x,x,x,x,x,x,x,x,end_of_sample,0"   # 값을 해석하면 오류
    got, dropped = loader.trades(_ledger(tmp_path, [ok, late]))
    assert [t.exit_ms for t in got] == [ms(2026, 6, 30, 16)] and dropped == 1


def test_screen_end_is_inclusive_and_the_first_reserve_millisecond_is_dropped(tmp_path):
    row = "{},{},r,190.0,304.0,1.0,0.0,0.0,0.57,0.0,0.0,0.0,1,x,0"
    got, dropped = loader.trades(_ledger(tmp_path, [row.format(W.SCREEN_END_MS, ms(2026, 6, 1)), row.format(W.SCREEN_END_MS + 1, ms(2026, 6, 1))]))
    assert len(got) == 1 and dropped == 1


def T(entry, exit_, notional=200.0, funding=1.0, resid=0.2, fees=0.6, slip=0.16, opp=0.4):  # noqa: ANN001, ANN201
    return Trade("r", entry, exit_, notional, notional * 1.6, funding, resid, fees, slip, opp, funding + resid - fees - slip - opp)


def test_cost_replaces_fees_and_slippage_and_dtb3_scales_by_holding_days_on_locked_capital():
    rates = [("2024-01-01", 5.0), ("2024-01-03", 4.0)]
    t = T(ms(2024, 1, 2, 12), ms(2024, 1, 2, 12) + 73 * reprice.DAY_MS)          # 진입일 1-2 → 1-1의 5.0%
    v = reprice.per_trade(t, rates)
    assert v["gross"] == pytest.approx((1.0 + 0.2) / 200 * 1e4)
    assert v["net_B"] == pytest.approx(v["gross"] - 17.5) and v["net_A"] == pytest.approx(v["gross"] - 10.0)
    assert v["dtb3"] == pytest.approx(320.0 * 0.05 * 73 / 365 / 200 * 1e4)
    assert v["net_B_dtb3"] == pytest.approx(v["net_B"] - v["dtb3"])
    assert v["orig_net"] == pytest.approx(t.net_pnl / 200 * 1e4)


def test_rate_uses_the_last_observation_on_or_before_the_entry_date():
    rates = [("2024-01-01", 5.0), ("2024-01-03", 4.0)]
    assert reprice.rate_at(rates, ms(2024, 1, 3)) == (4.0, False)
    assert reprice.rate_at(rates, ms(2024, 1, 2, 23, 59)) == (5.0, False)
    with pytest.raises(ValueError):
        reprice.rate_at(rates, ms(2023, 12, 31))


def test_blocks_are_60_calendar_days_by_entry_and_cover_the_window():
    s = ms(2021, 1, 1)
    assert reprice.block_of(s + 59 * reprice.DAY_MS, s) == 0 and reprice.block_of(s + 60 * reprice.DAY_MS, s) == 1
    assert reprice.n_blocks(s, W.SCREEN_END_MS) == 34
    assert reprice.n_blocks(ms(2024, 7, 1), W.SCREEN_END_MS) == 13


def test_block_bootstrap_redraws_empty_draws_and_is_deterministic():
    vals, blocks = np.array([1.0, 3.0]), np.array([0, 0])
    a = reprice.block_boot(vals, blocks, 10, np.random.default_rng(20261014), 200)
    b = reprice.block_boot(vals, blocks, 10, np.random.default_rng(20261014), 200)
    assert a == b and a[1] > 0 and a[0][0] == pytest.approx(2.0) and a[0][1] == pytest.approx(2.0)


def test_mde_uses_the_protocol_n_eff_floor_and_labels():
    v = np.array([0.0, 10.0] * 8)                                                      # ρ̂ < 0 → 바닥 0.15
    m, n_eff, rho = reprice.mde(v, reprice.COEF_UNCORRECTED)
    assert rho < 0 and n_eff == pytest.approx(16 / 1.6)
    assert m == pytest.approx(2.80 * np.std(v, ddof=1) / np.sqrt(10))
    assert [reprice.power_label(x) for x in (20, 20.01, 40, 40.01)] == ["feasible", "marginal", "marginal", "infeasible"]


def test_first_observation_rule_applies_only_before_2021_01_04_and_is_flagged():
    rates = [("2021-01-04", 0.09), ("2021-01-05", 0.08)]
    assert reprice.rate_at(rates, ms(2021, 1, 1)) == (0.09, True)
    assert reprice.rate_at(rates, ms(2021, 1, 2, 8)) == (0.09, True)
    assert reprice.rate_at(rates, ms(2021, 1, 4)) == (0.09, False)
    with pytest.raises(ValueError):                                                # 다른 첫 관측이면 규칙이 걸리지 않는다
        reprice.rate_at([("2021-01-05", 0.08)], ms(2021, 1, 4))


def test_dtb3_blank_values_are_missing_and_pre_2021_rows_are_never_parsed(tmp_path):
    p = tmp_path / "DTB3.csv"
    p.write_text("observation_date,DTB3\n2020-12-31,BAD\n2021-01-01,\n2021-01-04,0.09\n2021-01-05,.\n", encoding="utf-8")
    assert loader.dtb3(p) == [("2021-01-04", 0.09)]


def test_slippage_sensitivity_subtracts_the_original_pair_round_trip():
    v = reprice.per_trade(T(ms(2024, 1, 2), ms(2024, 2, 2)), [("2024-01-01", 5.0)])
    assert v["net_B_slip_dtb3"] == pytest.approx(v["net_B_dtb3"] - 8.0)


def test_undefined_rho_is_zero_and_two_trades_still_get_an_mde():
    assert reprice.lag1(np.array([1.0, 1.0, 1.0, 1.0])) == 0.0
    assert reprice.lag1(np.array([1.0, 2.0])) == 0.0
    m, n_eff, rho = reprice.mde(np.array([0.0, 10.0]), reprice.COEF_UNCORRECTED)
    assert rho == 0.0 and n_eff == pytest.approx(2 / 1.6) and m > 0


def test_empty_window_reports_null_statistics():
    from research.screens.p1 import run
    out = run.window_stats([], [], W.SCREEN_START_MS)
    assert out["n"] == 0 and out["mde"] is None and out["ci95_block60_net_B_dtb3"] is None
    assert all(v is None for v in out["mean"].values())
