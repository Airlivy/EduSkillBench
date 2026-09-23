#!/usr/bin/env bash
# _smoke_force_skill.sh -- 用 deepseek-v4-flash 小批验证"强制注入技能"。
#   1 个技能 × 3 道题 × 2 条件 = 6 次运行，输出到独立目录（不混入 v2）
set -u
R=/home/airlivy/EduSkillBench
cd "$R" || exit 2
export PATH="$HOME/.local/bin:$PATH"
source jobs/_env_ark.sh
source jobs/_guard.sh
guard_acquire "smoke-force-skill" || exit 2

# 容器装 opencode 需要本地包缓存服务；没起就自动拉起（2026-09 踩过的坑）
if ! ss -ltn 2>/dev/null | grep -q ':8123'; then
  ( cd .nodecache && nohup python3 -m http.server 8123 --bind 0.0.0.0 \
      >> ../logs/nodecache-server.out 2>&1 & )
  sleep 2
fi
ss -ltn 2>/dev/null | grep -q ':8123' || { echo '✗ 缓存服务起不来，容器会装不上 opencode'; exit 2; }
guard_start_watch

MODEL=deepseek-v4-flash
SKILL=hinge-question-designer
OUT="jobs/forcecheck-$MODEL"
PREP="/tmp/forcecheck_${SKILL}"
rm -rf "$OUT" "$PREP"; mkdir -p "$PREP"
cp -r "skills/single_turn/$SKILL" "$PREP/"
python3 - "$PREP/$SKILL/evals/evals.json" "$MODEL" <<'PY'
import json, sys
p, model = sys.argv[1], sys.argv[2]
d = json.load(open(p))
d.setdefault("defaults", {})["judge_model"] = model
d.setdefault("defaults", {})["timeout_sec"] = 600
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
print(f"  试卷: {len(d['cases'])} 个 case · 评委={model}")
PY

echo
echo "=== 跑 3 题 × 2 条件（共 6 次运行）==="
bench skills eval "$PREP/$SKILL" --agent opencode --model "ark/$MODEL" \
  --sandbox docker --concurrency 2 --jobs-dir "$OUT/$SKILL" 2>&1 | tail -14

echo
echo "=== 验证1：带技能运行的题面里有没有技能说明 ==="
python3 - "$OUT" "$SKILL" <<'PY'
import json, glob, os, sys
out, skill = sys.argv[1], sys.argv[2]
for pj in glob.glob(os.path.join(out, "**", "prompts.json"), recursive=True):
    cond = "with-skill" if "/with-skill/" in pj.replace("\\","/") else "baseline"
    txt = open(pj, encoding="utf-8").read()
    has = "Required procedure" in txt or "SKILL.md" in txt
    print(f"  {cond:11s} 题面 {len(txt):>7,} 字符 · 含技能注入: {'✅' if has else '—'}")
PY

echo
echo "=== 验证2：6 次运行是否都判到了分 ==="
python3 - "$OUT" <<'PY'
import json, glob, os, sys
rows = []
for f in glob.glob(os.path.join(sys.argv[1], "**", "result.json"), recursive=True):
    d = json.load(open(f))
    p = f.replace("\\","/")
    cond = "with-skill" if "/with-skill/" in p else "baseline"
    m = None
    import re
    mm = re.search(r"__(\d+)__", p)
    if mm: m = mm.group(1)
    rows.append((m or "?", cond, (d.get("rewards") or {}).get("reward"),
                 d.get("n_tool_calls"), str(d.get("error"))[:40]))
for m, cond, rw, tc, err in sorted(rows):
    print(f"  case{m} {cond:11s} reward={rw} 工具调用={tc} {err if err!='None' else ''}")
import statistics
for cond in ("baseline","with-skill"):
    v = [r[2] for r in rows if r[1]==cond and r[2] is not None]
    if v: print(f"  {cond:11s} 均值 = {statistics.mean(v):.3f}（{len(v)} 条）")
PY
