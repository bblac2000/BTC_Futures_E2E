"""트라이얼 #4 판정 가능 술어((c) · 규약 B15~B20 · 사전등록 r3 §1 "표본 규칙" · 결정 7·16·17).

`Eligibility(bars, fundings)(t)` — t = 체결 봉 open_ms(= 결정 시각 T + 1분). 원판·P2·P3는 원판 체결 t에서, P1은 자기 무작위 시작 t에서
**같은 함수**를 부른다. 미래 구간을 보는 백테스트 표본 필터다 — 실시간 진입 조건이 아니다(전진 규칙은 r3 §3-3).

검사 순서(고정 · 첫 실패 사유만): ① window_start: t < 창 시작 ② window_end: t + 6일 > 창 끝(분 시작 시각 비교) ③ mark_incomplete:
닫힌 [t, t + 6일]의 8,641분이 각각 정확히 한 번 · mark 4필드 유한 양수 ④ atr_days: day(t) 앞 14 UTC 날 완전 ⑤ funding: 반열린
(t, t + 6일]의 경계 18개마다 그 분 버킷에 확정 펀딩 정확히 1건 — **체결 분이 경계여도 그 경계는 요구하지 않는다**(결정 17 ·
트라이얼 #3 `Admissibility`의 닫힌 구간과 의도적으로 다르다). 격자 밖 펀딩 기록은 보지 않는다.

`_finite_pos` · `complete_days`는 import하지 않고 **복사**했다(출처: strategies/trial03/harness.py @ 8b8f103 · 바꾼 것 없음 —
(a)의 정적 시험이 `strategies.trial03.harness` import를 막는다).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

import numpy as np

from backtest.data import MINUTE_MS, Bar1m, Funding
from strategies.trial04 import anchor as A
from strategies.trial04.exit_schedule import EVAL_SPAN_MIN

DAY = 86_400_000
SPAN_MS = EVAL_SPAN_MIN * MINUTE_MS                        # 6일
N_BOUNDARIES = SPAN_MS // A.H8_MS                          # 18
ATR_DAYS = 14                                              # r3 §1 ATR_1d(14): 결정일 전날까지 완전한 14일
REASONS = ("window_start", "window_end", "mark_incomplete", "atr_days", "funding")


def _finite_pos(v: str) -> bool:
    try:
        x = Decimal(v)
    except (InvalidOperation, ValueError):
        return False
    return x.is_finite() and x > 0


def complete_days(bars: Sequence[Bar1m]) -> set[int]:
    """(복사 · harness @ 8b8f103) 완전한 mark 날 = 정렬 분 1,440개가 **한 번씩**(중복 분이 있으면 그 날은 완전하지 않다) · mark 4필드 유한 양수."""
    per: dict[int, list[int]] = defaultdict(list)
    bad: set[int] = set()
    for b in bars:
        d = b.open_ms // DAY
        if b.open_ms % MINUTE_MS or not all(_finite_pos(x) for x in (b.mark_open, b.mark_high, b.mark_low, b.mark_close)):
            bad.add(d)
            continue
        per[d].append(b.open_ms)
    return {d for d, s in per.items() if len(s) == 1440 and len(set(s)) == 1440 and d not in bad}


def boundaries(t: int) -> list[int]:
    """반열린 (t, t + 6일] 안의 펀딩 경계(00/08/16 UTC) — 어떤 t에서도 정확히 18개."""
    b0 = (t // A.H8_MS + 1) * A.H8_MS
    bs = [b0 + k * A.H8_MS for k in range(N_BOUNDARIES)]
    assert t < bs[0] and bs[-1] <= t + SPAN_MS < bs[-1] + A.H8_MS, (t, bs[0], bs[-1])
    return bs


class Eligibility:
    def __init__(self, bars: Sequence[Bar1m], fundings: Sequence[Funding], *, window_start: int = A.WINDOW_START_MS,
                 window_end: int = A.IS_END_MS):
        self.window_start, self.window_end = window_start, window_end
        self.days = complete_days(bars)
        self.fund: Counter[int] = Counter(f.funding_ms - f.funding_ms % MINUTE_MS for f in fundings)
        #  유효 분 = 분 격자 위 · mark 4필드 유한 양수 · 그 분의 봉이 정확히 하나 → 누적 합으로 구간 개수를 O(1)에 센다
        seen: Counter[int] = Counter()
        bad: set[int] = set()
        for b in bars:
            m = b.open_ms - b.open_ms % MINUTE_MS
            seen[m] += 1
            if b.open_ms % MINUTE_MS or not all(_finite_pos(x) for x in (b.mark_open, b.mark_high, b.mark_low, b.mark_close)):
                bad.add(m)
        self._first = min(seen) if seen else 0
        n = (max(seen) - self._first) // MINUTE_MS + 1 if seen else 0
        ok = np.zeros(n, dtype=np.int64)
        for m, c in seen.items():
            if c == 1 and m not in bad:
                ok[(m - self._first) // MINUTE_MS] = 1
        self._cum = np.concatenate(([0], np.cumsum(ok)))

    def _valid_minutes(self, lo: int, hi: int) -> int:
        """닫힌 [lo, hi](분 격자) 안의 유효 분 개수 — 입력 범위 밖은 0으로 센다."""
        i = max(0, (lo - self._first) // MINUTE_MS)
        j = min(len(self._cum) - 1, (hi - self._first) // MINUTE_MS + 1)
        return int(self._cum[j] - self._cum[i]) if j > i else 0

    def __call__(self, t: int) -> str | None:
        if t % MINUTE_MS:
            raise ValueError(f"t={t}: 분 격자가 아니다")
        hi = t + SPAN_MS
        if t < self.window_start:
            return "window_start"
        if hi > self.window_end:
            return "window_end"
        if self._valid_minutes(t, hi) != EVAL_SPAN_MIN + 1:
            return "mark_incomplete"
        d = t // DAY
        if any(x not in self.days for x in range(d - ATR_DAYS, d)):
            return "atr_days"
        if any(self.fund[b] != 1 for b in boundaries(t)):
            return "funding"
        return None
