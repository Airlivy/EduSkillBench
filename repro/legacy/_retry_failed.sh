#!/usr/bin/env bash
# Resume the same frozen corrected experiment; the shared scanner selects missing cells.
set -euo pipefail
REPRO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${BENCHFLOW_PYTHON:-python3}" "$REPRO_DIR/runner.py" "$@"
