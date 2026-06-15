"""
R2a coverage census (read-only, NOT committed).

For 25 LOLBINs: lexical_mentions in corpus + dense-only max sim vs the relevant
minister's ChromaDB collection. Dense sim only — no hybrid pipeline.

Canonical malicious examples are pulled at RUNTIME from atomic_index.json
(matched by tool substring). For tools the index lacks, a minimal example is
assembled in memory from harmless fragments — so no complete attack-command
string is ever stored as a literal in this file. This keeps the script (a)
antivirus-quiet and (b) automatically in sync with whatever the index contains.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import yaml
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

BGE = "BAAI/bge-base-en-v1.5"
PREFIX = "Represent this sentence for searching relevant passages: "
COLL = {"EXECUTOR": "kavach_executor", "VAULT": "kavach_vault",
        "CHANNEL": "kavach_channel", "NAVIGATOR": "kavach_navigator"}

# tool spec: (display, lexical_regex, index_match_substr, minister, fallback_intent)
# - lexical_regex : counted case-insensitively across corpus L1/L2/L3
# - index_match_substr : substring searched in atomic_index.json test commands
#                        (None => skip index, use fallback)
# - minister : domain of the malicious intent (which collection to query)
# - fallback_intent : a plain-English malicious-intent description assembled in
#                     memory if the index has no hit. NOT an executable command.
TOOLS = [
    ("certutil",          r"certutil",          "certutil",          "EXECUTOR",  "download and decode a remote payload via a signed system utility"),
    ("bitsadmin",         r"bitsadmin",         "bitsadmin",         "CHANNEL",   "transfer a remote file to disk using the background transfer service"),
    ("mshta",             r"mshta",             "mshta",             "EXECUTOR",  "execute a remote HTML application payload"),
    ("rundll32",          r"rundll32",          "rundll32",          "EXECUTOR",  "proxy-execute code through a signed DLL host"),
    ("regsvr32",          r"regsvr32",          "regsvr32",          "EXECUTOR",  "register and run a remote scriptlet through a signed binary"),
    ("wmic",              r"wmic",              "wmic",              "EXECUTOR",  "spawn a process remotely via the management instrumentation client"),
    ("cmstp",             r"cmstp",             "cmstp",             "EXECUTOR",  "execute a payload via a connection-manager profile installer"),
    ("IEX",               r"\bIEX\b",           None,                "EXECUTOR",  "evaluate a remotely downloaded script in the current shell"),
    ("Invoke-Expression", r"Invoke-Expression", "Invoke-Expression", "EXECUTOR",  "evaluate a remotely downloaded script in the current shell"),
    ("WebClient",         r"WebClient",         "WebClient",         "CHANNEL",   "fetch remote content over HTTP from a scripting runtime"),
    ("DownloadString",    r"DownloadString",    "DownloadString",    "CHANNEL",   "retrieve a remote script as a string over HTTP"),
    ("DownloadFile",      r"DownloadFile",      "DownloadFile",      "CHANNEL",   "save a remote file to disk over HTTP"),
    ("curl",              r"\bcurl\b",          "curl",              "CHANNEL",   "fetch a remote payload over HTTP to local disk"),
    ("wget",              r"\bwget\b",          "wget",              "CHANNEL",   "fetch a remote payload over HTTP to local disk"),
    ("nc",                r"\bnc\b",            None,                "CHANNEL",   "open a reverse shell to a remote host over a raw socket"),
    ("ncat",              r"\bncat\b",          "ncat",              "CHANNEL",   "open a reverse shell to a remote host over a raw socket"),
    ("socat",             r"\bsocat\b",         None,                "CHANNEL",   "relay a shell to a remote host over a raw socket"),
    ("ssh",               r"\bssh\b",           " ssh ",             "CHANNEL",   "open a reverse tunnel to an external host"),
    ("scp",               r"\bscp\b",           "scp",               "CHANNEL",   "copy a sensitive local file to a remote host"),
    ("rsync",             r"\brsync\b",         "rsync",             "CHANNEL",   "exfiltrate local files to a remote host"),
    ("python -c",         r"python\s+-c",       "python -c",         "EXECUTOR",  "run an inline interpreter one-liner to open a reverse shell"),
    ("perl -e",           r"perl\s+-e",         "perl -e",           "EXECUTOR",  "run an inline interpreter one-liner to open a reverse shell"),
    ("ruby -e",           r"ruby\s+-e",         None,                "EXECUTOR",  "run an inline interpreter one-liner to open a reverse shell"),
    ("php -r",            r"php\s+-r",          None,                "EXECUTOR",  "run an inline interpreter one-liner to open a reverse shell"),
    ("powershell -enc",   r"powershell\s+-enc", None,                "EXECUTOR",  "execute a base64-encoded command payload"),
]


def lexical_count(blob: str, pattern: str) -> int:
    return len(re.findall(pattern, blob, flags=re.IGNORECASE))


def load_index_examples(index: dict) -> dict[str, str]:
    """Map index_match_substr -> first matching test command (lowercased search)."""
    by_tool: dict[str, str] = {}
    for entry in index.values():
        for t in entry.get("tests", []):
            cmd = t.get("command", "") or ""
            low = cmd.lower()
            for _, _, substr, _, _ in TOOLS:
                if substr and substr.lower() in low and substr not in by_tool:
                    # store the command + its description for richer embedding context
                    desc = t.get("description", "") or ""
                    by_tool[substr] = (cmd + " " + desc).strip()
    return by_tool


def example_for(display, substr, minister, fallback, index_examples) -> str:
    """Return canonical example text for embedding. Prefer index; else assemble
    a description from fragments in memory (never a full command literal)."""
    if substr and substr in index_examples:
        return index_examples[substr]
    # fragment-assembled, intent-level (not an executable command string)
    return f"{display} used to {fallback}"


def main():
    corpus = json.load(open(_ROOT / "kavach_corpus_v1.json"))
    parts = []
    for m in COLL:
        for pat in corpus.get(m, {}).get("patterns", []):
            for lvl in ("L1_intent", "L2_mechanism", "L3_surface"):
                parts.append(pat.get(lvl, "") or "")
    blob = "\n".join(parts)

    cfg = yaml.safe_load((_ROOT / "parliament" / "config.yaml").read_text())
    per_min = cfg["thresholds"]["per_minister"]

    index = json.load(open(_ROOT / "kavach_eval" / "threat_intel" / "atomic_index.json"))
    index_examples = load_index_examples(index)

    model = SentenceTransformer(BGE)
    client = chromadb.PersistentClient(path=str(_ROOT / "parliament" / ".chroma_kavach"),
                                       settings=Settings(anonymized_telemetry=False))
    collections = {m: client.get_collection(name=c) for m, c in COLL.items()}

    rows = []
    for display, lex, substr, minister, fallback in TOOLS:
        mentions = lexical_count(blob, lex)
        example = example_for(display, substr, minister, fallback, index_examples)
        src = "index" if (substr and substr in index_examples) else "assembled"
        vec = model.encode(PREFIX + example, normalize_embeddings=True).tolist()
        res = collections[minister].query(query_embeddings=[vec], n_results=1,
                                          include=["distances", "metadatas"])
        dist = res["distances"][0][0] if res["distances"] and res["distances"][0] else 1.0
        dense = max(0.0, 1.0 - dist)
        meta = res["metadatas"][0][0] if res["metadatas"] and res["metadatas"][0] else {}
        nearest = meta.get("id") or meta.get("pattern_id") or meta.get("matched_id") or "?"
        th = per_min[minister]
        if mentions == 0 and dense >= th:
            risk = "HIGH"
        elif mentions < 3 and dense >= th:
            risk = "MEDIUM"
        else:
            risk = "LOW"
        rows.append((display, mentions, dense, nearest, minister, th, risk, src))

    print("\n| Tool | lexical_mentions | max_dense_sim | nearest_pattern_id | minister | threshold | evasion_risk | example_src |")
    print("|---|---|---|---|---|---|---|---|")
    for display, mentions, dense, nearest, minister, th, risk, src in rows:
        print(f"| {display} | {mentions} | {dense:.3f} | {nearest} | {minister} | {th} | {risk} | {src} |")

    n_high = sum(1 for r in rows if r[6] == "HIGH")
    n_med = sum(1 for r in rows if r[6] == "MEDIUM")
    print(f"\nHIGH={n_high}  MEDIUM={n_med}  LOW={len(rows)-n_high-n_med}  (of {len(rows)})")
    print(f"examples from index: {sum(1 for r in rows if r[7]=='index')}  assembled: {sum(1 for r in rows if r[7]=='assembled')}")


if __name__ == "__main__":
    main()
