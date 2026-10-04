import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repro import source_runner as runner


class ApiConfigTests(unittest.TestCase):
    def test_budget_reaches_generation_request_and_frozen_model_options(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(runner.OPTIONS):
            path=Path(tmp)/'config.json'
            path.write_text(json.dumps({'max_output_tokens':16000,'total_timeout_seconds':300}))
            runner.load_api_config(path)
            seen=[]
            def call(text,model,**kwargs):
                seen.append((kwargs['max_output_tokens'],kwargs['timeouts']['total']))
                return 'OK',{'stop_reason':'end_turn'}
            runner.exchange('test','glm-5.3',Path(tmp),call=call)
            self.assertEqual(seen,[(16000,300)])
            self.assertEqual(runner.model_options('deepseek-v4-pro')['max_output_tokens'],16000)
            self.assertEqual(runner.model_options('glm-5.3')['thinking_budget'],1024)

    def test_invalid_budget_fails_before_any_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(runner.OPTIONS):
            path=Path(tmp)/'config.json'
            for config in ({'max_output_tokens':True},{'max_output_tokens':1024},
                           {'max_output_tokens':16001},{'max_tokens':16000},[],
                           {'max_output_tokens':16000,'total_timeout_seconds':True},
                           {'max_output_tokens':16000,'total_timeout_seconds':float('nan')},
                           {'max_output_tokens':16000,'total_timeout_seconds':601}):
                path.write_text(json.dumps(config))
                with self.assertRaises(ValueError):runner.load_api_config(path)
