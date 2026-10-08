# 正式实验评分交付

[263题四类评分算法与公式（简洁版）](263题四类评分算法与公式.md)

**先看：[评分与计算方式：通俗完整版（含公式与例子）](评分与计算方式_通俗完整版.md)。** 从评委逐项判断到单题分、组均值、Skill差值、失败记零及95%区间，逐步解释。

本目录解释 2026-10-02 正式实验及后续恢复结果的评分方法。评委统一为 DeepSeek V4 Pro，包括对它自身回答的评分。这是模型评审，尚不能替代独立专家校准。

## 从哪里看

- [305题评分标准（含题目、背景）](305题评分标准.txt)：直接阅读本次实际使用的逐题检查项、权重和等级描述；TXT仅规范化换行和行尾空白，机器输入以JSON为准。
- [机器可读题库](../../data/releases/source-native-20261001/cases.json)：core 使用 rubric；advisory 使用 criteria 和 applicable_ids。保留修改记录；不是未经修改的来源原文。
- [模型实际配置](judge_model.json)：评委名称、接口和解析后的参数，没有 API 密钥。
- [正式运行配置](../../repro/api_config_formal.json)：作答与评分均使用 Chat；10000 token 输出上限、120秒总时限。评委 DeepSeek V4 Pro 关闭思考；其他模型的覆盖配置见文件。
- [42题评审提示词和计分](../../repro/judge.py)：build_prompt、score_items、evaluate。
- [263题评审提示词和等级校验](../../repro/source_protocol.py)：prompt、labels、allowed_labels、validate。
- [正式评分调用入口](../../repro/source_runner.py)：run_cell；当前42题没有启用 fixed-pro-v2 反证分支。
- [双组正式运行入口](../../repro/paired_runner.py)：baseline 不附 Skill，with-skill 附对应 Skill 全部非评测资源；不是容器内按需调用。
- [论文统计脚本](../../acl-style-files-master/analysis/build_results.py)：从保存的逐项判定核算两套成绩、失败记零和95%置信区间。
- [正式输入与代码校验值](formal_scoring_hashes.json)：上述已有代码和 cases.json 已与正式运行冻结快照逐字节比对一致。

## 42题如何评分

每题有自己的任务维度，每项通过得其全部权重，不通过得0。原任务维度合计80分，另有20分“实质正确性与明确约束”。单题分数为通过项权重之和除以全部权重；模型每组结果为42题均值。critical_pass 另存，不作为加权总分的整题清零开关。

这是修订后的量规，不是最初221项的旧量规；当前合计344项。评委只需返回逐项id/pass，不要求逐项理由。

## 263题如何评分

只评价每题 applicable_ids 指定的维度，要求返回等级、理由、证据和反证。60题有优秀A/合格B/不合格C；100题有优秀/良好/合格/不合格及原数值区间；20题原文只有优秀/合格，程序补充“低于原文最低等级”；83题无原生等级，程序用满足/部分满足/未满足作核查状态。补充状态不是来源原文等级。维度描述和适用范围有编辑性适配，不能声称全文原样评分。

原始判定保留原等级、权重，以及能从原文得到的区间；没有转换依据时总分留空。论文另用“最高等级占比”：每题最高档维度数 / 适用维度数，再对263题平均。最高档包括无原生等级时的“满足”。该统计不使用维度权重，良好/合格在此统计中不计最高档，但不等于原量规得0分。

42题和263题分开报告。Skill提升为两个组均值之差。按本次最终报告约定，剩余28个失败计0，原始失败状态不修改。95%区间来自5000次配对分组重采样：42题按14个Skill、263题按30个来源文档；不衡量模型重复生成的随机性。

## 如何运行

Python 3.12。直接 Chat 评分模块使用标准库；容器旧入口的 BenchFlow 依赖另见 repro/requirements.txt，本次正式 Chat 路径不需要加载本地权重。凭据通过本地环境变量 ANTHROPIC_API_KEY 或 LLM_API_KEY 提供。

只查看计划、不调用模型：

```bash
python3 -m repro source-run --dataset core --task-id hinge-question-designer__01 --models deepseek-v4-pro --judge-model deepseek-v4-pro --api-config repro/api_config_formal.json --base-url https://ark.cn-beijing.volces.com/api/plan/v1 --out results_v2/scoring-smoke
```

加 --execute 会真正生成回答并评分，产生 API 用量；--retry-failed 用于恢复失败。答案保存在 answer.txt，core判定为 grading/judge_result.json，advisory判定为 grading/result.json，status.json 保留状态。

全量双组计划：

```bash
python3 -m repro.paired_runner --api-config repro/api_config_formal.json --out results_v2/new-paired-run
```

同样只有加 --execute 才执行。新运行不会保证复现旧回答及完全相同的分数。

## 论文统计脚本的输入边界

build_results.py 是本次实际使用的原脚本，保留其固定批次路径和28个失败的断言。它需要本地完整 results_v2 正式批次、最终 combined_summary.json、逐项判定、skillbench.pdf，以及输出目录 acl-style-files-master/tables；普通 GitHub 克隆不含这些原始运行文件，因此不能仅凭克隆重建历史论文表格。运行目录需保留原布局，combined_summary 中结果路径需可解析到该仓库内。该脚本不调用模型，不会自动重新评分。

恢复完整运行归档后，安装 analysis/requirements.txt，创建 tables 目录，运行 python3 acl-style-files-master/analysis/build_results.py。没有归档时可用上面的计划/试跑入口验证评分链路，不能声称已复现历史成绩。
