#!/usr/bin/env bash
set -euo pipefail
REPRO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${BENCHFLOW_PYTHON:-python3}" "$REPRO_DIR/runner.py" \
  --tag forcecheck-corrected --models deepseek-v4-flash --skill-mode forced \
  --task-id hinge-question-designer__01 "$@"
