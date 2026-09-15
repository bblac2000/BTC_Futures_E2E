"""거래소 규칙 **해석** — 응답 JSON → 불변 dataclass. 값은 전부 응답에서 온다.

🔴 헌법(exchange-rules §1): tick/step/MIN_NOTIONAL/MMR/수수료/펀딩 cap/브라켓은 **리터럴 금지**.
   이 모듈은 숫자를 하나도 갖지 않는다. 필요한 필터가 응답에 없으면 `RulesError`로 멈춘다 —
   "없으면 BTC 값" 같은 대체값은 v6가 금지한 심볼 간 차용과 같다.
⚠️ 스냅샷마다 숫자 표기가 다르다(VolumeClockBot: JSON float `0.004` / BreakoutTrading: 문자열 `"0.004"`).
   전부 `Decimal(str(x))`로 읽어 float 오차를 들이지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from exchange.errors import RulesError


def dec(x: Any, what: str) -> Decimal:
    if x is None or isinstance(x, bool):
        raise RulesError(f"{what}: 값 없음({x!r})")
    try:
        return Decimal(str(x))
    except InvalidOperation as e:
        raise RulesError(f"{what}: Decimal 변환 불가 {x!r}") from e


@dataclass(frozen=True)
class SymbolRules:
    symbol: str
    status: str
    contract_type: str
    margin_asset: str
    price_precision: int
    quantity_precision: int
    tick_size: Decimal
    min_price: Decimal
    max_price: Decimal
    lot_step: Decimal
    lot_min_qty: Decimal
    lot_max_qty: Decimal
    market_step: Decimal
    market_min_qty: Decimal
    market_max_qty: Decimal
    min_notional: Decimal
    liquidation_fee: Decimal
    market_take_bound: Decimal
    trigger_protect: Decimal


@dataclass(frozen=True)
class Bracket:
    bracket: int
    initial_leverage: int
    notional_floor: Decimal
    notional_cap: Decimal
    maint_margin_ratio: Decimal
    cum: Decimal


@dataclass(frozen=True)
class Commission:
    maker: Decimal
    taker: Decimal


@dataclass(frozen=True)
class FundingInfo:
    """`present=False` = fundingInfo에 심볼이 없다 → 거래소 기본값 적용 중. 🚫cap을 추정하지 않는다."""
    present: bool
    cap: Decimal | None
    floor: Decimal | None
    interval_hours: int | None


@dataclass(frozen=True)
class AccountModes:
    dual_side_position: bool
    multi_assets_margin: bool


@dataclass(frozen=True)
class RateLimit:
    rate_limit_type: str      # REQUEST_WEIGHT | ORDERS
    interval: str             # SECOND | MINUTE | HOUR | DAY
    interval_num: int
    limit: int

    @property
    def window_ms(self) -> int:
        unit = {"SECOND": 1_000, "MINUTE": 60_000, "HOUR": 3_600_000, "DAY": 86_400_000}
        if self.interval not in unit:
            raise RulesError(f"알 수 없는 rateLimit interval {self.interval!r}")
        return unit[self.interval] * self.interval_num


@dataclass(frozen=True)
class RuntimeRules:
    """한 심볼의 런타임 규칙 묶음 + 출처 시각. 봇은 이것만 보고 사이징·정규화한다."""
    symbol: str
    symbol_rules: SymbolRules
    brackets: tuple[Bracket, ...]
    commission: Commission
    funding: FundingInfo
    account_modes: AccountModes | None          # PAPER에서 서명 조회 불가면 None
    rate_limits: tuple[RateLimit, ...]
    fetched_at_utc: dict[str, str] = field(default_factory=dict)   # endpoint → ISO 시각
    server_time_ms: int | None = None

    @property
    def max_leverage(self) -> int:
        return max(b.initial_leverage for b in self.brackets)

    def bracket_for_notional(self, notional: Decimal) -> Bracket:
        """`floor ≤ notional < cap`인 브라켓. 범위 밖이면 예외(마지막 cap 초과 = 거래 불가 규모)."""
        if notional < 0:
            raise RulesError(f"음수 명목 {notional}")
        for b in self.brackets:
            if b.notional_floor <= notional < b.notional_cap:
                return b
        raise RulesError(f"명목 {notional}이 어떤 브라켓에도 없다(최대 cap {self.brackets[-1].notional_cap})")


# ─────────────────────────── 파서 ───────────────────────────
def _filters(sym: dict) -> dict[str, dict]:
    return {f["filterType"]: f for f in sym.get("filters", [])}


def _need(filters: dict[str, dict], name: str, symbol: str) -> dict:
    if name not in filters:
        raise RulesError(f"{symbol}: exchangeInfo에 {name} 필터가 없다 — 추정하지 않는다")
    return filters[name]


def parse_symbol_rules(exchange_info: dict, symbol: str) -> SymbolRules:
    syms = [s for s in exchange_info.get("symbols", []) if s.get("symbol") == symbol]
    if len(syms) != 1:
        raise RulesError(f"exchangeInfo에 {symbol}이 {len(syms)}개 — 정확히 1개여야 한다")
    s = syms[0]
    f = _filters(s)
    pf, lot, mlot, mn = (_need(f, n, symbol) for n in
                         ("PRICE_FILTER", "LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL"))
    return SymbolRules(
        symbol=symbol,
        status=str(s.get("status")),
        contract_type=str(s.get("contractType")),
        margin_asset=str(s.get("marginAsset")),
        price_precision=int(s["pricePrecision"]),
        quantity_precision=int(s["quantityPrecision"]),
        tick_size=dec(pf.get("tickSize"), f"{symbol}.tickSize"),
        min_price=dec(pf.get("minPrice"), f"{symbol}.minPrice"),
        max_price=dec(pf.get("maxPrice"), f"{symbol}.maxPrice"),
        lot_step=dec(lot.get("stepSize"), f"{symbol}.LOT_SIZE.stepSize"),
        lot_min_qty=dec(lot.get("minQty"), f"{symbol}.LOT_SIZE.minQty"),
        lot_max_qty=dec(lot.get("maxQty"), f"{symbol}.LOT_SIZE.maxQty"),
        market_step=dec(mlot.get("stepSize"), f"{symbol}.MARKET_LOT_SIZE.stepSize"),
        market_min_qty=dec(mlot.get("minQty"), f"{symbol}.MARKET_LOT_SIZE.minQty"),
        market_max_qty=dec(mlot.get("maxQty"), f"{symbol}.MARKET_LOT_SIZE.maxQty"),
        min_notional=dec(mn.get("notional"), f"{symbol}.MIN_NOTIONAL.notional"),
        liquidation_fee=dec(s.get("liquidationFee"), f"{symbol}.liquidationFee"),
        market_take_bound=dec(s.get("marketTakeBound"), f"{symbol}.marketTakeBound"),
        trigger_protect=dec(s.get("triggerProtect"), f"{symbol}.triggerProtect"),
    )


def parse_rate_limits(exchange_info: dict) -> tuple[RateLimit, ...]:
    rl = exchange_info.get("rateLimits")
    if not rl:
        raise RulesError("exchangeInfo.rateLimits 없음 — rate limit 가드를 추정값으로 돌리지 않는다")
    return tuple(RateLimit(str(r["rateLimitType"]), str(r["interval"]), int(r["intervalNum"]),
                           int(r["limit"])) for r in rl)


def parse_brackets(resp: Any, symbol: str) -> tuple[Bracket, ...]:
    """`/fapi/v1/leverageBracket` 응답 — 리스트·단일 객체·심볼 키 dict(스냅샷) 모두 받는다."""
    entries: list
    if isinstance(resp, dict) and "brackets" in resp:
        entries = [resp]
    elif isinstance(resp, dict):
        v = resp.get(symbol)
        entries = v if isinstance(v, list) else ([v] if v else [])
    elif isinstance(resp, list):
        entries = resp
    else:
        raise RulesError(f"leverageBracket 응답 형태 불명: {type(resp).__name__}")
    hit = [e for e in entries if e.get("symbol") == symbol]
    if len(hit) != 1:
        raise RulesError(f"leverageBracket에 {symbol}이 {len(hit)}개")
    out = tuple(sorted((
        Bracket(int(b["bracket"]), int(b["initialLeverage"]),
                dec(b.get("notionalFloor"), f"{symbol}.bracket.notionalFloor"),
                dec(b.get("notionalCap"), f"{symbol}.bracket.notionalCap"),
                dec(b.get("maintMarginRatio"), f"{symbol}.bracket.maintMarginRatio"),
                dec(b.get("cum"), f"{symbol}.bracket.cum"))
        for b in hit[0].get("brackets", [])), key=lambda b: b.bracket))
    if not out:
        raise RulesError(f"{symbol}: 브라켓 0개")
    for b in out:
        if b.cum < 0:
            raise RulesError(f"{symbol}: 브라켓 {b.bracket} cum {b.cum} < 0 — cum 무시가 보수적이라는 전제가 깨진다")
    for a, b in zip(out, out[1:], strict=False):
        if a.notional_cap != b.notional_floor:
            raise RulesError(f"{symbol}: 브라켓 {a.bracket}→{b.bracket} 구간이 이어지지 않는다")
        #  🔴 Codex layer 2 검토: 사이징은 '명목이 줄면 위험이 줄어든다'(MMR 비감소)를 전제로 한다
        if b.maint_margin_ratio < a.maint_margin_ratio:
            raise RulesError(f"{symbol}: 브라켓 {a.bracket}→{b.bracket} MMR이 감소한다 "
                             f"({a.maint_margin_ratio}→{b.maint_margin_ratio})")
        #  🔴 Codex L2 전체검토 Q2: 바이낸스 cum은 유지증거금이 경계에서 **연속**이 되도록 정의된다.
        #     불연속이면 청산가 티어 탐색이 두 티어 사이를 진동할 수 있다(고정점 없음).
        if b.cum != a.cum + b.notional_floor * (b.maint_margin_ratio - a.maint_margin_ratio):
            raise RulesError(f"{symbol}: 브라켓 {a.bracket}→{b.bracket} cum 불연속 "
                             f"({a.cum} + {b.notional_floor}×({b.maint_margin_ratio}−{a.maint_margin_ratio}) ≠ {b.cum})")
        if b.initial_leverage > a.initial_leverage:
            raise RulesError(f"{symbol}: 브라켓 {a.bracket}→{b.bracket} 최대 레버리지가 증가한다 "
                             f"({a.initial_leverage}→{b.initial_leverage})")
    return out


def parse_commission(resp: Any, symbol: str) -> Commission:
    if isinstance(resp, dict) and "symbol" not in resp:
        resp = resp.get(symbol)
    if not isinstance(resp, dict) or resp.get("symbol") != symbol:
        raise RulesError(f"commissionRate에 {symbol} 없음")
    return Commission(dec(resp.get("makerCommissionRate"), f"{symbol}.maker"),
                      dec(resp.get("takerCommissionRate"), f"{symbol}.taker"))


def parse_funding_info(resp: Any, symbol: str) -> FundingInfo:
    if not isinstance(resp, list):
        raise RulesError(f"fundingInfo 응답이 리스트가 아니다: {type(resp).__name__}")
    hit = [r for r in resp if r.get("symbol") == symbol]
    if not hit:
        return FundingInfo(present=False, cap=None, floor=None, interval_hours=None)
    r = hit[0]
    return FundingInfo(True, dec(r.get("adjustedFundingRateCap"), f"{symbol}.fundingCap"),
                       dec(r.get("adjustedFundingRateFloor"), f"{symbol}.fundingFloor"),
                       int(r["fundingIntervalHours"]))


def parse_account_modes(dual_resp: dict, multi_resp: dict) -> AccountModes:
    for d, k in ((dual_resp, "dualSidePosition"), (multi_resp, "multiAssetsMargin")):
        if not isinstance(d, dict) or not isinstance(d.get(k), bool):
            raise RulesError(f"{k} 응답 해석 불가: {d!r}")
    return AccountModes(dual_resp["dualSidePosition"], multi_resp["multiAssetsMargin"])
