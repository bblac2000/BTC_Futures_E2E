# 런북 — 도쿄 VPS 페이퍼 배포 (BTC_Futures_E2E · 템플릿 단계)

> 상태: **템플릿 — 아직 배포하지 않았다.** VPS 배포는 사용자와 따로 논의한 뒤 진행한다(2026-09-16 지시).
> 상위 규칙: 스킬 `vps-ops.md` · 설계서 §2 "E2E 수집기와 별도 Linux 사용자·별도 systemd 유닛 · 메모리·디스크는 수집기 우선 · 수집기 데이터 디렉터리 접근 금지".
> 🔴 수집기 호스트에 닿는 변경 = **Codex 검토 후** 배포.

## 0. 호스트 확인 (모든 작업의 0단계)
SSH 키가 공유돼 있다. 명령 전에 **`hostname`·`whoami`·`df -h /`를 보여주고 사용자가 대상 인스턴스를 확인**한다.
E2E 수집기 유닛이 살아 있는지 먼저 본다: `sudo -u <수집기 사용자> XDG_RUNTIME_DIR=/run/user/$(id -u <수집기 사용자>) systemctl --user list-units 'e2e-*'`.

## 1. 봇 전용 사용자
```bash
sudo adduser --disabled-password --gecos "" btcfut
sudo loginctl enable-linger btcfut          # 로그아웃해도 user 유닛 유지
sudo -iu btcfut
```
- 🚫 btcfut를 수집기 사용자 그룹에 넣지 않는다 · 수집기 홈/데이터 디렉터리에 ACL을 주지 않는다.
- 확인: `ls -ld ~<수집기 사용자>` 가 btcfut에게 읽기 불가여야 한다(`700`/`750` + 그룹 불일치).

## 2. 코드·환경
```bash
git clone https://github.com/bblac2000/BTC_Futures_E2E.git ~/BTC_Futures_E2E
cd ~/BTC_Futures_E2E && curl -LsSf https://astral.sh/uv/install.sh | sh && ~/.local/bin/uv sync
mkdir -p logs var && chmod 700 var
cp .env.example .env && chmod 600 .env    # 값은 사용자가 채운다(에이전트는 값을 출력하지 않는다)
```
`.env`(페이퍼): `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` · `TELEGRAM_OWNER_IDS` · `BTCFUT_DRIVE_REMOTE` · `BINANCE_API_KEY`/`BINANCE_API_SECRET`.
- 바이낸스 키 = **읽기 전용 키**(거래·출금 권한 끔 · VPS IP 화이트리스트, 사용자 2026-09-16 (ii)). 러너가 기동 때 권한을 실측하고
  읽기 외 권한이 하나라도 켜져 있으면 **기동 거부(종료 코드 4)**. 키가 없거나 조회가 실패하면 캡처 스냅샷으로 기동하되
  진입 차단 `rules_from_snapshot`(상태 파일 `rules.fallback_reason` · /start로 안 풀림 → 원인 해결 후 `systemctl --user restart btcfut-bot`).
- 봇 토큰은 이 봇 전용. 다른 프로세스가 같은 토큰으로 `getUpdates`를 하면 409 — 상태 파일 `poll_errors`로 드러난다.
- rclone: btcfut 사용자 자신의 `~/.config/rclone/rclone.conf`. `BTCFUT_DRIVE_REMOTE=<remote>:BTC_Futures_E2E` — **E2E 폴더를 가리키면 sync·prune이 거부**한다.

사전 검사(전부 통과해야 다음 단계):
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ops.stream_tiers --scan
.venv/bin/python -m ops.run_bot --mode paper --duration-s 240 --var-dir ~/BTC_Futures_E2E/var/dryrun --db ~/BTC_Futures_E2E/var/dryrun/bot.sqlite
cat var/dryrun/run/status.json          # shutdown=stop · exit_code=0 · delivered=sent · blockers=[] · db_errors=0 · rules.source=runtime:signed
```

## 3. 유닛 설치 (user 유닛)
```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/btcfut-{bot,failed@,health-alert,health-digest,sync}.service ops/systemd/btcfut-{health-alert,health-digest,sync}.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now btcfut-bot.service btcfut-health-alert.timer btcfut-health-digest.timer btcfut-sync.timer
```
- ⚠️ **prune은 이 단계에서 설치·enable하지 않는다** — §6.
- 수동 실행은 `systemctl --user start <unit>`(저널에 남게). `OnFailure=` 검증은 러너 직접 호출로(오경보 방지).

## 4. 수집기 우선 확인
```bash
systemctl --user show btcfut-bot -p MemoryMax -p Nice -p IOSchedulingClass -p CPUWeight
cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers   # memory가 있어야 MemoryMax가 적용된다
free -m ; df -h / ; du -sh ~/BTC_Futures_E2E/var/*
```
`memory` 위임이 없으면 MemoryMax는 **적용되지 않는다** — 사용자에게 보고하고 system 유닛(`User=btcfut`) 전환 여부를 결정받는다.

## 5. 기동 후 확인 (보고를 믿기 전에 대조 — vps-ops §8)
| 확인 | 명령 / 기준 |
|---|---|
| 프로세스 active ≠ 루프 생존 | `var/run/status.json` 나이 < 120초(1초마다 갱신) |
| 텔레그램 배달 | 기동 알림 수신 · 상태 파일 `delivered == sent` · `send_errors == 0` (`sent`는 배달이 아니다) |
| 명령 왕복 | `/status` → 모든 차단 사유가 나열된 답 · `/help` 메뉴 |
| 피드 | `stalled: []` · `delivery`의 세 스트림 `last_seen_age_sec` < 120 |
| DB | `sqlite3 var/bot.sqlite "select source,count(*) from bars_1m group by 1"` 가 늘어난다 · `db_errors: 0` |
| shard | `var/raw/live/BTCUSDT/<오늘>/{kline1m_update,kline1m_close,markprice}/` 파일 증가 · 대장 `stop_dirty` 없음 |
| sync | `var/markers/LAST_SYNC.txt` 시간당 갱신 · 원격 폴더가 **E2E 폴더가 아님** |
| health | `journalctl --user -u btcfut-health-alert -n 20` 에 `alert none/throttled/sent` · `send_failed` 없음 |
| 경보 설계 | 반복형 키에 숫자·날짜 없음(테스트 잠금) · 확정 사실은 하루 1통 · 상시 발화 경보가 없는지 첫 24시간 관찰 |
| 수집기 | E2E 유닛 상태·최신 shard 시각이 배포 전과 같다 · 디스크 증가율 store별로 분리 기록 |

반복된 실패 유형(체크): `sent: true`인데 배달 0 · 죽은 상수 · `|| true`가 실패를 삼킴 · `OnFailure=`가 `[Service]`에 ·
0건 삭제인데 성공 마커 · active인데 내부 스레드 사망 · 상시 발화 경보 → 침묵 · 한 store만 재는 예보 · 검사 범위와 삭제 범위 비대칭.

## 6. prune 켜기 (사람 확인 후)
1. 최소 1주기 무삭제 관측: sync 성공 마커가 계속 갱신되고 원격에 shard가 쌓인다.
2. dry-run: `.venv/bin/python -m ops.prune --var-dir ~/BTC_Futures_E2E/var` → 날짜별 삭제 예정 수·보류 사유를 사용자에게 보인다.
3. 사용자 확인 후에만: `cp ops/systemd/btcfut-prune.{service,timer} ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now btcfut-prune.timer`.
4. 첫 `--apply` 뒤: 저널의 `deleted` == `manifest_marked`, `LAST_PRUNE.txt` 갱신, sqlite 파일 그대로.

## 7. 정지·재기동
- 정지: `systemctl --user stop btcfut-bot` → 러너가 shard 종료 플러시·상태 저장·정지 알림. 알림의 `stop`/`stop_dirty` 확인.
- 페이퍼 포지션은 재기동 때 **DB 열린 행과 마지막 엔진 스냅샷이 일치할 때만** 복원된다(알림 `♻️ 재기동: 포지션 복원`).
  불일치면 flat으로 시작 · `paused:system:restart_position_mismatch` · 알림(양쪽 값) · DB 행은 `restart_unrestored`로 닫힌다 → 확인 후 /start.
  정지 중 펀딩 경계(00/08/16 UTC)를 지나면 첫 틱에 `FundingMissed` + 엔진 진입 차단(율 불명) → /start.
- 킬스위치·일시정지·대사 sticky 상태는 `safety_state`에서 복원된다(재기동이 트립을 풀지 않는다).

## 8. 아직 없는 것 (배포 논의 항목)
- 외부 heartbeat(dead-man's switch) — 텔레그램이 죽으면 health 경보도 못 나간다(E2E 2026-08-16).
- Drive 사본 재검증(`verify_drive_copies`에 해당) — pruned 행의 원격 md5를 주기적으로 다시 대조하는 도구.
- 대장↔파일 reconcile(고아·결손) 도구.
- LIVE 배선(`ExchangeReader` 실구현 · 계좌 응답 필드는 공식 문서·실캡처 확인 필요) — 설계서 §10 체크리스트·사용자 승인 전 금지.
