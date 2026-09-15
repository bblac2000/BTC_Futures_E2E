"""명령 이름·한글 별칭·메뉴 — Bot API 10.3 제약(ops_log 2026-09-15 렌더링 확인).

- `BotCommand.command`: 1-32자, 영문 소문자·숫자·밑줄만 → 한글(시작·중지·일시정지·상태 …)은 **등록 명령이 아니라 텍스트 별칭**.
  답장 키보드 버튼을 누르면 그 텍스트가 메시지로 오므로 같은 파서를 탄다.
- `/stop`·`/close`는 청산(확인 흐름) · `/pause`는 신규 진입만 중지 · `/start`는 재개(킬스위치 해제는 이 경로뿐).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Command(StrEnum):
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    STATUS = "status"
    POSITION = "position"
    CLOSE = "close"
    PROFIT = "profit"
    HELP = "help"


@dataclass(frozen=True)
class BotCommandSpec:
    command: str
    description: str
    aliases: tuple[str, ...]


BOT_COMMANDS: tuple[BotCommandSpec, ...] = (
    BotCommandSpec("start", "재개 — 신규 진입 허용(킬스위치 해제 포함)", ("시작",)),
    BotCommandSpec("stop", "중지 — 신규 진입 차단 + 전량 청산(확인 필요)", ("중지",)),
    BotCommandSpec("pause", "일시정지 — 신규 진입만 차단, 포지션 유지", ("일시정지",)),
    BotCommandSpec("status", "상태 — 진입 허용 여부·차단 사유·피드", ("상태",)),
    BotCommandSpec("position", "포지션 — 수량·진입가·mark·미실현손익", ("포지션",)),
    BotCommandSpec("close", "청산 — 전량 MARKET reduceOnly(확인 필요)", ("청산",)),
    BotCommandSpec("profit", "수익 — 실현·누적 순손익", ("수익",)),
    BotCommandSpec("help", "도움말 — 명령 목록", ("도움말",)),
)

_CMD_RE = re.compile(r"^/([A-Za-z0-9_]{1,32})(?:@([A-Za-z0-9_]+))?$")
_BY_NAME = {c.command: Command(c.command) for c in BOT_COMMANDS}
_BY_ALIAS = {a: Command(c.command) for c in BOT_COMMANDS for a in c.aliases}


def parse_command(text: str | None, *, bot_username: str | None) -> Command | None:
    """`/cmd`, `/cmd@이봇`, 영문 명령어 단어(`stop`), 한글 별칭(`중지`) — 정확히 일치할 때만."""
    if not isinstance(text, str):
        return None
    t = text.strip()
    if not t:
        return None
    m = _CMD_RE.match(t)
    if m:
        if m.group(2) is not None and (bot_username is None or m.group(2).lower() != bot_username.lower()):
            return None                                    # 다른 봇에게 보낸 명령
        return _BY_NAME.get(m.group(1).lower())
    if t in _BY_ALIAS:
        return _BY_ALIAS[t]
    return _BY_NAME.get(t.lower()) if t.isascii() else None


def api_commands() -> list[dict[str, str]]:
    return [{"command": c.command, "description": c.description} for c in BOT_COMMANDS]


def reply_keyboard() -> dict[str, Any]:
    """메뉴 버튼(답장 키보드) — 버튼 텍스트는 전부 별칭이라 누르면 명령으로 파싱된다."""
    return {"keyboard": [["상태", "포지션", "수익"], ["일시정지", "시작", "도움말"], ["청산", "중지"]],
            "is_persistent": True, "resize_keyboard": True, "input_field_placeholder": "명령 또는 버튼"}


def help_text() -> str:
    lines = ["명령 (한글 별칭도 같다)"]
    lines += [f"/{c.command} · {'/'.join(c.aliases)} — {c.description}" for c in BOT_COMMANDS]
    lines.append("청산·중지는 [예/아니오] 확인 — 3초 간격 3회 재전송 후 무응답이면 취소(청산 안 됨)")
    return "\n".join(lines)
