#!/usr/bin/env bash
#  VPS 메모리 5초 표집(읽기 전용) — E2E quality 00:10 겹침 창(기본 00:08~00:15 UTC)의 **실측 최저 가용 메모리**를 얻는다.
#  호스트에는 읽기 명령만 보낸다(systemctl show · free · cat cgroup). 사용법:
#    scripts/vps_memory_sampler.sh [샘플수=84] [간격초=5] > var/mem_sampler_<날짜>.log
set -u
N=${1:-84}; EVERY=${2:-5}
ssh -o BatchMode=yes -i ~/.ssh/e2e-bot-key.pem ubuntu@35.79.38.63 "
hostname; date -u +%FT%TZ
U=\$(id -u ubuntu); B=\$(id -u btcfut)
for i in \$(seq 1 $N); do
  ts=\$(date -u +%T)
  av=\$(free -m | awk '/Mem:/{print \$7}')
  bot=\$(sudo -u btcfut XDG_RUNTIME_DIR=/run/user/\$B systemctl --user show btcfut-bot -p MemoryCurrent --value)
  q=\$(XDG_RUNTIME_DIR=/run/user/\$U systemctl --user show e2e-quality -p MemoryCurrent --value)
  col=\$(XDG_RUNTIME_DIR=/run/user/\$U systemctl --user show e2e-l2collector -p MemoryCurrent --value)
  echo \"\$ts avail_mb=\$av bot=\$bot quality=\$q collector=\$col\"
  sleep $EVERY
done
echo ==final
sudo -u btcfut XDG_RUNTIME_DIR=/run/user/\$B systemctl --user show btcfut-bot -p ActiveState -p NRestarts -p MemoryCurrent -p MemoryPeak -p ActiveEnterTimestamp
sudo cat /sys/fs/cgroup/user.slice/user-\$B.slice/user@\$B.service/app.slice/btcfut-bot.service/memory.events
XDG_RUNTIME_DIR=/run/user/\$U systemctl --user show e2e-quality -p Result -p MemoryPeak -p ExecMainStartTimestamp -p ExecMainExitTimestamp
XDG_RUNTIME_DIR=/run/user/\$U systemctl --user show e2e-l2collector -p ActiveState -p NRestarts -p ActiveEnterTimestamp
free -m
"
