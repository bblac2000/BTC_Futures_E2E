"""트라이얼 #1 피처 — `params_version = sr_v1`(사전등록 §1 표 · 레지스트리 #18·#19). **증분 계산**(단계 2b).

전부 결정론적이고, 한 1m 봉이 마감될 때마다 그 시각까지의 정보만 쓴다.

| 피처 | 정의(사전등록) | 구현 메모 |
|---|---|---|
| ATR_1m(60) · ATR_15m(14) | Wilder: 첫 값 = 첫 n개 TR 평균, 이후 `(ATR·(n−1) + TR)/n` | Decimal |
| 15m·4h 버킷 | UTC 격자 · 마감 봉만 | #19 ⑨: 구성 분 ≥ 2/3면 있는 분으로 계산, 미만이면 **이전 값을 이어 쓰고** `bucket_incomplete` — 불완전 버킷은 ATR·스윙·TSMOM 계열에 **넣지 않는다** |
| 스윙 | 15m fractal k=3(좌우 각 3봉보다 **엄격히** 높/낮음) · 확정 = 스윙 봉 뒤 **3번째 15m 봉 마감** · 유효 48h · 무효화 = 15m 종가가 레벨 밖으로 0.25×ATR_15m **초과** | 저항(고점)은 종가 > 레벨 + 0.25·ATR, 지지(저점)는 종가 < 레벨 − 0.25·ATR |
| 볼륨 프로파일 | 마감 1m 봉의 quote volume 전부를 **종가 bin**에 · bin = 100 × tick · 창 = 결정 봉 종가 **직전까지** 마감된 1440봉(결정 봉 자신은 제외 — Codex "strictly before the decision close") · POC 동률 저가 · VA = POC에서 인접 bin 중 큰 쪽을 하나씩(동률 아래쪽) 누적 ≥ 70% · VAH = 포함 최상단 bin 상단 경계 · VAL = 최하단 bin 하단 경계 | quote volume은 **정수(10⁻⁵ USDT 단위)**로 누적 — 더하고 빼도 오차가 없어 동률 판정이 결정론적이다 |
| TSMOM_4h | `sign(close_4h[t] − close_4h[t−180])` · 4h 봉 마감 시각에만 갱신 | 완전한 4h 봉만 계열에 넣는다(#19 ⑨) |
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

import numpy as np

from backtest.data import MINUTE_MS, Bar1m

H_MS = 3_600_000


@dataclass(frozen=True)
class SrV1:
    swing_k: int = 3
    swing_valid_ms: int = 48 * H_MS
    invalidate_atr_mult: Decimal = Decimal("0.25")
    atr1_n: int = 60
    atr15_n: int = 14
    vp_window: int = 1440
    vp_bin_ticks: int = 100
    va_frac_num: int = 70                      # 70% — 정수 비교(누적·100 ≥ 총·70)
    tsmom_lookback: int = 180
    bucket_min_num: int = 2                    # ≥ 2/3
    bucket_min_den: int = 3


SR_V1 = SrV1()
QV_SCALE = Decimal(100_000)                    # quote volume → 정수(10⁻⁵ USDT)


# ── ATR ─────────────────────────────────────────────────────────────────────
class WilderATR:
    def __init__(self, n: int):
        self.n = n
        self.prev_close: Decimal | None = None
        self.seed: list[Decimal] = []
        self.value: Decimal | None = None

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal | None:
        tr = high - low if self.prev_close is None else max(high - low, abs(high - self.prev_close),
                                                            abs(low - self.prev_close))
        self.prev_close = close
        if self.value is None:
            self.seed.append(tr)
            if len(self.seed) == self.n:
                self.value = sum(self.seed, Decimal()) / self.n
            return self.value
        self.value = (self.value * (self.n - 1) + tr) / self.n
        return self.value


# ── 버킷(15m·4h) ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Bucket:
    open_ms: int
    close_ms: int
    n_minutes: int
    complete_enough: bool                      # 구성 분 ≥ 2/3
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class BucketAggregator:
    """1m 봉을 받아 k분 버킷을 낸다. 분이 하나도 없는 버킷도 `complete_enough=False`로 낸다(건너뛰지 않는다)."""

    def __init__(self, k: int, cfg: SrV1 = SR_V1):
        self.k, self.span = k, k * MINUTE_MS
        self.need = math.ceil(k * cfg.bucket_min_num / cfg.bucket_min_den)
        self.cur_start: int | None = None
        self.rows: list[Bar1m] = []

    def _emit(self, start: int, rows: list[Bar1m]) -> Bucket:
        if not rows:
            z = Decimal(0)
            return Bucket(start, start + self.span - 1, 0, False, z, z, z, z)
        return Bucket(start, start + self.span - 1, len(rows), len(rows) >= self.need, rows[0].d("open"),
                      max(r.d("high") for r in rows), min(r.d("low") for r in rows), rows[-1].d("close"))

    def push(self, b: Bar1m) -> list[Bucket]:
        s = b.open_ms // self.span * self.span
        out: list[Bucket] = []
        if self.cur_start is None:
            self.cur_start = s
        elif s != self.cur_start:
            out.append(self._emit(self.cur_start, self.rows))
            gap = self.cur_start + self.span
            while gap < s:                                   # 통째로 빈 버킷
                out.append(self._emit(gap, []))
                gap += self.span
            self.cur_start, self.rows = s, []
        self.rows.append(b)
        if b.open_ms + MINUTE_MS == self.cur_start + self.span:   # 버킷 마지막 분이 마감 → 바로 낸다
            out.append(self._emit(self.cur_start, self.rows))
            self.cur_start, self.rows = None, []
        return out


# ── 스윙 ─────────────────────────────────────────────────────────────────────
@dataclass
class SwingLevel:
    level_id: int
    kind: str                                  # "swing_high"(저항) · "swing_low"(지지)
    price: Decimal
    bar_open_ms: int                           # 스윙 봉(15m) 시작
    confirmed_ms: int                          # 3번째 뒤 봉 마감 시각 — 이때부터 사용
    expires_ms: int                            # confirmed + 48h(배타)
    invalidated_ms: int | None = None

    def active(self, t: int) -> bool:
        return self.confirmed_ms <= t < self.expires_ms and (self.invalidated_ms is None or t < self.invalidated_ms)


class SwingTracker:
    def __init__(self, cfg: SrV1 = SR_V1):
        self.cfg = cfg
        self.win: deque[Bucket] = deque(maxlen=2 * cfg.swing_k + 1)
        self.levels: list[SwingLevel] = []
        self._next_id = 0

    def on_bucket(self, b: Bucket, atr15: Decimal | None) -> list[SwingLevel]:
        """완전한 15m 버킷만 넘긴다. 새로 확정된 레벨을 돌려준다. 무효화는 이 버킷 종가로 판정."""
        if atr15 is not None:
            band = self.cfg.invalidate_atr_mult * atr15
            for lv in self.levels:
                if lv.invalidated_ms is None and lv.confirmed_ms <= b.close_ms < lv.expires_ms:
                    if (lv.kind == "swing_high" and b.close > lv.price + band) or \
                            (lv.kind == "swing_low" and b.close < lv.price - band):
                        lv.invalidated_ms = b.close_ms                # 이 15m 마감 시각의 결정부터 무효
        self.win.append(b)
        new: list[SwingLevel] = []
        k = self.cfg.swing_k
        if len(self.win) == 2 * k + 1:
            mid = self.win[k]
            others = [x for i, x in enumerate(self.win) if i != k]
            conf = b.close_ms                                         # 3번째 뒤 봉 마감 시각의 결정부터 사용
            if all(mid.high > x.high for x in others):
                new.append(self._add("swing_high", mid.high, mid.open_ms, conf))
            if all(mid.low < x.low for x in others):
                new.append(self._add("swing_low", mid.low, mid.open_ms, conf))
        cutoff = b.close_ms - self.cfg.swing_valid_ms
        self.levels = [lv for lv in self.levels if lv.expires_ms > cutoff]
        return new

    def _add(self, kind: str, price: Decimal, bar_open_ms: int, conf: int) -> SwingLevel:
        lv = SwingLevel(self._next_id, kind, price, bar_open_ms, conf, conf + self.cfg.swing_valid_ms)
        self._next_id += 1
        self.levels.append(lv)
        return lv

    def active(self, t: int) -> list[SwingLevel]:
        return [lv for lv in self.levels if lv.active(t)]


# ── 볼륨 프로파일(24h 롤링 · 정수) ──────────────────────────────────────────────
@dataclass(frozen=True)
class VP:
    poc: Decimal
    vah: Decimal
    val: Decimal


class RollingVP:
    """창 = 직전 `window`개 마감 1m 봉(결정 봉 제외). bin 인덱스 = floor(종가 / bin)."""

    def __init__(self, tick: Decimal, lo_price: Decimal, hi_price: Decimal, cfg: SrV1 = SR_V1):
        self.cfg = cfg
        self.bin = tick * cfg.vp_bin_ticks
        self.base = int((lo_price / self.bin).to_integral_value(rounding=ROUND_FLOOR)) - 2
        top = int((hi_price / self.bin).to_integral_value(rounding=ROUND_FLOOR)) + 2
        self.vol = np.zeros(top - self.base + 1, dtype=np.int64)
        self.queue: deque[tuple[int, int]] = deque()          # (bin, 정수 거래대금)
        self.total = 0
        self.lo_bin = self.hi_bin = -1                          # 거래량이 있는 bin 범위(인덱스)

    def _idx(self, close: Decimal) -> int:
        return int((close / self.bin).to_integral_value(rounding=ROUND_FLOOR)) - self.base

    def push(self, b: Bar1m) -> None:
        """봉 b가 마감됐다 → 다음 결정부터 창에 들어간다."""
        i = self._idx(b.d("close"))
        q = int(b.d("quote_volume") * QV_SCALE)
        self.vol[i] += q
        self.total += q
        self.queue.append((i, q))
        if len(self.queue) > self.cfg.vp_window:
            j, r = self.queue.popleft()
            self.vol[j] -= r
            self.total -= r
        self._refresh_range()

    def _refresh_range(self) -> None:
        nz = np.flatnonzero(self.vol)
        if nz.size:
            self.lo_bin, self.hi_bin = int(nz[0]), int(nz[-1])

    @property
    def ready(self) -> bool:
        return len(self.queue) == self.cfg.vp_window and self.total > 0

    def value(self) -> VP | None:
        if not self.ready:
            return None
        lo, hi = self.lo_bin, self.hi_bin
        seg = self.vol[lo:hi + 1]
        p = int(np.argmax(seg))                                  # 첫 최대 = 가장 낮은 가격(동률 저가)
        vols = seg.tolist()
        a = b = p
        acc = vols[p]
        need = self.total * self.cfg.va_frac_num
        n = len(vols)
        while acc * 100 < need:
            up = vols[b + 1] if b + 1 < n else -1
            dn = vols[a - 1] if a - 1 >= 0 else -1
            if dn >= up:                                         # 동률이면 아래쪽
                a -= 1
                acc += dn
            else:
                b += 1
                acc += up
        base = self.base + lo
        return VP(poc=(base + p) * self.bin + self.bin / 2, vah=(base + b + 1) * self.bin, val=(base + a) * self.bin)


# ── TSMOM ───────────────────────────────────────────────────────────────────
class TSMOM:
    def __init__(self, cfg: SrV1 = SR_V1):
        self.closes: deque[Decimal] = deque(maxlen=cfg.tsmom_lookback + 1)
        self.value: int | None = None

    def on_bucket(self, b: Bucket) -> int | None:
        self.closes.append(b.close)
        if len(self.closes) == self.closes.maxlen:
            d = self.closes[-1] - self.closes[0]
            self.value = 1 if d > 0 else (-1 if d < 0 else 0)
        return self.value


# ── 조립: 1m 봉마다 피처 행 ────────────────────────────────────────────────────
@dataclass
class FeatureRow:
    bar_open_ms: int
    values: dict[str, Decimal | None]


@dataclass
class FeatureEngine:
    tick: Decimal
    lo_price: Decimal
    hi_price: Decimal
    cfg: SrV1 = field(default_factory=lambda: SR_V1)

    def __post_init__(self) -> None:
        self.atr1 = WilderATR(self.cfg.atr1_n)
        self.atr15 = WilderATR(self.cfg.atr15_n)
        self.b15 = BucketAggregator(15, self.cfg)
        self.b240 = BucketAggregator(240, self.cfg)
        self.swings = SwingTracker(self.cfg)
        self.vp = RollingVP(self.tick, self.lo_price, self.hi_price, self.cfg)
        self.tsmom = TSMOM(self.cfg)
        self.swing_events: list[SwingLevel] = []

    def step(self, b: Bar1m) -> FeatureRow:
        """봉 b가 마감된 직후의 피처(결정 시각 = b 마감). VP는 b를 넣기 **전** 값(결정 봉 제외)."""
        vp = self.vp.value()
        a1 = self.atr1.update(b.d("high"), b.d("low"), b.d("close"))
        row: dict[str, Decimal | None] = {"atr_1m": a1, "vp_poc": vp.poc if vp else None,
                                          "vp_vah": vp.vah if vp else None, "vp_val": vp.val if vp else None}
        for bk in self.b15.push(b):
            row["bucket_incomplete_15m"] = Decimal(0 if bk.complete_enough else 1)
            if bk.complete_enough:
                a15 = self.atr15.update(bk.high, bk.low, bk.close)
                row["atr_15m"] = a15
                self.swing_events += self.swings.on_bucket(bk, a15)
            else:
                row["atr_15m"] = self.atr15.value                 # 이어 쓰기(#19 ⑨)
        for bk in self.b240.push(b):
            row["bucket_incomplete_4h"] = Decimal(0 if bk.complete_enough else 1)
            v = self.tsmom.on_bucket(bk) if bk.complete_enough else self.tsmom.value
            row["tsmom_4h"] = None if v is None else Decimal(v)
        self.vp.push(b)
        return FeatureRow(b.open_ms, row)


def run(bars: list[Bar1m], tick: Decimal, cfg: SrV1 = SR_V1) -> tuple[list[FeatureRow], list[SwingLevel]]:
    """전 구간 피처 행(1m마다) + 확정된 스윙 레벨(무효화 시각 포함). 결정 시각 = 각 1m 봉 마감(open_ms + 59,999)."""
    lo = min(b.d("close") for b in bars)
    hi = max(b.d("close") for b in bars)
    eng = FeatureEngine(tick, lo, hi, cfg)
    rows = [eng.step(b) for b in bars]
    return rows, eng.swing_events
