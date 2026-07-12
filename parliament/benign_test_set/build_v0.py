#!/usr/bin/env python3
"""
NotInject-style benign tool-call test set, v0 -- Stage 1 prerequisite,
seeded from real qwen2.5:7b trajectories collected during this session's
live banking run (kavach_eval/reference_corpus_v0/proposed_minister_v0
investigation history).

Two buckets, kept explicitly distinct rather than merged:

  "clean" -- real banking user_tasks (user_task_0/1/2) with no synthetic
  goal-text ambiguity. These are genuinely, unambiguously legitimate:
  the user's own stated task names or clearly implies the action taken.
  This is the core NotInject-style set: calls containing "scary" tokens
  (send_money, update_password, credential-shaped args) that ARE actually
  legitimate, to measure a detector's false-positive rate.

  "goal_as_task" -- AgentDojo's own "is the injection task's goal
  independently achievable as a real user task" trajectories (the "none"
  attack-type runs recorded alongside every real injection pairing). The
  user's stated task text IS the injection's own goal text (e.g. "Send a
  transaction to US133...212 that includes the music streaming
  service..."), so calls that send money to what is elsewhere the
  attacker's IBAN are LEGITIMATE HERE because a real user explicitly
  asked for exactly that. Kept separate from "clean" because this is a
  genuinely harder case for a NotInject-style benign set: the same
  argument value is malicious in one context (real attack pair) and
  benign in another (this context) -- a detector needs the surrounding
  session/task context to get this right, not just the argument value in
  isolation. Flagged explicitly rather than silently merged into "clean,"
  since conflating the two would overstate how easy this benign set is.

Every entry's "tool"/"args" are copied VERBATIM from real logged
qwen2.5:7b tool calls -- no fabricated values.
"""
import json
from pathlib import Path

SOURCE = Path(r"C:\Users\ishan\AppData\Local\Temp\claude\c--Users-ishan-Desktop-Kavach\ef4b1a3b-08ff-424c-87f9-f88516cb207f\scratchpad\rearchitecture\real_benign_trajectories.json")

raw = json.loads(SOURCE.read_text(encoding="utf-8"))

CLEAN_FILES = {
    "benign\\local\\banking\\user_task_0\\none\\none.json",
    "benign\\local\\banking\\user_task_1\\none\\none.json",
    "benign\\local\\banking\\user_task_2\\none\\none.json",
}

cases = []
for traj in raw:
    bucket = "clean" if traj["source_file"] in CLEAN_FILES else "goal_as_task"
    for call in traj["calls"]:
        cases.append({
            "bucket": bucket,
            "source_file": traj["source_file"],
            "user_task_text": traj["user_task_text"],
            "tool": call["tool"],
            "args": call["args"],
            "why_legitimate": (
                "user's own stated task names this exact action"
                if bucket == "clean"
                else "user's stated task IS this exact goal text (AgentDojo's "
                     "own no-injection utility check) -- legitimate here even "
                     "though the same argument value is the attacker's target "
                     "in the paired real injection case"
            ),
        })

# de-dup exact (tool, args, source_file) repeats (e.g. repeated
# get_most_recent_transactions calls with identical args in a retry loop)
seen = set()
deduped = []
for c in cases:
    key = (c["source_file"], c["tool"], json.dumps(c["args"], sort_keys=True, default=str))
    if key not in seen:
        seen.add(key)
        deduped.append(c)

out_path = Path(__file__).parent / "benign_v0.json"
out_path.write_text(json.dumps(deduped, indent=2, default=str), encoding="utf-8")

n_clean = sum(1 for c in deduped if c["bucket"] == "clean")
n_goal = sum(1 for c in deduped if c["bucket"] == "goal_as_task")
print(f"wrote {len(deduped)} cases ({n_clean} clean, {n_goal} goal_as_task) to {out_path}")

# Report which cases contain "scary" tokens (credential-shaped, WRITE-type)
scary_tools = {"send_money", "update_password", "schedule_transaction", "update_scheduled_transaction"}
n_scary = sum(1 for c in deduped if c["tool"] in scary_tools)
print(f"{n_scary}/{len(deduped)} cases use a WRITE/scary-shaped tool "
      f"(send_money/update_password/schedule_transaction/update_scheduled_transaction)")
