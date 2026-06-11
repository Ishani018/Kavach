#!/usr/bin/env python3
"""
benign_gate_usercases.py
========================

Benign FPR gate for the laptop secondary config, using the *real* InjecAgent
benign user instructions in benchmarks/data/user_cases.jsonl.

The InjecAgent runner (injecagent_runner.py) is built around attack-paired cases
and has no benign-only mode, and user_cases.jsonl carries no `label`/`Modifed`
field (so the runner would mislabel them as attacks). This standalone probe
sends each benign "User Instruction" to the parliament as a normal action and
counts how often it is BLOCKed / ESCALATEd — i.e. the false-positive rate.

  FPR (block-only)        = blocks / N
  FPR (block-or-escalate) = (blocks + escalates) / N

Writes a single JSON summary (default: benign_results.json).

Usage:
  py benchmarks/benign_gate_usercases.py \
     --cases benchmarks/data/user_cases.jsonl \
     --parliament-url http://127.0.0.1:8088 \
     --out benchmarks/results_v2/laptop_qwen25_3b/benign_results.json
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def call_parliament(url: str, text: str, session_id: str, timeout: float) -> tuple[dict | None, float, str | None]:
    payload = json.dumps({"text": text, "session_id": session_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/hook/parliament",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode("utf-8"))
        return resp, (time.time() - t0) * 1000.0, None
    except Exception as e:  # noqa: BLE001 — surface any failure as a per-case error
        return None, (time.time() - t0) * 1000.0, str(e)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="benchmarks/data/user_cases.jsonl")
    p.add_argument("--parliament-url", default="http://127.0.0.1:8088")
    p.add_argument("--out", default="benchmarks/results_v2/laptop_qwen25_3b/benign_results.json")
    p.add_argument("--timeout", type=float, default=15.0)
    args = p.parse_args()

    cases = load_cases(Path(args.cases))
    rows: list[dict] = []
    blocks = escalates = allows = errors = 0
    latencies: list[float] = []

    for i, c in enumerate(cases):
        instr = c.get("User Instruction") or c.get("user_instruction") or ""
        resp, lat, err = call_parliament(args.parliament_url, instr, f"benigncase_{i:04d}", args.timeout)
        if err is not None or resp is None:
            errors += 1
            rows.append({"id": i, "verdict": "ERROR", "error": err, "instruction": instr[:160]})
            continue
        verdict = resp.get("verdict", "ERROR")
        latencies.append(lat)
        if verdict == "BLOCK":
            blocks += 1
        elif verdict == "ESCALATE":
            escalates += 1
        elif verdict == "ALLOW":
            allows += 1
        rows.append({
            "id": i,
            "verdict": verdict,
            "decided_by": resp.get("speaker", {}).get("decided_by", ""),
            "confidence": resp.get("speaker", {}).get("confidence", 0.0),
            "instruction": instr[:160],
        })

    n_scored = blocks + escalates + allows
    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        return round(latencies[min(len(latencies) - 1, int(p * len(latencies)))], 2)

    summary = {
        "config": "laptop secondary (qwen2.5:3b, CPU)",
        "cases_file": args.cases,
        "n": len(cases),
        "n_scored": n_scored,
        "errors": errors,
        "blocks": blocks,
        "escalates": escalates,
        "allows": allows,
        "fpr_block_only": round(blocks / n_scored, 4) if n_scored else None,
        "fpr_block_or_escalate": round((blocks + escalates) / n_scored, 4) if n_scored else None,
        "latency_ms": {"p50": pct(0.50), "p95": pct(0.95), "n": len(latencies)},
        "blocked_or_escalated": [r for r in rows if r.get("verdict") in ("BLOCK", "ESCALATE")],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "blocked_or_escalated"}, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
