import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'code/evaluation'))
from senior_structure_checks import structural


class SeniorStructureChecks(unittest.TestCase):
    def test_new_metadata_accepted_but_lost_weights_detected(self):
        rubric=[{'id':f'C{i+1}','criterion':str(i),'description':f'Check {i}','points':100/6} for i in range(6)]
        row={'task_id':'example__01','skill_id':'example','context':'Context',
             'user_prompt':'Question','expected_output':'Reference','rubric':json.dumps(rubric)}
        case={'id':row['task_id'],'question':'Context\n\nQuestion','ground_truth':'Reference',
              'expected_behavior':[c['description'] for c in rubric],'rubric':rubric,'status':'review_only','score_metric':'weighted'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);skill=root/'example';(skill/'evals').mkdir(parents=True)
            (skill/'SKILL.md').write_text('Example')
            p=skill/'evals/evals.json'
            p.write_text(json.dumps({'skill_name':'example','cases':[case]}))
            issues,extra=structural([row],root)
            self.assertFalse(any(issues.values()));self.assertEqual(extra,[])
            case['rubric'][0]['points']=1
            p.write_text(json.dumps({'skill_name':'example','cases':[case]}))
            issues,_=structural([row],root)
            self.assertIn('weighted rubric mismatch',issues['example__01'])


if __name__=='__main__':unittest.main()
