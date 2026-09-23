#!/usr/bin/env bash
# _patch_force_skill.sh -- 让 with-skill 条件【强制】带上技能说明。
#
# 为什么改：框架原本把技能挂进容器目录，由 agent 自己"发现并加载"。
#   实测 438/438 都主动加载了，但这是模型行为、不是协议保证 —— 别人复现时
#   换个模型/换个技能描述就可能不加载，with-skill 那组就退化成 baseline，
#   对比随即失真。强制注入后，"有没有技能说明"成为两条件的唯一差异。
#
# 改法：benchflow/skill_eval/_core.py 里生成任务题面的那一行：
#     instruction = case.question + "\n"
#   → with_skill 时追加 SKILL.md 全文（基线条件完全不改）。
#
# 可逆：bash jobs/_patch_force_skill.sh restore
set -u
CORE=$(ls -d ~/.local/share/uv/tools/benchflow/lib/python*/site-packages/benchflow | head -1)
F="$CORE/skill_eval/_core.py"
MODE="${1:-apply}"

python3 - "$F" "$MODE" <<'PY'
import pathlib, sys
f, mode = pathlib.Path(sys.argv[1]), sys.argv[2]
s = f.read_text()
MARK = "# BENCHFLOW-FORCE-SKILL"
OLD = '        instruction = case.question + "\\n"\n'
NEW = (
    '        instruction = case.question + "\\n"\n'
    '        ' + MARK + ': 强制把技能说明写进题面（仅 with-skill）\n'
    '        if with_skill:\n'
    '            _skill_md = dataset.skill_dir / "SKILL.md"\n'
    '            if _skill_md.is_file():\n'
    '                instruction = (instruction\n'
    '                    + "\\n\\n---\\n\\n## Required procedure\\n"\n'
    '                    + "Follow the procedure below when completing the task.\\n\\n"\n'
    '                    + _skill_md.read_text(encoding="utf-8"))\n'
)
if mode == "restore":
    if MARK in s:
        f.write_text(s.replace(NEW, OLD)); print("已还原（不再强制注入技能）")
    else:
        print("没有打过补丁，无需还原")
else:
    if MARK in s:
        print("补丁已存在")
    elif OLD in s:
        f.write_text(s.replace(OLD, NEW, 1)); print("✅ 已启用【强制注入技能】")
    else:
        print("✗ 找不到目标行，未改动"); sys.exit(1)
PY

echo
echo "=== 改动后的那段 ==="
grep -n -A9 "BENCHFLOW-FORCE-SKILL" "$F" | cut -c1-120
echo
echo "=== 语法与导入检查 ==="
python3 -c "
import ast; ast.parse(open('$F',encoding='utf-8').read()); print('  ✓ 语法正确')
import sys; sys.path.insert(0, '$CORE'.rsplit('/benchflow',1)[0])
import benchflow.skill_eval._core as m; print('  ✓ 模块可导入')
"
