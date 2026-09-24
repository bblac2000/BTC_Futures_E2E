"""트라이얼 #2 런타임 규칙 스냅샷 캡처(사용자 결정 2026-09-24 (a) · 레지스트리 #36) — read-only GET만.

    uv run python scripts/capture_trial02_rules.py

- 출처 하나: 이 캡처(앵커 뒤 같은 날 · 2026-09-24 UTC). 대체 경로(2026-09-02 fixture) 없음.
- 대상: exchangeInfo · leverageBracket · commissionRate(서명 GET) + fundingInfo(공개 GET — `build_rules`의 필수 입력이라
  다른 출처와 섞지 않으려고 같은 캡처에서 받는다).
- 🔴 POST 없음(`ReadOnlyClient`) · 키 권한을 먼저 실측 — 읽기 외 권한이 켜져 있으면 아무것도 쓰지 않는다.
- taker 수수료가 사전등록 §2의 5 bps(0.0005)가 아니면 `TakerMismatch` — 아무것도 쓰지 않는다(§2 정정이 필요한 경우).
- 출력: `docs/trials/trial_02_rules_snapshot/<name>.json` + 파일별 SHA256(표준출력 · 레지스트리 행에 고정).
- 키 값은 출력하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exchange.client import ReadOnlyClient  # noqa: E402
from exchange.client_types import RestClient  # noqa: E402
from exchange.loader import ENDPOINTS, rules_from_snapshot_dir  # noqa: E402
from exchange.permissions import NotReadOnlyKey, check_permissions  # noqa: E402,F401
from exchange.rules import RuntimeRules  # noqa: E402

SYMBOL = "BTCUSDT"
OUT_DIR = ROOT / "docs" / "trials" / "trial_02_rules_snapshot"
NAMES = ("exchangeInfo", "leverageBracket", "commissionRate", "fundingInfo")
PREREG_TAKER = Decimal("0.0005")          # 사전등록 §2 taker 5 bps(비교 기준 — 거래소 값의 대체가 아니다)


class TakerMismatch(RuntimeError):
    pass


def utc_iso(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + f".{ms % 1000:03d}Z"


def load(d: Path) -> RuntimeRules:
    return rules_from_snapshot_dir(d, SYMBOL)


def capture(client: RestClient, out_dir: Path, *, clock_ms: Callable[[], int]) -> dict[str, Any]:
    ro = ReadOnlyClient(client)
    check_permissions(ro)                                           # 실패 시 여기서 끝 — 쓰기 전
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        for name in NAMES:
            spec = ENDPOINTS[name]
            params = {"symbol": SYMBOL} if spec.per_symbol else None
            captured = utc_iso(clock_ms())
            data = ro.get(spec.path, params, signed=spec.signed).data
            doc = {"_meta": {"captured_at_utc": captured, "endpoint": spec.path, "params": params, "method": "GET",
                             "signed": spec.signed, "read_only": True, "symbol": SYMBOL,
                             "purpose": "trial #2 runtime rules (registry #36) — single source, no fallback",
                             "script": "scripts/capture_trial02_rules.py"},
                   "response": data}
            (tmp / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        rules = load(tmp)                                           # 파싱 실패(RulesError)도 쓰기 전
        if rules.commission.taker != PREREG_TAKER:
            raise TakerMismatch(f"taker {rules.commission.taker} ≠ 사전등록 §2 {PREREG_TAKER} — §2 정정 필요")
        out_dir.mkdir(parents=True, exist_ok=True)
        sha = {}
        for name in NAMES:
            shutil.copyfile(tmp / f"{name}.json", out_dir / f"{name}.json")
            sha[name] = hashlib.sha256((out_dir / f"{name}.json").read_bytes()).hexdigest()
    return {"sha256": sha, "taker": str(rules.commission.taker.normalize()),
            "maker": str(rules.commission.maker.normalize()),
            "captured_at_utc": {n: json.loads((out_dir / f"{n}.json").read_text())["_meta"]["captured_at_utc"]
                                for n in NAMES}}


def main() -> int:
    from exchange.ccxt_rest import CcxtRestClient
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    key, secret = env.get("BINANCE_API_KEY"), env.get("BINANCE_API_SECRET")
    if not key or not secret:
        print("BINANCE_API_KEY / BINANCE_API_SECRET이 .env에 없다", file=sys.stderr)
        return 1
    wall: Callable[[], int] = lambda: int(time.time() * 1000)  # noqa: E731
    client = CcxtRestClient(api_key=key, secret=secret, clock_ms=wall)
    client.sync_time()
    try:
        s = capture(client, OUT_DIR, clock_ms=wall)
    except (NotReadOnlyKey, TakerMismatch) as e:
        print(f"🚫 {e}", file=sys.stderr)
        return 2
    print(json.dumps(s, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
