import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol import dataset_source, load_tasks, task_digest, inspect_model, MODELS, validate_run_binding
from prepare import build, verify
from judge import score_items
from runner import immutable_image_reference, configure_local_proxy_bypass, worker


class ReleaseTests(unittest.TestCase):
    def test_worker_exports_answers_for_host_scoring_in_both_conditions(self):
        rollout_module = ModuleType('benchflow.rollout')
        policy_module = ModuleType('benchflow.skill_policy')
        policy_module.SKILL_MODE_WITH_SKILL = 'with-skill'
        policy_module.SKILL_MODE_NO_SKILL = 'no-skill'
        seen = []
        completed = []
        class FakeRollout:
            @classmethod
            async def create(cls, config):
                seen.append(config)
                return cls()
            async def run(self):
                completed.append(True)
        rollout_module.Rollout = FakeRollout
        rollout_module.RolloutConfig = SimpleNamespace(from_legacy=lambda **kw: kw)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {
            'benchflow.rollout': rollout_module, 'benchflow.skill_policy': policy_module,
        }), patch.dict(os.environ, {}, clear=True):
            plan_file = Path(tmp)/'plan.json'
            for condition in ('baseline','with-skill'):
                plan_file.write_text(json.dumps({
                    'model': 'glm-5.3-flash', 'condition': condition,
                    'task_ids': ['lesson-builder__01'], 'system_profile': 'education-single-turn',
                    'tasks_dir': tmp, 'jobs_dir': str(Path(tmp)/'jobs'),
                }))
                self.assertEqual(worker(plan_file), 0)
        self.assertEqual(len(completed), 2)
        self.assertEqual([c['skill_mode'] for c in seen], ['no-skill','with-skill'])
        for config in seen:
            self.assertTrue(config['skip_verify'])
            self.assertEqual(config['task_path'].name, 'lesson-builder__01')
            self.assertEqual(config['model'], 'ark/glm-5.3-flash')
            self.assertIn('OPENCODE_CONFIG_CONTENT', config['agent_env'])

    def test_local_health_proxy_bypass_retains_user_entries(self):
        with patch.dict(os.environ,{'NO_PROXY':'example.test','no_proxy':'localhost'},clear=True):
            configure_local_proxy_bypass(['172.17.0.1'])
            self.assertEqual(os.environ['NO_PROXY'],os.environ['no_proxy'])
            self.assertTrue({'example.test','localhost','172.17.0.1'} <= set(os.environ['NO_PROXY'].split(',')))

    def test_dockerfile_uses_repository_digest_not_bare_image_id(self):
        image={'Id':'sha256:config','RepoDigests':['python@sha256:manifest']}
        with patch('runner.subprocess.check_output',return_value=json.dumps([image])):
            self.assertEqual(immutable_image_reference('python:3.12-slim'),('sha256:config','python@sha256:manifest'))
        with patch('runner.subprocess.check_output',return_value=json.dumps([{'Id':'sha256:local','RepoDigests':[]}])):
            with self.assertRaises(ValueError):immutable_image_reference('unpublished:local')

    def test_suite_coverage_and_conditions(self):
        core_path,core_conditions=dataset_source('core')
        core=load_tasks(core_path)
        self.assertEqual(len(core),42)
        self.assertEqual(core_conditions,('baseline','with-skill'))
        for suite in ('all','advisory'):
            with self.assertRaisesRegex(ValueError,'source-run|263题已恢复原文'):
                dataset_source(suite)
        with tempfile.TemporaryDirectory() as tmp:
            report=inspect_model(tmp,MODELS[0],core,core_conditions)
            self.assertEqual(report['expected'],84)
            self.assertEqual(len(report['missing']),84)

    def test_baseline_only_compilation_and_changed_inputs(self):
        source,_=dataset_source('core');conditions=('baseline',)
        task=load_tasks(source)['hinge-question-designer__01']
        tasks={task['task_id']:task}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'tasks'
            manifest=build(out,tasks,[MODELS[0]],conditions=conditions)
            self.assertFalse(any(p.name=='with-skill' for p in out.rglob('*')))
            self.assertEqual(manifest['task_input_sha256'],task_digest(tasks))
            task['expected_output']+=' Changed answer.'
            self.assertNotEqual(manifest['task_input_sha256'],task_digest(tasks))
            instruction=next(out.rglob('instruction.md'))
            instruction.write_text('contaminated')
            with self.assertRaises(ValueError):verify(out)

    def test_critical_failure_is_separate_from_partial_credit(self):
        source,_=dataset_source('core')
        rubric=load_tasks(source)['self-explanation-prompt-designer__03']['rubric']
        verdict=score_items({'items':[{'id':r['id'],'pass':not r.get('critical',False)} for r in rubric]},rubric,'weighted')
        self.assertFalse(verdict['critical_pass'])
        self.assertGreater(verdict['score'],0)
        self.assertLess(verdict['score'],1)
        off=score_items({'items':[{'id':r['id'],'pass':False} for r in rubric]},rubric,'weighted')
        self.assertEqual(off['score'],0)

    def test_historical_results_cannot_be_relabelled_as_new_dataset(self):
        source,conditions=dataset_source('core');tasks=load_tasks(source)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old-glm-5.3';old.mkdir()
            (old/'result.json').write_text('{}')
            with self.assertRaises(ValueError):validate_run_binding(root,'old',tasks,conditions)
            protocol=root/'protocols/new/tasks';protocol.mkdir(parents=True)
            (protocol/'manifest.json').write_text(json.dumps({'task_input_sha256':task_digest(tasks),'conditions':list(conditions)}))
            validate_run_binding(root,'new',tasks,conditions)
            tasks['lesson-builder__01']['expected_output']+=' changed'
            with self.assertRaises(ValueError):validate_run_binding(root,'new',tasks,conditions)

if __name__=='__main__':unittest.main()
