"""트라이얼 #3 (d) — 암별 상태 기계 · 전이·중단 사유 · P2/P3 · 하네스 불변식 · 결정론(계획 r2/r3 · 사용자 (d) 요구 1~10). 합성만."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.engine_replay import replay
from exchange.normalize import normalize_price
from exchange.orders import Direction, Intent, side_for
from paper.sender import adverse_fill_estimate
from sizing.position import size_entry
from strategies.trial03 import anchor as A
from strategies.trial03.config import LIMITS, REGIME, TF_V1, TfParams
from strategies.trial03.exit_schedule import PositionBusyError
from strategies.trial03.features import OiIndex
from strategies.trial03.harness import Admissibility, RulesSnapshotMismatch, complete_days, load_rules, v_days
from strategies.trial03.strategy import BASE, Trial03, Variant
from tests.fixtures import t3_scenario as S

ROOT = Path(__file__).resolve().parent.parent
TICK = S.RULES.symbol_rules.tick_size
ARMS = ["L", "S"]
F = S.F_DEFAULT
M = MINUTE_MS


def qualified(r) -> list[dict]:
    return [e for e in S.tails(r) if e["reason"] == "qualified"]


def bar_at(sc: S.Scenario, open_ms: int) -> Bar1m:
    return next(b for b in sc.bars() if b.open_ms == open_ms)


def t0_index(r) -> int:
    return (qualified(r)[0]["t"] - S.DAY0) // M - 1


# ── 끝에서 끝(암마다 · 손으로 계산한 장부) ────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
def test_end_to_end_known_ledger(arm):
    sc = S.Scenario(arm=arm)
    r = S.run(sc)
    s = r.strategy
    assert s.funnel["qualified"] == 1 and s.entry == {"filled": 1, "exit.time_exit": 1}
    assert len(r.trades) == 1
    t, i = r.trades[0], r.trades[0]["t3"]
    d = Direction.LONG if arm == "L" else Direction.SHORT
    assert i["t_e"] - i["t0"] == 20 * M                                   # 첫 냉각 봉 = t0 + 20분
    assert t["entry_ms"] == i["t_e"] and t["exit_ms"] == t["entry_ms"] + 240 * M and t["exit_reason"] == "time_exit"
    m, atr = D(i["m"]), D(i["atr"])
    assert D(i["sl_dist"]) == D("1.5") * atr / m
    raw = m - D("1.5") * atr if d is Direction.LONG else m + D("1.5") * atr
    assert D(i["sl"]) == normalize_price(raw, S.RULES.symbol_rules) == D(t["sl"])
    dec = size_entry(m, D(i["sl"]), d, D(1000), REGIME, S.RULES, LIMITS)          # 결정 = 기준가 m 그대로(§1 29행)
    assert dec.ok and dec.leverage == i["decision_leverage"] and str(dec.qty) == i["decision_qty"]
    o = bar_at(sc, t["entry_ms"]).d("mark_open")
    quote = adverse_fill_estimate(side_for(d, Intent.ENTRY), o, TICK, D("0.0006"))
    assert D(t["entry_fill"]) == quote
    fill_dec = size_entry(quote, D(i["sl"]), d, D(1000), REGIME, S.RULES, LIMITS)  # 체결 시점 재사이징(6 bps 예상 체결가)
    assert D(t["qty"]) == fill_dec.qty and t["leverage"] == fill_dec.leverage
    assert D(t["exit_ref"]) == bar_at(sc, t["exit_ms"]).d("mark_open")
    net = (D(t["wallet_after"]) - D(1000)) / (D(t["qty"]) * D(t["entry_fill"])) * 10_000
    assert D(t["net_bps"]) == net and D(-23) < net < D(-21)               # 가격 평평 → 명목 22 bps
    assert s.funnel["in_cooldown"] == len(S.tails(r)) - 1


GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "golden_trial03_e2e.json").read_text())


@pytest.mark.parametrize("arm", ARMS)
def test_end_to_end_matches_committed_golden(arm):
    """배선(위 테스트)과 별개로 값 자체를 고정 — size_entry·엔진 안의 회귀도 잡는다(advisor (d) after #1)."""
    r = S.run(S.Scenario(arm=arm))
    g = GOLDEN[arm]
    t = r.trades[0]
    assert {k: t[k] for k in g["trade"]} == g["trade"] and t["t3"] == g["intent"]
    assert dict(r.strategy.funnel) == g["funnel"] and dict(r.strategy.entry) == g["entry"]
    assert S.digest(r) == g["digest"]


def test_real_runs_use_tf_v1_unchanged():
    assert TF_V1 == TfParams()


# ── 이벤트 깔때기 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
def test_quantile_invalid_whole_window(arm):
    r = S.run(S.Scenario(arm=arm), p=replace(S.P, quantile_min_defined=10**7))
    assert dict(r.strategy.funnel) == {"quantile_invalid": 2880} and r.trades == [] and S.tails(r) == []


@pytest.mark.parametrize("arm", ARMS)
def test_incomplete_day_is_not_admissible_and_r30_undefined_is_no_tail(arm):
    r = S.run(S.Scenario(arm=arm, drop={1440 + 100}))
    s = r.strategy
    assert s.sub["no_tail.r30_undefined"] == 1 and s.funnel["qualified"] == 0
    assert {e["reason"] for e in S.tails(r)} == {"not_admissible"} and s.sub["not_admissible.incomplete"] > 0


@pytest.mark.parametrize("arm", ARMS)
def test_missing_funding_boundary_is_not_admissible(arm):
    fl = [1440 + 14 * 60]                                                 # 구간 [13:51, 19:57]이 16:00을 지난다
    assert S.run(S.Scenario(arm=arm, flushes=fl)).strategy.funnel["qualified"] == 1
    r = S.run(S.Scenario(arm=arm, flushes=fl, no_funding_at={S.DAY0 + S.DAY + 16 * 3_600_000}))
    assert r.strategy.funnel["qualified"] == 0 and r.strategy.sub["not_admissible.funding"] > 0


@pytest.mark.parametrize("arm", ARMS)
def test_window_end_subreason(arm):
    t0 = qualified(S.run(S.Scenario(arm=arm)))[0]["t"]
    r = S.run(S.Scenario(arm=arm), window=(S.WINDOW[0], t0 + 365 * M))
    assert r.strategy.funnel["qualified"] == 0 and S.tails(r)[0]["sub"] == "window_end"


@pytest.mark.parametrize("arm", ARMS)
def test_cooldown_boundary_719_blocked_720_allowed(arm):
    base = S.run(S.Scenario(arm=arm))
    i0 = t0_index(base)
    t0 = qualified(base)[0]["t"]
    r = S.run(S.Scenario(arm=arm, flushes=[F, F + 715]))            # 두 번째 꼬리가 t0+715분부터 이어진다
    by_t = {e["t"]: e["reason"] for e in S.tails(r)}
    assert by_t[t0 + 719 * M] == "in_cooldown" and by_t[t0 + 720 * M] == "qualified"
    assert F - 9 <= i0 <= F and len(qualified(r)) == 2


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("oi,sub", [("none", "absent"), ("unusable", "unusable")])
def test_oi_missing_never_starts_cooldown(arm, oi, sub):
    r = S.run(S.Scenario(arm=arm, oi=oi))
    rs = S.tails(r)
    assert rs and {e["reason"] for e in rs} == {"oi_missing"} and {e["sub"] for e in rs} == {sub}
    assert r.strategy.cooldown_end == -1 and r.trades == []


@pytest.mark.parametrize("arm", ARMS)
def test_oi_not_decreasing_then_qualified_later(arm):
    t0 = qualified(S.run(S.Scenario(arm=arm)))[0]["t"]
    r = S.run(S.Scenario(arm=arm, oi="flat_then_decreasing", oi_switch_ms=t0 + 10 * M))
    rs = S.tails(r)
    assert rs[0]["reason"] == "oi_not_decreasing" and rs[0]["t"] == t0
    q = qualified(r)
    assert len(q) == 1 and q[0]["t"] > t0                             # 감소 아님은 쿨다운을 시작하지 않았다
    assert all(e["reason"] == "oi_not_decreasing" for e in rs if e["t"] < q[0]["t"])
    assert {e["reason"] for e in S.tails(S.run(S.Scenario(arm=arm, oi="increasing")))} == {"oi_not_decreasing"}


# ── 냉각 · 결정 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
def test_not_cooled_at_t0_plus_121(arm):
    r = S.run(S.Scenario(arm=arm, noise_until={F: F + 300}))
    ab = [e for e in r.strategy.events if e["kind"] == "abort"]
    assert [e["reason"] for e in ab] == ["not_cooled"] and ab[0]["t"] - ab[0]["t0"] == 121 * M and r.trades == []


def _cool_at(arm: str, noise_offset: int, variant: Variant = BASE):
    """교대 잡음을 t0 봉 + noise_offset까지. 잡음 수익률이 창에 조금 남아도 rv5 ≤ 0.5·rv_peak가 되므로(합성 값) 첫 냉각 봉은
    offset에 따라 정해진다 — offset 116 → 결정 t0 + 120(포함 경계), offset 117 → t0 + 121 → not_cooled. 교대 잡음의 짝수·홀수
    위상 때문에 S는 플러시를 한 봉 옮겨야 120에 정확히 떨어진다(L = F · S = F + 1)."""
    fl = F if arm == "L" else F + 1
    i0 = t0_index(S.run(S.Scenario(arm=arm, flushes=[fl])))
    return S.run(S.Scenario(arm=arm, flushes=[fl], noise_until={fl: i0 + noise_offset}), variant)


def _cool_at_120(arm: str, variant: Variant = BASE):
    return _cool_at(arm, 116, variant)


@pytest.mark.parametrize("arm", ARMS)
def test_decision_exactly_at_t0_plus_120(arm):
    r = _cool_at_120(arm)
    i = r.trades[0]["t3"]
    assert i["t_e"] - i["t0"] == 120 * M and S.aborts(r) == []
    late = _cool_at(arm, 117)                                            # 한 봉 늦으면 t0 + 121 → not_cooled
    assert S.aborts(late) == ["not_cooled"] and late.trades == []


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("spread,sub", [(5.0, "floor"), (3000.0, "ceiling")])
def test_sl_dist_out_of_range(arm, spread, sub):
    r = S.run(S.Scenario(arm=arm, spread=spread))
    assert S.aborts(r) == ["sl_dist_out_of_range"] and r.strategy.sub[f"sl_dist_out_of_range.{sub}"] == 1 and r.trades == []


@pytest.mark.parametrize("arm", ARMS)
def test_one_decision_per_event_no_retry(arm):
    """첫 냉각 봉에서 띠 바닥 중단 → 종결. 뒤의 봉에서는 띠를 통과했겠지만 다시 결정하지 않는다(계획 D5)."""
    sc = S.Scenario(arm=arm, spread=5.0, spread_from={F + 12: 1500.0})
    r = S.run(sc)
    assert S.aborts(r) == ["sl_dist_out_of_range"] and r.trades == [] and r.strategy.sub["sl_dist_out_of_range.floor"] == 1
    assert not [e for e in r.strategy.events if e["kind"] == "intent"]
    ab = next(e for e in r.strategy.events if e["kind"] == "abort")
    t_late = ab["t"] + 90 * M
    probe = Trial03(arm, rules=S.RULES, oi=OiIndex(*sc.oi_rows(), S.P), admissible=lambda t: None, p=S.P, window=S.WINDOW)
    m = D(0)
    for b in sc.bars():
        if b.open_ms + M > t_late:
            break
        probe.atr.add(b)
        m = b.d("mark_close")
    atr = probe.atr.atr(t_late)
    assert atr is not None and D("0.0044") <= D("1.5") * atr / m <= D("0.05")       # 그 봉이라면 통과


@pytest.mark.parametrize("arm", ARMS)
def test_sizing_rejected_at_decision(arm):
    r = S.run(S.Scenario(arm=arm), rules=S.rules_with(min_notional=10**6))
    assert S.aborts(r) == ["sizing_rejected_decision"] and r.trades == []


def _fill_bar_override(arm: str, key: str, value_of: Callable[[dict], float]) -> tuple[S.Scenario, int]:
    base = S.run(S.Scenario(arm=arm))
    i = base.trades[0]["t3"]
    fill_idx = (i["t_e"] - S.DAY0) // M
    val = float(value_of(i))
    return S.Scenario(arm=arm, over={fill_idx: {key: val}}), fill_idx


@pytest.mark.parametrize("arm", ARMS)
def test_sl_crossed_before_fill(arm):
    sc, _ = _fill_bar_override(arm, "open", lambda i: float(D(i["sl"])) + (-100 if arm == "L" else 100))
    r = S.run(sc)
    assert S.aborts(r) == ["sl_crossed_before_fill"] and r.trades == []


@pytest.mark.parametrize("arm", ARMS)
def test_sizing_rejected_at_fill(arm):
    sc, _ = _fill_bar_override(arm, "open", lambda i: float(D(i["m"])) * (1.08 if arm == "L" else 0.92))
    r = S.run(sc)
    assert S.aborts(r) == ["sizing_rejected_fill"] and r.trades == []


@pytest.mark.parametrize("arm", ARMS)
def test_normalization_at_fill(arm):
    sc, _ = _fill_bar_override(arm, "open", lambda i: float(D(i["m"])) * (1.03 if arm == "L" else 0.97))
    r = S.run(sc, rules=S.rules_with(min_notional=1000))
    assert S.aborts(r) == ["normalization"] and r.trades == []


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("what", ["sl", "liquidation"])
def test_exit_sl_and_liquidation_then_cooldown_then_idle(arm, what):
    base = S.run(S.Scenario(arm=arm))
    i = base.trades[0]["t3"]
    idx = (i["t_e"] - S.DAY0) // M + 1
    sl, m = float(D(i["sl"])), float(D(i["m"]))
    if what == "sl":
        ov = {"low": sl - 50} if arm == "L" else {"high": sl + 50}
    else:
        ov = {"low": m * 0.9} if arm == "L" else {"high": m * 1.1}
    r = S.run(S.Scenario(arm=arm, over={idx: ov}))
    assert r.strategy.entry == {"filled": 1, f"exit.{what}": 1} and r.trades[0]["exit_reason"] == what
    states = [e["state"] for e in r.strategy.events if e["kind"] == "state"]
    assert states == ["COOLING", "ENTRY_PENDING", "IN_POSITION", "COOLDOWN", "IDLE"]
    idle = [e for e in r.strategy.events if e.get("state") == "IDLE"][0]
    assert idle["t"] == i["t0"] + 720 * M                               # 쿨다운은 t0 기준(청산 기준 아님)


@pytest.mark.parametrize("arm", ARMS)
def test_position_busy_records_after_cooldown_start_then_raises(arm):
    sc = S.Scenario(arm=arm)
    p = replace(S.P, cooldown_ms=25 * M)
    rows, bad = sc.oi_rows()
    bars, fund = sc.bars(), sc.fundings()
    s = Trial03(arm, rules=S.RULES, oi=OiIndex(rows, bad, p), admissible=Admissibility(bars, fund, p=p, window_end=S.WINDOW[1]),
                p=p, window=S.WINDOW)
    with pytest.raises(PositionBusyError):
        replay(bars, fund, s, rules=S.RULES, limits=LIMITS, equity=D(1000), sizing_capital=D(1000), slippage_rate=D("0.0006"))
    busy = s.events[-1]
    assert busy["kind"] == "busy" and busy["arm"] == arm and busy["reason"] == "position_busy"
    assert s.cooldown_end == busy["ts_ms"] + 25 * M


# ── 변형 P2 · P3 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("k", [1, 5])
def test_p2_fill_timing(arm, k):
    r = S.run(S.Scenario(arm=arm), Variant(delay=k))
    t, i = r.trades[0], r.trades[0]["t3"]
    assert t["entry_ms"] == i["t_e"] + k * M and i["decided_ms"] == i["t_e"] + k * M - 1
    pend = [e for e in r.strategy.events if e.get("state") == "ENTRY_PENDING"][0]
    assert pend["t"] == i["t_e"] + k * M                                 # 상태 기록은 의도를 낸 봉의 마감(시간순)
    ts = [e["t"] for e in r.strategy.events if e["kind"] == "state"]
    assert ts == sorted(ts)
    base = S.run(S.Scenario(arm=arm)).trades[0]["t3"]
    assert {x: i[x] for x in ("t0", "t_e", "m", "sl", "sl_dist")} == {x: base[x] for x in ("t0", "t_e", "m", "sl", "sl_dist")}


@pytest.mark.parametrize("arm", ARMS)
def test_p2_edge_decision_at_120_delay_5(arm):
    r = _cool_at_120(arm, Variant(delay=5))
    i = r.trades[0]["t3"]
    assert i["t_e"] - i["t0"] == 120 * M and r.trades[0]["entry_ms"] == i["t_e"] + 5 * M and S.aborts(r) == []


@pytest.mark.parametrize("arm", ARMS)
def test_p3_reverses_fill_and_mirrors_sl_about_m(arm):
    r = S.run(S.Scenario(arm=arm), Variant(invert=True))
    t, i = r.trades[0], r.trades[0]["t3"]
    m, atr = D(i["m"]), D(i["atr"])
    assert t["direction"] == ("SHORT" if arm == "L" else "LONG")
    mirrored = m + D("1.5") * atr if arm == "L" else m - D("1.5") * atr
    assert D(i["intent_sl"]) == normalize_price(mirrored, S.RULES.symbol_rules) == D(t["sl"])
    orig = Direction.LONG if arm == "L" else Direction.SHORT
    assert size_entry(m, D(i["sl"]), orig, D(1000), REGIME, S.RULES, LIMITS).leverage == i["decision_leverage"]


# ── 워밍업 · 창 경계 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
def test_warmup_flush_creates_nothing(arm):
    r = S.run(S.Scenario(arm=arm, flushes=[600]))
    assert r.trades == [] and S.tails(r) == [] and r.strategy.started


@pytest.mark.parametrize("arm", ARMS)
def test_flush_straddling_window_start_qualifies_at_first_window_bar(arm):
    r = S.run(S.Scenario(arm=arm, flushes=[1440 + 3]))
    assert qualified(r)[0]["t"] == S.WINDOW[0] + M


# ── 하네스 · 입자 ────────────────────────────────────────────────────────────
def _fund_all(days: int) -> list[Funding]:
    return [Funding(S.DAY0 + d * S.DAY + h * 3_600_000, "0", "1") for d in range(days) for h in (0, 8, 16)]


def test_admissibility_real_window_end_edge():
    """2025-12-31 하루를 완전하게 주면 17:53은 판정 가능(구간 [13:23, 23:59] · 경계 없음), 17:54는 window_end."""
    d0 = A.IS_END_MS + 1 - S.DAY
    bars = [Bar1m(d0 + k * M, "1", "1", "1", "1", "1", "1", 1, "0", "0", "1", "1", "1", "1", "archive") for k in range(1440)]
    adm = Admissibility(bars, [], window_end=A.IS_END_MS)
    t_1754 = A.IS_END_MS + 1 - 366 * M
    assert adm(t_1754) == "window_end" and adm(t_1754 - M) is None


def test_admissibility_closed_interval_day_set_and_funding_upper_end():
    bars2 = [b for b in S.Scenario().bars() if b.open_ms < S.DAY0 + 2 * S.DAY]
    fund = _fund_all(2)
    adm = Admissibility(bars2, fund, window_end=S.DAY0 + 10 * S.DAY)
    t_mid = S.DAY0 + 2 * S.DAY - 366 * M                                 # 구간 끝 = 날 2 00:00 → 날 2가 필요
    assert adm(t_mid) == "incomplete" and adm(t_mid - M) is None
    t16 = S.DAY0 + S.DAY + 16 * 3_600_000 - 366 * M                      # 구간 끝 = 16:00(포함)
    assert adm(t16) is None
    adm2 = Admissibility(bars2, [f for f in fund if f.funding_ms != S.DAY0 + S.DAY + 16 * 3_600_000], window_end=S.DAY0 + 10 * S.DAY)
    assert adm2(t16) == "funding" and adm2(t16 - M) is None


def test_v_days_are_complete_and_quantile_valid():
    sc = S.Scenario()
    r = S.run(sc)
    assert v_days(r.strategy, complete_days(sc.bars())) == [(S.DAY0 + S.DAY) // S.DAY, (S.DAY0 + 2 * S.DAY) // S.DAY]


def test_input_validation_and_duplicate_minutes():
    from strategies.trial03.harness import InputError, validate_inputs
    sc = S.Scenario()
    bars, fund = sc.bars(), sc.fundings()
    validate_inputs(bars, fund)
    with pytest.raises(InputError):
        validate_inputs(bars[:10] + [bars[9]] + bars[10:], fund)                  # 중복 분
    with pytest.raises(InputError):
        validate_inputs(bars, fund + [fund[0]])                                    # 펀딩 버킷 중복
    with pytest.raises(InputError):
        validate_inputs(bars, [Funding(fund[0].funding_ms, "NaN", "60000")])        # 비유한 율
    with pytest.raises(InputError):
        validate_inputs(bars, [Funding(fund[0].funding_ms + 3_600_000, "0", "60000")])   # 격자 밖
    assert (S.DAY0 // S.DAY) not in complete_days(bars[:10] + [bars[9]] + bars[10:1439])


def test_run_arm_without_rules_uses_pinned_snapshot():
    import inspect

    from strategies.trial03 import harness as H
    assert inspect.signature(H.run_arm).parameters["rules"].default is None
    assert "load_rules()" in inspect.getsource(H.run_arm)


def test_load_rules_pins_snapshot_48_and_taker():
    rules = load_rules()
    assert rules.commission.taker == D("0.0005")
    with pytest.raises(RulesSnapshotMismatch):
        load_rules(expected={"exchangeInfo": "0" * 64})


# ── 결정론 ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arm", ARMS)
def test_determinism_in_process_and_across_spawned_processes(arm):
    d1, d2 = S.digest(S.run(S.Scenario(arm=arm))), S.digest(S.run(S.Scenario(arm=arm)))
    assert d1 == d2
    outs = {subprocess.run([sys.executable, "-m", "tests.fixtures.t3_scenario", arm], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.strip() for _ in range(2)}
    assert outs == {d1} == {GOLDEN[arm]["digest"]}


# ── 정적 검사 ────────────────────────────────────────────────────────────────
def test_static_no_other_trial_imports_and_no_rolling_price_channel():
    for p in (ROOT / "strategies" / "trial03").glob("*.py"):
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [m for m in mods if "trial01" in m or "trial02" in m], p
        low = src.lower()
        assert ".rolling(" not in src and "donchian" not in low and "channel" not in low, p
        assert "highest" not in low and "lowest" not in low, p
