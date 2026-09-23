#!/usr/bin/env bash
# _patch_judge_truncation.sh -- 让评委不再"截掉交付物"。
#
# 问题：模板原本只保留轨迹【前 50,000 字符】：
#     MAX_TRAJECTORY_CHARS = 50_000
#     text = text[:MAX_TRAJECTORY_CHARS] + "[TRUNCATED ...]"
#   而带技能的运行常把交付物【写进文件】（工具调用的后半段）→ 被截掉 → 评委看不到 → 误判低分。
#   这既是"掉点"的来源之一，也让别人复现不出同样的分数。
#
# 修法：改为【头 + 尾】都保留（任务在头部、最终交付物在尾部），并把上限提到 200,000 字符。
#
# 可逆：bash jobs/_patch_judge_truncation.sh restore
set -u
CORE=$(ls -d ~/.local/share/uv/tools/benchflow/lib/python*/site-packages/benchflow | head -1)
J="$CORE/templates/judge.py.tmpl"
MODE="${1:-apply}"

python3 - "$J" "$MODE" <<'PY'
import pathlib, re, sys
p, mode = pathlib.Path(sys.argv[1]), sys.argv[2]
s = p.read_text()

MARK = "BENCHFLOW-KEEP-TAIL"
if mode == "restore":
    if MARK in s:
        # 还原成原始的"只保留头部"
        s = re.sub(r"MAX_TRAJECTORY_CHARS = 200_000.*?\n", "MAX_TRAJECTORY_CHARS = 50_000  # truncate to avoid exceeding context window\n", s, count=1, flags=re.S)
        s = re.sub(r"    # " + MARK + r".*?(?=\n\S|\Z)", "", s, count=1, flags=re.S)
        p.write_text(s); print("已还原为原版截断")
    else:
        print("没有打过补丁，无需还原")
else:
    if MARK in s:
        print("补丁已存在")
    else:
        # 1) 提高上限
        s = s.replace("MAX_TRAJECTORY_CHARS = 50_000  # truncate to avoid exceeding context window",
                      "MAX_TRAJECTORY_CHARS = 200_000\n# " + MARK + ": 头尾都保留，避免把写在文件里的交付物截掉\n"
                      "KEEP_HEAD = 120_000\nKEEP_TAIL = 80_000")
        # 2) 改截断策略：头 + 尾
        old = re.search(r"if len\(text\) > MAX_TRAJECTORY_CHARS:\n(\s*)text = text\[:MAX_TRAJECTORY_CHARS\][^\n]*\n", s)
        if not old:
            print("✗ 找不到原始截断语句，未改动"); sys.exit(1)
        indent = old.group(1)
        new_block = (
            f"if len(text) > MAX_TRAJECTORY_CHARS:\n"
            f"{indent}# {MARK}: 保留开头（任务）与结尾（最终交付物/文件写入），中间省略\n"
            f"{indent}_total = len(text)\n"
            f"{indent}text = (text[:KEEP_HEAD]\n"
            f"{indent}        + f\"\\n\\n[...中间省略 {{_total - KEEP_HEAD - KEEP_TAIL}} 字符...]\\n\\n\"\n"
            f"{indent}        + text[-KEEP_TAIL:])\n"
        )
        s = s[:old.start()] + new_block + s[old.end():]
        p.write_text(s); print("✅ 已改为【头+尾保留】，上限 200,000 字符")
PY

echo
echo "=== 当前截断设置 ==="
grep -n -A6 "MAX_TRAJECTORY_CHARS" "$J" | head -14 | cut -c1-120
echo
echo "=== 语法检查 ==="
python3 -c "import ast,sys; ast.parse(open('$J',encoding='utf-8').read()); print('  ✓ 语法正确')"
