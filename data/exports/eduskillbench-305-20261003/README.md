# EduSkillBench 当前305题快照（2026-10-03）

这是当前本地实验实际使用的305题内容快照，与2026-10-02启动的双条件实验题库逐字节一致。本次发布只更新题库交付，不发布实验成绩或替换运行代码。

## 文件

- [cases.json](cases.json)：全部305题，包括背景、问题、参考输出要求及评分规则。
- [305题运行审阅.txt](305题运行审阅.txt)：逐题阅读版；42题保留英文原文，263题保留当前中文内容。
- [scope_and_changes.json](scope_and_changes.json)：评分适用范围和修订记录。
- [snapshot.json](snapshot.json)：文件校验值与内容说明。

## 如何理解答案和评分

- 42题 core 使用原有rubric；expected_output通常是交付要求或参考要点，不一定是完整标准答案。
- 263题 advisory 保留原文等级与权重，criteria为评分维度、applicable_ids为本题适用维度。这263题没有原文逐题标准答案，expected_output为空，不补编答案。
- 原始文档名称可能对应其他教学主题，original_source用于溯源。实际作答与评分以本题context、user_prompt、适用维度为准；原文其他主题示例不属于必答内容。
- core数值分与advisory原文等级不能直接混算为统一总分。

## 已知限制

之前发现的双曲线套用椭圆背景、主元法套用梅涅劳斯背景等错配已修订。本快照不代表305题已获得专家逐题无误认证。

该数据用于单轮教学任务；有技能/无技能两种条件使用同一题库，差异在作答时是否提供技能材料，数据文件本身不复制为610题。技能材料仍见仓库skills/single_turn目录。

另附 `cases.csv`（UTF-8 BOM，305 行），字段与 cases.json 对应；列表/对象字段用 JSON 文本保存。CSV 便于 Excel 审阅，运行仍读取发布版 JSON。
