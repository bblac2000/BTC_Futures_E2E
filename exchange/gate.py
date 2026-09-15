"""기동 게이트 — exchange-rules §4 · v6 §0.4(B2).

LIVE (계정을 **바꾸는** 유일한 기동 경로 — Codex 독립 검토 대상):
  0. 심볼 status=TRADING, 설정 레버리지가 `1 ≤ L ≤ 브라켓 최대`(런타임 조회값)인지 — 아니면 POST 없이 중단
  1. `positionSide/dual` → true면 (**계정 전 심볼** 포지션·미체결 0 확인 후) false로 → **재조회 확정**
  2. `multiAssetsMargin` → true면 중단(멀티에셋 모드는 격리를 지원하지 않는다 · 계정 전역 설정이라 자동 변경 안 함)
  3. `positionRisk.marginType` → ISOLATED가 아니면 포지션·미체결 0 확인 후 `marginType=ISOLATED`
     → **재조회로 확정**(POST 응답을 믿지 않는다 — "성공 보고 ≠ 실제" 실패 유형)
  4. `leverage` 명시 설정(미설정 시 계정 기본 5x·cross로 매매된다) → 응답 레버리지 일치 확인
  어느 단계든 실패 → `StartupAbort`: **진입 금지, 청산만 허용**.

PAPER: `ReadOnlyClient`로 감싸 **POST 0회**를 구조적으로 보장. 불일치는 WARNING만, 기동 계속.

⚠️ 거래당 실효 레버리지(50~100x, SL 거리에서 도출)는 layer 2/3이 진입 직전에 설정한다.
   여기서 받는 `leverage`는 config의 기동 초기값이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import NoReturn

from exchange.client import ReadOnlyClient
from exchange.client_types import RestClient
from exchange.errors import (
    BinanceAPIError,
    CredentialsMissing,
    LeverageNotConfirmed,
    StartupAbort,
    TransportError,
)
from exchange.rules import RuntimeRules

NO_NEED_TO_CHANGE_MARGIN = -4046
#  공식 문서 "Current All Algo Open Orders (USER_DATA)" — 2026-09-15 렌더링 페이지에서 경로·파라미터 확인
ALGO_OPEN_ORDERS = "/fapi/v1/openAlgoOrders"
LEVERAGE = "/fapi/v1/leverage"


class Mode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


@dataclass
class GateResult:
    mode: Mode
    entries_allowed: bool = False
    exits_allowed: bool = True
    margin_type_before: str | None = None
    isolated_confirmed: bool = False
    leverage_set: int | None = None
    dual_side_position: bool | None = None
    multi_assets_margin: bool | None = None
    warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def _symbol_rows(client: RestClient, symbol: str) -> list[dict]:
    """심볼의 positionRisk 행 전부. 🔴 원웨이는 BOTH 1행, **헤지 모드는 LONG·SHORT 2행**(BOTH 없음)."""
    rows = [r for r in client.get("/fapi/v2/positionRisk", {"symbol": symbol}, signed=True).data
            if r.get("symbol") == symbol]
    if not rows:
        raise BinanceAPIError(200, None, f"positionRisk에 {symbol} 행이 없다", "/fapi/v2/positionRisk")
    return rows


def _position_row(client: RestClient, symbol: str) -> dict:
    """원웨이 확정 **후**에만 쓴다 — BOTH 행 정확히 1개."""
    hit = [r for r in _symbol_rows(client, symbol) if r.get("positionSide", "BOTH") == "BOTH"]
    if len(hit) != 1:
        raise BinanceAPIError(200, None, f"positionRisk에 {symbol}/BOTH 행이 {len(hit)}개", "/fapi/v2/positionRisk")
    return hit[0]


def _is_isolated(rows: list[dict]) -> bool:
    """⚠️ v6 §0.4는 재조회 `isolated=true`를 요구하지만 현행 공식 positionRisk V2 문서에는 `isolated` bool이 없고
    `marginType`만 있다(Codex 검토 2026-09-15, 불확실 표기). → `marginType=="isolated"`로 판정하고,
    `isolated` 키가 **있으면** true여야 한다. 라이브 전 실계정 read-only 캡처로 필드를 확인한다(TODO)."""
    return all(str(r.get("marginType", "")).lower() == "isolated" and r.get("isolated", True) is True
               for r in rows)


def _bool(data: object, key: str) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get(key), bool):
        raise TypeError(f"{key} 응답이 bool이 아니다: {data!r}")
    return data[key]


def _amt(row: dict) -> Decimal:
    """positionAmt 엄격 해석 — 🔴 Codex 재검토 F1: 필드가 없으면 0으로 치지 않는다(fail-closed)."""
    if "positionAmt" not in row:
        raise TypeError(f"positionRisk 행에 positionAmt 없음: {row!r}")
    return Decimal(str(row["positionAmt"]))


def _account_flat(client: RestClient) -> tuple[bool, str]:
    """계정 전역 설정(positionSide/dual)을 바꾸기 전 — **모든 USDⓈ-M 심볼**의 포지션·미체결이 0인가."""
    rows = client.get("/fapi/v2/positionRisk", signed=True).data
    legs = [f"{r.get('symbol')}/{r.get('positionSide', 'BOTH')}={r.get('positionAmt')}" for r in rows
            if _amt(r) != 0]
    if legs:
        return False, f"포지션 보유({', '.join(legs)})"
    orders = client.get("/fapi/v1/openOrders", signed=True).data
    if orders:
        return False, f"미체결 {len(orders)}건({', '.join(sorted({str(o.get('symbol')) for o in orders}))})"
    #  조건부(algo) 주문은 openOrders에 안 나온다(2025-12 algo 서비스 이관). 공식 문서 확인(2026-09-15):
    #  `GET /fapi/v1/openAlgoOrders` · symbol 생략 = 전 심볼 · IP weight 40(기동 시 1회)
    algos = client.get(ALGO_OPEN_ORDERS, signed=True).data
    if algos:
        return False, f"algo 미체결 {len(algos)}건({', '.join(sorted({str(o.get('symbol')) for o in algos}))})"
    return True, ""


def _flat(client: RestClient, symbol: str, rows: list[dict]) -> tuple[bool, str]:
    """모든 행(헤지면 두 다리)의 positionAmt가 0이고 미체결이 없어야 flat."""
    open_legs = [f"{r.get('positionSide', 'BOTH')}={r.get('positionAmt')}" for r in rows
                 if _amt(r) != 0]
    if open_legs:
        return False, f"포지션 보유 중({', '.join(open_legs)})"
    orders = client.get("/fapi/v1/openOrders", {"symbol": symbol}, signed=True).data
    if orders:
        return False, f"미체결 {len(orders)}건"
    algos = client.get(ALGO_OPEN_ORDERS, {"symbol": symbol}, signed=True).data
    if algos:
        return False, f"algo 미체결 {len(algos)}건"
    return True, ""


def set_leverage_confirmed(client: RestClient, symbol: str, leverage: int) -> int:
    """`POST /fapi/v1/leverage` → 응답 레버리지 == 요청일 때만 반환. 기동 게이트와 layer 3 LIVE 송신기가 공유한다.
    🔴 POST 성공 ≠ 적용 — 응답 모양이 다르거나 값이 다르면 `LeverageNotConfirmed`(그 레버리지로 진입 금지)."""
    echo = client.post(LEVERAGE, {"symbol": symbol, "leverage": str(leverage)}).data
    if not isinstance(echo, dict) or "leverage" not in echo:
        raise LeverageNotConfirmed(f"레버리지 응답 모양 해석 불가: {echo!r}")
    if int(echo["leverage"]) != leverage:
        raise LeverageNotConfirmed(f"레버리지 {leverage}x 요청했으나 응답 {echo['leverage']}x")
    return leverage


def run_startup_gate(client: RestClient, rules: RuntimeRules, mode: Mode, *, leverage: int) -> GateResult:
    if mode is Mode.PAPER:
        return _paper(ReadOnlyClient(client), rules, leverage)
    if mode is Mode.LIVE:
        return _live(client, rules, leverage)
    raise ValueError(f"알 수 없는 모드 {mode!r}")


def _paper(client: RestClient, rules: RuntimeRules, leverage: int) -> GateResult:
    sym = rules.symbol
    res = GateResult(Mode.PAPER, entries_allowed=True, exits_allowed=True)
    if rules.symbol_rules.status != "TRADING":
        res.warnings.append(f"{sym} status={rules.symbol_rules.status}")
    if not 1 <= leverage <= rules.max_leverage:
        res.warnings.append(f"설정 레버리지 {leverage}x가 브라켓 범위 1~{rules.max_leverage}x 밖")
    try:
        res.dual_side_position = _bool(client.get("/fapi/v1/positionSide/dual", signed=True).data, "dualSidePosition")
        res.multi_assets_margin = _bool(client.get("/fapi/v1/multiAssetsMargin", signed=True).data, "multiAssetsMargin")
        rows = _symbol_rows(client, sym)
        legs = [f"{r.get('positionSide', 'BOTH')}={r.get('positionAmt')}" for r in rows if _amt(r) != 0]
    except (CredentialsMissing, BinanceAPIError, TransportError, OSError,
            KeyError, TypeError, AttributeError, InvalidOperation) as e:
        res.warnings.append(f"계정 상태를 읽을 수 없다(PAPER는 계속): {type(e).__name__}: {e}")
        return res
    res.margin_type_before = str(rows[0].get("marginType"))
    res.isolated_confirmed = _is_isolated(rows)
    if res.dual_side_position:
        res.warnings.append("dualSidePosition=true(헤지 모드) — LIVE 전환 시 원웨이로 바꿔야 한다")
    if res.multi_assets_margin:
        res.warnings.append("multiAssetsMargin=true — LIVE는 이 상태로 기동하지 않는다")
    if not res.isolated_confirmed:
        res.warnings.append(f"marginType={res.margin_type_before} — LIVE 전환 시 ISOLATED 강제(§0.4). PAPER는 SET 금지")
    if legs:
        res.warnings.append(f"실계정에 {sym} 포지션 {', '.join(legs)} 존재 — 페이퍼와 무관하나 기록")
    return res


def _live(client: RestClient, rules: RuntimeRules, leverage: int) -> GateResult:
    sym = rules.symbol
    res = GateResult(Mode.LIVE)

    def abort(reason: str) -> NoReturn:
        res.entries_allowed, res.exits_allowed = False, True
        raise StartupAbort(reason, res)

    if rules.symbol_rules.status != "TRADING":
        abort(f"{sym} status={rules.symbol_rules.status} — TRADING 아님")
    if not isinstance(leverage, int) or not 1 <= leverage <= rules.max_leverage:
        abort(f"설정 레버리지 {leverage!r}가 브라켓 범위 1~{rules.max_leverage}x 밖")

    try:
        # 1. 원웨이
        dual = _bool(client.get("/fapi/v1/positionSide/dual", signed=True).data, "dualSidePosition")
        if dual:
            #  🔴 Codex 검토 Q3: 포지션 모드는 **계정 전 심볼** 설정 — BTC만 보면 안 된다.
            #  ⚠️ COIN-M(dapi) 포지션은 이 API로 안 보인다. 그 경우 거래소가 POST를 거부하고 여기서 중단된다(fail-closed).
            ok, why = _account_flat(client)
            if not ok:
                abort(f"헤지 모드인데 계정에 {why} — 원웨이로 바꿀 수 없다")
            client.post("/fapi/v1/positionSide/dual", {"dualSidePosition": "false"})
            res.actions.append("positionSide/dual → false")
            dual = _bool(client.get("/fapi/v1/positionSide/dual", signed=True).data, "dualSidePosition")
            if dual:
                abort("dualSidePosition=false 설정 후 재조회가 여전히 true")
        res.dual_side_position = dual

        # 2. 단일에셋
        multi = _bool(client.get("/fapi/v1/multiAssetsMargin", signed=True).data, "multiAssetsMargin")
        res.multi_assets_margin = multi
        if multi:
            abort("multiAssetsMargin=true — 격리 불가 모드. 계정 전역 설정이라 사람이 바꾼다")

        # 3. 격리
        row = _position_row(client, sym)
        res.margin_type_before = str(row.get("marginType"))
        if not _is_isolated([row]):
            ok, why = _flat(client, sym, [row])
            if not ok:
                abort(f"marginType={res.margin_type_before}인데 {why} — ISOLATED로 바꿀 수 없다")
            try:
                client.post("/fapi/v1/marginType", {"symbol": sym, "marginType": "ISOLATED"})
                res.actions.append(f"marginType {res.margin_type_before} → ISOLATED")
            except BinanceAPIError as e:
                if e.code != NO_NEED_TO_CHANGE_MARGIN:
                    raise
                res.actions.append("marginType POST -4046(no need to change) — 재조회로 확인")
            row = _position_row(client, sym)
        res.isolated_confirmed = _is_isolated([row])
        if not res.isolated_confirmed:
            abort(f"재조회 marginType={row.get('marginType')} — ISOLATED 확정 실패")

        # 4. 레버리지
        try:
            res.leverage_set = set_leverage_confirmed(client, sym, leverage)
        except LeverageNotConfirmed as e:
            abort(str(e))
        res.actions.append(f"leverage → {leverage}x")
    except (CredentialsMissing, BinanceAPIError) as e:
        abort(f"계정 조회/설정 실패: {e}")
    except (TransportError, OSError) as e:
        #  🔴 Codex 재검토 F3 — POST 뒤 끊겼으면 계정이 바뀌었는지 모른다. 진입 금지로 끝내고 사람이 재조회한다.
        abort(f"전송 실패 — 계정 상태 불명(직전 POST 반영 여부 모름 · actions={res.actions}) · 재조회 후 재기동: {e}")
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation) as e:
        #  🔴 Codex 검토 Q5: 예상 밖 응답 모양도 **항상** StartupAbort(진입 금지·청산 허용)로 끝난다
        abort(f"거래소 응답 모양 해석 불가: {type(e).__name__}: {e}")

    res.entries_allowed, res.exits_allowed = True, True
    return res
