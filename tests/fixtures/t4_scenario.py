"""트라이얼 #4 (d) 합성 시나리오 — 평평한 60,000 가격 + 날마다 범위 봉 하나(ATR 제어) + 인쇄 목록(분포 제어). 실데이터 아님.

- 봉: D0(2024-03-01 00:00Z · 합성 날짜)부터 n_days일 · 날마다 12:00 봉이 고가 60,000 + x · 저가 60,000 − x → TR = 2x · ATR = 2x ·
  sl_dist = 2·ATR / 60,000 = 4x / 60,000(x = 900 → 6% → L = 10).
- 인쇄: D0 앞 `prior`개(작은 결정론적 값 — 분포) + 창 안은 기본 0.0(띠 안) · `over`로 극단(S +1e-3 · L −1e-3) 등을 덮어쓴다.
- 기본 사건: T_E = D0 + 16일 08:00(앞 14일 + d − 15 종가가 차는 뒤) · 체결 T_E + 1분 · 시간 청산 + 7,200분.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backtest.data import MINUTE_MS, Bar1m, Funding
from exchange.loader import rules_from_snapshot_dir
from strategies.trial04 import anchor as A
from strategies.trial04 import harness as H
from strategies.trial04.config import TC_V3, TcParams
from strategies.trial04.strategy import BASE, Variant

ROOT = Path(__file__).resolve().parent.parent.parent
RULES = rules_from_snapshot_dir(ROOT / A.RULES_SNAPSHOT_DIR, "BTCUSDT")
M = MINUTE_MS
DAY = 86_400_000
H8 = A.H8_MS
D0 = 1_709_251_200_000                                     # 2024-03-01 00:00Z
T_E = D0 + 16 * DAY + H8
EXT = {"S": 1e-3, "L": -1e-3}
RATE, FMARK = "0.0001", "60000"


def bar(ms: int, o: str = "60000", lo: str | None = None, hi: str | None = None, c: str | None = None) -> Bar1m:
    low, high, close = lo or o, hi or o, c or o
    return Bar1m(ms, o, high, low, close, "1", o, 1, "0", "0", o, high, low, close, "archive")


@dataclass
class Scenario:
    arm: str = "S"
    n_days: int = 30
    x: int = 900
    prior: int = 300
    over: dict[int, float] | None = None                   # T → p(None이면 {T_E: 극단})
    invalid: set[int] = field(default_factory=set)
    incomplete: set[int] = field(default_factory=set)
    drop: set[int] = field(default_factory=set)            # 없는 봉(open_ms)
    bar_over: dict[int, Bar1m] = field(default_factory=dict)
    no_funding: set[int] = field(default_factory=set)

    @property
    def window(self) -> tuple[int, int]:
        return D0, D0 + self.n_days * DAY - 1

    def bars(self) -> list[Bar1m]:
        out = []
        for i in range(self.n_days * 1440):
            ms = D0 + i * M
            if ms in self.drop:
                continue
            if ms in self.bar_over:
                out.append(self.bar_over[ms])
            elif i % 1440 == 720:
                out.append(bar(ms, hi=str(60000 + self.x), lo=str(60000 - self.x)))
            else:
                out.append(bar(ms))
        return out

    def fundings(self) -> list[Funding]:
        return [Funding(D0 + k * H8, RATE, FMARK) for k in range(self.n_days * 3) if D0 + k * H8 not in self.no_funding]

    def prints(self) -> list[dict[str, Any]]:
        over = {T_E: EXT[self.arm]} if self.over is None else self.over
        out = []
        for k in range(-self.prior, self.n_days * 3):
            t = D0 + k * H8
            if t in self.invalid:
                out.append({"T": t, "p": None, "n_minutes": 474, "valid": False, "complete": False})
                continue
            p = over.get(t, ((k * 37) % 101 - 50) * 1e-6 if k < 0 else 0.0)
            n = 479 if t in self.incomplete else 480
            out.append({"T": t, "p": repr(float(p)), "n_minutes": n, "valid": True, "complete": n == 480})
        return out


def run(sc: Scenario, variant: Variant = BASE, p: TcParams = TC_V3, eligible: Any = None) -> H.T4Run:
    return H.run_arm_with_fixture_rules(sc.bars(), sc.fundings(), sc.prints(), sc.arm, variant, rules=RULES, p=p, window=sc.window,
                                        eligible=eligible)


def lines(r: H.T4Run, kind: str) -> list[dict[str, Any]]:
    return [e for e in r.strategy.events if e["kind"] == kind]


def digest(r: H.T4Run) -> str:
    blob = json.dumps({"events": r.strategy.events, "trades": r.trades, "funnel": dict(r.strategy.funnel),
                       "sub": dict(r.strategy.sub), "entry": dict(r.strategy.entry)}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
