"""
calibrate.py — Kavach Minister confidence calibration
Reads minister_runs.jsonl, measures how well each Minister's stated
confidence matches reality, and fits a temperature-scaling correction.

Why this matters: the Bayesian Speaker assumes confidence ~ P(correct).
If a Minister says 0.9 but is only right 70% of the time, the Speaker
trusts it too much. Temperature scaling rescales confidences so they
mean what they say.

Outputs:
  - Per-Minister ECE before and after calibration
  - Fitted temperature T per Minister
  - minister_temperatures.json  (Parv loads this into the Speaker)

Run: python calibrate.py minister_runs.jsonl
"""

import sys
import json
import math
import statistics
from collections import defaultdict


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


# ---------------------------------------------------------------------------
# Confidence <-> logit helpers
# ---------------------------------------------------------------------------

def _clip(p, eps=1e-6):
    return max(eps, min(1 - eps, p))


def conf_to_logit(p):
    p = _clip(p)
    return math.log(p / (1 - p))


def logit_to_conf(z):
    return 1.0 / (1.0 + math.exp(-z))


def apply_temperature(conf, T):
    """Temperature scaling: divide the logit by T, map back to probability.
    T > 1 softens overconfidence; T < 1 sharpens underconfidence."""
    return logit_to_conf(conf_to_logit(conf) / T)


# ---------------------------------------------------------------------------
# ECE
# ---------------------------------------------------------------------------

def ece(pairs, n_bins=10):
    """pairs = [(confidence, correct_bool)]. Expected Calibration Error."""
    if not pairs:
        return 0.0
    bins = [[] for _ in range(n_bins)]
    for conf, correct in pairs:
        idx = min(int(conf * n_bins), n_bins - 1)
        bins[idx].append((conf, correct))
    total = len(pairs)
    e = 0.0
    for b in bins:
        if not b:
            continue
        avg_conf = statistics.mean(c for c, _ in b)
        acc = statistics.mean(1.0 if ok else 0.0 for _, ok in b)
        e += (len(b) / total) * abs(avg_conf - acc)
    return e


# ---------------------------------------------------------------------------
# Fit temperature by minimising ECE (grid search — robust, no autograd needed)
# ---------------------------------------------------------------------------

def fit_temperature(pairs):
    """Find T that minimises ECE for one Minister."""
    if len(pairs) < 20:
        return 1.0  # not enough data — leave uncorrected
    best_T, best_e = 1.0, ece(pairs)
    # search T in a sensible range
    T = 0.5
    while T <= 5.0:
        scaled = [(apply_temperature(c, T), ok) for c, ok in pairs]
        e = ece(scaled)
        if e < best_e:
            best_e, best_T = e, T
        T += 0.05
    return round(best_T, 2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def calibrate(path, out="minister_temperatures.json"):
    runs = load(path)
    by_minister = defaultdict(list)
    for r in runs:
        gt = r["ground_truth"]
        for v in r["minister_votes"]:
            if v["vote"] == "ABSTAIN":
                continue
            by_minister[v["minister"]].append((v["confidence"], v["vote"] == gt))

    print(f"\n{'='*58}")
    print(f"KAVACH CALIBRATION  —  {len(runs)} actions")
    print(f"{'='*58}\n")
    print(f"{'Minister':<12}{'n':>6}{'ECE_before':>12}{'T':>6}{'ECE_after':>12}")
    print("-" * 58)

    temps = {}
    for minister, pairs in sorted(by_minister.items()):
        e_before = ece(pairs)
        T = fit_temperature(pairs)
        scaled = [(apply_temperature(c, T), ok) for c, ok in pairs]
        e_after = ece(scaled)
        temps[minister] = T

        verdict = ""
        if e_before < 0.05:
            verdict = "already well-calibrated"
        elif e_after < e_before - 0.02:
            verdict = f"improved {e_before-e_after:+.3f}"
        else:
            verdict = "no meaningful gain"
        print(f"{minister:<12}{len(pairs):>6}{e_before:>12.3f}{T:>6}{e_after:>12.3f}  {verdict}")

    with open(out, "w") as f:
        json.dump(temps, f, indent=2)

    print(f"\n  Fitted temperatures written to {out}")
    print(f"  Load into Speaker: apply_temperature(conf, T[minister]) before aggregate()\n")

    # Recommendation
    avg_before = statistics.mean(ece(p) for p in by_minister.values())
    avg_after = statistics.mean(
        ece([(apply_temperature(c, temps[m]), ok) for c, ok in p])
        for m, p in by_minister.items()
    )
    print(f"  Avg ECE: {avg_before:.3f} -> {avg_after:.3f}")
    if avg_after < 0.1:
        print("  >> Confidences trustworthy after scaling. Safe to tune + trust Bayesian conf.")
    else:
        print("  >> Still poorly calibrated. Bayesian confidence output remains unreliable;")
        print("     report decisions but flag confidence as approximate.")
    print(f"{'='*58}\n")
    return temps


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "minister_runs.jsonl"
    calibrate(path)
