"""트라이얼 #4 하네스((d) · 규약 C25·C27·C35·C36) — 준비 입력 위의 순수 실행 · 암마다 독립 재생.

- `load_rules`: #69 스냅샷 네 파일 SHA256 + taker 0.0005(§2) 단언 뒤에만 규칙을 돌려준다.
- `validate_inputs`: (복사 · strategies/trial03/harness.py @ 8b8f103 · 바꾼 것 없음) 봉 정렬·엄격 증가 · 펀딩 격자 버킷마다 최대 1건 · 유한 값.
- `validate_prints`(C27): 8시간 격자 · 빠진 경계 없음 · `valid ⇔ n ≥ 475` · `complete ⇔ n = 480` · 유효면 p 유한.
- `FillRef`(C25): 체결 봉 mark 시가 조회 — **결정 중인 T + 1분 키 하나만** 허용.
- `run_arm`: 재생(슬리피지 0.0006 · 사이징 자본 E_ref · LIMITS) → `finish` → 실행 불변식(창 끝 열린 포지션 없음 · `entry_refused` 없음 ·
  깔때기 합 = 창 안 경계 수 · 진입 종결 합 = 후보 · 청산 = 체결 = 트레이드 · 진입일 ∈ V) → `trades`(공유 dict + "t4": 결정 기록).
- V(C35) = 창 안 완전한 mark 날 ∧ 그날 00:00 경계에서 후행 분포 정의.
"""
from __future__ import annotations

import hashlib
import inspect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backtest.data import MINUTE_MS, Bar1m, Funding
from backtest.engine_replay import ReplayResult, replay
from exchange.loader import rules_from_snapshot_dir
from exchange.rules import RuntimeRules
from strategies.trial04 import anchor as A
from strategies.trial04.config import LIMITS, TC_V3, TcParams
from strategies.trial04.eligibility import Eligibility, complete_days
from strategies.trial04.strategy import Eligible, RunInvariantError, Trial04, Variant

ROOT = Path(__file__).resolve().parent.parent.parent
DAY = 86_400_000
H8 = A.H8_MS
GRID = (0, H8, 2 * H8)
ENTRY_TERMINALS = ("sl_crossed_before_fill", "sizing_rejected_fill", "normalization", "filled")
PREREG_TAKER = Decimal("0.0005")
PRINT_VALID_MIN, PRINT_MINUTES = 475, 480


class RulesSnapshotMismatch(RuntimeError):
    pass


class RunFailure(RuntimeError):
    """재생·마무리 검사 중 실패 — 전략 객체(기록·깔때기·상태)를 담아 실행 CLI가 보존한다(원인은 __cause__)."""

    def __init__(self, strategy: Trial04):
        super().__init__(f"트라이얼 #4 실행 실패(arm {strategy.arm} · 상태 {strategy.state})")
        self.strategy = strategy


class InputError(RuntimeError):
    """실행 입력이 준비 규약을 어긴다 — 실행하지 않는다."""


@dataclass
class T4Run:
    arm: str
    variant: Variant
    result: ReplayResult
    strategy: Trial04
    trades: list[dict[str, Any]]              # 공유 트레이드 dict + "t4": 결정 기록


def validate_inputs(bars: Sequence[Bar1m], fundings: Sequence[Funding]) -> None:
    """(복사 · trial03 harness @ 8b8f103) 봉 open_ms는 분 정렬·엄격 증가 · 펀딩은 00/08/16 버킷마다 최대 1건 · 율·mark는 유한(mark 양수)."""
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


def validate_prints(prints: Sequence[dict[str, Any]]) -> None:
    prev = None
    for pr in prints:
        t, n = pr["T"], pr["n_minutes"]
        if not isinstance(t, int) or t % H8 or (prev is not None and t != prev + H8):
            raise InputError(f"인쇄 {t}: 격자 밖 또는 빠진 경계·중복(앞 {prev})")
        prev = t
        if not isinstance(n, int) or pr["valid"] is not (n >= PRINT_VALID_MIN) or pr["complete"] is not (n == PRINT_MINUTES):
            raise InputError(f"인쇄 {t}: 플래그가 n_minutes {n}와 맞지 않는다")
        if pr["valid"]:
            try:
                ok = math.isfinite(float(pr["p"]))
            except (TypeError, ValueError):
                ok = False
            if not ok:
                raise InputError(f"인쇄 {t}: 유효인데 p가 유한하지 않다")


class FillRef:
    """체결 봉 mark 시가(C25) — 결정 중인 T에 대해 키 T + 1분만 허용한다."""

    def __init__(self, bars: Sequence[Bar1m]):
        self.opens = {b.open_ms: b.mark_open for b in bars}

    def __call__(self, t: int, t_print: int) -> Decimal:
        if t != t_print + MINUTE_MS:
            raise RunInvariantError(f"체결 기준가 조회 {t}는 결정 중인 T {t_print} + 1분이 아니다")
        v = self.opens.get(t)
        if v is None:
            raise RunInvariantError(f"체결 봉 {t}이 없다(판정 가능 술어 위반)")
        return Decimal(v)


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


def run_arm(bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]], arm: str, variant: Variant, *,
            window: tuple[int, int] = (A.WINDOW_START_MS, A.IS_END_MS)) -> T4Run:
    """실행 경로: 규칙은 항상 `load_rules()`(#69 네 파일 SHA256 + taker 단언) · 매개변수는 항상 `TC_V3` — 덮어쓸 인자가 없다."""
    return _run_arm(bars, fundings, prints, arm, variant, rules=load_rules(), p=TC_V3, window=window)


def run_arm_with_fixture_rules(bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]], arm: str,
                               variant: Variant, *, rules: RuntimeRules, p: TcParams = TC_V3,
                               window: tuple[int, int] = (A.WINDOW_START_MS, A.IS_END_MS),
                               eligible: Eligible | None = None) -> T4Run:
    """**테스트 전용**(합성 창·술어 대체) — 호출자 파일이 `tests/` 아래가 아니면 거부(실행 시점): tests/ 전용."""
    caller = Path(inspect.stack()[1].filename).resolve()
    if (ROOT / "tests") not in caller.parents:
        raise RulesSnapshotMismatch(f"픽스처 규칙 경로는 tests/ 전용이다(호출자 {caller})")
    return _run_arm(bars, fundings, prints, arm, variant, rules=rules, p=p, window=window, eligible=eligible)


def _run_arm(bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]], arm: str, variant: Variant, *,
             rules: RuntimeRules, p: TcParams, window: tuple[int, int], eligible: Eligible | None = None) -> T4Run:
    validate_inputs(bars, fundings)
    validate_prints(prints)
    elig = eligible or Eligibility(bars, fundings, window_start=window[0], window_end=window[1])
    s = Trial04(arm, rules=rules, prints=prints, eligible=elig, fill_ref=FillRef(bars), variant=variant, p=p, window=window)
    try:
        return _run_protected(s, bars, fundings, prints, arm, variant, rules=rules, p=p)
    except BaseException as e:                                  # 재생 → 마무리 검사 전체 · 전략 기록을 들고 나간다
        raise RunFailure(s) from e


def _run_protected(s: Trial04, bars: Sequence[Bar1m], fundings: Sequence[Funding], prints: Sequence[dict[str, Any]], arm: str,
                   variant: Variant, *, rules: RuntimeRules, p: TcParams) -> T4Run:
    r = replay(bars, fundings, s, rules=rules, limits=LIMITS, equity=p.e_ref, sizing_capital=p.e_ref, slippage_rate=p.slippage)
    s.finish()
    if r.open_at_end is not None:
        raise RunInvariantError("창 끝에 열린 포지션")
    if any(x.get("reason") == "entry_refused" for x in r.decisions):
        raise RunInvariantError("엔진이 의도를 거부했다(entry_refused)")
    last = bars[-1].open_ms if bars else -1
    expect = sum(1 for pr in prints if s.window[0] <= pr["T"] + MINUTE_MS and pr["T"] <= s.window[1] and pr["T"] <= last)
    if sum(s.funnel.values()) != s.window_prints or s.window_prints != expect:
        raise RunInvariantError(f"인쇄 깔때기 합 {sum(s.funnel.values())} · 처리 {s.window_prints} ≠ 창 안 경계 {expect}")
    if sum(s.entry[k] for k in ENTRY_TERMINALS) != s.funnel["candidate"]:
        raise RunInvariantError("진입 종결 합 ≠ 후보")
    if sum(v for k, v in s.entry.items() if k.startswith("exit.")) != s.entry["filled"] or len(r.trades) != s.entry["filled"]:
        raise RunInvariantError("청산·트레이드 수 ≠ 체결")
    trades = [t | {"t4": i} for t, i in zip(r.trades, s.filled_intents, strict=True)]
    assert_entries_in_v(trades, set(v_days(s, complete_days(bars))))
    return T4Run(arm, variant, r, s, trades)


def assert_entries_in_v(trades: Sequence[dict[str, Any]], v: set[int]) -> None:
    """§3-1 "블록 = 진입 UTC 날 · V" — 진입일이 V 밖이면 실행 실패로 드러낸다(C37 · 표본 규칙은 진입일의 앞부분을 보지 않는다)."""
    bad = [int(t["entry_ms"]) for t in trades if int(t["entry_ms"]) // DAY not in v]
    if bad:
        raise RunInvariantError(f"진입일이 V 밖인 체결 {len(bad)}건(첫 {bad[0]})")


def v_days(s: Trial04, days: set[int]) -> list[int]:
    """V = 창 안의 완전한 mark 날 ∧ 그날 00:00 경계에서 후행 분포 정의(C35)."""
    return sorted(d for d, ok in s.dist_defined.items() if ok and d in days)


__all__ = ["Eligibility", "FillRef", "InputError", "RulesSnapshotMismatch", "RunFailure", "T4Run", "complete_days", "load_rules",
           "run_arm", "run_arm_with_fixture_rules", "v_days", "validate_inputs", "validate_prints"]
