# 영역 C — VPS 수집기 운영 런북

대상: 도쿄 AWS. 서버 2(t4g.medium, VolumeClockBot 페이퍼 운용)와 E2E_Hybrid_Bot 수집기 VPS. SSH 키가 공유돼 있으므로 호스트 확인이 모든 인스턴스 내 작업의 0단계다.

## 목차
1. 수집 원칙
2. E2E systemd 유닛 지도
3. prune · reconcile · drive-verify 상보성
4. store를 늘릴 때 (대칭 확장 절차)
5. 파생물 정책
6. 디스크 예보와 EBS 확장
7. 알림 설계 규칙
8. 반복된 실패 유형 (보고를 믿기 전 대조)
9. 진단 명령 모음

---

## 1. 수집 원칙
- 원천 최고 해상도(틱/100ms)로 저장. 매매봉은 의사결정 주기지 수집 주기가 아니다.
- 공백·재연결·시계 드리프트는 `manifest.sqlite`에 전부 기록. 일별 quality(00:10 UTC)가 게이트를 판정하는 **유일한 주체**다.
- L2·청산은 소급 구매 불가 → 수집 중단 = 영구 결손. 디스크·프로세스·스레드 어느 것이 멈춰도 같은 손실이다.
- 신규 데이터(OI·bookTicker·forceOrder 등)는 "수집만, 파생 피처·알림은 사전등록 전 금지"로 들어간다(v1.3/v1.4 방식). 샘플링 특성(forceOrder의 1초·largest)은 manifest 꼬리표로 데이터와 함께 다닌다.
- Tardis 데이터는 교차검증 전용, 학습 혼입 금지.
- 수집기 웹소켓은 티어별로 연결을 분리한다(`exchange-rules.md §8-1`). E2E l2collector·depthdiff는 `/public/ws`로 명시 이관 예정, E2E_COLLECT_DERIVS는 `/market` 소켓 분리 전까지 켜지 않는다. VolumeClockBot 수집기 URL도 같은 감사 대상.
- VPS venv는 경량(numpy 없음). 게이트 집계 모듈(`e2e.quality`·`ops/*`)에 numpy import 한 줄이 들어가면 게이트가 조용히 멈춘다. 분석 모듈(`e2e/bench`·`e2e/cost`)은 로컬 전용.

## 2. E2E systemd 유닛 지도 (user 유닛)
| 유닛 | 역할 | 주의 |
|---|---|---|
| `e2e-l2collector` | depth20@100ms + 체결 + bookTicker | 코어·60초 shard·atomic rename |
| `e2e-markprice` | mark/index/funding + OI REST 1s | OI는 수집만. REST 1s는 2026-04-23 라우팅 변경(markPrice가 /market 티어로 이동)을 가린 폴백이었음 — WS 복귀 여부 Codex 협의 중 |
| `e2e-depthdiff` | 전체깊이 diff + 10분 앵커 | **quarantine** — 복원·피처 금지 |
| `e2e-sync.timer` | Drive 시간당 백업 | 체크섬 검증. sync 실패는 비치명 → 무보장, verify가 보완 |
| `e2e-quality.timer` | 전일 확정 판정 00:10 UTC | 게이트 집계 유일 주체 |
| `e2e-health-digest.timer` | 텔레그램 일일 리포트 00:30 UTC | quality 확정(00:10) 이후여야 함 |
| `e2e-health-alert.timer` | 이슈 시 경보 30분 | 반복형 3h 스로틀, 확정 사실 하루 1통 |
| `e2e-prune.timer` | 주1회 02:30 UTC 로컬 shard 정리 | Drive 검증분만, 보존 30일 |
| `e2e-integrity.timer` | 주1회 03:30 UTC 대장↔파일 대사 + Drive 사본 | 보고 전용, 실패 시 텔레그램(`OnFailure=`는 `[Unit]`에) |
| `e2e-gate-notify.timer` | 🔕 휴면(#124) | 스로틀 키가 매일 바뀌어 무한 발송 |
| 외부 heartbeat | VPS 사망 감시(dead-man's switch) | 런북 2026-08-16 |

수동 실행은 `systemctl --user start <unit>`로(저널에 남게). `OnFailure=`가 붙은 유닛을 검증 목적으로 돌릴 때는 러너를 직접 호출해 오경보를 피한다.

## 3. prune · reconcile · drive-verify 상보성
- **prune**(`ops/prune_local.py`): 보존 30일 밖 shard를 **Drive rclone check 통과분만** 로컬 삭제하고 대장에 `pruned` 마킹. `pruned` = "Drive가 유일본".
- **reconcile**(`ops/reconcile_manifest.py`): 30일 창 안에서 대장↔파일 대사(고아·결손·0행·스트림 통째 결손). 대장에 쓰지 않는다.
- **drive-verify**(`ops/verify_drive_copies.py`): pruned 날짜의 파일이 원격에 *지금도* 있는지 크기·md5 대조.
- 세 검사의 30일은 **의도적으로 맞춘 상보 설계**(#128). `--keep-days`만 낮추는 것은 튜닝이 아니라 설계 변경이다.
- 검사는 살아 있는 시스템을 재므로 "진행 중"(flush 안 된 shard·등록 직전 파일)을 제외한다. 안 그러면 상시 발화 → 사람이 끔 → 침묵.
- healthy 판정은 `prune_day()`가 돌려주는 `manifest_marked`와 실제 삭제 수가 같은지를 봐야 한다(2026-09-12 Codex #②). 삭제됐는데 pruned 행이 없으면 verify가 그 존재를 모른다.

## 4. store를 늘릴 때 (2026-09-12 prune 확장 설계 v2, Codex 검토 반영)
순서를 지킨다. 삭제가 검사보다 먼저 넓어지면 검증 0인 유일본이 생긴다.
0. 기존 구멍 먼저: `manifest_marked != deleted → healthy=False` + 테스트.
1. `ops/data_stores.py` 도입 + reconcile·drive-verify를 새 store까지 확장. 특히 `_pruned_rows()`가 날짜만으로 묶는 구조를 **store별 grouping**으로, `adopt_day`의 `source LIKE 'l2live%'` 하드코딩을 store 인자로. SQLite LIKE의 `_` 와일드카드는 접두어에 `_`가 들어가는 순간 문제 → GLOB/escape(현행 결함 아님, 주의사항).
2. 무삭제로 1주기 관측(자동 prune 1회 + 자동 integrity 1회, 확장된 검사로).
3. prune 확장: **allowlist**(`deletion_mode="drive_verified_prune"`인 store만 삭제 가능)로 뒤집는다. NEVER_TOUCH denylist를 고쳐 쓰지 않는다. depthsnap은 registry에 넣지 않아 제외. dry-run으로 store별 파일 수·바이트를 보이고 사용자 확인 후 실삭제.
4. 파생물 prune은 별도 정책(§5).

각 단계 사이에 게이트(저널 수치·테스트·dry-run)를 두고, 삭제 코드는 Codex 검토 후 배포.

## 5. 파생물 정책
- raw에서 재생성 가능한 파생물(`data/parquet/l2` 등)은 백업 목록에 넣지 않는다(읽는 코드가 없는데 원격 무결성 부담만 는다). 짧은 보존(7일)의 별도 prune.
- 대장 상태는 `pruned`가 아니라 `expired_local_derivative`, bytes와 사유를 note에. 재압축(compact)이 note를 덮어야 stale이 안 남는다.
- 삭제 얘기가 나오면 재보정(#106)이 그 파생물을 읽는지 먼저 코드로 확인한다(2026-09-12 확인: 읽는 코드 0건, #106은 raw 복원 #22).

## 5-1. 봇 배포 (같은 호스트, 별도 유저)
- 봇은 수집기 인스턴스에 **별도 리눅스 유저·별도 systemd 유닛·별도 데이터/DB/Drive 원격·별도 텔레그램 봇**으로. 격리는 테스트로 확인(`ls` 수집기 디렉터리 → Permission denied).
- 메모리: 봇 유닛에 `MemoryMax`(400M) + `OOMScoreAdjust=500`(전역 OOM 시 봇이 먼저 죽음). cgroup memory 위임 확인 후 활성화. 봇 타이머는 수집기 quality 스파이크(00:10 UTC)와 겹치지 않게.
- 배포는 이틀 분할(D1 유저·코드·env·dry run / D2 유닛·기동), 하루에 라이브 호스트 변경 하나. 엔진 산술·스키마 변경은 **flat 상태에서 clean stop → start**(§9.7)로만.
- 라이브 전환 전 필수: 규칙 주기 재조회, pause 사유 집합, 거래 전용 키(VPS IP 하나·VPS .env만).

## 6. 디스크 예보와 EBS 확장
- 증가하는 store를 **전부** 잰다. l2live만 재는 `disk_days_left`는 우연히 맞는다(#21). 두 봇이 같은 인스턴스면 `du -sh`로 분리해 각각의 증가율을 기록한다.
- 2026-09-12 실측: l2live +500MB/일, quarantine/depthdiff +320MB/일, parquet/l2 +145MB/일, prune 반영 후 순감 −5.4GB/주.
- **소진 전에 늘리는 게 먼저다.** 온라인 확장은 수집을 안 멈추고 아무것도 안 지우며 gp3 ~$0.08/GB-월(도쿄는 약간 높음). 지우는 정책은 그 뒤에.

EBS 확장 절차(콘솔은 사용자, 인스턴스 내부는 에이전트):
1. EC2 → Instances → **E2E 인스턴스**(VolumeClockBot과 헷갈리지 않기) → Storage → 루트 볼륨 ID·크기·타입 메모.
2. (권장) Create snapshot.
3. Modify volume → 새 크기(줄이기 불가, 같은 볼륨 6시간 재수정 불가 → 여유 있게, 예 +50GB) → gp2면 gp3로.
4. State modifying → optimizing → completed. optimizing부터 사용 가능. 재부팅 불필요. 이 시점 `df -h`는 아직 안 늘어난 게 정상.
5. 에이전트: **`hostname`·`lsblk` 먼저 보여주고 사용자가 볼륨 일치 확인** → `sudo growpart /dev/nvme0n1 1` → ext4 `sudo resize2fs /dev/nvme0n1p1` / xfs `sudo xfs_growfs /` → `df -h`.
6. 사후: 수집기 active, 최신 shard, disk_forecast 경보 해소 확인. 운영일지에 경위 기록 후 커밋·푸시.

## 7. 알림 설계 규칙
- 확정 사실은 하루 1통, 반복형은 스로틀. 스로틀 키가 날짜를 포함하면 매일 리셋 = 무한 발송.
- digest는 quality 확정 뒤에 돌린다(00:00에 돌리면 매일 "판정 대기"만 나간다).
- 정체 경보: 0건 처리인데 성공 마커를 남기면 영원히 안 울린다. 마커는 실제 처리 수와 묶는다.
- `sent: true`는 배달이 아니다. 단명 프로세스 + 데몬 스레드는 전송 전에 죽는다.

## 8. 반복된 실패 유형
에이전트의 "완료" 보고를 받으면 이 목록과 대조한다.
- `sent: true`인데 배달 0건
- 죽은 상수(`SYNC_STALE_SEC`·`VAR_LAG`) — 이름은 있는데 아무도 안 읽음
- `|| true`가 게이트 실패를 삼킴 · `OnFailure=`를 `[Service]`에 둬 systemd가 무시
- 0건 삭제인데 성공 마커
- 대체값 가드가 분모를 바꿔치기해 그럴듯한 쓰레기
- 프로세스 `active`인데 내부 스레드 사망(`Restart=always` 무력)
- 상시 발화 경보 → 사람이 끔 → 침묵
- 예보가 한 store만 잼
- 검사 범위(reconcile/verify)와 삭제 범위(prune)의 비대칭
- 웹소켓 구독 수락 ≠ 전달(레거시 URL이 /market 티어를 조용히 폐기) · 대조군을 같은 소켓이 아니라 같은 티어로 · "준비됨" 플래그가 마지막 업스트림 변경 후 한 번도 끝까지 안 돌아봄
- 정밀한 측정(대조군·관측 길이)도 불변식이 틀리면 오답에 확신만 더한다 — 0건 결론 전에 "이 스트림이 이 엔드포인트에서 올 수 있는가"부터 확인
- **목(fake)이 내 가정을 돌려주면 테스트는 시스템이 아니라 내 믿음을 검증한다**(한 달에 세 번: 열 대신 키 #136, 추적 파일이 배포 대상인지 미대조 #139, oneshot은 실행 중 `activating`). 규칙: 목 상수 옆에 실측 출처를 남긴다 · 대응표가 아니라 호출 인자를 검사한다 · "고쳤다" 전에 그 경로가 참이 되는 상태를 한 번 관측한다(유휴에선 옛/새 코드가 같아 보인다)
- 대기 루프의 문자열 매칭("failed" 단어)이 상태를 대신하면 오탐 — 작업의 phase를 읽는다
- SSH 별칭이 다른 서버를 가리킬 수 있다 — 호스트를 건드리는 세션은 `hostname` 확인으로 시작한다
- 런북에 박힌 해시가 낡으면 옛 유닛이 배포된다 — 배포 단계는 자기 커밋을 리터럴 해시로 대조한다

## 9. 진단 명령 모음
```
systemctl --user list-units 'e2e-*' --all          # 유닛 상태
journalctl --user -u e2e-prune.service -n 50       # prune 저널
df -h / ; lsblk ; du -sh data/raw/* data/parquet/* # 디스크·store별 크기
.venv/bin/python -m ops.reconcile_manifest         # 대사 (rc=0, 디스크=대장)
.venv/bin/python -m ops.verify_drive_copies        # Drive 사본 md5
.venv/bin/python -m ops.scan_order_path            # 실주문 경로 금지 (위반 0)
.venv/bin/python -m e2e.quality gate               # 수집 건전성
```
