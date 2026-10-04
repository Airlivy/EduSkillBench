"""Generate a pinned-snapshot audit ledger, not model scores or automatic semantic labels.

Semantic findings below encode a human-readable file review dated 2026-09-28.
Unreviewed CN263 cases stay PENDING. Does not modify any source data or evals.
"""
import argparse
import collections
import csv
import hashlib
import json
import re
from pathlib import Path


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def structural(rows, root):
    issues = collections.defaultdict(list)
    ids = [r['task_id'] for r in rows]
    cases = {}
    for path in root.glob('*/evals/evals.json'):
        payload = json.loads(path.read_text())
        for case in payload['cases']:
            if case['id'] in cases:
                issues[case['id']].append('duplicate eval id')
            cases[case['id']] = (payload['skill_name'], case)
    for row in rows:
        tid = row['task_id']
        if ids.count(tid) != 1:
            issues[tid].append('duplicate csv id')
        if any(not value.strip() for value in row.values()):
            issues[tid].append('empty field')
        rubric = json.loads(row['rubric'])
        if sum(c['points'] for c in rubric) != 100:
            issues[tid].append('rubric points do not sum to 100')
        expected = {'id': tid, 'question': row['context']+'\n\n'+row['user_prompt'],
                    'ground_truth': row['expected_output'],
                    'expected_behavior': [c['description'] for c in rubric]}
        if cases.get(tid) != (row['skill_id'], expected):
            issues[tid].append('csv/evals mismatch')
        if not (root / row['skill_id'] / 'SKILL.md').is_file():
            issues[tid].append('missing SKILL.md')
    extra_ids = sorted(set(cases) - set(ids))
    return issues, extra_ids


def classify(dataset, row):
    tid = row['task_id']
    findings = []

    def add(level, code, reason, action):
        findings.append(dict(level=level, code=code, reason=reason, action=action))

    weights = [c['points'] for c in json.loads(row['rubric'])]
    if len(set(weights)) > 1:
        add('待核验', 'WEIGHT_POLICY', f'CSV 分值为 {weights}，evals 仅保留 description，未携带权重。',
            '确认正式等权 PASS/FAIL 或加权评分协议；不可把两种分数视为等价。')
    if dataset == 'v1_42':
        undergrad_bad = {
            'socratic-questioning-sequence-generator__03', 'backwards-design-unit-planner__03',
            'lesson-builder__01', 'lesson-builder__02', 'adaptive-hint-sequence-designer__03',
            'spaced-practice-scheduler__03'}
        if tid in undergrad_bad:
            add('不通过', 'STAGE_LABEL', f'education_level={row["education_level"]}，但 education_stage=graduate。',
                '修正为 undergraduate；同步更新分层统计，保留旧版本用于历史复现。')
        if tid == 'retrieval-practice-generator__03':
            add('不通过', 'STAGE_LABEL', '题面明确 A-Level / pre-university，education_stage 却为 undergraduate。',
                '改为高中/大学预科对应学段，明确统一映射表。')
        if tid == 'self-explanation-prompt-designer__03':
            add('不通过', 'PHYSICS_WORKED_EXAMPLE',
                '非均匀 B(x) 的示例 Step 1 把积分写成 L*w*B(前沿 x)，得 0.012 Wb；题干也未明确线圈朝向和磁场朝向。',
                '明确几何和磁场方向，重新积分并更新解法；允许学生指出原解错误。若 w 沿运动方向且全入场，正确磁通为 0.008 Wb。')
        if tid == 'retrieval-practice-generator__01':
            add('待核验', 'RUBRIC_RECOGNITION',
                'rubric 允许 recognition 类型并要求混合偏向 recall，但另一项说 each question 不能只是 recognition。',
                '明确是否允许识别题及其评分规则，避免合法的混合题集被另一个评分项惩罚。')
        if tid == 'socratic-questioning-sequence-generator__02':
            add('待核验', 'OPEN_ENDED_TARGET',
                '题面要求不导向预设结论，expected_output 却要求走向 necessity of negative emotions。',
                '将目标改为能评估利弊与论证，允许有依据的不同结论。')
        if tid == 'lesson-builder__02':
            add('待核验', 'VERIFY_SCOPE',
                '题面仅要求不确定统计加标，rubric 要求 any specific real-world statistics 均采用固定 VERIFY 格式。',
                '明确确定数据、有来源数据、无外部统计时的规则；不要把有据数据自动视为不确定。')
    else:
        group, index = map(int, re.search(r'__cn(\d+)_(\d+)$', tid).groups())
        if group == 59 and index != 7:
            add('不通过', 'TOPIC_MISMATCH', '问题不是摆锤实验，context/expected_output 却要求绳长、摆锤轻重和摆动计时。',
                '按具体实验重写 context、expected_output 和 rubric。')
        if group == 24 and index != 8:
            add('不通过', 'TOPIC_MISMATCH', '问题目标不是参考限定的线面平行逆向构造，参考仍要求证明线面平行。',
                '按本题数学命题重写专属参考，核对原文映射。')
        if group == 24 and index == 8:
            add('待核验', 'MIDSEGMENT_SCOPE', '本题问中位线定理，参考包含中位线用于线面平行的实例；是否过度限定需复核。',
                '确认是否允许该实例作为合理回答；不再直接归为确定跨主题错误。')
        if group == 25:
            add('不通过', 'TOPIC_MISMATCH', 'user_prompt 为 principal variable method，expected_output 却是 Menelaus theorem。',
                '回溯原文并修正题目—答案配对。')
        if group in {23, 28, 29, 62, 63}:
            add('不通过', 'GROUP_REFERENCE_SCOPE', '单题只问一个子问题，参考要求或 rubric 却覆盖整组不同主题/场景。',
                '按单题拆分参考和 rubric；删除其他子题要求，重新编译 evals。')
        if group == 29:
            add('待核验', 'SKILL_ROUTE', '任务问错因诊断，hinge-question Skill 的核心交付物是诊断选择题；题面未要求该交付物。',
                '重新标注 Skill 适用性，必要时允许多标签或无适配 Skill。')
        if group == 1 and index in {4, 10}:
            add('不通过', 'STAGE_LABEL', '问题明确五/六年级，但 education_stage=middle_school；该批中文小学语境映射不一致。',
                '核对原文及地区学制，按本数据统一学段映射修正。')
        if (group, index) in {(18, 10), (21, 10)}:
            add('不通过', 'MISSING_REVIEW_OBJECT', '要求评价已经设计的完整方案，但没有提供该方案，无法做针对性验收。',
                '补充被评方案，或明确改为条件性评审清单并让 rubric 接受追问。')
        if (group, index) == (7, 10):
            add('待核验', 'MISSING_REVIEW_OBJECT', '要求判断调整后的方案可行性，但未提供完整方案；可以条件性回答，当前 rubric 是否接受不明确。',
                '补充方案，或将任务明确为一般可行性评审方法。')
        if group == 21:
            add('待核验', 'OUTCOME_OBSERVABILITY', 'rubric 涉及学生实际接受度、持续习惯、教师长期疲劳，单次生成文本无法证实。',
                '改为可观察的方案机制与实施指标，不直接要求证明实际长期效果。')
        if group in {29, 63, 50, 54, 56}:
            add('待核验', 'ANONYMIZATION', 'context 残留姓名样式字符串或教师姓名称呼，与无姓名声明不一致；未验证真实身份。',
                '确认是否虚构化名，统一改为教师角色或明确匿名化范围。')
        add('待核验', 'CN263_SEMANTIC_SOURCE_PENDING',
            '已完成全量结构检查和重点语义排查，但本题没有完成原始中文逐句回溯及独立语义通过认证。',
            '补源文并逐题核验 context/question/reference/rubric/Skill；不能因未报错就算通过。')
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger, summary = [], {}
    for dataset, filename, skilldir in [('v1_42','single_turn_tasks.csv','single_turn'),
                                       ('cn263','single_turn_tasks_cn263.csv','single_turn_cn263')]:
        path = args.snapshot/'data'/filename
        rows = read_csv(path)
        errors, extras = structural(rows, args.snapshot/'skills'/skilldir)
        assert not extras, extras
        for number, row in enumerate(rows, 1):
            findings = classify(dataset, row)
            if errors.get(row['task_id']):
                findings.append(dict(level='不通过', code='STRUCTURE',
                                     reason='; '.join(errors[row['task_id']]), action='修正数据与编译文件。'))
            levels = {f['level'] for f in findings}
            status = '不通过' if '不通过' in levels else '待核验' if levels else '通过'
            ledger.append(dict(dataset=dataset, row_number=number, task_id=row['task_id'],
                skill_id=row['skill_id'], status=status,
                structure_status='不通过' if errors.get(row['task_id']) else '通过',
                review_scope='逐题文本初审；非专家/实跑认证' if dataset=='v1_42' else '结构全检+重点语义排查；未全量源文回溯',
                issue_codes=';'.join(f['code'] for f in findings),
                reasons=' | '.join(f['reason'] for f in findings) or '本轮未发现阻塞性题面、参考、评分及学段问题。',
                actions=' | '.join(dict.fromkeys(f['action'] for f in findings)) or '可进入小批 Judge 校准；不表示已完成训练集泄漏认证。',
                education_level=row['education_level'], education_stage=row['education_stage'],
                user_prompt=row['user_prompt'], context=row['context'], expected_output=row['expected_output'],
                rubric=row['rubric']))
        selected = [r for r in ledger if r['dataset']==dataset]
        summary[dataset] = dict(total=len(rows), counts={s:sum(r['status']==s for r in selected) for s in ['通过','不通过','待核验']},
            structural_pass=sum(r['structure_status']=='通过' for r in selected),
            csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            by_skill={s:{state:sum(r['status']==state for r in selected if r['skill_id']==s) for state in ['通过','不通过','待核验']}
                      for s in sorted({r['skill_id'] for r in selected})},
            ids_by_status={s:[r['task_id'] for r in selected if r['status']==s] for s in ['通过','不通过','待核验']})
    for name, subset in [('all',ledger),('passed',[r for r in ledger if r['status']=='通过']),
                         ('failed',[r for r in ledger if r['status']=='不通过']),
                         ('pending',[r for r in ledger if r['status']=='待核验'])]:
        with (args.output_dir/f'task_acceptance_{name}.csv').open('w',encoding='utf-8-sig',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(ledger[0]))
            writer.writeheader()
            writer.writerows(subset)
    (args.output_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 42 + 263 题逐题验收台账','',
        '日期：2026-09-28；快照：65e7fd2119e6afa9d862dbc6166e97887462918e。', '',
        '这是数据验收，不是模型得分。通过仅表示本轮文本初审没有阻塞项；不保证无泄漏或 Judge 已校准。',
        '不通过表示已有明确错误；待核验包含评分协议未确认、语义歧义或未完成源文核验，不等于错误。',
        '优先级：不通过 > 待核验 > 通过。按 task_id 去重计数；一题多问题只计一次。', '',
        '| 数据集 | 总数 | 结构通过 | 初审通过 | 不通过 | 待核验 |','|---|---:|---:|---:|---:|---:|']
    for ds, info in summary.items():
        c=info['counts']; lines.append(f'| {ds} | {info["total"]} | {info["structural_pass"]} | {c["通过"]} | {c["不通过"]} | {c["待核验"]} |')
    for ds, info in summary.items():
        lines.extend(['',f'## {ds} 分 Skill 统计','', '| Skill | 初审通过 | 不通过 | 待核验 |','|---|---:|---:|---:|'])
        for skill,c in info['by_skill'].items():
            lines.append(f'| {skill} | {c["通过"]} | {c["不通过"]} | {c["待核验"]} |')
        for status in ['通过','不通过','待核验']:
            lines.extend(['',f'### {ds}：{status}题号（{len(info["ids_by_status"][status])}）',''])
            lines.extend('- `'+tid+'`' for tid in info['ids_by_status'][status])
            if not info['ids_by_status'][status]: lines.append('无。')
    lines.extend(['','## 逐题阻塞原因（通过题详见 CSV）','', '| 数据集 / CSV 数据行号 | task_id | 状态 | 原因 |','|---|---|---|---|'])
    for row in ledger:
        if row['status']=='通过': continue
        reasons=row['reasons'].replace('|','；').replace('\n',' ')
        lines.append(f'| {row["dataset"]} / {row["row_number"]} | {row["task_id"]} | {row["status"]} | {reasons} |')
    (args.output_dir/'TASK_ACCEPTANCE_LEDGER.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:{a:v[a] for a in ['total','counts','structural_pass']} for k,v in summary.items()},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
