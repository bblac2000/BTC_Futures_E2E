"""layer 6 전송 — Bot API 호출(`ok` 검증 · 토큰 비노출) + 롱폴링 러너(offset 재계산 · 명령 메뉴 등록).

네트워크 없음: `opener`를 주입한다(notify/sender.py와 같은 방식).
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from notify import commands as C
from notify import config as K
from notify.bot import Answer, Send
from notify.poller import TelegramPoller
from notify.telegram_api import TelegramApi, TelegramApiError, TelegramTransportError

TOKEN = "123456:SECRET-token-value"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):  # type: ignore[override]
        return False


class Opener:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests: list[tuple[str, dict, float]] = []

    def __call__(self, req, timeout):
        self.requests.append((req.full_url, json.loads(req.data.decode()), timeout))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return Resp(json.dumps(r).encode())


def test_calls_post_json_to_the_method_url_and_return_result():
    op = Opener([{"ok": True, "result": {"message_id": 5}}])
    api = TelegramApi(TOKEN, opener=op)
    assert api.send_message(111, "안녕", reply_markup={"remove_keyboard": True}) == {"message_id": 5}
    url, body, _ = op.requests[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert body == {"chat_id": 111, "text": "안녕", "reply_markup": {"remove_keyboard": True}}


def test_ok_false_is_an_error_even_with_http_200_and_the_token_never_appears():
    op = Opener([{"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}])
    with pytest.raises(TelegramApiError) as e:
        TelegramApi(TOKEN, opener=op).send_message(1, "x")
    assert e.value.error_code == 400 and "chat not found" in str(e.value) and "SECRET" not in str(e.value)


def test_http_error_body_is_parsed_and_transport_errors_are_redacted():
    body = io.BytesIO(json.dumps({"ok": False, "error_code": 409, "description": "Conflict: webhook is active"}).encode())
    err = urllib.error.HTTPError(f"https://api.telegram.org/bot{TOKEN}/getUpdates", 409, "Conflict", {}, body)  # type: ignore[arg-type]
    with pytest.raises(TelegramApiError) as e:
        TelegramApi(TOKEN, opener=Opener([err])).get_updates(offset=None, timeout_s=0)
    assert e.value.error_code == 409 and "SECRET" not in str(e.value)
    with pytest.raises(TelegramTransportError) as t:
        TelegramApi(TOKEN, opener=Opener([OSError(f"connect to api.telegram.org/bot{TOKEN} failed")])).send_message(1, "x")
    assert "SECRET" not in str(t.value) and "<token>" in str(t.value)


@pytest.mark.parametrize("call", [
    lambda api: api.send_message(1, ""),
    lambda api: api.send_message(1, "x" * 4097),
    lambda api: api.answer_callback_query("q", "x" * 201),
    lambda api: api.send_message(1, "x", reply_markup={"inline_keyboard": [[{"text": "t", "callback_data": "x" * 65}]]}),
])
def test_documented_limits_are_checked_before_sending(call):
    op = Opener([])
    with pytest.raises(ValueError):
        call(TelegramApi(TOKEN, opener=op))
    assert op.requests == []


def test_get_updates_long_poll_http_timeout_exceeds_the_poll_timeout():
    op = Opener([{"ok": True, "result": []}])
    TelegramApi(TOKEN, opener=op).get_updates(offset=42, timeout_s=30, allowed_updates=["message", "callback_query"])
    _, body, timeout = op.requests[0]
    assert body == {"offset": 42, "timeout": 30, "allowed_updates": ["message", "callback_query"]} and timeout > 30


# ── 러너 ────────────────────────────────────────────────────────────────────
class FakeApi:
    def __init__(self, batches):
        self.batches = list(batches)
        self.calls: list[tuple] = []

    def get_updates(self, *, offset, timeout_s, allowed_updates=None):
        self.calls.append(("get_updates", offset, timeout_s, tuple(allowed_updates or ())))
        r = self.batches.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def send_message(self, chat_id, text, reply_markup=None):
        self.calls.append(("send", chat_id, text))
        if text == "boom":
            raise TelegramTransportError("x")
        return {"message_id": 1}

    def answer_callback_query(self, qid, text=None):
        self.calls.append(("answer", qid, text))
        return True

    def set_my_commands(self, commands):
        self.calls.append(("set_my_commands", tuple(c["command"] for c in commands)))
        return True

    def set_chat_menu_button(self, chat_id=None, menu_button=None):
        self.calls.append(("set_chat_menu_button", chat_id, menu_button))
        return True


class FakeBot:
    def __init__(self, fail_on=None):
        self.seen: list[int] = []
        self.fail_on = fail_on
        self.ticks = 0

    def on_update(self, update, now_ms):
        self.seen.append(update["update_id"])
        if update["update_id"] == self.fail_on:
            raise RuntimeError("handler bug")
        return [Send(1, f"u{update['update_id']}"), Answer("q", "ok")]

    def on_tick(self, now_ms):
        self.ticks += 1
        return [Send(1, "boom")] if self.ticks == 1 else []


def test_poll_processes_updates_in_order_recomputes_offset_and_never_reprocesses_a_failed_one():
    api = FakeApi([[{"update_id": 8}, {"update_id": 7}, {"update_id": 9}], []])
    b = FakeBot(fail_on=8)
    p = TelegramPoller(api, b, clock_ms=lambda: 0, long_poll_s=30)
    p.poll_once()
    assert b.seen == [7, 8, 9] and p.offset == 10 and p.handler_errors == 1
    assert p.send_errors == 1, "tick 발송 실패는 세고 계속"
    p.poll_once()
    gets = [c for c in api.calls if c[0] == "get_updates"]
    assert gets == [("get_updates", None, 30, ("message", "callback_query")),
                    ("get_updates", 10, 30, ("message", "callback_query"))]


def test_setup_registers_commands_and_the_commands_menu_button():
    api = FakeApi([])
    TelegramPoller(api, FakeBot(), clock_ms=lambda: 0).setup()
    assert api.calls == [("set_my_commands", tuple(c.command for c in C.BOT_COMMANDS)),
                         ("set_chat_menu_button", None, {"type": "commands"})]


def test_transport_failure_of_get_updates_propagates_for_backoff_and_keeps_offset():
    api = FakeApi([[{"update_id": 3}], TelegramTransportError("down")])
    p = TelegramPoller(api, FakeBot(), clock_ms=lambda: 0)
    p.poll_once()
    with pytest.raises(TelegramTransportError):
        p.poll_once()
    assert p.offset == 4


def test_poll_timeout_shortens_while_a_confirmation_is_pending_so_3s_resends_are_on_time():
    """롱폴링 30초 동안 tick이 안 돌면 3초 재전송·12초 취소가 늦어진다 → 대기 중엔 1초 폴링."""
    from notify.bot import CommandBot
    from tests.test_notify_bot import T0, FakeController, msg

    api = FakeApi([[msg("/close", uid=1)], [], []])
    clock = {"t": T0 + 6000}
    b = CommandBot(FakeController(), owner_ids=frozenset({111}), started_ms=T0)
    p = TelegramPoller(api, b, clock_ms=lambda: clock["t"], long_poll_s=30)
    p.poll_once()
    assert b.pending is not None
    p.poll_once()
    b.pending = None
    p.poll_once()
    timeouts = [c[2] for c in api.calls if c[0] == "get_updates"]
    assert timeouts == [30, K.FAST_POLL_TIMEOUT_S, 30] and K.FAST_POLL_TIMEOUT_S <= 1
