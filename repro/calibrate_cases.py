"""Paid, bounded, resumable contrast calibration using complete authored answers."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
from . import judge
from .credentials import load_env_file
from .calibration.fixtures_v3 import FIXTURES

ROOT=Path(__file__).resolve().parents[1]

def run_one(item,case,destination):
    case={**case,'judge_model':'glm-5.3','score_metric':'weighted'}
    evidence=json.dumps({'type':'agent_message','text':item['answer']},ensure_ascii=False)
    path=Path(destination)/item['task_id']/item['variant']
    try:
        verdict=judge.evaluate(case,evidence,path)
        decisions={x['id']:x['pass'] for x in verdict['items']}
        checks={}
        if 'min_score' in item:checks['minimum_score']=verdict['score']>=item['min_score']
        if 'max_score' in item:checks['maximum_score']=verdict['score']<=item['max_score']
        for cid in item.get('must_pass',[]):checks['must_pass_'+cid]=decisions.get(cid) is True
        for cid in item.get('must_fail',[]):checks['must_fail_'+cid]=decisions.get(cid) is False
        result={'task_id':item['task_id'],'variant':item['variant'],'score':verdict['score'],
                'expectation_checks':checks,'meets_authored_expectation':all(checks.values()),'status':'scored',
                'input_sha256':verdict['input_sha256']}
    except judge.JudgeError as e:
        result={'task_id':item['task_id'],'variant':item['variant'],'status':'failed','category':e.category}
    judge.atomic_json(path/'calibration_check.json',result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',required=True);p.add_argument('--base-url',required=True)
    p.add_argument('--out',required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--workers',type=int,choices=[1,2,3],default=2)
    p.add_argument('--start',type=int,default=0,help='Skip this many fixtures; use to continue a separately frozen calibration wave')
    p.add_argument('--limit',type=int,default=None)
    a=p.parse_args()
    if not 0<=a.start<len(FIXTURES):p.error('start out of range')
    if a.limit is None:a.limit=len(FIXTURES)-a.start
    if not 1<=a.limit<=len(FIXTURES)-a.start:p.error('limit out of range')
    load_env_file(a.env_file);os.environ['ANTHROPIC_BASE_URL']=a.base_url
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'data/revisions/case-review-v3-20260930/evals.json'
    cases={x['id']:x for x in json.loads(source.read_text())['cases']}
    chosen=FIXTURES[a.start:a.start+a.limit]
    protocol={'model':'glm-5.3','judge_version':judge.VERSION,'judge_sha256':hashlib.sha256(Path(judge.__file__).read_bytes()).hexdigest(),
       'fixtures_sha256':hashlib.sha256(json.dumps(chosen,sort_keys=True).encode()).hexdigest(),
       'dataset_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'max_verdict_calls':len(chosen)*3,
       'items':len(chosen),'endpoint_sha256':hashlib.sha256(a.base_url.encode()).hexdigest()}
    plan=out/'plan.json'
    if plan.exists() and json.loads(plan.read_text())!=protocol:raise SystemExit('Plan changed; choose a fresh output directory')
    judge.atomic_json(plan,protocol);judge.atomic_json(out/'fixtures.json',chosen)
    (out/'judge_source.py').write_text(Path(judge.__file__).read_text())
    (out/'dataset_source.json').write_bytes(source.read_bytes())
    if not a.execute:print(json.dumps(protocol));return
    results=[]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(run_one,item,cases[item['task_id']],out) for item in chosen]
        for future in as_completed(futures):
            result=future.result();results.append(result)
            print(json.dumps(result),flush=True)
            judge.atomic_json(out/'summary.json',{'items':len(chosen),'completed':len(results),'results':results,
                'scope':'authored contrast calibration only; not independent full-corpus acceptance'})
    print(json.dumps({'completed':len(results),'scored':sum(x['status']=='scored' for x in results),
         'expectation_matches':sum(x.get('meets_authored_expectation',False) for x in results)}),flush=True)

if __name__=='__main__':main()
