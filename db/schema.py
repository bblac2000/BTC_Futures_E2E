"""스키마 단계 — **append-only**. 적용된 단계의 SQL을 고치지 않는다(체크섬이 거부한다) · 바꾸려면 새 단계를 붙인다.

v1 (2026-09-15): strategy-modules §5 테이블 전부 + `exchange/store.py`의 `runtime_rules` DDL(글자 그대로 흡수).
규칙: 모든 데이터 테이블에 `mode` CHECK(paper|live) · 가격·수량·비율은 TEXT(Decimal 원문, float 금지) ·
bool은 INTEGER CHECK(0/1) · 시각은 거래소 ms(`*_ms`) 또는 UTC ISO(`*_utc`).
피처는 긴 형식 `(name, params_version, value)` + `feature_definitions` — 같은 이름·버전의 정의는 바꿀 수 없다
(파라미터를 바꾸면 버전을 올린다). 넓은 열 형식은 피처마다 마이그레이션이 필요해 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

MODE = "mode TEXT NOT NULL CHECK (mode IN ('paper','live'))"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


V1 = f"""
CREATE TABLE IF NOT EXISTS runtime_rules(
    id INTEGER PRIMARY KEY,
    load_id TEXT NOT NULL,              -- 한 번의 로드(엔드포인트 묶음)
    endpoint TEXT NOT NULL,             -- exchangeInfo | leverageBracket | ...
    path TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('paper','live')),
    source TEXT NOT NULL,               -- rest | snapshot:<path>
    fetched_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runtime_rules_ep ON runtime_rules(endpoint, symbol, fetched_at_utc);

CREATE TABLE IF NOT EXISTS bars_1m(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    open_time_ms INTEGER NOT NULL,
    close_time_ms INTEGER NOT NULL,
    open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
    volume TEXT NOT NULL, quote_volume TEXT NOT NULL, trades INTEGER NOT NULL,
    taker_buy_base TEXT NOT NULL, taker_buy_quote TEXT NOT NULL,
    mark_close TEXT, index_close TEXT, funding_rate TEXT,
    is_closed INTEGER NOT NULL CHECK (is_closed IN (0,1)),
    source TEXT NOT NULL CHECK (source IN ('ws','rest')),
    recorded_at_utc TEXT NOT NULL,
    UNIQUE(mode, symbol, open_time_ms)
);

CREATE TABLE IF NOT EXISTS feature_definitions(
    name TEXT NOT NULL,
    params_version INTEGER NOT NULL,
    table_name TEXT NOT NULL CHECK (table_name IN ('features_base','features_adv')),
    params_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(name, params_version)
);
CREATE TABLE IF NOT EXISTS features_base(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    bar_open_ms INTEGER NOT NULL,
    name TEXT NOT NULL,
    params_version INTEGER NOT NULL,
    value TEXT,
    UNIQUE(mode, symbol, bar_open_ms, name, params_version)
);
CREATE TABLE IF NOT EXISTS features_adv(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    bar_open_ms INTEGER NOT NULL,
    name TEXT NOT NULL,
    params_version INTEGER NOT NULL,
    value TEXT,
    UNIQUE(mode, symbol, bar_open_ms, name, params_version)
);
CREATE TABLE IF NOT EXISTS features_custom(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    bar_open_ms INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(mode, symbol, bar_open_ms, schema_version)
);

CREATE TABLE IF NOT EXISTS decisions(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('entered','skipped')),
    skip_reason TEXT,
    tp TEXT,
    ok INTEGER CHECK (ok IN (0,1)),
    reason TEXT,                        -- exchange.normalize.RejectReason
    detail TEXT,
    regime TEXT,
    direction TEXT CHECK (direction IN ('LONG','SHORT')),
    entry TEXT, sl TEXT, sl_trigger_basis TEXT, buffer_rel TEXT, min_gap TEXT, sl_dist_pct TEXT,
    risk_budget_usdt TEXT, notional_target TEXT,
    leverage INTEGER, bracket INTEGER, mmr TEXT, cum TEXT, mmr_eff TEXT, taker_rate TEXT,
    liq_dist_pct TEXT, liq_price_est TEXT, liq_tier_basis_notional TEXT,
    notional TEXT, margin TEXT, pos_pct TEXT,
    pos_pct_capped INTEGER CHECK (pos_pct_capped IN (0,1)),
    pos_pct_below_min INTEGER CHECK (pos_pct_below_min IN (0,1)),
    qty TEXT, chunks TEXT,
    loss_at_sl_usdt TEXT, loss_at_liquidation_usdt TEXT, liquidation_fee TEXT,
    decision_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(mode, symbol, ts_ms);

CREATE TABLE IF NOT EXISTS positions(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    event TEXT NOT NULL CHECK (event IN ('open','close')),
    position_id INTEGER,                -- open 행 id(open 행은 자기 자신 · 연결 못 한 close는 NULL)
    direction TEXT NOT NULL CHECK (direction IN ('LONG','SHORT')),
    reason TEXT,                        -- close: paper.types.ExitReason
    qty TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    exit_price TEXT,
    leverage INTEGER,
    sl TEXT, tp TEXT,
    liq_price_exchange TEXT,            -- positionRisk.liquidationPrice(LIVE)
    liq_price_est TEXT,                 -- 자체 계산(#4)
    trail_anchor TEXT,
    entry_commission_usdt TEXT,
    realized_pnl_usdt TEXT, exit_commission_usdt TEXT, funding_paid_usdt TEXT, wallet_after TEXT,
    detail TEXT,
    pf_entry_price TEXT, pf_qty TEXT, pf_notional TEXT, pf_sl_dist_pct TEXT, pf_liq_price_est TEXT, pf_liq_dist_pct TEXT,
    pf_bracket INTEGER,
    pf_gate_ok INTEGER CHECK (pf_gate_ok IN (0,1)),
    pf_sl_before_liquidation INTEGER CHECK (pf_sl_before_liquidation IN (0,1)),
    pf_loss_at_sl_usdt TEXT,
    pf_loss_over_budget INTEGER CHECK (pf_loss_over_budget IN (0,1)),
    lc_status TEXT CHECK (lc_status IN ('OK','CHECK')),
    lc_exchange_dist_pct TEXT, lc_estimate_dist_pct TEXT, lc_estimate_no_fee_dist_pct TEXT,
    lc_gap_vs_fee_pct TEXT, lc_gap_vs_no_fee_pct TEXT,
    lc_closer_model TEXT CHECK (lc_closer_model IN ('fee','no_fee','tie')),
    lc_bracket INTEGER, lc_buffer_rel TEXT, lc_detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_positions_link ON positions(mode, symbol, position_id);

CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    position_id INTEGER,
    intent TEXT NOT NULL CHECK (intent IN ('entry','exit')),
    exit_reason TEXT,
    order_id TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    qty TEXT NOT NULL,
    price TEXT NOT NULL,
    commission TEXT NOT NULL,
    commission_estimated INTEGER NOT NULL DEFAULT 0 CHECK (commission_estimated IN (0,1)),
    reduce_only INTEGER NOT NULL CHECK (reduce_only IN (0,1)),
    ref_mark TEXT,
    slippage_vs_mark_bps TEXT,          -- 불리한 방향 = 양수
    status TEXT NOT NULL DEFAULT 'filled',
    error_code INTEGER,
    error_msg TEXT,
    request_json TEXT,
    response_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_ts ON orders(mode, symbol, ts_ms);

CREATE TABLE IF NOT EXISTS funding_events(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    rate TEXT, mark TEXT, signed_qty TEXT NOT NULL, paid_usdt TEXT, wallet_after TEXT,
    missed INTEGER NOT NULL CHECK (missed IN (0,1)),
    boundaries_json TEXT
);

CREATE TABLE IF NOT EXISTS account_snapshots(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT,
    ts_ms INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('engine','exchange')),
    wallet_balance TEXT, margin_balance TEXT, available_balance TEXT, isolated_margin TEXT, unrealized_pnl TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS engine_events(
    id INTEGER PRIMARY KEY,
    {MODE},
    symbol TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    kind TEXT NOT NULL,                 -- EntriesBlocked | ExitFailed | LiquidationThresholdCrossed
    detail TEXT,
    payload_json TEXT
);
"""

MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "section5_tables_and_runtime_rules", V1),
)
