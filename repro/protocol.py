"""Shared offline experiment inventory and result validation (stdlib only)."""
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODELS = ("glm-5.3", "glm-5.3-flash", "deepseek-v4-pro", "deepseek-v4-flash", "kimi-k2.7-code")
CONDITIONS = ("baseline", "with-skill")
ERROR_FIELDS = ("error", "error_category", "verifier_error", "verifier_error_category", "export_error",
                "idle_timeout_info", "agent_timeout_info", "sandbox_startup_info", "transport_error_info",
                "verifier_timeout_info", "api_error_info")
RUN_RE = re.compile(r"skill-eval/(?P<skill>[^/]+)/opencode/(?P<cond>baseline|with-skill)/"
                    r"(?P<ts>[^/]+)/(?P<task>[^/]+)__[0-9a-f]+$")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_tasks(path=None):
    path = Path(path or REPO / "data/single_turn_tasks.csv")
    tasks = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            tid, skill = row["task_id"], row["skill_id"]
            if not re.fullmatch(r"[a-z0-9-]+__(?:cn\d+_)?\d+", tid) or not tid.startswith(skill + "__"):
                raise ValueError(f"Invalid task identity: {tid}")
            if tid in tasks:
                raise ValueError(f"Duplicate task: {tid}")
            rubric = json.loads(row["rubric"])
            weights = [c["points"] for c in rubric]
            if not weights or any(type(w) not in (int, float) or not math.isfinite(w) or w <= 0 for w in weights):
                raise ValueError(f"Invalid rubric weights: {tid}")
            if not math.isclose(sum(weights), 100):
                raise ValueError(f"Rubric must total 100: {tid}")
            tasks[tid] = {**row, "rubric": rubric}
    if not tasks:
        raise ValueError("Empty task inventory")
    return tasks


def make_case(task, model, metric, judge_profile='self-v1'):
    if judge_profile not in ('self-v1','fixed-pro-v1','fixed-pro-v2','fixed-pro-v3'):
        raise ValueError('Unknown judge profile')
    case = {'question': task['context']+'\n\n'+task['user_prompt'],
            'ground_truth': task['expected_output'], 'judge_model': model,
            'score_metric': metric,
            'rubric': [{'id': f'C{i+1}', **r} for i, r in enumerate(task['rubric'])]}
    if judge_profile in ('fixed-pro-v1','fixed-pro-v2','fixed-pro-v3'):
        case.update(response_model=model, judge_model='deepseek-v4-pro',
                    judge_profile=judge_profile, arithmetic_audit=True)
    return case


def run_judge_profile(root, model):
    root=Path(root)
    suffix='-'+model
    if root.name.endswith(suffix):
        manifest=root.parent/'protocols'/root.name[:-len(suffix)]/'tasks/manifest.json'
        if manifest.is_file():
            profile=json.loads(manifest.read_text()).get('judge_profile','self-v1')
            if profile not in ('self-v1','fixed-pro-v1','fixed-pro-v2','fixed-pro-v3'):
                raise ValueError('Unknown frozen judge profile')
            return profile
    return 'self-v1'


def task_digest(tasks):
    return hashlib.sha256(json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def dataset_source(name):
    """Resolve an explicit execution suite; historical reporting keeps its old default."""
    if name == 'historical':
        return REPO/'data/single_turn_tasks.csv', CONDITIONS
    if name not in ('core', 'advisory', 'all'):
        raise ValueError('Unknown dataset')
    index = json.loads((REPO/'data/releases/current.json').read_text())
    index = index.get('suite_overrides', {}).get(name, index)
    release = REPO/'data/releases'/index['release']
    if sha256(release/'manifest.json') != index['manifest_sha256']:
        raise ValueError('Release manifest changed')
    manifest = json.loads((release/'manifest.json').read_text())
    for filename, digest in manifest['artifacts'].items():
        if sha256(release/filename) != digest:
            raise ValueError('Release artifact changed: '+filename)
    for filename, digest in manifest['skill_files'].items():
        if sha256(REPO/filename) != digest:
            raise ValueError('Released Skill resource changed: '+filename)
    gate = json.loads((release/'release_gate.json').read_text())
    if gate.get('protocol') == 'source-native-v1':
        raise ValueError('原标准适配版请用 python3 -m repro source-run --dataset '+name+' --out <新目录>；原等级不能交给旧布尔评分器。')
    if not gate['ready']:
        raise ValueError('Execution suite is not ready: '+gate.get('reason', '')+' ['+str(release)+']')
    return release/(name+'.csv'), tuple(gate['allowed_conditions'][name])


def validate_run_binding(jobs_dir, tag, tasks, conditions):
    """Do not attach new answers/rubrics to old results merely because IDs match."""
    jobs_dir = Path(jobs_dir)
    manifest_path = jobs_dir/'protocols'/tag/'tasks/manifest.json'
    if not manifest_path.exists():
        if any(p.is_dir() and next(p.rglob('result.json'), None) is not None for p in jobs_dir.glob(tag+'-*')):
            raise ValueError('Results have no matching frozen protocol; do not relabel historical scores')
        return
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('task_input_sha256') != task_digest(tasks) or manifest.get('conditions') != list(conditions):
        raise ValueError('Requested dataset differs from frozen run inputs/conditions')


def execution_error(data):
    verifier_fields = {'verifier_error', 'verifier_error_category', 'verifier_timeout_info'}
    return next((k for k in ERROR_FIELDS if k not in verifier_fields and data.get(k)), None)


def recovered_verdict(path, data, task, model, judge_profile='self-v1'):
    """Validate a sidecar without changing the original execution record."""
    from judge import cached_verdict, read_trajectory
    dest = path.parent/'scoring_recovery'
    if not (dest/'judge_result.json').exists():
        return None
    if execution_error(data) or data.get('model', '').removeprefix('ark/') != model:
        raise ValueError('Cannot recover an execution failure')
    case = json.loads((dest/'case.json').read_text())
    expected = make_case(task, model, case['score_metric'], judge_profile)
    expected['source_result_sha256'] = sha256(path)
    if case != expected:
        raise ValueError('Recovery inputs changed')
    verdict = cached_verdict(case, read_trajectory(path.parent/'trajectory'), dest)
    return verdict, str(dest/'judge_result.json'), sha256(dest/'judge_result.json')


def expected_cells(tasks, conditions=CONDITIONS):
    return {(r["skill_id"], tid, cond) for tid, r in tasks.items() for cond in conditions}


def result_reason(data, model=None):
    if not isinstance(data, dict):
        return "invalid_result_object"
    recorded_model = data.get("model")
    if model and (not isinstance(recorded_model, str) or recorded_model.removeprefix("ark/") != model):
        return "model_mismatch"
    for key in ERROR_FIELDS:
        if data.get(key):
            return key
    rewards = data.get("rewards")
    value = rewards.get("reward") if isinstance(rewards, dict) else None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        return "invalid_or_missing_reward"
    return None


def choose(runs):
    valid = [r for r in runs if r["valid"]]
    return max(valid or runs, key=lambda r: (r["finished_at"], r["source"]))


def inspect_model(root, model, tasks, conditions=CONDITIONS):
    root = Path(root)
    judge_profile=run_judge_profile(root,model)
    expected = expected_cells(tasks, conditions)
    groups = defaultdict(list)
    errors, excluded = [], 0
    for path in sorted(root.rglob("result.json")):
        if any(p.startswith("_failed_runs_") for p in path.relative_to(root).parts):
            excluded += 1
            continue
        match = RUN_RE.search(path.parent.as_posix())
        if not match:
            errors.append({"source": str(path), "reason": "unrecognized_result_path"})
            continue
        cell = (match["skill"], match["task"], match["cond"])
        try:
            data = json.loads(path.read_text())
            reason = result_reason(data, model)
            if reason is None:
                for log in (path.parent / 'verifier').glob('*.txt'):
                    if 'Could not parse judge response' in log.read_text(errors='replace'):
                        reason = 'judge_parse_failure_recorded_as_reward'
                        break
        except (ValueError, OSError) as exc:
            data, reason = {}, "unreadable_result:" + type(exc).__name__
        recovery = None
        if cell in expected and isinstance(data, dict):
            try:
                recovery = recovered_verdict(path, data, tasks[cell[1]], model, judge_profile)
                if recovery is not None:
                    reason = None
            except (ValueError, OSError, KeyError, TypeError, AttributeError):
                reason = 'invalid_scoring_recovery'
        if judge_profile != 'self-v1' and recovery is None and reason is None:
            reason = 'missing_fixed_judge_verdict'
        if cell not in expected:
            errors.append({"source": str(path), "reason": "unexpected_task_or_condition"})
        if not isinstance(data, dict):
            data = {}
        reward = data["rewards"].get("reward") if isinstance(data.get("rewards"), dict) else None
        if type(reward) not in (int, float) or not math.isfinite(reward):
            reward = None
        if recovery is not None:
            reward = recovery[0]['score']
        groups[cell].append({"source": str(path),
                             "recovery_source": recovery[1] if recovery else None,
                             "recovery_sha256": recovery[2] if recovery else None, "sha256": sha256(path),
                             "finished_at": str(data.get("finished_at") or match["ts"]),
                             "reward": reward, "valid": reason is None, "reason": reason})
    picked = {k: choose(v) for k, v in groups.items() if k in expected}
    valid = {k: r for k, r in picked.items() if r["valid"]}
    missing = [{"model": model, "skill": s, "task_id": tid, "condition": cond,
                "reason": picked.get((s, tid, cond), {}).get("reason") or "not_run"}
               for s, tid, cond in sorted(expected - set(valid))]
    return {"model": model, "judge_profile":judge_profile, "expected": len(expected), "valid": valid,
            "missing": missing, "errors": errors, "picked": picked,
            "attempts": sum(len(v) for v in groups.values()),
            "valid_attempts": sum(r["valid"] for v in groups.values() for r in v),
            "excluded_quarantined_attempts": excluded,
            "complete": not missing and not errors}


def check_models(models):
    if not models or len(set(models)) != len(models) or set(models) - set(MODELS):
        raise ValueError("Choose unique model names from: " + ", ".join(MODELS))
    return models


def check_tag(tag):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", tag):
        raise ValueError("Invalid experiment tag")
    return tag
