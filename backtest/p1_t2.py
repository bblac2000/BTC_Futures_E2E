"""트라이얼 #2 P1(단계 2f F2 · 사전등록 §4 P1 행) — 규약 (a)~(f) + 같은 날 적격 제약. 전략 모듈을 import하지 않는다.

- 적격 진입 분(h) = 유효일 d ∈ V_A(오름차순)마다 t = d·일 + m·분, m ∈ [0, 1439 − h] 를 이어 붙인 목록 —
  t와 t+h−1이 같은 UTC 날 · t+h−1 ≤ 23:58 · V_A 날은 1,440분이 다 있다. h ≥ 1440 → 빈 목록(슬롯 실패 · 난수 없음).
- 사이징·실행 = #36 규칙(`harness.load_rules` — 호출자가 넘긴다) · `config.LIMITS`((10,30) · 청산가 기준 수수료) · E_ref 1,000 ·
  `config.P1_REGIME` · 시간 청산 사유 TIME_EXIT(G6) · 설정 = `P1Config(20260924, 1000, 1000, 10)`(G2 · 기본값 없음).
- 원판 Arm A가 0건이면 계산 불가(G5) — 귀무분포를 만들지 않는다.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from backtest import p1_core as C
from backtest import placebo_exec as PX
from backtest.data import MINUTE_MS, Bar1m, Funding
from exchange.rules import RuntimeRules
from paper.types import ExitReason
from strategies.trial02 import anchor as A
from strategies.trial02.config import BO_V1, LIMITS, P1_REGIME

DAY = A.DAY_MS
LAST_EXIT_MINUTE = 1438
CFG = C.P1Config(master_seed=A.MASTER_SEED, draws=A.P1_DRAWS, slot_attempts=1000, fail_limit=A.P1_FAIL_MAX)


class SameDayEligible:
    """h별 적격 진입 분의 게으른 오름차순 보기(목록을 만들지 않는다)."""

    def __init__(self, days: Sequence[int], h: int):
        self.days = sorted(days)
        self.per = max(0, LAST_EXIT_MINUTE - (h - 1) + 1)     # m ∈ [0, 1439 − h]

    def __len__(self) -> int:
        return len(self.days) * self.per

    def __getitem__(self, j: int) -> int:
        if not 0 <= j < len(self):
            raise IndexError(j)
        d, m = divmod(j, self.per)
        return self.days[d] * DAY + m * MINUTE_MS


def draw(d: int, source: Sequence[C.SourceTrade], v_a: Sequence[int], bars: dict[int, Bar1m], rules: RuntimeRules) -> C.P1Draw:
    cache: dict[int, SameDayEligible] = {}

    def eligible_for(h: int) -> SameDayEligible:
        return cache.setdefault(h, SameDayEligible(v_a, h))

    def sizing_ok(t: int, direction: int, sl_dist: Decimal) -> bool:
        _, dec = PX.sizing_decision(bars[t].d("mark_open"), direction, sl_dist, rules, LIMITS, BO_V1.e_ref, P1_REGIME)
        return bool(dec.ok)

    return C.p1_draw_generic(d, CFG, source, eligible_for, sizing_ok)


def null_point(dr: C.P1Draw, bars: dict[int, Bar1m], fundings: Sequence[Funding], rules: RuntimeRules) -> dict[str, Any]:
    """성공한 추출 하나 → 트레이드당 평균 net_bps(Decimal 문자열) + 청산 사유 개수(보고)."""
    assert dr.ok
    nets: list[Decimal] = []
    reasons = {"time_exit": 0, "liquidation": 0}
    for p in dr.placed:
        r = PX.run_time_exit(bars, fundings, entry_ms=p.entry_ms, h=p.h, direction=p.direction, sl_dist=p.sl_dist, rules=rules,
                             limits=LIMITS, equity=BO_V1.e_ref, regime=P1_REGIME, reason=ExitReason.TIME_EXIT)
        if not r.ok or r.ret is None:
            raise AssertionError(f"추출 {dr.draw} 슬롯 {p.slot}: 배치 때 수락된 사이징이 실행에서 거부됐다")
        nets.append(r.ret.net_bps)
        reasons[r.reason] += 1
    return {"draw": dr.draw, "n": len(nets), "mean_net_bps": str(sum(nets, Decimal()) / len(nets)), "exits": reasons}
