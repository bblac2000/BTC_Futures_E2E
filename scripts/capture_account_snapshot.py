"""계정 상태 read-only 캡처 → `tests/fixtures/snapshots/` (합성 fixture 교체용).

사용:  uv run python scripts/capture_account_snapshot.py            # 캡처·기록
       uv run python scripts/capture_account_snapshot.py --dry-run  # 조회·요약만, 파일 안 씀

- 키는 저장소 루트 `.env`(git 미추적)의 `BINANCE_API_KEY`/`BINANCE_API_SECRET`에서 읽는다. 값을 출력하지 않는다.
- 🔴 **POST 없음.** 클라이언트를 `ReadOnlyClient`로 감싸 계정 변경 요청이 구조적으로 불가능하다.
  주문·레버리지·마진 타입·포지션 모드 **변경** 엔드포인트는 이 파일에 없다(`tests/test_capture_script.py`가 AST로 확인).
- 🔴 **키 권한을 먼저 실측한다**(`GET /sapi/v1/account/apiRestrictions`). 읽기 외 권한(선물·현물 거래, 출금,
  이체 등)이 하나라도 켜져 있으면 **아무 파일도 쓰지 않고 종료**(exit 2).
- 공개 저장소이므로 positionRisk는 **BTCUSDT 행만** 받는다(`symbol=BTCUSDT`). 권한은 bool 플래그만 기록한다.

캡처 대상(서명 GET):
| 파일 | 엔드포인트 |
|---|---|
| positionSideDual.json | /fapi/v1/positionSide/dual |
| multiAssetsMargin.json | /fapi/v1/multiAssetsMargin |
| positionRisk_v2.json | /fapi/v2/positionRisk?symbol=BTCUSDT |
| positionRisk_v3.json | /fapi/v3/positionRisk?symbol=BTCUSDT (없으면 '사용 불가'로 기록) |

Codex 검토 질문("positionRisk에 `isolated` bool이 있는가")은 문서가 아니라 **이 캡처의 필드 존재 여부**로 판정해
PROVENANCE.md에 기록한다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exchange.ccxt_rest import CcxtRestClient  # noqa: E402
from exchange.client import ReadOnlyClient  # noqa: E402
from exchange.client_types import RestClient  # noqa: E402
from exchange.errors import BinanceAPIError, TransportError  # noqa: E402

SYMBOL = "BTCUSDT"
OUT_DIR = ROOT / "tests" / "fixtures" / "snapshots"
PROV_START = "<!-- account-capture:start -->"
PROV_END = "<!-- account-capture:end -->"

#  읽기 외 권한 — 하나라도 true면 캡처 거부
NON_READ_PERMISSIONS = ("enableFutures", "enableSpotAndMarginTrading", "enableMargin", "enableWithdrawals",
                        "enableInternalTransfer", "permitsUniversalTransfer", "enableVanillaOptions",
                        "enablePortfolioMarginTrading", "enableFixApiTrade")

CAPTURES: tuple[tuple[str, str, dict | None, bool], ...] = (
    # (파일 이름, 경로, 파라미터, 필수 여부)
    ("positionSideDual", "/fapi/v1/positionSide/dual", None, True),
    ("multiAssetsMargin", "/fapi/v1/multiAssetsMargin", None, True),
    ("positionRisk_v2", "/fapi/v2/positionRisk", {"symbol": SYMBOL}, True),
    ("positionRisk_v3", "/fapi/v3/positionRisk", {"symbol": SYMBOL}, False),
)


class NotReadOnlyKey(RuntimeError):
    pass


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def utc_iso(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + f".{ms % 1000:03d}Z"


def check_permissions(sapi: RestClient) -> dict[str, bool]:
    data = sapi.get("/sapi/v1/account/apiRestrictions", signed=True).data
    if not isinstance(data, dict):
        raise NotReadOnlyKey(f"apiRestrictions 응답 해석 불가: {type(data).__name__}")
    flags = {k: v for k, v in data.items() if isinstance(v, bool)}
    if flags.get("enableReading") is not True:
        raise NotReadOnlyKey("enableReading이 true가 아니다 — 읽기 권한 키가 아니다")
    on = [k for k in NON_READ_PERMISSIONS if flags.get(k) is True]
    if on:
        raise NotReadOnlyKey(f"읽기 외 권한이 켜져 있다: {on} — 캡처 거부(아무 파일도 쓰지 않음)")
    return flags


def field_presence(rows: Any) -> dict[str, Any]:
    """positionRisk 행의 필드 존재 요약 — `isolated` 질문을 캡처로 판정한다."""
    if not isinstance(rows, list) or not rows:
        return {"rows": 0}
    keys = sorted({k for r in rows if isinstance(r, dict) for k in r})
    return {"rows": len(rows), "has_isolated": "isolated" in keys, "has_marginType": "marginType" in keys,
            "positionSides": sorted({str(r.get("positionSide")) for r in rows if isinstance(r, dict)}),
            "fields": keys}


def capture(fapi: RestClient, sapi: RestClient, out_dir: Path, *, clock_ms: Callable[[], int],
            server_ms: int | None, dry_run: bool = False) -> dict[str, Any]:
    fapi, sapi = ReadOnlyClient(fapi), ReadOnlyClient(sapi)          # 🔴 POST 구조적 불가
    perms = check_permissions(sapi)                                    # 실패 시 여기서 끝 — 쓰기 전
    captured_at = utc_iso(clock_ms())
    docs: dict[str, dict] = {}
    unavailable: dict[str, str] = {}
    for name, path, params, required in CAPTURES:
        try:
            data = fapi.get(path, params, signed=True).data
        except (BinanceAPIError, TransportError) as e:
            if required:
                raise
            unavailable[name] = f"{path}: {e}"
            continue
        docs[name] = {"_meta": {"captured_at_utc": captured_at, "server_time_ms": server_ms,
                                "endpoint": path, "params": params, "method": "GET", "signed": True,
                                "read_only": True, "synthetic": False,
                                "key_permissions": perms, "script": "scripts/capture_account_snapshot.py"},
                      "response": data}
    summary = {"captured_at_utc": captured_at, "key_permissions": perms, "unavailable": unavailable,
               "positionRisk_v2": field_presence(docs.get("positionRisk_v2", {}).get("response")),
               "positionRisk_v3": field_presence(docs.get("positionRisk_v3", {}).get("response"))
               if "positionRisk_v3" in docs else None,
               "written": []}
    if dry_run:
        return summary
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, doc in docs.items():
        p, tmp = out_dir / f"{name}.json", out_dir / f".{name}.json.tmp"
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.rename(p)
        summary["written"].append(p.name)
    update_provenance(out_dir / "PROVENANCE.md", summary)
    return summary


def update_provenance(path: Path, s: dict[str, Any]) -> None:
    perms_on = sorted(k for k, v in s["key_permissions"].items() if v)
    v2, v3 = s["positionRisk_v2"], s["positionRisk_v3"]
    lines = [
        PROV_START,
        f"## Account capture (real, read-only) — {s['captured_at_utc']}",
        "",
        "Written by `scripts/capture_account_snapshot.py`. Replaces the synthetic fixtures below.",
        f"Key permissions measured via `GET /sapi/v1/account/apiRestrictions`: enabled = `{perms_on}` "
        "(capture refuses to run if any non-read permission is on).",
        "",
        "| file | endpoint | method |",
        "|---|---|---|",
        *[f"| {n} | `{p}`{'?symbol=' + SYMBOL if q else ''} | GET (signed) |"
          for n, p, q, _r in CAPTURES if f"{n}.json" in s["written"]],
        "",
        "### positionRisk `isolated` field — settled from this capture (Codex review question)",
        f"- v2: rows={v2.get('rows')} · has_isolated=**{v2.get('has_isolated')}** · has_marginType={v2.get('has_marginType')}"
        f" · positionSides={v2.get('positionSides')}",
        f"- v3: {'unavailable: ' + s['unavailable'].get('positionRisk_v3', '') if v3 is None else ''}"
        + ("" if v3 is None else f"rows={v3.get('rows')} · has_isolated=**{v3.get('has_isolated')}** · "
                                 f"has_marginType={v3.get('has_marginType')}"),
        PROV_END,
    ]
    block = "\n".join(lines)
    text = path.read_text(encoding="utf-8") if path.exists() else "# Snapshot fixtures — provenance\n"
    if PROV_START in text and PROV_END in text:
        a, rest = text.split(PROV_START, 1)
        _old, b = rest.split(PROV_END, 1)
        text = a + block + b
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="계정 상태 read-only 캡처")
    ap.add_argument("--dry-run", action="store_true", help="조회·요약만 출력, 파일을 쓰지 않는다")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    a = ap.parse_args(argv)
    env = load_env(ROOT / ".env")
    key, secret = env.get("BINANCE_API_KEY"), env.get("BINANCE_API_SECRET")
    if not key or not secret:
        print("BINANCE_API_KEY / BINANCE_API_SECRET이 .env에 없다", file=sys.stderr)
        return 1
    wall: Callable[[], int] = lambda: int(time.time() * 1000)  # noqa: E731
    #  전송 = ccxt(레지스트리 #8). 한 클라이언트가 /fapi·/sapi 경로를 모두 받는다 — capture()가 ReadOnlyClient로 감싼다.
    client = CcxtRestClient(api_key=key, secret=secret, clock_ms=wall)
    offset = client.sync_time()
    try:
        s = capture(client, client, a.out, clock_ms=wall, server_ms=wall() + offset, dry_run=a.dry_run)
    except NotReadOnlyKey as e:
        print(f"🚫 {e}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in s.items() if k != "key_permissions"}, ensure_ascii=False, indent=1))
    print(f"enabled permissions: {sorted(k for k, v in s['key_permissions'].items() if v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
