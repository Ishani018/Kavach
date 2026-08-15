"""Phase 2 end-to-end live-HTTP latency measurement (M1 Max, CPU-pinned).

Sequential (no concurrency), client-side time.perf_counter around each
POST /hook/parliament. 20 untimed warm-up calls first. Decision path is
classified from existing response fields only (no server instrumentation):

  deterministic : short_circuited == true (a VAULT/EXECUTOR deterministic
                  rule matched and the embedding/retrieval path was skipped)
  cosine        : short_circuited == false and the deciding minister (or the
                  fired minister) used retrieval_mode == "hybrid"
  channel       : decided_by == CHANNEL via session taint/provenance
  allow-full    : ALLOW after the full embedding+retrieval path ran
                  (short_circuited == false, nothing fired)

Sample (deterministic, per plan): all 55 agent-shaped benign + every 5th
attack case by sorted case_id (~104 of 519).
"""
import csv
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "latency_percall.csv"
KAVACH_URL = "http://127.0.0.1:8088"
FIRED = ("BLOCK", "ESCALATE")
MIN = ("VAULT", "EXECUTOR", "CHANNEL", "NAVIGATOR")


def post(text, session_id):
    payload = json.dumps({"text": text, "session_id": session_id, "context": {}}).encode()
    req = urllib.request.Request(f"{KAVACH_URL}/hook/parliament", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read().decode())
        status = r.status
    dt_ms = (time.perf_counter() - t0) * 1000.0
    return body, dt_ms, status


def classify(resp):
    if resp.get("short_circuited"):
        return "deterministic"
    decided = (resp.get("speaker") or {}).get("decided_by")
    ministers = resp.get("ministers") or {}
    if decided == "CHANNEL":
        return "channel"
    # which minister fired, and via what retrieval mode?
    for m in MIN:
        md = ministers.get(m) or {}
        if md.get("verdict") in FIRED:
            if md.get("retrieval_mode") == "deterministic":
                return "deterministic"      # fired via rule but pipeline didn't short-circuit
            return "cosine"
    return "allow-full"                      # full path ran, nothing fired


def load_cases():
    attack = json.loads((ROOT / "benchmarks/results_v2/_kavach_pb_attack_checkpoint.json").read_text())
    benign = json.loads((ROOT / "benchmarks/results_v2/_kavach_pb_benign_v0_agent_shaped_checkpoint.json").read_text())
    attack_sample = sorted(attack.values(), key=lambda c: c["case_id"])[::5]
    benign_all = sorted(benign.values(), key=lambda c: c["case_id"])
    return benign_all, attack_sample


def main():
    benign_all, attack_sample = load_cases()
    print(f"warm-up: 20 untimed calls; then timed: {len(benign_all)} benign + {len(attack_sample)} attack")

    warm = (benign_all + attack_sample)
    for i in range(20):
        post(warm[i % len(warm)]["call_text"], f"warmup-{i}")

    rows = []
    for pop, cases in (("benign", benign_all), ("attack", attack_sample)):
        for c in cases:
            cid = c["case_id"]
            resp, dt_ms, status = post(c["call_text"], f"latency-{cid}")
            rows.append({
                "case_id": cid, "pop": pop, "verdict": resp.get("verdict"),
                "path": classify(resp), "latency_ms": round(dt_ms, 3),
                "status": status, "short_circuited": resp.get("short_circuited"),
                "server_latency_ms": resp.get("latency_ms"),
            })

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    non200 = [r for r in rows if r["status"] != 200]
    print(f"non-200 responses: {len(non200)}")


if __name__ == "__main__":
    main()
