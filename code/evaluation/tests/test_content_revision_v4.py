import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'code/evaluation'))
from eval_compiler import compile_cases


class ContentRevisionChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'data/revisions/case-review-v4-20260930'
        cls.before=ROOT/'data/revisions/case-review-v3-20260930'
        cls.rows={}
        for name in ['single_turn_tasks.csv','single_turn_tasks_cn263.csv']:
            with (cls.folder/name).open() as f:
                cls.rows.update({r['task_id']:r for r in csv.DictReader(f)})

    def test_frozen_v3_artifacts_remain_unchanged(self):
        manifest=json.loads((self.before/'manifest.json').read_text())
        for name,expected in manifest['artifact_sha256'].items():
            self.assertEqual(hashlib.sha256((self.before/name).read_bytes()).hexdigest(),expected,name)

    def test_complete_binding_and_audit_trail(self):
        cases=json.loads((self.folder/'evals.json').read_text())['cases']
        self.assertEqual(len(cases),305)
        self.assertEqual({c['id'] for c in cases},set(self.rows))
        for c in cases:
            r=self.rows[c['id']]
            self.assertEqual(c['question'],r['context']+'\n\n'+r['user_prompt'])
            self.assertEqual(c['ground_truth'],r['expected_output'])
            self.assertEqual(c['rubric'],json.loads(r['rubric']))
            self.assertTrue(math.isclose(sum(x['points'] for x in c['rubric']),100))
        for delta in json.loads((self.folder/'changes.json').read_text()):
            for field,change in delta['fields'].items():
                self.assertEqual(change['after'],self.rows[delta['task_id']][field])
                self.assertNotEqual(change['before'],change['after'])

    def test_qualifiers_cannot_earn_standalone_repeated_points(self):
        for r in self.rows.values():
            rubric=json.loads(r['rubric'])
            self.assertEqual(len({c['description'] for c in rubric}),len(rubric),r['task_id'])
            for c in rubric:
                self.assertFalse(c['description'].startswith('Judge feasibility within'))
                self.assertFalse(c['description'].startswith('Accept equivalent wording for the five'))

    def test_monopoly_worked_solution_and_boundary_counterexample(self):
        profit=lambda q:(20-q)*q-(4*q+10)
        self.assertEqual(profit(8),54)
        self.assertEqual((profit(0),profit(20)),(-10,-90))
        # Exact identity establishes the global maximum over the whole interval.
        for q in range(21):
            self.assertEqual(profit(q),54-(q-8)**2)
        # MR=MC can be infeasible: P=1-Q, C=2Q => Q=-1/2.
        candidate=(1-2)/2
        self.assertLess(candidate,0)
        self.assertTrue(all((1-q)*q-2*q<=0 for q in [0,.25,.5,.75,1]))

    def test_real_compile_remains_gated_and_preserves_new_rubric(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'not released'):
                compile_cases(self.folder/'single_turn_tasks.csv',d,ROOT/'skills/single_turn')
            result=compile_cases(self.folder/'single_turn_tasks.csv',d,ROOT/'skills/single_turn',review_only=True)
            self.assertEqual(result['eval_cases'],42)
            for p in Path(d).glob('*/evals/evals.json'):
                for c in json.loads(p.read_text())['cases']:
                    self.assertEqual(c['rubric'],json.loads(self.rows[c['id']]['rubric']))


if __name__=='__main__':unittest.main()
