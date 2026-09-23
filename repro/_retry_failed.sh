#!/usr/bin/env bash
# _retry_failed.sh -- 补齐"没有有效分数"的格子。
#
# 会处理两类问题（第二类以前漏了）：
#   A. 有运行但失败：超时 / 评委崩溃 / 无分数 —— 把失败运行移到隔离区后重跑
#   B. 连运行目录都没有（比如被中断在"移动后、重跑前"）—— 直接重跑，bench 会补空位
#
# 用法：bash jobs/_retry_failed.sh <模型> [轮数] [目录前缀]
#   目录前缀默认 v2（jobs/v2-<模型>）；处理旧批次传 formal
set -u
R=/home/airlivy/EduSkillBench
cd "$R" || exit 2

# ⚠️ 必须显式加 PATH：用 setsid/nohup 启动时没有登录 shell，bench 会找不到
export PATH="$HOME/.local/bin:$PATH"
source jobs/_env_ark.sh

MODEL="${1:-}"
ROUNDS="${2:-2}"
ROOT="${3:-v2}"
[ -n "$MODEL" ] || { echo "用法: bash jobs/_retry_failed.sh <模型> [轮数] [前缀]"; exit 2; }

OUT="jobs/$ROOT-$MODEL"
PREP="jobs/_${ROOT}_${MODEL}_skills"
[ -d "$OUT" ] || { echo "✗ 没有 $OUT"; exit 2; }
[ -d "$PREP" ] || { echo "✗ 没有技能副本 $PREP"; exit 2; }
command -v bench >/dev/null || { echo "✗ bench 仍不可用（PATH 问题）"; exit 2; }

for round in $(seq 1 "$ROUNDS"); do
  echo "================ 第 $round 轮 ($(date '+%H:%M')) ================"

  # ---- A. 有运行但失败的 ----
  BAD=$(python3 - "$OUT" <<'PY'
import json, glob, os, sys
bad = []
for f in glob.glob(os.path.join(sys.argv[1], "**", "result.json"), recursive=True):
    if "/_failed_runs_" in f.replace("\\", "/"):
        continue                      # 隔离区不重复处理
    try: d = json.load(open(f))
    except Exception: bad.append(os.path.dirname(f)); continue
    if (d.get("error_category") == "timeout" or d.get("verifier_error")
            or (d.get("rewards") or {}).get("reward") is None):
        bad.append(os.path.dirname(f))
print("\n".join(bad))
PY
)
  # ---- B. 连运行目录都没有的格（靠扫 result.json 发现不了）----
  MISS_SKILLS=$(python3 - "$PREP" "$OUT" <<'PY'
import json, glob, os, re, sys
prep, out = sys.argv[1], sys.argv[2]
expected = set()
for ev in glob.glob(os.path.join(prep, "*/evals/evals.json")):
    skill = os.path.basename(os.path.dirname(os.path.dirname(ev)))
    try: d = json.load(open(ev))
    except Exception: continue
    for c in d.get("cases") or []:
        m = re.search(r"__(\d+)$", str(c.get("id", "")))
        if m:
            for cond in ("baseline", "with-skill"):
                expected.add((skill, m.group(1), cond))
present = set()
for f in glob.glob(os.path.join(out, "**", "result.json"), recursive=True):
    p = f.replace("\\", "/")
    if "/_failed_runs_" in p: continue
    m = re.search(r"skill-eval/([^/]+)/opencode/(baseline|with-skill)/[^/]+/[^/]+__(\d+)__", p)
    if not m: continue
    try: d = json.load(open(f))
    except Exception: continue
    if (d.get("rewards") or {}).get("reward") is None: continue
    present.add((m.group(1), m.group(3), m.group(2)))
print("\n".join(sorted({k[0] for k in expected - present})))
PY
)

  NB=$(printf '%s\n' "$BAD" | grep -c . || true)
  NM=$(printf '%s\n' "$MISS_SKILLS" | grep -c . || true)
  echo "  A类(有运行但失败): ${NB:-0} 次运行"
  echo "  B类(缺格子无运行): ${NM:-0} 个技能"

  if [ "${NB:-0}" -eq 0 ] && [ "${NM:-0}" -eq 0 ]; then
    echo "  ✓ 没有需要补的，收工"; break
  fi

  SKILLS=$( { printf '%s\n' "$BAD" | grep . | while read -r d; do
                echo "$d" | sed -n 's|.*skill-eval/\([^/]*\)/.*|\1|p'; done
              printf '%s\n' "$MISS_SKILLS" | grep . ; } | sort -u)

  # 把失败的运行移到隔离区（不删除）
  if [ "${NB:-0}" -gt 0 ]; then
    QUAR="$OUT/_failed_runs_$(date +%m%d-%H%M%S)"
    mkdir -p "$QUAR"
    printf '%s\n' "$BAD" | grep . | while read -r d; do
      rel="${d#$OUT/}"
      mkdir -p "$QUAR/$(dirname "$rel")"
      mv "$d" "$QUAR/$rel" 2>/dev/null || cp -a "$d" "$QUAR/$rel" 2>/dev/null || true
    done
    echo "  失败运行已【移动】（未删除）到: $QUAR"
  fi

  for s in $SKILLS; do
    [ -f "$PREP/$s/evals/evals.json" ] || { echo "  ✗ 缺 $PREP/$s，跳过"; continue; }
    echo "  重跑 $s …"
    if bench skills eval "$PREP/$s" --agent opencode --model "ark/$MODEL" \
        --sandbox docker --concurrency "${RETRY_CONC:-2}" \
        --jobs-dir "$OUT/$s" >> "logs/retry-$ROOT-$MODEL.log" 2>&1; then
      echo "    ok"
    else
      echo "    失败（见 logs/retry-$ROOT-$MODEL.log）"
    fi
  done
done

echo
echo "== 收尾统计 =="
python3 - "$OUT" <<'PY'
import json, glob, os, sys, collections
c = collections.Counter()
for f in glob.glob(os.path.join(sys.argv[1], "**", "result.json"), recursive=True):
    if "/_failed_runs_" in f.replace("\\", "/"): continue
    try: d = json.load(open(f))
    except Exception: c["坏文件"] += 1; continue
    if (d.get("rewards") or {}).get("reward") is not None: c["有分数"] += 1
    elif d.get("verifier_error"): c["评委失败"] += 1
    elif d.get("error_category"): c["运行错误:" + str(d["error_category"])] += 1
    else: c["无分数"] += 1
for k, v in c.most_common(): print(f"  {k}: {v}")
PY
