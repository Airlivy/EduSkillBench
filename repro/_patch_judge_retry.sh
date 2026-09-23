#!/usr/bin/env bash
# _patch_judge_retry.sh -- 给评委的 Anthropic 调用加官方重试（一行改动）。
#
# 背景（本次排查结论）：
#   评委有两条通道：① Anthropic(/api/plan) ② OpenAI(/api/v3) 回退。
#   实测 ② 用我们的密钥永远 401（形同虚设），① 长请求偶发 Connection error。
#   于是任何一次抖动 = 丢一整格分数 → 每批 10~30% 缺口。
#   修法：让 anthropic SDK 自己重试（官方机制，不做源码手术）。
#
# 可逆：bash jobs/_patch_judge_retry.sh restore
set -u
CORE=$(ls -d ~/.local/share/uv/tools/benchflow/lib/python*/site-packages/benchflow | head -1)
J="$CORE/templates/judge.py.tmpl"
MODE="${1:-apply}"
RETRIES="${2:-5}"

python3 - "$J" "$MODE" "$RETRIES" <<'PY'
import pathlib, re, sys
p, mode, n = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
s = p.read_text()
OLD = "client = anthropic.Anthropic()"
NEW = f"client = anthropic.Anthropic(max_retries={n})"
if mode == "restore":
    if NEW in s:
        p.write_text(s.replace(NEW, OLD)); print("已还原（去掉 max_retries）")
    else:
        print("当前没有 max_retries，无需还原")
else:
    if NEW in s:
        print(f"已存在 max_retries={n}")
    elif OLD in s:
        p.write_text(s.replace(OLD, NEW, 1))
        print(f"✅ 已加 max_retries={n}（连接错误自动重试 {n} 次）")
    else:
        print("✗ 找不到 client = anthropic.Anthropic()，未改动"); sys.exit(1)
PY

echo
echo "当前该行："
grep -n "anthropic.Anthropic(" "$J" | cut -c1-120
echo
echo "语法检查（确保模板没被改坏）："
python3 -c "
import ast, sys
src = open('$J', encoding='utf-8').read()
try:
    ast.parse(src); print('  ✓ 语法正确')
except SyntaxError as e:
    print(f'  ✗ 语法错误: {e}'); sys.exit(1)
"
