# 五个模型的最低思考配置

2026-10-01，按要求设置：能关闭则关闭，不能关闭则请求最低档low。覆盖新的305题直接运行入口、原评分器默认调用、self/fixed评分配置，以及BenchFlow使用的OpenCode模型选项。

| 模型 | 实际请求设置 | 简单OK探测耗时 | 返回思考字符数 |
|---|---|---|---|
| glm-5.3 | 开启，low | 2.824秒 | 657 |
| glm-5.3-flash | 开启，low | 3.131秒 | 421 |
| deepseek-v4-pro | 关闭 | 1.069秒 | 0 |
| deepseek-v4-flash | 关闭 | 1.516秒 | 0 |
| kimi-k2.7-code | 开启，low | 1.489秒 | 221 |

五个模型均返回正常结束和OK正文。DeepSeek两个模型在该请求下未返回思考内容；GLM两个模型和Kimi的low参数被接口接受。这只是参数兼容性与简短请求探测，不能把1—3秒推广到实际评分耗时，也不能证明服务端对budget_tokens实施硬上限。

GLM-5.3和Kimi关闭思考会返回HTTP400，重复同参数不会解决。GLM官方说明不再支持关闭思考：https://z.ai/blog/glm-5.3 。方舟Messages接口使用output_config.effort：https://docs.volcengine.com/docs/ark/messages-api?lang=en 。Kimi此处只声称low被当前方舟接口接受，不声称其他平台具备相同能力。

当前集中配置位于repro/judge.py的MINIMAL_MODEL_OPTIONS；新旧运行入口均从这里读取。OpenCode使用thinking.budgetTokens与effort，实际HTTP调用使用thinking.budget_tokens与output_config.effort。开启思考时请求budget_tokens=1024；这不是已实测保证的绝对生成上限。

评分器版本已更新，旧结果保持原文件，新配置不能冒充旧协议续算。既有fixed-pro-v3名称保留兼容，但新运行同样遵循用户要求关闭DeepSeek思考，不再使用它过去的开启思考设置。

原始探测日志：results_v2/minimal-thinking-probe-20261001/summary.json。参数兼容性通过不代表评分准确性通过，关闭思考的DeepSeek已通过15组正确、错误、跑题评分对照；耗时2.182—6.339秒。这不是全库专家验收或外部网络稳定性保证。


补充完整流程验收：五模型各一道同题测试，GLM-5.3、DeepSeek-V4-Pro、DeepSeek-V4-Flash、Kimi-K2.7-Code完成作答、保存和评分；GLM-5.3-Flash仍有思考阶段超时，保留generation_failed记录，不记零分。本轮85项工程测试与36项数据测试共121项通过。设置最低思考已经完成，不等于服务器端所有请求永不超时。完整流程记录见results_v2/minimal-thinking-five-model-smoke-20261001/summary.json。
