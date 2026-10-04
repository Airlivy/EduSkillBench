> 当前正式运行使用 `api_config_formal.json`；3050 位置批次已执行过。以下历史记录的“尚未启动”仅描述当时状态，详见 [交接说明](handoff/README.md)。

# API 请求配置

当前 repro/api_config.json 已按用户要求设置：

```json
{
  "max_output_tokens": 10000,
  "total_timeout_seconds": 120,
  "api_protocol": "chat_completions",
  "thinking_mode": "disabled"
}
```

启动 source-run 时加 --api-config repro/api_config.json 生效。api_protocol 和 thinking_mode 覆盖所有模型的默认策略，包括评分模型。关闭思考时不再发送默认effort或thinking_budget。所有实际选项写入plan并参与缓存绑定；不会影响之前的运行快照。

**服务端验收未通过：两个GLM明确拒绝disabled；Kimi返回参数无效；两个DeepSeek通过。不得将此配置视为五模型正式运行已验收。** 详见 results_v2/all-chat-disabled-6144-probe-20261002/验收说明.md。

配置支持总时限60—600秒、输出上限1025—16000，headers=45秒、idle=45秒、content_idle=60秒不变。省略配置时保留原6144/120秒及各模型原先的思考策略，用于兼容旧命令。旧glm_api_protocol仅影响两个GLM；不能与全局api_protocol同时配置。

## 当前正式配置候选

api_config_formal.json 同样已提高到10000 tokens，全部Chat、120秒；两个DeepSeek关闭思考，两个GLM与Kimi使用low。api_config.json保留全关闭的请求配置（已知部分模型拒绝），不能误用来启动五模型实验。10000额度下的Kimi复测单独记录，尚未启动3050组。
