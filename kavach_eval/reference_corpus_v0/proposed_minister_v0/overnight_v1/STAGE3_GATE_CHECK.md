# Stage 3 gate check — router replacement, checked against real data

**Status: gate checked, condition not met. Stage 3 formally closed out —
no router change needed.**

## What Stage 3 was

A possible replacement for `_route()` (`parliament/server.py`'s
embedding-based semantic router, which decides which ministers get
`activated` for a call). Explicitly deferred pending "a measured
routing-miss rate from real evaluation data" — there wasn't enough
evaluation data at scoping time to know if this was a real problem. The
concern was RouteGuard's finding that embedding/kNN routers collapse
sharply out-of-domain (16.97 F1 vs 48.55 in-domain), though Kavach's
fail-open design (a routing miss activates all four ministers, not zero)
was already noted as mitigating the worst case. If ever triggered, the
bias was toward an LLM-router, given three prior embedding-hybrid
attempts already failed held-out testing this session.

## First finding: the question is structurally narrower than originally scoped

Direct code read of `parliament/server.py` (lines 637–660) confirms
**VAULT, EXECUTOR, and CHANNEL no longer route through `activated` at
all**, as a direct consequence of this session's Stage 2 swaps:

```python
for minister in activated:
    if minister in ("VAULT", "EXECUTOR", "CHANNEL"):
        continue  # Stage 2: VAULT/EXECUTOR/CHANNEL no longer run the cosine path at all.
    ...
# vault_scan / executor_scan / channel_scan computed unconditionally below,
# regardless of `activated` -- same fail-open discipline as Stage 1.
```

This isn't informal — it's the actual dispatch logic. A routing miss
literally cannot affect VAULT/EXECUTOR/CHANNEL's verdicts anymore; their
deterministic detectors run on every single call regardless of what the
router decides. **Only NAVIGATOR remains gated by `activated`.** So the
real Stage 3 question collapses to: *how often does the router fail to
activate NAVIGATOR when NAVIGATOR is the minister that should decide?*

## Method

`_route()` is a pure function of input text — confirmed via code read:
no ChromaDB query, no session state, just a BGE query-embedding compared
against a static `kavach_router_config.json` description set, thresholded
at `router_min = 0.40`. This means it's exactly reproducible offline,
standalone, without a live server or touching the production ledger —
same model (`BAAI/bge-base-en-v1.5`), same config, same threshold.

Reconstructed `activated` for every case in this session's available
evaluation data with real input text and a recorded `decided_by`:
- **267-case Type B set** (`wire_text` field preserved per case, joined
  to `type_b_scored_results.json`'s `decided_by` by `pattern_id`/index).
- **25-case `benign_probe.json`** (`text` field preserved, joined to its
  scored results by index).
- **119 additional benign calls** (`benign_v0.json` 55 + 64 calls across
  22 real sessions) — reconstructed `activated` but these don't carry a
  recorded `decided_by` in the collected data, so they contribute to the
  activation-distribution picture but not the miss-rate calculation
  directly.

**DH/DS honestly could not be included in the miss-rate calculation.**
The collected DH/DS result data (`dh_ds_full_rescore_results.json`) is
actually the Slack-domain rescore, not a per-case join of real input
text to `decided_by` — its `decided_by` values are `Speaker`/`NAVIGATOR`/
`TRAJECTORY` but there's no `args` field to reconstruct exact wire text
from, and no separate DH/DS-specific file has both fields together.
Reconstructing this would need either a live rescore (which the
"measurement pass only" instruction ruled out) or accepting a much
looser text approximation — neither felt honest to include in the
headline number, so it's left out rather than papered over.

## Result

**0 routing misses found, out of every case where a real check was
possible.**

- Type B: 169/267 cases decided by NAVIGATOR. **0/169 would have been
  missed** if Kavach did NOT fail-open (router-only dispatch).
- `benign_probe.json`: 8/25 decided by NAVIGATOR. **0/8 would have been
  missed.**
- Across all 411 reconstructed cases (267 Type B + 55 + 64 + 25 benign),
  **the router activated all four ministers, every single time** — the
  0/169 and 0/8 above aren't from a narrow miss margin, they're because
  NAVIGATOR (and every other minister) was activated on essentially
  every call.

**This second part is itself a real, worth-reporting finding, verified
directly** (not just inferred from the miss-rate being zero): spot-
checked individual per-minister similarity scores on several genuinely
unrelated example calls (a `read_file`, a `send_email`, a `web_search`,
a `calendar_create_event`) — every minister independently cleared the
0.40 threshold on every example, with scores clustering in the 0.41–0.57
range regardless of whether the call had anything to do with that
minister's actual domain. The `tool:X args:{...}` wire-format boilerplate
text appears to sit close enough to all four minister descriptions in
BGE embedding space that `router_min = 0.40` rarely discriminates
anything in practice — this is NOT the fallback-on-zero-activation path
firing (verified: no case hit the "no minister crossed threshold" branch),
it's four independent per-minister comparisons each genuinely clearing
the bar.

## Interpretation

The router-collapse concern behind RouteGuard's cited numbers (16.97 F1
out-of-domain) doesn't apply here in the way originally worried about.
RouteGuard's finding is about a router **wrongly discriminating** —
confidently routing to the wrong minister out-of-domain. What's measured
here is different: Kavach's router at its current threshold barely
discriminates at all — it activates nearly everything nearly always. The
practical effect on VAULT/EXECUTOR/CHANNEL is moot (they bypass routing
entirely now), and the practical effect on NAVIGATOR is that it gets
activated so consistently that a "miss" essentially doesn't occur in
this data.

This is not unambiguously good — a router that activates everything
provides no actual filtering benefit (its only remaining function is the
fail-open safety net, which never needed to be invoked in this data
because activation was never selective to begin with). But it directly
answers the Stage 3 gating question: **the routing-miss rate that would
justify building an LLM-router replacement is not present in the data.**
There's a latent, separate question (is `router_min = 0.40` doing any
useful work at all, or should it be raised) — but that's a threshold-
tuning question, not a "replace the router mechanism" question, and is
explicitly out of scope for this gate check.

## Recommendation

**Close out Stage 3 formally: gate checked against real data, condition
not met, no router replacement needed.** Same honest treatment as every
other finding this session — this isn't "deferred again," it's a real
measurement that resolves the open question. If `router_min`'s
apparent lack of discrimination is worth investigating later, that's a
separate, smaller-scoped follow-up (threshold calibration, not an LLM-
router build) and should be scoped on its own rather than folded into
Stage 3's original justification, which specifically was about
out-of-domain routing collapse — not observed here.

## Data and reproducibility

- `stage3_routing_gate_results.json` (same directory) — the full
  per-case `activated` reconstruction for all 411 cases.
- Reconstruction script referenced router config
  (`kavach_router_config.json`) and the exact embedding model/prefix/
  threshold the live server uses (`BAAI/bge-base-en-v1.5`,
  `"Represent this sentence for searching relevant passages: "` query
  prefix, `router_min = 0.40`) — no live server or production ledger
  touched. Corpus MD5 and `main` unaffected (this check reads
  evaluation data and a static router config only, never
  `kavach_corpus_v1.json`).
