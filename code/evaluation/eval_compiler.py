"""Compile without dropping rubric identities/weights or bypassing revision release gates."""
import csv
import json
import math
import re
import shutil
from pathlib import Path


def compile_cases(source, output, skill_source, *, review_only=False):
    source=Path(source).resolve();output=Path(output).resolve();skill_source=Path(skill_source).resolve()
    gate=source.parent/'release_gate.json'
    gated=gate.exists() and not json.loads(gate.read_text())['ready']
    if gated and not review_only:
        raise ValueError('Revision not released: use review_only for isolated inspection, not a formal run')
    # Prevent a revised input from overwriting historical Skill/eval directories.
    repo=Path(__file__).resolve().parents[2]
    if gated and (output==repo/'skills' or repo/'skills' in output.parents):
        raise ValueError('Unreleased revision must compile outside historical skills directories')
    if (gated or review_only) and output.exists() and any(output.iterdir()):
        raise ValueError('Review output must be empty to prevent stale cases or skills')
    with source.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    seen=set();groups={}
    for r in rows:
        tid=r['task_id'];sid=r['skill_id']
        if not re.fullmatch(r'[a-z0-9-]+',sid) or not tid.startswith(sid+'__') or tid in seen:
            raise ValueError('Invalid or duplicate task identity')
        seen.add(tid)
        rubric=json.loads(r['rubric'])
        if not rubric or any(type(c.get('points')) not in (int,float) or not math.isfinite(c['points']) or c['points']<=0 for c in rubric):
            raise ValueError('Invalid rubric weights')
        if not math.isclose(sum(c['points'] for c in rubric),100):raise ValueError('Rubric must total 100')
        rubric=[{'id':f'C{i+1}',**c} for i,c in enumerate(rubric)]
        if len({c['id'] for c in rubric})!=len(rubric):raise ValueError('Duplicate criterion ID')
        groups.setdefault(sid,[]).append({'id':tid,'question':r['context']+'\n\n'+r['user_prompt'],
           'ground_truth':r['expected_output'],'rubric':rubric,
           'expected_behavior':[c['description'] for c in rubric],
           'score_metric':'weighted','status':'review_only' if gated or review_only else 'compiled_not_calibrated'})
    if not rows:raise ValueError('No cases')
    # Validate every dependency before writing any output.
    for sid in groups:
        if not (skill_source/sid/'SKILL.md').exists():raise FileNotFoundError(sid)
    for sid,cases in groups.items():
        dst=output/sid
        if dst.resolve()!=(skill_source/sid).resolve():
            shutil.copytree(skill_source/sid,dst,dirs_exist_ok=True,ignore=shutil.ignore_patterns('evals'))
        (dst/'evals').mkdir(parents=True,exist_ok=True)
        (dst/'evals/evals.json').write_text(json.dumps({'version':'2','skill_name':sid,
           'defaults':{'timeout_sec':300},'scoring_contract':'rubric weights retained; legacy consumers ignoring rubric do not implement weighted scoring',
           'release_status':'review_only' if gated or review_only else 'compiled_not_calibrated','cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'skills':len(groups),'eval_cases':len(rows),'review_only':gated or review_only}


def main(default_source,default_output):
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',default=default_source)
    p.add_argument('--output',default=default_output)
    p.add_argument('--skill-source',default='skills/single_turn')
    p.add_argument('--review-only',action='store_true')
    args=p.parse_args()
    print(json.dumps(compile_cases(args.source,args.output,args.skill_source,review_only=args.review_only)))
