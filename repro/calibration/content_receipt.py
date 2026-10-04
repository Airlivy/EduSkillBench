"""Collect only reviews and contrast checks matching the current scoring input."""
import csv
import json
from collections import Counter
from pathlib import Path

from repro.calibration.review_content import payload
from repro.source_protocol import digest, load_release


def main():
    _, cases, manifest = load_release()
    current = {c['task_id']: c for c in cases}
    reviews = {}
    for suffix in ('revised', 'final-delta', 'last-two', 'closure', 'material'):
        directory = Path(f'results_v2/full-content-review-{suffix}-20261001')
        snapshot = {c['task_id']: c for c in json.loads((directory / 'cases.json').read_text())}
        for result in json.loads((directory / 'summary.json').read_text())['results']:
            tid = result['task_id']
            if digest(payload(snapshot[tid])) == digest(payload(current[tid])):
                reviews[tid, result['model']] = dict(result, source_run=str(directory))
    models = ('deepseek-v4-pro', 'deepseek-v4-flash')
    missing = [(tid, m) for tid in current for m in models
               if reviews.get((tid, m), {}).get('status') != 'reviewed']
    if missing:
        raise ValueError(f'Missing current reviews: {missing}')
    contrasts = {}
    for suffix in ('20261001', 'coordination-20261001', 'closure-20261001', 'material-20261001'):
        directory = Path('results_v2/content-fix-contrasts-' + suffix)
        fixtures = {(c['task_id'], variant): (c, answer) for c, variant, answer
                    in json.loads((directory / 'fixtures.json').read_text())}
        for result in json.loads((directory / 'summary.json').read_text())['results']:
            key = result['task_id'], result['variant']
            case, answer = fixtures[key]
            if digest(payload(case)) == digest(payload(current[key[0]])):
                contrasts[key] = dict(result, source_run=str(directory), answer_sha256=digest(answer))
    dest = Path('docs/data-quality')
    issues = []
    rows = []
    for case in cases:
        tid = case['task_id']
        findings = []
        for model in models:
            result = reviews[tid, model]
            for finding in result['issues']:
                item = dict(task_id=tid, model=model, source_run=result['source_run'], **finding)
                item['finding_id'] = digest(item)
                item['disposition'] = 'AI候选意见，非已确认缺陷；不据此自动修改或宣布验收通过'
                findings.append(item)
        issues.extend(findings)
        rows.append(dict(task_id=tid, suite=case['suite'], content_sha256=digest(payload(case)),
                         reviews_completed=2, ai_candidates=len(findings),
                         reference_kind='原输出要求说明' if case['suite']=='core' else '来源未提供逐题标准答案',
                         review_status='存在AI分歧，不能据此认定有错或无错' if findings else '双模型未报内容问题，非专家认证'))
    receipt = dict(release_manifest_sha256=digest(manifest), cases=len(cases),
                   current_reviews=len(reviews), reviewed=sum(r['status']=='reviewed' for r in reviews.values()),
                   flagged_cases=sum(bool(r['ai_candidates']) for r in rows),
                   candidate_issues=len(issues), candidates_by_model=dict(Counter(i['model'] for i in issues)),
                   current_contrasts=len(contrasts), passed_contrasts=sum(r['passed'] for r in contrasts.values()),
                   contrast_cases=len({k[0] for k in contrasts}), full_expert_acceptance=False,
                   scope='结构检查、模型内容审查、少量实际评分对照分别记录；均不构成305题全部语义正确的保证。',
                   reviews=list(reviews.values()), contrasts=list(contrasts.values()))
    for name, value in [('content_acceptance_receipt_20261001.json', receipt),
                        ('content_current_candidates_20261001.json', issues)]:
        (dest / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    with (dest / 'content_case_ledger_20261001.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('reviews', 'contrasts')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
