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
