#!/usr/bin/env bash
# Bounded retries, same lock/inventory as the batch runner. Default is a dry-run.
set -euo pipefail
REPRO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${BENCHFLOW_PYTHON:-python3}" "$REPRO_DIR/runner.py" --rounds 2 "$@"
