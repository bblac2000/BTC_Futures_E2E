"""layer 6 텔레그램 명령 — 사용자 확정(open-decisions #9, 2026-09-12) · Bot API 10.3 렌더링 확인(ops_log 2026-09-15).

- 주인 ID 화이트리스트(env) · 개인 채팅만 · 기동 전 메시지(재시작 재생) 무시
- `/stop`·`/close`(텍스트 '중지'·'청산'·'stop' 포함): 포지션·미실현손익과 함께 [예/아니오] → 3초 간격 3회 재전송 →
  그래도 무응답이면 **취소 + "청산 안 됨"** · 콜백 토큰 60초 만료 · 모든 콜백에 answerCallbackQuery
- `/pause` = 신규 진입 중지(포지션 유지) · `/start` = 재개(킬스위치 해제는 사람만) · `/status` `/position` `/profit` `/help`
- 명령 이름은 1-32자 소문자·숫자·밑줄(BotCommand) → 한글 별칭은 텍스트/답장 키보드 · callback_data ≤ 64 bytes
"""
from __future__ import annotations

import re

import pytest

from notify import commands as C
from notify import config as K
from notify.bot import Answer, CommandBot, Send

OWNER = 111
STRANGER = 999
T0 = 1_789_430_400_000


class FakeController:
    def __init__(self, position=True, fail_close=False):
        self.calls: list[tuple[str, str]] = []
        self.position = position
        self.fail_close = fail_close

    def status_text(self):
        return "상태: 진입 허용"

    def position_text(self):
        return "LONG 0.010 @ 60000.0 · mark 60100.0 · uPnL +1.00 USDT" if self.position else "포지션 없음"

    def profit_text(self):
        return "누적 순손익 +3.20 USDT"

    def has_position(self):
        return self.position

    def pause_entries(self, actor):
        self.calls.append(("pause", actor))
        return "신규 진입 중지"

    def resume(self, actor):
        self.calls.append(("resume", actor))
        return "재개"

    def close_all(self, actor):
        self.calls.append(("close_all", actor))
        if self.fail_close:
            raise RuntimeError("OrderOutcomeUnknown")
        self.position = False
        return "청산 완료 0.010"


def msg(text, *, user=OWNER, chat_type="private", date_s=T0 // 1000 + 5, uid=1):
    return {"update_id": uid, "message": {"message_id": 10, "date": date_s, "text": text,
                                          "from": {"id": user, "is_bot": False},
                                          "chat": {"id": user, "type": chat_type}}}


def cb(data, *, user=OWNER, qid="q1", uid=2):
    return {"update_id": uid, "callback_query": {"id": qid, "from": {"id": user, "is_bot": False}, "data": data,
                                                 "chat_instance": "x", "message": {"message_id": 11, "chat": {"id": user}}}}


def bot(ctrl=None, **kw):
    nonces = iter(f"{i:016x}" for i in range(1, 100))
    return CommandBot(ctrl or FakeController(), owner_ids=frozenset({OWNER}), started_ms=T0,
                      nonce=lambda: next(nonces), **kw)


def sends(actions):
    return [a for a in actions if isinstance(a, Send)]


def markup(action: Send) -> dict:
    assert action.reply_markup is not None
    return action.reply_markup


def confirm_data(action: Send, answer: str) -> str:
    buttons = markup(action)["inline_keyboard"][0]
    return next(b["callback_data"] for b in buttons if b["callback_data"].endswith(":" + answer))


# ── 문서 제약 · 파싱 ─────────────────────────────────────────────────────────
def test_registered_commands_satisfy_the_bot_api_botcommand_constraints():
    assert {c.command for c in C.BOT_COMMANDS} == {"start", "stop", "pause", "status", "position", "close", "profit", "help"}
    for c in C.BOT_COMMANDS:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", c.command) and 1 <= len(c.description) <= 256
    assert len(C.BOT_COMMANDS) <= 100


@pytest.mark.parametrize("text, cmd", [
    ("/stop", C.Command.STOP), ("/STOP", C.Command.STOP), ("/stop@btc_e2e_bot", C.Command.STOP), ("  stop ", C.Command.STOP),
    ("중지", C.Command.STOP), ("청산", C.Command.CLOSE), ("/close", C.Command.CLOSE), ("시작", C.Command.START),
    ("일시정지", C.Command.PAUSE), ("상태", C.Command.STATUS), ("포지션", C.Command.POSITION), ("수익", C.Command.PROFIT),
    ("도움말", C.Command.HELP), ("/help", C.Command.HELP),
])
def test_commands_and_korean_aliases_parse(text, cmd):
    assert C.parse_command(text, bot_username="btc_e2e_bot") is cmd


@pytest.mark.parametrize("text", ["", "hello", "/stop@other_bot", "중지해", "/stopp", None])
def test_non_commands_and_other_bots_commands_do_not_parse(text):
    assert C.parse_command(text, bot_username="btc_e2e_bot") is None


def test_reply_keyboard_buttons_are_all_aliases():
    labels = [b for row in C.reply_keyboard()["keyboard"] for b in row]
    assert labels and all(C.parse_command(t, bot_username="x") is not None for t in labels)
    assert C.reply_keyboard()["is_persistent"] is True and len(C.reply_keyboard()["input_field_placeholder"]) <= 64


def test_confirmation_timing_is_the_user_decided_values():
    """open-decisions #9(2026-09-12): 3초 간격 3회 재전송 · 무응답 취소 · 콜백 만료 60초."""
    assert (K.CONFIRM_RESEND_INTERVAL_MS, K.CONFIRM_RESENDS, K.CALLBACK_TTL_MS) == (3000, 3, 60_000)


def test_owner_ids_come_from_env_and_empty_is_refused():
    assert K.owner_ids_from_env({"TELEGRAM_OWNER_IDS": "111, 222"}) == frozenset({111, 222})
    for bad in ({}, {"TELEGRAM_OWNER_IDS": ""}, {"TELEGRAM_OWNER_IDS": "abc"}):
        with pytest.raises(ValueError):
            K.owner_ids_from_env(bad)


# ── 권한 · 재생 ──────────────────────────────────────────────────────────────
def test_strangers_groups_and_pre_start_messages_are_ignored_without_side_effects():
    ctrl = FakeController()
    b = bot(ctrl)
    assert b.on_update(msg("/stop", user=STRANGER), T0 + 6000) == []
    assert b.on_update(msg("/stop", chat_type="group"), T0 + 6000) == []
    assert b.on_update(msg("/pause", date_s=T0 // 1000 - 1), T0 + 6000) == []            # 기동 전(재시작 재생)
    assert ctrl.calls == [] and b.pending is None
    assert b.stats == {"ignored_non_owner": 1, "ignored_non_private": 1, "ignored_stale": 1}


def test_stranger_callback_is_answered_but_never_executes():
    ctrl = FakeController()
    b = bot(ctrl)
    (s,) = sends(b.on_update(msg("/close"), T0 + 6000))
    acts = b.on_update(cb(confirm_data(s, "y"), user=STRANGER), T0 + 7000)
    assert acts == [Answer("q1", "권한 없음")] and ctrl.calls == [] and b.pending is not None


# ── 확인 흐름 ────────────────────────────────────────────────────────────────
def test_close_confirm_shows_position_and_yes_closes_everything():
    ctrl = FakeController()
    b = bot(ctrl)
    (s,) = sends(b.on_update(msg("청산"), T0 + 6000))
    assert s.chat_id == OWNER and "uPnL +1.00" in s.text and "예" in str(s.reply_markup)
    assert all(len(btn["callback_data"].encode()) <= 64 for btn in markup(s)["inline_keyboard"][0])
    acts = b.on_update(cb(confirm_data(s, "y")), T0 + 8000)
    assert acts[0] == Answer("q1", "실행") and "청산 완료" in sends(acts)[0].text
    assert ctrl.calls == [("close_all", f"telegram:{OWNER}")] and b.pending is None


def test_stop_yes_pauses_entries_then_closes():
    ctrl = FakeController()
    b = bot(ctrl)
    (s,) = sends(b.on_update(msg("/stop"), T0 + 6000))
    b.on_update(cb(confirm_data(s, "y")), T0 + 7000)
    assert ctrl.calls == [("pause", f"telegram:{OWNER}"), ("close_all", f"telegram:{OWNER}")]


def test_no_cancels_and_reports_not_closed():
    ctrl = FakeController()
    b = bot(ctrl)
    (s,) = sends(b.on_update(msg("/close"), T0 + 6000))
    acts = b.on_update(cb(confirm_data(s, "n")), T0 + 7000)
    assert acts[0] == Answer("q1", "취소") and "청산 안 됨" in sends(acts)[0].text and ctrl.calls == []


def test_no_answer_resends_three_times_at_three_seconds_then_cancels():
    ctrl = FakeController()
    b = bot(ctrl)
    t = T0 + 6000
    (first,) = sends(b.on_update(msg("/close"), t))
    timeline = {}
    for dt in range(0, 13_000, 500):
        out = sends(b.on_tick(t + dt))
        if out:
            timeline[dt] = out[0].text
    assert sorted(timeline) == [3000, 6000, 9000, 12_000]
    assert "재전송 1/3" in timeline[3000] and "재전송 3/3" in timeline[9000]
    assert "청산 안 됨" in timeline[12_000] and b.pending is None and ctrl.calls == []
    #  취소 뒤 옛 버튼을 눌러도 실행되지 않는다(응답은 한다)
    acts = b.on_update(cb(confirm_data(first, "y")), t + 13_000)
    assert acts == [Answer("q1", "만료되었거나 이미 처리됨 — 실행 안 함")] and ctrl.calls == []


def test_resends_carry_the_same_buttons_and_any_of_them_confirms():
    ctrl = FakeController()
    b = bot(ctrl)
    t = T0 + 6000
    sends(b.on_update(msg("/close"), t))
    (resend,) = sends(b.on_tick(t + 3000))
    b.on_update(cb(confirm_data(resend, "y")), t + 3500)
    assert ctrl.calls == [("close_all", f"telegram:{OWNER}")]


def test_callback_older_than_the_ttl_never_executes_even_if_ticks_did_not_run():
    ctrl = FakeController()
    b = bot(ctrl, resend_interval_ms=30_000)            # 취소 기한(+120초)이 TTL(60초)보다 늦은 설정 — TTL이 마지막 방어선
    (s,) = sends(b.on_update(msg("/close"), T0 + 6000))
    acts = b.on_update(cb(confirm_data(s, "y")), T0 + 6000 + K.CALLBACK_TTL_MS + 1)
    assert acts[0] == Answer("q1", "만료 — 실행 안 함") and "청산 안 됨" in sends(acts)[0].text
    assert ctrl.calls == [] and b.pending is None


def test_forged_or_foreign_callback_data_is_answered_and_ignored():
    ctrl = FakeController()
    b = bot(ctrl)
    sends(b.on_update(msg("/close"), T0 + 6000))
    for data in ("cf:ffffffffffffffff:y", "cf:0000000000000001:maybe", "garbage", ""):
        acts = b.on_update(cb(data), T0 + 7000)
        assert len(acts) == 1 and isinstance(acts[0], Answer), data
    assert ctrl.calls == [] and b.pending is not None


def test_only_one_confirmation_at_a_time():
    b = bot()
    sends(b.on_update(msg("/close"), T0 + 6000))
    (s,) = sends(b.on_update(msg("/stop"), T0 + 7000))
    assert "이미 확인 대기 중" in s.text and b.pending is not None and b.pending.command is C.Command.CLOSE


def test_close_failure_is_reported_not_raised():
    ctrl = FakeController(fail_close=True)
    b = bot(ctrl)
    (s,) = sends(b.on_update(msg("/close"), T0 + 6000))
    acts = b.on_update(cb(confirm_data(s, "y")), T0 + 7000)
    assert "청산 실패" in sends(acts)[0].text and "OrderOutcomeUnknown" in sends(acts)[0].text and b.pending is None


def test_close_when_flat_says_nothing_to_close_without_a_confirmation():
    ctrl = FakeController(position=False)
    b = bot(ctrl)
    (s,) = sends(b.on_update(msg("/close"), T0 + 6000))
    assert "포지션 없음" in s.text and s.reply_markup is None and b.pending is None and ctrl.calls == []


# ── 즉시 명령 ────────────────────────────────────────────────────────────────
def test_pause_start_status_position_profit_help():
    ctrl = FakeController()
    b = bot(ctrl)
    assert "신규 진입 중지" in sends(b.on_update(msg("/pause"), T0 + 6000))[0].text
    start = sends(b.on_update(msg("시작"), T0 + 6000))[0]
    assert "재개" in start.text and start.reply_markup == C.reply_keyboard()
    assert ctrl.calls == [("pause", f"telegram:{OWNER}"), ("resume", f"telegram:{OWNER}")]
    assert "진입 허용" in sends(b.on_update(msg("상태"), T0 + 6000))[0].text
    assert "uPnL" in sends(b.on_update(msg("/position"), T0 + 6000))[0].text
    assert "순손익" in sends(b.on_update(msg("수익"), T0 + 6000))[0].text
    h = sends(b.on_update(msg("/help"), T0 + 6000))[0]
    assert all(f"/{c.command}" in h.text for c in C.BOT_COMMANDS) and "중지" in h.text


def test_unknown_text_from_owner_gets_a_hint():
    (s,) = sends(bot().on_update(msg("뭐해"), T0 + 6000))
    assert "/help" in s.text


def test_controller_exception_on_an_immediate_command_is_reported():
    class Broken(FakeController):
        def status_text(self):
            raise RuntimeError("db locked")
    (s,) = sends(bot(Broken()).on_update(msg("/status"), T0 + 6000))
    assert "실패" in s.text and "db locked" in s.text


# ── 중요 이벤트 알림(설정으로 3회 규칙) ────────────────────────────────────────
def test_plain_alert_goes_once_to_every_owner():
    b = bot()
    assert sends(b.alert("킬스위치 발동", important=True, now_ms=T0)) == [Send(OWNER, "킬스위치 발동")]
    assert sends(b.on_tick(T0 + 10_000)) == []


def test_important_alert_resends_three_times_until_acknowledged_when_enabled():
    b = bot(important_resend=True)
    (a,) = sends(b.alert("킬스위치 발동", important=True, now_ms=T0))
    ack = markup(a)["inline_keyboard"][0][0]["callback_data"]
    assert len(sends(b.on_tick(T0 + 3000))) == 1
    acts = b.on_update(cb(ack), T0 + 4000)
    assert acts == [Answer("q1", "확인됨")]
    assert sends(b.on_tick(T0 + 6000)) == [] and sends(b.on_tick(T0 + 9000)) == []
    b2 = bot(important_resend=True)
    b2.alert("청산 발생", important=True, now_ms=T0)
    n = sum(len(sends(b2.on_tick(T0 + dt))) for dt in range(500, 20_000, 500))
    assert n == 3
    assert len(sends(b2.alert("진입", important=False, now_ms=T0))) == 1 and not b2.on_tick(T0 + 30_000)


def test_yes_after_the_no_answer_cancel_deadline_never_executes_even_if_ticks_stalled():
    """Codex L6·7 #1: 취소는 tick에만 달려 있으면 폴링이 멈춘 사이 +30초의 '예'가 실행된다 — 기한은 콜백에서도 검사한다."""
    ctrl = FakeController()
    b = bot(ctrl)
    t = T0 + 6000
    (s,) = sends(b.on_update(msg("/close"), t))
    deadline = t + (K.CONFIRM_RESENDS + 1) * K.CONFIRM_RESEND_INTERVAL_MS
    acts = b.on_update(cb(confirm_data(s, "y")), deadline + 1)                  # tick 한 번도 없이
    assert acts[0] == Answer("q1", "응답 기한 지남 — 실행 안 함") and "청산 안 됨" in sends(acts)[0].text
    assert ctrl.calls == [] and b.pending is None
    #  Codex 재검토: 경계는 tick 취소(>=)와 같게 — 정확히 +12초의 '예'는 처리 순서와 무관하게 실행되지 않는다
    for at, executed in ((deadline - 1, True), (deadline, False)):
        c2 = FakeController()
        b2 = bot(c2)
        (s2,) = sends(b2.on_update(msg("/close"), t))
        b2.on_update(cb(confirm_data(s2, "y")), at)
        assert (c2.calls == [("close_all", f"telegram:{OWNER}")]) is executed, at
    c3 = FakeController()
    b3 = bot(c3)
    sends(b3.on_update(msg("/close"), t))
    for dt in range(0, 12_001, 3000):
        b3.on_tick(t + dt)
    assert b3.pending is None, "tick도 정확히 +12초에 취소"
