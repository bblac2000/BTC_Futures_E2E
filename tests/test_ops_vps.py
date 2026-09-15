"""layer 8 VPS 운영 — 저장소 표(allowlist) · Drive 복사 · Drive 검증 prune · health 경보 · systemd 템플릿.

🔴 prune은 삭제 코드다(Codex 검토 대상): 테스트가 안전장치를 하나씩 잠근다. rclone은 가짜 러너로 대체한다(원격 접근 없음).
"""
from __future__ import annotations

import configparser
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from data import manifest
from ops import data_stores as DS
from ops import drive_sync as SY
from ops import health as HE
from ops import prune as PR

REMOTE = "gdrive:BTC_Futures_E2E"
TODAY = dt.date(2026, 10, 30)
UNITS = Path(__file__).resolve().parent.parent / "ops" / "systemd"


# ── 저장소 표 ────────────────────────────────────────────────────────────────
def test_only_shard_stores_are_prunable_and_sqlite_never(tmp_path):
    specs = DS.stores(tmp_path)
    assert [s.id for s in DS.prunable(specs)] == ["raw_live"]
    assert {s.id: s.deletion_mode for s in specs if s.kind == "sqlite"} == {"bot_db": "never", "manifest": "never"}
    bad = (DS.StoreSpec("db", tmp_path / "x.sqlite", "db/x", "sqlite", "drive_verified_prune"),)
    with pytest.raises(DS.StoreConfigError):
        DS.prunable(bad)
    assert all(str(s.local_path).startswith(str(tmp_path.resolve())) for s in specs)


@pytest.mark.parametrize("value", ["", "gdrive", "gdrive:", "gdrive:/", "gdrive:E2E_Hybrid_Bot",
                                   "gdrive:backup/e2e_hybrid_bot/x"])
def test_remote_root_must_be_this_bots_own_folder(value):
    with pytest.raises(DS.StoreConfigError):
        DS.remote_root({DS.REMOTE_ENV: value})
    assert DS.remote_root({DS.REMOTE_ENV: "gdrive:BTC_Futures_E2E/"}) == "gdrive:BTC_Futures_E2E"


# ── Drive 복사 ───────────────────────────────────────────────────────────────
class Runner:
    def __init__(self, handler=None):
        self.cmds: list[list[str]] = []
        self.handler = handler or (lambda cmd: (0, "", ""))

    def __call__(self, cmd, **kw):
        self.cmds.append(list(cmd))
        rc, out, err = self.handler(cmd)
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def _var(tmp_path: Path) -> Path:
    var = tmp_path / "var"
    (var / "raw" / "live" / "BTCUSDT" / "2026-09-01" / "markprice").mkdir(parents=True)
    con = sqlite3.connect(var / "bot.sqlite")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(x)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    return var


def test_sync_copies_only_never_deletes_remote_and_writes_the_marker_only_on_success(tmp_path):
    var = _var(tmp_path)
    r = Runner()
    code, _ = SY.sync(var, REMOTE, runner=r)
    assert code == 0 and (var / "markers" / "LAST_SYNC.txt").exists()
    verbs = {c[1] for c in r.cmds}
    assert verbs <= {"copy", "copyto"}, "원격 쓰기는 copy/copyto뿐 — sync·delete·purge 없음"
    shard = next(c for c in r.cmds if c[1] == "copy")
    assert shard[3] == f"{REMOTE}/raw/live/BTCUSDT" and "--checksum" in shard and shard[shard.index("--min-age") + 1] == "90s"
    db = next(c for c in r.cmds if c[1] == "copyto")
    assert db[2].endswith("backup/bot.sqlite") and db[3] == f"{REMOTE}/db/bot.sqlite"
    assert sqlite3.connect(var / "backup" / "bot.sqlite").execute("SELECT x FROM t").fetchall() == [(1,)]
    (var / "markers" / "LAST_SYNC.txt").unlink()
    code, lines = SY.sync(var, REMOTE, runner=Runner(lambda cmd: (1, "", "quota") if cmd[1] == "copy" else (0, "", "")))
    assert code == 1 and not (var / "markers" / "LAST_SYNC.txt").exists() and any("quota" in ln for ln in lines)


def test_sync_refuses_to_run_without_this_bots_remote(tmp_path, capsys):
    assert SY.main(["--var-dir", str(tmp_path)], env={DS.REMOTE_ENV: "gdrive:E2E_Hybrid_Bot"}) == 2
    assert PR.main(["--var-dir", str(tmp_path)], env={}) == 2


# ── prune (삭제) ─────────────────────────────────────────────────────────────
def _shards(var: Path, day: str, n: int = 3) -> list[Path]:
    out = []
    for kind in ("markprice", "kline1m_update"):
        d = var / "raw" / "live" / "BTCUSDT" / day / kind
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            p = d / f"00000{i}_000.parquet"
            p.write_bytes(b"x" * (10 + i))
            out.append(p)
    return out


def _check_all_equal(var: Path, *, override: dict[str, str] | None = None, lsf_ok=True):
    def handler(cmd):
        if cmd[1] == "check":
            src = Path(cmd[2])
            lines = []
            for f in sorted(src.rglob("*")):
                if f.is_file():
                    rel = str(f.relative_to(src))
                    lines.append(f"{(override or {}).get(rel, '=')} {rel}")
            return (0, "\n".join(lines), "")
        if cmd[1] == "lsf":
            day = cmd[-1].rsplit("/", 1)[1]
            src = var / "raw" / "live" / "BTCUSDT" / day
            return (0 if lsf_ok else 3, "\n".join(f"md5{f.stat().st_size};{f.relative_to(src)}"
                                                  for f in sorted(src.rglob("*.parquet"))), "")
        raise AssertionError(cmd)
    return Runner(handler)


class Ledger:
    def __init__(self, short_by: int = 0):
        self.calls, self.short_by = [], short_by

    def __call__(self, paths, note, sizes=None, md5s=None):
        self.calls.append((list(paths), note, dict(sizes or {}), dict(md5s or {})))
        return len(paths) - self.short_by


@pytest.fixture(autouse=True)
def _manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(manifest, "MANIFEST_DB", tmp_path / "manifest.sqlite")


def test_dry_run_deletes_nothing(tmp_path):
    var = _var(tmp_path)
    files = _shards(var, "2026-09-01")
    code, results = PR.run_prune(var, REMOTE, apply=False, max_days=7, today=TODAY, runner=_check_all_equal(var),
                                 mark_pruned=Ledger())
    assert code == 0 and all(f.exists() for f in files) and results[0]["deleted"] == len(files)
    assert not (var / "markers" / "LAST_PRUNE.txt").exists()


def test_apply_deletes_only_checksum_equal_old_parquet_records_md5_and_marks_healthy(tmp_path):
    var = _var(tmp_path)
    old = _shards(var, "2026-09-01")
    recent = _shards(var, "2026-10-15")                                   # 30일 창 안
    (var / "raw" / "live" / "BTCUSDT" / "2026-09-01" / "markprice" / "notes.txt").write_text("keep")
    ledger = Ledger()
    r = _check_all_equal(var)
    code, results = PR.run_prune(var, REMOTE, apply=True, max_days=7, today=TODAY, runner=r, mark_pruned=ledger)
    assert code == 0 and not any(f.exists() for f in old) and all(f.exists() for f in recent)
    assert (var / "raw" / "live" / "BTCUSDT" / "2026-09-01" / "markprice" / "notes.txt").exists(), ".parquet만 지운다"
    (paths, note, sizes, md5s) = ledger.calls[0]
    assert len(paths) == len(old) and note.startswith("pruned_verified_checksum:")
    assert set(md5s) == {str(p) for p in old} and all(v.startswith("md5") for v in md5s.values())
    assert (var / "markers" / "LAST_PRUNE.txt").exists() and results[0]["ledger_gap"] == 0
    assert {c[1] for c in r.cmds} <= {"check", "lsf"}, "원격은 읽기만"
    assert (var / "bot.sqlite").exists()


@pytest.mark.parametrize("mark", ["-", "*", "!"])
def test_any_unverified_file_holds_back_the_whole_day(tmp_path, mark):
    var = _var(tmp_path)
    files = _shards(var, "2026-09-01")
    code, results = PR.run_prune(var, REMOTE, apply=True, max_days=7, today=TODAY,
                                 runner=_check_all_equal(var, override={"markprice/000001_000.parquet": mark}),
                                 mark_pruned=Ledger())
    assert code == 1 and all(f.exists() for f in files) and "전체 보류" in results[0]["skipped"]
    assert not (var / "markers" / "LAST_PRUNE.txt").exists(), "보류는 성공이 아니다 — 마커 갱신 안 함"


def test_rclone_error_or_ledger_gap_is_not_success(tmp_path):
    var = _var(tmp_path)
    _shards(var, "2026-09-01")
    err = Runner(lambda cmd: (2, "", "auth failed"))
    code, results = PR.run_prune(var, REMOTE, apply=True, max_days=7, today=TODAY, runner=err, mark_pruned=Ledger())
    assert code == 1 and "검증 실패" in results[0]["skipped"]
    code, results = PR.run_prune(var, REMOTE, apply=True, max_days=7, today=TODAY, runner=_check_all_equal(var),
                                 mark_pruned=Ledger(short_by=1))
    assert code == 1 and results[0]["ledger_gap"] == 1 and not (var / "markers" / "LAST_PRUNE.txt").exists()


def test_symlinked_day_or_file_is_never_followed(tmp_path):
    var = _var(tmp_path)
    outside = tmp_path / "collector_data" / "markprice"
    outside.mkdir(parents=True)
    victim = outside / "000000_000.parquet"
    victim.write_bytes(b"collector")
    (var / "raw" / "live" / "BTCUSDT" / "2026-09-02").symlink_to(outside.parent)
    d = var / "raw" / "live" / "BTCUSDT" / "2026-09-03" / "markprice"
    d.mkdir(parents=True)
    (d / "000000_000.parquet").symlink_to(victim)
    PR.run_prune(var, REMOTE, apply=True, max_days=7, today=TODAY, runner=_check_all_equal(var), mark_pruned=Ledger())
    assert victim.exists() and victim.read_bytes() == b"collector"


def test_max_days_limits_one_run(tmp_path):
    var = _var(tmp_path)
    for day in ("2026-09-01", "2026-09-02", "2026-09-03"):
        _shards(var, day, n=1)
    _, results = PR.run_prune(var, REMOTE, apply=True, max_days=2, today=TODAY, runner=_check_all_equal(var),
                              mark_pruned=Ledger())
    assert [r["day"] for r in results] == ["2026-09-01", "2026-09-02"]
    assert (var / "raw" / "live" / "BTCUSDT" / "2026-09-03").exists()


def test_prune_module_has_no_remote_write_verbs():
    src = (Path(PR.__file__)).read_text()
    for verb in ('"delete"', '"deletefile"', '"purge"', '"sync"', '"move"', '"rmdirs"', '"copy"'):
        assert verb not in src


# ── health ──────────────────────────────────────────────────────────────────
def _status(var: Path, **kw):
    body = {"mode": "paper", "entries_allowed": True, "blockers": [], "stalled": [], "db_errors": 0, "unrecorded": 0,
            "counts": {"bars": 1, "ticks": 2}, "poll_errors": 0, "last_poll_ok_ms": int(time.time() * 1000)} | kw
    (var / "run").mkdir(parents=True, exist_ok=True)
    (var / "run" / "status.json").write_text(json.dumps(body))
    (var / "markers").mkdir(parents=True, exist_ok=True)
    (var / "markers" / "LAST_SYNC.txt").write_text("ok")


def test_health_healthy_bot_has_no_problems_and_stale_status_is_detected(tmp_path):
    var = tmp_path / "var"
    _status(var)
    now = time.time()
    assert HE.problem_items(HE.gather(var, now=now) | {"disk_free_gb": 50.0}) == []
    keys = [k for k, _t, _o in HE.problem_items(HE.gather(var, now=now + 121) | {"disk_free_gb": 50.0})]
    assert keys == ["bot_stale"] and HE.STATUS_MAX_AGE_S == 120


def test_health_keys_are_fixed_codes_without_numbers_and_settled_facts_carry_a_date(tmp_path):
    var = tmp_path / "var"
    _status(var, blockers=["kill_switch:daily_loss", "stale:markprice"], stalled=["markprice"], db_errors=3,
            shutdown="stop_dirty", exit_code=1, ts_ms=123, poll_errors=4, last_poll_ok_ms=0)
    t_sync = time.time() - 4 * 3600
    os.utime(var / "markers" / "LAST_SYNC.txt", (t_sync, t_sync))
    (var / "markers" / "LAST_PRUNE.txt").write_text("old")
    t_prune = time.time() - 9 * 86400
    os.utime(var / "markers" / "LAST_PRUNE.txt", (t_prune, t_prune))
    items = HE.problem_items(HE.gather(var, now=time.time()) | {"disk_free_gb": 1.0})
    repeat = {k for k, _t, once in items if not once}
    once = {k for k, _t, o in items if o}
    assert repeat == {"entries_blocked", "feed_stalled", "db_errors", "telegram_poll", "sync_stale", "disk_low"}
    assert all(not re.search(r"\d", k) for k in repeat), "반복형 키에 숫자·날짜가 들어가면 스로틀이 깨진다"
    assert any(k.startswith("dirty_shutdown:") for k in once) and any(k.startswith("prune_stale:") for k in once)


def test_alert_throttles_recurring_sends_once_facts_once_and_keeps_state_on_send_failure(tmp_path):
    var = tmp_path / "var"
    _status(var, blockers=["paused:telegram:1"])
    state = tmp_path / "state"
    now = time.time()
    m = HE.gather(var, now=now) | {"disk_free_gb": 50.0}
    sent = []
    assert HE.alert(m, state, lambda t: {"ok": False}, now=now) == "send_failed" and not state.exists()
    assert HE.alert(m, state, lambda t: sent.append(t) or {"ok": True}, now=now) == "sent"
    assert HE.alert(m, state, lambda t: sent.append(t) or {"ok": True}, now=now + 600) == "throttled"
    m2 = HE.gather(var, now=now + 700) | {"disk_free_gb": 1.0}
    assert HE.alert(m2, state, lambda t: sent.append(t) or {"ok": True}, now=now + 700) == "sent", "키 집합이 바뀌면 즉시"
    m3 = HE.gather(var, now=now + 700 + HE.ALERT_THROTTLE_SEC + 1) | {"disk_free_gb": 1.0}
    assert HE.alert(m3, state, lambda t: {"ok": True}, now=now + 700 + HE.ALERT_THROTTLE_SEC + 1) == "sent"
    _status(var)
    t4 = time.time()                                                  # 상태 파일 나이는 실제 mtime 기준
    m4 = HE.gather(var, now=t4) | {"disk_free_gb": 50.0}
    assert HE.alert(m4, state, lambda t: {"ok": True}, now=t4) == "none" and not (state / "alert_state").exists()
    assert "paused:telegram:1" in sent[0]


# ── systemd 템플릿 ───────────────────────────────────────────────────────────
def _unit(name: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # type: ignore[assignment]
    cp.read_string((UNITS / name).read_text())
    return cp


def test_units_are_bot_user_units_with_onfailure_in_unit_and_no_inline_code():
    names = sorted(p.name for p in UNITS.iterdir())
    assert {"btcfut-bot.service", "btcfut-failed@.service", "btcfut-health-alert.timer", "btcfut-health-digest.timer",
            "btcfut-sync.timer", "btcfut-prune.timer"} <= set(names)
    for n in names:
        text = (UNITS / n).read_text()
        assert "/home/" not in text and "E2E_Hybrid_Bot" not in text.replace("E2E 수집기", ""), f"{n}: 절대경로·E2E 경로 금지"
        assert "python -c" not in text and "|| true" not in text
        cp = _unit(n)
        if n.endswith(".service"):
            assert "OnFailure" not in cp["Service"], f"{n}: OnFailure는 [Unit]에"
            execs = [ln for ln in text.splitlines() if ln.startswith("ExecStart=")]
            assert len(execs) == 1, f"{n}: oneshot ExecStart는 한 줄(E2E #128)"
            assert cp["Service"]["WorkingDirectory"] == "%h/BTC_Futures_E2E"
            if n != "btcfut-failed@.service":
                assert cp["Unit"]["OnFailure"] == "btcfut-failed@%n.service"
        else:
            assert cp["Timer"]["Persistent"] == "true" and cp["Install"]["WantedBy"] == "timers.target"
    bot = _unit("btcfut-bot.service")
    assert "--mode paper" in bot["Service"]["ExecStart"] and bot["Install"]["WantedBy"] == "default.target"
    assert bot["Service"]["Nice"] == "10" and bot["Service"]["MemoryMax"], "수집기 우선"


def test_unit_modules_exist_and_parse_their_arguments(tmp_path):
    root = Path(__file__).resolve().parent.parent
    for n in sorted(UNITS.iterdir()):
        for ln in n.read_text().splitlines():
            if ln.startswith("ExecStart="):
                m = re.search(r"-m (ops\.[a-z_]+)", ln)
                assert m and (root / (m.group(1).replace(".", "/") + ".py")).exists(), ln
    r = subprocess.run([str(root / ".venv" / "bin" / "python"), "-m", "ops.prune", "--help"], capture_output=True,
                       text=True, cwd=root, timeout=60)
    assert r.returncode == 0 and "--apply" in r.stdout
