import io,json,os,unittest
from unittest.mock import patch
from repro import judge,profiles
from repro.source_runner import model_options


class MinimumThinkingTests(unittest.TestCase):
    def test_default_wire_payload_and_both_entry_points(self):
        body=json.dumps({'content':[{'type':'text','text':'OK'}],'stop_reason':'end_turn'})
        config=profiles.opencode_config('education-single-turn')['provider']['ark']['models']
        for model,expected in judge.MINIMAL_MODEL_OPTIONS.items():
            with self.subTest(model=model),patch.dict(os.environ,{'ANTHROPIC_API_KEY':'test','ANTHROPIC_BASE_URL':'https://example.invalid/v1'},clear=True),patch('urllib.request.urlopen',return_value=io.StringIO(body)) as api:
                judge.call_judge('question',model)
                wire=json.loads(api.call_args.args[0].data)
                self.assertEqual(wire['thinking']['type'],expected['thinking_mode'])
                self.assertEqual(model_options(model)['thinking_mode'],expected['thinking_mode'])
                self.assertEqual(config[model]['options']['thinking']['type'],expected['thinking_mode'])
                if expected['thinking_mode']=='disabled':
                    self.assertNotIn('budget_tokens',wire['thinking'])
                    self.assertNotIn('output_config',wire)
                else:
                    self.assertEqual(wire['output_config']['effort'],'low')
                    self.assertEqual(wire['thinking']['budget_tokens'],1024)
                    self.assertEqual(config[model]['options']['effort'],'low')
                    self.assertEqual(config[model]['options']['thinking']['budgetTokens'],1024)

    def test_self_and_fixed_judge_profiles_follow_policy(self):
        for model in judge.MINIMAL_MODEL_OPTIONS:
            self.assertEqual(judge.request_options({'judge_model':model}),judge.minimal_model_options(model))
        for profile in ('fixed-pro-v1','fixed-pro-v2','fixed-pro-v3'):
            options=judge.request_options({'judge_model':'deepseek-v4-pro','judge_profile':profile,'arithmetic_audit':True,'rubric':[{'id':'C1'}]})
            self.assertEqual(options['thinking_mode'],'disabled')

if __name__=='__main__':unittest.main()
