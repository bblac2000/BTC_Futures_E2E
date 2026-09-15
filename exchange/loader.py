"""런타임 규칙 로더 — REST(기동·주기) 또는 캡처 스냅샷 → `RuntimeRules`.

조회 대상(v6 §0 "런타임 진리원"):
| 이름 | 경로 | 서명 |
|---|---|---|
| exchangeInfo | /fapi/v1/exchangeInfo | – |
| leverageBracket | /fapi/v1/leverageBracket | ✔ |
| commissionRate | /fapi/v1/commissionRate | ✔ |
| fundingInfo | /fapi/v1/fundingInfo | – |
| positionSideDual | /fapi/v1/positionSide/dual | ✔ |
| multiAssetsMargin | /fapi/v1/multiAssetsMargin | ✔ |

🚫 로더는 **GET만** 한다. 서명 조회가 불가능하면(`CredentialsMissing`) 조용히 넘기지 않는다 —
   브라켓·수수료 없이 사이징할 수 없으므로 호출자가 스냅샷 경로를 명시적으로 골라야 한다.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from exchange import rules as R
from exchange.client_types import RestClient
from exchange.errors import RulesError
from exchange.loader_types import EndpointSpec, RawFetch

ENDPOINTS: dict[str, EndpointSpec] = {
    "exchangeInfo": EndpointSpec("/fapi/v1/exchangeInfo", signed=False, per_symbol=False),
    "leverageBracket": EndpointSpec("/fapi/v1/leverageBracket", signed=True, per_symbol=True),
    "commissionRate": EndpointSpec("/fapi/v1/commissionRate", signed=True, per_symbol=True),
    "fundingInfo": EndpointSpec("/fapi/v1/fundingInfo", signed=False, per_symbol=False),
    "positionSideDual": EndpointSpec("/fapi/v1/positionSide/dual", signed=True, per_symbol=False),
    "multiAssetsMargin": EndpointSpec("/fapi/v1/multiAssetsMargin", signed=True, per_symbol=False),
}
REQUIRED = ("exchangeInfo", "leverageBracket", "commissionRate", "fundingInfo")


def utc_iso() -> str:
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}Z"


def build_rules(payloads: Mapping[str, Any], symbol: str, fetched_at: Mapping[str, str]) -> R.RuntimeRules:
    missing = [n for n in REQUIRED if n not in payloads]
    if missing:
        raise RulesError(f"{symbol}: 필수 규칙 {missing} 없음 — 추정값으로 기동하지 않는다")
    ei = payloads["exchangeInfo"]
    modes = None
    has_dual, has_multi = "positionSideDual" in payloads, "multiAssetsMargin" in payloads
    if has_dual != has_multi:
        raise RulesError("positionSideDual과 multiAssetsMargin은 함께 있어야 한다")
    if has_dual:
        modes = R.parse_account_modes(payloads["positionSideDual"], payloads["multiAssetsMargin"])
    st = ei.get("serverTime")
    return R.RuntimeRules(
        symbol=symbol,
        symbol_rules=R.parse_symbol_rules(ei, symbol),
        brackets=R.parse_brackets(payloads["leverageBracket"], symbol),
        commission=R.parse_commission(payloads["commissionRate"], symbol),
        funding=R.parse_funding_info(payloads["fundingInfo"], symbol),
        account_modes=modes,
        rate_limits=R.parse_rate_limits(ei),
        fetched_at_utc=dict(fetched_at),
        server_time_ms=int(st) if st is not None else None,
    )


def fetch_all(client: RestClient, symbol: str, *, clock: Callable[[], str] = utc_iso) -> list[RawFetch]:
    out = []
    for name, spec in ENDPOINTS.items():
        params = {"symbol": symbol} if spec.per_symbol else None
        r = client.get(spec.path, params, signed=spec.signed)
        out.append(RawFetch(name, spec.path, symbol, clock(), r.data))
    return out


def load_runtime_rules(client: RestClient, symbol: str, *,
                       clock: Callable[[], str] = utc_iso) -> tuple[R.RuntimeRules, list[RawFetch]]:
    fetches = fetch_all(client, symbol, clock=clock)
    rules = build_rules({f.endpoint: f.payload for f in fetches}, symbol,
                        {f.endpoint: f.fetched_at_utc for f in fetches})
    return rules, fetches


def rules_from_snapshots(snaps: Mapping[str, Mapping[str, Any]], symbol: str) -> R.RuntimeRules:
    """`{name: {"_meta": {...}, "response": ...}}` 형식(VolumeClockBot·capture_snapshots 공통)."""
    payloads, fetched = {}, {}
    for name, doc in snaps.items():
        if name not in ENDPOINTS:
            continue
        if "response" not in doc:
            raise RulesError(f"스냅샷 {name}: response 없음")
        meta = doc.get("_meta", {})
        payloads[name] = doc["response"]
        fetched[name] = str(meta.get("captured_at_utc") or meta.get("created_at_utc") or "unknown")
    return build_rules(payloads, symbol, fetched)


def rules_from_snapshot_dir(d: Path, symbol: str) -> R.RuntimeRules:
    snaps = {p.stem: json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(Path(d).glob("*.json")) if p.stem in ENDPOINTS}
    return rules_from_snapshots(snaps, symbol)


def capture_snapshots(client: RestClient, symbol: str, out_dir: Path, *,
                      clock: Callable[[], str] = utc_iso) -> list[Path]:
    """read-only GET으로 스냅샷을 떠서 `<name>.json`에 쓴다(tmp → rename). 테스트 fixture·드리프트 기준선용."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for f in fetch_all(client, symbol, clock=clock):
        spec = ENDPOINTS[f.endpoint]
        doc = {"_meta": {"captured_at_utc": f.fetched_at_utc, "endpoint": spec.path, "method": "GET",
                         "read_only": True, "signed": spec.signed, "symbol": symbol},
               "response": f.payload}
        p = out_dir / f"{f.endpoint}.json"
        tmp = out_dir / f".{f.endpoint}.json.tmp"
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.rename(p)
        written.append(p)
    return written
