"""Phase 1 verdict-parity check for the M1 Max latency measurement.

Replays a deterministic subset through the live CPU-pinned server and
compares verdict + fired-minister set against the committed reference
(benchmarks/results_v2/_kavach_pb_*checkpoint.json, captured earlier this
session on the same machine but MPS-backed). Any divergence must halt the
latency measurement.

Subset (deterministic, per the measurement plan):
  - all 55 agent-shaped benign calls (benign_v0)
  - every 10th attack case by sorted case_id (~52 of 519)
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KAVACH_URL = "http://127.0.0.1:8088"
FIRED = ("BLOCK", "ESCALATE")
MIN = ("VAULT", "EXECUTOR", "CHANNEL", "NAVIGATOR")


def post(text, session_id):
    payload = json.dumps({"text": text, "session_id": session_id, "context": {}}).encode()
    req = urllib.request.Request(f"{KAVACH_URL}/hook/parliament", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fired_set(ministers_map):
    """Normalize the per-minister verdict map to the set of ministers that
    fired (BLOCK or ESCALATE). Reference stores {minister: verdict-string};
    live response stores {minister: {verdict: ...}}."""
    out = set()
    for m in MIN:
        v = ministers_map.get(m)
        if isinstance(v, dict):
            v = v.get("verdict")
        if v in FIRED:
            out.add(m)
    return out


def main():
    attack = json.loads((ROOT / "benchmarks/results_v2/_kavach_pb_attack_checkpoint.json").read_text())
    benign = json.loads((ROOT / "benchmarks/results_v2/_kavach_pb_benign_v0_agent_shaped_checkpoint.json").read_text())

    attack_sorted = sorted(attack.values(), key=lambda c: c["case_id"])
    attack_sample = attack_sorted[::10]
    benign_all = sorted(benign.values(), key=lambda c: c["case_id"])
    print(f"parity subset: {len(benign_all)} benign + {len(attack_sample)} attack (every 10th of {len(attack)})")

    mismatches = []
    n = 0
    for pop, cases in (("benign", benign_all), ("attack", attack_sample)):
        for c in cases:
            cid = c["case_id"]
            ref_verdict = c["verdict"]
            ref_fired = fired_set(c.get("ministers") or {})
            resp = post(c["call_text"], f"parity-{cid}")
            got_verdict = resp.get("verdict")
            got_fired = fired_set(resp.get("ministers") or {})
            n += 1
            if got_verdict != ref_verdict or got_fired != ref_fired:
                mismatches.append({
                    "case_id": cid, "pop": pop,
                    "ref_verdict": ref_verdict, "got_verdict": got_verdict,
                    "ref_fired": sorted(ref_fired), "got_fired": sorted(got_fired),
                })

    print(f"\nchecked {n} cases; {len(mismatches)} mismatch(es)")
    if mismatches:
        for m in mismatches:
            print(json.dumps(m))
        print("\nPARITY FAILED — do not proceed to latency.")
        sys.exit(1)
    print("PARITY OK — 100% identical verdict + fired-minister set.")


if __name__ == "__main__":
    main()
