"""주문 송신기 — 페이퍼와 라이브가 **같은 인터페이스**다. 엔진은 모드를 모른 채 `OrderSender`만 부른다.

| | PaperSender | LiveSender |
|---|---|---|
| 생성 | 언제나 | `Mode.LIVE` + `LiveChecklist` 전 항목 True + 쓰기 가능 클라이언트 — 아니면 `LiveNotAuthorized` |
| 레버리지 | 기록·그대로 반환 | `POST /fapi/v1/leverage` → 응답 == 요청 확인(`set_leverage_confirmed`) |
| 예상 체결가 | `adverse_fill_estimate`(#7: 편도 2 bps 불리 + 불리 tick) | **같은 함수**(사용자 2026-09-15) — 사이징은 불리한 체결을 가정 |
| MARKET | 예상 체결가 그대로 · 수수료 = 런타임 taker | `POST /fapi/v1/order`(RESULT) → avgPrice·executedQty · 수수료 = userTrades 합 |
| positionRisk | 항상 None(레지스트리 #6) | `GET /fapi/v2/positionRisk` BOTH 행 |

🔴 LiveSender는 **이 저장소의 첫 실주문 경로**다 — 병합 전 Codex 검토(CLAUDE.md). 라이브 전환 배선(config·기동)은 아직 없다.
🔴 전송 불명(TransportError)·FILLED 아닌 상태 → `OrderOutcomeUnknown`: 호출자는 positionRisk 재조회 전까지 진입을 막는다.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import count
from typing import Any, Protocol

from exchange.client import ReadOnlyClient
from exchange.client_types import RestClient
from exchange.decimal_context import in_exec_context
from exchange.errors import BinanceAPIError, TransportError
from exchange.gate import Mode, set_leverage_confirmed
from exchange.orders import Side, validate_order_params
from exchange.rules import RuntimeRules
from paper.config import PAPER_SLIPPAGE_RATE
from paper.types import Fill, PositionRisk

ORDER = "/fapi/v1/order"
USER_TRADES = "/fapi/v1/userTrades"
POSITION_RISK = "/fapi/v2/positionRisk"


class LiveNotAuthorized(RuntimeError):
    """LIVE 송신기를 만들 조건(모드·체크리스트·쓰기 클라이언트)이 안 된다."""


class OrderOutcomeUnknown(RuntimeError):
    """주문이 체결됐는지 모른다(전송 끊김·FILLED 아닌 응답). positionRisk로 확인 전까지 진입 금지."""


class OrderSender(Protocol):
    mode: Mode

    def set_leverage(self, leverage: int) -> int: ...

    def quote_fill_price(self, side: Side, ref_mark: Decimal) -> Decimal: ...

    def send_market(self, params: dict[str, str], *, ref_mark: Decimal, ts_ms: int) -> Fill: ...

    def position_risk(self) -> PositionRisk | None: ...


@dataclass(frozen=True)
class LiveChecklist:
    """설계서 §10 라이브 전환 체크리스트 + 사용자 승인. 기본값 전부 False — 사람이 하나씩 켠다(자동 판정 없음)."""
    isolated_leverage_one_way_confirmed: bool = False           # 기동 게이트 재조회·레버리지 응답·원웨이
    runtime_rules_snapshot_and_config_hash_recorded: bool = False
    kill_switch_and_telegram_roundtrip_tested: bool = False      # 킬스위치 페이퍼 강제 발동 · 텔레그램 왕복
    usdm_only_account_no_coinm: bool = False                     # B6
    registry4_post_entry_check_logging_ready: bool = False       # #6: 첫 라이브 진입부터 진입 후 검사 로그
    registry5_day14_row_exists: bool = False
    #  사용자 2026-09-16(페이퍼는 기동 때만 읽음 · LIVE 필수): 런타임 규칙 주기 재조회 ≥ 6시간마다 + 24시간 넘은 규칙으로는 진입 금지
    runtime_rules_refresh_6h_and_entries_need_rules_under_24h: bool = False
    pause_reasons_are_a_set: bool = False                       # 사용자 2026-09-16: 일시정지 사유 단일값 → 집합(LIVE 전)
    #  사용자 2026-09-16: 거래 권한 키는 **LIVE 전환 때 새로 발급** · 화이트리스트 = VPS IP 하나만 · **VPS `.env`에만** 둔다(로컬 금지).
    #  페이퍼의 읽기 전용 키는 그대로 두고 따로 관리한다(권한이 다르므로 같은 키를 승격하지 않는다).
    trading_key_separate_vps_ip_only_and_never_local: bool = False
    user_approval: bool = False

    def missing(self) -> list[str]:
        return [f.name for f in fields(self) if getattr(self, f.name) is not True]


@in_exec_context
def adverse_fill_estimate(side: Side, ref_mark: Decimal, tick: Decimal, rate: Decimal = PAPER_SLIPPAGE_RATE) -> Decimal:
    """레지스트리 #7 예상 체결가 — mark × (1 ± rate)를 **불리한 tick**으로(BUY 올림 · SELL 내림).
    PAPER 체결가이자 PAPER·LIVE 공통 사이징 가격이다. LIVE에서 달라지는 건 실제 체결뿐(체결 후 #5 재검증이 잡는다)."""
    if not isinstance(rate, Decimal) or rate < 0:
        raise ValueError(f"slippage rate {rate!r}")
    if side is Side.BUY:
        return (ref_mark * (1 + rate) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
    return (ref_mark * (1 - rate) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


def _side(params: dict[str, str]) -> Side:
    return Side(params["side"])


class PaperSender:
    mode = Mode.PAPER

    def __init__(self, rules: RuntimeRules, *, slippage_rate: Decimal = PAPER_SLIPPAGE_RATE):
        if not isinstance(slippage_rate, Decimal) or slippage_rate < 0:
            raise ValueError(f"slippage_rate {slippage_rate!r}")
        self.rules, self.slippage_rate = rules, slippage_rate
        self.leverage: int | None = None
        self._ids = count(1)

    def set_leverage(self, leverage: int) -> int:
        self.leverage = leverage
        return leverage

    def quote_fill_price(self, side: Side, ref_mark: Decimal) -> Decimal:
        """PAPER 체결가는 결정적이다 — 엔진이 이 가격으로 사이징하면 체결 후 #5 게이트가 슬리피지로 깨지지 않는다."""
        return adverse_fill_estimate(side, ref_mark, self.rules.symbol_rules.tick_size, self.slippage_rate)

    def send_market(self, params: dict[str, str], *, ref_mark: Decimal, ts_ms: int) -> Fill:
        validate_order_params(params)
        if params["symbol"] != self.rules.symbol:
            raise ValueError(f"심볼 {params['symbol']} ≠ {self.rules.symbol}")
        side = _side(params)
        price = self.quote_fill_price(side, ref_mark)
        qty = Decimal(params["quantity"])
        return Fill(order_id=f"paper-{next(self._ids)}", side=side, qty=qty, price=price,
                    commission=qty * price * self.rules.commission.taker,
                    reduce_only=params.get("reduceOnly") == "true", ts_ms=ts_ms, ref_mark=ref_mark,
                    raw={"params": dict(params), "slippage_rate": str(self.slippage_rate)})

    def position_risk(self) -> None:
        return None


class LiveSender:
    mode = Mode.LIVE

    def __init__(self, client: RestClient, rules: RuntimeRules, *, mode: Mode, checklist: LiveChecklist):
        if mode is not Mode.LIVE:
            raise LiveNotAuthorized(f"LiveSender는 Mode.LIVE에서만 — 받은 값 {mode!r}")
        if not isinstance(checklist, LiveChecklist):
            raise LiveNotAuthorized("LiveChecklist가 필요하다")
        missing = checklist.missing()
        if missing:
            raise LiveNotAuthorized(f"라이브 체크리스트 미충족: {missing}")
        if isinstance(client, ReadOnlyClient):
            raise LiveNotAuthorized("읽기 전용 클라이언트로는 주문할 수 없다")
        self.client, self.rules = client, rules

    def set_leverage(self, leverage: int) -> int:
        return set_leverage_confirmed(self.client, self.rules.symbol, leverage)

    def quote_fill_price(self, side: Side, ref_mark: Decimal) -> Decimal:
        """사용자 결정(2026-09-15): #7 모델 그대로 — mark로 추정하면 모든 진입이 #5 경계에 붙어 실제 슬리피지가 곧
        체결 후 청산이 된다. 실제 체결이 추정보다 나쁘면 체결 후 #5 재검증이 즉시 청산한다(엔진)."""
        return adverse_fill_estimate(side, ref_mark, self.rules.symbol_rules.tick_size)

    def send_market(self, params: dict[str, str], *, ref_mark: Decimal, ts_ms: int) -> Fill:
        p = dict(params) | {"newOrderRespType": "RESULT"}
        validate_order_params(p)
        if p["symbol"] != self.rules.symbol:
            raise ValueError(f"심볼 {p['symbol']} ≠ {self.rules.symbol}")
        try:
            resp: Any = self.client.post(ORDER, p).data
        except TransportError as e:
            raise OrderOutcomeUnknown(f"주문 전송 결과 불명: {e}") from e
        if not isinstance(resp, dict) or resp.get("status") != "FILLED":
            raise OrderOutcomeUnknown(f"MARKET 응답이 FILLED가 아니다: {resp!r}")
        try:
            qty, price = Decimal(str(resp["executedQty"])), Decimal(str(resp["avgPrice"]))
            oid = str(resp["orderId"])
        except (KeyError, ArithmeticError) as e:
            raise OrderOutcomeUnknown(f"체결 응답 해석 불가: {resp!r}") from e
        if qty <= 0 or price <= 0:
            raise OrderOutcomeUnknown(f"체결 수량·가격이 0: {resp!r}")
        #  🔴 Codex L3 검토 2: 여기부터는 **이미 체결된 주문**이다 — 어떤 조회·해석 실패도 예외로 새면 안 된다
        commission, estimated = self._commission(oid, qty, price)
        try:
            ts = int(str(resp.get("updateTime", ts_ms)))
        except ValueError:
            ts = ts_ms
        return Fill(order_id=oid, side=_side(p), qty=qty, price=price, commission=commission,
                    reduce_only=p.get("reduceOnly") == "true", ts_ms=ts,
                    ref_mark=ref_mark, commission_estimated=estimated, raw={"params": p, "response": resp})

    def _commission(self, order_id: str, qty: Decimal, price: Decimal) -> tuple[Decimal, bool]:
        """userTrades(이 주문·이 심볼 행만) 수수료 합. 조회 실패·빈 응답·해석 불가·USDT 아님·수량 합 불일치 →
        런타임 taker로 추정하고 `commission_estimated=True`(체결 자체는 유효)."""
        estimate = (qty * price * self.rules.commission.taker, True)
        try:
            data = self.client.get(USER_TRADES, {"symbol": self.rules.symbol, "orderId": order_id}, signed=True).data
            if not isinstance(data, list):
                return estimate
            rows = [t for t in data if isinstance(t, dict) and str(t.get("orderId")) == order_id
                    and t.get("symbol", self.rules.symbol) == self.rules.symbol]
            if not rows or any(str(t.get("commissionAsset")) != "USDT" for t in rows):
                return estimate
            if sum((Decimal(str(t["qty"])) for t in rows), Decimal()) != qty:
                return estimate
            return sum((Decimal(str(t["commission"])) for t in rows), Decimal()), False
        except (BinanceAPIError, TransportError, KeyError, TypeError, ArithmeticError):
            return estimate

    def position_risk(self) -> PositionRisk:
        """BOTH 행 1개. 🔴 Codex L3 재검토 1: 응답 모양·숫자 해석 실패도 `OrderOutcomeUnknown` 하나로 올린다
        (주문 뒤 대사 조회에서 파서 예외가 엔진 밖으로 새지 않게). 전송·HTTP 오류는 원래 예외 그대로."""
        data = self.client.get(POSITION_RISK, {"symbol": self.rules.symbol}, signed=True).data
        try:
            rows = [r for r in data if isinstance(r, dict) and r.get("symbol") == self.rules.symbol
                    and r.get("positionSide", "BOTH") == "BOTH"]
            if len(rows) != 1:
                raise OrderOutcomeUnknown(f"positionRisk {self.rules.symbol}/BOTH 행 {len(rows)}개")
            r = rows[0]
            return PositionRisk(Decimal(str(r["positionAmt"])), Decimal(str(r["entryPrice"])),
                                Decimal(str(r["liquidationPrice"])), raw=r)
        except (KeyError, TypeError, ArithmeticError, AttributeError) as e:
            raise OrderOutcomeUnknown(f"positionRisk 해석 불가 {type(e).__name__}: {data!r}") from e


def make_sender(mode: Mode, rules: RuntimeRules, *, client: RestClient | None = None,
                checklist: LiveChecklist | None = None) -> OrderSender:
    if mode is Mode.PAPER:
        return PaperSender(rules)
    if mode is Mode.LIVE:
        if client is None or checklist is None:
            raise LiveNotAuthorized("LIVE는 쓰기 클라이언트와 체크리스트가 필요하다")
        return LiveSender(client, rules, mode=mode, checklist=checklist)
    raise ValueError(f"알 수 없는 모드 {mode!r}")
