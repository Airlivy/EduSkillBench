"""Read-only capability probe against the five explicitly named model IDs."""
import argparse,json,os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from repro.judge import call_judge,JudgeError,atomic_json
from repro.credentials import load_env_file
from repro.protocol import MODELS


def one(model,out):
    dest=Path(out)/model;dest.mkdir(parents=True,exist_ok=True)
    # Try disabled first except GLM 5.3 whose rejection is already documented and logged.
    candidates=([{'thinking_mode':'disabled'}] if not model.startswith('glm-5.3') else [])+[
        {'thinking_mode':'enabled','thinking_budget':1024,'effort':x} for x in ('low','medium','high')]
    trials=[]
    for i,options in enumerate(candidates):
        try:
            answer,meta=call_judge('只回答 OK，不需要解释。',model,telemetry_path=dest/f'{i}.trace.json',
                timeouts={'headers':30.,'idle':30.,'content_idle':45.,'total':60.},max_output_tokens=2048,**options)
            record={'options':options,'status':'accepted','stop_reason':meta.get('stop_reason'),'thinking_chars':meta.get('thinking_chars'),
                    'text_chars':meta.get('text_chars'),'elapsed_seconds':meta.get('elapsed_seconds'),'answer':answer}
            trials.append(record);break
        except JudgeError as exc:
            trials.append({'options':options,'status':'failed','category':exc.category,'metadata':exc.metadata})
            # Only a rejected parameter permits trying a different capability setting.
            if exc.metadata.get('http_status')!=400:break
    result={'model':model,'trials':trials};atomic_json(dest/'probe.json',result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print('5 models; probe disabled then increasing supported effort; --execute enables paid calls');return
    load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1'
    a.out.mkdir(parents=True,exist_ok=True);results=[]
    with ProcessPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(one,m,a.out) for m in MODELS]):
            r=f.result();results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
            atomic_json(a.out/'summary.json',results)
if __name__=='__main__':main()
