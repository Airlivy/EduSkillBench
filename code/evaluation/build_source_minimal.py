"""Apply explicit, small source corrections; never synthesize new gold answers."""
import copy
import csv
import json
import re
import shutil
from pathlib import Path
from restore_source263 import ROOT, OUT as BASE, sha, dump, write_csv

OUT=ROOT/'data/releases/source-minimal-20261001'
SPEC=Path(__file__).with_name('source_minimal_patches_20261001.json')


def revised_cases():
    cases=json.loads((BASE/'cases.json').read_text())
    spec=json.loads(SPEC.read_text())
    changes=[]
    for rule in spec['replacement_rules']:
        selected=[c for c in cases if c['source_record']==rule.get('source_record') or c['task_id'] in rule.get('task_ids',[])]
        assert selected,rule['id']
        for c in selected:
            if rule['field']=='user_prompt':
                assert c['user_prompt'].count(rule['before'])==1,(rule['id'],c['task_id'])
                c['user_prompt']=c['user_prompt'].replace(rule['before'],rule['after'])
            else:
                selected_sections=[s for s in c['context_sections' if rule['field']=='context' else 'rubric_sections'] if rule['before'] in s['text']]
                assert len(selected_sections)==1,(rule['id'],c['task_id'])
                section=selected_sections[0]
                assert section['text'].count(rule['before'])==1,(rule['id'],c['task_id'])
                section.setdefault('original_text',section['text'])
                section['text']=section['text'].replace(rule['before'],rule['after'])
                section['edited']=True
            c.setdefault('editorial_change_ids',[]).append(rule['id'])
        changes.append({**rule,'affected_task_ids':[c['task_id'] for c in selected]})
    pick=spec['rubric_selection']
    selected=[c for c in cases if c['source_record']==pick['source_record']]
    for c in selected:
        original=c['rubric_sections']
        assert len(original)==2 and '对智能体融合设计的评价' in original[pick['keep_section_index']]['text']
        c['reference_only_rubric_sections']=[s for i,s in enumerate(original) if i!=pick['keep_section_index']]
        c['rubric_sections']=[original[pick['keep_section_index']]]
        c.setdefault('editorial_change_ids',[]).append('S01')
    changes.append({'id':'S01','field':'rubric_selection','reason':pick['reason'],
        'before':'过程性评价表、结果性评价表和对智能体输出的评价表同时放入评分字段。',
        'after':'评分字段仅保留原文“对智能体融合设计的评价”表；其余两套表保留为参考。',
        'affected_task_ids':[c['task_id'] for c in selected]})
    for rule in spec['topic_alignments']:
        selected=[c for c in cases if c['source_record']==rule['source_record']]
        for c in selected:
            c['reference_only_context_sections']=c['context_sections']
            c['reference_only_rubric_sections']=c['rubric_sections']
            c['context_sections']=[{'kind':'context','text':rule['context'],'edited':True}]
            c['rubric_sections']=[{'kind':'rubric','text':rule['rubric'],'edited':True}]
            c.setdefault('editorial_change_ids',[]).append(rule['id'])
        changes.append({**rule,'affected_task_ids':[c['task_id'] for c in selected]})
    for rule in spec.get('context_alignments',[]):
        selected=[c for c in cases if c['source_record']==rule['source_record']]
        before='\n'.join(s['text'] for s in selected[0]['context_sections'])
        for c in selected:
            c['reference_only_context_sections']=c['context_sections']
            c['context_sections']=[{'kind':'context','text':rule['after'],'edited':True}]
            c.setdefault('editorial_change_ids',[]).append(rule['id'])
        changes.append({**rule,'field':'context','before':before,'affected_task_ids':[c['task_id'] for c in selected]})
    for rule in spec.get('consultation_scopes',[]):
        c=next(c for c in cases if c['task_id']==rule['task_id'])
        original=c['rubric_sections']
        lines='\n'.join(s['text'] for s in original).splitlines()
        dims=[line for line in lines if line[:1] in '①②③④⑤⑥' and line.strip()]
        assert len(dims)==6
        retained=[dims[i-1] for i in rule['keep_dimension_numbers']]
        text='本题评价范围：只评价具体咨询所需的建议，不要求提交整套方案。以下保留原文中与本题直接相关的维度；不新增权重或等级转分规则。\n'+'\n'.join(retained)
        c['reference_only_rubric_sections']=original
        c['rubric_sections']=[{'kind':'rubric','text':text,'edited':True}]
        c.setdefault('editorial_change_ids',[]).append(rule['id'])
        changes.append({**rule,'field':'consultation_scope','before':'\n'.join(s['text'] for s in original),'after':text,'affected_task_ids':[c['task_id']]})
    return cases,changes,spec


def build():
    cases,changes,spec=revised_cases()
    shutil.copytree(BASE,OUT,dirs_exist_ok=True)
    with (BASE/'advisory.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    fields=list(rows[0])+['editorial_change_ids']
    for c,r in zip(cases,rows):
        r['user_prompt']=c['user_prompt']
        r['context']='\n'.join(s['text'] for s in c['context_sections'])
        r['rubric']='\n'.join(s['text'] for s in c['rubric_sections'])
        r['editorial_change_ids']=','.join(c.get('editorial_change_ids',[]))
    write_csv(OUT/'advisory.csv',rows,fields)
    with (BASE/'all.csv').open(encoding='utf-8-sig',newline='') as f:core=list(csv.DictReader(f))[:42]
    write_csv(OUT/'all.csv',[{**r,'editorial_change_ids':''} for r in core]+rows,fields)
    dump(OUT/'cases.json',cases);dump(OUT/'changes.json',changes)
    shutil.copyfile(SPEC,OUT/'patch_spec.json')
    dump(OUT/'release_gate.json',{'ready':False,'source_fidelity_verified':False,'originals_preserved':True,
        'reason':'263题已恢复原文并完成有限小修；原量规的自动评分适配和题目背景适用性尚未完成，不能套用旧改写评分规则。',
        'allowed_conditions':{'core':['baseline','with-skill'],'advisory':['baseline'],'all':['baseline']}})
    dump(OUT/'unresolved.json',{'examples':spec['unresolved_examples'],'remaining':['10份数学来源的71题已处理背景与量规适用关系；其余来源仍需复核细节，不能据此宣称全库内容无误。','原量规未给出的数字权重与等级转分规则仍未补造。','作业支持与劳动教育12题已限定咨询评分范围；其余带数字权重的共享量规仍需逐题适配，不能直接删项后沿用总分。','尚未完成真实模型评分校准。']})
    # The unchanged original text view remains clearly historical; export a new review view.
    txt=['EduSkillBench：263题有限小修审阅版','基于原文恢复版；仅修正明确不合理的短句与评分适用说明。改动可在 changes.json 或小修对照.txt 中逐项核对。',
         '原始文件及 source_documents.json 完整保留。原文件没有的逐题答案、权重和等级转分规则没有新增。',
         'Word公式与排版仍以 originals 原件为准。带“本轮小修”标记的栏目采用修订内容。','']
    for i,(c,r) in enumerate(zip(cases,rows),1):
        txt += ['='*72,f'第 {i:03d} / 263 题',f'题号：{c["task_id"]}',f'原文件：{c["source_file"]}',
            '本轮改动：'+(', '.join(c.get('editorial_change_ids',[])) or '无，保留恢复版内容'),
            '【题目】',r['user_prompt'],'【背景与核心问题】',r['context'],
            '【评价标准】',r['rubric'],'【原文解决方案（仅供来源参考，不作为本题标准答案）】',r['source_solution'],
            '【原文案例（仅供来源参考，不作为本题评分要求）】',r['source_examples'],'【原文依据】',r['source_references']]
        if c.get('reference_only_context_sections'):
            txt+=['【原文背景，仅供溯源，不作为本题条件】']+[s['text'] for s in c['reference_only_context_sections']]
        if c.get('reference_only_rubric_sections'):
            txt+=['【仅作原始参考的其他评价表，不与上表混算】']+[s['text'] for s in c['reference_only_rubric_sections']]
        txt+=['']
    (OUT/'263题小修审阅.txt').write_text('\n'.join(txt),encoding='utf-8-sig')
    note=['EduSkillBench：本轮小修对照','前42题未改。只改所列文字；共享量规同步应用到该来源下的题目。','']
    for c in changes:
        note += [c['id']+'｜'+c['reason'],f'影响 {len(c["affected_task_ids"])} 题：'+', '.join(c['affected_task_ids']),
            '修改前：'+c['before'],'修改后：'+c['after'],'']
    note+=['本轮未硬改的问题：']+[x['task_id']+'：'+x['reason'] for x in spec['unresolved_examples']]
    (OUT/'小修对照.txt').write_text('\n'.join(note)+'\n',encoding='utf-8-sig')
    changed={t for c in changes for t in c['affected_task_ids']}
    prompts={t for c in changes if c['field']=='user_prompt' for t in c['affected_task_ids']}
    (OUT/'README.md').write_text(f'''# 原文基础上的有限小修版

只在用户授权后实施清单中的小幅修订。前42题不变；后263题中涉及 {len(changed)} 题，其中实际题干改动 {len(prompts)} 题，其余影响来自共享评价表的定点修改。未改题仍使用原文恢复版内容。完整修改前后见 `小修对照.txt` 和 `changes.json`。

主要修正：不能保证的反AI/绝对公平要求、替代作业被强制降级、单题缺少“上述”所指对象、把实操一概判得高于书面作业、将真实教学效果当作方案文字得分证据、误罚科学澄清、材料组织方式一刀切。同文档多套量规时，选择原文明确标注“对智能体输出”的原表；其余表作为参考保存，不重复计分。

没有统一改写题目，没有新编标准答案，没有新增评分维度、数字权重、关键项或等级转分规则。数学主题适配保留原评价维度数量；12道局部咨询题选择相关原文维度。已有数字权重不变；异主题措辞作适用性修正。原文恢复包、原始文件、公式对象不变；这里不能再标为“一字不改原文版”。

已核对并修正全部10份数学来源下的71题背景、量规适用关系，同时修正作业支持与劳动教育12题的背景预设和局部咨询评分范围、小学科学支架教学的年级及必要示范限制；异主题案例完整归档为参考，不作为当前评分条件。其余尚待核对事项见 `unresolved.json`。自动评分仍未就绪；不能把文本修改验收当作题库完全无误或全量评分校准。
''')
    # Reuse the first 42 translated cases verbatim; only renumber the restored portion.
    previous=Path('/home/airlivy/EduSkillBench_305题合并审阅版_42题中文加263题原文_2026-10-01.txt').read_text(encoding='utf-8-sig')
    starts=list(re.finditer(r'^第 \d{3} / 305 题',previous,re.M));assert len(starts)==305
    blocks=[]
    for i in range(42):
        block=previous[starts[i].start():starts[i+1].start()]
        block=block.split('【第二部分：')[0]
        blocks.append(re.sub(r'\n=+\s*\Z','\n',block).rstrip())
    combined=['EduSkillBench：305题有限小修审阅版','第1—42题保留之前主集中文阅读版；第43—305题采用本轮原文基础上的有限小修版。','请结合“小修对照.txt”审阅。未补编逐题答案，Word公式排版以原文件为准。','']
    combined+=['='*72+'\n'+b for b in blocks]
    tail='\n'.join(txt);ss=list(re.finditer(r'^第 (\d{3}) / 263 题',tail,re.M));assert len(ss)==263
    for i,m in enumerate(ss):
        block=tail[m.start():ss[i+1].start() if i+1<len(ss) else len(tail)]
        block=re.sub(r'\n=+\s*\Z','\n',block)
        block=re.sub(r'^第 \d{3} / 263 题',f'第 {i+43:03d} / 305 题',block,count=1)
        combined.append('='*72+'\n'+block.rstrip())
    (OUT/'305题小修审阅.txt').write_text('\n\n'.join(combined)+'\n',encoding='utf-8-sig')
    dump(OUT/'manifest.json',{'release':OUT.name,'parent_release':BASE.name,'parent_manifest_sha256':sha(BASE/'manifest.json'),
        'counts':{'core':42,'advisory':263,'all':305,'changed_advisory_cases':len(changed),'changed_prompts':len(prompts)},
        'builder_sha256':sha(Path(__file__)), 'artifacts':{str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'},'skill_files':{}})
    print(json.dumps({'release':str(OUT),'changed_cases':len(changed),'changed_prompts':len(prompts),'changes':len(changes)},ensure_ascii=False))

if __name__=='__main__':build()
