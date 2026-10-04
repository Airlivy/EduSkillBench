#!/usr/bin/env bash
# Compatibility lock helpers. New runner owns workers directly and starts no watcher.
guard_acquire() {
  exec 9>"${GUARD_LOCK:-/tmp/eduskillbench-guard.lock}"
  flock -n 9 || { echo 'A runner owns the lock; do not delete its file.' >&2; return 1; }
}
guard_start_watch() { :; }
guard_wait_memory() {
  local available
  available=$(awk '/MemAvailable:/{print $2}' /proc/meminfo)
  [ "$available" -ge "$(( ${MEM_FLOOR_MB:-1500} * 1024 ))" ] || {
    echo 'Insufficient memory; stop rather than spawn more workers.' >&2; return 1;
  }
}
guard_wait_containers() {
  local containers
  containers=$(docker ps -q) || return 1
  local count=0
  if [ -n "$containers" ]; then count=$(printf '%s\n' "$containers" | wc -l); fi
  [ "$count" -lt "${CONTAINER_CAP:-8}" ] || { echo 'Container cap reached.' >&2; return 1; }
}
