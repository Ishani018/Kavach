# NAVIGATOR corpus expansion candidates — staged for review, not merged

**Status: first-pass candidate batch, not validated at scale, not wired
into the live corpus, not committed to `kavach_corpus_v1.json`.** This
was Parv's originally-assigned task; this batch doesn't block or
pre-empt his work — treat it as a draft he can review, refine, or
discard, not a final deliverable.

## What's here

- `navigator_candidates_v0.json` — 34 candidate NAVIGATOR corpus
  patterns (`NAV-101`–`NAV-134`), same 7-field JSON shape as the live
  corpus (`id`, `category`, `source`, `rationale`, `L1_intent`,
  `L2_mechanism`, `L3_surface`).
- `SUMMARY.md` — full design write-up: category breakdown, sourcing
  discipline, and caveats.

## Why this exists

NAVIGATOR's corpus (`kavach_corpus_v1.json`, 100 existing patterns) has
a confirmed, exhaustive zero-coverage gap for financial-authorization-
abuse and physical-access-control-abuse attack categories — it was
built almost entirely for Linux/infrastructure-level agentic attacks.
This gap traces back to this session's own README §4 ("The fine-tune
regression, the STEWARD pivot, and the real conclusion") — the STEWARD
investigation concluded a new pattern-matching minister wasn't the fix
for this category, not that the category should stay uncovered
forever. These candidates are a direct, literal-syntax-first attempt at
closing part of that gap through NAVIGATOR's existing mechanism, using
the same corpus-mining discipline this session used for VAULT/EXECUTOR.

## Categories covered

`financial_threshold_manipulation` (7), `unauthorized_payment_override`
(6), `badge_credential_misuse` (6), `physical_security_tampering` (6),
`approval_chain_injection` (5), `spending_limit_bypass` (4).

## Sourcing

Real, verifiable MITRE ATT&CK technique IDs (T1657 Financial Theft,
T1078 Valid Accounts, T1098 Account Manipulation, T1531 Account Access
Removal, T1556 Modify Authentication Process, T1489 Service Stop,
T1562 Impair Defenses, T1070 Indicator Removal), OWASP Agentic AI Top
10 2026 categories (A01, A02, cited by name only — matching the live
corpus's own citation convention), and CWE-841 where MITRE/OWASP didn't
map cleanly. No technique ID was invented; where ATT&CK doesn't
enumerate a specific sub-technique (e.g. badge-system tampering
specifically), the parent technique is cited by name without a
fabricated sub-ID.

## Held-out discipline — and its honest limitation

**The available real-world validation pool for this domain is thin: 3
cases.** `benchmarks/data/dh_structured_args.json` contains exactly 3
financial-tool-shaped InjecAgent DH cases (`BankManagerPayBill`,
`BankManagerTransferFunds`, `VenmoWithdrawMoney`). A search of the
267-case Type B set found zero genuine financial-authorization-abuse
cases — the keyword-matched hits (SSH `authorized_keys`, OAuth
`authorization` flows) are false positives unrelated to NAVIGATOR's
target categories here.

Given that thinness, the held-out split used was: **build entirely from
external sources (MITRE/OWASP/CWE technique descriptions + real
tool-naming conventions), with the 3 DH cases reserved as a pure
validation-only set never touched during design.** Their exact
instruction text is quoted verbatim in `SUMMARY.md` specifically so
this reservation is checkable, not just asserted. This is NOT the same
as this session's other held-out splits (e.g. the 301-pattern held-out
set used for VAULT/EXECUTOR, or the 170 independently-constructed
generalization-test variants) — those had a real, sizeable pool to
split. **A 3-case validation set has genuinely weak statistical power
— it can catch a candidate pattern that's badly wrong, but it cannot
establish real generalization the way this session's other validation
work did.** Treat any "N/3 candidates would have matched the reserved
DH cases" result (if run) as a sanity check, not a generalization
claim, until a larger, real financial-authorization test set exists.

## Known limitations (surfaced, not hidden)

- Physical-access-control tool names (`grant_badge_access`,
  `disable_alarm`, `unlock_door`, etc.) are plausible but invented — no
  real benchmark corpus for facility-access-control tooling exists in
  this repo to ground naming conventions the way InjecAgent grounds the
  financial ones. A reviewer with real vendor API knowledge (Lenel,
  Genetec, HID) should sanity-check these before merge.
- No dedupe/similarity pass against the existing NAV-001–NAV-100
  patterns has been run — recommended before merge.
- Not run through any scoring/eval script against a live server.
- Not merged into `kavach_corpus_v1.json`. Corpus MD5 and `main`
  unaffected by this batch.
