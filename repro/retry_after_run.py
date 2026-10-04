"""Wait for a complete run, retry failed cells once, and merge with provenance."""
import argparse
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import time

from . import source_runner as runner
from .source_protocol import digest, load_release


def read(path):
    return json.loads(Path(path).read_text())


def key(row):
    return row['model'], row['task_id']


def select_failed(summary, plan):
    expected={(m,t) for m in plan['models'] for t in plan['task_ids']}
    rows=summary['results']
    if len(rows)!=len(expected) or {key(r) for r in rows}!=expected:
        raise ValueError('Original run must finish every cell before retry selection')
    return [r for r in rows if r['status']!='evaluated']


def merged_rows(original, retries, base, out, run_label='retry_16000'):
    replacements={key(r):r for r in retries}
    result=[]
    for row in original:
        replacement=replacements.get(key(row))
        if replacement is not None and row['status']=='evaluated':
            raise ValueError('Refusing to replace a successful original result')
        selected=replacement if replacement is not None else row
        if replacement is None and 'result_directory' in row:
            result.append(dict(row));continue
        previous_directory=row.get('result_directory',str(base/row['model']/row['task_id']))
        source=out if replacement is not None else base
        result.append({**selected,'result_directory':str(source/row['model']/row['task_id']),
                       'run_source':run_label if replacement is not None else 'original_6144',
                       'original_status':row.get('original_status',row['status']),
                       'original_directory':row.get('original_directory',previous_directory),
                       'attempt_history':row.get('attempt_history',[])+[{'status':row['status'],'directory':previous_directory}],
                       'retry_status':replacement['status'] if replacement is not None else None})
    return result


def save_merged(original, retries, base, out, complete=False):
    rows=merged_rows(original,retries,base,out,run_label=out.name)
    summary={'expected':len(rows),'finished':len(rows),'evaluated':sum(r['status']=='evaluated' for r in rows),
             'retry_finished':len(retries),'retry_complete':complete,
             'content_review_required':sum(bool(r.get('review_required')) for r in rows),
             'statuses':dict(Counter(r['status'] for r in rows)),
             'configuration_note':'混合配置结果：各轮输出额度与时限见各自plan.json。保留各轮记录，不作为同配置单轮成绩。',
             'results':rows}
    runner.judge.atomic_json(out/'combined_summary.json',summary)
    if not complete:return
    responses=[]
    for row in rows:
        answer=Path(row['result_directory'])/'answer.json'
        responses.append({**row,'response':read(answer)['text'] if answer.exists() else None})
    runner.judge.atomic_json(out/'combined_responses.json',responses)


def run_failed(cases, failed, judge_model, out):
    pending={m:deque(cases[r['task_id']] for r in failed if r['model']==m)
             for m in dict.fromkeys(r['model'] for r in failed)}
    order=deque(pending);active=Counter();futures={}
    # Explicit fork preserves the already validated request options in workers.
    with ProcessPoolExecutor(max_workers=16,mp_context=multiprocessing.get_context('fork')) as pool:
        while any(pending.values()) or futures:
            while len(futures)<16:
                submitted=False
                for _ in range(len(order)):
                    model=order.popleft();order.append(model)
                    cap=2 if runner.model_options(model)['thinking_mode']=='enabled' else 16
                    if pending[model] and active[model]<cap and len(futures)<16:
                        f=pool.submit(runner.run_cell,pending[model].popleft(),model,judge_model,out)
                        futures[f]=model;active[model]+=1;submitted=True
                if not submitted:break
            done,_=wait(futures,return_when=FIRST_COMPLETED)
            for f in done:
                active[futures.pop(f)]-=1
                yield f.result()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--api-config',type=Path,required=True)
    ap.add_argument('--env-file',type=Path,required=True)
    ap.add_argument('--accept-interrupted',action='store_true',help='Explicitly continue a stopped previous retry using its complete merged coverage')
    a=ap.parse_args();a.base=a.base.resolve();a.out=a.out.resolve()
    if a.base==a.out:ap.error('Retry output must be separate')
    a.out.mkdir(parents=True,exist_ok=True)
    with runner.run_lock(a.out):
        def state(status,**extra):
            runner.judge.atomic_json(a.out/'followup_status.json',{'status':status,'pid':os.getpid(),
                'updated_at':datetime.now(timezone.utc).isoformat(),**extra})
        try:
            # Load and freeze inputs now, before waiting. No credentials are saved.
            runner.load_api_config(a.api_config)
            if runner.OPTIONS['max_output_tokens']!=16000:raise ValueError('This retry requires 16000')
            runner.load_env_file(a.env_file)
            base_plan=read(a.base/'plan.json')
            coverage_plan=base_plan
            while 'models' not in coverage_plan:
                coverage_plan=read(Path(coverage_plan['base_directory'])/'plan.json')
            os.environ['ANTHROPIC_BASE_URL']=base_plan['endpoint']
            _,cases,manifest=load_release()
            if digest(cases)!=base_plan['case_sha256']:raise ValueError('Dataset changed')
            options={m:runner.model_options(m) for m in set(coverage_plan['models']+[base_plan['judge_model']])}
            plan={'base_directory':str(a.base),'base_plan_sha256':digest(base_plan),
                  'release_sha256':digest(manifest),'case_sha256':digest(cases),'options':options,
                  'judge_model':base_plan['judge_model'],'endpoint':base_plan['endpoint'],
                  'models':coverage_plan['models'],'task_ids':coverage_plan['task_ids'],
                  'workers':16,'thinking_workers_per_model':2,
                  'accept_interrupted':a.accept_interrupted,
                  'retry_policy':'One new cell attempt per failed original cell; bounded internal recovery. No repeated retry rounds.'}
            if (a.out/'plan.json').exists() and read(a.out/'plan.json')!=plan:
                raise ValueError('Retry plan changed; use a new directory')
            runner.judge.atomic_json(a.out/'plan.json',plan)
            state('waiting_for_original')
            while True:
                with (a.base/'.run.lock').open('a') as lock:
                    try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:pass
                    else:
                        if (a.base/'combined_summary.json').exists():
                            summary=read(a.base/'combined_summary.json')
                            if not summary.get('retry_complete') and not a.accept_interrupted:raise ValueError('Previous retry did not complete')
                        else:summary=read(a.base/'summary.json')
                        failed=select_failed(summary,coverage_plan)
                        break
                time.sleep(15)
            runner.judge.atomic_json(a.out/'original_summary.json',summary)
            runner.judge.atomic_json(a.out/'retry_selection.json',failed)
            print(json.dumps({'event':'retry_start','failed_cells':len(failed)}),flush=True)
            results=[];save_merged(summary['results'],results,a.base,a.out)
            state('retry_running',expected=len(failed),finished=0)
            for result in run_failed({c['task_id']:c for c in cases},failed,base_plan['judge_model'],a.out):
                results.append(result)
                print(json.dumps(result,ensure_ascii=False),flush=True)
                runner.judge.atomic_json(a.out/'retry_summary.json',{'expected':len(failed),'finished':len(results),'results':results})
                save_merged(summary['results'],results,a.base,a.out)
                state('retry_running',expected=len(failed),finished=len(results))
            save_merged(summary['results'],results,a.base,a.out,complete=True)
            state('completed',expected=len(failed),finished=len(results),
                  remaining_failures=sum(r['status']!='evaluated' for r in results))
        except Exception as exc:
            state('error',error_type=type(exc).__name__,message=str(exc))
            raise


if __name__=='__main__':main()
