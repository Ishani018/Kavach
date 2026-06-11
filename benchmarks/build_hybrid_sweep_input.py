#!/usr/bin/env python3
"""
build_hybrid_sweep_input.py
===========================

Build a combined attack+benign results CSV (with per-minister sim columns)
scored through the CURRENT hybrid parliament server, so threshold_sweep.py can
be re-run on the post-hybrid corpus.

SMALL-N: uses the local InjecAgent slices (attacker_cases_dh + _ds = 62 attacks)
and the benign user_cases (17). This is ~79 cases vs the ~1116 the original
results_v1 sweep used — directionally informative, NOT a same-N replacement for
the Dell large-N sweep. Output filenames are tagged `_smalln`.

Emits the columns threshold_sweep.py reads: test_kind + <minister>_sim.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

MINISTERS = ["executor", "vault", "channel", "navigator"]


def call(url: str, text: str, sid: str, timeout: float):
    payload = json.dumps({"text": text, "session_id": sid}).encode()
    req = urllib.request.Request(f"{url}/hook/parliament", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def row_from(resp, case_id, test_kind, category):
    base = {"case_id": case_id, "test_kind": test_kind, "category": category,
            "verdict": resp.get("verdict", "ERROR"),
            "decided_by": resp.get("speaker", {}).get("decided_by", "")}
    mins = resp.get("ministers", {}) or {}
    for m in MINISTERS:
        d = mins.get(m.upper(), {}) or {}
        base[f"{m}_sim"] = d.get("confidence", 0.0)
        base[f"{m}_verdict"] = d.get("verdict", "")
    return base


def load_attacks(paths):
    out = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            text = item.get("Attacker Instruction") or item.get("attacker_instruction") or ""
            out.append((text, item.get("Attack Type") or "attack"))
    return out


def load_benign(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        text = item.get("User Instruction") or ""
        out.append((text, item.get("Level") or "benign"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parliament-url", default="http://127.0.0.1:8088")
    ap.add_argument("--attacks", nargs="+",
                    default=["benchmarks/data/attacker_cases_dh.jsonl",
                             "benchmarks/data/attacker_cases_ds.jsonl"])
    ap.add_argument("--benign", default="benchmarks/data/user_cases.jsonl")
    ap.add_argument("--out", default="benchmarks/results_v2/results_hybrid_smalln.csv")
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args()

    attacks = load_attacks(args.attacks)
    benign = load_benign(args.benign)
    rows, errors = [], 0
    t0 = time.time()

    for i, (text, cat) in enumerate(attacks):
        resp, err = call(args.parliament_url, text, f"atk_{i:04d}", args.timeout)
        if resp is None:
            errors += 1
            continue
        rows.append(row_from(resp, f"atk_{i:04d}", "attack", cat))

    for i, (text, cat) in enumerate(benign):
        resp, err = call(args.parliament_url, text, f"ben_{i:04d}", args.timeout)
        if resp is None:
            errors += 1
            continue
        rows.append(row_from(resp, f"ben_{i:04d}", "benign", cat))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["case_id", "test_kind", "category", "verdict", "decided_by"]
    for m in MINISTERS:
        cols += [f"{m}_sim", f"{m}_verdict"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    n_atk = sum(1 for r in rows if r["test_kind"] == "attack")
    n_ben = sum(1 for r in rows if r["test_kind"] == "benign")
    print(f"wrote {out}: {len(rows)} rows ({n_atk} attack, {n_ben} benign), "
          f"errors={errors}, {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
