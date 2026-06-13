# Trajectory Ceiling — Diagnosis & Redesign (2026-06-13)

## The problem the Dell benign gate exposed

The Dell benign gate (`benchmarks/results_v2/latency/`) blocked **93/93** benign
coding actions — `read_file src/cli.py`, `pytest -x`, etc. **Every** block was
`decided_by: TRAJECTORY` (none from the four ministers; see `blocked_actions.txt`).
So the InjecAgent "FPR 0.0%" (per-action, fresh sessions, ministers only) is real,
but the **session-level trajectory ceiling** is firing on ordinary work.

## Root cause: the ceiling was an absolute threshold on a non-transferable quantity

Extracted `traj_risk` from the 93 benign Dell sessions (`benign_results.csv` `reason`):

```
BENIGN traj_risk (Dell, n=93): min=0.519 p50=0.616 p95=0.638 max=0.663 mean=0.617
```

Compared to the laptop calibration (`traj_distribution.json`, 10+10 sessions) the
0.50 ceiling was tuned on:

| | Laptop (calibration) | Dell (live benign) |
|---|---|---|
| Benign peak traj_risk | mean 0.419, **max 0.497** | mean 0.617, **min 0.519** |
| Attack peak traj_risk | mean 0.524, max 0.616 | (not captured) |

Two findings:

1. **No clean separation even in-distribution.** The laptop `attack_peaks` were
   `[0.444, 0.450, 0.455, 0.469, 0.529, ...]` — **4 of 10 attacks scored *below*
   the 0.497 benign max.** The `analysis.separable_at: True` claim in
   `traj_distribution.json` is wrong; no single absolute threshold catches all
   attacks without benign false-triggers.

2. **Not transferable across configs.** Dell *benign* sessions (min 0.519) score
   *higher* than laptop *attacks* (mean 0.524). The whole distribution shifted up
   ~0.2, so the 0.50 ceiling → **100% benign FPR** on Dell.

### Why it shifted: `_accumulation` measured absolute confidence

The dominant leg (`W_ACCUMULATION=0.35`) was the decayed **absolute** average of
per-call minister confidence. On the Dell (Gemma 4 26B) benign coding actions sit
at cosine ~0.6 against the corpus vs ~0.4 on the laptop, so benign accumulation
ran ~0.62. The signal was tracking the **backbone's confidence floor**, not attack
behavior. An absolute threshold on a scale-dependent quantity cannot transfer.

## The redesign: baseline-relative accumulation (scale-invariant)

`_accumulation` now subtracts a **per-session baseline** (the floor of observed
confidence — "what benign looks like in *this* session/config") and normalizes by
the headroom above it. Only confidence that **rises above the session's own floor**
accumulates risk; a session that stays flat at its baseline scores ~0, regardless
of whether that baseline is 0.4 (laptop) or 0.6 (Dell).

### Synthetic validation (pure-Python, scale-invariance check)

| Session | OLD accum | NEW accum |
|---|---|---|
| Laptop benign (flat ~0.4) | 0.403 | **0.038** |
| Dell benign (flat ~0.6) | 0.618 | **0.045** |
| Attack, rising 0.4→0.85 | 0.651 | **0.419** |
| Attack, sustained-high flat 0.7 | 0.718 | 0.059 |

- Flat benign collapses to ~0.04 at **both** scales → the config-transfer bug is fixed.
- A **rising** attack (the stealthy ramp trajectory is designed to catch) scores
  9× higher than benign → separation restored for the relevant class.
- A **sustained-high-flat** attack now scores low on this leg — by design: that
  case is caught by per-minister BLOCK (each call already exceeds the block
  threshold), not by the trajectory layer. Trajectory's job is the individually-
  benign-but-escalating chain.

## Status & what still needs the Dell

- ✅ **Code:** `_accumulation` redesigned to baseline-relative (this commit).
- ⚠️ **Combined-risk re-validation pending.** The saved laptop traces are per-step
  *combined* risk, not raw confidences, so the full `trajectory_risk` (all 5 legs)
  could not be re-simulated offline. The new benign accumulation is ~0.04, so
  combined benign risk should fall well under any reasonable ceiling — but this
  must be confirmed by re-running the benign gate (and the staged 5-step attack
  for the attack side) on the next Dell/GPU session.
- ⚠️ **Ceiling value (`TRAJ_BLOCK_CEILING=0.50`) left unchanged** pending that
  re-validation. With relative accumulation it should no longer trip on benign,
  but the final value should be set from the *new* benign/attack distributions,
  not the stale laptop ones. Capture per-call `confidence` + `traj_risk` in the
  next benign-gate + staged-attack runs so the ceiling can be set with real
  separation data.

## Paper implication (§4 / §7)

The honest framing: the per-minister parliament FPR is 0% (hard blocks,
high-precision). The session trajectory ceiling needed a scale-invariant
redesign; the absolute-threshold version did not transfer across backbones. This
is a deployment lesson worth one sentence in §7 limitations / future work.
