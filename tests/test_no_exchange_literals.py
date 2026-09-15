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


def _violations(py: Path, root: Path = ROOT) -> list[str]:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float) and node.value not in (0.0, 1.0):
            out.append(f"{py.relative_to(root).as_posix()}:{node.lineno} float 리터럴 {node.value!r}")
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Decimal" and node.args
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str | int | float)):
            out.append(f"{py.relative_to(root).as_posix()}:{node.lineno} Decimal 리터럴 {node.args[0].value!r}")
    return out


def test_guarded_packages_have_no_exchange_value_literals():
    v = []
    for d in GUARDED:
        for py in sorted((ROOT / d).rglob("*.py")):
            v += _violations(py)
    #  거래소 규칙이 아닌 값만 **파일·값 단위로** 명시 허용한다(목록이 자라면 경계를 여는 것이다):
    #  - HTTP timeout 기본값(운영 파라미터)
    #  - 사이징 정책 기본값 — 사용자 확정 레지스트리 #2(pos_pct_max 40% · pos_pct_min 10% · loss_tolerance 0)
    allowed = {("exchange/client.py", "float 리터럴 10.0"),
               ("sizing/config.py", "Decimal 리터럴 '0.40'"),
               ("sizing/config.py", "Decimal 리터럴 '0.10'"),
               ("sizing/config.py", "Decimal 리터럴 '0'"),
               #  - SL·청산 게이트 — 사용자 사전확약 레지스트리 #5(b_rel 1.5 · 절대 간격 10bp)
               ("sizing/config.py", "Decimal 리터럴 '1.5'"),
               ("sizing/config.py", "Decimal 리터럴 '0.0010'"),
               #  - 페이퍼 체결 슬리피지 — 실측값(스킬 exchange-rules §6 · 0.016 bps 2026-08 레짐 꼬리표)
               ("paper/config.py", "Decimal 리터럴 '0.0000016'")}
    v = [x for x in v if not any(x.startswith(f + ":") and x.endswith(val) for f, val in allowed)]
    assert v == [], "\n".join(v)


def test_the_guard_actually_detects_literals(tmp_path):
    p = tmp_path / "bad.py"
    p.write_text("from decimal import Decimal\nMIN_NOTIONAL = Decimal('50')\nFEE = 0.0005\n", encoding="utf-8")
    assert len(_violations(p, tmp_path)) == 2
