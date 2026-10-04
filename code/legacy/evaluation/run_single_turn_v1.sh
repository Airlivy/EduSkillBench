#!/usr/bin/env bash

mkdir -p logs

for d in skills/single_turn/*; do
  [ -f "$d/evals/evals.json" ] || continue
  s=$(basename "$d")

  echo
  echo "========== $s =========="

  bench skills eval "$d" \
    --agent opencode \
    --model qwen3.7-plus \
    --sandbox docker \
    --concurrency 1 \
    --jobs-dir "jobs/formal-single-v1/$s"

done
