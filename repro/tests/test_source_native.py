import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from repro.source_protocol import dimensions,load_release,labels,validate,prompt
from repro.source_runner import evaluate_native,exchange,run_cell,model_options
from repro.judge import JudgeError


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cases,_=load_release();cls.cases={c['task_id']:c for c in cases}

    def case(self,part):return copy.deepcopy(next(c for k,c in self.cases.items() if part in k))

    def verdict(self,c,answer,rank=0):
        return {'items':[{'id':r['id'],'counterevidence':'','level':labels(r)[rank],'evidence':answer,'reason':'符合此项'} for r in c['criteria'] if r['id'] in c['applicable_ids']]}

    def test_glm_does_not_receive_disabled_thinking(self):
        for model in ('glm-5.3','glm-5.3-flash'):
            self.assertEqual(model_options(model)['thinking_mode'],'enabled')
            self.assertEqual(model_options(model)['effort'],'low')
        self.assertEqual(model_options('deepseek-v4-pro')['thinking_mode'],'disabled')

    def test_all_source_formats_parsed_without_added_weights(self):
        c=self.case('cn22_01');self.assertEqual(len(c['criteria']),9)
        self.assertTrue(all(r['weight'] is None and not r['levels'] for r in c['criteria']))
        c=self.case('cn01_01');self.assertEqual(sum(r['weight'] for r in c['criteria']),100)
        self.assertEqual(len(c['criteria'][0]['levels']),3)

    def test_original_grade_does_not_become_fake_scalar(self):
        c=self.case('cn01_01');v=validate(self.verdict(c,'回答'),c,'回答')
        self.assertIsNone(v['score']);self.assertIsNone(v['score_interval'])

    def test_numeric_range_uses_selected_original_denominator(self):
        c=self.case('cn60_06');v=validate(self.verdict(c,'回答'),c,'回答')
        self.assertEqual(v['score_interval']['lower'],90)
        self.assertEqual(v['score_interval']['upper'],100)
        self.assertLess(v['score_interval']['denominator_original_weights'],100)

    def test_unacceptable_two_level_rubric_not_forced_to_pass(self):
        c=self.case('cn62_01');v=self.verdict(c,'错误')
        v['items'][0]['level']='低于原文最低等级'
        self.assertEqual(validate(v,c,'错误')['items'][0]['level'],'低于原文最低等级')

    def test_fake_evidence_duplicate_missing_and_unknown_grades_fail(self):
        c=self.case('cn01_01');base=self.verdict(c,'回答')
        variants=[]
        x=copy.deepcopy(base);x['items'][0]['evidence']='伪造';variants.append(x)
        x=copy.deepcopy(base);x['items'][1]['id']=x['items'][0]['id'];variants.append(x)
        x=copy.deepcopy(base);x['items'].pop();variants.append(x)
        x=copy.deepcopy(base);x['items'][0]['level']='满分';variants.append(x)
        for item in variants:
            with self.assertRaises(ValueError):validate(item,c,'回答')

    def test_reference_topics_not_sent_to_judge(self):
        c=self.case('cn22_01');p=prompt(c,'我的答案')
        self.assertNotIn('2a>2c',p);self.assertNotIn('半焦距',p)

    def test_recognized_material_counterevidence_cannot_receive_high_grade(self):
        c=self.case('cn62_03');v=self.verdict(c,'实际耗时45分钟')
        v['items'][0]['counterevidence']='E1'
        with self.assertRaisesRegex(ValueError,'lowest allowed'):
            validate(v,c,'实际耗时45分钟',require_counterevidence=True)
        v['items'][0]['level']='低于原文最低等级'
        result=validate(v,c,'实际耗时45分钟',require_counterevidence=True)
        self.assertEqual(result['items'][0]['counterevidence_spans'][0]['text'],'实际耗时45分钟')

    def test_live_verdict_requires_counterevidence_field_and_real_source(self):
        c=self.case('cn62_03');v=self.verdict(c,'实际耗时45分钟')
        del v['items'][0]['counterevidence']
        with self.assertRaisesRegex(ValueError,'Missing counterevidence'):
            validate(v,c,'实际耗时45分钟',require_counterevidence=True)
        v['items'][0]['counterevidence']='E999'
        with self.assertRaises(ValueError):validate(v,c,'实际耗时45分钟',require_counterevidence=True)

    def test_no_full_course_demand_for_local_feedback(self):
        c=self.case('cn51_05');self.assertNotIn('D2',c['applicable_ids'])
        self.assertIn('D5',c['applicable_ids'])
        c=self.case('cn63_03');self.assertEqual(c['applicable_ids'],['D4'])

    def test_ellipsis_evidence_requires_ordered_exact_fragments(self):
        from repro.source_protocol import evidence_spans
        answer='先观察学生动作。中间步骤。最后请学生自己再试。'
        spans=evidence_spans('先观察学生动作……最后请学生自己再试',answer)
        self.assertEqual(len(spans),2)
        with self.assertRaises(ValueError):evidence_spans('先观察学生动作……教师直接代做',answer)
        with self.assertRaises(ValueError):evidence_spans('最后请学生自己再试……先观察学生动作',answer)

    def test_evidence_ids_resolve_to_exact_saved_answer(self):
        from repro.source_protocol import evidence_spans,answer_segments
        answer='这是原文。'*100
        segments=answer_segments(answer)
        self.assertEqual(''.join(s['text'] for s in segments),answer)
        self.assertEqual(evidence_spans('E1,E3',answer),[segments[0],segments[2]])
        with self.assertRaises(ValueError):evidence_spans('E999',answer)
        with self.assertRaises(ValueError):evidence_spans('E1,E1',answer)

    def test_cache_reuses_validated_verdict(self):
        c=self.case('cn01_01');answer='具体回答';calls=[]
        def call(*a,**kw):calls.append(1);return json.dumps(self.verdict(c,answer)),{'stop_reason':'end_turn'}
        with tempfile.TemporaryDirectory() as tmp:
            first=evaluate_native(c,answer,'glm-5.3',tmp,call=call)
            self.assertEqual(first,evaluate_native(c,answer,'glm-5.3',tmp,call=call));self.assertEqual(len(calls),1)
            with self.assertRaises(ValueError):evaluate_native(c,answer+'改动','glm-5.3',tmp,call=call)

    @patch('repro.source_runner.time.sleep')
    def test_failure_stays_null_and_requires_explicit_retry(self,_sleep):
        c=self.case('cn01_01');calls=[]
        def call(*a,**kw):calls.append(1);return '{}',{'stop_reason':'end_turn'}
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(2):
                with self.assertRaises(JudgeError):evaluate_native(c,'回答','glm-5.3',tmp,call=call)
            self.assertEqual(len(calls),2)
            self.assertIsNone(json.loads((Path(tmp)/'error.json').read_text())['score'])
            self.assertFalse((Path(tmp)/'result.json').exists())

    @patch('repro.source_runner.time.sleep')
    def test_invalid_evidence_is_corrected_without_changing_rubric(self,_sleep):
        c=self.case('cn01_01');answer='具体回答';calls=[]
        invalid=self.verdict(c,answer);invalid['items'][0]['evidence']='E999'
        def call(text,*a,**kw):
            calls.append(text)
            return json.dumps(invalid if len(calls)==1 else self.verdict(c,answer)),{'stop_reason':'end_turn'}
        with tempfile.TemporaryDirectory() as tmp:
            result=evaluate_native(c,answer,'deepseek-v4-pro',tmp,call=call)
            self.assertEqual(result['status'],'evaluated');self.assertEqual(len(calls),2)
            self.assertTrue(calls[1].startswith(calls[0]))
            self.assertIn('Invalid evidence reference',calls[1])
            self.assertEqual(len(list(Path(tmp).glob('raw_*.txt'))),2)
            self.assertFalse((Path(tmp)/'error.json').exists())

    @patch('repro.source_runner.time.sleep')
    def test_transport_and_format_recovery_share_two_calls(self,_sleep):
        c=self.case('cn01_01');calls=[]
        def call(*a,**kw):
            calls.append(1)
            if len(calls)==1:raise JudgeError('transport',True,{'network_error_kind':'dns'})
            return 'not json',{'stop_reason':'end_turn'}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(JudgeError):evaluate_native(c,'回答','deepseek-v4-pro',tmp,call=call)
            self.assertEqual(len(calls),2)
            saved=json.loads((Path(tmp)/'error.json').read_text())
            self.assertIsNone(saved['score']);self.assertTrue(saved['validation_error'])

    def test_deadline_is_reported_without_repeating_slow_generation(self):
        c=self.case('cn22_01')
        details={'timeout_kind':'total_deadline','first_text_seconds':115.6,'thinking_chars':10875}
        with tempfile.TemporaryDirectory() as tmp:
            with patch('repro.source_runner.judge.call_judge',side_effect=JudgeError('transport',True,details)) as call:
                result=run_cell(c,'glm-5.3-flash','deepseek-v4-pro',tmp)
            self.assertEqual(call.call_count,1)
            self.assertEqual(result['failed_stage'],'generation')
            self.assertEqual(result['failure_details'],details)

    def test_exhaustion_not_retried(self):
        calls=[]
        def call(*a,**kw):calls.append(1);return '',{'stop_reason':'max_tokens'}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(JudgeError):exchange('问题','glm-5.3',Path(tmp),call=call)
        self.assertEqual(len(calls),1)

    def test_resume_failed_grading_does_not_regenerate_answer(self):
        c=self.case('cn22_01')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('repro.source_runner.exchange',return_value=('已保存答案',{'stop_reason':'end_turn'})) as generated,patch('repro.source_runner.evaluate_native',side_effect=JudgeError('transport')):
                self.assertEqual(run_cell(c,'glm-5.3','glm-5.3',tmp)['status'],'pending_review')
                self.assertEqual(generated.call_count,1)
            with patch('repro.source_runner.exchange',side_effect=AssertionError('must not regenerate')),patch('repro.source_runner.evaluate_native',return_value={'score':None,'score_interval':None}):
                self.assertEqual(run_cell(c,'glm-5.3','glm-5.3',tmp,True)['status'],'evaluated')

if __name__=='__main__':unittest.main()
