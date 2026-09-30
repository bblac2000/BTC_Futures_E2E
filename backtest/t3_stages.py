"""트라이얼 #3 단계 실행기(단계 2 (g) HALF 1 · 계획 r3 K1~K12) — 모든 실행을 격리 subprocess로 · 작업마다 verbatim 기록 · 판정은 한 번.

    python -m backtest.t3_stages --evaluator-commit H --stage prepare
    python -m backtest.t3_stages --evaluator-commit H --stage pins         # data_pins.json 쓰기 → 커밋 + 행 #54 + 푸시(체크포인트)
    python -m backtest.t3_stages --evaluator-commit H --stage verify       # 원시에서 다시 빌드 대조 → verify 영수증
    python -m backtest.t3_stages --evaluator-commit H --stage runs --only L_base     # 메모리 측정(계획 K10)
    python -m backtest.t3_stages --evaluator-commit H --stage runs --jobs 3
    python -m backtest.t3_stages --evaluator-commit H --stage p1 --parts 8 --jobs 3
    python -m backtest.t3_stages --evaluator-commit H --stage p1-merge
    python -m backtest.t3_stages --evaluator-commit H --stage evaluate     # 한 번만

- 모든 단계: fetch 한 번 → 동결(H) + 레지스트리 행(#52·#53) + 지문 · 자식에게 T3_STAGE_ORIGIN(= fetch한 origin/main) 전달(K3′).
- 스케줄러(K6): 동시에 최대 --jobs · 첫 rc ≠ 0에서 새 제출 중단 · 돌던 자식은 끝까지 기록 · 실패 단계 뒤 다음 단계 없음 ·
  rc ≠ 0 기록이나 기록 없는 부분 출력 디렉터리(K6′)는 다시 돌리지 않고 거부(검토용으로 그대로 둔다) · 실패 파일은 _records/failures/로 복사.
- 이어 하기: rc 0 · 명령·인자·출처(H · 지문 · 핀 커밋 · 매니페스트 · 변형) · 모든 출력 해시가 지금과 같을 때만 "완료".
- 이 실행기는 산출물을 열지 않는다(해시만) — 판정은 `evaluate_t3.evaluate` 한 번(지연 import · K11).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backtest import t3_provenance as PV
from backtest.replay import RunRecord, run_isolated

ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = ROOT / "var" / "t3" / "IS"
STRATEGY = "strategies.trial03.run"
P1_MODULE = "backtest.p1_t3_run"
PREP_MODULE = "backtest.prepare_t3"
ARMS = ("L", "S")
VARIANTS = ("base", "P2_delay1", "P2_delay5", "P3_invert")
RUN_OUTPUTS = ("events.jsonl", "summary.json", "trades_t3.jsonl")
P1_OUTPUTS = ("p1_part.json",)
PREP_OUTPUTS = ("bars_1m.parquet", "funding.json", "kline_close_daily.json", "manifest.json", "oi_5m.json", "oi_unusable.json",
                "source_audit.json")
P1_DRAWS = 1000
PROV_KEYS = ("evaluator_commit", "fingerprint", "pins_commit", "manifest_sha256", "variant")

Job = tuple[str, list[str], Path, tuple[str, ...]]


class StageFailed(RuntimeError):
    pass


def partition(parts: int, draws: int = P1_DRAWS) -> list[list[int]]:
    if not 1 <= parts <= draws:
        raise StageFailed(f"--parts {parts}")
    step = -(-draws // parts)
    return [[lo, min(draws - 1, lo + step - 1)] for lo in range(0, draws, step)]


class Stages:
    def __init__(self, evaluator_commit: str, base: Path = BASE_DIR, repo: Path = ROOT,
                 runner: Callable[..., RunRecord] = run_isolated, fetch: bool = True):
        self.h, self.base, self.repo, self.runner, self.fetch = evaluator_commit, base, repo, runner, fetch
        self.prep, self.runs, self.records = base / "prepared", base / "runs", base / "_records"
        self.origin = ""

    # ── 관문 ─────────────────────────────────────────────────────────────
    def begin(self) -> dict[str, Any]:
        if self.fetch:
            PV.fetch(self.repo)
        self.origin = PV._git(self.repo, "rev-parse", "origin/main").stdout.strip()
        PV.require_frozen(self.repo, self.h, fetch_first=False)
        rows = PV.require_rows(self.repo, self.h)
        return {"evaluator_commit": self.h, "fingerprint": rows["fingerprint"], "origin": self.origin,
                "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "rows": rows}

    def env(self) -> dict[str, str]:
        return dict(os.environ) | {"T3_STAGE_ORIGIN": self.origin, "T3_STAGE_REPO": str(self.repo)}

    def receipt_ok(self, prov: dict[str, Any]) -> dict[str, Any]:
        pins, pc = PV.load_pins(self.repo, fetch_first=False)
        vprov = prov | {"pins_commit": pc, "manifest_sha256": pins["manifest_sha256"]}
        if not self.done("verify", self.verify_job(), vprov | {"variant": "verify"}):
            raise StageFailed("verify 기록이 없다 — verify 단계를 먼저")
        f = self.records / "verify_receipt.json"
        if not f.exists():
            raise StageFailed("verify 영수증이 없다")
        PV.check_receipt(json.loads(f.read_text()), prepared=self.prep, pins=pins, pins_c=pc, commit=self.h, fp=prov["fingerprint"])
        return vprov

    # ── 기록 ─────────────────────────────────────────────────────────────
    def _rec(self, name: str) -> Path:
        return self.records / f"{name}.json"

    def check_record(self, name: str, job: Job, expect: dict[str, Any]) -> None:
        module, args, out, required = job
        body = json.loads(self._rec(name).read_text())
        run, prov = body["run"], body["provenance"]
        if run["returncode"] != 0:
            raise StageFailed(f"{name}: 실패 기록(rc {run['returncode']}) — 다시 돌리지 않는다(검토 필요)")
        if run["module"] != module or run["args"] != args:
            raise StageFailed(f"{name}: 기록의 명령·인자가 기대와 다르다")
        if any(prov.get(k) != expect.get(k) for k in PROV_KEYS if k in expect):
            raise StageFailed(f"{name}: 기록의 출처(H·지문·핀·매니페스트·변형)가 지금과 다르다")
        files = {p.name: PV.sha_file(p) for p in sorted(out.iterdir()) if p.is_file()} if out.exists() else {}
        if files != run["outputs"] or any(n.startswith("_failure") for n in files) or not set(required) <= set(files):
            raise StageFailed(f"{name}: 출력 파일·해시가 기록과 다르거나 필수 출력이 없다")

    def done(self, name: str, job: Job, expect: dict[str, Any]) -> bool:
        if not self._rec(name).exists():
            out = job[2]
            if out.exists() and any(out.iterdir()) and name not in ("prepare", "verify"):
                raise StageFailed(f"{name}: 기록 없는 부분 출력 {out} — 다시 돌리지 않는다(검토용 보존 · K6′)")
            return False
        self.check_record(name, job, expect)
        return True

    def run_one(self, name: str, job: Job, prov: dict[str, Any]) -> int:
        module, args, out, _ = job
        if PV.fingerprint(self.repo) != prov["fingerprint"]:
            raise StageFailed(f"{name}: 실행 코드 지문이 단계 시작 뒤 바뀌었다")
        t0 = time.time()
        rec = self.runner(module, args, out, timeout_s=48 * 3600, env=self.env())
        self.records.mkdir(parents=True, exist_ok=True)
        body = {"run": asdict(rec), "provenance": {k: v for k, v in prov.items() if k != "rows"} | {"rows": prov.get("rows")},
                "wall_s": round(time.time() - t0, 1)}
        self._rec(name).write_text(json.dumps(body, sort_keys=True, indent=1, ensure_ascii=False) + "\n")
        if rec.returncode != 0 and out.exists():
            dst = self.records / "failures" / name
            dst.mkdir(parents=True, exist_ok=True)
            for p in out.iterdir():
                if p.name.startswith("_failure"):
                    shutil.copy(p, dst / p.name)
        return rec.returncode

    def run_many(self, jobs: dict[str, Job], prov: dict[str, Any], n_jobs: int) -> list[tuple[str, int]]:
        """K6: 동시에 최대 n_jobs · 첫 실패에서 새 제출 중단 · 돌던 것은 끝까지 기록 · 실패면 StageFailed."""
        todo = [(k, v) for k, v in jobs.items() if not self.done(k, v, prov | {"variant": k})]
        results: list[tuple[str, int]] = []
        failed = False
        with ThreadPoolExecutor(max(1, n_jobs)) as ex:
            running: dict[Future[int], str] = {}
            it = iter(todo)
            while True:
                while not failed and len(running) < max(1, n_jobs):
                    nxt = next(it, None)
                    if nxt is None:
                        break
                    k, v = nxt
                    running[ex.submit(self.run_one, k, v, prov | {"variant": k})] = k
                if not running:
                    break
                fin, _ = wait(running, return_when=FIRST_COMPLETED)
                for f in fin:
                    k = running.pop(f)
                    rc = f.result()
                    results.append((k, rc))
                    failed = failed or rc != 0
        if failed:
            raise StageFailed(f"실패한 작업: {[k for k, rc in results if rc != 0]} — 다음 작업·단계를 시작하지 않았다")
        return results

    # ── 작업 정의 ─────────────────────────────────────────────────────────
    def prepare_job(self) -> Job:
        return (PREP_MODULE, ["--evaluator-commit", self.h], self.prep, PREP_OUTPUTS)

    def verify_job(self) -> Job:
        return (PREP_MODULE, ["--verify", "--evaluator-commit", self.h], self.prep, PREP_OUTPUTS)

    def run_job(self, arm: str, var: str) -> Job:
        return (STRATEGY, ["--arm", arm, "--variant", var, "--prepared", str(self.prep), "--evaluator-commit", self.h],
                self.runs / f"{arm}_{var}", RUN_OUTPUTS)

    def p1_job(self, arm: str, lo: int, hi: int) -> Job:
        return (P1_MODULE, ["--arm", arm, "--lo", str(lo), "--hi", str(hi), "--prepared", str(self.prep), "--evaluator-commit", self.h],
                self.runs / f"{arm}_P1" / f"part_{lo:03d}_{hi:03d}", P1_OUTPUTS)

    def run_jobs(self) -> dict[str, Job]:
        return {f"{a}_{v}": self.run_job(a, v) for a in ARMS for v in VARIANTS}

    def p1_jobs(self) -> dict[str, Job]:
        part = self.partition()
        return {f"P1_{a}_{lo:03d}_{hi:03d}": self.p1_job(a, lo, hi) for a in ARMS for lo, hi in part}

    def partition(self) -> list[list[int]]:
        f = self.records / "p1_partition.json"
        if not f.exists():
            raise StageFailed("P1 분할이 기록되지 않았다")
        return json.loads(f.read_text())

    # ── 단계 ─────────────────────────────────────────────────────────────
    def stage_prepare(self) -> list[tuple[str, int]]:
        prov = self.begin() | {"variant": "prepare"}
        if self.done("prepare", self.prepare_job(), prov):
            return []
        rc = self.run_one("prepare", self.prepare_job(), prov)
        if rc != 0:
            raise StageFailed(f"prepare rc {rc} — 데이터 품질 중단이면 보고하고 멈춘다")
        return [("prepare", rc)]

    def stage_pins(self) -> dict[str, Any]:
        prov = self.begin()
        if not self.done("prepare", self.prepare_job(), prov | {"variant": "prepare"}):
            raise StageFailed("prepare 기록이 없다")
        pins = PV.make_pins(self.prep)
        (self.repo / PV.PINS_REL).write_text(json.dumps(pins, sort_keys=True, indent=1) + "\n")
        return pins

    def stage_verify(self) -> list[tuple[str, int]]:
        prov = self.begin()
        pins, pc = PV.load_pins(self.repo, fetch_first=False)
        if not self.done("prepare", self.prepare_job(), prov | {"variant": "prepare"}):
            raise StageFailed("prepare 기록이 없다")
        PV.check_pins_against_prepared(self.prep, pins)
        vprov = prov | {"pins_commit": pc, "manifest_sha256": pins["manifest_sha256"], "variant": "verify"}
        out: list[tuple[str, int]] = []
        if not self.done("verify", self.verify_job(), vprov):
            rc = self.run_one("verify", self.verify_job(), vprov)
            out.append(("verify", rc))
            if rc != 0:
                raise StageFailed(f"verify rc {rc}")
        (self.records / "verify_receipt.json").write_text(
            json.dumps(PV.make_receipt(pins, pc, self.h, prov["fingerprint"]), sort_keys=True, indent=1) + "\n")
        return out

    def stage_runs(self, n_jobs: int, only: str | None = None) -> list[tuple[str, int]]:
        prov = self.receipt_ok(self.begin())
        jobs = self.run_jobs()
        if only is not None:
            if only not in jobs:
                raise StageFailed(f"--only {only}")
            jobs = {only: jobs[only]}
        return self.run_many(jobs, prov, n_jobs)

    def stage_p1(self, parts: int, n_jobs: int) -> list[tuple[str, int]]:
        prov = self.receipt_ok(self.begin())
        for k, job in self.run_jobs().items():
            if k.endswith("_base") and not self.done(k, job, prov | {"variant": k}):
                raise StageFailed(f"P1은 기본 실행 {k} 뒤")
        want = partition(parts)
        f = self.records / "p1_partition.json"
        if f.exists():
            if json.loads(f.read_text()) != want:
                raise StageFailed("P1 분할이 처음 기록과 다르다(--parts 변경 금지 · K9)")
        else:
            self.records.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(want) + "\n")
        return self.run_many(self.p1_jobs(), prov, n_jobs)

    def check_p1_complete(self, prov: dict[str, Any]) -> None:
        jobs = self.p1_jobs()
        for k, job in jobs.items():
            if not self.done(k, job, prov | {"variant": k}):
                raise StageFailed(f"P1 조각 {k}가 끝나지 않았다")
        for a in ARMS:
            have = sorted(p.name for p in (self.runs / f"{a}_P1").iterdir())
            if have != sorted(job[2].name for k, job in jobs.items() if k.startswith(f"P1_{a}_")):
                raise StageFailed(f"{a}: P1 조각 디렉터리가 분할과 다르다")

    def merge_expected(self, arm: str) -> Path:
        return self.runs / f"{arm}_P1_merged"

    def stage_p1_merge(self) -> list[tuple[str, int]]:
        from backtest import t3_outputs as O
        prov = self.receipt_ok(self.begin())
        self.check_p1_complete(prov)
        out = []
        for a in ARMS:
            name = f"P1_merge_{a}"
            d = self.merge_expected(a)
            rec = self._rec(name)
            if rec.exists():
                self.check_merge_record(a, prov)
                continue
            if d.exists():
                raise StageFailed(f"{name}: 기록 없는 병합 디렉터리 — 검토용 보존")
            O.write_p1_merged(self.base, a, O.read_p1_parts(self.base, a))
            files = {p.name: PV.sha_file(p) for p in sorted(d.iterdir())}
            rec.write_text(json.dumps({"provenance": {k: v for k, v in prov.items() if k != "rows"} | {"variant": name},
                                       "outputs": files}, sort_keys=True, indent=1) + "\n")
            out.append((name, 0))
        return out

    def check_merge_record(self, arm: str, prov: dict[str, Any]) -> None:
        name = f"P1_merge_{arm}"
        body = json.loads(self._rec(name).read_text())
        d = self.merge_expected(arm)
        files = {p.name: PV.sha_file(p) for p in sorted(d.iterdir())} if d.exists() else {}
        exp = {k: v for k, v in prov.items() if k in PROV_KEYS} | {"variant": name}
        if any(body["provenance"].get(k) != v for k, v in exp.items()) or body["outputs"] != files:
            raise StageFailed(f"{name}: 병합 기록이 출처·출력 해시와 다르다")

    def check_all_records(self, prov: dict[str, Any]) -> dict[str, str]:
        """판정 전(K5): 8개 실행 · 분할의 모든 P1 조각 · 두 병합 기록 — rc 0 · 출처 · 출력 해시. 반환 = 기록 파일 SHA256."""
        for k, job in self.run_jobs().items():
            if not self.done(k, job, prov | {"variant": k}):
                raise StageFailed(f"실행 {k} 기록이 없다")
        self.check_p1_complete(prov)
        for a in ARMS:
            if not self._rec(f"P1_merge_{a}").exists():
                raise StageFailed(f"P1_merge_{a} 기록이 없다")
            self.check_merge_record(a, prov)
        return {p.name: PV.sha_file(p) for p in sorted(self.records.glob("*.json"))}

    def stage_evaluate(self) -> tuple[str, dict[str, Any]]:
        from backtest import evaluate_t3 as E
        return E.evaluate(self.base, self.repo, evaluator_commit=self.h, fetch=self.fetch)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="트라이얼 #3 단계 실행기")
    ap.add_argument("--evaluator-commit", required=True)
    ap.add_argument("--stage", required=True, choices=["prepare", "pins", "verify", "runs", "p1", "p1-merge", "evaluate"])
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--parts", type=int, default=8)
    ap.add_argument("--only")
    a = ap.parse_args(argv)
    st = Stages(a.evaluator_commit)
    try:
        if a.stage == "prepare":
            res: Any = st.stage_prepare()
        elif a.stage == "pins":
            res = st.stage_pins()
        elif a.stage == "verify":
            res = st.stage_verify()
        elif a.stage == "runs":
            res = st.stage_runs(a.jobs, a.only)
        elif a.stage == "p1":
            res = st.stage_p1(a.parts, a.jobs)
        elif a.stage == "p1-merge":
            res = st.stage_p1_merge()
        else:
            verdict, _ = st.stage_evaluate()
            res = {"trial_verdict": verdict}
    except (StageFailed, PV.ProvenanceError) as e:
        print(f"🚫 {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(json.dumps(res, sort_keys=True, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
