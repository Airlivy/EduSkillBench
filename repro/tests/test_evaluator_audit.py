import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from repro import judge
from repro.source_protocol import load_release
from repro.source_runner import evaluate_native, run_cell


class EvaluatorAuditTests(unittest.TestCase):
    def setUp(self):
        self.case = dict(question='2+2?', ground_truth='4', judge_model='deepseek-v4-pro',
                         score_metric='weighted', rubric=[dict(id='C1', points=100, description='4', critical=True)])
        self.text = json.dumps({'items':[{'id':'C1', 'pass':True}]})

    def test_abnormal_stop_cannot_be_committed_as_valid_score(self):
        for stop in ('tool_use', 'refusal', None):
            with self.subTest(stop=stop), tempfile.TemporaryDirectory() as tmp:
                call=Mock(return_value=(self.text, {'stop_reason':stop}))
                with self.assertRaises(judge.JudgeError):
                    judge.evaluate(self.case, '4', tmp, call, max_attempts=2)
                self.assertEqual(call.call_count, 2)
                self.assertFalse((Path(tmp)/'judge_result.json').exists())
                self.assertFalse((Path(tmp)/'reward.json').exists())

    def test_total_deadline_with_partial_text_is_not_repeated(self):
        error=judge.JudgeError('transport', True, {'timeout_kind':'total_deadline','text_chars':40})
        with tempfile.TemporaryDirectory() as tmp:
            call=Mock(side_effect=error)
            for _ in range(2):
                with self.assertRaises(judge.JudgeError):
                    judge.evaluate(self.case, '4', tmp, call, max_attempts=2, stop_on_deadline=True)
            self.assertEqual(call.call_count, 1)

    def test_native_retry_cannot_overwrite_different_failed_input(self):
        _, cases, _=load_release()
        case=next(c for c in cases if c['suite']=='advisory')
        with tempfile.TemporaryDirectory() as tmp:
            first=Mock(side_effect=judge.JudgeError('http_error', False))
            with self.assertRaises(judge.JudgeError):
                evaluate_native(case, '原答案', 'deepseek-v4-pro', tmp, call=first)
            saved=(Path(tmp)/'error.json').read_bytes()
            next_call=Mock()
            with self.assertRaises(ValueError):
                evaluate_native(case, '另一个答案', 'deepseek-v4-pro', tmp, call=next_call, retry_failed=True)
            next_call.assert_not_called()
            self.assertEqual(saved, (Path(tmp)/'error.json').read_bytes())

    def test_core_summary_keeps_critical_failure_and_binds_execution(self):
        _, cases, _=load_release();case=cases[0]
        verdict=dict(score=.8, critical_pass=False)
        with tempfile.TemporaryDirectory() as tmp, patch('repro.source_runner.exchange',return_value=('answer',{})), patch('repro.source_runner.judge.evaluate',return_value=verdict) as call:
            result=run_cell(case, 'deepseek-v4-pro', 'deepseek-v4-pro', tmp)
            self.assertEqual(result['score'], .8)
            self.assertIs(result['critical_pass'], False)
            self.assertEqual(call.call_args.kwargs['max_attempts'],2)
            self.assertTrue(call.call_args.kwargs['stop_on_deadline'])
            self.assertIn('execution_options',call.call_args.args[0])
            self.assertIn('endpoint',call.call_args.args[0])

    def test_native_summary_preserves_non_numeric_grades(self):
        _, cases, _=load_release();case=next(c for c in cases if c['suite']=='advisory')
        verdict=dict(score=None,score_interval=None,items=[dict(id='D1',level='不合格（C）',counterevidence='E1')])
        with tempfile.TemporaryDirectory() as tmp, patch('repro.source_runner.exchange',return_value=('answer',{})), patch('repro.source_runner.evaluate_native',return_value=verdict):
            result=run_cell(case,'deepseek-v4-pro','deepseek-v4-pro',tmp)
            self.assertIsNone(result['score'])
            self.assertEqual(result['criterion_levels'],{'D1':'不合格（C）'})
            self.assertTrue(result['review_required'])
            self.assertEqual(result['counterevidence_review_ids'],['D1'])


if __name__=='__main__':unittest.main()
