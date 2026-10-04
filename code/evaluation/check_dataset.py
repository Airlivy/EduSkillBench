"""Offline integrity and known-defect checks; never certify full semantic correctness."""
import csv
import hashlib
import json
import math
import tempfile
from pathlib import Path
from eval_compiler import compile_cases
from senior_structure_checks import read_csv, structural

ROOT=Path(__file__).resolve().parents[2]


def check(root=ROOT):
    index=json.loads((root/'data/revisions/index.json').read_text())
    directory=root/'data/revisions'/index['current_candidate']
    manifest=json.loads((directory/'manifest.json').read_text())
    errors=[]
    def require(condition,message):
        if not condition:errors.append(message)
    for name,expected in manifest['artifact_sha256'].items():
        p=directory/name
        require(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==expected,'artifact hash: '+name)
    for name,expected in manifest['input_sha256'].items():
        p=root/name
        require(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==expected,'input hash: '+name)
    rows=[]
    for name,count in [('single_turn_tasks.csv',42),('single_turn_tasks_cn263.csv',263)]:
        with (directory/name).open(encoding='utf-8-sig') as f:part=list(csv.DictReader(f))
        require(len(part)==count,'row count: '+name);rows.extend(part)
    byid={r['task_id']:r for r in rows}
    require(len(byid)==len(rows)==305,'duplicate/missing task IDs')
    cases=json.loads((directory/'evals.json').read_text())['cases']
    require(len(cases)==len(rows) and {c['id'] for c in cases}==set(byid),'compiled coverage')
    for c in cases:
        r=byid.get(c['id'])
        if r is None:continue
        tid=c['id'];rubric=json.loads(r['rubric'])
        require(all(isinstance(v,str) and v.strip() for v in r.values()),'empty field: '+tid)
        require(c['question']==r['context']+'\n\n'+r['user_prompt'],'question binding: '+tid)
        require(c['ground_truth']==r['expected_output'] and c['rubric']==rubric,'reference/rubric binding: '+tid)
        require(c['expected_behavior']==[x['description'] for x in rubric],'behavior binding: '+tid)
        require(len({x['id'] for x in rubric})==len(rubric),'criterion IDs: '+tid)
        require(len({x['description'] for x in rubric})==len(rubric),'duplicate criterion: '+tid)
        require(all(type(x['points']) in (int,float) and math.isfinite(x['points']) and x['points']>0 for x in rubric),'weights: '+tid)
        require(math.isclose(sum(x['points'] for x in rubric),100),'weight total: '+tid)
    changed=json.loads((directory/'changes.json').read_text())
    notes=json.loads((directory/'correction_notes.json').read_text())
    require({x['task_id'] for x in changed}<={x['task_id'] for x in notes},'changed task missing reason')
    for delta in changed:
        for field,values in delta['fields'].items():
            require(byid[delta['task_id']][field]==values['after'],'change receipt: '+delta['task_id'])
    bindings=json.loads((directory/'source_bindings.json').read_text())
    require({r['task_id'] for r in bindings}=={t for t in byid if '__cn' in t},'source coverage')
    for b in bindings:
        p=root/b['local_source_path']
        require(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==b['local_source_sha256'],'source hash: '+b['task_id'])
    routes=json.loads((directory/'skill_routing_review.json').read_text())
    quarantined=[r['task_id'] for r in routes if r['routing_status'].startswith('quarantined')]
    require(len(quarantined)==9,'known routing quarantine')
    require(not any(r['routing_gold'] for r in routes),'unaccepted routing promoted to gold')
    gate=json.loads((directory/'release_gate.json').read_text())
    require(not gate['ready'] and gate['formal_cases_released']==0 and index['formal_release'] is None,'premature release')
    senior_results=[]
    with tempfile.TemporaryDirectory(prefix='eduskill-acceptance-') as temporary:
        for name in ['single_turn_tasks.csv','single_turn_tasks_cn263.csv']:
            compiled=Path(temporary)/Path(name).stem
            compile_cases(directory/name,compiled,root/'skills/single_turn',review_only=True)
            issues,extra_ids=structural(read_csv(directory/name),compiled)
            failed={tid:problems for tid,problems in issues.items() if problems}
            senior_results.append({'dataset':name,'task_issues':failed,'extra_eval_ids':extra_ids})
            require(not failed and not extra_ids,'senior structure checks: '+name)
    return {'candidate':directory.name,'tasks':len(rows),'changed_tasks':len(changed),
            'offline_checks_passed':not errors,'errors':errors,'routing_quarantined':quarantined,
            'senior_structure_checks':senior_results,
            'full_content_acceptance':'pending','formal_release':False,
            'scope':'integrity, binding and explicit known-defect checks only; not automatic semantic certification'}


def main():
    result=check()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['offline_checks_passed'] else 1


if __name__=='__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(main())
