"""build_evals_cn263.py -- 把 263 道扩展题（v2 任务集）编译成 bench 能跑的 evals.json。

与 build_evals.py 的关系：
  build_evals.py      读 data/single_turn_tasks.csv        → 写 skills/single_turn/        （v1，已发表）
  build_evals_cn263.py 读 data/single_turn_tasks_cn263.csv → 写 skills/single_turn_cn263/   （v2，本文件）

**两套目录完全隔开**：本脚本只写 skills/single_turn_cn263/，不碰 skills/single_turn/，
因此 v1 的 42 例配置与论文数字的可复现性不受影响。

技能目录从 v1 复制 SKILL.md（技能本体不变），只新生成 evals/evals.json。

用法（在仓库根目录）：python3 code/evaluation/build_evals_cn263.py
"""
import csv, json, shutil
from pathlib import Path

SRC_CSV = Path("data/single_turn_tasks_cn263.csv")
V1_ROOT = Path("skills/single_turn")
V2_ROOT = Path("skills/single_turn_cn263")

if not SRC_CSV.exists():
    raise SystemExit(f"找不到 {SRC_CSV}")

rows = list(csv.DictReader(open(SRC_CSV, encoding="utf-8")))
V2_ROOT.mkdir(exist_ok=True)

total = 0
for sid in sorted(set(r["skill_id"] for r in rows)):
    src = V1_ROOT / sid
    if not (src / "SKILL.md").exists():
        raise FileNotFoundError(f"v1 里没有这个技能的 SKILL.md：{src}")

    dst = V2_ROOT / sid
    (dst / "evals").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "SKILL.md", dst / "SKILL.md")

    cases = []
    for r in rows:
        if r["skill_id"] != sid:
            continue
        rubric = json.loads(r["rubric"])
        cases.append({
            "id": r["task_id"],
            "question": r["context"] + "\n\n" + r["user_prompt"],
            "ground_truth": r["expected_output"],
            "expected_behavior": [x["description"] for x in rubric],
        })

    (dst / "evals" / "evals.json").write_text(
        json.dumps({
            "version": "1",
            "skill_name": sid,
            "defaults": {"timeout_sec": 300},
            "cases": cases,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  {sid:<48} {len(cases):>3} 例")
    total += len(cases)

print(f"\nskills = {len(set(r['skill_id'] for r in rows))}")
print(f"eval_cases = {total}")
print(f"输出目录 = {V2_ROOT}/")
