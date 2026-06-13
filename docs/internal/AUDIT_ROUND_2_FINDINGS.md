# Audit Round 2 — Findings (2026-06-11)

Laptop secondary config (qwen2.5:3b, CPU), current hybrid corpus on :8088.
**All numbers here are SMALL-N (79 cases: 62 attack + 17 benign) and are
directional, not publishable magnitudes.** The real numbers need the Dell
large-N run. Tables produced via `make_section5.py` are `--synthetic`
watermarked.

## #1 — Threshold sweep on hybrid corpus (small-N)
Re-ran `threshold_sweep.py` on a freshly scored hybrid `results.csv`
(`results_hybrid_smalln.csv`, built by `build_hybrid_sweep_input.py`).
Output: `results_v2/sweep_smalln/`.

| Minister | Old (pre-hybrid, ~1116) TPR/FPR/J | New (hybrid, small-N 79) TPR/FPR/J |
|---|---|---|
| EXECUTOR | 0.90 / 0.47 / 0.43 | 0.32 / 0.18 / 0.15 |
| VAULT | 0.84 / 0.71 / 0.13 | 0.82 / 0.71 / 0.12 |
| CHANNEL | 0.52 / 0.24 / 0.28 | 0.90 / 0.59 / 0.32 |
| NAVIGATOR | 0.37 / 0.29 / 0.077 | 0.73 / 0.53 / 0.20 |

**NOT apples-to-apples** (different N and different case sets — old used full
InjecAgent 1054). Robust signal across both: every Youden's J is low (≤0.32),
optimal thresholds cluster at the 0.30 floor, all FPR ≥ 0.18. Per-minister
discrimination looks weak on small-N; defer the verdict to the Dell run.

## #2 — Trajectory ceiling (issue #9): mechanism works, never fires
The accumulation logic and Speaker Case 0 (`decided_by="TRAJECTORY"`,
`traj_risk >= 0.72`) are correctly wired. But:
- **No integration test ever makes >1 `/hook/parliament` call per session**, so
  the ceiling is unreachable in the e2e suite. It has never fired end-to-end.
- **Live staged 5-step credential-exfil chain** (same session): traj_risk
  climbs 0.0 → 0.227 → 0.501 → 0.462 → **0.562** — peaks **below** the 0.72
  ceiling. Every step was still BLOCK'd by individual ministers.
- **Benign 5-step session**: traj_risk peaks **0.381**.

Attack-vs-benign separation is only ~0.18 and they interleave. The ceiling
(0.72) is above both. **Decision pending** (retune to ~0.45–0.50 vs document as
unfired defense-in-depth backstop); needs a larger benign/attack traj_risk
distribution (N=1 each is too thin to set a threshold).

**Bug found:** the offline Bayesian aggregator (`speaker_bayesian._likelihood`)
rejects `ESCALATE` votes (only ALLOW/BLOCK/ABSTAIN), but the live parliament
emits ESCALATE constantly. `make_section5.py` on real votes hits this. Needs a
real ESCALATE-handling decision before the §5 Bayesian numbers are trustworthy.

## #3 — Minister ablation (small-N, synthetic-watermarked)
| Config | ASR | FPR | Accuracy |
|---|---|---|---|
| 1 (CHANNEL) | 100.0% | 0.0% | 0.632 |
| 2 (+EXECUTOR) | 46.9% | 0.8% | 0.823 |
| 3 (+NAVIGATOR) | 45.6% | 1.6% | 0.823 |
| 4 (+VAULT) | 21.8% | 0.0% | 0.920 |

Full parliament beats every subset (acc 0.92 vs best-single 0.63) — supports
defense-in-depth. VAULT is the biggest ensemble contributor here. NAVIGATOR's
marginal value on this per-call benchmark is small but non-negative (doesn't
raise ASR) — consistent with #4.

## #4 — NAVIGATOR vs EXECUTOR overlap: hypothesis REFUTED
Cosine of each NAVIGATOR pattern to its nearest EXECUTOR pattern (both
collections L2-normalized, 300 docs each):
- mean **0.742**, median **0.750**, max **0.877**
- > 0.80: 11% · > 0.85: 1% · **> 0.90: 0%**

This is moderate shared-vocabulary relatedness, **not duplication** (a weak
duplicate would show mean ~0.90+ and many >0.90 pairs; there are none).
NAVIGATOR's content is a distinct class (scope_widening, task_pivot,
filesystem/process recon, COMPASS-drift-coupled). Its low single-call InjecAgent
TPR is a **benchmark-mismatch artifact** — it's a trajectory/scope detector that
a per-call benchmark structurally under-tests (the paper already states this).
**No corpus change warranted.**

## #5 — Integration test key mismatches: FIXED
Five Category-A test-harness bugs (wrong JSON keys, fail() arity). Server was
correct. Suite 9/17 → 14/17. See commit.
