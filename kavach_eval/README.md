# Kavach Offline Eval Suite — `kavach_eval/`

**Author:** Ishani · **For:** Parv (Dell runs) + paper evaluation
**Status:** all tools tested & GPU-free. Positioned as **additive** — nothing
here overwrites the working `parliament/speaker.py` (13 tests) or
`compass_calibrator.py`.

---

## What this is

A complete offline analysis pipeline for Kavach. The idea: **Parv runs the
Ministers on the Dell once and dumps the votes; everything else runs here with
no GPU.** Metrics, calibration, correlation, tuning, and adaptive-attack
evaluation all read a single dump file.

```
   [Dell / Parv]                    [anywhere / Ishani + Claude]
  run Ministers over    --dump-->   minister_runs.jsonl  -->  eval_harness.py
  AgentDojo/ASB/etc                                            minister_calibrate.py
  (only step needing GPU)                                      tune.py
                                                               adaptive_attack.py
```

---

## IMPORTANT: how this relates to the existing repo

| This suite | Existing repo | Relationship |
|---|---|---|
| `speaker_bayesian.py` (proposed) | `parliament/speaker.py` (working, 13 tests) | **Candidate, NOT replacement.** See below. |
| `minister_calibrate.py` | `compass_calibrator.py` | Different jobs — per-Minister temperature scaling vs COMPASS threshold (Youden's J). No overwrite. |
| everything else | — | Pure new analysis. Touches nothing. |

### The Bayesian Speaker is a candidate, not a drop-in
The real Speaker uses **weighted-risk + veto** (any BLOCK@conf>0.9 → instant
block). Testing showed:
- Bayesian aggregator: **excellent FPR (~1%)** but **brittle to adaptive attack**.
- Existing veto Speaker: **robust to adaptive attack** but **FPR ~11% (fails <5%)**.

**Neither wins outright.** Do not promote the Bayesian Speaker to default. The
recommended direction is a **hybrid** (Bayesian path + veto floor), tuned on
real data. See `ADAPTIVE_FINDINGS.md`. Promotion is **data-gated**: only if the
harness shows a hybrid beats the current Speaker on Parv's real runs.

### Note on Ministers vs corpus domains
Real Ministers: **Integrity, Memory, Trajectory** (weights 1.0 / 0.8 / 0.9).
EXECUTOR/VAULT/CHANNEL/NAVIGATOR are corpus/router domains, a different layer.
The synthetic data here uses 4 placeholder names for pipeline testing only —
swap to the real 3 Ministers when wiring to real dumps.

---

## Files

| File | What it does |
|---|---|
| `HANDOFF_SCHEMA.md` | The JSONL contract Parv dumps. Read this first. |
| `eval_harness.py` | ASR / FPR / utility under each Speaker variant; per-Minister calibration; correlation matrix (measures real rho); N-Minister ablation; latency. |
| `minister_calibrate.py` | Per-Minister temperature scaling. Recovers overconfident Ministers (tested: ECE 0.23→0.11). Writes `minister_temperatures.json`. |
| `tune.py` | Sweeps (rho, threshold), prints utility/security Pareto frontier, recommends an operating point under an FPR ceiling. |
| `adaptive_attack.py` | Corrupts K Minister votes per attack; measures ASR vs K for each aggregator. The experiment that tests robustness. |
| `make_synthetic.py` | Generates test-fixture dumps with tunable correlation/skill/miscalibration. **For testing the pipeline only — not results.** |
| `ADAPTIVE_FINDINGS.md` | The corrected robustness analysis + the FPR/robustness tradeoff. **Read before writing the paper.** |
| `STATUS.md` | Honest state of every finding. |

---

## Parv's run order (on the Dell)

```bash
# 1. Run the 3 Ministers over a benchmark, dump one line per action.
#    Follow HANDOFF_SCHEMA.md exactly. This is the ONLY GPU step.
#    Output: minister_runs.jsonl

# 2. Hand minister_runs.jsonl to Ishani. Done on the Dell side.
```

That's it for Parv. He does not run the Speaker, compute metrics, calibrate,
or tune. All of that is below.

## Ishani's run order (no GPU, any machine)

```bash
cd kavach_eval

# 1. Full report — also prints the MEASURED rho to set in the Speaker
python3 eval_harness.py minister_runs.jsonl

# 2. Calibrate Minister confidences BEFORE tuning
python3 minister_calibrate.py minister_runs.jsonl

# 3. Find the operating point (rho, threshold) under your FPR ceiling
python3 tune.py minister_runs.jsonl --max-fpr 0.05

# 4. Adaptive-attack robustness curve for every aggregator
python3 adaptive_attack.py minister_runs.jsonl
```

---

## BLOCKING ISSUES before any live demo or benchmark

1. **Threshold is not the default.** `speaker.py` default BLOCK_THRESHOLD (0.55)
   is NOT the tuned operating point (~0.35–0.40 in tests). Set it from
   `tune.py` on REAL data before any demo, or the system is far too permissive.
2. **Benign FPR < 5%** must pass before any benchmark (already a known team
   blocker). The veto threshold likely needs tuning to hit this.
3. **Calibrate before tuning.** If Minister ECE is high, `tune.py` may find no
   feasible point. Run `minister_calibrate.py` first.

---

## What's verified (tested by running, not just reading)

- All metrics handle empty / all-attack / all-benign inputs without div-by-zero.
- Loader skips malformed JSONL lines with a warning (doesn't crash the run).
- Speaker rejects NaN/inf confidence and unknown vote strings (no silent corruption).
- Duplicate-Minister vote-stuffing is deduplicated.
- Calibration correctly recovers overconfident Ministers.
- Correlation math unit-tested against known cases (1.0 / -1.0 / 0.0 exact).
- Adaptive attack tested against the REAL veto aggregator (corrected finding).

## What is NOT done (needs Parv's real data)
- Real benchmark numbers (everything here is synthetic pipeline-validation).
- Veto-threshold sweep for the hybrid.
- Heterogeneous-Minister diversity test.
