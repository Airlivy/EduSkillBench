import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'data/revisions/case-review-v3-20260930'
sys.path.insert(0,str(ROOT/'code/evaluation'))
from eval_compiler import compile_cases
from case_specs_v3 import SPECS

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def norm(s):return ''.join(c for c in s if c.isalnum())

class FullRevisionChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=read(OUT/'single_turn_tasks.csv');cls.new=read(OUT/'single_turn_tasks_cn263.csv')
        cls.byid={r['task_id']:r for r in cls.old+cls.new}
    def test_every_row_and_change_is_accounted_for(self):
        self.assertEqual((len(self.old),len(self.new),len(self.byid)),(42,263,305))
        changes=json.loads((OUT/'changes.json').read_text());self.assertEqual(len(changes),305)
        byid={r['task_id']:r for r in changes}
        for name,after in [('single_turn_tasks.csv',self.old),('single_turn_tasks_cn263.csv',self.new)]:
            before=read(ROOT/'data'/name)
            self.assertEqual([r['task_id'] for r in before],[r['task_id'] for r in after])
            for a,b in zip(before,after):
                self.assertEqual(byid[a['task_id']]['fields'],{k:{'before':a[k],'after':b[k]} for k in a if a[k]!=b[k]})
    def test_sources_unchanged(self):
        m=json.loads((OUT/'manifest.json').read_text())
        for path,expected in m['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),expected)
    def test_all_chinese_quotes_exist_in_original_documents(self):
        bindings=json.loads((OUT/'source_bindings.json').read_text());self.assertEqual(len(bindings),263)
        cache={}
        for r in bindings:
            p=ROOT/r['local_source_path']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),r['local_source_sha256'])
            if p not in cache:
                if p.suffix=='.docx':
                    with zipfile.ZipFile(p) as z:xml=ET.fromstring(z.read('word/document.xml'))
                    txt=''.join(e.text or '' for e in xml.iter() if e.tag.endswith('}t'))
                else:txt=p.read_text()
                cache[p]=norm(txt)
            self.assertIn(norm(r['source_question_zh']),cache[p],r['task_id'])
        principal=next(x for x in bindings if x['task_id']=='lesson-builder__cn25_01')
        self.assertEqual(principal['original_scene_index'],3)
        self.assertIn('主元法',principal['source_question_zh'])
    def test_compiled_case_binding_and_weights(self):
        cases=json.loads((OUT/'evals.json').read_text())['cases']
        self.assertEqual(len(cases),305)
        for c in cases:
            r=self.byid[c['id']];rubric=json.loads(r['rubric'])
            self.assertEqual(c['question'],r['context']+'\n\n'+r['user_prompt'])
            self.assertEqual(c['ground_truth'],r['expected_output'])
            self.assertEqual(c['rubric'],rubric)
            self.assertEqual(len({x['id'] for x in rubric}),len(rubric))
            self.assertTrue(math.isclose(sum(x['points'] for x in rubric),100))
            self.assertTrue(all(math.isfinite(x['points']) and x['points']>0 for x in rubric))
            self.assertEqual(c['score_metric'],'weighted')
    def test_case_specific_references_not_source_templates(self):
        self.assertEqual(len({r['expected_output'] for r in self.new}),263)
        self.assertEqual(len({r['rubric'] for r in self.new}),263)
        self.assertEqual(len(SPECS),193)
        for r in self.new:
            self.assertNotIn('Xu Xin',r['context'])
            self.assertNotIn('Song Mengqi',r['context'])
        clip=self.byid['adaptive-hint-sequence-designer__cn59_01']
        self.assertNotIn('pendulum',clip['context'].lower())
        self.assertEqual(clip['education_level'],'Grade 1 (primary)')
    def test_known_metadata_and_unseen_plan_cases(self):
        self.assertEqual(self.byid['retrieval-practice-generator__03']['education_stage'],'high_school')
        for tid in ['lesson-builder__cn01_04','lesson-builder__cn01_10']:
            self.assertEqual(self.byid[tid]['education_stage'],'elementary')
        for tid in ['lesson-builder__cn18_10','lesson-builder__cn21_10','differentiation-adapter__cn07_10']:
            self.assertIn('No complete plan is attached',self.byid[tid]['user_prompt'])
    def test_scope_mismatch_is_not_routing_gold(self):
        routes=json.loads((OUT/'skill_routing_review.json').read_text())
        self.assertEqual(len(routes),263)
        hinge=[r for r in routes if '__cn29_' in r['task_id']]
        self.assertEqual(len(hinge),9)
        self.assertTrue(all(r['routing_status']=='quarantined_scope_mismatch' and not r['routing_gold'] for r in hinge))
        self.assertFalse(any(r['routing_gold'] for r in routes))
    def test_release_is_blocked_until_real_acceptance(self):
        gate=json.loads((OUT/'release_gate.json').read_text())
        self.assertFalse(gate['ready']);self.assertEqual(gate['formal_cases_released'],0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'not released'):
                compile_cases(OUT/'single_turn_tasks.csv',tmp,ROOT/'skills/single_turn')
        with self.assertRaisesRegex(ValueError,'outside historical'):
            compile_cases(OUT/'single_turn_tasks.csv',ROOT/'skills/single_turn',ROOT/'skills/single_turn',review_only=True)
    def test_real_compiler_retains_weights_and_supporting_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=compile_cases(OUT/'single_turn_tasks.csv',tmp,ROOT/'skills/single_turn',review_only=True)
            self.assertEqual(result['eval_cases'],42)
            p=Path(tmp)/'lesson-builder/evals/evals.json';obj=json.loads(p.read_text())
            self.assertEqual(obj['release_status'],'review_only')
            self.assertTrue((Path(tmp)/'lesson-builder/references/lesson_anatomy.md').exists())
            for c in obj['cases']:
                self.assertEqual(c['rubric'],json.loads(self.byid[c['id']]['rubric']))
            result=compile_cases(OUT/'single_turn_tasks_cn263.csv',Path(tmp)/'expanded',ROOT/'skills/single_turn',review_only=True)
            self.assertEqual(result['eval_cases'],263)
    def test_invalid_weights_are_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'bad.csv';r=dict(self.old[0]);rr=json.loads(r['rubric']);rr[0]['points']=-1;r['rubric']=json.dumps(rr)
            with src.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(r));w.writeheader();w.writerow(r)
            with self.assertRaises(ValueError):compile_cases(src,Path(tmp)/'out',ROOT/'skills/single_turn')
            self.assertFalse((Path(tmp)/'out').exists())
    def test_manifest_artifacts(self):
        m=json.loads((OUT/'manifest.json').read_text())
        for name,expected in m['artifact_sha256'].items():
            self.assertEqual(hashlib.sha256((OUT/name).read_bytes()).hexdigest(),expected)

if __name__=='__main__':unittest.main()

class NumericAndPartitionChecks(unittest.TestCase):
    def test_same_source_never_split_between_training_and_test(self):
        groups=json.loads((OUT/'split_groups.json').read_text())
        self.assertEqual(len(groups),305)
        partitions={}
        for x in groups:partitions.setdefault(x['source_group'],set()).add(x['partition'])
        self.assertTrue(all(len(v)==1 for v in partitions.values()))
        self.assertTrue(all(x['partition']=='evaluation_candidate_only' for x in groups))
    def test_key_numerical_results_are_present_in_revised_artifact(self):
        byid={r['task_id']:r for name in ['single_turn_tasks.csv','single_turn_tasks_cn263.csv'] for r in read(OUT/name)}
        expected={
          'self-explanation-prompt-designer__03':['0.008','0.12','0.06'],
          'lesson-builder__03':['1.924'],
          'lesson-builder__cn27_03':['x<-2','x>1'],
          'hinge-question-designer__cn29_06':['c>=1'],
          'lesson-builder__cn30_04':['0','area 1'],
          'project-brief-designer__cn52_04':['ten groups of four','one group of five']}
        for tid,values in expected.items():
            for v in values:self.assertIn(v,byid[tid]['expected_output'],tid)
    def test_math_counterexamples_and_transfer_values(self):
        for x in [-3,-1,0,1,2]:
            self.assertEqual((x-1)/(x+2)>0,x<-2 or x>1)
        for c in [0,1,2]:
            self.assertEqual(1-2+c>=0,c>=1)
        self.assertEqual(sum(1/(k*(k+1)) for k in range(1,2)),1-1/2)
        for n in [3,10,20]:
            self.assertTrue(math.isclose(sum(1/(k*(k+1)) for k in range(1,n+1)),1-1/(n+1)))
        self.assertEqual(abs(3+4j),5)
        self.assertEqual((3+4j)*(3-4j),25)
        self.assertEqual(10*4+5,45)
    def test_compiled_weighted_score_is_used_consistently(self):
        sys.path.insert(0,str(ROOT))
        from repro.judge import score_items
        cases=json.loads((OUT/'evals.json').read_text())['cases']
        case=next(x for x in cases if x['id']=='motivation-diagnostic-task-redesign__01')
        rubric=case['rubric']
        decisions={'items':[{'id':r['id'],'pass':i==0} for i,r in enumerate(rubric)]}
        verdict=score_items(decisions,rubric,primary=case['score_metric'])
        self.assertTrue(math.isclose(verdict['score'],rubric[0]['points']/100))
