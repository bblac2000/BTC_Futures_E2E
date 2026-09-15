# 런북 — 도쿄 VPS 페이퍼 배포 (BTC_Futures_E2E · 템플릿 단계)

> 상태: **템플릿 — 아직 배포하지 않았다.** 배포 창 절차는 §9(2026-09-16 준비 · 실행은 사용자 지시 후).
> 상위 규칙: 스킬 `vps-ops.md` · 설계서 §2 "E2E 수집기와 별도 Linux 사용자·별도 systemd 유닛 · 메모리·디스크는 수집기 우선 · 수집기 데이터 디렉터리 접근 금지".
> 🔴 수집기 호스트에 닿는 변경 = **Codex 검토 후** 배포.

## 0. 호스트 확인 (모든 작업의 0단계)
SSH 키가 공유돼 있다. 명령 전에 **`hostname`·`whoami`·`df -h /`를 보여주고 사용자가 대상 인스턴스를 확인**한다.
E2E 수집기 유닛이 살아 있는지 먼저 본다: `sudo -u <수집기 사용자> XDG_RUNTIME_DIR=/run/user/$(id -u <수집기 사용자>) systemctl --user list-units 'e2e-*'`.

## 1. 봇 전용 사용자
> 🔧 **봇 사용자의 user 유닛 명령 형식(Codex 배포 전 #2)** — `sudo -iu btcfut` 셸의 사용자 버스에 기대지 않는다. 이 런북의 모든
> 봇 `systemctl --user`·`journalctl --user`는 운영자(sudo 가능) 셸에서 아래 두 함수로 실행한다(E2E 점검과 같은 모양):
> ```bash
> bsc() { sudo -u btcfut XDG_RUNTIME_DIR=/run/user/$(id -u btcfut) systemctl --user "$@"; }
> bjc() { sudo -u btcfut XDG_RUNTIME_DIR=/run/user/$(id -u btcfut) journalctl --user "$@"; }
> ```
> `loginctl enable-linger btcfut` 뒤 `ls -d /run/user/$(id -u btcfut)`가 있어야 한다(없으면 STOP — 사용자 버스 없음).
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
  진입 차단 `rules_from_snapshot`(상태 파일 `rules.fallback_reason` · /start로 안 풀림 → 원인 해결 후 `bsc restart btcfut-bot`).
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
B=/home/btcfut/BTC_Futures_E2E
sudo -u btcfut mkdir -p /home/btcfut/.config/systemd/user
sudo -u btcfut cp $B/ops/systemd/btcfut-{bot,failed@,health-alert,health-digest,sync}.service \
  $B/ops/systemd/btcfut-{health-alert,health-digest,sync}.timer /home/btcfut/.config/systemd/user/
bsc daemon-reload
bsc enable --now btcfut-bot.service btcfut-health-alert.timer btcfut-health-digest.timer btcfut-sync.timer
```
- ⚠️ **prune은 이 단계에서 설치·enable하지 않는다** — §6.
- 수동 실행은 `bsc start <unit>`(저널에 남게). `OnFailure=` 검증은 러너 직접 호출로(오경보 방지).

## 4. 수집기 우선 확인
```bash
bsc show btcfut-bot -p MemoryMax -p Nice -p IOSchedulingClass -p CPUWeight
U=$(id -u btcfut); cat /sys/fs/cgroup/user.slice/user-$U.slice/user@$U.service/cgroup.controllers   # memory가 있어야 MemoryMax가 적용된다
free -m ; df -h / ; sudo du -sh /home/btcfut/BTC_Futures_E2E/var/*
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
| shard | `var/raw/live/BTCUSDT/<오늘>/{kline1m_update,kline1m_close,markprice}/` 파일 증가 · 대장 `stop_dirty` 없음 · `confirmed_facts`에 `dirty_previous_run` 없음(SIGKILL은 `stop`을 안 남긴다 — #15 ⑤) |
| sync | `var/markers/LAST_SYNC.txt` 시간당 갱신 · 원격 폴더가 **E2E 폴더가 아님** |
| health | `bjc -u btcfut-health-alert -n 20` 에 `alert none/throttled/sent` · `send_failed` 없음 |
| 경보 설계 | 반복형 키에 숫자·날짜 없음(테스트 잠금) · 확정 사실은 하루 1통 · 상시 발화 경보가 없는지 첫 24시간 관찰 |
| 수집기 | E2E 유닛 상태·최신 shard 시각이 배포 전과 같다 · 디스크 증가율 store별로 분리 기록 |

반복된 실패 유형(체크): `sent: true`인데 배달 0 · 죽은 상수 · `|| true`가 실패를 삼킴 · `OnFailure=`가 `[Service]`에 ·
0건 삭제인데 성공 마커 · active인데 내부 스레드 사망 · 상시 발화 경보 → 침묵 · 한 store만 재는 예보 · 검사 범위와 삭제 범위 비대칭.

## 6. prune 켜기 (사람 확인 후)
1. 최소 1주기 무삭제 관측: sync 성공 마커가 계속 갱신되고 원격에 shard가 쌓인다.
2. dry-run: `.venv/bin/python -m ops.prune --var-dir ~/BTC_Futures_E2E/var` → 날짜별 삭제 예정 수·보류 사유를 사용자에게 보인다.
3. 사용자 확인 후에만: `sudo -u btcfut cp $B/ops/systemd/btcfut-prune.{service,timer} /home/btcfut/.config/systemd/user/ && bsc daemon-reload && bsc enable --now btcfut-prune.timer`.
4. 첫 `--apply` 뒤: 저널의 `deleted` == `manifest_marked`, `LAST_PRUNE.txt` 갱신, sqlite 파일 그대로.

## 7. 정지·재기동
- 정지: `bsc stop btcfut-bot` → 러너가 shard 종료 플러시·상태 저장·정지 알림. 알림의 `stop`/`stop_dirty` 확인.
- 페이퍼 포지션은 재기동 때 **DB 열린 행과 마지막 엔진 스냅샷이 일치할 때만** 복원된다(알림 `♻️ 재기동: 포지션 복원`).
  불일치면 flat으로 시작 · `paused:system:restart_position_mismatch` · 알림(양쪽 값) · DB 행은 `restart_unrestored`로 닫힌다 → 확인 후 /start.
  정지 중 펀딩 경계(00/08/16 UTC)를 지나면 첫 틱에 `FundingMissed` + 엔진 진입 차단(율 불명) → /start.
- 킬스위치·일시정지·대사 sticky 상태는 `safety_state`에서 복원된다(재기동이 트립을 풀지 않는다).

## 8. 아직 없는 것 (배포 논의 항목)
- 외부 heartbeat(dead-man's switch) — 텔레그램이 죽으면 health 경보도 못 나간다(E2E 2026-08-16).
- Drive 사본 재검증(`verify_drive_copies`에 해당) — pruned 행의 원격 md5를 주기적으로 다시 대조하는 도구.
- 대장↔파일 reconcile(고아·결손) 도구.
- LIVE 배선(`ExchangeReader` 실구현 · 계좌 응답 필드는 공식 문서·실캡처 확인 필요) — 설계서 §10 체크리스트·사용자 승인 전 금지.

## 9. 배포 창 — E2E Restart A/B와 같은 모양 (준비만 · 실행은 사용자 지시 후)
> 확정(사용자 2026-09-16): **D1 = 2026-09-18**(사용자·코드·환경·VPS 드라이런 · 유닛 없음) · **D2 = 2026-09-19**(유닛 설치·기동) ·
> 둘 다 **00:35–02:30 UTC** 창 안, 그날 E2E 00:10 판정 뒤 · **라이브 호스트 변경 하루 1건**.
> 🔴 어떤 배포 단계도 ① 이 절 포함 Codex 배포 전 배치 **MERGE** 전, ② E2E Restart B 게이트가 닫히기(**2026-09-18 00:16 UTC**) 전에는 하지 않는다.
> 명령마다 E2E에 닿지 않는지 먼저 본다.

### 9.0 전제 — 하나라도 아니면 창을 열지 않는다
- E2E Restart B 24h 게이트 판정이 닫혔다(E2E 쪽 보고로 확인 — 이 봇은 판정하지 않는다).
- Codex 배포 전 배치 MERGE · 배포 커밋 해시 `D` 고정(브랜치가 아니라 해시).
- 사용자 측 완료(D1 전): 봇 사용자 rclone remote · `.env`의 `TELEGRAM_OWNER_IDS` · 캡처 스크립트 실행.
- 키 IP 화이트리스트는 **마지막 — §9.1 로컬 점검이 끝난 뒤** 켠다(사용자 2026-09-16).
- ⚠️ 화이트리스트가 켜지면 로컬(WSL) 키 조회는 실패한다 → 로컬 키 드라이런은 화이트리스트 **전**에 끝낸다.
  `ipRestrict=true` 확인은 **VPS에서** 캡처 `--dry-run`으로(로컬에서는 -2015로 실패하는 것이 정상).

### 9.1 창 밖 사전 점검 ① — 로컬 worktree (창 전날까지 · 호스트 변경 없음)
```bash
git fetch origin && git worktree add ../btcfut-deploy-D D && cd ../btcfut-deploy-D
uv sync --frozen
uv run pytest -q && uv run ruff check . && uv run pyright && uv run python -m ops.stream_tiers --scan
V=$PWD/var/predeploy && uv run python -m ops.run_bot --mode paper --duration-s 240 --var-dir $V --db $V/bot.sqlite
```
- 기록: `D` · 테스트 수 · `status.json` = `exit_code 0` · `shutdown stop` · `delivered == sent` · `confirmed_facts []`.
- 규칙 출처: 이 점검은 화이트리스트 **전**에 한다 → `rules.source runtime:signed` · `blockers []`.
  (화이트리스트가 이미 켜졌다면 로컬은 `fallback:public+snapshot` + `blockers ["rules_from_snapshot"]`이 정상 — 그때는 VPS에서만 확인.)
- 끝나면 사용자에게 알린다 → 사용자가 키 IP 화이트리스트를 켠다.
- 유닛 파일: `git diff <마지막 Codex 검토 커밋>..D -- ops/systemd/` 가 비어 있다(아니면 검토부터).
- STOP: 하나라도 실패 · worktree는 창이 끝난 뒤 `git worktree remove`.

### 9.2 창 밖 사전 점검 ② — VPS 읽기만 (창 전날 · 변경 없음)
- §0 호스트 확인(`hostname`·`whoami`·`df -h /`)을 사용자가 대조.
- E2E 기준선(수집기 사용자 = E2E 레지스트리 #139 기준 `ubuntu`, §0에서 대조):
  `sudo -u ubuntu XDG_RUNTIME_DIR=/run/user/$(id -u ubuntu) systemctl --user list-units 'e2e-*' --all` ·
  `... list-timers --all` · `... show e2e-l2collector -p NRestarts -p ActiveEnterTimestamp` · 최신 shard 시각 · `free -m` · `df -h /`.
  🔴 **추적 사본이 아니라 VPS에 실제 설치된 타이머를 읽는다**(E2E #139: 추적 유닛 ≠ VPS 유닛이었다).
- 봇 흔적 없음(첫 배포): `id btcfut` 실패 · `/home/btcfut` 없음.
- 타이머 겹침 표(추적 사본 기준 — 위 실측으로 교체): E2E quality 00:10 · gate-notify 00:15(휴면) · health-digest 00:30 ·
  health-alert :00/:30 · sync :07 · prune 일 02:30 · integrity 일 03:30 ↔ 봇 health-alert 5분 · digest 00:30 · sync :20 ·
  prune 일 03:30(**설치 안 함** — §9.6).
- STOP: E2E 유닛 중 failed/inactive · 디스크 여유 < 5 GB + 봇 예상 증가분 · 호스트 불일치.

### 9.3 창 D1 (2026-09-18) — 봇 사용자·코드·환경 (첫 번째 변경 · 봇 유닛 없음)
시각: E2E 00:10 UTC 전일 판정이 기록되고 E2E health의 00:25 판정 대기가 끝난 뒤 **00:35 UTC 이후** 시작 ·
02:30 UTC 전 종료(일요일 E2E prune). 판정이 늦거나 FAIL이면 그날 창은 열지 않는다.
1. §0 호스트 확인 → 9.2 E2E 기준선 **재기록**(창 시작 시점).
2. §1 사용자 생성 · linger · 수집기 홈 읽기 불가 확인.
3. §2 `git clone` → `git checkout D` · `uv sync --frozen` · `.env`(사용자가 채움 · `chmod 600`) · rclone(사용자).
4. VPS에서 캡처 `--dry-run` → 사용자가 `ipRestrict=true`·읽기 외 권한 없음 확인.
5. VPS 드라이런 240초(§2 사전 검사 · 유닛 없이) → 9.1과 같은 기준 + `confirmed_facts []`.
6. 9.5 보고 → **멈춘다**(유닛 설치는 다음 날).

### 9.4 창 D2 (2026-09-19) — 유닛 설치·기동 (두 번째 변경)
시각: 9.3과 같은 규칙.
1. §0 호스트 확인 · E2E 기준선 재기록 · `git -C ~/BTC_Futures_E2E rev-parse HEAD` == `D`.
2. §3 유닛 설치(bot · failed@ · health-alert · health-digest · sync) — prune 제외.
3. §4 cgroup `memory` 위임 확인 — 없으면 **STOP**, 사용자 결정(system 유닛 `User=btcfut` 전환 여부).
4. `bsc enable --now …`(§3 명령 그대로) → `bsc is-active btcfut-bot` · §5 기동 후 대조표 전체.
5. 9.5 보고.

### 9.5 배포 후 보고 항목 (D1·D2 각각 · 24시간 뒤 한 번 더)
| 항목 | 기준 |
|---|---|
| E2E 유닛 | 상태·`NRestarts`·`ActiveEnterTimestamp`가 기준선과 같다 |
| E2E 데이터 | 최신 shard 시각이 계속 전진 · 대장에 창 동안 새 `stop`/`connect` 없음 |
| E2E 판정 | 다음 날 00:10 판정 결과(봇 영향 여부만 본다 — E2E 게이트는 E2E가 판정) |
| 호스트 | `free -m`·`df -h /` 기준선 대비 · `du -sh ~btcfut/BTC_Futures_E2E/var/*` |
| 봇 규칙 | `rules.source runtime:signed` · `fallback_reason null` · 사용자 `ipRestrict=true` 확인 |
| 봇 상태(D2) | 상태 파일 나이 < 120초 · `blockers []` · `stalled []` · `db_errors 0` · `confirmed_facts []` |
| 텔레그램(D2) | 기동 알림 수신 · `delivered == sent` · `poll_errors 0` · `/status` 왕복 |
| 데이터(D2) | `bars_1m` 증가 · shard 파일 증가 · 첫 :20 `LAST_SYNC.txt` · health-alert `none/throttled` |
| 24시간 뒤 | health digest 수신 · 반복 경보 없음 · E2E 판정 영향 없음 |

### 9.6 prune 시각 (D2 뒤 · 별도 변경 · 사용자 2026-09-16)
- prune 타이머는 D1·D2에 설치하지 않는다.
- D2 뒤 VPS에서 `sudo -u ubuntu XDG_RUNTIME_DIR=/run/user/$(id -u ubuntu) systemctl --user list-timers --all`로 **설치된 E2E 타이머를 실측**
  (추적 파일 금지) → **모든 E2E 타이머에서 30분 이상 떨어진** 시각을 고른다(봇 타이머와도 겹치지 않게).
- 시각 변경은 템플릿 커밋 + Codex → §6 절차(dry-run 출력 사용자 확인) → 별도 날의 라이브 호스트 변경.

롤백(봇만): `bsc disable --now btcfut-bot.service btcfut-health-alert.timer btcfut-health-digest.timer btcfut-sync.timer` → `bsc list-units 'btcfut-*' --all`로 비활성 확인.
E2E에 닿는 명령은 롤백에도 없다. 봇 사용자·데이터 삭제는 사람 확인 + Codex(삭제) 후.
