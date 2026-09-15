"""헌법 §0 "하드코딩 금지는 값에 대한 것이다" — `exchange/`·`sizing/`·`paper/`에 거래소 값 리터럴이 없어야 한다.

AST로 **실행되는 코드의 상수**만 본다(주석·문서 문자열 제외). 잡는 것:
- float 리터럴 전부(가격·비율은 Decimal로 런타임 값에서 온다)
- 숫자처럼 보이는 문자열을 Decimal로 만드는 `Decimal("0.001")` 형태
허용: 정수 0/1(비교·증감), 에러코드(음수 정수), HTTP 상태 등 **이름 붙은 모듈 상수**는 목록으로 명시.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARDED = ("exchange", "sizing", "paper")


def _violations(py: Path) -> list[str]:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float) and node.value not in (0.0, 1.0):
            out.append(f"{py.name}:{node.lineno} float 리터럴 {node.value!r}")
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Decimal" and node.args
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str | int | float)):
            out.append(f"{py.name}:{node.lineno} Decimal 리터럴 {node.args[0].value!r}")
    return out


def test_guarded_packages_have_no_exchange_value_literals():
    v = []
    for d in GUARDED:
        for py in sorted((ROOT / d).rglob("*.py")):
            v += _violations(py)
    #  HTTP timeout 기본값은 거래소 규칙이 아니라 운영 파라미터다 — 파일·값 단위로 명시 허용
    allowed = ("client.py:", "float 리터럴 10.0")
    v = [x for x in v if not (x.startswith(allowed[0]) and x.endswith(allowed[1]))]
    assert v == [], "\n".join(v)


def test_the_guard_actually_detects_literals(tmp_path):
    p = tmp_path / "bad.py"
    p.write_text("from decimal import Decimal\nMIN_NOTIONAL = Decimal('50')\nFEE = 0.0005\n", encoding="utf-8")
    assert len(_violations(p)) == 2
