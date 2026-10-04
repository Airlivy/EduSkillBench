import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import judge
import protocol as P
import prepare
import runner


class FastJudgeTests(unittest.TestCase):
    def test_arithmetic_is_exact_and_does_not_guess_symbolic_expressions(self):
        self.assertEqual(judge.arithmetic_audit('11*4=45 pupils')[0]['left_value'],'44')
        self.assertEqual(judge.arithmetic_audit('11×4=45')[0]['right_value'],'45')
        for expression in ['0.1+0.2=0.3','10*4+5=45','-3+2=-1','x + 2=3','10=2+x','2**3=8','2e3+2=2002','1/0=0']:
            with self.subTest(expression=expression):self.assertEqual(judge.arithmetic_audit(expression),[])
        text='A pupil writes "11*4=45"; correct it to 11*4=44.'
        self.assertEqual(len(judge.arithmetic_audit(text)),1)
        # The helper supplies evidence; it never turns a quoted mistake into a grade.
        self.assertNotIn('pass',judge.arithmetic_audit(text)[0])

    def test_profile_preserves_inputs_and_binds_response_and_judge_separately(self):
        task=next(iter(P.load_tasks().values()));model='glm-5.3-flash'
        old=P.make_case(task,model,'weighted')
        fast=P.make_case(task,model,'weighted','fixed-pro-v1')
        for key in ('question','ground_truth','rubric','score_metric'):self.assertEqual(old[key],fast[key])
        self.assertEqual(fast['response_model'],model)
        self.assertEqual(fast['judge_model'],'deepseek-v4-pro')
        self.assertNotEqual(judge.input_digest(old,'answer'),judge.input_digest(fast,'answer'))
        options=judge.request_options(fast)
        self.assertEqual(options['thinking_mode'],'disabled')
        self.assertEqual(options['max_output_tokens'],4096)
        self.assertEqual(options['output_schema']['properties']['items']['minItems'],len(fast['rubric']))
        with self.assertRaises(judge.JudgeError):judge.request_options({**fast,'judge_model':model})

    def test_disabled_thinking_omits_budget_and_sends_schema(self):
        import io,os
        body=json.dumps({'content':[{'type':'text','text':'{}'}],'stop_reason':'end_turn'})
        schema=judge.verdict_schema([{'id':'C1'}])
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'test','ANTHROPIC_BASE_URL':'https://example.invalid/v1'},clear=True),patch('urllib.request.urlopen',return_value=io.StringIO(body)) as api:
            judge.call_judge('q','deepseek-v4-pro',thinking_mode='disabled',max_output_tokens=4096,output_schema=schema)
            sent=json.loads(api.call_args.args[0].data)
            self.assertEqual(sent['thinking'],{'type':'disabled'})
            self.assertEqual(sent['output_format']['schema'],schema)

    def test_all_fixed_profiles_follow_requested_minimum_policy(self):
        task=next(iter(P.load_tasks().values()))
        case=P.make_case(task,'glm-5.3-flash','weighted','fixed-pro-v3')
        options=judge.request_options(case)
        self.assertEqual(options['thinking_mode'],'disabled')
        self.assertNotIn('thinking_budget',options)
        self.assertNotIn('effort',options)
        self.assertEqual(options['max_output_tokens'],4096)
        self.assertEqual(options['timeouts']['total'],120)
        legacy=P.make_case(task,'glm-5.3-flash','weighted')
        self.assertEqual(judge.request_options(legacy),{'thinking_mode':'enabled','thinking_budget':1024,'effort':'low'})
        self.assertNotEqual(judge.input_digest(case,'answer'),judge.input_digest(legacy,'answer'))

    def test_fixed_judge_recovery_requires_frozen_profile_and_retains_raw_result(self):
        task=next(iter(P.load_tasks().values()));tid=task['task_id'];model='glm-5.3-flash'
        case=P.make_case(task,model,'weighted','fixed-pro-v1')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job=root/('new-'+model)
            run=job/'skill-eval'/task['skill_id']/'opencode/baseline/2026-10-01'/f'{tid}__abcdef'
            (run/'trajectory').mkdir(parents=True)
            (run/'trajectory/acp_trajectory.jsonl').write_text(json.dumps({'type':'agent_message','text':'answer'}))
            source=run/'result.json';source.write_text(json.dumps({'model':'ark/'+model,'rewards':None}))
            original=source.read_bytes()
            response=json.dumps({'items':[{'id':r['id'],'pass':True} for r in case['rubric']]})
            real=judge.evaluate
            with patch('judge.evaluate',side_effect=lambda c,t,d:real(c,t,d,call=lambda *a:response)):
                self.assertTrue(runner.recover_scoring(source,case))
            self.assertEqual(source.read_bytes(),original)
            self.assertFalse(P.inspect_model(job,model,{tid:task},('baseline',))['complete'])
            manifest=root/'protocols/new/tasks/manifest.json';manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'judge_profile':'fixed-pro-v1'}))
            report=P.inspect_model(job,model,{tid:task},('baseline',))
            self.assertTrue(report['complete'])
            self.assertEqual(report['judge_profile'],'fixed-pro-v1')
            manifest.write_text(json.dumps({'judge_profile':'self-v1'}))
            self.assertFalse(P.inspect_model(job,model,{tid:task},('baseline',))['complete'])

    def test_prepare_freezes_profile_for_both_conditions(self):
        task=next(iter(P.load_tasks().values()))
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'tasks'
            manifest=prepare.build(out,{task['task_id']:task},['glm-5.3-flash'],judge_profile='fixed-pro-v1')
            self.assertEqual(manifest['judge_profile'],'fixed-pro-v1')
            cases=[json.loads(p.read_text()) for p in out.rglob('case.json')]
            self.assertEqual(len(cases),2);self.assertEqual(cases[0],cases[1])
            self.assertEqual(cases[0]['judge_model'],'deepseek-v4-pro')
            prepare.verify(out)

    def test_v2_counterevidence_must_be_from_answer_and_consistent(self):
        items=[{'id':'C1','pass':False}]
        judge.validate_counterevidence(items,{'C1':'11*4=45'},'Answer: 11*4=45 pupils.')
        for bad in ({'C1':'invented quote'},{'C2':''},{'C1':None}):
            with self.assertRaises(judge.JudgeError):judge.validate_counterevidence(items,bad,'Answer: 11*4=45 pupils.')
        with self.assertRaises(judge.JudgeError):
            judge.validate_counterevidence([{'id':'C1','pass':True}],{'C1':'11*4=45'},'11*4=45')

    def test_v2_saves_and_revalidates_evidence(self):
        task=next(iter(P.load_tasks().values()))
        case=P.make_case(task,'glm-5.3-flash','weighted','fixed-pro-v2')
        response={'items':[{'id':r['id'],'pass':False,'counterevidence':'wrong statement'} for r in case['rubric']]}
        with tempfile.TemporaryDirectory() as tmp:
            result=judge.evaluate(case,'wrong statement',tmp,call=lambda *a:json.dumps(response))
            self.assertEqual(result['score'],0)
            self.assertEqual(len(result['criterion_counterevidence']),len(case['rubric']))
            self.assertIsNotNone(judge.cached_verdict(case,'wrong statement',tmp))
            path=Path(tmp)/'judge_result.json';data=json.loads(path.read_text())
            data['criterion_counterevidence'][case['rubric'][0]['id']]='fabricated';path.write_text(json.dumps(data))
            with self.assertRaises(judge.JudgeError):judge.cached_verdict(case,'wrong statement',tmp)

if __name__=='__main__':unittest.main()
