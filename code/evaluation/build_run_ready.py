"""Build a runnable, reviewed delivery; never relabel a calibration as expert certification."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'data/revisions/case-review-v4-20260930'
OUT = ROOT/'data/releases/run-ready-20260930'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    datasets = {}
    for name in ('single_turn_tasks.csv', 'single_turn_tasks_cn263.csv'):
        with (SOURCE/name).open(encoding='utf-8-sig', newline='') as f:
            datasets[name] = list(csv.DictReader(f))
    changes = []
    records = []
    allrows = []
    for filename, rows in datasets.items():
        for source in rows:
            r = dict(source)
            tid = r['task_id']; core = '__cn' not in tid
            rubric = json.loads(r['rubric'])
            reasons = []
            def criterion(cid, description):
                next(c for c in rubric if c['id'] == cid)['description'] = description
            def replace(old, new):
                found = False
                for field in ('user_prompt', 'context', 'expected_output'):
                    if old in r[field]:
                        r[field] = r[field].replace(old, new); found = True
                for c in rubric:
                    if old in c['description']:
                        c['description'] = c['description'].replace(old, new); found = True
                if not found: raise ValueError((tid, old))
            if tid == 'hinge-question-designer__02':
                criterion('C2', "The four options use comparable presentation and length without answer cues. Their grammatical correctness may differ because that is being tested; identical grammatical form is not required. Avoid all/none-of-the-above options.")
                criterion('C1', 'Presents an unambiguous, correct application of the independent-clause comma rule, with one correct option and an item answerable in under two minutes.')
                reasons.append('去掉必须语法形式完全相同的要求，避免与语法错误干扰项矛盾；补快速作答与唯一正确选项检查。')
            if tid == 'retrieval-practice-generator__02':
                r['user_prompt'] += '\nUse a majority of free or cued recall items; begin with unaided retrieval, then give corrective feedback. Spacing intervals are justified proposals, not a universal optimum.'
                criterion('C5', 'Proposes a feasible later reuse interval and explains how it may be adjusted to observed performance; does not claim a universally optimal schedule.')
                reasons.append('把回忆题占多数写入题面，取消未经证实的最优间隔要求。')
            if tid == 'retrieval-practice-generator__03':
                criterion('C4', 'Collectively covers the three named misconceptions through explanation, contrast or error correction; does not require an unstated minimum number per misconception.')
                criterion('C9', 'Provides timing, low-stakes framing, an initial unaided retrieval phase with appropriate language/access support, feedback after retrieval and practical mixed-ability/EAL adaptations.')
                reasons.append('取消每个误区必须多道题的隐藏数量要求；区分无答案提示的提取与必要语言支持。')
            if r['skill_id'] == 'socratic-questioning-sequence-generator' and core:
                criterion('C5', 'Provides deliberate thinking time and a practical way to handle silence; an integrated note is acceptable and no exact wait-time number or dedicated heading is required.')
                criterion('C10', 'Opens substantive exploration of the stated topic without forcing one normative conclusion; accurate factual clarification and correction of misconceptions are allowed.')
                reasons.append('开放讨论不等于禁止教师澄清事实；等待时间不限定秒数或标题。')
            if tid == 'self-efficacy-builder-sequence__02':
                criterion('C8', 'Offers a feasible, low-pressure route into writing based on the observed difficulty; does not diagnose anxiety or require a particular psychological technique.')
                reasons.append('消除参考允许可选支持、评分却强制心理干预的不一致。')
            if tid == 'self-efficacy-builder-sequence__03':
                criterion('C2', 'Uses agreed, low-pressure speaking opportunities with a pause/help route and observes readiness; no particular breathing or psychological intervention is mandatory, and symptom reduction is not guaranteed.')
                criterion('C4', 'Provides four to six tasks beginning with an agreed supported speaking attempt and progressing toward classroom interaction as readiness permits; recording alone is an example, not a required first task.')
                reasons.append('以课堂支持和学生准备度评分，取消固定干预路线与症状改善暗示。')
            if tid == 'adaptive-hint-sequence-designer__01':
                criterion('C2', 'Early hints focus on an identifiable sticking point, including direction/signs, combining forces and units. The bottom-out level may combine the steps needed for a complete solution.')
                criterion('C5', 'Includes an overview, exactly four hint levels with text, purpose, triggers, expected response and escalation, an exhausted-hints strategy, trigger summary and adaptation notes. Equivalent headings and integrated presentation are accepted.')
                reasons.append('四级提示必须明确；完整兜底解不能因覆盖多个步骤被误扣分。')
            if tid == 'self-explanation-prompt-designer__03':
                criterion('C4', 'Covers all four requested conceptual steps (integral, chain rule, velocity and Lenz law), each with placement, prompt, deep explanation, shallow response and contingent follow-up; integrated entries may cover linked steps.')
                reasons.append('补上必须覆盖题目明确要求的四个概念步骤，不能自选少量步骤蒙混通过。')
            if tid == 'emergent-project-design-scaffold__03':
                r['user_prompt'] += '\nFor hands-on engineering, use teacher-selected safe demonstration mechanisms or models; do not ask children to dismantle unknown antique clocks or loaded spring mechanisms.'
                reasons.append('把实际拆解范围限制为教师准备的适龄模型，保留工程探究目标。')
            if tid == 'lesson-builder__cn24_08':
                r['user_prompt'] = r['user_prompt'].replace('the midsegment theorem', 'the triangle midsegment theorem')
                reasons.append('题源只说中位线，本改编明确限定三角形，不再隐藏范围。')
            if tid == 'lesson-builder__cn25_01':
                replace('Here principal-variable method means treating a multivariable expression as a function of one chosen variable while other variables act as parameters.', 'In this introductory adaptation, principal-variable reasoning means choosing one variable, using constraints to express dependent variables, and holding any remaining independent parameters fixed as appropriate.')
                r['user_prompt'] += '\nFor this introductory adaptation, focus on selecting one variable and using a constraint to express the others; state the feasible domain. More advanced parameter-based approaches are also accepted if explained at the stated level.'
                reasons.append('统一主元法定义和代入约束示例，并把本改编的入门范围告知答题模型。')
            if tid == 'lesson-builder__cn22_01':
                replace('where c^2=a^2+b^2.', 'for foci (+/-c,0), where c^2=a^2+b^2.')
                reasons.append('双曲线标准式示例显式说明焦点方向和坐标约定。')
            if tid == 'lesson-builder__cn50_03':
                replace('Fairness means meaningful roles and predictable rotation, not winning a contest for the preferred role.', 'Fairness requires meaningful roles and equitable opportunities over time; random selection can choose an initial turn if followed by accessible rotation.')
                reasons.append('明确可以用抽签确定首轮，不能把所有随机分配都视为不公平。')
            if tid == 'lesson-builder__cn55_02':
                replace('Attention during instructions depends on material access and clear sequence.', 'A usable attention cue needs a clear, accessible response that is explicitly modeled and rehearsed; shouting a cue alone is insufficient.')
                reasons.append('把核心评分从泛泛材料管理改为本题实际要求的口令及练习。')
            if core:
                # Explicit public contract, identical in both experimental conditions.
                r['user_prompt'] += '\nAssessment contract: Provide a substantive, factually correct response that meets the stated constraints. Equivalent sound methods and headings are accepted. Separate teacher keys from unsolved student tasks where relevant; identify material assumptions and do not invent observed outcomes.'
                for c in rubric:
                    c['points'] *= 0.8
                    c['description'] = ('Award only for a substantive response to this task. ' + c['description'] + ' Equivalent defensible wording and methods are accepted; illustrative examples are not mandatory unless requested in the question.')
                rubric.append({'id':f'C{len(rubric)+1}', 'criterion':'Substantive correctness and explicit constraints', 'points':20.0, 'critical':True,
                    'description':'The response substantively completes this task without a material factual, mathematical or logical error, fabricated evidence, or violation of an explicit time, safety or delivery constraint. A response with correct surrounding prose but a substantive contradictory answer fails. Merely quoting the request, empty and off-topic answers fail.'})
                reasons.append('所有评分先要求回应本题，增加20分关键正确性项；原维度等比例保留80分，避免只靠格式掩盖错误。')
            r['rubric'] = json.dumps(rubric, ensure_ascii=False)
            allrows.append(r)
            changes.append({'task_id':tid, 'reasons':reasons, 'fields':{k:{'before':source[k],'after':r[k]} for k in source if source[k]!=r[k]}})
            records.append({'task_id':tid, 'case_sha256':hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                'review_method':'direct reading of current prompt/reference; rubric alignment checked; numerical anchors independently recalculated where present',
                'editorial_content_review':'completed', 'suite':'core' if core else 'advisory',
                'skill_comparison':'included' if core else 'excluded_from_primary_skill_comparison',
                'scope_reason':'Explicit requested deliverable matches the named Skill.' if core else 'Adapted classroom consultation; routing labels are not independently established gold labels. Retained for baseline answer quality, not pooled Skill lift.',
                'live_judge_calibration':'not_certified_per_case', 'expert_certification':False})
    def dump(name, value):
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    for name, rows in [('core.csv',allrows[:42]),('advisory.csv',allrows[42:]),('all.csv',allrows)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    cases=[]
    for r in allrows:
        rub=json.loads(r['rubric'])
        cases.append({'id':r['task_id'],'question':r['context']+'\n\n'+r['user_prompt'],
            'ground_truth':r['expected_output'],'rubric':rub,'expected_behavior':[x['description'] for x in rub],
            'score_metric':'weighted','suite':'core' if '__cn' not in r['task_id'] else 'advisory'})
    dump('evals.json',{'schema_version':5,'status':'runnable_editorially_reviewed','cases':cases})
    dump('changes.json',[x for x in changes if x['fields']])
    dump('review_ledger.json',records)
    dump('source_bindings.json',json.loads((SOURCE/'source_bindings.json').read_text()))
    dump('release_gate.json',{'ready':True,'purpose':'runnable evaluation delivery, not all-criteria expert acceptance',
         'full_acceptance':False,'core_skill_cases':42,'advisory_answer_cases':263,
         'allowed_conditions':{'core':['baseline','with-skill'],'advisory':['baseline'],'all':['baseline']},
         'judge_calibration':'See separately recorded bounded smoke results; not a 305-case calibration claim.'})
    (OUT/'README.md').write_text('''# 可运行测试集（2026-09-30）

本包保留全部 305 题，题面、参考与评分项一并冻结。`core.csv` 是 42 道明确要求对应 Skill 交付物的主集，支持有/无 Skill 对照；`advisory.csv` 是 263 道教学咨询题，保留原编号，仅用于无 Skill 的回答质量测试；`all.csv` 包含全部 305 题。

已逐题阅读当前题面和参考，核对评分锚点，并复算数理例子。修复记录见 changes.json。此处 ready 表示允许按声明用途运行；不表示专家认证、所有 API 请求永不失败或 305 题均完成了四类回答的真实评分校准。之前的完整验收门槛没有被改成已通过。

运行入口：仓库根目录 `python3 -m repro run --dataset core --tag ready-20260930`（默认只显示计划）。全量回答质量测试使用 `--dataset all`。添加 `--execute` 才调用模型。运行依赖与完整命令见仓库 `docs/RUN_READY_2026-09-30.md`。

加权分和关键项是否通过应分别报告；不能把关键项失败的高格式分解释成答案正确。不同题库、版本、条件和评分权重的结果不得混算。题源快照与改编记录保留，但本包不声称取得了上游公开再分发许可。
''')
    artifact_names=['core.csv','advisory.csv','all.csv','evals.json','changes.json','review_ledger.json','source_bindings.json','release_gate.json','README.md']
    dump('manifest.json',{'release':'run-ready-20260930','counts':{'core':42,'advisory':263,'all':305},
         'source_manifest_sha256':sha(SOURCE/'manifest.json'), 'builder_sha256':sha(Path(__file__)),
         'artifacts':{n:sha(OUT/n) for n in artifact_names},
         'skill_files':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'skills/single_turn').rglob('*')) if p.is_file() and not {'evals','__pycache__','.git'}.intersection(p.parts)}})
    index={'release':'run-ready-20260930','manifest_sha256':sha(OUT/'manifest.json')}
    (ROOT/'data/releases/current.json').write_text(json.dumps(index,indent=2)+'\n')
    print(json.dumps({'release':str(OUT),'core':42,'advisory':263,'all':305,'changed':sum(bool(x['fields']) for x in changes)}))

if __name__ == '__main__':
    build()
