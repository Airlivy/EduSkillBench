"""Live contrast calibration for native levels, with strict persisted evidence."""
import argparse,json,os
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from repro.credentials import load_env_file
from repro.source_protocol import load_release,labels,digest
from repro.source_runner import evaluate_native
from repro.judge import atomic_json,JudgeError
from repro.calibration.native_fixtures import FIXTURES


def one(item,case,out,model):
    dest=Path(out)/item['task_id']/item['variant']
    try:
        result=evaluate_native(case,item['answer'],model,dest)
        ranks=[]
        for it in result['items']:
            r=next(r for r in case['criteria'] if r['id']==it['id']);ls=labels(r)
            ranks.append(ls.index(it['level']) if it['level'] in ls else len(ls))
        if item['variant']=='correct':passed=all(rank<=1 for rank in ranks) and any(rank==0 for rank in ranks)
        elif item['variant']=='wrong':passed=any(rank>=2 for rank in ranks) if any(len(labels(r))>2 for r in case['criteria']) else all(rank>=1 for rank in ranks)
        else:passed=all(rank>=len(labels(next(r for r in case['criteria'] if r['id']==it['id'])))-1 for rank,it in zip(ranks,result['items']))
        record={'task_id':item['task_id'],'variant':item['variant'],'status':'evaluated','expectation_passed':passed,'ranks':ranks}
    except JudgeError as e:record={'task_id':item['task_id'],'variant':item['variant'],'status':'failed','category':e.category,'expectation_passed':False}
    atomic_json(dest/'check.json',record);return record


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--model',default='glm-5.3',choices=['glm-5.3','deepseek-v4-pro']);a=p.parse_args()
    load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1'
    _,cases,manifest=load_release();byid={c['task_id']:c for c in cases}
    a.out.mkdir(parents=True,exist_ok=True)
    plan={'manifest':digest(manifest),'fixtures':digest(FIXTURES),'judge_model':a.model,'count':len(FIXTURES)}
    path=a.out/'plan.json'
    if path.exists() and json.loads(path.read_text())!=plan:raise ValueError('Calibration plan changed')
    atomic_json(path,plan);atomic_json(a.out/'fixtures.json',FIXTURES)
    atomic_json(a.out/'release_manifest.json',manifest)
    atomic_json(a.out/'cases.json',[byid[t] for t in sorted({f['task_id'] for f in FIXTURES})])
    for name in ('source_protocol.py','source_runner.py','judge.py'):
        (a.out/name).write_bytes((Path(__file__).resolve().parents[1]/name).read_bytes())
    if not a.execute:print(plan);return
    results=[]
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(one,f,byid[f['task_id']],a.out,a.model) for f in FIXTURES]
        for f in as_completed(futures):
            r=f.result();results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
            atomic_json(a.out/'summary.json',{'expected':len(FIXTURES),'completed':len(results),'passed':sum(r['expectation_passed'] for r in results),'results':results,'scope':'15 authored contrasts over five native rubric formats, not independent expert certification'})
    if not all(r['expectation_passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
