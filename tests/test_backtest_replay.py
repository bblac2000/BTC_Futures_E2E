"""단계 2a — 격리 실행 러너·verbatim 기록기·재생 루프 결정론. 가짜 전략·합성 봉만."""
from __future__ import annotations

import json
import sys

import pytest

from backtest import replay as RP

MOD = "tests.fixtures.dummy_replay_strategy"


def test_isolated_run_does_not_import_the_strategy_and_records_outputs_verbatim(tmp_path, monkeypatch):
    monkeypatch.delitem(sys.modules, MOD, raising=False)             # 테스트 순서와 무관하게(다른 테스트가 import했을 수 있다)
    assert MOD not in sys.modules
    rec = RP.run_isolated(MOD, ["--minutes", "600"], tmp_path / "out")
    assert rec.returncode == 0, rec.stderr
    assert MOD not in sys.modules, "러너는 전략 모듈을 import하지 않는다"
    assert set(rec.outputs) == {"trades.jsonl", "decisions.jsonl", "summary.json"}
    trades = RP.read_jsonl(tmp_path / "out" / "trades.jsonl")
    assert trades and all({"entry_ms", "exit_ms", "gross_bps", "net_bps", "exit_reason", "sl_dist"} <= set(t) for t in trades)
    assert rec.stdout.strip() == f"trades={len(trades)}" and rec.numpy == "2.5.3" and rec.git_head
    reasons = {t["exit_reason"] for t in trades}
    assert {"sl", "tp"} <= reasons, reasons
    assert "open_at_end" in json.loads((tmp_path / "out" / "summary.json").read_text())
    sha = RP.record_verbatim(tmp_path / "record.json", rec, {"note": "fixture"})
    body = json.loads((tmp_path / "record.json").read_text())
    assert body["run"]["outputs"]["trades.jsonl"] == rec.outputs["trades.jsonl"] and len(sha) == 64


def test_two_isolated_runs_produce_byte_identical_outputs(tmp_path, monkeypatch):
    monkeypatch.delitem(sys.modules, MOD, raising=False)
    a = RP.run_isolated(MOD, ["--minutes", "600"], tmp_path / "a")
    b = RP.run_isolated(MOD, ["--minutes", "600"], tmp_path / "b")
    assert a.returncode == b.returncode == 0
    assert a.outputs == b.outputs, "같은 입력 → 같은 트레이드·결정 파일(바이트 동일)"


def test_the_runner_refuses_when_the_strategy_module_is_already_imported(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, MOD, object())
    with pytest.raises(AssertionError, match="격리 실행 위반"):
        RP.run_isolated(MOD, [], tmp_path)


def test_gross_uses_the_mark_reference_not_the_slipped_fill(rules):
    """advisor 2026-09-21: gross는 mark 기준(슬리피지 전) — 체결가를 쓰면 G1이 P1보다 ~2 bps 과소평가된다."""
    from decimal import Decimal

    from backtest.engine_replay import replay
    from sizing.config import SizingLimits
    from tests.fixtures import dummy_replay_strategy as DS
    r = replay(DS.bars(600), [], DS.Every30(), rules=rules, limits=SizingLimits(), equity=Decimal("1000"))
    sl = [t for t in r.trades if t["exit_reason"] == "sl"]
    assert sl
    for t in sl:
        em, ref = Decimal(t["entry_mark"]), Decimal(t["exit_ref"])
        assert Decimal(t["gross_bps"]) == (ref - em) / em * 10_000
        assert ref != Decimal(t["wallet_after"]) and Decimal(t["gross_bps"]) > Decimal(t["net_bps"]), "net = gross − 비용"
