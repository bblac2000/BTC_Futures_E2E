"""트라이얼 #3 (d) 합성 시나리오 — 3일(날 0 = 워밍업 · 날 1~2 = 창) · 작은 매개변수(분위수 창 1일 · 최소 정의 1,000)만 바꾼 TfParams.

가격: 60000 + 3·sin(0.7 i)(분위수 ±0.01% 수준) · 고가/저가 = 종가 ± spread. 플러시(L = 급락 · S = 급등): 봉 F−9 … F에 1.5% 이동 +
큰 교대 잡음(rv 급등) → 이후 조용(냉각). OI: 5분 행, 기본 감소. 펀딩: 모든 00/08/16에 1건(율 0.0001). 실데이터 없음.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from backtest.data import MINUTE_MS, Bar1m, Funding
from exchange.loader import rules_from_snapshot_dir
from strategies.trial03.config import TF_V1, TfParams
from strategies.trial03.harness import T3Run, run_arm_with_fixture_rules
from strategies.trial03.strategy import BASE, Variant

ROOT = Path(__file__).resolve().parent.parent.parent
RULES = rules_from_snapshot_dir(ROOT / "tests" / "fixtures" / "snapshots", "BTCUSDT")
DAY = 86_400_000
DAY0 = int(dt.datetime(2025, 3, 1, tzinfo=dt.UTC).timestamp() * 1000)
N = 3 * 1440
WINDOW = (DAY0 + DAY, DAY0 + 3 * DAY - 1)
P = replace(TF_V1, w_ref_days=1, quantile_min_defined=1000)
F_DEFAULT = 1440 + 600                                              # 날 1 10:00 봉(마감 10:01)


def t_close(i: int) -> int:
    return DAY0 + i * MINUTE_MS + MINUTE_MS


@dataclass
class Scenario:
    arm: str = "L"
    flushes: list[int] = field(default_factory=lambda: [F_DEFAULT])
    move: float = 0.015
    spread: float = 100.0
    noise_until: dict[int, int] = field(default_factory=dict)       # 플러시 F → 교대 잡음이 계속되는 마지막 봉(기본 F)
    spread_from: dict[int, float] = field(default_factory=dict)     # 봉 i부터 spread 변경
    over: dict[int, dict[str, float]] = field(default_factory=dict) # 봉 i의 open/high/low/close 덮어쓰기(mark)
    drop: set[int] = field(default_factory=set)
    oi: str = "decreasing"                                           # decreasing | none | unusable | flat_then_decreasing
    oi_switch_ms: int = 0
    no_funding_at: set[int] = field(default_factory=set)

    def closes(self) -> list[float]:
        sgn = -1.0 if self.arm == "L" else 1.0
        out, level = [], 60000.0
        fl = sorted(self.flushes)
        for i in range(N):
            for f in fl:
                if f - 9 <= i <= f:
                    level = level * (1 + sgn * self.move / 10)
            c = level + (3 if i < 1440 else 1) * math.sin(0.7 * i)      # 창 날의 잡음은 워밍업 꼬리에 닿지 않는다
            for f in fl:
                if f - 9 <= i <= self.noise_until.get(f, f):
                    c *= 1 + (0.003 if i % 2 else -0.003)
            out.append(c)
        return out

    def bars(self) -> list[Bar1m]:
        cs = self.closes()
        out, sp = [], self.spread
        for i, c in enumerate(cs):
            if i in self.spread_from:
                sp = self.spread_from[i]
            o = cs[i - 1] if i else c
            h, lo = max(o, c) + sp, min(o, c) - sp
            ov = self.over.get(i, {})
            o, h, lo, c2 = ov.get("open", o), ov.get("high", h), ov.get("low", lo), ov.get("close", c)
            h, lo = max(h, o, c2), min(lo, o, c2)
            if i in self.drop:
                continue
            s = [f"{x:.1f}" for x in (o, h, lo, c2)]
            out.append(Bar1m(DAY0 + i * MINUTE_MS, s[0], s[1], s[2], s[3], "1", s[0], 1, "0", "0", s[0], s[1], s[2], s[3], "archive"))
        return out

    def fundings(self) -> list[Funding]:
        out = []
        for d in range(3):
            for h in (0, 8, 16):
                t = DAY0 + d * DAY + h * 3_600_000
                if t not in self.no_funding_at:
                    out.append(Funding(t, "0.0001", "60000"))
        return out

    def oi_rows(self) -> tuple[list[list[Any]], list[int]]:
        cs = [DAY0 - DAY + k * 300_000 for k in range(4 * 288)]
        if self.oi == "none":
            return [], []
        if self.oi == "unusable":
            return [], cs
        rows = []
        for k, c in enumerate(cs):
            if self.oi == "flat_then_decreasing" and c < self.oi_switch_ms:
                v = 1_000_000
            elif self.oi == "increasing":
                v = 1_000_000 + k
            else:
                v = 1_000_000 - k
            rows.append([c, str(v)])
        return rows, []


def run(sc: Scenario, variant: Variant = BASE, *, p: TfParams = P, rules=RULES, window=WINDOW) -> T3Run:
    rows, bad = sc.oi_rows()
    return run_arm_with_fixture_rules(sc.bars(), sc.fundings(), rows, bad, sc.arm, variant, rules=rules, p=p, window=window)


def digest(r: T3Run) -> str:
    blob = json.dumps({"trades": r.trades, "events": r.strategy.events, "funnel": dict(r.strategy.funnel),
                       "entry": dict(r.strategy.entry), "sub": dict(r.strategy.sub)}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def tails(r: T3Run) -> list[dict[str, Any]]:
    return [e for e in r.strategy.events if e["kind"] == "tail"]


def aborts(r: T3Run) -> list[str]:
    return [e["reason"] for e in r.strategy.events if e["kind"] == "abort"]


def rules_with(**kw: Any):
    return replace(RULES, symbol_rules=replace(RULES.symbol_rules, **{k: D(str(v)) for k, v in kw.items()}))


if __name__ == "__main__":                                          # 교차 프로세스 결정론 검사용
    import sys
    arm = sys.argv[1]
    print(digest(run(Scenario(arm=arm))))
