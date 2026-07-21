#!/usr/bin/env python3
"""
test_full_pipeline.py
=====================

Run the FULL Kavach pipeline (all ministers: VAULT, EXECUTOR, CHANNEL,
NAVIGATOR via Chroma + COMPASS drift + Trajectory + Speaker) against the
AgentDojo ground truth dataset.

Requires a running Kavach parliament server on 127.0.0.1:8088.

For each case:
  1. POST /hook/seed_intent with the goal text
  2. POST /hook/parliament with each tool call text
  3. Record every minister's verdict

Output:
  - nav4/full_pipeline_predictions.jsonl
  - nav4/full_pipeline_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

_this = Path(__file__).resolve()
repo_root = _this.parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


KAVACH_URL = "http://127.0.0.1:8088"
TIMEOUT = 30.0


def _load_inputs(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def _post(endpoint: str, payload: dict) -> dict:
    url = f"{KAVACH_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def health_check(max_retries: int = 6, delay: float = 5.0) -> bool:
    for i in range(max_retries):
        try:
            req = urllib.request.Request(f"{KAVACH_URL}/health")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                d = json.loads(resp.read().decode("utf-8"))
                if d.get("status") == "ok":
                    print(f"Server healthy (attempt {i+1}): {d.get('retrieval_mode')}, "
                          f"ministers={d.get('ministers')}")
                    return True
        except Exception as e:
            print(f"Server not ready (attempt {i+1}/{max_retries}): {e}")
            time.sleep(delay)
    return False


def summarise_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    tp = sum(1 for r in results if r["truth"] == "ATTACK" and r["pred"] == "BLOCK")
    fn = sum(1 for r in results if r["truth"] == "ATTACK" and r["pred"] != "BLOCK")
    fp = sum(1 for r in results if r["truth"] == "BENIGN" and r["pred"] == "BLOCK")
    tn = sum(1 for r in results if r["truth"] == "BENIGN" and r["pred"] != "BLOCK")

    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "n_cases": n,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "recall": round(recall, 4),
        "fpr": round(fpr, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
    }


def main():
    ap = argparse.ArgumentParser(description="Full Kavach pipeline evaluation on AgentDojo dataset")
    ap.add_argument("--input", type=str,
                    default="benchmarks/results_v2/agentdojo_groundtruth_dataset.jsonl")
    ap.add_argument("--outdir", type=str,
                    default="benchmarks/results_v2/nav4")
    ap.add_argument("--url", type=str, default=KAVACH_URL)
    args = ap.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not health_check():
        print("ERROR: Server not reachable. Start Kavach server first:")
        print("  cd parliament && python -m uvicorn server:app --host 127.0.0.1 --port 8088")
        sys.exit(1)

    dataset = _load_inputs(input_path)

    rows: list[dict[str, Any]] = []

    for case_idx, case in enumerate(dataset):
        case_id = case.get("case_id", "?")
        goal = case.get("goal", "")
        turns = case.get("turns", [])
        labels = case.get("labels", {})
        is_attack = labels.get("is_attack_case", False)
        truth_label = "ATTACK" if is_attack else "BENIGN"

        # Generate a unique session per case
        session_id = f"fullpipe-{case_id}"

        # Step 1: Seed intent
        if goal:
            seed_resp = _post("/hook/seed_intent", {"text": goal, "session_id": session_id})
            if "error" in seed_resp:
                print(f"  ERROR seeding intent for {case_id}: {seed_resp['error']}")

        # Step 2: Score each tool call
        minister_results: list[dict[str, Any]] = []
        most_restrictive_pred = "ALLOW"
        most_restrictive_speaker = {}
        most_restrictive_verdict = "ALLOW"
        pred_confidence = 0.0
        compass_sim = None
        traj_risk = None
        retrieval_mode = None
        activated = []

        for s, tc in enumerate(turns):
            text = tc.get("text", "")
            if not text:
                text = f"tool:{tc.get('tool','')} args:{json.dumps(tc.get('args',{}), default=str, sort_keys=True)}"

            resp = _post("/hook/parliament", {
                "text": text,
                "session_id": session_id,
                "context": {},
            })

            if "error" in resp:
                print(f"  ERROR on {case_id} step {s}: {resp['error']}")
                continue

            verdict = resp.get("verdict", "ALLOW")
            speaker = resp.get("speaker", {})
            ministers = resp.get("ministers", {})
            this_compass_sim = resp.get("compass_sim")
            this_traj_risk = resp.get("traj_risk")
            this_retrieval = resp.get("retrieval_mode")
            this_activated = resp.get("activated", [])

            compass_sim = compass_sim if compass_sim is not None else this_compass_sim
            traj_risk = traj_risk if traj_risk is not None else this_traj_risk
            retrieval_mode = this_retrieval
            activated = this_activated

            # Track the most restrictive verdict
            verdict_rank = {"BLOCK": 2, "ESCALATE": 1, "ALLOW": 0}
            if verdict_rank.get(verdict, 0) > verdict_rank.get(most_restrictive_verdict, 0):
                most_restrictive_verdict = verdict
                most_restrictive_speaker = speaker
                most_restrictive_pred = "BLOCK" if verdict in ("BLOCK", "ESCALATE") else "ALLOW"
                pred_confidence = speaker.get("confidence", 0.0)

            minister_results.append({
                "step": s,
                "tool": tc.get("tool"),
                "verdict": verdict,
                "speaker": speaker,
                "ministers": ministers,
                "compass_sim": this_compass_sim,
                "traj_risk": this_traj_risk,
            })

        if not minister_results:
            most_restrictive_pred = "ALLOW"
            most_restrictive_verdict = "ALLOW"

        rows.append({
            "case_id": case_id,
            "truth": truth_label,
            "pred": most_restrictive_pred,
            "verdict": most_restrictive_verdict,
            "speaker": most_restrictive_speaker,
            "n_tool_calls": len(turns),
            "compass_sim": compass_sim,
            "traj_risk": traj_risk,
            "retrieval_mode": retrieval_mode,
            "activated": activated,
            "steps": minister_results,
        })

        if (case_idx + 1) % 10 == 0:
            print(f"  Processed {case_idx + 1}/{len(dataset)} cases...")

    # Compute metrics
    summary = summarise_results(rows)
    summary["n_attack"] = sum(1 for r in rows if r["truth"] == "ATTACK")
    summary["n_benign"] = sum(1 for r in rows if r["truth"] == "BENIGN")
    summary["input_dataset"] = str(input_path)

    # Write outputs
    pred_path = outdir / "full_pipeline_predictions.jsonl"
    with pred_path.open("w", encoding="utf-8") as f:
        for r in rows:
            # Strip steps from the main prediction file to keep it concise
            r_out = {k: v for k, v in r.items() if k != "steps"}
            f.write(json.dumps(r_out) + "\n")

    # Full verbose output
    verbose_path = outdir / "full_pipeline_verbose.jsonl"
    with verbose_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")

    summ_path = outdir / "full_pipeline_summary.json"
    summ_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nResults written to {outdir}/")
    print(f"Predictions: {pred_path}")
    print(f"Full output: {verbose_path}")


if __name__ == "__main__":
    main()
