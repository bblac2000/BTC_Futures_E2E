"""트라이얼 #2 단계 실행기(단계 2f F5 · G1·G3·G10~G13) — 모든 실행을 격리 subprocess로 · 실행마다 verbatim 기록 · 이어 하기는 검증 뒤만.

    python -m backtest.t2_stages --evaluator-commit H --stage prepare      # 원시 캡처 → 감사·빌드(한 번)
    (data_pins.json + 레지스트리 행 커밋 · 푸시 = 사용자 체크포인트)
    python -m backtest.t2_stages --evaluator-commit H --stage verify       # 원시에서 다시 빌드 대조 → verify 영수증
    python -m backtest.t2_stages --evaluator-commit H --stage A
    python -m backtest.t2_stages --evaluator-commit H --stage base --jobs 2    # B · P2_delay1 · P2_delay5 · P3_invert
    python -m backtest.t2_stages --evaluator-commit H --stage p1 --parts 8 --jobs 4
    python -m backtest.t2_stages --evaluator-commit H --stage p1-merge
    python -m backtest.t2_stages --evaluator-commit H --stage p4 --jobs 3      # P4_draw000..199

- 모든 단계(prepare 포함): 판정기 커밋 H가 푸시됐고 판정기 파일이 그대로이며 작업 트리가 깨끗해야 한다(G1).
- verify 뒤 단계: 커밋·푸시된 data_pins.json · verify 영수증 = 현재 매니페스트 해시·핀 커밋·핀 값·H·코드 지문(G11·G13).
- 이어 하기(G3): 기록이 있으면 출처(H · 핀 커밋 · 매니페스트 · 지문 · 변형)와 **모든 출력 해시**가 지금과 같아야 "완료" —
  다르면 오류(조용히 다시 돌리지 않는다).
- 이 실행기는 산출물을 열지 않는다(해시만) — 판정은 `backtest.evaluate_t2` 한 번. OOS는 없다.
"""
from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backtest import t2_provenance as PV
from backtest.replay import RunRecord, run_isolated

ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = ROOT / "var" / "backtest" / "t2" / "IS"
STRATEGY = "strategies.trial02.run"
P1_MODULE = "backtest.p1_t2_run"
P1_DRAWS = 1000
P4_DRAWS = 200
BASE_NAMES = ("B", "P2_delay1", "P2_delay5", "P3_invert")


def p4_names() -> list[str]:
    return [f"P4_draw{d:03d}" for d in range(P4_DRAWS)]


RUN_OUTPUTS = ("trades.jsonl", "crosses.jsonl", "days.jsonl", "validity.json", "meta.json")
P1_OUTPUTS = ("p1_draws.json", "p1_null.jsonl")
PREP_OUTPUTS = ("manifest.json", "bars_1m.parquet", "funding.json", "source_audit.json", "kline_close_daily.json")
PREP_MODULE = "backtest.prepare_t2"


class Stages:
    def __init__(self, evaluator_commit: str, base: Path = BASE_DIR, repo: Path = ROOT,
                 runner: Callable[..., RunRecord] = run_isolated, fetch: bool = True):
        self.h, self.base, self.repo, self.runner, self.fetch = evaluator_commit, base, repo, runner, fetch
        self.prep, self.runs, self.records = base / "prepared", base / "runs", base / "_records"

    # ── 공통 검사 ──────────────────────────────────────────────────────────
    def preflight(self) -> str:
        PV.require_evaluator_frozen(self.repo, self.h, fetch=self.fetch)
        return PV.fingerprint(self.repo)

    def receipt_ok(self, fp: str) -> dict[str, Any]:
        """G11·G13 + Codex 2f after #2: 영수증은 **성공한 verify 실행 기록**과 함께만 — 그 기록의 명령·출처·출력 해시가
        지금 준비 파일과 같아야 한다(건너뛴 이어 하기에서도 준비 파일 변경을 잡는다)."""
        pins, pc = PV.load_pins(self.repo, fetch=self.fetch)
        base_prov = {"evaluator_commit": self.h, "fingerprint": fp, "pins_commit": pc}
        vrec = self._record_path("verify")
        if not vrec.exists():
            raise PV.ProvenanceError("verify 실행 기록이 없다 — verify 단계를 먼저")
        PV.check_record(json.loads(vrec.read_text()), out_dir=self.prep, expect=base_prov | {"variant": "verify"},
                        module=PREP_MODULE, args=["--verify"], required=PREP_OUTPUTS)
        f = self.records / "verify_receipt.json"
        if not f.exists():
            raise PV.ProvenanceError("verify 영수증이 없다")
        receipt = json.loads(f.read_text())
        PV.check_receipt(receipt, prepared=self.prep, pins=pins, pins_c=pc, evaluator_commit=self.h, fp=fp)
        return base_prov | {"manifest_sha256": receipt["manifest_sha256"]}

    def _record_path(self, name: str) -> Path:
        return self.records / f"{name}.json"

    def done(self, name: str, job: tuple[str, list[str], Path, tuple[str, ...]], expect: dict[str, Any]) -> bool:
        f = self._record_path(name)
        if not f.exists():
            return False
        module, args, out, required = job
        PV.check_record(json.loads(f.read_text()), out_dir=out, expect=expect, module=module, args=args, required=required)
        return True                                               # 불일치 → 위에서 오류(다시 돌리지 않는다)

    def run_one(self, name: str, module: str, args: list[str], out: Path, prov: dict[str, Any]) -> dict[str, Any]:
        t0 = time.time()
        if "fingerprint" in prov and PV.fingerprint(self.repo) != prov["fingerprint"]:
            #  K4: 긴 단계 도중 코드가 바뀌면 다음 하위 프로세스를 띄우지 않는다(기록된 지문과 실제 코드의 불일치 방지)
            raise PV.ProvenanceError(f"{name}: 실행 코드 지문이 단계 시작 뒤 바뀌었다")
        rec = self.runner(module, args, out, timeout_s=24 * 3600)
        self.records.mkdir(parents=True, exist_ok=True)
        body = {"run": asdict(rec), "provenance": prov | {"head": PV.head(self.repo)}, "wall_s": round(time.time() - t0, 1)}
        self._record_path(name).write_text(json.dumps(body, sort_keys=True, indent=1, ensure_ascii=False) + "\n")
        return {"name": name, "returncode": rec.returncode, "stdout": rec.stdout.strip()[-300:]}

    def run_many(self, jobs: dict[str, tuple[str, list[str], Path, tuple[str, ...]]], prov: dict[str, Any],
                 n_jobs: int) -> list[dict[str, Any]]:
        todo = {k: v for k, v in jobs.items() if not self.done(k, v, prov | {"variant": k})}
        with ThreadPoolExecutor(max(1, n_jobs)) as ex:
            return list(ex.map(lambda kv: self.run_one(kv[0], kv[1][0], kv[1][1], kv[1][2], prov | {"variant": kv[0]}),
                               todo.items()))

    # ── 단계 ──────────────────────────────────────────────────────────────
    def prepare(self) -> list[dict[str, Any]]:
        fp = self.preflight()
        prov = {"evaluator_commit": self.h, "fingerprint": fp, "variant": "prepare"}
        if self.done("prepare", (PREP_MODULE, [], self.prep, PREP_OUTPUTS), prov):
            return []                                             # 검증된 완료 — 다시 캡처하지 않는다
        return [self.run_one("prepare", PREP_MODULE, [], self.prep, prov)]

    def verify(self) -> list[dict[str, Any]]:
        fp = self.preflight()
        pins, pc = PV.load_pins(self.repo, fetch=self.fetch)
        if not self.done("prepare", (PREP_MODULE, [], self.prep, PREP_OUTPUTS),
                         {"evaluator_commit": self.h, "fingerprint": fp, "variant": "prepare"}):
            raise PV.ProvenanceError("prepare 기록이 없다")
        m = json.loads((self.prep / "manifest.json").read_text())
        if m["raw"] != pins["raw"] or {k: m[k] for k in pins["prepared"]} != pins["prepared"]:
            raise PV.ProvenanceError("data_pins.json이 준비 산출물 매니페스트와 다르다")
        prov = {"evaluator_commit": self.h, "fingerprint": fp, "pins_commit": pc, "variant": "verify"}
        if self.done("verify", (PREP_MODULE, ["--verify"], self.prep, PREP_OUTPUTS), prov):
            return []
        res = self.run_one("verify", PREP_MODULE, ["--verify"], self.prep, prov)
        if res["returncode"] == 0:
            receipt = PV.make_receipt(self.prep, pins, pc, self.h, fp)
            (self.records / "verify_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=1) + "\n")
        return [res]

    def strategy_jobs(self, names: list[str]) -> dict[str, tuple[str, list[str], Path, tuple[str, ...]]]:
        return {n: (STRATEGY, ["--variant", n, "--prepared", str(self.prep)], self.runs / n, RUN_OUTPUTS) for n in names}

    def arm(self, names: list[str], n_jobs: int) -> list[dict[str, Any]]:
        prov = self.receipt_ok(self.preflight())
        if names != ["A"] and not self.done("A", self.strategy_jobs(["A"])["A"], prov | {"variant": "A"}):
            raise PV.ProvenanceError("원판 Arm A가 먼저(검증된 기록)")
        return self.run_many(self.strategy_jobs(names), prov, n_jobs)

    def p1_jobs(self, parts: int) -> dict[str, tuple[str, list[str], Path, tuple[str, ...]]]:
        step = -(-P1_DRAWS // parts)
        jobs = {}
        for lo in range(0, P1_DRAWS, step):
            hi = min(P1_DRAWS - 1, lo + step - 1)
            jobs[f"P1_part_{lo:03d}_{hi:03d}"] = (P1_MODULE, ["--a-dir", str(self.runs / "A"), "--prepared", str(self.prep),
                                                              "--draws", f"{lo}-{hi}"], self.runs / "P1" / f"part_{lo:03d}_{hi:03d}",
                                                  P1_OUTPUTS)
        return jobs

    def p1(self, parts: int, n_jobs: int) -> list[dict[str, Any]]:
        prov = self.receipt_ok(self.preflight())
        if not self.done("A", self.strategy_jobs(["A"])["A"], prov | {"variant": "A"}):
            raise PV.ProvenanceError("P1은 원판 Arm A 뒤(쌍 입력)")
        return self.run_many(self.p1_jobs(parts), prov, n_jobs)

    def p1_merge(self) -> list[dict[str, Any]]:
        prov = self.receipt_ok(self.preflight())
        expect: dict[str, dict[str, str]] = {}
        parts = sorted(self.records.glob("P1_part_*.json"))
        if not parts:
            raise PV.ProvenanceError("P1 조각 기록이 없다")
        for f in parts:
            name = f.stem
            rec = json.loads(f.read_text())
            job = (P1_MODULE, rec["run"]["args"], self.runs / "P1" / name.removeprefix("P1_"), P1_OUTPUTS)
            lo_hi = name.removeprefix("P1_part_").split("_")
            want_args = ["--a-dir", str(self.runs / "A"), "--prepared", str(self.prep), "--draws", f"{int(lo_hi[0])}-{int(lo_hi[1])}"]
            if rec["run"]["args"] != want_args:
                raise PV.ProvenanceError(f"P1 조각 {name}의 명령이 기대와 다르다")
            self.done(name, job, prov | {"variant": name})
            expect[name.removeprefix("P1_")] = rec["run"]["outputs"]
        ef = self.records / "p1_merge_expect.json"
        merge_args = ["--merge", "--parts-root", str(self.runs / "P1"), "--expect", str(ef), "--prepared", str(self.prep)]
        mjob = (P1_MODULE, merge_args, self.runs / "P1_merged", P1_OUTPUTS)
        if self.done("P1_merge", mjob, prov | {"variant": "P1_merge"}):
            if json.loads(ef.read_text()) != expect:
                raise PV.ProvenanceError("P1 병합 기대값이 조각 기록과 다르다")
            return []
        ef.write_text(json.dumps(expect, sort_keys=True, indent=1) + "\n")
        return [self.run_one("P1_merge", P1_MODULE, merge_args, self.runs / "P1_merged", prov | {"variant": "P1_merge"})]


def gate_cli(prepared: Path, *, repo: Path = ROOT) -> dict[str, Any]:
    """직접 CLI 실행도 같은 문을 지난다(Codex 2f after #5): 영수증의 판정기 커밋으로 선행 검사 + 영수증·verify 기록 대조."""
    base = prepared.parent
    rf = base / "_records" / "verify_receipt.json"
    if not rf.exists():
        raise PV.ProvenanceError("verify 영수증이 없다 — 실행 전 verify 단계가 필요")
    s = Stages(json.loads(rf.read_text())["evaluator_commit"], base=base, repo=repo, fetch=True)   # 직접 실행은 항상 fetch
    return s.receipt_ok(s.preflight())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator-commit", required=True)
    ap.add_argument("--stage", choices=["prepare", "verify", "A", "base", "p1", "p1-merge", "p4"], required=True)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--parts", type=int, default=4)
    a = ap.parse_args(argv)
    s = Stages(a.evaluator_commit)
    if a.stage == "prepare":
        res = s.prepare()
    elif a.stage == "verify":
        res = s.verify()
    elif a.stage == "A":
        res = s.arm(["A"], 1)
    elif a.stage == "base":
        res = s.arm(list(BASE_NAMES), a.jobs)
    elif a.stage == "p1":
        res = s.p1(a.parts, a.jobs)
    elif a.stage == "p1-merge":
        res = s.p1_merge()
    else:
        res = s.arm(p4_names(), a.jobs)
    for r in res:
        print(json.dumps(r, ensure_ascii=False), flush=True)
    return 0 if all(r["returncode"] == 0 for r in res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
