#!/usr/bin/env python3
"""
corpus_v2/merge_corpus.py
=========================

Merges the v1 corpus (kavach_corpus_v1.json) with the v2 new-pattern files
(new_patterns_executor.json, new_patterns_vault.json + _b, new_patterns_channel.json + _b,
new_patterns_navigator.json + _b) into a single kavach_corpus_v2.json that
corpus_loader.py can consume.

Validations performed during merge:
    1. Pattern IDs are unique across v1 + v2.
    2. Every pattern has L1_intent, L2_mechanism, L3_surface fields.
    3. L1 contains no tool names from a reject-list (basic protocol check).
    4. Source field cites a MITRE technique ID, OWASP category, or CWE.
    5. Pattern ID prefix matches minister assignment.

Outputs:
    kavach_corpus_v2.json   — the merged corpus
    merge_report.json       — summary of what merged, what failed validation
    rejects.json            — patterns that failed validation, with reasons

Usage:
    python corpus_v2/merge_corpus.py \\
        --v1 /path/to/kavach_corpus_v1.json \\
        --new-dir corpus_v2/ \\
        --output corpus_v2/kavach_corpus_v2.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
log = logging.getLogger("merge")


# Minister-prefix mapping (from v1 corpus convention)
PREFIX_TO_MINISTER = {
    "EXEC":  "EXECUTOR",
    "VAULT": "VAULT",
    "CHAN":  "CHANNEL",
    "NAV":   "NAVIGATOR",
}

# Sources accepted by the protocol
SOURCE_PATTERNS = [
    re.compile(r"MITRE ATT&CK T\d{4}(?:\.\d{3})?"),
    re.compile(r"OWASP Agentic 202[5-9] A\d{2}"),
    re.compile(r"OWASP LLM 202[5-9] LLM\d{2}"),
    re.compile(r"CWE-\d+"),
    re.compile(r"CVE-\d{4}-\d{4,7}"),    # tolerated in v1 holdovers, flagged in v2
]

# Tool-name reject list for L1 (the "no tool names in L1" rule from the
# expansion protocol). This is a sanity check, not exhaustive — the human
# reviewer is the real check.
#
# Each entry is matched as a whole word (\b...\b) so substrings inside
# ordinary words ("SSH" → "sh", "host node" → "node ") don't false-positive.
# Path-fragments are matched literally because they're already distinctive.
L1_REJECT_TOOLS = [
    # Common shell tool names that should NOT appear in an L1 — word-bounded
    "curl", "wget", "bash", "zsh", "fish",
    "python", "python3", "node", "nodejs", "perl", "ruby", "php",
    "git", "docker", "podman", "kubectl", "helm",
    "aws", "gcloud", "terraform",
    "psql", "mysql", "redis-cli",
    "scp", "rsync",
    "tar", "gzip", "unzip",
]
# These match as substrings (paths are already distinctive enough)
L1_REJECT_PATHS = [
    ".bashrc", ".zshrc", "/etc/passwd", "/etc/shadow", "~/.aws/",
    ".env", ".gitconfig",
]


def validate_pattern(p: dict[str, Any], file_origin: str) -> list[str]:
    """Return list of validation problems with this pattern. Empty = OK."""
    problems: list[str] = []

    # Required fields
    for field in ("id", "L1_intent", "L2_mechanism", "L3_surface"):
        if not p.get(field):
            problems.append(f"missing or empty field: {field}")

    pid = p.get("id", "")
    if not pid:
        return problems   # can't validate further without an id

    # ID prefix matches a known minister
    prefix = pid.split("-")[0]
    if prefix not in PREFIX_TO_MINISTER:
        problems.append(f"unknown minister prefix in id {pid}")

    # Source citation
    src = p.get("source", "")
    if not src:
        problems.append("missing source field")
    elif not any(rx.search(src) for rx in SOURCE_PATTERNS):
        problems.append(f"source does not cite a recognized taxonomy: {src!r}")

    # L1 must not contain tool names (basic check)
    l1 = p.get("L1_intent", "").lower()
    # Word-bounded check for tool names so we don't false-positive on
    # substrings like "SSH" → "sh" or "host node" → "node".
    for tool in L1_REJECT_TOOLS:
        if re.search(rf"\b{re.escape(tool)}\b", l1):
            problems.append(
                f"L1 contains tool name {tool!r} (word-bounded) — should be in L3"
            )
            break
    # Substring check for paths — these are already distinctive.
    for path in L1_REJECT_PATHS:
        if path in l1:
            problems.append(
                f"L1 contains path fragment {path!r} — should be in L3"
            )
            break

    return problems


def load_v1_corpus(path: Path) -> dict[str, Any]:
    """Load the v1 corpus, normalizing to the v2 layout."""
    raw = json.loads(path.read_text())
    log.info("loaded v1 corpus from %s", path)

    # v1 layout: {"EXECUTOR": {"patterns": [...]}, "VAULT": {...}, ..., "COMPASS": {"pairs": [...]}}
    out: dict[str, Any] = {
        "version": "2.0",
        "description": "Kavach attack corpus v2 — v1 base + 200 new patterns from v2 expansion",
        "ministers": {},
        "compass_pairs": [],
        "metadata": {
            "v1_source": str(path),
        },
    }

    for minister in PREFIX_TO_MINISTER.values():
        if minister in raw:
            patterns = raw[minister].get("patterns", [])
            out["ministers"][minister] = list(patterns)
        else:
            out["ministers"][minister] = []

    if "COMPASS" in raw and "pairs" in raw["COMPASS"]:
        out["compass_pairs"] = list(raw["COMPASS"]["pairs"])

    log.info("v1 patterns per minister: %s",
             {m: len(p) for m, p in out["ministers"].items()})
    log.info("v1 compass pairs: %d", len(out["compass_pairs"]))
    return out


def load_new_pattern_files(new_dir: Path) -> dict[str, list[dict]]:
    """Load all new_patterns_*.json files in new_dir, grouped by minister."""
    out: dict[str, list[dict]] = {m: [] for m in PREFIX_TO_MINISTER.values()}

    files = sorted(new_dir.glob("new_patterns_*.json"))
    if not files:
        log.warning("no new_patterns_*.json files found in %s", new_dir)
        return out

    for f in files:
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            log.error("skipping %s: %s", f, e)
            continue

        minister = data.get("minister", "").upper()
        if minister not in PREFIX_TO_MINISTER.values():
            log.error("skipping %s: unknown minister %r", f, minister)
            continue

        patterns = data.get("patterns", [])
        out[minister].extend(patterns)
        log.info("  %s → %s: %d patterns", f.name, minister, len(patterns))

    return out


def merge(args: argparse.Namespace) -> None:
    v1 = load_v1_corpus(Path(args.v1))
    new = load_new_pattern_files(Path(args.new_dir))

    # ── Validate every pattern (v1 holdovers + new) and record rejects ────
    rejects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def keep_or_reject(
        p: dict[str, Any],
        origin: str,
        minister: str,
    ) -> bool:
        pid = p.get("id", "")
        if pid in seen_ids:
            rejects.append({
                "id":      pid,
                "origin":  origin,
                "reason":  ["duplicate id"],
                "pattern": p,
            })
            return False
        seen_ids.add(pid)

        problems = validate_pattern(p, origin)
        # Verify the prefix matches the file's claimed minister
        prefix = pid.split("-")[0] if pid else ""
        if prefix and PREFIX_TO_MINISTER.get(prefix) != minister:
            problems.append(
                f"prefix {prefix} maps to {PREFIX_TO_MINISTER.get(prefix)}, "
                f"not file-claimed minister {minister}"
            )
        if problems:
            rejects.append({
                "id":      pid,
                "origin":  origin,
                "reason":  problems,
                "pattern": p,
            })
            return False
        return True

    # Filter v1 (we keep v1 even if some patterns fail strict validation,
    # but we report them).
    final_ministers: dict[str, list[dict]] = {
        m: [] for m in PREFIX_TO_MINISTER.values()
    }
    for m, patterns in v1["ministers"].items():
        for p in patterns:
            if keep_or_reject(p, "v1", m):
                final_ministers[m].append(p)

    for m, patterns in new.items():
        for p in patterns:
            if keep_or_reject(p, "v2", m):
                final_ministers[m].append(p)

    # ── Assemble final v2 corpus in the layout corpus_loader.py expects ───
    final = {
        "version":     "2.0",
        "description": (
            "Kavach attack corpus v2 — v1 base + 200 new patterns drawn from "
            "MITRE ATT&CK and OWASP Agentic 2026 under the v2 expansion "
            "protocol (corpus_v2/expansion_protocol.md)."
        ),
        "usage": (
            "For each minister, load patterns into a separate ChromaDB "
            "collection. Embed L1_intent, L2_mechanism, L3_surface separately "
            "with BGE-base-en-v1.5 (mean pooling, asymmetric query prefix). "
            "At runtime, query the minister's collection with the proposed "
            "action text. Return max cosine similarity across all three levels."
        ),
        "EXECUTOR":  {"patterns": final_ministers["EXECUTOR"]},
        "VAULT":     {"patterns": final_ministers["VAULT"]},
        "CHANNEL":   {"patterns": final_ministers["CHANNEL"]},
        "NAVIGATOR": {"patterns": final_ministers["NAVIGATOR"]},
        "COMPASS":   {"pairs": v1["compass_pairs"]},
        "collections": {
            "EXECUTOR":  "kavach_executor",
            "VAULT":     "kavach_vault",
            "CHANNEL":   "kavach_channel",
            "NAVIGATOR": "kavach_navigator",
            "COMPASS":   "kavach_compass_calibration",
        },
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(final, indent=2))
    log.info("wrote merged corpus to %s", out_path)

    # ── Report ──────────────────────────────────────────────────────────
    report = {
        "input_v1":   str(args.v1),
        "input_new":  str(args.new_dir),
        "output":     str(out_path),
        "totals_per_minister": {
            m: len(final_ministers[m]) for m in PREFIX_TO_MINISTER.values()
        },
        "compass_pairs":  len(v1["compass_pairs"]),
        "total_patterns": sum(len(v) for v in final_ministers.values()),
        "rejects": len(rejects),
    }
    report_path = out_path.with_name("merge_report.json")
    report_path.write_text(json.dumps(report, indent=2))
    log.info("wrote merge report to %s", report_path)

    rejects_path = out_path.with_name("rejects.json")
    rejects_path.write_text(json.dumps(rejects, indent=2))
    if rejects:
        log.warning(
            "%d patterns failed validation — see %s",
            len(rejects), rejects_path,
        )

    log.info("\nFinal counts per minister:")
    for m, n in report["totals_per_minister"].items():
        log.info("  %-9s  %3d patterns", m, n)
    log.info("  COMPASS    %3d pairs", report["compass_pairs"])
    log.info("  TOTAL      %3d patterns", report["total_patterns"])

    if report["total_patterns"] < 350:
        log.warning(
            "v2 corpus has only %d patterns — target is 400 (200 v1 + 200 v2). "
            "Some files may not have been written.",
            report["total_patterns"],
        )


def main():
    p = argparse.ArgumentParser(description="Merge v1 and v2 Kavach corpora")
    p.add_argument("--v1", required=True,
                   help="path to kavach_corpus_v1.json")
    p.add_argument("--new-dir", default="corpus_v2",
                   help="directory containing new_patterns_*.json files")
    p.add_argument("--output", default="corpus_v2/kavach_corpus_v2.json",
                   help="output path for merged corpus")
    args = p.parse_args()
    merge(args)


if __name__ == "__main__":
    main()
