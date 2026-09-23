#!/usr/bin/env bash
# _backup.sh -- 把不可再生的数据备份到【仓库之外】，防误删/防意外。
#
# 备份到 /home/airlivy/eduskillbench-backup/
#   latest/          滚动镜像（每 10 分钟刷新；只增不删，绝不因为源缺失而删备份）
#   snapshots/       每小时一个带时间戳的快照（tar，含 jobs + 关键数据）
#   latest/MANIFEST.txt  每次都记数量与体积，日后可核对有没有丢东西
#
# 用法：
#   bash jobs/_backup.sh once      # 立刻备份一次
#   bash jobs/_backup.sh watch     # 常驻，每 10 分钟一次（跑批期间用）
set -u
SRC=/home/airlivy/EduSkillBench
DST=/home/airlivy/eduskillbench-backup
SUBS="jobs data results paper code skills"
mkdir -p "$DST/latest" "$DST/snapshots"

sync_once() {
  local stamp; stamp=$(date '+%F %T')
  for sub in $SUBS; do
    [ -e "$SRC/$sub" ] || continue
    mkdir -p "$DST/latest/$sub"
    if command -v rsync >/dev/null 2>&1; then
      # 注意：不加 --delete —— 备份只会变多，不会因为源出问题被清掉
      rsync -a "$SRC/$sub/" "$DST/latest/$sub/" 2>/dev/null
    else
      cp -a "$SRC/$sub/." "$DST/latest/$sub/" 2>/dev/null
    fi
  done
  {
    echo "备份时间: $stamp"
    echo "result.json 总数:   $(find "$DST/latest/jobs" -name result.json 2>/dev/null | wc -l)"
    echo "  其中 v2 批次:     $(find "$DST/latest/jobs" -path '*v2-*' -name result.json 2>/dev/null | wc -l)"
    echo "  其中旧批次:       $(find "$DST/latest/jobs" -path '*formal-*' -name result.json 2>/dev/null | wc -l)"
    echo "任务定义(evals):    $(find "$DST/latest/skills" -name evals.json 2>/dev/null | wc -l)"
    echo "题目表:             $(ls "$DST/latest/data" 2>/dev/null | wc -l) 个文件"
    echo "jobs 体积:          $(du -sh "$DST/latest/jobs" 2>/dev/null | cut -f1)"
    echo "总体积:             $(du -sh "$DST/latest" 2>/dev/null | cut -f1)"
  } > "$DST/latest/MANIFEST.txt"
  cp "$DST/latest/MANIFEST.txt" "$DST/LAST_BACKUP.txt" 2>/dev/null
}

if [ "${1:-once}" = "watch" ]; then
  echo "常驻备份启动（每 10 分钟一次）→ $DST"
  n=0
  while true; do
    sync_once
    n=$((n+1))
    if [ $((n % 6)) -eq 0 ]; then     # 每小时一个 tar 快照
      ts=$(date +%m%d-%H%M)
      tar -czf "$DST/snapshots/snap-$ts.tar.gz" -C "$SRC" jobs data results paper code skills 2>/dev/null
      echo "[$(date '+%H:%M')] 快照 snap-$ts.tar.gz 完成"
    fi
    sleep 600
  done
else
  sync_once
  echo "已备份一次 → $DST/latest"
  cat "$DST/latest/MANIFEST.txt"
fi
