"""Content corrections after v3; keep reviewed inputs and historical scores immutable."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'data/revisions/case-review-v3-20260930'
OUT = ROOT/'data/revisions/case-review-v4-20260930'
NOTES = []


def read(name):
    with (SOURCE/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def note(row, code, reason):
    NOTES.append({'task_id':row['task_id'],'issue_code':code,'reason':reason,
                  'status':'corrected_pending_recheck'})


def replace(row, field, old, new):
    if old not in row[field]:
        raise ValueError((row['task_id'],field,'patch source not found',old))
    row[field]=row[field].replace(old,new)


def original_fixes(row):
    r=dict(row);tid=r['task_id'];rubric=json.loads(r['rubric'])
    if r['skill_id']=='self-efficacy-builder-sequence':
        if tid.endswith('__01'):
            replace(r,'expected_output','an efficacy diagnostic identifying the primary barrier',
                    'evidence-linked hypotheses about possible barriers and a brief way to check them')
            replace(r,'expected_output','avoid generic praise or peer comparison.',
                    'avoid relying on generic praise or comparison with high achievers as the main intervention; ordinary supportive encouragement alongside specific feedback is acceptable.')
            rubric[5]['description']='Uses specific, credible feedback and attainable practice rather than making generic praise, rewards or comparisons with high achievers the main intervention; supportive encouragement is not itself an error.'
            rubric[6]['description']='Does not assert a confirmed psychological cause from the brief classroom observations; proposes a way to check plausible barriers.'
        elif tid.endswith('__02'):
            r['expected_output']='A four-to-six-task progression from demonstrated practical/verbal strengths toward independent Year 9 lab-report writing. Offer plausible barriers as hypotheses and check them; do not diagnose perfectionism or anxiety as established facts. Include attainable steps, observable readiness checks, specific feedback scripts and a maintenance plan. Similar-peer modeling and pressure-reduction strategies are optional where useful, not mandatory mechanisms. Accept defensible alternative scaffolds.'
            rubric[3]['description']='If peer modeling is used, it makes a relevant learning process visible rather than presenting only a polished result; do not deduct for omitting optional peer modeling.'
        else:
            r['expected_output']='A four-to-six-task progression from demonstrated written French knowledge toward supported speaking and classroom interaction. Treat possible anxiety, perfectionism and social concerns as hypotheses rather than diagnoses. Include agreed low-pressure first steps, readiness-dependent progression, specific feedback grounded in the stated evidence and a maintenance plan. Do not invent past achievements, guarantee anxiety reduction, or require a particular psychological intervention. Peer modeling is optional; equivalent defensible supports are accepted.'
            rubric[0]['description']='Distinguishes demonstrated written-language competence from the reported speaking difficulty; offers evidence-linked hypotheses about barriers without equating performance with measured self-efficacy or asserting a diagnosis.'
            rubric[2]['description']='Discusses a possible link between the reported physical reactions and avoidance conditionally, without claiming to know the student\'s internal interpretation.'
            rubric[7]['description']='Teacher scripts draw on the written-language strengths actually supplied, or clearly mark any more specific achievement as a hypothetical example; they do not invent a completed assignment or promise effortless transfer to speaking.'
        note(r,'UNCERTAIN_BARRIER_AND_OPTIONAL_SUPPORT','观察只能支持障碍假设；同步取消参考答案中的确定诊断和强制示范，修复条件句拆分造成的误扣分。')
    if tid=='adaptive-hint-sequence-designer__03':
        r['user_prompt']+='\nFor the worked illustration use inverse demand P(Q)=20-Q and total cost C(Q)=4Q+10 for 0<=Q<=20; the fixed cost is unavoidable in this short-run comparison. Derive profit and check the stationary candidate against the feasible boundaries. Explain that MR=MC identifies an interior candidate, not a universal guarantee for an arbitrary cost function. Keep the worked solution in the final hint/teacher key.'
        r['expected_output']+=' For the specified illustration, profit is 16Q-Q^2-10, so Q*=8, P*=12 and profit=54; the second derivative is -2 and boundary profits are -10 and -90. Price exceeds MC=4 at this positive interior optimum. For other cost functions, check feasibility, maxima and shutdown/boundary options rather than treating MR=MC as sufficient by itself.'
        rubric[0]['description']='Hints progress from profit maximization and feasible output to deriving MR, identifying the interior MR=MC candidate and checking that it maximizes profit; they do not present the first-order condition as universally sufficient.'
        rubric[3]['description']='The final hint/teacher key correctly obtains Q=8, P=12 and profit=54 for the supplied functions, checks concavity or compares feasible candidates including boundaries, and asks the student to explain why P>MC for this positive interior optimum.'
        note(r,'MONOPOLY_INTERIOR_ASSUMPTIONS','原题未给成本函数和可行范围，却把 MR=MC 与 P>MC 当作无条件结论；补可核算实例与边界检查。')
    if r['skill_id']=='spaced-practice-scheduler':
        if tid.endswith('__01'):
            replace(r,'expected_output','The schedule should demonstrate expanding retrieval intervals (e.g., first review 1-3 days after teaching, subsequent reviews at increasing gaps).',
                    'The schedule should distribute retrieval after initial teaching within the available timetable; fixed, expanding or adaptive gaps are acceptable when justified.')
            rubric[4]['description']='Retrieval is distributed after initial teaching within the available lessons; accepts justified fixed, expanding or adaptive intervals, without requiring a particular day count not stated in the task.'
        elif tid.endswith('__02'):
            replace(r,'expected_output','difficulty-weighted spacing and expanding intervals','difficulty-sensitive distributed practice; fixed, expanding or adaptive intervals may be justified')
            rubric[8]['description']='The rationale links distributed review choices to topic difficulty and the actual timetable; expanding intervals are an option, not an unstated requirement.'
        note(r,'SPACING_CONTRACT','将课表可行性恢复为评分解释条件，取消题面未要求的固定扩展间隔；保留第三题明确要求的扩展安排。')
    if r['skill_id']=='emergent-project-design-scaffold':
        r['expected_output']=r['expected_output'].replace('3-5 provocations','at least 3 provocations').replace('4-5 provocations','at least 4 provocations')
        for c in rubric:
            c['description']=c['description'].replace('At least 3-4 provocations','At least 3 provocations')
        note(r,'COUNT_CONSISTENCY','参考中的 3–5/4–5 与题面“至少”统一，不因合理增加活动而扣分。')
    # v3 split repeated interpretive conditions into separately rewarded criteria.
    qualifiers={
        'Judge feasibility within the stated timetable; allow a prerequisite check in the first lesson and adapt intervals where insufficient later lessons exist.',
        'Accept equivalent wording for the five functions; no personal disclosure or demonstrated reduction in distress is required.'}
    removed=[c for c in rubric if c['description'] in qualifiers]
    if removed:
        kept=[c for c in rubric if c['description'] not in qualifiers]
        for condition in removed:
            targets=[c for c in kept if c['criterion']==condition['criterion']]
            if not targets:raise ValueError('orphan rubric qualifier')
            total=sum(c['points'] for c in targets)
            for c in targets:
                c['points']+=condition['points']*c['points']/total
                c['description']+=' Interpretation: '+condition['description']
        rubric=kept
        note(r,'DUPLICATED_QUALIFIER_POINTS','通用解释条件曾被拆成五条重复得分项；移回对应评分项，保留各原维度总权重，避免形式合规反复得分。')
    for i,c in enumerate(rubric,1):c['id']=f'C{i}'
    r['rubric']=json.dumps(rubric,ensure_ascii=False)
    return r


def expanded_fixes(row):
    r=dict(row);rubric=json.loads(r['rubric'])
    for c in rubric:
        if c['description'].startswith('Task-specific deliverable check: '):
            illustration=c['description'].split(': ',1)[1]
            c['description']=('Provides a feasible, correct response to the actual user request. The following is an illustrative teaching approach, not a mandatory example, material, numeric value or fixed sequence unless explicitly requested in the question: '+illustration+
                              ' Accept other approaches that meet the same stated objective; do not deduct merely for not reproducing this illustration.')
        elif c['description'].startswith('Critical-error check: the response does not endorse this error: '):
            c['description']=c['description'].replace('Critical-error check: the response does not endorse this error: ',
                'Critical-error check: the response substantively addresses this case and does not endorse the following error; an irrelevant, empty or purely evasive response fails this criterion: ')
        elif c['description']=='The response gives an observable way to check the proposed explanation or next teaching action.':
            c['description']='The response gives an observable way to check the explanation or next teaching action for this specific case; a check for an unrelated topic does not meet this requirement.'
        elif c['description']=='The response distinguishes supplied facts from assumptions or hypothetical examples.':
            c['description']='The response addresses this case using the supplied facts and labels material assumptions or hypothetical examples when it introduces them. Do not require invented assumptions or a boilerplate disclaimer when none is needed; irrelevant or empty responses fail.'
    r['expected_output']=r['expected_output'].replace('Requested application:', 'Illustrative application (equivalent approaches accepted; only explicit question requirements are mandatory):')
    r['rubric']=json.dumps(rubric,ensure_ascii=False)
    note(r,'ILLUSTRATION_NOT_HIDDEN_REQUIREMENT','应用示例中指定的数字、材料或步骤不能成为题面未提出的唯一答案；直接修改交付物评分项，保留知识正确性要求。')
    note(r,'NO_VACUOUS_CREDIT','实跑中出现跑题答案仅因未犯指定错误而得到 0.2 分；负向评分增加实质回应本题的条件，避免无关答案获得这部分分数。')
    return r


def build():
    NOTES.clear();OUT.mkdir(parents=True,exist_ok=True)
    datasets={name:read(name) for name in ['single_turn_tasks.csv','single_turn_tasks_cn263.csv']}
    revised={name:[(original_fixes if name=='single_turn_tasks.csv' else expanded_fixes)(r) for r in rows] for name,rows in datasets.items()}
    # Additional individually adjudicated corrections use exact old text, never free-form model patches.
    patches_path=Path(__file__).with_name('content_review_patches_v4.json')
    patches=json.loads(patches_path.read_text()) if patches_path.exists() else []
    byid={r['task_id']:r for rows in revised.values() for r in rows}
    for patch in patches:
        r=byid[patch['task_id']]
        replace(r,patch['field'],patch['old'],patch['new'])
        note(r,patch['issue_code'],patch['reason'])
    def dump(name,value):
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    cases=[];changes=[]
    for name,rows in revised.items():
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        for old,r in zip(datasets[name],rows):
            rubric=json.loads(r['rubric'])
            assert math.isclose(sum(c['points'] for c in rubric),100)
            assert all(c['points']>0 for c in rubric)
            cases.append({'id':r['task_id'],'question':r['context']+'\n\n'+r['user_prompt'],
                          'ground_truth':r['expected_output'],'rubric':rubric,
                          'expected_behavior':[c['description'] for c in rubric],
                          'score_metric':'weighted','status':'review_only'})
            if r!=old:
                changes.append({'task_id':r['task_id'],'fields':{k:{'before':old[k],'after':r[k]} for k in old if old[k]!=r[k]}})
    dump('evals.json',{'schema_version':4,'release_status':'blocked_pending_acceptance','cases':cases})
    dump('changes.json',changes);dump('correction_notes.json',NOTES)
    for name in ['source_bindings.json','skill_routing_review.json','split_groups.json','split_policy.json']:
        (OUT/name).write_bytes((SOURCE/name).read_bytes())
    dump('release_gate.json',{'ready':False,'formal_cases_released':0,
         'content_review':'v3 AI findings are evidence for corrections, not v4 acceptance',
         'judge_calibration':'v3 calibration does not certify changed v4 rubrics',
         'independent_acceptance':'pending'})
    (OUT/'README.md').write_text('# 内容复核修订候选 v4\n\n保留 v3 冻结题库及其评分记录。这里记录内容复核后的修订，不是正式发布版本；v3 的 30 份评分结果不能移用于本版本。改动与原因见 changes.json 和 correction_notes.json。\n')
    inputs=[SOURCE/'manifest.json',SOURCE/'single_turn_tasks.csv',SOURCE/'single_turn_tasks_cn263.csv',Path(__file__)]
    if patches_path.exists():inputs.append(patches_path)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    dump('manifest.json',{'revision':OUT.name,'source_revision':SOURCE.name,'counts':{'total':len(cases),'changed':len(changes)},
         'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in inputs},
         'artifact_sha256':{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'},'release_ready':False})
    print(json.dumps({'cases':len(cases),'changed':len(changes),'release_ready':False}))


if __name__=='__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
