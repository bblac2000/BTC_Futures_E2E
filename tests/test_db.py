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
V2_TABLES = {"safety_state"}


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
    assert M.current_version(con) == MIGRATIONS[-1].version == 2
    assert tables(con) == V1_TABLES | V2_TABLES | {"schema_version"}
    rows = con.execute("SELECT version, sql_sha256 FROM schema_version ORDER BY version").fetchall()
    assert rows == [(m.version, m.sha256) for m in MIGRATIONS]


def test_migrate_is_idempotent(con):
    assert M.migrate(con) == []
    assert con.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == len(MIGRATIONS)


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
    assert M.current_version(c) == MIGRATIONS[-1].version
    assert c.execute("SELECT load_id FROM runtime_rules").fetchall() == [("L",)]


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
    assert f"version {MIGRATIONS[-1].version}" in capsys.readouterr().out


# ── 스키마 규칙 ──────────────────────────────────────────────────────────────
def test_every_table_has_a_mode_column_that_rejects_other_values(con):
    for t in (V1_TABLES | V2_TABLES) - {"feature_definitions"}:
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
        ("close", "liquidation", None, None, "SHORT", R.ORPHAN_CLOSE)]
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


# ── Codex 재검토(task-mu2l1ukd-e0sy2c) db/ 메모 ────────────────────────────────
def test_nested_floats_in_json_payloads_are_refused(con):
    """#1: `json.dumps(default=)`는 float에 불리지 않는다 — 원시 응답·페이로드 안의 float도 조용히 저장하지 않는다."""
    f = Fill("x", Side.BUY, D("0.01"), D("60000"), D("0.3"), False, DAY0, D("60000"), raw={"response": {"avgPrice": 60000.1}})
    ev = PositionClosed(DAY0, Direction.LONG, ExitReason.MANUAL, D("0.01"), D("60000"), D("60000"), (f,), D("0"), D("0.3"),
                        D("0"), D("999.7"))
    with pytest.raises(TypeError):
        R.record_events(con, [ev], mode="paper", symbol="BTCUSDT")
    with pytest.raises(TypeError):
        R.record_custom_features(con, DAY0, {"x": [1.5]}, schema_version=1, mode="paper", symbol="BTCUSDT")
    assert con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_bar_enrichment_fills_nulls_and_differences_in_any_field_are_conflicts(con):
    """#2: 비교가 mark/index/funding/is_closed를 빼먹으면 보강 데이터가 'duplicate'로 조용히 버려진다."""
    assert R.record_bar(con, bar(), mode="paper", symbol="BTCUSDT", source="ws") == "inserted"
    assert R.record_bar(con, bar(mark_close=D("60001.0"), funding_rate=D("0.0001")), mode="paper", symbol="BTCUSDT",
                        source="rest") == "enriched"
    assert con.execute("SELECT mark_close, funding_rate, index_close FROM bars_1m").fetchall() == [("60001.0", "0.0001", None)]
    assert R.record_bar(con, bar(mark_close=D("60001.0")), mode="paper", symbol="BTCUSDT", source="rest") == "duplicate"
    assert R.record_bar(con, bar(mark_close=D("59999.9")), mode="paper", symbol="BTCUSDT", source="rest") == "conflict"
    assert R.record_bar(con, bar(is_closed=False), mode="paper", symbol="BTCUSDT", source="ws") == "conflict"
    assert con.execute("SELECT mark_close, is_closed FROM bars_1m").fetchall() == [("60001.0", 1)]


def test_recorders_never_commit_or_roll_back_a_callers_open_transaction(con):
    """#3: `with con:`는 호출자의 열린 트랜잭션을 커밋/롤백한다 — migrate와 같이 거부한다."""
    con.execute("INSERT INTO engine_events(mode, symbol, ts_ms, kind) VALUES ('paper','BTCUSDT',1,'caller')")
    assert con.in_transaction
    with pytest.raises(R.TransactionOpen):
        R.record_events(con, [EntriesBlocked(DAY0, "x")], mode="paper", symbol="BTCUSDT")
    with pytest.raises(R.TransactionOpen):
        R.record_bar(con, bar(), mode="paper", symbol="BTCUSDT", source="ws")
    with pytest.raises(R.TransactionOpen):
        R.register_feature(con, "atr_1m", 1, "features_base", {"period": 14})
    assert con.in_transaction
    con.rollback()
    assert con.execute("SELECT COUNT(*) FROM engine_events").fetchone()[0] == 0


def test_a_close_never_links_to_an_open_position_of_the_other_direction(con, rules):
    """#4: 채택된 SHORT의 close가 닫히지 않은 LONG open 행에 붙으면 두 포지션 기록이 모두 틀린다."""
    _, ev = run_engine(rules)                                          # LONG open
    R.record_events(con, ev, mode="paper", symbol="BTCUSDT")
    short_close = PositionClosed(DAY0 + 9000, Direction.SHORT, ExitReason.SL, D("0.010"), D("60000"), None, (), D("-1"),
                                 D("0"), D("0"), D("999"))
    R.record_events(con, [short_close], mode="paper", symbol="BTCUSDT")
    assert con.execute("SELECT position_id, detail FROM positions WHERE event='close'").fetchall() == [(None, R.ORPHAN_CLOSE)]
    assert R.open_position_id(con, mode="paper", symbol="BTCUSDT", direction=Direction.LONG) is not None


def test_adopted_entry_open_row_carries_the_exchange_position_as_source_of_truth(con):
    """사용자 결정(2026-09-15): 채택 포지션의 open 행 = reason 'adopted_from_exchange' · 채택 시점 positionRisk(수량·평균가·청산가·원문)."""
    from dataclasses import replace

    from paper.types import PositionRisk
    pr = PositionRisk(D("0.033"), D("60000.5"), D("59700.1"), raw={"positionAmt": "0.033", "liquidationPrice": "59700.1"})
    base = _entry_filled_event()
    ev = replace(base, fills=(), adopted=pr, post_fill=replace(base.post_fill, qty=D("0.033"), entry_price=D("60000.5")))
    R.record_events(con, [ev], mode="live", symbol="BTCUSDT")
    (row,) = con.execute("SELECT event, reason, qty, entry_price, liq_price_exchange, detail, position_id, id"
                         " FROM positions").fetchall()
    assert row[:5] == ("open", "adopted_from_exchange", "0.033", "60000.5", "59700.1")
    assert json.loads(row[5]) == {"positionRisk": {"liquidationPrice": "59700.1", "positionAmt": "0.033"}}
    assert row[6] == row[7] and con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    close = PositionClosed(DAY0 + 5000, Direction.LONG, ExitReason.SL, D("0.033"), D("60000.5"), D("59800"), (), D("-6.6"),
                           D("0"), D("0"), D("990"))
    R.record_events(con, [close], mode="live", symbol="BTCUSDT")
    assert con.execute("SELECT position_id FROM positions WHERE event='close'").fetchone()[0] == row[7]


_CACHED: list = []


def _entry_filled_event():
    if not _CACHED:
        from exchange.loader import rules_from_snapshots
        from tests.conftest import SYMBOL, load_snapshot
        snap = {n: load_snapshot(n) for n in ("exchangeInfo", "leverageBracket", "commissionRate", "fundingInfo",
                                              "positionSideDual", "multiAssetsMargin")}
        _, ev = run_engine(rules_from_snapshots(snap, SYMBOL))
        _CACHED.append(next(x for x in ev if isinstance(x, EntryFilled)))
    return _CACHED[0]


# ── v2 (사용자 2026-09-15): 피처 인덱스 · 넓은 형식 내보내기 · safety_state ─────────────────────
def test_v1_database_upgrades_to_v2_without_touching_v1_rows(monkeypatch):
    c = sqlite3.connect(":memory:")
    M.migrate(c, target=1)
    c.execute("INSERT INTO engine_events(mode, symbol, ts_ms, kind) VALUES ('paper','BTCUSDT',1,'x')")
    c.commit()
    assert M.migrate(c) == [2] and c.execute("SELECT kind FROM engine_events").fetchall() == [("x",)]


def test_feature_tables_have_the_bar_name_version_index(con):
    """사용자: (bar_ts, name, params_version) 인덱스 — 이 스키마의 봉 시각 열 이름은 `bar_open_ms`."""
    for t in ("features_base", "features_adv"):
        idx = {r[1]: [c[2] for c in con.execute(f"PRAGMA index_info('{r[1]}')")]
               for r in con.execute(f"PRAGMA index_list('{t}')")}
        assert ["bar_open_ms", "name", "params_version"] in idx.values(), (t, idx)
        plan = " ".join(r[3] for r in con.execute(
            f"EXPLAIN QUERY PLAN SELECT value FROM {t} WHERE bar_open_ms=? AND name=? AND params_version=?", (1, "a", 1)))
        assert "INDEX" in plan, plan


def test_wide_export_round_trips_a_bars_feature_set(con):
    R.register_feature(con, "atr_1m", 1, "features_base", {"period": 14})
    R.register_feature(con, "atr_1m", 2, "features_base", {"period": 20})
    R.register_feature(con, "rsi_1m", 1, "features_base", {"period": 14})
    R.register_feature(con, "regime", 3, "features_adv", {"k": 2})
    bars = {DAY0: {("atr_1m", 1): D("35.2"), ("atr_1m", 2): D("33.9"), ("rsi_1m", 1): D("51.25")},
            DAY0 + 60_000: {("atr_1m", 1): D("35.4"), ("rsi_1m", 1): None}}
    for t, vals in bars.items():
        R.record_features(con, "features_base", t, vals, mode="paper", symbol="BTCUSDT")
    R.record_features(con, "features_adv", DAY0, {("regime", 3): D("2")}, mode="paper", symbol="BTCUSDT")
    R.record_features(con, "features_base", DAY0, {("atr_1m", 1): D("99")}, mode="live", symbol="BTCUSDT")   # 다른 모드
    wide = R.wide_features(con, "features_base", DAY0, DAY0 + 120_000, mode="paper", symbol="BTCUSDT")
    assert [w["bar_open_ms"] for w in wide] == [DAY0, DAY0 + 60_000]
    back = {w["bar_open_ms"]: {R.parse_feature_key(k): v for k, v in w["features"].items()} for w in wide}
    assert back == bars                                                  # Decimal·None 그대로 왕복
    assert R.feature_key("atr_1m", 2) == "atr_1m@v2" and R.parse_feature_key("atr_1m@v2") == ("atr_1m", 2)
    assert R.wide_features(con, "features_base", DAY0 + 60_000, DAY0 + 60_000, mode="paper", symbol="BTCUSDT") == []
    assert R.wide_features(con, "features_adv", DAY0, DAY0 + 1, mode="paper", symbol="BTCUSDT") == [
        {"bar_open_ms": DAY0, "features": {"regime@v3": D("2")}}]
    with pytest.raises(ValueError):
        R.wide_features(con, "features_custom", DAY0, DAY0 + 1, mode="paper", symbol="BTCUSDT")


def test_safety_state_is_append_only_history_and_latest_wins(con):
    assert R.load_safety_state(con, "kill_switch", mode="paper") is None
    R.save_safety_state(con, "kill_switch", {"tripped": None, "n": 1}, ts_ms=DAY0, mode="paper")
    R.save_safety_state(con, "kill_switch", {"tripped": "liquidation", "n": 2}, ts_ms=DAY0 + 1, mode="paper")
    R.save_safety_state(con, "kill_switch", {"tripped": None, "n": 0}, ts_ms=DAY0 + 2, mode="live")
    assert R.load_safety_state(con, "kill_switch", mode="paper") == {"tripped": "liquidation", "n": 2}
    assert con.execute("SELECT COUNT(*) FROM safety_state").fetchone()[0] == 3


# ── Codex L6·7 배치 ───────────────────────────────────────────────────────────
def test_adopted_entry_commission_estimate_is_recorded(con):
    from dataclasses import replace
    base = _entry_filled_event()
    R.record_events(con, [replace(base, fills=(), entry_commission=D("0.99"))], mode="live", symbol="BTCUSDT")
    assert con.execute("SELECT entry_commission_usdt FROM positions").fetchone()[0] == "0.99"


def test_exit_sync_amends_the_open_position_and_the_larger_close_leaves_it_flat(con):
    """Codex #3: 동기화는 root open 행의 **수정 행**(reason adopted_from_exchange) — 남은 수량 = 최신 수정 수량 − close 합."""
    from paper.types import PositionRisk, PositionSynced
    base = _entry_filled_event()
    R.record_events(con, [base], mode="live", symbol="BTCUSDT")
    root = con.execute("SELECT id FROM positions").fetchone()[0]
    q0 = base.post_fill.qty
    pr = PositionRisk(q0 + D("0.004"), D("59990"), D("59000"), raw={"positionAmt": str(q0 + D("0.004"))})
    sync = PositionSynced(DAY0 + 2000, Direction.LONG, q0, q0 + D("0.004"), D("59990"), D("0.12"), pr)
    R.record_events(con, [sync], mode="live", symbol="BTCUSDT")
    (row,) = con.execute("SELECT event, reason, position_id, qty, entry_price, entry_commission_usdt, liq_price_exchange"
                         " FROM positions WHERE id != ?", (root,)).fetchall()
    assert row == ("open", R.ADOPTED_FROM_EXCHANGE, root, str(q0 + D("0.004")), "59990", "0.12", "59000")
    st = R.open_position_state(con, mode="live", symbol="BTCUSDT")
    assert st is not None and st.remaining_qty == q0 + D("0.004")
    close = PositionClosed(DAY0 + 2000, Direction.LONG, ExitReason.MANUAL, q0 + D("0.004"), D("59990"), D("60000"), (),
                           D("0.04"), D("0.1"), D("0"), D("999"))
    R.record_events(con, [close], mode="live", symbol="BTCUSDT")
    assert con.execute("SELECT position_id FROM positions WHERE event='close'").fetchone()[0] == root
    assert R.open_position_state(con, mode="live", symbol="BTCUSDT") is None


def test_position_vanished_closes_the_db_position_with_unknown_exit(con):
    from paper.types import PositionVanished
    base = _entry_filled_event()
    R.record_events(con, [base], mode="live", symbol="BTCUSDT")
    v = PositionVanished(DAY0 + 9000, Direction.LONG, base.post_fill.qty, base.post_fill.entry_price, "거래소 포지션 0")
    R.record_events(con, [v], mode="live", symbol="BTCUSDT")
    (row,) = con.execute("SELECT reason, exit_price, realized_pnl_usdt, position_id, detail FROM positions WHERE event='close'").fetchall()
    assert row[:3] == ("vanished", None, None) and row[3] is not None and "거래소 포지션 0" in row[4]
    assert R.open_position_state(con, mode="live", symbol="BTCUSDT") is None


def test_partial_vanish_then_close_leaves_the_position_flat_and_every_unit_accounted(con):
    from paper.types import PositionVanished
    base = _entry_filled_event()
    R.record_events(con, [base], mode="live", symbol="BTCUSDT")
    q0 = base.post_fill.qty
    v = PositionVanished(DAY0 + 2000, Direction.LONG, D("0.004"), base.post_fill.entry_price, "부분 감소")
    R.record_events(con, [v], mode="live", symbol="BTCUSDT")
    st = R.open_position_state(con, mode="live", symbol="BTCUSDT")
    assert st is not None and st.remaining_qty == q0 - D("0.004")
    close = PositionClosed(DAY0 + 2000, Direction.LONG, ExitReason.MANUAL, q0 - D("0.004"), D("60000"), D("60000"), (),
                           D("0"), D("0"), D("0"), D("999"))
    R.record_events(con, [close], mode="live", symbol="BTCUSDT")
    assert R.open_position_state(con, mode="live", symbol="BTCUSDT") is None
    assert [r[0] for r in con.execute("SELECT reason FROM positions WHERE event='close' ORDER BY id")] == ["vanished", "manual"]


# ── layer 8 배치(2026-09-16): 부분 청산 행 · 지갑 재동기화 · account_snapshots · 운영 이벤트 ─────────────
def test_partial_close_writes_orders_and_a_close_row_so_db_remaining_equals_the_engine(con, rules):
    import dataclasses as dc

    from paper.types import PositionReduced
    from tests.test_paper_engine import SpySender, intent, tick
    r2 = dc.replace(rules, symbol_rules=dc.replace(rules.symbol_rules, market_max_qty=D("0.010")))
    s = SpySender(PaperSender(r2))
    e = Engine(r2, s, mode=Mode.PAPER, wallet=D("1000"), limits=SizingLimits())
    e.request_entry(intent(sl="59820", risk="0.02"))
    ev = e.on_tick(tick(DAY0 + 1000, "60000"))
    R.record_events(con, ev, mode="paper", symbol="BTCUSDT")
    k = len([c for c in s.calls if c[0] == "send"])
    s.unknown_on_send = k + 2
    ev = e.close_now(ref_mark=D("60100"), ts_ms=DAY0 + 2000)
    (red,) = [x for x in ev if isinstance(x, PositionReduced)]
    R.record_events(con, ev, mode="paper", symbol="BTCUSDT")
    st = R.open_position_state(con, mode="paper", symbol="BTCUSDT")
    assert e.position is not None and st is not None and st.remaining_qty == e.position.qty
    (row,) = con.execute("SELECT qty, exit_price, realized_pnl_usdt, exit_commission_usdt, wallet_after, reason, detail,"
                         " position_id FROM positions WHERE event='close'").fetchall()
    root = con.execute("SELECT id FROM positions WHERE event='open'").fetchone()[0]
    assert row[:6] == (str(red.qty), str(red.exit_price), str(red.realized_pnl_usdt), str(red.exit_commission_usdt),
                       str(red.wallet_after), "manual") and "partial" in row[6] and row[7] == root
    assert con.execute("SELECT count(*) FROM orders WHERE intent='exit'").fetchone()[0] == 1
    R.record_events(con, e.close_now(ref_mark=D("60100"), ts_ms=DAY0 + 3000), mode="paper", symbol="BTCUSDT")
    assert R.open_position_state(con, mode="paper", symbol="BTCUSDT") is None


def test_wallet_resync_is_an_engine_event_row(con):
    from paper.types import WalletResynced
    R.record_events(con, [WalletResynced(DAY0, D("1000"), D("912.5"), "exchange", "소실 뒤")], mode="live", symbol="BTCUSDT")
    (kind, detail, payload) = con.execute("SELECT kind, detail, payload_json FROM engine_events").fetchone()
    assert kind == "WalletResynced" and "소실 뒤" in detail and json.loads(payload)["wallet"] == "912.5"


def test_account_snapshot_rows_keep_exact_decimals_and_source(con):
    R.record_account_snapshot(con, mode="paper", symbol="BTCUSDT", ts_ms=DAY0, source="engine", wallet_balance=D("999.1"),
                              margin_balance=D("1000.2"), available_balance=D("959.1"), isolated_margin=D("40"),
                              unrealized_pnl=D("1.1"), raw={"reason": "bar"})
    row = con.execute("SELECT source, wallet_balance, margin_balance, available_balance, isolated_margin, unrealized_pnl,"
                      " raw_json FROM account_snapshots").fetchone()
    assert row[:6] == ("engine", "999.1", "1000.2", "959.1", "40", "1.1") and json.loads(row[6]) == {"reason": "bar"}
    with pytest.raises(TypeError):
        R.record_account_snapshot(con, mode="paper", symbol="BTCUSDT", ts_ms=DAY0, source="engine",
                                  wallet_balance=999.1)  # type: ignore[arg-type]
    with pytest.raises(sqlite3.IntegrityError):
        R.record_account_snapshot(con, mode="paper", symbol="BTCUSDT", ts_ms=DAY0, source="guess", wallet_balance=D("1"))


def test_ops_events_are_recorded_beside_engine_events(con):
    R.record_ops_event(con, "KillSwitchTripped", "daily_loss …", ts_ms=DAY0, mode="paper", symbol="BTCUSDT",
                       payload={"reason": "daily_loss"})
    assert con.execute("SELECT kind, payload_json FROM engine_events").fetchone() == ("KillSwitchTripped",
                                                                                      '{"reason": "daily_loss"}')


def test_ops_event_with_an_op_id_is_idempotent(con):
    for _ in range(2):
        R.record_ops_event(con, "KillSwitchTripped", "x", ts_ms=DAY0, mode="paper", symbol="BTCUSDT",
                           payload={"reason": "daily_loss"}, op_id="abc123")
    R.record_ops_event(con, "KillSwitchTripped", "x", ts_ms=DAY0, mode="paper", symbol="BTCUSDT", payload=None, op_id="def")
    rows = con.execute("SELECT json_extract(payload_json, '$.op_id') FROM engine_events ORDER BY id").fetchall()
    assert rows == [("abc123",), ("def",)]
