# ── PROVENANCE ─────────────────────────────────────────────────────────────
# Copied from: /home/cms/project/E2E_Hybrid_Bot/e2e/paper/notify.py
# Source commit: a60f4f8 (F-TGDAEMON fix, 2026-08-08; E2E HEAD f1e7d86) · copied 2026-09-15
# Local changes:
#   - ROOT computed locally (no e2e.paths); env file = <repo>/.env (never shared with E2E/BreakoutTrading)
#   - message prefix is a parameter (PREFIX, default "[BTC]") instead of "[E2E]"
#   - _post takes an injectable `opener` so tests can prove a 200 with ok:false is a failure
#   - typing annotations added (pyright clean); delivery semantics unchanged
#   - 2026-09-15: transport error text redacts the bot token before it is logged/printed (Codex L6·7 review #5)
# ───────────────────────────────────────────────────────────────────────────
"""텔레그램 send-only 발송 — **응답 검증 + 단명 프로세스 join**.

⚠️ E2E 2026-08-08 결함(F-TGDAEMON): 발송을 `daemon=True` 스레드에 맡기고 곧바로 반환했기
   때문에, **단명 프로세스**(oneshot CLI)에서는 인터프리터가 종료되며 스레드가 죽어 HTTP 요청이
   중단됐다. 증상: systemd는 `success`, 스크립트는 `sent: true`를 찍는데 **메시지는 도착하지 않음**.
   → ①`atexit`으로 미완 발송 스레드를 **join**하고 ②응답 JSON의 `ok`를 **검증**해 성공/실패를
     반환하며 ③실패는 stderr로도 남긴다.

🚫 이 모듈은 명령 수신(getUpdates·콜백)을 하지 않는다 — 그건 layer 6 `notify/` 명령 계층이다.
   (패키지명: `telegram/`은 PyPI `python-telegram-bot`의 import 이름을 가리므로 2026-09-15 `notify/`로 개명)
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "[BTC]"

logger = logging.getLogger(__name__)
_loaded = False
_pending: list[threading.Thread] = []
_results: list[dict] = []
JOIN_TIMEOUT_S = 10.0
HTTP_TIMEOUT_S = 8.0


def _load_env() -> None:
    global _loaded
    if _loaded:
        return
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    _loaded = True


def _post(token: str, chat_id: str, text: str,
          opener: Callable[..., Any] = urllib.request.urlopen) -> dict:
    """실제 발송. **응답을 파싱해 ok 여부를 확인**한다(2xx만으로 성공을 단정하지 않는다)."""
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
        with opener(req, timeout=HTTP_TIMEOUT_S) as r:
            body = json.loads(r.read().decode())
        ok = bool(body.get("ok"))
        res = {"ok": ok, "message_id": (body.get("result") or {}).get("message_id"),
               "description": body.get("description")}
    except Exception as e:
        #  urllib 예외 문구에 요청 URL(= 토큰 포함)이 들어갈 수 있다 → 기록·stderr 전에 가린다(Codex L6·7 #5)
        res = {"ok": False, "error": f"{type(e).__name__}: {e}".replace(token, "<token>") if token else f"{type(e).__name__}: {e}"}
    if res["ok"]:
        logger.info(f"텔레그램 발송 성공 message_id={res.get('message_id')}")
    else:
        logger.warning(f"텔레그램 발송 실패: {res}")
        print(f"[notify] 텔레그램 발송 실패: {res}", file=sys.stderr, flush=True)
    _results.append(res)
    return res


def _drain(timeout: float = JOIN_TIMEOUT_S) -> None:
    """미완 발송 스레드를 기다린다. **단명 프로세스가 발송을 끊고 죽는 것을 막는 장치.**"""
    for t in list(_pending):
        if t.is_alive():
            t.join(timeout)
        if t in _pending:
            _pending.remove(t)


atexit.register(_drain)


def notify(text: str, block: bool = False) -> dict | None:
    """알림 발송. `block=True`면 결과를 동기적으로 돌려준다(oneshot 스크립트 권장).

    `block=False`여도 `atexit`이 join하므로 **프로세스가 짧아도 배달된다**.
    """
    _load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    msg = f"{PREFIX} {text}"
    logger.info(f"notify: {msg.splitlines()[0]}")
    if not token or not chat_id:
        logger.warning("텔레그램 미설정(.env의 TELEGRAM_BOT_TOKEN/CHAT_ID 없음) — 발송 생략")
        print("[notify] 텔레그램 미설정 — 발송 생략", file=sys.stderr, flush=True)
        return {"ok": False, "error": "not_configured"}
    if block:
        return _post(token, chat_id, msg)
    t = threading.Thread(target=_post, args=(token, chat_id, msg), daemon=True)
    _pending.append(t)
    t.start()
    return None


def last_result() -> dict | None:
    """가장 최근 발송 결과(감사용). 배달 여부를 호출부가 확인할 수 있게 한다."""
    _drain()
    return _results[-1] if _results else None
