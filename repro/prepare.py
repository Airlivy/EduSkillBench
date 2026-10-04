"""Build isolated, inspectable tasks without editing installed BenchFlow."""
import argparse
import json
import shutil
from pathlib import Path
from profiles import PROFILES, opencode_config
from judge import THINKING_POLICY, MINIMAL_MODEL_OPTIONS
from protocol import REPO, MODELS, CONDITIONS, check_models, load_tasks, sha256, make_case, dataset_source, task_digest

TEST_SH = '''#!/usr/bin/env bash
set -euo pipefail
VERIFIER_DIR="${BENCHFLOW_VERIFIER_DIR:-/tests}"
if [ ! -f "$VERIFIER_DIR/case.json" ]; then VERIFIER_DIR=/tests; fi
export BENCHFLOW_VERIFIER_DIR="$VERIFIER_DIR"
DETAILS="${BENCHFLOW_REWARD_DETAILS_JSON:-/logs/verifier/judge_result.json}"
mkdir -p "$(dirname "$DETAILS")"
trap 'for f in "$VERIFIER_DIR"/judge_raw_*.txt "$VERIFIER_DIR"/judge_response_*.json "$VERIFIER_DIR"/judge_trace_*.json "$VERIFIER_DIR"/judge_failure_*.json "$VERIFIER_DIR"/judge_error.json; do
  if [ -f "$f" ]; then cp "$f" "$(dirname "$DETAILS")/"; fi
done' EXIT
python3 "$VERIFIER_DIR/judge.py"
TEXT="${BENCHFLOW_REWARD_TEXT:-/logs/verifier/reward.txt}"
JSON="${BENCHFLOW_REWARD_JSON:-/logs/verifier/reward.json}"
mkdir -p "$(dirname "$TEXT")" "$(dirname "$JSON")"
cp "$VERIFIER_DIR/reward.txt" "$TEXT"
cp "$VERIFIER_DIR/reward.json" "$JSON"
cp "$VERIFIER_DIR/judge_result.json" "$DETAILS"
'''


def skill_files(skill_dir):
    return {p.relative_to(skill_dir).as_posix(): sha256(p)
            for p in sorted(skill_dir.rglob('*')) if p.is_file()
            and not {'evals', '__pycache__', '.git'}.intersection(p.relative_to(skill_dir).parts)}


def build(out, tasks, models, mode='access', metric='equal', timeout=600,
          image='python:3.12-slim', skill_root=None, system_profile='original', conditions=CONDITIONS, judge_profile='self-v1'):
    check_models(models)
    if not conditions or len(set(conditions)) != len(conditions) or not set(conditions) <= set(CONDITIONS):
        raise ValueError('Invalid conditions')
    agent_config = opencode_config(system_profile)
    if mode not in ('access', 'forced') or metric not in ('equal', 'weighted'):
        raise ValueError('Unknown skill mode or metric')
    if timeout <= 0 or '\n' in image or not image:
        raise ValueError('Invalid timeout/image')
    skill_root = Path(skill_root or REPO/'skills/single_turn')
    out = Path(out)
    if out.exists():
        raise ValueError('Task output already exists; refusing overwrite')
    inventories = {}
    for skill in {r['skill_id'] for r in tasks.values()}:
        src = skill_root / skill
        if not (src/'SKILL.md').is_file():
            raise ValueError(f'Missing skill: {skill}')
        inventories[skill] = skill_files(src)
    out.mkdir(parents=True)
    (out/'opencode-config.json').write_text(json.dumps(agent_config, indent=2))
    for model in models:
        for tid, row in tasks.items():
            skill = row['skill_id']
            for cond in conditions:
                task = out/model/skill/cond/tid
                env, verifier = task/'environment', task/'tests'
                env.mkdir(parents=True)
                verifier.mkdir()
                question = row['context'] + '\n\n' + row['user_prompt']
                instruction = question + '\n'
                if cond == 'with-skill' and mode == 'forced':
                    instruction += '\n## Required procedure\n' + (skill_root/skill/'SKILL.md').read_text()
                (task/'instruction.md').write_text(instruction, encoding='utf-8')
                skill_setting = '\nskills_dir = "/skills"' if cond == 'with-skill' else ''
                (task/'task.toml').write_text(
                    'version = "1.0"\n[metadata]\nauthor_name = "EduSkillBench"\n'
                    'difficulty = "medium"\ncategory = "education"\n'
                    f'[agent]\ntimeout_sec = {timeout}\n'
                    '[verifier]\ntimeout_sec = 1900\n[verifier.env]\n'
                    'ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"\n'
                    'ANTHROPIC_BASE_URL = "${ANTHROPIC_BASE_URL}"\n'
                    '[environment]\ncpus = 1\nmemory_mb = 1024\nallow_internet = true'
                    + skill_setting + '\n')
                docker = (f'FROM {image}\nRUN apt-get update -qq && apt-get install -y -qq curl git '
                          '&& rm -rf /var/lib/apt/lists/*\n'
                          'RUN mkdir -p /logs/verifier /logs/agent /logs/artifacts /app /tests\n')
                if cond == 'with-skill':
                    shutil.copytree(skill_root/skill, env/'skills'/skill,
                                    ignore=shutil.ignore_patterns('evals', '__pycache__', '.git'))
                    docker += 'COPY skills/ /skills/\n'
                (env/'Dockerfile').write_text(docker + 'WORKDIR /app\n')
                case = make_case(row, model, metric, judge_profile)
                (verifier/'case.json').write_text(json.dumps(case, indent=2, ensure_ascii=False))
                shutil.copy2(REPO/'repro/judge.py', verifier/'judge.py')
                (verifier/'test.sh').write_text(TEST_SH)
                (verifier/'test.sh').chmod(0o755)
    manifest = {'thinking_policy':THINKING_POLICY, 'model_request_options':MINIMAL_MODEL_OPTIONS, 'protocol': 'eduskill-corrected-2', 'system_profile': system_profile, 'skill_mode': mode, 'score_metric': metric,
                'secondary_metric': 'weighted' if metric == 'equal' else 'equal',
                'agent_timeout_sec': timeout, 'judge_timeout_sec': 1900,
                'models': list(models), 'task_ids': sorted(tasks), 'base_image': image,
                'conditions': list(conditions), 'task_input_sha256': task_digest(tasks),
                'scoring_location': 'host', 'judge_profile':judge_profile,
                'skill_files': inventories, 'judge_sha256': sha256(REPO/'repro/judge.py'),
                'generated_files': {p.relative_to(out).as_posix(): sha256(p)
                                    for p in sorted(out.rglob('*')) if p.is_file()}}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    verify(out)
    return manifest


def verify(out):
    out = Path(out)
    manifest = json.loads((out/'manifest.json').read_text())
    actual = {p.relative_to(out).as_posix(): sha256(p) for p in out.rglob('*')
              if p.is_file() and p != out/'manifest.json'}
    if actual != manifest['generated_files']:
        raise ValueError('Generated task files changed or are missing/unexpected')
    for model in manifest['models']:
        for tid in manifest['task_ids']:
            skill = tid.rsplit('__', 1)[0]
            b = out/model/skill/'baseline'/tid
            w = out/model/skill/'with-skill'/tid
            conditions = manifest.get('conditions', list(CONDITIONS))
            present = [p for cond, p in [('baseline', b), ('with-skill', w)] if cond in conditions]
            cases = [json.loads((p/'tests/case.json').read_text()) for p in present]
            if any(c != cases[0] for c in cases):
                raise ValueError('Conditions have different judge rubrics')
            base = cases[0]['question'] + '\n'
            if 'baseline' in conditions and ((b/'instruction.md').read_text() != base or (b/'environment/skills').exists()):
                raise ValueError('Baseline contamination')
            if 'with-skill' not in conditions:
                continue
            installed = w/'environment/skills'/skill
            if skill_files(installed) != manifest['skill_files'][skill]:
                raise ValueError('Incomplete or modified skill resources')
            target = base
            if manifest['skill_mode'] == 'forced':
                target += '\n## Required procedure\n' + (installed/'SKILL.md').read_text()
            if (w/'instruction.md').read_text() != target:
                raise ValueError('With-skill instruction mismatch')
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--dataset', choices=['core','advisory','all','historical'], default='core')
    ap.add_argument('--models', nargs='+', default=list(MODELS))
    ap.add_argument('--skill-mode', choices=['access', 'forced'], default='access')
    ap.add_argument('--metric', choices=['equal', 'weighted'], default='weighted')
    ap.add_argument('--task-id', action='append')
    ap.add_argument('--system-profile', choices=PROFILES, default='education-single-turn')
    ap.add_argument('--image', default='python:3.12-slim')
    ap.add_argument('--judge-profile', choices=['self-v1','fixed-pro-v1','fixed-pro-v2','fixed-pro-v3'], default='self-v1', help='self-v1 preserves the existing protocol; fixed-pro profiles are experimental and have not passed the stability gate')
    args = ap.parse_args()
    source, conditions = dataset_source(args.dataset)
    tasks = load_tasks(source)
    if args.task_id:
        tasks = {tid: tasks[tid] for tid in args.task_id}
    build(args.out, tasks, args.models, args.skill_mode, args.metric, image=args.image, system_profile=args.system_profile, conditions=conditions, judge_profile=args.judge_profile)
    print(f'Prepared and verified {len(tasks)*len(args.models)*len(conditions)} tasks in {args.out}; dataset={source}')


if __name__ == '__main__':
    main()
