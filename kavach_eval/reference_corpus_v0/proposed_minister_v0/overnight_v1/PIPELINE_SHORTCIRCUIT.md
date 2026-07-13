# Pipeline short-circuit — mechanism, validation, real numbers

**Status: built, fully validated, committed. Not pushed, not wired for
production traffic beyond what's in this branch.**

## The problem this addresses

The full DS rescore earlier this session measured **p50 3.69s, p95
7.42s** end-to-end latency (CPU-only laptop), regardless of which
minister ultimately decided the verdict — because COMPASS's drift check
and the embedding-based semantic router ran unconditionally, first,
before any minister (deterministic or cosine) was ever consulted.
VAULT/EXECUTOR/CHANNEL's deterministic checks are microseconds, but that
speed advantage never showed up in real end-to-end latency, since the
embedding+routing cost was paid on every call regardless.

## The mechanism

`parliament/server.py`'s request handler now runs VAULT/EXECUTOR/
CHANNEL's deterministic checks (already unconditional since the Stage 2
swaps) **before** COMPASS/routing/NAVIGATOR, not after. If one of them
produces a confident BLOCK (`confidence >= 1.0`) on a rule that's
**short-circuit-eligible**, the response is returned immediately —
`compass_sim=None`, `activated=[]`, no NAVIGATOR consultation — and
COMPASS + the router + NAVIGATOR are kicked off as a **fire-and-forget
async task** afterward, purely to complete the ledger's provenance
picture. The caller never waits on that task; it writes a second ledger
row (same `correlation_id`, `stage="parliament_async_completion"`) once
it finishes, rather than mutating the original row — the hash chain is
append-only/content-addressed by design, so editing an already-hashed
row would break every subsequent `entry_hash`.

If no eligible confident BLOCK is found, the call proceeds through the
exact same full pipeline as before this change — byte-for-byte identical
logic, just re-using the deterministic results already computed instead
of recomputing them later in the function.

## The safeguard: a rule-name denylist, not a blanket policy

Eligibility is gated by `parliament.prefilters.SHORT_CIRCUIT_INELIGIBLE_
RULE_NAMES`, a denylist of 4 rule identities that must still go through
the full synchronous pipeline (COMPASS+NAVIGATOR included) even when
they fire:

- `interpreter-inline-eval-payload` — the broadest-match-surface rule in
  the corpus expansion, explicitly flagged in its own source comment as
  needing extra scrutiny before being trusted as much as older rules.
- `dotenv-read-call`, `redis-mongo-unauth-dump`, `path-env-prepend` —
  the 3 rules from the corpus-expansion generalization test that failed
  BOTH independent test variants (see `rule_generalization_results.json`)
  — each still correctly catches its one validated source-syntax case
  with zero benign FPs, but isn't proven to generalize, so it doesn't
  yet earn the response-time trust of skipping semantic confirmation.

This is a denylist specifically so it's easy to expand eligibility
later: removing an entry (once a rule earns more real-world confidence)
grants it short-circuit eligibility automatically, rather than requiring
every new rule to be manually added to a growing allowlist.

## Validation

### Verdict-identical: 0/411 mismatches (after fixing an unrelated test-harness bug)

Ran all 411 available test cases (267-case Type B malicious set + 144
benign calls) against two live, isolated servers on identical input:
one running the new short-circuit code, one running the exact
pre-change code from commit `88b63ae` (checked out via `git show`,
never touching the working tree). 

**First run found 26 verdict mismatches — root-caused, NOT a bug in the
short-circuit logic.** All 26 mismatches shared one property: every
single one had `short_circuited: False`, meaning they occurred on the
full-pipeline path, which was never touched by this change's logic.
Direct repro on one mismatching case showed NAVIGATOR producing the
*exact same* confidence score (0.6544) on both servers, but a different
verdict (`ESCALATE` on new, `BLOCK` on baseline) — the two servers were
using different BLOCK thresholds. Traced to a test-harness setup bug:
the scratch copy of the baseline server was missing `config.yaml`
(`block: 0.55` + `per_minister` overrides), so it silently fell back to
different hardcoded defaults (`block: 0.65`, no per-minister overrides).
Fixed by copying the real `config.yaml` into the baseline scratch
package and confirming via direct repro that the mismatch disappeared.

**Re-ran clean: 0/411 verdict mismatches.** This is the trustworthy
result — logged in `results/pipeline_shortcircuit_verdict_identical_
results.json`.

### Excluded-rule denylist: confirmed live, end-to-end

Tested all 4 denylisted rules directly against the live server:
`interpreter-inline-eval-payload`, `dotenv-read-call`, `redis-mongo-
unauth-dump`, `path-env-prepend` all produced `short_circuited: false`
with full-pipeline latency (4.5-7.6s), even where 3 of the 4 still fired
a confident BLOCK/ESCALATE. An eligible control case (`aws-credentials-
file`) correctly short-circuited at 348ms. Also confirmed via unit test
before the live check: `is_short_circuit_eligible()` correctly returns
`False` for all 4 denylisted names and `True` for every other tested
rule identity, including AST-resolved matches.

### Ledger integrity: confirmed both row shapes

Directly queried the isolated ledger DB for both case types:
- **Excluded-rule cases** (never short-circuit): exactly ONE row per
  call, `stage="parliament"`, `short_circuited=0`, `compass_sim` filled
  in synchronously as before.
- **Eligible short-circuited case**: TWO rows sharing one
  `correlation_id` — the immediate row (`stage="parliament"`,
  `short_circuited=1`, `compass_sim=NULL`) and the async completion row
  (`stage="parliament_async_completion"`, `short_circuited=1`,
  `compass_sim` filled in from the backgrounded COMPASS/NAVIGATOR run).
  `decided_by` matches between the two rows (fixed a naming
  inconsistency found during testing — see below).

### One bug found and fixed during testing (not shipped)

The async completion function initially logged `decided_by` as the
rule's `matched_id` (e.g. `"VAULT-PREFILTER:aws-credentials-file"`)
instead of the minister name (`"VAULT"`), inconsistent with every other
ledger row's convention. Found via direct ledger inspection during
testing, fixed before any commit, re-verified the two rows for one
`correlation_id` now agree on `decided_by`.

## Real latency numbers

Measured via 411 paired requests against two live, isolated servers
(identical corpus, identical thresholds, identical hardware — CPU-only
laptop, no GPU):

| | NEW (with short-circuit) | BASELINE (pre-change) |
|---|---|---|
| p50 | 3229ms | 3371ms |
| p95 | 5479ms | 5926ms |
| mean | **2914ms** | **3720ms** |

- **Short-circuit trigger rate: 99/411 = 24.1% blended** (267 malicious
  + 144 benign mixed together). On the **267-case Type B malicious set
  alone, the trigger rate is 36.7%** (98/267) — measured directly
  against `parliament.prefilters.run_prefilters()` during the original
  feasibility check, before any code was built. The blended rate is
  lower because benign calls almost never short-circuit (correctly —
  only the one pre-existing `bitsadmin-transfer` false positive would).
- **Short-circuited calls: mean 410ms, p50 311ms** — roughly a **10x
  speedup** relative to the ~3.4-3.7s the same call would have taken
  through the full pipeline.
- **Non-short-circuited calls: mean 3708ms, p50 3403ms** — statistically
  unchanged from the baseline's non-short-circuited latency, as
  expected (this path's logic is byte-for-byte identical to before).
- **Blended mean latency: 3720ms → 2914ms, a ~22% reduction** across the
  full 411-case mixed set — the real, honest number for "how much faster
  is Kavach now," not the ~10x number (which only applies to the subset
  that short-circuits) and not a claim that every call got faster (most
  didn't, by design — only calls with an eligible confident deterministic
  BLOCK do).

## What this does NOT change

- The non-short-circuited path is untouched — same COMPASS, same router,
  same NAVIGATOR, same Speaker logic, same latency profile as before.
- CHANNEL's session-stateful taint tracking, trajectory's session-risk
  accumulation, and the ledger's tamper-evident hash chain are all
  unaffected — confirmed directly (not assumed) during the feasibility
  check before any code was written: COMPASS and the router are pure
  reads with no cross-call session-state writes, and trajectory's
  `record_action()` only consumes `action_vec`/`verdict`/`confidence`/
  `decided_by`/`is_denial`, none of which originate from COMPASS or
  NAVIGATOR.
- No rule's own detection logic changed — this is purely a response-path
  reordering + an async ledger-completion mechanism, not a change to
  what gets detected or how.

## Data and reproducibility

- `results/pipeline_shortcircuit_verdict_identical_results.json` — the
  full 411-case verdict/latency comparison (clean run, post-config-fix).
- The denylist itself: `parliament/prefilters.py`'s
  `SHORT_CIRCUIT_INELIGIBLE_RULE_NAMES` and `is_short_circuit_eligible()`.
- The dispatch logic: `parliament/server.py`'s `_run_deterministic_
  ministers()`, `_short_circuit_candidate()`, `_complete_ledger_async()`,
  and the restructured `parliament()` handler.
