# ── PROVENANCE ─────────────────────────────────────────────────────────────
# Copied from: /home/cms/project/E2E_Hybrid_Bot/ops/stream_tiers.py
# Source commit: 4718287 (E2E HEAD f1e7d86, 2026-09-14) · copied 2026-09-15
# Local changes (back-port candidates are logged in docs/ops_log.md):
#   - SCAN_DIRS: e2e/ops -> this repo's packages
#   - usage docstring path unchanged (python -m ops.stream_tiers --scan)
# ───────────────────────────────────────────────────────────────────────────
"""Binance USDⓈ-M WS **티어 대응표 + URL 생성** — 혼합 티어 구독을 구조적으로 막는다.

## 왜 있나 (2026-09-12 · 레지스트리 #132·#133)

Binance는 USDⓈ-M WS를 `/public`·`/market`·`/private` 티어로 쪼갰고 **legacy 미라우팅
URL은 2026-04-23 폐기**됐다. 그 뒤 legacy 소켓은 `/market` 스트림 구독을 **거부하지 않는다** —
🔴 **수락해 놓고 한 건도 보내지 않는다.** 에러도 로그도 없다.

우리는 이걸 **두 달 넘게 "Binance가 WS로 안 준다"로 오독**했다. `markprice_rest.py`의
REST 1s 폴백(2026-07-24)은 그 오독 위에 지어졌고 — 폐기일로부터 **3개월 뒤**다 —
라우팅 변경을 가리고 있었다. `E2E_COLLECT_DERIVS=1`은 *"복구 시 즉시 활성"*이라 적힌 채
**켜도 조용히 0건**인 상태로 남아 있었다.

🔴 **그래서 이 모듈의 목적은 "기록"이 아니라 "불가능하게 만들기"다.** 엔드포인트 URL은
`build_stream_url()`만 만들 수 있고, 거기서 티어가 어긋나면 **예외로 죽는다**.

## fail-closed

🚫 **모르는 스트림에 기본 티어를 주지 않는다.** `classify_stream()`은 매칭이 없으면
`UnknownStreamError`를 던진다. *"모르면 public"* 같은 기본값은 **정확히 이 사고를 다시
만든다** — 새 스트림이 조용히 틀린 소켓에 실려 0건이 된다.

## 근거 등급 (#133)

⚠️ **공식 고지와 우리 실측을 섞지 않는다.** 항목마다 `provenance`를 남긴다 —
섞어 적으면 다음 사람이 고지를 뒤져도 우리 문장을 못 찾고, 반대로 우리 관측이
고지의 권위를 빌리게 된다. `@trade`가 그 예다: **공식 고지 표에 아예 없어서**
우리 90초 측정(509건 vs aggTrade 0건)으로만 public이라 판정했다.

사용: `python -m ops.stream_tiers [--scan] [--json]`   (`--scan` 위반 시 exit 1)
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BASE = "wss://fstream.binance.com"
TIERS = ("public", "market", "private")

#  고지 URL — 티어 지도의 🅐 등급 근거
NOTICE = ("https://developers.binance.com/docs/derivatives/usds-margined-futures/"
          "websocket-market-streams/Important-WebSocket-Change-Notice")
#  실측 근거 — 🅑 등급
MEASURED = "레지스트리 #132·#133 (2026-09-12 VPS 도쿄)"


class UnknownStreamError(ValueError):
    """모르는 스트림 — 🚫기본 티어를 주지 않는다(#133 fail-closed)."""


class TierMismatchError(ValueError):
    """엔드포인트 티어와 스트림 티어가 어긋남, 또는 한 소켓에 여러 티어."""


@dataclass(frozen=True)
class StreamSpec:
    pattern: str            # 스트림명 전체 일치 정규식
    tier: str
    provenance: str         # binance_notice | measured | notice_and_measured
    source_ref: str
    measured_at: str | None
    notes: str


#  ⚠️ 순서 주의: 더 좁은 패턴이 먼저다(`@depth20@100ms`가 `@depth`보다 앞).
STREAMS: tuple[StreamSpec, ...] = (
    StreamSpec(r".+@depth\d+(@\d+ms)?", "public", "binance_notice", NOTICE, None,
               "partial depth — 고지 public 표에 명시"),
    StreamSpec(r".+@depth(@\d+ms)?", "public", "binance_notice", NOTICE, None,
               "diff depth — 고지 public 표에 명시"),
    StreamSpec(r".+@bookTicker", "public", "binance_notice", NOTICE, None,
               "고지 public 표에 명시"),
    StreamSpec(r"!bookTicker", "public", "binance_notice", NOTICE, None,
               "고지 public 표에 명시"),
    #  🔴 `@trade`는 **고지 표에 아예 없다** — 우리 실측으로만 public이라 판정했다.
    StreamSpec(r".+@trade", "public", "measured", MEASURED, "2026-09-12",
               "고지 표에 부재. legacy /ws 90초 실측: @trade 509건 vs @aggTrade 0건 "
               "→ legacy에서 살아남았으므로 public"),
    StreamSpec(r".+@aggTrade", "market", "notice_and_measured", NOTICE, "2026-09-12",
               "고지 market + 실측(legacy 90초 0건 / market/ws 240초 1,590건)"),
    StreamSpec(r".+@markPrice(@1s)?", "market", "notice_and_measured", NOTICE, "2026-09-12",
               "고지 market + 실측(market/ws 240초 81건)"),
    StreamSpec(r"!markPrice@arr(@1s)?", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r".+@forceOrder", "market", "notice_and_measured", NOTICE, "2026-09-12",
               "고지 market + 실측(market/ws 240초 40건)"),
    StreamSpec(r"!forceOrder@arr", "market", "notice_and_measured", NOTICE, "2026-09-12",
               "고지 market + 실측(market/stream 240초 64건)"),
    StreamSpec(r".+@kline_.+", "market", "binance_notice", NOTICE, None,
               "⚠️v6:989 예제가 legacy URL로 써 둬 이중으로 깨져 있었다(#133)"),
    StreamSpec(r".+@continuousKline_.+", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r".+@miniTicker", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r"!miniTicker@arr", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r".+@ticker", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r"!ticker@arr", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r".+@compositeIndex", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r"!contractInfo", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r"!assetIndex@arr", "market", "binance_notice", NOTICE, None, ""),
    StreamSpec(r".+@assetIndex", "market", "binance_notice", NOTICE, None, ""),
)


def classify_stream(name: str) -> StreamSpec:
    """스트림명 → `StreamSpec`. 🚫**모르면 예외**(기본값 금지·#133)."""
    for spec in STREAMS:
        if re.fullmatch(spec.pattern, name):
            return spec
    raise UnknownStreamError(
        f"모르는 스트림 '{name}' — 티어를 추측하지 않는다. "
        f"`ops/stream_tiers.py:STREAMS`에 provenance와 함께 추가할 것. "
        f"🚫기본값을 주면 새 스트림이 조용히 틀린 소켓에 실려 0건이 된다(#132).")


def build_stream_url(tier: str, streams, *, combined: bool = True) -> str:
    """티어를 **검증한 뒤에만** 엔드포인트 URL을 만든다.

    🔴 혼합 티어(한 소켓에 public+market)는 정확히 #132가 만들어진 방식이다 —
       public은 오고 market은 조용히 안 온다.
    """
    if tier not in TIERS:
        raise TierMismatchError(f"알 수 없는 티어 '{tier}' — {TIERS} 중 하나여야 한다")
    streams = list(streams)
    if not streams:
        raise TierMismatchError("스트림이 비었다")
    got = {}
    for s in streams:
        got.setdefault(classify_stream(s).tier, []).append(s)
    if len(got) > 1:
        raise TierMismatchError(
            "한 소켓에 티어가 섞였다: "
            + " · ".join(f"{t}={v}" for t, v in sorted(got.items()))
            + " — 소켓을 티어별로 나눌 것(#132: 섞으면 한쪽이 조용히 0건이 된다)")
    (only,) = got
    if only != tier:
        raise TierMismatchError(
            f"엔드포인트 티어 '{tier}'인데 스트림은 '{only}' 티어다: {streams}")
    if combined:
        return f"{BASE}/{tier}/stream?streams=" + "/".join(streams)
    if len(streams) != 1:
        raise TierMismatchError("단일(raw) 엔드포인트에는 스트림 1개만")
    return f"{BASE}/{tier}/ws/{streams[0]}"


# ─────────────────────────── 정적 검사 (양방향) ───────────────────────────
#  🔴 **양방향이다**(#133 인간 보강):
#    ① legacy bare URL 금지 — 오늘의 사고 그 자체
#    ② 이 모듈 **밖에서** 티어 문자열 하드코딩 금지 — 다음 사람이 registry를 우회하고
#       `/public/...`을 문자열로 박으면 검증이 통째로 비활성된다. 그럼 ①만 막는 검사는
#       "고쳤다"고 말하면서 같은 구멍을 남긴다.
#  BTC_Futures_E2E: 이 저장소의 패키지 전부.
SCAN_DIRS = ("exchange", "sizing", "paper", "db", "data", "telegram", "safety", "ops", "strategies")
#  ⚠️ `tests/`는 **legacy 검사만** 받는다(Codex Q5). 테스트는 `build_stream_url()`로 만든
#     티어 URL 문자열을 정당하게 단언하므로 `hardcoded_tier`를 걸면 오탐이 되고,
#     오탐이 쌓이면 사람이 검사를 끈다. 반면 **legacy URL을 목킹한 테스트는 프로덕션이
#     깨져도 계속 통과**하므로 그건 반드시 막아야 한다(2026-09-12 기준 0건 — 생기지 않게 잠근다).
LEGACY_ONLY_DIRS = ("tests",)
#  ⚠️ allowlist는 "검사 안 함"이 아니라 **"여기가 정의하는 곳"**이라는 뜻이다.
ALLOWLIST = ("ops/stream_tiers.py",)

LEGACY_RE = re.compile(r"wss://fstream\.binance\.com/(ws|stream)\b")
TIER_LITERAL_RE = re.compile(r"wss://fstream\.binance\.com/(public|market|private)\b")


def scan(root: Path | None = None) -> list[dict]:
    """소스의 **문자열 리터럴**(f-string 조각 포함)을 AST로 훑는다.

    ⚠️문자열 포함 검사가 아니라 AST인 이유: 주석·문서에 URL이 적힌 것은 위반이 아니다.
      집행 대상은 **실행되는 코드**다(`scan_order_path`와 같은 근거).
    """
    root = root or ROOT
    out: list[dict] = []
    for d in SCAN_DIRS + LEGACY_ONLY_DIRS:
        legacy_only = d in LEGACY_ONLY_DIRS
        if not (root / d).is_dir():
            continue
        for py in sorted((root / d).rglob("*.py")):
            rel = py.relative_to(root).as_posix()
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError as e:
                out.append({"file": rel, "line": e.lineno or 0,
                            "kind": "parse_error", "detail": str(e)})
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                v = node.value
                if LEGACY_RE.search(v):
                    out.append({
                        "file": rel, "line": node.lineno, "kind": "legacy_url",
                        "detail": f"legacy 미라우팅 URL(2026-04-23 폐기): {v[:80]!r} — "
                                  f"build_stream_url()을 쓸 것"})
                if (not legacy_only and rel not in ALLOWLIST
                        and TIER_LITERAL_RE.search(v)):
                    out.append({
                        "file": rel, "line": node.lineno, "kind": "hardcoded_tier",
                        "detail": f"티어 URL 하드코딩: {v[:80]!r} — registry를 우회한다. "
                                  f"build_stream_url()만 엔드포인트를 만든다"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="WS 티어 대응표·URL 생성·정적 검사")
    ap.add_argument("--scan", action="store_true", help="저장소 정적 검사(위반 시 exit 1)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.scan:
        for s in STREAMS:
            print(f"  {s.tier:7s} {s.pattern:28s} {s.provenance:20s} "
                  f"{s.measured_at or '-':12s} {s.notes}")
        return 0
    v = scan()
    if a.json:
        print(json.dumps(v, ensure_ascii=False, indent=2))
    else:
        print(f"[stream-tiers] 검사 대상 {'/'.join(SCAN_DIRS + LEGACY_ONLY_DIRS)} · 위반 {len(v)}건")
        for x in v:
            print(f"  🔴 {x['file']}:{x['line']}  [{x['kind']}]  {x['detail']}")
    return 1 if v else 0


if __name__ == "__main__":
    raise SystemExit(main())
