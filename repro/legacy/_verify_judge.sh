#!/usr/bin/env bash
set -euo pipefail
REPRO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${BENCHFLOW_PYTHON:-python3}" "$REPRO_DIR/runner.py" \
  --tag judgecheck-corrected --models glm-5.3 --task-id lesson-builder__01 "$@"
