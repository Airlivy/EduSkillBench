# EduSkillBench

**EduSkillBench** is a benchmark for evaluating whether reusable educational agent Skills improve the performance of large language models on realistic education tasks.

The benchmark collects publicly available education-oriented Agent Skills, maps them to educational scenarios inspired by EduBench, constructs Skill-aligned tasks and rubrics, and compares **With-Skill** against **No-Skill** execution.

## Overview

EduSkillBench v1 contains:

* **18 education-oriented Agent Skills**
* **54 benchmark tasks**
* **14 single-turn Skills / 42 single-turn tasks**
* **4 multi-turn Skills / 12 multi-turn tasks**
* Coverage of **6 EduBench educational scenario categories**

The Skills are collected from existing open-source educational Skill repositories rather than newly invented for this benchmark.

## Benchmark Structure

```text
EduSkillBench/
├── data/
│   ├── single_turn_tasks.csv
│   ├── multi_turn_tasks.csv
│   ├── skill_mapping.csv
│   └── release_manifest.json
├── skills/
│   ├── single_turn/
│   └── multi_turn/
├── code/
│   ├── generation/
│   ├── evaluation/
│   └── utils/
├── results/
├── README.md
└── THIRD_PARTY_NOTICES.md
```

## Skill Collection

Skills were collected from two public repositories:

* `GarethManning/education-agent-skills`
* `YujxZJCN/teaching-skills`

After filtering for relevance, executability, and compatibility with educational benchmark scenarios, **18 Skills** were retained.

The mapping between Skills and EduBench-inspired educational scenarios is provided in:

```text
data/skill_mapping.csv
```

EduSkillBench v1 currently covers six educational scenario categories. No artificial Skills were created solely to fill uncovered categories.

## Tasks

### Single-turn

The single-turn benchmark contains:

```text
14 Skills × 3 tasks = 42 tasks
```

The released tasks are available at:

```text
data/single_turn_tasks.csv
```

### Multi-turn

The multi-turn portion contains:

```text
4 Skills × 3 tasks = 12 tasks
```

The released tasks are available at:

```text
data/multi_turn_tasks.csv
```

The multi-turn tasks are included in the benchmark release but are **not part of the main v1 empirical evaluation**, because they require a dedicated learner-agent multi-turn execution protocol.

## Experimental Setup

The current v1 evaluation uses:

* **Model:** Qwen3.7-Plus
* **Agent:** OpenCode
* **Evaluation framework:** BenchFlow
* **Execution:** Docker sandbox
* **Comparison:** With-Skill vs. No-Skill

BenchFlow compatibility adjustments used in our environment are documented in:

```text
code/utils/patch_benchflow.sh
```

## Results

The main experiment evaluates all 42 single-turn tasks under both conditions:

```text
42 tasks × 2 settings = 84 runs
```

All **84/84 runs** were successfully completed.

| Setting       | Average Reward |
| ------------- | -------------: |
| With-Skill    |          0.948 |
| No-Skill      |          0.767 |
| Absolute Lift |         +0.180 |

Skill augmentation therefore improves average reward by **18.0 percentage points** in the current single-turn evaluation.

Across the 14 evaluated Skills:

* **10/14** improve
* **3/14** remain unchanged
* **1/14** decreases

The three unchanged Skills have ceiling-level baseline performance, while `hinge-question-designer` is the only Skill showing a negative result.

Detailed results are available in:

```text
results/single_turn_overall.json
results/single_turn_skill_summary.csv
```

## Quick Start

### Requirements

The v1 experiments were conducted with:

* Python 3.12
* BenchFlow 0.6.7
* Docker
* OpenCode
* Qwen3.7-Plus

Make sure Docker is running and `bench` is available in your environment.

### Configure the model endpoint

API credentials must be provided through environment variables and must not be committed to the repository.

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_BASE_URL="YOUR_OPENAI_COMPATIBLE_ENDPOINT"
```

If you use a standard provider configuration supported directly by BenchFlow, configure the corresponding environment variables instead.

### BenchFlow compatibility patch

Our experiments used BenchFlow 0.6.7 with an OpenAI-compatible endpoint and a non-OpenAI judge model.

For this configuration, apply the included compatibility patch:

```bash
bash code/utils/patch_benchflow.sh
```

The patch forwards the custom endpoint variables to the verifier and prevents the judge model from being replaced by the default OpenAI model.

### Run the single-turn benchmark

Run all 42 single-turn tasks under the released evaluation configuration:

```bash
bash code/evaluation/run_single_turn_v1.sh
```

The script evaluates the released Skills with:

* Agent: `opencode`
* Model: `qwen3.7-plus`
* Sandbox: `docker`
* Concurrency: `1`

Runtime artifacts are written under `jobs/` and are intentionally excluded from version control.

### Aggregate results

After evaluation, summarize the completed runs with:

```bash
python code/evaluation/summarize_single_turn_v1.py
```

The released aggregate results are stored in:

```text
results/single_turn_overall.json
results/single_turn_skill_summary.csv
```

### Task generation

The task-generation pipeline is provided under:

```text
code/generation/
```

The released benchmark tasks are already available under `data/`; regeneration is not required to reproduce the main evaluation.

### Multi-turn evaluation

The 12 multi-turn tasks and four associated Skills are included in the benchmark release, but the v1 empirical results cover only the 42 single-turn tasks.

A dedicated learner-agent multi-turn execution protocol is left for future work.

## Limitations

EduSkillBench v1 has several limitations.

First, only 14 Skills and 42 single-turn tasks are included in the main empirical evaluation.

Second, each Skill currently contains three evaluation cases, so Skill-level differences should not be interpreted as strong causal evidence.

Third, the 12 multi-turn tasks require a dedicated execution protocol and are released for future evaluation rather than included in the current main results.

Finally, Skill augmentation is not universally beneficial. The negative result observed for one Skill suggests that over-constraining instructions, task-Skill mismatch, or evaluation variance may reduce performance in some settings.

## Third-Party Skills

EduSkillBench redistributes selected third-party educational Agent Skills for benchmark reproducibility.

These Skills retain their original licenses and attribution. See:

```text
THIRD_PARTY_NOTICES.md
```

for details.

## Status

This repository contains the **EduSkillBench v1 benchmark release and single-turn evaluation results**.

Multi-turn execution and larger-scale evaluation are planned as future extensions.
