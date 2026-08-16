"""benchmarks/atriumos_dispatch.py
===================================

Dispatches benchmarks/data/atriumos_scenarios.jsonl through the REAL, live
/hook/parliament pipeline (parliament/server.py) -- the same style of
dispatch used to generate cosine_primary_ablation_rerun_20260723.json and
_fresh_kavach_pb.json (sequential HTTP POSTs, unique session_id per
scenario, raw response recorded verbatim, scoring computed afterward from
the recorded fields -- no standalone/offline reimplementation of any
minister logic).

Multi-call scenarios (CHANNEL's read-then-send pairs) are dispatched
sequentially under the SAME session_id so channel_taint.py's per-session
taint state carries across the two calls, exactly like a real multi-turn
session. Single-call scenarios get their own unique session_id.

No account_email / user_instruction / tool_output context fields are sent,
matching the ACTUAL OpenClaw plugin's wire behavior (confirmed in the prior
audit: plugin/openclaw-plugin-kavach.ts never populates these fields) --
this dispatch measures what the deployed system actually does, not an
idealized configuration.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = ROOT / "benchmarks" / "data" / "atriumos_scenarios.jsonl"
KAVACH_URL = "http://127.0.0.1:8088"


def load_scenarios() -> list[dict]:
    rows = []
    with SCENARIOS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dispatch_call(text: str, session_id: str) -> dict:
    payload = {"text": text, "session_id": session_id, "context": {}}
    t0 = time.perf_counter()
    resp = requests.post(f"{KAVACH_URL}/hook/parliament", json=payload, timeout=30)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    resp.raise_for_status()
    body = resp.json()
    body["_client_latency_ms"] = round(latency_ms, 2)
    return body


def run() -> dict:
    scenarios = load_scenarios()
    assert len(scenarios) == 36, len(scenarios)

    results = []
    for i, sc in enumerate(scenarios, 1):
        session_id = f"atriumos-{sc['case_id']}"
        call_responses = []
        for call_text in sc["calls"]:
            resp = dispatch_call(call_text, session_id)
            call_responses.append({"call_text": call_text, "response": resp})
        # The scenario's own verdict is the LAST call's response (the
        # consequential action, for two-call CHANNEL scenarios; the only
        # call, for single-call scenarios) -- matches how a real deployment
        # would judge "was THIS action stopped."
        final = call_responses[-1]["response"]
        target = sc["target_minister"]
        target_result = (final.get("ministers") or {}).get(target)
        target_fired = bool(target_result and target_result.get("verdict") in ("BLOCK", "ESCALATE"))
        any_fired = final.get("verdict") in ("BLOCK", "ESCALATE")
        results.append({
            "case_id": sc["case_id"],
            "target_minister": target,
            "ground_truth": sc["ground_truth"],
            "description": sc["description"],
            "n_calls": len(sc["calls"]),
            "call_responses": call_responses,
            "final_verdict": final.get("verdict"),
            "final_decided_by": (final.get("speaker") or {}).get("decided_by"),
            "final_reason": (final.get("speaker") or {}).get("reason"),
            "target_minister_result": target_result,
            "target_minister_fired": target_fired,
            "any_minister_fired": any_fired,
            "retrieval_mode": final.get("retrieval_mode"),
            "latency_ms": final.get("latency_ms"),
        })
        print(f"[{i:2d}/36] {sc['case_id']:14s} target={target:10s} gt={sc['ground_truth']:6s} "
              f"-> verdict={final.get('verdict'):8s} target_fired={target_fired} any_fired={any_fired}")

    return {
        "benchmark": "AtriumOS generalization audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kavach_url": KAVACH_URL,
        "scenario_file": str(SCENARIOS_PATH.relative_to(ROOT)),
        "n_scenarios": len(results),
        "results": results,
    }


def main() -> int:
    # Confirm exactly one live server before trusting anything (same
    # discipline as eval/latency_m1max/README.md's duplicate-process guard).
    health = requests.get(f"{KAVACH_URL}/health", timeout=5).json()
    print("Server health:", json.dumps(health, indent=2))
    print()

    out = run()

    out_path = ROOT / "benchmarks" / "results_v2" / f"atriumos_generalization_audit_{datetime.now().strftime('%Y%m%d')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote raw results to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
