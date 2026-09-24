"""트라이얼 #2 유효일(단계 2d · 사전등록 §1 "데이터 완결성(엄격)" · §3-1 · 설계 C1·C2·C18) — 전략과 무관한 순수 함수.

- **완전한 mark 날**: 그 UTC 날의 정렬된 분 00:00…23:59마다 봉이 **정확히 하나**, mark 4필드가 전부 유한 Decimal.
  같은 open_ms 중복은 준비 단계(`prepare_t2`)가 없앤다 — 여기서 보이면 `ValueError`.
- **V_A**(창 안 날 d): d와 d−1이 완전한 mark 날 ∧ d 08:00·16:00 버킷 [b, b+60,000)에 확정 펀딩 이벤트가 있다.
- **V_B**: V_A ∧ d−21…d−2가 전부 완전한 mark 날.
- 범위 이력(R_d)은 **완전한 mark 날마다** 존재한다(C1) — 펀딩 때문에 무효인 날도 다음 날의 R_{d−1}을 준다(전략이 같은 정의로 계산).
- 워밍업 날(창 이전)은 V 집합에 들어가지 않는다. 전진 페이퍼에는 쓰지 않는다(§1 · 결손 = G-F 실행 결함).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backtest.data import Bar1m, Funding

MIN = 60_000
DAY = 86_400_000
HOUR = 3_600_000
MARK = ("mark_open", "mark_high", "mark_low", "mark_close")
B_WINDOW = range(2, 22)                         # d−2 … d−21(20일)


def _finite(v: str) -> bool:
    try:
        return Decimal(v).is_finite()
    except (InvalidOperation, ValueError, TypeError):
        return False


def complete_mark_days(bars: Iterable[Bar1m]) -> set[int]:
    per: dict[int, set[int]] = defaultdict(set)
    bad: set[int] = set()
    seen: set[int] = set()
    for b in bars:
        if b.open_ms in seen:
            raise ValueError(f"중복 open_ms {b.open_ms} — 준비 단계에서 없어져야 한다")
        seen.add(b.open_ms)
        di = b.open_ms // DAY
        if b.open_ms % MIN or not all(_finite(getattr(b, k)) for k in MARK):
            bad.add(di)
            continue
        per[di].add((b.open_ms % DAY) // MIN)
    return {di for di, mins in per.items() if len(mins) == 1440 and di not in bad}


def funding_boundaries(fundings: Iterable[Funding]) -> set[int]:
    """확정 펀딩 이벤트가 있는 분 버킷의 시작 시각."""
    return {f.funding_ms - f.funding_ms % MIN for f in fundings}


@dataclass
class Validity:
    v_a: set[int]
    v_b: set[int]
    complete: set[int]
    reasons: dict[int, list[str]] = field(default_factory=dict)      # A 무효 사유(창 안 날)
    reasons_b: dict[int, list[str]] = field(default_factory=dict)    # A 유효지만 B 무효인 날

    def as_dict(self) -> dict[str, object]:
        return {"v_a": sorted(self.v_a), "v_b": sorted(self.v_b), "n_a": len(self.v_a), "n_b": len(self.v_b),
                "reasons": {str(k): v for k, v in sorted(self.reasons.items())},
                "reasons_b": {str(k): v for k, v in sorted(self.reasons_b.items())}}


def validity(bars: Sequence[Bar1m], fundings: Sequence[Funding], first_day: int, last_day: int) -> Validity:
    comp = complete_mark_days(bars)
    fb = funding_boundaries(fundings)
    v_a: set[int] = set()
    v_b: set[int] = set()
    reasons: dict[int, list[str]] = {}
    reasons_b: dict[int, list[str]] = {}
    for d in range(first_day, last_day + 1):
        why = []
        if d not in comp:
            why.append("missing_bars_d")
        if d - 1 not in comp:
            why.append("missing_bars_prev")
        if d * DAY + 8 * HOUR not in fb:
            why.append("missing_funding_08")
        if d * DAY + 16 * HOUR not in fb:
            why.append("missing_funding_16")
        if why:
            reasons[d] = why
            continue
        v_a.add(d)
        if all(d - k in comp for k in B_WINDOW):
            v_b.add(d)
        else:
            reasons_b[d] = ["missing_bars_window_b"]
    return Validity(v_a, v_b, comp, reasons, reasons_b)
