# Overnight session status

Live tracking doc for the Phase 0-4 + NAVIGATOR + GPT-4o + paper work.
Updated as phases land, not a final report (see
`benchmarks/OVERNIGHT_PHASE_REPORT.md` for the detailed Phase 0-2
writeup).

## Done

- **Phase 0** (blocking): resolved the independent audit's two findings
  — the 34.2%/34.5% vs 72.6%/89.9% vs 14.9%/19.2% metric mismatch
  (root cause: `_fired()`'s BLOCK-or-ESCALATE definition vs. audit's
  deterministic-only scorer, plus a duplicate uvicorn process), and the
  held-out generalization overclaim (corrected from a 3-case delta to
  a genuine full-population split).
- **Phase 1**: real AST-based parsing (`parliament/ast_parse.py`,
  bashlex for sh/bash — wired live; PowerShell AST built and tested
  but excluded from the live path, ~1.4s/call, 18x over budget).
  VAULT 34.2%→74.4% (87/117), EXECUTOR 34.5%→90.1% (181/201)
  full-pipeline, 0 new benign FPs on both populations (793 bfcl, 55
  benign_v0).
- **Phase 2**: CHANNEL generalization (`_general_destination_values()`
  fallback for tools outside `DESTINATION_TOOLS`), 2 self-caught
  regressions fixed (arg-joining false phone match, ISO-date-as-phone
  false match). Re-confirmed clean: 5/22 benign ESCALATE / 0 BLOCK,
  5/5 AgentDojo applicable attack cases via CHANNEL.
- **PRIORITY CHECK**: CHANNEL's 5/5 re-verified against AgentDojo's
  REAL recorded trajectories (not the minimal `ground_truth()`
  subsequence) — genuine 5/5, after fixing a scoring bug in my own
  verification script (was only tracking the last step's verdict).
- **Housekeeping**: stale `navigator-fixer` branch deleted from origin
  (confirmed safe ancestor first). `navigator-local-backup` (mistakenly
  branched off `navigator-rearch`) deleted after confirming zero code
  diff, replaced by `navigator-local` off `kavach-rearch`'s tip.
- **NAVIGATOR Pieces 1-2** (`parliament/navigator_authflow.py`, on
  `navigator-local`, uncommitted): pinned intent capture (immutable
  after first real instruction) + observational/consequential/
  ambiguous tool taxonomy (69 real AgentDojo tool names, exact-match +
  regex-fallback). 34/34 tests passing
  (`parliament/test_navigator_authflow.py`).

## Paused (documented negative result, not abandoned)

- **NAVIGATOR Piece 3** (hard-constraint / derivability layer): three
  independent heuristic designs tried against the same frozen
  criterion (GO if ≥7/8 AgentDojo attack cases correctly flagged NOT
  derivable AND ≤1/22 benign sessions falsely flagged) —
  1. **Tool-name token overlap**: NO-GO, attack 5/8. Any shared noun
     between pinned intent and the tool NAME counted as authorization
     — can't distinguish a read intent ("give me their email
     addresses") from a same-topic write action (`send_email`).
  2. **Argument-value text overlap only**: NO-GO, benign 6/22. Fixed
     all 3 attack misses (8/8), but wrongly flagged legitimate actions
     whose destination value was read from a same-session tool call
     (e.g. an IBAN read out of a bill file) — text-overlap can't see
     same-session provenance, only same-session taint tracking can.
  3. **Composed with CHANNEL's own provenance state**
     (`channel_taint.check_provenance()`'s `ProvenanceRecord`,
     read-only, per explicit user-approved composition rule): NO-GO,
     benign 6/22 against the frozen ≤1/22 threshold. Attack stayed
     8/8. 5 of the 6 benign flags are NAVIGATOR echoing CHANNEL's own
     already-accepted 5/22 ESCALATE population (not a new false
     positive), the 6th is a genuine gap (`schedule_transaction`/
     `update_scheduled_transaction` reference an existing transaction
     by internal id, no destination-shaped argument for either
     text-overlap or CHANNEL's own destination-arg map to check at
     all). Reported honestly against the criterion AS FROZEN, not
     retroactively reinterpreted even though a defensible carve-out
     (not counting CHANNEL-overlap sessions) would flip it to a GO —
     that reinterpretation was only proposed after seeing the result.
  - **Verdict**: 3 independent failures on the same sub-problem is a
    real signal it's genuinely hard, not one clever heuristic away
    from working. `channel_taint.py` was READ-ONLY throughout all
    three attempts — confirmed 13/13 unit tests still pass, zero
    residue.
  - Piece 4 (authorized-flow derivation) depends on Piece 3 and is
    correspondingly blocked.
  - Revisit with a genuinely different mechanism in a future session
    — candidate future-methodology note: a frozen criterion for a
    NAVIGATOR-layer census should probably exclude sessions CHANNEL
    already independently escalates, since those aren't a NEW false
    positive NAVIGATOR introduces. Not applied this session.

## Branch state

- `kavach-rearch`: has the Phase 0-2 uncommitted work (AST parsing,
  CHANNEL generalization fix, benchmark/audit corrections). Not
  committed — awaiting review.
- `navigator-local`: branched off `kavach-rearch`'s tip, no upstream
  tracking ref, zero remote presence. Carries Phase 0-2's changes plus
  NAVIGATOR Pieces 1-2 (uncommitted). This is the active branch for
  all NAVIGATOR work — a genuinely separate, parallel redesign, not a
  completion of or comparison to other NAVIGATOR work elsewhere.
- `navigator-rearch`: confirmed byte-identical to `origin/navigator-rearch`
  (empty diff) — completely untouched all session. Absolute
  push/merge/modify prohibition remains in force.
- `main`: untouched.
- Nothing has been committed or pushed anywhere tonight without
  explicit review and go-ahead first.

## Needs decision

- Whether/when to commit the Phase 0-2 work on `kavach-rearch` (report
  written, awaiting review — see `benchmarks/OVERNIGHT_PHASE_REPORT.md`).
- Whether/how NAVIGATOR's Piece 3 gets a fourth attempt, and with what
  mechanism, given three independent designs have now hit real walls.
- Cleanup of leftover untracked debug/audit artifacts in
  `benchmarks/results_v2/` from earlier work (kept vs. removed, not yet
  decided).

## Up next

1. GPT-4o real-trajectory expansion (all 4 suites, one model, bounded
   scope) — independent of NAVIGATOR, not blocked by Piece 3's pause.
2. Paper rewrite, Step 2 onward (Introduction/System Design/Negative
   Results/Evaluation/Limitations/Related Work), using the
   user-confirmed Step 1 historical timeline as the spine. NAVIGATOR's
   full 3-attempt negative result folds into the Negative Results
   section alongside STEWARD's falsification, the dense fine-tune
   regression, and the R2 arc.
