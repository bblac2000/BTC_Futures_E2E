"""트라이얼 #3 (e) P1 골든·교차 프로세스 결정론용 — 두 트레이드 합성 원판 · 추출 0..19. 실데이터 없음."""
from __future__ import annotations

import hashlib
import json
import sys

from backtest import p1_t3 as P
from tests.fixtures import t3_scenario as S


def part(arm: str) -> P.P1Part:
    sc = S.Scenario(arm=arm, flushes=[S.F_DEFAULT, S.F_DEFAULT + 715])
    r = S.run(sc)
    return P.run_range_with_fixture_rules(arm, r.trades, sc.bars(), sc.fundings(), 0, 19, rules=S.RULES, window=S.WINDOW)


def digest(p: P.P1Part) -> str:
    return hashlib.sha256((p.draws_json + json.dumps(p.null, sort_keys=True)).encode()).hexdigest()


if __name__ == "__main__":
    print(digest(part(sys.argv[1])))
