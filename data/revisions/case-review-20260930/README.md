# Case review 2026-09-30 — candidate, not released

The original CSVs and historical scores remain the experiment source of record. These revisions are isolated content-review candidates, not a new accepted benchmark release.

- `single_turn_tasks.csv`: 42 original tasks, 27 rows revised.
- `single_turn_tasks_cn263.csv`: 263 expanded tasks, 70 rows revised.
- `changes.json`: field-level before/after values and reasons for 97 changed rows.
- `review_inventory.csv`: all 305 rows; unchanged means not accepted, not error-free.
- `acceptance_cases.json`: authored positive anchors and error examples for 72 cases; not a record of independent judge passes.
- `result_evidence.json`: 46 selected verdicts mentioning truncation; review flags, not automatic score invalidation.
- `truncation_case_evidence.json`: saved response contradicting a zero verdict's claim that the final answer was not visible to the judge.
- `manifest.json`: source and artifact hashes, scope and limitations.

Build: `python3 code/evaluation/revise_cases_20260930.py`

Check: `python3 -B -m unittest discover -s code/evaluation/tests -v`

The six offline tests check data/ledger integrity, unchanged sources, saved verdict hashes, numerical integration, SIR arithmetic, combinatorial enumeration and other numerical anchors. They do not establish full semantic correctness, educational suitability or live judge reliability. Existing 34 reproduction tests also passed.

Changing a question requires new agent answers in both conditions. Changing only a rubric may permit regrading existing complete answers, but needs a new rubric/version binding. Do not mix these scores with historical v2 scores. The current production protocol is not switched to these files.

Pending: independent case review; remaining source-template groups (including cn21 observable-outcome criteria and cn57 role-assignment contradictions); live judge contrast checks; revised-case experiments. The 208 unchanged tasks are not independently accepted.

Scientific checks: the flux correction was independently integrated using the surface-flux definition in [OpenStax, Faraday's Law](https://openstax.org/books/university-physics-volume-2/pages/13-1-faradays-law). The SIR estimate follows directly from the explicitly supplied equations and assumptions; it is a synthetic teaching calculation, not an empirical epidemic estimate. For the importance of generation intervals, see [Wallinga and Lipsitch (2007)](https://pubmed.ncbi.nlm.nih.gov/17476782/).
