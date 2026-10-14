"""S-carry-1 로더(스펙 §2) — 창 가드 읽기만. 장부는 청산 시각(첫 칸)으로, DTB3는 관측 날짜로 거른다."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research.screens.window import bounded_benchmark_csv, bounded_csv_file

DATA = Path(__file__).resolve().parent / "data"
LEDGER = DATA / "carrybot_trades.csv"
DTB3 = DATA / "DTB3_2020-12-01_2026-06-30.csv"
LEDGER_COLS = ("exit_ms", "entry_ms", "run", "notional", "locked", "funding_collected", "funding_paid", "residual_delta_pnl", "fees",
               "slippage", "opportunity_cost", "net_pnl", "holding_periods", "exit_reason", "forced")


@dataclass(frozen=True)
class Trade:
    run: str
    entry_ms: int
    exit_ms: int
    notional: float
    locked: float
    funding_collected: float
    residual_delta_pnl: float
    fees: float
    slippage: float
    opportunity_cost: float
    net_pnl: float


def _trade(line: str) -> Trade:
    c = dict(zip(LEDGER_COLS, line.rstrip("\r\n").split(","), strict=True))
    return Trade(c["run"], int(c["entry_ms"]), int(c["exit_ms"]), float(c["notional"]), float(c["locked"]),
                 float(c["funding_collected"]), float(c["residual_delta_pnl"]), float(c["fees"]), float(c["slippage"]),
                 float(c["opportunity_cost"]), float(c["net_pnl"]))


def trades(path: Path = LEDGER) -> tuple[list[Trade], int]:
    """(창 안에서 닫힌 거래, 버린 거래 수) — 청산이 2026-06-30 뒤인 거래는 값 해석 없이 버린다."""
    dropped = [0]
    out = list(bounded_csv_file(path, _trade, ts_field=0, header=True, dropped=dropped))
    return out, dropped[0]


def _rate(line: str) -> tuple[str, float | None]:
    d, v = line.rstrip("\r\n").split(",")
    return d, (None if v.strip() in ("", ".") else float(v))


def dtb3(path: Path = DTB3) -> list[tuple[str, float]]:
    """(날짜, 연율 %) — 벤치마크 예외(#108): 창 시작 10일 전부터 · 관측 없는 날(빈 칸 · ".")은 뺀다."""
    return [(d, v) for d, v in bounded_benchmark_csv(path, _rate) if v is not None]
