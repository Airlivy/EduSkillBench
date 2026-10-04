import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from repro import judge
from repro.source_protocol import load_release, allowed_labels
from repro.source_runner import run_cell, run_lock, evaluate_native, prompt


class RunIsolationTests(unittest.TestCase):
    def test_second_coordinator_cannot_overwrite_plan_or_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=Path(tmp)/'plan.json'
            plan.write_text('original plan')
            with run_lock(tmp):
                with self.assertRaises(SystemExit):
                    with run_lock(tmp):
                        plan.write_text('overwritten')
                self.assertEqual(plan.read_text(),'original plan')
            with run_lock(tmp):
                pass

    def test_core_transient_failure_waits_for_explicit_retry(self):
        case=dict(question='q',ground_truth='a',judge_model='deepseek-v4-pro',score_metric='weighted',
                  rubric=[dict(id='C1',description='a',points=100)])
        with tempfile.TemporaryDirectory() as tmp, patch('repro.judge.time.sleep'):
            call=Mock(side_effect=judge.JudgeError('http_error',True,{'http_status':503}))
            for _ in range(2):
                with self.assertRaises(judge.JudgeError):
                    judge.evaluate(case,'a',tmp,call,max_attempts=2,require_explicit_retry=True)
            self.assertEqual(call.call_count,2)
            call.side_effect=None
            call.return_value=(json.dumps({'items':[{'id':'C1','pass':True}]}),{'stop_reason':'end_turn'})
            result=judge.evaluate(case,'a',tmp,call,max_attempts=2,require_explicit_retry=True,retry_blocked=True)
            self.assertEqual(result['score'],1)
            self.assertEqual(call.call_count,3)

    def test_changed_generation_input_cannot_replace_failed_record(self):
        _,cases,_=load_release();case=cases[0]
        with tempfile.TemporaryDirectory() as tmp:
            with patch('repro.source_runner.exchange',side_effect=judge.JudgeError('http_error',False)):
                first=run_cell(case,'deepseek-v4-pro','deepseek-v4-pro',tmp)
            self.assertEqual(first['status'],'generation_failed')
            error=Path(tmp)/'deepseek-v4-pro'/case['task_id']/'generation_error.json'
            before=error.read_bytes();changed=copy.deepcopy(case);changed['user_prompt']+='changed'
            with patch('repro.source_runner.exchange') as call:
                result=run_cell(changed,'deepseek-v4-pro','deepseek-v4-pro',tmp,True)
            call.assert_not_called()
            self.assertEqual(result['category'],'ValueError')
            self.assertEqual(error.read_bytes(),before)

    def test_changed_grading_prompt_invalidates_native_cache(self):
        _,cases,_=load_release();case=next(c for c in cases if c['suite']=='advisory')
        raw=json.dumps({'items':[dict(id=r['id'],counterevidence='',level=allowed_labels(r)[0],evidence='E1',reason='对应证据')
                                for r in case['criteria'] if r['id'] in case['applicable_ids']]})
        with tempfile.TemporaryDirectory() as tmp:
            call=Mock(return_value=(raw,{'stop_reason':'end_turn'}))
            evaluate_native(case,'回答','deepseek-v4-pro',tmp,call=call)
            with patch('repro.source_runner.prompt',return_value=prompt(case,'回答')+'changed policy'):
                with self.assertRaises(ValueError):
                    evaluate_native(case,'回答','deepseek-v4-pro',tmp,call=call)
            self.assertEqual(call.call_count,1)


if __name__=='__main__':unittest.main()
