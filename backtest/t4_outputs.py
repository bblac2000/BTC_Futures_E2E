"""트라이얼 #4 실행 산출물 계약((f) · 규약 E61) — (g) 단계 실행기가 **이 모듈로 쓰고**, 판정기가 **이 모듈로 읽는다**.

**복사**: `backtest/t3_outputs.py` @ 75c3b6a에서 — 바꾼 것: 암 순서 S · L · 변형 이름(P2_print1 · P2_print3) · 트레이드 파일 `trades_t4.jsonl` ·
요약 키(window_prints · dist_defined · tc_v3_sha256) · P1 조각·병합에 보고 전용 timing과 적격 분 개수(조각 간 일치 검사) · 실패 보존은 Trial04 필드와 P1의 게이트·timing 넷(F77).

배치(`base` = 트라이얼 #4 IS 디렉터리):
- `runs/<arm>_<variant>/` (arm ∈ S·L · variant ∈ base·P2_print1·P2_print3·P3_invert) = `trades_t4.jsonl` · `events.jsonl` · `summary.json`
- `runs/<arm>_P1/part_<lo>_<hi>/p1_part.json` · `runs/<arm>_P1_merged/` = `p1_draws.json` · `p1_null.jsonl` · `p1_timing_draws.json` ·
  `p1_timing_null.jsonl` · `p1_summary.json`
파일 집합·요약 키는 고정이다 — 빠짐·남음·스키마 불일치는 판정 **거부**(판정 없음 · §7 IS(0) 폐기와 다르다).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from backtest import p1_t4 as P1
from backtest.replay import read_jsonl, write_jsonl
from strategies.trial04.harness import T4Run

ARMS = ("S", "L")
VARIANTS = ("base", "P2_print1", "P2_print3", "P3_invert")
RUN_FILES = ("events.jsonl", "summary.json", "trades_t4.jsonl")
SUMMARY_KEYS = frozenset({"arm", "variant", "funnel", "sub", "entry", "window_prints", "dist_defined", "v_days", "n_trades",
                          "tc_v3_sha256", "rules_sha256"})
P1_PART_FILE = "p1_part.json"
P1_PART_KEYS = frozenset({"arm", "lo", "hi", "n_source", "computable", "draws_json", "null", "timing_draws_json", "timing_null",
                          "n_eligible", "n_eligible_atr_prev_close_ok"})
P1_MERGED_FILES = ("p1_draws.json", "p1_null.jsonl", "p1_summary.json", "p1_timing_draws.json", "p1_timing_null.jsonl")
P1_SUMMARY_KEYS = frozenset({"arm", "n_source", "computable", "failed", "evaluable", "parts", "timing_failed", "n_eligible",
                             "n_eligible_atr_prev_close_ok"})


class ContractError(RuntimeError):
    """산출물이 계약과 다르다 → 판정 거부."""


def run_dir(base: Path, arm: str, variant: str) -> Path:
    return base / "runs" / f"{arm}_{variant}"


def p1_parts_dir(base: Path, arm: str) -> Path:
    return base / "runs" / f"{arm}_P1"


def p1_merged_dir(base: Path, arm: str) -> Path:
    return base / "runs" / f"{arm}_P1_merged"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_run(d: Path, run: T4Run, v_days: Sequence[int], *, tc_v3_sha256: str, rules_sha256: dict[str, str]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    s = run.strategy
    write_jsonl(d / "trades_t4.jsonl", run.trades)
    write_jsonl(d / "events.jsonl", s.events)
    summary = {"arm": run.arm, "variant": run.variant.name, "funnel": dict(sorted(s.funnel.items())), "sub": dict(sorted(s.sub.items())),
               "entry": dict(sorted(s.entry.items())), "window_prints": s.window_prints,
               "dist_defined": {str(k): v for k, v in sorted(s.dist_defined.items())}, "v_days": sorted(v_days),
               "n_trades": len(run.trades), "tc_v3_sha256": tc_v3_sha256, "rules_sha256": dict(sorted(rules_sha256.items()))}
    (d / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=1) + "\n")


def read_run(d: Path, arm: str, variant: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    files = sorted(p.name for p in d.iterdir()) if d.exists() else []
    if tuple(files) != RUN_FILES:
        raise ContractError(f"{d}: 파일 {files} ≠ {list(RUN_FILES)}")
    summary = json.loads((d / "summary.json").read_text())
    if set(summary) != SUMMARY_KEYS or summary["arm"] != arm or summary["variant"] != variant:
        raise ContractError(f"{d}: summary 스키마·arm·variant 불일치")
    _check_summary_types(d, summary)
    trades = read_jsonl(d / "trades_t4.jsonl")
    if len(trades) != summary["n_trades"]:
        raise ContractError(f"{d}: 트레이드 {len(trades)} ≠ summary {summary['n_trades']}")
    return trades, read_jsonl(d / "events.jsonl"), summary


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _check_summary_types(d: Path, s: dict[str, Any]) -> None:
    """중첩 스키마: 깔때기·부사유·진입 = {str: int ≥ 0} · dist_defined = {정수 문자열: bool} · v_days = 오름차순 정수 ·
    window_prints·n_trades = 정수 ≥ 0 · 해시 = 64자리 소문자 16진."""
    def counts(x: Any) -> bool:
        return isinstance(x, dict) and all(isinstance(k, str) and _is_int(v) and v >= 0 for k, v in x.items())

    def hexsha(x: Any) -> bool:
        return isinstance(x, str) and len(x) == 64 and all(c in "0123456789abcdef" for c in x)

    ok = (counts(s["funnel"]) and counts(s["sub"]) and counts(s["entry"]) and _is_int(s["window_prints"]) and s["window_prints"] >= 0
          and _is_int(s["n_trades"]) and s["n_trades"] >= 0
          and isinstance(s["dist_defined"], dict)
          and all(k.lstrip("-").isdigit() and isinstance(v, bool) for k, v in s["dist_defined"].items())
          and isinstance(s["v_days"], list) and all(_is_int(x) for x in s["v_days"]) and s["v_days"] == sorted(set(s["v_days"]))
          and hexsha(s["tc_v3_sha256"]) and isinstance(s["rules_sha256"], dict) and all(hexsha(v) for v in s["rules_sha256"].values()))
    if not ok:
        raise ContractError(f"{d}: summary 중첩 스키마 불일치")


def _part_dict(p: P1.P1Part) -> dict[str, Any]:
    return {"arm": p.arm, "lo": p.lo, "hi": p.hi, "n_source": p.n_source, "computable": p.computable,
            "draws_json": p.draws_json, "null": p.null, "timing_draws_json": p.timing_draws_json, "timing_null": p.timing_null,
            "n_eligible": p.n_eligible, "n_eligible_atr_prev_close_ok": p.n_eligible_atr_prev_close_ok}


def write_p1_part(base: Path, part: P1.P1Part) -> Path:
    return write_p1_part_to(p1_parts_dir(base, part.arm) / f"part_{part.lo:03d}_{part.hi:03d}", part)


def write_p1_part_to(d: Path, part: P1.P1Part) -> Path:
    if d.name != f"part_{part.lo:03d}_{part.hi:03d}" or d.parent.name != f"{part.arm}_P1":
        raise ContractError(f"{d}: 조각 경로가 arm·범위와 다르다")
    d.mkdir(parents=True, exist_ok=True)
    (d / P1_PART_FILE).write_text(json.dumps(_part_dict(part), sort_keys=True) + "\n")
    return d / P1_PART_FILE


def read_p1_parts(base: Path, arm: str) -> list[P1.P1Part]:
    root = p1_parts_dir(base, arm)
    if not root.exists():
        raise ContractError(f"{root} 없음")
    out = []
    for d in sorted(root.iterdir()):
        if [p.name for p in d.iterdir()] != [P1_PART_FILE]:
            raise ContractError(f"{d}: 조각 파일 집합 불일치")
        x = json.loads((d / P1_PART_FILE).read_text())
        if set(x) != P1_PART_KEYS or x["arm"] != arm \
                or not (_is_int(x["lo"]) and _is_int(x["hi"]) and 0 <= x["lo"] <= x["hi"] and _is_int(x["n_source"])
                        and x["n_source"] >= 0 and isinstance(x["computable"], bool) and isinstance(x["draws_json"], str)
                        and isinstance(x["null"], list) and isinstance(x["timing_draws_json"], str)
                        and isinstance(x["timing_null"], list) and _is_int(x["n_eligible"]) and x["n_eligible"] >= 0
                        and _is_int(x["n_eligible_atr_prev_close_ok"]) and 0 <= x["n_eligible_atr_prev_close_ok"] <= x["n_eligible"]) \
                or d.name != f"part_{x['lo']:03d}_{x['hi']:03d}":
            raise ContractError(f"{d}: 조각 스키마 불일치")
        out.append(P1.P1Part(x["arm"], x["lo"], x["hi"], x["n_source"], x["computable"], x["draws_json"], x["null"],
                             x["timing_draws_json"], x["timing_null"], x["n_eligible"], x["n_eligible_atr_prev_close_ok"]))
    return out


def eligible_counts(parts: Sequence[P1.P1Part]) -> tuple[int, int]:
    """모든 조각이 같은 입력으로 돌았다면 적격 분 개수가 같다 — 다르면 거부(E61)."""
    got = {(p.n_eligible, p.n_eligible_atr_prev_close_ok) for p in parts}
    if len(got) != 1:
        raise ContractError(f"조각 간 적격 분 개수 불일치: {sorted(got)}")
    return got.pop()


def write_p1_merged(base: Path, arm: str, parts: Sequence[P1.P1Part], draws_total: int = P1.A.P1_DRAWS) -> dict[str, Any]:
    m = P1.merge(parts, draws_total)                 # 위치 인자 — 추출 수 덮어쓰기는 이 계약 모듈과 판정기 계산 경로에서만(정적 시험)
    n_el, n_ok = eligible_counts(parts)
    d = p1_merged_dir(base, arm)
    d.mkdir(parents=True, exist_ok=True)
    (d / "p1_draws.json").write_text(json.dumps(m["draws"], sort_keys=True, separators=(",", ":")))
    write_jsonl(d / "p1_null.jsonl", m["null"])
    (d / "p1_timing_draws.json").write_text(json.dumps(m["timing"]["draws"], sort_keys=True, separators=(",", ":")))
    write_jsonl(d / "p1_timing_null.jsonl", m["timing"]["null"])
    part_shas = [{"lo": p.lo, "hi": p.hi, "sha256": sha(p1_parts_dir(base, arm) / f"part_{p.lo:03d}_{p.hi:03d}" / P1_PART_FILE)}
                 for p in sorted(parts, key=lambda p: p.lo)]
    summ = {"arm": arm, "n_source": m["n_source"], "computable": m["computable"], "failed": m["failed"], "evaluable": m["evaluable"],
            "parts": part_shas, "timing_failed": m["timing"]["failed"], "n_eligible": n_el, "n_eligible_atr_prev_close_ok": n_ok}
    (d / "p1_summary.json").write_text(json.dumps(summ, sort_keys=True, indent=1) + "\n")
    return m


def read_p1_merged(base: Path, arm: str) -> dict[str, Any]:
    """반환: draws · null · timing_draws · timing_null · summary."""
    d = p1_merged_dir(base, arm)
    files = sorted(p.name for p in d.iterdir()) if d.exists() else []
    if tuple(files) != P1_MERGED_FILES:
        raise ContractError(f"{d}: 파일 {files} ≠ {list(P1_MERGED_FILES)}")
    summ = json.loads((d / "p1_summary.json").read_text())
    if set(summ) != P1_SUMMARY_KEYS or summ["arm"] != arm:
        raise ContractError(f"{d}: p1_summary 스키마 불일치")
    ok = (_is_int(summ["n_source"]) and summ["n_source"] >= 0 and isinstance(summ["computable"], bool)
          and _is_int(summ["failed"]) and summ["failed"] >= 0 and isinstance(summ["evaluable"], bool)
          and _is_int(summ["timing_failed"]) and summ["timing_failed"] >= 0 and _is_int(summ["n_eligible"]) and summ["n_eligible"] >= 0
          and _is_int(summ["n_eligible_atr_prev_close_ok"]) and 0 <= summ["n_eligible_atr_prev_close_ok"] <= summ["n_eligible"]
          and isinstance(summ["parts"], list)
          and all(isinstance(q, dict) and set(q) == {"lo", "hi", "sha256"} and _is_int(q["lo"]) and _is_int(q["hi"])
                  and 0 <= q["lo"] <= q["hi"] and isinstance(q["sha256"], str) and len(q["sha256"]) == 64 for q in summ["parts"]))
    if not ok:
        raise ContractError(f"{d}: p1_summary 중첩 스키마 불일치(bool은 정수가 아니다)")
    return {"draws": json.loads((d / "p1_draws.json").read_text()), "null": read_jsonl(d / "p1_null.jsonl"),
            "timing_draws": json.loads((d / "p1_timing_draws.json").read_text()),
            "timing_null": read_jsonl(d / "p1_timing_null.jsonl"), "summary": summ}


def expected_run_dirs(base: Path) -> set[str]:
    names = {f"{a}_{v}" for a in ARMS for v in VARIANTS} | {f"{a}_P1" for a in ARMS} | {f"{a}_P1_merged" for a in ARMS}
    return {str(base / "runs" / n) for n in names}


def check_run_inventory(base: Path) -> None:
    got = {str(p) for p in (base / "runs").iterdir()} if (base / "runs").exists() else set()
    want = expected_run_dirs(base)
    if got != want:
        raise ContractError(f"runs/ 목록 불일치: 빠짐 {sorted(want - got)} · 남음 {sorted(got - want)}")


# ── 실패 보존((g) 전반 · 규약 F77) ──────────────────────────────────────────
FAILURE_FILES = ("_failure_error.txt", "_failure_events.jsonl", "_failure_state.json")
P1_FAILURE_FILES = ("_failure_draws.json", "_failure_error.txt", "_failure_null.jsonl", "_failure_timing_draws.json",
                    "_failure_timing_null.jsonl")


def write_error(out: Path, e: BaseException) -> None:
    import traceback
    out.mkdir(parents=True, exist_ok=True)
    (out / "_failure_error.txt").write_text("".join(traceback.format_exception(e)))


def write_run_failure(out: Path, strategy: Any, cause: BaseException) -> dict[str, Any]:
    """전략 기록 보존: 이벤트 전부 · 상태·깔때기 요약 · 원인 트레이스백 — 출력 디렉터리에 바로(기록이 해시하고 read_run은 거부)."""
    out.mkdir(parents=True, exist_ok=True)
    s = strategy
    (out / "_failure_events.jsonl").write_text("".join(json.dumps(e, sort_keys=True, default=str) + "\n" for e in s.events))
    state = {"arm": s.arm, "variant": s.variant.name, "state": s.state, "exit_ts": s.exit_ts, "window_prints": s.window_prints,
             "ingested": s.ingested, "funnel": dict(s.funnel), "sub": dict(s.sub), "entry": dict(s.entry), "n_events": len(s.events)}
    (out / "_failure_state.json").write_text(json.dumps(state, sort_keys=True, indent=1) + "\n")
    write_error(out, cause)
    return state


def write_p1_failure(out: Path, failure: P1.P1Failure, cause: BaseException) -> None:
    """P1 조각 기록 보존: 끝난 게이트·timing 추출 · 귀무 행 · 원인 트레이스백."""
    from backtest import p1_core as C
    out.mkdir(parents=True, exist_ok=True)
    (out / "_failure_draws.json").write_text(C.canonical_json(failure.draws))
    (out / "_failure_null.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in failure.null))
    (out / "_failure_timing_draws.json").write_text(C.canonical_json(failure.timing_draws))
    (out / "_failure_timing_null.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in failure.timing_null))
    write_error(out, cause)
