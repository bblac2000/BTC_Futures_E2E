"""트라이얼 #2 실행 고정부(단계 2d·2e after-pass · Codex #1·#4) — 모든 트라이얼 #2 재생은 이 함수로만.

- 규칙 = #36 스냅샷(`anchor.RULES_SNAPSHOT_DIR`) · 파일 4개의 SHA256을 앵커 값과 대조(불일치 → `RulesSnapshotMismatch` · 대체 없음).
- tick = 그 규칙의 tickSize(호출자가 주지 않는다) · limits = `SizingLimits(leverage_range=(10,30), liq_fee_on_liq_price=True)` ·
  equity = sizing_capital = E_ref 1,000(§1 사이징 행 · 규약 1·3·4).
- §7-3 결합(C6 · 규약 23): 전략의 `first_cross`(outcome = intent) 다음에 오는 엔진 `EntrySkipped`를 `on_event`로 받아 그 교차의
  사유로 기록 — sl_crossed_before_fill · normalization(`below_min_qty`·`min_notional`) · sizing_rejected(그 밖) · entry_refused.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backtest import days as DY
from backtest import prepare_t2 as PT
from backtest.data import Bar1m, Funding
from backtest.engine_replay import ReplayResult, replay
from exchange.loader import rules_from_snapshot_dir
from exchange.normalize import RejectReason
from exchange.rules import RuntimeRules
from paper.types import EntryFilled, EntrySkipped, SkipReason
from strategies.trial02 import anchor as A
from strategies.trial02.config import BO_V1, LIMITS
from strategies.trial02.strategy import Trial02, Variant

ROOT = Path(__file__).resolve().parent.parent.parent
NORMALIZATION = {RejectReason.BELOW_MIN_QTY, RejectReason.MIN_NOTIONAL}


class RulesSnapshotMismatch(RuntimeError):
    pass


def load_rules(snapshot_dir: Path | None = None) -> RuntimeRules:
    d = snapshot_dir or ROOT / A.RULES_SNAPSHOT_DIR
    for name, sha in A.RULES_SNAPSHOT_SHA256.items():
        got = hashlib.sha256((d / f"{name}.json").read_bytes()).hexdigest()
        if got != sha:
            raise RulesSnapshotMismatch(f"{name}.json SHA256 {got} ≠ #36 {sha}")
    return rules_from_snapshot_dir(d, "BTCUSDT")


@dataclass
class T2Run:
    result: ReplayResult
    strategy: Trial02
    crosses: list[dict[str, Any]]          # first_cross 기록 + 엔진 사유를 이은 최종 사유(`final_reason`)


def skip_reason(ev: EntrySkipped) -> str:
    if ev.reason is SkipReason.SL_CROSSED_BEFORE_FILL:
        return "sl_crossed_before_fill"
    if ev.reason is SkipReason.SIZING_REJECTED:
        return "normalization" if ev.decision is not None and ev.decision.reason in NORMALIZATION else "sizing_rejected"
    return str(ev.reason)


def run_t2(bars: Sequence[Bar1m], fundings: Sequence[Funding], trade_days: set[int], variant: Variant) -> T2Run:
    rules = load_rules()
    s = Trial02(tick=rules.symbol_rules.tick_size, trade_days=trade_days, variant=variant)
    engine_outcomes: list[tuple[str, str | None]] = []      # 체결/건너뜀 순서(의도 하나당 정확히 하나)

    def on_event(ev: object) -> None:
        if isinstance(ev, EntryFilled):
            engine_outcomes.append(("entered", None))
        elif isinstance(ev, EntrySkipped):
            engine_outcomes.append(("skipped", skip_reason(ev)))

    r = replay(bars, fundings, s, rules=rules, limits=LIMITS, equity=BO_V1.e_ref, on_event=on_event,
               sizing_capital=BO_V1.e_ref)
    refused = [d for d in r.decisions if d.get("reason") == "entry_refused"]
    assert not refused, f"진입 요청 거부(설정 오류): {refused[:3]}"
    crosses = [dict(x) for x in s.log if x["event"] == "first_cross"]
    intents = [c for c in crosses if c["outcome"] == "intent"]
    assert len(intents) == len(engine_outcomes), f"의도 {len(intents)} ≠ 엔진 결과 {len(engine_outcomes)}"
    for c in crosses:
        c["final_reason"] = c.get("reason")
    for c, (kind, why) in zip(intents, engine_outcomes, strict=True):
        c["engine"] = kind
        c["final_reason"] = None if kind == "entered" else why
    return T2Run(r, s, crosses)



def _run_prepared(out: Path, pins: dict[str, Any], variant: Variant, expect_range: tuple[int, int],
                  first_day: int, last_day: int) -> tuple[T2Run, DY.Validity]:
    bars, fundings = PT.load_prepared_pinned(out, pins, expect_range)                  # G12: 해시만(다시 빌드는 verify 단계·판정기)
    v = DY.validity(bars, fundings, first_day, last_day)
    return run_t2(bars, fundings, v.v_a if variant.arm == "A" else v.v_b, variant), v


def run_prepared_is(out: Path, pins: dict[str, Any], variant: Variant) -> tuple[T2Run, DY.Validity]:
    """판정 경로의 유일한 입구 — IS 창(+21일)만 · 커밋된 data_pins(원시 + 산출물 해시) 필수 · V_A/V_B를 여기서 계산.
    pins는 호출자(run.py)가 `t2_provenance.load_pins`로 읽는다(추적·깨끗·푸시)."""
    return _run_prepared(out, pins, variant, PT.window_range(), A.IS_START_MS // A.DAY_MS, A.IS_END_MS // A.DAY_MS)
