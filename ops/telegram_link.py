"""텔레그램 네트워크 스레드 두 개 — 폴(`getUpdates` → inbox) · 발송(outbox → sendMessage/answerCallbackQuery).

- 🔒 두 스레드는 엔진·게이트·`CommandBot` 상태를 **바꾸지 않는다**. 봇 처리는 런타임 루프 스레드의 `safety_tick`이 한다
  (`ops.runtime` 스레드 소유권). 폴 스레드가 읽는 것은 `fast()` 불리언 하나(확인·알림 대기 여부 — 오래된 값이어도
  폴링 간격만 달라진다).
- 폴 실패(전송·API 오류 · 409 다른 getUpdates 소비자 포함)는 백오프(1·2·5·10·30·60초) 후 재시도하고 세며, 마지막 오류
  문구(토큰은 `TelegramApi`가 이미 가림)를 `stats`에 둔다 → 상태 파일 → health 경보. 텔레그램이 죽은 사실은 텔레그램으로
  알릴 수 없다(E2E 2026-08-16) — health는 상태 파일을 본다.
- 발송 실패는 `TelegramPoller.execute`가 세고 넘어간다(다른 행동을 막지 않는다) · 종료 시 남은 발송을 제한 시간 안에 비운다.
"""
from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any

BACKOFF_S = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)


class TelegramLink:
    def __init__(self, poller: Any, inbox: queue.SimpleQueue, outbox: queue.SimpleQueue, *, fast: Callable[[], bool],
                 sleep: Callable[[float], None] = time.sleep, backoff_s: tuple[float, ...] = BACKOFF_S):
        self.poller, self.inbox, self.outbox, self.fast = poller, inbox, outbox, fast
        self.sleep, self.backoff_s = sleep, backoff_s
        self._stop = threading.Event()
        self.poll_errors = 0
        self.last_poll_error: str | None = None
        self.last_poll_ok_ms: int | None = None
        self.sent = 0
        self.delivered_message_ids: list[int] = []            # sendMessage 응답 ok=true의 message_id — "보냈다"가 아니라 배달 증거
        self._poll = threading.Thread(target=self._poll_loop, name="tg-poll", daemon=True)
        self._send = threading.Thread(target=self._send_loop, name="tg-send", daemon=True)

    def start(self) -> None:
        self._poll.start()
        self._send.start()

    def _poll_loop(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                for u in self.poller.fetch(fast=self.fast()):
                    self.inbox.put(u)
                self.last_poll_ok_ms = int(time.time() * 1000)
                attempt = 0
            except Exception as e:  # noqa: BLE001 — 폴 스레드는 죽지 않는다(세고 백오프)
                self.poll_errors += 1
                self.last_poll_error = f"{type(e).__name__}: {e}"
                self.sleep(self.backoff_s[min(attempt, len(self.backoff_s) - 1)])
                attempt += 1

    def _send_loop(self) -> None:
        while True:
            try:
                a = self.outbox.get(timeout=0.2)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            for r in self.poller.execute([a]) or []:
                if isinstance(r, dict) and isinstance(r.get("message_id"), int):
                    self.delivered_message_ids.append(r["message_id"])
            self.sent += 1

    def stop(self, *, flush_timeout_s: float = 10.0) -> None:
        """폴을 멈추고 남은 발송을 비운다(롱폴링 중인 폴 스레드는 daemon이라 기다리지 않는다)."""
        deadline = time.monotonic() + flush_timeout_s
        while not self.outbox.empty() and time.monotonic() < deadline:
            time.sleep(0.05)
        self._stop.set()
        self._send.join(timeout=max(0.0, deadline - time.monotonic()) + 1.0)

    def stats(self) -> dict[str, Any]:
        return {"poll_errors": self.poll_errors, "last_poll_error": self.last_poll_error,
                "last_poll_ok_ms": self.last_poll_ok_ms, "sent": self.sent,
                "delivered": len(self.delivered_message_ids), "last_message_id": (self.delivered_message_ids or [None])[-1],
                "send_errors": getattr(self.poller, "send_errors", None),
                "handler_errors": getattr(self.poller, "handler_errors", None)}
