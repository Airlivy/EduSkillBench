#!/usr/bin/env bash
# _verify_judge.sh -- 用【1 道题】验证评委能不能出分（跑批前的必做检查）
#   跑 lesson-builder 的 case 01、单模型、单条件 → 看 verifier 有没有写出 reward
set -u
R=/home/airlivy/EduSkillBench
cd "$R" || exit 2
source jobs/_env_ark.sh
MODEL="${1:-glm-5.3}"

command -v bench >/dev/null || { echo "✗ 找不到 bench"; exit 2; }
ss -ltn 2>/dev/null | grep -q ':8123' || {
  ( cd .nodecache && nohup python3 -m http.server 8123 --bind 0.0.0.0 \
      >> ../logs/nodecache-server.out 2>&1 & )
  sleep 2; }

echo "== 环境 =="
source jobs/_env_ark.sh --check

PREP="/tmp/judgecheck_skills"
rm -rf "$PREP"; mkdir -p "$PREP"
cp -r skills/single_turn/lesson-builder "$PREP/"
python3 - "$PREP" "$MODEL" <<'PY'
import json, pathlib, sys
prep, model = pathlib.Path(sys.argv[1]), sys.argv[2]
p = prep / "lesson-builder" / "evals" / "evals.json"
d = json.loads(p.read_text())
d.setdefault("defaults", {})["judge_model"] = model
d.setdefault("defaults", {})["timeout_sec"] = 600
d["cases"] = [c for c in d["cases"] if c["id"].endswith("__01")]
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print(f"  试卷裁成 1 个 case：{d['cases'][0]['id']}，评委模型={model}")
PY

OUT="jobs/judgecheck-$MODEL"
rm -rf "$OUT"
echo
echo "== 开跑（1 题 × 2 条件）=="
bench skills eval "$PREP/lesson-builder" \
  --agent opencode --model "ark/$MODEL" --sandbox docker \
  --concurrency 1 --jobs-dir "$OUT" 2>&1 | tail -20

echo
echo "== 结果：评委出分了吗 =="
python3 - "$OUT" <<'PY'
import json, glob, os, sys
found = 0
for f in glob.glob(os.path.join(sys.argv[1], "**", "result.json"), recursive=True):
    d = json.load(open(f))
    rw = (d.get("rewards") or {}).get("reward")
    ve = d.get("verifier_error")
    print(f"  {os.path.basename(os.path.dirname(f))[:40]:42s} reward={rw} "
          f"verifier_error={'有' if ve else '无'}")
    if rw is not None:
        found += 1
print()
print("  ✅ 评委正常出分" if found else "  ❌ 评委仍然出不了分 —— 看 verifier/test-stdout.txt")
PY
