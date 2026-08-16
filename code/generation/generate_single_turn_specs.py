import os
import csv
import json
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

MAPPING = Path("data/skill_mapping.csv")
OUTPUT = Path("data/single_turn_tasks_generated.csv")
RAW_DIR = Path("data/raw_generations")
META = Path("data/generation_meta.json")

MODEL = os.environ.get("TASK_GEN_MODEL")
API_KEY = os.environ.get("OPENAI_API_KEY")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

if not MODEL:
    raise SystemExit("ERROR: set TASK_GEN_MODEL")
if not API_KEY:
    raise SystemExit("ERROR: OPENAI_API_KEY is not set")

RAW_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM = """
You are constructing EduSkillBench, a benchmark for measuring the incremental
value of reusable educational agent Skills.

Generate benchmark TASKS, not demonstrations of the Skill.

Critical rules:
1. Base each task on the actual behavior and constraints in the supplied SKILL.md.
2. The user prompt must NEVER mention the Skill name, SKILL.md, benchmark,
   curated skill, or tell the model to follow a particular framework.
3. A capable model without the Skill must still be able to attempt the task.
   The Skill should provide a procedural or pedagogical advantage.
4. Do not copy scenarios or examples from SKILL.md. Create new situations.
5. Make the three tasks meaningfully different in subject/context.
6. Use at least two different education levels when pedagogically appropriate.
7. Difficulties must be exactly: easy, medium, hard.
8. All benchmark task content must be in English.
9. No web browsing, external files, or unavailable tools may be required.
10. Rubrics must evaluate observable output quality, not whether the Skill
    was invoked or named.
11. Derive rubric criteria from the Skill's actual procedure, output schema,
    iron rules, and self-check requirements.
12. Rubric points must total exactly 100.

Return ONLY a valid JSON array containing exactly three objects.

Each object must have:
{
  "subject": "...",
  "education_level": "...",
  "difficulty": "easy|medium|hard",
  "context": "...",
  "user_prompt": "...",
  "expected_output": "...",
  "rubric": [
    {
      "criterion": "...",
      "points": 20,
      "description": "Observable scoring rule..."
    }
  ]
}
""".strip()


def find_skill(skill_id):
    matches = list(Path("third_party").rglob(f"{skill_id}/SKILL.md"))
    if not matches:
        raise FileNotFoundError(skill_id)
    return matches[0]


def trim_skill(text, limit=60000):
    if len(text) <= limit:
        return text
    return text[:50000] + "\n\n[...middle truncated...]\n\n" + text[-10000:]


def extract_json(text):
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("[")
    end = text.rfind("]")

    if start < 0 or end < start:
        raise ValueError("No JSON array found")

    return json.loads(text[start:end+1])


def validate(tasks):
    if not isinstance(tasks, list) or len(tasks) != 3:
        raise ValueError("Expected exactly 3 tasks")

    expected_diff = ["easy", "medium", "hard"]

    required = {
        "subject",
        "education_level",
        "difficulty",
        "context",
        "user_prompt",
        "expected_output",
        "rubric",
    }

    for i, task in enumerate(tasks):
        missing = required - set(task)
        if missing:
            raise ValueError(f"Missing fields: {missing}")

        if task["difficulty"] != expected_diff[i]:
            raise ValueError(
                f"Task {i+1} difficulty must be {expected_diff[i]}"
            )

        if not isinstance(task["rubric"], list) or len(task["rubric"]) < 4:
            raise ValueError("Rubric must contain at least 4 criteria")

        total = sum(int(x["points"]) for x in task["rubric"])
        if total != 100:
            raise ValueError(f"Rubric total={total}, expected 100")

        forbidden = [
            "SKILL.md",
            "curated skill",
            "EduSkillBench",
            "benchmark skill",
        ]

        prompt_lower = task["user_prompt"].lower()
        for x in forbidden:
            if x.lower() in prompt_lower:
                raise ValueError(f"Prompt leakage: {x}")

    return True


def call_model(skill_id, scenario, skill_text):
    prompt = f"""
EDUBENCH SCENARIO:
{scenario}

SKILL ID (metadata only; never expose this name in the generated task):
{skill_id}

SOURCE SKILL DEFINITION:
------------------------
{trim_skill(skill_text)}
------------------------

Generate exactly three new benchmark tasks.

Task 1 = easy
Task 2 = medium
Task 3 = hard

The tasks should naturally create situations where the supplied educational
procedure is useful, while remaining solvable in principle without it.

Return JSON only.
""".strip()

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.35,
        "max_tokens": 6500,
    }

    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=240) as r:
        response = json.loads(r.read().decode("utf-8"))

    content = response["choices"][0]["message"]["content"]
    tasks = extract_json(content)
    validate(tasks)
    return tasks


rows = list(csv.DictReader(MAPPING.open(encoding="utf-8")))
skills = [
    r for r in rows
    if r["interaction_type"] == "single_turn"
]

generated_rows = []
failures = []

for skill in skills:
    sid = skill["skill_id"]
    print(f"[{len(generated_rows)//3+1}/{len(skills)}] {sid} ...", flush=True)
    scenario = skill["edubench_scenario"]
    raw_path = RAW_DIR / f"{sid}.json"

    try:
        skill_path = find_skill(sid)
        skill_text = skill_path.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        tasks = None

        if raw_path.exists():
            try:
                cached = json.loads(raw_path.read_text(encoding="utf-8"))
                tasks = cached["tasks"]
                validate(tasks)
            except Exception:
                tasks = None

        if tasks is None:
            last_error = None

            for attempt in range(3):
                try:
                    tasks = call_model(
                        sid,
                        scenario,
                        skill_text
                    )
                    break
                except Exception as e:
                    last_error = e
                    time.sleep(3 * (attempt + 1))

            if tasks is None:
                raise last_error

            raw_path.write_text(
                json.dumps(
                    {
                        "skill_id": sid,
                        "scenario": scenario,
                        "source_skill_path": str(skill_path),
                        "source_sha256": hashlib.sha256(
                            skill_text.encode("utf-8")
                        ).hexdigest(),
                        "generation_model": MODEL,
                        "tasks": tasks,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        for i, task in enumerate(tasks, 1):
            generated_rows.append({
                "task_id": f"{sid}__{i:02d}",
                "skill_id": sid,
                "edubench_scenario": scenario,
                "subject": task["subject"],
                "education_level": task["education_level"],
                "difficulty": task["difficulty"],
                "context": task["context"],
                "user_prompt": task["user_prompt"],
                "expected_output": task["expected_output"],
                "rubric": json.dumps(
                    task["rubric"],
                    ensure_ascii=False
                ),
            })

    except Exception as e:
        failures.append((sid, str(e)[:160]))


fields = [
    "task_id",
    "skill_id",
    "edubench_scenario",
    "subject",
    "education_level",
    "difficulty",
    "context",
    "user_prompt",
    "expected_output",
    "rubric",
]

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(generated_rows)


META.write_text(
    json.dumps(
        {
            "prompt_version": "single-turn-v2.1",
            "generation_model": MODEL,
            "generated_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "number_of_skills": len(skills),
            "expected_tasks": 42,
            "generated_tasks": len(generated_rows),
            "failed_skills": [x[0] for x in failures],
        },
        indent=2,
    ),
    encoding="utf-8",
)


if failures:
    print(
        f"generated={len(generated_rows)} "
        f"failed_skills={len(failures)}"
    )
    for sid, err in failures:
        print(f"FAILED {sid}: {err}")
    raise SystemExit(1)

print(f"generated={len(generated_rows)}")
print(f"skills={len(skills)}")
print(f"file={OUTPUT}")
