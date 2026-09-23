#!/usr/bin/env bash
# _run_batch.sh -- 统一到 ark 的正式跑批（v2）
#
# 特点：
#   * 环境走 jobs/_env_ark.sh（agent + 评委都用 ark，已修 base URL 覆盖问题）
#   * 容器用预装镜像 bf-baked:v1（node+opencode 已烤进去）
#   * 输出到【新目录】 jobs/v2-<模型>，不覆盖旧的 formal-*（旧数据留着对比，也避免被跳过）
#   * 缓存服务自动拉起；一次最多并行 4 个模型（把容器总数压在 8 个以内，实测安全）
#   * 跑完自动做完整性检查（缺格会列出来）
#
# 用法：
#   bash jobs/_run_batch.sh                       # 默认 5 个模型，每模型并发 2
#   bash jobs/_run_batch.sh "glm-5.3 kimi-k2.7-code"
#   CONC=2 MAXPAR=4 bash jobs/_run_batch.sh
set -u
R=/home/airlivy/EduSkillBench
cd "$R" || exit 2
export PATH="$HOME/.local/bin:$PATH"
source jobs/_env_ark.sh
source jobs/_guard.sh
guard_acquire "run_batch" || exit 2    # 单实例锁：禁止并发跑批（2026-09-21 事故的根因）
guard_start_watch                       # 自动清理泄漏的 litellm 代理

MODELS="${1:-glm-5.3 glm-5.3-flash deepseek-v4-pro deepseek-v4-flash kimi-k2.7-code}"
CONC="${CONC:-2}"
MAXPAR="${MAXPAR:-4}"
SKILL_SRC="skills/single_turn"
TAG="${TAG:-v2}"

command -v bench >/dev/null || { echo "✗ 找不到 bench（用登录 shell）"; exit 2; }
docker info >/dev/null 2>&1 || { echo "✗ Docker 没在跑"; exit 2; }

# 缓存服务（容器取 opencode 包用）
if ! ss -ltn 2>/dev/null | grep -q ':8123'; then
  echo "→ 启动缓存服务"
  ( cd .nodecache && nohup python3 -m http.server 8123 --bind 0.0.0.0 \
      >> ../logs/nodecache-server.out 2>&1 & )
  sleep 2
fi
ss -ltn 2>/dev/null | grep -q ':8123' && echo "✓ 缓存服务在跑" || { echo "✗ 缓存服务起不来"; exit 2; }

echo "模型: $MODELS"
echo "每模型并发: $CONC · 最多并行模型数: $MAXPAR · 输出: jobs/$TAG-<模型>"
echo "开始时间: $(date '+%m-%d %H:%M')"
echo

# 准备各模型的技能副本（注入 judge_model / timeout）
for m in $MODELS; do
  PREP="jobs/_${TAG}_${m}_skills"
  rm -rf "$PREP"; mkdir -p "$PREP"
  cp -r "$SKILL_SRC"/. "$PREP"/
  python3 - "$PREP" "$m" <<'PY'
import json, pathlib, sys
prep, model = pathlib.Path(sys.argv[1]), sys.argv[2]
n = 0
for ev in prep.glob("*/evals/evals.json"):
    d = json.loads(ev.read_text())
    d.setdefault("defaults", {})["judge_model"] = model
    d.setdefault("defaults", {})["timeout_sec"] = 600
    ev.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n"); n += 1
print(f"  prep {model}: {n} 个技能")
PY
done

# 逐批并行（每批最多 MAXPAR 个模型）
run_model() {
  m="$1"
  OUT="jobs/$TAG-$m"; PREP="jobs/_${TAG}_${m}_skills"
  mkdir -p "$OUT"
  for s in "$PREP"/*; do
    [ -f "$s/evals/evals.json" ] || continue
    b=$(basename "$s")
    bench skills eval "$s" --agent opencode --model "ark/$m" \
      --sandbox docker --concurrency "$CONC" --jobs-dir "$OUT/$b" \
      >> "logs/$TAG-$m.log" 2>&1
  done
  echo "  [$(date '+%H:%M')] $m 跑完"
}

i=0
for m in $MODELS; do
  run_model "$m" &
  i=$((i+1))
  if [ $((i % MAXPAR)) -eq 0 ]; then wait; fi
done
wait
echo
echo "全部结束: $(date '+%m-%d %H:%M')"
echo
echo "== 各模型完成情况 =="
for m in $MODELS; do
  n=$(find "jobs/$TAG-$m" -name result.json 2>/dev/null | wc -l)
  echo "  $TAG-$m: $n / 84"
done
echo
echo "== 完整性检查（缺格会被列出）=="
python3 jobs/_validity_check.py --all --root "$TAG" 2>&1 | head -20
