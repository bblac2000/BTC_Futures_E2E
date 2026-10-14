"""스크린 자료 창과 예약 구간 가드(docs/screen_protocol.md §4 · 사용자 결정 D4).

스크린은 [2021-01-01, 2026-06-30] UTC만 읽는다. 2026-07-01부터는 예약 구간이고 **우회 인자가 없다** — 정식 트라이얼이
이 구간을 읽게 하려면 코드 변경과 레지스트리 행이 필요하다.

스크린 로더가 쓸 수 있는 읽기 경로는 이 모듈의 셋뿐이다(시험이 강제):
- `bounded_csv_file` · `bounded_zip_csv`: 파일을 **이 모듈이** 열고, 줄마다 시각 칸만 잘라 읽은 뒤 창 안의 줄만 `parse`에 넘긴다.
  호출자가 주는 것은 경로와 `parse`뿐이라, 호출자 코드가 예약 구간 줄의 값을 해석할 기회가 없다.
- `fetch_json_rows`: 공개 GET을 **이 모듈이** 부르고 응답 행의 시각을 먼저 검사한다 — 창 밖 행이 하나라도 오면 아무 행도 넘기지 않고 **예외**다.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping
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
    yield from _filtered(raw_items, ts_of, parse, start_ms, end_ms, dropped)


def _filtered[R, T](raw_items: Iterable[R], ts_of: Callable[[R], int], parse: Callable[[R], T], start_ms: int, end_ms: int,
                    dropped: list[int] | None) -> Iterator[T]:
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


def bounded_zip_csv[T](path: Path, parse: Callable[[str], T], *, header: bool, ts_field: int = 0, ts_kind: str = "ms",
                       delimiter: str = ",", start_ms: int = SCREEN_START_MS, end_ms: int = SCREEN_END_MS,
                       dropped: list[int] | None = None) -> Iterator[T]:
    """binance.vision 식 zip(안에 CSV 하나)을 열어 창 안의 줄만 `parse`한다. 머리줄 유무는 호출자가 **명시**한다(자동 판별 없음 —
    머리줄이 아닌 첫 줄의 시각이 잘못됐으면 예외다)."""
    require_window(start_ms, end_ms)
    refuse_reserved_archive(Path(path).name)
    with zipfile.ZipFile(path) as z:
        [name] = z.namelist()
        refuse_reserved_archive(name)
        with z.open(name) as raw:
            fh = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            yield from _bounded(_data_lines(fh, header), _ts_of_line(ts_field, ts_kind, delimiter), parse, start_ms=start_ms,
                                end_ms=end_ms, dropped=dropped)


#: 벤치마크 예외(사용자 #108): 이 이름의 **벤치마크 파일만** 창 시작 10일 전부터 읽을 수 있다(진입 시점의 마지막 관측용).
#: 시장 · 펀딩 · 프리미엄 · 전략 자료의 읽기(`bounded_csv_file` · `bounded_zip_csv` · `fetch_json_rows`)는 그대로 2021-01-01부터다.
BENCHMARK_FILE = re.compile(r"^DTB3_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}\.csv$")
BENCHMARK_LOOKBACK_MS = 10 * 86_400_000


def bounded_benchmark_csv[T](path: Path, parse: Callable[[str], T], *, ts_kind: str = "iso") -> Iterator[T]:
    """벤치마크 CSV(첫 칸 = 날짜 · 머리줄 있음)를 [창 시작 − 10일, 창 끝]으로 읽는다. 이름이 `BENCHMARK_FILE`이 아니면 열기 전에 거부."""
    name = Path(path).name
    if not BENCHMARK_FILE.match(name):
        raise ReserveError(f"벤치마크 예외는 벤치마크 파일에만: {name}")
    refuse_reserved_archive(name)
    with Path(path).open(encoding="utf-8", newline="") as fh:
        yield from _filtered(_data_lines(fh, True), _ts_of_line(0, ts_kind, ","), parse, SCREEN_START_MS - BENCHMARK_LOOKBACK_MS,
                             SCREEN_END_MS, None)


def zip_has_header(path: Path, *, ts_field: int = 0, delimiter: str = ",", names: frozenset[str] | None = None) -> bool:
    """첫 줄의 **시각 칸만** 보고 머리줄인지 답한다(숫자가 아니면 머리줄) — 값 칸은 읽지 않는다. 결과는 로더가 `header=`로 명시해 넘긴다.
    `names`를 주면 더 엄격하다: 숫자가 아닌 첫 칸은 그 이름 가운데 하나여야 하고, 아니면(예 `NaN` · `NULL`) 예외다(S-xs-carry-1 코드 검토)."""
    refuse_reserved_archive(Path(path).name)
    with zipfile.ZipFile(path) as z:
        [name] = z.namelist()
        refuse_reserved_archive(name)
        with z.open(name) as raw:
            head = io.TextIOWrapper(raw, encoding="utf-8", newline="").readline()
    cell = head.split(delimiter, ts_field + 1)[ts_field].strip()
    if cell.isdigit():
        return False
    if not re.fullmatch(r"[A-Za-z_]+", cell):                                  # 머리줄의 칸 이름 꼴이 아니면 잘못된 자료다
        raise ReserveError(f"첫 줄의 시각 칸이 숫자도 칸 이름도 아니다: {cell!r}")
    if names is not None and cell not in names:
        raise ReserveError(f"첫 줄의 시각 칸이 알려진 머리줄 이름이 아니다: {cell!r}")
    return True


def fetch_json_rows[T](url: str, params: Mapping[str, str | int], ts_key: str | int, parse: Callable[[Any], T], *,
                       timeout_s: float = 30.0) -> list[T]:
    """공개 GET 하나를 **이 모듈이** 부르고(요청의 startTime·endTime이 창 안이어야 한다) 응답 행의 시각을 먼저 검사한 뒤 `parse`한다.
    창 밖 행이 하나라도 있으면 어떤 행도 `parse`하지 않고 예외 — 호출자 코드는 응답을 직접 만지지 못한다."""
    start_ms, end_ms = int(params["startTime"]), int(params["endTime"])
    require_window(start_ms, end_ms)
    q = urllib.parse.urlencode(dict(params))
    with urllib.request.urlopen(f"{url}?{q}", timeout=timeout_s) as resp:        # 호출자가 전송을 갈아 끼울 수 없다
        rows = json.loads(resp.read())
    if not isinstance(rows, list):
        raise ReserveError(f"행 목록이 아닌 응답: {type(rows).__name__}")
    for r in rows:
        v = r[ts_key]
        v = int(v) if isinstance(v, str) and v.isdigit() else v
        if not isinstance(v, int) or isinstance(v, bool) or not (start_ms <= v <= end_ms):
            raise ReserveError(f"요청 범위 밖 행이 응답에 있다: {v!r}")
    return [parse(r) for r in rows]


def write_result(path: Path, obj: Any) -> str:
    """결과 JSON을 한 번만 쓴다(있으면 거부 — 재실행은 새 id) · 반환 = 파일 내용의 문자열(해시는 호출자가 원장에 적는다)."""
    p = Path(path)
    s = json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as fh:                                 # 배타 생성 — 이미 있으면 FileExistsError
        fh.write(s)
    return s


#: 스크린 모듈이 이 모듈에서 가져다 쓸 수 있는 이름(시험이 강제 — `window.io` 같은 우회 금지)
PUBLIC = ("SCREEN_START_MS", "SCREEN_END_MS", "ReserveError", "require_window", "refuse_reserved_archive", "assert_within",
          "bounded_csv_file", "bounded_zip_csv", "zip_has_header", "fetch_json_rows", "write_result", "bounded_benchmark_csv")

#: loader.py가 아닌 스크린 모듈이 쓸 수 있는 이름(읽기 함수 제외)
PUBLIC_NON_LOADER = ("SCREEN_START_MS", "SCREEN_END_MS", "ReserveError", "assert_within", "write_result")
