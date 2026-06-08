# Kavach Eval Harness — Status & Honest Findings

## What's built and tested (all runs, no GPU)
- `HANDOFF_SCHEMA.md` — the JSONL contract Parv dumps from the Dell.
- `eval_harness.py` — ASR/FPR/utility under 3 Speaker variants, per-Minister
  calibration (ECE), Minister correlation matrix (measures real rho),
  N-Minister ablation, latency percentiles. **Correlation math unit-tested
  (1.0 / -1.0 / 0.0 exact).**
- `make_synthetic.py` — test-fixture data generator with tunable correlation,
  skill, miscalibration, attack rate.
- `tune.py` — sweeps (rho, threshold), prints the Pareto frontier, recommends
  an operating point under an FPR ceiling.

## Honest findings from the synthetic run (500 actions)

1. **On clean data, Bayesian ≈ max-score.** Both reach ~ASR 0.04. The Bayesian
   Speaker does NOT obviously beat the simple aggregator when Minister
   confidences are well-behaved. Do not claim it does.

2. **The Bayesian Speaker's advantage is conditional.** It should win only when:
   (a) confidences are miscalibrated/inflated, and/or
   (b) attacks are adaptive and fool individual Ministers.
   That is the experiment that justifies the architecture — and it needs
   Parv's real adaptive-attack runs to show. Until then, the architecture is
   defensible on *design* grounds (uses full distribution, discounts correlated
   votes, calibrated confidence output) but not yet on *empirical* grounds.

3. **rho and threshold are coupled.** Conservative rho + conservative threshold
   stack into double-penalty (ASR jumped to 0.42). They must be tuned together
   against the *measured* correlation. `tune.py` does this.

4. **Calibration matters first.** If ECE is high, tune.py may find no feasible
   point. Run temperature scaling before tuning. (Calibration module: TODO next.)

## What Parv runs on the Dell (only this needs GPU)
- Run the 4 Ministers over AgentDojo / ASB / InjecAgent.
- Dump one `minister_runs.jsonl` line per action per HANDOFF_SCHEMA.md.
- That's it. He does not run the Speaker, compute metrics, or tune.

## What Ishani + Claude do with the dump (no GPU)
1. `python eval_harness.py minister_runs.jsonl` — full report, reads real rho.
2. Set `KAVACH_CORRELATION_RHO` to the measured value.
3. `python tune.py minister_runs.jsonl --max-fpr 0.05` — get operating point.
4. (next) calibration + temperature scaling module.
5. (next) adaptive-attack harness — the experiment that proves the architecture.

## Caveats for the paper
- Synthetic numbers here are NOT results. They only prove the pipeline works.
- The generator's "rho" knob is not in Pearson units — it's a monotonic dial.
  The harness measures true Pearson rho on real data; trust that, not the dial.
- No claim about Bayesian superiority until adaptive-attack runs exist.
