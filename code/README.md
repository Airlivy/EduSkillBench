# 数据构建与历史程序

`generation/` 和 `evaluation/build_evals*.py` 用于数据构建。当前题库已经存在，正常评测不需要重新生成。

当前五模型的运行、检查、评分和汇总统一使用仓库根目录的 `python3 -m repro`。

当前题库修订也通过这一入口：`data-build` 重建 v4 候选，`data-check` 检查完整性及已知问题，`data-report` 更新汇报。当前版本见 `data/revisions/index.json`。`revise_cases_20260930.py` 和 `revise_cases_v3.py` 是可追溯的早期构建步骤；当前 v4 从冻结的 v3 数据继续修订，不应反复覆盖已经评分的旧输入。

历史实验运行与汇总脚本移到 `legacy/evaluation/`，历史安装环境补丁移到 `legacy/utils/`。它们保留用于追溯，不是当前推荐入口；从仓库根目录执行时仍使用原有数据路径。整理时未执行这些历史脚本。
