# 当前可运行数据

使用 `releases/current.json` 指向的 `run-ready-20260930`。`core.csv` 为 42 题 Skill 对照，`advisory.csv` 为 263 题咨询回答质量，`all.csv` 为全量 305 题无 Skill 测试。运行命令见 [交付说明](../docs/RUN_READY_2026-09-30.md)。`revisions/` 保留此前未完成完整验收的修订过程，不再是新运行默认输入。

# 题库入口

目前修订候选为 [case-review-v4-20260930](revisions/case-review-v4-20260930/README.md)，共 305 题。版本入口由 [index.json](revisions/index.json) 指定。

| 文件或目录 | 用途 |
|---|---|
| `single_turn_tasks.csv`、`single_turn_tasks_cn263.csv` | 历史实验输入，用于追溯已有成绩 |
| `revisions/case-review-20260930/` | 第一轮局部修订记录 |
| `revisions/case-review-v3-20260930/` | 已冻结的上一版候选；10 题、30 份回答做过评分校准 |
| `revisions/case-review-v4-20260930/` | 当前内容修订候选：修正隐含要求、重复计分、条件与参考错漏 |

题面、参考和评分要求修改后，旧成绩不能直接移用。正式发布状态仍关闭；离线检查通过不等于内容全部正确。

从仓库根目录运行：

```bash
python3 -m repro data-check
python3 -m repro data-report
# 根据冻结的 v3 输入和明确修订规则重建 v4 候选：
python3 -m repro data-build
```

这些命令不调用模型。逐字段改动见候选目录的 `changes.json`，修改理由见 `correction_notes.json`。来源原文、分组和 Skill 隔离状态随候选保存。

验收按[测试集验收原则](../docs/data-quality/ACCEPTANCE_PRINCIPLES_2026-09-30.md)执行；逐题分别记录结构、内容专项、Skill 用途和真实评分校准，不能将某一项通过当作整题通过。
