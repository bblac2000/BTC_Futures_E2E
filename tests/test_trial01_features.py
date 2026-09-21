"""단계 2b — sr_v1 피처(합성 입력). 롤링 VP = 처음부터 다시 계산한 값 · 규약 경계 · 결정론."""
from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from backtest.data import MINUTE_MS as M
from backtest.data import Bar1m
from strategies.trial01 import features as F

D = Decimal
T0 = int(dt.datetime(2024, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
TICK = D("0.1")


def bar(t: int, o: str, h: str, lo: str, c: str, qv: str = "1000") -> Bar1m:
    return Bar1m(t, o, h, lo, c, "1", qv, 1, "0", "0", o, h, lo, c, "archive")


def flat(t: int, c: str, qv: str = "1000") -> Bar1m:
    return bar(t, c, c, c, c, qv)


# ── ATR ─────────────────────────────────────────────────────────────────────
def test_wilder_atr_seeds_with_the_mean_then_smooths():
    a = F.WilderATR(3)
    assert a.update(D(10), D(8), D(9)) is None and a.update(D(11), D(9), D(10)) is None
    v = a.update(D(12), D(9), D(11))                              # TR 2, 2, 3 → 7/3
    assert v == D(7) / 3
    assert a.update(D(11), D(11), D(11)) == (D(7) / 3 * 2 + 0) / 3


# ── 버킷 ─────────────────────────────────────────────────────────────────────
def test_bucket_two_thirds_rule_and_fully_empty_buckets_are_emitted():
    agg = F.BucketAggregator(15)
    assert agg.need == 10
    out = []
    for i in list(range(10)) + list(range(15, 24)) + [45]:        # 버킷0: 10분(계산) · 버킷1: 9분(이어 쓰기) · 버킷2: 0분
        out += agg.push(flat(T0 + i * M, "100"))
    assert [(b.open_ms, b.n_minutes, b.complete_enough) for b in out] == \
        [(T0, 10, True), (T0 + 15 * M, 9, False), (T0 + 30 * M, 0, False)]


def test_bucket_is_emitted_when_its_last_minute_closes_not_later():
    agg = F.BucketAggregator(15)
    got = [agg.push(flat(T0 + i * M, "100")) for i in range(15)]
    assert got[13] == [] and len(got[14]) == 1 and got[14][0].close_ms == T0 + 15 * M - 1


# ── 스윙 ─────────────────────────────────────────────────────────────────────
def _b15(i: int, hi: int, lo: int, close: int) -> F.Bucket:
    return F.Bucket(T0 + i * 15 * M, T0 + (i + 1) * 15 * M - 1, 15, True, D(close), D(hi), D(lo), D(close))


def test_swing_confirmed_at_the_close_of_the_third_bar_after_and_strictly_higher():
    st = F.SwingTracker()
    highs = [100, 101, 102, 110, 103, 102, 101, 100]
    new = []
    for i, h in enumerate(highs):
        new += st.on_bucket(_b15(i, h, h - 50, h - 10), D(5))
    sh = [x for x in new if x.kind == "swing_high"]
    assert len(sh) == 1 and sh[0].price == 110 and sh[0].bar_open_ms == T0 + 3 * 15 * M
    assert sh[0].confirmed_ms == T0 + 7 * 15 * M - 1, "스윙 봉(3) 뒤 3번째 봉(6)의 마감"
    assert not sh[0].active(sh[0].confirmed_ms - 1) and sh[0].active(sh[0].confirmed_ms)
    assert sh[0].expires_ms == sh[0].confirmed_ms + 48 * 3_600_000
    st2 = F.SwingTracker()
    tie = []
    for i, h in enumerate([100, 101, 102, 110, 110, 102, 101, 100]):
        tie += st2.on_bucket(_b15(i, h, h - 50, h - 10), D(5))
    assert not [x for x in tie if x.kind == "swing_high"], "동률은 fractal이 아니다(엄격히 높아야)"


def test_swing_invalidation_needs_a_close_beyond_the_level_by_more_than_quarter_atr():
    st = F.SwingTracker()
    for i, h in enumerate([100, 101, 102, 110, 103, 102, 101]):
        st.on_bucket(_b15(i, h, h - 50, h - 10), D(8))
    lv = [x for x in st.levels if x.kind == "swing_high"][0]
    st.on_bucket(_b15(7, 115, 100, 112), D(8))                   # 110 + 2 = 112 → 초과 아님
    assert lv.invalidated_ms is None
    st.on_bucket(_b15(8, 115, 100, 113), D(8))                   # 113 > 112 → 무효
    inv: int | None = lv.invalidated_ms               # 위의 None 좁히기를 끊는다(호출 뒤 값이 바뀐다)
    assert inv is not None and inv == T0 + 9 * 15 * M - 1 and not lv.active(inv)


# ── 볼륨 프로파일 ─────────────────────────────────────────────────────────────
def _vp_scratch(window: list[Bar1m], cfg: F.SrV1) -> F.VP:
    """정의 그대로 처음부터 — 롤링 구현과 대조용."""
    binw = TICK * cfg.vp_bin_ticks
    vols: dict[int, int] = {}
    for b in window:
        k = int(b.d("close") // binw)
        vols[k] = vols.get(k, 0) + int(b.d("quote_volume") * F.QV_SCALE)
    lo, hi = min(vols), max(vols)
    arr = [vols.get(k, 0) for k in range(lo, hi + 1)]
    total = sum(arr)
    p = max(range(len(arr)), key=lambda i: (arr[i], -i))
    a = b = p
    acc = arr[p]
    while acc * 100 < total * cfg.va_frac_num:
        up = arr[b + 1] if b + 1 < len(arr) else -1
        dn = arr[a - 1] if a - 1 >= 0 else -1
        if dn >= up:
            a, acc = a - 1, acc + dn
        else:
            b, acc = b + 1, acc + up
    return F.VP((lo + p) * binw + binw / 2, (lo + b + 1) * binw, (lo + a) * binw)


def test_rolling_volume_profile_equals_a_from_scratch_recompute_every_minute():
    cfg = F.SrV1(vp_window=60)
    rnd = random.Random(7)
    bars = []
    px = 60000.0
    for i in range(400):
        px += rnd.choice([-35, -12, 0, 12, 35])
        bars.append(flat(T0 + i * M, f"{px:.1f}", f"{rnd.randint(1, 50) * 1000}.12345"))
    vp = F.RollingVP(TICK, D("50000"), D("70000"), cfg)
    checked = 0
    for i, b in enumerate(bars):
        if i >= 60:
            assert vp.value() == _vp_scratch(bars[i - 60:i], cfg), i    # 결정 봉 i 자신은 창 밖
            checked += 1
        else:
            assert vp.value() is None
        vp.push(b)
    assert checked == 340


def test_vp_ties_poc_lower_and_value_area_expands_lower_on_ties():
    cfg = F.SrV1(vp_window=4)
    vp = F.RollingVP(TICK, D("50000"), D("70000"), cfg)
    for i, (c, q) in enumerate([("60005", "10"), ("60015", "10"), ("59995", "5"), ("60025", "5")]):
        vp.push(flat(T0 + i * M, c, q))
    v = vp.value()
    assert v is not None and v.poc == D("60005"), "동률 POC는 낮은 가격 bin"
    # 총 30 → 70% = 21: POC(10) + 위 10 → 20 < 21 → 다음 위 5 vs 아래 5 동률 → 아래
    assert v.val == D("59990") and v.vah == D("60020")


# ── TSMOM ───────────────────────────────────────────────────────────────────
def test_tsmom_sign_uses_exactly_180_bars_back():
    ts = F.TSMOM()
    for i in range(180):
        assert ts.on_bucket(F.Bucket(0, 0, 240, True, D(0), D(0), D(0), D(100 + i))) is None
    assert ts.on_bucket(F.Bucket(0, 0, 240, True, D(0), D(0), D(0), D(50))) == -1
    assert ts.on_bucket(F.Bucket(0, 0, 240, True, D(0), D(0), D(0), D(500))) == 1


# ── 전체 · 결정론 ─────────────────────────────────────────────────────────────
def test_feature_run_is_deterministic_and_carries_values_on_incomplete_buckets():
    rnd = random.Random(3)
    bars = []
    px = 60000.0
    for i in range(3 * 1440):
        if 1500 <= i < 1506:                                     # 15m 버킷 하나를 9/15로 만든다
            continue
        px += rnd.choice([-20, -5, 0, 5, 20])
        bars.append(bar(T0 + i * M, f"{px:.1f}", f"{px + 8:.1f}", f"{px - 8:.1f}", f"{px:.1f}", f"{rnd.randint(1, 9)}000"))
    a, sa = F.run(bars, TICK)
    b, sb = F.run(bars, TICK)
    assert [(r.bar_open_ms, r.values) for r in a] == [(r.bar_open_ms, r.values) for r in b] and sa == sb
    inc = [r for r in a if r.values.get("bucket_incomplete_15m") == 1]
    assert inc, "9/15 버킷은 불완전"
    prev = [r for r in a if "atr_15m" in r.values and r.bar_open_ms < inc[0].bar_open_ms][-1]
    assert inc[0].values["atr_15m"] == prev.values["atr_15m"], "불완전 버킷은 이전 값을 이어 쓴다"
    assert sa, "스윙이 확정된다"


def test_features_adv_rows_are_byte_identical_across_two_builds_and_export_wide(tmp_path):
    """사용자 요구(2026-09-21): 같은 입력 → features_adv 행 바이트 동일."""
    from strategies.trial01 import feature_store as FS
    rnd = random.Random(11)
    bars = []
    px = 60000.0
    for i in range(2 * 1440):
        px += rnd.choice([-20, -5, 0, 5, 20])
        bars.append(bar(T0 + i * M, f"{px:.1f}", f"{px + 8:.1f}", f"{px - 8:.1f}", f"{px:.1f}", f"{rnd.randint(1, 9)}000"))
    shas = []
    for k in range(2):
        rows, _ = F.run(bars, TICK)
        con = FS.open_store(tmp_path / f"f{k}.sqlite")
        assert FS.write_rows(con, rows) > 0
        shas.append(FS.rows_sha256(con))
        if k == 0:
            n = FS.export_wide(con, tmp_path / "wide.parquet")
            assert n == len(bars)
            defs = con.execute("SELECT DISTINCT params_version, params_json FROM feature_definitions").fetchall()
            assert len(defs) == 1 and defs[0][0] == 1 and FS.A.SR_V1_SHA256 in defs[0][1]
        con.close()
    assert shas[0] == shas[1]


def test_tick_size_comes_from_the_captured_exchange_rules():
    from strategies.trial01 import feature_build as FB
    assert FB.tick_size() == Decimal("0.1")


def test_slow_features_are_carried_from_warmup_into_the_first_window_row():
    from strategies.trial01.feature_build import carry_into_window
    rows = [F.FeatureRow(T0 - 2 * M, {"atr_1m": D(1), "atr_15m": D(5), "tsmom_4h": D(1), "bucket_incomplete_15m": D(0)}),
            F.FeatureRow(T0 - M, {"atr_1m": D(2)}),
            F.FeatureRow(T0, {"atr_1m": D(3)}),
            F.FeatureRow(T0 + M, {"atr_1m": D(4), "atr_15m": D(6)})]
    out = carry_into_window(rows, T0, T0 + 10 * M)
    assert [r.bar_open_ms for r in out] == [T0, T0 + M]
    assert out[0].values == {"atr_15m": D(5), "tsmom_4h": D(1), "bucket_incomplete_15m": D(0), "atr_1m": D(3)}
    assert out[1].values == rows[3].values, "둘째 행부터는 그대로"


def test_features_do_not_depend_on_the_callers_decimal_context():
    """ccxt `decimal_to_precision`은 전역 rounding을 HALF_UP으로 바꿔 놓는다 — 피처는 정본 문맥으로 고정돼 같아야 한다."""
    import decimal

    from strategies.trial01.features import run as frun
    from tests.fixtures.dummy_replay_strategy import bars as tri_bars
    bs = tri_bars(3000)
    base, _ = frun(bs, Decimal("0.1"))
    with decimal.localcontext() as c:
        c.rounding, c.prec = decimal.ROUND_HALF_UP, 12
        other, _ = frun(bs, Decimal("0.1"))
    assert [r.values for r in base] == [r.values for r in other]


# ── 워밍업 로더(Codex 단계 d #6) — 합성 경계만 · OOS 데이터는 읽지도 만들지도 않는다 ─────────────────
def _wbar(t: int, px: str = "100", src: str = "archive"):
    from backtest.data import Bar1m
    return Bar1m(t, px, px, px, px, "1", "1", 1, "0", "0", px, px, px, px, src)


def test_merge_warmup_prefers_archive_fills_gaps_from_prior_window_and_never_crosses_start():
    from backtest.data import MINUTE_MS
    from strategies.trial01.feature_build import WARMUP_MS, merge_warmup
    start = 1_000 * WARMUP_MS                                   # 임의의 분 경계
    lo = start - WARMUP_MS
    arch = [_wbar(lo + i * MINUTE_MS, "1") for i in range(100)]                 # 아카이브는 앞 100분만
    prior = [_wbar(t, "2", "rest") for t in range(lo - 5 * MINUTE_MS, start + 5 * MINUTE_MS, MINUTE_MS)]
    w = merge_warmup(start, arch, prior)
    assert len(w) == WARMUP_MS // MINUTE_MS and w[0].open_ms == lo and w[-1].open_ms == start - MINUTE_MS
    assert all(b.close == "1" for b in w[:100]) and all(b.close == "2" for b in w[100:])   # 겹치면 아카이브
    assert [b.open_ms for b in w] == sorted({b.open_ms for b in w})


def test_merge_warmup_leaves_unfillable_minutes_missing():
    from backtest.data import MINUTE_MS
    from strategies.trial01.feature_build import WARMUP_MS, merge_warmup
    start = 1_000 * WARMUP_MS
    lo = start - WARMUP_MS
    prior = [_wbar(t) for t in range(lo, start, MINUTE_MS) if t != lo + 7 * MINUTE_MS]
    w = merge_warmup(start, [], prior)
    assert len(w) == WARMUP_MS // MINUTE_MS - 1 and lo + 7 * MINUTE_MS not in {b.open_ms for b in w}


def test_prior_windows_order():
    from strategies.trial01.feature_build import prior_windows
    assert prior_windows("IS") == [] and prior_windows("OOS") == ["IS"]


def test_oos_warmup_continues_from_the_prior_is_bars_on_a_synthetic_var_dir(tmp_path):
    """OOS 워밍업 = 아카이브(여기선 없음) + IS 준비 봉. 합성 IS parquet만 쓴다 — OOS 창의 봉은 없고 읽지 않는다."""
    from backtest import prepare as PR
    from backtest.data import MINUTE_MS
    from strategies.trial01.feature_build import WARMUP_MS, load_warmup
    start = PR.WINDOWS["OOS"][0]
    n = WARMUP_MS // MINUTE_MS
    synth = [_wbar(start - (n + 3 - i) * MINUTE_MS, src="rest") for i in range(n + 3)]   # 창 직전까지 35일 + 3분 여유
    (tmp_path / "IS").mkdir()
    PR.write_bars(tmp_path / "IS" / "bars_1m.parquet", synth)
    w = load_warmup("OOS", tmp_path, archive=tmp_path / "no_archive")
    assert len(w) == n and w[0].open_ms == start - WARMUP_MS and w[-1].open_ms == start - MINUTE_MS
    assert not (tmp_path / "OOS").exists()


def test_is_warmup_is_archive_only(tmp_path):
    from backtest import prepare as PR
    from backtest.data import MINUTE_MS
    from strategies.trial01.feature_build import load_warmup
    start = PR.WINDOWS["IS"][0]
    (tmp_path / "IS").mkdir()
    PR.write_bars(tmp_path / "IS" / "bars_1m.parquet", [_wbar(start - MINUTE_MS)])    # 자기 창 봉은 쓰지 않는다
    assert load_warmup("IS", tmp_path, archive=tmp_path / "no_archive") == []


def test_feature_metadata_cites_the_convention_rows():
    from strategies.trial01.feature_store import params_json
    assert params_json()["registry_rows"] == [18, 19, 20, 22]      # #20 피처 규약 · #22 거래대금 정수 스케일(Codex 단계 d #10)
