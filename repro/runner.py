"""Serial, bounded runner. Dry-run by default; never append new protocol to v2."""
import argparse
import asyncio
import contextlib
import fcntl
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from protocol import REPO, MODELS, check_tag, check_models, load_tasks, inspect_model, sha256, execution_error, make_case, dataset_source, task_digest
from prepare import build, verify
from profiles import PROFILES, opencode_config


def environment_identity():
    import benchflow
    root = Path(benchflow.__file__).parent
    if importlib.metadata.version('benchflow') != '0.6.7':
        raise ValueError('This adapter is tested with BenchFlow 0.6.7 only')
    return {'python': sys.version.split()[0], 'benchflow': '0.6.7',
            'packages': dict(sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions() if d.metadata['Name'])),
            'benchflow_sources': {p.relative_to(root).as_posix(): sha256(p)
                                 for p in sorted(root.rglob('*')) if p.is_file() and p.suffix in ('.py', '.tmpl')}}


def immutable_image_reference(image):
    """Dockerfile FROM needs a repository digest, not a bare config/image ID."""
    records = json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))
    record = records[0]
    digests = record.get('RepoDigests') or []
    if not digests:
        raise ValueError('Base image has no repository digest; use a pulled repository image with a digest')
    reference = image if image in digests else sorted(digests)[0]
    if '@sha256:' not in reference:
        raise ValueError('Invalid immutable repository reference')
    return record['Id'], reference


def configure_local_proxy_bypass(gateways):
    """Local Docker/LiteLLM health checks must not go through an HTTP proxy."""
    entries = {v.strip() for key in ('NO_PROXY','no_proxy') for v in os.environ.get(key,'').split(',') if v.strip()}
    entries.update(('localhost','127.0.0.1','::1'))
    entries.update(g for g in gateways if g)
    value = ','.join(sorted(entries))
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = value


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another batch/retry holds the lock; do not delete the lock file') from None
        yield


def run_owned(command, log, timeout):
    """Only this worker's process group is terminated, never global process names."""
    with log.open('w') as out:
        child = subprocess.Popen(command, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return child.wait(timeout=timeout)
        finally:
            # Also reap a worker's own leaked proxy descendants after normal completion.
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def worker(plan_file):
    from benchflow.rollout import Rollout, RolloutConfig
    from benchflow.skill_policy import SKILL_MODE_WITH_SKILL, SKILL_MODE_NO_SKILL
    plan = json.loads(Path(plan_file).read_text())
    env = {k: os.environ[k] for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'ARK_API_KEY') if k in os.environ}
    config = opencode_config(plan['system_profile'])
    if config:
        env['OPENCODE_CONFIG_CONTENT'] = json.dumps(config)
    async def generate():
        for tid in plan['task_ids']:
            config = RolloutConfig.from_legacy(
                task_path=Path(plan['tasks_dir'])/tid, jobs_dir=plan['jobs_dir'],
                agent='opencode', model='ark/'+plan['model'], environment='docker',
                concurrency=1, agent_env=env, agent_idle_timeout=600,
                skip_verify=True,
                skill_mode=SKILL_MODE_WITH_SKILL if plan['condition']=='with-skill' else SKILL_MODE_NO_SKILL)
            rollout = await Rollout.create(config)
            await rollout.run()
    asyncio.run(generate())
    return 0


def recover_scoring(source, case, *, retry_blocked=False):
    """Return False only when generating a new answer is necessary."""
    from judge import evaluate, read_trajectory, atomic_json
    source = Path(source)
    raw = json.loads(source.read_text())
    if raw.get('model', '').removeprefix('ark/') != case.get('response_model',case['judge_model']):
        raise ValueError('Result model mismatch; refusing recovery')
    if execution_error(raw):
        return False
    if not (source.parent/'trajectory/acp_trajectory.jsonl').is_file():
        return False
    # This executes on the host against preserved evidence, without an agent/container.
    bound_case = {**case, 'source_result_sha256': sha256(source)}
    dest = source.parent/'scoring_recovery'
    dest.mkdir(exist_ok=True)
    case_file = dest/'case.json'
    if case_file.exists() and json.loads(case_file.read_text()) != bound_case:
        raise ValueError('Recovery protocol changed; do not overwrite preserved scores')
    atomic_json(case_file, bound_case)
    if retry_blocked:
        evaluate(bound_case, read_trajectory(source.parent/'trajectory'), dest, retry_blocked=True)
    else:
        evaluate(bound_case, read_trajectory(source.parent/'trajectory'), dest)
    return True


def try_recovery(report, row, case, *, retry_blocked=False):
    from judge import JudgeError
    run = report['picked'].get((row['skill'], row['task_id'], row['condition']))
    if run is None:
        return False
    if run['reason'] == 'invalid_scoring_recovery':
        raise ValueError('Saved recovery is invalid; resolve before continuing')
    try:
        return recover_scoring(run['source'], case, retry_blocked=retry_blocked)
    except JudgeError as exc:
        detail = exc.metadata
        diagnostics = {key: detail[key] for key in
                       ('failure_cause', 'retry_action', 'retry_suppressed', 'network_error_kind', 'timeout_kind', 'stage', 'elapsed_seconds', 'reason_type')
                       if key in detail}
        print(f"Scoring pending: {row['model']} {row['task_id']} {row['condition']}: "
              f"{exc.category}; diagnostics={json.dumps(diagnostics)}", flush=True)
        if not exc.retryable and exc.category in ('authentication', 'missing_credentials', 'http_error'):
            raise
        # Preserved answers must not be regenerated just because the judge failed.
        return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--tag', default='ready-20260930')
    ap.add_argument('--dataset', choices=['core','advisory','all','historical'], default='core')
    ap.add_argument('--models', nargs='+', default=list(MODELS))
    ap.add_argument('--skill-mode', choices=['access', 'forced'], default='access')
    ap.add_argument('--system-profile', choices=PROFILES, default='education-single-turn')
    ap.add_argument('--metric', choices=['equal', 'weighted'], default='weighted')
    ap.add_argument('--judge-profile', choices=['self-v1','fixed-pro-v1','fixed-pro-v2','fixed-pro-v3'], default='self-v1', help='self-v1 preserves the existing protocol; fixed-pro profiles are experimental and have not passed the stability gate')
    ap.add_argument('--task-id', action='append')
    ap.add_argument('--image', default='python:3.12-slim')
    ap.add_argument('--rounds', type=int, default=1)
    ap.add_argument('--retry-blocked-scoring', action='store_true', help='Explicitly retry a saved output-limit/thinking-deadline failure once per cell in this invocation')
    ap.add_argument('--execute', action='store_true', help='Allow paid model requests')
    ap.add_argument('--env-file', type=Path, help='Read literal API assignments without executing shell code')
    ap.add_argument('--base-url', help='Explicit endpoint override after reading the credential file')
    args = ap.parse_args(argv)
    if args.worker:
        return worker(args.worker)
    def stop_on_signal(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_on_signal)
    check_models(args.models)
    check_tag(args.tag)
    if args.tag in ('v2', 'formal'):
        ap.error('Historical batches are immutable; choose a new tag')
    if not 1 <= args.rounds <= 3:
        ap.error('--rounds must be 1..3 (bounded retries)')
    source, conditions = dataset_source(args.dataset)
    tasks = load_tasks(source)
    if args.task_id:
        tasks = {tid: tasks[tid] for tid in args.task_id}
    print(f'Dataset: {source}; tasks={len(tasks)}; conditions={list(conditions)}; input={task_digest(tasks)}')
    if not args.execute:
        for model in args.models:
            report = inspect_model(REPO/'jobs'/f'{args.tag}-{model}', model, tasks, conditions)
            print(f"{model}: planned {len(report['missing'])} missing cells, mode={args.skill_mode}, metric={args.metric}, system={args.system_profile}, judge={args.judge_profile}")
        print('Dry-run only. Use --execute after preflight and review of protocol/cost.')
        return 0
    if args.env_file:
        from credentials import load_env_file
        load_env_file(args.env_file)
    if args.base_url:
        os.environ['ANTHROPIC_BASE_URL'] = args.base_url
    key = next((os.environ.get(k) for k in ('ARK_API_KEY','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','LLM_API_KEY') if os.environ.get(k)), None)
    if not key or not os.environ.get('ANTHROPIC_BASE_URL'):
        raise ValueError('Set an API credential and ANTHROPIC_BASE_URL, or select --env-file')
    os.environ['ARK_API_KEY'] = key
    os.environ['ANTHROPIC_API_KEY'] = key
    # Do not inherit alternate provider credentials from unrelated shell sessions.
    for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'GOOGLE_API_KEY', 'GEMINI_API_KEY'):
        os.environ.pop(key, None)
    subprocess.run(['docker', 'info'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    network = json.loads(subprocess.check_output(['docker','network','inspect','bridge'],text=True))[0]
    gateways = [entry.get('Gateway','') for entry in network.get('IPAM',{}).get('Config',[])]
    configure_local_proxy_bypass(gateways)
    # Require a locally available immutable image reference, to avoid mutable-tag drift on resume.
    image_id, image_reference = immutable_image_reference(args.image)
    identity = environment_identity()
    identity['image_id'] = image_id
    identity['image_reference'] = image_reference
    identity['endpoint'] = os.environ['ANTHROPIC_BASE_URL']
    identity['local_proxy_bypass'] = os.environ['NO_PROXY']
    identity['adapter_sources'] = {p.name: sha256(p) for p in (REPO/'repro').glob('*.py')}
    frozen = REPO/'jobs'/'protocols'/args.tag
    with lock(Path('/tmp/eduskillbench-guard.lock')):
        generated = frozen/'tasks'
        requested = {'models': args.models, 'task_ids': sorted(tasks), 'skill_mode': args.skill_mode, 'score_metric': args.metric, 'system_profile': args.system_profile, 'conditions':list(conditions), 'task_input_sha256':task_digest(tasks), 'scoring_location':'host', 'judge_profile':args.judge_profile}
        if frozen.exists():
            manifest = verify(generated)
            if any(manifest.get(k) != v for k, v in requested.items()):
                raise ValueError('Protocol changed; choose a new tag')
            if json.loads((frozen/'environment.json').read_text()) != identity:
                raise ValueError('Environment changed; choose a new tag')
        else:
            if any((REPO/'jobs'/f'{args.tag}-{m}').exists() for m in args.models):
                raise ValueError('Existing results have no frozen manifest; choose a new tag')
            frozen.mkdir(parents=True)
            build(generated, tasks, args.models, args.skill_mode, args.metric, image=image_reference, system_profile=args.system_profile, conditions=conditions, judge_profile=args.judge_profile)
            (frozen/'environment.json').write_text(json.dumps(identity, indent=2))
            (frozen/'dataset_source.csv').write_bytes(source.read_bytes())
        from judge import preflight
        pending_models = [m for m in args.models
                          if not inspect_model(REPO/'jobs'/f'{args.tag}-{m}', m, tasks, conditions)['complete']]
        preflight(pending_models, frozen/'preflight'/str(time.time_ns()), judge_profile=args.judge_profile)
        failed = False
        unblocked_cells = set()
        try:
            for iteration in range(args.rounds):
                for model in args.models:
                    report = inspect_model(REPO/'jobs'/f'{args.tag}-{model}', model, tasks, conditions)
                    if report['errors']:
                        raise ValueError('Unexpected result identities; refusing retries')
                    # One cell per worker: bounded resources and exact condition-specific retries.
                    for row in report['missing']:
                        case = make_case(tasks[row['task_id']], model, args.metric, args.judge_profile)
                        cell = (model, row['task_id'], row['condition'])
                        unblock = args.retry_blocked_scoring and cell not in unblocked_cells
                        unblocked_cells.add(cell)
                        if try_recovery(report, row, case, retry_blocked=unblock):
                            continue
                        containers = subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines()
                        if len(containers) >= 8:
                            raise RuntimeError('Container cap reached; stopped before launching another worker')
                        mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
                        if int(mem['MemAvailable'].split()[0]) < 1500 * 1024:
                            raise RuntimeError('Less than 1500 MiB available; stopped before starting another cell')
                        tid, skill, cond = row['task_id'], row['skill'], row['condition']
                        stamp = str(time.time_ns())
                        plan = {'model': model, 'condition': cond, 'task_ids': [tid],
                                'system_profile': args.system_profile,
                                'tasks_dir': str(generated/model/skill/cond),
                                'jobs_dir': str(REPO/'jobs'/f'{args.tag}-{model}'/skill/'skill-eval'/skill/'opencode'/cond)}
                        plan_file = frozen/f'worker-{stamp}.json'
                        plan_file.write_text(json.dumps(plan))
                        try:
                            rc = run_owned([sys.executable, str(Path(__file__).resolve()), '--worker', str(plan_file)],
                                           frozen/f'worker-{stamp}.log', timeout=2400)
                            failed |= rc != 0
                        except subprocess.TimeoutExpired:
                            failed = True
                        # Native skip_verify exports the answer without calling a
                        # container-side API or inventing a placeholder reward.
                        # Host scoring is the only retry owner (at most 3 calls).
                        fresh = inspect_model(REPO/'jobs'/f'{args.tag}-{model}', model, tasks, conditions)
                        try_recovery(fresh, row, case)
                        print(f'{model} {tid} {cond}: attempt completed', flush=True)
        except KeyboardInterrupt:
            print('Interrupted; own worker cleaned up, existing results preserved')
            return 130
        complete = all(inspect_model(REPO/'jobs'/f'{args.tag}-{m}', m, tasks, conditions)['complete'] for m in args.models)
        print(f'Coverage complete={complete}; worker failure observed={failed}')
        return 0 if complete else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Runner stopped: {exc}', file=sys.stderr)
        raise SystemExit(1)
