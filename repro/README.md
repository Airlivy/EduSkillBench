# 旧OpenCode／BenchFlow harness运行指南

本文件保留旧版容器运行方式及当时的排查记录。当前正式Chat实验请使用[完整环境与Harness说明](FORMAL_CONFIG.md)，环境迁移与旧框架补丁见[交接说明](handoff/README.md)。下文历史状态、时限和结果数量不代表当前正式实验。

统一使用 `python3 -m repro <命令>`，从仓库根目录运行。这里的 Python 应为当前要使用的环境；付费实验需要安装 BenchFlow 的解释器。默认不调用模型。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `data-check` | 离线检查当前修订题库的完整性、权重、来源与编译绑定 |
| `data-build` | 从冻结输入与修订规则重建当前候选题库 |
| `data-report` | 更新题目内容修订报告；不调用模型 |
| `calibrate` | 对修订题库的正确、错误和跑题回答进行小批评分校准 |
| `check` | 检查全部应有题目、条件及有效成绩 |
| `run` | 运行新实验，或恢复同一标签下未完成的位置 |
| `rejudge` | 对保存的回答统一重新评分，支持断点恢复 |
| `summarize` | 汇总某个运行标签下的成绩及同协议评分恢复结果 |
| `review-summary` | 汇总单独的统一补评分结果 |
| `prepare` | 生成隔离的任务材料 |
| `verify` | 检查双条件题面和完整技能资源 |
| `snapshot` | 记录源码、输入及现有结果的版本对应关系 |

查看参数：`python3 -m repro <命令> --help`。模块文件属于实现，不需要记住多个脚本入口。

## 离线检查

离线工具使用 Python 3.10+ 标准库，不需要密钥或 Docker。

```bash
python3 -m unittest discover -s repro/tests -v
python3 -m repro check --all --root v2 --csv /tmp/eduskill-missing.csv
python3 -m repro verify
python3 -m repro run --tag corrected-2
```

当前已有成绩仍有至少 12 个无效位置，另一个 Kimi 零分缺少逐项详情。因此完整性检查非零退出是预期结果。真实评分接口已进行小批对照校准，记录见 `docs/data-quality/LIVE_CALIBRATION_2026-09-30.md`；容器端到端流程仍待验证。

## 新实验

需要 Python 3.12、BenchFlow **0.6.7**、可用 Docker 和模型接口。`requirements.txt` 固定框架版本，但本机安装仍有此前的额外修改，尚未验证干净环境复现。

使用安装了 BenchFlow 的 Python，例如：

```bash
export BENCHFLOW_PYTHON=/path/to/benchflow-venv/bin/python
export ARK_API_KEY='在本机配置实际密钥'
export ANTHROPIC_BASE_URL='本次实验确定的 Anthropic 兼容接口'
# 基础镜像必须已存在于本机。
# 先查看一题两条件的计划：
"$BENCHFLOW_PYTHON" -m repro run --tag smoke-judge2 --models glm-5.3 --task-id lesson-builder__01
# 显式执行：
"$BENCHFLOW_PYTHON" -m repro run --tag smoke-judge2 --models glm-5.3 --task-id lesson-builder__01 --execute
# 核验成功后，使用独立标签运行完整清单：
"$BENCHFLOW_PYTHON" -m repro run --tag corrected-2 --execute
```

再次运行相同命令会检查已有结果，只处理缺失位置。配置必须一致；题目集合、代码或环境改变时使用新标签。`--rounds 2` 可启用两轮处理，上限三轮。

开始生成回答前会对本次需要的评委模型做接口预检，预检也消耗调用额度。串行执行、单实例锁和资源检查防止无限拉起任务。强制超时后的容器回收仍需真实运行核验。

## 评分失败和恢复

- 单次评分阶段最多三次请求，不再嵌套格式与网络重试。分别限制等待响应头 90 秒、流无数据 60 秒、有心跳但无模型内容进展 180 秒、整次请求 600 秒。仍在正常生成的请求不会在 180 秒时无条件被打断。跨轮恢复和预检会产生额外请求。
- 方舟 `ark.cn-beijing.volces.com` 的评分请求直接连接；本机代理已实测发生 TLS 断连，其他服务仍遵循环境代理设置。每次评分的 `judge_trace_*.json` 保留时间、阶段、内容字符数、事件计数、请求编号及网络错误类型，不保存思考正文或密钥。日志区分连接失败与生成较慢，无法直接看到服务端内部排队原因。
- 认证失败立即停止；空正文、输出中断、格式错误、暂时性网络错误分别记录。持续失败不生成零分。
- 真正全项不通过的回答正常得零分，不会因分数低而重跑。
- 回答已完成但评分失败时，主运行器评价原轨迹，写入该次运行的 `scoring_recovery/`，不覆盖原始结果。
- 保存成功评分后，中断恢复直接复用；题目、轨迹或输入身份改变时拒绝混用。
- 保留完整回答、用户消息和工具记录，排除内部思考。仍超过 200,000 字符就明确报错，不截掉中间部分。
- 记录评分正文、结束原因、用量、请求 ID、内容块类型和分类错误，不记录认证头或密钥。

## 对已有回答统一补评分

修改评分规则后不能只给失败题换新规则，再拼回原榜单。当前计划覆盖 419 份有轨迹且没有明确执行错误的回答；另一个位置需处理回答阶段失败。有轨迹不代表回答已确认完整。

```bash
export ANTHROPIC_API_KEY="$ARK_API_KEY"
python3 -m repro rejudge --out jobs/regrade-v2-judge2
python3 -m repro rejudge --out jobs/regrade-v2-judge2 --resume --execute --limit 2
# 接着未成功的位置继续：
python3 -m repro rejudge --out jobs/regrade-v2-judge2 --resume --execute --limit 2
```

`--limit` 限制本次尝试的待评分位置数，不是 HTTP 次数。每个位置最多三次评分请求，另外还有本次涉及模型的预检。恢复时核对源码、任务、原回答、轨迹及已绑定的接口身份。

旧版本评分程序生成的计划不能直接恢复；使用新目录重新生成计划，保留原计划用于追溯。

## 汇总

```bash
# 统一补评分后的结果：
python3 -m repro review-summary --review jobs/regrade-v2-judge2 --out jobs/regrade-summary
# 某一运行标签下的结果：
python3 -m repro summarize --root corrected-2 --out jobs/corrected-2-summary
```

两个命令默认都拒绝为不完整结果生成榜单，也拒绝覆盖已有输出目录。仅需检查时可加 `--allow-incomplete` 生成明确标记的预览，只比较同题双条件都有效的结果。来源和哈希保存在相应的明细与 `provenance.json` 中。

## 实验选项

- `--metric equal` 为默认主指标，同时保存加权分数；`weighted` 使用题库权重。正式报告需要说明选用的指标。
- `--skill-mode access` 让模型自行读取挂载的完整技能包；`forced` 还把技能正文加入带技能组的题面，两者属于不同条件。
- `--system-profile original` 保留原系统设置；`education-single-turn` 为教育任务专用提示的独立对照，两组公共提示相同。实际系统消息及效果尚待真实验证。

教育提示选项依据 OpenCode 的 [Agent prompt 配置](https://opencode.ai/docs/agents/#prompt) 和 [运行时配置优先级](https://opencode.ai/docs/config/#precedence-order)，通过 `OPENCODE_CONFIG_CONTENT` 设置 `agent.build.prompt`。

## 兼容工具

原来的 shell 入口和安装目录补丁移到 `repro/legacy/`。当前流程不需要修改安装目录，也不需要运行历史看守或备份脚本。归档工具不作为推荐流程的一部分。

## 本地凭据与校准

`ANTHROPIC_API_KEY` 使用 x-api-key；`ANTHROPIC_AUTH_TOKEN` 或 `LLM_API_KEY` 使用 Bearer。已有值优先。`--env-file` 只读取白名单变量的字面赋值，不执行 shell 配置文件。凭据不写入运行计划或评分日志。

```bash
python3 -m repro calibrate --env-file /path/to/local/env \
  --base-url https://ark.cn-beijing.volces.com/api/plan/v1 \
  --out jobs/repair-audit/new-calibration --workers 3 --execute
```

此校准命令明确使用冻结的 **v3 题库与 v3 对照回答**，不是当前 v4 的内容验收入口。校准会产生真实 API 调用，最多每份回答三次；默认只生成计划。冻结后重新执行同一命令会复用已成功结果。`--start` 和 `--limit` 可以限定独立的一批对照样本。

当前评委版本使用完整流式消息，必须收到结束事件才接受评分；允许将完整的顶层评分数组规范为 items 对象，但仍严格验证全部 ID、数量和布尔类型。仅说明性文字、缺项、重复项和截断结果仍拒绝。原始加权分数和关键检查通过状态分别保留，不用部分格式得分代替内容验收。

本接口的 GLM-5.3 实测拒绝 `thinking.type=disabled`，因此保留思考模式与 16,000 输出上限。流式接收不保证永不超时；失败日志区分 HTTP 参数拒绝、网络异常、输出上限和流未完整结束。

批量题目内容复核曾反复耗尽输出额度，未取得有效验收记录；相关实验代码已归档到 `.local-artifacts/`，当前评分实现恢复为已完成上述 v3 校准的版本。本轮不继续批量 API 调用。

当前并发设置（2026-10-01）：`source-run` 默认16路，`--workers` 可选1—16；GLM与Kimi各最多2路。压力测试结果见 [并发测试报告](../docs/data-quality/CONCURRENCY_STRESS_2026-10-01.md)。
