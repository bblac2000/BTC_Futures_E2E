"""10진 문맥 독립성(Codex 단계 d #7·#8 · 레지스트리 #22) — exchange/·sizing/·paper/(엔진 전체)는 이름 붙은 고정 문맥
`EXEC_CTX`로만 계산한다. ccxt `decimal_to_precision`은 호출되면 스레드 전역 문맥의 rounding을 HALF_UP으로, Underflow 트랩을
켠 채로 **바꿔 놓고 되돌리지 않는다** → 호출자 문맥이 기본 · ccxt 모양 · 낮은 정밀도 어느 것이어도 출력이 **바이트 단위로 같아야** 한다.
입력은 기본 문맥에서 **먼저** 만든다(호출자 문맥이 입력 자체를 바꾸지 않게) — 비교 대상은 함수 안의 계산뿐이다.
"""
from __future__ import annotations

import decimal
import json
import random
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Any

from exchange.normalize import (
    ceil_to_step,
    floor_to_step,
    normalize_entry_qty,
    normalize_price,
    split_market_qty,
)
from exchange.orders import Direction, Intent, Side, market_order_params
from paper.sender import adverse_fill_estimate
from sizing.config import RegimeSizing, SizingLimits
from sizing.position import liquidation_estimate, post_entry_liquidation_check, size_entry

D = Decimal


def _ctx(kind: str) -> AbstractContextManager[decimal.Context]:
    c = decimal.Context()                                   # 파이썬 기본
    if kind == "ccxt":
        c.rounding = decimal.ROUND_HALF_UP
        c.traps[decimal.Underflow] = True
    elif kind == "lowprec":
        c.prec, c.rounding = 6, decimal.ROUND_DOWN
    return decimal.localcontext(c)


CONTEXTS = ("default", "ccxt", "lowprec")


def _cases(n: int = 400) -> list[tuple[Decimal, Decimal, Direction, Decimal]]:
    rnd = random.Random(20260921)
    out = []
    for _ in range(n):
        entry = D(rnd.randrange(2_000_000, 15_000_000)) / 100 + D(rnd.randrange(0, 10**6)) / 10**8
        dist = D(rnd.randrange(10, 200)) / 10_000 + D(rnd.randrange(0, 10**6)) / 10**12
        direction = Direction.LONG if rnd.random() < 0.5 else Direction.SHORT
        sl = entry * (1 - dist) if direction is Direction.LONG else entry * (1 + dist)
        equity = D(rnd.randrange(5_000, 10_000_000)) / 100 + D(1) / 3
        out.append((entry, sl, direction, equity))
    return out


def _thunks(rules) -> list[Callable[[], Any]]:
    """기본 문맥에서 입력을 모두 만든 뒤, 계산만 남긴 호출 목록."""
    sr = rules.symbol_rules
    regime = RegimeSizing("t", D("0.01"), 50, 100)
    lim = SizingLimits()
    out: list[Callable[[], Any]] = []
    with decimal.localcontext(decimal.Context()):
        for entry, sl, direction, equity in _cases():
            notional, third, raw = entry * D("0.0371") * 100, entry / 3, equity / entry * 7
            fq, cq = equity / entry, sr.min_notional / entry
            d = size_entry(entry, sl, direction, equity, regime, rules, lim)
            out += [lambda e=entry, s=sl, di=direction, q=equity: size_entry(e, s, di, q, regime, rules, lim),
                    lambda di=direction, e=entry, n=notional: liquidation_estimate(di, e, n, 75, rules),
                    lambda x=third: normalize_price(x, sr),
                    lambda x=fq: floor_to_step(x, sr.market_step),
                    lambda x=cq: ceil_to_step(x, sr.market_step),
                    lambda x=raw, e=entry: normalize_entry_qty(x, e, sr),
                    lambda x=raw, e=entry: split_market_qty(x, sr, ref_price=e, reduce_only=False)]
            out += [lambda si=side, e=entry: adverse_fill_estimate(si, e, sr.tick_size) for side in (Side.BUY, Side.SELL)]
            if d.ok and d.leverage is not None:
                fill = entry * D("1.00021")
                out += [lambda di=direction, q=d.chunks[0]: market_order_params(sr.symbol, di, Intent.ENTRY, q, sr),
                        lambda dd=d, f=fill: post_entry_liquidation_check(dd, rules, entry_price=f, qty=dd.qty,
                                                                          exchange_liq_price=dd.liq_price_est or f)]
    return out


def _outputs(thunks: list[Callable[[], Any]], kind: str) -> list[str]:
    with _ctx(kind):
        return [repr(t()) for t in thunks]


def test_sizing_and_normalization_are_byte_identical_under_any_caller_context(rules):
    th = _thunks(rules)
    base = _outputs(th, "default")
    assert len(base) > 3000
    for kind in CONTEXTS[1:]:
        other = _outputs(th, kind)
        diff = [i for i, (a, b) in enumerate(zip(base, other, strict=True)) if a != b]
        assert diff == [], (kind, len(diff), base[diff[0]], other[diff[0]]) if diff else kind


def test_real_ccxt_mutation_is_neutralised(rules):
    from ccxt.base.decimal_to_precision import ROUND, TICK_SIZE, decimal_to_precision
    th = _thunks(rules)
    base = _outputs(th, "default")
    with decimal.localcontext():                 # ccxt가 바꾸는 것은 이 지역 문맥 — 테스트 밖으로 새지 않는다
        decimal_to_precision("1.25", ROUND, "0.1", TICK_SIZE)
        assert decimal.getcontext().rounding == decimal.ROUND_HALF_UP      # ccxt가 실제로 바꿨다
        mutated = [repr(t()) for t in th]
    assert base == mutated


# ── 엔진 전체: 이벤트 · 스냅샷 · DB 바이트 ─────────────────────────────────────
def _engine_run(rules, kind: str) -> tuple[str, str, str]:
    """트레일·체결 뒤 TP·펀딩·청산이 모두 도는 한 시나리오를 호출자 문맥 `kind`에서 돌린다(입력은 미리 만든 값)."""
    from db import migrate as M
    from db import record as R
    from exchange.gate import Mode
    from paper.engine import Engine, EntryIntent, TpFromFill, Trail
    from paper.sender import PaperSender
    from paper.types import MarkTick
    t0, h8 = 1_789_430_400_000, 8 * 3_600_000
    regime = RegimeSizing("t", D("0.01"), 50, 100)
    marks = [D("60000"), D("60000.37"), D("60333.33"), D("60611.11"), D("60777.77"), D("60444.44"), D("60123.45")]
    ticks = [MarkTick(t0 + i * 1_000_000, m, D("0.000123"), (t0 // h8 + 1) * h8) for i, m in enumerate(marks)]
    con = sqlite3.connect(":memory:")
    M.migrate(con)
    events: list[object] = []
    states: list[Any] = []
    with decimal.localcontext(decimal.Context()):
        wallet = D("1000") + D(1) / 7                       # 입력은 기본 문맥에서
    with _ctx(kind):
        e = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=wallet, limits=SizingLimits())
        e.request_entry(EntryIntent(Direction.LONG, D("59701.7"), None, regime, t0 - 1, D("60000"),
                                    trail=Trail(D(1), D("97.3")), tp_rule=TpFromFill(D("61111.1"), D("1.5"), D("2"))))
        for tk in ticks:
            ev = e.on_tick(tk)
            events += ev
            states.append(e.position_state())
            R.record_events(con, ev, mode="paper", symbol="BTCUSDT", tp=e.last_entry_tp)
        states.append(str(e.equity(D("60001.01"))))
    dump = json.dumps({t: con.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
                       for t in ("decisions", "positions", "orders", "funding_events", "engine_events")}, default=str)
    return repr(events), json.dumps(states), dump


def test_engine_events_snapshots_and_db_rows_are_byte_identical_under_any_caller_context(rules):
    import re
    base = _engine_run(rules, "default")
    assert "StopTrailed" in base[2] and "TrailSet" in base[2] and "funding" in base[0].lower()
    for kind in CONTEXTS[1:]:
        other = _engine_run(rules, kind)
        #  DB의 created_at(벽시계)만 다를 수 있다 — 값 열은 전부 같아야 한다
        strip = [re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+Z?", "T", x) for x in (base[2], other[2])]
        assert base[0] == other[0] and base[1] == other[1] and strip[0] == strip[1], kind


def test_quantize_calls_pass_explicit_rounding():
    """exchange/·sizing/·paper/의 quantize·to_integral_value 호출은 전부 rounding을 명시한다(문맥 상속 금지)."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    bad = []
    for pkg in ("exchange", "sizing", "paper"):
        for f in sorted((root / pkg).rglob("*.py")):
            for i, line in enumerate(f.read_text().splitlines(), 1):
                for m in re.finditer(r"\.(quantize|to_integral_value|to_integral_exact|to_integral)\(([^)]*)\)", line):
                    if "rounding=" not in m.group(2):
                        bad.append(f"{f.relative_to(root)}:{i}: {line.strip()}")
    assert bad == []


def test_exec_context_is_fully_fixed():
    from exchange.decimal_context import EXEC_CTX
    assert (EXEC_CTX.prec, EXEC_CTX.rounding, EXEC_CTX.Emin, EXEC_CTX.Emax, EXEC_CTX.capitals, EXEC_CTX.clamp) == \
        (34, decimal.ROUND_HALF_EVEN, decimal.MIN_EMIN, decimal.MAX_EMAX, 1, 0)
    assert {k for k, v in EXEC_CTX.traps.items() if v} == {decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow}


# ── 런타임 전체: 실제 account_snapshots 행까지(Codex 단계 d 후속 #5) ─────────────────────
def _runtime_run(rules, kind: str) -> str:
    import re
    from dataclasses import replace

    from paper.engine import TpFromFill, Trail
    from tests.test_ops_runtime import DAY0, build, feed
    from tests.test_paper_engine import intent
    with decimal.localcontext(decimal.Context()):
        it = replace(intent(sl="59701.7", decided_ms=DAY0 + 61_000), trail=Trail(D(1), D("97.3")),
                     tp_rule=TpFromFill(D("61111.1"), D("1.5"), D("2")))
    import tests.test_ops_runtime as TR
    orig_kline = TR.kline

    def kline_default(*a, **k):                                   # 입력(테스트가 만드는 kline)은 기본 문맥에서
        with decimal.localcontext(decimal.Context()):
            return orig_kline(*a, **k)

    TR.kline = kline_default
    try:
        with _ctx(kind):
            rt, counter, clock = build(rules)
            feed(rt, counter, clock, DAY0, DAY0 + 61_000, mark="60000.37")
            rt.submit_entry(it)
            feed(rt, counter, clock, DAY0 + 61_000, DAY0 + 181_000, mark="60000.37")
            feed(rt, counter, clock, DAY0 + 181_000, DAY0 + 241_000, mark="60444.44")   # 무장·조임
            feed(rt, counter, clock, DAY0 + 241_000, DAY0 + 301_000, mark="60123.45")
    finally:
        TR.kline = orig_kline
    tables = [t for (t,) in rt.con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    dump = json.dumps({t: rt.con.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in tables}, default=str)
    return re.sub(r"\d{4}-\d\d-\d\d[T ][\d:.]+Z?", "T", dump)                        # 벽시계 열만 지운다


def test_runtime_db_including_account_snapshots_is_byte_identical_under_any_caller_context(rules):
    base = _runtime_run(rules, "default")
    assert "account_snapshots" in base and "StopTrailed" in base and '"arith"' in base.replace('\\"', '"')
    for kind in CONTEXTS[1:]:
        other = _runtime_run(rules, kind)
        if other != base:
            k = next((i for i, (x, y) in enumerate(zip(base, other, strict=False)) if x != y), min(len(base), len(other)))
            raise AssertionError(f"{kind}: {base[max(0, k - 200):k + 80]!r} ≠ {other[max(0, k - 200):k + 80]!r}")
