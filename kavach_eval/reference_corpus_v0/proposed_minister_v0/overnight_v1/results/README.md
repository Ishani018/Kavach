# Result data index

All real result data (not scripts, not server logs) generated across this
session's re-architecture work, organized by topic. Nothing here was
regenerated for this commit — these are the actual outputs from when
each measurement was originally run, staged from scratchpad into the
repo so they're not lost. See `../MORNING_REPORT.md` for the narrative
write-up these numbers back.

## InjecAgent DH/DS rescore
- `dh_ds_full_rescore_results.json` — the full 510+544 rescore (DH partial at 429, DS complete at 544/544).
- `dh_from_ledger_summary.json` — DH's partial-run summary recovered directly from the ledger.
- `dh_manual_extractions.json` / `ds_manual_extractions.json` — the 30 DH + 32 DS manually-extracted structured-arg sets (see `benchmarks/data/dh_structured_args.json` / `ds_structured_args.json` for the versions actually wired into the harness).
- `pilot_dh_arg_extraction_results.json` — the initial 10-case qwen2.5:7b feasibility pilot (superseded by manual extraction, kept for the record).
- `slack_rescore_sessions.json` — Slack-domain session data from the InjecAgent rescore.

## Type B (267-case narrative-phrasing red-team set)
- `type_b_wireformat.json` — the 267 cases in wire format, `EXEC-097` tagged `label_fidelity: "loose"`.
- `type_b_scored_results.json` — scored against the live server.
- `typeb_build_set.json` / `typeb_heldout_set.json` — the 70/30 build/held-out split used to validate the entity-extraction pre-step design before regression testing.

## Corpus coverage audit
- `corpus_coverage_results.json` — VAULT (7/100) and EXECUTOR (10/100) original-coverage audit, the source data Track 2's expansion was built from.
- `vault_uncovered_full.json` / `exec_uncovered_full.json` — full L3_surface text for every uncovered corpus pattern.

## Stage 1/2 before/after measurements
- `stage1_measurement.json` — Stage 1 (additive deterministic pre-filters) wiring measurement.
- `stage2_vault_before.json` / `_after.json` — VAULT's cosine-to-deterministic swap measurement.
- `stage2_executor_before.json` / `_after.json` — EXECUTOR's swap measurement.
- `stage2_channel_live_eval.json` — CHANNEL's initial taint-tracking validation.
- `stage2_channel_workspacefix_eval.json` — CHANNEL's `account_email` workspace-self-send fix re-validation.

## LLM tiebreaker (Track 1) history
- `llm_tiebreaker_pilot_results.json` — the original 17-case holistic-vs-split-extraction pilot comparison.
- `extraction_only_pilot_results.json` — the split-extraction-only pilot (16/17 validated design).
- `full_pipeline_17_results.json` — the 17 pilot cases re-run through the real wired pipeline.
- `ground_truth_flags.json` — hand-labeled ground truth for the pilot cases.
- `entity_prestep_validation.json` — the rejected entity-proximity-only design's validation (7 new benign FPs, why it was rejected).
- `../track1_benign_results.json` — the 144-call full benign-set validation (both the original stop-condition-hit run and the post-fix re-run).
- `../track1_generalization_results.json` — the 4/5 generalization test on new phrasings.

## Track 2 (corpus-driven VAULT/EXECUTOR expansion)
- `../held_out_301.json` — the 301 never-tested-in-Type-B corpus patterns, the mandated held-out validation set.
- `../track2_validation_results.json` — the original 85-candidate benign-FP validation (all 85 passed).
- `../post_merge_validation_results.json` — full post-merge regression suite (LOLBIN/benign/Type B/DH-DS) against the real merged `prefilters.py`.
- `rule_generalization_variants.json` — the 170 independently-constructed test cases (2 per rule) used for the real generalization test.
- `../rule_generalization_results.json` — the real generalization result: 151/170 (88.8%), including the `windows-run-key-write` bug found and fixed during this test.

## AgentHarm benchmark survey
- `agentharm_sample_v0.json` — the 18-case manual-approximation sample (13 harmful + 5 benign), explicitly tagged `extraction_type: "manual_approximation"`, awaiting review before scaling to the full 416.

## Benign sets
- `benign_probe_results.json` — `benign_probe.json`'s 25 cases scored against the live server.
