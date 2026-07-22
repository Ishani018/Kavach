"""Naive keyword/regex blocklist baseline — a deliberately unsophisticated
floor for comparison, NOT a serious detector. See README.md in this directory
for the full disclaimer before reading these numbers.

This baseline represents "what a non-expert defender might block with basic
keyword matching over the raw tool-call text" — no AST parsing, no cosine
retrieval, no session state, no corpus, no tuning. It is scored against the
exact same Kavach-PB populations Kavach's own eval harness uses:

  - 519 attack cases   (benchmarks/results_v2/_kavach_pb_attack_checkpoint.json)
  - 793 BFCL benign    (benchmarks/results_v2/_kavach_pb_bfcl_general_purpose_checkpoint.json)
  - 55 agent-shaped benign (benchmarks/results_v2/_kavach_pb_benign_v0_agent_shaped_checkpoint.json)

Methodology discipline (see README): all patterns below were hand-written in
ONE pass, BEFORE this script was ever run against the data. It was run
exactly once. The results are reported as-is, including if they look bad or
weird. No pattern was added, removed, or reworded after seeing a score.

Each case's `call_text` field (format: `tool:<name> args:<json>`) is scanned,
case-insensitively, against every pattern. If any pattern matches, the case
is flagged BLOCK; otherwise ALLOW. This is a single binary decision — there
is no BLOCK/ESCALATE/ALLOW tri-state, no confidence score, no minister
attribution. That's the point: it's naive.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATTACK_FILE = ROOT / "benchmarks/results_v2/_kavach_pb_attack_checkpoint.json"
BFCL_FILE = ROOT / "benchmarks/results_v2/_kavach_pb_bfcl_general_purpose_checkpoint.json"
AGENT_BENIGN_FILE = ROOT / "benchmarks/results_v2/_kavach_pb_benign_v0_agent_shaped_checkpoint.json"

# ---------------------------------------------------------------------------
# The naive pattern list. ~20-30 hand-written keyword/regex rules covering
# the categories a non-expert would reach for first: remote fetch, dynamic
# code eval, permission changes, encoding/obfuscation, credential paths,
# reverse shells, and persistence. Written in one pass; not iterated on.
# ---------------------------------------------------------------------------
PATTERNS = [
    (r"\bcurl\b", "curl (remote fetch)"),
    (r"\bwget\b", "wget (remote fetch)"),
    (r"eval\(", "eval( — dynamic code execution"),
    (r"\bexec\(", "exec( — dynamic code execution"),
    (r"chmod\s+\+x", "chmod +x — making a file executable"),
    (r"base64\s+(-d|--decode)", "base64 decode — obfuscated payload"),
    (r"\.pem\b", ".pem file reference — key material"),
    (r"\.ssh\b", ".ssh directory reference — key material"),
    (r"id_rsa", "id_rsa — private key filename"),
    (r"authorized_keys", "authorized_keys — SSH persistence"),
    (r"/etc/passwd", "/etc/passwd — sensitive system file"),
    (r"/etc/shadow", "/etc/shadow — credential file"),
    (r"\bnc\s+-e\b", "nc -e — reverse shell"),
    (r"/dev/tcp/", "/dev/tcp/ — bash reverse shell"),
    (r"bash\s+-i\b", "bash -i — interactive reverse shell"),
    (r"crontab\s+-e", "crontab -e — persistence via cron"),
    (r"/etc/sudoers", "/etc/sudoers write — privilege persistence"),
    (r"rm\s+-rf\b", "rm -rf — destructive delete"),
    (r"powershell.*-enc(odedcommand)?\b", "PowerShell -EncodedCommand — obfuscated payload"),
    (r"invoke-webrequest", "Invoke-WebRequest — remote fetch (PowerShell)"),
    (r"certutil.*-urlcache", "certutil -urlcache — LOLBIN download"),
    (r"mimikatz", "mimikatz — credential dumping tool"),
    (r"net\s+user\s+.*\s+/add", "net user ... /add — account persistence"),
    (r"schtasks\b", "schtasks — scheduled-task persistence"),
    (r"wevtutil\s+cl\b", "wevtutil cl — clearing event logs"),
    (r"history\s+-c\b", "history -c — clearing shell history"),
    (r"python[0-9.]*\s+-c\b", "python -c — inline code execution"),
    (r"/proc/kmem|/dev/mem\b", "raw memory device access"),
    (r"iptables\s+-F\b", "iptables -F — flushing firewall rules"),
    (r"\.bash_profile|\.bashrc", "shell rc file — persistence via startup script"),
]

COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in PATTERNS]


def naive_flag(call_text: str):
    """Return (flagged: bool, matched_labels: list[str])."""
    hits = [label for regex, label in COMPILED if regex.search(call_text)]
    return (len(hits) > 0), hits


def load_cases(path: Path):
    data = json.loads(path.read_text())
    return sorted(data.values(), key=lambda c: c["case_id"])


def score_population(cases, is_attack: bool):
    flagged = 0
    details = []
    for c in cases:
        hit, labels = naive_flag(c["call_text"])
        if hit:
            flagged += 1
        details.append({"case_id": c["case_id"], "flagged": hit, "matched": labels})
    total = len(cases)
    rate = flagged / total if total else 0.0
    return {
        "total": total,
        "flagged": flagged,
        "rate": rate,
        "kind": "recall" if is_attack else "fpr",
        "details": details,
    }


def main():
    attack_cases = load_cases(ATTACK_FILE)
    bfcl_cases = load_cases(BFCL_FILE)
    agent_benign_cases = load_cases(AGENT_BENIGN_FILE)

    attack_result = score_population(attack_cases, is_attack=True)
    bfcl_result = score_population(bfcl_cases, is_attack=False)
    agent_benign_result = score_population(agent_benign_cases, is_attack=False)

    combined_benign_total = bfcl_result["total"] + agent_benign_result["total"]
    combined_benign_flagged = bfcl_result["flagged"] + agent_benign_result["flagged"]
    combined_benign_rate = (
        combined_benign_flagged / combined_benign_total if combined_benign_total else 0.0
    )

    print("=" * 72)
    print("NAIVE KEYWORD/REGEX BASELINE — single-author, unvalidated. See README.")
    print("=" * 72)
    print(f"Patterns: {len(PATTERNS)} (hand-written, one pass, not tuned on this data)")
    print()
    print(f"Attack recall (of {attack_result['total']}, AtomicRedTeam+GTFOBins):"
          f" {attack_result['flagged']}/{attack_result['total']}"
          f" ({attack_result['rate']*100:.1f}%)")
    print()
    print(f"FPR — BFCL general-purpose benign (of {bfcl_result['total']}):"
          f" {bfcl_result['flagged']}/{bfcl_result['total']}"
          f" ({bfcl_result['rate']*100:.1f}%)")
    print(f"FPR — agent-shaped benign_v0 (of {agent_benign_result['total']}):"
          f" {agent_benign_result['flagged']}/{agent_benign_result['total']}"
          f" ({agent_benign_result['rate']*100:.1f}%)")
    print(f"FPR — combined benign (of {combined_benign_total}):"
          f" {combined_benign_flagged}/{combined_benign_total}"
          f" ({combined_benign_rate*100:.1f}%)")
    print("=" * 72)

    out = {
        "n_patterns": len(PATTERNS),
        "attack_recall": attack_result,
        "bfcl_fpr": bfcl_result,
        "agent_benign_fpr": agent_benign_result,
        "combined_benign_fpr": {
            "total": combined_benign_total,
            "flagged": combined_benign_flagged,
            "rate": combined_benign_rate,
            "kind": "fpr",
        },
    }
    out_path = Path(__file__).resolve().parent / "naive_baseline_results.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote full per-case detail to {out_path}")


if __name__ == "__main__":
    main()
