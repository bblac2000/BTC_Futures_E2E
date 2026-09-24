"""LIVE 기본 경로 골든 시나리오(단계 2b·2c after-pass · Codex #4) — 2b 이전 트리(bdf0554)와 현재 트리에서 같은 출력이어야 한다.

LIVE 흉내 송신기(SpySender)로: 롱 진입(틱) → 펀딩 경계 → SL 청산 / 숏 진입 → TP / 트레일 켠 롱 → 트레일 청산.
출력 = 이벤트 종류·시각·핵심 값 + 송신기 호출 열(JSON). 네트워크·실데이터 없음.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from exchange.gate import Mode  # noqa: E402
from exchange.loader import rules_from_snapshot_dir  # noqa: E402
from exchange.orders import Direction  # noqa: E402
from paper.engine import Engine, Trail  # noqa: E402
from paper.sender import PaperSender  # noqa: E402
from sizing.config import SizingLimits  # noqa: E402
from tests.test_paper_engine import DAY0, W0, H, SpySender, intent, tick  # noqa: E402

D = Decimal


def _ev(e: object) -> list:
    keep = ("ts_ms", "reason", "qty", "entry_price", "exit_price", "realized_pnl_usdt", "wallet_after", "paid", "old", "new",
            "leverage", "dist", "r")
    return [type(e).__name__] + [str(getattr(e, k)) for k in keep if hasattr(e, k)]


def run() -> dict:
    rules = rules_from_snapshot_dir(Path(__file__).resolve().parent / "snapshots", "BTCUSDT")
    out: dict = {}
    for name, direction, marks, trail in (
            ("long_sl", Direction.LONG, ["60000", "60100", "59900", "59600", "59500"], None),
            ("short_tp", Direction.SHORT, ["60000", "59800", "59500", "59300"], None),
            ("long_trail", Direction.LONG, ["60000", "60400", "60800", "60500", "60300"], Trail(D("1"), D("200")))):
        s = SpySender(PaperSender(rules), mode=Mode.LIVE, exchange_liq=D("1"))
        e = Engine(rules, s, mode=Mode.LIVE, wallet=W0, limits=SizingLimits())
        tp = "59400" if direction is Direction.SHORT else None
        it = intent(direction, tp=tp)
        if trail is not None:
            from dataclasses import replace
            it = replace(it, trail=trail)
        e.request_entry(it)
        evs: list = []
        for i, m in enumerate(marks):
            ts = DAY0 + 1000 + i * (3 * H)                  # 3h 간격 — 08:00 펀딩 경계를 지난다
            if i == 1 and e.position is not None:
                s.exchange_amt = e.position.signed_qty
            evs += [_ev(x) for x in e.on_tick(tick(ts, m))]
        out[name] = {"events": evs, "calls": [[str(c) for c in call] for call in s.calls], "wallet": str(e.wallet)}
    return out


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
