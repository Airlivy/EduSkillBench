import json, csv, re
from pathlib import Path
from collections import defaultdict

FORMAL = Path("jobs/formal-single-v1")
RETRY = Path("jobs/spaced-case3-retry")
OUT = Path("results")
OUT.mkdir(exist_ok=True)

ERR_FIELDS = [
    "error", "verifier_error", "export_error",
    "transport_error_info", "api_error_info",
    "idle_timeout_info", "agent_timeout_info",
    "verifier_timeout_info"
]

def load_result(p):
    d = json.loads(p.read_text())
    parts = p.parts
    skill = parts[parts.index("skill-eval") + 1]
    mode = "with-skill" if "with-skill" in parts else "baseline"

    m = re.search(r"__(\d+)__", p.parent.name)
    case = m.group(1) if m else "?"

    reward = d.get("rewards", {}).get("reward")
    clean = reward is not None and not any(d.get(x) for x in ERR_FIELDS)

    return {
        "skill": skill,
        "mode": mode,
        "case": case,
        "reward": reward,
        "clean": clean,
        "finished_at": d.get("finished_at", ""),
        "n_tool_calls": d.get("n_tool_calls", 0),
        "n_skill_invocations": d.get("n_skill_invocations", 0),
        "total_tokens": d.get("agent_result", {}).get("total_tokens", 0),
        "total_time_sec": d.get("timing", {}).get("total"),
        "source": str(p),
    }

# 1. Formal results: deduplicate, prefer clean + latest
groups = defaultdict(list)
for p in FORMAL.rglob("result.json"):
    r = load_result(p)
    groups[(r["skill"], r["mode"], r["case"])].append(r)

chosen = {}
for k, xs in groups.items():
    chosen[k] = sorted(
        xs,
        key=lambda x: (x["clean"], x["finished_at"]),
        reverse=True
    )[0]

# 2. Only use retry results to replace failed formal runs
if RETRY.exists():
    retry_groups = defaultdict(list)
    for p in RETRY.rglob("result.json"):
        r = load_result(p)
        retry_groups[(r["skill"], r["mode"], r["case"])].append(r)

    for k, old in list(chosen.items()):
        if old["clean"]:
            continue
        candidates = [x for x in retry_groups.get(k, []) if x["clean"]]
        if candidates:
            chosen[k] = sorted(
                candidates,
                key=lambda x: x["finished_at"],
                reverse=True
            )[0]

rows = sorted(chosen.values(),
              key=lambda x: (x["skill"], x["mode"], x["case"]))

bad = [r for r in rows if not r["clean"]]

print(f"unique_runs = {len(rows)}")
print(f"clean_runs  = {len(rows)-len(bad)}")

if len(rows) != 84 or bad:
    print("PROBLEM:")
    for r in bad:
        print(r["skill"], r["mode"], r["case"], r["source"])
    raise SystemExit(1)

# Run-level CSV
run_fields = [
    "skill", "mode", "case", "reward", "full_score",
    "n_tool_calls", "n_skill_invocations",
    "total_tokens", "total_time_sec", "source"
]

with open(OUT/"single_turn_runs_v1.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=run_fields)
    w.writeheader()
    for r in rows:
        x = {k: r.get(k) for k in run_fields if k != "full_score"}
        x["full_score"] = int(abs(float(r["reward"]) - 1.0) < 1e-9)
        w.writerow(x)

# Skill-level summary
by_skill = defaultdict(list)
for r in rows:
    by_skill[r["skill"]].append(r)

summaries = []

for skill, xs in sorted(by_skill.items()):
    ws = [x for x in xs if x["mode"] == "with-skill"]
    bs = [x for x in xs if x["mode"] == "baseline"]

    ws_avg = sum(x["reward"] for x in ws) / len(ws)
    bs_avg = sum(x["reward"] for x in bs) / len(bs)

    ws_full = sum(abs(x["reward"]-1.0) < 1e-9 for x in ws)
    bs_full = sum(abs(x["reward"]-1.0) < 1e-9 for x in bs)

    invoked = sum(x["n_skill_invocations"] > 0 for x in ws)

    summaries.append({
        "skill": skill,
        "with_skill_avg_reward": round(ws_avg, 4),
        "baseline_avg_reward": round(bs_avg, 4),
        "reward_lift": round(ws_avg-bs_avg, 4),
        "with_skill_full_score": ws_full,
        "baseline_full_score": bs_full,
        "full_score_lift": ws_full-bs_full,
        "skill_invocation_rate": round(invoked/len(ws), 4),
        "avg_skill_invocations": round(
            sum(x["n_skill_invocations"] for x in ws)/len(ws), 4
        ),
    })

with open(OUT/"single_turn_skill_summary_v1.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=summaries[0].keys())
    w.writeheader()
    w.writerows(summaries)

# Overall
ws = [r for r in rows if r["mode"] == "with-skill"]
bs = [r for r in rows if r["mode"] == "baseline"]

wa = sum(r["reward"] for r in ws)/len(ws)
ba = sum(r["reward"] for r in bs)/len(bs)
inv = sum(r["n_skill_invocations"] > 0 for r in ws)/len(ws)

overall = {
    "skills": len(by_skill),
    "tasks": len(ws),
    "runs": len(rows),
    "with_skill_avg_reward": round(wa, 4),
    "baseline_avg_reward": round(ba, 4),
    "reward_lift": round(wa-ba, 4),
    "skill_invocation_rate": round(inv, 4),
    "positive_lift_skills": sum(x["reward_lift"] > 0 for x in summaries),
    "zero_lift_skills": sum(x["reward_lift"] == 0 for x in summaries),
    "negative_lift_skills": sum(x["reward_lift"] < 0 for x in summaries),
}

(OUT/"single_turn_overall_v1.json").write_text(
    json.dumps(overall, indent=2)
)

print()
for k,v in overall.items():
    print(f"{k} = {v}")

print("\nSaved:")
print("results/single_turn_runs_v1.csv")
print("results/single_turn_skill_summary_v1.csv")
print("results/single_turn_overall_v1.json")
