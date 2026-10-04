"""Content review with field IDs so source citations cannot be paraphrased."""
import argparse,json,os,time
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from repro import judge
from repro.credentials import load_env_file
from repro.source_protocol import load_release,digest
from repro.source_runner import model_options
from repro.calibration.review_content import payload,INSTRUCTION

RULES=INSTRUCTION.split('输出JSON，checked')[0]+'''\n本次输入为带F编号的字段清单，path表明原始字段位置，value为实际文字或数字。每个问题用references列出支撑判断的F编号，不输出或改写引文。不要报告以下误报：题目要求per question就是每题；子年级包含于背景年级范围不是冲突；“或”不是同时强制；参考说明和标准给出的示例不是唯一方法；综合准确性/显式约束条目可覆盖主题、数量和时限，不必每条重复；某项内容在其他激活维度已评，不再说完全遗漏。教学案例中的错误观点或未验证猜测不自动等于作者认可的事实。
只报告确定的内容错误或会实质错判的显式矛盾，不能仅因“可能被误解”添加新要求。不确定才用uncertain；无问题返回issues=[]。输出JSON {"issues":[{"component":"rubric","severity":"must_fix","references":["F1"],"reason":"具体矛盾","minimal_fix":"最小修正"}]}。'''


def fields(record):
    result={}
    def visit(x,path):
        if isinstance(x,dict):
            for k,v in x.items():visit(v,path+[k])
        elif isinstance(x,list):
            for i,v in enumerate(x):visit(v,path+[i])
        else:result['F'+str(len(result)+1)]={'path':path,'value':x}
    visit(record,[]);return result


def review(c,model,out):
    dest=Path(out)/model/c['task_id'];dest.mkdir(parents=True,exist_ok=True)
    data=fields(payload(c));binding=digest({'data':data,'rules':RULES});saved=dest/'result.json'
    if saved.exists():
        r=json.loads(saved.read_text())
        if r['binding']!=binding:raise ValueError('changed input')
        return r
    schema={'type':'object','properties':{'issues':{'type':'array','maxItems':4,'items':{'type':'object','properties':{'component':{'type':'string','enum':['question','context','reference','rubric','scope']},'severity':{'type':'string','enum':['must_fix','uncertain']},'references':{'type':'array','items':{'type':'string','enum':list(data)},'minItems':1},'reason':{'type':'string'},'minimal_fix':{'type':'string'}},'required':['component','severity','references','reason','minimal_fix'],'additionalProperties':False}}},'required':['issues'],'additionalProperties':False}
    base=RULES+'\n'+json.dumps(data,ensure_ascii=False);text=base
    r={'task_id':c['task_id'],'model':model,'binding':binding,'case_sha256':digest(c)}
    for attempt in range(2):
        try:
            raw,meta=judge.call_judge(text,model,output_schema=schema,telemetry_path=dest/f'trace_{attempt}.json',**model_options(model))
            (dest/f'raw_{attempt}.txt').write_text(raw);judge.atomic_json(dest/f'metadata_{attempt}.json',meta)
            if meta.get('stop_reason')!='end_turn':raise ValueError('Incomplete response')
            v=judge.decode_verdict(raw)
            if not isinstance(v,dict) or set(v)!={'issues'} or not isinstance(v['issues'],list):raise ValueError('Expected issues array')
            for issue in v['issues']:
                if set(issue)!= {'component','severity','references','reason','minimal_fix'} or not issue['references'] or not set(issue['references'])<=set(data):raise ValueError('Invalid fields or F references')
                if issue['severity'] not in ('must_fix','uncertain'):raise ValueError('Invalid severity')
                issue['source_fields']=[data[f] for f in issue['references']]
            r.update(status='reviewed',issues=v['issues']);break
        except (judge.JudgeError,ValueError,KeyError,TypeError) as exc:
            detail=str(exc)[:200] if not isinstance(exc,judge.JudgeError) else exc.category
            judge.atomic_json(dest/f'failure_{attempt}.json',{'category':getattr(exc,'category','invalid_review'),'detail':detail,'metadata':getattr(exc,'metadata',{})})
            r.update(status='review_failed',category=getattr(exc,'category','invalid_review'))
            text=base+'\n上次输出校验失败：'+detail+'。请按要求返回完整JSON及存在的F编号。'
            if isinstance(exc,judge.JudgeError) and not exc.retryable:break
    judge.atomic_json(saved,r);return r


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--models',nargs='+',default=['deepseek-v4-pro','deepseek-v4-flash']);ap.add_argument('--ids-file',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    if any(m not in ('deepseek-v4-pro','deepseek-v4-flash') for m in a.models):ap.error('unsupported model')
    load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1'
    _,cases,manifest=load_release();a.out.mkdir(parents=True,exist_ok=True)
    if a.ids_file:
        ids=set(json.loads(a.ids_file.read_text()))
        if not ids<={c['task_id'] for c in cases}:raise ValueError('Unknown task ID')
        cases=[c for c in cases if c['task_id'] in ids]
    plan={'manifest':digest(manifest),'cases':digest(cases),'rules':digest(RULES),'models':a.models}
    path=a.out/'plan.json'
    if path.exists() and json.loads(path.read_text())!=plan:raise ValueError('Changed audit plan')
    judge.atomic_json(path,plan);judge.atomic_json(a.out/'cases.json',cases);judge.atomic_json(a.out/'release_manifest.json',manifest)
    if not a.execute:return
    results=[]
    with ProcessPoolExecutor(max_workers=16) as pool:
        futures=[pool.submit(review,c,m,a.out) for c in cases for m in a.models]
        for future in as_completed(futures):
            r=future.result();results.append(r)
            summary={'expected':len(futures),'finished':len(results),'reviewed':sum(r['status']=='reviewed' for r in results),'flagged':sum(bool(r.get('issues')) for r in results),'results':results,'scope':'AI content candidates, not expert certification.'}
            judge.atomic_json(a.out/'summary.json',summary)
            if len(results)%40==0:print(json.dumps({k:v for k,v in summary.items() if k not in ('results','scope')}),flush=True)
if __name__=='__main__':main()
