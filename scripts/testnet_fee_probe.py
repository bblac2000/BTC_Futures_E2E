"""테스트넷 수수료 가정 프로브 — 레지스트리 #4 "진입 taker 수수료가 격리 마진을 줄이는가"를 **메커니즘**으로 판정.

사용:  uv run python scripts/testnet_fee_probe.py                 # 실행 → var/testnet_probe/<UTC>.json + 레지스트리 새 행
       uv run python scripts/testnet_fee_probe.py --no-registry   # JSON만

🔴 **테스트넷 전용.** base URL은 `.env`의 `BINANCE_TESTNET_BASE_URL`(공식 문서 2026-09-15 확인: `https://demo-fapi.binance.com`).
   `TESTNET_HOSTS` 밖 호스트(메인넷 `fapi.binance.com` 포함)는 **나가는 요청마다** 네트워크 도달 전에 거부한다.
   키는 `BINANCE_TESTNET_API_KEY`/`BINANCE_TESTNET_API_SECRET`만 읽는다 — 메인넷 변수로 대체하지 않고, 메인넷 키와 같으면 거부.
🔴 테스트넷의 MMR·수수료 **값**은 어디에도 쓰지 않는다(값은 항상 메인넷 런타임 조회). 결과 JSON에 scope로 남긴다.

해석 규칙은 **설계서 §11**(사전확약 `622794c` · 보충 `79880d1`, 이 스크립트 작성 전 커밋)이 정한다 — 여기서 바꾸지 않는다.
절차: 런타임 규칙(테스트넷) → L=100 가능 확인 → `run_startup_gate(Mode.LIVE)`(원웨이·ISOLATED 재조회·레버리지 응답)
      → LONG: MARKET 진입 → positionRisk v2·v3 + userTrades 읽기 → **try/finally 청산(reduceOnly) + flat 재조회** → SHORT 동일.
청산이 확인되지 않으면 즉시 멈추고(exit 3) 레지스트리에 쓰지 않는다 — 테스트넷 계정에서 수동 정리.
"""
from __future__ import annotations

import argparse
import decimal
import json
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exchange.client import BinanceRestClient  # noqa: E402
from exchange.client_types import RestClient  # noqa: E402
from exchange.errors import BinanceAPIError, RulesError, StartupAbort, TransportError  # noqa: E402
from exchange.gate import ALGO_OPEN_ORDERS, Mode, run_startup_gate  # noqa: E402
from exchange.loader import load_runtime_rules  # noqa: E402
from exchange.normalize import ceil_to_step  # noqa: E402
from exchange.orders import (  # noqa: E402
    Direction,
    close_position_orders,
    entry_orders,
    validate_order_params,
)
from exchange.rules import RuntimeRules, SymbolRules  # noqa: E402
from exchange.timesync import TimeSync  # noqa: E402
from sizing.position import DECIMAL_PREC, liquidation_estimate  # noqa: E402

#  공식 문서 "Testnet API Information"(2026-09-15 확인) + v6 §9의 옛 주소. 메인넷 호스트는 절대 넣지 않는다.
TESTNET_HOSTS = frozenset({"demo-fapi.binance.com", "testnet.binancefuture.com"})

SYMBOL = "BTCUSDT"
ORDER = "/fapi/v1/order"
POSITION_V2 = "/fapi/v2/positionRisk"
POSITION_V3 = "/fapi/v3/positionRisk"
OPEN_ORDERS = "/fapi/v1/openOrders"
USER_TRADES = "/fapi/v1/userTrades"
PREMIUM_INDEX = "/fapi/v1/premiumIndex"

#  설계서 §11 고정 파라미터(사전확약)
PROBE_LEVERAGE = 100
NOTIONAL_HEADROOM = Decimal("1.1")
TRADES_RETRIES = 5
TRADES_RETRY_SEC = 1
CLOSE_ATTEMPTS = 3
CLOSE_RETRY_SEC = 1
DISPLAY_ROUNDING = Decimal("0.00000002")
RULE_REF = "설계서 §11 (사전확약 622794c · 보충 79880d1)"
SCOPE = "testnet mechanism only — testnet MMR/fee values are not used anywhere else"

REGISTRY = ROOT / "docs" / "trial_registry.md"
OUT_DIR = ROOT / "var" / "testnet_probe"


class NotTestnet(RuntimeError):
    pass


class ProbeAbort(RuntimeError):
    pass


class CloseFailed(RuntimeError):
    pass


# ── 호스트 가드 ─────────────────────────────────────────────────────────────
def require_testnet(url: str) -> None:
    """https · 허용 호스트 · **포트 명시 금지(기본 443만)** · userinfo 금지. hostname은 urlsplit이 소문자로 만든다."""
    u = urllib.parse.urlsplit(url or "")
    try:
        port = u.port
    except ValueError as e:
        raise NotTestnet(f"URL 포트 해석 불가: {url!r}") from e
    if u.scheme != "https" or u.hostname not in TESTNET_HOSTS or port is not None or u.username or u.password:
        raise NotTestnet(f"테스트넷 URL이 아니다: scheme={u.scheme!r} host={u.hostname!r} port={port!r} "
                         f"userinfo={'있음' if (u.username or u.password) else '없음'} — 허용 {sorted(TESTNET_HOSTS)}")


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """🔴 Codex 검토 Q1: urllib 기본 opener는 3xx를 따라가며 가드를 다시 거치지 않는다 → 리다이렉트는 **전부** 거부."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise NotTestnet(f"리다이렉트 거부 HTTP {code} → {newurl!r} (주문·서명 요청은 다른 URL로 가지 않는다)")


#  build_opener는 기본 HTTPRedirectHandler 대신 이 하위 클래스를 쓴다(기본 핸들러가 추가되지 않는다)
DEFAULT_OPENER = urllib.request.build_opener(RefuseRedirects())


def guarded_opener(inner: Callable[..., Any]) -> Callable[..., Any]:
    """실제로 나가는 URL을 **요청마다** 검사한다(생성 후 base_url이 바뀌어도 막힌다)."""
    def op(req: urllib.request.Request, timeout: float) -> Any:
        require_testnet(req.full_url)
        return inner(req, timeout=timeout)
    return op


def _wall_ms() -> int:
    return int(time.time() * 1000)


def make_client(base_url: str, key: str, secret: str, *, opener: Callable[..., Any] = DEFAULT_OPENER.open,
                clock_ms: Callable[[], int] = _wall_ms) -> BinanceRestClient:
    require_testnet(base_url)
    return BinanceRestClient(base_url, key, secret, time_sync=TimeSync(), opener=guarded_opener(opener),
                             clock_ms=clock_ms)


# ── 읽기 도우미 ─────────────────────────────────────────────────────────────
def _both_row(data: Any) -> dict:
    rows = [r for r in (data or []) if isinstance(r, dict) and r.get("symbol") == SYMBOL
            and r.get("positionSide", "BOTH") == "BOTH"]
    if len(rows) != 1:
        raise ValueError(f"positionRisk {SYMBOL}/BOTH 행 {len(rows)}개")
    return rows[0]


def _mark(client: RestClient) -> Decimal:
    m = Decimal(str(client.get(PREMIUM_INDEX, {"symbol": SYMBOL}).data["markPrice"]))
    if m <= 0:
        raise ProbeAbort(f"markPrice {m}")
    return m


def probe_qty(mark: Decimal, sr: SymbolRules) -> Decimal:
    return max(ceil_to_step(sr.min_notional * NOTIONAL_HEADROOM / mark, sr.market_step),
               ceil_to_step(sr.market_min_qty, sr.market_step))


# ── 판정(설계서 §11) ──────────────────────────────────────────────────────────
def evaluate_leg(direction: Direction, row: dict, trades: list, rules: RuntimeRules, *, gate_leverage: int) -> dict:
    with decimal.localcontext() as ctx:
        ctx.prec = DECIMAL_PREC
        out: dict[str, Any] = {"A": None, "B": None, "verdict": "INCONCLUSIVE", "notes": []}
        notes: list[str] = out["notes"]
        q = abs(Decimal(str(row["positionAmt"])))
        e = Decimal(str(row["entryPrice"]))
        lev = int(str(row["leverage"]))
        if q == 0 or e <= 0:
            notes.append(f"포지션 없음(positionAmt={row.get('positionAmt')}, entryPrice={row.get('entryPrice')})")
            return out
        if not trades:
            notes.append(f"userTrades {TRADES_RETRIES}회 조회에도 비어 있음")
            return out
        assets = {str(t.get("commissionAsset")) for t in trades}
        n = q * e
        tick = rules.symbol_rules.tick_size
        tol = q * tick / Decimal(lev) + DISPLAY_ROUNDING
        out.update(Q=str(q), E=str(e), N=str(n), L=lev, tol=str(tol), commission_assets=sorted(assets))
        if assets != {"USDT"}:
            notes.append(f"commissionAsset {sorted(assets)} ≠ USDT")
            return out
        c = sum((Decimal(str(t["commission"])) for t in trades), Decimal(0))
        wallet = Decimal(str(row["isolatedWallet"]))
        w_fee, w_nofee = n / Decimal(lev) - c, n / Decimal(lev)
        out.update(C=str(c), isolatedWallet=str(wallet), W_fee=str(w_fee), W_nofee=str(w_nofee),
                   wallet_minus_W_fee=str(wallet - w_fee), wallet_minus_W_nofee=str(wallet - w_nofee))
        if "isolatedMargin" in row and "unRealizedProfit" in row:
            out["isolatedMargin_minus_wallet_minus_uPnL"] = str(
                Decimal(str(row["isolatedMargin"])) - wallet - Decimal(str(row["unRealizedProfit"])))

        near_fee, near_nofee = abs(wallet - w_fee) <= tol, abs(wallet - w_nofee) <= tol
        out["A"] = "FEE" if near_fee and not near_nofee else "NO_FEE" if near_nofee and not near_fee else "A_NEITHER"

        try:
            liq = Decimal(str(row["liquidationPrice"]))
            if liq > 0:
                est_fee = liquidation_estimate(direction, e, n, lev, rules, taker=c / n)
                est_nofee = liquidation_estimate(direction, e, n, lev, rules, taker=Decimal(0))
                t_fee = (abs(liq - est_fee.price) / tick).to_integral_value(rounding=decimal.ROUND_HALF_UP)
                t_nofee = (abs(liq - est_nofee.price) / tick).to_integral_value(rounding=decimal.ROUND_HALF_UP)
                out.update(liquidationPrice=str(liq), liq_fee_model=str(est_fee.price),
                           liq_nofee_model=str(est_nofee.price), ticks_fee=str(t_fee), ticks_nofee=str(t_nofee))
                out["B"] = "tie" if t_fee == t_nofee else ("fee" if t_fee < t_nofee else "no_fee")
            else:
                notes.append(f"liquidationPrice {liq} ≤ 0 — B 계산 불가")
        except (RulesError, InvalidOperation, KeyError, ZeroDivisionError) as ex:
            notes.append(f"B 계산 불가: {type(ex).__name__}: {ex}")

        if lev != gate_leverage:
            notes.append(f"행 leverage {lev} ≠ 게이트 응답 {gate_leverage}")
            return out
        if not c > 2 * tol:
            notes.append(f"C {c} ≤ 2×tol {2 * tol} — 두 모델 구별 불가")
            return out
        if out["A"] == "FEE" and out["B"] in ("fee", "tie"):
            out["verdict"] = "FEE"
        elif out["A"] == "NO_FEE" and out["B"] in ("no_fee", "tie"):
            out["verdict"] = "NO_FEE"
        return out


def overall_verdict(legs: list[dict]) -> str:
    v = [leg.get("verdict") for leg in legs]
    if len(v) == 2 and all(x == "FEE" for x in v):
        return "CONFIRMED_FEE"
    if len(v) == 2 and all(x == "NO_FEE" for x in v):
        return "CONFIRMED_NO_FEE"
    return "INCONCLUSIVE"


# ── 실행 ─────────────────────────────────────────────────────────────────────
def close_all(client: RestClient, rules: RuntimeRules, *, sleep: Callable[[float], Any]) -> list:
    """재조회 → 0이 아니면 reduceOnly 전량 청산 → 다음 시도에서 재조회. 최대 `CLOSE_ATTEMPTS`회, 끝에 마지막 재조회.
    🔴 Codex 검토 Q3: 첫 조회 실패·청산 POST 전송 실패도 재시도한다. 끝내 flat을 확인 못 하면 `CloseFailed`."""
    sent: list = []
    last: Any = "조회 전"
    for _ in range(CLOSE_ATTEMPTS):
        try:
            row = _both_row(client.get(POSITION_V2, {"symbol": SYMBOL}, signed=True).data)
            last = row
            amt = Decimal(str(row["positionAmt"]))
            if amt == 0:
                return sent
            for p in close_position_orders(amt, rules.symbol_rules):
                sent.append(client.post(ORDER, p).data)
        except (BinanceAPIError, TransportError, RulesError, ValueError, KeyError, InvalidOperation) as e:
            last = f"{type(e).__name__}: {e}"
        sleep(CLOSE_RETRY_SEC)
    try:
        row = _both_row(client.get(POSITION_V2, {"symbol": SYMBOL}, signed=True).data)
        if Decimal(str(row["positionAmt"])) == 0:
            return sent
        last = row
    except (BinanceAPIError, TransportError, ValueError, KeyError, InvalidOperation) as e:
        last = f"{type(e).__name__}: {e}"
    raise CloseFailed(f"{CLOSE_ATTEMPTS}회 청산 시도 후에도 flat 확인 실패 — 테스트넷 계정에서 수동 정리 · "
                      f"마지막 positionAmt/행: {last}")


def require_flat(client: RestClient) -> None:
    """🔴 Codex 검토 Q3 추가 결함: 이미 ISOLATED면 기동 게이트가 flat을 보지 않는다 → 첫 주문 **전** 무조건 확인."""
    #  헤지 모드는 LONG·SHORT 두 행(BOTH 없음) — 심볼의 **모든 행**이 0이어야 flat(Codex L3 검토 Q7)
    rows = [r for r in (client.get(POSITION_V2, {"symbol": SYMBOL}, signed=True).data or [])
            if isinstance(r, dict) and r.get("symbol") == SYMBOL]
    if not rows:
        raise ProbeAbort(f"positionRisk에 {SYMBOL} 행이 없다 — flat 확인 불가")
    legs = [f"{r.get('positionSide', 'BOTH')}={r.get('positionAmt')}" for r in rows if Decimal(str(r["positionAmt"])) != 0]
    if legs:
        raise ProbeAbort(f"{SYMBOL} 포지션 보유 중 {legs} — 프로브는 flat 계정에서만")
    if client.get(OPEN_ORDERS, {"symbol": SYMBOL}, signed=True).data:
        raise ProbeAbort(f"{SYMBOL} 미체결 주문 있음 — 프로브는 미체결 0에서만")
    if client.get(ALGO_OPEN_ORDERS, {"symbol": SYMBOL}, signed=True).data:
        raise ProbeAbort(f"{SYMBOL} algo 미체결 있음 — 프로브는 미체결 0에서만")


def run_leg(client: RestClient, rules: RuntimeRules, direction: Direction, *, leverage: int,
            sleep: Callable[[float], Any]) -> dict:
    sr = rules.symbol_rules
    leg: dict[str, Any] = {"direction": direction.value, "closed_flat": False, "A": None, "B": None,
                           "verdict": "INCONCLUSIVE"}
    mark = _mark(client)
    qty = probe_qty(mark, sr)
    orders = entry_orders(direction, qty, mark, sr)
    if len(orders) != 1:
        raise ProbeAbort(f"프로브 수량 {qty}이 MARKET maxQty 분할을 요구한다 — 최소 명목 프로브가 아니다")
    leg.update(mark_before_entry=str(mark), qty=str(qty))
    try:
        order = orders[0] | {"newOrderRespType": "RESULT"}
        validate_order_params(order)
        resp = client.post(ORDER, order).data
        leg["entry_response"] = resp
        if not isinstance(resp, dict) or resp.get("status") != "FILLED" or Decimal(str(resp.get("executedQty"))) != qty:
            raise ValueError(f"진입 응답이 FILLED·executedQty={qty}가 아니다: {resp!r}")
        oid = int(resp["orderId"])
        row = _both_row(client.get(POSITION_V2, {"symbol": SYMBOL}, signed=True).data)
        leg["position_v2"] = row
        if abs(Decimal(str(row["positionAmt"]))) != qty:
            raise ValueError(f"positionRisk positionAmt {row['positionAmt']} ≠ 체결 수량 {qty}")
        try:
            leg["position_v3"] = _both_row(client.get(POSITION_V3, {"symbol": SYMBOL}, signed=True).data)
        except (BinanceAPIError, TransportError, ValueError) as e:
            leg["position_v3"], leg["v3_error"] = None, f"{type(e).__name__}: {e}"
        leg["has_isolated_field"] = {"v2": "isolated" in row,
                                     "v3": None if leg["position_v3"] is None else "isolated" in leg["position_v3"]}
        trades: list = []
        for i in range(TRADES_RETRIES):
            trades = client.get(USER_TRADES, {"symbol": SYMBOL, "orderId": oid}, signed=True).data or []
            if trades:
                break
            if i < TRADES_RETRIES - 1:
                sleep(TRADES_RETRY_SEC)
        leg["trades"] = trades
        trades = [t for t in trades if str(t.get("orderId")) == str(oid) and t.get("symbol", SYMBOL) == SYMBOL]
        if trades and sum((Decimal(str(t["qty"])) for t in trades), Decimal(0)) != qty:
            raise ValueError(f"userTrades(orderId {oid}) 수량 합이 체결 수량 {qty}와 다르다")
        leg.update(evaluate_leg(direction, row, trades, rules, gate_leverage=leverage))
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 청산은 finally에서 반드시 시도하고, 판정 미도달로 기록
        leg["error"] = f"{type(e).__name__}: {e}"
        leg["verdict"] = "INCONCLUSIVE"
    finally:
        leg["close_responses"] = close_all(client, rules, sleep=sleep)
        leg["closed_flat"] = True
    return leg


def utc_iso() -> str:
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}Z"


def run_probe(client: RestClient, *, sleep: Callable[[float], Any] = time.sleep,
              clock: Callable[[], str] = utc_iso) -> dict:
    started = clock()
    rules, _ = load_runtime_rules(client, SYMBOL)
    sr = rules.symbol_rules
    mark = _mark(client)
    qty = probe_qty(mark, sr)
    b = rules.bracket_for_notional(qty * mark)
    if b.initial_leverage < PROBE_LEVERAGE:
        raise ProbeAbort(f"테스트넷 브라켓 {b.bracket} 최대 {b.initial_leverage}x < {PROBE_LEVERAGE}x — "
                         "§11은 L을 자동으로 낮추지 않는다(주문 없이 중단)")
    require_flat(client)
    gate = run_startup_gate(client, rules, Mode.LIVE, leverage=PROBE_LEVERAGE)
    legs = [run_leg(client, rules, d, leverage=PROBE_LEVERAGE, sleep=sleep) for d in (Direction.LONG, Direction.SHORT)]
    return {"started_at_utc": started, "finished_at_utc": clock(), "scope": SCOPE, "rule": RULE_REF,
            "symbol": SYMBOL, "leverage": PROBE_LEVERAGE, "gate_actions": gate.actions,
            "testnet_rules": {"taker": str(rules.commission.taker), "maker": str(rules.commission.maker),
                              "tick_size": str(sr.tick_size), "min_notional": str(sr.min_notional),
                              "bracket": b.bracket, "mmr": str(b.maint_margin_ratio), "cum": str(b.cum)},
            "legs": legs, "verdict": overall_verdict(legs),
            "verdict_reached": all("error" not in leg and leg["closed_flat"] for leg in legs)}


# ── 기록 ─────────────────────────────────────────────────────────────────────
def _leg_summary(leg: dict) -> str:
    keys = ("Q", "E", "N", "L", "C", "isolatedWallet", "W_fee", "W_nofee", "tol", "liquidationPrice",
            "liq_fee_model", "liq_nofee_model", "ticks_fee", "ticks_nofee")
    vals = " · ".join(f"{k} {leg[k]}" for k in keys if k in leg)
    iso = leg.get("has_isolated_field")
    return (f"**{leg['direction']}** {vals} · A={leg.get('A')} · B={leg.get('B')} → **{leg.get('verdict')}**"
            + (f" · 비고 {'; '.join(leg['notes'])}" if leg.get("notes") else "")
            + (f" · `isolated` 필드 v2={iso.get('v2')} v3={iso.get('v3')}" if iso else ""))


def registry_row(result: dict, number: int, *, raw_file: str = "") -> str:
    legs = " / ".join(_leg_summary(leg) for leg in result["legs"])
    tr = result["testnet_rules"]
    cells = [
        str(number), result["started_at_utc"][:10],
        "검증 · 레지스트리 #4 진입 수수료 가정 — **테스트넷 메커니즘**(#6 경로 · 사용자 결정 2026-09-15)",
        "`positionRisk.isolatedWallet` vs `N/L − C`·`N/L`(A) · `liquidationPrice` tick 비교(B)",
        f"{legs} · 호스트 {result.get('base_host', '?')} · 테스트넷 taker {tr['taker']}·브라켓 {tr['bracket']} MMR {tr['mmr']}",
        f"해석 규칙 = {RULE_REF} · {SCOPE}",
        f"**{result['verdict']}**",
        f"실행 `scripts/testnet_fee_probe.py` {result['started_at_utc']} · 원자료 `var/testnet_probe/{raw_file}` · "
        "INCONCLUSIVE면 실계정 최소 명목 프로브(Codex 검토 + 사용자 명시 승인) · CONFIRMED_NO_FEE여도 게이트 변경은 새 행",
    ]
    return "| " + " | ".join(c.replace("|", "/") for c in cells) + " |"


def append_registry(path: Path, result: dict, *, raw_file: str = "") -> int:
    """append-only(파일 끝에 **추가 모드**로 한 행). 판정 미도달 결과는 거부."""
    if result.get("verdict_reached") is not True:
        raise ValueError("판정에 도달하지 않은 실행은 레지스트리에 쓰지 않는다(§11 재실행 규칙)")
    text = path.read_text(encoding="utf-8")
    nums = [int(cell) for line in text.splitlines() if line.startswith("| ")
            for cell in [line.split("|")[1].strip()] if cell.isdigit()]
    n = max(nums, default=0) + 1
    with path.open("a", encoding="utf-8") as fh:
        fh.write(("" if not text or text.endswith("\n") else "\n") + registry_row(result, n, raw_file=raw_file) + "\n")
    return n


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def main(argv: list[str] | None = None, *, env: dict[str, str] | None = None,
         client_factory: Callable[..., RestClient] | None = None, sleep: Callable[[float], Any] = time.sleep) -> int:
    ap = argparse.ArgumentParser(description="테스트넷 수수료 가정 프로브(설계서 §11)")
    ap.add_argument("--no-registry", action="store_true", help="레지스트리에 쓰지 않고 JSON만 남긴다")
    a = ap.parse_args(argv)
    env = load_env(ROOT / ".env") if env is None else env
    base = env.get("BINANCE_TESTNET_BASE_URL", "")
    key, secret = env.get("BINANCE_TESTNET_API_KEY", ""), env.get("BINANCE_TESTNET_API_SECRET", "")
    if not (base and key and secret):
        print("🚫 .env에 BINANCE_TESTNET_BASE_URL · BINANCE_TESTNET_API_KEY · BINANCE_TESTNET_API_SECRET이 모두 있어야 한다"
              " (테스트넷 키는 테스트넷 사이트에서 발급 · 메인넷 키로 대체하지 않는다)", file=sys.stderr)
        return 2
    try:
        require_testnet(base)
    except NotTestnet as e:
        print(f"🚫 {e}", file=sys.stderr)
        return 2
    if key == env.get("BINANCE_API_KEY") or secret == env.get("BINANCE_API_SECRET"):
        print("🚫 테스트넷 키가 메인넷 키(BINANCE_API_KEY/SECRET)와 같다 — 거부", file=sys.stderr)
        return 2

    client = (client_factory or make_client)(base, key, secret)
    if isinstance(client, BinanceRestClient) and client.time_sync is not None:
        client.time_sync.measure(client, _wall_ms)
    try:
        result = run_probe(client, sleep=sleep)
    except (ProbeAbort, StartupAbort) as e:
        print(f"⛔ 주문 전 중단: {e}", file=sys.stderr)
        return 4
    except CloseFailed as e:
        print(f"🚨 {e}", file=sys.stderr)
        return 3
    result["base_host"] = urllib.parse.urlsplit(base).hostname
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = OUT_DIR / f"{result['started_at_utc'].replace(':', '').replace('.', '_')}.json"
    raw.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"], "verdict_reached": result["verdict_reached"],
                      "legs": [{k: leg.get(k) for k in ("direction", "A", "B", "verdict", "notes", "error")}
                               for leg in result["legs"]], "raw": str(raw)}, ensure_ascii=False, indent=1))
    if not result["verdict_reached"]:
        print("⚠️ 운영 실패로 판정 미도달 — 시도로만 기록(§11 재실행 규칙) · 레지스트리에 쓰지 않음", file=sys.stderr)
        return 5
    if not a.no_registry:
        n = append_registry(REGISTRY, result, raw_file=raw.name)
        print(f"레지스트리 #{n} 기록")
    return 0


if __name__ == "__main__":
    sys.exit(main())
