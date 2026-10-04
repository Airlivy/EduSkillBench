#!/usr/bin/env python3
"""Aggregate identical complete task pairs with a per-cell evidence ledger."""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from protocol import REPO, MODELS, CONDITIONS, check_models, check_tag, inspect_model, load_tasks, sha256, dataset_source, validate_run_binding


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default='v2')
    ap.add_argument('--models', nargs='+', default=list(MODELS))
    ap.add_argument('--jobs-dir', type=Path, default=REPO / 'jobs')
    ap.add_argument('--tasks', type=Path)
    ap.add_argument('--dataset', choices=['core','advisory','all','historical'])
    ap.add_argument('--out', type=Path, required=True, help='New directory; never overwrite results')
    ap.add_argument('--allow-incomplete', action='store_true', help='Export labelled paired preview')
    args = ap.parse_args(argv)
    try:
        check_models(args.models)
        check_tag(args.root)
        if args.tasks and args.dataset:raise ValueError('Use --tasks or --dataset, not both')
        source, conditions = dataset_source(args.dataset) if args.dataset else (args.tasks or REPO/'data/single_turn_tasks.csv', CONDITIONS)
        tasks = load_tasks(source)
        args.tasks = source
        if args.dataset and args.dataset != 'historical':
            validate_run_binding(args.jobs_dir,args.root,tasks,conditions)
    except (ValueError, OSError, KeyError) as e:
        ap.error(str(e))
    if args.out.exists():
        ap.error('Output exists; choose a new directory')
    reports = [inspect_model(args.jobs_dir / f'{args.root}-{m}', m, tasks, conditions) for m in args.models]
    if any(r['errors'] for r in reports):
        print('Unexpected task identities/paths; refusing aggregation')
        return 1
    if any(not r['complete'] for r in reports) and not args.allow_incomplete:
        for r in reports:
            print(f"{r['model']}: {len(r['valid'])}/{r['expected']}")
        print('Incomplete; no files written')
        return 1
    if tuple(conditions) == ('baseline',):
        # Advisory tasks do not establish the value of a routed Skill.
        args.out.mkdir(parents=True)
        summary=[]
        for report in reports:
            valid=list(report['valid'].values())
            summary.append({'model':report['model'],'judge_profile':report['judge_profile'],'status':'complete' if report['complete'] else 'incomplete_preview',
                'valid_cells':len(valid),'expected_cells':report['expected'],
                'baseline_mean':mean(x['reward'] for x in valid) if valid else None,
                'skill_lift':None,'scope':'baseline answer quality only; partial-credit score is not a correctness certificate'})
        (args.out/'summary.json').write_text(json.dumps({'dataset':str(source),'dataset_sha256':sha256(source),'models':summary},ensure_ascii=False,indent=2)+'\n')
        (args.out/'ledger.json').write_text(json.dumps([{'model':r['model'],'runs':list(r['picked'].values())} for r in reports],ensure_ascii=False,indent=2)+'\n')
        print(f'Baseline-only summary: {args.out}')
        return 0
    overall, skills, ledger = [], [], []
    for report in reports:
        valid, model = report['valid'], report['model']
        pairs = []
        for tid, task in tasks.items():
            s = task['skill_id']
            b, w = valid.get((s, tid, 'baseline')), valid.get((s, tid, 'with-skill'))
            if b and w:
                pairs.append((s, b['reward'], w['reward']))
        overall.append({'model': model, 'judge_profile':report['judge_profile'], 'status': 'complete' if report['complete'] else 'incomplete_preview',
                        'cells': len(valid), 'expected_cells': report['expected'],
                        'paired_tasks': len(pairs), 'attempts': report['attempts'],
                        'valid_attempts': report['valid_attempts'],
                        'baseline_avg_reward': mean(p[1] for p in pairs) if pairs else None,
                        'with_skill_avg_reward': mean(p[2] for p in pairs) if pairs else None,
                        'reward_lift': mean(p[2]-p[1] for p in pairs) if pairs else None})
        for skill in sorted({t['skill_id'] for t in tasks.values()}):
            ps = [p for p in pairs if p[0] == skill]
            skills.append({'model': model, 'skill': skill, 'paired_tasks': len(ps),
                           'baseline': mean(p[1] for p in ps) if ps else None,
                           'with_skill': mean(p[2] for p in ps) if ps else None,
                           'lift': mean(p[2]-p[1] for p in ps) if ps else None})
        for (skill, tid, cond), run in sorted(report['picked'].items()):
            ledger.append({'model': model, 'skill': skill, 'task_id': tid, 'condition': cond, **run})
    args.out.mkdir(parents=True)
    for name, rows in [('model_overall_summary', overall), ('model_skill_summary', skills), ('selected_runs', ledger)]:
        (args.out / f'{name}.json').write_text(json.dumps(rows, indent=2, allow_nan=False)+'\n')
        if rows:
            with (args.out / f'{name}.csv').open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    meta = {'task_sha256': sha256(args.tasks), 'source_prefix': args.root,
            'judge_profiles':sorted({r['judge_profile'] for r in reports}),
            'selection': 'latest valid attempt; finished_at then source path; quarantined attempts excluded',
            'aggregation': 'task-weighted mean over identical complete pairs only',
            'score_semantics': 'recorded reward; coverage audit does not revalidate historical judge output',
            'complete': all(r['complete'] for r in reports),
            'missing': [row for r in reports for row in r['missing']]}
    (args.out/'provenance.json').write_text(json.dumps(meta, indent=2)+'\n')
    print(f"Written to {args.out}; complete={meta['complete']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
