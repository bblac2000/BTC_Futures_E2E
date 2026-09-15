"""health — `alert`(5분 타이머, 문제 있을 때만) · `digest`(하루 1회 00:30 UTC). E2E `ops/vps_health.py` 경보 구조 이식(패턴).

## 무엇을 보나 (프로세스 `active`가 아니라 **데이터 신선도** — "active인데 내부 스레드 사망"을 잡는다 · vps-ops §8)
- 상태 파일(`var/run/status.json`, 런타임 안전 틱이 1초마다 원자적으로 쓴다)의 나이 · 진입 차단 사유 · 피드 정지 ·
  DB 오류/미기록 · 텔레그램 폴 마지막 성공 · 종료 코드
- 디스크 여유 · Drive sync 마커 나이 · prune 마커 나이

## 경보 규칙 (vps-ops §7 · E2E 2026-08-16 교훈)
- **키는 고정 코드다**(문구·숫자·날짜가 아니다) — 숫자가 들어간 키는 스로틀이 안 걸리고, 날짜가 들어간 반복 키는 매일 리셋된다.
- **반복형**(지금 벌어지는 일): 같은 키 집합이면 3시간 스로틀(`ALERT_THROTTLE_SEC`), 집합이 바뀌면 즉시.
- **하루 한 번**(확정 사실: 비정상 종료·prune 정체): 키에 날짜를 넣어 **딱 한 번**.
- **발송 실패 시 상태를 갱신하지 않는다** — 다음 주기에 재시도. `sent: true`가 아니라 응답 `ok`로 판정(`notify(block=True)`).
- 텔레그램이 죽은 사실은 텔레그램으로 알릴 수 없다 — 외부 heartbeat는 VPS 배포 논의 항목(런북).

## 운영 경보 값 (게이트 아님 · 설계서 §17에 기록)
상태 파일 나이 > 레지스트리 #1 grace(120초) · sync 마커 > 3시간(시간당 타이머 3회 실패) · prune 마커 > 8일(주 1회 + 1일) ·
텔레그램 폴 마지막 성공 > 10분 · 디스크 여유 < 5 GB · 반복형 스로틀 3시간(E2E 값).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ops.delivery_counter import DELIVERY

ROOT = Path(__file__).resolve().parent.parent
STATUS_MAX_AGE_S = max(s.grace_sec for s in DELIVERY.values())     # 레지스트리 #1 grace 재사용(새 숫자 아님)
SYNC_MAX_AGE_S = 3 * 3600
PRUNE_MAX_AGE_S = 8 * 86400
TELEGRAM_POLL_MAX_AGE_S = 600
DISK_MIN_FREE_GB = 5.0
ALERT_THROTTLE_SEC = 3 * 3600

Item = tuple[str, str, bool]                                         # (고정 키, 문구, 하루 한 번)


def _age_s(path: Path, now: float) -> float | None:
    try:
        return now - path.stat().st_mtime
    except OSError:
        return None


def gather(var_dir: Path, *, now: float) -> dict[str, Any]:
    var_dir = Path(var_dir)
    m: dict[str, Any] = {"now": now, "var_dir": str(var_dir)}
    sp = var_dir / "run" / "status.json"
    m["status_age_s"] = _age_s(sp, now)
    try:
        m["status"] = json.loads(sp.read_text())
    except (OSError, ValueError):
        m["status"] = None
    m["sync_age_s"] = _age_s(var_dir / "markers" / "LAST_SYNC.txt", now)
    m["prune_age_s"] = _age_s(var_dir / "markers" / "LAST_PRUNE.txt", now)
    try:
        m["disk_free_gb"] = shutil.disk_usage(var_dir if var_dir.exists() else var_dir.parent).free / 1e9
    except OSError:
        m["disk_free_gb"] = None
    return m


def problem_items(m: dict[str, Any]) -> list[Item]:
    now = m["now"]
    today = dt.datetime.fromtimestamp(now, dt.UTC).date().isoformat()
    out: list[Item] = []
    st = m.get("status")
    age = m.get("status_age_s")
    if st is None or age is None:
        out.append(("bot_status_missing", "봇 상태 파일 없음/해석 불가 — 봇이 떠 있지 않다", False))
    else:
        if st.get("shutdown") is not None:
            code = st.get("exit_code")
            if code not in (0, None):
                out.append((f"dirty_shutdown:{st.get('ts_ms')}", f"봇 비정상 종료 코드 {code} · {st.get('shutdown_detail')}", True))
            if age > STATUS_MAX_AGE_S:
                out.append(("bot_down", f"봇 정지 상태({st.get('shutdown')}) · 상태 {age:.0f}초 전", False))
        elif age > STATUS_MAX_AGE_S:
            out.append(("bot_stale", f"봇 상태 {age:.0f}초 갱신 없음(> {STATUS_MAX_AGE_S}) — 루프 멈춤·프로세스 사망 의심", False))
        if st.get("blockers"):
            out.append(("entries_blocked", "신규 진입 금지: " + ", ".join(st["blockers"]), False))
        if st.get("stalled"):
            out.append(("feed_stalled", "피드 정지(레지스트리 #1): " + ", ".join(st["stalled"]), False))
        if st.get("db_errors") or st.get("unrecorded"):
            out.append(("db_errors", f"DB 오류 {st.get('db_errors')} · 미기록 {st.get('unrecorded')}", False))
        ok_ms = st.get("last_poll_ok_ms")
        if st.get("poll_errors") and (ok_ms is None or now - ok_ms / 1000 > TELEGRAM_POLL_MAX_AGE_S):
            out.append(("telegram_poll", f"텔레그램 폴 실패 {st.get('poll_errors')}회 · 마지막 오류 {st.get('last_poll_error')}",
                        False))
    if m.get("sync_age_s") is None or m["sync_age_s"] > SYNC_MAX_AGE_S:
        out.append(("sync_stale", f"Drive sync 성공 마커 {'없음' if m.get('sync_age_s') is None else f'{m['sync_age_s'] / 3600:.1f}시간 전'}",
                    False))
    if m.get("prune_age_s") is not None and m["prune_age_s"] > PRUNE_MAX_AGE_S:
        out.append((f"prune_stale:{today}", f"prune 성공 마커 {m['prune_age_s'] / 86400:.1f}일 전 — 검증 실패 반복이면 디스크가 찬다",
                    True))
    if m.get("disk_free_gb") is not None and m["disk_free_gb"] < DISK_MIN_FREE_GB:
        out.append(("disk_low", f"디스크 여유 {m['disk_free_gb']:.1f} GB < {DISK_MIN_FREE_GB} GB — 수집기 우선", False))
    return out


def fmt(m: dict[str, Any], texts: list[str], *, title: str) -> str:
    st = m.get("status") or {}
    lines = [title, f"모드 {st.get('mode', '-')} · 진입 {'허용' if st.get('entries_allowed') else '금지'} · "
                    f"포지션 {st.get('position') or '없음'} · 지갑 {st.get('wallet', '-')}",
             f"봉 {st.get('counts', {}).get('bars', '-')} · 틱 {st.get('counts', {}).get('ticks', '-')} · "
             f"알림 배달 {st.get('delivered', '-')}",
             f"디스크 {m.get('disk_free_gb') if m.get('disk_free_gb') is None else round(m['disk_free_gb'], 1)} GB · "
             f"sync {'-' if m.get('sync_age_s') is None else f'{m['sync_age_s'] / 3600:.1f}h 전'} · "
             f"prune {'-' if m.get('prune_age_s') is None else f'{m['prune_age_s'] / 86400:.1f}d 전'}"]
    if texts:
        lines.append("문제: " + " / ".join(texts))
    return "\n".join(lines)


def alert(m: dict[str, Any], state_dir: Path, send: Callable[[str], dict | None], *, now: float) -> str:
    """'none' · 'throttled' · 'sent' · 'send_failed' — 발송 실패는 상태를 바꾸지 않는다."""
    items = problem_items(m)
    state, state_once = state_dir / "alert_state", state_dir / "alert_once"
    if not items:
        state.unlink(missing_ok=True)
        return "none"
    once = [(k, t) for k, t, o in items if o]
    repeat = [(k, t) for k, t, o in items if not o]
    sent_once: set[str] = set()
    if state_once.exists():
        sent_once = {ln.strip() for ln in state_once.read_text().splitlines() if ln.strip()}
    fresh_once = [(k, t) for k, t in once if k not in sent_once]
    prev_sig, prev_ts = "", 0.0
    if state.exists():
        try:
            prev_sig, prev_ts_s = state.read_text().split("\n")[:2]
            prev_ts = float(prev_ts_s)
        except ValueError:
            pass
    sig = "|".join(sorted(k for k, _ in repeat))
    repeat_due = bool(repeat) and (sig != prev_sig or now - prev_ts > ALERT_THROTTLE_SEC)
    if not (fresh_once or repeat_due):
        return "throttled"
    res = send(fmt(m, [t for _k, t, _o in items], title="⚠️ BTC 봇 health")) or {}
    if not res.get("ok"):
        return "send_failed"
    state_dir.mkdir(parents=True, exist_ok=True)
    if repeat:
        state.write_text(f"{sig}\n{now}")
    if fresh_once:
        month = dt.datetime.fromtimestamp(now, dt.UTC).strftime("%Y-%m")
        keep = {k for k in sent_once | {k for k, _ in fresh_once} if month in k or ":" not in k}
        state_once.write_text("\n".join(sorted(keep)) + "\n")
    return "sent"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="봇 health 경보·일일 요약")
    ap.add_argument("mode", choices=["alert", "digest"])
    ap.add_argument("--var-dir", default=str(ROOT / "var"))
    a = ap.parse_args(argv)
    from notify.sender import notify
    var_dir = Path(a.var_dir).resolve()
    now = time.time()
    m = gather(var_dir, now=now)
    if a.mode == "digest":
        res = notify(fmt(m, [t for _k, t, _o in problem_items(m)], title="📋 BTC 봇 일일 요약"), block=True) or {}
        if not res.get("ok"):
            print(f"[health] digest 발송 실패: {res}", file=sys.stderr)
            return 1
        return 0
    out = alert(m, var_dir / "health", lambda text: notify(text, block=True), now=now)
    print(f"[health] alert {out}")
    return 1 if out == "send_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
