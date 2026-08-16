import os,csv,json,urllib.request
from pathlib import Path

base=os.environ["OPENAI_BASE_URL"].rstrip("/")
key=os.environ["OPENAI_API_KEY"]
model=os.environ.get("TASK_GEN_MODEL","qwen3.7-plus")

rows=list(csv.DictReader(open("data/skill_mapping.csv")))
skills=[r for r in rows if r["interaction_type"]=="multi_turn"]
out=[]

for n,s in enumerate(skills,1):
    sid=s["skill_id"]
    print(f"[{n}/{len(skills)}] {sid} ...",flush=True)

    p=list(Path("third_party").rglob(f"{sid}/SKILL.md"))[0]
    skill=p.read_text(errors="ignore")

    prompt=f"""
Create exactly 3 multi-turn benchmark tasks for this educational agent skill.

Skill:
{skill}

Scenario category: {s["edubench_scenario"]}

Rules:
- English only.
- Tasks must be new; do not copy examples from the skill.
- Do NOT mention the skill name or framework in the learner messages.
- difficulties exactly easy, medium, hard.
- The dialogue must test the PROCEDURE, not merely final-answer correctness.
- learner_turn_1 should naturally trigger the skill.
- expected_agent_turn_1 describes required behavior, not exact wording.
- learner_turn_2 should react naturally to turn 1.
- expected_agent_turn_2 describes the next required behavior.
- rubric must have observable criteria totaling exactly 100 points.
- Return JSON only, exactly 3 objects.

Schema:
[
 {{
  "subject":"",
  "education_level":"",
  "difficulty":"easy",
  "initial_context":"",
  "learner_turn_1":"",
  "expected_agent_turn_1":"",
  "learner_turn_2":"",
  "expected_agent_turn_2":"",
  "success_condition":"",
  "rubric":[{{"criterion":"","points":20,"description":""}}]
 }}
]
"""

    body=json.dumps({
        "model":model,
        "messages":[{"role":"user","content":prompt}],
        "temperature":0.35,
        "max_tokens":7000
    }).encode()

    req=urllib.request.Request(
        base+"/chat/completions",
        data=body,
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"}
    )

    txt=json.loads(urllib.request.urlopen(req,timeout=240).read())["choices"][0]["message"]["content"]
    txt=txt[txt.find("["):txt.rfind("]")+1]
    tasks=json.loads(txt)

    if len(tasks)!=3:
        raise RuntimeError(f"{sid}: expected 3 tasks")

    for i,t in enumerate(tasks,1):
        if sum(int(x["points"]) for x in t["rubric"])!=100:
            raise RuntimeError(f"{sid}: rubric != 100")

        out.append({
            "task_id":f"{sid}__{i:02d}",
            "skill_id":sid,
            "edubench_scenario":s["edubench_scenario"],
            "subject":t["subject"],
            "education_level":t["education_level"],
            "difficulty":t["difficulty"],
            "initial_context":t["initial_context"],
            "learner_turn_1":t["learner_turn_1"],
            "expected_agent_turn_1":t["expected_agent_turn_1"],
            "learner_turn_2":t["learner_turn_2"],
            "expected_agent_turn_2":t["expected_agent_turn_2"],
            "success_condition":t["success_condition"],
            "rubric":json.dumps(t["rubric"],ensure_ascii=False)
        })

fields=list(out[0].keys())
with open("data/multi_turn_tasks_generated.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields)
    w.writeheader(); w.writerows(out)

print("generated =",len(out))
print("skills =",len(skills))
print("file = data/multi_turn_tasks_generated.csv")
