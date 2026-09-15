"""동적 포지션 사이징 — 순수 함수. **순서가 규칙이다**(strategy-modules §1).

    sl_dist_pct = |entry − sl| / entry
    L_raw       = risk_pct / sl_dist_pct
    L_start     = clamp(floor(L_raw), l_min, l_max)                     # 레짐은 구간만 준다
    for L = L_start … l_min:                                             # 정수 레버리지(POST /leverage는 int)
        notional = equity × pos_pct × L
        bracket  = bracket_for_notional(notional)                        # 🔴 tier1 가정 금지
        require  L ≤ bracket.initialLeverage
        liq_dist = 1/L − bracket.MMR − liquidationFee                    # 런타임 값
        require  sl_dist_pct × buffer < liq_dist                         # 못 넘으면 L을 1 낮춘다
    → 어떤 L도 못 넘으면 거부(L을 l_min 밑으로 내리지 않는다)
    qty = normalize_entry_qty(notional / entry) → MIN_NOTIONAL → MARKET_LOT maxQty 분할

⚠️ 알려진 보수성·미결(설계서 §8에 기록, 사용자 결정 대기):
- 검사식은 v6 §4.4 격리 청산 거리(1/L − MMR)에서 **liquidationFee를 더 뺀다**(사용자 결정 2026-09-15).
  BTC tier1(MMR 0.4% + fee 1.25% = 1.65%)에서는 **100x가 어떤 SL로도 불가능**하고, 가능한 최대 L은
  floor(1/(0.0165 + sl×buffer)) — SL 0.15% ≈ 55x, 0.30% ≈ 51x, 0.36% 이상은 50x에서도 거부.
- 브라켓 `cum`(유지증거금 공제액)을 무시한다 → 실효 MMR을 과대평가 = 보수적.
- 클램프가 걸리면(L_raw < l_min 또는 > l_max) **risk_pct는 결과 손실에 들어가지 않는다**.
  실제 SL 손실 = qty × |entry − sl| 를 `loss_at_sl_usdt`로 노출하고, 목표치 `risk_budget_usdt`와 나란히 둔다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from decimal import Decimal

from exchange.errors import RulesError
from exchange.normalize import RejectReason, normalize_entry_qty, split_market_qty
from exchange.orders import Direction
from exchange.rules import RuntimeRules
from sizing.config import RegimeSizing


@dataclass(frozen=True)
class SizingDecision:
    """판단 시점 값 전부 — layer 4 `decisions` 행으로 그대로 들어간다(거부 사유 포함)."""
    ok: bool
    reason: RejectReason | None
    detail: str
    regime: str
    direction: Direction
    entry: Decimal
    sl: Decimal
    buffer: Decimal
    sl_dist_pct: Decimal
    l_raw: Decimal | None
    leverage_start: int | None
    leverage: int | None
    bracket: int | None
    mmr: Decimal | None
    liquidation_fee: Decimal
    liq_dist_pct: Decimal | None          # 1/L − MMR − liquidationFee (검사식)
    liq_price_v6: Decimal | None          # v6 §4.4 원문(fee 없음) — 비교·복기용
    notional: Decimal
    margin: Decimal
    qty: Decimal
    chunks: tuple[Decimal, ...]
    loss_at_sl_usdt: Decimal
    risk_budget_usdt: Decimal


def _dec(x: object, what: str) -> Decimal:
    if not isinstance(x, Decimal):
        raise TypeError(f"{what}는 Decimal이어야 한다(float 금지): {type(x).__name__}")
    return x


def liq_price_v6(direction: Direction, entry: Decimal, leverage: int, mmr: Decimal) -> Decimal:
    inv = 1 / Decimal(leverage)
    return entry * (1 - inv + mmr) if direction is Direction.LONG else entry * (1 + inv - mmr)


def size_entry(entry: Decimal, sl: Decimal, direction: Direction, equity: Decimal, regime: RegimeSizing,
               rules: RuntimeRules, *, buffer: Decimal) -> SizingDecision:
    entry, sl, equity, buffer = (_dec(entry, "entry"), _dec(sl, "sl"), _dec(equity, "equity"),
                                 _dec(buffer, "buffer"))
    if type(direction) is not Direction:
        raise TypeError(f"direction은 Direction이어야 한다: {direction!r}")
    if entry <= 0 or sl <= 0 or equity <= 0:
        raise ValueError(f"entry·sl·equity는 양수: {entry}, {sl}, {equity}")
    if buffer < 1:
        raise ValueError(f"buffer {buffer} < 1은 청산 거리 검사를 **느슨하게** 만든다")

    fee = rules.symbol_rules.liquidation_fee
    risk_budget = equity * regime.risk_pct
    zero = entry - entry

    def reject(reason: RejectReason, detail: str, **kw: object) -> SizingDecision:
        base = SizingDecision(ok=False, reason=reason, detail=detail, regime=regime.name, direction=direction,
                              entry=entry, sl=sl, buffer=buffer, sl_dist_pct=abs(entry - sl) / entry, l_raw=None,
                              leverage_start=None, leverage=None, bracket=None, mmr=None, liquidation_fee=fee,
                              liq_dist_pct=None, liq_price_v6=None, notional=zero, margin=zero, qty=zero,
                              chunks=(), loss_at_sl_usdt=zero, risk_budget_usdt=risk_budget)
        return replace(base, **kw)  # type: ignore[arg-type]

    long_ = direction is Direction.LONG
    if (long_ and sl >= entry) or (not long_ and sl <= entry):
        return reject(RejectReason.SL_WRONG_SIDE, f"{direction} entry={entry} sl={sl}")

    sl_dist = abs(entry - sl) / entry
    l_raw = regime.risk_pct / sl_dist
    start = max(regime.l_min, min(regime.l_max, math.floor(l_raw)))
    liq_failures = bracket_failures = 0
    chosen = None
    for L in range(start, regime.l_min - 1, -1):
        notional = equity * regime.pos_pct * L
        try:
            b = rules.bracket_for_notional(notional)
        except RulesError:
            bracket_failures += 1
            continue
        if L > b.initial_leverage:
            bracket_failures += 1
            continue
        liq_dist = 1 / Decimal(L) - b.maint_margin_ratio - fee
        if sl_dist * buffer < liq_dist:
            chosen = (L, b, liq_dist)
            break
        liq_failures += 1

    common = dict(sl_dist_pct=sl_dist, l_raw=l_raw, leverage_start=start)
    if chosen is None:
        detail = (f"L {start}→{regime.l_min} 전부 불가 · sl×buffer={sl_dist * buffer} · "
                  f"fee={fee} · 브라켓 실패 {bracket_failures} · 청산거리 실패 {liq_failures}")
        reason = RejectReason.LIQ_DISTANCE if liq_failures else RejectReason.LEVERAGE_INFEASIBLE
        return reject(reason, detail, **common)

    L, b, liq_dist = chosen
    planned = equity * regime.pos_pct * L
    q = normalize_entry_qty(planned / entry, entry, rules.symbol_rules)
    if not q.ok:
        assert q.reason is not None
        return reject(q.reason, q.detail, **common, leverage=L, bracket=b.bracket, mmr=b.maint_margin_ratio,
                      liq_dist_pct=liq_dist)
    chunks = tuple(split_market_qty(q.qty, rules.symbol_rules, ref_price=entry, reduce_only=False))
    notional = q.qty * entry
    return SizingDecision(
        ok=True, reason=None, detail="", regime=regime.name, direction=direction, entry=entry, sl=sl, buffer=buffer,
        sl_dist_pct=sl_dist, l_raw=l_raw, leverage_start=start, leverage=L, bracket=b.bracket,
        mmr=b.maint_margin_ratio, liquidation_fee=fee, liq_dist_pct=liq_dist,
        liq_price_v6=liq_price_v6(direction, entry, L, b.maint_margin_ratio),
        notional=notional, margin=notional / Decimal(L), qty=q.qty, chunks=chunks,
        loss_at_sl_usdt=q.qty * abs(entry - sl), risk_budget_usdt=risk_budget)
