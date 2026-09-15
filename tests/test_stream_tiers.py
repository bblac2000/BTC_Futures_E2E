# ── PROVENANCE ─────────────────────────────────────────────────────────────
# Copied from: /home/cms/project/E2E_Hybrid_Bot/tests/test_stream_tiers.py
# Source commit: 4718287 (E2E HEAD f1e7d86, 2026-09-14) · copied 2026-09-15
# Local changes:
#   - tmp-tree fixtures write under this repo's package dirs (exchange/, data/) instead of e2e/
#   - dropped the last two E2E tests (they import e2e.l2_collector, which does not exist here)
#   - added: this bot's two streams classify as market tier and share one socket
# ───────────────────────────────────────────────────────────────────────────
"""WS 티어 대응표 테스트 — **혼합 티어 구독을 불가능하게** 만든다(E2E #132·#133).

🔴 이 파일이 지키는 사고: legacy 소켓이 `/market` 구독을 **수락해 놓고 한 건도 안 보냈고**,
   E2E는 그걸 두 달 넘게 *"Binance가 WS로 안 준다"*로 오독했다. 구독 수락 ≠ 전달.
"""
from __future__ import annotations

import pytest

from ops import stream_tiers as T

#  🔴 픽스처 URL은 **런타임에 조립**한다. 통째로 리터럴로 쓰면 이 테스트 파일 자신이
#     `tests/` legacy 잠금에 걸린다. 🚫 allowlist를 늘려 빠져나가지 않는다.
_HOST = "wss://fstream.binance.com/"
_LEGACY_COMBINED = _HOST + "stream?streams="
_LEGACY_RAW = _HOST + "ws/"

PUBLIC = ["btcusdt@depth20@100ms", "btcusdt@trade", "btcusdt@bookTicker"]
MARKET = ["btcusdt@aggTrade", "btcusdt@markPrice@1s", "btcusdt@forceOrder"]
#  이 봇이 실제로 구독할 스트림(설계서 build order 5)
BOT_STREAMS = ["btcusdt@kline_1m", "btcusdt@markPrice@1s"]


# ── 티어별로 제 엔드포인트에서만 통과 ────────────────────────────────────
def test_public_streams_build_only_on_the_public_endpoint():
    url = T.build_stream_url("public", PUBLIC)
    assert url.startswith("wss://fstream.binance.com/public/stream?streams=")
    assert all(s in url for s in PUBLIC)
    with pytest.raises(T.TierMismatchError):
        T.build_stream_url("market", PUBLIC)


def test_market_streams_build_only_on_the_market_endpoint():
    url = T.build_stream_url("market", MARKET)
    assert url.startswith("wss://fstream.binance.com/market/stream?streams=")
    with pytest.raises(T.TierMismatchError):
        T.build_stream_url("public", MARKET)


def test_the_bots_kline_and_markprice_share_one_market_socket():
    """kline_1m과 markPrice@1s는 **같은 market 티어**라 한 소켓에 실어도 된다."""
    url = T.build_stream_url("market", BOT_STREAMS)
    assert url == "wss://fstream.binance.com/market/stream?streams=btcusdt@kline_1m/btcusdt@markPrice@1s"
    with pytest.raises(T.TierMismatchError):
        T.build_stream_url("public", BOT_STREAMS)


# ── 혼합은 실패 ────────────────────────────────────────────────────────
def test_a_mixed_tier_subscription_cannot_be_built():
    """🔴 E2E #132를 만든 구조 그 자체다 — public은 오고 market은 조용히 0건."""
    with pytest.raises(T.TierMismatchError) as e:
        T.build_stream_url("public", PUBLIC + MARKET)
    msg = str(e.value)
    assert "섞" in msg
    assert "btcusdt@trade" in msg and "btcusdt@forceOrder" in msg, \
        "어느 스트림이 어느 티어인지 보여야 사람이 고칠 수 있다"


# ── 모르는 스트림은 fail-closed ────────────────────────────────────────
def test_an_unknown_stream_raises_instead_of_defaulting_to_a_tier():
    with pytest.raises(T.UnknownStreamError) as e:
        T.classify_stream("btcusdt@someNewStreamBinanceAddsIn2027")
    assert "추측하지 않는다" in str(e.value)
    with pytest.raises(T.UnknownStreamError):
        T.build_stream_url("public", ["btcusdt@trade", "btcusdt@brandNew"])


def test_unknown_stream_is_not_silently_dropped_from_the_url():
    with pytest.raises(T.UnknownStreamError):
        T.build_stream_url("market", ["btcusdt@forceOrder", "btcusdt@unknownThing"])


# ── provenance: 고지와 실측을 섞지 않는다(E2E #133) ────────────────────
def test_trade_is_marked_as_measured_not_as_notice():
    """🔴 `@trade`는 **공식 고지 표에 아예 없다** — E2E 90초 실측으로만 public이다."""
    spec = T.classify_stream("btcusdt@trade")
    assert spec.tier == "public"
    assert spec.provenance == "measured", "고지에 없는 것을 고지 근거로 적으면 안 된다"
    assert spec.measured_at == "2026-09-12"
    assert "509" in spec.notes and "0건" in spec.notes, "실측 수치가 근거로 남아야 한다"


def test_every_spec_carries_provenance_and_measured_entries_carry_a_date():
    for s in T.STREAMS:
        assert s.provenance in ("binance_notice", "measured", "notice_and_measured"), s
        assert s.source_ref, s
        if s.provenance != "binance_notice":
            assert s.measured_at, f"{s.pattern}: 실측 근거인데 측정일이 없다"


def test_kline_is_market_tier():
    """v6:989 예제가 legacy URL + market 스트림으로 **이중으로** 깨져 있었다(E2E #133)."""
    assert T.classify_stream("btcusdt@kline_15m").tier == "market"
    assert T.classify_stream("btcusdt@kline_1m").tier == "market"


# ── 정적 검사가 진짜를 잡는가 ──────────────────────────────────────────
def _write(tmp_path, rel, body):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_scan_catches_a_bare_legacy_url(tmp_path):
    _write(tmp_path, "data/x.py", f'WS = "{_LEGACY_COMBINED}btcusdt@kline_1m"\n')
    _write(tmp_path, "ops/keep.py", "X = 1\n")
    v = T.scan(tmp_path)
    assert len(v) == 1 and v[0]["kind"] == "legacy_url" and v[0]["file"] == "data/x.py"


def test_scan_catches_a_legacy_url_inside_an_fstring(tmp_path):
    _write(tmp_path, "exchange/y.py",
           'S = "btcusdt"\n' + 'WS = f"' + _LEGACY_RAW + '{S}@kline_1m"\n')
    _write(tmp_path, "ops/keep.py", "X = 1\n")
    assert [x["kind"] for x in T.scan(tmp_path)] == ["legacy_url"]


def test_scan_catches_a_hardcoded_tier_url_that_bypasses_the_registry(tmp_path):
    """🔴 **반대 방향** — legacy만 막으면 다음 사람이 `/market/...`을 문자열로 박아 registry를 우회한다."""
    _write(tmp_path, "data/z.py", f'WS = "{_HOST}market/stream?streams=btcusdt@kline_1m"\n')
    _write(tmp_path, "ops/keep.py", "X = 1\n")
    v = T.scan(tmp_path)
    assert len(v) == 1 and v[0]["kind"] == "hardcoded_tier"


def test_the_module_that_defines_the_urls_is_allowed_to_contain_them():
    assert "ops/stream_tiers.py" in T.ALLOWLIST
    assert len(T.ALLOWLIST) == 1, "allowlist가 늘어나는 것은 경계를 여는 행위다"


def test_scan_ignores_urls_in_comments_and_docstrings_of_prose(tmp_path):
    _write(tmp_path, "data/c.py", f'# 예전에는 {_LEGACY_COMBINED}... 를 썼다\nX = 1\n')
    _write(tmp_path, "ops/keep.py", "X = 1\n")
    assert T.scan(tmp_path) == []


# ── 저장소 전역 잠금 ───────────────────────────────────────────────────
def test_no_production_file_builds_an_endpoint_url_by_hand():
    """🔒 회귀 잠금 — 저장소 전체에서 직접 만든 엔드포인트 URL이 0건이어야 한다."""
    v = T.scan()
    assert v == [], "직접 만든 엔드포인트 URL:\n" + "\n".join(
        f"  {x['file']}:{x['line']} [{x['kind']}] {x['detail']}" for x in v)


def test_tests_dir_is_scanned_for_legacy_urls_but_not_for_tier_literals(tmp_path):
    _write(tmp_path, "data/keep.py", "X = 1\n")
    _write(tmp_path, "ops/keep.py", "X = 1\n")
    _write(tmp_path, "tests/t_ok.py",
           f'assert U == "{_HOST}public/stream?streams=btcusdt@trade"\n')
    assert T.scan(tmp_path) == [], "티어 URL 단언은 테스트에서 정당하다"
    _write(tmp_path, "tests/t_bad.py", f'MOCK = "{_LEGACY_COMBINED}btcusdt@trade"\n')
    v = T.scan(tmp_path)
    assert len(v) == 1 and v[0]["kind"] == "legacy_url" and v[0]["file"] == "tests/t_bad.py"
