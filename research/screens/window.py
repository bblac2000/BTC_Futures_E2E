"""스크린 자료 창과 예약 구간 가드(docs/screen_protocol.md §4 · 사용자 결정 D4).

스크린은 [2021-01-01, 2026-06-30] UTC만 읽는다. 2026-07-01부터는 예약 구간이고 **우회 인자가 없다** — 정식 트라이얼이
이 구간을 읽게 하려면 코드 변경과 레지스트리 행이 필요하다. 모든 스크린 로더는 `bounded`로만 자료를 읽는다:
원시 항목에서 시각만 먼저 꺼내고(`ts_of`), 창 안의 항목에만 값 해석(`parse`)을 부른다.
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Iterable, Iterator

SCREEN_START_MS = int(dt.datetime(2021, 1, 1, tzinfo=dt.UTC).timestamp() * 1000)
SCREEN_END_MS = int(dt.datetime(2026, 7, 1, tzinfo=dt.UTC).timestamp() * 1000) - 1      # 2026-06-30 23:59:59.999Z
_MONTH = re.compile(r"(20\d\d)-(\d\d)")


class ReserveError(RuntimeError):
    """예약 구간(2026-07-01~) 또는 창 밖 자료를 읽으려 했다."""


def require_window(start_ms: int, end_ms: int) -> None:
    """I/O 전에 부른다 — 요청 범위가 스크린 창 안이 아니면 거부."""
    if not (isinstance(start_ms, int) and isinstance(end_ms, int)) or isinstance(start_ms, bool) or isinstance(end_ms, bool):
        raise ReserveError(f"시각은 UTC 밀리초 정수여야 한다: {start_ms!r}, {end_ms!r}")
    if not (SCREEN_START_MS <= start_ms <= end_ms <= SCREEN_END_MS):
        raise ReserveError(f"범위 [{start_ms}, {end_ms}]가 스크린 창 [{SCREEN_START_MS}, {SCREEN_END_MS}] 밖")


def refuse_reserved_archive(name: str) -> None:
    """파일을 열기 전에 부른다 — 이름이 2026-06 뒤의 달을 가리키면 거부(월별·일별 아카이브)."""
    for y, m in _MONTH.findall(name):
        if (int(y), int(m)) > (2026, 6):
            raise ReserveError(f"예약 구간 아카이브는 열지 않는다: {name}")


def bounded[R, T](raw_items: Iterable[R], ts_of: Callable[[R], int], parse: Callable[[R], T], *, start_ms: int = SCREEN_START_MS,
                  end_ms: int = SCREEN_END_MS, dropped: list[int] | None = None) -> Iterator[T]:
    """원시 항목을 게으르게 받아 창 안의 것만 `parse`한다. 창 밖 항목은 값 해석 없이 버리고 센다(`dropped[0]`)."""
    require_window(start_ms, end_ms)
    for raw in raw_items:
        t = ts_of(raw)
        if not isinstance(t, int) or isinstance(t, bool) or t < 0:
            raise ReserveError(f"시각을 읽을 수 없다: {t!r}")
        if start_ms <= t <= end_ms:
            yield parse(raw)
        elif dropped is not None:
            dropped[0] += 1


def assert_within(ts_values: Iterable[int], *, end_ms: int = SCREEN_END_MS) -> None:
    """계산에 넘기기 직전 — 결과 구간(보유·다음 주 수익률)의 마지막 시각까지 포함해 검사한다."""
    require_window(SCREEN_START_MS, end_ms)
    for t in ts_values:
        if not (SCREEN_START_MS <= t <= end_ms):
            raise ReserveError(f"창 밖 시각이 계산에 들어왔다: {t}")
