"""트라이얼 #3 시간 청산 일정(단계 2 (c) · 계획 r4 · 사전등록 §1 31행 · 사용자 결정 (A) 2026-09-30).

- 체결 봉 t_f(= `EntryFilled`가 든 봉의 open_ms) → 종료 봉 = t_f + 240분(`due`). 보유 = 봉 t_f … t_f+239(240봉).
- 종료 봉 처리는 재생 루프의 기존 훅(`exit_at_bar_open`)이 한다: ① 펀딩 → ② 시가가 추정 청산가 너머면 청산 → ③ 아니면 시가에
  `time_exit`(그 봉의 고가·저가는 판정하지 않는다). t_f … t_f+239는 엔진 경로 그대로(청산 → SL · 봉 안 고가·저가).
- 더 이른 청산(SL·청산)은 일정을 지운다. 종료 봉이 없으면(§1 35행 판정 가능 구간이 보장하므로 백테스트에서는 버그) 실행 실패:
  다음 봉에서 `guard`(재생의 `before_minute` — 펀딩·엔진 처리 전) 또는 입력 끝에서 `assert_no_due`.
- 포지션(또는 대기 진입) 중의 적격 이벤트 = `position_busy`를 전략 소유 기록에 남기고 실행 실패(쿨다운 720분 > 최대 구간 366분이라
  구조적으로 도달 불가 — 불변식 검사).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backtest.data import MINUTE_MS, Bar1m
from paper.types import EntryFilled, PositionClosed

HOLD_MIN = 240                                             # §1 H = 4시간(tf_v1)


class MissingExitBar(RuntimeError):
    """종료 봉 t_f+240이 입력에 없다 — 판정 가능 구간 위반(실행 실패)."""


class PositionBusyError(RuntimeError):
    """포지션(또는 대기 진입) 중 적격 이벤트 — 구조적으로 도달 불가(실행 실패)."""


class TimeExitSchedule:
    def __init__(self, hold_min: int = HOLD_MIN):
        self.hold_ms = hold_min * MINUTE_MS
        self.due: int | None = None

    def observe(self, bar: Bar1m, bar_events: Iterable[object]) -> None:
        """분 마감에 그 분의 엔진 이벤트로 일정을 갱신한다(체결 → 설정 · 청산 → 삭제)."""
        for ev in bar_events:
            if isinstance(ev, EntryFilled):
                if self.due is not None:
                    raise PositionBusyError(f"일정이 있는데 새 체결 {bar.open_ms}")
                self.due = bar.open_ms + self.hold_ms
            elif isinstance(ev, PositionClosed):
                self.due = None

    def exit_at_bar_open(self, bar: Bar1m) -> bool:
        return self.due is not None and bar.open_ms == self.due

    def guard(self, bar: Bar1m) -> None:
        if self.due is not None and bar.open_ms > self.due:
            raise MissingExitBar(f"종료 봉 {self.due}가 없다(다음 봉 {bar.open_ms})")

    def assert_no_due(self) -> None:
        if self.due is not None:
            raise MissingExitBar(f"입력이 종료 봉 {self.due} 전에 끝났다")


def busy_check(ctx: Any, log: list[dict[str, Any]], ts_ms: int) -> None:
    """적격 이벤트를 내기 직전에 부른다: 포지션·대기 진입이 있으면 기록(§7-3 `position_busy`) 후 실행 실패."""
    if ctx.has_position:
        log.append({"ts_ms": ts_ms, "reason": "position_busy"})
        ctx.skip("position_busy")
        raise PositionBusyError(f"{ts_ms}: 포지션 중 적격 이벤트")
