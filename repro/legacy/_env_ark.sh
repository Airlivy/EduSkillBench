#!/usr/bin/env bash
# Optional shell helper; never eval credential-bearing scripts or print keys.
if [ -z "${ARK_API_KEY:-}" ]; then
  echo 'Set ARK_API_KEY in your shell.' >&2
  return 2 2>/dev/null || exit 2
fi
if [ -z "${ANTHROPIC_BASE_URL:-}" ]; then
  echo 'Set ANTHROPIC_BASE_URL explicitly for this experiment.' >&2
  return 2 2>/dev/null || exit 2
fi
export ARK_API_KEY ANTHROPIC_BASE_URL
export ANTHROPIC_API_KEY="$ARK_API_KEY"
if [ "${1:-}" = '--check' ]; then
  echo 'Credentials present; values hidden.'
fi
