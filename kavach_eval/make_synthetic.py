"""
make_synthetic.py — generate a realistic minister_runs.jsonl for testing
the eval harness WITHOUT the Dell. Lets us verify the whole pipeline and
also stress-test the Speaker under known conditions.

Knobs:
  --rho        : how correlated the Ministers' errors are (0=independent, 1=identical)
  --skill      : base per-Minister accuracy (0.5=coin flip, 0.9=strong)
  --miscalib   : how badly confidence is inflated (0=perfect, 0.3=overconfident)
  --n          : number of actions
  --attack-rate: fraction that are attacks (ground_truth=BLOCK)

Because we KNOW the true rho and calibration we injected, we can check the
harness recovers them correctly.
"""

import json
import random
import argparse
from datetime import datetime, timezone

MINISTERS = ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"]


def gen(n, rho, skill, miscalib, attack_rate, seed=42):
    random.seed(seed)
    runs = []
    for i in range(n):
        is_attack = random.random() < attack_rate
        gt = "BLOCK" if is_attack else "ALLOW"

        # Shared "difficulty" signal drives correlation: a common latent error
        # term shared across Ministers with weight rho.
        common_error = random.random() < (1 - skill)

        votes = []
        for m in MINISTERS:
            # Each Minister errs if the shared error fires (weight rho) OR its
            # own independent error fires (weight 1-rho).
            indep_error = random.random() < (1 - skill)
            errs = (random.random() < rho and common_error) or \
                   (random.random() < (1 - rho) and indep_error)

            if errs:
                vote = "ALLOW" if gt == "BLOCK" else "BLOCK"
            else:
                vote = gt

            # Some Ministers abstain on hard cases
            if random.random() < 0.08:
                vote = "ABSTAIN"
                conf = 0.5
            else:
                # Confidence: high when correct, but inflated by miscalib
                base = random.uniform(0.7, 0.95) if not errs else random.uniform(0.55, 0.8)
                conf = min(0.99, base + miscalib)

            votes.append({
                "minister": m,
                "vote": vote,
                "confidence": round(conf, 3),
                "reason": f"synthetic {'attack' if is_attack else 'benign'} judgment",
                "latency_ms": random.randint(150, 320),
            })

        runs.append({
            "action_id": f"synth_{i:04d}",
            "benchmark": "synthetic",
            "is_attack": is_attack,
            "ground_truth": gt,
            "action": {"tool": "send_money" if is_attack else "read_file",
                       "raw": f"action_{i}"},
            "minister_votes": votes,
            "model": "synthetic-gemma-4-27b",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    return runs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--rho", type=float, default=0.4)
    ap.add_argument("--skill", type=float, default=0.82)
    ap.add_argument("--miscalib", type=float, default=0.1)
    ap.add_argument("--attack-rate", type=float, default=0.35)
    ap.add_argument("--out", default="minister_runs.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    runs = gen(a.n, a.rho, a.skill, a.miscalib, a.attack_rate, a.seed)
    with open(a.out, "w") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(runs)} runs to {a.out}")
    print(f"  injected rho={a.rho}, skill={a.skill}, miscalib={a.miscalib}, "
          f"attack_rate={a.attack_rate}")
    print(f"  -> harness should recover rho near {a.rho}")
