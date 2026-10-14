"""스크린 자료 창과 예약 구간 가드(docs/screen_protocol.md §4 · 사용자 결정 D4).

스크린은 [2021-01-01, 2026-06-30] UTC만 읽는다. 2026-07-01부터는 예약 구간이고 **우회 인자가 없다** — 정식 트라이얼이
이 구간을 읽게 하려면 코드 변경과 레지스트리 행이 필요하다.

스크린 로더가 쓸 수 있는 읽기 경로는 이 모듈의 셋뿐이다(시험이 강제):
- `bounded_csv_file` · `bounded_zip_csv`: 파일을 **이 모듈이** 열고, 줄마다 시각 칸만 잘라 읽은 뒤 창 안의 줄만 `parse`에 넘긴다.
  호출자가 주는 것은 경로와 `parse`뿐이라, 호출자 코드가 예약 구간 줄의 값을 해석할 기회가 없다.
- `bounded_records`: 요청 단계에서 이미 창으로 묶은 API 응답(행 목록)용 — 창 밖 행이 하나라도 오면 버리지 않고 **예외**다.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

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


def _bounded[R, T](raw_items: Iterable[R], ts_of: Callable[[R], int], parse: Callable[[R], T], *, start_ms: int = SCREEN_START_MS,
                  end_ms: int = SCREEN_END_MS, dropped: list[int] | None = None) -> Iterator[T]:
    """(모듈 내부용) 원시 항목을 게으르게 받아 창 안의 것만 `parse`한다. 창 밖 항목은 값 해석 없이 버리고 센다(`dropped[0]`)."""
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


def _ts_of_line(ts_field: int, ts_kind: str, delimiter: str) -> Callable[[str], int]:
    """줄에서 **시각 칸만** 잘라 UTC 밀리초로 — 다른 칸은 건드리지 않는다. `ms`: 정수(마이크로초면 밀리초로) · `iso`: UTC로 읽는 ISO 문자열."""
    if ts_kind not in ("ms", "iso"):
        raise ValueError(ts_kind)

    def ts_of(line: str) -> int:
        cell = line.split(delimiter, ts_field + 1)[ts_field].strip()
        if ts_kind == "ms":
            if not cell.isdigit():
                raise ReserveError(f"시각 칸이 정수가 아니다: {cell!r}")
            v = int(cell)
            return v // 1000 if v >= 10**15 else v                           # 2025년부터 현물 아카이브는 마이크로초
        try:
            d = dt.datetime.fromisoformat(cell)
        except ValueError as e:
            raise ReserveError(f"시각 칸을 읽을 수 없다: {cell!r}") from e
        return int((d if d.tzinfo else d.replace(tzinfo=dt.UTC)).timestamp() * 1000)

    return ts_of


def _data_lines(fh: Iterable[str], header: bool) -> Iterator[str]:
    first = True
    for line in fh:
        if first:
            first = False
            if header:
                continue
        if line.strip():
            yield line


def bounded_csv_file[T](path: Path, parse: Callable[[str], T], *, ts_field: int = 0, ts_kind: str = "ms", header: bool = False,
                        delimiter: str = ",", start_ms: int = SCREEN_START_MS, end_ms: int = SCREEN_END_MS,
                        dropped: list[int] | None = None) -> Iterator[T]:
    """CSV 파일을 열어 창 안의 줄만 `parse(줄)`한다. 이름이 예약 구간의 달이면 열기 전에 거부."""
    require_window(start_ms, end_ms)
    refuse_reserved_archive(Path(path).name)
    with Path(path).open(encoding="utf-8", newline="") as fh:
        yield from _bounded(_data_lines(fh, header), _ts_of_line(ts_field, ts_kind, delimiter), parse, start_ms=start_ms, end_ms=end_ms,
                            dropped=dropped)


def bounded_zip_csv[T](path: Path, parse: Callable[[str], T], *, ts_field: int = 0, ts_kind: str = "ms", header: bool | None = None,
                       delimiter: str = ",", start_ms: int = SCREEN_START_MS, end_ms: int = SCREEN_END_MS,
                       dropped: list[int] | None = None) -> Iterator[T]:
    """binance.vision 식 zip(안에 CSV 하나)을 열어 창 안의 줄만 `parse`한다. `header=None`이면 첫 줄의 시각 칸이 숫자가 아닐 때만 머리줄로 본다."""
    require_window(start_ms, end_ms)
    refuse_reserved_archive(Path(path).name)
    with zipfile.ZipFile(path) as z:
        [name] = z.namelist()
        refuse_reserved_archive(name)
        with z.open(name) as raw:
            fh = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            skip = header
            if skip is None:
                head = fh.readline()
                cell = head.split(delimiter, ts_field + 1)[ts_field].strip() if head.strip() else ""
                lines: Iterable[str] = _data_lines(fh, False) if (not cell or not cell.isdigit()) and ts_kind == "ms" else _chain(head, fh)
            else:
                lines = _data_lines(fh, skip)
            yield from _bounded(lines, _ts_of_line(ts_field, ts_kind, delimiter), parse, start_ms=start_ms, end_ms=end_ms, dropped=dropped)


def _chain(head: str, fh: Iterable[str]) -> Iterator[str]:
    if head.strip():
        yield head
    yield from _data_lines(fh, False)


def bounded_records[T](records: Iterable[Mapping[str, Any] | Sequence[Any]], ts_key: str | int, parse: Callable[[Any], T], *,
                       start_ms: int, end_ms: int) -> Iterator[T]:
    """요청에서 이미 [start_ms, end_ms]로 묶은 API 응답의 행들 — 창 밖 행이 오면 **예외**(조용히 버리지 않는다)."""
    require_window(start_ms, end_ms)
    for r in records:
        t = r[ts_key]                                                         # type: ignore[index]
        t = int(t) if isinstance(t, str) and t.isdigit() else t
        if not isinstance(t, int) or isinstance(t, bool) or not (start_ms <= t <= end_ms):
            raise ReserveError(f"요청 범위 밖 행이 응답에 있다: {t!r}")
        yield parse(r)


def write_result(path: Path, obj: Any) -> str:
    """결과 JSON을 한 번만 쓴다(있으면 거부 — 재실행은 새 id) · 반환 = 파일 내용의 문자열(해시는 호출자가 원장에 적는다)."""
    p = Path(path)
    if p.exists():
        raise FileExistsError(f"{p} 가 이미 있다 — 스크린 결과는 덮어쓰지 않는다")
    s = json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")
    return s
