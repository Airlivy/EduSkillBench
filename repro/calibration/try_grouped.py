"""Validate smaller rubric groups with complete evidence before deployment."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from repro import judge
from repro.credentials import load_env_file
from repro.calibration.smoke_ready import fixtures
from repro.calibration.fixtures_v3 import FIXTURES

ROOT=Path(__file__).resolve().parents[2]

def verdict_schema(rubric):
    return judge.verdict_schema(rubric)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--env-file',type=Path,required=True)
    ap.add_argument('--base-url',required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--variant',choices=['positive','factual_error','off_topic','equivalent_correct'])
    ap.add_argument('--task-id')
    ap.add_argument('--format',choices=['schema','text'],default='schema')
    ap.add_argument('--group-size',type=int,choices=[0,1,2],default=2,help='0 keeps the entire rubric')
    ap.add_argument('--model',default='glm-5.3-flash',choices=['glm-5.3-flash','deepseek-v4-flash','deepseek-v4-pro'])
    ap.add_argument('--thinking',choices=['enabled','disabled'],default='enabled')
    ap.add_argument('--max-output',type=int,default=16000)
    ap.add_argument('--audit-arithmetic',action='store_true')
    ap.add_argument('--broader',action='store_true')
    ap.add_argument('--production-profile',action='store_true')
    ap.add_argument('--profile',choices=['fixed-pro-v1','fixed-pro-v2','fixed-pro-v3'],default='fixed-pro-v3')
    ap.add_argument('--execute',action='store_true')
    a=ap.parse_args()
    data=ROOT/'data/releases/run-ready-20260930/evals.json'
    cases={c['id']:c for c in json.loads(data.read_text())['cases']}
    selected=[f for f in fixtures() if (not a.variant or f['variant']==a.variant) and (not a.task_id or f['task_id']==a.task_id)]
    if not selected:raise ValueError('No fixtures selected')
    timeout={**judge.DEFAULT_TIMEOUTS,'total':120.0}
    if a.audit_arithmetic and not a.variant and not a.task_id:
        quoted = dict(next(f for f in selected if f['task_id']=='project-brief-designer__cn52_04' and f['variant']=='positive'))
        quoted['variant']='corrected_student_error'
        quoted['answer'] += '\nA pupil might write "11*4=45". This equality is wrong: 11*4=44. Explain that ten groups of four plus one group of five give 10*4+5=45.'
        selected.append(quoted)
    if a.broader:
        if a.variant or a.task_id:ap.error('--broader cannot be combined with a fixture filter')
        existing={f['task_id'] for f in selected}
        selected.extend(dict(f) for f in FIXTURES if f['task_id'] not in existing)
    if a.production_profile and (a.model!='deepseek-v4-pro' or a.thinking!=('enabled' if a.profile=='fixed-pro-v3' else 'disabled') or a.group_size or not a.audit_arithmetic or a.max_output!=4096 or a.format!='schema'):
        ap.error('The selected experimental profile requires matching full-rubric request settings')
    plan={'model':a.model,'group_size':a.group_size,'thinking':a.thinking,'max_output':a.max_output,'arithmetic_audit':a.audit_arithmetic,'format':a.format,'timeouts':timeout,'production_profile':(a.profile if a.production_profile else None),
          'judge_sha256':hashlib.sha256(Path(judge.__file__).read_bytes()).hexdigest(),
          'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'data_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),
          'fixtures_sha256':hashlib.sha256(json.dumps(selected,sort_keys=True).encode()).hexdigest(),
          'max_calls':(3 if a.production_profile else 1)*sum((len(cases[f['task_id']]['rubric'])+a.group_size-1)//a.group_size if a.group_size else 1 for f in selected)}
    a.out.mkdir(parents=True,exist_ok=False)
    judge.atomic_json(a.out/'plan.json',plan)
    judge.atomic_json(a.out/'fixtures.json',selected)
    if not a.execute:print(json.dumps(plan));return
    load_env_file(a.env_file);os.environ['ANTHROPIC_BASE_URL']=a.base_url
    rows=[]
    for f in selected:
        case={**cases[f['task_id']],'score_metric':'weighted','judge_model':plan['model'],'arithmetic_audit':a.audit_arithmetic}
        if a.production_profile:case['judge_profile']=a.profile
        dest=a.out/f['task_id']/f['variant'];dest.mkdir(parents=True)
        merged=[];started=time.monotonic();failed=False
        size=a.group_size or len(case['rubric'])
        for idx in range(0,len(case['rubric']),size):
            part={**case,'rubric':case['rubric'][idx:idx+size]}
            prefix=dest/f'group-{idx//size+1}'
            judge.atomic_json(prefix.with_suffix('.case.json'),part)
            try:
                if a.production_profile:
                    result=judge.evaluate(part,f['answer'],prefix)
                    meta=json.loads(sorted(prefix.glob('judge_response_*.json'))[-1].read_text())
                    text=sorted(prefix.glob('judge_raw_*.txt'))[-1].read_text()
                else:
                    text,meta=judge.call_judge(judge.build_prompt(part,f['answer']),plan['model'],
                       telemetry_path=prefix.with_suffix('.trace.json'),timeouts=timeout,
                       output_schema=verdict_schema(part['rubric']) if a.format=='schema' else None,
                       thinking_mode=a.thinking,max_output_tokens=a.max_output)
                prefix.with_suffix('.text.txt').write_text(text)
                judge.atomic_json(prefix.with_suffix('.response.json'),meta)
                if meta.get('stop_reason') in ('max_tokens','stream_incomplete'):
                    raise judge.JudgeError(meta['stop_reason'],metadata=meta)
                result=judge.score_items(judge.decode_verdict(text),part['rubric'],'weighted')
                judge.atomic_json(prefix.with_suffix('.verdict.json'),result)
                merged.extend(result['items'])
                print(json.dumps({'task':f['task_id'],'variant':f['variant'],'group':idx//size+1,'status':'scored','seconds':meta['elapsed_seconds']}),flush=True)
            except (judge.JudgeError,ValueError,KeyError,TypeError) as exc:
                failure={'category':getattr(exc,'category',type(exc).__name__),'metadata':getattr(exc,'metadata',{})}
                judge.atomic_json(prefix.with_suffix('.failure.json'),failure)
                row={'task':f['task_id'],'variant':f['variant'],'status':'failed','failure':failure,'seconds':round(time.monotonic()-started,3)}
                rows.append(row);judge.atomic_json(a.out/'summary.json',rows);print(json.dumps(row),flush=True);failed=True
                break
        if failed:raise SystemExit(1)
        verdict=judge.score_items({'items':merged},case['rubric'],'weighted')
        decisions={item['id']:item['pass'] for item in verdict['items']}
        match=all(decisions.get(cid) for cid in f.get('must_pass',[])) and all(decisions.get(cid) is False for cid in f.get('must_fail',[]))
        match=match and f.get('min_score',0)<=verdict['score']<=f.get('max_score',1)
        judge.atomic_json(dest/'merged.verdict.json',verdict)
        row={'task':f['task_id'],'variant':f['variant'],'status':'scored','score':verdict['score'],'critical_pass':verdict['critical_pass'],
             'matches_expectation':bool(match),'seconds':round(time.monotonic()-started,3)}
        rows.append(row);judge.atomic_json(a.out/'summary.json',rows);print(json.dumps(row),flush=True)
        if not match:raise SystemExit(1)

if __name__=='__main__':main()
