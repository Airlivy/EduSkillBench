#!/usr/bin/env bash
set -euo pipefail
REPRO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${BENCHFLOW_PYTHON:-python3}" "$REPRO_DIR/legacy/patch_framework.py" truncation "$@"
