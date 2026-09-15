"""봉마다 대사 — 봇 내부 포지션 ↔ 거래소 positionRisk(LIVE만, 레지스트리 #6) ↔ DB `positions`(strategy-modules §6).

- 비교는 **부호 있는 수량**(Decimal 정확 일치). 평균가는 거래소·체결 VWAP 반올림이 달라 판정에 쓰지 않는다.
- PAPER에 거래소 값을 넘기면 `ValueError`(페이퍼 포지션은 거래소에 없다 — 다른 포지션과 비교하는 오류를 막는다).
- 불일치 → 신규 진입 금지 + 알림. 수량·방향 불일치는 **사람이 확인할 때까지 유지**(sticky), 거래소 조회 실패는 다음 성공 조회로 풀린다.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from db.record import DbPosition
from exchange.gate import Mode
from paper.types import PositionRisk

__all__ = ["DbPosition", "ReconcileGuard", "ReconcileResult", "reconcile"]


@dataclass(frozen=True)
class ReconcileResult:
    ok: bool
    mismatches: tuple[str, ...]
    internal_signed: Decimal
    exchange_signed: Decimal | None
    db_signed: Decimal
    detail: str

    @property
    def sticky(self) -> bool:
        return any(m != "exchange_unavailable" for m in self.mismatches)


def reconcile(mode: Mode, *, internal_signed: Decimal, exchange: PositionRisk | None, exchange_error: str | None,
              db: DbPosition | None) -> ReconcileResult:
    db_signed = db.signed if db is not None else Decimal(0)
    mism: list[str] = []
    ex_signed: Decimal | None = None
    if mode is Mode.PAPER:
        if exchange is not None or exchange_error is not None:
            raise ValueError("PAPER 대사에 거래소 positionRisk를 쓰지 않는다(레지스트리 #6)")
    else:
        if exchange is None:
            mism.append("exchange_unavailable")
        else:
            ex_signed = exchange.amt
            if ex_signed != internal_signed:
                mism.append("internal_vs_exchange")
    if db_signed != internal_signed:
        mism.append("internal_vs_db")
    detail = f"내부 {internal_signed} · 거래소 {ex_signed if exchange is not None else exchange_error or '-'} · DB {db_signed}"
    return ReconcileResult(not mism, tuple(mism), internal_signed, ex_signed, db_signed, detail)


class ReconcileGuard:
    def __init__(self) -> None:
        self.blocker: str | None = None          # 사유 종류만(수치는 알림 문구에) — 수치가 바뀔 때마다 재알림하지 않게
        self.sticky = False
        self.last: ReconcileResult | None = None
        self.alerts_sent = 0

    def update(self, result: ReconcileResult) -> list[str]:
        """차단 상태가 **바뀌면** 알림 문구 목록을 돌려준다(같은 상태 반복 알림 없음)."""
        self.last = result
        before = self.blocker
        if result.sticky:
            self.sticky = True
            self.blocker = f"reconcile:{','.join(result.mismatches)}"
        elif not result.ok:
            if not self.sticky:                      # 조회 실패가 이미 걸린 sticky 사유를 덮지 않는다
                self.blocker = "reconcile:exchange_unavailable"
        elif not self.sticky:
            self.blocker = None
        if self.blocker == before:
            return []
        self.alerts_sent += 1
        return [f"대사 불일치 — 신규 진입 금지: {self.blocker} · {result.detail}" if self.blocker
                else f"대사 회복 — 차단 해제 · {result.detail}"]

    def resume(self, *, actor: str) -> str:
        if not actor:
            raise ValueError("재개는 사람(actor)만")
        was, self.blocker, self.sticky = self.blocker, None, False
        return f"대사 차단 해제 ({actor})" if was else ""

    def to_state(self) -> dict:
        return {"blocker": self.blocker, "sticky": self.sticky}

    def restore(self, state: dict) -> None:
        self.blocker, self.sticky = state.get("blocker"), bool(state.get("sticky"))
