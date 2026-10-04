import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from repro import paired_runner as paired,source_runner as runner
from repro.source_protocol import load_release


class PairedTests(unittest.TestCase):
    def test_all_305_pairs_have_same_question_and_complete_skill_materials(self):
        _,cases,_=load_release();inventory,bundles=paired.skill_inventory(cases)
        self.assertEqual(len(inventory),14);self.assertEqual(len(inventory['lesson-builder']),11)
        for case in cases:
            before=copy.deepcopy(case);base=paired.make_prompt(case,'baseline',bundles);skill=paired.make_prompt(case,'with-skill',bundles)
            self.assertEqual(base,case['context']+'\n\n'+case['user_prompt'])
            self.assertTrue(skill.startswith(base+'\n\n## Required procedure'))
            for name in inventory[paired.skill_id(case)]:self.assertIn('### Skill file: '+name+'\n',skill)
            self.assertEqual(case,before)

    def test_work_passes_identical_grading_case_but_different_generation_prompt(self):
        case={'task_id':'x','suite':'core'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(runner,'run_cell',return_value={'task_id':'x','model':'m','status':'evaluated','score':1}) as call:
            (Path(tmp)/'with-skill/m/x').mkdir(parents=True)
            result=paired.work(case,'m','with-skill','j',tmp,'question plus skill')
            self.assertIs(call.call_args.args[0],case)
            self.assertEqual(call.call_args.kwargs['generation_prompt'],'question plus skill')
            self.assertEqual(call.call_args.args[3],Path(tmp)/'with-skill')
            self.assertEqual(result['condition'],'with-skill')

    def test_gate_requires_every_model_condition_and_both_scoring_protocols(self):
        rows=[{'model':m,'condition':c,'suite':s,'status':'evaluated'} for m in paired.MODELS for c in paired.CONDITIONS for s in ('core','advisory')]
        self.assertTrue(paired.pilot_ok(rows))
        self.assertFalse(paired.pilot_ok([r for r in rows if r['model']!='glm-5.3']))
        self.assertFalse(paired.pilot_ok([r for r in rows if r['suite']!='advisory']))
