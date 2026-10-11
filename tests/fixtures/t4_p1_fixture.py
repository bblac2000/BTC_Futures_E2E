"""트라이얼 #4 (e) P1 골든·교차 프로세스 결정론용 — 두 트레이드 합성 원판 · 추출 0..19(게이트 + timing). 실데이터 없음."""
from __future__ import annotations

import hashlib
import json
import sys

from backtest import p1_t4 as P
from tests.fixtures import t4_scenario as S

N_DAYS = 40


def scenario(arm: str) -> S.Scenario:
    e = S.EXT[arm]
    return S.Scenario(arm=arm, n_days=N_DAYS, over={S.T_E: e, S.T_E + 5 * S.DAY + S.H8: e, S.T_E + 5 * S.DAY + 3 * S.H8: e})


def part(arm: str, lo: int = 0, hi: int = 19) -> P.P1Part:
    sc = scenario(arm)
    r = S.run(sc)
    return P.run_range_with_fixture_rules(arm, r.trades, sc.bars(), sc.fundings(), lo, hi, rules=S.RULES, window=sc.window)


def digest(p: P.P1Part) -> str:
    blob = p.draws_json + json.dumps(p.null, sort_keys=True) + p.timing_draws_json + json.dumps(p.timing_null, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


if __name__ == "__main__":
    print(digest(part(sys.argv[1])))
