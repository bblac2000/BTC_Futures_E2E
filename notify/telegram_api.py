"""Bot API 전송 — `https://api.telegram.org/bot<token>/METHOD` · POST JSON · **응답 `ok` 검증**(Bot API 10.3, ops_log 2026-09-15).

- `ok=false`(HTTP 200이어도) → `TelegramApiError(error_code, description)` · 네트워크 실패 → `TelegramTransportError`
- 🔒 토큰은 URL에만 있다 — 예외 문구에서 `<token>`으로 가린다(로그·텔레그램·ops_log에 새지 않게)
- 문서 한도는 보내기 전에 검사: text 1-4096 · answer text 0-200 · callback_data 1-64 bytes
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any

API_BASE = "https://api.telegram.org"
HTTP_TIMEOUT_S = 10.0
LONG_POLL_MARGIN_S = 10.0


class TelegramApiError(RuntimeError):
    def __init__(self, method: str, error_code: int | None, description: str):
        super().__init__(f"{method}: {error_code} {description}")
        self.method, self.error_code, self.description = method, error_code, description


class TelegramTransportError(RuntimeError):
    pass


def _check_markup(markup: dict[str, Any] | None) -> None:
    if not markup:
        return
    for row in markup.get("inline_keyboard", []):
        for b in row:
            data = b.get("callback_data")
            if data is not None and not 1 <= len(str(data).encode()) <= 64:
                raise ValueError(f"callback_data는 1-64 bytes: {len(str(data).encode())}")


class TelegramApi:
    def __init__(self, token: str, *, opener: Callable[..., Any] = urllib.request.urlopen):
        if not token:
            raise ValueError("텔레그램 토큰 없음")
        self._token, self._opener = token, opener

    def _redact(self, s: str) -> str:
        return s.replace(self._token, "<token>")

    def call(self, method: str, params: dict[str, Any], *, timeout_s: float = HTTP_TIMEOUT_S) -> Any:
        req = urllib.request.Request(f"{API_BASE}/bot{self._token}/{method}", data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self._opener(req, timeout=timeout_s) as r:
                body = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode())
            except Exception as inner:  # noqa: BLE001
                raise TelegramTransportError(self._redact(f"{method}: HTTP {e.code} 본문 해석 불가")) from inner
        except Exception as e:  # noqa: BLE001 — 네트워크·JSON 실패 전부 전송 실패(토큰 가림)
            raise TelegramTransportError(self._redact(f"{method}: {type(e).__name__}: {e}")) from None
        if not isinstance(body, dict) or body.get("ok") is not True:
            b = body if isinstance(body, dict) else {}
            raise TelegramApiError(method, b.get("error_code"), self._redact(str(b.get("description", body))))
        return body.get("result")

    def get_updates(self, *, offset: int | None, timeout_s: int, allowed_updates: Sequence[str] | None = None) -> Any:
        p: dict[str, Any] = {"timeout": timeout_s}
        if offset is not None:
            p = {"offset": offset} | p
        if allowed_updates is not None:
            p["allowed_updates"] = list(allowed_updates)
        return self.call("getUpdates", p, timeout_s=timeout_s + LONG_POLL_MARGIN_S)

    def send_message(self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> Any:
        if not 1 <= len(text) <= 4096:
            raise ValueError(f"sendMessage text는 1-4096자: {len(text)}")
        _check_markup(reply_markup)
        p: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            p["reply_markup"] = reply_markup
        return self.call("sendMessage", p)

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> Any:
        p: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text is not None:
            if len(text) > 200:
                raise ValueError(f"answerCallbackQuery text는 0-200자: {len(text)}")
            p["text"] = text
        return self.call("answerCallbackQuery", p)

    def set_my_commands(self, commands: list[dict[str, str]]) -> Any:
        return self.call("setMyCommands", {"commands": commands})

    def set_chat_menu_button(self, chat_id: int | None = None, menu_button: dict[str, Any] | None = None) -> Any:
        p: dict[str, Any] = {}
        if chat_id is not None:
            p["chat_id"] = chat_id
        if menu_button is not None:
            p["menu_button"] = menu_button
        return self.call("setChatMenuButton", p)
