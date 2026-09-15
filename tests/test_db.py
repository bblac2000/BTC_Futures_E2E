"""layer 4 `db/` — 버전 마이그레이션 SQLite + layer 3 이벤트 → 행 (strategy-modules §5 · 설계서 §3).

- 스키마 변경은 **마이그레이션 단계로만**(append-only). 적용된 단계의 SQL이 코드에서 바뀌면(체크섬 불일치) 거부 ·
  DB가 코드보다 새 버전이면 거부 · 단계는 한 트랜잭션(실패 시 부분 적용 없음)
- v1 = strategy-modules §5 테이블 전부 + `exchange/store.py`의 `runtime_rules` DDL 흡수(기존 DB 행 보존)
- 모든 테이블에 `mode`(paper|live) CHECK · 가격·수량은 **TEXT Decimal 원문**(float 금지)
- 피처는 `(name, params_version)`으로 추적 — 같은 이름·버전에 다른 정의를 덮어쓰지 않는다
- "판단 시점에 봇이 본 값": `SizingDecision`·`PostFillCheck`·`LiquidationCheck`·`Fill`·`PositionClosed`·펀딩 이벤트의
  **모든 필드에 열이 있다**(열이 없는 필드 = 복기에서 사라지는 값)
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
from decimal import Decimal

import pytest

from db import migrate as M
from db import record as R
from db.schema import MIGRATIONS
from exchange import store
from exchange.gate import Mode
from exchange.loader_types import RawFetch
from exchange.orders import Direction, Side
from paper.engine import Engine, EntryIntent
from paper.sender import PaperSender
from paper.types import (
    EntriesBlocked,
    EntryFilled,
    EntrySkipped,
    ExitReason,
    Fill,
    FundingMissed,
    FundingSettled,
    MarkTick,
    PositionClosed,
    PostFillCheck,
    SkipReason,
)
from sizing.config import RegimeSizing, SizingLimits
from sizing.position import LiquidationCheck, SizingDecision

D = Decimal
DAY0 = 1_789_430_400_000
H = 3_600_000

V1_TABLES = {"bars_1m", "features_base", "features_adv", "features_custom", "feature_definitions", "decisions",
             "orders", "positions", "funding_events", "account_snapshots", "runtime_rules", "engine_events"}


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    M.migrate(c)
    yield c
    c.close()


def tables(c) -> set[str]:
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")} - {"sqlite_sequence"}


def columns(c, table) -> set[str]:
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


# ── 마이그레이션 ─────────────────────────────────────────────────────────────
def test_fresh_database_migrates_to_the_latest_version_with_every_section_5_table(con):
    assert M.current_version(con) == MIGRATIONS[-1].version == 1
    assert tables(con) == V1_TABLES | {"schema_version"}
    (row,) = con.execute("SELECT version, name, sql_sha256 FROM schema_version").fetchall()
    assert row[0] == 1 and row[2] == MIGRATIONS[0].sha256


def test_migrate_is_idempotent(con):
    assert M.migrate(con) == []
    assert con.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1


def test_steps_are_numbered_contiguously_from_one():
    assert [m.version for m in MIGRATIONS] == list(range(1, len(MIGRATIONS) + 1))


def test_an_applied_step_whose_sql_changed_is_refused(con):
    """🔴 append-only: 적용된 단계를 고치면 기존 DB와 새 DB의 스키마가 갈라진다 — 새 단계를 추가해야 한다."""
    con.execute("UPDATE schema_version SET sql_sha256='edited' WHERE version=1")
    con.commit()
    with pytest.raises(M.SchemaError, match="체크섬"):
        M.migrate(con)


def test_database_newer_than_the_code_is_refused(con):
    con.execute("INSERT INTO schema_version(version, name, sql_sha256, applied_at_utc) VALUES (99, 'future', 'x', 'now')")
    con.commit()
    with pytest.raises(M.SchemaError, match="99"):
        M.migrate(con)


def test_a_failing_step_leaves_no_partial_schema(monkeypatch):
    c = sqlite3.connect(":memory:")
    bad = M.Migration(1, "broken", "CREATE TABLE half_done(x INTEGER);\nCREATE TABLE oops(;")
    monkeypatch.setattr(M, "MIGRATIONS", (bad,))
    with pytest.raises(sqlite3.Error):
        M.migrate(c)
    assert "half_done" not in tables(c) and M.current_version(c) == 0


def test_target_version_stops_early_and_downgrade_is_refused(con):
    c = sqlite3.connect(":memory:")
    assert M.migrate(c, target=0) == [] and M.current_version(c) == 0
    with pytest.raises(M.SchemaError):
        M.migrate(con, target=0)


def test_legacy_runtime_rules_database_is_absorbed_with_rows_intact():
    """layer 1이 만든 DB(`store.py` 옛 DDL, schema_version 없음) → v1 적용 후 행 보존·같은 열."""
    c = sqlite3.connect(":memory:")
    c.executescript(M.LEGACY_RUNTIME_RULES_DDL)
    c.execute("INSERT INTO runtime_rules(load_id,endpoint,path,symbol,mode,source,fetched_at_utc,payload_json,payload_sha256)"
              " VALUES('L','commissionRate','/fapi/v1/commissionRate','BTCUSDT','paper','rest','2026-09-15T00:00:00Z','{}','h')")
    with pytest.raises(M.SchemaError, match="트랜잭션"):
        M.migrate(c)                                                  # 호출자 작업을 대신 커밋하지 않는다
    c.commit()
    M.migrate(c)
    assert M.current_version(c) == 1 and c.execute("SELECT load_id FROM runtime_rules").fetchall() == [("L",)]


def test_store_goes_through_the_migration_tool_not_its_own_ddl():
    c = sqlite3.connect(":memory:")
    fetch = RawFetch("commissionRate", "/fapi/v1/commissionRate", "BTCUSDT", "2026-09-15T00:00:00Z", {"a": 1})
    store.persist_fetches(c, [fetch], mode="paper", source="rest")
    assert M.current_version(c) == MIGRATIONS[-1].version
    assert not hasattr(store, "DDL"), "runtime_rules DDL은 db/schema.py v1로 흡수됐다"


def test_cli_status_reports_the_version(tmp_path, capsys):
    db = tmp_path / "bot.sqlite"
    assert M.main([str(db)]) == 0
    assert M.main([str(db), "--status"]) == 0
    assert "version 1" in capsys.readouterr().out


# ── 스키마 규칙 ──────────────────────────────────────────────────────────────
def test_every_table_has_a_mode_column_that_rejects_other_values(con):
    for t in V1_TABLES - {"feature_definitions"}:
        assert "mode" in columns(con, t), t
        sql = con.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
        assert "CHECK (mode IN ('paper','live'))" in sql, t


def _fields(cls) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


def test_every_decision_value_the_bot_saw_has_a_column(con):
    """🔴 필드에 열이 없으면 복기에서 그 값이 사라진다 — 새 필드를 추가하면 마이그레이션 단계가 필요하다."""
    assert _fields(SizingDecision) <= columns(con, "decisions")
    assert {"ts_ms", "outcome", "skip_reason", "tp", "decision_json"} <= columns(con, "decisions")


def test_every_fill_post_fill_and_close_value_has_a_column(con):
    assert _fields(Fill) - {"raw"} <= columns(con, "orders")
    assert {"request_json", "response_json", "slippage_vs_mark_bps", "error_code", "error_msg", "intent"} <= columns(con, "orders")
    assert {"pf_" + f for f in _fields(PostFillCheck) - {"liquidation_check"}} <= columns(con, "positions")
    assert {"lc_" + f for f in _fields(LiquidationCheck)} <= columns(con, "positions")
    assert _fields(PositionClosed) - {"fills", "ts_ms"} <= columns(con, "positions")
    assert _fields(FundingSettled) <= columns(con, "funding_events")


# ── 이벤트 기록 (실제 엔진 실행에서 나온 이벤트) ──────────────────────────────────
def run_engine(rules, *, mark="60000", sl=None, tp=None):
    e = Engine(rules, PaperSender(rules), mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    m = D(mark)
    e.request_entry(EntryIntent(Direction.LONG, D(sl) if sl else m * D("0.995"), D(tp) if tp else None,
                                RegimeSizing("trend", D("0.01"), 50, 100), DAY0, m))
    return e, e.on_tick(MarkTick(DAY0 + 1000, m, D("0.0001"), DAY0 + 8 * H))


def test_entry_filled_writes_decision_orders_and_an_open_position_with_exact_decimals(con, rules):
    e, ev = run_engine(rules, tp="60600")
    (fill,) = [x for x in ev if isinstance(x, EntryFilled)]
    R.record_events(con, ev, mode="paper", symbol="BTCUSDT", tp=D("60600"))
    (dec,) = con.execute("SELECT outcome, qty, leverage, entry, sl, tp, chunks, mode, regime FROM decisions").fetchall()
    d = fill.decision
    assert dec == ("entered", str(d.qty), d.leverage, str(d.entry), str(d.sl), "60600",
                   json.dumps([str(c) for c in d.chunks]), "paper", "trend")
    assert D(dec[1]) == d.qty                                         # TEXT → Decimal 정확 복원
    orders = con.execute("SELECT side, qty, price, reduce_only, intent, ref_mark, slippage_vs_mark_bps, commission,"
                         " request_json FROM orders ORDER BY id").fetchall()
    assert len(orders) == len(fill.fills)
    f0 = fill.fills[0]
    assert orders[0][:6] == ("BUY", str(f0.qty), str(f0.price), 0, "entry", "60000")
    assert D(orders[0][6]) == (f0.price - D("60000")) / D("60000") * 10_000 and D(orders[0][6]) > 0   # 불리 = 양수
    assert D(orders[0][7]) == f0.commission and '"side": "BUY"' in orders[0][8]
    (pos,) = con.execute("SELECT event, direction, qty, entry_price, leverage, pf_gate_ok, pf_liq_price_est, lc_status,"
                         " position_id, id FROM positions").fetchall()
    assert pos[:6] == ("open", "LONG", str(fill.post_fill.qty), str(fill.post_fill.entry_price), fill.leverage, 1)
    assert pos[6] == str(fill.post_fill.liq_price_est) and pos[7] is None and pos[8] == pos[9]


def test_skipped_entry_records_the_skip_and_the_sizing_reject_reason(con, rules):
    _, ev = run_engine(rules, sl="58800")                             # #5 불가 → SIZING_REJECTED
    (skip,) = [x for x in ev if isinstance(x, EntrySkipped)]
    assert skip.reason is SkipReason.SIZING_REJECTED and skip.decision is not None and skip.decision.reason is not None
    R.record_events(con, ev, mode="paper", symbol="BTCUSDT")
    (row,) = con.execute("SELECT outcome, skip_reason, reason, ok, qty, detail FROM decisions").fetchall()
    assert row[:4] == ("skipped", "sizing_rejected", skip.decision.reason.value, 0) and row[5]


def test_skip_without_a_decision_still_writes_a_row(con):
    R.record_events(con, [EntrySkipped(DAY0, None, SkipReason.SL_CROSSED_BEFORE_FILL, "mark 1 · SL 2")],
                    mode="live", symbol="BTCUSDT")
    assert con.execute("SELECT outcome, skip_reason, qty, mode FROM decisions").fetchall() == [
        ("skipped", "sl_crossed_before_fill", None, "live")]


def test_close_writes_exit_orders_and_a_close_row_linked_to_the_open_position(con, rules):
    e, ev = run_engine(rules)
    R.record_events(con, ev, mode="paper", symbol="BTCUSDT")
    ev2 = e.close_now(ref_mark=D("60100"), ts_ms=DAY0 + 5000)
    (closed,) = [x for x in ev2 if isinstance(x, PositionClosed)]
    R.record_events(con, ev2, mode="paper", symbol="BTCUSDT")
    open_id = con.execute("SELECT id FROM positions WHERE event='open'").fetchone()[0]
    (row,) = con.execute("SELECT event, reason, position_id, realized_pnl_usdt, exit_price, wallet_after, funding_paid_usdt"
                         " FROM positions WHERE event='close'").fetchall()
    assert row == ("close", "manual", open_id, str(closed.realized_pnl_usdt), str(closed.exit_price),
                   str(closed.wallet_after), str(closed.funding_paid_usdt))
    exits = con.execute("SELECT side, reduce_only, intent, exit_reason FROM orders WHERE intent='exit'").fetchall()
    assert exits and all(x == ("SELL", 1, "exit", "manual") for x in exits)
    assert R.open_position_id(con, mode="paper", symbol="BTCUSDT") is None


def test_liquidation_close_has_no_orders_and_an_orphan_close_is_recorded_not_dropped(con):
    ev = PositionClosed(DAY0, Direction.SHORT, ExitReason.LIQUIDATION, D("0.010"), D("60000"), None, (), D("-12.5"),
                        D("0"), D("0.1"), D("987.5"))
    R.record_events(con, [ev], mode="live", symbol="BTCUSDT")         # 채택 포지션처럼 open 행이 없다
    assert con.execute("SELECT event, reason, position_id, exit_price, direction, detail FROM positions").fetchall() == [
        ("close", "liquidation", None, None, "SHORT", "open 행 없음(채택·기록 전 포지션)")]
    assert con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_funding_settled_and_missed_and_other_events(con):
    R.record_events(con, [
        FundingSettled(DAY0 + 8 * H, D("0.0001"), D("60000"), D("0.010"), D("0.06"), D("999.94")),
        FundingMissed(DAY0 + 16 * H, (DAY0 + 8 * H, DAY0 + 16 * H), D("-0.010")),
        EntriesBlocked(DAY0, "positionRisk 실패"),
    ], mode="paper", symbol="BTCUSDT")
    assert con.execute("SELECT ts_ms, rate, paid_usdt, missed, boundaries_json FROM funding_events ORDER BY id").fetchall() == [
        (DAY0 + 8 * H, "0.0001", "0.06", 0, None), (DAY0 + 16 * H, None, None, 1, f"[{DAY0 + 8 * H}, {DAY0 + 16 * H}]")]
    assert con.execute("SELECT kind, detail FROM engine_events").fetchall() == [("EntriesBlocked", "positionRisk 실패")]


def test_unknown_event_types_and_bad_modes_are_refused(con):
    with pytest.raises(TypeError):
        R.record_events(con, [object()], mode="paper", symbol="BTCUSDT")
    with pytest.raises(ValueError):
        R.record_events(con, [], mode="demo", symbol="BTCUSDT")


def test_events_of_one_call_are_one_transaction(con, rules):
    _, ev = run_engine(rules)
    with pytest.raises(TypeError):
        R.record_events(con, [*ev, object()], mode="paper", symbol="BTCUSDT")
    assert con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


def test_floats_are_refused_for_decimal_columns(con):
    ev = FundingSettled(DAY0, 0.0001, D("60000"), D("0.01"), D("0.06"), D("999.94"))   # type: ignore[arg-type]
    with pytest.raises(TypeError):
        R.record_events(con, [ev], mode="paper", symbol="BTCUSDT")


# ── 봉 · 피처 ────────────────────────────────────────────────────────────────
def bar(**kw):
    base = R.BarRow(open_ms=DAY0, close_ms=DAY0 + 59_999, open=D("60000.1"), high=D("60010.0"), low=D("59990.0"),
                    close=D("60000.5"), volume=D("1.234"), quote_volume=D("74000.1"), trades=42,
                    taker_buy_base=D("0.6"), taker_buy_quote=D("36000.2"))
    return dataclasses.replace(base, **kw)


def test_bars_insert_once_duplicates_are_ignored_and_conflicts_are_reported(con):
    assert R.record_bar(con, bar(), mode="paper", symbol="BTCUSDT", source="ws") == "inserted"
    assert R.record_bar(con, bar(), mode="paper", symbol="BTCUSDT", source="rest") == "duplicate"
    assert R.record_bar(con, bar(close=D("1")), mode="paper", symbol="BTCUSDT", source="rest") == "conflict"
    assert con.execute("SELECT close, source, is_closed FROM bars_1m").fetchall() == [("60000.5", "ws", 1)]


def test_feature_definitions_never_change_under_the_same_name_and_version(con):
    R.register_feature(con, "atr_1m", 1, "features_base", {"period": 14})
    R.register_feature(con, "atr_1m", 1, "features_base", {"period": 14})           # 같은 정의 재등록은 허용
    with pytest.raises(R.FeatureDefinitionConflict):
        R.register_feature(con, "atr_1m", 1, "features_base", {"period": 20})       # 바꾸려면 버전을 올린다
    R.register_feature(con, "atr_1m", 2, "features_base", {"period": 20})
    R.record_features(con, "features_base", DAY0, {("atr_1m", 1): D("35.2"), ("atr_1m", 2): D("33.9")},
                      mode="paper", symbol="BTCUSDT")
    assert sorted(con.execute("SELECT name, params_version, value FROM features_base").fetchall()) == [
        ("atr_1m", 1, "35.2"), ("atr_1m", 2, "33.9")]
    with pytest.raises(R.FeatureDefinitionConflict):
        R.record_features(con, "features_base", DAY0, {("rsi_1m", 1): D("50")}, mode="paper", symbol="BTCUSDT")


def test_custom_features_are_json_with_a_schema_version(con):
    R.record_custom_features(con, DAY0, {"sr_levels": ["60000.0"]}, schema_version=1, mode="paper", symbol="BTCUSDT")
    assert con.execute("SELECT schema_version, payload_json FROM features_custom").fetchall() == [
        (1, '{"sr_levels": ["60000.0"]}')]


def test_side_values_are_constrained(con):
    f = Fill("x", Side.BUY, D("0.01"), D("60000"), D("0.3"), False, DAY0, D("60000"))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO orders(mode, symbol, ts_ms, intent, order_id, side, qty, price, commission, reduce_only)"
                    " VALUES ('paper','BTCUSDT',1,'entry','x','LONG','1','1','0',0)")
    assert f.side.value in ("BUY", "SELL")
