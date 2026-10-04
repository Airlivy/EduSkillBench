import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_source_minimal import revised_cases
from check_source_minimal import check


class MinimalRevisionTests(unittest.TestCase):
    def test_release_scope_and_artifacts(self):
        result=check()
        self.assertEqual(result['changed_cases'],153)
        self.assertFalse(result['auto_scoring_ready'])

    def test_ellipse_examples_not_active_for_other_concepts(self):
        cases,_,_=revised_cases()
        selected=[c for c in cases if c['source_record']==22]
        self.assertEqual(len(selected),9)
        self.assertEqual(selected[0]['user_prompt'],'如何讲透双曲线的概念')
        for c in selected:
            active='\n'.join(s['text'] for s in c['context_sections']+c['rubric_sections'])
            for term in ('椭圆','2a>2c','半焦距','焦点位置'):
                self.assertNotIn(term,active)
            self.assertIn('椭圆',c['reference_only_rubric_sections'][0]['text'])
            self.assertIn('即时检测',active)

    def test_main_variable_method_not_graded_as_menelaus(self):
        cases,_,_=revised_cases()
        c=next(c for c in cases if c['source_record']==25)
        self.assertIn('主元法',c['user_prompt'])
        active='\n'.join(s['text'] for s in c['context_sections']+c['rubric_sections'])
        for term in ('梅涅劳斯','截线','三点共线','面积法'):
            self.assertNotIn(term,active)
        for term in ('知识引入','原理推导','条件辨析','认知匹配'):
            self.assertIn(term,active)
        self.assertIn('梅涅劳斯',c['reference_only_rubric_sections'][0]['text'])

    def test_all_math_sources_keep_questions_and_dimension_counts(self):
        cases,_,spec=revised_cases()
        self.assertEqual({r['source_record'] for r in spec['topic_alignments']},set(range(22,32)))
        self.assertEqual(sum(c['source_record'] in range(22,32) for c in cases),71)
        c=next(c for c in cases if c['task_id']=='retrieval-practice-generator__cn23_02')
        self.assertNotIn('非集合语言',c['rubric_sections'][0]['text'])
        c=next(c for c in cases if c['task_id']=='lesson-builder__cn28_02')
        self.assertNotIn('三个角',c['rubric_sections'][0]['text'])

    def test_parent_support_not_ruled_out_by_background(self):
        cases,_,_=revised_cases()
        c=next(c for c in cases if c['task_id']=='self-efficacy-builder-sequence__cn35_05')
        self.assertNotIn('必须在缺乏外部支援',c['context_sections'][0]['text'])
        self.assertIn('⑥ 家校合作鼓励',c['rubric_sections'][0]['text'])
        self.assertNotIn('① 抗拒成因分析',c['rubric_sections'][0]['text'])

    def test_grade_six_and_safety_demonstration_allowed(self):
        cases,_,_=revised_cases()
        c=next(c for c in cases if c['task_id']=='adaptive-hint-sequence-designer__cn53_10')
        active='\n'.join(s['text'] for s in c['context_sections']+c['rubric_sections'])
        self.assertNotIn('1-5 年级',active)
        self.assertIn('1—6 年级',active)
        self.assertIn('制止危险操作',active)

if __name__=='__main__':unittest.main()
