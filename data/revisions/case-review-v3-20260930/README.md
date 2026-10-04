# 42 + 263 full revision v3 — not a released benchmark

All 305 rows have been reviewed and edited at the task-definition level. All 263 expanded cases now have distinct case-specific reference guidance and rubric text. Shared contexts are short cohort facts, not source-wide stories or solution procedures. This does **not** certify that every educational judgment is correct.

The candidate preserves historical IDs solely for traceability. Its questions, criteria and scores are a new version. Do not combine its scores with v1/v2, or silently replace the historical CSVs.

## Artifacts

- Two task CSVs: revised original 42 and expanded 263.
- `changes.json`: exact before/after fields for all 305 rows.
- `merged_issue_ledger.csv`: 641 issue entries from the senior review, with treatment and unresolved acceptance status. Entries are issues, not unique task counts.
- `source_bindings.json`: 263 Chinese excerpts, local original-document paths and hashes. Every normalized excerpt was found in its source document. This validates local positioning, not independent bilingual quality or upstream redistribution rights. The principal-variable question is source scene 3, not scene 1 of the original document.
- `skill_routing_review.json`: nine cn29 cases quarantined from hinge-question routing gold; other labels remain candidates, not certified gold. A broad lesson consultation is not automatically rejected just because it requests a subtask.
- `acceptance_cases.json`: case-specific review anchors and prohibited errors; these are not completed model responses or successful live judge tests.
- `evals.json`: isolated evaluation specification retaining criteria, weights and identifiers.
- `split_groups.json`: evaluation-only candidate partition. Source groups are preserved; no training set is created. Cross-source semantic leakage is not certified absent.
- `release_gate.json`: currently closed; **zero cases formally released by this revision**.
- `historical_result_integrity.json`: all 1,114 saved result.json files unchanged against the pre-cleanup hash inventory.

## Scoring

V3 explicitly selects weighted scoring. Original-case criterion totals are preserved when independent sentences are split; expanded-case checks are newly defined equal-weight checks. Scores are not numerically equivalent to the historical protocol. Critical flags identify content/errors needing particular review, but are not an implemented score cap in the current judge. Legacy consumers that read only `expected_behavior` still cannot implement weighted scoring; use the full rubric contract.

Sentence splitting is a mechanical aid, not proof that every criterion is perfectly atomic. Some deliverable checks retain related requirements. These need live contrast calibration and independent review before release. No final benchmark acceptance is inferred from passing unit tests.

## Build and validate

```bash
python3 code/evaluation/revise_cases_v3.py
python3 -B -m unittest discover -s code/evaluation/tests -v
python3 -B -m unittest discover -s repro/tests -v
```

To compile into an **empty isolated directory** for review:

```bash
python3 code/evaluation/build_evals_cn263.py \
  --source data/revisions/case-review-v3-20260930/single_turn_tasks_cn263.csv \
  --output /tmp/eduskill-v3-review \
  --review-only
```

The compiler refuses an unreleased revision without `--review-only`, refuses overwriting historical skills with this revision, preserves rubric weights, and copies supporting Skill resources. The production runner is not switched to these candidate CSVs.

## Remaining acceptance gates

Independent content and bilingual review; appropriate Skill routing; complete-answer positive/negative judge calibration; cross-source overlap review before any training split; upstream source/version and redistribution confirmation. No API credentials were available during this run, and no model or judge calls were made.
