import unittest
from pathlib import Path
from repro.retry_after_run import select_failed, merged_rows


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'model':'m','task_id':'a','status':'evaluated','score':1},
                   {'model':'m','task_id':'b','status':'generation_failed','score':None}]
        self.plan={'models':['m'],'task_ids':['a','b']}

    def test_waits_for_complete_unique_coverage(self):
        for rows in (self.rows[:1],[self.rows[0],self.rows[0]]):
            with self.assertRaises(ValueError):select_failed({'results':rows},self.plan)
        self.assertEqual(select_failed({'results':self.rows},self.plan),[self.rows[1]])

    def test_preserves_success_and_tracks_new_result_even_if_score_is_lower(self):
        retry={**self.rows[1],'status':'evaluated','score':0}
        rows=merged_rows(self.rows,[retry],Path('/base'),Path('/retry'))
        self.assertEqual(rows[0]['score'],1)
        self.assertEqual(rows[0]['run_source'],'original_6144')
        self.assertEqual(rows[1]['score'],0)
        self.assertEqual(rows[1]['run_source'],'retry_16000')
        with self.assertRaises(ValueError):merged_rows(self.rows,[self.rows[0]],Path('/base'),Path('/retry'))

    def test_retry_failure_stays_missing_not_zero(self):
        rows=merged_rows(self.rows,[self.rows[1]],Path('/base'),Path('/retry'))
        self.assertIsNone(rows[1]['score'])
        self.assertEqual(rows[1]['status'],'generation_failed')

    def test_third_round_preserves_original_paths_and_failure_history(self):
        first=merged_rows(self.rows,[self.rows[1]],Path('/base'),Path('/retry'))
        third=merged_rows(first,[{**self.rows[1],'status':'evaluated','score':0}],
                          Path('/retry'),Path('/third'),run_label='retry_300s')
        self.assertEqual(third[0],first[0])
        self.assertEqual(third[1]['original_directory'],'/base/m/b')
        self.assertEqual(third[1]['attempt_history'][-1]['directory'],'/retry/m/b')
        self.assertEqual(third[1]['result_directory'],'/third/m/b')
