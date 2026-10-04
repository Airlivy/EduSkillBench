# CN263 数据验收报告（2026-09-28）

## 更新：纳入原有 42 题及逐题验收台账

已将同一快照的 `data/single_turn_tasks.csv`（42 题）与新增 CN263 一起纳入，共 **305 题**。这不是把原有 42 题替换掉，也没有修改原测试集或实验结果。

| 数据集 | 总数 | 结构检查通过 | 本轮初审通过 | 明确不通过 | 待核验 |
|---|---:|---:|---:|---:|---:|
| 原有 v1 | 42 | 42 | 22 | 8 | 12 |
| 新增 CN263 | 263 | 263 | 0 | 63 | 200 |
| 合计 | 305 | 305 | 22 | 71 | 212 |

**这不是模型答题通过率。** “初审通过”仅表示本轮逐题文本检查未发现阻塞项，不是无泄漏、专家复审、Judge 校准或真实课堂有效性的认证。“不通过”是已确认的题面/参考/元数据错误；“待核验”是评分协议待确认、语义歧义或尚未完成充分核验。不能把 CN263 的 200 条待核验算成通过，也不能算成 200 条已确认错误。

42 题已逐题阅读 context、user_prompt、expected_output、rubric 与学段；263 题完成结构全检及重点问题组排查，尚未完成全部源文回溯。评分权重问题单独记为待核验：若明确采用等权 PASS/FAIL，可以更新判定；它不是题目本身必然错误。

每题的完整 task_id、CSV 数据行序号（不含表头）、状态、问题类别、证据和修改建议见：

- [逐题台账与分 Skill 统计](task_acceptance_2026-09-28/TASK_ACCEPTANCE_LEDGER.md)
- [全部 305 题 CSV](task_acceptance_2026-09-28/task_acceptance_all.csv)
- [通过题目 CSV](task_acceptance_2026-09-28/task_acceptance_passed.csv)
- [不通过题目 CSV](task_acceptance_2026-09-28/task_acceptance_failed.csv)
- [待核验题目 CSV](task_acceptance_2026-09-28/task_acceptance_pending.csv)
- [机器统计及按状态分组的题号 JSON](task_acceptance_2026-09-28/summary.json)

计数按 task_id 去重；同一题多个问题只算一次，状态优先级为“不通过 > 待核验 > 通过”。台账标注是本次阅读审查的判断，脚本只是复查结构并编译已记录判断，不是自动语义判定器。

### 原有 42 题：8 条明确不通过

| task_id | 问题 | 影响 |
|---|---|---|
| retrieval-practice-generator__03 | 题面为 A-Level / pre-university，stage 却为 undergraduate | 学段元数据错误；不表示题目不可回答 |
| socratic-questioning-sequence-generator__03 | 明确本科二年级，却标为 graduate | 学段统计错误 |
| backwards-design-unit-planner__03 | 明确本科一年级，却标为 graduate | 学段统计错误 |
| lesson-builder__01 | Undergraduate 标成 graduate | 学段统计错误 |
| lesson-builder__02 | Undergraduate 标成 graduate；另有统计数据 VERIFY 范围不一致待确认 | 学段统计错误及评分歧义 |
| adaptive-hint-sequence-designer__03 | Undergraduate 标成 graduate | 学段统计错误 |
| spaced-practice-scheduler__03 | 明确本科二年级，却标为 graduate | 学段统计错误 |
| self-explanation-prompt-designer__03 | 非均匀磁场的示例解法错误，几何和磁场方向未明确 | 教材解法可能诱导错误，或使模型纠错被误判为偏离任务 |

物理题的具体核对：题目用 B(x)=B₀x/d，却在 Step 1 把磁通积分替换为 LwB(x)，并把 x 明确设为前沿位置，而非面积中点。磁通应积分整个线圈面积。[公式依据：OpenStax Faraday’s Law](https://openstax.org/books/university-physics-volume-2/pages/13-1-faradays-law)。

本审查的条件性计算：若 w=0.2m 沿运动方向、L=0.5m 垂直运动方向，线圈全处于磁场内且磁场垂直线圈，则前沿 x=0.3m 时，磁通应为 `L*(B₀/d)*[x²-(x-w)²]/2 = 0.008 Wb`，不是题目的 `0.012 Wb`。该假设下磁通对 x 的导数仍为 `0.04 Wb/m`，所以 `0.12 V` 与 `0.06 A` 恰好不变，**不能据此说其最终电压和电流一定错误**。应先补明确方向和入场区间，再修正示例与评分。

### 原有 42 题：12 条待核验

- 不等权 rubric 在 evals 转换中未保留，需确认评分协议：motivation-diagnostic-task-redesign__01、__02、__03；self-efficacy-builder-sequence__01、__02、__03；lesson-builder__03；emergent-project-design-scaffold__01、__02、__03。共 10 题。
- retrieval-practice-generator__01：允许 recognition 类型的要求，与“每题不能仅靠 recognition”之间需要明确适用范围。
- socratic-questioning-sequence-generator__02：题目要求开放探究，参考却要求走向“负面情绪的必要性”；应允许有依据的不同结论。

### CN263：63 条不通过的去重组成

| 问题 | 题号范围（完整前缀见台账） | 数量 |
|---|---|---:|
| 非摆锤题配摆锤参考 | cn59_01–06、08–10 | 9 |
| 不同数学命题配线面平行参考 | cn24_01–07、09 | 8 |
| 主元法配梅涅劳斯定理 | cn25_01 | 1 |
| 单题配整组主题的参考/评分要求 | cn23_01–08、cn28_01–04、cn29_01–09、cn62_01–10、cn63_01–10 | 41 |
| 学段映射错误 | cn01_04、cn01_10 | 2 |
| 要求评审完整方案，却没有给出方案 | cn18_10、cn21_10 | 2 |

复核修正：前版将 cn24 全部 9 题计为跨主题错配；本次把 `lesson-builder__cn24_08` 降为待核验，因为其中位线问题与参考中的中位线构造实例存在关联，不能直接断言错误。因此前版“19 题明确跨主题错配”更新为 **18 题**；另新确认了整组参考范围等问题，形成当前 63 条去重不通过记录。`differentiation-adapter__cn07_10` 缺少完整被评方案，但可作条件性可行性回答，保守列入待核验。

复现台账：

```bash
python3 code/evaluation/build_task_acceptance_ledger.py external/cn263-review-20260928 docs/task_acceptance_2026-09-28
```

以下保留首轮分析，数量解释以上述更新及台账为准。

## 结论

**结构检查通过，语义与评测验收不通过。暂不作为正式测试集、Skill 路由金标或直接 SFT 目标。** 可保留为待修订的真实教学任务候选池。没有修改下载的数据，没有启动训练或付费 Judge。

核心问题不是数量，而是拆题后没有同步拆分背景、参考要求和 rubric：263 个不同问题只有 30 套背景、30 套参考要求、30 套 rubric。复用本身并非错误，但已发现直接跨主题错配和单题被要求回答整组问题的情况。这会把数据问题误判成模型不会使用 Skill。

## 版本与来源

- 数据所在仓库：`Airlivy/EduSkillBench`，提交 `65e7fd2119e6afa9d862dbc6166e97887462918e`。
- 独立快照：`/home/gpuuser/csl/EduSkillBench/external/cn263-review-20260928`。
- 参考仓库 `ybai-nlp/EduBench` 另行下载到 `external/EduBench-source-20260928`，提交 `f19004a5c68c27cd9d354401654345072fb712c6`。
- 新版发布说明将直接题源标为 `edu_scene_66` 的 `467fcaf`，EduBench 是场景分类参考，不应把 263 题描述成从 EduBench 直接抽取。
- 尚未获得可核对的原始中文题源快照，不能认证翻译忠实性、原始授权或全部抽取链路。需作者补充题源访问方式及每题原文位置。

## 全量结构检查

| 项目 | 结果 |
|---|---:|
| CSV / trace / evals 条数 | 263 / 263 / 263 |
| 字段数 | 11 |
| 空字段、重复 task_id、溯源索引错位 | 均未发现 |
| CSV 到现有 evals 的逐字段一致性 | 通过 |
| 不同 user_prompt | 263 |
| 不同 context / expected_output / rubric | 30 / 30 / 30 |
| source_record 数量 | 30 |
| rubric 分值合计 | 全部 100 |
| 存在不等权 rubric 的题目 | 224 |
| Skill 数 | 9（原版为 14） |
| 已复制 Skill 文件与 v1 内容相同 | 9 / 9 |
| 与 v1 完整题面规范化后完全重复 | 0（不等于语义无泄漏） |

Skill 分布：lesson-builder 154；differentiation-adapter 30；adaptive-hint-sequence-designer 20；project-brief-designer 16；backwards-design-unit-planner 10；socratic-questioning-sequence-generator 10；hinge-question-designer 9；retrieval-practice-generator 8；self-efficacy-builder-sequence 6。lesson-builder 占 58.6%，总平均分会主要反映这一类。

缺少的 5 个原版 Skill：emergent-project-design-scaffold、motivation-diagnostic-task-redesign、ruler-emotional-literacy-sequence、self-explanation-prompt-designer、spaced-practice-scheduler。9 类任务不适合直接声称覆盖了全部 14 类能力。

## 语义问题与可复查样本

以下是人工阅读文件后确认的具体问题，不是运行 LLM Judge 得到的错误率；不能将抽查结果外推为全部 263 题都错误。

| 优先级 | task_id / 分组 | 题目与问题证据 | 修订要求 |
|---|---|---|---|
| P0 | adaptive-hint-sequence-designer__cn59_01 | 问一年级回形针沉水，背景和参考却要求比较摆锤绳长、释放高度、计时及轻重摆锤 | 按水面张力现象重写背景、参考与 rubric |
| P0 | cn59 组除 _07 外的 9 题 | 用户问题分别涉及其他科学实验，但全组沿用摆锤背景与参考 | 逐题拆分；不能只换 user_prompt |
| P0 | lesson-builder__cn24_01 | 问线面垂直判定，参考明确要求证明线面平行 | 按实际数学命题改写 |
| P0 / 待核验 | cn24 组 9 题 | 涉及不同几何/代数命题，全组参考却固定为线面平行的逆向构造 | 8 题不通过；_08 中位线实例的适用性待核验 |
| P0 | lesson-builder__cn25_01 | 问主元法，参考是梅涅劳斯定理的动机、推导和训练 | 回溯原文确定抽取或配对错误 |
| P0 | retrieval-practice-generator__cn23_01 | 只问函数定义域，参考要求八类题组，包含三角、数列、圆、二项式等 | 将整组参考按单题拆开 |
| P0 | differentiation-adapter__cn62_02 | 只问连续答错后的自动保护动作，参考要求全部十种场景，还包括防 AI、实训作业、题库管理 | 仅保留本题可观察的目标与评分项 |
| P1 | hinge-question-designer__cn29_01 至 _09 | 问错因诊断；Skill 规定输出单个选择题、干扰项诊断与课堂分流，但任务并未要求这些产物 | 独立审核路由；可接受多 Skill / 无适配 Skill，不能强置唯一金标 |
| P1 | lesson-builder__cn21_10 | 请求评价已设计的课堂方案却没有给出完整方案；rubric 又要求学生实际响应、习惯稳定、教师不疲劳 | 补方案与观察证据，或改为评估设计是否包含可执行机制 |
| P1 | lesson-builder__cn01_04、__cn01_10 | 分别明确五、六年级，education_stage 却为 middle_school | 统一年级到学段的映射 |

跨主题分组经本次复核确认 **18 题**存在具体参考目标错配（cn59 的 9 题、cn24 的 8 题、cn25 的 1 题；cn24_08 待核验）。这不是全部问题数量；单题/整组答案范围错配等问题另计，完整去重记录见上方台账。

## 评分口径问题

`code/evaluation/build_evals_cn263.py` 将 `expected_output` 原样放入 `ground_truth`，仅把 rubric 的 `description` 放入 `expected_behavior`，没有保留 `points` 和 `criterion`。

因此，224 题原本不等权的评分标准在编译后的文件中丢失权重。若继续用等权逐项 PASS/FAIL 比例，就不是原始加权分数。是否采用等权二值判定可以决定，但必须显式定义，不能把两种分数当作同一口径。

此外，多个 description 同时包含 Excellent / Pass / Fail 的分档描述，不是独立的“满足某条件”命题。应拆成与本题对应、可由输出证据判断的原子标准，明确通过阈值；不能让 Judge 自行猜测多档描述如何二值化。本次没有运行 Judge，因此没有宣称具体误判率。

## 匿名化、隔离与内化实验风险

1. 发布说明宣称题面没有姓名，但 cn29、cn63 的 context 仍有完整拼音姓名样式字符串，合计 19 题；另有 30 题含教师姓名称呼。未验证这些是否是真实人物，不能据此认定真实身份泄漏；但与匿名化声明不一致，应核对并替换为角色。
2. 263 题不是 263 个独立来源。随机按题切 train/dev/test 会把同一 source_record 的相同背景、参考和 rubric 分到不同集合。至少按 source_record 分组，再检查跨来源近似模板；应先冻结测试来源，再合成训练变体。
3. 与旧 v1 无完全重复，不代表与既有合成训练集无语义重叠。本次未完成对所有历史训练池的语义泄漏审计，不对其作保证。
4. expected_output 多是“A satisfactory answer should...”式评分说明，**不是完成任务的成功解法，不能直接当 SFT target**。应在任务修订后生成实际解法，再验证。
5. 某些 context 已给出应采用的解决流程。内化评测需标记哪些题面提供了 SOP：No-Skill 不应暗中包含完整方法，否则无法明确归因到模型内化。

## 建议返修顺序与验收门槛

1. 补原始中文来源与定位信息；逐题建立“原文问题 → 英文问题 → 独立背景 → 该题交付物 → 原子 rubric”的记录。
2. 优先修复上述跨主题错配和整组参考污染，再全量检查 263 题。背景仅保留本题必要事实，不携带其他问题和答案步骤。
3. 将 Skill 适用性与答案质量分开审核。先判断题目是否真正需要该 SOP，再决定唯一或多标签路由；不要为填满 14 类强行贴标签。
4. 确定评分口径（等权 PASS/FAIL 或显式加权），编译后可追溯每个评分项。加入正确主题答案和跑题但迎合旧参考的答案作为 Judge 单元测试。
5. 按来源与近似任务簇隔离集合；报告总体均分同时报告各 Skill 均分与 macro average。若仍仅覆盖 9 Skill，应明确标注。
6. 返修验收通过后，再做小批模型试跑验证题面和 Judge；当前不建议消耗 GPU/API 跑正式 263 题或把它们直接训练进去。

## 复查方式

在主工作仓库运行：

```bash
python3 code/evaluation/audit_cn263_snapshot.py external/cn263-review-20260928
```

该脚本只做结构检查和明确字符串标记，不认证语义正确性。机器报告保存在同目录 `CN263_STRUCTURE_AUDIT_2026-09-28.json`。

任务 CSV SHA256：`05c12f470c84ce27f9d95711af4e1dc4b68734fb8cdeed08859cca9a3ad0ae30`。

溯源 CSV SHA256：`0054d64b2732905d9eac4f88693bbdd79cd95e1e039ee881f1dfdd95cbd259b7`。
