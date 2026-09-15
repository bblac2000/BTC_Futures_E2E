"""systemd `OnFailure=` 알림 — `btcfut-failed@<unit>.service`가 부른다.

🔴 유닛 파일에 파이썬 코드를 박지 않는다(E2E 2026-08-15: systemd가 `\\n`을 줄바꿈으로 바꿔 알림 장치가 SyntaxError로 죽었다).
발송은 `notify(block=True)` — 응답 `ok`가 아니면 종료 코드 1(저널에 남는다).
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from notify.sender import notify
    args = sys.argv[1:] if argv is None else argv
    unit = args[0] if args else "?"
    res = notify(f"🔴 systemd 유닛 실패: {unit} — journalctl --user -u {unit} -n 50", block=True) or {}
    if not res.get("ok"):
        print(f"[notify_failure] 발송 실패: {res}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
