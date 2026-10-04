"""Check all 305 native cases against the reviewed parent and explicit scope map."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from repro.source_protocol import load_release,dimensions,digest
from build_source_native import SCOPES,BASE
from check_source_minimal import check as check_parent
from content_fixes import revised_prompt,check_applied


def check():
    check_parent();directory,cases,manifest=load_release()
    assert len(cases)==305 and len({c['task_id'] for c in cases})==305
    parent=json.loads((BASE/'cases.json').read_text());advisory=cases[42:]
    assert len(advisory)==263
    for old,new in zip(parent,advisory):
        assert old['task_id']==new['task_id'] and revised_prompt(old['task_id'],old['user_prompt'])==new['user_prompt']
        assert new['expected_output']=='' and new['parent_case_sha256']==digest(old)
        original=dimensions('\n'.join(s['text'] for s in old['rubric_sections']))
        assert [(c['id'],c['name'],c['weight'],[l['label'] for l in c['levels']]) for c in original]==[(c['id'],c['name'],c['weight'],[l['label'] for l in c['levels']]) for c in new['criteria']]
        expected=SCOPES[old['source_record']][old['source_scene_index']-1] if old['source_record'] in SCOPES else list(range(1,len(original)+1))
        assert new['applicable_ids']==[f'D{i}' for i in expected]
        assert new['applicable_ids'] and set(new['applicable_ids'])<={r['id'] for r in original}
    import csv
    with (BASE/'core.csv').open(encoding='utf-8-sig',newline='') as f:core=list(csv.DictReader(f))
    for old,new in zip(core,cases[:42]):
        for k,v in old.items():assert new[k]==(json.loads(v) if k=='rubric' else v)
    text=(directory/'305题运行审阅.txt').read_text(encoding='utf-8-sig')
    assert re.findall(r'^题号：(.*)$',text,re.M)==[c['task_id'] for c in cases]
    gate=json.loads((directory/'release_gate.json').read_text());assert gate['ready'] and not gate['full_expert_acceptance']
    check_applied(cases)
    return {'status':'native_release_verified','cases':305,'fixed_case_scopes':263,'core_preserved':True,
        'original_weights_and_level_labels_preserved':True,'invented_scalar_scores':False,'expert_certified':False}
if __name__=='__main__':print(json.dumps(check(),ensure_ascii=False,indent=2))
