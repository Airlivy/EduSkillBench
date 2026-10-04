"""Frozen native-rubric, single-turn baseline/forced-skill experiment."""
import argparse
from collections import Counter,deque
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
import hashlib,json,multiprocessing,os,shutil
from pathlib import Path
from . import source_runner as runner
from .source_protocol import load_release,digest
from .protocol import MODELS

ROOT=Path(__file__).resolve().parents[1]
CONDITIONS=('baseline','with-skill')


def skill_id(case):
    derived=case['task_id'].split('__')[0]
    if case.get('skill_id',derived)!=derived:raise ValueError('Skill identity mismatch')
    return derived


def skill_inventory(cases):
    root=ROOT/'skills/single_turn';inventory={};bundles={}
    for skill in sorted({skill_id(c) for c in cases}):
        directory=root/skill
        if not (directory/'SKILL.md').is_file():raise ValueError('Missing skill: '+skill)
        files=sorted((p for p in directory.rglob('*') if p.is_file()
                      and not {'evals','__pycache__','.git'}.intersection(p.relative_to(directory).parts)),
                     key=lambda p:(p.name!='SKILL.md',str(p)))
        inventory[skill]={};parts=[]
        for path in files:
            if not path.resolve().is_relative_to(directory.resolve()):raise ValueError('Skill symlink leaves directory')
            name=path.relative_to(directory).as_posix();content=path.read_text(encoding='utf-8')
            inventory[skill][name]=hashlib.sha256(path.read_bytes()).hexdigest()
            parts.append('### Skill file: '+name+'\n'+content)
        bundles[skill]='\n\n'.join(parts)
    return inventory,bundles


def make_prompt(case,condition,bundles):
    question=case['context']+'\n\n'+case['user_prompt']
    if condition=='baseline':return question
    if condition!='with-skill':raise ValueError('Unknown condition')
    return question+'\n\n## Required procedure and supplied skill resources\n'+bundles[skill_id(case)]


def work(case,model,condition,judge_model,out,prompt):
    result=runner.run_cell(case,model,judge_model,Path(out)/condition,generation_prompt=prompt)
    result={**result,'condition':condition}
    runner.judge.atomic_json(Path(out)/condition/model/case['task_id']/'status.json',result)
    return result


def schedule(pool,cells,out,judge_model,workers):
    pending={m:deque(c for c in cells if c[1]==m) for m in MODELS};order=deque(MODELS)
    active=Counter();futures={}
    while any(pending.values()) or futures:
        while len(futures)<workers:
            submitted=False
            for _ in range(len(order)):
                m=order.popleft();order.append(m)
                cap=2 if runner.model_options(m)['thinking_mode']=='enabled' else workers
                if pending[m] and active[m]<cap and len(futures)<workers:
                    case,model,condition,prompt=pending[m].popleft()
                    f=pool.submit(work,case,model,condition,judge_model,out,prompt)
                    futures[f]=m;active[m]+=1;submitted=True
            if not submitted:break
        done,_=wait(futures,return_when=FIRST_COMPLETED)
        for f in done:
            active[futures.pop(f)]-=1
            yield f.result()


def pilot_ok(results):
    good=[r for r in results if r['status']=='evaluated']
    return (all(any(r['model']==m and r['condition']==c for r in good) for m in MODELS for c in CONDITIONS)
            and all(any(r['suite']==s and r['condition']==c for r in good) for s in ('core','advisory') for c in CONDITIONS))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--api-config',type=Path,required=True)
    ap.add_argument('--env-file',type=Path);ap.add_argument('--execute',action='store_true')
    ap.add_argument('--workers',type=int,choices=range(1,17),default=16)
    a=ap.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    with runner.run_lock(a.out):
        def state(status,**extra):
            runner.judge.atomic_json(a.out/'process.json',{'status':status,'pid':os.getpid(),
                'updated_at':datetime.now(timezone.utc).isoformat(),**extra})
        try:
            runner.load_api_config(a.api_config)
            if a.env_file:runner.load_env_file(a.env_file)
            endpoint='https://ark.cn-beijing.volces.com/api/plan/v1';os.environ['ANTHROPIC_BASE_URL']=endpoint
            release,cases,manifest=load_release();inventory,bundles=skill_inventory(cases)
            if len(cases)!=305 or len({c['task_id'] for c in cases})!=305:raise ValueError('Expected exactly 305 cases')
            for c in cases:skill_id(c)
            options={m:runner.model_options(m) for m in MODELS}
            if any(o.get('api_protocol')!='chat_completions' or o['max_output_tokens']!=10000 or o['timeouts']['total']!=120 for o in options.values()):raise ValueError('Formal run requires Chat/10000/120s for all models')
            code={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'repro').rglob('*.py'))}
            plan={'protocol':'native-paired-forced-resources-v1','release_sha256':digest(manifest),'case_sha256':digest(cases),
                  'models':list(MODELS),'conditions':list(CONDITIONS),'task_ids':[c['task_id'] for c in cases],
                  'expected':3050,'options':options,'endpoint':endpoint,'judge_model':'deepseek-v4-pro',
                  'workers':a.workers,'thinking_workers_per_model':2,'skill_files':inventory,'code':code,
                  'skill_mode':'forced text: all skill files supplied in prompt; no agent tools or automatic skill discovery',
                  'recovery_policy':runner.RECOVERY_POLICY,'pilot_included':True,
                  'pilot_task_ids':['hinge-question-designer__03','lesson-builder__cn22_01']}
            plan_path=a.out/'plan.json'
            if plan_path.exists() and json.loads(plan_path.read_text())!=plan:raise ValueError('Frozen plan changed; new directory required')
            runner.judge.atomic_json(plan_path,plan)
            snapshot=a.out/'snapshot'
            if not snapshot.exists():
                shutil.copytree(release,snapshot/'release')
                shutil.copy2(a.api_config,snapshot/'api_config.json')
                for name in code:
                    dest=snapshot/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
                for skill,files in inventory.items():
                    for name in files:
                        dest=snapshot/'skills'/skill/name;dest.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(ROOT/'skills/single_turn'/skill/name,dest)
            cells=[]
            for i,case in enumerate(cases):
                prompts={c:make_prompt(case,c,bundles) for c in CONDITIONS}
                for condition,text in prompts.items():
                    dest=a.out/'inputs'/condition/(case['task_id']+'.txt');dest.parent.mkdir(parents=True,exist_ok=True)
                    if dest.exists() and dest.read_bytes()!=text.encode('utf-8'):raise ValueError('Frozen prompt changed')
                    dest.write_text(text)
                for j,m in enumerate(MODELS):
                    for condition in CONDITIONS[::1 if (i+j)%2==0 else -1]:cells.append((case,m,condition,prompts[condition]))
            runner.judge.atomic_json(a.out/'input_hashes.json',{str(p.relative_to(a.out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.out/'inputs').rglob('*.txt')})
            if not a.execute:state('plan_only',expected=len(cells));print('Plan verified: 3050 cells, 610 prompts, 14 skills');return
            results=[]
            def record(result,phase):
                results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
                runner.judge.atomic_json(a.out/'summary.json',{'expected':3050,'finished':len(results),
                    'evaluated':sum(r['status']=='evaluated' for r in results),
                    'content_review_required':sum(bool(r.get('review_required')) for r in results),
                    'by_condition':{c:dict(Counter(r['status'] for r in results if r['condition']==c)) for c in CONDITIONS},
                    'phase':phase,'results':results,'aggregation':'core数值分与advisory等级分开；失败不当作0分；含反证结果需复核。'})
                state(phase,finished=len(results),expected=3050)
            pilot=[c for c in cells if c[0]['task_id'] in plan['pilot_task_ids']]
            if len(pilot)!=20:raise ValueError('Expected 20 pilot cells')
            state('pilot_running',finished=0,expected=3050)
            with ProcessPoolExecutor(max_workers=a.workers,mp_context=multiprocessing.get_context('fork')) as pool:
                for result in schedule(pool,pilot,a.out,plan['judge_model'],a.workers):record(result,'pilot_running')
                passed=pilot_ok(results)
                runner.judge.atomic_json(a.out/'pilot_gate.json',{'passed':passed,'finished':len(results),
                    'criterion':'At least one evaluated cell per model/condition and per suite/condition; failed pilot cells remain in results.'})
                if not passed:state('pilot_failed',finished=len(results),expected=3050);return
                remaining=[c for c in cells if c[0]['task_id'] not in plan['pilot_task_ids']]
                state('running',finished=len(results),expected=3050)
                for result in schedule(pool,remaining,a.out,plan['judge_model'],a.workers):record(result,'running')
            state('completed',finished=len(results),expected=3050,failures=sum(r['status']!='evaluated' for r in results))
        except Exception as exc:
            state('error',error_type=type(exc).__name__,message=str(exc));raise


if __name__=='__main__':main()
