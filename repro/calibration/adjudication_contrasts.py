"""Counterexamples for 2026-10-02 adjudications; never benchmark gold answers."""
import argparse,json,os
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from repro import judge
from repro.credentials import load_env_file
from repro.source_protocol import load_release,digest,allowed_labels
from repro.source_runner import evaluate_native

FIXTURES=[
('cn01_06',['D3'],'先保留学生已掌握的循环流程图，不急着换成抽象符号。第一步在原图加一个可观察的判断条件，第二步加入一条分支，第三步比较两个生活情境下的执行路径。每次只增加一处结构，让学生用手指追踪并说出下一步；能解释就继续，出错就回到前一张图核对。全程使用已有纸卡或PPT即可，图形与变量含义保持一致。这是一条增加结构复杂度的路线，不必强制从实物转向符号。','不用观察学生理解，直接把最复杂的代码和全部符号塞给学生背下来，不分步骤也不提供支架。'),
('cn01_07',['D1'],'邮箱类比只能帮助理解给变量命名和保存当前值，不能把现实邮箱的所有性质搬进程序。可用一排有编号的格子表示数组，说明索引与元素的对应，并展示读写一个元素的例子；这仍是示意，实际语言中的元素类型、索引起点等要按所教语言说明。若学生把变量与容器物理大小混同，就对照简单程序检查类比不适用之处并修正。采用纸格与卡片，控制一次出现的元素数，检查学生能否解释每个格子与程序对象的关系。不承诺一个类比永远不会失效。','邮箱现实中能装很多封信，所以所有编程语言中的单个变量都天然是无限数组，任何现实邮箱性质都可以直接套到程序上。'),
('cn01_10',['D4'],'用纸卡画一个数n的递归求和过程：S(1)=1，n大于1时S(n)=n+S(n-1)。从S(3)开始，先画需要S(2)、再需要S(1)的三张卡，随后按1、3、6回传结果，用颜色区分调用与返回。先说明终止条件，防止学生以为不停自我调用。展示后请学生补画S(4)缺的一张卡，并解释何时停止、怎样返回；若混淆就缩回S(2)。只用板书或纸卡，六年级学生逐步追踪，不必同时加入复杂代码。这构成同一套表征的呈现、使用和检查。','递归很重要，可以画点好看的图，教师自己想怎么用就怎么用。'),
('cn02_09',['D3','D4'],'先确定本课希望学生观察什么，核对已有视频的相关画面与事实，未看到视频前不能断言具体内容。以对称轴导入为例，可在提出“怎样判断两边对应”后播放约一分钟的相关片段，在关键画面停顿，让学生指出对应部位，再用纸图折叠验证，转入概念讨论。时长按片段信息量和低段学生注意情况调整，不整段放完才提问。备课只需标注播放起止点、两处停顿和两道问题，用现有播放器即可；保存静帧作为备用，不要求重新生成或精剪视频。','我没看过视频但可以保证每一帧都正确；直接整节课循环播放即可，不用提问，也不用与学习目标联系。'),
('cn18_06',['D3'],'先让学生说清融合任务中用到的数学关系和信息技术方法，区分概念本身与软件按钮。再给一题不使用原软件的数学解释题，以及一个换数据或工具的信息技术任务，让学生指出共同结构和需要调整之处。提供一次带提示的比较，再独立做新情境题，依据解释和操作证据检查迁移；若只会照搬按钮就补练相关原理。分别记录两学科目标是否达成，不能承诺融合课一定提高考试成绩。本回答只设计迁移环节，不重复整课导入。','融合过一次就能自动迁移到所有学科考试，不需要新情境练习或检查，只要相信学生就行。'),
('cn30_06',['D2'],'先让学生比较从n个不同元素选k个与选出其余n-k个，二者一一对应，得到C(n,k)=C(n,n-k)，其中n为非负整数且0≤k≤n。解释递推时固定一个元素，将k元子集分成包含和不包含该元素两类，分别有C(n-1,k-1)和C(n-1,k)种，互斥且穷尽，所以两数相加为C(n,k)。先在n≥1且1≤k≤n-1内说明，边界C(n,0)=C(n,n)=1；若把越界系数约定为0，也可统一写边界递推。用帕斯卡三角形对应两上邻项，检查学生能否解释C(4,2)=3+3及对称两端，而不是只背公式。','二项式系数递推关系是C(n,k)=C(n-1,k-1)乘C(n-1,k)，所以C(4,2)=3乘3=9，先让学生记住这个正确公式。'),
('cn31_01',['D5'],'先明确球相同、盒有编号，并区分是否允许空盒。5个相同球分到3个非空盒，把球排一行，在4个间隙选2个位置放隔板；追问为什么每种隔板位置恰对应一个分配、为什么不会重复遗漏，所以共有C(4,2)=6种。若允许空盒，可把5个球和2个隔板的排列对应到非负整数解，共C(7,2)=21种；让学生解释相邻隔板、两端隔板的含义。再改为球有编号作对比，不能继续直接套相同球隔板法。本题直接按组合对应计数，不必额外构造相加或相乘步骤。','隔板法永远只能套同一个公式，不用区分空盒或编号，也不用解释每一步的含义。'),
('cn51_03',['D3'],'保留已有标准，选两份匿名样例让学生先找表现证据再评等级，全班比较“达到标准”的证据是什么。自评时要求在原标准旁标出一处作品或过程记录，并写一条尚需改进之处；教师抽样复核，对没有证据的满分提出具体追问，允许学生订正评分。反馈只针对证据和下一步，不公开排名或强制所有人降分。若原标准含糊，再一起澄清那一条，不必重建三到五条新标准或整套表格。','只要自信就全给自己满分，不用看证据，也不用教师核对，这就是有效自评。'),
('cn51_06',['D4'],'保留教师已经说明的核心标准，给基础弱学生设置在同一目标上的小步表现与适当表达支持，例如先独立记录一次观察，再补充解释。评价同时记录个人前后进步和下一步目标，不把学生长期固定在低组，不公开排名。反馈指出具体独立完成的一步，并提供重做机会；学生可以选择口述、图示等适合的证据方式，核心科学要求不随意降低。不要求重新召开师生共同制定标准会议，也能让每个学生参与并看见有依据的进步。','继续公开排名，把基础弱的学生固定当旁观者，告诉他们反正做不好，没必要参与评价。'),
('cn52_02',['D1'],'先用学生熟悉且能观察的小问题进入，例如怎样让纸桥承受更多相同的小物件。让学生说预测和理由，教师示范如何记一次观察，再由小组尝试一个变化并比较结果，明确一次只改一个条件。把设计、测试、记录和修改拆成小步，用现有纸张和安全轻物，分配轮换机会；提问帮助学生从“做一个作品”转向“用证据改进解释”。先完成一轮简短探究，再逐步放手，不强求刚接触项目的学生一次完成大项目或背核心素养表。','所谓探究就是让学生抄一份现成结论，作品漂亮就算完成，不需要问题、证据或学生思考。'),
('cn52_04',['D5'],'45人分成10个4人组和1个5人组。先把本次任务拆为观察或测试、记录、材料管理和汇报等实际工作，5人组可把测试与检查分开，不能让第五人只旁观。角色按任务需要轮换，保证每人都有动手和表达机会，不固定给能力弱的学生低参与角色；教师在中途用个人记录或短问答核查参与，发现一人包办就调整步骤和支架。使用当前已有活动，不另设计材料采购清单；注意共享工具的使用顺序与安全。','把45个人分成11个4人组就正好，不用管剩下的人，弱的学生只看着即可。'),
('cn57_03',['D3'],'先不点名提醒全组暂停并执行轮换规则，让其他同学也获得操作机会；课间私下问该学生担心什么，肯定愿意参与，同时明确不能独占。请他练习把材料交给下一位并做必要协助，约定轮换节点，教师观察落实并给予具体反馈。若协商暂时无效，教师公平暂定角色，后续再调整。全程不当众点名批评、不羞辱，也不放任其他学生持续被排斥。','当着全班点名批评该学生，把他叫到讲台前训斥，告诉大家他自私，然后继续让他独占操作。'),
('cn60_04',['D1'],'立即用清晰的停手信号，让学生将材料放桌面、手离开材料，先制止抛掷并检查是否有人受伤或物品破损，危险物由教师处理。确认全班停下后，用短句示范安全拿放，请学生复述并练一次；说明收到开始信号才操作，按需要分批恢复。对仍难以停手的学生靠近提醒或暂收材料后指导，不羞辱、不体罚。材料准备已经完成，本次先解决眼前失控，再恢复实验说明。','学生互相扔材料时不用管，继续发更多材料和大声讲知识，等他们累了自然停下来。'),
('cn63_08',['D3'],'在评分表中增加两项必填字段：①支持本项评分的实际表现：写明视频时间点、学生实际动作及对应评价标准；②核对结果：写明实测数据或检查记录，以及它达到或未达到该标准的哪一条件。不得只填“很好”“满分”，缺少可核对事实时退回补填。','新增两个必填字段：我和这个同学关系好不好；我愿意给他多少人情分。')]


def one(case,targets,variant,answer,out):
    dest=Path(out)/case['task_id']/variant
    try:
        result=evaluate_native(case,answer,'deepseek-v4-pro',dest)
        ranks={i['id']:allowed_labels(next(r for r in case['criteria'] if r['id']==i['id'])).index(i['level']) for i in result['items']}
        last={r['id']:len(allowed_labels(r))-1 for r in case['criteria'] if r['id'] in ranks}
        passed=all(ranks[d]==0 for d in targets) if variant=='correct' else (any(ranks[d]==last[d] for d in targets) if variant=='wrong' else all(ranks[d]==last[d] for d in ranks))
        result=dict(task_id=case['task_id'],variant=variant,targets=targets,status='evaluated',passed=passed,ranks=ranks)
    except judge.JudgeError as exc:
        result=dict(task_id=case['task_id'],variant=variant,targets=targets,status='failed',passed=False,category=exc.category)
    judge.atomic_json(dest/'check.json',result);return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);ap.add_argument('--task-id');ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    _,cases,manifest=load_release();jobs=[]
    for suffix,targets,good,bad in FIXTURES:
        case=next(c for c in cases if c['task_id'].endswith('__'+suffix))
        if a.task_id and case['task_id']!=a.task_id:continue
        for variant,answer in [('correct',good),('wrong',bad),('off_topic','今天做番茄炒蛋，先洗番茄，再打鸡蛋，下锅炒熟。')]:jobs.append((case,targets,variant,answer))
    a.out.mkdir(parents=True,exist_ok=True);plan=dict(manifest=digest(manifest),jobs=digest(jobs),expected=len(jobs))
    if (a.out/'plan.json').exists() and json.loads((a.out/'plan.json').read_text())!=plan:raise ValueError('Changed plan')
    judge.atomic_json(a.out/'plan.json',plan);judge.atomic_json(a.out/'fixtures.json',jobs)
    if not a.execute:return
    load_env_file('/home/airlivy/.bashrc');os.environ['ANTHROPIC_BASE_URL']='https://ark.cn-beijing.volces.com/api/plan/v1'
    results=[]
    with ProcessPoolExecutor(max_workers=16) as pool:
        for f in as_completed([pool.submit(one,*j,a.out) for j in jobs]):
            r=f.result();results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
            judge.atomic_json(a.out/'summary.json',dict(expected=len(jobs),finished=len(results),passed=sum(r['passed'] for r in results),results=results,scope='14 modified cases; targeted criteria of reasonable answers must be highest, wrong answers must fail at least one targeted criterion, off-topic must fail all. Not 305-case expert certification.'))
    if not all(r['passed'] for r in results):raise SystemExit(1)

if __name__=='__main__':main()
