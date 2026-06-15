#!/usr/bin/env python3
"""
kavach_eval/corpus_agent/agent.py
=================================

Corpus-improvement agent (v0) — orchestrator.

Closed loop: the red-teamer finds evasions -> this agent proposes corpus
patterns to cover them -> the anti-poisoning gate validates each proposal ->
survivors are STAGED for human review. Optionally estimates gap closure.

It NEVER writes to kavach_corpus_v1.json or anything under parliament/. The
staging file is the only output that touches "corpus" data, and it is clearly
marked human-review-required.

Usage:
    python kavach_eval/corpus_agent/agent.py \
        --evasion-report kavach_eval/evasion_results/evasion_report_20260614T200623Z.json \
        --minister CHANNEL \
        --model qwen2.5:3b \
        --measure-closure

Defaults: newest evasion_report in evasion_results/, minister CHANNEL,
model qwen2.5:3b.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from kavach_eval.corpus_agent.proposer import PatternProposer
from kavach_eval.corpus_agent.validator import PatternValidator
from kavach_eval.corpus_agent.staging import write_staging

log = logging.getLogger("kavach.corpus_agent")

CORPUS_PATH   = _REPO_ROOT / "kavach_corpus_v1.json"
CONFIG_PATH   = _REPO_ROOT / "parliament" / "config.yaml"
EVASION_DIR   = _REPO_ROOT / "kavach_eval" / "evasion_results"
BENIGN_PROBE  = Path(__file__).resolve().parent / "benign_probe.json"

MINISTER_ID_PREFIX = {"EXECUTOR": "EXEC", "VAULT": "VAULT",
                      "CHANNEL": "CHAN", "NAVIGATOR": "NAV"}


def _load_thresholds() -> dict[str, float]:
    """Per-minister block thresholds from config.yaml — never hardcoded."""
    import yaml
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    th  = cfg.get("thresholds", {})
    per = th.get("per_minister", {})
    block_global = float(th.get("block", 0.55))
    return {m: float(per.get(m, block_global))
            for m in ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR")}


def _load_corpus():
    return json.loads(CORPUS_PATH.read_text())


def _newest_report() -> Path:
    reports = sorted(glob.glob(str(EVASION_DIR / "evasion_report_*.json")))
    if not reports:
        log.error("No evasion_report_*.json in %s", EVASION_DIR)
        sys.exit(1)
    return Path(reports[-1])


def _load_evasions(report_path: Path, minister_filter: str | None) -> list[dict]:
    """Load the evasions (ALLOW + malicious-by-construction) from a report.

    The red-teamer already excluded AMBIGUOUS (non-malicious) paraphrases, so
    every record in top_examples is an evasion of a genuine attack. We additionally
    require speaker_verdict == ALLOW (defensive)."""
    d = json.loads(report_path.read_text())
    out = []
    for i, ex in enumerate(d.get("top_examples", [])):
        if ex.get("speaker_verdict") != "ALLOW":
            continue
        if minister_filter and ex.get("minister") != minister_filter:
            continue
        out.append({
            "evasion_id":  f"{ex['pattern_id']}_{ex['level']}_{i}",
            "pattern_id":  ex["pattern_id"],
            "minister":    ex["minister"],
            "level":       ex["level"],
            "paraphrase":  ex["paraphrase"],
            "dense_sim":   ex.get("dense_sim"),
            "hybrid_conf": ex.get("hybrid_conf"),
        })
    return out


def _pattern_l1l2l3(corpus: dict, minister: str, pattern_id: str):
    for p in corpus.get(minister, {}).get("patterns", []):
        if p["id"] == pattern_id:
            return p.get("L1_intent", ""), p.get("L2_mechanism", ""), p.get("L3_surface", "")
    return "", "", ""


def _next_ids(corpus: dict, minister: str, n: int) -> list[str]:
    pref = MINISTER_ID_PREFIX[minister]
    existing = [p["id"] for p in corpus.get(minister, {}).get("patterns", [])]
    nums = [int(pid.split("-")[1]) for pid in existing if "-" in pid and pid.split("-")[1].isdigit()]
    start = (max(nums) + 1) if nums else 1
    return [f"{pref}-{start + i:03d}" for i in range(n)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--evasion-report", type=Path, default=None,
                    help="Evasion report JSON (default: newest in evasion_results/)")
    ap.add_argument("--minister", default="CHANNEL",
                    choices=["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR", "ALL"],
                    help="Restrict to one minister's evasions (default: CHANNEL).")
    ap.add_argument("--model", default="qwen2.5:3b",
                    help="Ollama model for proposals (default: qwen2.5:3b).")
    ap.add_argument("--measure-closure", action="store_true",
                    help="Estimate gap closure (forward-looking, not a benchmark).")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    report = args.evasion_report or _newest_report()
    minister_filter = None if args.minister == "ALL" else args.minister
    log.info("Evasion report: %s | minister filter: %s", report.name, args.minister)

    corpus     = _load_corpus()
    thresholds = _load_thresholds()
    log.info("Block thresholds (from config.yaml): %s", thresholds)

    evasions = _load_evasions(report, minister_filter)
    if not evasions:
        log.error("No evasions matched the filter — nothing to do.")
        sys.exit(1)
    log.info("Loaded %d evasions", len(evasions))

    # Build the validator (embeds benign probe + corpus L1s once).
    benign_probe = json.loads(BENIGN_PROBE.read_text())["benign_actions"]
    corpus_l1_by_min = {
        m: [(p["id"], p.get("L1_intent", ""))
            for p in corpus.get(m, {}).get("patterns", [])]
        for m in ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR")
    }
    validator = PatternValidator(thresholds, benign_probe, corpus_l1_by_min)
    proposer  = PatternProposer(model=args.model)

    # Reserve IDs per minister as we go.
    id_pools: dict[str, list[str]] = {}
    def next_id(minister: str) -> str:
        if minister not in id_pools:
            id_pools[minister] = _next_ids(corpus, minister, len(evasions))
        return id_pools[minister].pop(0)

    passed, rejected, failed = [], [], []

    for ev in evasions:
        l1, l2, l3 = _pattern_l1l2l3(corpus, ev["minister"], ev["pattern_id"])
        new_id = next_id(ev["minister"])

        pattern = proposer.propose(
            evasion_text=ev["paraphrase"], l1=l1, l2=l2, l3=l3,
            new_id=new_id, evasion_id=ev["evasion_id"],
        )
        if pattern is None:
            failed.append({"evasion_id": ev["evasion_id"],
                           "reason": "LLM produced no usable pattern after 2 attempts"})
            # return the reserved id so it isn't skipped
            id_pools[ev["minister"]].insert(0, new_id)
            continue

        vr = validator.validate(
            proposed_l1=pattern["L1_intent"],
            minister=ev["minister"],
            evasion_text=ev["paraphrase"],
        )
        record = {
            "pattern": pattern,
            "evasion": ev,
            "validation": {
                "verdict": vr.verdict,
                "fp_max_sim": vr.fp_max_sim, "fp_worst_action": vr.fp_worst_action,
                "detection_sim": vr.detection_sim,
                "dedup_max_sim": vr.dedup_max_sim, "dedup_nearest_id": vr.dedup_nearest_id,
                "block_threshold": vr.block_threshold, "reason": vr.reason,
            },
        }
        if vr.verdict == "PASSED":
            passed.append(record)
        else:
            id_pools[ev["minister"]].insert(0, new_id)  # reclaim the id
            rejected.append({"evasion_id": ev["evasion_id"], "minister": ev["minister"],
                             "verdict": vr.verdict, "reason": vr.reason})

    # ── Optional gap-closure estimate ─────────────────────────────────────────
    closure = None
    if args.measure_closure and passed:
        # Of the evasions whose proposal passed, how many would the new L1 catch?
        # (detection_sim >= block threshold is exactly "would catch", already checked
        #  by CHECK B — so every PASSED proposal catches its own target by construction.
        #  We report it explicitly as the estimate.)
        n_catch = sum(1 for r in passed
                      if r["validation"]["detection_sim"] >= r["validation"]["block_threshold"])
        closure = {"n_target_evasions": len(passed), "n_would_catch": n_catch}

    config = {
        "evasion_report": report.name,
        "ministers": args.minister,
        "model": args.model,
        "thresholds": thresholds,
        "benign_probe_size": len(benign_probe),
        "note": "Laptop-measured candidate generation; FP gate uses a curated "
                "benign probe, not the Dell benign set. Hypothesis until Dell-confirmed.",
    }
    json_path, txt_path = write_staging(
        passed=passed, rejected=rejected, failed=failed,
        n_evasions=len(evasions), config=config, closure=closure,
    )

    print(f"\n  Loaded {len(evasions)} evasions | "
          f"PASSED {len(passed)} | REJECTED {len(rejected)} | FAILED {len(failed)}")
    print(f"  Staging: {json_path}")
    print(f"  Report : {txt_path}")
    print("  >>> CANDIDATES ONLY — human review required before corpus admission. <<<\n")


if __name__ == "__main__":
    main()
