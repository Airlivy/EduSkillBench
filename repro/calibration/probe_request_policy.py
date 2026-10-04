"""Probe the exact configured request policy, without silently enabling thinking."""
import argparse,json,os
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from repro import source_runner as runner
from repro.source_protocol import load_release
from repro.protocol import MODELS


def one(model,prompt,out):
    dest=Path(out)/model;dest.mkdir(parents=True,exist_ok=True)
    options=runner.model_options(model)
    try:
        answer,meta=runner.judge.call_judge(prompt,model,telemetry_path=dest/'trace.json',**options)
        (dest/'answer.txt').write_text(answer)
        runner.judge.atomic_json(dest/'response.json',meta)
        result={'model':model,'options':options,'status':'complete' if meta.get('stop_reason')=='end_turn' and answer.strip() else 'incomplete',
                'returned_thinking':bool(meta.get('thinking_chars')),
                **{k:meta.get(k) for k in ['stop_reason','elapsed_seconds','thinking_chars','text_chars','usage','request_id']}}
    except runner.judge.JudgeError as exc:
        result={'model':model,'options':options,'status':'failed','category':exc.category,'metadata':exc.metadata}
    runner.judge.atomic_json(dest/'result.json',result);return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execute',action='store_true');ap.add_argument('--api-config',type=Path,default=Path(__file__).resolve().parents[1]/'api_config.json');a=ap.parse_args()
    runner.load_api_config(a.api_config)
    _,cases,_=load_release();case=next(c for c in cases if c['task_id']=='hinge-question-designer__03')
    a.out.mkdir(parents=True,exist_ok=True)
    runner.judge.atomic_json(a.out/'plan.json',{'task_id':case['task_id'],'options':{m:runner.model_options(m) for m in MODELS},'purpose':'capability probe, not benchmark scores','retries':0})
    if not a.execute:return
    runner.load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1'
    results=[]
    with ProcessPoolExecutor(max_workers=5) as pool:
        for f in as_completed([pool.submit(one,m,case['context']+'\n\n'+case['user_prompt'],a.out) for m in MODELS]):
            result=f.result();results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
            runner.judge.atomic_json(a.out/'summary.json',{'expected':len(MODELS),'finished':len(results),'results':results})


if __name__=='__main__':main()
