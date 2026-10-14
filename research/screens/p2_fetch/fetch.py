"""S-xs-carry-1 내려받기(스펙 r6 §1) — START 행 **뒤에** 한 번.

    uv run python -m research.screens.p2_fetch.fetch

- 허용 목록 `research/screens/p2/data/archive_listing_le_2026-06.tsv`의 키만 받는다(목록 해시를 먼저 확인 · 목록 밖 키 없음).
- 2021-01 이전 달은 받지 않는다 · 2026-07 이후 달 이름은 거부(`refuse_reserved_archive`).
- 각 zip을 `.CHECKSUM`(SHA256)과 대조한다 — 실패하면 zip을 지우고 `<zip>.unusable` 표시만 남긴다(로더가 그 심볼-달을 '쓸 수 없음'으로 본다).
- 내용은 열지 않는다(바이트 해시만). 결과 목록 `research/screens/p2/data/fetch_manifest.tsv`(키 · 상태 · SHA256).
"""
from __future__ import annotations

import hashlib
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research.screens.window import refuse_reserved_archive

ROOT = Path(__file__).resolve().parents[3]
LISTING = ROOT / "research" / "screens" / "p2" / "data" / "archive_listing_le_2026-06.tsv"
LISTING_SHA256 = "32cfccee8f366627ae707b8105d2b52ddeac18a36dcbf355634c5ebee9d21d45"
DEST = ROOT / "var" / "p2_archive"
MANIFEST = ROOT / "research" / "screens" / "p2" / "data" / "fetch_manifest.tsv"
BASE = "https://data.binance.vision/"


def keys() -> list[str]:
    raw = LISTING.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LISTING_SHA256:
        raise SystemExit("허용 목록 해시 불일치")
    out = []
    for line in raw.decode().splitlines():
        k = line.split("\t")[0]
        ym = k.rsplit("-", 2)[-2] + "-" + k.rsplit("-", 1)[-1][:2]
        refuse_reserved_archive(Path(k).name)
        if ym >= "2021-01":
            out.append(k)
    return out


def _get(url: str) -> bytes:
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception:                                                     # noqa: BLE001
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(url)


def one(k: str) -> tuple[str, str, str]:
    f = DEST / k
    f.parent.mkdir(parents=True, exist_ok=True)
    f.unlink(missing_ok=True)                                                  # 실패하면 남은 zip이 없도록(표시 파일이 권위)
    try:
        data = _get(BASE + k)
        want = _get(BASE + k + ".CHECKSUM").decode().split()[0].lower()
    except Exception as e:                                                    # noqa: BLE001
        (DEST / (k + ".unusable")).write_text(f"download: {type(e).__name__}\n")
        return k, "unusable:download", ""
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        (DEST / (k + ".unusable")).write_text("checksum mismatch\n")
        return k, "unusable:checksum", got
    f.write_bytes(data)
    return k, "ok", got


def main() -> int:
    if MANIFEST.exists():
        print("거부: 이미 내려받았다(fetch_manifest.tsv)", file=sys.stderr)
        return 2
    ks = keys()
    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(one, ks))
    with MANIFEST.open("x", encoding="utf-8") as fh:
        fh.write("key\tstatus\tsha256\n")
        fh.writelines(f"{k}\t{s}\t{h}\n" for k, s, h in sorted(rows))
    bad = sum(1 for _, s, _ in rows if s != "ok")
    print(f"keys {len(rows)} ok {len(rows) - bad} unusable {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
