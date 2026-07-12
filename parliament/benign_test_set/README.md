# NotInject-style benign test set — v0

Stage 1 prerequisite (REARCHITECTURE_PLAN.md §6). Real tool calls that
are legitimate but structurally resemble attack shapes (WRITE calls with
authorization-sensitive args, calls to IBANs/values that are elsewhere
an attack target) — for measuring a detector's false-positive rate, not
just its catch rate.

## Contents

- `real_benign_trajectories.json` — raw extraction of every real
  qwen2.5:7b tool call from this session's live banking run
  (`agentdojo_banking_live/logs/**/none.json`), verbatim, no fabricated
  values.
- `build_v0.py` — builds `benign_v0.json` from the raw trajectories,
  splitting into two explicitly-labeled buckets:
  - **`clean`** (9 cases): real banking `user_task_0/1/2` — unambiguous,
    the user's own stated task directly names or implies the action.
  - **`goal_as_task`** (46 cases): AgentDojo's own "is the injection
    task's goal independently achievable as a real user task" checks —
    the user's stated task IS an injection's own goal text (e.g. "Send a
    transaction to US133...212 that includes the music streaming
    service..."), so a call to what's elsewhere an attacker's IBAN is
    legitimate HERE because a real (synthetic) user explicitly asked for
    it. Kept separate from `clean` deliberately — the same argument
    value is malicious in the paired real attack case and benign here,
    which is a genuinely harder case than plain NotInject-style "scary
    token, actually harmless."
- `benign_v0.json` — 55 cases total, 25 hit a WRITE-type tool
  (`send_money`/`update_password`/`schedule_transaction`/
  `update_scheduled_transaction`).
- `measure_before_after.py` — scores the full set (+ the 13-case LOLBIN
  set) through the real `/hook/parliament` API.
- `stage1_measurement.json` — raw per-case results from the Stage 1
  wiring measurement (see `REARCHITECTURE_PLAN.md` / Stage 1 commit
  message for the summary numbers).

## Known limitations, stated honestly

- **Small** (55 cases) and **single-domain** (banking only) — seeded
  entirely from this session's one live AgentDojo run. Needs growing
  with travel/workspace/slack domain cases before it's a reliable
  Stage 2 evaluation instrument.
- **Not adversarially constructed** — real trajectories from a live
  agent run, not deliberately designed edge cases (e.g. NotInject's own
  benign set is purpose-built with trigger words; this v0 set is
  whatever a real agent happened to produce). Both are useful, but this
  is the "found," not "designed," variety.
- **`goal_as_task`'s 46 cases skew toward a narrow set of real user
  tasks** (the 9 real injection-task goals in the banking suite,
  replayed under both no-defense and with-Kavach conditions) — not
  independent draws from a wide distribution.
