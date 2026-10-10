"""트라이얼 #4 시간 청산 일정((c) · 규약 B13·B14 · 사전등록 r3 §1 "청산 (a) 시간" · 결정 5).

- 시계는 트라이얼 #3의 `TimeExitSchedule`을 **수정 없이** 쓴다(체결 봉 t_f → 종료 봉 t_f + 7,200분 · 보유 봉 7,200개 ·
  종료 봉 = ① 펀딩 → ② 시가가 추정 청산가 너머면 청산 → ③ 시가에 time_exit — 재생 루프의 기존 훅).
- 보유 상수는 여기 한 곳이다 — (d)의 tc_v3 설정은 이 값을 import한다.
- **일정이 있는데 새 체결**은 여전히 `PositionBusyError`(원웨이 불변식 위반 · `TimeExitSchedule.observe`)다. 트라이얼 #4가 쓰지 않는
  것은 결정 단계 관문 `busy_check`뿐이다: 포지션 중 극단 인쇄는 정상 기록(`position_busy`)이고 전략 (d)가 남긴다 — 여기서 내보내지 않는다.
"""
from __future__ import annotations

from strategies.trial03.exit_schedule import MissingExitBar, PositionBusyError, TimeExitSchedule

HOLD_MIN = 7_200                                           # r3 §1: 체결 분 + 7,200분 봉 시가(5일)
EVAL_TAIL_MIN = 1_440                                      # r3 §1 표본 규칙: + 24시간(P2 +3 인쇄 지연까지 · 결정 16)
EVAL_SPAN_MIN = HOLD_MIN + EVAL_TAIL_MIN                   # 6일

__all__ = ["EVAL_SPAN_MIN", "EVAL_TAIL_MIN", "HOLD_MIN", "MissingExitBar", "PositionBusyError", "TimeExitSchedule", "schedule"]


def schedule() -> TimeExitSchedule:
    return TimeExitSchedule(HOLD_MIN)
