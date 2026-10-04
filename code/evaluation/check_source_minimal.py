"""Verify the exact limited edit scope against the immutable source restoration."""
import csv
import json
import re
from pathlib import Path
from build_source_minimal import ROOT,BASE,OUT,revised_cases
from restore_source263 import sha
from check_source263 import check as check_original


def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def dimensions(text):
    result=[]
    for line in text.splitlines():
        if '%' not in line:continue
        cells=[s.strip().strip('*') for s in (line.strip('|').split('|') if line.startswith('|') else line.split('\t'))]
        weights=[s for s in cells if re.fullmatch(r'\d+(?:\.\d+)?%',s)]
        if weights:result.append((cells[0],weights))
    return result


def check():
    check_original()
    manifest=json.loads((OUT/'manifest.json').read_text())
    assert manifest['parent_manifest_sha256']==sha(BASE/'manifest.json')
    for name,digest in manifest['artifacts'].items():
        if sha(OUT/name)!=digest:raise ValueError('Changed revision artifact: '+name)
    cases=json.loads((OUT/'cases.json').read_text());expected,changes,spec=revised_cases()
    assert cases==expected
    assert json.loads((OUT/'changes.json').read_text())==changes
    before=read(BASE/'advisory.csv');after=read(OUT/'advisory.csv');allrows=read(OUT/'all.csv')
    assert len(cases)==len(before)==len(after)==263 and len(allrows)==305
    assert allrows[42:]==after
    assert (BASE/'core.csv').read_bytes()==(OUT/'core.csv').read_bytes()
    baseall=read(BASE/'all.csv')
    for old,new in zip(baseall[:42],allrows[:42]):
        assert all(new[k]==v for k,v in old.items()) and not new['editorial_change_ids']
    changed=[];prompts=[]
    oldcases=json.loads((BASE/'cases.json').read_text())
    for old,new,c,oldc in zip(before,after,cases,oldcases):
        assert new['task_id']==old['task_id']==c['task_id']
        fields={k for k in old if old[k]!=new[k]}
        assert fields <= {'user_prompt','rubric','context'},(new['task_id'],fields)
        if fields:changed.append(new['task_id'])
        if 'user_prompt' in fields:prompts.append(new['task_id'])
        assert new['context']=='\n'.join(s['text'] for s in c['context_sections'])
        if c['source_record'] in (22,25):
            assert c['user_prompt']==oldc['user_prompt']
            assert c['reference_only_context_sections']==oldc['context_sections']
            assert c['reference_only_rubric_sections']==oldc['rubric_sections']
            active=new['context']+new['rubric']
            assert not any(word in active for word in ('椭圆','梅涅劳斯','焦距','截线','面积法'))
            assert len(re.findall(r'^\d+\.',new['rubric'],re.M))==9 if c['source_record']==22 else len(re.findall(r'^维度',new['rubric'],re.M))==4
        topic_rule=next((r for r in spec['topic_alignments'] if r['source_record']==c['source_record']),None)
        if topic_rule:
            assert c['user_prompt']==oldc['user_prompt']
            assert c['reference_only_context_sections']==oldc['context_sections']
            assert c['reference_only_rubric_sections']==oldc['rubric_sections']
            def dimension_count(text):
                return len(re.findall(r'^(?:\d+\.|维度[一二三四五六七八九十]+：)',text,re.M))
            assert dimension_count(old['rubric'])==dimension_count(new['rubric'])
        assert new['user_prompt']==c['user_prompt']
        assert new['rubric']=='\n'.join(s['text'] for s in c['rubric_sections'])
        assert new['editorial_change_ids']==','.join(c.get('editorial_change_ids',[]))
        original_rubric=oldc['rubric_sections'][1]['text'] if c['source_record']==18 else old['rubric']
        assert dimensions(original_rubric)==dimensions(new['rubric']),new['task_id']
        assert new['expected_output']==old['expected_output']==''
    assert len(changed)==153 and len(prompts)==5
    for p in (BASE/'originals').rglob('*'):
        if p.is_file():assert p.read_bytes()==(OUT/p.relative_to(BASE)).read_bytes()
    for name in ['source_documents.json','source_issues.json']:
        assert (BASE/name).read_bytes()==(OUT/name).read_bytes()
    text=(OUT/'305题小修审阅.txt').read_text(encoding='utf-8-sig')
    assert re.findall(r'^题号：(.*)$',text,re.M)==[r['task_id'] for r in allrows]
    assert re.findall(r'^第 (\d{3}) / 305 题',text,re.M)==[f'{i:03d}' for i in range(1,306)]
    gate=json.loads((OUT/'release_gate.json').read_text());assert gate['ready'] is False
    return {'release':OUT.name,'status':'limited_edit_checks_passed','advisory_cases':263,
        'changed_cases':len(changed),'changed_prompts':5,'unchanged_advisory_cases':263-len(changed),'core_42_unchanged':True,
        'existing_weights_preserved':True,'original_files_preserved':True,
        'no_generated_gold_answers':True,'auto_scoring_ready':False,'full_content_acceptance':False}

if __name__=='__main__':print(json.dumps(check(),ensure_ascii=False,indent=2))
