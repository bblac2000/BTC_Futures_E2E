# Snapshot fixtures — provenance

| file | source | commit | captured | notes |
|---|---|---|---|---|
| exchangeInfo.json | /home/cms/project/VolumeClockBot/snapshots/exchangeInfo.json | 6d0129d | 2026-09-02T10:54:01Z mainnet, read-only GET | symbols filtered to 5, all other fields verbatim |
| leverageBracket.json | /home/cms/project/VolumeClockBot/snapshots/leverageBracket.json | 6d0129d | same | signed GET; numbers stored as JSON numbers (not strings) |
| commissionRate.json | /home/cms/project/VolumeClockBot/snapshots/commissionRate.json | 6d0129d | same | signed GET |
| fundingInfo.json | /home/cms/project/VolumeClockBot/snapshots/fundingInfo.json | 6d0129d | same | full list |
| positionSideDual.json | **synthetic** (this repo) | — | — | no capture exists; value from v6 §1.0(A) |
| multiAssetsMargin.json | **synthetic** (this repo) | — | — | no capture exists; value from v6 §1.0(A) |

Copied verbatim (md5 equal to source at copy time). These are test fixtures and drift baselines, **not** runtime truth —
the bot loads live values at startup (`exchange.loader.load_runtime_rules`).

## Account capture — pending
`positionSideDual.json` and `multiAssetsMargin.json` above are still **synthetic** (`_meta.synthetic: true`).
Replace them by running, with a **read-only** key in `.env`:

```bash
uv run python scripts/capture_account_snapshot.py --dry-run   # 먼저 요약만 확인
uv run python scripts/capture_account_snapshot.py             # 기록 — 이 파일에 캡처 블록이 추가된다
```
The script measures key permissions first and writes nothing if any non-read permission is enabled.
It also writes `positionRisk_v2.json` / `positionRisk_v3.json` (BTCUSDT rows only — the repo is public) and records
whether positionRisk carries an `isolated` field, which settles the open Codex question from data, not docs.

<!-- account-capture:start -->
## Account capture (real, read-only) — 2026-09-15T22:22:57.318Z

Written by `scripts/capture_account_snapshot.py`. Replaces the synthetic fixtures below.
Key permissions measured via `GET /sapi/v1/account/apiRestrictions`: enabled = `['enableReading', 'ipRestrict']` (capture refuses to run if any non-read permission is on).

| file | endpoint | method |
|---|---|---|
| positionSideDual | `/fapi/v1/positionSide/dual` | GET (signed) |
| multiAssetsMargin | `/fapi/v1/multiAssetsMargin` | GET (signed) |
| positionRisk_v2 | `/fapi/v2/positionRisk`?symbol=BTCUSDT | GET (signed) |
| positionRisk_v3 | `/fapi/v3/positionRisk`?symbol=BTCUSDT | GET (signed) |

### positionRisk `isolated` field — settled from this capture (Codex review question)
- v2: rows=1 · has_isolated=**True** · has_marginType=True · positionSides=['BOTH']
- v3: rows=0 · has_isolated=**None** · has_marginType=None
<!-- account-capture:end -->
