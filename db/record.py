"""layer 3 이벤트 → layer 4 행. **판단 시점에 봇이 본 값**을 그대로 쓴다(사후 재계산 없음 · strategy-modules §5).

| 이벤트 | 행 |
|---|---|
| `EntryFilled` | `decisions`(entered · SizingDecision 전 필드) + `positions` open(PostFillCheck `pf_*` · LiquidationCheck `lc_*`) + `orders` 체결마다 |
| `EntrySkipped` | `decisions`(skipped · skip_reason · 결정이 있으면 전 필드) |
| `PositionClosed` | `orders` 청산 체결마다 + `positions` close(열린 open 행에 연결 · 없으면 NULL + 사유) |
| `FundingSettled`·`FundingMissed` | `funding_events` |
| `EntriesBlocked`·`ExitFailed`·`LiquidationThresholdCrossed` | `engine_events` |

- 한 번의 `record_events` = 한 트랜잭션(모르는 이벤트가 섞이면 전부 롤백).
- Decimal은 `str()` 원문 · float가 오면 `TypeError`(정밀도 손실을 조용히 저장하지 않는다).
- 스키마는 여기서 만들지 않는다 — `db.migrate`만.
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from collections.abc import Iterable, Mapping
from decimal import Decimal
from enum import Enum
from typing import Any

from exchange.orders import Side
from paper.types import (
    EntriesBlocked,
    EntryFilled,
    EntrySkipped,
    ExitFailed,
    Fill,
    FundingMissed,
    FundingSettled,
    LiquidationThresholdCrossed,
    PositionClosed,
)
from sizing.position import SizingDecision

MODES = ("paper", "live")
FEATURE_TABLES = ("features_base", "features_adv")
ORPHAN_CLOSE = "open 행 없음(채택·기록 전 포지션)"


class FeatureDefinitionConflict(ValueError):
    """같은 (name, params_version)에 다른 정의 · 등록 안 된 피처 · 다른 테이블 — 덮어쓰지 않는다."""


@dataclasses.dataclass(frozen=True)
class BarRow:
    open_ms: int
    close_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int
    taker_buy_base: Decimal
    taker_buy_quote: Decimal
    mark_close: Decimal | None = None
    index_close: Decimal | None = None
    funding_rate: Decimal | None = None
    is_closed: bool = True


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"mode={mode!r} — {MODES} 중 하나")
    return mode


def _v(x: Any) -> Any:
    """열 값 — Decimal → 원문 · Enum → value · bool → 0/1 · float 거부."""
    if x is None:
        return None
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, float):
        raise TypeError(f"float 값 {x!r} — Decimal만 기록한다")
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, Enum):
        return x.value
    return x


def _json(x: Any) -> str | None:
    if x is None:
        return None

    def default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, Enum):
            return o.value
        if isinstance(o, float):
            raise TypeError(f"float 값 {o!r} — Decimal만 기록한다")
        return str(o)
    return json.dumps(x, ensure_ascii=False, sort_keys=True, default=default)


def _insert(con: sqlite3.Connection, table: str, row: Mapping[str, Any]) -> int:
    cols = list(row)
    cur = con.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      [row[c] for c in cols])
    return int(cur.lastrowid or 0)


def _decision_cols(d: SizingDecision | None) -> dict[str, Any]:
    if d is None:
        return {}
    out = {f.name: _v(getattr(d, f.name)) for f in dataclasses.fields(d) if f.name != "chunks"}
    out["chunks"] = json.dumps([str(c) for c in d.chunks])
    out["decision_json"] = _json(dataclasses.asdict(d))
    return out


def _slippage_bps(f: Fill) -> Decimal | None:
    if f.ref_mark is None or f.ref_mark == 0:
        return None
    diff = f.price - f.ref_mark if f.side is Side.BUY else f.ref_mark - f.price
    return diff / f.ref_mark * 10_000


def _order(con: sqlite3.Connection, f: Fill, *, mode: str, symbol: str, position_id: int | None, intent: str,
           exit_reason: Any = None) -> None:
    raw = dict(f.raw or {})
    request = raw.pop("params", None)
    response = raw.pop("response", None)
    _insert(con, "orders", {
        "mode": mode, "symbol": symbol, "ts_ms": f.ts_ms, "position_id": position_id, "intent": intent,
        "exit_reason": _v(exit_reason), "order_id": f.order_id, "side": _v(f.side), "qty": _v(f.qty),
        "price": _v(f.price), "commission": _v(f.commission), "commission_estimated": _v(f.commission_estimated),
        "reduce_only": _v(f.reduce_only), "ref_mark": _v(f.ref_mark), "slippage_vs_mark_bps": _v(_slippage_bps(f)),
        "status": "filled", "request_json": _json(request),
        "response_json": _json(response if response is not None else (raw or None)),
    })


def open_position_id(con: sqlite3.Connection, *, mode: str, symbol: str) -> int | None:
    """아직 다 닫히지 않은 가장 최근 open 행(부분 청산은 close 수량 합 < open 수량)."""
    for pid, qty in con.execute("SELECT id, qty FROM positions WHERE mode=? AND symbol=? AND event='open' "
                                "ORDER BY id DESC", (mode, symbol)):
        closed = sum((Decimal(q) for (q,) in con.execute(
            "SELECT qty FROM positions WHERE event='close' AND position_id=?", (pid,))), Decimal())
        if closed < Decimal(qty):
            return int(pid)
    return None


def _entry_filled(con: sqlite3.Connection, ev: EntryFilled, mode: str, symbol: str, tp: Decimal | None) -> None:
    d, pf = ev.decision, ev.post_fill
    _insert(con, "decisions", {"mode": mode, "symbol": symbol, "ts_ms": ev.ts_ms, "outcome": "entered",
                               "tp": _v(tp)} | _decision_cols(d))
    row: dict[str, Any] = {
        "mode": mode, "symbol": symbol, "ts_ms": ev.ts_ms, "event": "open", "direction": _v(d.direction),
        "qty": _v(pf.qty), "entry_price": _v(pf.entry_price), "leverage": ev.leverage, "sl": _v(d.sl), "tp": _v(tp),
        "liq_price_est": _v(pf.liq_price_est),
        "entry_commission_usdt": _v(sum((f.commission for f in ev.fills), Decimal())),
    }
    row |= {f"pf_{f.name}": _v(getattr(pf, f.name)) for f in dataclasses.fields(pf) if f.name != "liquidation_check"}
    lc = pf.liquidation_check
    if lc is not None:
        row |= {f"lc_{f.name}": _v(getattr(lc, f.name)) for f in dataclasses.fields(lc)}
    pid = _insert(con, "positions", row)
    con.execute("UPDATE positions SET position_id=? WHERE id=?", (pid, pid))
    for f in ev.fills:
        _order(con, f, mode=mode, symbol=symbol, position_id=pid, intent="entry")


def _entry_skipped(con: sqlite3.Connection, ev: EntrySkipped, mode: str, symbol: str, tp: Decimal | None) -> None:
    _insert(con, "decisions", {"mode": mode, "symbol": symbol, "ts_ms": ev.ts_ms, "outcome": "skipped",
                               "skip_reason": _v(ev.reason), "tp": _v(tp)} | _decision_cols(ev.decision)
            | {"detail": ev.detail})


def _position_closed(con: sqlite3.Connection, ev: PositionClosed, mode: str, symbol: str) -> None:
    pid = open_position_id(con, mode=mode, symbol=symbol)
    for f in ev.fills:
        _order(con, f, mode=mode, symbol=symbol, position_id=pid, intent="exit", exit_reason=ev.reason)
    _insert(con, "positions", {
        "mode": mode, "symbol": symbol, "ts_ms": ev.ts_ms, "event": "close", "position_id": pid,
        "direction": _v(ev.direction), "reason": _v(ev.reason), "qty": _v(ev.qty), "entry_price": _v(ev.entry_price),
        "exit_price": _v(ev.exit_price), "realized_pnl_usdt": _v(ev.realized_pnl_usdt),
        "exit_commission_usdt": _v(ev.exit_commission_usdt), "funding_paid_usdt": _v(ev.funding_paid_usdt),
        "wallet_after": _v(ev.wallet_after), "detail": None if pid is not None else ORPHAN_CLOSE,
    })


def record_events(con: sqlite3.Connection, events: Iterable[object], *, mode: str, symbol: str,
                  tp: Decimal | None = None) -> None:
    mode = _mode(mode)
    with con:
        for ev in events:
            if isinstance(ev, EntryFilled):
                _entry_filled(con, ev, mode, symbol, tp)
            elif isinstance(ev, EntrySkipped):
                _entry_skipped(con, ev, mode, symbol, tp)
            elif isinstance(ev, PositionClosed):
                _position_closed(con, ev, mode, symbol)
            elif isinstance(ev, FundingSettled):
                _insert(con, "funding_events", {
                    "mode": mode, "symbol": symbol, "ts_ms": ev.ts_ms, "rate": _v(ev.rate), "mark": _v(ev.mark),
                    "signed_qty": _v(ev.signed_qty), "paid_usdt": _v(ev.paid_usdt), "wallet_after": _v(ev.wallet_after),
                    "missed": 0})
            elif isinstance(ev, FundingMissed):
                _insert(con, "funding_events", {
                    "mode": mode, "symbol": symbol, "ts_ms": ev.ts_ms, "signed_qty": _v(ev.signed_qty), "missed": 1,
                    "boundaries_json": json.dumps(list(ev.boundaries_ms))})
            elif isinstance(ev, EntriesBlocked | ExitFailed | LiquidationThresholdCrossed):
                detail = getattr(ev, "detail", None) or str(_v(getattr(ev, "reason", "")))
                _insert(con, "engine_events", {"mode": mode, "symbol": symbol, "ts_ms": ev.ts_ms,
                                               "kind": type(ev).__name__, "detail": detail,
                                               "payload_json": _json(dataclasses.asdict(ev))})
            else:
                raise TypeError(f"기록할 수 없는 이벤트 {type(ev).__name__}")


def record_bar(con: sqlite3.Connection, bar: BarRow, *, mode: str, symbol: str, source: str) -> str:
    """'inserted' · 'duplicate'(같은 값) · 'conflict'(같은 봉에 다른 값 — 덮어쓰지 않는다, 호출자가 알린다)."""
    mode = _mode(mode)
    vals = {"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume,
            "quote_volume": bar.quote_volume, "trades": bar.trades, "taker_buy_base": bar.taker_buy_base,
            "taker_buy_quote": bar.taker_buy_quote, "close_time_ms": bar.close_ms}
    with con:
        existing = con.execute(f"SELECT {','.join(vals)} FROM bars_1m WHERE mode=? AND symbol=? AND open_time_ms=?",
                               (mode, symbol, bar.open_ms)).fetchone()
        if existing is not None:
            return "duplicate" if tuple(existing) == tuple(_v(v) for v in vals.values()) else "conflict"
        _insert(con, "bars_1m", {"mode": mode, "symbol": symbol, "open_time_ms": bar.open_ms}
                | {k: _v(v) for k, v in vals.items()}
                | {"mark_close": _v(bar.mark_close), "index_close": _v(bar.index_close),
                   "funding_rate": _v(bar.funding_rate), "is_closed": _v(bar.is_closed), "source": source,
                   "recorded_at_utc": _utcnow()})
    return "inserted"


def register_feature(con: sqlite3.Connection, name: str, params_version: int, table: str,
                     params: Mapping[str, Any]) -> None:
    if table not in FEATURE_TABLES:
        raise ValueError(f"피처 테이블 {table!r} — {FEATURE_TABLES}")
    params_json = _json(dict(params))
    with con:
        row = con.execute("SELECT table_name, params_json FROM feature_definitions WHERE name=? AND params_version=?",
                          (name, params_version)).fetchone()
        if row is None:
            _insert(con, "feature_definitions", {"name": name, "params_version": params_version, "table_name": table,
                                                 "params_json": params_json, "created_at_utc": _utcnow()})
        elif tuple(row) != (table, params_json):
            raise FeatureDefinitionConflict(f"{name} v{params_version}는 이미 {row[0]} {row[1]}로 정의됐다 — 버전을 올릴 것")


def record_features(con: sqlite3.Connection, table: str, bar_open_ms: int, values: Mapping[tuple[str, int], Decimal | None],
                    *, mode: str, symbol: str) -> None:
    mode = _mode(mode)
    with con:
        for (name, ver), value in values.items():
            row = con.execute("SELECT table_name FROM feature_definitions WHERE name=? AND params_version=?",
                              (name, ver)).fetchone()
            if row is None or row[0] != table:
                raise FeatureDefinitionConflict(f"{name} v{ver}: {table}에 등록된 정의가 없다")
            _insert(con, table, {"mode": mode, "symbol": symbol, "bar_open_ms": bar_open_ms, "name": name,
                                 "params_version": ver, "value": _v(value)})


def record_custom_features(con: sqlite3.Connection, bar_open_ms: int, payload: Mapping[str, Any], *, schema_version: int,
                           mode: str, symbol: str) -> None:
    mode = _mode(mode)
    with con:
        _insert(con, "features_custom", {"mode": mode, "symbol": symbol, "bar_open_ms": bar_open_ms,
                                         "schema_version": schema_version, "payload_json": _json(dict(payload))})
