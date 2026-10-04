import os
import subprocess
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import judge
import protocol as P
import runner
import rejudge
import prepare
import finalize_review
import profiles


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task_id, self.task = next(iter(P.load_tasks().items()))
        self.model = P.MODELS[0]
        self.case = P.make_case(self.task, self.model, 'equal')
        self.answer = json.dumps({'items': [{'id': r['id'], 'pass': False} for r in self.case['rubric']]})

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_retries_but_truncation_stops_without_false_zero(self):
        responses = iter([('', {'block_types': ['thinking']}),
                          (self.answer, {'stop_reason': 'max_tokens'}), self.answer])
        calls = []
        def call(*args):
            calls.append(args)
            return next(responses)
        with self.assertRaisesRegex(judge.JudgeError, 'output_truncated'):
            judge.evaluate(self.case, 'answer', self.root, call)
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.root/'reward.json').exists())
        reasons = [json.loads(p.read_text())['category'] for p in self.root.glob('judge_failure_*.json')]
        self.assertCountEqual(reasons, ['empty_text', 'output_truncated'])
        self.assertFalse(json.loads((self.root/'judge_error.json').read_text())['retryable'])

    def test_thinking_exhaustion_is_one_call_with_specific_cause(self):
        from unittest.mock import Mock
        call=Mock(return_value=('',{'stop_reason':'max_tokens','block_types':['thinking']}))
        with self.assertRaises(judge.JudgeError) as caught:
            judge.evaluate(self.case,'answer',self.root,call)
        self.assertEqual(call.call_count,1)
        self.assertEqual(caught.exception.metadata['failure_cause'],'thinking_exhausted_output')
        self.assertFalse((self.root/'reward.json').exists())
        # A resumed batch must not silently issue the same expensive request again.
        with self.assertRaises(judge.JudgeError) as resumed:
            judge.evaluate(self.case,'answer',self.root,call)
        self.assertTrue(resumed.exception.metadata['retry_suppressed'])
        self.assertEqual(call.call_count,1)
        with self.assertRaises(judge.JudgeError):
            judge.evaluate(self.case,'answer',self.root,call,retry_blocked=True)
        self.assertEqual(call.call_count,2)

    def test_changed_answer_is_not_blocked_by_previous_exhaustion(self):
        with self.assertRaises(judge.JudgeError):
            judge.evaluate(self.case,'old answer',self.root,lambda *a:('',{'stop_reason':'max_tokens'}))
        result=judge.evaluate(self.case,'new answer',self.root,lambda *a:self.answer)
        self.assertEqual(result['score'],0)
        self.assertFalse((self.root/'judge_error.json').exists())

    def test_thinking_deadline_stops_but_network_retry_is_preserved(self):
        from unittest.mock import Mock
        error=judge.JudgeError('transport',True,{'timeout_kind':'total_deadline','thinking_chars':100,'text_chars':0})
        call=Mock(side_effect=error)
        with self.assertRaises(judge.JudgeError) as caught:
            judge.evaluate(self.case,'answer',self.root,call)
        self.assertEqual(call.call_count,1)
        self.assertEqual(caught.exception.metadata['failure_cause'],'thinking_exceeded_deadline')

    def test_exhausted_empty_has_no_reward_and_has_reason(self):
        with self.assertRaisesRegex(judge.JudgeError, 'empty_text'):
            judge.evaluate(self.case, 'answer', self.root, lambda *a: '')
        self.assertEqual(len(list(self.root.glob('judge_failure_*.json'))), 3)
        self.assertFalse((self.root/'reward.json').exists())

    def test_auth_does_not_retry_or_expose_server_body(self):
        error = urllib.error.HTTPError('https://example.invalid', 401, 'secret-body', {}, None)
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-secret', 'ANTHROPIC_BASE_URL': 'https://example.invalid'}):
            with patch('urllib.request.urlopen', side_effect=error) as call:
                with self.assertRaisesRegex(judge.JudgeError, 'authentication'):
                    judge.evaluate(self.case, 'answer', self.root)
                self.assertEqual(call.call_count, 1)
        logs = '\n'.join(p.read_text() for p in self.root.glob('*.json'))
        self.assertNotIn('test-secret', logs)
        self.assertNotIn('secret-body', logs)
        self.assertIn('401', logs)

    def test_transport_retry_is_one_layer_only(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test', 'ANTHROPIC_BASE_URL': 'https://example.invalid'}):
            with patch('urllib.request.urlopen', side_effect=TimeoutError) as call, patch('judge.time.sleep'):
                with self.assertRaisesRegex(judge.JudgeError, 'transport'):
                    judge.evaluate(self.case, 'answer', self.root)
                self.assertEqual(call.call_count, 3)

    def test_provider_metadata_and_multiple_text_blocks(self):
        data = {'id': 'request-1', 'stop_reason': 'end_turn', 'usage': {'output_tokens': 10},
                'content': [{'type': 'thinking', 'thinking': 'internal'},
                            {'type': 'text', 'text': 'a'}, {'type': 'text', 'text': 'b'}]}
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test', 'ANTHROPIC_BASE_URL': 'https://example.invalid'}):
            with patch('urllib.request.urlopen', return_value=io.StringIO(json.dumps(data))):
                text, metadata = judge.call_judge('q', 'm')
        self.assertEqual(text, 'a\nb')
        self.assertEqual(metadata['request_id'], 'request-1')
        self.assertEqual(metadata['block_types'], ['thinking', 'text', 'text'])
        self.assertNotIn('internal', json.dumps(metadata))

    def test_fenced_whole_json_accepted_partial_not_salvaged(self):
        self.assertEqual(judge.decode_verdict('```json\n'+self.answer+'\n```'), json.loads(self.answer))
        with self.assertRaises(ValueError):
            judge.decode_verdict(self.answer[:-1])

    def test_interrupted_reward_commit_resumes_without_new_call(self):
        with patch('judge.emit_rewards', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                judge.evaluate(self.case, 'answer', self.root, lambda *a: self.answer)
        self.assertTrue((self.root/'judge_result.json').exists())
        result = judge.evaluate(self.case, 'answer', self.root, lambda *a: self.fail('Must reuse verdict'))
        self.assertEqual(result['score'], 0)
        self.assertTrue((self.root/'reward.txt').exists())
        with self.assertRaisesRegex(judge.JudgeError, 'input_mismatch'):
            judge.evaluate(self.case, 'changed answer', self.root)

    def test_corrupt_cached_score_not_reused(self):
        judge.evaluate(self.case, 'answer', self.root, lambda *a: self.answer)
        path = self.root/'judge_result.json'
        data = json.loads(path.read_text()); data['score'] = 1
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(judge.JudgeError, 'saved_verdict_invalid'):
            judge.cached_verdict(self.case, 'answer', self.root)

    def test_evidence_keeps_middle_and_tools_excludes_thoughts(self):
        trace = self.root/'acp_trajectory.jsonl'
        rows = [{'type': 'agent_thought', 'text': 'x'*250000},
                {'type': 'agent_message', 'text': 'middle answer'},
                {'type': 'tool_call', 'content': ['artifact']}]
        trace.write_text('\n'.join(json.dumps(r) for r in rows))
        evidence = judge.read_trajectory(self.root)
        self.assertIn('middle answer', evidence)
        self.assertIn('artifact', evidence)
        self.assertNotIn('x'*100, evidence)
        trace.write_text(json.dumps({'type': 'agent_message', 'text': 'x'*210000}))
        with self.assertRaisesRegex(judge.JudgeError, 'evidence_too_large'):
            judge.read_trajectory(self.root)

    def make_run(self):
        skill = self.task['skill_id']
        run = self.root/f'corrected-2-{self.model}'/'skill-eval'/skill/'opencode'/'baseline'/'2026-09-29'/f'{self.task_id}__abcdef'
        (run/'trajectory').mkdir(parents=True)
        (run/'trajectory/acp_trajectory.jsonl').write_text(json.dumps({'type': 'agent_message', 'text': 'answer'}))
        (run/'result.json').write_text(json.dumps({'model': 'ark/'+self.model, 'verifier_error': 'judge failed', 'rewards': None}))
        return run

    def test_runner_recovers_score_without_modifying_answer_or_result(self):
        run = self.make_run(); original = (run/'result.json').read_bytes()
        real = judge.evaluate
        with patch('judge.evaluate', side_effect=lambda c,t,d: real(c,t,d,lambda *a:self.answer)):
            self.assertTrue(runner.recover_scoring(run/'result.json', self.case))
        self.assertEqual((run/'result.json').read_bytes(), original)
        report = P.inspect_model(self.root/f'corrected-2-{self.model}', self.model, {self.task_id:self.task})
        picked = report['picked'][(self.task['skill_id'], self.task_id, 'baseline')]
        self.assertTrue(picked['valid'])
        self.assertEqual(picked['reward'], 0)
        self.assertTrue(picked['recovery_sha256'])
        (run/'trajectory/acp_trajectory.jsonl').write_text(json.dumps({'type':'agent_message','text':'changed'}))
        report = P.inspect_model(self.root/f'corrected-2-{self.model}', self.model, {self.task_id:self.task})
        self.assertFalse(report['valid'])

    def test_execution_failure_is_not_recovered(self):
        run = self.make_run()
        data = json.loads((run/'result.json').read_text()); data['error'] = 'timeout'
        (run/'result.json').write_text(json.dumps(data))
        self.assertFalse(runner.recover_scoring(run/'result.json', self.case))
        self.assertFalse((run/'scoring_recovery').exists())

    def test_review_resume_only_scores_pending_and_stops_on_auth(self):
        rows = []
        for i in range(3):
            trace = self.root/f'trace-{i}'; trace.mkdir()
            (trace/'acp_trajectory.jsonl').write_text(json.dumps({'type':'agent_message','text':str(i)}))
            rows.append({'model':self.model, 'task_id':str(i), 'condition':'baseline',
                         'trajectory':str(trace), 'case':self.case})
        manifest = {'plan':rows,'blocked':[], 'expected_cells':3}
        out = self.root/'review';out.mkdir()
        calls=[]
        def evaluator(c,t,d):
            calls.append(d)
            return judge.evaluate(c,t,d,lambda *a:self.answer)
        self.assertEqual(rejudge.execute_review(manifest,out,limit=1,evaluator=evaluator),1)
        self.assertEqual(len(calls),1)
        def auth(*a): raise judge.JudgeError('authentication')
        with patch('builtins.print'):
            self.assertEqual(rejudge.execute_review(manifest,out,evaluator=auth),1)
        self.assertEqual(json.loads((out/'status.json').read_text())['scored'],1)
        self.assertEqual(rejudge.execute_review(manifest,out,evaluator=evaluator),0)
        self.assertEqual(len(calls),3)
        self.assertEqual(rejudge.execute_review(manifest,out,evaluator=lambda *a:self.fail('cached')),0)

    def test_review_summary_only_compares_matched_new_verdicts(self):
        rows = []
        for tid, cond in [('one__01','baseline'), ('one__01','with-skill'), ('one__02','baseline')]:
            trace = self.root/(tid+cond); trace.mkdir()
            (trace/'acp_trajectory.jsonl').write_text(json.dumps({'type':'agent_message','text':'answer'}))
            row = {'model':self.model,'task_id':tid,'condition':cond,'case':self.case,'trajectory':str(trace)}
            rows.append(row)
            judge.evaluate(self.case,judge.read_trajectory(trace),self.root/'review'/self.model/tid/cond,
                           lambda *a:self.answer)
        manifest={'plan':rows,'blocked':[], 'expected_cells':4, 'metric':'equal'}
        complete, overall, skills, ledger = finalize_review.summarize(manifest,self.root/'review')
        self.assertFalse(complete)
        self.assertEqual(overall[0]['paired_tasks'],1)
        self.assertEqual(len(ledger),3)
        self.assertEqual(overall[0]['score_baseline'],0)

    def test_education_profile_frozen_and_same_for_both_conditions(self):
        dest=self.root/'prepared'
        manifest=prepare.build(dest,{self.task_id:self.task},[self.model],system_profile='education-single-turn')
        self.assertEqual(manifest['system_profile'],'education-single-turn')
        self.assertEqual(json.loads((dest/'opencode-config.json').read_text()),profiles.opencode_config('education-single-turn'))
        self.assertNotIn('agent',profiles.opencode_config('original'))
        self.assertIn('provider',profiles.opencode_config('original'))
        prepare.verify(dest)
        (dest/'opencode-config.json').write_text('{}')
        with self.assertRaises(ValueError):prepare.verify(dest)

    def test_generated_shell_verifier_exports_score_and_diagnostics(self):
        dest=self.root/'prepared'
        prepare.build(dest,{self.task_id:self.task},[self.model])
        verifier=dest/self.model/self.task['skill_id']/'baseline'/self.task_id/'tests'
        trace=self.root/'trace';trace.mkdir()
        (trace/'acp_trajectory.jsonl').write_text(json.dumps({'type':'agent_message','text':'answer'}))
        mock=self.root/'mock';mock.mkdir()
        payload={'content':[{'type':'text','text':self.answer}], 'stop_reason':'end_turn', 'id':'offline-request'}
        (mock/'sitecustomize.py').write_text('import urllib.request,io\n'
            +'urllib.request.urlopen=lambda *a,**k: io.StringIO('+repr(json.dumps(payload))+')\n')
        logs=self.root/'logs';logs.mkdir()
        env={**os.environ,'PYTHONPATH':str(mock),'ANTHROPIC_API_KEY':'offline-fixture',
             'ANTHROPIC_BASE_URL':'https://offline.invalid', 'BENCHFLOW_VERIFIER_DIR':str(verifier),
             'BENCHFLOW_AGENT_LOG_DIR':str(trace),'BENCHFLOW_REWARD_DETAILS_JSON':str(logs/'judge_result.json'),
             'BENCHFLOW_REWARD_TEXT':str(logs/'reward.txt'),'BENCHFLOW_REWARD_JSON':str(logs/'reward.json')}
        done=subprocess.run(['bash',str(verifier/'test.sh')],env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(json.loads((logs/'reward.json').read_text())['reward'],0)
        self.assertEqual(len(list(logs.glob('judge_response_*.json'))),1)
        self.assertTrue((logs/'judge_result.json').exists())

    def test_resume_rejects_changed_raw_evidence_and_protocol(self):
        run=self.make_run()
        row={'model':self.model,'task_id':self.task_id,'condition':'baseline',
             'source':str(run/'result.json'),'source_sha256':P.sha256(run/'result.json'),
             'trajectory':str(run/'trajectory'), 'evidence_files':rejudge.evidence_files(run/'trajectory'),
             'case':self.case}
        blocked=[{'model':m,'task_id':tid,'condition':cond}
                 for m in P.MODELS for _,tid,cond in P.expected_cells(P.load_tasks())
                 if (m,tid,cond)!=(self.model,self.task_id,'baseline')]
        manifest={'judge_version':judge.VERSION,'judge_sha256':P.sha256(P.REPO/'repro/judge.py'),
                  'source_tag':'v2','metric':'equal','task_sha256':P.sha256(P.REPO/'data/single_turn_tasks.csv'),
                  'plan':[row],'blocked':blocked}
        rejudge.validate_manifest(manifest,'v2','equal')
        with self.assertRaises(ValueError): rejudge.validate_manifest(manifest,'v2','weighted')
        (run/'trajectory/added.txt').write_text('new evidence')
        with self.assertRaises(ValueError): rejudge.validate_manifest(manifest,'v2','equal')


    def test_preflight_auth_stops_before_next_model(self):
        with patch('judge.evaluate',side_effect=judge.JudgeError('authentication')) as call:
            with self.assertRaisesRegex(judge.JudgeError,'authentication'):
                judge.preflight(['first','second'],self.root)
            self.assertEqual(call.call_count,1)


    def test_wall_deadline_interrupts_stalled_read(self):
        import time
        with self.assertRaises(TimeoutError):
            with judge.request_deadline(.02):
                time.sleep(.2)


if __name__ == '__main__':
    unittest.main()
