# 本轮正式评测固定配置

2026-10-08确认。适用于已运行的五模型305题、No-Skill/With-Skill两条件实验及其同配置恢复。配置文件为[api_config_formal.json](api_config_formal.json)，与原正式运行保存的API配置一致。

| 模型 | 接口 | 思考开关 | 强度 |
|---|---|---|---|
| deepseek-v4-pro | Chat Completions | disabled | 不传 |
| deepseek-v4-flash | Chat Completions | disabled | 不传 |
| glm-5.3 | Chat Completions | enabled | low |
| glm-5.3-flash | Chat Completions | enabled | low |
| kimi-k2.7-code | Chat Completions | enabled | low |

- 输出上限：10000 tokens；思考模型的服务端用量可能包含思考tokens。
- 单次请求总时限：120秒；响应头45秒、流无数据45秒、无模型内容60秒。
- 总并发上限：16；每个开启思考的模型最多2路。
- 评委：deepseek-v4-pro。
- 执行方式：Python直连Chat API；With-Skill加入匹配Skill文本，不经过OpenCode/BenchFlow容器执行。
- API基础地址：`https://ark.cn-beijing.volces.com/api/plan/v1`；Chat端点为`/chat/completions`。密钥在本地配置，不随仓库发布。

## 同配置恢复要求

补跑和重试必须沿用原运行冻结代码、数据、Skill、提示词、评分协议和请求参数。新运行的计划会保存解析后配置、代码及输入哈希；已有运行应使用原快照恢复并核对绑定。此文档是固定配置说明，不是新增自动校验器，也不保证远端模型服务永不变化。

不要把[api_config.json](api_config.json)用于本轮恢复：它是全关闭思考的试验配置，不能替代正式配置。调整思考、输出额度、时限、题目或评分规则后，应另开实验，不能并入本轮成绩。

原结果恢复还需要原运行目录及快照，仅下载GitHub源码不能恢复未公开的本地日志。新机器从头运行请按[交接说明](handoff/README.md)。

## 配置校验

`api_config_formal.json`的SHA-256：

```text
ed18bfebfe05d6047f86d29a5b3b36c1d6b7900ee1e7a0a7d524f835a3e26cd5
```

从仓库根目录离线检查，不调用API：

```bash
python3 -m repro.paired_runner --out results_v2/formal-config-check --api-config repro/api_config_formal.json --workers 16
```

全新运行（消耗API额度；不是恢复原结果）：

```bash
python3 -m repro.paired_runner --out results_v2/new-formal-run --api-config repro/api_config_formal.json --env-file .env --workers 16 --execute
```
