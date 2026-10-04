"""Legacy patch maintenance: verified backups and atomic writes, no blind restore.

The corrected runner does not need these patches. Use only for a separate legacy environment.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import tempfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.eduskill-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.chmod(name, path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def transform(source, feature):
    ast.parse(source)
    if feature == 'retry':
        new, count = re.subn(r'anthropic\.Anthropic\((?:max_retries=\d+)?\)',
                             'anthropic.Anthropic(max_retries=5)', source)
        if count != 1:
            raise ValueError('Unsupported Anthropic constructor; no changes made')
    elif feature == 'truncation':
        # Replace just the assignment, retaining its indentation/if/return structure.
        tree = ast.parse(source)
        fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'read_trajectory'), None)
        if fn is None:
            raise ValueError('Unsupported template; no read_trajectory')
        source = re.sub(r'MAX_TRAJECTORY_CHARS = (?:50_000|200_000)', 'MAX_TRAJECTORY_CHARS = 200_000', source)
        if 'BENCHFLOW-KEEP-TAIL' in source:
            new = source
        else:
            new, count = re.subn(r'(?m)^(\s*)text = text\[:MAX_TRAJECTORY_CHARS\][^\n]*$',
                                 r'\1text = text[:120_000] + "\\n[Middle omitted]\\n" + text[-80_000:]', source)
            if count != 1:
                raise ValueError('Unsupported truncation; no changes made')
    else:
        if 'BENCHFLOW-FORCE-SKILL' in source:
            new = source
        else:
            old = '        instruction = case.question + "\\n"\n'
            if source.count(old) != 1:
                raise ValueError('Unsupported task generator; no changes made')
            new = source.replace(old, old + '        # BENCHFLOW-FORCE-SKILL\n'
                                 '        if with_skill:\n'
                                 '            instruction += "\\n## Required procedure\\n" + (dataset.skill_dir / "SKILL.md").read_text()\n')
    ast.parse(new)
    return new


def patch(path, feature, mode):
    path = Path(path)
    backup = path.with_name(path.name + '.eduskill-' + feature + '.backup')
    state = backup.with_suffix(backup.suffix + '.json')
    before = path.read_bytes()
    if mode == 'restore':
        if not backup.exists() or not state.exists():
            raise ValueError('No verified backup. Refusing to guess the pre-patch source; installed file untouched')
        record = json.loads(state.read_text())
        original = backup.read_bytes()
        if digest(original) != record['before']:
            raise ValueError('Backup hash mismatch')
        if digest(before) == record['before']:
            return 'Already restored'
        if digest(before) != record['after']:
            raise ValueError('File changed since patch; restore patches in reverse order')
        ast.parse(original)
        atomic_write(path, original)
        return 'Restored verified backup'
    after = transform(before.decode(), feature).encode()
    if after == before:
        return 'Already applied; no new restore point created'
    if backup.exists():
        record = json.loads(state.read_text())
        if digest(before) != record['before'] or digest(backup.read_bytes()) != record['before']:
            raise ValueError('Existing backup belongs to another source state')
    else:
        backup.write_bytes(before)
        state.write_text(json.dumps({'before': digest(before), 'after': digest(after)}, indent=2))
    atomic_write(path, after)
    return 'Applied after syntax validation; verified backup retained'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('feature', choices=['retry', 'truncation', 'force'])
    ap.add_argument('mode', choices=['apply', 'restore'])
    ap.add_argument('--framework-root', type=Path)
    a = ap.parse_args()
    root = a.framework_root
    if root is None:
        spec = importlib.util.find_spec('benchflow')
        if spec is None:
            ap.error('Use the BenchFlow interpreter or --framework-root; no implicit install lookup')
        root = Path(spec.origin).parent
    target = root / ('skill_eval/_core.py' if a.feature == 'force' else 'templates/judge.py.tmpl')
    try:
        print(patch(target, a.feature, a.mode))
    except (ValueError, OSError, SyntaxError) as e:
        ap.exit(1, str(e) + '\n')


if __name__ == '__main__':
    main()
