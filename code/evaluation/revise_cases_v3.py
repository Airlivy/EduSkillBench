"""Reproducible full-corpus revision with explicit release gates; never overwrites historical data."""
import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from case_specs_v3 import SPECS

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/revisions/case-review-v3-20260930'
spec=importlib.util.spec_from_file_location('previous_revision',Path(__file__).with_name('revise_cases_20260930.py'))
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def write_csv(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)

def source_scenes(text):
    text=text.replace('\\n','\n')
    text=re.split(r'(?m)^#{1,6}\s*\d+[、.．]\s*规范依据',text)[0]
    heads=list(re.finditer(r'(?:\*\*)?情[景境]\s*\d+\s*[:：]',text))
    if heads:return [text[m.start():heads[i+1].start() if i+1<len(heads) else len(text)].strip() for i,m in enumerate(heads)]
    return [p.strip() for p in text.split('\n\n') if p.strip()]

# Retain factual cohort constraints without embedding a solution or unrelated scenarios.
CONTEXT={
 1:'An information-technology teacher is planning representations of programming concepts. The grade is unspecified except where stated in the question.',
 2:'A primary-school teacher is designing a mathematics or information-technology lesson opening. Local landmark references are scenario premises, not verified architectural descriptions.',
 5:'A vocational-school Python teacher teaches 120-minute double lessons to pupils with varied prior knowledge. No official examination syllabus is supplied.',
 7:'A vocational-school teacher is adapting data-analysis teaching to ordinary computers and varied starting points. No official curriculum text or complete adapted plan is supplied.',
 18:'A primary-school teacher is planning integration of information technology and mathematics. No complete unit plan is supplied.',
 21:'A teacher works with Grade 1-2 pupils on classroom routines. No complete command system or longitudinal classroom observation data is supplied.',
 22:'A senior-secondary mathematics teacher is preparing the concept named in the question.',
 23:'A senior-secondary mathematics teacher requests one three-item variant set for a 15-20 minute segment: a misconception probe, a disguised application and a flawed-solution repair. Include answer guidance.',
 24:'A senior-secondary mathematics teacher wants to make the reasoning behind the named construction or theorem visible. No figure is supplied; define any example used.',
 25:'A Grade 12 teacher requests an accessible enrichment lesson. In this revised task, principal-variable method means selecting a main variable and using constraints or treating other variables as parameters. This is an explicitly scoped adaptation, not a claim about every use of that term.',
 26:'A senior-secondary mathematics teacher requests a concept-building explanation of the single topic in the question.',
 27:'A Grade 11-12 mathematics teacher wants pupils to recognize when an expression can be transformed into a familiar form.',
 28:'A senior-secondary mathematics teacher requests a motivated introduction to the single concept in the question.',
 29:'A senior-secondary mathematics teacher asks for an error-diagnosis plan. No actual student solution is supplied; hypothetical examples must be labelled as such. The task does not require a multiple-choice hinge question.',
 30:'A senior-secondary mathematics teacher wants a conceptual explanation of the single topic in the question.',
 31:'A senior-secondary mathematics teacher wants pupils to choose the correct counting model for the single topic in the question.',
 35:'A primary-school teacher is concerned about homework avoidance. The observations do not establish a clinical diagnosis.',
 43:'An upper-primary teacher is designing practical labor education for Grades 4-6. Resources beyond those in the question are unspecified.',
 50:'A primary science teacher is teaching cooperation during practical work. Use the grade specified in the question; otherwise state an age assumption.',
 51:'A primary science teacher asks about one assessment difficulty. Use only the resources and project duration stated in this question.',
 52:'A Grade 3 teacher works in a rural school with limited resources. Any additional project constraints must be stated as assumptions.',
 53:'A primary teacher wants contingent support that helps a pupil resume practical work. Use the particular material, difficulty and grade described in the question.',
 54:'A primary science teacher is revising learning objectives. No official curriculum-standard text is supplied; a quoted requirement in the question is a scenario premise, not an independently verified legal or policy claim.',
 55:'A primary science teacher needs help with one classroom-management difficulty. No actual outcome of a proposed intervention has been observed.',
 56:'A primary science teacher wants to improve questioning in the specific lesson described.',
 57:'A primary teacher needs an equitable response to the particular group-role problem described. Teacher intervention may be appropriate; no categorical ban on temporary assignment is assumed.',
 59:'A primary science teacher encountered an unexpected observation in the experiment described in the question. Its cause has not been established.',
 60:'A primary science teacher works with limited resources. A proposed activity must be feasible with suitable supervision and materials; missing equipment is not a reason to improvise hazards.',
 62:'A vocational-school teacher or administrator asks about the single homework-design issue described. Absolute claims in a teacher request may be challenged with a reasoned alternative.',
 63:'A vocational-school teacher or administrator asks about the single practical-assignment issue described. No student health diagnosis, perfect fairness or verified real-world outcome should be inferred beyond the stated observations.',
}

# Sentence-level criteria are individually judged; numeric examples are optional equivalents.
def criterion_rows(key,teach,bad):
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])',key) if s.strip()]
    descriptions=[f'Content check (equivalent correct explanations/examples accepted; the anchor example is not mandatory): {s}' for s in sentences]
    descriptions += [f'Task-specific deliverable check: {teach}',
       'The response gives an observable way to check the proposed explanation or next teaching action.',
       'The response distinguishes supplied facts from assumptions or hypothetical examples.',
       f'Critical-error check: the response does not endorse this error: {bad}']
    # Equal rubric weights are intentional in v3, explicitly distinct from historical weights.
    n=len(descriptions)
    # Use exact equal fractions as numeric weights instead of remainder-biased integer weights.
    return [{'id':f'C{i+1}','criterion':f'Case check {i+1}','points':100/n,
             'description':s,'critical':i<len(sentences) or i==n-1} for i,s in enumerate(descriptions)]


def old_case_fixes(row):
    r=dict(row);r.update(previous.PATCHES.get(('original42',r['task_id']),{}));tid=r['task_id']
    if tid=='retrieval-practice-generator__03':r['education_stage']='high_school'
    if tid=='emergent-project-design-scaffold__01':
        r['user_prompt']=r['user_prompt'].replace('a Reception class of 3-4 year olds','an early-years class of 3-4 year olds')
        r['education_level']='Early years, ages 3-4'
    if tid=='differentiation-adapter__03':
        r['user_prompt']+='\nThe source texts are not supplied. Adapt the task structure; do not invent quotations or conclusions about their actual reliability. The teacher will provide appropriately dated source excerpts.'
    if tid=='hinge-question-designer__01':
        r['user_prompt']+='\nUse four options. Distinguish evidence about reactants from evidence about cellular location; one answer cannot prove full understanding.'
    if tid=='hinge-question-designer__02':
        r['user_prompt']+='\nUse standard formal written English and avoid borderline stylistic cases involving very short clauses.'
    if r['skill_id']=='ruler-emotional-literacy-sequence':
        r['user_prompt']+='\nCover recognizing, understanding, naming, expressing and regulating emotions, without requiring these exact labels. Allow private or fictional examples; personal disclosure is optional and teacher modeling should remain appropriately bounded.'
    if r['skill_id']=='self-efficacy-builder-sequence':
        r['user_prompt']+='\nTreat possible barriers as hypotheses, not clinical diagnoses. Progression depends on observed readiness; success and anxiety reduction cannot be guaranteed.'
    if r['skill_id']=='spaced-practice-scheduler':
        r['user_prompt']+='\nBefore a topic has been introduced, use an explicitly labelled prerequisite check rather than claiming retrieval of that topic. Adjust intervals to available lessons and observed performance; no universal optimal interval is required.'
    rubric=json.loads(r['rubric'])
    for c in rubric:
        d=re.sub(r'^Award \d+ points if ', '', c['description'])
        d=d.replace('It ensures that a successful design is impossible without a deep, calculable understanding of heat transfer, preventing trial-and-error guessing.', 'It requires students to submit heat-transfer reasoning and calculations alongside prototype evidence; a working prototype alone is insufficient evidence of understanding.')
        d=d.replace('The design ensures students cannot complete the project successfully without genuinely understanding the ecological concepts.', 'The assessment requests ecological reasoning as well as a finished product.')
        d=d.replace('It ensures that producing the digital exhibit requires deep historical understanding and cannot be achieved merely by summarizing textbook information.', 'The assessment requests an evidence-based historical argument rather than only a summary or polished exhibit.')
        d=d.replace('The first task should be virtually guaranteed to succeed','The first task should be chosen from demonstrated strengths and adjusted after observing the response')
        d=d.replace('are identified as counterproductive','are not used as substitutes for skill development and specific feedback')
        d=d.replace('analyzes which source of self-efficacy is most damaged','offers evidence-linked hypotheses about the barrier')
        d=d.replace('diagnostic key that explicitly states what choosing the correct answer confirms','diagnostic key that states what the chosen answer suggests and what a follow-up would need to confirm')
        d=d.replace("the correct answer's confirmation of understanding","the evidence suggested by the correct answer, without claiming that one choice proves understanding")
        d=d.replace('The correct answer requires true understanding of independent clauses.','Distractors probe independent-clause reasoning; the teacher should check reasoning rather than assume that guessing is impossible.')
        d=d.replace('The correct answer cannot be arrived at through flawed reasoning or test-taking shortcuts.','The design minimizes obvious surface cues; a correct choice alone does not prove the intended reasoning.')
        d=d.replace('The correct answer cannot be guessed without conceptual understanding.','The design minimizes obvious surface cues; a correct choice alone does not prove the intended reasoning.')
        if r['skill_id']=='spaced-practice-scheduler':
            d=d.replace('optimal spacing intervals','spacing principles').replace('optimal long-term retention','supported long-term retention')
            d+=' Judge feasibility within the stated timetable; allow a prerequisite check in the first lesson and adapt intervals where insufficient later lessons exist.'
        if r['skill_id']=='ruler-emotional-literacy-sequence':
            d=d.replace('authentic emotional engagement','evidence-based engagement with emotional themes').replace('rigorously enforces','explains')
            d+=' Accept equivalent wording for the five functions; no personal disclosure or demonstrated reduction in distress is required.'
        c['description']=d
    # Split independent sentences while preserving each original criterion's total weight.
    atomic=[]
    for c in rubric:
        pieces=[s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])',c['description']) if s.strip()]
        for d in pieces:
            atomic.append({'id':f'C{len(atomic)+1}','criterion':c['criterion'],
                           'points':c['points']/len(pieces),'description':d,'critical':False})
    r['rubric']=json.dumps(atomic,ensure_ascii=False)
    return r


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    original=read(ROOT/'data/single_turn_tasks.csv');expanded=read(ROOT/'data/single_turn_tasks_cn263.csv')
    trace={r['task_id']:r for r in read(ROOT/'data/single_turn_tasks_cn263_trace.csv')}
    sources=read(ROOT/'jobs/new_scenarios/source/questions.csv')
    revised42=[old_case_fixes(r) for r in original]
    revised263=[];bindings=[];acceptance=[];routes=[]
    previous_anchors={r['task_id']:r for r in previous.ACCEPTANCE if r['dataset']=='cn263'}
    for old in expanded:
        r=dict(old);tid=r['task_id'];g,i=map(int,re.search(r'__cn(\d+)_(\d+)$',tid).groups())
        r.update(previous.PATCHES.get(('cn263',tid),{}))
        if (g,i) in SPECS:key,teach,bad=SPECS[(g,i)]
        else:
            assert tid in previous_anchors,tid
            expected=r['expected_output']
            key=expected.split('Core answer: ',1)[1].split('\nClassroom implementation:',1)[0]
            teach=expected.split('Classroom implementation: ',1)[1].split('\nDo not accept:',1)[0]
            bad=expected.split('Do not accept: ',1)[1]
        r['context']=CONTEXT[g]
        # Normalized topic-specific expected answer remains teacher/judge-only.
        r['expected_output']=f'Answer only this case. Accept equivalent correct approaches and examples.\nCorrectness: {key}\nRequested application: {teach}\nReject endorsement of: {bad}'
        r['rubric']=json.dumps(criterion_rows(key,teach,bad),ensure_ascii=False)
        # Keep the original question instead of carrying unrelated clarification boilerplate.
        r['user_prompt']=old['user_prompt']
        r['user_prompt']+='\nProvide a concrete response to this case and a brief rationale. Include a feasible way to check the proposed learning or teaching action. State material assumptions. Hypothetical examples are allowed; do not claim unseen classroom outcomes. Equivalent defensible approaches are welcome.'
        if g in (7,18,21) and i==10:
            r['user_prompt']+='\nNo complete plan is attached. Identify what is needed for an actual review and provide conditional review guidance; do not certify an unseen plan.'
        if g==1 and i==8:
            r['user_prompt']+='\nDistinguish learner preferences and accessibility needs from the claim that teaching must match fixed learning-style types.'
        if g==55 and i==1:
            key='Immediate grabbing calls for a calm pause and controlled access before further explanation.'
            teach='Give a short stop cue, secure materials if needed, model one handling action and reopen access after a brief practice.'
            bad='Continuing a long explanation while unsafe grabbing persists or humiliating the class.'
            r['expected_output']=f'Correctness: {key}\nRequested application: {teach}\nReject endorsement of: {bad}'
            r['rubric']=json.dumps(criterion_rows(key,teach,bad),ensure_ascii=False)
        if g==55 and i==2:
            teach='Give a directly usable short cue and visible response, demonstrate it, rehearse once and check pupils who did not respond.'
            r['expected_output']=f'Correctness: {key}\nRequested application: {teach}\nReject endorsement of: {bad}'
            r['rubric']=json.dumps(criterion_rows(key,teach,bad),ensure_ascii=False)
        if g==63 and i==5:
            r['user_prompt']=r['user_prompt'].replace('above-mentioned online store operation group assignment','online store operation group assignment')
        # Grade in question takes precedence over the old shared source grade.
        matches=re.findall(r'\b(first|second|third|fourth|fifth|sixth)[ -]grade\b',old['user_prompt'],re.I)
        if matches:
            grade={'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6}[matches[0].lower()]
            r['education_level']=f'Grade {grade} (primary)';r['education_stage']='elementary'
        elif g==1:
            r['education_level']='Primary/secondary; grade unspecified';r['education_stage']='mixed_k12'
        elif g in (50,51,53,54,55,56,57,59,60):
            r['education_level']='Primary; grade unspecified';r['education_stage']='elementary'
        source=sources[g-1];scenes=source_scenes(source['questions']);source_index=3 if g==25 else i
        assert 0<source_index<=len(scenes),(tid,source_index,len(scenes))
        raw=ROOT/'jobs/new_scenarios/source/raw'/source['source']
        assert raw.exists(),raw
        bindings.append({'task_id':tid,'source_record':g,'original_scene_index':source_index,
                         'previous_scene_index':trace[tid]['scene_index'],
                         'local_source_path':str(raw.relative_to(ROOT)),'local_source_sha256':sha(raw),
                         'source_question_zh':scenes[source_index-1],
                         'source_status':'local_snapshot_bound; upstream provenance/rights not independently certified',
                         'translation_status':'adapted_english; source quote retained; independent bilingual review pending',
                         'special_note':'Old scene_index 1 referred to the selected subset, not source scene 3; term explicitly scoped in revised English.' if g==25 else ''})
        # Never silently treat a broad consultation label as validated Skill-routing gold.
        mismatch=g==29
        partial=g in (7,23,35,43,54,62,63)
        routes.append({'task_id':tid,'legacy_skill_id':r['skill_id'],
                       'routing_status':'quarantined_scope_mismatch' if mismatch else ('partial_match_needs_review' if partial else 'candidate_needs_independent_review'),
                       'routing_gold':False,
                       'reason':('The question asks for an error-diagnosis consultation, not the Skill-required multiple-choice hinge question.' if mismatch else
                                 'The question covers a subtask or broader consultation; verify applicability without forcing a different deliverable.' if partial else
                                 'The requested lesson/scaffold/questioning support is plausibly related; independent applicability review remains pending.')})
        acceptance.append({'task_id':tid,'correctness_anchor':key,'application_anchor':teach,
                           'reject_endorsement':bad,'live_judge_test':'not_run','independent_review':'pending'})
        revised263.append(r)
    changes=[];inventory=[]
    for dataset,olds,news,name in [('original42',original,revised42,'single_turn_tasks.csv'),('cn263',expanded,revised263,'single_turn_tasks_cn263.csv')]:
        write_csv(name,news,list(olds[0]))
        for old,new in zip(olds,news):
            diff={k:{'before':old[k],'after':new[k]} for k in old if old[k]!=new[k]}
            changes.append({'dataset':dataset,'task_id':new['task_id'],'fields':diff})
            inventory.append({'dataset':dataset,'task_id':new['task_id'],'content_status':'editorially_revised_pending_independent_acceptance',
                              'release_status':'blocked_pending_acceptance','changed_fields':','.join(diff)})
    compiled=[]
    for r in revised42+revised263:
        rr=json.loads(r['rubric'])
        compiled.append({'id':r['task_id'],'question':r['context']+'\n\n'+r['user_prompt'],
                         'ground_truth':r['expected_output'],'rubric':rr,
                         'expected_behavior':[x['description'] for x in rr],
                         'score_metric':'weighted','dataset_revision':'case-review-v3-20260930',
                         'status':'not_released'})
    dump('evals.json',{'schema_version':3,'release_status':'blocked_pending_acceptance','cases':compiled})
    dump('changes.json',changes);dump('source_bindings.json',bindings);dump('acceptance_cases.json',acceptance)
    write_csv('review_inventory.csv',inventory);dump('skill_routing_review.json',routes)
    dump('split_groups.json',[{'task_id':r['task_id'], 'source_group':'original42:'+r['skill_id'], 'partition':'evaluation_candidate_only'} for r in revised42]+[{'task_id':b['task_id'],'source_group':'cn_source:'+str(b['source_record']),'partition':'evaluation_candidate_only'} for b in bindings])
    dump('split_policy.json',{'status':'unsplit_evaluation_candidates','training_use':'not_authorized_by_this_artifact',
       'group_key':'source_record','never_random_split_individual_cases':True,
       'cross_source_near_duplicate_review':'pending','expected_output_is_sft_target':False,
       'reporting':['per-skill n and mean','macro mean over represented skills','micro mean explicitly labelled'],
       'coverage':'263 expanded tasks retain 9 historical labels, not validated coverage of all 14 skills'})
    dump('release_gate.json',{'ready':False,'reason':'A generated revision and offline checks cannot certify a benchmark.',
       'requirements':{'offline_integrity':'run tests','independent_content_acceptance':'pending',
                       'skill_routing_acceptance':'pending; known hinge mismatch quarantined',
                       'judge_positive_negative_calibration':'not_run','source_rights_and_upstream_version':'pending',
                       'cross_source_semantic_leakage':'pending'},
       'historical_results_compatible':False,'formal_cases_released':0})
    files=['data/single_turn_tasks.csv','data/single_turn_tasks_cn263.csv','data/single_turn_tasks_cn263_trace.csv','jobs/new_scenarios/source/questions.csv','docs/data-quality/review-inputs/SENIOR_AUDIT_2026-09-28.md','docs/data-quality/review-inputs/SENIOR_LEDGER_2026-09-28.csv']
    dump('manifest.json',{'revision':'case-review-v3-20260930','counts':{'original42':42,'cn263':263,'total':305},
                         'source_sha256':{f:sha(ROOT/f) for f in files},
                         'builder_sha256':sha(Path(__file__)),'specs_sha256':sha(Path(__file__).with_name('case_specs_v3.py')),
                         'previous_builder_sha256':sha(Path(__file__).with_name('revise_cases_20260930.py')),
                         'artifact_sha256':{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'},
                         'release_ready':False})
    print(json.dumps({'rows':305,'cn_specs':len(acceptance),'source_bindings':len(bindings),
                      'routing_quarantined':sum(x['routing_status'].startswith('quarantined') for x in routes),'release_ready':False}))

if __name__=='__main__':build()
