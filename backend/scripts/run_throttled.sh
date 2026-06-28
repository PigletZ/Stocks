#!/usr/bin/env bash
# 资源节流包装器：用于 cron 同步任务，降低瞬时资源冲击
#   - nice -n 19 / ionice -c3 : 最低 CPU 与磁盘 IO 优先级，不抢占交互与后端
#   - choom -n 800            : 提高自身 OOM 评分，内存紧张时优先杀本任务而非后端
#   - systemd-run --scope     : 把任务放进独立 cgroup
#       MemoryMax=900M        : 限制本任务内存，超限只杀本任务，不波及整机
#       MemorySwapMax=0       : 不使用 swap（本机无 swap，显式声明）
# 用法: run_throttled.sh <command> [args...]
set -euo pipefail

exec systemd-run --scope --quiet --collect \
  -p MemoryMax=900M \
  -p MemorySwapMax=0 \
  -p CPUWeight=20 \
  nice -n 19 ionice -c3 choom -n 800 -- "$@"
