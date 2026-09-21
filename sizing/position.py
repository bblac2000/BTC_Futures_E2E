"""동적 포지션 사이징 — 순수 함수. 레지스트리 #2(위험 예산) · #4(정확 청산식) · #5(SL 게이트)가 규칙이다.

    sl_dist         = |entry − sl| / entry                                      (SL 트리거 기준 = mark, #5)
    risk_budget     = equity × risk_pct(regime)                                 #2
    notional_target = risk_budget / sl_dist
    liquidation     = 바이낸스 FAQ 원식(격리·원웨이: TMM=0·UPNL=0), 신규 포지션 WB = N/L − N×taker   #4
        LONG  dist = (1/L − taker − MMR_eff) / (1 − MMR)
        SHORT dist = (1/L − taker − MMR_eff) / (1 + MMR)
        MMR_eff = MMR − cum/N,  MMR·cum = max(진입 명목, 청산가 명목)의 티어(바뀌면 재계산)
    gate(L)         = sl_dist × buffer_rel < dist  AND  dist − sl_dist ≥ min_gap   #5 (1.5 · 10bp)
    L               = [l_min, l_max] 안 최고 정수 중 L ≤ bracket(target).initialLeverage 이고 gate 통과
    margin = notional/L · pos_pct = margin/equity · pos_pct_max 캡 · pos_pct_min 권고
    qty = floor(notional/entry) → MIN_NOTIONAL → **최종 명목으로 브라켓·청산식·게이트 재검증**
    loss_at_sl = qty × |entry − sl| > budget × (1 + tol) → 거부

liquidationFee는 거리에 없다 — 청산 뒤 남은 격리 마진에서 부과 → `loss_at_liquidation_usdt`로만.
⚠️ "진입 수수료가 격리 마진을 줄인다"(WB = N/L − N×taker)는 **보수적 가정**이다. 실제 여부는 진입 후
   `positionRisk.liquidationPrice`와 두 모델(차감/미차감)을 비교하는 `post_entry_liquidation_check`가 판정한다.
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from exchange.decimal_context import EXEC_PREC, exec_context
from exchange.errors import RulesError
from exchange.normalize import RejectReason, normalize_entry_qty, split_market_qty
from exchange.orders import Direction
from exchange.rules import Bracket, RuntimeRules
from sizing.config import SL_TRIGGER_BASIS, RegimeSizing, SizingLimits

#  나눗셈이 많은 안전 검사 — 호출자의 전역 Decimal 문맥(정밀도)에 판정이 흔들리지 않게 고정한다(Codex L2 권고 4)
DECIMAL_PREC = EXEC_PREC                # = exchange.decimal_context.EXEC_CTX 정밀도(레지스트리 #22)


@dataclass(frozen=True)
class LiqEstimate:
    price: Decimal
    dist_pct: Decimal
    bracket: int
    mmr: Decimal
    cum: Decimal
    mmr_eff: Decimal
    taker: Decimal
    tier_basis_notional: Decimal          # max(진입 명목, 청산가 명목)


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
    sl_trigger_basis: str
    buffer_rel: Decimal
    min_gap: Decimal
    sl_dist_pct: Decimal
    risk_budget_usdt: Decimal
    notional_target: Decimal
    leverage: int | None
    bracket: int | None
    mmr: Decimal | None
    cum: Decimal | None
    mmr_eff: Decimal | None
    taker_rate: Decimal
    liq_dist_pct: Decimal | None          # #4 정확식(최종 명목 기준)
    liq_price_est: Decimal | None
    liq_tier_basis_notional: Decimal | None
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
    estimate_dist_pct: Decimal            # 수수료 차감 모델(#4 가정)
    estimate_no_fee_dist_pct: Decimal     # 수수료 미차감 모델 — 가정 검증용
    gap_vs_fee_pct: Decimal | None        # exchange − estimate(부호 있음)
    gap_vs_no_fee_pct: Decimal | None
    closer_model: Literal["fee", "no_fee", "tie"] | None   # 진단 전용 — 이것으로 자동 결정하지 않는다
    bracket: int
    buffer_rel: Decimal
    detail: str


def _dec(x: object, what: str) -> Decimal:
    if not isinstance(x, Decimal):
        raise TypeError(f"{what}는 Decimal이어야 한다(float 금지): {type(x).__name__}")
    return x


def liquidation_estimate(direction: Direction, entry: Decimal, notional: Decimal, leverage: int, rules: RuntimeRules,
                         *, taker: Decimal | None = None) -> LiqEstimate:
    """신규 격리·원웨이 포지션의 청산가·거리(#4). `taker=None`이면 런타임 commissionRate의 taker를 쓴다.

    티어: 진입 명목의 브라켓으로 시작 → 청산가 명목과 비교해 max 쪽 브라켓이 다르면 그 브라켓으로 재계산
    (바이낸스 FAQ: "position notional (determined by the liquidation price calculation)이 다른 티어면 재계산").
    🔴 이미 거친 티어로 되돌아가면(진동 · 고정점 없음) **추정하지 않고** `RulesError` — cum 연속성을 파서가
       강제하므로 실제 브라켓에서는 나오지 않는다(Codex L2 전체검토 Q2). 모든 브라켓 밖이어도 `RulesError`.
    """
    with exec_context():                            # EXEC_CTX(정밀도 34 · rounding·트랩 고정) — ccxt 전역 문맥 무관
        side = 1 if direction is Direction.LONG else -1
        t = rules.commission.taker if taker is None else taker
        b: Bracket = rules.bracket_for_notional(notional)
        seen: list[Bracket] = []
        while True:
            me = b.maint_margin_ratio - b.cum / notional
            dist = (1 / Decimal(leverage) - t - me) / (1 - side * b.maint_margin_ratio)
            price = entry * (1 - side * dist)
            basis = max(notional, notional * price / entry)
            nb = rules.bracket_for_notional(basis)
            if nb == b:
                return LiqEstimate(price, dist, b.bracket, b.maint_margin_ratio, b.cum, me, t, basis)
            if nb in seen:
                raise RulesError(f"청산가 티어 고정점 없음: 브라켓 {b.bracket}↔{nb.bracket} 진동(명목 {notional}·L {leverage})")
            seen.append(b)
            b = nb


def sl_gate_passes(sl_dist: Decimal, dist: Decimal, limits: SizingLimits) -> bool:
    """레지스트리 #5 게이트 — 진입 전 사이징과 layer 3 체결 후 재검증이 **같은 함수**를 쓴다."""
    return sl_dist * limits.buffer_rel < dist and dist - sl_dist >= limits.min_gap


_gate = sl_gate_passes


def size_entry(entry: Decimal, sl: Decimal, direction: Direction, equity: Decimal, regime: RegimeSizing,
               rules: RuntimeRules, limits: SizingLimits) -> SizingDecision:
    with exec_context():                            # EXEC_CTX(정밀도 34 · rounding·트랩 고정) — ccxt 전역 문맥 무관
        return _size_entry(entry, sl, direction, equity, regime, rules, limits)


def _size_entry(entry: Decimal, sl: Decimal, direction: Direction, equity: Decimal, regime: RegimeSizing,
                rules: RuntimeRules, limits: SizingLimits) -> SizingDecision:
    entry, sl, equity = _dec(entry, "entry"), _dec(sl, "sl"), _dec(equity, "equity")
    if type(direction) is not Direction:
        raise TypeError(f"direction은 Direction이어야 한다: {direction!r}")
    if entry <= 0 or sl <= 0 or equity <= 0:
        raise ValueError(f"entry·sl·equity는 양수: {entry}, {sl}, {equity}")

    fee = rules.symbol_rules.liquidation_fee
    taker = rules.commission.taker
    budget = equity * regime.risk_pct
    zero = entry - entry
    sl_dist = abs(entry - sl) / entry

    def reject(reason: RejectReason, detail: str, **kw: object) -> SizingDecision:
        base = SizingDecision(
            ok=False, reason=reason, detail=detail, regime=regime.name, direction=direction, entry=entry, sl=sl,
            sl_trigger_basis=SL_TRIGGER_BASIS, buffer_rel=limits.buffer_rel, min_gap=limits.min_gap,
            sl_dist_pct=sl_dist, risk_budget_usdt=budget, notional_target=zero, leverage=None, bracket=None,
            mmr=None, cum=None, mmr_eff=None, taker_rate=taker, liq_dist_pct=None, liq_price_est=None,
            liq_tier_basis_notional=None, notional=zero, margin=zero, pos_pct=zero, pos_pct_capped=False,
            pos_pct_below_min=False, qty=zero, chunks=(), loss_at_sl_usdt=zero, loss_at_liquidation_usdt=zero,
            liquidation_fee=fee)
        return replace(base, **kw)  # type: ignore[arg-type]

    long_ = direction is Direction.LONG
    if (long_ and sl >= entry) or (not long_ and sl <= entry):
        return reject(RejectReason.SL_WRONG_SIDE, f"{direction} entry={entry} sl={sl}")

    target = budget / sl_dist
    try:
        tb = rules.bracket_for_notional(target)
    except RulesError as e:
        return reject(RejectReason.NOTIONAL_CAP, f"목표 명목 {target}: {e}", notional_target=target)

    chosen: tuple[int, LiqEstimate] | None = None
    liq_failures = lev_failures = cap_failures = 0
    last: LiqEstimate | None = None
    for L in range(regime.l_max, regime.l_min - 1, -1):
        if L > tb.initial_leverage:
            lev_failures += 1
            continue
        try:
            est = liquidation_estimate(direction, entry, target, L, rules)
        except RulesError:
            cap_failures += 1                       # 청산가 명목이 모든 브라켓 밖
            continue
        last = est
        if _gate(sl_dist, est.dist_pct, limits):
            chosen = (L, est)
            break
        liq_failures += 1
    if chosen is None:
        reason = (RejectReason.LIQ_DISTANCE if liq_failures else
                  RejectReason.LEVERAGE_INFEASIBLE if lev_failures else RejectReason.NOTIONAL_CAP)
        extra: dict[str, object] = {}
        if last is not None:
            extra = dict(bracket=last.bracket, mmr=last.mmr, cum=last.cum, mmr_eff=last.mmr_eff,
                         liq_dist_pct=last.dist_pct, liq_tier_basis_notional=last.tier_basis_notional)
        return reject(reason, f"L {regime.l_max}→{regime.l_min} 전부 불가 · sl×{limits.buffer_rel}={sl_dist * limits.buffer_rel}"
                              f" · 최소간격 {limits.min_gap} · 청산거리 실패 {liq_failures} · 브라켓 레버리지 실패 "
                              f"{lev_failures} · 청산가 명목 cap 초과 {cap_failures}",
                      notional_target=target, **extra)
    L, _ = chosen

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
    try:
        fe = liquidation_estimate(direction, entry, final, L, rules)
    except RulesError as e:
        return reject(RejectReason.NOTIONAL_CAP, f"내림 후 최종 명목 {final} 청산가 명목이 브라켓 밖: {e}",
                      notional_target=target, leverage=L)
    brk = dict(bracket=fe.bracket, mmr=fe.mmr, cum=fe.cum, mmr_eff=fe.mmr_eff, liq_dist_pct=fe.dist_pct,
               liq_price_est=fe.price, liq_tier_basis_notional=fe.tier_basis_notional)
    if L > fb.initial_leverage or not _gate(sl_dist, fe.dist_pct, limits):
        return reject(RejectReason.LIQ_DISTANCE,
                      f"내림 후 최종 명목 {final} → 브라켓 {fe.bracket}(MMR_eff {fe.mmr_eff}, 최대 {fb.initial_leverage}x)에서 "
                      f"L={L} 게이트 실패 · 청산거리 {fe.dist_pct} vs sl×{limits.buffer_rel} {sl_dist * limits.buffer_rel}",
                      notional_target=target, leverage=L, **brk)

    loss = q.qty * abs(entry - sl)
    if loss > budget * (1 + limits.loss_tolerance):
        return reject(RejectReason.LOSS_OVER_BUDGET,
                      f"최종 SL 손실 {loss} > 예산 {budget} × (1 + {limits.loss_tolerance})",
                      notional_target=target, leverage=L, qty=q.qty, notional=final, loss_at_sl_usdt=loss, **brk)

    margin = final / Decimal(L)
    pos_pct = margin / equity
    below = pos_pct < limits.pos_pct_min
    if below:
        notes.append(f"pos_pct {pos_pct} < 권고 최소 {limits.pos_pct_min} (크기 유지 — 부풀리지 않음)")
    return SizingDecision(
        ok=True, reason=None, detail=" · ".join(notes), regime=regime.name, direction=direction, entry=entry, sl=sl,
        sl_trigger_basis=SL_TRIGGER_BASIS, buffer_rel=limits.buffer_rel, min_gap=limits.min_gap, sl_dist_pct=sl_dist,
        risk_budget_usdt=budget, notional_target=target, leverage=L, bracket=fe.bracket, mmr=fe.mmr, cum=fe.cum,
        mmr_eff=fe.mmr_eff, taker_rate=taker, liq_dist_pct=fe.dist_pct, liq_price_est=fe.price,
        liq_tier_basis_notional=fe.tier_basis_notional, notional=final, margin=margin, pos_pct=pos_pct,
        pos_pct_capped=capped, pos_pct_below_min=below, qty=q.qty,
        chunks=tuple(split_market_qty(q.qty, rules.symbol_rules, ref_price=entry, reduce_only=False)),
        loss_at_sl_usdt=loss, loss_at_liquidation_usdt=margin + final * fee, liquidation_fee=fee)


def post_entry_liquidation_check(decision: SizingDecision, rules: RuntimeRules, *, entry_price: Decimal, qty: Decimal,
                                 exchange_liq_price: Decimal) -> LiquidationCheck:
    """진입 후 — 거래소 `positionRisk.liquidationPrice`(진리원)를 **실제 체결 기준으로 재계산한** 추정과 비교한다.

    - 추정은 실제 `entry_price × qty`로 브라켓·청산식을 다시 구한다(Codex Q4 · 결정 비율 재사용 금지).
      레버리지는 결정값(layer 3가 `POST /leverage` 응답 == decision.leverage를 확인한 뒤에만 진입).
    - CHECK ⇔ `exchange_dist × buffer_rel < estimate_dist`(수수료 차감 모델) — "추정보다 버퍼 이상 가깝다".
    - 🔎 #4의 수수료 가정 판정용: 수수료 미차감 모델도 계산해 두 모델과의 차이·더 가까운 모델을 남긴다.
    """
    with exec_context():                            # EXEC_CTX(정밀도 34 · rounding·트랩 고정) — ccxt 전역 문맥 무관
        entry_price, qty = _dec(entry_price, "entry_price"), _dec(qty, "qty")
        exchange_liq_price = _dec(exchange_liq_price, "exchange_liq_price")
        if not decision.ok or decision.leverage is None:
            raise ValueError("수락된 사이징 결정에만 진입 후 검사를 한다")
        if entry_price <= 0 or qty <= 0:
            raise ValueError(f"실제 체결 entry_price·qty는 양수: {entry_price}, {qty}")
        notional = entry_price * qty
        est = liquidation_estimate(decision.direction, entry_price, notional, decision.leverage, rules)
        nofee = liquidation_estimate(decision.direction, entry_price, notional, decision.leverage, rules,
                                     taker=entry_price - entry_price)
        buf = decision.buffer_rel

        def result(status: Literal["OK", "CHECK"], dist: Decimal | None, detail: str) -> LiquidationCheck:
            g_fee = None if dist is None else dist - est.dist_pct
            g_nofee = None if dist is None else dist - nofee.dist_pct
            closer: Literal["fee", "no_fee", "tie"] | None = None
            if g_fee is not None and g_nofee is not None:
                #  거래소 청산가는 tick 단위다 → 두 모델 가격이 거래소 값에서 **몇 tick** 떨어졌는지로 비교(같으면 tie)
                tick = rules.symbol_rules.tick_size
                t_fee = (abs(exchange_liq_price - est.price) / tick).to_integral_value(rounding=decimal.ROUND_HALF_UP)
                t_nofee = (abs(exchange_liq_price - nofee.price) / tick).to_integral_value(rounding=decimal.ROUND_HALF_UP)
                closer = "tie" if t_fee == t_nofee else ("fee" if t_fee < t_nofee else "no_fee")
            return LiquidationCheck(status=status, exchange_dist_pct=dist, estimate_dist_pct=est.dist_pct,
                                    estimate_no_fee_dist_pct=nofee.dist_pct, gap_vs_fee_pct=g_fee,
                                    gap_vs_no_fee_pct=g_nofee, closer_model=closer, bracket=est.bracket,
                                    buffer_rel=buf, detail=detail)

        if exchange_liq_price <= 0:
            return result("CHECK", None, f"거래소 청산가 해석 불가: {exchange_liq_price}")
        if decision.direction is Direction.LONG:
            dist = (entry_price - exchange_liq_price) / entry_price
        else:
            dist = (exchange_liq_price - entry_price) / entry_price
        if dist <= 0:
            return result("CHECK", dist, f"거래소 청산가 {exchange_liq_price}가 {decision.direction} 진입가 {entry_price}의 잘못된 쪽")
        if dist * buf < est.dist_pct:
            return result("CHECK", dist, f"거래소 청산 거리 {dist} × {buf} < 실제 체결 기준 추정 {est.dist_pct}"
                                         f"(명목 {notional}·브라켓 {est.bracket})")
        return result("OK", dist, "")
