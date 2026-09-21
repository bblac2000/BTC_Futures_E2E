"""10진 문맥 독립성(단계 d 전 수정 · 사용자 2026-09-21) — ccxt `decimal_to_precision`은 호출되면 스레드 전역 문맥의
rounding을 HALF_UP으로, Underflow 트랩을 켠 채로 **바꿔 놓고 되돌리지 않는다**. 봇 프로세스는 ccxt를 쓰므로
사이징·정규화·체결가 추정이 호출자 문맥에 따라 달라지면 안 된다 → 기본 문맥과 **바이트 단위로 같은 출력**을 요구한다.
"""
from __future__ import annotations

import decimal
import random
from decimal import Decimal

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


def _outputs(rules) -> list[str]:
    sr = rules.symbol_rules
    regime = RegimeSizing("t", D("0.01"), 50, 100)
    lim = SizingLimits()
    out: list[str] = []
    for entry, sl, direction, equity in _cases():
        d = size_entry(entry, sl, direction, equity, regime, rules, lim)
        out.append(repr(d))
        out.append(repr(liquidation_estimate(direction, entry, entry * D("0.0371") * 100, 75, rules)))
        out.append(repr(normalize_price(entry / 3, sr)))
        out.append(repr(floor_to_step(equity / entry, sr.market_step)))
        out.append(repr(ceil_to_step(sr.min_notional / entry, sr.market_step)))
        out.append(repr(normalize_entry_qty(equity / entry * 7, entry, sr)))
        out.append(repr(split_market_qty(equity / entry * 7, sr, ref_price=entry, reduce_only=False)))
        for side in (Side.BUY, Side.SELL):
            out.append(repr(adverse_fill_estimate(side, entry, sr.tick_size)))
        if d.ok and d.leverage is not None:
            out.append(repr(market_order_params(sr.symbol, direction, Intent.ENTRY, d.chunks[0], sr)))
            fill = entry * D("1.00021")
            out.append(repr(post_entry_liquidation_check(d, rules, entry_price=fill, qty=d.qty,
                                                         exchange_liq_price=d.liq_price_est or fill)))
    return out


def test_ccxt_like_context_gives_byte_identical_outputs(rules):
    base = _outputs(rules)
    with decimal.localcontext() as c:
        c.rounding = decimal.ROUND_HALF_UP
        c.traps[decimal.Underflow] = True
        mutated = _outputs(rules)
    assert len(base) > 2000
    diff = [i for i, (a, b) in enumerate(zip(base, mutated, strict=True)) if a != b]
    assert diff == [], (len(diff), base[diff[0]], mutated[diff[0]]) if diff else None


def test_real_ccxt_mutation_is_neutralised(rules):
    from ccxt.base.decimal_to_precision import ROUND, TICK_SIZE, decimal_to_precision
    base = _outputs(rules)
    with decimal.localcontext():                 # ccxt가 바꾸는 것은 이 지역 문맥 — 테스트 밖으로 새지 않는다
        decimal_to_precision("1.25", ROUND, "0.1", TICK_SIZE)
        assert decimal.getcontext().rounding == decimal.ROUND_HALF_UP      # ccxt가 실제로 바꿨다
        mutated = _outputs(rules)
    assert base == mutated


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
