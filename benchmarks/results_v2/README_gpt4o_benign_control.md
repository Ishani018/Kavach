# `gpt4o_real_trajectory_benign_control.json` — benign control for the 629-trajectory replay

## Why this exists

`gpt4o_real_trajectory_expansion.json` (467/629 = 74.2%) reports how often
Kavach fires on AgentDojo's real recorded GPT-4o **attack** trajectories,
under the criterion "Block or Escalate, any minister, at any point in the
session." That number had no benign comparison point at the same
granularity anywhere in the paper — a real gap flagged in review. This
file closes it.

## A bug was found and fixed in this file's own generation (read this first)

The first version of this script counted **124** trajectories, one per
subdirectory under each suite that had a `none/none.json` file. That was
wrong: AgentDojo's suite directories contain both `user_task_N/` (real
user tasks) and `injection_task_N/` (attack-task bookkeeping) folders, and
**both** happen to have a `none/none.json`. The `injection_task_N` copies
are not independent user tasks — their own `user_task_id` field literally
reads `"injection_task_0"`, not a real task name, and they duplicate the
same file structure as a real `none.json` with a mislabeled ID. Confirmed
by diffing an `injection_task_0/none/none.json` against a real
`user_task_0/none/none.json` field-by-field.

The correct count is **97** — exactly matching AgentDojo's own published
"97 user tasks" total (16 banking + 21 slack + 20 travel + 40 workspace).
The fix: only iterate directories named `user_task_*`. The buggy 124-file
run is kept at `gpt4o_real_trajectory_benign_control_BUGGY_124.json` /
`_gpt4o_benign_control_run_BUGGY_124.log` for the record, not used
anywhere in the paper.

## What it is

AgentDojo publishes one recorded **no-injection** transcript per real user
task (`runs/gpt-4o-2024-05-13/<suite>/user_task_N/none/none.json` —
`attack_type: null`, `injection_task_id: null`, confirmed by inspection).
These are real GPT-4o transcripts with the model attempting its ordinary
task, zero attacker instruction ever injected. 97 such files exist across
the four suites (banking 16, slack 21, travel 20, workspace 40).

## How it was generated

`benchmarks/_gpt4o_real_trajectory_benign_control.py`, a direct adaptation
of `benchmarks/_gpt4o_real_trajectory_expansion.py` (the script behind the
629-trajectory attack number): identical dispatch/session/"ever fired"
aggregation logic, same `POST /hook/parliament` wire format, same
Block-or-Escalate-any-minister-anywhere criterion. The AgentDojo `runs/`
data was sparse-checked-out from `github.com/ethz-spylab/agentdojo` into
`scratch_agentdojo_repo/` (not committed — regenerate via `git
sparse-checkout`, see the script's docstring for the exact path).

## Result

Kavach fires on 64/97 (66.0%) of these real, unattacked trajectories,
under the identical criterion that gives 74.2% on the attack set. Split
by verdict, not just the combined rate:

| | count | rate |
|---|---|---|
| Any fire (Block-or-Escalate) | 64/97 | 66.0% |
| **Hard-Block** (actual breakage) | **4/97** | **4.1%** |
| Soft Escalate | 60/97 | 61.9% |

Per-minister credit (which minister the Speaker credited for each of the
64 fired trajectories):

| minister | count | share |
|---|---|---|
| CHANNEL | 28 | 43.8% |
| EXECUTOR | 19 | 29.7% |
| NAVIGATOR | 12 | 18.8% |
| VAULT | 5 | 7.8% |

Per-suite:

| suite | n | fired | rate |
|---|---|---|---|
| banking | 16 | 12 | 75.0% |
| slack | 21 | 21 | 100% |
| travel | 20 | 7 | 35.0% |
| workspace | 40 | 24 | 60.0% |

**Reading this correctly:** NAVIGATOR (the paper's admittedly weak,
unvalidated minister) is a minority contributor (18.8%), not the driver of
this rate — CHANNEL and EXECUTOR together account for 73% of the fires.
The near-two-thirds firing rate is a real property of the validated
ministers, not an artifact of the known-weak one. Separately, the
hard-block rate (4.1%) is low — the system rarely breaks legitimate
sessions outright; it mostly asks for human review, consistent with (and
independently confirming) the paper's already-disclosed 67.3% agent-shaped
Escalate rate (§3.8). It does not undermine 74.2%; it recontextualizes
what that number means (a session-level sensitivity measure, not a
precision measure), reported as such in `paper/section_4_deployment.tex`
§4.6 and in the abstract.
