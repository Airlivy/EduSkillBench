#!/usr/bin/env python3
"""Check the declared inventory, including missing whole models/skills."""
import argparse
import csv
import sys
from pathlib import Path
from protocol import REPO, MODELS, CONDITIONS, check_models, check_tag, load_tasks, inspect_model, dataset_source, validate_run_binding


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('models', nargs='*')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--root', default='v2')
    ap.add_argument('--jobs-dir', type=Path, default=REPO / 'jobs')
    ap.add_argument('--tasks', type=Path)
    ap.add_argument('--dataset', choices=['core','advisory','all','historical'])
    ap.add_argument('--expect', type=int, help='Assert expected count against the task inventory')
    ap.add_argument('--csv', type=Path)
    args = ap.parse_args(argv)
    try:
        if args.tasks and args.dataset:
            raise ValueError('Use --tasks or --dataset, not both')
        source, conditions = dataset_source(args.dataset) if args.dataset else (args.tasks, CONDITIONS)
        tasks = load_tasks(source)
        models = check_models(list(MODELS) if args.all or not args.models else args.models)
        check_tag(args.root)
        if args.dataset and args.dataset != 'historical':
            validate_run_binding(args.jobs_dir,args.root,tasks,conditions)
        if args.expect is not None and args.expect != len(tasks) * len(conditions):
            raise ValueError('--expect disagrees with task inventory')
    except (ValueError, OSError, KeyError) as e:
        ap.error(str(e))
    missing, complete = [], True
    for model in models:
        report = inspect_model(args.jobs_dir / f'{args.root}-{model}', model, tasks, conditions)
        complete &= report['complete']
        print(f"{model}: {len(report['valid'])}/{report['expected']} valid cells; "
              f"{report['attempts']} attempts; {len(report['errors'])} unexpected records")
        for row in report['missing']:
            print(f"  missing {row['task_id']} {row['condition']}: {row['reason']}")
        for row in report['errors']:
            print(f"  invalid path/identity: {row['source']}: {row['reason']}")
        missing.extend(report['missing'])
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['model', 'skill', 'task_id', 'condition', 'reason'])
            writer.writeheader()
            writer.writerows(missing)
    print('Coverage complete (scoring/protocol require separate validation).' if complete
          else 'INCOMPLETE: not eligible for a complete leaderboard.')
    return 0 if complete else 1


if __name__ == '__main__':
    sys.exit(main())
