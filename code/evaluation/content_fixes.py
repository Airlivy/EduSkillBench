"""Apply reviewed literal edits; fail on drift rather than silently replacing data."""
import json
from pathlib import Path
SPEC=Path(__file__).with_name('source_content_fixes_20261001.json')

def operations():
    return (json.loads(SPEC.read_text())['operations']
            + json.loads(SPEC.with_name('source_content_fixes_20261002.json').read_text())['operations'])

def apply(cases):
    byid={c['task_id']:c for c in cases}
    for edit in operations():
        c=byid[edit['task_id']];target=c
        for key in edit['path'][:-1]:target=target[key]
        key=edit['path'][-1]
        if target[key]!=edit['before']:raise ValueError('Content edit input drift: '+edit['task_id']+' '+str(edit['path']))
        target[key]=edit['after']
        c.setdefault('editorial_changes',[]).append({'field':'/'.join(map(str,edit['path'])),'before':edit['before'],'after':edit['after'],'reason':edit['reason']})
    return cases

def revised_prompt(task_id,original):
    for edit in operations():
        if edit['task_id']==task_id and edit['path']==['user_prompt']:
            if original!=edit['before']:raise ValueError('Prompt source drift')
            original=edit['after']
    return original

def check_applied(cases):
    byid={c['task_id']:c for c in cases}
    final={(e['task_id'],tuple(e['path'])):e for e in operations()}
    for edit in final.values():
        value=byid[edit['task_id']]
        for key in edit['path']:value=value[key]
        if value!=edit['after']:raise ValueError('Unapplied content fix: '+edit['task_id'])
