import contextlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import protocol as P
import judge
import prepare
from legacy import patch_framework
import runner
import check as checker
import summarize as finalizer


class ReproTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tasks = P.load_tasks()
        self.model = P.MODELS[0]

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, tid, cond='baseline', reward=1, **extra):
        skill = tid.rsplit('__', 1)[0]
        p = self.root/f'v2-{self.model}'/'skill-eval'/skill/'opencode'/cond/'2026-09-01__00-00-00'/f'{tid}__abcdef'
        p.mkdir(parents=True, exist_ok=True)
        (p/'result.json').write_text(json.dumps({'model': 'ark/'+self.model, 'rewards': {'reward': reward}, **extra}))
        return p

    def test_empty_and_whole_missing_skills_fail(self):
        for tid in list(self.tasks)[:3]:
            for cond in P.CONDITIONS:
                self.put(tid, cond)
        report = P.inspect_model(self.root/f'v2-{self.model}', self.model, self.tasks)
        self.assertEqual(report['expected'], 84)
        self.assertEqual(len(report['missing']), 78)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(checker.main(['--all', '--jobs-dir', str(self.root)]), 1)
            self.assertEqual(checker.main(['--all', '--jobs-dir', str(self.root/'empty')]), 1)

    def test_invalid_rewards_and_errors(self):
        for value in [None, True, '1', float('nan'), float('inf'), -0.1, 1.1]:
            self.assertIsNotNone(P.result_reason({'rewards': {'reward': value}}))
        self.assertIsNone(P.result_reason({'rewards': {'reward': 0}}))
        self.assertEqual(P.result_reason({'rewards': {'reward': 1}, 'error': 'broken'}), 'error')
        self.assertEqual(P.result_reason({'model':None, 'rewards':{'reward':1}},self.model),'model_mismatch')

    def test_unexpected_task_cannot_replace_missing(self):
        self.put('invented__01')
        report = P.inspect_model(self.root/f'v2-{self.model}', self.model, self.tasks)
        self.assertEqual(len(report['missing']), 84)
        self.assertTrue(report['errors'])

    def test_parser_failure_zero_is_not_valid(self):
        tid = next(iter(self.tasks))
        p = self.put(tid, reward=0)
        (p/'verifier').mkdir()
        (p/'verifier/test-stdout.txt').write_text('WARNING: Could not parse judge response: invalid\nJudge score: 0.0')
        report = P.inspect_model(self.root/f'v2-{self.model}', self.model, self.tasks)
        self.assertFalse(report['valid'])
        self.assertEqual(report['picked'][(tid.rsplit('__',1)[0],tid,'baseline')]['reason'], 'judge_parse_failure_recorded_as_reward')

    def test_selection_not_highest_score(self):
        a = {'valid': True, 'reward': 1, 'finished_at': '01', 'source': 'a'}
        b = {'valid': True, 'reward': 0, 'finished_at': '02', 'source': 'b'}
        self.assertEqual(P.choose([a,b]), b)

    def test_finalize_does_not_write_incomplete_and_pairs_preview(self):
        first, second = list(self.tasks)[:2]
        self.put(first, 'baseline', 0)
        self.put(first, 'with-skill', 1)
        self.put(second, 'baseline', 1)
        out = self.root/'summary'
        args = ['--models', self.model, '--jobs-dir', str(self.root), '--out', str(out)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(finalizer.main(args), 1)
            self.assertFalse(out.exists())
            self.assertEqual(finalizer.main(args+['--allow-incomplete']), 0)
        row = json.loads((out/'model_overall_summary.json').read_text())[0]
        self.assertEqual(row['paired_tasks'], 1)
        self.assertEqual(row['reward_lift'], 1)
        self.assertEqual(row['status'], 'incomplete_preview')

    def test_strict_scoring_rejects_bad_items_and_ignores_self_score(self):
        rubric = [{'id':'C1','points':90,'description':'a'}, {'id':'C2','points':10,'description':'b'}]
        response = {'items':[{'id':'C2','pass':False},{'id':'C1','pass':True}], 'score':0}
        result = judge.score_items(response,rubric)
        self.assertEqual(result['equal_score'], .5)
        self.assertEqual(result['weighted_score'], .9)
        for items in [[], [{'id':'C1','pass':True}]*2,
                      [{'id':'C1','pass':'false'},{'id':'C2','pass':False}],
                      [{'id':'C3','pass':True},{'id':'C2','pass':False}]]:
            with self.assertRaises(ValueError): judge.score_items({'items':items},rubric)

    def test_judge_format_failure_emits_no_reward(self):
        case = {'question':'q','ground_truth':'g','judge_model':'m','score_metric':'equal',
                'rubric':[{'id':'C1','points':100,'description':'a'}]}
        calls=[]
        def bad(*args):
            calls.append(args)
            return '{"score": 0}'
        with self.assertRaises(ValueError): judge.evaluate(case,'answer',self.root,call=bad)
        self.assertEqual(len(calls),3)
        self.assertFalse((self.root/'reward.json').exists())
        self.assertEqual(len(list(self.root.glob('judge_raw_*.txt'))),3)

    def test_true_zero_is_written_without_rerunning(self):
        case = {'question':'q','ground_truth':'g','judge_model':'m','score_metric':'equal',
                'rubric':[{'id':'C1','points':100,'description':'a'}]}
        judge.evaluate(case,'answer',self.root,call=lambda *a:'{"items":[{"id":"C1","pass":false}]}')
        self.assertEqual(json.loads((self.root/'reward.json').read_text())['reward'],0)

    def test_every_task_and_full_resources_verified(self):
        for mode in ['access','forced']:
            p = self.root/mode
            tasks = {k:v for k,v in self.tasks.items() if v['skill_id']=='lesson-builder'}
            prepare.build(p,tasks,[self.model],mode=mode)
            prepare.verify(p)
            artifact=next(p.glob('*/lesson-builder/with-skill/*/environment/skills/lesson-builder/templates/*.md'))
            artifact.unlink()
            with self.assertRaises(ValueError): prepare.verify(p)

    def test_patch_roundtrip_and_unknown_restore_refused(self):
        p = self.root/'judge.py'
        original = ('MAX_TRAJECTORY_CHARS = 50_000\n'
                    'def read_trajectory():\n    text = "x"\n'
                    '    if len(text) > MAX_TRAJECTORY_CHARS:\n'
                    '        text = text[:MAX_TRAJECTORY_CHARS] + "truncated"\n    return text\n')
        p.write_text(original)
        with self.assertRaises(ValueError): patch_framework.patch(p,'truncation','restore')
        patch_framework.patch(p,'truncation','apply')
        patch_framework.patch(p,'truncation','restore')
        self.assertEqual(p.read_text(), original)

    def test_lock_excludes_other_runner(self):
        lockfile=self.root/'lock'
        with runner.lock(lockfile):
            with self.assertRaises(RuntimeError):
                with runner.lock(lockfile):pass

    def test_owned_worker_ends_without_waiting_for_background_service(self):
        self.assertEqual(runner.run_owned([sys.executable,'-c','print("done")'], self.root/'log',2),0)
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.run_owned([sys.executable,'-c','import time; time.sleep(10)'],self.root/'slow',.1)


if __name__ == '__main__':
    unittest.main()
