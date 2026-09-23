#!/usr/bin/env bash
# _guard.sh -- 跑批护栏：防止"多个任务同时跑 + 代理泄漏"把机器压垮。
#
# 背景（2026-09-21 事故）：同时跑 3 个重跑任务 → 8 个 bench 进程各自起一个
# litellm 代理（各约 300MB）→ 内存只剩 126MB、负载 13 → WSL 拒绝服务、
# 评委连接失败、整格作废。这是"总有缺口"的系统性根因。
#
# 护栏做三件事：
#   1. 【单实例】用 flock 锁住，同一时刻只允许一个跑批/补缺任务
#   2. 【内存看守】后台循环：清理陈旧的 litellm 进程；内存过低时告警
#   3. 【并发上限】容器数超过上限就等待，不硬冲
#
# 用法：在脚本开头写  source jobs/_guard.sh && guard_acquire "任务名"

GUARD_LOCK="/tmp/eduskillbench-guard.lock"
GUARD_LOG="${GUARD_LOG:-logs/guard.log}"
CONTAINER_CAP="${CONTAINER_CAP:-8}"
MEM_FLOOR_MB="${MEM_FLOOR_MB:-1500}"     # 可用内存低于此值就等待
LEAK_AGE_SEC="${LEAK_AGE_SEC:-2400}"     # litellm 超过 40 分钟视为泄漏

guard_acquire() {
  local name="${1:-task}"
  exec 9>"$GUARD_LOCK"
  if ! flock -n 9; then
    echo "✗ 已有跑批/补缺任务在运行（锁被占用）—— 拒绝并发，避免把机器压垮"
    echo "  查看： pgrep -af '_run_batch|_autofix|_retry'"
    echo "  若确认是残留，删锁： rm -f $GUARD_LOCK"
    return 1
  fi
  echo "✓ 已获得跑批锁（$name）"
  echo "$$" > "$GUARD_LOCK.pid"
}

guard_start_watch() {
  mkdir -p "$(dirname "$GUARD_LOG")" 2>/dev/null
  (
    exec 9>&- 2>/dev/null || true   # 关闭继承的锁 fd，主脚本退出即释放
    while true; do
      # 清理陈旧的 litellm（泄漏的代理，每个约 300MB）
      for pid in $(pgrep litellm 2>/dev/null); do
        et=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')
        [ -z "$et" ] && continue
        if [ "$et" -gt "$LEAK_AGE_SEC" ]; then
          kill "$pid" 2>/dev/null && echo "[$(date '+%H:%M')] 清理泄漏 litellm pid=$pid（已 $((et/60)) 分钟）" >> "$GUARD_LOG"
        fi
      done
      avail=$(free -m | awk 'NR==2{print $7}')
      if [ "${avail:-0}" -lt "$MEM_FLOOR_MB" ]; then
        echo "[$(date '+%H:%M')] ⚠ 可用内存仅 ${avail}MB，低于底线 ${MEM_FLOOR_MB}MB" >> "$GUARD_LOG"
      fi
      sleep 120
    done
  ) &
  GUARD_WATCH_PID=$!
  echo "✓ 内存看守已启动（每 2 分钟清一次泄漏；底线 ${MEM_FLOOR_MB}MB）"
}

guard_wait_containers() {
  local n
  n=$(docker ps -q 2>/dev/null | wc -l)
  while [ "$n" -ge "$CONTAINER_CAP" ]; do
    echo "  容器 $n ≥ 上限 $CONTAINER_CAP，等待…"
    sleep 20
    n=$(docker ps -q 2>/dev/null | wc -l)
  done
}

guard_wait_memory() {
  local avail
  avail=$(free -m | awk 'NR==2{print $7}')
  while [ "${avail:-0}" -lt "$MEM_FLOOR_MB" ]; do
    echo "  可用内存 ${avail}MB < ${MEM_FLOOR_MB}MB，等待释放…"
    sleep 30
    avail=$(free -m | awk 'NR==2{print $7}')
  done
}
