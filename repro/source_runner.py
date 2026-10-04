"""Bounded, resumable native-rubric evaluation. Default is an offline plan."""
import argparse
from contextlib import contextmanager
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from collections import deque
import fcntl
import json
import os
from pathlib import Path
import time
try:
    from . import judge
    from .credentials import load_env_file
    from .source_protocol import VERSION,digest,load_release,prompt,schema,validate
    from .protocol import MODELS,check_models
except ImportError:
    import judge
    from credentials import load_env_file
    from source_protocol import VERSION,digest,load_release,prompt,schema,validate
    from protocol import MODELS,check_models

LIMITS={'headers':45.,'idle':45.,'content_idle':60.,'total':120.}
OPTIONS={'thinking_mode':'disabled','max_output_tokens':6144,'timeouts':LIMITS}
RECOVERY_POLICY='shared-two-attempts-validation-feedback-v1'
MAX_WORKERS=16
DEFAULT_WORKERS=16
SLOW_MODEL_WORKERS=2
GLM_API_PROTOCOL='messages'
API_OVERRIDES={}
MODEL_OVERRIDES={}

@contextmanager
def run_lock(out):
    """One coordinator owns a run's plan, preflight and summary."""
    with (Path(out)/'.run.lock').open('a') as guard:
        try:fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('该输出目录已有运行进程；请等待完成，不要重复启动。') from None
        try:yield
        finally:fcntl.flock(guard.fileno(),fcntl.LOCK_UN)

def model_options(model):
    options={**OPTIONS,**judge.minimal_model_options(model)}
    if model in ('glm-5.3','glm-5.3-flash') and GLM_API_PROTOCOL=='chat_completions':
        options['api_protocol']='chat_completions'
    options.update(API_OVERRIDES)
    options.update(MODEL_OVERRIDES.get(model,{}))
    if options.get('thinking_mode')=='disabled':
        options.pop('thinking_budget',None)
        options.pop('effort',None)
    return options


def load_api_config(path):
    """Read explicit request limits; resolved options are frozen in plan/bindings."""
    global GLM_API_PROTOCOL
    config=json.loads(Path(path).read_text())
    if not isinstance(config,dict) or 'max_output_tokens' not in config or set(config)-{'max_output_tokens','total_timeout_seconds','glm_api_protocol','api_protocol','thinking_mode','model_overrides'}:
        raise ValueError('Invalid API config fields')
    value=config['max_output_tokens']
    if type(value) is not int or not 1025 <= value <= 16000:
        raise ValueError('max_output_tokens must be an integer from 1025 to 16000')
    total=config.get('total_timeout_seconds',LIMITS['total'])
    if type(total) not in (int,float) or not 60 <= total <= 600:
        raise ValueError('total_timeout_seconds must be a finite number from 60 to 600')
    protocol=config.get('glm_api_protocol','messages')
    if protocol not in ('messages','chat_completions'):raise ValueError('Invalid glm_api_protocol')
    if 'api_protocol' in config and config['api_protocol'] not in ('messages','chat_completions'):raise ValueError('Invalid api_protocol')
    if 'thinking_mode' in config and config['thinking_mode'] not in ('enabled','disabled'):raise ValueError('Invalid thinking_mode')
    if 'api_protocol' in config and 'glm_api_protocol' in config:raise ValueError('Choose api_protocol or glm_api_protocol, not both')
    overrides=config.get('model_overrides',{})
    if not isinstance(overrides,dict) or set(overrides)-set(MODELS):raise ValueError('Unknown model override')
    for model,entry in overrides.items():
        if not isinstance(entry,dict) or set(entry)-{'thinking_mode','effort'}:raise ValueError('Invalid model override fields')
        if entry.get('thinking_mode','enabled') not in ('enabled','disabled'):raise ValueError('Invalid model thinking mode')
        if entry.get('effort','low') not in ('low','high','max'):raise ValueError('Invalid model effort')
    OPTIONS.update(max_output_tokens=value,timeouts={**LIMITS,'total':float(total)})
    GLM_API_PROTOCOL=protocol
    API_OVERRIDES.clear()
    API_OVERRIDES.update({k:config[k] for k in ('api_protocol','thinking_mode') if k in config})
    MODEL_OVERRIDES.clear();MODEL_OVERRIDES.update(overrides)


def schedule_cells(pool,cases,models,judge_model,out,workers,retry_failed=False):
    """Bound active cells and rotate models; thinking calls cannot occupy all slots."""
    pending={m:deque(cases) for m in models}
    order=deque(models)
    active={m:0 for m in models};futures={}
    caps={m:min(workers,SLOW_MODEL_WORKERS) if model_options(m).get('thinking_mode')=='enabled' else workers for m in models}
    while any(pending.values()) or futures:
        while len(futures)<workers:
            submitted=False
            for _ in range(len(order)):
                if len(futures)>=workers:break
                model=order.popleft();order.append(model)
                if pending[model] and active[model]<caps[model]:
                    future=pool.submit(run_cell,pending[model].popleft(),model,judge_model,out,retry_failed)
                    futures[future]=model;active[model]+=1;submitted=True
            if not submitted:break
        done,_=wait(futures,return_when=FIRST_COMPLETED)
        for future in done:
            active[futures.pop(future)]-=1
            yield future.result()


def exchange(text,model,dest,output_schema=None,call=None,validator=None):
    """Persist traces/raw output; at most 2 calls, never retry budget exhaustion."""
    call=call or judge.call_judge
    request_text=text
    for attempt in range(2):
        stamp=str(time.time_ns())
        try:
            answer,metadata=call(request_text,model,telemetry_path=dest/f'trace_{stamp}.json',output_schema=output_schema,**model_options(model))
            (dest/f'raw_{stamp}.txt').write_text(answer)
            judge.atomic_json(dest/f'response_{stamp}.json',metadata)
            stop=metadata.get('stop_reason')
            if stop=='max_tokens':raise judge.JudgeError('output_truncated',False,metadata)
            if stop not in ('end_turn','stop_sequence'):raise judge.JudgeError('incomplete_response',True,metadata)
            if not answer.strip():raise judge.JudgeError('empty_response',True,metadata)
            if validator is not None:
                try:validator(answer)
                except (ValueError,KeyError,TypeError) as exc:
                    detail=str(exc)[:200]
                    request_text=text+'\n上次输出未通过程序校验：'+detail+'。请重新评审并返回完整 JSON，逐项检查编号、等级及证据编号；不要修改评分标准或为了通过校验提高等级。'
                    raise judge.JudgeError('invalid_verdict',True,{**metadata,'validation_error':detail}) from None
            return answer,metadata
        except judge.JudgeError as exc:
            judge.atomic_json(dest/f'failure_{stamp}.json',{'category':exc.category,'metadata':exc.metadata,'attempt':attempt+1,'retryable':exc.retryable,'recovery_policy':RECOVERY_POLICY})
            if not exc.retryable or attempt==1 or exc.metadata.get('timeout_kind')=='total_deadline':raise
            time.sleep(1)


def evaluate_native(case,answer,model,dest,*,retry_failed=False,call=None):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    binding=digest({'case':case,'answer':answer,'model':model,'options':model_options(model),'version':VERSION,'recovery_policy':RECOVERY_POLICY,
                    'prompt_sha256':digest(prompt(case,answer)),
                    'endpoint':os.environ.get('ANTHROPIC_BASE_URL','')})
    with (dest/'.lock').open('a') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise judge.JudgeError('already_running') from None
        result=dest/'result.json';failure=dest/'error.json'
        if result.exists():
            saved=json.loads(result.read_text())
            if saved['binding']!=binding:raise ValueError('Native cached inputs changed')
            expected=validate(saved['raw_verdict'],case,answer,require_counterevidence=True)
            if saved['verdict']!=expected:raise ValueError('Native cached verdict changed')
            return expected
        if failure.exists():
            previous=json.loads(failure.read_text())
            if previous['binding']!=binding:
                raise ValueError('Failure inputs changed: use a fresh run directory')
            if not retry_failed:
                raise judge.JudgeError('previous_failure_requires_retry_failed',False,previous)
        try:
            active=[r for r in case['criteria'] if r['id'] in case['applicable_ids']]
            text,metadata=exchange(prompt(case,answer),model,dest,schema(active),call,
                                   validator=lambda text:validate(judge.decode_verdict(text),case,answer,require_counterevidence=True))
            # Strict validation, not permissive coercion or silent evidence repair.
            parsed=judge.decode_verdict(text)
            verdict=validate(parsed,case,answer,require_counterevidence=True)
            judge.atomic_json(result,{'binding':binding,'raw_verdict':parsed,'verdict':verdict,'metadata':metadata})
            failure.unlink(missing_ok=True)
            return verdict
        except (judge.JudgeError,ValueError,KeyError,TypeError) as exc:
            record={'binding':binding,'status':'pending_review','score':None,'category':getattr(exc,'category','invalid_verdict'),
                    'metadata':getattr(exc,'metadata',{}),'validation_error':getattr(exc,'metadata',{}).get('validation_error') if isinstance(exc,judge.JudgeError) else str(exc)[:200],'retry_policy':'最多两次请求，网络与格式纠错共享次数；仍失败则保留答案，显式 --retry-failed 仅重试失败阶段。'}
            judge.atomic_json(failure,record)
            if isinstance(exc,judge.JudgeError):raise
            raise judge.JudgeError('invalid_verdict',False,record) from None


def run_cell(case,model,judge_model,out,retry_failed=False,generation_prompt=None):
    dest=Path(out)/model/case['task_id'];dest.mkdir(parents=True,exist_ok=True)
    with (dest/'.cell.lock').open('a') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'task_id':case['task_id'],'model':model,'status':'already_running','score':None}
        try:
            answer_path=dest/'answer.json'
            binding=digest({'case':case,'model':model,'options':model_options(model),'endpoint':os.environ.get('ANTHROPIC_BASE_URL','')})
            if generation_prompt is not None:binding=digest({'base_binding':binding,'generation_prompt':generation_prompt})
            if answer_path.exists():
                saved=json.loads(answer_path.read_text())
                if saved['binding']!=binding or saved['text_sha256']!=digest(saved['text']):raise ValueError('Saved answer changed')
                answer=saved['text']
            else:
                if (dest/'generation_error.json').exists():
                    previous=json.loads((dest/'generation_error.json').read_text())
                    if previous.get('binding')!=binding:
                        raise ValueError('Generation failure inputs changed: use a fresh run directory')
                    if not retry_failed:
                        raise judge.JudgeError('generation_previously_failed',False,previous.get('metadata',{}))
                stage=dest/'generation';stage.mkdir(exist_ok=True)
                try:
                    answer,metadata=exchange(generation_prompt if generation_prompt is not None else case['context']+'\n\n'+case['user_prompt'],model,stage)
                except judge.JudgeError as exc:
                    judge.atomic_json(dest/'generation_error.json',{'binding':binding,'category':exc.category,'metadata':exc.metadata,'score':None})
                    raise
                judge.atomic_json(answer_path,{'binding':binding,'text':answer,'text_sha256':digest(answer),'metadata':metadata})
                (dest/'answer.txt').write_text(answer)
                (dest/'generation_error.json').unlink(missing_ok=True)
            if case['suite']=='core':
                # Preserve the existing core rubric and score semantics; only bounded transport is reused.
                old={'question':case['context']+'\n\n'+case['user_prompt'],'ground_truth':case['expected_output'],
                     'judge_model':judge_model,'score_metric':'weighted','rubric':[{'id':f'C{i+1}',**r} for i,r in enumerate(case['rubric'])],
                     'execution_options':model_options(judge_model),'endpoint':os.environ.get('ANTHROPIC_BASE_URL',''),
                     'recovery_policy':RECOVERY_POLICY}
                def bounded(p,m):
                    stage=dest/'grading';stage.mkdir(exist_ok=True)
                    return judge.call_judge(p,m,telemetry_path=stage/f'trace_{time.time_ns()}.json',output_schema=judge.verdict_schema(old['rubric']),**model_options(m))
                verdict=judge.evaluate(old,answer,dest/'grading',call=bounded,retry_blocked=retry_failed,
                                       max_attempts=2,stop_on_deadline=True,require_explicit_retry=True)
            else:verdict=evaluate_native(case,answer,judge_model,dest/'grading',retry_failed=retry_failed)
            summary={'task_id':case['task_id'],'model':model,'suite':case['suite'],'status':'evaluated',
                     'score':verdict['score'],'score_interval':verdict.get('score_interval')}
            if case['suite']=='core':
                summary['critical_pass']=verdict.get('critical_pass')
            else:
                summary['criterion_levels']={item['id']:item['level'] for item in verdict.get('items',[])}
                flagged=[item['id'] for item in verdict.get('items',[]) if item.get('counterevidence')]
                summary['review_required']=bool(flagged)
                summary['counterevidence_review_ids']=flagged
                summary['review_note']='反证也可能被模型误识别；含反证的等级应复核原回答是否实际采纳该说法。' if flagged else ''
        except (judge.JudgeError,ValueError,KeyError,OSError) as exc:
            summary={'task_id':case['task_id'],'model':model,'suite':case['suite'],'status':'pending_review' if (dest/'answer.json').exists() else 'generation_failed',
                     'score':None,'category':getattr(exc,'category',type(exc).__name__),
                     'failed_stage':'grading' if (dest/'answer.json').exists() else 'generation',
                     'failure_details':{k:v for k,v in getattr(exc,'metadata',{}).items() if k in (
                         'timeout_kind','network_error_kind','stage','elapsed_seconds','first_text_seconds',
                         'thinking_chars','text_chars','validation_error','request_id')}}
        judge.atomic_json(dest/'status.json',summary)
        return summary


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--dataset',choices=['core','advisory','all'],default='all')
    ap.add_argument('--models',nargs='+',default=['glm-5.3']);ap.add_argument('--judge-model',choices=MODELS,default='deepseek-v4-pro')
    ap.add_argument('--task-id',action='append');ap.add_argument('--workers',type=int,choices=range(1,MAX_WORKERS+1),default=DEFAULT_WORKERS,
                    help='全局并发上限，默认16，可选1—16；每个保留思考的作答模型最多2路，避免慢请求占满队列')
    ap.add_argument('--api-config',type=Path,help='JSON请求配置；max_output_tokens用于作答和评分，启动时冻结；省略沿用6144')
    ap.add_argument('--env-file',type=Path);ap.add_argument('--base-url');ap.add_argument('--execute',action='store_true');ap.add_argument('--retry-failed',action='store_true')
    a=ap.parse_args();check_models(a.models)
    if a.api_config:
        try:load_api_config(a.api_config)
        except (OSError,ValueError) as exc:ap.error(str(exc))
    if a.env_file:load_env_file(a.env_file)
    if a.base_url:os.environ['ANTHROPIC_BASE_URL']=a.base_url
    directory,cases,manifest=load_release()
    cases=[c for c in cases if a.dataset=='all' or c['suite']==a.dataset]
    if a.task_id:
        wanted=set(a.task_id)
        if not wanted <= {c['task_id'] for c in cases}:ap.error('Unknown task ID for selected suite')
        cases=[c for c in cases if c['task_id'] in wanted]
    a.out.mkdir(parents=True,exist_ok=True)
    with run_lock(a.out):
        return execute_plan(a,ap,cases,manifest)


def execute_plan(a,ap,cases,manifest):
    plan={'protocol':VERSION,'recovery_policy':RECOVERY_POLICY,'release_sha256':digest(manifest),'case_sha256':digest(cases),'dataset':a.dataset,'task_ids':[c['task_id'] for c in cases],
          'models':a.models,'judge_model':a.judge_model,'condition':'baseline','options':{m:model_options(m) for m in set(a.models+[a.judge_model])},'endpoint':os.environ.get('ANTHROPIC_BASE_URL','')}
    plan_path=a.out/'plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text())!=plan:ap.error('Frozen plan changed; use a new output directory')
    judge.atomic_json(plan_path,plan)
    if not a.execute:
        print(json.dumps({'tasks':len(cases),'models':a.models,'cells':len(cases)*len(a.models),'status':'plan_only','command':'Add --execute to run paid calls'},ensure_ascii=False));return
    probe_dir=a.out/'preflight';probe_dir.mkdir(exist_ok=True)
    for model in dict.fromkeys(a.models+[a.judge_model]):
        stage=probe_dir/model;stage.mkdir(exist_ok=True)
        cached=stage/'ok.json'
        if not cached.exists():
            try:
                _,metadata=exchange('只回答 OK。',model,stage)
                judge.atomic_json(cached,{'model':model,'options':model_options(model),'metadata':metadata})
            except judge.JudgeError as exc:
                judge.atomic_json(stage/'error.json',{'category':exc.category,'metadata':exc.metadata})
                raise SystemExit('模型请求参数或接口预检失败，未启动整批任务：'+model+' '+exc.category)
    results=[]
    expected=len(cases)*len(a.models)
    judge.atomic_json(a.out/'concurrency.json',{'global_workers':a.workers,'thinking_workers_per_model':min(a.workers,SLOW_MODEL_WORKERS),
                     'scheduling':'round_robin_bounded_active_cells','scope':'保留思考的模型仍可能超时或耗尽输出预算；并发限制不是成功保证。'})
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for result in schedule_cells(pool,cases,a.models,a.judge_model,a.out,a.workers,a.retry_failed):
            results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
            judge.atomic_json(a.out/'summary.json',{'expected':expected,'finished':len(results),'evaluated':sum(r['status']=='evaluated' for r in results),
                'content_review_required':sum(bool(r.get('review_required')) for r in results),
                'results':results,'aggregation':'core数值分与advisory原文等级分开，不混算；pending不当作0分。evaluated表示技术上完成评分；含反证的结果需复核，不代表语义已经验收。'})
    if any(r['status']!='evaluated' for r in results):raise SystemExit(1)
if __name__=='__main__':main()
