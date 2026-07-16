#!/usr/bin/env python3
"""
navigator_channel_regression_check.py
=======================================

Post-Phase-1 regression spot-check: GmailSendEmail is now covered by BOTH
CHANNEL's taint-chain BLOCK and the new NAVIGATOR tier floor's ESCALATE.
Confirms this dual-coverage doesn't downgrade or otherwise change any of
the 29 real CHANNEL-BLOCK-on-GmailSendEmail cases from the 100-case
forced-format run (kavach-rearch commit 466c9c9).

Replays each case's FULL prior turn sequence (all calls in order, same
session_id) so CHANNEL's session-level taint tracker sees the same
source-read-then-send context it saw originally -- dispatching the send
alone would not reproduce the taint state.
"""
import json
from pathlib import Path

import requests

KAVACH_URL = "http://127.0.0.1:8088"
FORCED_RUN = Path("benchmarks/results_v2/injecagent_100case_forced.jsonl")


def dispatch(tool: str, args: dict, session_id: str) -> dict:
    text = f"tool:{tool} args:{json.dumps(args, default=str)}"
    r = requests.post(
        f"{KAVACH_URL}/hook/parliament",
        json={"text": text, "session_id": session_id, "context": {}},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def main():
    cases = []
    with open(FORCED_RUN, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            for t in rec["turns"]:
                for c in t.get("calls", []):
                    if c.get("parsed_tool_name") == "GmailSendEmail":
                        v = c.get("kavach_verdict") or {}
                        decided_by = (v.get("speaker") or {}).get("decided_by")
                        if v.get("verdict") == "BLOCK" and decided_by == "CHANNEL":
                            # collect the FULL ordered call sequence for this case
                            calls_seq = []
                            for t2 in rec["turns"]:
                                for c2 in t2.get("calls", []):
                                    calls_seq.append((c2.get("parsed_tool_name"), c2.get("parsed_args")))
                            cases.append({"case_id": rec["case_id"], "calls": calls_seq})
                            break  # one match per case is enough

    print(f"Found {len(cases)} cases with original CHANNEL BLOCK on GmailSendEmail")

    results = []
    for case in cases:
        session_id = f"regcheck-{case['case_id']}"
        last_verdict = None
        for tool, args in case["calls"]:
            v = dispatch(tool, args or {}, session_id=session_id)
            if tool == "GmailSendEmail":
                last_verdict = v

        speaker = (last_verdict or {}).get("speaker", {})
        navigator = (last_verdict or {}).get("ministers", {}).get("NAVIGATOR", {})
        channel = (last_verdict or {}).get("ministers", {}).get("CHANNEL", {})
        results.append({
            "case_id": case["case_id"],
            "verdict": (last_verdict or {}).get("verdict"),
            "decided_by": speaker.get("decided_by"),
            "channel_verdict": channel.get("verdict"),
            "channel_matched_id": channel.get("matched_id"),
            "navigator_verdict": navigator.get("verdict"),
            "navigator_matched_id": navigator.get("matched_id"),
        })
        print(f"  {case['case_id']:15s} verdict={results[-1]['verdict']:10s} decided_by={results[-1]['decided_by']:12s} "
              f"CHANNEL={results[-1]['channel_verdict']:8s} NAVIGATOR={results[-1]['navigator_verdict']}")

    n_total = len(results)
    n_still_block = sum(1 for r in results if r["verdict"] == "BLOCK")
    n_still_channel = sum(1 for r in results if r["decided_by"] == "CHANNEL")
    n_regressed = sum(1 for r in results if r["verdict"] != "BLOCK" or r["decided_by"] != "CHANNEL")

    out = {
        "n_total": n_total,
        "n_still_block": n_still_block,
        "n_still_decided_by_channel": n_still_channel,
        "n_regressed": n_regressed,
        "results": results,
    }
    out_path = Path("benchmarks/results_v2/navigator_channel_regression_check.json")
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")
    print(f"still BLOCK: {n_still_block}/{n_total}, still decided_by=CHANNEL: {n_still_channel}/{n_total}, regressed: {n_regressed}/{n_total}")


if __name__ == "__main__":
    main()
