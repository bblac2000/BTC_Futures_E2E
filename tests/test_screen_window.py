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
        out = list(W.bounded_zip_csv(z, parse))
        assert out[-1] == 2.0 and all("SECRET" not in s for s in seen)


def test_reserved_file_is_refused_before_it_is_opened(tmp_path):
    f = tmp_path / "BTCUSDT-1m-2026-07.csv"                      # 존재하지 않는다 — 열려고 하면 FileNotFoundError가 났을 것
    with pytest.raises(W.ReserveError):
        list(W.bounded_csv_file(f, lambda s: s))
    with pytest.raises(W.ReserveError):
        list(W.bounded_zip_csv(tmp_path / "BTCFDUSD-1m-2026-08.zip", lambda s: s))
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


def test_api_records_outside_the_requested_window_raise():
    ok = [{"fundingTime": ms(2026, 6, 30, 16), "fundingRate": "0.0001"}]
    assert len(list(W.bounded_records(ok, "fundingTime", dict, start_ms=ms(2026, 6, 1), end_ms=W.SCREEN_END_MS))) == 1
    with pytest.raises(W.ReserveError):
        list(W.bounded_records(ok + [{"fundingTime": ms(2026, 7, 1), "fundingRate": "9"}], "fundingTime", dict,
                               start_ms=ms(2026, 6, 1), end_ms=W.SCREEN_END_MS))
    with pytest.raises(W.ReserveError):
        list(W.bounded_records(ok, "fundingTime", dict, start_ms=ms(2026, 6, 1), end_ms=ms(2026, 7, 1)))


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


IO_MODULES = {"csv", "zipfile", "io", "pathlib", "os", "urllib", "requests", "pandas", "gzip", "json", "pyarrow", "glob", "shutil",
              "subprocess", "sqlite3", "pickle", "httpx", "aiohttp", "ccxt", "polars", "tarfile", "lzma", "bz2", "tempfile", "builtins"}
READ_NAMES = {"open", "read_text", "read_bytes", "read_csv", "read_json", "read_parquet", "read_table", "ZipFile", "urlopen",
              "loadtxt", "genfromtxt", "fromfile", "load", "__import__", "import_module", "exec", "eval"}
BOUNDED = {"bounded_csv_file", "bounded_zip_csv", "bounded_records"}
FORBIDDEN_PREFIX = ("backtest", "strategies", "paper", "exchange", "data", "ops", "db")


def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            base = ("." * n.level) + (n.module or "")
            out.add(base)
            out |= {f"{base}.{a.name}" if base and not base.endswith(".") else f"{base}{a.name}" for a in n.names}
    return out


def _names(tree: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}


def screen_violations(src: str, *, is_loader: bool) -> list[str]:
    """p1·p2 모듈 규칙: p0 import 금지 · 기존 계층 import 금지 · 파일/네트워크 읽기는 `window`의 bounded_* 뿐.
    loader.py 밖은 I/O 모듈 자체를 import할 수 없고, loader.py도 직접 읽기 이름을 쓸 수 없으며 bounded_* 를 불러야 한다."""
    tree = ast.parse(src)
    mods, names, bad = _imports(tree), _names(tree), []
    if any(m.split(".")[-1] == "p0" or ".p0." in m or m.endswith(".p0") or "screens.p0" in m for m in mods):
        bad.append("imports p0")
    if any(m.lstrip(".").split(".")[0] in FORBIDDEN_PREFIX for m in mods if not m.startswith(".")):
        bad.append("imports a legacy layer")
    if names & READ_NAMES:
        bad.append(f"direct read name {sorted(names & READ_NAMES)}")
    io_used = {m.lstrip(".").split(".")[0] for m in mods if not m.startswith(".")} & IO_MODULES
    if is_loader:
        if io_used - {"pathlib"}:
            bad.append(f"loader imports I/O module {sorted(io_used - {'pathlib'})}")
        if not (names & BOUNDED):
            bad.append("loader does not call a bounded_* reader")
    elif io_used:
        bad.append(f"non-loader imports I/O module {sorted(io_used)}")
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
])
def test_static_rule_catches_known_bypasses(src, is_loader):
    assert screen_violations(src, is_loader=is_loader)


def test_static_rule_accepts_a_compliant_loader_and_a_pure_module():
    ok_loader = ("from pathlib import Path\nfrom research.screens.window import bounded_zip_csv\n"
                 "def closes(p: Path):\n    return list(bounded_zip_csv(p, lambda s: float(s.split(',')[4])))\n")
    assert screen_violations(ok_loader, is_loader=True) == []
    assert screen_violations("import math\nimport numpy as np\nfrom . import loader\nx = math.sqrt(np.mean([1.0]))", is_loader=False) == []


def test_alpha_screen_modules_obey_the_static_rule():
    """p1·p2가 생기면 모든 모듈에 적용된다(없으면 검사할 것이 없다 — 가족 디렉터리가 생기는 커밋부터 실효)."""
    for fam in ("p1", "p2"):
        for p in sorted((SCREENS / fam).rglob("*.py")) if (SCREENS / fam).exists() else []:
            assert screen_violations(p.read_text(encoding="utf-8"), is_loader=p.name == "loader.py") == [], p


def test_no_order_path_in_screens():
    for p in SCREENS.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert "create_order" not in src and "/fapi/v1/order" not in src and "new_order" not in src, p
