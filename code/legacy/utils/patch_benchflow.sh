#!/usr/bin/env bash
set -e

ROOT=$(find ~/.local/share/uv/tools/benchflow/lib/python*/site-packages/benchflow -maxdepth 0 -type d | head -1)

CORE="$ROOT/skill_eval/_core.py"
JUDGE="$ROOT/templates/judge.py.tmpl"

python3 - "$CORE" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()

for anchor in ['"OPENAI_API_KEY",']:
    parts = [
        '"OPENAI_BASE_URL",',
        '"NO_PROXY",',
        '"no_proxy",',
    ]
    pos = 0
    while True:
        i = s.find(anchor, pos)
        if i < 0:
            break
        end = i + len(anchor)
        block = s[end:end+150]
        missing = [x for x in parts if x not in block]
        if missing:
            s = s[:end] + "\n            " + "\n            ".join(missing) + s[end:]
        pos = end + 1

p.write_text(s)
PY

sed -i 's/model=model if is_openai_model else "gpt-4o-mini"/model=model/' "$JUDGE"

echo "BenchFlow custom-endpoint patch applied."
