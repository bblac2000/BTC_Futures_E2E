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


def test_reserve_payloads_are_never_parsed():
    """실제 읽기 경로: 오염된 입력(7월 행 포함)에서 `parse`는 창 안의 행에만 불린다."""
    rows = [f"{ms(2026, 6, 30, 23, 58)},1.0", f"{ms(2026, 6, 30, 23, 59)},2.0", f"{ms(2026, 7, 1)},SECRET", f"{ms(2026, 9, 20)},SECRET"]
    parsed: list[str] = []

    def parse(raw: str) -> float:
        parsed.append(raw)
        return float(raw.split(",")[1])

    dropped = [0]
    out = list(W.bounded(rows, lambda r: int(r.split(",", 1)[0]), parse, dropped=dropped))
    assert out == [1.0, 2.0] and dropped == [2] and all("SECRET" not in r for r in parsed)


def test_bounded_is_lazy_and_rejects_malformed_timestamps():
    def gen():
        yield f"{ms(2025, 1, 1)},1"
        raise AssertionError("게으르지 않다")

    it = W.bounded(gen(), lambda r: int(r.split(",")[0]), lambda r: r)
    assert next(it).endswith(",1")
    with pytest.raises(W.ReserveError):
        list(W.bounded(["x"], lambda r: -1, lambda r: r))
    with pytest.raises(W.ReserveError):
        list(W.bounded(["x"], lambda r: ms(2025, 1, 1), lambda r: r, end_ms=ms(2026, 7, 2)))


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


def _calls(tree: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            out.add(f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else "")
    return out


def test_alpha_screens_read_data_only_through_their_loader_and_never_import_p0():
    """p1·p2: 파일 읽기는 `loader.py`에서만(그 모듈은 `window`를 import) · p0(예약 구간 예외)를 import하지 않는다."""
    readers = {"open", "read_text", "read_bytes", "read_csv", "read_parquet", "ZipFile", "urlopen"}
    for fam in ("p1", "p2"):
        for p in sorted((SCREENS / fam).rglob("*.py")) if (SCREENS / fam).exists() else []:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
            mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {
                n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            assert not any(m.startswith("research.screens.p0") for m in mods), p
            assert not any(m.startswith(("backtest", "strategies", "paper", "exchange")) for m in mods), p
            if p.name == "loader.py":
                assert "research.screens.window" in mods or "research.screens" in mods, p
            else:
                assert not (_calls(tree) & readers), (p, _calls(tree) & readers)


def test_no_order_path_in_screens():
    for p in SCREENS.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert "create_order" not in src and "/fapi/v1/order" not in src and "new_order" not in src, p
