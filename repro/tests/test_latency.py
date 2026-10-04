import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from repro import judge


class LatencyTests(unittest.TestCase):
    def env(self):
        return patch.dict(os.environ, {'ANTHROPIC_API_KEY':'secret-key', 'ANTHROPIC_BASE_URL':'https://example.invalid/v1'}, clear=True)

    def test_progress_survives_timeout_without_recording_thought_text(self):
        thought = 'private-thought-content'
        class Stream:
            headers = {'Content-Type':'text/event-stream', 'x-request-id':'header-id'}
            status = 200
            def __enter__(self):return self
            def __exit__(self, *args):return False
            def __iter__(self):
                for event in [
                    {'type':'message_start','message':{'id':'message-id','usage':{'input_tokens':40}}},
                    {'type':'content_block_delta','index':0,'delta':{'type':'thinking_delta','thinking':thought}},
                ]:
                    yield 'data: '+json.dumps(event)+'\n'
                    yield '\n'
                raise TimeoutError('request deadline')
        with tempfile.TemporaryDirectory() as tmp, self.env(), patch('urllib.request.urlopen',return_value=Stream()):
            path=Path(tmp)/'trace.json'
            with self.assertRaises(judge.JudgeError) as ctx:
                judge.call_judge('secret-prompt','m',telemetry_path=path)
            metadata=ctx.exception.metadata
            self.assertEqual(metadata['stage'],'receiving_thinking')
            self.assertEqual(metadata['request_id'],'message-id')
            self.assertEqual(metadata['thinking_chars'],len(thought))
            self.assertEqual(metadata['text_chars'],0)
            self.assertEqual(metadata['timeout_kind'],'total_deadline')
            saved=path.read_text()
            for secret in (thought,'secret-key','secret-prompt'):
                self.assertNotIn(secret,saved)
            self.assertEqual(json.loads(saved)['events']['content_block_delta'],1)

    def test_waiting_for_headers_is_distinct_from_stalled_body(self):
        with self.env(), patch('urllib.request.urlopen',side_effect=TimeoutError('socket timed out')):
            with self.assertRaises(judge.JudgeError) as ctx:
                judge.call_judge('q','m')
            self.assertEqual(ctx.exception.metadata['stage'],'awaiting_headers')
            self.assertNotIn('headers_seconds',ctx.exception.metadata)

    def test_ping_is_not_model_content(self):
        payload={'max_tokens':16000,'thinking':{'type':'enabled','budget_tokens':8000},'stream':True}
        trace=judge.RequestTrace('m','q',payload)
        response=io.StringIO('data: {"type":"ping"}\n\ndata: {"type":"message_stop"}\n\n')
        response.headers={'Content-Type':'text/event-stream'}
        trace.headers(response)
        judge.read_provider_response(response,trace)
        self.assertEqual(trace.data['events']['ping'],1)
        self.assertNotIn('first_content_seconds',trace.data)
        self.assertEqual(trace.data['thinking_chars'],0)

    def test_deadlines_distinguish_headers_idle_content_and_total(self):
        payload={'max_tokens':16000,'thinking':{'type':'enabled','budget_tokens':8000},'stream':True}
        trace=judge.RequestTrace('m','q',payload)
        deadline=judge.ProgressDeadline(trace,judge.DEFAULT_TIMEOUTS)
        self.assertEqual(deadline.next_expiry(),(90.0,'headers_timeout'))
        trace.data.update(headers_seconds=3, last_line_seconds=20, last_content_seconds=10)
        self.assertEqual(deadline.next_expiry(),(80.0,'stream_idle_timeout'))
        # Continuous pings cannot postpone the model-content deadline.
        trace.data['last_line_seconds']=185
        self.assertEqual(deadline.next_expiry(),(190.0,'content_idle_timeout'))
        # A working model past 180 seconds keeps its request, not a fresh retry.
        trace.data.update(last_line_seconds=200,last_content_seconds=200)
        self.assertEqual(deadline.next_expiry(),(260.0,'stream_idle_timeout'))
        trace.data.update(last_line_seconds=599,last_content_seconds=599)
        self.assertEqual(deadline.next_expiry(),(600.0,'total_deadline'))

    def test_live_deadline_stops_a_read_without_more_events(self):
        class Stalled(io.StringIO):
            headers={'Content-Type':'text/event-stream'}
            status=200
            def __iter__(self):
                time.sleep(.2)
                return iter(())
        limits={'headers':.1,'idle':.02,'content_idle':.1,'total':.5}
        with self.env(), patch('urllib.request.urlopen',return_value=Stalled()):
            with self.assertRaises(judge.JudgeError) as ctx:
                judge.call_judge('q','m',timeouts=limits)
        self.assertEqual(ctx.exception.metadata['timeout_kind'],'stream_idle_timeout')
        self.assertEqual(ctx.exception.metadata['stage'],'awaiting_body')

    def test_header_deadline_interrupts_before_response(self):
        def blocked(*a,**kw):time.sleep(.2)
        limits={'headers':.02,'idle':.1,'content_idle':.1,'total':.5}
        with self.env(), patch('urllib.request.urlopen',side_effect=blocked):
            with self.assertRaises(judge.JudgeError) as ctx:
                judge.call_judge('q','m',timeouts=limits)
        self.assertEqual(ctx.exception.metadata['timeout_kind'],'headers_timeout')

    def test_evaluate_writes_attempt_trace_without_false_zero(self):
        case={'question':'q','ground_truth':'a','judge_model':'m','score_metric':'weighted',
              'rubric':[{'id':'C1','description':'correct','points':1}]}
        with tempfile.TemporaryDirectory() as tmp, self.env(), patch('urllib.request.urlopen',side_effect=TimeoutError), patch('repro.judge.time.sleep'):
            with self.assertRaises(judge.JudgeError):judge.evaluate(case,'answer',tmp)
            path=Path(tmp)
            self.assertEqual(len(list(path.glob('judge_trace_*.json'))),3)
            self.assertEqual(len(list(path.glob('judge_failure_*.json'))),3)
            self.assertFalse((path/'reward.json').exists())

    def test_only_verified_ark_hostname_bypasses_proxy(self):
        with patch('urllib.request.build_opener') as build:
            opened, route=judge.request_transport('https://ark.cn-beijing.volces.com/api/plan/v1/messages')
            self.assertEqual(route,'direct_ark')
            self.assertEqual(build.call_args.args[0].proxies,{})
            self.assertEqual(opened,build.return_value.open)
            for url in ('https://example.invalid/v1','https://ark.cn-beijing.volces.com.example.invalid/v1'):
                opened,route=judge.request_transport(url)
                self.assertEqual(route,'environment')
                self.assertEqual(opened,judge.urllib.request.urlopen)

    def test_tls_failure_is_not_mislabeled_model_thinking_timeout(self):
        import ssl
        import urllib.error
        failure=urllib.error.URLError(ssl.SSLEOFError(8,'TLS ended'))
        with self.env(), patch('urllib.request.urlopen',side_effect=failure):
            with self.assertRaises(judge.JudgeError) as ctx:
                judge.call_judge('q','m')
        self.assertEqual(ctx.exception.metadata['network_error_kind'],'tls_error')
        self.assertEqual(ctx.exception.metadata['stage'],'awaiting_headers')
        self.assertEqual(ctx.exception.metadata['thinking_chars'],0)


if __name__=='__main__':unittest.main()
