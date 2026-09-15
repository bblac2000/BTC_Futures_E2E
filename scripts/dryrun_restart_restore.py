"""페이퍼 드라이런 — 재기동 복원(사용자 지시 2026-09-16): 가짜 포지션을 연 채 **SIGKILL** → 재기동 → 복원·진입 재허용 확인.

사용:  uv run python -m scripts.dryrun_restart_restore --var-dir var/dryrun-restore-YYYYMMDD [--run2-s 300]

- 🔒 **PAPER 전용**. 운영 러너(`ops.run_bot.run`)를 그대로 부르고, 이 파일은 `feed_factory`로 실제 피드(`MarketFeed`)를 감싸
  ① 1차 실행에서 진입 게이트가 열린 첫 mark에 **진입 의도 1건**을 `BotRuntime.submit_entry`로 낸다(게이트 우회 없음)
  ② 2차 실행 끝 무렵 `/close`와 같은 경로(`close_all`)로 청산해 복원 포지션의 close가 같은 root에 붙는지 본다.
  systemd 유닛은 이 파일을 부르지 않는다(운영 경로에 진입 주입 코드가 없다).
- 1차 실행이 포지션을 연 뒤 부모가 자식 프로세스에 **SIGKILL**(정지 절차 없음 → 종료 스냅샷 없음 · shard 기록기 `stop` 없음).
- 거래소 쓰기 없음: 러너의 PAPER 경로(`ReadOnlyClient` · `PaperSender`).
- 🔒 바이낸스 키는 **`--use-binance-key`를 명시할 때만** 자식에게 넘긴다(기본은 키를 지운다 → 러너가 스냅샷 fallback +
  `rules_from_snapshot` 차단 — 이 경우 1차 실행은 진입하지 못하고 그 사실을 보고한다). 키를 넘기면 러너가 읽기 전용 권한을 먼저 실측한다.
- 출력은 요약 JSON(키·토큰 값 없음).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exchange.gate import Mode  # noqa: E402
from exchange.orders import Direction  # noqa: E402
from ops import run_bot as RB  # noqa: E402
from paper.engine import EntryIntent  # noqa: E402
from sizing.config import RegimeSizing  # noqa: E402

#  드라이런 전용 진입 의도 — 전략이 아니다(성과 집계 대상 아님). SL 0.5%는 50–100x에서 #5 게이트를 통과하는 거리.
DRYRUN_REGIME = RegimeSizing("dryrun_restart_restore", Decimal("0.01"), 50, 100)
DRYRUN_SL_FRACTION = Decimal("0.005")


def injecting_factory(*, inject: bool, close_after_s: float | None):
    def factory(counter, rt, recorder):
        if rt.mode is not Mode.PAPER:
            raise SystemExit("드라이런 하네스는 PAPER 전용")
        rt.alert(f"🧪 DRY RUN(재기동 복원 하네스) — {'1차: 진입 1건 주입 후 SIGKILL 예정' if inject else '2차: 복원 확인'}")
        if inject:
            orig = rt.on_mark
            state = {"done": False}

            def on_mark(t):
                orig(t)
                if state["done"] or rt.engine.position is not None or rt.engine.pending is not None or rt.entry_blockers():
                    return
                state["done"] = True
                rt.submit_entry(EntryIntent(Direction.LONG, t.mark * (1 - DRYRUN_SL_FRACTION), None, DRYRUN_REGIME,
                                            decided_ms=t.ts_ms, decision_mark=t.mark))
            rt.on_mark = on_mark
        if close_after_s is not None:
            def close() -> None:
                rt.alert(f"🧪 DRY RUN 청산: {rt.close_all('dryrun:harness')}")
            asyncio.get_running_loop().call_later(close_after_s, close)
        return RB._default_feed(counter, rt, recorder)
    return factory


def child(a: argparse.Namespace) -> int:
    var = Path(a.var_dir).resolve()
    cfg = RB.parse_args(["--mode", "paper", "--var-dir", str(var), "--db", str(var / "bot.sqlite"), "--backfill-minutes", "30"]
                        + (["--duration-s", str(a.duration_s)] if a.duration_s else []))
    env = RB.load_env_file(ROOT / ".env") | dict(os.environ)
    if not a.use_binance_key:
        env = {k: v for k, v in env.items() if k not in (RB.KEY_ENV, RB.SECRET_ENV)}
    factory = injecting_factory(inject=a.child == "run1", close_after_s=a.close_after_s)
    return asyncio.run(RB.run(cfg, env=env, feed_factory=factory))


def _status(var: Path) -> dict[str, Any] | None:
    try:
        return json.loads((var / "run" / "status.json").read_text())
    except (OSError, ValueError):
        return None


def _db_summary(var: Path) -> dict[str, Any]:
    con = sqlite3.connect(var / "bot.sqlite")
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    out = {
        "positions": q("SELECT id, ts_ms, event, position_id, direction, qty, entry_price, leverage, reason FROM positions ORDER BY id"),
        "orders": q("SELECT id, intent, side, qty, price, reduce_only, exit_reason FROM orders ORDER BY id"),
        "engine_events": q("SELECT kind, count(*) FROM engine_events GROUP BY kind ORDER BY kind"),
        "rules_source": q("SELECT DISTINCT source FROM runtime_rules"),
        "snapshots_with_position": q("SELECT count(*) FROM account_snapshots WHERE source='engine' "
                                     "AND json_extract(raw_json,'$.position') IS NOT NULL"),
        "restore_ops": q("SELECT kind, detail FROM engine_events WHERE kind IN ('RestartRestore','RestartRestoreMismatch')"),
    }
    con.close()
    return out


def parent(a: argparse.Namespace) -> int:
    var = Path(a.var_dir).resolve()
    var.mkdir(parents=True, exist_ok=True)
    me = [sys.executable, "-m", "scripts.dryrun_restart_restore", "--var-dir", str(var)] + \
        (["--use-binance-key"] if a.use_binance_key else [])
    report_key = "binance key passed to runner (read-only check first)" if a.use_binance_key else "no binance key (fallback)"
    report: dict[str, Any] = {"var_dir": str(var), "rules_key": report_key}
    p1 = subprocess.Popen(me + ["--child", "run1"], cwd=ROOT)
    t0 = time.time()
    opened_at = None
    while time.time() - t0 < a.run1_max_s:
        time.sleep(1)
        if p1.poll() is not None:
            report["run1"] = {"exited_early": p1.returncode, "status": _status(var)}
            print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
            return 1
        st = _status(var)
        if st and st.get("position") and opened_at is None:
            opened_at = time.time()
        if opened_at is not None and time.time() - opened_at >= a.hold_s:
            break
    if opened_at is None:
        p1.send_signal(signal.SIGTERM)
        p1.wait(60)
        report["run1"] = {"no_position_within_s": a.run1_max_s, "status": _status(var)}
        print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
        return 1
    before = _status(var)
    os.kill(p1.pid, signal.SIGKILL)
    p1.wait(30)
    report["run1"] = {"killed": "SIGKILL", "returncode": p1.returncode, "killed_at_utc": time.strftime("%H:%M:%SZ", time.gmtime()),
                      "status_before_kill": {k: before.get(k) for k in ("position", "blockers", "wallet", "counts")} if before else None,
                      "db_after_kill": _db_summary(var)}
    time.sleep(a.gap_s)
    p2 = subprocess.Popen(me + ["--child", "run2", "--duration-s", str(a.run2_s), "--close-after-s", str(a.run2_s - 60)], cwd=ROOT)
    restored_view = None
    t1 = time.time()
    while p2.poll() is None:
        time.sleep(1)
        st = _status(var)
        if st and st.get("ts_ms", 0) / 1000 > t1 + 90 and restored_view is None:
            restored_view = {k: st.get(k) for k in ("position", "blockers", "entries_allowed", "stalled", "rules", "wallet")}
    final = _status(var) or {}
    report["run2"] = {"returncode": p2.returncode, "view_90s_after_start": restored_view,
                      "final": {k: final.get(k) for k in ("position", "blockers", "entries_allowed", "shutdown", "exit_code",
                                                          "sent", "delivered", "poll_errors", "send_errors", "db_errors",
                                                          "counts", "rules")},
                      "db": _db_summary(var)}
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return 0 if p2.returncode == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PAPER 재기동 복원 드라이런(SIGKILL)")
    ap.add_argument("--var-dir", required=True)
    ap.add_argument("--child", choices=["run1", "run2"])
    ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--close-after-s", type=float, default=None)
    ap.add_argument("--run1-max-s", type=float, default=240)
    ap.add_argument("--hold-s", type=float, default=75, help="포지션이 열린 뒤 SIGKILL까지(봉 스냅샷 1개 이상)")
    ap.add_argument("--gap-s", type=float, default=5)
    ap.add_argument("--run2-s", type=float, default=300)
    ap.add_argument("--use-binance-key", action="store_true", help=".env의 읽기 전용 키를 러너에 넘긴다(사용자 확인 후에만)")
    a = ap.parse_args(argv)
    return child(a) if a.child else parent(a)


if __name__ == "__main__":
    raise SystemExit(main())
