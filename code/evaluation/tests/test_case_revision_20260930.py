"""Offline checks; these do not constitute independent subject or LLM acceptance."""
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'data/revisions/case-review-20260930'

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

class RevisionChecks(unittest.TestCase):
    def test_preservation_and_exact_change_ledger(self):
        manifest=json.loads((OUT/'manifest.json').read_text())
        changes=json.loads((OUT/'changes.json').read_text())
        ledger={(x['dataset'],x['task_id']):x for x in changes}
        for name,sha in manifest['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest(),sha)
        for ds,name,count in [('original42','single_turn_tasks.csv',42),('cn263','single_turn_tasks_cn263.csv',263)]:
            before=rows(ROOT/'data'/name);after=rows(OUT/name)
            self.assertEqual(len(after),count)
            self.assertEqual([r['task_id'] for r in before],[r['task_id'] for r in after])
            for old,new in zip(before,after):
                diff={k:{'before':old[k],'after':new[k]} for k in old if old[k]!=new[k]}
                self.assertEqual(diff,ledger.get((ds,old['task_id']),{}).get('fields',{}))
                if diff:
                    rubric=json.loads(new['rubric'])
                    self.assertEqual(sum(x['points'] for x in rubric),100)
                    self.assertTrue(all(new[k] for k in old))
        self.assertEqual(len(rows(OUT/'review_inventory.csv')),305)

    def test_evidence_hashes(self):
        evidence=json.loads((OUT/'result_evidence.json').read_text())
        self.assertEqual(len(evidence),46)
        for item in evidence:
            self.assertEqual(hashlib.sha256((ROOT/item['source']).read_bytes()).hexdigest(),item['source_sha256'])

    def test_flux_by_independent_midpoint_integration(self):
        def flux(x):
            width=.2;n=10000;dx=width/n
            return .5*sum(.4*(x-width+(i+.5)*dx)*dx for i in range(n))
        self.assertAlmostEqual(flux(.3),.008,places=10)
        derivative=(flux(.30001)-flux(.29999))/.00002
        self.assertAlmostEqual(abs(derivative*3),.12,places=8)
        self.assertAlmostEqual(abs(derivative*3)/2,.06,places=8)

    def test_sir_assumptions_and_nonuniqueness(self):
        r=math.log(80/10)/9
        self.assertAlmostEqual(1+r/.25,1.924196240746594,places=10)
        self.assertNotEqual(1+r*4,1+r*6)

    def test_counting_by_enumeration(self):
        compositions=[x for x in itertools.product(range(5),repeat=3) if sum(x)==4]
        self.assertEqual(len(compositions),15)
        self.assertEqual(sum(all(v>0 for v in x) for x in compositions),3)
        assignments=list(itertools.product(range(2),repeat=3))
        self.assertEqual(len(assignments),8)
        partitions={tuple(sorted(tuple(i for i,v in enumerate(x) if v==j) for j in set(x))) for x in assignments}
        self.assertEqual(len(partitions),4)
        self.assertEqual(sum(len(x)==2 for x in partitions),3)
        for n,expected in [(3,2),(4,9)]:
            self.assertEqual(sum(all(i!=v for i,v in enumerate(p)) for p in itertools.permutations(range(n))),expected)
        permutations=list(itertools.permutations('ABCDE'))
        adjacent=sum(abs(p.index('A')-p.index('B'))==1 for p in permutations)
        self.assertEqual((adjacent,len(permutations)-adjacent),(48,72))
        circles={min(p[i:]+p[:i] for i in range(4)) for p in itertools.permutations(range(4))}
        self.assertEqual(len(circles),6)
        divisions={tuple(sorted((tuple(c),tuple(i for i in range(6) if i not in c)))) for c in itertools.combinations(range(6),3)}
        self.assertEqual(len(divisions),10)

    def test_other_numeric_anchors(self):
        polynomial={0:1}
        for _ in range(3):
            new={}
            for power,coefficient in polynomial.items():
                new[power]=new.get(power,0)-coefficient
                new[power+1]=new.get(power+1,0)+2*coefficient
            polynomial=new
        self.assertEqual(polynomial,{0:-1,1:6,2:-12,3:8})
        self.assertEqual(50-(3*2+5*2+2*3),28)
        for k in range(601):
            x=k/100
            self.assertLessEqual(x*(6-x),9)
        b=math.degrees(math.asin(.8))
        self.assertTrue(30+b<180 and 30+(180-b)<180)
        self.assertEqual(30+40+40,110)

if __name__=='__main__':
    unittest.main()
