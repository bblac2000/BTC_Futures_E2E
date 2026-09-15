"""동적 포지션 사이징 — 순수 함수. 레지스트리 #2(2026-09-15 사용자 결정 B1·B2)가 규칙이다.

    sl_dist         = |entry − sl| / entry
    risk_budget     = equity × risk_pct(regime)                                   # B2: 1차 제약
    notional_target = risk_budget / sl_dist
    MMR_eff(n)      = MMR_bracket(n) − cumB(n) / n                                # B1: v6 §4.4 거래소 공식
    liq_dist(L, n)  = 1/L − MMR_eff(n)                                            # 🚫 liquidationFee 없음
    L               = [l_min, l_max] 안 최고 정수 중 L ≤ bracket(n).initialLeverage 이고
                      sl_dist × buffer < liq_dist(L, notional_target) 인 것 — 없으면 거부
    margin = notional/L · pos_pct = margin/equity
    pos_pct > pos_pct_max → notional = pos_pct_max × equity × L (손실은 예산 아래로 — 허용)
    pos_pct < pos_pct_min → 기록만(부풀리지 않는다)
    qty = floor(notional/entry) → MIN_NOTIONAL → **최종 명목으로 브라켓·게이트 재검증**(Codex L2 Q1)
    loss_at_sl = qty × |entry − sl| > risk_budget × (1 + tol) → 거부

liquidationFee는 **청산이 난 뒤** 남은 격리 마진에서 부과된다 → 거리가 아니라 `loss_at_liquidation_usdt`
(= 마진 전액 + 명목 × fee)로만 모델링한다. 진입 후 진리원은 `positionRisk.liquidationPrice`이고
`post_entry_liquidation_check`가 추정과 비교한다.
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from exchange.errors import RulesError
from exchange.normalize import RejectReason, normalize_entry_qty, split_market_qty
from exchange.orders import Direction
from exchange.rules import Bracket, RuntimeRules
from sizing.config import RegimeSizing, SizingLimits

#  나눗셈이 많은 안전 검사 — 호출자의 전역 Decimal 문맥(정밀도)에 판정이 흔들리지 않게 고정한다(Codex L2 권고 4)
DECIMAL_PREC = 34


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
    risk_budget_usdt: Decimal
    notional_target: Decimal
    leverage: int | None
    bracket: int | None
    mmr: Decimal | None
    cum: Decimal | None
    mmr_eff: Decimal | None
    liq_dist_pct: Decimal | None          # 1/L − MMR_eff (최종 명목 기준)
    liq_price_est: Decimal | None         # v6 §4.4 Entry × (1 ∓ 1/L ± MMR_eff) — 진입 전 추정
    notional: Decimal
    margin: Decimal
    pos_pct: Decimal
    pos_pct_capped: bool
    pos_pct_below_min: bool
    qty: Decimal
    chunks: tuple[Decimal, ...]
    loss_at_sl_usdt: Decimal
    loss_at_liquidation_usdt: Decimal     # 마진 전액 + 명목 × liquidationFee
    liquidation_fee: Decimal


@dataclass(frozen=True)
class LiquidationCheck:
    status: Literal["OK", "CHECK"]
    exchange_dist_pct: Decimal | None
    estimate_dist_pct: Decimal
    buffer: Decimal
    detail: str


def _dec(x: object, what: str) -> Decimal:
    if not isinstance(x, Decimal):
        raise TypeError(f"{what}는 Decimal이어야 한다(float 금지): {type(x).__name__}")
    return x


def mmr_eff(b: Bracket, notional: Decimal) -> Decimal:
    return b.maint_margin_ratio - b.cum / notional


def liq_price_est(direction: Direction, entry: Decimal, leverage: int, mmr_effective: Decimal) -> Decimal:
    inv = 1 / Decimal(leverage)
    return entry * (1 - inv + mmr_effective) if direction is Direction.LONG else entry * (1 + inv - mmr_effective)


def size_entry(entry: Decimal, sl: Decimal, direction: Direction, equity: Decimal, regime: RegimeSizing,
               rules: RuntimeRules, limits: SizingLimits) -> SizingDecision:
    with decimal.localcontext() as ctx:
        ctx.prec = DECIMAL_PREC
        return _size_entry(entry, sl, direction, equity, regime, rules, limits)


def _size_entry(entry: Decimal, sl: Decimal, direction: Direction, equity: Decimal, regime: RegimeSizing,
                rules: RuntimeRules, limits: SizingLimits) -> SizingDecision:
    entry, sl, equity = _dec(entry, "entry"), _dec(sl, "sl"), _dec(equity, "equity")
    if type(direction) is not Direction:
        raise TypeError(f"direction은 Direction이어야 한다: {direction!r}")
    if entry <= 0 or sl <= 0 or equity <= 0:
        raise ValueError(f"entry·sl·equity는 양수: {entry}, {sl}, {equity}")

    fee = rules.symbol_rules.liquidation_fee
    budget = equity * regime.risk_pct
    zero = entry - entry
    sl_dist = abs(entry - sl) / entry

    def reject(reason: RejectReason, detail: str, **kw: object) -> SizingDecision:
        base = SizingDecision(
            ok=False, reason=reason, detail=detail, regime=regime.name, direction=direction, entry=entry, sl=sl,
            buffer=limits.buffer, sl_dist_pct=sl_dist, risk_budget_usdt=budget, notional_target=zero,
            leverage=None, bracket=None, mmr=None, cum=None, mmr_eff=None, liq_dist_pct=None, liq_price_est=None,
            notional=zero, margin=zero, pos_pct=zero, pos_pct_capped=False, pos_pct_below_min=False, qty=zero,
            chunks=(), loss_at_sl_usdt=zero, loss_at_liquidation_usdt=zero, liquidation_fee=fee)
        return replace(base, **kw)  # type: ignore[arg-type]

    long_ = direction is Direction.LONG
    if (long_ and sl >= entry) or (not long_ and sl <= entry):
        return reject(RejectReason.SL_WRONG_SIDE, f"{direction} entry={entry} sl={sl}")

    target = budget / sl_dist
    try:
        tb = rules.bracket_for_notional(target)
    except RulesError as e:
        return reject(RejectReason.NOTIONAL_CAP, f"목표 명목 {target}: {e}", notional_target=target)
    t_mmr_eff = mmr_eff(tb, target)

    chosen = None
    liq_failures = lev_failures = 0
    for L in range(regime.l_max, regime.l_min - 1, -1):
        if L > tb.initial_leverage:
            lev_failures += 1
            continue
        if sl_dist * limits.buffer < 1 / Decimal(L) - t_mmr_eff:
            chosen = L
            break
        liq_failures += 1
    if chosen is None:
        reason = RejectReason.LIQ_DISTANCE if liq_failures else RejectReason.LEVERAGE_INFEASIBLE
        return reject(reason, f"L {regime.l_max}→{regime.l_min} 전부 불가 · sl×buffer={sl_dist * limits.buffer} · "
                              f"MMR_eff={t_mmr_eff}(브라켓 {tb.bracket}, 최대 {tb.initial_leverage}x) · "
                              f"청산거리 실패 {liq_failures} · 브라켓 레버리지 실패 {lev_failures}",
                      notional_target=target, bracket=tb.bracket, mmr=tb.maint_margin_ratio, cum=tb.cum,
                      mmr_eff=t_mmr_eff)
    L = chosen

    notes: list[str] = []
    notional = target
    capped = notional / Decimal(L) / equity > limits.pos_pct_max
    if capped:
        notional = limits.pos_pct_max * equity * L
        notes.append(f"pos_pct 캡 {limits.pos_pct_max} → 명목 {target}→{notional}")

    q = normalize_entry_qty(notional / entry, entry, rules.symbol_rules)
    if not q.ok:
        assert q.reason is not None
        return reject(q.reason, q.detail, notional_target=target, leverage=L)

    final = q.qty * entry
    fb = rules.bracket_for_notional(final)
    f_mmr_eff = mmr_eff(fb, final)
    f_liq = 1 / Decimal(L) - f_mmr_eff
    if L > fb.initial_leverage or not sl_dist * limits.buffer < f_liq:
        return reject(RejectReason.LIQ_DISTANCE,
                      f"내림 후 최종 명목 {final} → 브라켓 {fb.bracket}(MMR_eff {f_mmr_eff}, 최대 {fb.initial_leverage}x)에서 "
                      f"L={L} 게이트 실패 · 청산거리 {f_liq} vs sl×buffer {sl_dist * limits.buffer}",
                      notional_target=target, leverage=L, bracket=fb.bracket, mmr=fb.maint_margin_ratio,
                      cum=fb.cum, mmr_eff=f_mmr_eff, liq_dist_pct=f_liq)

    loss = q.qty * abs(entry - sl)
    if loss > budget * (1 + limits.loss_tolerance):
        return reject(RejectReason.LOSS_OVER_BUDGET,
                      f"최종 SL 손실 {loss} > 예산 {budget} × (1 + {limits.loss_tolerance})",
                      notional_target=target, leverage=L, bracket=fb.bracket, mmr=fb.maint_margin_ratio,
                      cum=fb.cum, mmr_eff=f_mmr_eff, liq_dist_pct=f_liq, qty=q.qty, notional=final,
                      loss_at_sl_usdt=loss)

    margin = final / Decimal(L)
    pos_pct = margin / equity
    below = pos_pct < limits.pos_pct_min
    if below:
        notes.append(f"pos_pct {pos_pct} < 권고 최소 {limits.pos_pct_min} (크기 유지 — 부풀리지 않음)")
    return SizingDecision(
        ok=True, reason=None, detail=" · ".join(notes), regime=regime.name, direction=direction, entry=entry, sl=sl,
        buffer=limits.buffer, sl_dist_pct=sl_dist, risk_budget_usdt=budget, notional_target=target, leverage=L,
        bracket=fb.bracket, mmr=fb.maint_margin_ratio, cum=fb.cum, mmr_eff=f_mmr_eff, liq_dist_pct=f_liq,
        liq_price_est=liq_price_est(direction, entry, L, f_mmr_eff), notional=final, margin=margin,
        pos_pct=pos_pct, pos_pct_capped=capped, pos_pct_below_min=below, qty=q.qty,
        chunks=tuple(split_market_qty(q.qty, rules.symbol_rules, ref_price=entry, reduce_only=False)),
        loss_at_sl_usdt=loss, loss_at_liquidation_usdt=margin + final * fee, liquidation_fee=fee)


def post_entry_liquidation_check(decision: SizingDecision, *, entry_price: Decimal,
                                 exchange_liq_price: Decimal) -> LiquidationCheck:
    """진입 후 — 거래소 `positionRisk.liquidationPrice`(진리원)를 진입 전 추정과 비교한다.

    해석(레지스트리 #2): "거래소 청산가가 추정보다 **버퍼 이상** 가깝다" ⇔ `exchange_dist × buffer < estimate_dist`
    → CHECK(로그·점검 대상). 거래소 값이 0/없음이거나 진입가의 잘못된 쪽이면 해석할 수 없으므로 CHECK.
    """
    entry_price = _dec(entry_price, "entry_price")
    exchange_liq_price = _dec(exchange_liq_price, "exchange_liq_price")
    if not decision.ok or decision.liq_dist_pct is None:
        raise ValueError("수락된 사이징 결정에만 진입 후 검사를 한다")
    est, buf = decision.liq_dist_pct, decision.buffer
    if exchange_liq_price <= 0 or entry_price <= 0:
        return LiquidationCheck("CHECK", None, est, buf, f"거래소 청산가 해석 불가: {exchange_liq_price}")
    if decision.direction is Direction.LONG:
        dist = (entry_price - exchange_liq_price) / entry_price
    else:
        dist = (exchange_liq_price - entry_price) / entry_price
    if dist <= 0:
        return LiquidationCheck("CHECK", dist, est, buf,
                                f"거래소 청산가 {exchange_liq_price}가 {decision.direction} 진입가 {entry_price}의 잘못된 쪽")
    if dist * buf < est:
        return LiquidationCheck("CHECK", dist, est, buf,
                                f"거래소 청산 거리 {dist} × buffer {buf} < 추정 {est} — 추정보다 버퍼 이상 가깝다")
    return LiquidationCheck("OK", dist, est, buf, "")
