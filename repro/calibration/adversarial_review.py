"""Fixed near-miss checks, not generated gold answers or score tuning."""
import argparse,json,os
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from repro import judge
from repro.credentials import load_env_file
from repro.source_protocol import load_release,digest,allowed_labels
from repro.source_runner import evaluate_native,model_options
from repro.calibration.adjudication_contrasts import FIXTURES


def jobs(cases):
    indexed={c['task_id']:c for c in cases};out=[]
    core=indexed['differentiation-adapter__01']
    good=json.loads(Path('results_v2/evaluate-audit-smoke-20261002/deepseek-v4-pro/differentiation-adapter__01/answer.json').read_text())['text']
    out.extend([(core,'valid',good,'critical'),(core,'contradiction',good+'\n教师最终核对：前面的28元有误，应将50减22算成29元，正确找零为29元。','critical')])
    for suffix,targets,good,_ in FIXTURES:
        if suffix not in ('cn30_06','cn63_08'):continue
        case=next(c for c in cases if c['task_id'].endswith('__'+suffix))
        contradiction=('\n最终数学结论：C(4,2)=9，上述等于6的结果应当改为9。' if suffix=='cn30_06' else '\n实际执行时，如果学生没有填写任何客观事实，仍然直接给满分，不退回补填。')
        out.extend([(case,'valid',good,targets[0]),(case,'contradiction',good+contradiction,targets[0])])
    c=indexed['differentiation-adapter__cn62_03']
    good='教师提供一张校内切土豆丝的示意图和三个操作记录：厚薄一致、薄厚混杂、未站稳就切。学生只用纸笔，不在家使用刀具。先用3分钟按图预测哪组更易粗细均匀、哪处有风险，再用5分钟从课堂记录找两条依据，最后用4分钟订正一处操作顺序并解释理由，提交预测表和一条订正。总计12分钟，不写心得，也不需要土豆或砧板。'
    bad=good.replace('先用3分钟','先用15分钟').replace('再用5分钟','再用20分钟').replace('最后用4分钟','最后用10分钟').replace('总计12分钟','总计45分钟')
    out.extend([(c,'valid',good,'D3'),(c,'over_time',bad,'D3')]);return out


def one(case,variant,answer,target,out):
    dest=Path(out)/case['task_id']/variant;dest.mkdir(parents=True,exist_ok=True)
    try:
        if case['suite']=='core':
            record=dict(question=case['context']+'\n'+case['user_prompt'],ground_truth=case['expected_output'],judge_model='deepseek-v4-pro',score_metric='weighted',rubric=case['rubric'],execution_options=model_options('deepseek-v4-pro'))
            def call(p,m):return judge.call_judge(p,m,telemetry_path=dest/'trace.json',output_schema=judge.verdict_schema(record['rubric']),**model_options(m))
            v=judge.evaluate(record,answer,dest,call,max_attempts=2,stop_on_deadline=True,require_explicit_retry=True)
            actual=v['critical_pass'];passed=actual is (variant=='valid')
        else:
            v=evaluate_native(case,answer,'deepseek-v4-pro',dest)
            criterion=next(r for r in case['criteria'] if r['id']==target);levels=allowed_labels(criterion)
            actual=next(i['level'] for i in v['items'] if i['id']==target)
            passed=actual==(levels[0] if variant=='valid' else levels[-1])
        result=dict(task_id=case['task_id'],variant=variant,target=target,actual=actual,passed=passed,status='evaluated')
    except judge.JudgeError as e:result=dict(task_id=case['task_id'],variant=variant,passed=False,status='failed',category=e.category)
    judge.atomic_json(dest/'check.json',result);return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    _,cases,manifest=load_release();work=jobs(cases);a.out.mkdir(parents=True,exist_ok=True);plan=dict(release=digest(manifest),fixtures=digest(work))
    if (a.out/'plan.json').exists() and json.loads((a.out/'plan.json').read_text())!=plan:raise ValueError('Changed probe inputs')
    judge.atomic_json(a.out/'plan.json',plan);judge.atomic_json(a.out/'fixtures.json',work)
    if not a.execute:return
    load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1';results=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(one,*w,a.out) for w in work]):
            result=f.result();results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
            judge.atomic_json(a.out/'summary.json',dict(expected=len(work),finished=len(results),passed=sum(r['passed'] for r in results),results=results))
    if not all(r['passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
