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

当前仓库只保留 `api_config_formal.json` 作为运行配置。调整思考、输出额度、时限、题目或评分规则后，应另开实验，不能并入本轮成绩。

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

## 完整运行环境与 Harness

这轮使用的 harness 是 **EduSkillBench 自写的 Python 单轮双条件评测程序**。协议标识为 `native-paired-forced-resources-v1`，原始运行标识为 `formal-paired-chat-10000-20261002-r2`。它没有独立pip版本号，版本由源码SHA-256和冻结运行快照标识。

| 环境项 | 本轮记录／要求 |
|---|---|
| 操作系统 | 交接时记录为Ubuntu 24.04.4 LTS；项目位于WSL Ubuntu工作区 |
| Python | 交接记录为3.12.3；复现建议Python 3.12 |
| 平台依赖 | Linux或WSL内Linux；使用`fcntl`文件锁和`multiprocessing`的`fork`，不保证Windows原生可运行 |
| Python第三方运行依赖 | 当前Chat入口仅用标准库，无需安装BenchFlow；`repro/requirements.txt`属于旧harness依赖 |
| OpenCode、BenchFlow、Docker | 当前Chat执行链路不调用，不需启动Docker；不能将宿主安装的版本当成本轮容器版本 |
| GPU／训练权重 | 本地只调远端模型API，不做训练、不加载本地权重；远端硬件和模型权重修订号未提供 |
| 网络 | HTTPS访问方舟Chat接口；客户端对该方舟域名走直连，系统证书、DNS和网络仍需可用 |
| 凭据 | 本地`.env`，使用`repro/handoff/env.example`模板；配置中的ANTHROPIC变量名不代表使用Messages协议 |

系统版本来自交接时观察，不是每个请求的系统证明。没有记录可用于恢复整台机器的系统镜像或完整OS包锁，也不能仅凭脚本断言当时宿主是否位于外层容器。这里确认的是运行链路本身没有启动OpenCode/BenchFlow/Docker。

### Harness代码和职责

| 文件 | 职责 |
|---|---|
| `repro/paired_runner.py` | 构造3050个位置、拼接两条件提示词、保存快照与输入哈希、多进程调度 |
| `repro/source_runner.py` | 单位置生成、缓存、评分、错误分类与有界重试 |
| `repro/judge.py` | Chat流式请求、超时控制、用量及请求轨迹、core二元判分支持 |
| `repro/source_protocol.py` | 加载冻结题库、构造263题原生量规提示、验证等级和证据 |
| `repro/protocol.py` | 模型清单及共用工具 |
| `repro/credentials.py` | 读取本地凭据，不执行shell配置文件 |
| `repro/resume_paired.py` | 加载原快照，仅恢复失败阶段，保留已有回答 |

2026-10-08逐文件校验：上述前六个核心运行文件与原正式运行计划中的哈希一致。整个`repro/`不宣称逐字相同：辅助探测程序等后来已有维护。恢复时应加载原快照，不能用当前全部源码替换原快照。

[formal_environment.json](formal_environment.json)附原计划、原代码哈希、305题标识与数据摘要、全部Skill文件哈希、610份提示词摘要及当前核心文件校验结果。原计划含历史辅助文件名，仅供追溯，不是另一个运行入口。SHA-256只能标识版本，不能保证模型输出逐字复现。

### 数据、Skill与提示词

- 输入发布目录：`data/releases/source-native-20261001/`，其中`cases.json`为305题：42题core＋263题advisory。
- 本轮305题、发布manifest和Skill资源均与原计划摘要核对一致；论文选择278题只是后续汇总子集，不改变原305题运行输入。
- Skill目录：`skills/single_turn/`，14个匹配Skill，共24个资源文件；`lesson-builder`含11个文件。排除`evals`、`__pycache__`、`.git`目录。
- 匹配方法：按题目ID前缀确定一个Skill，检查显式skill_id一致性；不是top-k检索，也不是让Agent自主发现。
- No-Skill提示词为背景＋用户问题；With-Skill在其后追加匹配Skill的所有所选资源文本。每题每条件一份提示词，五模型共用，共610份。
- 单轮生成，Chat消息只含一条user消息，没有额外system消息、工具调用或多轮环境交互；Skill内部的角色指令属于加入的文本。
- 没有显式发送temperature、top_p或seed，因此不能宣称采样确定性或服务端默认值恒定。

### 实际发送的Chat参数

`model`为表中模型ID，`max_tokens=10000`，`stream=true`，`stream_options.include_usage=true`。两个DeepSeek发送`thinking.type=disabled`；GLM和Kimi发送`thinking.type=enabled`及`reasoning_effort=low`。评分请求还按需要发送JSON schema响应格式约束。

**计划里的`thinking_budget=1024`是内部继承字段，不是实际Chat硬预算。** Chat序列化分支将thinking对象替换为仅含type，未发送budget_tokens；不能据此说思考被限制在1024 tokens。所有请求均使用`/chat/completions`，没有切回Messages。

### 调度、恢复、评分和日志

总并发16；每个开启思考的模型最多2个活动位置。初次执行先运行20个pilot位置并计入3050总数；门槛是各模型/条件及题库/条件均有成功位置，不要求pilot全成功。

生成及原生评分的单阶段重试为`shared-two-attempts-validation-feedback-v1`：网络与格式纠错共享最多两次请求。后续显式恢复属于额外轮次，不能说一个位置在整个实验中最多只请求两次。恢复调度另有全局请求启动间隔至少0.5秒、频率429后30秒冷却、额度耗尽暂停派发；这属于已有恢复实现，原模型参数和提示词不变。

所有模型均由DeepSeek V4 Pro评分。42题保留原加权通过/不通过量规；263题保留原等级及证据判定。此环境没有启用候选答案与参考答案的联合相对评分。评分模型与被测模型为同一型号的情况在DeepSeek V4 Pro行确实存在。

有效回答、判分、失败状态分别保存。评分失败不伪造成有效低分；用户后来选择在结果汇总中将未完成位置记零，这是统计处理，不是模型原判分。重试只处理失败阶段，不按得分高低挑选答案。

输出目录主要包含`plan.json`、`snapshot/`、`inputs/`、`input_hashes.json`、`summary.json`、按条件/模型/题号分组的回答、generation和grading轨迹。轨迹记录请求ID、时间、字数、结束原因及可用usage，不记录思考正文。旧实现总时限异常时不保存内存中的部分正文，因此超时记录并非完整逐token回放。

### 新机器从头运行

从仓库根目录执行；这会创建新实验，不会自动恢复本机已有成绩。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
cp repro/handoff/env.example .env
# 编辑.env，填写自己的API凭据。
python -m repro.paired_runner --out results_v2/new-machine-plan --api-config repro/api_config_formal.json --workers 16
# 确认计划后，以下命令会产生API费用：
python -m repro.paired_runner --out results_v2/new-machine-formal --api-config repro/api_config_formal.json --env-file .env --workers 16 --execute
```

上述Chat计划直接使用发布题库，不需要先恢复旧题源或安装旧容器依赖。运行前可执行`python -m unittest discover -s repro/tests`。不需要重新训练。

### 恢复原实验

须先取得原运行目录（包含完整plan、summary、snapshot、inputs、input_hashes及已有回答），GitHub源码不包含全部原始运行日志。单个完整运行目录的恢复命令：

```bash
python3 repro/resume_paired.py --base /path/to/original-run --out results_v2/recovery-new-round --env-file .env --execute
```

该工具核对原源码、提示词、配置和题库摘要后加载原实现。不能把只有失败子集的恢复目录或仅有combined_summary的汇总目录直接当作完整base；多轮已合并结果需要同时保留其指向的实际结果目录，并正确排除已经成功的位置。

### 验证范围

本次核验覆盖原配置一致性、核心harness源码、题库和Skill摘要、干净源码副本的离线3050位置计划。没有新增付费推理，也没有在另一台机器验证远端模型可用性。接口服务、模型别名、默认采样策略与额度由服务端控制；配置相同不代表永不超时或回答逐字相同。
