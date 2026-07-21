# NAVIGATOR intent-drift vs. real InjecAgent data — exploratory re-run

**Status: exploratory, NOT validated. Do not cite as a locked number or wire
into `server.py` without doing the missing checks below first.**

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

## What is NOT yet true, and must not be implied by these numbers

1. **No held-out split.** `T=0.60` was chosen by inspecting the similarity
   distribution on the same 100 cases it's scored against. It has never
   been evaluated on a case it wasn't tuned against.
2. **Thin benign sample.** Only 17 benign cases — a real 0% FPR, but not
   enough data to call it a stable, locked-in rate the way e.g. Kavach-PB's
   793+55-case benign FPR is.
3. **No adversarial/off-corpus/novel-vocabulary check** — the exact class of
   test (`benign_probe.json`, narrative-phrasing gap) that previously
   exposed blind spots in NAVIGATOR's original cosine mechanism and in
   VAULT/EXECUTOR's deterministic rules. This mechanism hasn't been put
   through anything equivalent yet.
4. This is a **different dataset and different result** from `nav-fixer2`'s
   own committed intent-drift numbers (`nav3/`: 7.3% recall on
   AgentDojo-groundtruth) — the two are not comparable and should not be
   blended into one headline number. `nav-fixer2`'s README documents that
   branch's Stage 2 NAVIGATOR swap as attempted and abandoned; this result
   does not overturn that finding, it's a separate, later, unvalidated
   probe against different data.

## Before this goes anywhere near the paper or `server.py`

- Do a genuine train/held-out split (or at minimum, a fresh case set the
  threshold wasn't picked by looking at).
- Grow the benign sample well past 17.
- Run an adversarial/paraphrase check analogous to `benign_probe.json`.
