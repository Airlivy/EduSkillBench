#!/usr/bin/env bash
# _autofix.sh -- 自动修复守护：把"缺格"补到满，全程无人值守。
#
# 每轮做四件事：
#   1. 清掉陈旧的 litellm 代理进程（防内存泄漏累积）
#   2. 扫出所有缺格（含"连运行目录都没有"的 B 类）
#   3. 只针对缺的那一格并行补跑（裁试卷，不重跑整个技能）
#   4. 复检，满格即退出
#
# 用法：setsid nohup bash jobs/_autofix.sh [最多轮数] > logs/autofix.log 2>&1 &
set -u
R=/home/airlivy/EduSkillBench
cd "$R" || exit 2
export PATH="$HOME/.local/bin:$PATH"
source jobs/_env_ark.sh
source jobs/_guard.sh
guard_acquire "autofix" || exit 2      # 单实例锁：防止与跑批/其它补缺并发压垮机器
guard_start_watch                       # 自动清理泄漏的 litellm 代理
command -v bench >/dev/null || { echo "✗ bench 不可用（PATH）"; exit 2; }
ROOT="${1:-v2}"
MAX_ROUNDS="${MAX_ROUNDS:-30}"
INTERVAL="${INTERVAL:-600}"      # 每轮间隔（秒）
MODELS="glm-5.3 glm-5.3-flash deepseek-v4-pro deepseek-v4-flash kimi-k2.7-code"

echo "=== 自动修复守护启动 $(date '+%F %H:%M') · 前缀=$ROOT · 最多 $MAX_ROUNDS 轮 ==="

find_missing() {   # 输出：模型|技能|题号
python3 - "$ROOT" "$MODELS" <<'PY'
import json, glob, os, re, sys
root, models = sys.argv[1], sys.argv[2].split()
for m in models:
    prep, outdir = f"jobs/_{root}_{m}_skills", f"jobs/{root}-{m}"
    if not os.path.isdir(outdir): continue
    expected = set()
    for ev in glob.glob(os.path.join(prep, "*/evals/evals.json")):
        skill = os.path.basename(os.path.dirname(os.path.dirname(ev)))
        try: d = json.load(open(ev))
        except Exception: continue
        for c in d.get("cases") or []:
            mm = re.search(r"__(\d+)$", str(c.get("id","")))
            if mm:
                for cond in ("baseline","with-skill"):
                    expected.add((skill, mm.group(1), cond))
    present = set()
    for f in glob.glob(os.path.join(outdir, "**", "result.json"), recursive=True):
        p = f.replace("\\","/")
        if "/_failed_runs_" in p: continue
        mm = re.search(r"skill-eval/([^/]+)/opencode/(baseline|with-skill)/[^/]+/[^/]+__(\d+)__", p)
        if not mm: continue
        try: dd = json.load(open(f))
        except Exception: continue
        if (dd.get("rewards") or {}).get("reward") is None: continue
        present.add((mm.group(1), mm.group(3), mm.group(2)))
    for k in sorted(expected - present):
        print(f"{m}|{k[0]}|{k[1]}")
PY
}

for round in $(seq 1 "$MAX_ROUNDS"); do
  echo
  echo "---------- 第 $round 轮 $(date '+%H:%M') ----------"

  # 1) 清掉超过 1 小时的 litellm 残留
  killed=0
  for pid in $(pgrep litellm 2>/dev/null); do
    et=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')
    [ -z "$et" ] && continue
    [ "$et" -gt 3600 ] && kill "$pid" 2>/dev/null && killed=$((killed+1))
  done
  [ "$killed" -gt 0 ] && echo "  清理陈旧 litellm 进程: $killed 个"

  # 2) 扫缺格
  MISS=$(find_missing)
  N=$(printf '%s\n' "$MISS" | grep -c . || true)
  if [ "${N:-0}" -eq 0 ]; then
    echo "  ✅ 满格，无需修复 —— 守护退出"
    python3 jobs/_validity_check.py --all --root "$ROOT" 2>&1 | grep 有效格
    exit 0
  fi
  echo "  发现 $N 个缺格，开始并行补跑（只跑缺的格）"

  # 3) 并行补跑（每个缺格单独裁试卷）
  # 去重：同一 (模型,技能,题号) 只跑一次（同一题的两个条件会一起补）
  COMBOS=$(printf '%s\n' "$MISS" | grep . | sort -u)
  echo "  去重后需补跑: $(printf '%s\n' "$COMBOS" | grep -c .) 个 (模型,技能,题号) 组合"

  PIDS=""
  while IFS='|' read -r MODEL SKILL CASE; do
    [ -z "${MODEL:-}" ] && continue
    guard_wait_memory          # 内存不足就等，别硬冲
    guard_wait_containers      # 容器数到上限就等
    TMP="/tmp/autofix_${MODEL}_${SKILL}_${CASE}"
    rm -rf "$TMP"; mkdir -p "$TMP"
    cp -r "jobs/_${ROOT}_${MODEL}_skills/$SKILL" "$TMP/"
    python3 - "$TMP/$SKILL/evals/evals.json" "$MODEL" "$CASE" <<'PY'
import json, sys
p, model, case = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(p))
d.setdefault("defaults", {})["judge_model"] = model
d.setdefault("defaults", {})["timeout_sec"] = 600
d["cases"] = [c for c in d.get("cases") or [] if str(c.get("id","")).endswith("__" + case)]
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
PY
    setsid nohup bash -lc "bench skills eval '$TMP/$SKILL' --agent opencode \
        --model 'ark/$MODEL' --sandbox docker --concurrency 2 \
        --jobs-dir 'jobs/$ROOT-$MODEL/$SKILL'" \
        > "logs/autofix-${MODEL}-${SKILL}-${CASE}.log" 2>&1 < /dev/null &
    PIDS="$PIDS $!"
    echo "    → $MODEL / $SKILL / case$CASE"
    sleep 2
  done <<< "$COMBOS"
  # 按 PID 等待（不要用名字匹配——临时目录名和模式对不上会立刻退出）
  for p in $PIDS; do wait "$p" 2>/dev/null || true; done
  echo "  本轮补跑结束 $(date '+%H:%M')"

  # 4) 复检
  python3 jobs/_validity_check.py --all --root "$ROOT" 2>&1 | grep 有效格 | sed 's/^/    /'
  echo "  等 ${INTERVAL}s 后进入下一轮…"
  sleep "$INTERVAL"
done
echo "=== 达到最大轮数，守护退出 $(date '+%F %H:%M') ==="
