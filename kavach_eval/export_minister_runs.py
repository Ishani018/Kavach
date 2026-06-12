#!/usr/bin/env python3
"""
export_minister_runs.py — InjecAgent results.csv  ->  minister_runs.jsonl
=========================================================================

The §5 frontier analysis (veto / Bayesian / hybrid aggregator comparison under
adaptive corruption) reads `minister_runs.jsonl` in the HANDOFF_SCHEMA format
(kavach_eval/HANDOFF_SCHEMA.md). Nothing else produces that file from a real run.

`injecagent_runner.py` already writes a per-case `results.csv` that contains
EVERYTHING the schema needs — the four per-minister verdict+similarity columns,
the test_kind (attack/benign) label, compass_sim, and latency. This script joins
those columns into the one-line-per-action JSONL the offline pipeline consumes.

IMPORTANT (why this exists): the live SQLite ledger does NOT store a ground-truth
label, so a ledger -> jsonl dump cannot be scored. The benchmark CSV is the only
source that carries the attack/benign label alongside the minister votes. Run
this on the Dell BEFORE tearing down, and commit minister_runs.jsonl.

Usage:
    python kavach_eval/export_minister_runs.py \
        --inputs benchmarks/results_v2/injecagent_dell/results.csv \
        --model gemma-4-27b \
        --out minister_runs.jsonl

    # multiple CSVs (e.g. default + gate-floor ablations) concatenate:
    python kavach_eval/export_minister_runs.py \
        --inputs a/results.csv b/results.csv --model gemma-4-27b --out runs.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

MINISTERS = ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"]


def _vote_from_verdict(v: str) -> str:
    """Map a per-minister verdict cell to a schema vote.

    The runner writes "" for a minister that was not routed/activated; the schema
    represents that as ABSTAIN (neutral, ignored by the aggregator).
    """
    v = (v or "").strip().upper()
    if v in ("ALLOW", "ESCALATE", "BLOCK"):
        return v
    return "ABSTAIN"


def _float(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def rows_from_csv(path: Path, model: str, benchmark: str):
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            # Skip rows where the parliament errored — no usable votes.
            if (row.get("verdict") or "").strip().upper() == "ERROR":
                continue

            test_kind = (row.get("test_kind") or "").strip().lower()
            is_attack = test_kind == "attack"
            ground_truth = "BLOCK" if is_attack else "ALLOW"

            votes = []
            for m in MINISTERS:
                key = m.lower()
                vote = _vote_from_verdict(row.get(f"{key}_verdict"))
                entry = {
                    "minister":   m,
                    "vote":       vote,
                    "confidence": round(_float(row.get(f"{key}_sim")), 4),
                }
                matched = (row.get(f"{key}_matched") or "").strip()
                if matched:
                    entry["matched_id"] = matched
                votes.append(entry)

            obj = {
                "action_id":   row.get("case_id") or f"{path.stem}_{i:05d}",
                "benchmark":   benchmark,
                "is_attack":   is_attack,
                "ground_truth": ground_truth,
                "action":      {"raw": row.get("matched_pattern", "") or ""},
                "minister_votes": votes,
                "speaker_verdict": (row.get("verdict") or "").strip().upper(),
                "model":       model,
            }
            # Optional enrichment columns — included only when present/non-empty.
            if row.get("category"):
                obj["category"] = row["category"]
            cs = row.get("compass_sim")
            if cs not in (None, "", "None"):
                obj["compass_sim"] = round(_float(cs), 4)
            lat = row.get("latency_ms")
            if lat not in (None, "", "None"):
                obj["minister_votes_latency_ms"] = round(_float(lat), 2)
            yield obj


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--inputs", nargs="+", required=True,
                    help="one or more InjecAgent-format results.csv files")
    ap.add_argument("--out", default="minister_runs.jsonl",
                    help="output JSONL path (default: %(default)s)")
    ap.add_argument("--model", default="unknown",
                    help="agent backbone used for the run (e.g. gemma-4-27b)")
    ap.add_argument("--benchmark", default="injecagent",
                    help="benchmark tag for every row (default: %(default)s)")
    args = ap.parse_args()

    n = 0
    n_attack = 0
    n_full = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for csv_path in args.inputs:
            p = Path(csv_path)
            if not p.exists():
                print(f"[export] WARN missing input: {p}", file=sys.stderr)
                continue
            for obj in rows_from_csv(p, args.model, args.benchmark):
                out.write(json.dumps(obj) + "\n")
                n += 1
                n_attack += obj["is_attack"]
                # "full" = all four ministers present (ABSTAIN counts as present)
                if len(obj["minister_votes"]) == 4:
                    n_full += 1

    # Built-in sanity summary — read this before tearing down the Dell.
    print(f"[export] wrote {n} actions to {args.out}")
    print(f"[export]   attacks={n_attack}  benign={n - n_attack}")
    print(f"[export]   rows with all 4 minister votes: {n_full}/{n}")
    if n == 0:
        print("[export] ERROR: no rows written — check the input CSV path/format.",
              file=sys.stderr)
        sys.exit(1)
    if n_full != n:
        print("[export] WARN: some rows are missing minister votes — inspect the CSV.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
