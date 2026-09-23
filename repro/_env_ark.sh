#!/usr/bin/env bash
# _env_ark.sh -- 跑批需要的全部环境变量，集中一处，供各脚本 source。
#
# 为什么需要两组变量：
#   ANTHROPIC_*  → 给 benchflow 的 LiteLLM 代理和 agent 走 ark 的 anthropic 路由
#   OPENAI_*     → 给【评委】(judge) 用；评委直接调 SDK，走 ark 的 OpenAI 兼容端点。
#                  缺这组，评委就会 401 / Missing credentials → 判不了分 → reward 缺失。
#
# 密钥来源：jobs/_resume_qwen.sh（明文，jobs/ 已被 git 忽略）
set -u

_KEYS_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_resume_qwen.sh"

if [ -z "${ARK_API_KEY:-}" ] && [ -f "$_KEYS_FILE" ]; then
  eval "$(grep -m1 '^export OPENAI_API_KEY=' "$_KEYS_FILE")" 2>/dev/null || true
  ARK_API_KEY="${OPENAI_API_KEY:-}"
fi
[ -n "${ARK_API_KEY:-}" ] || { echo "✗ 拿不到密钥（看 jobs/_resume_qwen.sh）"; return 2 2>/dev/null || exit 2; }

# agent / 代理
export ARK_API_KEY
export ANTHROPIC_API_KEY="$ARK_API_KEY"
# ⚠️ 必须【强制覆盖】，不能写成 ${VAR:-默认}：
#    .bashrc 里为 Claude Code 配了 ANTHROPIC_BASE_URL=…/api/coding，
#    继承下来会让评委 401（官方成功运行用的是 /api/plan）。
export ANTHROPIC_BASE_URL="https://ark.cn-beijing.volces.com/api/plan"
# 评委：只走 Anthropic 通道（/api/plan）。
# ⚠️ 不要导出 OPENAI_* ：
#   1) 实测我们的 ark key 对 /api/v3 一律 401（那条路根本走不通）
#   2) judge 模板里 "try OpenAI" 是无条件执行的 —— 给了 key 只会多一条误导性的 401 日志
#   3) 评委真正的可靠性来自 anthropic 客户端的 max_retries（见 jobs/_patch_judge_retry.sh）
unset OPENAI_API_KEY OPENAI_BASE_URL 2>/dev/null || true
# 代理绑定（WSL2 容器健康检查）
export BENCHFLOW_HOST_LITELLM_BIND="0.0.0.0"

if [ "${1:-}" = "--check" ]; then
  echo "  ARK_API_KEY        : $([ -n "$ARK_API_KEY" ] && echo 有 || echo 无)"
  echo "  ANTHROPIC_API_KEY  : $([ -n "$ANTHROPIC_API_KEY" ] && echo 有 || echo 无)"
  echo "  ANTHROPIC_BASE_URL : ${ANTHROPIC_BASE_URL}"
  echo "  OPENAI_API_KEY     : ${OPENAI_API_KEY:-（故意不设——/api/v3 用不了）}"
  echo "  OPENAI_BASE_URL    : ${OPENAI_BASE_URL:-（故意不设）}"
fi
