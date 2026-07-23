# `gpt4o_real_trajectory_benign_control.json` — benign control for the 629-trajectory replay

## Why this exists

`gpt4o_real_trajectory_expansion.json` (467/629 = 74.2%) reports how often
Kavach fires on AgentDojo's real recorded GPT-4o **attack** trajectories,
under the criterion "Block or Escalate, any minister, at any point in the
session." That number had no benign comparison point at the same
granularity anywhere in the paper — a real gap flagged in review. This
file closes it.

## What it is

AgentDojo also publishes one recorded **no-injection** transcript per user
task per suite (`runs/gpt-4o-2024-05-13/<suite>/user_task_N/none/none.json`
— `attack_type: null`, `injection_task_id: null`; confirmed by inspection,
not assumed from the filename). These are real GPT-4o transcripts with the
model attempting its ordinary task, with zero attacker instruction ever
injected. 124 such files exist across the four suites (banking 25, slack
26, travel 27, workspace 46).

## How it was generated

`benchmarks/_gpt4o_real_trajectory_benign_control.py`, a direct adaptation
of `benchmarks/_gpt4o_real_trajectory_expansion.py` (the script behind the
629-trajectory attack number): identical dispatch/session/"ever fired"
aggregation logic, same `POST /hook/parliament` wire format, same
Block-or-Escalate-any-minister-anywhere criterion — only the input file
set changes (no-injection transcripts instead of `important_instructions`
attack transcripts). The AgentDojo `runs/` data was sparse-checked-out from
`github.com/ethz-spylab/agentdojo` into `scratch_agentdojo_repo/` (not
committed — regenerate via `git sparse-checkout` if needed; see the script
for the exact path).

## Result

Kavach fires on 80/124 (64.5%) of these real, unattacked trajectories, under
the identical criterion that gives 74.2% on the attack set:

| suite     | n  | fired | rate  |
|-----------|----|-------|-------|
| banking   | 25 | 17    | 68.0% |
| slack     | 26 | 26    | 100%  |
| travel    | 27 | 8     | 29.6% |
| workspace | 46 | 29    | 63.0% |

This is consistent with (slightly below) the paper's already-disclosed
67.3% agent-shaped benign Escalate rate (§3.8) — the same session-level
firing behavior that catches attacks also fires on most ordinary sessions.
It does not undermine 74.2%; it recontextualizes what that number means
(a session-level sensitivity measure, not a precision measure) and is
reported as such in `paper/section_4_deployment.tex` §4.6.
