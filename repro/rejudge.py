"""Uniform regrading of preserved answers with immutable inputs and safe resume."""
import argparse
import hashlib
import time
import json
import os
from pathlib import Path
from protocol import REPO, MODELS, inspect_model, load_tasks, sha256, ERROR_FIELDS, check_tag, expected_cells, make_case
from judge import VERSION, evaluate, read_trajectory, cached_verdict, atomic_json, JudgeError, emit_rewards, preflight
from runner import lock

FATAL = {'authentication', 'missing_credentials', 'http_error'}
EXECUTION_ERRORS = set(ERROR_FIELDS) - {'verifier_error', 'verifier_error_category', 'verifier_timeout_info'}


def evidence_files(directory):
    directory = Path(directory)
    paths = [directory/'acp_trajectory.jsonl'] + sorted(directory.glob('*.txt'))
    return {str(p): sha256(p) for p in paths if p.is_file()}


def create_manifest(tag, metric):
    tasks = load_tasks()
    plan, blocked = [], []
    for model in MODELS:
        report = inspect_model(REPO/'jobs'/f'{tag}-{model}', model, tasks)
        if report['errors']:
            raise ValueError('Unexpected run identity; resolve before regrading')
        for cell in sorted(expected_cells(tasks)):
            skill, tid, cond = cell
            run = report['picked'].get(cell)
            row = {'model': model, 'task_id': tid, 'condition': cond}
            if run is None:
                blocked.append({**row, 'reason': 'not_run'})
                continue
            path = Path(run['source'])
            raw = json.loads(path.read_text())
            error = next((k for k in sorted(EXECUTION_ERRORS) if raw.get(k)), None)
            trajectory = path.parent/'trajectory'
            row.update(source=str(path), source_sha256=sha256(path))
            if error or not (trajectory/'acp_trajectory.jsonl').is_file():
                blocked.append({**row, 'reason': error or 'missing_trajectory'})
                continue
            row.update(trajectory=str(trajectory), evidence_files=evidence_files(trajectory),
                       case=make_case(tasks[tid], model, metric))
            plan.append(row)
    return {'judge_version': VERSION, 'judge_sha256': sha256(REPO/'repro/judge.py'),
            'metric': metric, 'source_tag': tag,
            'task_sha256': sha256(REPO/'data/single_turn_tasks.csv'),
            'expected_cells': len(tasks)*len(MODELS)*2, 'plan': plan, 'blocked': blocked,
            'scope': 'uniform regrade; never mix with original rewards'}


def validate_manifest(manifest, tag, metric):
    if (manifest['judge_version'] != VERSION or manifest['metric'] != metric
        or manifest['source_tag'] != tag
        or manifest['judge_sha256'] != sha256(REPO/'repro/judge.py')
        or manifest['task_sha256'] != sha256(REPO/'data/single_turn_tasks.csv')):
        raise ValueError('Review protocol changed; use a new review directory')
    tasks = load_tasks()
    identities = [(r['model'], r['task_id'], r['condition'])
                  for r in manifest['plan'] + manifest['blocked']]
    expected = {(m, tid, cond) for m in MODELS for _, tid, cond in expected_cells(tasks)}
    if len(identities) != len(expected) or set(identities) != expected:
        raise ValueError('Review inventory changed')
    for row in manifest['plan']:
        if (sha256(row['source']) != row['source_sha256']
            or evidence_files(row['trajectory']) != row['evidence_files']
            or row['case'] != make_case(tasks[row['task_id']], row['model'], metric)):
            raise ValueError('Preserved answer or task changed; refusing resume')


def execute_review(manifest, out, limit=None, evaluator=evaluate):
    """Scan durable verdicts before paid work; limit counts cells, not HTTP attempts."""
    out = Path(out)
    results, pending = [], []
    for row in manifest['plan']:
        dest = out/row['model']/row['task_id']/row['condition']
        try:
            trajectory = read_trajectory(row['trajectory'])
            saved = cached_verdict(row['case'], trajectory, dest)
        except JudgeError as exc:
            if exc.category != 'evidence_too_large':
                raise
            results.append({**row, 'status': 'blocked', 'category': exc.category})
            continue
        if saved is not None:
            emit_rewards(dest, saved)
            results.append({**row, 'status': 'scored', 'verdict': saved})
        else:
            pending.append((row, dest, trajectory))
    def checkpoint():
        atomic_json(out/'review_results.json', results)
        scored = sum(r['status'] == 'scored' for r in results)
        complete = scored == manifest['expected_cells'] and not manifest['blocked']
        atomic_json(out/'status.json', {'complete': complete, 'scored': scored,
                    'pending': len(manifest['plan'])-scored, 'blocked': len(manifest['blocked']),
                    'expected': manifest['expected_cells']})
        return complete
    checkpoint()
    for row, dest, trajectory in pending[:limit]:
        try:
            verdict = evaluator(row['case'], trajectory, dest)
            results.append({**row, 'status': 'scored', 'verdict': verdict})
        except JudgeError as exc:
            results.append({**row, 'status': 'judge_failed', 'category': exc.category,
                            'metadata': exc.metadata})
            checkpoint()
            if exc.category in FATAL and not exc.retryable:
                print(f'Review stopped: {exc.category}; saved scores retained')
                return 1
        except (OSError, ValueError) as exc:
            results.append({**row, 'status': 'local_failure', 'error_type': type(exc).__name__})
            checkpoint()
            raise
        checkpoint()
    return 0 if checkpoint() else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--env-file', type=Path, help='Read literal credential assignments; never execute a shell profile')
    ap.add_argument('--base-url', help='Explicit endpoint override for this run')
    ap.add_argument('--metric', choices=['equal', 'weighted'], default='equal')
    ap.add_argument('--source-tag', default='v2')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--limit', type=int, help='Maximum pending cells this invocation; at most 3 HTTP calls per cell')
    args = ap.parse_args(argv)
    if args.env_file:
        from credentials import load_env_file
        load_env_file(args.env_file)
    if args.base_url:
        os.environ['ANTHROPIC_BASE_URL'] = args.base_url
    check_tag(args.source_tag)
    if args.limit is not None and args.limit < 1:
        ap.error('--limit must be positive')
    if args.execute and (not any(os.environ.get(k) for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'LLM_API_KEY')) or not os.environ.get('ANTHROPIC_BASE_URL')):
        ap.error('Set explicit judge credentials/endpoint first')
    with lock(Path('/tmp/eduskillbench-guard.lock')):
        if args.resume:
            manifest = json.loads((args.out/'plan.json').read_text())
            validate_manifest(manifest, args.source_tag, args.metric)
        else:
            if args.out.exists():
                ap.error('Review directory exists; use --resume or a new directory')
            manifest = create_manifest(args.source_tag, args.metric)
            args.out.mkdir(parents=True)
            atomic_json(args.out/'plan.json', manifest)
        print(f"Review plan: {len(manifest['plan'])} preserved outputs; {len(manifest['blocked'])} blocked")
        if not args.execute:
            print('No API calls; use --resume --execute to continue this plan')
            return 0
        # Record the endpoint identity without storing its URL or any credentials.
        identity = {'endpoint_sha256': hashlib.sha256(os.environ['ANTHROPIC_BASE_URL'].rstrip('/').encode()).hexdigest()}
        identity_file = args.out/'execution_identity.json'
        if identity_file.exists() and json.loads(identity_file.read_text()) != identity:
            raise ValueError('Judge endpoint changed; use a separate review')
        atomic_json(identity_file, identity)
        pending = []
        for row in manifest['plan']:
            try:
                evidence = read_trajectory(row['trajectory'])
            except JudgeError as exc:
                if exc.category == 'evidence_too_large':
                    continue
                raise
            saved = cached_verdict(row['case'], evidence,
                                   args.out/row['model']/row['task_id']/row['condition'])
            if saved is None:
                pending.append(row)
        pending_models = sorted({r['model'] for r in pending[:args.limit]})
        preflight(pending_models, args.out/'preflight'/str(time.time_ns()))
        return execute_review(manifest, args.out, args.limit)


if __name__ == '__main__':
    raise SystemExit(main())
