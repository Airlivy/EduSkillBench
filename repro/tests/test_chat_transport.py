import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from repro import judge,source_runner as runner


def stream(stop='stop',done=True):
    events=[{'id':'req1','model':'glm-5.3','choices':[{'index':0,'delta':{'reasoning_content':'thinking'}}]},
            {'choices':[{'index':0,'delta':{'content':'answer'}}]},
            {'choices':[{'index':0,'delta':{},'finish_reason':stop}]},
            {'choices':[],'usage':{'completion_tokens':3}}]
    return ''.join('data: '+json.dumps(e)+'\n\n' for e in events)+('data: [DONE]\n\n' if done else '')


class ChatTransportTests(unittest.TestCase):
    def test_all_models_explicit_off_overrides_default_thinking_policy(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(runner.OPTIONS),patch.dict(runner.API_OVERRIDES),patch.object(runner,'GLM_API_PROTOCOL','messages'):
            p=Path(tmp)/'config.json';p.write_text(json.dumps({'max_output_tokens':6144,'total_timeout_seconds':120,'api_protocol':'chat_completions','thinking_mode':'disabled'}))
            runner.load_api_config(p)
            for model in ('glm-5.3','glm-5.3-flash','deepseek-v4-pro','deepseek-v4-flash','kimi-k2.7-code'):
                opts=runner.model_options(model)
                self.assertEqual((opts['api_protocol'],opts['thinking_mode'],opts['max_output_tokens'],opts['timeouts']['total']),('chat_completions','disabled',6144,120))
                self.assertNotIn('effort',opts)
                self.assertNotIn('thinking_budget',opts)
    def call(self,body):
        env={'ANTHROPIC_API_KEY':'test','ANTHROPIC_BASE_URL':'https://example.invalid/v1'}
        with patch.dict(os.environ,env,clear=True),patch('urllib.request.urlopen',return_value=io.BytesIO(body.encode())) as api:
            text,meta=judge.call_judge('question','glm-5.3',api_protocol='chat_completions',thinking_mode='enabled',effort='low',thinking_budget=1024)
            req=api.call_args.args[0];payload=json.loads(req.data)
        return text,meta,req,payload

    def test_correct_wire_protocol_and_reasoning_not_in_answer(self):
        text,meta,req,payload=self.call(stream())
        self.assertTrue(req.full_url.endswith('/v1/chat/completions'))
        self.assertEqual(req.get_header('Authorization'),'Bearer test')
        self.assertEqual(payload['reasoning_effort'],'low')
        self.assertNotIn('budget_tokens',payload['thinking'])
        self.assertNotIn('output_config',payload)
        self.assertEqual(text,'answer')
        self.assertEqual(meta['thinking_chars'],8)
        self.assertEqual(meta['usage']['completion_tokens'],3)
        self.assertEqual(meta['stop_reason'],'end_turn')
        self.assertEqual(meta['api_protocol'],'chat_completions')

    def test_truncation_eof_and_unknown_stop_are_not_success(self):
        for reason,done,want in [('length',True,'max_tokens'),('stop',False,'stream_incomplete'),('content_filter',True,'content_filter'),(None,True,'stream_incomplete')]:
            self.assertEqual(self.call(stream(reason,done))[1]['stop_reason'],want)

    def test_provider_error_and_invalid_envelope_fail(self):
        for data in ['{"error":{"message":"failed"}}','[]','{"choices":3}']:
            with self.assertRaises(judge.JudgeError):self.call('data: '+data+'\n\n')

    def test_only_glm_routes_to_chat_and_config_is_bound(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(runner.OPTIONS),patch.object(runner,'GLM_API_PROTOCOL','messages'):
            p=Path(tmp)/'config.json';p.write_text(json.dumps({'max_output_tokens':16000,'total_timeout_seconds':300,'glm_api_protocol':'chat_completions'}))
            runner.load_api_config(p)
            self.assertEqual(runner.model_options('glm-5.3')['api_protocol'],'chat_completions')
            self.assertEqual(runner.model_options('glm-5.3-flash')['api_protocol'],'chat_completions')
            self.assertNotIn('api_protocol',runner.model_options('deepseek-v4-pro'))
            self.assertNotIn('api_protocol',runner.model_options('kimi-k2.7-code'))
