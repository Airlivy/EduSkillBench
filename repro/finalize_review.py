"""Summarize one verified regrading protocol without importing original rewards."""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from protocol import MODELS, sha256
from rejudge import validate_manifest
from judge import cached_verdict, read_trajectory, atomic_json
from runner import lock


def summarize(manifest, directory):
    ledger = []
    scores = {}
    for row in manifest['plan']:
        dest = directory/row['model']/row['task_id']/row['condition']
        verdict = cached_verdict(row['case'], read_trajectory(row['trajectory']), dest)
        if verdict is None:
            continue
        scores[(row['model'], row['task_id'], row['condition'])] = verdict
        ledger.append({**row, 'verdict': verdict, 'verdict_source': str(dest/'judge_result.json'),
                       'verdict_sha256': sha256(dest/'judge_result.json')})
    complete = len(scores) == manifest['expected_cells'] and not manifest['blocked']
    overall, skills = [], []
    tids = sorted({r['task_id'] for r in manifest['plan'] + manifest['blocked']})
    for model in MODELS:
        for skill in [None] + sorted({t.rsplit('__',1)[0] for t in tids}):
            pairs = [(scores[(model,t,'baseline')], scores[(model,t,'with-skill')])
                     for t in tids if (skill is None or t.rsplit('__',1)[0] == skill)
                     and (model,t,'baseline') in scores and (model,t,'with-skill') in scores]
            row = {'model': model, 'status': 'complete' if complete else 'incomplete_preview',
                   'paired_tasks': len(pairs), 'primary_metric': manifest['metric']}
            if skill is not None:
                row['skill'] = skill
            for metric in ('score', 'equal_score', 'weighted_score'):
                row[metric+'_baseline'] = mean(b[metric] for b,w in pairs) if pairs else None
                row[metric+'_with_skill'] = mean(w[metric] for b,w in pairs) if pairs else None
                row[metric+'_lift'] = mean(w[metric]-b[metric] for b,w in pairs) if pairs else None
            (overall if skill is None else skills).append(row)
    return complete, overall, skills, ledger


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--review', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--allow-incomplete', action='store_true')
    args = ap.parse_args(argv)
    with lock(Path('/tmp/eduskillbench-guard.lock')):
        if args.out.exists():
            ap.error('Output exists; choose a new output directory')
        manifest = json.loads((args.review/'plan.json').read_text())
        validate_manifest(manifest, manifest['source_tag'], manifest['metric'])
        complete, overall, skills, ledger = summarize(manifest, args.review)
        if not complete and not args.allow_incomplete:
            print('Review incomplete; no leaderboard written')
            return 1
        args.out.mkdir(parents=True)
        for name, rows in [('model_overall_summary',overall),('model_skill_summary',skills),('selected_reviews',ledger)]:
            atomic_json(args.out/(name+'.json'), rows)
            if rows and name != 'selected_reviews':
                with (args.out/(name+'.csv')).open('w',newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader(); writer.writerows(rows)
        atomic_json(args.out/'provenance.json', {'complete':complete, 'review_manifest_sha256':sha256(args.review/'plan.json'),
                    'judge_version':manifest['judge_version'], 'primary_metric':manifest['metric'],
                    'scored':len(ledger), 'expected':manifest['expected_cells'],
                    'aggregation':'same-task pairs only; one regrading protocol; no original rewards'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
