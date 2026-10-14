"""스크린 예약 구간 가드(docs/screen_protocol.md §4 · D4) — 2026-07-01 이후 자료는 읽히지 않는다."""
from __future__ import annotations

import ast
import datetime as dt
import inspect
from pathlib import Path

import pytest

from research.screens import window as W

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ROOT / "research" / "screens"


def ms(*a: int) -> int:
    return int(dt.datetime(*a, tzinfo=dt.UTC).timestamp() * 1000)


def test_window_constants_are_utc_millisecond_boundaries():
    assert W.SCREEN_START_MS == ms(2021, 1, 1) and W.SCREEN_END_MS == ms(2026, 7, 1) - 1


def test_request_reaching_into_the_reserve_is_refused():
    with pytest.raises(W.ReserveError):
        W.require_window(ms(2026, 6, 1), ms(2026, 7, 1))
    with pytest.raises(W.ReserveError):
        W.require_window(ms(2020, 12, 31), ms(2021, 6, 1))
    with pytest.raises(W.ReserveError):
        W.require_window(ms(2026, 9, 17), ms(2026, 10, 11))
    W.require_window(ms(2021, 1, 1), ms(2026, 7, 1) - 1)


def test_guard_has_no_bypass_parameter():
    assert list(inspect.signature(W.require_window).parameters) == ["start_ms", "end_ms"]
    assert "token" not in inspect.getsource(W)


def _spy():
    seen: list[str] = []

    def parse(line: str) -> float:
        seen.append(line)
        return float(line.split(",")[1])

    return seen, parse


ROWS = [f"{ms(2026, 6, 30, 23, 58)},1.0", f"{ms(2026, 6, 30, 23, 59)},2.0", f"{ms(2026, 7, 1)},SECRET", f"{ms(2026, 9, 20)},SECRET"]


def test_csv_file_path_never_parses_reserve_payloads(tmp_path):
    """실제 읽기 경로(파일 → 줄 → 시각 칸 → parse): 7월 줄의 값은 한 번도 해석되지 않는다."""
    f = tmp_path / "BTCUSDT-1m-2026-06.csv"
    f.write_text("open_time,close\n" + "\n".join(ROWS) + "\n", encoding="utf-8")
    seen, parse = _spy()
    dropped = [0]
    assert list(W.bounded_csv_file(f, parse, header=True, dropped=dropped)) == [1.0, 2.0]
    assert dropped == [2] and all("SECRET" not in s for s in seen)


def test_zip_path_never_parses_reserve_payloads_and_handles_microseconds_and_headers(tmp_path):
    import zipfile
    us = [f"{ms(2026, 6, 30, 23, 59) * 1000},2.0", f"{ms(2026, 7, 1) * 1000},SECRET"]
    for name, body in (("X-1m-2026-06.zip", "\n".join(ROWS)), ("Y-1m-2026-06.zip", "open_time,close\n" + "\n".join(us))):
        z = tmp_path / name
        with zipfile.ZipFile(z, "w") as zz:
            zz.writestr(name.replace(".zip", ".csv"), body + "\n")
        seen, parse = _spy()
        out = list(W.bounded_zip_csv(z, parse, header=W.zip_has_header(z)))
        assert out[-1] == 2.0 and all("SECRET" not in s for s in seen)


def test_reserved_file_is_refused_before_it_is_opened(tmp_path):
    f = tmp_path / "BTCUSDT-1m-2026-07.csv"                      # 존재하지 않는다 — 열려고 하면 FileNotFoundError가 났을 것
    with pytest.raises(W.ReserveError):
        list(W.bounded_csv_file(f, lambda s: s))
    with pytest.raises(W.ReserveError):
        list(W.bounded_zip_csv(tmp_path / "BTCFDUSD-1m-2026-08.zip", lambda s: s, header=False))
    with pytest.raises(W.ReserveError):
        W.zip_has_header(tmp_path / "BTCFDUSD-1m-2026-08.zip")
    import zipfile
    z = tmp_path / "Q-1m-2025-01.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("Q-1m-2025-01.csv", f"not-a-time,9.0\n{ms(2025, 1, 1)},1.0\n")
    with pytest.raises(W.ReserveError):                                        # 머리줄 꼴이 아닌 첫 줄은 건너뛰지 않는다
        W.zip_has_header(z)
    with pytest.raises(W.ReserveError):
        list(W.bounded_csv_file(tmp_path / "ok-2026-06.csv", lambda s: s, end_ms=ms(2026, 7, 2)))


def test_malformed_timestamp_is_an_error_not_a_skip(tmp_path):
    f = tmp_path / "a-2025-01.csv"
    f.write_text(f"{ms(2025, 1, 1)},1\nnot-a-time,2\n", encoding="utf-8")
    with pytest.raises(W.ReserveError):
        list(W.bounded_csv_file(f, lambda s: s))
    g = tmp_path / "b-2025-01.csv"
    g.write_text("2025-01-01 00:00:00,1\n2026-07-01 00:00:00,SECRET\n", encoding="utf-8")
    assert list(W.bounded_csv_file(g, lambda s: s.split(",")[1].strip(), ts_kind="iso")) == ["1"]


def test_zip_with_a_malformed_first_data_line_raises_instead_of_skipping_it(tmp_path):
    import zipfile
    z = tmp_path / "Z-1m-2025-01.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("Z-1m-2025-01.csv", f"not-a-time,9.0\n{ms(2025, 1, 1)},1.0\n")
    with pytest.raises(W.ReserveError):
        list(W.bounded_zip_csv(z, lambda s: s, header=False))


class _Resp:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_api_fetch_checks_every_timestamp_before_any_row_is_parsed(monkeypatch):
    import json
    rows = [{"fundingTime": ms(2026, 6, 30, 16), "fundingRate": "0.0001"}, {"fundingTime": ms(2026, 7, 1), "fundingRate": "SECRET"}]
    seen: list[object] = []
    urls: list[str] = []

    def opener(url, timeout):
        urls.append(url)
        return _Resp(json.dumps(rows if "bad" in url else rows[:1]).encode())

    monkeypatch.setattr(W.urllib.request, "urlopen", opener)
    assert "opener" not in inspect.signature(W.fetch_json_rows).parameters      # 호출자가 전송을 갈아 끼울 수 없다

    params = {"symbol": "BTCUSDT", "startTime": ms(2026, 6, 1), "endTime": W.SCREEN_END_MS}
    assert W.fetch_json_rows("https://x/ok", params, "fundingTime", lambda r: seen.append(r) or r["fundingRate"]) == ["0.0001"]
    seen.clear()
    with pytest.raises(W.ReserveError):
        W.fetch_json_rows("https://x/bad", params, "fundingTime", lambda r: seen.append(r))
    assert seen == []                                                          # 창 밖 행이 있으면 어떤 행도 해석하지 않는다
    with pytest.raises(W.ReserveError):                                        # 요청 자체가 예약 구간 → 네트워크 호출 전 거부
        W.fetch_json_rows("https://x/never", {**params, "endTime": ms(2026, 7, 1)}, "fundingTime", dict)
    assert not any("never" in u for u in urls)


def test_result_is_created_exclusively(tmp_path):
    W.write_result(tmp_path / "r.json", {"a": 1})
    with pytest.raises(FileExistsError):
        W.write_result(tmp_path / "r.json", {"a": 2})
    assert "open(\"x\"" in inspect.getsource(W.write_result)


def test_reserved_archives_are_refused_before_opening():
    for name in ("BTCUSDT-1m-2026-07.zip", "BTCFDUSD-1m-2026-10-11.zip", "FDUSDUSDT-1m-2027-01.zip"):
        with pytest.raises(W.ReserveError):
            W.refuse_reserved_archive(name)
    W.refuse_reserved_archive("BTCUSDT-1m-2026-06.zip")
    W.refuse_reserved_archive("BTCUSDT-1m-2021-01.zip")


def test_assert_within_checks_outcome_timestamps():
    W.assert_within([ms(2026, 6, 30)])
    with pytest.raises(W.ReserveError):
        W.assert_within([ms(2026, 6, 1), ms(2026, 7, 1)])


ALLOWED_IMPORTS = {"__future__", "math", "statistics", "datetime", "dataclasses", "collections", "typing", "itertools", "functools",
                   "decimal", "fractions", "bisect", "enum", "hashlib", "numpy", "research"}
BANNED_NAMES = {"open", "read", "readline", "readlines", "readinto", "read_text", "read_bytes", "read_csv", "read_json", "read_parquet",
                "read_table", "ZipFile", "FileIO", "urlopen", "loadtxt", "genfromtxt", "fromfile", "fromregex", "load", "memmap",
                "DataSource", "open_memmap", "tofile", "save", "savez", "savetxt", "__import__", "import_module", "exec", "eval",
                "compile", "getattr", "setattr", "globals", "vars", "locals", "__dict__", "__builtins__", "io", "json", "zipfile",
                "urllib", "os", "sys", "subprocess", "bounded_records", "_bounded", "__kwdefaults__", "__defaults__", "__globals__",
                "__closure__", "__code__", "__wrapped__", "__module__"}
BOUNDED = {"bounded_csv_file", "bounded_zip_csv", "fetch_json_rows", "bounded_benchmark_csv"}


def screen_violations(src: str, *, is_loader: bool, family: str = "p1") -> list[str]:
    """p1·p2 모듈 규칙(허용 목록 방식):
    - import는 허용 목록 + 같은 가족 패키지 + `research.screens.window`의 공개 이름만(`window.PUBLIC`). loader.py만 `pathlib.Path`를 더 쓸 수 있다.
    - 직접 읽기·동적 접근 이름(`open` · `read` · `load` · `getattr` · `io` …)은 이름으로도 속성으로도 쓸 수 없다.
    - loader.py는 `window`의 읽기 함수(bounded_* · fetch_json_rows)를 실제로 불러야 한다."""
    tree = ast.parse(src)
    bad: list[str] = []
    own = f"research.screens.{family}"
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS - {"research"} or (a.asname and (a.name, a.asname) != ("numpy", "np")):
                    bad.append(f"import {a.name} as {a.asname}")
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            names = {a.name for a in n.names}
            if names & BANNED_NAMES or any(a.asname for a in n.names):          # 금지 이름의 import · 별칭 import 금지
                bad.append(f"banned or aliased import {sorted(names)}")
            if n.level:                                                         # 상대 import: 같은 가족 안(`.` 하나)만
                if n.level != 1 or mod.split(".")[0] in ("p0", "window") or "p0" in names:
                    bad.append(f"relative import {'.' * n.level}{mod} {sorted(names)}")
            elif mod == "research.screens.window":
                allowed = set(W.PUBLIC if is_loader else W.PUBLIC_NON_LOADER)
                if names - allowed:
                    bad.append(f"window names {sorted(names - allowed)}")
            elif mod == own or mod.startswith(own + "."):
                pass
            elif mod == "pathlib" and is_loader and names == {"Path"}:
                pass
            elif mod.split(".")[0] in ALLOWED_IMPORTS - {"research"}:
                pass
            else:
                bad.append(f"from {mod} import {sorted(names)}")
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    if used & BANNED_NAMES:
        bad.append(f"banned name {sorted(used & BANNED_NAMES)}")
    if is_loader and not (used & BOUNDED):
        bad.append("loader does not call a window reader")
    return bad


@pytest.mark.parametrize("src,is_loader", [
    ("read_file = open\nx = read_file('a')", False),                                   # open 별칭
    ("import pandas\nd = pandas.read_json('a')", False),                               # 로더 밖 pandas
    ("from research.screens import window\nimport csv\nrows = list(csv.reader(open('a')))", True),   # window만 import하고 가드 미사용
    ("from .. import p0", False),                                                      # 상대 import로 p0
    ("from research.screens.p0 import loader", True),
    ("from pathlib import Path\nt = Path('a').read_text()", True),
    ("import importlib\nm = importlib.import_module('research.screens.p0')", False),
    ("from backtest import data", True),
    ("from research.screens.window import io\npayload = io.FileIO('reserve.csv').read()", False),          # Codex POST r2 (c)
    ("import research.screens.window as W\nx = W.io.FileIO('a')", False),
    ("import numpy as np\nx = np.fromregex('a', r'(\\d+)', [('n', int)])", False),                        # numpy 파일 읽기
    ("from research.screens.window import fetch_json_rows, _bounded", True),
    ("import pandas as pd", True),
    ("from research.screens.p2 import loader", False),                                                    # 다른 가족
    ("from numpy import fromregex as scan\nr = scan('a', r'v', [('v', int)])", False),                    # Codex POST r3 (c): 별칭
    ("from research.screens.window import fetch_json_rows\nx = fetch_json_rows.__kwdefaults__", True),    # Codex POST r3 (b)
    ("from research.screens.window import bounded_zip_csv\nrows = list(bounded_zip_csv('a', str, header=False))", False),  # 로더 밖 읽기
    ("from . import loader\nx = loader.bounded_records([], 't', dict)", False),                           # Codex POST r4
    ("import math as np", False),
    ("import numpy.linalg as np", False),
])
def test_static_rule_catches_known_bypasses(src, is_loader):
    assert screen_violations(src, is_loader=is_loader)


def test_static_rule_accepts_a_compliant_loader_and_a_pure_module():
    ok_loader = ("from pathlib import Path\nfrom research.screens.window import bounded_zip_csv, zip_has_header\n"
                 "def closes(p: Path):\n    return list(bounded_zip_csv(p, lambda s: float(s.split(',')[4]), header=zip_has_header(p)))\n")
    assert screen_violations(ok_loader, is_loader=True) == []
    assert screen_violations("import math\nimport numpy as np\nfrom . import loader\nx = math.sqrt(np.mean([1.0]))", is_loader=False) == []


def test_alpha_screen_modules_obey_the_static_rule():
    """p1·p2가 생기면 모든 모듈에 적용된다(없으면 검사할 것이 없다 — 가족 디렉터리가 생기는 커밋부터 실효)."""
    for fam in ("p1", "p2"):
        for p in sorted((SCREENS / fam).rglob("*.py")) if (SCREENS / fam).exists() else []:
            assert screen_violations(p.read_text(encoding="utf-8"), is_loader=p.name == "loader.py", family=fam) == [], p


def test_no_order_path_in_screens():
    for p in SCREENS.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert "create_order" not in src and "/fapi/v1/order" not in src and "new_order" not in src, p


# ---------- 벤치마크 예외(사용자 #108) ----------
def test_market_and_funding_reads_at_2020_12_31_are_still_refused(tmp_path):
    """실패하도록 설계: 벤치마크 예외가 생긴 뒤에도 시장 · 펀딩 읽기는 2021-01-01 전을 거부한다."""
    p = tmp_path / "BTCUSDT-fundingRate-2020-12.csv"
    p.write_text(f"{ms(2020, 12, 31)},0.0001\n", encoding="utf-8")
    with pytest.raises(W.ReserveError):
        list(W.bounded_csv_file(p, str, start_ms=ms(2020, 12, 31)))
    with pytest.raises(W.ReserveError):
        W.require_window(ms(2020, 12, 31), ms(2021, 1, 2))
    q = tmp_path / "BTCUSDT-1m-2021-01.csv"
    q.write_text(f"{ms(2020, 12, 31)},1.0\n{ms(2021, 1, 1)},2.0\n", encoding="utf-8")
    assert list(W.bounded_csv_file(q, lambda s: s.split(",")[1].strip())) == ["2.0"]          # 12-31 줄은 버린다


def test_benchmark_exception_is_keyed_to_the_benchmark_file_and_ten_days(tmp_path):
    rows = "observation_date,DTB3\n2020-12-21,BAD\n2020-12-22,0.09\n2020-12-31,0.09\n2021-01-04,0.09\n2026-06-30,4.0\n2026-07-01,BAD\n"
    good = tmp_path / "DTB3_2020-12-01_2026-06-30.csv"
    good.write_text(rows, encoding="utf-8")
    got = list(W.bounded_benchmark_csv(good, lambda s: s.split(",")[0]))
    assert got == ["2020-12-22", "2020-12-31", "2021-01-04", "2026-06-30"]                   # 10일 전부터 · 예약 구간 없음
    for name in ("BTCUSDT-fundingRate-2020-12.csv", "premiumIndex_2020-12-01_2026-06-30.csv", "DTB3.csv"):
        bad = tmp_path / name
        bad.write_text(rows, encoding="utf-8")
        with pytest.raises(W.ReserveError):
            list(W.bounded_benchmark_csv(bad, str))
    assert list(inspect.signature(W.bounded_benchmark_csv).parameters) == ["path", "parse", "ts_kind"]   # 창을 넓히는 인자 없음
