"""Summarize frozen live calibration evidence without promoting a benchmark release."""
import hashlib
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'jobs/repair-audit'

def read_round(name):
    folder=BASE/name
    plan=json.loads((folder/'plan.json').read_text())
    fixtures=json.loads((folder/'fixtures.json').read_text())
    rows=[]
    for item in fixtures:
        p=folder/item['task_id']/item['variant']/'calibration_check.json'
        rows.append(json.loads(p.read_text()) if p.exists() else {'task_id':item['task_id'],'variant':item['variant'],'status':'pending_or_interrupted'})
    errors=Counter()
    for p in folder.glob('*/*/judge_failure*.json'):
        errors[json.loads(p.read_text())['category']]+=1
    usage=Counter()
    for p in folder.glob('*/*/judge_response*.json'):
        for k,v in (json.loads(p.read_text()).get('usage') or {}).items():
            if isinstance(v,(float,int)):usage[k]+=v
    return {'directory':str(folder.relative_to(ROOT)),'plan':plan,'rows':rows,
            'failure_attempts':dict(errors),'reported_usage':dict(usage)}

def main():
    names=['v3-calibration-20260930-pass1','v3-calibration-20260930-pass2',
           'v3-calibration-20260930-probe3','v3-calibration-20260930-probe3-detail',
           'v3-calibration-20260930-probe4','v3-calibration-20260930-pass4']
    rounds=[read_round(n) for n in names if (BASE/n/'plan.json').exists()]
    final=rounds[-2:]
    if len(final)!=2:raise RuntimeError('final waves missing')
    for field in ['judge_version','judge_sha256','dataset_sha256','endpoint_sha256','model']:
        if final[0]['plan'][field]!=final[1]['plan'][field]:raise RuntimeError('incompatible final waves: '+field)
    rows=[r for x in final for r in x['rows']]
    assert len({(r['task_id'],r['variant']) for r in rows})==len(rows)==30
    scored=[r for r in rows if r['status']=='scored']
    matches=sum(r.get('meets_authored_expectation',False) for r in scored)
    final_errors=Counter()
    for wave in final: final_errors.update(wave['failure_attempts'])
    complete=len(scored)==30
    details={r['task_id']:{} for r in rows}
    for r in rows:details[r['task_id']][r['variant']]=str(round(r['score'],4)) if r['status']=='scored' else r['status']
    report={'model':'glm-5.3','judge_version':final[0]['plan']['judge_version'],
            'expected_responses':30,'scored':len(scored),'expectation_matches':matches,
            'final_failure_attempts':dict(final_errors),
            'all_expectations_met':complete and matches==30,'rounds':rounds,
            'limitations':['Only 10 authored cases, not all 305 tasks.','Eight cases informed development; two added holdouts are not independent expert validation.',
                           'No five-model agent experiment was performed.','Connection success does not guarantee future service availability.'],
            'benchmark_release_ready':False}
    (BASE/'v3-calibration-20260930-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    text=f'''# EduSkillBench 真实评分校准（2026-09-30）

接口已经接通。凭据原本保存在本地 `.bashrc`，变量名是 `ANTHROPIC_AUTH_TOKEN`；之前只检查另一种变量名，误报成没有凭据，这一点已修正。未把密钥写入项目文件。

目前最终配置完成 **{len(scored)}/30** 份评分，其中 **{matches}** 份符合事先写定的对照预期。状态：{'本批对照完成' if complete else '本批仍在进行或有未完成项'}。使用 GLM-5.3，评委版本 `{report['judge_version']}`。

## 本轮真正发现和处理的问题

| 问题 | 日志证据与原因 | 处理 |
|---|---|---|
| 配置存在但程序找不到 | 凭据变量名不同，且非交互 shell 没自动加载配置 | 支持 AUTH_TOKEN、API_KEY 和 LLM_API_KEY；显式读取 env 文件，不执行 shell 内容 |
| 返回完整评分数组却被当成格式失败 | 第一轮出现完整数组，而解析器只接受外层 items 对象 | 只规范化这种完整结构；缺项、错 ID、重复项和非布尔值仍拒绝 |
| 答案有错误仍得高分 | 第一轮把 11×4 写成 45 的回答得满分；几何矛盾也有漏判 | 要求逐项检查完整回答，不能用其他正确句子抵消实质错误；分别记录分数和关键检查状态 |
| 请求没有完整结束 | 第一轮有 transport 错误；旧日志不足以进一步确认每次网络失败的原因 | 改为完整流式接收，记录异常类型、时长和终止原因；未收齐不记零分 |
| 输出预算耗尽 | 第二轮实际返回 max_tokens，输出达到 8192 | 停止该轮，恢复 16000 上限；不能把继续重试当成解决预算问题 |
| 关闭思考被服务端拒绝 | 小样探测返回 HTTP 400，明确说该模型不支持 disabled | 恢复兼容配置；不再重复发送这个不支持的参数 |

第一轮：24 份对照，14 份成功评分，其中 12 份符合预期；10 份评分失败。第二轮因实际发现输出上限问题中止，保留中间结果。最终两批使用相同代码、题库和接口身份，合并为 30 份对照；没有覆盖失败记录，也没有把先前不通过的样本删掉。

最终配置中的失败尝试记录：{dict(final_errors)}。即使提高到 16000 token，本轮仍出现过输出截断，随后通过有限次数的自动重试完成。这说明预算调整缓解了问题，但没有彻底消除；30/30 是最终完成数，不代表每次请求都一次成功。

## 最终配置逐题对照

| 题号 | 正确回答 | 含实质错误的回答 | 跑题回答 |
|---|---:|---:|---:|
'''
    for tid,values in details.items():
        text+='| '+tid+' | '+' | '.join(values.get(v,'pending') for v in ['positive','factual_error','off_topic'])+' |\n'
    text+='''
分数范围为 0–1。错误回答可能仍因其他部分正确而有部分得分，所以校准还检查指定错误是否被对应评分项识别，不以“分数小于 1”冒充识别成功。

## 结论边界

这是 10 道题、每题 3 种完整回答的小批校准，不是 305 题全部验收，也不是五个模型的正式对比实验。8 道参与了开发排错，另有 2 道新增检查；这些预期仍由本次修订者编写，没有冒充独立专家验收。测试集发布状态继续保持关闭。

外部接口仍可能超时、限流或中断。已经修正的是明确的配置、格式和判定问题，以及失败时不生成假零分的处理，不能保证外部 API 从此永不失败。

配置依据还参考了[方舟 Agent Plan 接入说明](https://docs.volcengine.com/docs/ark/agent-plan-enterprise-claude-code?lang=zh)；模型是否支持某个参数以本次实际返回为准。

逐项评分、原始评分正文、请求标识、用量与失败分类保存在 `jobs/repair-audit/` 中对应校准目录。汇总文件为 `v3-calibration-20260930-summary.json`。
'''
    p=ROOT/'docs/data-quality/LIVE_CALIBRATION_2026-09-30.md';p.write_text(text)
    (ROOT.parent/'EduSkillBench_真实评分校准与修复_2026-09-30.md').write_text(text)
    print(json.dumps({k:report[k] for k in ['scored','expectation_matches','all_expectations_met']}))

if __name__=='__main__':main()
