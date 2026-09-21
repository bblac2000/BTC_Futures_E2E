"""트레이드당 수익률 정의(단계 2a) — 전략 트레이드와 플라시보 트레이드가 **같은 식**을 쓴다.

- **gross_bps**(G1 "비용 전") = 방향 부호 × (청산 기준 mark − 진입 mark) / 진입 mark × 10⁴ — 슬리피지·수수료·펀딩 전.
- **net_bps**(G2 "비용 차감 후") = (청산 뒤 지갑 − 진입 전 지갑) / 진입 명목(수량 × 진입 체결가) × 10⁴ — 엔진이 반영한
  불리 체결(#7)·taker 수수료 양쪽·실펀딩·청산 손실을 전부 포함.
- θ = +10 bps/트레이드는 **net_bps**와 비교한다(명목 대비 bps).
이 정의는 사전등록이 명시하지 않은 **구현 해석**이다 — 2a 보고·Codex 검토(단계 d) 대상.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from exchange.orders import Direction

BPS = Decimal(10_000)


@dataclass(frozen=True)
class TradeReturn:
    gross_bps: Decimal
    net_bps: Decimal
    notional: Decimal
    net_pnl: Decimal


def trade_return(*, direction: Direction, entry_mark: Decimal, exit_ref: Decimal, qty: Decimal, entry_fill: Decimal,
                 wallet_before: Decimal, wallet_after: Decimal) -> TradeReturn:
    sign = Decimal(1) if direction is Direction.LONG else Decimal(-1)
    notional = qty * entry_fill
    net = wallet_after - wallet_before
    return TradeReturn(gross_bps=sign * (exit_ref - entry_mark) / entry_mark * BPS, net_bps=net / notional * BPS,
                       notional=notional, net_pnl=net)
