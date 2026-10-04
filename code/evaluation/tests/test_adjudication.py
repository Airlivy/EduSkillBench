import json
import unittest
from unittest.mock import patch

from repro.calibration.adjudication_receipt import check_decisions, DIRECTORY
from repro.source_protocol import load_release


class AdjudicationTests(unittest.TestCase):
    def test_every_candidate_has_bound_decision_and_edits_are_limited(self):
        document, _ = check_decisions()
        self.assertEqual(document['total'], 197)
        self.assertEqual(document['modified_cases'], 14)
        self.assertEqual(document['pending'], 0)

    def test_changed_scoring_input_invalidates_old_receipt(self):
        directory, cases, manifest = load_release()
        case = next(c for c in cases if c['task_id']=='lesson-builder__cn31_01')
        case['criteria'][4]['description'] += '未经裁决的追加要求'
        with patch('repro.calibration.adjudication_receipt.load_release', return_value=(directory, cases, manifest)):
            with self.assertRaises(AssertionError):
                check_decisions()

    def test_group_allocation_excludes_material_design_only(self):
        _, cases, _ = load_release()
        before = json.loads((DIRECTORY / 'cases_before.json').read_text())
        for snapshot, expected in [(before, ['D1','D3','D5','D7']), (cases, ['D1','D5','D7'])]:
            case = next(c for c in snapshot if c['task_id']=='project-brief-designer__cn52_04')
            self.assertEqual(case['applicable_ids'], expected)


if __name__ == '__main__':
    unittest.main()
