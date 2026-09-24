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
        pins, pc = PV.load_pins(self.repo, fetch=self.fetch)
        f = self.records / "verify_receipt.json"
        if not f.exists():
            raise PV.ProvenanceError("verify 영수증이 없다 — verify 단계를 먼저")
        receipt = json.loads(f.read_text())
        PV.check_receipt(receipt, prepared=self.prep, pins=pins, pins_c=pc, evaluator_commit=self.h, fp=fp)
        return {"evaluator_commit": self.h, "pins_commit": pc, "manifest_sha256": receipt["manifest_sha256"], "fingerprint": fp}

    def _record_path(self, name: str) -> Path:
        return self.records / f"{name}.json"

    def done(self, name: str, out: Path, expect: dict[str, Any]) -> bool:
        f = self._record_path(name)
        if not f.exists():
            return False
        PV.check_record(json.loads(f.read_text()), out_dir=out, expect=expect)      # 불일치 → 오류(다시 돌리지 않는다)
        return True

    def run_one(self, name: str, module: str, args: list[str], out: Path, prov: dict[str, Any]) -> dict[str, Any]:
        t0 = time.time()
        rec = self.runner(module, args, out, timeout_s=24 * 3600)
        self.records.mkdir(parents=True, exist_ok=True)
        body = {"run": asdict(rec), "provenance": prov | {"head": PV.head(self.repo)}, "wall_s": round(time.time() - t0, 1)}
        self._record_path(name).write_text(json.dumps(body, sort_keys=True, indent=1, ensure_ascii=False) + "\n")
        return {"name": name, "returncode": rec.returncode, "stdout": rec.stdout.strip()[-300:]}

    def run_many(self, jobs: dict[str, tuple[str, list[str], Path]], prov: dict[str, Any], n_jobs: int) -> list[dict[str, Any]]:
        todo = {k: v for k, v in jobs.items() if not self.done(k, v[2], prov | {"variant": k})}
        with ThreadPoolExecutor(max(1, n_jobs)) as ex:
            return list(ex.map(lambda kv: self.run_one(kv[0], kv[1][0], kv[1][1], kv[1][2], prov | {"variant": kv[0]}),
                               todo.items()))

    # ── 단계 ──────────────────────────────────────────────────────────────
    def prepare(self) -> list[dict[str, Any]]:
        fp = self.preflight()
        return [self.run_one("prepare", "backtest.prepare_t2", [], self.prep, {"evaluator_commit": self.h, "fingerprint": fp})]

    def verify(self) -> list[dict[str, Any]]:
        fp = self.preflight()
        pins, pc = PV.load_pins(self.repo, fetch=self.fetch)
        m = json.loads((self.prep / "manifest.json").read_text())
        if m["raw"] != pins["raw"] or {k: m[k] for k in pins["prepared"]} != pins["prepared"]:
            raise PV.ProvenanceError("data_pins.json이 준비 산출물 매니페스트와 다르다")
        res = self.run_one("verify", "backtest.prepare_t2", ["--verify"], self.prep,
                           {"evaluator_commit": self.h, "fingerprint": fp, "pins_commit": pc})
        if res["returncode"] == 0:
            receipt = PV.make_receipt(self.prep, pins, pc, self.h, fp)
            (self.records / "verify_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=1) + "\n")
        return [res]

    def strategy_jobs(self, names: list[str]) -> dict[str, tuple[str, list[str], Path]]:
        return {n: (STRATEGY, ["--variant", n, "--prepared", str(self.prep)], self.runs / n) for n in names}

    def arm(self, names: list[str], n_jobs: int) -> list[dict[str, Any]]:
        prov = self.receipt_ok(self.preflight())
        if names != ["A"] and not self.done("A", self.runs / "A", prov | {"variant": "A"}):
            raise PV.ProvenanceError("원판 Arm A가 먼저(검증된 기록)")
        return self.run_many(self.strategy_jobs(names), prov, n_jobs)

    def p1(self, parts: int, n_jobs: int) -> list[dict[str, Any]]:
        prov = self.receipt_ok(self.preflight())
        if not self.done("A", self.runs / "A", prov | {"variant": "A"}):
            raise PV.ProvenanceError("P1은 원판 Arm A 뒤(쌍 입력)")
        step = -(-P1_DRAWS // parts)
        jobs = {}
        for lo in range(0, P1_DRAWS, step):
            hi = min(P1_DRAWS - 1, lo + step - 1)
            jobs[f"P1_part_{lo:03d}_{hi:03d}"] = (P1_MODULE, ["--a-dir", str(self.runs / "A"), "--prepared", str(self.prep),
                                                              "--draws", f"{lo}-{hi}"], self.runs / "P1" / f"part_{lo:03d}_{hi:03d}")
        return self.run_many(jobs, prov, n_jobs)

    def p1_merge(self) -> list[dict[str, Any]]:
        prov = self.receipt_ok(self.preflight())
        expect: dict[str, dict[str, str]] = {}
        parts = sorted(p for p in self.records.glob("P1_part_*.json"))
        if not parts:
            raise PV.ProvenanceError("P1 조각 기록이 없다")
        for f in parts:
            name = f.stem
            out = self.runs / "P1" / name.removeprefix("P1_")
            self.done(name, out, prov | {"variant": name})
            rec = json.loads(f.read_text())
            expect[name.removeprefix("P1_")] = rec["run"]["outputs"]
        ef = self.records / "p1_merge_expect.json"
        ef.write_text(json.dumps(expect, sort_keys=True, indent=1) + "\n")
        return [self.run_one("P1_merge", P1_MODULE, ["--merge", "--parts-root", str(self.runs / "P1"), "--expect", str(ef)],
                             self.runs / "P1_merged", prov | {"variant": "P1_merge"})]


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
