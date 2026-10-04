import tempfile
import unittest
from concurrent.futures import Future
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from repro.calibration.stress_concurrency import request, summarize
from repro.judge import JudgeError
from repro.source_runner import schedule_cells


class ConcurrencyStressTests(unittest.TestCase):
    def test_scheduler_caps_slow_models_and_does_not_starve_fast_models(self):
        submitted=[]
        class Pool:
            def submit(self,fn,case,model,*args):
                f=Future();f.payload=(case,model);submitted.append(f)
                active=Counter(x.payload[1] for x in submitted if not x.done())
                assert sum(active.values())<=6
                assert all(active[m]<=2 for m in ('glm-5.3','glm-5.3-flash','kimi-k2.7-code'))
                return f
        def finish_one(futures,**kwargs):
            # Keep early slow requests waiting while later requests complete.
            f=list(futures)[-1];f.set_result(f.payload)
            return {f},set(futures)-{f}
        models=['glm-5.3','glm-5.3-flash','kimi-k2.7-code','deepseek-v4-pro']
        with patch('repro.source_runner.wait',side_effect=finish_one):
            results=list(schedule_cells(Pool(),list(range(5)),models,'judge','unused',6))
        self.assertEqual(set(results),{(i,m) for i in range(5) for m in models})
        self.assertEqual(len(results),20)
        self.assertEqual([f.payload[1] for f in submitted[:4]],models)
        submitted.clear()
        with patch('repro.source_runner.wait',side_effect=finish_one):
            list(schedule_cells(Pool(),list(range(2)),models,'judge','unused',1))
        self.assertEqual([f.payload[1] for f in submitted[:4]],models)

    def test_failed_request_is_not_retried_or_counted_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            job={'dest':directory,'model':'deepseek-v4-pro','stage':'generation',
                 'task_id':'test','prompt':'test'}
            with patch('repro.calibration.stress_concurrency.judge.call_judge',
                       side_effect=JudgeError('http_error',True,{'http_status':429})) as call:
                record=request(job)
            self.assertEqual(call.call_count,1)
            self.assertEqual(record['status'],'failed')
            self.assertTrue((Path(directory)/'result.json').exists())
            report=summarize([record],10,1)
            self.assertEqual(report['successful_requests_per_minute'],0)
            self.assertEqual(report['errors'][0]['http_status'],429)

    def test_incomplete_generation_does_not_pass_stress(self):
        with tempfile.TemporaryDirectory() as directory:
            job={'dest':directory,'model':'deepseek-v4-pro','stage':'generation',
                 'task_id':'test','prompt':'test'}
            with patch('repro.calibration.stress_concurrency.judge.call_judge',
                       return_value=('partial',{'stop_reason':'max_tokens'})):
                record=request(job)
            self.assertEqual(record['category'],'incomplete_response')
            self.assertEqual((Path(directory)/'raw.txt').read_text(),'partial')

if __name__=='__main__':unittest.main()
