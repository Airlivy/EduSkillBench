# 环境迁移与报错交接（2026-10-04）

这次上传包含当前评测代码、配置模板、题库和来源链、Skill 资源、测试、历史整改文档及环境版本记录。不包含真实密钥、模型权重、虚拟环境二进制或全部运行日志。学长的 Qwen 训练环境、权重路径和代理配置尚未收到，不能声称已完整复制该环境。

## 先分清两条流程

| 流程 | 当前用途 | 环境和限制 |
| --- | --- | --- |
| Chat 直连 | 本机五模型 × 305 题 × baseline/with-skill，共 3050 个评测位置 | Python 标准库 + API；Skill 全文放入提示词，不使用 OpenCode 自动发现或工具执行；一个位置可能含生成、评分和重试等多次 HTTP 请求 |
| OpenCode / BenchFlow 容器 | 历史 Agent 流程和学长的复现排查 | 需要 Docker、BenchFlow、OpenCode、可读且正确注册的 Skill；与 Chat 流程不能当成同一实验。学长的三组/Qwen流程没有在本机端到端验收 |

本机实测：Ubuntu 24.04.4 LTS、Python 3.12.3、Docker 客户端/服务端 29.7.1、OpenCode 1.18.18。系统 Python 没有安装 BenchFlow；另一个独立工具环境装有 BenchFlow 0.6.7。该环境的 107 个包版本和 268 个框架源码文件哈希见 `benchflow-environment.json`。这是本机现状记录，不是已验收的跨平台锁文件；框架可能含历史本地补丁。不能仅凭 `pip install benchflow==0.6.7` 宣称恢复相同运行行为。

## 新机器运行 Chat 评测

在仓库根目录执行；建议 Python 3.12。这个入口只依赖标准库，不需要装 BenchFlow，也不重新训练。

```bash
python3 -m venv .venv
source .venv/bin/activate
cp repro/handoff/env.example .env
# 在本机编辑 .env，填写自己的凭据。
python -m unittest discover -s repro/tests
python repro/handoff/restore_sources.py
# 不访问接口：检查数据、Skill、配置，生成 3050 位置/610 提示词计划。
python -m repro.paired_runner --out results_v2/new-machine-plan --api-config repro/api_config_formal.json
# 以下命令会产生真实 API 消耗，使用独立的新结果目录。
python -m repro.paired_runner --out results_v2/new-machine-formal --api-config repro/api_config_formal.json --env-file .env --workers 16 --execute
```

正式配置为 Chat、输出额度 10000、单次请求总限时 120 秒。两个 DeepSeek 关闭思考；两个 GLM 和 Kimi 使用 low，因为此前服务端拒绝关闭思考参数。`repro/api_config.json` 是已知部分模型会拒绝的全关闭试验配置，不能代替正式配置。服务端可用模型和额度仍需新机器实际验证。

总并发上限 16；保留思考的模型每个最多 2。首次正式执行先跑 20 个位置的 pilot，计入总数；门槛是每模型/条件及题库/条件都有成功位置，并非 20 个全部成功才继续。无额度、网络或格式故障仍可能让任务失败；不得把失败当成零分。

## 目录怎么看

```text
repro/paired_runner.py        当前 Chat 双条件批量入口
repro/source_runner.py        单位置生成、评分、缓存与错误记录
repro/judge.py                API 流式读取、超时、评分校验
repro/resume_paired.py        使用原运行冻结代码与原回答恢复失败位置
repro/api_config_formal.json  正式 API 参数
repro/prepare.py、runner.py   OpenCode / BenchFlow 历史容器入口
repro/handoff/               本交接、版本清单、凭据模板、来源恢复工具
repro/tests/                 离线工程测试
skills/single_turn/          14 个 Skill 的完整公开资源
code/evaluation/             题库构建、修订规则及检查脚本
code/evaluation/tests/       数据及历史证据检查
data/releases/current.json  当前题库指针
data/releases/              冻结题库及父版本来源链，不要单独删父版本
data/exports/               便于审阅的 305 题 JSON、CSV、TXT
data/revisions/             历史修订记录
docs/                       历史审计与整改记录，以文件日期区分阶段
results_v2/                 本地产物，Git 忽略，不随 clone 下载
repro/legacy/、code/legacy/  历史脚本，不作为新机器运行入口
```

历史文档中的本机绝对路径只是当时证据位置；新的运行命令均从仓库根目录执行。`repro/handoff/source-inputs/` 保存历史题源，恢复脚本补齐旧检查器需要的 `jobs/new_scenarios/source/` 路径，遇到不同内容会拒绝覆盖。

## 报错、原因和处理状态

| 问题 | 原因 / 怎样判断 | 处理方法和当前状态 |
| --- | --- | --- |
| Skill 找不到，随后无活动超时 | 学长反馈：快照里目录 700、文件 600，root 所有，agent 无法读取；请求被代理拦在模型之前 | 本机源 Skill 为 755/644，但打包器没有统一权限保证。应在镜像构建时仅对公开 `/skills` 目录设置 755、文件设置 644；检查所有父目录可进入。再以真实 agent 用户验证读取、发现和调用。此处记录学长根因，尚未在其容器中验证修复 |
| 有文件但仍无法调用 Skill | 可读权限与 OpenCode 的发现目录、配置和 Skill 名称匹配是不同条件 | 保存 OpenCode 实际配置/版本、Skill 列表、代理拒绝日志；以实际用户确认目标 Skill 出现在列表，名称与调用一致。不能通过绕过代理校验冒充修复 |
| 失败后轨迹没有导出 | 容器清理可能先于轨迹导出；模型没被调用时也可能根本没有模型轨迹 | 容器清理前，在成功、异常和超时路径都导出 OpenCode/代理日志、容器日志、已有轨迹和退出状态；没有轨迹需注明原因。当前评分 shell 有 EXIT 日志拷贝，但这不代表 Agent 轨迹生命周期已修好，学长环境仍待验证 |
| 请求慢或超时 | 连接、等待响应头、流无数据、只有心跳无内容、整次请求超过时限分别处理；不能仅凭总时长认定模型一直思考 | 当前代码已拆分计时并记录 trace，保留请求 ID/阶段/用量；采用 Chat、可关闭的模型关思考，否则 low。服务端排队与计算无法在客户端保证消除 |
| HTTP 429 | 必须区分并发频率限制和周额度耗尽 | `resume_paired.py` 已加额度熔断、请求间隔及限频冷却；这是恢复入口的保护，不能说原始批量入口也有相同全局保护。额度耗尽需要服务端恢复，盲目重试无效 |
| HTTP 400 / thinking 参数不支持 | 模型或接口不接受某个参数；不是题目错误 | 使用正式配置；已知 GLM/Kimi 全关闭被拒绝。保存脱敏错误正文定位，不把所有 400 都归为同一原因 |
| 有回答但评分失败 | JSON 缺项、无效等级/证据、截断、评分接口或网络错误 | 保存回答和原始评分，严格验证；失败单独记录，不补零分。恢复时优先复用原回答；模型仍可能输出不合格格式，不能保证永不失败 |
| 输出被截断 | 输出和可能的思考耗尽 token 额度，或流没有完整结束 | 检查 finish_reason、usage、完整结束标志；正式上限为 10000。改变配置需新实验/清晰记录，不能混入原冻结结果 |
| 历史验收脚本找不到文件/哈希不符 | 旧测试依赖未发布的运行证据；裁决记录绑定的整份 manifest 已落后于当前版本 | 先恢复随仓库附带的题源；原始历史运行证据仍需另行迁移。过期裁决绑定保持可见，不为测试通过擅自改验收结论；这不是当前 Chat 计划检查失败 |

容器权限修复示例（加入实际镜像构建流程，`/skills` 必须仅包含公开 Skill 资源）：

```dockerfile
COPY skills/ /skills/
RUN find /skills -type d -exec chmod 755 {} + \
 && find /skills -type f -exec chmod 644 {} +
```

这只是权限修复建议，尚未改动冻结实验的打包代码。要验证的三组由学长的实验配置确定，本仓库当前 Chat 入口只有 baseline/with-skill 两条件；不能把离线检查当作三组容器端到端通过。

## 日志保存什么、在哪里、如何迁移

2026-10-04 实测磁盘占用：全部 `results_v2/` 约 567 MiB，最近正式批次 `formal-paired-chat-10000-20261002-r2/` 约 234 MiB。是目录磁盘占用，不是纯日志文本长度或压缩包大小。

- `answer.txt / answer.json`：回答和生成信息，评分失败时用于复用。
- `result.json / status.json`、评分原文：评分结果、有效/失败状态及详细依据。
- 请求 trace/error：请求编号、各阶段耗时、结束原因、用量与报错，排查慢/超时/限频。
- `inputs/、snapshot/、plan.json`：实际提示词、题库/源码/Skill/配置冻结版本及身份绑定。
- `run.log、process.json、summary.json`：进度与汇总；异常退出时需结合退出状态，不能只看某份旧 summary。

本次没有上传整批回答与日志。需要原批次断点恢复，必须迁移完整原目录，不能只拷汇总 CSV。可在原机器打包，再以私下文件传输交接：

```bash
tar -czf /tmp/eduskillbench-run-r2.tar.gz -C results_v2 formal-paired-chat-10000-20261002-r2
# 新机器把该包解压到仓库 results_v2 后：
python repro/resume_paired.py --base results_v2/formal-paired-chat-10000-20261002-r2 --out results_v2/recovery-new-machine --env-file .env --execute
```

恢复输出目录必须是新的；恢复器使用原批次冻结代码，保留已有成功结果，只处理失败位置。分享压缩包前需检查日志里的凭据或私人内容；本次 GitHub 提交已经做凭据模式检查，未上传 .env。

## 本次验证范围

详见同目录 `validation.md`。Chat 运行计划和离线工程测试通过不等于远端接口、全部题目内容或容器流程通过。没有重新训练，没有启动新的付费全量运行。

## 本机框架补丁与镜像

与下载的 BenchFlow 0.6.7 wheel 逐文件对比，本地修改了 5 个 Python 文件，差异见 `benchflow-local.patch`；版本/来源 wheel 哈希见 `benchflow-wheel-comparison.json`。在解压的 wheel 上应用补丁后，268 个 Python 文件哈希与本机一致。补丁用于还原历史环境，含当时的接口和模型假设，不代表目前推荐配置。

`benchflow-observed-requirements.txt` 记录本机工具虚拟环境的所有包版本。仅供独立虚拟环境复现排查，不应覆盖 Chat 的标准库环境；不同系统能否安装这些版本尚未验证。

容器基础镜像本机为 `python:3.12-slim`，观察到的摘要是 `sha256:dd29372629eeba2dd003fd9e9d35a5b8236c44727875a0364254b5127af88e65`。仓库历史入口默认可变 tag，并未自动锁到该摘要；新机器使用其他镜像会产生环境差异。本机 OpenCode 二进制、Docker 镜像和操作系统文件未上传，学长容器内的 OpenCode 版本仍需单独记录。

### 额外发现的容器差异（不能漏掉）

本机宿主 OpenCode 是 1.18.18，但历史 BenchFlow 安装器指定 `opencode-ai@1.18.11`，并用 Node 22.20.0，不能以宿主版本代表容器版本。历史补丁还引用 `http://172.17.0.1:8123/` 的本机缓存服务和预构建 npm 包；新机器通常没有这个服务，安装可能因此失败。交接未上传约 744 MiB 磁盘占用的 `.nodecache`，因此补丁源码一致不等于这条历史容器链路可立即运行。应在学长实际容器环境选择独立安装或迁移相应缓存服务，并验证版本；不要直接套用本机 IP。

宿主 OpenCode 的脱敏 JSON/JSONC 配置及 npm package/lock 文件已附在本目录，名称以 `opencode.host.example` 或 `opencode-host-` 开头。只作为对照，不自动覆盖新机器全局配置，不包含认证值；它们不代表容器内配置。宿主 shell、代理和账户认证可能影响行为，未上传原始个人配置文件。

`historical-build-bundle.sh` 原样保存旧缓存构建脚本，含本机绝对路径和删除旧缓存操作，仅供对照，不能在新机器直接执行。`skill-permissions.json` 记录本机 Skill 文件和目录权限/所有者；Git 不保存原用户 UID/GID 或完整权限位，解包后的权限仍需实际检查。
