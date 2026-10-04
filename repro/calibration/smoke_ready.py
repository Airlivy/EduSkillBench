"""Bounded live contrasts on the runnable delivery; this is not full-corpus certification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from repro import judge
from repro.credentials import load_env_file
from repro.calibration.fixtures_v3 import FIXTURES

ROOT=Path(__file__).resolve().parents[2]


def fixtures():
    result=[]
    for tid in ['self-explanation-prompt-designer__03','project-brief-designer__cn52_04']:
        selected=[dict(x) for x in FIXTURES if x['task_id']==tid]
        for f in selected:
            if f['variant']=='off_topic':f['max_score']=0.0
            if tid=='self-explanation-prompt-designer__03':
                if f['variant']=='positive':f['must_pass']=['C1','C6']
                if f['variant']=='factual_error':f['must_fail']=['C1','C6']
        positive=next(x for x in selected if x['variant']=='positive')
        equivalent=dict(positive);equivalent['variant']='equivalent_correct'
        if tid=='self-explanation-prompt-designer__03':
            equivalent['answer']=positive['answer'].replace('Phi=0.008 Wb.', 'The magnetic flux is 8 milliw webers (8 mWb = 0.008 Wb).'.replace('milliw webers','milliwebers')).replace('current magnitude 0.06 A.','current magnitude 60 mA.')
        else:
            equivalent['answer']='''Arrange nine groups of four, one of three, and one of six: 9*4+3+6=45 pupils in 11 groups. This is a possible layout, not a requirement for ten groups of four plus one of five.
In each four-person group assign operator, observer, recorder and materials coordinator. In the three-person group combine observation with recording, provided the task is simple enough and the observer has time to record. In the six-person group split materials preparation and return between two pupils and give the sixth a substantive verification role checking recorded observations against what happened. Everyone has an actual contribution; no pupil is an extra spectator.
For a simple classroom observation, demonstrate duties and a safe handover, use a visible role card and rotate at a completed trial. Do not change operators mid-operation. Adapt supports to each pupil without permanently assigning less confident pupils to watching. Check each pupil's contribution through a short explanation or record, and reallocate a concrete next action if anyone is left idle. This assumes the room and chosen activity can accommodate the six-person group; if not, use ten groups of four and one of five. The routine is a proposal, not evidence that participation has already improved.'''
        result.extend(selected+[equivalent])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',required=True)
    p.add_argument('--base-url')
    p.add_argument('--model', choices=['glm-5.3','glm-5.3-flash'], default='glm-5.3')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    load_env_file(a.env_file)
    if a.base_url:os.environ['ANTHROPIC_BASE_URL']=a.base_url
    source=ROOT/'data/releases/run-ready-20260930/evals.json'
    cases={x['id']:x for x in json.loads(source.read_text())['cases']}
    items=fixtures();a.out.mkdir(parents=True,exist_ok=True)
    protocol={'dataset_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'judge_sha256':hashlib.sha256(Path(judge.__file__).read_bytes()).hexdigest(),
        'fixtures_sha256':hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest(),
        'endpoint_sha256':hashlib.sha256(os.environ.get('ANTHROPIC_BASE_URL','').encode()).hexdigest(),
        'model':a.model,'maximum_calls':8,'scope':'2 tasks x 4 full-answer contrasts; not all-case acceptance'}
    plan=a.out/'plan.json'
    if plan.exists() and json.loads(plan.read_text())!=protocol:raise ValueError('Inputs changed; use another output directory')
    judge.atomic_json(plan,protocol);judge.atomic_json(a.out/'fixtures.json',items)
    if not a.execute:print(json.dumps(protocol));return
    load_env_file(a.env_file)
    results=[]
    for item in items:
        case={**cases[item['task_id']],'judge_model':a.model,'score_metric':'weighted'}
        calls=0
        def once(prompt,model):
            nonlocal calls
            if calls:raise judge.JudgeError('smoke_retry_disabled')
            calls+=1
            try:return judge.call_judge(prompt,model)
            except judge.JudgeError as e:
                e.retryable=False
                raise
        dest=a.out/item['task_id']/item['variant']
        try:
            verdict=judge.evaluate(case,json.dumps({'type':'agent_message','text':item['answer']}),dest,call=once)
            decisions={x['id']:x['pass'] for x in verdict['items']}
            match=all(decisions.get(cid) for cid in item.get('must_pass',[])) and all(decisions.get(cid) is False for cid in item.get('must_fail',[]))
            match=match and verdict['score']>=item.get('min_score',0) and verdict['score']<=item.get('max_score',1)
            result={'task_id':item['task_id'],'variant':item['variant'],'status':'scored','score':verdict['score'],'matches_expectation':bool(match),'critical_pass':verdict['critical_pass']}
        except judge.JudgeError as e:
            result={'task_id':item['task_id'],'variant':item['variant'],'status':'failed','category':e.category}
        results.append(result)
        summary={'protocol':protocol,'results':results,'completed':len(results),'expected':len(items),'all_expectations_passed':len(results)==len(items) and all(x.get('matches_expectation') for x in results)}
        judge.atomic_json(a.out/'summary.json',summary)
        print(json.dumps(result),flush=True)
        if result['status']=='failed':raise SystemExit(1)
    raise SystemExit(0 if summary['all_expectations_passed'] else 1)

if __name__=='__main__':main()
