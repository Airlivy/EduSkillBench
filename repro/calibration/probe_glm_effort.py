"""Isolated GLM endpoint/conciseness experiment; never changes benchmark results."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from repro import judge
from repro.credentials import load_env_file
from repro.source_protocol import load_release

BASE='https://ark.cn-beijing.volces.com/api/plan/v1'
LIMITS={'headers':45.,'idle':45.,'content_idle':60.,'total':300.}
BRIEF='请直接给出满足题目全部要求的答案，简洁表达，避免重复解释和不必要的扩展。'


def read_chat(response, trace):
    text=[];stop=None;done=False
    for raw in response:
        trace.line(raw)
        line=raw.decode('utf-8').strip()
        if not line.startswith('data:'):continue
        data=line[5:].strip()
        if data=='[DONE]':done=True;break
        event=json.loads(data)
        if event.get('model'):trace.data['response_model']=event['model']
        if event.get('error'):raise ValueError(str(event['error'])[:500])
        if event.get('id'):trace.data['request_id']=event['id']
        if event.get('usage'):trace.data['usage']=event['usage']
        for choice in event.get('choices',[]):
            delta=choice.get('delta') or {}
            trace.data['delta_fields']=sorted(set(trace.data.get('delta_fields',[]))|set(delta))
            trace.content('thinking',delta.get('reasoning_content') or '')
            value=delta.get('content') or ''
            trace.content('text',value);text.append(value)
            if choice.get('finish_reason'):stop=choice['finish_reason']
        trace.save()
    return ''.join(text),stop,done


def trial(spec):
    model,arm,prompt,out=spec;dest=Path(out)/model/arm;dest.mkdir(parents=True,exist_ok=True)
    if arm=='messages_brief':prompt=prompt+'\n\n'+BRIEF
    payload={'model':model,'max_tokens':16000,'stream':True,'messages':[{'role':'user','content':prompt}]}
    chat=arm.startswith('chat_')
    if chat:
        payload.update(thinking={'type':'enabled'},reasoning_effort=arm.removeprefix('chat_'),stream_options={'include_usage':True})
    else:
        payload.update(thinking={'type':'enabled','budget_tokens':1024},output_config={'effort':'low'})
    url=BASE+('/chat/completions' if chat else '/messages')
    judge.atomic_json(dest/'request.json',{'url':url,'body':payload,'timeouts':LIMITS})
    trace=judge.RequestTrace(model,prompt,payload,dest/'trace.json')
    trace.data['request_settings']= {k:v for k,v in payload.items() if k!='messages'}
    trace.data['timeouts_seconds']=LIMITS
    key=os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN') or os.environ.get('LLM_API_KEY')
    if not key:raise ValueError('Missing credentials')
    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','anthropic-version':'2023-06-01'}
    request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers)
    text='';stop=None;complete=False;error=None
    try:
        opener,route=judge.request_transport(url);trace.data['transport_route']=route
        with judge.ProgressDeadline(trace,LIMITS):
            with opener(request,timeout=300) as response:
                trace.headers(response)
                if chat:text,stop,complete=read_chat(response,trace)
                else:
                    data=judge.read_provider_response(response,trace)
                    text='\n'.join(b['text'] for b in data.get('content',[]) if b.get('type')=='text')
                    stop=data.get('stop_reason');complete=stop in ('end_turn','stop_sequence')
                    trace.data['usage']=data.get('usage')
        status='complete' if complete and stop in ('stop','end_turn','stop_sequence') and text.strip() else 'incomplete'
    except urllib.error.HTTPError as exc:
        status='http_error';error={'http_status':exc.code}
        try:
            with judge.request_deadline(5):error['body']=exc.read(4096).decode(errors='replace').replace(key,'[redacted]')
        except Exception:pass
    except Exception as exc:
        status='failed';error={'type':type(exc).__name__,'message':str(exc).replace(key,'[redacted]')[:500]}
    (dest/'answer.txt').write_text(text)
    metadata=trace.finish(status)
    result={'model':model,'arm':arm,'status':status,'stop_reason':stop,'error':error,
            **{k:metadata.get(k) for k in ['elapsed_seconds','first_text_seconds','thinking_chars','text_chars','usage','request_id','response_model','delta_fields']}}
    judge.atomic_json(dest/'result.json',result)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execute',action='store_true')
    ap.add_argument('--task-id',default='hinge-question-designer__03')
    ap.add_argument('--arms',nargs='+',default=['messages_low','chat_low','messages_brief'])
    a=ap.parse_args()
    if not set(a.arms)<={'messages_low','messages_brief','chat_low','chat_high','chat_max'}:ap.error('Unknown arm')
    _,cases,_=load_release();case=next(c for c in cases if c['task_id']==a.task_id)
    a.out.mkdir(parents=True,exist_ok=True)
    plan={'task_id':case['task_id'],'models':['glm-5.3','glm-5.3-flash'],'arms':a.arms,
          'max_tokens':16000,'timeouts':LIMITS,'workers':6,'repeats':1,
          'note':'Exploratory comparison while the benchmark is running; not a controlled latency benchmark or final proof of parameter effectiveness.'}
    judge.atomic_json(a.out/'plan.json',plan);judge.atomic_json(a.out/'case.json',case)
    if not a.execute:print(json.dumps(plan));return
    load_env_file('/home/airlivy/.bashrc')
    specs=[(m,arm,case['context']+'\n\n'+case['user_prompt'],str(a.out)) for m in plan['models'] for arm in plan['arms']]
    results=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(trial,s) for s in specs]):
            result=future.result();results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
            judge.atomic_json(a.out/'summary.json',{'expected':len(specs),'finished':len(results),'results':results})


if __name__=='__main__':main()
