"""Bounded live concurrency sweep; real case prompts, no retries masking failures."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import time
from repro import judge
from repro.credentials import load_env_file
from repro.source_protocol import load_release, prompt, schema, validate, digest
from repro.source_runner import model_options
from repro.calibration.native_fixtures import FIXTURES

MODELS=list(judge.MINIMAL_MODEL_OPTIONS)


def request(job):
    dest=Path(job['dest']);dest.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    record={k:job[k] for k in ('model','stage','task_id')}
    try:
        text,meta=judge.call_judge(job['prompt'],job['model'],telemetry_path=dest/'trace.json',
                                  output_schema=job.get('schema'),**model_options(job['model']))
        (dest/'raw.txt').write_text(text)
        judge.atomic_json(dest/'response.json',meta)
        if meta.get('stop_reason') not in ('end_turn','stop_sequence'):
            raise judge.JudgeError('incomplete_response',False,meta)
        if not text.strip():raise judge.JudgeError('empty_response',False,meta)
        if job['stage']=='grading':validate(judge.decode_verdict(text),job['case'],job['answer'])
        record.update(status='ok',metadata=meta)
    except (judge.JudgeError,ValueError,KeyError,TypeError) as exc:
        record.update(status='failed',category=getattr(exc,'category','invalid_verdict'),metadata=getattr(exc,'metadata',{}))
    record['elapsed_seconds']=round(time.monotonic()-start,3)
    judge.atomic_json(dest/'result.json',record)
    return record


def summarize(records,elapsed,workers):
    times=sorted(r['elapsed_seconds'] for r in records)
    ok=sum(r['status']=='ok' for r in records)
    return {'workers':workers,'requests':len(records),'success':ok,'failed':len(records)-ok,
            'wall_seconds':round(elapsed,3),'successful_requests_per_minute':round(ok*60/elapsed,3),
            'p95_seconds':times[min(len(times)-1,int(len(times)*.95))],
            'models':{m:{'requests':sum(r['model']==m for r in records),'failed':sum(r['model']==m and r['status']!='ok' for r in records)} for m in sorted({r['model'] for r in records})},
            'errors':[{'model':r['model'],'category':r['category'],'timeout_kind':r['metadata'].get('timeout_kind'),'http_status':r['metadata'].get('http_status')} for r in records if r['status']!='ok']}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--mode',choices=['grading','mixed'],required=True)
    ap.add_argument('--levels',type=int,nargs='+',required=True)
    ap.add_argument('--models',nargs='+',choices=MODELS,default=MODELS)
    ap.add_argument('--execute',action='store_true')
    a=ap.parse_args()
    if any(w<1 or w>32 for w in a.levels):ap.error('levels must be 1..32')
    if a.out.exists():ap.error('Use a fresh directory to preserve stress evidence')
    a.out.mkdir(parents=True)
    load_env_file('/home/airlivy/.bashrc')
    os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1'
    _,cases,manifest=load_release();byid={c['task_id']:c for c in cases}
    plan={'mode':a.mode,'levels':a.levels,'models':a.models,'release_sha256':digest(manifest),'max_requests':sum(2*w for w in a.levels),'retry':False,'options':{m:model_options(m) for m in MODELS}}
    judge.atomic_json(a.out/'plan.json',plan)
    if not a.execute:print(json.dumps(plan));return
    reports=[]
    for workers in a.levels:
        jobs=[]
        for i in range(workers*2):
            fixture=FIXTURES[i%len(FIXTURES)];case=byid[fixture['task_id']]
            index=i%(len(a.models)+1)
            grading=a.mode=='grading' or index==len(a.models)
            model='deepseek-v4-pro' if grading else a.models[index]
            job={'dest':str(a.out/f'w{workers}'/str(i)),'model':model,'task_id':case['task_id'],'stage':'grading' if grading else 'generation'}
            if grading:
                job.update(prompt=prompt(case,fixture['answer']),case=case,answer=fixture['answer'],schema=schema([r for r in case['criteria'] if r['id'] in case['applicable_ids']]))
            else:job['prompt']=case['context']+'\n\n'+case['user_prompt']
            jobs.append(job)
        start=time.monotonic();records=[]
        print(json.dumps({'event':'level_started','workers':workers,'requests':len(jobs)}),flush=True)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(request,j) for j in jobs]):
                r=future.result();records.append(r)
                print(json.dumps({'event':'request_completed','workers':workers,'model':r['model'],'stage':r['stage'],'status':r['status'],'seconds':r['elapsed_seconds']},ensure_ascii=False),flush=True)
        report=summarize(records,time.monotonic()-start,workers);reports.append(report)
        judge.atomic_json(a.out/'summary.json',{'mode':a.mode,'levels':reports,'scope':'Two waves per level on five representative cases; not a quota guarantee or full 305-case acceptance.'})
        print(json.dumps(report,ensure_ascii=False),flush=True)
        if report['failed']:
            print('STOP: first failed level; inspect failures before increasing load.',flush=True);break

if __name__=='__main__':main()
