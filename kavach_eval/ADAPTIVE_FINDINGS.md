# Kavach — Adaptive Attack Findings (CORRECTED v2)

## CORRECTION NOTICE
An earlier version of this doc claimed "no aggregator survives K=2 corrupted
Ministers." That was WRONG — it tested max-score / majority / Bayesian but NOT
the real repo Speaker, which uses **weighted-risk + veto**. Re-tested against
the actual design. The corrected results are below.

## The real Speaker design (from repo)
`risk_score = Σ(confidence × weight × vote) / Σ weight`, block if risk > 0.6.
Weights: Integrity 1.0, Trajectory 0.9, Memory 0.8.
**VETO: any Minister voting BLOCK with confidence > 0.9 → instant BLOCK.**
(That veto is the "5th case" and it matters enormously.)

## Corrected adaptive-attack curve (synthetic, 300 actions)

Attacker corrupts K Ministers' votes to ALLOW@0.92 on each attack:

| K corrupted | max-score | majority | bayesian(rho=.05) | **real (veto)** |
|---|---|---|---|---|
| 0 | 0.025 | 0.118 | 0.252 | **0.025** |
| 1 | 0.109 | 0.445 | 0.664 | **0.076** |
| 2 | 0.286 | 0.824 | 1.000 | **0.277** |
| 3 | 0.664 | 1.000 | 1.000 | **0.664** |
| 4 | 1.000 | 1.000 | 1.000 | **1.000** |

**The veto-based Speaker is the most robust of all four.** It does not collapse
at K=2. The attacker must defeat EVERY high-confidence BLOCK, not just a
majority, because one surviving BLOCK@>0.9 vetoes.

## The real tradeoff (this is the contribution)

| Aggregator | clean FPR | adaptive robustness |
|---|---|---|
| Bayesian (tuned) | **0.011 (excellent)** | poor — collapses at K=2 |
| Real veto | 0.116 (too high, >5% target) | **strong — holds at K=2** |

- The veto buys robustness but is **trigger-happy**: FPR 11.6% fails the
  team's <5% benign requirement.
- The Bayesian aggregator has great FPR but is brittle under attack.
- **Neither alone is acceptable.** The honest research result is the tension.

## Recommended architecture (hybrid)
Use **Bayesian aggregation for the normal decision path** (low FPR, calibrated
confidence) but **retain the veto as a hard safety floor** (adaptive robustness).
Then tune the veto confidence threshold (currently 0.9) to claw FPR back under
5% while keeping the K=2 robustness. That tuning is an offline sweep we can run
on Parv's real dump — no GPU.

## What this means for the paper
The story is NOT "our aggregator is best." It's:
"Pure score-aggregation (incl. our Bayesian variant) is brittle to adaptive
attack; pure veto is robust but sacrifices benign utility; we characterise the
exact FPR/robustness frontier and propose a hybrid (Bayesian path + veto floor)
that we tune to the operating point." That's a real, defensible, honest
contribution with quantified curves.

## Still TODO (Parv, on real data)
1. Re-run this curve on REAL minister_runs.jsonl (not synthetic).
2. Sweep veto-confidence threshold to find FPR<5% AND K=2 robustness.
3. Test with the genuinely diverse Ministers (Integrity/Memory/Trajectory run
   different signals) — diversity should raise per-Minister flip cost further.

## What NOT to claim
- Do NOT claim the Bayesian Speaker beats the existing veto Speaker. It does not
  on robustness. It wins only on FPR.
- Do NOT repeat the earlier "everything collapses at K=2" — that was a testing
  error against the wrong aggregator. Corrected here.
