# ── PROVENANCE ─────────────────────────────────────────────────────────────
# Copied from: /home/cms/project/E2E_Hybrid_Bot/ops/delivery_counter.py
# Source commit: 98da74d (E2E HEAD f1e7d86, 2026-09-14) · copied 2026-09-15
# Local changes:
#   - DELIVERY / TS_COLUMN redefined for this bot's streams (kline1m_update, kline1m_close, markprice). E2E's #134
#     numbers are untouched in E2E; the values here are this repo's own pre-commitment
#     (docs/trial_registry.md row #1, 2026-09-15).
#   - removed E2E_COLLECT_DERIVS / derivs_from_env / enabled_kinds(derivs) (no public/market
#     switch here — this bot only uses the market tier). enabled_kinds() keeps the live filter.
#   - consumer table in the docstring rewritten for this repo; judgement rule, live adapter
#     and replay adapter are byte-identical in logic.
# ───────────────────────────────────────────────────────────────────────────
"""스트림별 **전달 감시** — 하나의 규칙, 두 어댑터.

## 왜 있나 (E2E 2026-09-12·#132·#133)

legacy WS URL이 `/market` 티어를 **구독 수락 후 조용히 버렸다**. E2E는 두 달 넘게 몰랐다.
🔴 **깨진 스트림의 증상은 예외가 아니라 "0"이다.** 예외는 시끄럽고 0은 조용하다.
그래서 *"얼마나 오래 안 왔나"*를 **명시적으로 재는** 장치가 필요하다.

## 🔴 판정 규칙은 `is_stalled()` 하나다

| 소비자(예정) | 어댑터 | 분류 |
|---|---|---|
| `data/` 수집기(layer 5) | **live**(`DeliveryCounter.observe()`) | 진행 중 사실 → `safety/` stale-data kill 입력 |
| `ops/` health(layer 8) | **shard 재생**(`scan_window()`) | 반복형 경보(고정 스로틀 키) |
| 일일 품질 요약(layer 8) | **shard 재생**(`silence_summary()`) | 하루 한 번 확정 사실 |

## 🔒 임계는 스트림별이고 `DELIVERY`가 유일한 출처다

🚫**결과를 본 뒤 여기 숫자를 고치지 않는다** — 바꾸려면 `docs/trial_registry.md` 행이 먼저다.

## 🔴 관측 시각은 수신 시각이 아니라 **shard에 실제로 저장되는 이벤트 시각**이다

라이터는 스트림마다 다른 열로 shard 경계를 정한다(`TS_COLUMN`). 라이브가 수신 시각을 보고
재생이 이벤트 시각을 보면 **두 시계를 비교하는 것**이라 우연히만 맞는다.

## 🚫 이 모듈이 하지 않는 것

- **fail-fast 하지 않는다.** 스트림 정지는 수집기 사망이 아니다(재연결이 처리한다).
- **대장에 쓰지 않는다**(SQLite 락 · E2E 2026-08-15 교훈).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BUCKET_MS = 60_000

#  스트림(라이터 kind) → shard 경계를 정하는 열. 재생 어댑터가 같은 값을 세게 한다.
#  🔴 layer 5 `ShardWriter(..., ts_index=...)`와 어긋나면 재생과 라이브가 **다른 시계**를 센다.
#     `kline_1m` 한 스트림이 kind 둘을 낸다(레지스트리 #1):
#       kline1m_update — 모든 push(x=false·x=true)의 이벤트 시각 `E`
#       kline1m_close  — 마감(x=true)만의 이벤트 시각 `E`
TS_COLUMN = {
    "kline1m_update": "event_time",
    "kline1m_close": "event_time",
    "markprice": "event_time",
}


@dataclass(frozen=True)
class DeliverySpec:
    """writer kind 하나의 전달 임계.

    🔴 **티어를 여기 적지 않는다**(E2E #134). 티어는 `ops.stream_tiers.StreamSpec`에만 있고
       `tier_of()`가 `classify_stream()`으로 **도출**한다. 티어 표가 둘이 되면 언젠가 갈라진다.
    """
    kind: str
    ws_suffix: str          # 구독하는 WS 스트림명의 심볼 뒤 부분
    grace_sec: int          # 이보다 오래 무수신이면 정지
    min_per_min: int        # 직전 **벽시계** 완결 분 최소 행 수(0 = 검사 안 함)
    live: bool = True       # 라이브 카운터가 볼 수 있는가(writer 스레드 파생이면 False)


#  🔒 레지스트리 #1 (2026-09-15 · 사용자 확정 · 이 봇의 스트림 데이터 관측 0건에서 커밋) — 숫자를 여기서 바꾸지 말 것.
#  - kline1m_update: 스트림 침묵 감지. 형성 중 push ~250ms(v6 §10)라 분당 1건은 느슨한 하한.
#  - kline1m_close : "업데이트는 오는데 봉이 안 닫힘" 감지. 🔴 min_per_min=0 — 마감은 분당 정확히 1회라
#    분당 규칙을 걸면 E=T(xx:59.999) 경계 흔들림 하나로 가짜 정지가 난다. 나이 규칙만(120초 = 마감 2회).
#  - markprice     : 2026-09-04 로컬 600초 실측 601틱·결손 0. E2E #134와 같은 (120초, 분당 1건).
DELIVERY: dict[str, DeliverySpec] = {s.kind: s for s in (
    DeliverySpec("kline1m_update", "@kline_1m", 120, 1),
    DeliverySpec("kline1m_close", "@kline_1m", 120, 0),
    DeliverySpec("markprice", "@markPrice@1s", 120, 1),
)}


def ws_stream(kind: str, symbol: str = "BTCUSDT") -> str:
    return f"{symbol.lower()}{DELIVERY[kind].ws_suffix}"


def tier_of(kind: str, symbol: str = "BTCUSDT") -> str:
    """티어는 **도출한다** — `StreamSpec`이 유일한 출처다."""
    from ops.stream_tiers import classify_stream
    return classify_stream(ws_stream(kind, symbol)).tier


def enabled_kinds(*, live: bool = False) -> tuple:
    """감시 대상 writer kind. `live=True`면 라이브 카운터가 볼 수 없는 파생 kind를 뺀다."""
    return tuple(k for k, s in DELIVERY.items() if not (live and not s.live))


def kinds_for_streams(streams, symbol: str = "BTCUSDT") -> tuple[tuple, tuple]:
    """WS 스트림명 목록 → (kind 튜플, 모르는 스트림 튜플). 한 스트림이 여러 kind를 낼 수 있다."""
    kinds, unknown = [], []
    for st in streams:
        hit = [k for k in DELIVERY if ws_stream(k, symbol) == st]
        if hit:
            kinds.extend(k for k in hit if k not in kinds)
        else:
            unknown.append(st)
    return tuple(kinds), tuple(unknown)


# ─────────────────────────── 판정 규칙 (단 하나) ───────────────────────────
def prev_minute_of(now_ms: int) -> int:
    return now_ms // BUCKET_MS - 1


def minute_covered(minute: int, start_ms: int) -> bool:
    """그 분 전체가 관측 시작 **이후**인가. 시작 전에 걸친 분은 0이어도 증거가 아니다."""
    return minute * BUCKET_MS >= start_ms


def is_stalled(kind: str, *, now_ms: int, start_ms: int,
               last_seen_ms: int | None, prev_minute_count: int | None) -> bool:
    """🔴 **판정 규칙은 여기 하나다.** 라이브·재생 모두 이 함수로 판정한다.

    - 한 번도 안 왔다: 관측 시작 후 `grace_sec`이 지났으면 정지. *"아직 한 건도 안 왔으니
      판단 보류"*로 영원히 두면 **켰는데 안 오는 그 경우**를 놓친다.
    - 마지막 수신이 `grace_sec`보다 오래됐다: 정지.
    - `min_per_min > 0`이고 직전 **벽시계** 완결 분의 행 수가 미달: 정지.
      ⚠️ E2E #134/B3 — *"관측이 있던 마지막 분"*을 보면 긴 침묵 뒤 1건이 오면 오래전
      60건을 보고 통과한다(검사가 사문화). 관측이 없던 분은 **0**이다.
    """
    spec = DELIVERY[kind]
    g = spec.grace_sec * 1000
    if last_seen_ms is None:
        return now_ms - start_ms > g
    if now_ms - last_seen_ms > g:
        return True
    return (spec.min_per_min > 0 and prev_minute_count is not None
            and prev_minute_count < spec.min_per_min)


# ─────────────────────────── 라이브 어댑터 ───────────────────────────
@dataclass
class _Bucket:
    minute: int = -1
    count: int = 0
    prev_minute: int = -1
    prev_count: int = 0
    last_seen_ms: int | None = None


@dataclass
class DeliveryCounter:
    """스트림별 분당 카운트. 🔴**스트림마다 독립**이다.

    E2E #132의 실패 형태가 *"하나만 0이고 나머지는 흐른다"*였다. 합산해서 *"뭐라도 왔으니
    정상"*이라 판정하면 **정확히 그 실패를 다시 못 본다.**
    ⚠️ 모르는 kind는 생성 시 `KeyError`다 — 임계 없는 스트림은 감시할 수 없다.
    """
    streams: tuple[str, ...]
    start_ms: int
    _b: dict = field(default_factory=dict)

    def __post_init__(self):
        self.streams = tuple(self.streams)
        for s in self.streams:
            DELIVERY[s]                                   # 임계 없는 스트림은 거부
        self._b = {s: _Bucket() for s in self.streams}

    def observe(self, stream: str, ts_ms: int) -> None:
        """`ts_ms` = **라이터가 shard 경계에 쓸 그 값**(수신 시각이 아니다).

        ⚠️ 모르는 스트림은 **조용히 버리지 않는다** — 세지 않는 스트림이 생기면
        그게 바로 이 모듈이 막으려던 침묵이다.
        """
        b = self._b.get(stream)
        if b is None:
            raise KeyError(f"세지 않는 스트림 '{stream}' — DeliveryCounter(streams=…)에 "
                           f"넣거나 관측을 지울 것. 조용히 버리면 0을 못 본다")
        m = ts_ms // BUCKET_MS
        if m != b.minute:
            if m > b.minute:
                b.prev_minute, b.prev_count = b.minute, b.count
                b.minute, b.count = m, 0
            else:
                #  늦게 온 과거 분(이벤트 시각 역행) — 직전 분이면 거기에 더한다
                if m == b.prev_minute:
                    b.prev_count += 1
                b.last_seen_ms = max(b.last_seen_ms or ts_ms, ts_ms)
                return
        b.count += 1
        b.last_seen_ms = ts_ms if b.last_seen_ms is None else max(b.last_seen_ms, ts_ms)

    def _prev_count(self, b: _Bucket, minute: int) -> int:
        if b.minute == minute:
            return b.count
        if b.prev_minute == minute:
            return b.prev_count
        return 0                       # 🔴 관측이 없던 분은 0이다(B3)

    def snapshot(self, now_ms: int) -> dict:
        cur = now_ms // BUCKET_MS
        L = cur - 1
        out = {}
        for s, b in self._b.items():
            out[s] = {
                "current_minute_count": b.count if b.minute == cur else 0,
                "prev_minute_count": (self._prev_count(b, L)
                                      if minute_covered(L, self.start_ms) else None),
                "last_seen_age_sec": (None if b.last_seen_ms is None
                                      else max(0.0, (now_ms - b.last_seen_ms) / 1000.0)),
            }
        return out

    def stalled(self, now_ms: int) -> list[str]:
        """정지 스트림 — 임계는 `DELIVERY`에서 **스트림별로** 온다(전역 인자 없음)."""
        L = prev_minute_of(now_ms)
        out = []
        for s in self.streams:
            b = self._b[s]
            pmc = self._prev_count(b, L) if minute_covered(L, self.start_ms) else None
            if is_stalled(s, now_ms=now_ms, start_ms=self.start_ms,
                          last_seen_ms=b.last_seen_ms, prev_minute_count=pmc):
                out.append(s)
        return out


# ─────────────────────────── 재생 어댑터 ───────────────────────────
#  shard는 첫 행 시각으로 파일 이름·날짜 dir이 정해지고 60초마다 닫힌다.
#  창 밖 파일을 이름만으로 건너뛰려면 **한 파일이 덮을 수 있는 최대 폭**이 필요하다.
#  ⚠️ writer 지연까지 넉넉히 5분. 좁히면 창 경계의 행을 조용히 놓친다.
FILE_SPAN_MARGIN_MS = 300_000


def _day(ms: int) -> _dt.date:
    return _dt.datetime.fromtimestamp(ms / 1000, _dt.UTC).date()


def _file_start_ms(day: _dt.date, name: str) -> int | None:
    """`HHMMSS_mmm.parquet` → 첫 행 시각(ms). 모르는 이름이면 None(= 건너뛰지 않는다)."""
    try:
        hms, ms = name.split(".")[0].split("_")
        t = _dt.datetime(day.year, day.month, day.day, int(hms[:2]), int(hms[2:4]),
                         int(hms[4:6]), tzinfo=_dt.UTC)
        return int(t.timestamp() * 1000) + int(ms)
    except (ValueError, IndexError):
        return None


def window_files(root, subdir: str, lo_ms: int, hi_ms: int) -> list[Path]:
    """`[lo, hi)`에 행이 있을 수 있는 shard — **인접일 dir까지** 본다.

    자정을 넘는 shard는 **첫 행 날짜(전일) dir**에 있다. 오늘 dir만 읽으면 자정 직후
    오늘 dir이 비어 *"한 번도 안 옴 = 정지"*로 매일 오발한다(E2E Codex C3).
    """
    root = Path(root)
    d, last = _day(lo_ms - FILE_SPAN_MARGIN_MS), _day(max(lo_ms, hi_ms - 1))
    out = []
    while d <= last:
        sd = root / d.isoformat() / subdir
        if sd.is_dir():
            for f in sorted(sd.glob("*.parquet")):
                fs = _file_start_ms(d, f.name)
                if fs is None or (lo_ms - FILE_SPAN_MARGIN_MS <= fs < hi_ms):
                    out.append(f)
        d += _dt.timedelta(days=1)
    return out


@dataclass
class WindowScan:
    """한 창 `[lo, hi)`의 재생 결과. 🔴**행을 메모리에 모으지 않는다**(파일 단위 스트리밍).

    ⚠️ 도쿄 VPS는 E2E 수집기와 메모리를 나눠 쓰고 수집기가 우선이다.
    """
    kind: str
    lo_ms: int
    hi_ms: int
    rows: int = 0
    first_ms: int | None = None
    last_ms: int | None = None
    max_interior_gap_ms: int = 0
    interior_over_grace: int = 0
    minute: int | None = None
    minute_count: int = 0
    unreadable_files: int = 0


def scan_window(root, kind: str, lo_ms: int, hi_ms: int, *,
                count_minute: int | None = None) -> WindowScan:
    import pyarrow as pa
    import pyarrow.compute as _pc
    import pyarrow.parquet as pq
    #  pyarrow.compute 함수는 런타임에 생성돼 pyright가 속성을 모른다 — 동작 무관
    pc: Any = _pc
    col = TS_COLUMN[kind]
    g = DELIVERY[kind].grace_sec * 1000
    ws = WindowScan(kind, lo_ms, hi_ms, minute=count_minute)
    for f in window_files(root, kind, lo_ms, hi_ms):
        try:
            a = pq.read_table(f, columns=[col]).column(col)
        except Exception:
            ws.unreadable_files += 1           # 🚫 조용히 버리지 않는다 — 센다
            continue
        a = pc.drop_null(a.combine_chunks() if isinstance(a, pa.ChunkedArray) else a)
        a = pc.filter(a, pc.and_(pc.greater_equal(a, lo_ms), pc.less(a, hi_ms)))
        n = len(a)
        if n == 0:
            continue
        a = pc.take(a, pc.array_sort_indices(a))   # 파일 안에서만 정렬(파일은 작다)
        fmin, fmax = a[0].as_py(), a[n - 1].as_py()
        if ws.last_ms is not None:
            gap = fmin - ws.last_ms                # 파일 사이 간격(겹치면 0 이하)
            if gap > ws.max_interior_gap_ms:
                ws.max_interior_gap_ms = gap
            if gap > g:
                ws.interior_over_grace += 1
        if n >= 2:
            d = pc.pairwise_diff(a)
            mx = pc.max(d).as_py() or 0
            ws.max_interior_gap_ms = max(ws.max_interior_gap_ms, mx)
            ws.interior_over_grace += int(pc.sum(pc.cast(pc.greater(d, g), "int64")).as_py() or 0)
        if count_minute is not None:
            m0 = count_minute * BUCKET_MS
            ws.minute_count += int(pc.sum(pc.cast(pc.and_(pc.greater_equal(a, m0),
                                                          pc.less(a, m0 + BUCKET_MS)),
                                                  "int64")).as_py() or 0)
        ws.rows += n
        ws.first_ms = fmin if ws.first_ms is None else min(ws.first_ms, fmin)
        ws.last_ms = fmax if ws.last_ms is None else max(ws.last_ms, fmax)
    return ws


def stalled_from_scan(scan: WindowScan, *, now_ms: int, start_ms: int) -> bool:
    """재생 결과를 **라이브와 같은 규칙**(`is_stalled`)으로 판정한다."""
    L = prev_minute_of(now_ms)
    pmc = None
    if minute_covered(L, start_ms):
        if scan.minute != L:
            raise ValueError("scan_window(count_minute=prev_minute_of(now_ms))로 읽어야 한다")
        pmc = scan.minute_count
    return is_stalled(scan.kind, now_ms=now_ms, start_ms=start_ms,
                      last_seen_ms=scan.last_ms, prev_minute_count=pmc)


def silence_summary(kind: str, scans: list[WindowScan]) -> dict:
    """구간들(`[lo, hi)`)의 침묵 요약 — 🔴**경계 침묵을 포함한다**(E2E Codex C4).

    행간 간격만 보면 *"창 시작 → 첫 행"*과 *"마지막 행 → 창 끝"*이 빠진다.
    """
    g = DELIVERY[kind].grace_sec * 1000
    rows = sum(s.rows for s in scans)
    max_sil, beyond, unreadable = 0, 0, 0
    for s in scans:
        unreadable += s.unreadable_files
        if s.rows == 0 or s.first_ms is None or s.last_ms is None:
            sil = s.hi_ms - s.lo_ms
            max_sil = max(max_sil, sil)
            beyond += int(sil > g)
            continue
        for sil in (s.first_ms - s.lo_ms, s.hi_ms - s.last_ms):
            max_sil = max(max_sil, sil)
            beyond += int(sil > g)
        max_sil = max(max_sil, s.max_interior_gap_ms)
        beyond += s.interior_over_grace
    return {"rows": rows,
            "max_silence_sec": round(max_sil / 1000.0, 3),
            "silences_beyond_grace": beyond,
            "grace_sec": DELIVERY[kind].grace_sec,
            "unreadable_files": unreadable,
            "ok": rows > 0 and beyond == 0 and unreadable == 0}
