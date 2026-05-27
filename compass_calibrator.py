#!/usr/bin/env python3
"""
compass_calibrator.py
=====================

Calibrates the COMPASS drift threshold from the 100 calibration pairs in the
corpus, using Youden's J on the cosine-similarity distribution between
"aligned" pairs (intent + on-task action) and "drifted" pairs (intent +
off-task action).

Read order: REPRODUCIBILITY.md Step 3.

Inputs:
    kavach_corpus_v2.json (or v1) — must have a COMPASS section with pairs
    .chroma_kavach/                — populated by corpus_loader.py

Outputs:
    compass_calibration.json — {threshold, distributions, n_aligned, n_drifted}
    compass_histogram.png    — visual sanity check
    parliament/config.yaml   — threshold updated in-place (with --update-config)

Usage:
    python compass_calibrator.py \\
        --corpus kavach_corpus_v1.json \\
        --output compass_calibration.json \\
        --update-config

CLI flags:
    --no-update-config: print the threshold but don't modify config.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from sentence_transformers import SentenceTransformer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
log = logging.getLogger("compass_calibrator")


# ──────────────────────────────────────────────────────────────────────────────
# BGE embedding helpers — must match parliament/server.py exactly
# ──────────────────────────────────────────────────────────────────────────────

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def embed_query(model: SentenceTransformer, text: str) -> np.ndarray:
    """BGE query-side embedding with the asymmetric prefix."""
    vec = model.encode(
        QUERY_PREFIX + text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vec, dtype=np.float32)


# ──────────────────────────────────────────────────────────────────────────────
# Calibration
# ──────────────────────────────────────────────────────────────────────────────

def calibrate(corpus_path: Path, model_name: str) -> dict:
    """Return calibration results: threshold, distributions, n_aligned, n_drifted."""
    corpus = json.loads(corpus_path.read_text())
    pairs = (
        corpus.get("COMPASS", {}).get("pairs")
        or corpus.get("compass_pairs")
        or []
    )
    if not pairs:
        log.error("no COMPASS pairs in corpus")
        sys.exit(1)
    log.info("loaded %d COMPASS pairs", len(pairs))

    log.info("loading BGE model: %s", model_name)
    model = SentenceTransformer(model_name)

    aligned_sims: list[float] = []
    drifted_sims: list[float] = []

    for i, pair in enumerate(pairs):
        intent_text = pair.get("user_intent") or pair.get("intent") or ""
        action_text = pair.get("proposed_action") or pair.get("action") or ""
        label = (
            pair.get("label")
            or pair.get("alignment")
            or ("aligned" if pair.get("aligned") else "drifted")
        )
        if not intent_text or not action_text:
            log.warning("skipping pair %d: missing intent or action", i)
            continue

        v_intent = embed_query(model, intent_text)
        v_action = embed_query(model, action_text)
        sim = float(np.dot(v_intent, v_action))

        if label.lower() in ("aligned", "on_task", "ontask", "true", "1"):
            aligned_sims.append(sim)
        elif label.lower() in ("drifted", "off_task", "offtask", "false", "0"):
            drifted_sims.append(sim)
        else:
            log.warning("skipping pair %d: unknown label %r", i, label)

    log.info(
        "aligned: n=%d  mean=%.3f  std=%.3f  min=%.3f  max=%.3f",
        len(aligned_sims),
        np.mean(aligned_sims) if aligned_sims else 0,
        np.std(aligned_sims) if aligned_sims else 0,
        min(aligned_sims) if aligned_sims else 0,
        max(aligned_sims) if aligned_sims else 0,
    )
    log.info(
        "drifted: n=%d  mean=%.3f  std=%.3f  min=%.3f  max=%.3f",
        len(drifted_sims),
        np.mean(drifted_sims) if drifted_sims else 0,
        np.std(drifted_sims) if drifted_sims else 0,
        min(drifted_sims) if drifted_sims else 0,
        max(drifted_sims) if drifted_sims else 0,
    )

    # ── Youden's J sweep ──────────────────────────────────────────────────
    # COMPASS treats sim < threshold as drift (i.e. drift → positive).
    # So at threshold t:
    #   TP = drifted sims < t
    #   FN = drifted sims ≥ t
    #   TN = aligned sims ≥ t
    #   FP = aligned sims < t
    # TPR = TP / (TP+FN)   FPR = FP / (FP+TN)   J = TPR - FPR
    candidates = np.linspace(0.0, 1.0, 201)
    best = {"threshold": 0.5, "tpr": 0.0, "fpr": 0.0, "j": -1.0}
    sweep = []

    for t in candidates:
        tp = sum(1 for s in drifted_sims if s < t)
        fn = sum(1 for s in drifted_sims if s >= t)
        fp = sum(1 for s in aligned_sims if s < t)
        tn = sum(1 for s in aligned_sims if s >= t)
        tpr = tp / max(1, tp + fn)
        fpr = fp / max(1, fp + tn)
        j = tpr - fpr
        sweep.append({
            "threshold": round(float(t), 3),
            "tpr": round(tpr, 4),
            "fpr": round(fpr, 4),
            "j":   round(j, 4),
        })
        if j > best["j"]:
            best = {
                "threshold": round(float(t), 3),
                "tpr": round(tpr, 4),
                "fpr": round(fpr, 4),
                "j":   round(j, 4),
            }

    log.info(
        "Youden's J optimum: threshold=%.3f  TPR=%.3f  FPR=%.3f  J=%.3f",
        best["threshold"], best["tpr"], best["fpr"], best["j"],
    )

    return {
        "threshold":  best["threshold"],
        "tpr":        best["tpr"],
        "fpr":        best["fpr"],
        "youden_j":   best["j"],
        "n_aligned":  len(aligned_sims),
        "n_drifted":  len(drifted_sims),
        "aligned_distribution": {
            "mean": float(np.mean(aligned_sims)) if aligned_sims else 0.0,
            "std":  float(np.std(aligned_sims))  if aligned_sims else 0.0,
            "min":  float(min(aligned_sims))     if aligned_sims else 0.0,
            "max":  float(max(aligned_sims))     if aligned_sims else 0.0,
        },
        "drifted_distribution": {
            "mean": float(np.mean(drifted_sims)) if drifted_sims else 0.0,
            "std":  float(np.std(drifted_sims))  if drifted_sims else 0.0,
            "min":  float(min(drifted_sims))     if drifted_sims else 0.0,
            "max":  float(max(drifted_sims))     if drifted_sims else 0.0,
        },
        "sweep": sweep,
        "_aligned_sims": aligned_sims,   # for plotting
        "_drifted_sims": drifted_sims,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Plot
# ──────────────────────────────────────────────────────────────────────────────

def plot_histogram(result: dict, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    bins = np.linspace(0, 1, 41)

    aligned = result["_aligned_sims"]
    drifted = result["_drifted_sims"]

    ax.hist(aligned, bins=bins, alpha=0.6, color="#16a085",
            label=f"aligned (n={len(aligned)})", edgecolor="black", linewidth=0.5)
    ax.hist(drifted, bins=bins, alpha=0.6, color="#c0392b",
            label=f"drifted (n={len(drifted)})", edgecolor="black", linewidth=0.5)

    ax.axvline(result["threshold"], color="black", linestyle="--", linewidth=2,
               label=f"Youden J optimum t={result['threshold']:.3f}")

    ax.set_xlabel("cosine similarity (intent ⇄ action)")
    ax.set_ylabel("count")
    ax.set_title(
        f"COMPASS calibration distribution\n"
        f"TPR={result['tpr']:.3f}  FPR={result['fpr']:.3f}  J={result['youden_j']:.3f}"
    )
    ax.set_xlim(0, 1)
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    log.info("wrote histogram to %s", out_path)


# ──────────────────────────────────────────────────────────────────────────────
# Config update
# ──────────────────────────────────────────────────────────────────────────────

def update_config_in_place(config_path: Path, threshold: float) -> None:
    text = config_path.read_text()
    cfg = yaml.safe_load(text)
    old = cfg.get("thresholds", {}).get("compass_drift")
    cfg["thresholds"]["compass_drift"] = float(threshold)

    config_path.write_text(yaml.dump(cfg, sort_keys=False, default_flow_style=False))
    log.info(
        "updated %s: thresholds.compass_drift %s → %.3f",
        config_path, old, threshold,
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Calibrate COMPASS threshold via Youden's J")
    p.add_argument("--corpus", default="kavach_corpus_v1.json",
                   help="path to merged corpus JSON")
    p.add_argument("--model", default="BAAI/bge-base-en-v1.5",
                   help="SentenceTransformer model id")
    p.add_argument("--output", default="compass_calibration.json",
                   help="output JSON path")
    p.add_argument("--histogram", default="compass_histogram.png",
                   help="output histogram path")
    p.add_argument("--config", default="parliament/config.yaml",
                   help="parliament config to update")
    p.add_argument("--no-update-config", dest="update_config",
                   action="store_false", default=True,
                   help="skip writing the threshold back to config.yaml")
    args = p.parse_args()

    result = calibrate(Path(args.corpus), args.model)
    plot_histogram(result, Path(args.histogram))

    # Strip the raw sims from the JSON output (they're in the histogram)
    result_clean = {k: v for k, v in result.items()
                    if not k.startswith("_")}
    Path(args.output).write_text(json.dumps(result_clean, indent=2))
    log.info("wrote calibration result to %s", args.output)

    if args.update_config:
        update_config_in_place(Path(args.config), result["threshold"])
    else:
        log.info("skipping config update (--no-update-config). Set "
                 "thresholds.compass_drift to %.3f manually.", result["threshold"])


if __name__ == "__main__":
    main()
