"""Resume failed cells using the original frozen implementation and inputs."""
import argparse
from collections import Counter,deque
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
import hashlib,json,multiprocessing,os,shutil,sys,time
from pathlib import Path


def read(path):return json.loads(Path(path).read_text())
def key(row):return row['model'],row['condition'],row['task_id']
def quota_error(metadata):
    text=str(metadata.get('provider_message','')).lower()
    return metadata.get('http_status')==429 and any(s in text for s in ('weekly usage quota','daily usage quota','monthly usage quota','insufficient quota','quota exhausted'))


def guarded_call(*args,**kwargs):
    # Gates apply before requests, so waiting is not counted as provider latency.
    while True:
        if STOP.is_set():raise RUNNER.judge.JudgeError('quota_paused',False)
        with GATE_LOCK:
            delay=max(NEXT_CALL.value,COOLDOWN.value)-time.monotonic()
            if delay<=0:NEXT_CALL.value=time.monotonic()+0.5;break
        time.sleep(min(delay,0.5))
    try:return ORIGINAL_CALL(*args,**kwargs)
    except RUNNER.judge.JudgeError as exc:
        if quota_error(exc.metadata):
            STOP.set();exc.retryable=False
        elif exc.metadata.get('http_status')==429:
            with GATE_LOCK:COOLDOWN.value=max(COOLDOWN.value,time.monotonic()+30)
        raise


def work(case,model,condition,prompt,out,judge_model):
    result=RUNNER.run_cell(case,model,judge_model,Path(out)/condition,retry_failed=True,generation_prompt=prompt)
    result={**result,'condition':condition}
    RUNNER.judge.atomic_json(Path(out)/condition/model/case['task_id']/'status.json',result)
    return result


def main():
    global RUNNER,ORIGINAL_CALL,STOP,GATE_LOCK,NEXT_CALL,COOLDOWN
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--env-file',type=Path,required=True);ap.add_argument('--execute',action='store_true')
    a=ap.parse_args();base=a.base.resolve();out=a.out.resolve()
    if out.exists():ap.error('Use a fresh output directory for each recovery round')
    plan=read(base/'plan.json');original=read(base/'summary.json')['results']
    expected={(m,c,t) for m in plan['models'] for c in plan['conditions'] for t in plan['task_ids']}
    if len(original)!=len(expected) or {key(r) for r in original}!=expected:raise ValueError('Incomplete original inventory')
    for name,sha in plan['code'].items():
        if hashlib.sha256((base/'snapshot'/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen code changed: '+name)
    for name,sha in read(base/'input_hashes.json').items():
        if hashlib.sha256((base/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen prompt changed: '+name)
    sys.path.insert(0,str(base/'snapshot'))
    from repro import source_runner as frozen
    from repro.source_protocol import digest
    RUNNER=frozen
    if not Path(frozen.__file__).resolve().is_relative_to(base/'snapshot'):raise ValueError('Must load frozen code')
    frozen.load_api_config(base/'snapshot/api_config.json')
    if {m:frozen.model_options(m) for m in plan['models']}!=plan['options']:raise ValueError('Request options changed')
    cases_list=read(base/'snapshot/release/cases.json')
    if digest(cases_list)!=plan['case_sha256']:raise ValueError('Cases changed')
    cases={c['task_id']:c for c in cases_list}
    selected=[r for r in original if r['status']!='evaluated']
    out.mkdir(parents=True);atomic=frozen.judge.atomic_json
    recovery={'base_directory':str(base),'expected':len(selected),'original_expected':len(original),
        'base_plan_sha256':digest(plan),'options':plan['options'],'workers':16,'thinking_workers_per_model':2,
        'transport_scheduling':'Shared minimum 0.5 seconds between request starts; 30s cooldown on frequency 429; stop dispatch on quota exhaustion.',
        'policy':'One recovery round. Reuse saved answers; explicit retry only failed stages; original scores and logs preserved.',
        'resume_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    atomic(out/'recovery_plan.json',recovery);atomic(out/'original_summary.json',read(base/'summary.json'))
    atomic(out/'retry_selection.json',selected);shutil.copy2(Path(__file__),out/'resume_paired.py')
    copied_answers=0
    for r in selected:
        rel=Path(r['condition'])/r['model']/r['task_id'];src=base/rel
        if (src/'answer.json').exists():
            answer=read(src/'answer.json');prompt=(base/'inputs'/r['condition']/(r['task_id']+'.txt')).read_bytes().decode()
            binding=digest({'case':cases[r['task_id']],'model':r['model'],'options':plan['options'][r['model']],'endpoint':plan['endpoint']})
            if answer['text_sha256']!=digest(answer['text']) or answer['binding']!=digest({'base_binding':binding,'generation_prompt':prompt}):raise ValueError('Saved answer binding mismatch')
            copied_answers+=1
        shutil.copytree(src,out/rel,ignore=shutil.ignore_patterns('*.lock'))
    atomic(out/'preparation.json',{'failed_cells':len(selected),'answers_reused':copied_answers,'generation_needed':len(selected)-copied_answers})
    results={}
    def save(status):
        rows=[]
        for row in original:
            latest=results.get(key(row));r=latest if latest is not None else row
            source=out if latest is not None else base
            rows.append({**r,'result_directory':str(source/row['condition']/row['model']/row['task_id']),
                         'recovery_attempted':latest is not None,'original_status':row['status']})
        atomic(out/'summary.json',{'expected':len(rows),'finished':len(rows),'evaluated':sum(r['status']=='evaluated' for r in rows),
            'recovery_expected':len(selected),'recovery_finished':len(results),'phase':status,
            'by_condition':{c:dict(Counter(r['status'] for r in rows if r['condition']==c)) for c in plan['conditions']},
            'content_review_required':sum(bool(r.get('review_required')) for r in rows),'results':rows})
        atomic(out/'process.json',{'status':status,'pid':os.getpid(),'updated_at':datetime.now(timezone.utc).isoformat(),
            'expected':len(selected),'finished':len(results),'original_expected':len(rows)})
    with frozen.run_lock(out):
        save('prepared')
        if not a.execute:print(json.dumps(recovery));return
        frozen.load_env_file(a.env_file);os.environ['ANTHROPIC_BASE_URL']=plan['endpoint']
        ctx=multiprocessing.get_context('fork');STOP=ctx.Event();GATE_LOCK=ctx.Lock()
        NEXT_CALL=ctx.Value('d',0);COOLDOWN=ctx.Value('d',0)
        ORIGINAL_CALL=frozen.judge.call_judge;frozen.judge.call_judge=guarded_call
        pending={m:deque(r for r in selected if r['model']==m) for m in plan['models']}
        order=deque(plan['models']);active=Counter();futures={};save('running')
        try:
            with ProcessPoolExecutor(max_workers=16,mp_context=ctx) as pool:
                while any(pending.values()) or futures:
                    while len(futures)<16 and not STOP.is_set():
                        added=False
                        for _ in range(len(order)):
                            m=order.popleft();order.append(m);cap=2 if plan['options'][m]['thinking_mode']=='enabled' else 16
                            if pending[m] and active[m]<cap and len(futures)<16 and not STOP.is_set():
                                r=pending[m].popleft();prompt=(base/'inputs'/r['condition']/(r['task_id']+'.txt')).read_bytes().decode()
                                f=pool.submit(work,cases[r['task_id']],m,r['condition'],prompt,out,plan['judge_model'])
                                futures[f]=m;active[m]+=1;added=True
                        if not added:break
                    if not futures:break
                    done,_=wait(futures,return_when=FIRST_COMPLETED)
                    for f in done:
                        active[futures.pop(f)]-=1;r=f.result();results[key(r)]=r
                        print(json.dumps(r,ensure_ascii=False),flush=True)
                    save('quota_stopping' if STOP.is_set() else 'running')
            save('quota_exhausted' if STOP.is_set() else 'completed')
        except Exception as exc:
            save('error');atomic(out/'fatal_error.json',{'type':type(exc).__name__,'message':str(exc)});raise


if __name__=='__main__':main()
