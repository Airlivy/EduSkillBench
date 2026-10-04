"""Validate the delivered dataset and its actual execution adapter, without API calls."""
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'repro'))
from protocol import dataset_source, load_tasks, MODELS, task_digest
from prepare import build, verify
from senior_structure_checks import structural, read_csv
from eval_compiler import compile_cases


def numerical_checks():
    checks={}
    def check(name, actual, expected):
        ok = math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-9) if isinstance(actual,(int,float)) else actual==expected
        if not ok:raise ValueError((name,actual,expected))
        checks[name]={'computed':actual,'expected':expected,'passed':True}
    check('bakery_change',50-(3*2+2*5+4*1.5),28)
    check('SIR_R0',1+math.log(80/10)/9*4,1.924196240746594)
    check('flux_integral',.5*.4*(.3**2-.1**2)/2,.008)
    check('emf_magnitude',.5*.4*.2*3,.12)
    check('induced_current',.5*.4*.2*3/2,.06)
    # Exhaustive feasible integer enumeration independently corroborates the stationary example.
    profits=[((20-q)*q-(4*q+10),q) for q in range(21)]
    check('monopoly_integer_optimum',max(profits),(54,8))
    check('monopoly_boundaries',[profits[0][0],profits[-1][0]],[-10,-90])
    check('principal_variable_max',max(x*(6-x) for x in range(7)),9)
    check('SSA_valid_angles',sum(30+b<180 for b in (math.degrees(math.asin(.8)),180-math.degrees(math.asin(.8)))),2)
    check('quadratic_roots_2_3',[x*x-5*x+6 for x in (2,3)],[0,0])
    check('quadratic_roots_quarters',[x*x-x+3/16 for x in (.25,.75)],[0,0])
    for x in (-2,-1,0,1,2,3):check('binomial_expansion_'+str(x),8*x**3-12*x*x+6*x-1,(2*x-1)**3)
    check('boxes_identical_balls_empty',sum(a+b+c==4 for a in range(5) for b in range(5) for c in range(5)),15)
    check('boxes_identical_balls_nonempty',sum(a+b+c==4 for a in range(1,5) for b in range(1,5) for c in range(1,5)),3)
    check('labelled_balls_boxes',len(list(itertools.product(range(2),repeat=3))),8)
    partitions={tuple(sorted(tuple(i for i,v in enumerate(a) if v==g) for g in set(a))) for a in itertools.product(range(2),repeat=3)}
    check('unlabelled_groups_exact2',sum(len(p)==2 for p in partitions),3)
    check('unlabelled_groups_at_most2',len(partitions),4)
    for n,expected in [(3,2),(4,9)]:
        check('derangements_'+str(n),sum(all(i!=v for i,v in enumerate(p)) for p in itertools.permutations(range(n))),expected)
    perms=list(itertools.permutations('ABCDE'))
    adjacent=sum(abs(p.index('A')-p.index('B'))==1 for p in perms)
    check('AB_adjacent',adjacent,48);check('AB_nonadjacent',len(perms)-adjacent,72)
    check('six_people_two_rooms',len(list(itertools.combinations(range(6),3))),20)
    check('eleven_groups',10*4+5,45)
    check('eleven_groups_alternative',9*4+3+6,45)
    check('homework_minutes',30+40+40,110)
    check('dot_product',1*3+2*4,11)
    check('complex_modulus',abs(3+4j),5)
    check('complex_conjugate_product',((3+4j)*(3-4j)).real,25)
    check('telescope',sum(1/(k*(k+1)) for k in range(1,18)),1-1/18)
    return checks


def check():
    index=json.loads((ROOT/'data/releases/current.json').read_text())
    if index.get('suite_overrides',{}).get('all',{}).get('release') == 'source-native-20261001':
        from check_source_native import check as native_check
        return native_check()
    if index.get('suite_overrides',{}).get('all',{}).get('release') == 'source-minimal-20261001':
        from check_source_minimal import check as revision_check
        return revision_check()
    if index.get('suite_overrides',{}).get('all',{}).get('release') == 'source-faithful-20261001':
        from check_source263 import check as source_check
        result=source_check()
        result['status']='source_restored_auto_scoring_pending'
        result['note']='263题原文保真通过；未把原文量规擅自转成旧评分器规则。42题运行入口保持原版本。'
        return result
    source,conditions=dataset_source('all')
    directory=source.parent
    tasks=load_tasks(source)
    cases={c['id']:c for c in json.loads((directory/'evals.json').read_text())['cases']}
    ledger=json.loads((directory/'review_ledger.json').read_text())
    assert len(tasks)==len(cases)==len(ledger)==305
    assert len({x['task_id'] for x in ledger})==305
    records={x['task_id']:x for x in ledger}
    raw=read_csv(source)
    for r in raw:
        tid=r['task_id'];c=cases[tid];rub=json.loads(r['rubric'])
        assert all(v.strip() for v in r.values()),tid
        assert c['question']==r['context']+'\n\n'+r['user_prompt'],tid
        assert c['ground_truth']==r['expected_output'] and c['rubric']==rub,tid
        assert c['expected_behavior']==[x['description'] for x in rub],tid
        assert len({x['id'] for x in rub})==len(rub),tid
        assert len({x['description'] for x in rub})==len(rub),tid
        assert any(x.get('critical') for x in rub),tid
        assert records[tid]['case_sha256']==hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),tid
        if '__cn' in tid:
            for criterion in rub:
                if criterion['description'].startswith('Content check'):
                    assert criterion['description'].split(': ',1)[1] in r['expected_output'],tid
    bindings=json.loads((directory/'source_bindings.json').read_text())
    assert {x['task_id'] for x in bindings}=={t for t in tasks if '__cn' in t}
    for b in bindings:
        assert hashlib.sha256((ROOT/b['local_source_path']).read_bytes()).hexdigest()==b['local_source_sha256']
    checks=numerical_checks()
    generated=[]
    with tempfile.TemporaryDirectory(prefix='eduskill-release-check-') as temp:
        temp=Path(temp)
        compiled=temp/'senior'
        compile_cases(source,compiled,ROOT/'skills/single_turn')
        problems,extra=structural(raw,compiled)
        assert not problems and not extra,(problems,extra)
        for suite in ['core','all']:
            src,conds=dataset_source(suite);rows=load_tasks(src)
            for mode in (['access','forced'] if suite=='core' else ['access']):
                dest=temp/(suite+'-'+mode)
                manifest=build(dest,rows,MODELS,mode=mode,metric='weighted',system_profile='education-single-turn',conditions=conds)
                verify(dest)
                assert manifest['task_input_sha256']==task_digest(rows)
                generated.append({'suite':suite,'mode':mode,'tasks':len(rows),'models':len(MODELS),'conditions':list(conds),'prepared_cells':len(rows)*len(MODELS)*len(conds)})
    return {'release':directory.name,'status':'passed','editorially_reviewed_tasks':305,
        'senior_structure_cases':305,'numerical_checks':checks,'execution_adapter_checks':generated,
        'live_api_test': 'recorded separately; not implied by offline checks', 'expert_certification':False}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path)
    a=p.parse_args();result=check()
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='numerical_checks'},ensure_ascii=False,indent=2))
