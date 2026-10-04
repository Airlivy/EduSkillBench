"""Compile an explicit per-case grading scope with native source levels."""
import copy,csv,json,re,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from repro.source_protocol import dimensions,digest,VERSION
from content_fixes import apply as apply_content_fixes
BASE=ROOT/'data/releases/source-minimal-20261001';OUT=ROOT/'data/releases/source-native-20261001'
# Dimension numbers are positions in each source's active table, not invented scores.
SCOPES={
1:[[1,2,3,4],[1,2,3,4],[1,2,3],[1,2,3,4],[2,3,4],[1,2,3,4],[1,2,3,4],[2,3,4],[1,2,3,4],[1,2,3,4]],
2:[[1,3,4],[3,4],[1,2,4],[1,3,4],[1,3,4],[1,3,4],[1,3,4],[1,2,4],[1,3,4],[1,2,3,4]],
5:[[1,2,3],[1,2,3],[1,2,3,4],[1,3,4],[1,2,3],[1,2,3],[1,2,3],[1,3,4],[1,3,4],[1,2,3,4]],
7:[[1,2,3],[1,2,4],[1,2,4],[1,2,3,4],[1,2,3,4],[1,2,4],[1,2,4],[1,2,3,4],[2,4],[1,2,3,4]],
18:[[1,2,4],[1,2,3],[1,3,4],[2,3,4],[1,4],[1,2,3,4],[1,2,3],[1,2,4],[1,2,3,4],[1,2,3,4]],
21:[[1,3,4],[1,2,3,4],[2,3,4],[1,3,4],[1,2,3],[1,3,4],[1,2,3],[1,3,4],[1,2,3],[1,2,3,4]],
50:[[1,2,3,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,3,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,7],[1,2,3,4,5,6,7],[1,3,5,7],[1,2,3,5,6,7]],
51:[[1,2,3,4,5,6,7],[1,2,3,4,5,6,7],[1,3,5,6,7],[1,3,4,5,6,7],[1,5,6,7],[1,3,4,5,6,7],[1,3,5,7],[1,2,3,4,5,6,7],[1,3,5,6,7],[1,3,4,5,6,7]],
52:[[1,2,3,4,5,6,7],[1,3,4,5,7],[1,3,5,6],[1,3,5,7],[1,2,3,4,5,6,7],[1,3,4,5,6],[1,3,5,6,7],[1,3,4,6,7],[1,3,5,7],[1,3,6,7]],
53:[[1,2,3,4,5,6]]*10,
54:[[1,2,3,5,6],[1,2,3,5,6],[1,2,3,5,6],[1,2,3,5,6],[1,2,3,5,6],[1,2,3,5,6],[1,2,3,5,6],[1,2,3,4,5,6],[1,2,3,5,6],[1,2,3,5,6]],
55:[[1,3,4,5,6,7],[1,2,3,4,6,7],[1,2,3,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,3,4,6,7],[1,3,4,6,7],[1,3,4,5,6,7],[1,4,5,6,7],[1,2,3,4,5,6,7]],
56:[[1,2,3,4,5,6,7],[2,3,5,6,7],[1,2,3,5,6,7],[2,3,5,6,7],[1,3,4,5,6,7],[1,3,5,6,7],[1,2,3,5,6,7],[2,3,5,6,7],[1,2,3,5,6,7],[1,2,3,5,6,7]],
57:[[1,3,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,2,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,2,4,5,6,7],[1,2,3,4,5,6,7]],
59:[[1,2,3,4,5,6,7]]*10,
60:[[1,3,5,6,7],[1,4,5,6,7],[1,3,5,6,7],[1,4,5,6,7],[1,4,5,6,7],[1,3,5,6,7],[1,4,5,6,7],[1,3,4,5,6,7],[1,3,4,5,6,7],[1,2,4,5,6,7]],
62:[[2],[1],[3],[1,2,4],[4],[1],[2],[1,4],[1],[4]],
63:[[1],[2,3],[4],[3],[3],[2,3],[2,4],[3],[2,3],[2]]}
# Content audit: local evaluation/teacher-response questions do not require
# unrelated local-material design or an additional peer-discussion activity.
SCOPES[52][9]=[1,2,3,6,7]
SCOPES[52][3]=[1,5,7]
SCOPES[56][7]=[3,5,6,7]
SCOPES[56][9]=[1,3,5,6,7]
SCOPES[35]=[[1,2],[1,2],[1,2,3],[1,2],[1],[6]]


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    OUT.mkdir(parents=True,exist_ok=True);raw=json.loads((BASE/'cases.json').read_text());cases=[];changes=[]
    with (BASE/'core.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            cases.append({**row,'suite':'core','grading_mode':'legacy-binary','rubric':json.loads(row['rubric'])})
    for c in raw:
        record=c['source_record'];context='\n'.join(s['text'] for s in c['context_sections']);rubric='\n'.join(s['text'] for s in c['rubric_sections'])
        criteria=dimensions(rubric)
        # Scope is frozen before seeing any model answer; all retained weights are original.
        numbers=SCOPES[record][c['source_scene_index']-1] if record in SCOPES else list(range(1,len(criteria)+1))
        assert numbers and len(set(numbers))==len(numbers) and max(numbers)<=len(criteria),(c['task_id'],numbers)
        topic=c['user_prompt']
        scope='只评价本题所问的具体环节及其必要的准确性、可行性与安全要求；未选维度不计缺失，不临时增删维度。'
        if record==52 and c['source_scene_index']==10:scope+=' 本题只问过程性评价，不要求另行设计本土化项目或技能分层任务。'
        if record==52 and c['source_scene_index']==4:scope+=' 本题只问45人11组的分工，不要求另行设计材料清单或单人微任务。'
        if record==56 and c['source_scene_index'] in (8,10):scope+=' 本题允许教师针对学生回答进行有效回应，不强制另加生生互评活动。'
        if record==35 and c['source_scene_index']==6:scope+=' 本题评价科任教师协作方案，不另要求完整的个体成因诊断、情绪干预和学习策略课程。'
        edits=[]
        for r in criteria:
            for level in r['levels']:
                before=level['description'];after=before
                if '流程' in r['name'] or '闭环' in r['name']:
                    labels=['优秀','良好','合格','不合格']
                    replacements=['完整交代本题所问环节的必要步骤、衔接和反馈，具体可执行；不要求无关环节。','本题所问环节的必要步骤基本完整，少量实施细节不清。','回应本题主要环节，但遗漏一项重要步骤或衔接，需要补充才能使用。','未回应本题所问环节，或关键步骤缺失、逻辑断裂，无法实施。']
                    after=next(v for k,v in zip(labels,replacements) if level['label'].startswith(k))
                if record==57 and r['id']=='D3':
                    rank=next(i for i,k in enumerate(['优秀','良好','合格','不合格']) if level['label'].startswith(k))
                    after=['针对本题出现的矛盾提供具体可行的处理步骤，必要时及时介入，并保护学生尊严。','回应本题主要矛盾，处理方法基本可行，少量细节不足。','识别本题矛盾，但处理建议较笼统或存在可修正缺陷。','未回应本题矛盾，或建议羞辱、放任排挤及其他明显不当处理。'][rank]
                if record==57 and r['id']=='D5' and level['label'].startswith('优秀'):
                    after='结合任务需求、学生意愿与学习机会安排并轮换角色，保障每人参与；不按性格固定分配高低地位角色。'
                if record==57 and r['id']=='D6':
                    rank=next(i for i,k in enumerate(['优秀','良好','合格','不合格']) if level['label'].startswith(k))
                    after=['尊重学生，不羞辱、不贴标签；支持自主协商，必要时公平暂定角色或制止伤害，并说明后续调整。','基本尊重学生，介入方式总体合理，少量解释不充分。','干预方式存在可修正的不当表述或忽视学生意见。','明确建议羞辱、贴标签，或无视欺凌与安全风险。'][rank]
                if '学段' in r['name'] or '年级' in r['name']:
                    rank=next(i for i,k in enumerate(['优秀','良好','合格','不合格']) if level['label'].startswith(k))
                    after=['具体匹配本题所给年级和学生特点，表达与任务难度适当；未给年级时说明适用范围，不强制列出所有年级。','基本匹配本题学生特点，少量表述需要调整。','学生适配说明笼统，部分要求偏难或偏易，可修正。','与本题学生能力或年级明显不符，难以理解或参与。'][rank]
                if record==54:after=after.replace('标注课标具体条目','说明课标目标的对应关系；未提供版本与条文时不得编造编号').replace('未标注课标条目','对应关系说明不充分')
                if record==56:after=after.replace('明确标注教参参考条目','如引用教参则说明依据；未提供版本时不编造条目')
                if record==5:after=after.replace('能精准指出"投纸片"类逻辑断裂、伪信息化等核心问题，未遗漏关键缺陷','能依据本题材料识别活动与目标、学情之间的问题，未遗漏关键缺陷；不因活动使用纸卡而预判无效')
                if after!=before:
                    level['description']=after;edits.append({'dimension':r['id'],'level':level['label'],'before':before,'after':after})
        if record==62:
            old=context;context=context.replace('中职不存在家长投诉“作业过多过难”的升学焦虑环境。相反，中职面临的现实是：','本题讨论的情景是：').replace('对技能提升毫无价值','缺少与实际技能学习的有效联系')
            if old!=context:edits.append({'field':'context','before':old,'after':context})
        if record==5:
            old=context;context=context.replace('既不符合信息化教学要求，也不符合成人化教学场景','是否适合应结合教学目标、学情和具体活动判断，不能仅因采用纸质材料就判定无效')
            if old!=context:edits.append({'field':'context','before':old,'after':context})
        if c['task_id'] in ('differentiation-adapter__cn07_10','lesson-builder__cn18_10','lesson-builder__cn21_10','lesson-builder__cn01_09'):
            context+='\n材料边界：本题未附实际设计方案，回答应说明需要哪些材料并提供核对方法，不得假装已经审阅方案后给出确定结论。'
            edits.append({'field':'context','after':'明确本题没有附方案，不得虚构审阅结论。'})
        item={'task_id':c['task_id'],'suite':'advisory','grading_mode':VERSION,'source_record':record,'source_scene_index':c['source_scene_index'],
              'context':context,'user_prompt':topic,'criteria':criteria,'applicable_ids':[f'D{i}' for i in numbers],
              'scope_note':scope,'expected_output':'','original_source':c['source_file'],'source_sha256':c['source_sha256'],
              'parent_case_sha256':digest(c),'editorial_changes':edits}
        cases.append(item);changes.append({'task_id':c['task_id'],'question':topic,'applicable':[{'id':r['id'],'name':r['name'],'original_weight':r['weight']} for r in criteria if r['id'] in item['applicable_ids']],
          'excluded':[{'id':r['id'],'name':r['name']} for r in criteria if r['id'] not in item['applicable_ids']], 'reason':scope,'edits':edits})
    apply_content_fixes(cases)
    byid={c['task_id']:c for c in cases}
    for change in changes:
        revised=byid[change['task_id']]
        change['question']=revised['user_prompt'];change['edits']=revised['editorial_changes']
    write(OUT/'cases.json',cases);write(OUT/'scope_and_changes.json',changes)
    write(OUT/'release_gate.json',{'ready':True,'execution_command':'python3 -m repro source-run','protocol':VERSION,
      'score_policy':'保留原文等级和数值区间；没有原文等级转分时不生成单点总分。前42题保留原评分协议，二者不混算。',
      'full_expert_acceptance':False,
      'content_acceptance_status':'reviewed_with_corrections_not_expert_certified',
      'readiness_scope':'ready 表示数据和协议可执行，不代表全部语义已经专家验收。',
      'allowed_conditions':{'core':['baseline'],'advisory':['baseline'],'all':['baseline']}})
    txt=['EduSkillBench 305题：原标准适配运行版','前42题保留原评分；后263题固定适用维度并保留来源等级，不补造统一100分。','原始文件与旧版本保留供溯源；当前有效背景及评价标准以下列内容为准。','']
    previous=Path('/home/airlivy/EduSkillBench_305题合并审阅版_42题中文加263题原文_2026-10-01.txt').read_text(encoding='utf-8-sig')
    starts=list(re.finditer(r'^第 \d{3} / 305 题',previous,re.M));assert len(starts)==305
    for i,c in enumerate(cases,1):
        if i<=42:
            block=previous[starts[i-1].start():starts[i].start()].split('【第二部分：')[0]
            txt+=['='*72,re.sub(r'\n=+\s*\Z','\n',block).rstrip()]
            continue
        txt+=['='*72,f'第 {i:03d} / 305 题','题号：'+c['task_id'],'【题目】',c['user_prompt'],'【有效背景】',c['context']]
        if c['suite']=='core':txt+=['【原参考答案】',c['expected_output'],'【原评分标准】',json.dumps(c['rubric'],ensure_ascii=False,indent=2)]
        else:
            txt+=['【参考答案】','原文未给出本题专属标准答案，不补编。','【本题评分范围】',c['scope_note']]
            for r in c['criteria']:
                if r['id'] not in c['applicable_ids']:continue
                txt += [r['id']+' '+r['name']+'；原权重：'+str(r['weight'] if r['weight'] is not None else '未规定'),r['description']]
                txt += [l['label']+'：'+l['description'] for l in r['levels']]
            txt+=['【不作为本题必答要求的维度】', '、'.join(r['name'] for r in c['criteria'] if r['id'] not in c['applicable_ids']) or '无',
                  '【原文溯源】',c['original_source'],'原文案例、参考方案完整保留于 source-minimal-20261001 与 source-faithful-20261001，不作为本题标准答案。']
    (OUT/'305题运行审阅.txt').write_text('\n'.join(txt)+'\n',encoding='utf-8-sig')
    (OUT/'README.md').write_text('# 原标准适配运行版\n\n305题可用 `python3 -m repro source-run` 运行。答案独立保存、评分失败为待评分，不是0分；恢复时不重生成答案。\n\n263题保留原文等级、权重；只评事先固定的适用维度。有数值范围时给区间，无数值换算则保留等级，不伪造总分。42题沿用原协议，与263题分开汇总。不能将不同覆盖范围和协议混排成一个总榜。\n\n逐题适用范围和所有本轮更改见 `scope_and_changes.json`，人工审阅见 `305题运行审阅.txt`。原始文件保留在父版本中。\n')
    code=['repro/source_protocol.py','repro/source_runner.py','code/evaluation/build_source_native.py','repro/judge.py',
          'code/evaluation/content_fixes.py','code/evaluation/source_content_fixes_20261001.json',
          'code/evaluation/source_content_fixes_20261002.json']
    write(OUT/'manifest.json',{'protocol':VERSION,'parent_release':BASE.name,'parent_manifest_sha256':sha(BASE/'manifest.json'),
        'counts':{'core':42,'advisory':263,'all':305},'artifacts':{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'},
        'code':{name:sha(ROOT/name) for name in code if (ROOT/name).exists()},'skill_files':{}})
    print(json.dumps({'release':str(OUT),'cases':len(cases),'scoped':len(changes)},ensure_ascii=False))
if __name__=='__main__':build()
