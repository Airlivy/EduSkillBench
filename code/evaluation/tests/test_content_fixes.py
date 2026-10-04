import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import content_fixes
from check_source_native import check


class ContentFixTests(unittest.TestCase):
    def test_ordered_edits_keep_auditable_history(self):
        ops = [dict(task_id='x', path=['user_prompt'], before=a, after=b,
                    reason='核对题意') for a, b in [('原题', '中间稿'), ('中间稿', '修订稿')]]
        with patch.object(content_fixes, 'operations', return_value=ops):
            cases = content_fixes.apply([dict(task_id='x', user_prompt='原题')])
            content_fixes.check_applied(cases)
            self.assertEqual(content_fixes.revised_prompt('x', '原题'), '修订稿')
            self.assertEqual([e['before'] for e in cases[0]['editorial_changes']], ['原题', '中间稿'])
            changed = copy.deepcopy(cases)
            changed[0]['user_prompt'] = '未登记修改'
            with self.assertRaises(ValueError):
                content_fixes.check_applied(changed)

    def test_source_drift_is_rejected(self):
        op = dict(task_id='x', path=['user_prompt'], before='原题', after='修订稿', reason='纠错')
        with patch.object(content_fixes, 'operations', return_value=[op]):
            with self.assertRaisesRegex(ValueError, 'drift'):
                content_fixes.apply([dict(task_id='x', user_prompt='别的题')])

    def test_complete_release_preserves_source_contract(self):
        result = check()
        self.assertEqual(result['cases'], 305)
        self.assertTrue(result['core_preserved'])
        self.assertTrue(result['original_weights_and_level_labels_preserved'])
        self.assertFalse(result['expert_certified'])


if __name__ == '__main__':
    unittest.main()
