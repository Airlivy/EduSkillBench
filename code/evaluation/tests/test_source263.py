import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_source263 import check
from restore_source263 import OUT


class OriginalSourceTests(unittest.TestCase):
    def test_selected_inventory_and_original_files_are_preserved(self):
        result=check()
        self.assertEqual(result['cases'],263)
        self.assertEqual(result['source_documents'],30)
        self.assertEqual(result['equation_objects_retained'],140)
        self.assertFalse(result['auto_scoring_ready'])

    def test_multiple_rubrics_and_broken_heading_are_not_dropped(self):
        docs=json.loads((OUT/'source_documents.json').read_text())
        source=next(d for d in docs.values() if d['source_record']==18)
        rubrics=[s for s in source['sections'] if s['kind']=='rubric']
        self.assertEqual(len(rubrics),2)
        self.assertIn('过程性评价维度',rubrics[0]['text'])
        self.assertIn('结果性评价维度',rubrics[0]['text'])
        self.assertIn('对智能体融合设计的评价',rubrics[1]['text'])
        self.assertIn('反面案例',next(s['text'] for s in source['sections'] if s['kind']=='examples'))

    def test_solution_does_not_leak_into_context_or_become_gold_answer(self):
        cases=json.loads((OUT/'cases.json').read_text())
        for c in cases:
            self.assertEqual(c['expected_output'],'')
            if c['source_record'] in (35,43):
                self.assertTrue(c['solution_sections'])
                self.assertNotIn('解决方案与流程',''.join(s['text'] for s in c['context_sections']))

if __name__=='__main__':unittest.main()
