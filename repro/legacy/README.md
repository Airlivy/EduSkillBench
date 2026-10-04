# 兼容入口归档

这些文件用于追溯此前的运行方式。当前推荐入口是仓库根目录的 `python3 -m repro`，见上一级 README。

| 原入口 | 当前对应方式 |
| --- | --- |
| `_run_batch.sh`、`_retry_failed.sh` | `python3 -m repro run` |
| `_autofix.sh` | `python3 -m repro run --rounds 2` |
| `_verify_judge.sh` | `python3 -m repro run --tag smoke-judge2 --models glm-5.3 --task-id lesson-builder__01` |
| `_smoke_force_skill.sh` | `run` 命令显式指定 `--skill-mode forced` 和题目 |
| `_guard.sh` | 主运行器自带进程管理与单实例锁 |
| `_env_ark.sh` | 在调用环境显式设置所需变量 |
| `_patch_*.sh`、`patch_framework.py` | 历史安装环境维护；新流程不需要 |
| `_backup.sh` | 本机专用历史备份脚本，含固定路径，不作为通用工具 |

兼容包装脚本已调整相对路径，可以从仓库根目录按归档位置调用。历史补丁和备份脚本只归档，没有在此次整理中执行。
