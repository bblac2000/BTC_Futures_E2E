"""텔레그램 명령 봇 — **순수 상태기계**(네트워크 없음). 전송은 `notify.poller`가 행동 객체(`Send`·`Answer`)를 실행한다.

사용자 확정(open-decisions #9 · strategy-modules §6, 2026-09-12):
- 발신자 ID 화이트리스트 → `/stop`·`/close`는 현재 포지션·미실현손익과 함께 [예/아니오] 인라인 버튼 →
  무응답이면 **3초 간격 3회 재전송** → 그래도 무응답이면 **취소 + "청산 안 됨"** (미확인 청산은 오터치일 수 있다)
- 콜백에는 발행 토큰(nonce)을 넣고 **60초 만료** — 오래된 버튼이 나중에 눌려 청산되지 않게
  (+12초 무응답 취소 기한도 콜백에서 직접 검사한다 — tick이 멈춰도 늦은 '예'가 실행되지 않게 · Codex L6·7 #1)
- 텍스트 명령('중지'·'stop')도 같은 경로 · 중요 이벤트 알림에 같은 3회 규칙을 설정으로 켤 수 있다

이 저장소의 해석(보고·설계서 기록):
- `/stop` 예 = 신규 진입 차단 **그리고** 전량 청산 · `/close` 예 = 전량 청산만(진입 상태 불변)
- 재전송은 발행 시각 기준 +3·+6·+9초, 취소는 +12초(3회 재전송 뒤 한 간격 더 기다린 뒤)
- 개인 채팅만 받는다(그룹에 포지션 정보를 내보내지 않는다) · 기동 전 날짜의 메시지는 무시(재시작 뒤 재생 방지)
- 확인 대기는 한 번에 하나 · 포지션이 없으면 `/close`는 확인 없이 "포지션 없음"
- 컨트롤러(엔진·킬스위치 배선, layer 8) 예외는 봇 밖으로 내보내지 않고 "실패" 문구로 알린다
- Bot API: 모든 콜백에 answerCallbackQuery(거부·만료 포함) · callback_data ≤ 64 bytes
"""
from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from notify import config as K
from notify.commands import Command, help_text, parse_command, reply_keyboard

CONFIRM_PREFIX = "cf"
ACK_PREFIX = "ak"


class BotController(Protocol):
    """layer 8 배선이 구현한다(엔진·킬스위치·DB). 문자열 결과를 돌려주고, 실패는 예외로."""

    def status_text(self) -> str: ...

    def position_text(self) -> str: ...

    def profit_text(self) -> str: ...

    def has_position(self) -> bool: ...

    def pause_entries(self, actor: str) -> str: ...

    def resume(self, actor: str) -> str: ...

    def close_all(self, actor: str) -> str: ...


@dataclass(frozen=True)
class Send:
    chat_id: int
    text: str
    reply_markup: dict[str, Any] | None = None


@dataclass(frozen=True)
class Answer:
    callback_query_id: str
    text: str | None = None


@dataclass
class PendingConfirm:
    command: Command
    nonce: str
    chat_id: int
    issued_ms: int
    actor: str
    resends: int = 0


@dataclass
class PendingAlert:
    nonce: str
    text: str
    issued_ms: int
    resends: int = 0


def _default_nonce() -> str:
    return secrets.token_hex(8)


@dataclass
class CommandBot:
    controller: BotController
    owner_ids: frozenset[int]
    started_ms: int
    bot_username: str | None = None
    nonce: Callable[[], str] = _default_nonce
    important_resend: bool = False
    resend_interval_ms: int = K.CONFIRM_RESEND_INTERVAL_MS
    resends: int = K.CONFIRM_RESENDS
    ttl_ms: int = K.CALLBACK_TTL_MS
    pending: PendingConfirm | None = None
    alerts: dict[str, PendingAlert] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=lambda: {"ignored_non_owner": 0, "ignored_non_private": 0,
                                                          "ignored_stale": 0})

    def __post_init__(self) -> None:
        if not self.owner_ids:
            raise ValueError("주인 ID 화이트리스트가 비어 있다")

    # ── 입력 ────────────────────────────────────────────────────────────────
    def on_update(self, update: dict[str, Any], now_ms: int) -> list[Send | Answer]:
        if isinstance(update.get("callback_query"), dict):
            return self._on_callback(update["callback_query"], now_ms)
        m = update.get("message")
        if not isinstance(m, dict):
            return []
        user = (m.get("from") or {}).get("id")
        chat = m.get("chat") or {}
        if user not in self.owner_ids:
            self.stats["ignored_non_owner"] += 1
            return []
        if chat.get("type") != "private":
            self.stats["ignored_non_private"] += 1
            return []
        date_s = m.get("date")
        if not isinstance(date_s, int) or date_s * 1000 < self.started_ms:
            self.stats["ignored_stale"] += 1
            return []
        chat_id = int(chat.get("id", user))
        actor = f"telegram:{user}"
        cmd = parse_command(m.get("text"), bot_username=self.bot_username)
        if cmd is None:
            return [Send(chat_id, "알 수 없는 명령 — /help")]
        if cmd in (Command.STOP, Command.CLOSE):
            return self._request_confirm(cmd, chat_id, actor, now_ms)
        return [self._immediate(cmd, chat_id, actor)]

    def on_tick(self, now_ms: int) -> list[Send | Answer]:
        out: list[Send | Answer] = []
        p = self.pending
        if p is not None and now_ms >= p.issued_ms + (p.resends + 1) * self.resend_interval_ms:
            if p.resends < self.resends:
                p.resends += 1
                out.append(self._confirm_message(p))
            else:
                self.pending = None
                out.append(Send(p.chat_id, f"응답 없음 — {self._label(p.command)} 취소, 청산 안 됨"))
        for a in list(self.alerts.values()):
            if now_ms >= a.issued_ms + (a.resends + 1) * self.resend_interval_ms:
                if a.resends < self.resends:
                    a.resends += 1
                    out += self._alert_sends(a)
                else:
                    del self.alerts[a.nonce]
        return out

    def alert(self, text: str, *, important: bool, now_ms: int) -> list[Send | Answer]:
        """이벤트 알림(진입·청산·펀딩·킬스위치). 중요 + 설정 켜짐이면 [확인] 버튼과 3회 재전송."""
        if not (important and self.important_resend):
            return [Send(uid, text) for uid in sorted(self.owner_ids)]
        a = PendingAlert(self.nonce(), text, now_ms)
        self.alerts[a.nonce] = a
        return self._alert_sends(a)

    def cancel_deadline_ms(self, p: PendingConfirm) -> int:
        """발행 + (재전송 횟수 + 1) × 간격 — 이 시각 **이후(경계 포함)**의 '예'는 실행하지 않는다(tick 취소와 같은 경계)."""
        return p.issued_ms + (self.resends + 1) * self.resend_interval_ms

    # ── 내부 ────────────────────────────────────────────────────────────────
    @staticmethod
    def _label(cmd: Command) -> str:
        return "중지(신규 진입 차단 + 전량 청산)" if cmd is Command.STOP else "전량 청산"

    def _safe(self, fn: Callable[[], str], what: str) -> str:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — 컨트롤러 실패는 사용자에게 알리고 봇은 계속
            return f"{what} 실패: {type(e).__name__}: {e}"

    def _immediate(self, cmd: Command, chat_id: int, actor: str) -> Send:
        c = self.controller
        if cmd is Command.START:
            return Send(chat_id, self._safe(lambda: c.resume(actor), "재개"), reply_keyboard())
        if cmd is Command.PAUSE:
            return Send(chat_id, self._safe(lambda: c.pause_entries(actor), "일시정지"))
        if cmd is Command.STATUS:
            return Send(chat_id, self._safe(c.status_text, "상태 조회"))
        if cmd is Command.POSITION:
            return Send(chat_id, self._safe(c.position_text, "포지션 조회"))
        if cmd is Command.PROFIT:
            return Send(chat_id, self._safe(c.profit_text, "수익 조회"))
        return Send(chat_id, help_text(), reply_keyboard())

    def _confirm_message(self, p: PendingConfirm) -> Send:
        position = self._safe(self.controller.position_text, "포지션 조회")
        suffix = f"\n(재전송 {p.resends}/{self.resends} · 무응답 시 취소)" if p.resends else "\n(무응답 시 3회 재전송 후 취소)"
        buttons = [{"text": "예", "callback_data": f"{CONFIRM_PREFIX}:{p.nonce}:y"},
                   {"text": "아니오", "callback_data": f"{CONFIRM_PREFIX}:{p.nonce}:n"}]
        return Send(p.chat_id, f"⚠️ {self._label(p.command)} — 정말 실행할까요?\n{position}{suffix}",
                    {"inline_keyboard": [buttons]})

    def _request_confirm(self, cmd: Command, chat_id: int, actor: str, now_ms: int) -> list[Send | Answer]:
        if self.pending is not None:
            return [Send(chat_id, f"이미 확인 대기 중: {self._label(self.pending.command)} — 먼저 예/아니오")]
        has = self._safe(lambda: "1" if self.controller.has_position() else "", "포지션 조회")
        if cmd is Command.CLOSE and has == "":
            return [Send(chat_id, "포지션 없음 — 청산할 것이 없다")]
        self.pending = PendingConfirm(cmd, self.nonce(), chat_id, now_ms, actor)
        return [self._confirm_message(self.pending)]

    def _alert_sends(self, a: PendingAlert) -> list[Send | Answer]:
        suffix = f"\n(재전송 {a.resends}/{self.resends})" if a.resends else ""
        markup = {"inline_keyboard": [[{"text": "확인", "callback_data": f"{ACK_PREFIX}:{a.nonce}"}]]}
        return [Send(uid, a.text + suffix, markup) for uid in sorted(self.owner_ids)]

    def _on_callback(self, q: dict[str, Any], now_ms: int) -> list[Send | Answer]:
        qid = str(q.get("id", ""))
        user = (q.get("from") or {}).get("id")
        if user not in self.owner_ids:
            self.stats["ignored_non_owner"] += 1
            return [Answer(qid, "권한 없음")]
        parts = str(q.get("data") or "").split(":")
        if len(parts) == 2 and parts[0] == ACK_PREFIX:
            if self.alerts.pop(parts[1], None) is not None:
                return [Answer(qid, "확인됨")]
            return [Answer(qid, "이미 확인됨")]
        if len(parts) != 3 or parts[0] != CONFIRM_PREFIX or parts[2] not in ("y", "n"):
            return [Answer(qid, "알 수 없는 버튼")]
        p = self.pending
        if p is None or parts[1] != p.nonce:
            return [Answer(qid, "만료되었거나 이미 처리됨 — 실행 안 함")]
        self.pending = None
        #  🔴 Codex L6·7 #1: 무응답 취소 기한(+12초)은 tick만이 아니라 **콜백에서도** 검사 — 폴링이 멈춘 사이의 '예'를 막는다
        if now_ms >= self.cancel_deadline_ms(p):             # tick 취소(>=)와 같은 경계 — 처리 순서와 무관
            return [Answer(qid, "응답 기한 지남 — 실행 안 함"),
                    Send(p.chat_id, f"응답 기한 지남 — {self._label(p.command)} 취소, 청산 안 됨")]
        if now_ms - p.issued_ms > self.ttl_ms:
            return [Answer(qid, "만료 — 실행 안 함"), Send(p.chat_id, f"확인 만료 — {self._label(p.command)} 취소, 청산 안 됨")]
        if parts[2] == "n":
            return [Answer(qid, "취소"), Send(p.chat_id, f"{self._label(p.command)} 취소 — 청산 안 됨")]
        actor = f"telegram:{user}"
        lines = []
        if p.command is Command.STOP:
            lines.append(self._safe(lambda: self.controller.pause_entries(actor), "진입 차단"))
        lines.append(self._safe(lambda: self.controller.close_all(actor), "청산"))
        return [Answer(qid, "실행"), Send(p.chat_id, "\n".join(lines))]
