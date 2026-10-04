"""Read-only provenance inventory, stored in a new directory; no model calls."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from protocol import REPO, MODELS, load_tasks, inspect_model, sha256


def source_inventory(root):
    root = Path(root)
    files = []
    for directory in ('repro', 'code', 'data', 'skills', 'docs', 'LICENSES'):
        files.extend(p for p in (root/directory).rglob('*') if p.is_file()
                     and p.suffix in ('.py', '.sh', '.md', '.txt', '.csv', '.json', '.toml')
                     and '__pycache__' not in p.parts)
    files.extend(root/name for name in ('README.md', '.gitignore', 'LICENSE.md', 'THIRD_PARTY_NOTICES.md')
                 if (root/name).is_file())
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(files)}


def content_id(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def capture():
    files = source_inventory(REPO)
    tasks = load_tasks()
    result_files = {p.relative_to(REPO).as_posix(): sha256(p)
                    for model in MODELS for p in sorted((REPO/'jobs'/f'v2-{model}').rglob('result.json'))}
    summaries = {p.relative_to(REPO).as_posix(): sha256(p)
                 for directory in ('results', 'results_v2') for p in (REPO/directory).glob('*')
                 if p.is_file() and p.suffix in ('.csv', '.json')}
    reports = [inspect_model(REPO/'jobs'/f'v2-{m}', m, tasks) for m in MODELS]
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO))
    except subprocess.CalledProcessError:
        head, dirty = None, None
    return {'schema': 1, 'captured_at': datetime.now(timezone.utc).isoformat(),
            'source_id': content_id(files), 'source_files': files,
            'git_head': head, 'working_tree_dirty': dirty,
            'input': {'single_turn_tasks_sha256': sha256(REPO/'data/single_turn_tasks.csv'),
                      'models': list(MODELS), 'tasks': len(tasks), 'conditions': 2},
            'historical_result_files': result_files, 'historical_summary_files': summaries,
            'coverage': [{'model':r['model'], 'valid':len(r['valid']), 'expected':r['expected'],
                          'complete':r['complete']} for r in reports],
            'relationship': 'Existing v2 results predate this source snapshot; no claim that this source produced them. '
                            'New runs bind code/environment/inputs in jobs/protocols/<tag>; regrading binds them in plan.json.'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True, help='New snapshot directory outside source directories')
    args = ap.parse_args(argv)
    output = args.out.resolve()
    for name in ('repro','code','data','skills','docs','LICENSES'):
        if output == REPO/name or REPO/name in output.parents:
            ap.error('Write snapshots under jobs/ or outside the source tree to avoid self-inclusion')
    if output.exists():
        ap.error('Snapshot directory exists; choose a new one')
    record = capture()
    output.mkdir(parents=True)
    (output/'manifest.json').write_text(json.dumps(record, indent=2, ensure_ascii=False)+'\n')
    print(f"Source snapshot: {record['source_id']}\nWritten to {output}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
