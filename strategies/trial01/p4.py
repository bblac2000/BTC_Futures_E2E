"""P4 무작위 레벨 플라시보(사전등록 §4 P4 행 · 레지스트리 #22) — 정본 전략·엔진 사슬을 그대로 두고 **레벨만** 바꾼다.

`P4Feed`는 정본 `EngineFeed`를 감싸 스냅샷의 레벨(스윙·VP)만 무작위 레벨로 바꾼다. ATR·TSMOM·봉은 정본 그대로다.
전략(`Trial01`)은 바뀌지 않는다 — 터치·확인·필터·쿨다운·**SL 앵커(바뀐 스윙)**·sl_dist 바닥/천장·TP 모두 같은 코드.

## 무작위화 규칙(사용자 2026-09-21 · #22)
- **스윙**: 정본 스윙 하나당 무작위 레벨 하나(1:1) — 같은 level_id·종류·확정 시각·만료(확정 + 48h)·**같은 무효화 규칙**
  (완전 15m 버킷 종가가 무작위 가격 밖으로 0.25 × ATR_15m 초과 → 그 버킷 마감부터 무효 · 정본과 같은 순서: 무효화 판정 뒤 새 레벨).
  가격 = **확정 시각 기준 직전 24시간 마감 1m**(kline last) 저가~고가의 tick 격자 균등추출 · 난수 = `anchor.P4_SEED`에서 spawn한
  추출 d 스트림(`placebo.p4_rng(d)`)을 확정 순서(확정 시각, level_id)대로 소비.
- **VP**(POC·VAH·VAL): **매 분 3개를 새로** — 그 분 시작 기준 직전 24시간 마감 1m 저가~고가(결정 봉 제외 · 정본 VP와 같은 정보 시점)에서
  tick 격자 균등추출 3회 → 정렬해 VAL ≤ POC ≤ VAH로 이름 붙임 · 난수 = `SeedSequence([20260921, 4, d, minute_index])`
  (minute_index = 봉 시작 UTC ms // 60,000). 🔎 **추출 번호 d를 넣었다** — 사용자 문언 (20260921, 4, minute_index)만 쓰면
  200회 추출의 VP 레벨이 모두 같아진다(추출끼리 다른 것은 스윙뿐). 정본 VP가 아직 없으면(워밍업 부족) 무작위 VP도 없다.
- 창 = 시간 기준 24시간(봉 수가 아니라) · 워밍업 봉에서도 같은 규칙으로 무작위 레벨을 만든다(창 첫 분에 유효한 스윙이 있게).
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from decimal import Decimal

import numpy as np

from backtest.data import MINUTE_MS, Bar1m
from backtest.placebo import p4_rng, tick_uniform
from strategies.trial01 import anchor as A
from strategies.trial01.features import VP, SwingLevel
from strategies.trial01.strategy import EngineFeed, Snapshot

DAY_MS = 24 * 3_600_000


def vp_rng(draw: int, minute_index: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([*A.P4_SEED, draw, minute_index])))


class _Range24h:
    """마감 1m 봉(kline last)의 시간 기준 24h 저가~고가 — 단조 덱(분마다 O(1)) + 임의 시각 조회(스캔)."""

    def __init__(self) -> None:
        self.bars: deque[tuple[int, Decimal, Decimal]] = deque()        # (open_ms, high, low)
        self.mx: deque[tuple[int, Decimal]] = deque()
        self.mn: deque[tuple[int, Decimal]] = deque()

    def push(self, b: Bar1m) -> None:
        h, lo = b.d("high"), b.d("low")
        self.bars.append((b.open_ms, h, lo))
        while self.mx and self.mx[-1][1] <= h:
            self.mx.pop()
        self.mx.append((b.open_ms, h))
        while self.mn and self.mn[-1][1] >= lo:
            self.mn.pop()
        self.mn.append((b.open_ms, lo))

    def as_of_open(self, open_ms: int) -> tuple[Decimal, Decimal] | None:
        """분 `open_ms` 시작 시점: 마감 시각이 (open_ms − 24h, open_ms) 안인 봉 = open ∈ [open_ms − 24h, open_ms − 1분]."""
        lo_open = open_ms - DAY_MS
        while self.mx and self.mx[0][0] < lo_open:
            self.mx.popleft()
        while self.mn and self.mn[0][0] < lo_open:
            self.mn.popleft()
        if not self.mx:
            return None
        return self.mn[0][1], self.mx[0][1]

    def prune_before(self, keep_open_ms: int) -> None:
        """시각 조회(`as_of_close`)용 봉 이력 — `keep_open_ms` 이전 봉만 버린다(단조 덱과 별개)."""
        while self.bars and self.bars[0][0] < keep_open_ms:
            self.bars.popleft()

    def as_of_close(self, t_ms: int) -> tuple[Decimal, Decimal] | None:
        """시각 t(봉 마감 = open + 59,999): 마감 시각이 (t − 24h, t]인 봉. 늦은 버킷 방출 때 t가 현재 봉보다 앞설 수 있다."""
        sel = [(h, lo) for o, h, lo in self.bars if t_ms - DAY_MS < o + MINUTE_MS - 1 <= t_ms]
        if not sel:
            return None
        return min(lo for _, lo in sel), max(h for h, _ in sel)


class P4Feed:
    def __init__(self, inner: EngineFeed, draw: int, tick: Decimal):
        if not 0 <= draw < A.P4_DRAWS:
            raise ValueError(f"P4 추출 번호는 0..{A.P4_DRAWS - 1}: {draw}")
        self.inner, self.fe, self.draw, self.tick = inner, inner.fe, draw, tick
        self.rng = p4_rng(draw)
        self.range = _Range24h()
        self.randoms: list[SwingLevel] = []
        self.by_real: dict[int, SwingLevel] = {}
        self._seen = 0
        self.last_vp: VP | None = None

    @property
    def last_row(self) -> dict[str, Decimal | None]:
        return self.inner.last_row

    def step(self, bar: Bar1m) -> Snapshot:
        vp_range = self.range.as_of_open(bar.open_ms)           # 이 봉을 넣기 전 = 결정 봉 제외
        snap = self.inner.step(bar)                             # 정본 피처(ATR·TSMOM·정본 스윙 확정/무효화)
        self.range.push(bar)                                    # 이제 이 봉 마감까지 포함(확정 시각 조회용)
        new = self.fe.swing_events[self._seen:]
        self._seen = len(self.fe.swing_events)
        for bk, a15 in self.fe.b15_complete:                    # 정본 on_bucket 순서: 무효화 → 새 레벨
            if a15 is not None:
                band = self.fe.cfg.invalidate_atr_mult * a15
                for lv in self.randoms:
                    if lv.invalidated_ms is None and lv.confirmed_ms <= bk.close_ms < lv.expires_ms:
                        if (lv.kind == "swing_high" and bk.close > lv.price + band) or \
                                (lv.kind == "swing_low" and bk.close < lv.price - band):
                            lv.invalidated_ms = bk.close_ms
            for real in sorted((x for x in new if x.confirmed_ms == bk.close_ms), key=lambda x: x.level_id):
                rng = self.range.as_of_close(real.confirmed_ms)
                assert rng is not None, "확정 시각 직전 24h 봉이 없다"
                rnd = SwingLevel(real.level_id, real.kind, tick_uniform(self.rng, rng[0], rng[1], self.tick),
                                 real.bar_open_ms, real.confirmed_ms, real.expires_ms)
                self.randoms.append(rnd)
                self.by_real[real.level_id] = rnd
            cutoff = bk.close_ms - self.fe.cfg.swing_valid_ms
            self.randoms = [lv for lv in self.randoms if lv.expires_ms > cutoff]
        #  이력 보존(Codex 단계 d 후속 #6): 아직 내지 않은 15m 버킷(늦은 방출 가능)의 확정 시각 t까지 조회할 수 있게,
        #  그 버킷 마감 − 24h − 1분 이전 봉만 버린다(긴 결손 뒤 늦게 나오는 버킷도 창이 남아 있다).
        pending = self.fe.b15.cur_start if self.fe.b15.cur_start is not None else bar.open_ms + MINUTE_MS
        self.range.prune_before(pending + self.fe.b15.span - 1 - DAY_MS - MINUTE_MS)
        if len(self.by_real) != len(self.fe.swing_events):
            raise AssertionError("정본 스윙과 무작위 스윙이 1:1이 아니다")
        vp = None
        if snap.vp is not None and vp_range is not None:
            g = vp_rng(self.draw, bar.open_ms // MINUTE_MS)
            val, poc, vah = sorted(tick_uniform(g, vp_range[0], vp_range[1], self.tick) for _ in range(3))
            vp = VP(poc, vah, val)
        self.last_vp = vp
        close_ms = bar.open_ms + MINUTE_MS - 1
        return replace(snap, vp=vp, swings_open=tuple(lv for lv in self.randoms if lv.active(bar.open_ms)),
                       swings_close=tuple(lv for lv in self.randoms if lv.active(close_ms)))
