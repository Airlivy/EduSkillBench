"""Check exact source slices, source bytes and complete selected-case inventory."""
import csv
import json
from pathlib import Path
from restore_source263 import ROOT, OLD, OUT, sha, doc_text, sections


def check(directory=OUT):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    for name,digest in manifest['artifacts'].items():
        if sha(directory/name)!=digest:raise ValueError('Changed restored artifact: '+name)
    bindings=json.loads((OLD/'source_bindings.json').read_text())
    cases=json.loads((directory/'cases.json').read_text())
    docs=json.loads((directory/'source_documents.json').read_text())
    if len(cases)!=263 or len(docs)!=30:raise ValueError('Wrong restoration inventory')
    if [c['task_id'] for c in cases]!=[b['task_id'] for b in bindings]:raise ValueError('Selected cases changed')
    if len({c['task_id'] for c in cases})!=263:raise ValueError('Duplicate cases')
    for source,d in docs.items():
        if (ROOT/source).read_bytes()!=(directory/d['original_path']).read_bytes():raise ValueError('Original changed: '+source)
        if sha(ROOT/source)!=d['source_sha256']:raise ValueError('Source fingerprint changed')
        text,equations=doc_text(ROOT/source)
        if text!=d['text'] or equations!=d['equation_objects_xml']:raise ValueError('Document export changed')
        if sections(text)!=d['sections']:raise ValueError('Section boundaries changed')
    with (directory/'advisory.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    with (directory/'all.csv').open(encoding='utf-8-sig',newline='') as f:allrows=list(csv.DictReader(f))
    if allrows[42:]!=rows or len(allrows)!=305:raise ValueError('Combined inventory differs')
    with (OLD/'core.csv').open(encoding='utf-8-sig',newline='') as f:core=list(csv.DictReader(f))
    if any(any(row[k]!=original[k] for k in original) for row,original in zip(allrows[:42],core)):raise ValueError('Core modified')
    if (OLD/'core.csv').read_bytes()!=(directory/'core.csv').read_bytes():raise ValueError('Core file changed')
    for c,b,r in zip(cases,bindings,rows):
        d=docs[b['local_source_path']];start,end=c['question_span']
        if c['user_prompt']!=d['text'][start:end] or r['user_prompt']!=c['user_prompt']:raise ValueError('Question changed')
        if ''.join(c['user_prompt'].split())!=''.join(b['source_question_zh'].split()):raise ValueError('Question selection changed')
        for field,kinds,col in [('context_sections',('title','context','problem'),'context'),
                               ('rubric_sections',('rubric',),'rubric'),
                               ('solution_sections',('solution',),'source_solution'),
                               ('example_sections',('examples',),'source_examples'),
                               ('reference_sections',('references',),'source_references')]:
            expected=[s for s in d['sections'] if s['kind'] in kinds]
            if c[field]!=expected or r[col]!='\n'.join(s['text'] for s in expected):raise ValueError('Missing/changed section: '+field)
            for s in expected:
                if s['text']!=d['text'][s['start']:s['end']]:raise ValueError('Not an original source slice')
        if c['expected_output'] or r['expected_output']:raise ValueError('Invented reference answer')
        if any(r[k] for k in ('skill_id','subject','difficulty','education_level','education_stage','edubench_scenario')):raise ValueError('Added metadata assumption')
        if r['source_document_text']!=d['text'] or json.loads(r['source_equation_objects_xml'])!=d['equation_objects_xml']:raise ValueError('Full source lost')
    return {'release':directory.name,'status':'source_fidelity_passed','cases':263,'source_documents':30,
            'original_files_byte_identical':True,'question_and_section_slices_verified':True,
            'equation_objects_retained':sum(len(d['equation_objects_xml']) for d in docs.values()),
            'core_42_unchanged':True,'auto_scoring_ready':False,'content_correctness_certified':False}

if __name__=='__main__':print(json.dumps(check(),ensure_ascii=False,indent=2))
