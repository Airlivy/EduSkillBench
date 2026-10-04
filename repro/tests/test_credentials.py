import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from repro.credentials import load_env_file
from repro import judge

class CredentialsTests(unittest.TestCase):
    def test_literal_env_without_shell_execution(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{},clear=True):
            p=Path(tmp)/'env'
            p.write_text("export ANTHROPIC_AUTH_TOKEN='local-test-token'\nexport ANTHROPIC_BASE_URL='https://example.invalid/v1'\nexport ANTHROPIC_API_KEY=$(touch should-not-exist)\nOTHER_SECRET=ignored\n")
            names=load_env_file(p)
            self.assertEqual(names,['ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL'])
            self.assertNotIn('ANTHROPIC_API_KEY',os.environ)
            self.assertNotIn('OTHER_SECRET',os.environ)
            self.assertFalse((Path(tmp)/'should-not-exist').exists())
    def test_existing_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'LLM_API_KEY':'existing'},clear=True):
            p=Path(tmp)/'env';p.write_text('LLM_API_KEY=file-value\n')
            load_env_file(p);self.assertEqual(os.environ['LLM_API_KEY'],'existing')
            load_env_file(p,override=True);self.assertEqual(os.environ['LLM_API_KEY'],'file-value')
    def test_bearer_aliases_and_complete_messages_url(self):
        body=json.dumps({'content':[{'type':'text','text':'{}'}],'stop_reason':'end_turn'})
        for variable in ['ANTHROPIC_AUTH_TOKEN','LLM_API_KEY']:
            with self.subTest(variable=variable),patch.dict(os.environ,{variable:'test-token','ANTHROPIC_BASE_URL':'https://example.invalid/v1/messages'},clear=True):
                with patch('urllib.request.urlopen',return_value=io.StringIO(body)) as request:
                    judge.call_judge('test','model')
                    req=request.call_args.args[0]
                    self.assertEqual(req.full_url,'https://example.invalid/v1/messages')
                    self.assertEqual(req.get_header('Authorization'),'Bearer test-token')
                    self.assertIsNone(req.get_header('X-api-key'))
    def test_api_key_precedence_preserves_original_contract(self):
        body=json.dumps({'content':[{'type':'text','text':'{}'}]})
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'key','ANTHROPIC_AUTH_TOKEN':'token','ANTHROPIC_BASE_URL':'https://example.invalid/v1'},clear=True):
            with patch('urllib.request.urlopen',return_value=io.StringIO(body)) as request:
                judge.call_judge('test','model');req=request.call_args.args[0]
                self.assertEqual(req.get_header('X-api-key'),'key')
                self.assertIsNone(req.get_header('Authorization'))

class StreamingJudgeTests(unittest.TestCase):
    def stream(self,complete=True):
        events=[
          {'type':'message_start','message':{'id':'test-request','usage':{'input_tokens':10}}},
          {'type':'content_block_start','index':0,'content_block':{'type':'thinking','thinking':''}},
          {'type':'content_block_delta','index':0,'delta':{'type':'thinking_delta','thinking':'not an answer'}},
          {'type':'content_block_start','index':1,'content_block':{'type':'text','text':''}},
          {'type':'content_block_delta','index':1,'delta':{'type':'text_delta','text':'{"items":['}},
          {'type':'content_block_delta','index':1,'delta':{'type':'text_delta','text':'{"id":"C1","pass":true}]}'}},
          {'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':30}},
        ]
        if complete:events.append({'type':'message_stop'})
        response=io.StringIO(''.join('data: '+json.dumps(e)+'\n\n' for e in events))
        response.headers={'Content-Type':'text/event-stream; charset=utf-8'}
        return response
    def test_complete_sse_preserves_text_usage_excludes_thought(self):
        data=judge.read_provider_response(self.stream())
        self.assertEqual(data['usage'],{'input_tokens':10,'output_tokens':30})
        self.assertEqual(data['stop_reason'],'end_turn')
        self.assertNotIn('not an answer',json.dumps(data))
        text=data['content'][1]['text']
        self.assertTrue(judge.decode_verdict(text)['items'][0]['pass'])
    def test_incomplete_stream_not_successful(self):
        data=judge.read_provider_response(self.stream(False))
        self.assertEqual(data['stop_reason'],'stream_incomplete')
    def test_complete_array_normalized_but_wrong_ids_rejected(self):
        parsed=judge.decode_verdict('[{"id":"C1","pass":true}]')
        rubric=[{'id':'C1','points':100,'description':'test','critical':True}]
        self.assertTrue(judge.score_items(parsed,rubric)['critical_pass'])
        bad=judge.decode_verdict('[{"id":"C2","pass":true}]')
        with self.assertRaises(ValueError):judge.score_items(bad,rubric)
        with self.assertRaises(ValueError):judge.decode_verdict('Here is the result: [{"id":"C1","pass":true}]')
    def test_critical_failure_visible_without_changing_raw_score(self):
        r=[{'id':'C1','points':20,'description':'correct','critical':True},
           {'id':'C2','points':80,'description':'format','critical':False}]
        v=judge.score_items({'items':[{'id':'C1','pass':False},{'id':'C2','pass':True}]},r,primary='weighted')
        self.assertEqual(v['score'],.8);self.assertFalse(v['critical_pass'])
