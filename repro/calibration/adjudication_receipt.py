"""Validate adjudication completeness and bind retained evidence to current data."""
import csv
import json
from collections import Counter
from pathlib import Path

from repro.calibration.review_content import payload
from repro.source_protocol import digest, load_release, prompt, validate, VERSION
from repro.source_runner import model_options, RECOVERY_POLICY

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / 'docs/data-quality/adjudication-20261002'


def check_decisions():
    document = json.loads((DIRECTORY / 'decisions.json').read_text())
    candidates = json.loads((DIRECTORY / 'content_current_candidates_20261001.json').read_text())
    before = {c['task_id']: c for c in json.loads((DIRECTORY / 'cases_before.json').read_text())}
    _, cases, manifest = load_release()
    current = {c['task_id']: c for c in cases}
    assert digest(candidates) == document['source_candidates_sha256']
    assert digest(manifest) == document['release_manifest_sha256']
    rows = document['decisions']
    assert len(rows) == len(candidates) == 197
    assert len({r['finding_id'] for r in rows}) == len(rows)
    assert {r['finding_id'] for r in rows} == {r['finding_id'] for r in candidates}
    counts = Counter(r['status'] for r in rows)
    assert set(counts) <= {'accepted_and_fixed', 'no_change_required'}
    for row in rows:
        tid = row['task_id']
        assert row['rationale'].strip()
        assert row['before_content_sha256'] == digest(payload(before[tid]))
        assert row['after_content_sha256'] == digest(payload(current[tid]))
        if row['status'] == 'accepted_and_fixed':
            assert row['related_edits'] and payload(before[tid]) != payload(current[tid])
    for tid, case in current.items():
        for field in ('user_prompt', 'context', 'expected_output'):
            assert case[field] == before[tid][field], (tid, field)
        if case['suite'] == 'core':
            assert case == before[tid]
        else:
            signature = lambda c: [(r['id'], r['name'], r['weight'], [l['label'] for l in r['levels']]) for r in c['criteria']]
            assert signature(case) == signature(before[tid])
    changed = {tid for tid in current if payload(current[tid]) != payload(before[tid])}
    assert changed == {r['task_id'] for r in rows if r['status'] == 'accepted_and_fixed'}
    assert document['pending'] == 0 and document['modified_cases'] == len(changed)
    assert document['accepted_and_fixed'] == counts['accepted_and_fixed']
    assert document['no_change_required'] == counts['no_change_required']
    return document, current


def collect_contrasts(current):
    selected = {}
    for name in ('adjudication-contrasts-20261002', 'adjudication-contrasts-boundary-20261002',
                 'adjudication-contrasts-counterevidence-20261002'):
        directory = ROOT / 'results_v2' / name
        if not (directory/'plan.json').exists():continue
        fixtures = {(c['task_id'], variant): (c, targets, answer)
                    for c, targets, variant, answer in json.loads((directory / 'fixtures.json').read_text())}
        for result in json.loads((directory / 'summary.json').read_text())['results']:
            key = result['task_id'], result['variant']
            case, targets, answer = fixtures[key]
            if digest(payload(case)) == digest(payload(current[key[0]])):
                path=directory/key[0]/key[1]/'result.json'
                if not path.exists():continue
                saved=json.loads(path.read_text())
                binding=digest({'case':current[key[0]],'answer':answer,'model':'deepseek-v4-pro',
                    'options':model_options('deepseek-v4-pro'),'version':VERSION,'recovery_policy':RECOVERY_POLICY,
                    'prompt_sha256':digest(prompt(current[key[0]],answer)),
                    'endpoint':'https://ark.cn-beijing.volces.com/api/plan/v1'})
                if saved['binding']!=binding:continue
                if validate(saved['raw_verdict'],current[key[0]],answer,require_counterevidence=True)!=saved['verdict']:continue
                selected[key] = dict(result, source_run=str(directory.relative_to(ROOT)),
                                     case_content_sha256=digest(payload(case)), answer_sha256=digest(answer))
    return list(selected.values())


def main():
    document, current = check_decisions()
    contrasts = collect_contrasts(current)
    changed = {r['task_id'] for r in document['decisions'] if r['status'] == 'accepted_and_fixed'}
    assert {(r['task_id'], r['variant']) for r in contrasts} == {(tid, v) for tid in changed for v in ('correct', 'wrong', 'off_topic')}
    summary = {k: v for k, v in document.items() if k != 'decisions'}
    summary.update(current_contrasts=len(contrasts), passed_contrasts=sum(r['passed'] for r in contrasts),
                   contrast_results=contrasts, historical_first_run='41/42; unchanged answer rechecked only after clarifying cn31_01 rubric boundary.')
    (DIRECTORY / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    with (DIRECTORY / 'decisions.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['序号', '题号', '裁决', '原审查意见', '裁决理由'])
        writer.writeheader()
        for r in document['decisions']:
            writer.writerow(dict(序号=r['adjudication_id'], 题号=r['task_id'],
                                 裁决='采纳并已修正' if r['status']=='accepted_and_fixed' else '不需修改',
                                 原审查意见=r['original_issue']['reason'], 裁决理由=r['rationale']))
    print(json.dumps({k:v for k,v in summary.items() if k!='contrast_results'}, ensure_ascii=False, indent=2))
    if not all(r['passed'] for r in contrasts):
        raise SystemExit('A current contrast check still fails; do not declare contrast acceptance.')


if __name__ == '__main__':
    main()
