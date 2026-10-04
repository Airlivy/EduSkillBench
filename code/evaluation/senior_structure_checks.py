"""Adapted from the senior's build_task_acceptance_ledger.py structural() only.
Original snapshot: docs/data-quality/review-inputs/SENIOR_ACCEPTANCE_CODE_2026-09-28.py
Changes: float tolerance; project legacy eval fields; also compare preserved weighted rubric.
Historical classify() labels are deliberately not reused as current semantic verdicts.
"""
import collections
import csv
import json
import math

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def structural(rows, root):
    issues = collections.defaultdict(list)
    ids = [r['task_id'] for r in rows]
    cases = {}
    for path in root.glob('*/evals/evals.json'):
        payload = json.loads(path.read_text())
        for case in payload['cases']:
            if case['id'] in cases:
                issues[case['id']].append('duplicate eval id')
            cases[case['id']] = (payload['skill_name'], case)
    for row in rows:
        tid = row['task_id']
        if ids.count(tid) != 1:
            issues[tid].append('duplicate csv id')
        if any(not value.strip() for value in row.values()):
            issues[tid].append('empty field')
        rubric = json.loads(row['rubric'])
        if not math.isclose(sum(c['points'] for c in rubric), 100, rel_tol=1e-9, abs_tol=1e-9):
            issues[tid].append('rubric points do not sum to 100')
        expected = {'id': tid, 'question': row['context']+'\n\n'+row['user_prompt'],
                    'ground_truth': row['expected_output'],
                    'expected_behavior': [c['description'] for c in rubric]}
        actual = cases.get(tid)
        projected = (actual[0], {k: actual[1].get(k) for k in expected}) if actual else None
        if projected != (row['skill_id'], expected):
            issues[tid].append('csv/evals mismatch')
        if actual and actual[1].get('rubric') != rubric:
            issues[tid].append('weighted rubric mismatch')
        if not (root / row['skill_id'] / 'SKILL.md').is_file():
            issues[tid].append('missing SKILL.md')
    extra_ids = sorted(set(cases) - set(ids))
    return issues, extra_ids


