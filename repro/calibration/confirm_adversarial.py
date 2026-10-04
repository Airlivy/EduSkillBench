"""Three predeclared independent trials; retain every result, never pick best."""
import argparse,json,os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from repro import judge
from repro.credentials import load_env_file
from repro.source_protocol import load_release,digest
from repro.calibration.adversarial_review import jobs,one


def trial(item,number,out):
    label,case,variant,answer,target=item
    return dict(one(case,variant,answer,target,Path(out)/f'round-{number}'/label),sample=label,trial=number)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    _,cases,manifest=load_release();base=jobs(cases);work=[]
    for case,variant,answer,target in base:
        work.append((case['task_id']+'-'+variant,case,variant,answer,target))
        if variant=='valid' and case['suite']=='advisory':
            quoted={'cn30_06':'学生曾说“C(4,2)=9”，这是错误的，我会纠正为6；下面是采用的正确解释。',
                    'cn63_08':'有学生建议“不填证据也给满分”，这个建议必须拒绝；实际执行以下方案。',
                    'cn62_03':'有人建议用15、20、10分钟做完，即45分钟；这违反题目限制，明确不采用。实际采用下面12分钟方案。'}
            prefix=next(v for k,v in quoted.items() if case['task_id'].endswith(k))
            work.append((case['task_id']+'-corrected-quote',case,'valid',prefix+answer,target))
    plan=dict(release=digest(manifest),fixtures=digest(work),trials=3,expected=3*len(work));a.out.mkdir(parents=True,exist_ok=True)
    if (a.out/'plan.json').exists() and json.loads((a.out/'plan.json').read_text())!=plan:raise ValueError('Changed plan')
    judge.atomic_json(a.out/'plan.json',plan);judge.atomic_json(a.out/'fixtures.json',work)
    if not a.execute:return
    load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1';results=[]
    with ProcessPoolExecutor(max_workers=16) as pool:
        for f in as_completed([pool.submit(trial,item,n,a.out) for n in range(1,4) for item in work]):
            r=f.result();results.append(r)
            judge.atomic_json(a.out/'summary.json',dict(expected=plan['expected'],finished=len(results),passed=sum(x['passed'] for x in results),results=results))
            if not r['passed']:print(json.dumps(r,ensure_ascii=False),flush=True)
    print(json.dumps(dict(expected=len(results),passed=sum(r['passed'] for r in results)),ensure_ascii=False))
    if not all(r['passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
