# Deterministic scope-router: design

## Goal

Reduce Kavach's false-positive rate by making the ministers ABSTAIN
(defer to a permissive default) on calls structurally outside their
reliable domain, instead of letting embedding/BM25 similarity fire on
everything indiscriminately — which is the exact mechanism behind every
false positive traced in this whole investigation (the original
`url`/`user` bug, the benign `get_most_recent_transactions` blocks just
observed in the live qwen2.5:7b run).

## Classification, purely structural — no similarity, no LLM

Two independent axes, both derived from the tool's **name and static
schema only**, never from the call's argument values or any embedding:

### Axis 1: READ vs WRITE

Same verb-prefix rule already used and validated in the Stage 1
provenance-tier design (`provenance_tier.py`'s `WRITE_PREFIXES`):
`send_`, `schedule_`, `update_`, `delete_`, `create_`, `book_`,
`reserve_`, `transfer_`, `invite_`, `remove_`, `add_`, `share_`,
`grant_`. Anything not matching one of these prefixes is READ.

Confirmed against the real banking tool inventory
(`banking_client.py` + `user_account.py`, read directly, not assumed):

| tool | classification |
|---|---|
| `send_money` | WRITE |
| `schedule_transaction` | WRITE |
| `update_scheduled_transaction` | WRITE |
| `update_password` | WRITE |
| `update_user_info` | WRITE |
| `set_balance` / `set_iban` | WRITE (not exposed to the agent in the real suite, listed for completeness) |
| `get_balance` | READ |
| `get_most_recent_transactions` | READ |
| `get_scheduled_transactions` | READ |
| `get_iban` | READ |
| `get_user_info` | READ |
| `read_file` | READ |

### Axis 2: sensitive-category lookup

A **static, per-tool table**, not inferred — every tool in the local
AgentDojo suites is hand-classified once into a category, and the table
is the only source of truth (no runtime guessing). Categories, chosen to
match the prompt's own list (money/credentials/access/data-exfil) plus a
catch-all:

- `MONEY`: `send_money`, `schedule_transaction`,
  `update_scheduled_transaction`, `get_balance`,
  `get_most_recent_transactions`, `get_scheduled_transactions`,
  `get_iban`
- `CREDENTIALS`: `update_password`
- `ACCESS`: `update_user_info`, `invite_user_to_slack`,
  `remove_user_from_slack`, `add_user_to_channel`, `share_file`,
  `grant_*`
- `EXFIL_SURFACE`: `send_email`, `send_direct_message`,
  `send_channel_message`, `post_webpage` (tools whose entire purpose is
  moving data OUT of the session — read tools that move information
  out of the agent's own state, distinct from a "READ" that stays
  internal)
- `NONE`: everything else (`get_webpage`, `read_channel_messages`,
  `get_channels`, `read_file`, `list_files`, etc.) — tools with no
  money/credential/access/exfil stakes at all.

**Important, stated honestly per the guardrail**: the category
assignment for a NEW tool not already in this table would need a human
to add it (or a deterministic rule over the tool's declared return type/
side-effect annotation, if the framework exposed one reliably — AgentDojo
does not, so for this prototype the table is hand-built from the same
direct source-reading already done for Stage 1). This is a real, stated
limitation: the router's coverage is only as good as the static table's
completeness, not something that "learns" new tools. Flagging this
explicitly rather than pretending the table generalizes automatically —
this is exactly the kind of honesty check the last several investigations
required.

## Scope decision (deterministic combination of the two axes)

```
in_scope = is_write(tool) OR category(tool) in {MONEY, CREDENTIALS, ACCESS, EXFIL_SURFACE}
```

Concretely for banking: every WRITE tool is automatically in-scope
(regardless of category, since WRITE alone is enough per the prompt's own
"WRITE calls" example). Every READ tool is in-scope ONLY if its category
is MONEY/CREDENTIALS/ACCESS/EXFIL_SURFACE — this actually means
`get_most_recent_transactions`, `get_balance`, `get_scheduled_transactions`,
and `get_iban` are classified MONEY-category but READ-type: **still
in-scope** under this rule (money-adjacent reads matter for later
provenance tracing even if they don't write anything themselves) — this
was a real design choice, not an oversight, and is called out below since
it directly affects whether the router "rescues" the exact
`get_most_recent_transactions` false-positives spotted in the live run.

**Given the live run's own false-positive evidence** (repeated
`get_most_recent_transactions` blocks on a benign task), a stricter,
second variant is also tested: `in_scope = is_write(tool)` only — i.e.,
READ calls are NEVER in-scope regardless of category, only WRITE calls
ever reach the ministers. This is the more aggressive FP-reduction
variant and is reported side-by-side with the category-aware variant, so
the tradeoff is visible rather than picking one silently.

## What "ABSTAIN" means operationally

For an out-of-scope call, the router returns `ALLOW` directly — it never
calls the ministers at all for that call. This is a genuine deferral to
"permissive default," per the prompt's own framing, not a soft
downweighting of the ministers' score.

## Wiring

Applied as a pre-filter in front of the existing ministers, replayed
against the SAME real trajectories already collected from the live
qwen2.5:7b run (27 attack pairs + the benign utility pass) — no new LLM
run needed, this re-scores real historical tool calls against the
router+ministers combination using the same isolated test infrastructure
(`test_chroma_ablation`, BGE-base + real BM25) already validated
throughout this whole investigation.
