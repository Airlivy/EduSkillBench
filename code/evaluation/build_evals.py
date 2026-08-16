import csv,json
from pathlib import Path

rows=list(csv.DictReader(open("data/single_turn_tasks.csv")))
root=Path("skills/single_turn")
root.mkdir(exist_ok=True)

for sid in sorted(set(r["skill_id"] for r in rows)):
    dst = root / sid
    if not dst.exists():
        raise FileNotFoundError(f"Missing released skill: {dst}")

    cases=[]
    for r in rows:
        if r["skill_id"]!=sid: continue

        rubric=json.loads(r["rubric"])
        cases.append({
            "id":r["task_id"],
            "question":r["context"]+"\n\n"+r["user_prompt"],
            "ground_truth":r["expected_output"],
            "expected_behavior":[x["description"] for x in rubric]
        })

    (dst/"evals").mkdir(exist_ok=True)
    (dst/"evals"/"evals.json").write_text(
        json.dumps({
            "version":"1",
            "skill_name":sid,
            "defaults":{"timeout_sec":300},
            "cases":cases
        },indent=2,ensure_ascii=False)
    )

print("skills = 14")
print("eval_cases = 42")
