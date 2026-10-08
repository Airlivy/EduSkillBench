# API 请求配置

当前运行入口只使用 [api_config_formal.json](api_config_formal.json)。完整参数及补跑要求见[固定配置说明](FORMAL_CONFIG.md)。

五个模型全部使用Chat Completions；两个DeepSeek关闭思考，两个GLM和Kimi开启思考并设为low。输出上限10000 tokens，总时限120秒。

新机器运行见[交接说明](handoff/README.md)。恢复原实验须使用原运行快照及其配置，不修改历史记录。
