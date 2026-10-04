"""Contrast checks for content-alignment repairs; not benchmark gold answers."""
import argparse,json,os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from repro.credentials import load_env_file
from repro.source_protocol import load_release,allowed_labels,digest
from repro.source_runner import evaluate_native
from repro import judge

PAIRS=[
('cn60_03','先请学生记录气泡很少这一真实现象，说明保存不当只是猜测，还不能断定小苏打失效。暂停盲目加料，核查材料标签、用量和操作；若有已知可用的食品级材料，由教师在敞口小容器中少量对照，一次只改变一个条件，避免入口、入眼和密闭产气。没有合适条件就保留记录与问题，采用可靠现象资料继续讨论，课后试做核查后再反馈，不编造成功现象。语言按小学学生调整，让学生用画图或简短记录参与。','直接告诉学生肯定是他们笨，把全部材料倒进密闭瓶子使劲摇，直到爆开。无需核查，也不用解释。'),
('cn60_09','提前发一份按本次实验目标筛选的可带清单，只选学生年龄适合、便宜常见的低风险材料，注明数量和收集方式；未知化学品、刀具、易燃物和破损玻璃不让学生自带。课前统计缺项，学校备少量公共材料或安排合理共享，不让家庭负担决定能否参与。到校由教师先查验再入组，不合格物品隔离并交成年人处理；明确搬运、使用及归还规则，分组轮换操作。具体清单由教师依实验内容确定，不把未经核查的材料直接交给学生。','让学生随便带危险材料，谁没有就整节课站旁边看。到校直接开做，不检查，也不安排共享。'),
('cn02_04','以对称轴导入为例：课前保存离线截图和一张可折叠的对称图形纸。视频无法播放时停止反复调试，用纸图折叠让学生观察两边是否重合，并提出原来的对称轴问题。离线截图仅在屏幕可用时采用；连屏幕也坏了就用纸图或板书。材料使用已有资源，几分钟即可备好，不临时重新生成视频。练习一次切换话术，把注意力转回数学观察与讨论，课后再处理技术故障。','故障时让全班一直等网络恢复，没有视频就不上课。只要视频画面漂亮就足够，知识点和备用方案不用考虑。'),
('cn18_05','先把两个学科目标分别写成可观察表现，例如数学看能否识别和解释对称，信息技术看能否选择、整理并恰当呈现相关信息。同一作品分别记录两种学习证据，不把动画漂亮当数学理解。按本单元主目标和实际任务贡献商定权重，例如本次数学目标较重可占60%、信息技术占40%，提前解释依据；另一个单元可以不同，不机械要求各一半。结合简短口头解释和过程记录核对个人学习成果，检查某一维是否只奖励设备熟练度，并据试评修正。','数学老师是主科老师，所以无论学什么全部按数学卷面分计分，信息技术目标和学习表现完全不用评价。'),
('cn35_06','先召集科任教师，各自带来近期作业样本、完成时间和课堂观察，向学生了解哪些环节困难，将能力、方法、负担和情绪视为待核对假设。共同选一个可完成的小目标，分解成少量任务，协调每天作业总量，允许合适的表达方式。教师使用一致的具体反馈：指出已独立完成的一步，再提示下一小步，不比较排名或贴懒惰标签。明确各科负责人、记录方式和每周复盘时间，按完成情况调整支持，逐步培养时间安排与检查策略。安排一位教师与家长沟通，让家长提醒和倾听而不包办、不批评；同伴或家庭支持不足时，校内支持照常提供。不凭一次成功断言根源已查清。','让每科老师互不沟通、各自增加作业。公开说他懒，要求家长全部代写，这样就不用协调了。'),
('cn43_02','先列出种植和小制作中会用到的工具、材料和场地，检查尖锐边缘、有毒不明植物、过敏源及绊倒风险。按年龄和能力选低风险任务，尖锐切割可改为预裁材料或由教师处理；危险步骤不因培养动手能力而交给学生独立做。活动前示范握持、传递、收纳规则，让学生练习停手并报告异常，明确教师监督位置和求助方式。活动中观察操作、及时暂停危险动作；出现破损材料先隔离，由成人处理，学生不要徒手捡碎片。活动后清点收纳、清洁双手，让学生说出发现的风险与下次的预防办法，把安全意识落实到行为。','劳动课只要让孩子动手就好，把尖刀和碎玻璃随便发下去，不需要检查材料、说明规则或教师监督，受伤也不要停。'),
('cn62_06','可设置三个连续的学习支持动作：第一步重看自己的选择，对照解析或提示指出一个具体错因，必要时请求帮助；第二步让学生重新作答并写出关键依据，系统保存修改前后及解释，不能仅靠点击“已读”通过；第三步给一道同目标的小变式再检验，比较依据是否迁移，仍不会就暂停续推并转为提示或教师支持。系统核查回答内容、订正结果和迁移表现，不能保证强制点击就代表掌握。','只要强制点击三次“我已阅读”就判定真正掌握，不用重做、解释或再检验。'),
('cn63_10','我理解您担心考试和活动安全。实操任务可以让学生运用知识、操作并核对证据，书面练习则帮助整理概念、计算和适应考试，两者都不能一概取消。我们会按课程目标和具体考试要求列出对应内容，安排必要的书面练习及检测，把项目中出现的薄弱点带回课堂复习，并反馈学生表现。视频不是目的，不能只看作品热闹。您提到的掀井盖涉及安全风险，我们会先核查并停止未经批准或缺乏专业保障的活动，采用安全模拟或合规材料；不会用项目价值为危险做法辩护。','所有实操作业都比书面练习高级，所以全部取消试卷，不需要考虑考试。让学生独自去掀井盖，越危险越能练能力。'),
('cn52_10','采用一张纸上的三项观察：提出或理解本组问题、用记录或测试支持判断、根据反馈改进。开始时让学生知道标准；活动中教师轮流观察少数组的关键证据，学生保存草图或简短记录；中途用两分钟自查或同伴指出一条有证据的建议，教师给一个可行动的反馈；结束比较修改前后，不只看作品漂亮。用日期、观察到的行为、下一步三栏记录即可，抽样轮换避免每次全员长评。依据学生水平提供画图、口述或简短书写等记录方式，不排名、不贴标签。方案只需现有纸笔和课堂观察，不另购项目材料，不把未观察到的成长写成事实。','只在最后按作品漂亮程度排名，不看过程、不记录证据，也不提供反馈或改进机会。'),
('cn56_08','先感谢学生说出想法，问“你是根据哪个现象这样判断的”，确认错误来自观察还是概念。例如学生把杯口白雾说成水蒸气，可明确澄清可见白雾是小液滴，水蒸气本身看不见，再让他对照可观察现象解释为什么出现小液滴。给一个与原说法不符的例子或简短提示，追问“这和刚才的解释一致吗、你想改哪一步”，最后让学生用自己的话修正。提示由少到多，不羞辱、不让全班嘲笑，也不只说“不对”；必要解释后仍留给学生判断和应用的机会。','学生答错就当众说他笨，要求死记老师的结论，不听原因、不核对证据也不再追问。')]


def one(case,variant,answer,out):
    dest=Path(out)/case['task_id']/variant
    try:
        v=evaluate_native(case,answer,'deepseek-v4-pro',dest)
        ranks=[];last=[]
        for item in v['items']:
            crit=next(r for r in case['criteria'] if r['id']==item['id']);levels=allowed_labels(crit)
            ranks.append(levels.index(item['level']));last.append(len(levels)-1)
        passed=(all(r<=1 for r in ranks) and any(r==0 for r in ranks)) if variant=='correct' else (any(r==l for r,l in zip(ranks,last)) if variant=='wrong' else all(r==l for r,l in zip(ranks,last)))
        result={'task_id':case['task_id'],'variant':variant,'status':'evaluated','passed':passed,'ranks':ranks}
    except judge.JudgeError as e:result={'task_id':case['task_id'],'variant':variant,'status':'failed','passed':False,'category':e.category}
    judge.atomic_json(dest/'check.json',result);return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--task-id',action='append');ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1'
    _,cases,manifest=load_release();a.out.mkdir(parents=True,exist_ok=True)
    jobs=[]
    for suffix,good,bad in PAIRS:
        c=next(c for c in cases if c['task_id'].endswith('__'+suffix))
        if a.task_id and c['task_id'] not in a.task_id:continue
        for variant,answer in [('correct',good),('wrong',bad),('off_topic','今天吃番茄炒蛋，先洗番茄再打鸡蛋，然后下锅炒。')]:jobs.append((c,variant,answer))
    plan={'manifest':digest(manifest),'jobs':digest(jobs),'expected':len(jobs)}
    if (a.out/'plan.json').exists() and json.loads((a.out/'plan.json').read_text())!=plan:raise ValueError('Changed calibration plan')
    judge.atomic_json(a.out/'plan.json',plan);judge.atomic_json(a.out/'fixtures.json',jobs)
    if not a.execute:return
    results=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(one,*j,a.out) for j in jobs]
        for f in as_completed(futures):
            r=f.result();results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
            judge.atomic_json(a.out/'summary.json',{'expected':len(jobs),'finished':len(results),'passed':sum(r['passed'] for r in results),'results':results,'scope':'Representative repaired cases, not all 305-case expert acceptance.'})
    if not all(r['passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
