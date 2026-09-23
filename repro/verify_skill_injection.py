#!/usr/bin/env python3
"""verify_skill_injection.py -- 验证 with-skill 条件确实把技能写进了题面。

不跑模型、不花钱：直接用框架的任务生成函数产出题面，逐技能比对。

判据（三项必须同时成立）：
  1. 带技能题面【包含】该技能 SKILL.md 的正文
  2. 基线题面【不包含】任何技能正文
  3. 两者差异只有"追加"：带技能题面相比基线【缺少】的行数为 0

用法：python repro/verify_skill_injection.py [技能目录，默认全部 14 个单轮技能]
退出码非 0 表示有技能未通过（此时不要开始跑批）。
"""
import difflib
import glob
import pathlib
import shutil
import sys
import tempfile

# 定位 BenchFlow（uv tool 安装位置）
for _p in glob.glob(str(pathlib.Path.home() /
                       ".local/share/uv/tools/benchflow/lib/python*/site-packages")):
    sys.path.insert(0, _p)
try:
    from benchflow.skill_eval._core import (load_eval_dataset, generate_tasks,
                                            cleanup_tasks)
except ImportError:
    sys.exit("找不到 benchflow 包 —— 请先安装 BenchFlow 并确认 uv tools 路径")


def render(skill_dir, with_skill):
    ds = load_eval_dataset(skill_dir)
    out = pathlib.Path(tempfile.mkdtemp(prefix="vsi_"))
    dirs = generate_tasks(ds, out, with_skill=with_skill, output_format="task-md")
    text = (dirs[0] / "task.md").read_text(encoding="utf-8")
    cleanup_tasks(dirs)
    shutil.rmtree(out, ignore_errors=True)
    return text


def check(skill_dir):
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return False, "缺少 SKILL.md"
    skill_text = md.read_text(encoding="utf-8")
    # 取技能正文里一句足够独特的话做指纹
    probe = next((l.strip() for l in skill_text.splitlines()
                  if len(l.strip()) > 40 and not l.startswith(("#", "|", "-"))), "")
    if not probe:
        return False, "SKILL.md 找不到可用作指纹的正文句"

    base = render(skill_dir, False)
    withsk = render(skill_dir, True)

    if probe[:60] not in withsk:
        return False, "带技能题面里找不到技能正文"
    if probe[:60] in base:
        return False, "⚠ 基线题面里也出现了技能正文（泄漏！）"
    added = [l for l in difflib.unified_diff(base.splitlines(), withsk.splitlines(),
                                             lineterm="", n=0)
             if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in difflib.unified_diff(base.splitlines(), withsk.splitlines(),
                                               lineterm="", n=0)
               if l.startswith("-") and not l.startswith("---")]
    if removed:
        return False, f"基线内容被改动（带技能题面少了 {len(removed)} 行）"
    return True, f"基线 {len(base):,} 字符 → 带技能 {len(withsk):,} 字符（追加 {len(added)} 行）"


def main():
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
        pathlib.Path(__file__).resolve().parent.parent / "skills" / "single_turn"
    skills = sorted(d for d in root.iterdir() if d.is_dir())
    print(f"检查 {len(skills)} 个技能（{root}）\n")
    bad = []
    for sk in skills:
        ok, msg = check(sk)
        print(f"  {'✅' if ok else '❌'} {sk.name:42s} {msg}")
        if not ok:
            bad.append(sk.name)
    print()
    if bad:
        print(f"❌ 未通过：{bad}\n   修好之前不要开始跑批。")
        return 1
    print("✅ 全部通过：with-skill 一定带技能正文，基线不含技能，且基线内容未被改动。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
