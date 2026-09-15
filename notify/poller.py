"""롱폴링 러너 — `getUpdates`(offset = 받은 최대 update_id + 1, 응답마다 재계산) → 봇 → 행동 실행 → tick.

- 업데이트는 update_id 순서로 처리 · 처리 중 예외가 나도 offset은 넘긴다(같은 명령이 재처리되어 두 번 청산되지 않게) ·
  예외는 `handler_errors`로 센다 · 발송 실패는 `send_errors`로 센다(러너는 계속)
- `getUpdates` 자체의 전송 실패는 호출자(layer 8)로 올린다 — 백오프는 호출자 몫, offset은 유지
- 확인·중요 알림 대기 중에는 폴링 timeout을 1초로 줄인다(30초 롱폴링이면 3초 재전송·12초 취소가 밀린다)
- 기동 시 `setup()`: `setMyCommands`(등록 명령 8개) + `setChatMenuButton(MenuButtonCommands)`
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from notify import config as K
from notify.bot import Answer, Send
from notify.commands import api_commands

logger = logging.getLogger(__name__)


class TelegramPoller:
    def __init__(self, api: Any, bot: Any, *, clock_ms: Callable[[], int], long_poll_s: int = K.LONG_POLL_TIMEOUT_S):
        self.api, self.bot, self.clock_ms, self.long_poll_s = api, bot, clock_ms, long_poll_s
        self.offset: int | None = None
        self.handler_errors = 0
        self.send_errors = 0

    def setup(self) -> None:
        self.api.set_my_commands(api_commands())
        self.api.set_chat_menu_button(menu_button={"type": "commands"})

    def execute(self, actions: list[Send | Answer]) -> None:
        for a in actions:
            try:
                if isinstance(a, Send):
                    self.api.send_message(a.chat_id, a.text, a.reply_markup)
                else:
                    self.api.answer_callback_query(a.callback_query_id, a.text)
            except Exception as e:  # noqa: BLE001 — 한 발송 실패가 나머지 행동을 막지 않는다
                self.send_errors += 1
                logger.warning("텔레그램 행동 실패 %s: %s", type(a).__name__, e)

    def poll_once(self) -> None:
        waiting = getattr(self.bot, "pending", None) is not None or bool(getattr(self.bot, "alerts", None))
        timeout = K.FAST_POLL_TIMEOUT_S if waiting else self.long_poll_s   # 대기 중 롱폴링이면 3초 재전송이 늦는다
        updates = self.api.get_updates(offset=self.offset, timeout_s=timeout,
                                       allowed_updates=list(K.ALLOWED_UPDATES))
        for u in sorted((u for u in updates or [] if isinstance(u, dict) and isinstance(u.get("update_id"), int)),
                        key=lambda u: u["update_id"]):
            self.offset = max(self.offset or 0, u["update_id"] + 1)
            try:
                actions = self.bot.on_update(u, self.clock_ms())
            except Exception as e:  # noqa: BLE001 — 재처리하지 않는다(offset은 이미 넘김)
                self.handler_errors += 1
                logger.error("업데이트 %s 처리 실패: %s", u["update_id"], e)
                continue
            self.execute(actions)
        self.execute(self.bot.on_tick(self.clock_ms()))
