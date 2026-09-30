"""트라이얼 #3 하네스(단계 2 (d) · 계획 r2/r3 D2·D3·D6·D7·D9) — 준비 입력 위의 순수 실행 · 암마다 독립 재생.

- `load_rules`: #48 스냅샷 네 파일 SHA256 + taker 0.0005(§2) 단언 뒤에만 규칙을 돌려준다.
- `Admissibility`: §1 35~36행 — t0의 닫힌 시각 구간 [t0 − 270분, t0 + 366분]:
  ① 구간 끝 > 창 끝 → `window_end` ② day_index(t0 − 270분) … day_index(t0 + 366분)의 날 중 완전하지 않은 날 → `incomplete`
  (완전 = 정렬 분 1,440 · mark 4필드 유한 양수) ③ t0 ≤ b ≤ t0 + 366분인 00/08/16 경계 b마다 검증된 확정 펀딩이 정확히 1건(버킷 분 =
  funding_ms − funding_ms % 60,000)이 아니면 → `funding`. L·S와 기본·P2·P3가 같은 판정을 쓴다.
- `run_arm`: 재생(슬리피지 0.0006 · 사이징 자본 E_ref · LIMITS) → `finish`(일정·미완 상태) → 실행 불변식(창 끝 열린 포지션 없음 ·
  `entry_refused` 없음) → 합 검사(이벤트 깔때기 = 창 봉 · 진입 종결 = 적격 · 청산 = 체결) → 트레이드와 체결된 의도를 순서로 짝지은
  `trades_t3`(결정 시점 sl_dist 등 · 공유 트레이드 dict는 그대로).
"""
from __future__ import annotations

import hashlib
import inspect
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.engine_replay import ReplayResult, replay
from exchange.loader import rules_from_snapshot_dir
from exchange.rules import RuntimeRules
from strategies.trial03 import anchor as A
from strategies.trial03.config import LIMITS, TF_V1, TfParams
from strategies.trial03.features import OiIndex
from strategies.trial03.strategy import RunInvariantError, Trial03, Variant

ROOT = Path(__file__).resolve().parent.parent.parent
DAY = A.DAY_MS
GRID = (0, 8 * 3_600_000, 16 * 3_600_000)
ENTRY_TERMINALS = ("not_cooled", "sl_dist_out_of_range", "sizing_rejected_decision", "sl_crossed_before_fill",
                   "sizing_rejected_fill", "normalization", "filled")
PREREG_TAKER = Decimal("0.0005")


class RulesSnapshotMismatch(RuntimeError):
    pass


class RunFailure(RuntimeError):
    """재생·마무리 검사 중 실패 — 전략 객체(이벤트 기록·깔때기·상태)를 담아 실행 CLI가 `_failure_*`로 보존한다(원인은 __cause__)."""

    def __init__(self, strategy: Trial03):
        super().__init__(f"트라이얼 #3 실행 실패(arm {strategy.arm} · 상태 {strategy.state})")
        self.strategy = strategy


class InputError(RuntimeError):
    """실행 입력이 준비 규약을 어긴다(중복·비정렬 분 · 펀딩 버킷 중복 · 비유한 율/mark) — 실행하지 않는다."""


def validate_inputs(bars: Sequence[Bar1m], fundings: Sequence[Funding]) -> None:
    """실행 경계 검사(Codex (d) after #1): 봉 open_ms는 분 정렬·엄격 증가(중복 없음) · 펀딩은 00/08/16 버킷마다 최대 1건 ·
    율·mark는 유한 Decimal(mark 양수). 준비 단계가 이미 보장하지만 하네스가 다시 단언한다."""
    prev = None
    for b in bars:
        if b.open_ms % MINUTE_MS or (prev is not None and b.open_ms <= prev):
            raise InputError(f"봉 {b.open_ms}: 정렬 안 됨 또는 중복·역순")
        prev = b.open_ms
    seen: set[int] = set()
    for f in fundings:
        bkt = f.funding_ms - f.funding_ms % MINUTE_MS
        if bkt % DAY not in GRID or bkt in seen:
            raise InputError(f"펀딩 {f.funding_ms}: 격자 밖 또는 버킷 중복")
        seen.add(bkt)
        try:
            rate, mark = Decimal(f.rate), Decimal(f.mark)
        except (InvalidOperation, ValueError) as e:
            raise InputError(f"펀딩 {f.funding_ms}: 해석 불가") from e
        if not (rate.is_finite() and mark.is_finite() and mark > 0):
            raise InputError(f"펀딩 {f.funding_ms}: 비유한 율 또는 mark")


def load_rules(snapshot_dir: Path | None = None, expected: dict[str, str] | None = None) -> RuntimeRules:
    d = snapshot_dir or ROOT / A.RULES_SNAPSHOT_DIR
    want = A.RULES_SNAPSHOT_SHA256 if expected is None else expected
    for name, sha in want.items():
        got = hashlib.sha256((d / f"{name}.json").read_bytes()).hexdigest()
        if got != sha:
            raise RulesSnapshotMismatch(f"{name}: {got} ≠ {sha}")
    rules = rules_from_snapshot_dir(d, "BTCUSDT")
    if rules.commission.taker != PREREG_TAKER:
        raise RulesSnapshotMismatch(f"taker {rules.commission.taker} ≠ §2 {PREREG_TAKER}")
    return rules


def _finite_pos(v: str) -> bool:
    try:
        x = Decimal(v)
    except (InvalidOperation, ValueError):
        return False
    return x.is_finite() and x > 0


def complete_days(bars: Sequence[Bar1m]) -> set[int]:
    """완전한 mark 날 = 정렬 분 1,440개가 **한 번씩**(중복 분이 있으면 그 날은 완전하지 않다) · mark 4필드 유한 양수."""
    per: dict[int, list[int]] = defaultdict(list)
    bad: set[int] = set()
    for b in bars:
        d = b.open_ms // DAY
        if b.open_ms % MINUTE_MS or not all(_finite_pos(x) for x in (b.mark_open, b.mark_high, b.mark_low, b.mark_close)):
            bad.add(d)
            continue
        per[d].append(b.open_ms)
    return {d for d, s in per.items() if len(s) == 1440 and len(set(s)) == 1440 and d not in bad}


class Admissibility:
    def __init__(self, bars: Sequence[Bar1m], fundings: Sequence[Funding], *, p: TfParams = TF_V1,
                 window_end: int = A.IS_END_MS):
        self.p, self.window_end = p, window_end
        self.days = complete_days(bars)
        self.fund: Counter[int] = Counter(f.funding_ms - f.funding_ms % MINUTE_MS for f in fundings)

    def __call__(self, t0: int) -> str | None:
        lo, hi = t0 - self.p.span_before_ms, t0 + self.p.span_after_ms
        if hi > self.window_end:
            return "window_end"
        if any(d not in self.days for d in range(lo // DAY, hi // DAY + 1)):
            return "incomplete"
        for d in range(t0 // DAY, hi // DAY + 1):
            for g in GRID:
                b = d * DAY + g
                if t0 <= b <= hi and self.fund[b] != 1:
                    return "funding"
        return None


@dataclass
class T3Run:
    arm: str
    variant: Variant
    result: ReplayResult
    strategy: Trial03
    trades: list[dict[str, Any]]              # 공유 트레이드 dict + "t3": 결정 기록


def run_arm(bars: Sequence[Bar1m], fundings: Sequence[Funding], oi_rows: Sequence[Sequence[Any]], unusable: Sequence[int],
            arm: str, variant: Variant, *, window: tuple[int, int] = (A.WINDOW_START_MS, A.IS_END_MS)) -> T3Run:
    """실행 경로: 규칙은 항상 `load_rules()`(#48 네 파일 SHA256 + taker 단언) · 매개변수는 항상 `TF_V1` — 덮어쓸 인자가 없다."""
    return _run_arm(bars, fundings, oi_rows, unusable, arm, variant, rules=load_rules(), p=TF_V1, window=window)


def run_arm_with_fixture_rules(bars: Sequence[Bar1m], fundings: Sequence[Funding], oi_rows: Sequence[Sequence[Any]],
                               unusable: Sequence[int], arm: str, variant: Variant, *, rules: RuntimeRules,
                               p: TfParams = TF_V1, window: tuple[int, int] = (A.WINDOW_START_MS, A.IS_END_MS),
                               admissible: Admissibility | None = None) -> T3Run:
    """**테스트 전용**(합성 픽스처 규칙·작은 TfParams) — 호출자 파일이 `tests/` 아래가 아니면 거부(실행 시점) · 저장소 전체 정적 검사도 있다."""
    caller = Path(inspect.stack()[1].filename).resolve()
    if (ROOT / "tests") not in caller.parents:
        raise RulesSnapshotMismatch(f"픽스처 규칙 경로는 tests/ 전용이다(호출자 {caller})")
    return _run_arm(bars, fundings, oi_rows, unusable, arm, variant, rules=rules, p=p, window=window, admissible=admissible)


def _run_arm(bars: Sequence[Bar1m], fundings: Sequence[Funding], oi_rows: Sequence[Sequence[Any]], unusable: Sequence[int],
             arm: str, variant: Variant, *, rules: RuntimeRules, p: TfParams, window: tuple[int, int],
             admissible: Admissibility | None = None) -> T3Run:
    validate_inputs(bars, fundings)
    adm = admissible or Admissibility(bars, fundings, p=p, window_end=window[1])
    s = Trial03(arm, rules=rules, oi=OiIndex(oi_rows, unusable, p), admissible=adm, variant=variant, p=p, window=window)
    try:
        return _run_protected(s, bars, fundings, arm, variant, rules=rules, p=p)
    except BaseException as e:                                  # 재생 → 마무리 검사 전체 · 전략 기록을 들고 나간다((g) 계획 K7)
        raise RunFailure(s) from e


def _run_protected(s: Trial03, bars: Sequence[Bar1m], fundings: Sequence[Funding], arm: str, variant: Variant, *,
                   rules: RuntimeRules, p: TfParams) -> T3Run:
    r = replay(bars, fundings, s, rules=rules, limits=LIMITS, equity=p.e_ref, sizing_capital=p.e_ref, slippage_rate=p.slippage)
    s.finish()
    if r.open_at_end is not None:
        raise RunInvariantError("창 끝에 열린 포지션")
    if any(x.get("reason") == "entry_refused" for x in r.decisions):
        raise RunInvariantError("엔진이 의도를 거부했다(entry_refused)")
    if sum(s.funnel.values()) != s.window_bars:
        raise RunInvariantError(f"이벤트 깔때기 합 {sum(s.funnel.values())} ≠ 창 봉 {s.window_bars}")
    if sum(s.entry[k] for k in ENTRY_TERMINALS) != s.funnel["qualified"]:
        raise RunInvariantError("진입 깔때기 종결 합 ≠ 적격 이벤트")
    if sum(v for k, v in s.entry.items() if k.startswith("exit.")) != s.entry["filled"] or len(r.trades) != s.entry["filled"]:
        raise RunInvariantError("청산·트레이드 수 ≠ 체결")
    trades = [t | {"t3": i} for t, i in zip(r.trades, s.filled_intents, strict=True)]
    assert_entries_in_v(trades, set(v_days(s, complete_days(bars))))
    return T3Run(arm, variant, r, s, trades)


def assert_entries_in_v(trades: Sequence[dict[str, Any]], v: set[int]) -> None:
    """§3-1 83행 "모든 체결의 진입일은 V 안이다"를 실행 시점에 먼저 검사(판정기 거부가 IS 실행 뒤에야 나지 않게 · (f) 계획 V1)."""
    bad = [int(t["entry_ms"]) for t in trades if int(t["entry_ms"]) // DAY not in v]
    if bad:
        raise RunInvariantError(f"진입일이 V 밖인 체결 {len(bad)}건(첫 {bad[0]})")


def v_days(s: Trial03, days: set[int]) -> list[int]:
    """V = 창 안의 완전한 mark 날 ∧ 그날 분위수 유효(§3-1)."""
    return sorted(d for d, ok in s.q_valid.items() if ok and d in days)


__all__ = ["RunFailure", "InputError", "validate_inputs", "run_arm_with_fixture_rules", "Admissibility", "RulesSnapshotMismatch", "T3Run", "complete_days", "load_rules", "run_arm", "v_days"]
