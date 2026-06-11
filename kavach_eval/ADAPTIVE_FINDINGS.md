# Kavach — Adaptive Attack Findings (v3 — CORRECTED AGAIN, June 10 2026)

## ⚠️ CORRECTION NOTICE v3 — READ FIRST
v2 of this document claimed to test "the real repo Speaker," described as a
weighted-risk aggregator (`Σ(confidence × weight × vote)/Σ weight`, weights
Integrity 1.0 / Trajectory 0.9 / Memory 0.8, veto at confidence > 0.9).

**That Speaker does not exist in this repo.** It was the April design-deck
aggregator and was never implemented. The deployed Speaker is
`parliament/speaker.py::combine_verdicts`: ministers EXECUTOR / VAULT /
CHANNEL / NAVIGATOR, and the rule is a **pure veto** — any single minister
at BLOCK (sim ≥ its per-minister block threshold) blocks. No weights, no
0.6 risk score, no 0.9 confidence floor. The v2 script also could not run
against the merged repo (`import speaker` → `BayesianSpeaker` lives in
`speaker_bayesian.py`).

**Every number in v2 is therefore INVALID** — including the widely-quoted
"real veto FPR 11.6% vs Bayesian 1.1%" comparison and the K=0..4 ASR table.
Do not cite them anywhere.

## What replaces them
`adaptive_attack.py` v3 evaluates five aggregators on a `minister_runs.jsonl`
dump, including the **actual** deployed `combine_verdicts` and the proposed
hybrid (Bayesian decision path + hard veto floor at a sweepable confidence
threshold). It is verified to run end-to-end offline (no GPU) on synthetic
data from `make_synthetic.py`.

Pipeline-verification run (synthetic, 500 actions, seed 42 — **NOT results,
do not cite numbers**): the qualitative structure holds and is, if anything,
sharper than v2 suggested, because the deployed Speaker is a *pure* veto:

- kavach-veto (REAL): lowest ASR at every K, but clean FPR far above the 5%
  gate on this fixture — trigger-happy by construction.
- bayesian(rho=0.05): passes the FPR gate easily, collapses to ASR 1.0 at K=2.
- hybrid(veto=0.90): passes the FPR gate AND tracks the real veto's K=2
  robustness within a few points. The veto-threshold sweep shows the
  FPR/robustness frontier cleanly — the knob works.

## The paper claim (unchanged in spirit, now actually testable)
"Pure score-aggregation (incl. our Bayesian variant) is brittle to adaptive
minister-corruption; the deployed pure-veto Speaker is robust but sacrifices
benign utility; we characterise the measured FPR/robustness frontier and
propose a hybrid (Bayesian path + veto floor) tuned to an operating point
satisfying both." All §5 numbers come from re-running v3 on Parv's real dump.

## TODO (Parv → Ishani, all offline after the dump)
1. Parv dumps `minister_runs.jsonl` per HANDOFF_SCHEMA.md (now with ESCALATE
   in the vote vocabulary and optional compass_sim / traj_risk per line).
2. `python adaptive_attack.py minister_runs.jsonl --sweep-veto`
3. Measure real rho with eval_harness.py; re-run with `--rho <measured>`.
4. Report the chosen operating point + full frontier table in paper §5.

## What NOT to claim
- Nothing from v2. The v2 script is preserved as
  `adaptive_attack_v2_deprecated.py.bak` for the audit trail only.
- No Bayesian-superiority claim — it wins only on FPR, loses on robustness.
- Synthetic fixture numbers are pipeline checks, never results.
