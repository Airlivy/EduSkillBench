"""One public CLI for EduSkillBench. Paid actions require explicit --execute."""
import sys
from pathlib import Path

COMMANDS = {
    'source-run': ('source_runner.py', '运行305题原标准适配版；保存等级与证据，失败只补评分，不伪造统一总分'),
    'native-check': ('../code/evaluation/check_source_native.py', '核对305题原标准适配版的逐题范围、权重与运行文件'),
    'source-check': ('../code/evaluation/check_source263.py', '核对恢复的263题与原始文件、原文片段是否一致；不调用模型'),
    'release-check': ('../code/evaluation/check_run_ready.py', '核验可运行测试集、逐题记录和编译结果；不调用模型'),
    'data-check': ('../code/evaluation/check_dataset.py', '检查保留的 v4 修订候选；可运行交付使用 release-check'),
    'data-build': ('../code/evaluation/revise_cases_v4.py', '重建保留的 v4 修订候选；不修改可运行交付'),
    'data-report': ('../code/evaluation/report_content_review.py', '更新 v4 历史修订报告并指向最新交付说明'),
    'calibrate': ('calibrate_cases.py', '对修订题库做正确、错误及跑题回答的评分校准'),
    'check': ('check.py', '检查固定实验清单与有效成绩'),
    'run': ('runner.py', '运行新实验或恢复缺失任务；默认只显示计划'),
    'rejudge': ('rejudge.py', '对保存的回答统一补评分；支持断点恢复'),
    'summarize': ('summarize.py', '汇总原始运行及同协议补评分'),
    'review-summary': ('finalize_review.py', '汇总独立的统一补评分结果'),
    'prepare': ('prepare.py', '生成并检查隔离任务'),
    'verify': ('verify_tasks.py', '离线检查双条件题面与技能材料'),
    'snapshot': ('snapshot.py', '记录源码、输入与现有结果的版本对应关系'),
}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ('-h', '--help'):
        print('用法：python3 -m repro <命令> [参数]\n')
        for name, (_, description) in COMMANDS.items():
            print(f'  {name:16} {description}')
        print('\n各命令参数：python3 -m repro <命令> --help')
        return 0
    command = args.pop(0)
    if command not in COMMANDS:
        print(f'未知命令：{command}；使用 python3 -m repro --help', file=sys.stderr)
        return 2
    script = Path(__file__).resolve().parent/COMMANDS[command][0]
    # Same Python environment; forward return codes, arguments and signal handling.
    # exec avoids leaving a second parent process when the runner is interrupted.
    import os
    if command == 'calibrate':
        os.execv(sys.executable, [sys.executable, '-m', 'repro.calibrate_cases', *args])
    os.execv(sys.executable, [sys.executable, str(script), *args])


if __name__ == '__main__':
    raise SystemExit(main())
