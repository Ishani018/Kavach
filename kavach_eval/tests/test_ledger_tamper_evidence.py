"""TEST 1 — Ledger tamper-evidence, using the REAL production hash-chain code.

Imports _entry_hash / GENESIS_HASH from parliament.server (the deployed logic)
and replays the exact verify walk. Uses a TEMP sqlite DB — never the production
ledger. No ChromaDB, no model, no server needed.
"""
import sys, sqlite3, tempfile, os, json
sys.path.insert(0, ".")

# Import the REAL production hash-chain primitives.
from parliament.server import _entry_hash, GENESIS_HASH

DB = tempfile.mktemp(suffix="_tamper_test.db")

CONTENT_COLS = ["ts","session_id","correlation_id","stage","input_text","verdict",
                "decided_by","confidence","reason","ministers_json","compass_sim",
                "traj_risk","latency_ms","provenance_json"]

def make_row(i, verdict):
    return {
        "ts": f"2026-07-05T10:00:0{i}Z", "session_id": "sess-1",
        "correlation_id": f"corr-{i}", "stage": "execution",
        "input_text": f"tool:exec args:{{cmd:cmd{i}}}", "verdict": verdict,
        "decided_by": "EXECUTOR", "confidence": 0.6+i*0.01,
        "reason": f"reason {i}", "ministers_json": json.dumps({"EXECUTOR": verdict}),
        "compass_sim": 0.4, "traj_risk": 0.1, "latency_ms": 78.0,
        "provenance_json": None,
    }

def append(conn, row):
    """Replay the REAL _log_vote chaining: prev = last entry_hash, entry = SHA(prev||row)."""
    last = conn.execute("SELECT entry_hash FROM votes ORDER BY id DESC LIMIT 1").fetchone()
    prev = last[0] if last and last[0] else GENESIS_HASH
    eh = _entry_hash(prev, row)
    conn.execute(
        f"INSERT INTO votes ({','.join(CONTENT_COLS)},prev_hash,entry_hash) "
        f"VALUES ({','.join(['?']*len(CONTENT_COLS))},?,?)",
        (*[row[c] for c in CONTENT_COLS], prev, eh),
    )
    conn.commit()

def verify(conn):
    """The REAL /ledger/verify walk, copied field-for-field from server.py:774."""
    rows = conn.execute(
        f"SELECT id,{','.join(CONTENT_COLS)},prev_hash,entry_hash FROM votes ORDER BY id ASC"
    ).fetchall()
    expected_prev = GENESIS_HASH; checked = 0; chain_started = False
    for r in rows:
        _id = r[0]
        colvals = dict(zip(CONTENT_COLS, r[1:1+len(CONTENT_COLS)]))
        stored_prev, stored_entry = r[-2], r[-1]
        if stored_entry is None:
            if chain_started:
                return {"intact": False, "entries_checked": checked, "tampered_at_id": _id,
                        "reason": "null hash after chain start"}
            expected_prev = GENESIS_HASH; continue
        chain_started = True
        recomputed = _entry_hash(stored_prev, colvals)
        if stored_prev != expected_prev or recomputed != stored_entry:
            return {"intact": False, "entries_checked": checked, "tampered_at_id": _id,
                    "reason": ("prev_hash discontinuity" if stored_prev != expected_prev
                               else "entry_hash mismatch — row content altered")}
        expected_prev = stored_entry; checked += 1
    return {"intact": True, "entries_checked": checked, "head_hash": expected_prev}

# ── Build a clean 5-entry chain ────────────────────────────────────────────────
conn = sqlite3.connect(DB)
# Match the PRODUCTION column affinity (server.py:273) so float fields round-trip
# as floats, not strings — otherwise the canonical hash differs by test artifact.
REAL_COLS = {"confidence", "compass_sim", "traj_risk", "latency_ms"}
coldefs = ", ".join(c + (" REAL" if c in REAL_COLS else " TEXT") for c in CONTENT_COLS)
conn.execute(f"CREATE TABLE votes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
             f"{coldefs}, prev_hash TEXT, entry_hash TEXT)")
for i, v in enumerate(["ALLOW","ESCALATE","BLOCK","ALLOW","BLOCK"]):
    append(conn, make_row(i, v))

print("=== TEST 1: LEDGER TAMPER-EVIDENCE ===")
print("Built a 5-entry hash chain through the real _entry_hash path.\n")

r = verify(conn)
print(f"[BEFORE tamper]  verify -> intact={r['intact']}  entries_checked={r['entries_checked']}")
assert r["intact"] is True, "clean chain should verify!"
print("  ✅ clean chain verifies (intact=True)\n")

# ── Tamper: flip entry id=3's verdict BLOCK -> ALLOW, directly in the DB row ────
print("Tampering: entry id=3 verdict BLOCK -> ALLOW (direct DB edit, hash NOT recomputed)")
conn.execute("UPDATE votes SET verdict='ALLOW' WHERE id=3")
conn.commit()

r2 = verify(conn)
print(f"[AFTER tamper]   verify -> intact={r2['intact']}  "
      f"tampered_at_id={r2.get('tampered_at_id')}  reason={r2.get('reason')}")
if r2["intact"] is False and r2.get("tampered_at_id") == 3:
    print("  ✅ TAMPER DETECTED at the exact edited row (id=3). Tamper-evidence WORKS.\n")
    ok = True
else:
    print("  🔴 TAMPER NOT DETECTED CORRECTLY — paper claim is FALSE.\n")
    ok = False

conn.close()
os.remove(DB)
print("scratch DB removed.")
print("RESULT:", "PASS ✅" if ok else "FAIL 🔴")
sys.exit(0 if ok else 1)
