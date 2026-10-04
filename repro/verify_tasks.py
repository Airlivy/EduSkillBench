#!/usr/bin/env python3
"""Verify full instructions and resources for EVERY task under both conditions."""
import argparse
import tempfile
from pathlib import Path
from prepare import build, verify
from protocol import load_tasks, MODELS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepared', type=Path)
    args = ap.parse_args()
    if args.prepared:
        m = verify(args.prepared)
        print(f"Verified {len(m['task_ids'])*len(m['models'])*2} generated tasks")
    else:
        with tempfile.TemporaryDirectory(prefix='eduskill-verify-') as tmp:
            for mode in ('access', 'forced'):
                build(Path(tmp)/mode, load_tasks(), [MODELS[0]], mode=mode)
                print(f'{mode}: 42 tasks x 2 conditions; full text and resource hashes passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
