# Stage 1: deterministic (no-LLM) provenance tier — design

## Scope, per explicit constraint

No LLM in the per-call decision path. Plan-time extraction (session start,
once) is allowed to use rules only for this prototype — genuinely no LLM
call anywhere in this tier, not even at plan time, since the rules below
turned out sufficient for AgentDojo's banking suite's real tool schemas
(confirmed by direct reading of `banking_client.py`, not assumed).

## What "WRITE-type/security-critical" means here, concretely

Read the real banking tool signatures directly
(`.venv/Lib/site-packages/agentdojo/default_suites/v1/tools/banking_client.py`)
rather than guessing at a generic rule. The write-type tools in this
suite:

- `send_money(recipient, amount, subject, date)`
- `schedule_transaction(recipient, amount, subject, date, recurring)`
- `update_scheduled_transaction(id, recipient=None, amount=None, ...)`
- `update_password(password)`
- `update_user_info(street=None, city=None, ...)` (not in banking_client.py
  directly but present in the suite's user account tools)

**Rule (deterministic, no LLM)**: a tool is WRITE-type if its name matches
any of a small verb-prefix list (`send_`, `schedule_`, `update_`,
`delete_`, `create_`, `book_`, `reserve_`, `transfer_`, `invite_`,
`remove_`, `add_`, `share_`, `grant_`) — this is exactly the prompt's own
suggested pattern (`send_money, transfer, update_password, book_,
delete_`), generalized to a prefix list rather than hardcoded per-tool
names so it works across banking/travel/workspace/slack without
suite-specific code. Confirmed against the real tool names across all
four v1 suites (banking: `send_money`/`schedule_transaction`/
`update_scheduled_transaction`/`update_password`; travel:
`reserve_hotel`; workspace: `send_email`/`delete_file`/
`create_calendar_event`/`share_file`; slack: `invite_user_to_slack`/
`remove_user_from_slack`/`add_user_to_channel`) — the prefix list covers
every real WRITE tool in the local suites without needing an LLM to
classify them.

For each WRITE tool, the **critical parameter(s)** are whichever
arguments hold a real-world identifier/value with authorization
consequence: `recipient` (send_money/schedule_transaction — the exact
STEWARD-target case), `password` (update_password), `amount` (secondary,
see limitations), `file_id`/`event_id` (delete/update-by-id tools). The
rule: any string- or numeric-typed parameter whose name matches a small
list (`recipient`, `password`, `amount`, `email`, `phone`,
`account`/`iban`, `file_id`, `user`, `channel`) is treated as critical;
everything else (dates, booleans, free-text subjects/descriptions) is
not checked, since those don't carry the same "who gets the money /
what's the new password" authorization stakes AuthGraph and DRIFT both
target.

## Deterministic authorization plan (Stage 1's "Plan-time" step)

At session start, from the user's task text ONLY (never tool outputs,
per the prompt's explicit constraint) — extract:

1. **Literal values named directly in the instruction.** Simple
   deterministic extraction: regex-scan the instruction text for
   substrings that look like IBANs (`[A-Z]{2}\d{2}[A-Z0-9]{10,30}`),
   quoted strings (`'...'` or `"..."`), and standalone email addresses.
   Each matched literal becomes an **authorized literal value** — if a
   WRITE call's critical parameter matches one of these verbatim, it's
   pre-authorized without needing any provenance trace at all (this
   reuses exactly the "literal" constraint type already validated in
   the Option B ablation — `banking_IT7`'s clean win there is the same
   mechanism).
2. **Everything else is provenance-checked at call time** (Stage 1's
   real mechanism, below) — no plan-time guess about which prior tool
   "should" produce a given value; the check happens when the WRITE call
   actually occurs, against whatever the session has actually observed
   by then.

This keeps Stage 1 fully deterministic: literal-matching is regex, and
provenance-matching (below) is string containment against real observed
tool-result text — no classifier, no LLM, nothing with weights to
overfit.

## Provenance check (Stage 1's core mechanism)

At each proposed WRITE-type tool call, for each critical parameter:

1. **Already covered by a plan-time literal match?** → PASS, no further
   check.
2. **Otherwise, search the session's tool-result history** (every prior
   `ChatToolResultMessage.content`/tool-output text this session has
   actually produced) **for the exact argument value as a substring.**
   - If the value string appears in **at least one** prior tool result →
     PASS (the value has a legitimate, observed origin in this session's
     own tool outputs — it's not being invented or smuggled in from
     nowhere).
   - If the value string does **not** appear anywhere in the session's
     tool-result history at all → **ABSTAIN** (the deterministic tier
     cannot resolve this — defer to the ministers' verdict, per the
     prompt's explicit "don't guess" instruction). A completely novel
     value with no traceable origin isn't necessarily an attack (the
     model could have computed it, e.g. "transfer half of $200" → "100"
     never appears verbatim anywhere) — this is exactly the class of
     case the design doc's original "runtime-binding" constraint type
     was scoped for and explicitly deferred, so ABSTAIN is the honest
     answer here, not a guess in either direction.
   - If the value **does** appear in the session's tool-result history,
     but ONLY inside a result the user's task did not ask the agent to
     read as part of achieving the stated goal (i.e., it traces to
     content that arrived via a tool call outside what a literal
     reading of the task would require) → this is the deliberately
     narrower, high-precision signal: **FLAG**, since this is exactly
     AuthGraph's `observation_direct` mechanism — a value legitimately
     present in the session, but sourced from the wrong place.

**Honest simplification, stated plainly**: distinguishing "traces to an
authorized source" from "traces to an unauthorized source" in general
requires knowing which tool call the user's task actually authorized —
a harder problem than plan-time literal extraction alone can solve
without an LLM. For this deterministic prototype, the check is
narrowed to the **decidable subset**: does the critical parameter value
appear ANYWHERE in the session's real tool-result history at all?
- **Appears nowhere** → ABSTAIN (genuinely undecidable without more
  information — could be attacker-injected, could be a value the LLM
  computed itself).
- **Appears, AND is also the plan-time literal** → PASS (clean case).
- **Appears, but is NOT the plan-time literal, AND a plan-time literal
  WAS extracted for this critical parameter** → **FLAG** (the strongest,
  most decidable signal: the user named one value, the call uses a
  DIFFERENT value that happens to trace to *some* observed content —
  this is precisely the `send_money(recipient=attacker_iban)` shape from
  the original discriminability test, where the injected IBAN is real,
  observed text (from the injected instruction's own payload, itself
  delivered via a tool result) but is NOT what the user named).
- **Appears, but NO plan-time literal was extracted for this parameter**
  (e.g., "pay Alice back the amount she sent me" — no literal amount
  named) → ABSTAIN (the value is real and traceable, but there was no
  literal to check it against — this is the same runtime-binding gap
  Option B scoped and deferred, not solved here).

This narrows Stage 1 to exactly the decidable case: **a literal-value
mismatch where the actual call's value is a real, different string than
what the user named, AND that different string is independently
verifiable as having appeared in the session** (i.e., not a total
fabrication either — most real prompt-injection payloads in AgentDojo
attach the attacker's target value in the tool output the injection
arrives in, so this condition fires on exactly that shape). Cases
needing genuine runtime re-derivation ("the largest file," "half of what
she sent me") are out of scope for this deterministic tier and will
ABSTAIN — consistent with Option B's own prior finding that this needs
the expensive tier, not the cheap one.

## Wiring: alongside ministers, not replacing

This tier runs as an independent check per WRITE-type tool call,
producing its own verdict (`PASS` / `FLAG` / `ABSTAIN`). Final verdict
composition: `FLAG` from this tier forces `BLOCK` regardless of the
ministers' verdict (deterministic authorization violations are
higher-confidence than similarity-based pattern matching); `PASS` or
`ABSTAIN` defers entirely to whatever the ministers already decided —
this tier only ever adds a BLOCK, never downgrades or overrides an
existing minister BLOCK/ESCALATE. This matches the prompt's "adds
coverage... not replacing" instruction precisely: the ministers' recall
on everything they already catch is unaffected; the only possible
delta is FLAG cases the ministers missed (ALLOW → BLOCK), and ABSTAIN
never changes anything.

## No new infrastructure needed for the live run

Per the earlier session's finding (`FINDINGS_SUMMARY.md`): AgentDojo's
`KavachDefense.query()` already receives the full `messages` list every
call, including prior `ChatToolResultMessage.content` — the tool-result
history this tier needs is already flowing through the pipeline, just
unused today. This prototype reads it directly from the same `messages`
list `KavachDefense` already has, no new hook or wiring into AgentDojo
itself required for the isolated test.
