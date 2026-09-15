# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is
BTCUSDT USDⓈ-M perpetual bot. Paper first (Tokyo VPS, 1 month), live only after user approval **and** the live checklist.
Binding rules, in precedence order: `.claude/skills/quant-bot-constitution/` (read SKILL.md + references first) → `docs/바이낸스문서API_2026_v6.md` (never edit; append dated corrections only) → `docs/design_v1.md`.
Fixed decisions, build order, and the E2E reuse table live in `docs/design_v1.md` — do not re-open them.

## Commands
```bash
uv sync                                   # env (py3.12)
uv run pytest                             # all tests
uv run pytest tests/test_gate.py::test_live_aborts_when_reread_is_not_isolated   # single test
uv run ruff check .
uv run pyright
uv run python -m ops.stream_tiers --scan  # two-way WS URL scan (CI runs this too)
```
TDD: write the test, see it fail, then implement.

## Architecture (build order — strategy-independent layers first)
1 `exchange/` runtime rules → 2 `sizing/` → 3 `paper/` → 4 `db/` → 5 `data/` → 6 `notify/` → 7 `safety/` → 8 `ops/`. `strategies/` only after 1–8 pass, and only after a pre-registration row in `docs/trial_registry.md` (append-only).
- `exchange/rules.py` parses exchange responses into Decimal dataclasses (`RuntimeRules`). Missing data raises `RulesError` — never default. `loader.py` fetches or loads snapshots; `store.py` persists raw payloads to `runtime_rules`.
- `exchange/normalize.py` → `orders.py`: floor qty → recheck MIN_NOTIONAL after flooring → split by MARKET_LOT maxQty; `Direction` and `Side` are distinct types so a direction can never reach `side`. Orders are built and validated, not sent.
- `exchange/gate.py`: LIVE mutates the account (one-way, ISOLATED confirmed by re-read, leverage) and raises `StartupAbort` (entries off, exits on) on any failure. PAPER wraps the client in `ReadOnlyClient`, so it makes zero POSTs.
- `paper/engine.py` is one engine for PAPER and LIVE; only the `OrderSender` differs. `LiveSender` (`paper/sender.py`) cannot be constructed without `Mode.LIVE` + every `LiveChecklist` item True + a writable client. Strategies submit an `EntryIntent`; sizing re-runs at the execution mark.
- `scripts/testnet_fee_probe.py` sends real orders **to testnet only** (per-request host allowlist, redirects refused). Its verdict rule is pre-committed in `docs/design_v1.md` §11.
- `ops/stream_tiers.py` is the only place WS endpoint URLs may be built (`build_stream_url`). Legacy `/ws` `/stream` URLs and hand-written tier URLs fail the scan. `ops/delivery_counter.py` detects silent zero-delivery streams per stream.
- Files copied from `/home/cms/project/E2E_Hybrid_Bot` carry a PROVENANCE header. Log any change to a copied file in `docs/ops_log.md`. Never import E2E at runtime.

## Hard rules
- No exchange values as literals in `exchange/` `sizing/` `paper/` (tick/step/MIN_NOTIONAL/MMR/fees/funding caps/brackets). `tests/test_no_exchange_literals.py` enforces this.
- MARKET only; exits `reduceOnly="true"`; no server-side STOP/TP; `side` is BUY/SELL only.
- Anything touching deletion, live trading, funds, or the E2E collector host needs Codex review before deploy.
- Thresholds, windows and gates are pre-committed. Never change them after seeing results; add a registry row instead.
- No Donchian code in this repo. Any Donchian proposal must first state how it differs from E2E #74.
