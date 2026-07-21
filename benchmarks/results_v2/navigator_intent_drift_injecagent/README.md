# NAVIGATOR intent-drift vs. real InjecAgent data — exploratory re-run

**Status: PASSED a fast held-out validation (see below) — held up across two
independent split-half directions, degrading only ~2-3pp on cold data with
FPR staying exactly 0% both ways. Still NOT fully validated: benign sample
remains thin (8-9 per half) and no adversarial/off-corpus check has been run.
Promising enough to justify the remaining validation work, not yet solid
enough to cite as a locked paper number or wire into `server.py`.**

## What this is

Parv's `test_navigator_intent_drift.py` (copied unmodified from `nav-fixer2`
commit `f2dd7ef`) run against real InjecAgent case content — not the
AgentDojo-groundtruth dataset it was originally validated against on
`nav-fixer2` (`nav/`, `nav2/`, `nav3/` there all score
`agentdojo_groundtruth_dataset.jsonl`, not InjecAgent).

## How this dataset was built

`adapt_injecagent_for_intent_drift.py` reshapes
`benchmarks/results_v2/injecagent_100case_forced.jsonl` (100 real InjecAgent
cases already committed on `kavach-rearch`: 43 DS + 40 DH + 17 benign) into
the `{case_id, goal, turns, labels}` shape `test_navigator_intent_drift.py`
expects — `goal` = `user_instruction`, `turns` = each recorded tool call's
name/args, `labels.is_attack_case` = `kind in ("ds", "dh")`. Output:
`injecagent_intent_dataset.jsonl` (83 attack / 17 benign).

## Results

`navigator_intent_drift_predictions.jsonl` / `navigator_intent_drift_summary_t0.40.json`
is Parv's script's actual output at its default `--drift-threshold 0.40`:
recall 31.33% (26/83), FPR 0% (0/17).

`threshold_sweep.json` is a **post-hoc arithmetic sweep** over the same run's
logged `min_similarity` scores (no re-embedding, no second model call) —
this is NOT 11 independent re-runs, just re-thresholding one run's already-
computed similarities. At `T=0.60`: recall 95.18% (79/83), FPR 0% (0/17).

Every number here was independently reproduced twice in the conversation
that generated it (once by the agent that built the dataset and ran the
script, once by a second, separate verification pass that re-derived the
same file, re-ran the same unmodified script, and got an exact match to
four decimal places) — the numbers themselves are real, not fabricated or
misremembered.

## Held-out validation (`held_out_validation.json`)

Stratified 50/50 split of the 100 cases (fixed seed `20260721`, attack/benign
ratio preserved in each half): Half A = 42 attack/9 benign, Half B = 41
attack/8 benign. Threshold picked by sweeping only the training half's
similarity scores (best recall at 0% FPR on that half), then applied cold
(no retuning) to the other half. Done in both directions:

| Trained on | Chosen T | Train recall/FPR | Tested on | **Cold test recall/FPR** |
|---|---|---|---|---|
| Half A | 0.653 | 97.62% / 0% | Half B | **95.12% / 0%** |
| Half B | 0.578 | 95.12% / 0% | Half A | **92.86% / 0%** |

**Verdict: holds up under held-out validation.** Cold recall drops only
~2.3–2.5 percentage points relative to the training half in both directions,
and FPR stays exactly 0% in both cold tests — no sign of the threshold being
overfit to whichever half it was picked on. Caveat: with only 8-9 benign
cases per half, "0% FPR" is coarse (a single false positive would jump it to
~11-12%), so this isn't a precise FPR estimate yet, just an absence of any
observed false positive across both held-out halves.

## What is still NOT yet true, and must not be implied by these numbers

1. **Thin benign sample.** Only 17 benign cases total (8-9 per held-out
   half) — the 0% FPR held up, but isn't precise enough to call a stable,
   locked-in rate the way e.g. Kavach-PB's 793+55-case benign FPR is.
   Attempted to grow this past 17 from other already-generated InjecAgent
   run artifacts in this repo (`injecagent_100case_freeform_*`,
   `injecagent_live_50case.jsonl`, etc.) — all either overlap the same
   100-case pool or contain zero benign cases (`injecagent_live_50case.jsonl`
   is 26 DS + 24 DH, no benign at all). Growing the benign sample needs a
   fresh generation run, out of scope for this pass.
2. **No adversarial/off-corpus/novel-vocabulary check** — the exact class of
   test (`benign_probe.json`, narrative-phrasing gap) that previously
   exposed blind spots in NAVIGATOR's original cosine mechanism and in
   VAULT/EXECUTOR's deterministic rules. This mechanism hasn't been put
   through anything equivalent yet.
3. This is a **different dataset and different result** from `nav-fixer2`'s
   own committed intent-drift numbers (`nav3/`: 7.3% recall on
   AgentDojo-groundtruth) — the two are not comparable and should not be
   blended into one headline number. `nav-fixer2`'s README documents that
   branch's Stage 2 NAVIGATOR swap as attempted and abandoned; this result
   does not overturn that finding, it's a separate, later probe against
   different data that has now cleared one more validation bar than that
   one had.

## Before this goes anywhere near the paper or `server.py`

- Grow the benign sample well past 17 (needs a fresh generation run).
- Run an adversarial/paraphrase check analogous to `benign_probe.json`.
- ~~Do a genuine train/held-out split~~ — done above, passed.
