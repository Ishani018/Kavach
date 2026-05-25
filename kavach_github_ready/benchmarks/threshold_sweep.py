#!/usr/bin/env python3
"""
benchmarks/threshold_sweep.py
==============================

Sweeps minister block thresholds across a range, runs the parliament at each
setting against the InjecAgent attacks AND the benign-traces set, then plots
the ROC curve and derives the optimal threshold via Youden's J.

This script does NOT replay the embedding work at every threshold — that would
be wasteful. Instead it expects a pre-computed CSV with one row per
(case_id, test_kind) and one column per minister giving the maximum cosine
similarity that minister produced. The threshold sweep is then a pure post-
processing step: at each candidate threshold, recompute verdicts from the
similarity columns and aggregate.

To produce the input CSV, run:
    python benchmarks/injecagent_runner.py \\
        --cases path/to/InjecAgent.json \\
        --output benchmarks/results_v1/ \\
        --include-benign

The runner emits per-minister sim columns (executor_sim, vault_sim,
channel_sim, navigator_sim) directly in results.csv. Pass that file as
--input here.

Outputs:
    sweep.csv               — TPR/FPR/F1 at each threshold for each minister
    roc_curves.png          — one ROC curve per minister
    optimal_thresholds.json — Youden's J optimum per minister

Usage:
    python benchmarks/threshold_sweep.py \\
        --input benchmarks/results_v1/results_per_minister.csv \\
        --output benchmarks/results_v1/sweep/

Threshold range:
    By default sweeps 0.30 → 0.85 in 0.05 increments (12 points).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
log = logging.getLogger("threshold_sweep")


MINISTERS = ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"]


# ──────────────────────────────────────────────────────────────────────────────
# Single-minister sweep
# ──────────────────────────────────────────────────────────────────────────────

def sweep_minister(
    df: pd.DataFrame,
    minister: str,
    thresholds: np.ndarray,
) -> pd.DataFrame:
    """
    For a given minister, compute TPR/FPR at each threshold.

    `df` must contain columns:
      - test_kind (attack | benign)
      - <minister>_sim    (the maximum cosine sim this minister produced)
    """
    sim_col = f"{minister.lower()}_sim"
    if sim_col not in df.columns:
        raise KeyError(f"input CSV missing column {sim_col}")

    attacks = df[df["test_kind"] == "attack"]
    benigns = df[df["test_kind"] == "benign"]

    rows = []
    for t in thresholds:
        # A minister "blocks" iff max sim ≥ threshold.
        tp = int((attacks[sim_col] >= t).sum())
        fn = int((attacks[sim_col] <  t).sum())
        fp = int((benigns[sim_col] >= t).sum())
        tn = int((benigns[sim_col] <  t).sum())

        n_atk = tp + fn
        n_ben = fp + tn

        tpr = tp / n_atk if n_atk else 0.0
        fpr = fp / n_ben if n_ben else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        f1 = (
            2 * precision * tpr / (precision + tpr)
            if (precision + tpr) > 0 else 0.0
        )
        youden_j = tpr - fpr

        rows.append({
            "minister":  minister,
            "threshold": round(float(t), 3),
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "tpr":       round(tpr, 4),
            "fpr":       round(fpr, 4),
            "precision": round(precision, 4),
            "f1":        round(f1, 4),
            "youden_j":  round(youden_j, 4),
        })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Main sweep
# ──────────────────────────────────────────────────────────────────────────────

def run_sweep(args: argparse.Namespace) -> None:
    in_path = Path(args.input)
    if not in_path.exists():
        log.error("input CSV not found: %s", in_path)
        log.error("run injecagent_runner.py first to produce per-minister scores")
        return

    df = pd.read_csv(in_path)
    log.info("loaded %d rows from %s", len(df), in_path)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    thresholds = np.arange(args.tmin, args.tmax + args.tstep / 2, args.tstep)
    log.info("sweeping thresholds %.2f → %.2f step %.2f (%d points)",
             args.tmin, args.tmax, args.tstep, len(thresholds))

    all_sweeps = []
    optimums: dict[str, dict] = {}

    for minister in MINISTERS:
        if f"{minister.lower()}_sim" not in df.columns:
            log.warning("skipping %s: column not in CSV", minister)
            continue

        sweep = sweep_minister(df, minister, thresholds)
        all_sweeps.append(sweep)

        # Find Youden's J optimum
        best_idx = int(sweep["youden_j"].idxmax())
        best = sweep.iloc[best_idx]
        optimums[minister] = {
            "threshold": float(best["threshold"]),
            "tpr":       float(best["tpr"]),
            "fpr":       float(best["fpr"]),
            "f1":        float(best["f1"]),
            "youden_j":  float(best["youden_j"]),
        }
        log.info(
            "%s: optimal threshold=%.2f  TPR=%.3f  FPR=%.3f  J=%.3f",
            minister, best["threshold"], best["tpr"], best["fpr"], best["youden_j"],
        )

    # Concatenate and save sweep CSV
    if all_sweeps:
        combined = pd.concat(all_sweeps, ignore_index=True)
        sweep_path = out_dir / "sweep.csv"
        combined.to_csv(sweep_path, index=False)
        log.info("wrote sweep table to %s", sweep_path)

    # Save optimum thresholds JSON
    opt_path = out_dir / "optimal_thresholds.json"
    opt_path.write_text(json.dumps(optimums, indent=2))
    log.info("wrote optimums to %s", opt_path)

    # Plot ROC
    plot_roc(combined, out_dir / "roc_curves.png", optimums)
    plot_f1(combined, out_dir / "f1_vs_threshold.png", optimums)


# ──────────────────────────────────────────────────────────────────────────────
# Plotting
# ──────────────────────────────────────────────────────────────────────────────

def plot_roc(combined: pd.DataFrame, out_path: Path, optimums: dict) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))
    colors = {
        "EXECUTOR":   "#c0392b",
        "VAULT":      "#8e44ad",
        "CHANNEL":    "#16a085",
        "NAVIGATOR":  "#d68910",
    }

    for minister in MINISTERS:
        sub = combined[combined["minister"] == minister]
        if sub.empty:
            continue
        sub = sub.sort_values("fpr")
        ax.plot(sub["fpr"], sub["tpr"], "o-",
                color=colors[minister], label=minister, markersize=4)

        if minister in optimums:
            opt = optimums[minister]
            ax.scatter([opt["fpr"]], [opt["tpr"]],
                       color=colors[minister], s=110,
                       edgecolor="black", linewidth=1.5, zorder=5)

    ax.plot([0, 1], [0, 1], "--", color="#888", linewidth=1, label="random")
    ax.set_xlabel("False Positive Rate (benign blocked / benign total)")
    ax.set_ylabel("True Positive Rate (attack blocked / attack total)")
    ax.set_title("Kavach minister ROC — InjecAgent + benign traces")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    log.info("wrote ROC plot to %s", out_path)


def plot_f1(combined: pd.DataFrame, out_path: Path, optimums: dict) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    colors = {
        "EXECUTOR":   "#c0392b",
        "VAULT":      "#8e44ad",
        "CHANNEL":    "#16a085",
        "NAVIGATOR":  "#d68910",
    }

    for minister in MINISTERS:
        sub = combined[combined["minister"] == minister].sort_values("threshold")
        if sub.empty:
            continue
        ax.plot(sub["threshold"], sub["f1"], "o-",
                color=colors[minister], label=minister, markersize=4)

        if minister in optimums:
            opt = optimums[minister]
            ax.axvline(opt["threshold"], linestyle=":",
                       color=colors[minister], alpha=0.5)

    ax.set_xlabel("threshold")
    ax.set_ylabel("F1")
    ax.set_title("Kavach minister F1 vs threshold")
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    log.info("wrote F1 plot to %s", out_path)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Sweep Kavach minister thresholds")
    p.add_argument("--input", required=True,
                   help="CSV with per-minister sim columns "
                        "(executor_sim, vault_sim, channel_sim, navigator_sim)")
    p.add_argument("--output", default="benchmarks/results_v1/sweep",
                   help="output directory")
    p.add_argument("--tmin",  type=float, default=0.30, help="min threshold")
    p.add_argument("--tmax",  type=float, default=0.85, help="max threshold")
    p.add_argument("--tstep", type=float, default=0.05, help="threshold step")

    args = p.parse_args()
    run_sweep(args)


if __name__ == "__main__":
    main()
