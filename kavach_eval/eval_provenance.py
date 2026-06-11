"""
eval_provenance.py — provenance correctness + tamper-evidence evaluation
========================================================================

Two evaluations for the paper's provenance contribution (Axis B):

  1. COVERAGE & CORRECTNESS: over the live corpora, what fraction of patterns
     carry a parseable technique ID (pattern-tagged vs minister-default), and
     does each tagged source resolve to a technique present in the taxonomy
     table? This is the "provenance correctness" number for the paper.

  2. TAMPER-EVIDENCE: the provenance chain is folded into the SHA-256 ledger
     hash. We prove that editing ONLY the provenance of a historical row (e.g.
     downgrading a credential-access BLOCK to look like a benign read) breaks
     the chain at that row — i.e. the *grounding* is tamper-evident, not just
     the verdict text.

Run:
    python kavach_eval/eval_provenance.py                 # both evals
    python kavach_eval/eval_provenance.py --corpus-dir corpus_v2
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from parliament import provenance as prov


def eval_coverage(corpus_dir: str) -> None:
    files = glob.glob(os.path.join(corpus_dir, "*.json"))
    total = tagged = resolved = 0
    by_stage: Counter = Counter()
    unmapped_ids: set[str] = set()

    for f in files:
        try:
            data = json.load(open(f))
        except Exception:
            continue
        patterns = data.get("patterns", []) if isinstance(data, dict) else []
        minister = data.get("patterns", [{}])[0].get("minister") if patterns else None
        # minister often on the file-level dict
        minister = data.get("minister", minister) if isinstance(data, dict) else minister
        for pat in patterns:
            total += 1
            src = pat.get("source")
            p = prov.resolve(src, minister or "")
            if p.provenance_basis.startswith("pattern-tagged"):
                tagged += 1
            if p.technique_id not in ("UNMAPPED",) and p.tactic != "unknown":
                resolved += 1
                by_stage[p.stage] += 1
            elif src:
                m = prov._ID_RE.search(src)
                if m:
                    unmapped_ids.add(m.group(1))

    print("=" * 70)
    print(f"PROVENANCE COVERAGE  ({len(files)} corpus files, {total} patterns)")
    print("=" * 70)
    if total:
        print(f"  pattern-tagged (precise):  {tagged:4d}  ({100*tagged/total:.1f}%)")
        print(f"  resolved to taxonomy:      {resolved:4d}  ({100*resolved/total:.1f}%)")
        print(f"  → fallback to default:     {total - tagged:4d}  ({100*(total-tagged)/total:.1f}%)")
    print("\n  stage distribution of tagged patterns:")
    for stage in prov.STAGE_ORDER:
        if by_stage.get(stage):
            print(f"    {stage:24} {by_stage[stage]:4d}")
    if unmapped_ids:
        print(f"\n  ⚠ technique IDs in corpus but NOT in taxonomy table (add them):")
        for tid in sorted(unmapped_ids):
            print(f"    {tid}")
    print()


# ── Tamper-evidence: minimal standalone chain mirroring server.py ────────────
GENESIS = "0" * 64
_HASH_FIELDS = ("ts", "session_id", "correlation_id", "stage", "input_text",
                "verdict", "decided_by", "confidence", "reason",
                "ministers_json", "compass_sim", "traj_risk", "latency_ms",
                "provenance_json")


def _eh(prev: str, row: dict) -> str:
    # Mirror server.py: provenance_json enters the hash only when present.
    fields = [f for f in _HASH_FIELDS if f != "provenance_json"]
    if row.get("provenance_json") is not None:
        fields.append("provenance_json")
    canon = json.dumps({k: row[k] for k in fields},
                       sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev + canon).encode()).hexdigest()


def eval_tamper() -> None:
    db = tempfile.mktemp(suffix=".db")
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE votes(id INTEGER PRIMARY KEY AUTOINCREMENT, "
              + ", ".join(f"{f} TEXT" for f in _HASH_FIELDS)
              + ", prev_hash TEXT, entry_hash TEXT)")

    def log(verdict, prov_chain):
        prev = (c.execute("SELECT entry_hash FROM votes ORDER BY id DESC LIMIT 1")
                .fetchone() or [None])[0] or GENESIS
        row = {f: "" for f in _HASH_FIELDS}
        row.update(ts=datetime.now(timezone.utc).isoformat(), verdict=verdict,
                   provenance_json=json.dumps(prov_chain, sort_keys=True))
        eh = _eh(prev, row)
        c.execute(f"INSERT INTO votes ({','.join(_HASH_FIELDS)},prev_hash,entry_hash) "
                  f"VALUES ({','.join('?' for _ in _HASH_FIELDS)},?,?)",
                  (*[row[f] for f in _HASH_FIELDS], prev, eh))
        c.commit()

    def verify():
        rows = c.execute(f"SELECT id,{','.join(_HASH_FIELDS)},prev_hash,entry_hash "
                         "FROM votes ORDER BY id ASC").fetchall()
        exp = GENESIS
        for r in rows:
            row = dict(zip(_HASH_FIELDS, r[1:1+len(_HASH_FIELDS)]))
            prev, entry = r[-2], r[-1]
            if prev != exp or _eh(prev, row) != entry:
                return {"intact": False, "tampered_at_id": r[0]}
            exp = entry
        return {"intact": True, "entries": len(rows)}

    # Honest log: a credential-access BLOCK grounded in T1552.001.
    log("BLOCK", prov.resolve("MITRE ATT&CK T1552.001", "VAULT").to_dict())
    log("ALLOW", prov.resolve(None, "EXECUTOR").to_dict())
    log("BLOCK", prov.resolve("MITRE ATLAS AML.T0086", "CHANNEL").to_dict())
    before = verify()

    # Attack: tamper ONLY the provenance of row 1 — relabel the credential
    # theft as benign discovery to hide the real technique from an auditor.
    forged = prov.resolve(None, "EXECUTOR").to_dict()
    c.execute("UPDATE votes SET provenance_json=? WHERE id=1",
              (json.dumps(forged, sort_keys=True),))
    c.commit()
    after = verify()

    print("=" * 70)
    print("PROVENANCE TAMPER-EVIDENCE")
    print("=" * 70)
    print(f"  3 honest writes:                         {before}")
    print(f"  after forging ONLY row-1 provenance:     {after}")
    assert before["intact"] and not after["intact"] and after["tampered_at_id"] == 1
    print("  ✓ editing the technique grounding alone breaks the chain at id=1")
    print("    → the taxonomy grounding is tamper-evident, not just the verdict\n")
    os.remove(db)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", default="corpus_v2")
    args = ap.parse_args()
    eval_coverage(args.corpus_dir)
    eval_tamper()
