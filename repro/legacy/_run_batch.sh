#!/usr/bin/env bash
# Dry-run by default; explicit --execute enables model calls.
set -euo pipefail
REPRO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${BENCHFLOW_PYTHON:-python3}" "$REPRO_DIR/runner.py" "$@"
