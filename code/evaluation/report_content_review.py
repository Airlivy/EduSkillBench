"""Report content-review coverage and corrections without treating grading as acceptance."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def main():
    revision=ROOT/'data/revisions/case-review-v4-20260930'
    review=ROOT/'jobs/repair-audit/content-review-v3-20260930-low'
    from check_dataset import check
    offline=check()
    validation_path=ROOT/'docs/data-quality/VALIDATION_2026-09-30.json'
    validation=json.loads(validation_path.read_text()) if validation_path.exists() else {}
    acceptance_path=ROOT/'docs/data-quality/ACCEPTANCE_SUMMARY_2026-09-30.json'
    acceptance=json.loads(acceptance_path.read_text()) if acceptance_path.exists() else {}
    if acceptance.get('manifest_sha256') != hashlib.sha256((revision/'manifest.json').read_bytes()).hexdigest():
        acceptance={}
    validation_current=validation.get('candidate_manifest_sha256')==hashlib.sha256((revision/'manifest.json').read_bytes()).hexdigest()
    test_count=sum(x.get('tests',0) for x in validation.get('checks',[]) if x.get('status')=='passed') if validation_current else 0
    rows=[]
    for name in ['single_turn_tasks.csv','single_turn_tasks_cn263.csv']:
        with (revision/name).open() as f:rows.extend(csv.DictReader(f))
    reviewed={}
    for p in review.glob('batch-*/review.json'):
        for r in json.loads(p.read_text())['items']:
            if r['task_id'] in reviewed:raise ValueError('duplicate reviewed task')
            reviewed[r['task_id']]=r
    notes=json.loads((revision/'correction_notes.json').read_text())
    byid=defaultdict(list)
    for n in notes:
        if n not in byid[n['task_id']]:byid[n['task_id']].append(n)
    with (ROOT/'docs/data-quality/review-inputs/SENIOR_LEDGER_2026-09-28.csv').open(encoding='utf-8-sig') as f:
        senior={r['task_id']:r for r in csv.DictReader(f)}
    evidence=[]
    for r in rows:
        tid=r['task_id'];old=senior[tid];reviewed_row=reviewed.get(tid)
        evidence.append({'task_id':tid,'senior_status':old['status'],'senior_issue_codes':old['issue_codes'],
            'ai_content_review_scope':'v3, not corrected v4','ai_content_review':reviewed_row or {'status':'pending'},
            'v4_corrections':byid[tid],'v4_acceptance':'pending_content_recheck_and_calibration'})
    errors=Counter()
    for name in ['content-review-v3-20260930','content-review-v3-20260930-small','content-review-v3-20260930-low','content-review-v3-20260930-effort-only']:
        for p in (ROOT/'jobs/repair-audit'/name).glob('batch-*/failure*.json'):
            errors[json.loads(p.read_text())['category']]+=1
    summary={'total':len(rows),'current_acceptance':acceptance,'v3_ai_content_reviewed':len(reviewed),
             'v3_ai_flagged_tasks':sum(bool(r['findings']) for r in reviewed.values()),
             'v4_changed_tasks':len(json.loads((revision/'changes.json').read_text())),
             'failure_attempts':dict(errors),'batch_content_review_status':'stopped_without_valid_verdicts','offline_checks':offline,'formal_accepted':0,'items':evidence}
    dest=ROOT/'docs/data-quality/CONTENT_REVIEW_2026-09-30.json'
    dest.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    text=f'''# EduSkillBench 题目内容复核与修改（2026-09-30）

> 本文保留 v4 修订阶段记录。当前可运行交付已另存为 run-ready-20260930，完整进度与命令见 [交付说明]({ROOT}/docs/RUN_READY_2026-09-30.md)。新版本与本阶段的验收计数不能混用。

这次检查的是题目、参考答案和评分要求本身，不是给模型回答打分。已把学长的逐题台账作为复查依据；没有直接复用按旧题号写死的“不通过”结论。

已根据直接阅读、原文对照和计算生成新的修订候选，**{summary['v4_changed_tasks']}** 道有字段调整。大部分是评分要求的共同修正，不代表这些题原来都有知识错误。全库编号、字段、参考与评分文件对应关系、权重及来源哈希的离线检查状态：**{'通过' if offline['offline_checks_passed'] else '未通过'}**。

额外尝试的 API 批量内容复核没有取得有效记录，已停止并归档。不能用这次尝试宣称任何题验收通过。

已实际复用学长代码中的结构检查，通过全部 305 题；未复用按旧题号写死的内容判断。当前有 **{acceptance.get('targeted_content_rechecked', 0)} 题**记录了限定范围的内容专项复查，其中科学实验主题对应检查只说明没有答错主题。具体范围和推导见[验收原则与进度]({ROOT.parent}/EduSkillBench_测试集验收原则与进度_2026-09-30.md)。专项通过不等于整题通过。

## 项目整理

已将未验证的接口试验归档，恢复经过小批校准的评分程序；统一题库版本入口、离线检查、重建和汇报命令。当前自动化测试通过数为 **{test_count}**（与本版题库校验值绑定）；测试通过不能替代内容验收。

## 已确认并修改的重点

| 问题 | 问题出现原因 | 解决方法 |
|---|---|---|
| 合理的其他答案可能被扣分 | 题目是开放教学咨询，评分项却指定某个数字例子、材料或步骤 | 直接把应用示例改为可替换示例；仍要求知识正确、满足题面明确限制 |
| 跑题也能因“没有犯错”拿分 | 负向评分只检查错误是否出现，之前实跑出现过跑题仍拿 0.2 分 | 增加“实质回应本题”的条件；新规则的真实评分效果仍待验证 |
| 同一条说明重复得分 | 上轮按句拆分时，把通用解释条件拆成了五条重复评分项 | 说明移回对应评分项，恢复各维度的总权重，避免靠重复的形式要求拿分 |
| 学生的可能障碍被写成确定诊断 | 参考答案对有限课堂观察下了过强结论 | 改成待验证假设，并修正可选同伴示范被拆成必选要求的问题 |
| 经济学解法缺少适用条件 | 把 MR=MC 当成任意成本函数下的充分条件，题内又没有可核算实例 | 补明确的需求、成本和范围，核算最优产量、价格、利润及边界 |
| 个别题问了两部分，参考只覆盖一部分 | “命题与充分条件”只写了充分条件 | 补命题定义，并明确充分、必要条件的不同方向 |
| 个别翻译改变了语气 | 中文询问方案是否符合要求，英文却把部分要求写成已符合 | 恢复待评估问题；没有方案时仍只能给条件性评价 |
| 参考中仍有范围和例外没讲清 | 如把所有向量都说成有方向、把终止递归的要求概括成所有递归的定义 | 补零向量例外、终止条件范围和控制变量实验的具体适用条件 |

以上改动已落到独立修订文件，并保存修改前后内容与原因。旧题库、原评分记录和前一轮校准输入均保留。

## 目前仍需完成的部分

**问题：** 不能宣布全部题目已经没有问题。

**问题出现原因：** 本轮完成了明确问题的修订与专项检查，尚未完成全题库独立内容验收。此前 10 道题的 30 份评分对照不适用于直接认证整个新题库。

**解决方法：** 按题目、参考、评分要求和原文继续核实修订后的内容；有争议的题继续隔离。随后补充不同合理答案和典型错误答案的评分校准，再决定正式纳入哪些题。

**问题：** 复杂复核请求有时没有返回完整结果。

**问题出现原因：** 已记录的失败尝试分类为 {dict(errors)}；其中多次耗尽输出额度，不能解释成题目不合格或题目通过。

**解决方法：** 已停止该批复核，保留全部失败日志，把未验证的接口试验代码移出当前程序。今后先验证最小样本，再考虑扩大；本次不再继续付费重跑。

接口参数参考[方舟 Messages API 文档](https://docs.volcengine.com/docs/ark/messages-api?lang=en)。经济学概念参考[OpenStax 垄断定价章节](https://openstax.org/books/principles-economics-2e/pages/9-2-how-a-profit-maximizing-monopoly-chooses-output-and-price)，本次具体数值另行计算核对。
'''
    (ROOT/'docs/data-quality/CONTENT_REVIEW_2026-09-30.md').write_text(text)
    (ROOT.parent/'EduSkillBench_题目内容复核与修改_2026-09-30.md').write_text(text)
    (ROOT.parent/'EduSkillBench_当前问题与修复状态_2026-09-30.md').write_text(text)
    print(json.dumps({k:v for k,v in summary.items() if k!='items'},ensure_ascii=False))


if __name__=='__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
