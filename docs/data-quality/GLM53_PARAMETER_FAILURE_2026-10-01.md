# GLM-5.3 请求参数失败原因

实际方舟请求返回 HTTP 400：`thinking.type disabled is not supported by this model`，约0.324秒返回。这是参数不兼容，并不是本次请求思考超时。

官方说明 https://z.ai/blog/glm-5.3 明确GLM-5.3不再允许关闭思考，支持low/high/max三档，默认max。不能把GLM-5.3的限制推广到全部GLM版本。

修正：新运行入口按模型选参数，GLM-5.3及Flash启用思考并显式传低强度请求；添加批量运行前的接口预检。Anthropic兼容接口当前通过output_config.effort传递强度，budget_tokens不是已验证的硬上限；方舟是否有效执行low及实际耗时仍需成功联网实测。

状态：参数构造的离线回归检查可运行；此前15组真实对照均因参数错误未形成评分结果，不能标记为已通过。上一轮联网修复与验收命令被中断，未完成成功调用。历史超时必须按各自日志判断，不能全部归因于这次HTTP400。
