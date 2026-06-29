#!/usr/bin/env python3
"""
kavach_eval/improvement_loop.py
===============================

Semi-automated corpus-improvement ORCHESTRATOR.

Chains the existing pieces into a human-in-the-loop closed loop:

    red-team (templated, deterministic)  →  evasion report
        →  corpus_agent (LLM proposer + 3-part anti-poisoning gate)
        →  per-candidate "does it actually fix the evasion?" test (temp ChromaDB)
        →  rebuild temp ChromaDB with survivors  →  re-run red-team (templated)
        →  compute delta (evasion before vs after)
        →  show human the summary  →  ASK approval
        →  on YES: append survivors to kavach_corpus_v1.json + rebuild PROD ChromaDB
        →  loop again only if (n_evaded > 0 AND delta improved AND human approved)

NON-NEGOTIABLE SAFETY DESIGN
----------------------------
* kavach_corpus_v1.json is APPEND-ONLY and is NEVER edited until a human types
  "yes". All intermediate work uses a temp copy in a scratch dir.
* New patterns are indexed into a TEMP ChromaDB (parliament/.chroma_kavach_staging/)
  first. The production ChromaDB (parliament/.chroma_kavach/) is never modified
  mid-loop — only after explicit approval.
* Rollback = don't approve. There is nothing to undo.
* A candidate is kept ONLY if it demonstrably fixes its triggering evasion
  against the temp ChromaDB (not just "passed the gate", not just "not a dup").
* Patterns are minister-scoped: CHANNEL evasions → CHANNEL corpus only.
* The regression delta uses the TEMPLATED (deterministic) paraphraser, never the
  LLM one — so "did it improve?" is attributable, not LLM-variance noise.

This script drives the REAL existing components (it does not reimplement scoring):
  - corpus_loader.py        (subprocess: --corpus <temp> --chroma <staging> --rebuild)
  - redteam_evasion_v0.py   (subprocess: --chroma <staging> templated --skip-sanity)
  - corpus_agent.{proposer,validator,staging}  (imported directly)
  - KavachScorer            (imported: per-candidate evasion-fix check)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import glob
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger("kavach.improvement_loop")

# ── Canonical paths ───────────────────────────────────────────────────────────
CORPUS_PATH       = _REPO_ROOT / "kavach_corpus_v1.json"
CONFIG_PATH       = _REPO_ROOT / "parliament" / "config.yaml"
PROD_CHROMA       = _REPO_ROOT / "parliament" / ".chroma_kavach"
STAGING_CHROMA    = _REPO_ROOT / "parliament" / ".chroma_kavach_staging"   # never the prod path
CORPUS_LOADER     = _REPO_ROOT / "corpus_loader.py"
REDTEAM           = _REPO_ROOT / "kavach_eval" / "redteam_evasion_v0.py"
AUDIT_LOG         = _REPO_ROOT / "kavach_eval" / "improvement_loop_audit.jsonl"
SCRATCH_DIR       = _REPO_ROOT / "kavach_eval" / ".improvement_loop_scratch"

# Expected baseline pattern counts — a guard against accidental corpus edits.
EXPECTED_COUNTS   = {"EXECUTOR": 100, "VAULT": 100, "CHANNEL": 101, "NAVIGATOR": 100}
MINISTERS         = ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR")
MINISTER_ID_PREFIX = {"EXECUTOR": "EXEC", "VAULT": "VAULT", "CHANNEL": "CHAN", "NAVIGATOR": "NAV"}


# ══════════════════════════════════════════════════════════════════════════════
# Small helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_corpus(path: Path = CORPUS_PATH) -> dict:
    return json.loads(path.read_text())


def _pattern_counts(corpus: dict) -> dict[str, int]:
    return {m: len(corpus.get(m, {}).get("patterns", [])) for m in MINISTERS}


def _load_thresholds() -> dict[str, float]:
    import yaml
    th = yaml.safe_load(CONFIG_PATH.read_text()).get("thresholds", {})
    per = th.get("per_minister", {})
    g = float(th.get("block", 0.55))
    return {m: float(per.get(m, g)) for m in MINISTERS}


def _assert_baseline_unchanged() -> None:
    """SAFETY 1: the live corpus's existing pattern counts must match the
    expected baseline. If they differ, something edited the corpus out of band —
    hard-abort rather than risk compounding an unexpected state."""
    counts = _pattern_counts(_load_corpus())
    if counts != EXPECTED_COUNTS:
        log.error("[ABORT] corpus pattern counts changed: got %s, expected %s.",
                  counts, EXPECTED_COUNTS)
        log.error("        Refusing to proceed — verify the corpus before running the loop.")
        sys.exit(2)


def _assert_staging_path(p: Path) -> None:
    """SAFETY 2: the staging ChromaDB must NEVER be the production path."""
    if p.resolve() == PROD_CHROMA.resolve():
        log.error("[ABORT] staging ChromaDB path equals the PRODUCTION path. Refusing.")
        sys.exit(2)


def _audit(record: dict) -> None:
    """SAFETY 4: append one JSONL line per iteration."""
    record = {"ts": _ts(), **record}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _next_ids(corpus: dict, minister: str, n: int) -> list[str]:
    pref = MINISTER_ID_PREFIX[minister]
    nums = [int(p["id"].split("-")[1]) for p in corpus.get(minister, {}).get("patterns", [])
            if "-" in p["id"] and p["id"].split("-")[1].isdigit()]
    start = (max(nums) + 1) if nums else 1
    return [f"{pref}-{start + i:03d}" for i in range(n)]


# ══════════════════════════════════════════════════════════════════════════════
# Driving the real components (subprocess)
# ══════════════════════════════════════════════════════════════════════════════

def run_redteam(chroma_path: Path, corpus_path: Path, out_dir: Path,
                minister: str | None) -> Path:
    """Run the TEMPLATED (deterministic) red-teamer against a given ChromaDB +
    corpus, write its report to out_dir, and return the report path.

    Templated only (no --use-llm): the regression check must be deterministic
    and attributable, not subject to LLM paraphrase variance."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(REDTEAM),
        "--chroma", str(chroma_path),
        "--corpus", str(corpus_path),
        "--config", str(CONFIG_PATH),
        "--out-dir", str(out_dir),
        "--skip-sanity",          # the loop already controls the environment
    ]
    if minister and minister != "ALL":
        cmd += ["--minister", minister]
    log.info("[redteam] %s", " ".join(cmd[1:]))
    subprocess.run(cmd, check=True)
    reports = sorted(glob.glob(str(out_dir / "evasion_report_*.json")))
    if not reports:
        log.error("[ABORT] red-teamer produced no evasion_report in %s", out_dir)
        sys.exit(2)
    return Path(reports[-1])


def rebuild_chroma(corpus_path: Path, chroma_path: Path) -> None:
    """Build/refresh a ChromaDB from a corpus JSON using the REAL corpus_loader."""
    if chroma_path != PROD_CHROMA:
        _assert_staging_path(chroma_path)
    cmd = [
        sys.executable, str(CORPUS_LOADER),
        "--corpus", str(corpus_path),
        "--chroma", str(chroma_path),
        "--rebuild", "--skip-smoke",
    ]
    log.info("[loader] %s", " ".join(cmd[1:]))
    subprocess.run(cmd, check=True)


def read_report(report_path: Path) -> dict:
    return json.loads(report_path.read_text())


# ══════════════════════════════════════════════════════════════════════════════
# corpus_agent (imported directly — not reimplemented)
# ══════════════════════════════════════════════════════════════════════════════

def propose_and_gate(report: dict, corpus: dict, thresholds: dict, model: str,
                     minister_filter: str | None):
    """Run the corpus_agent proposer + 3-part anti-poisoning gate on a report's
    evasions. Returns (passed, rejected, failed) — same shapes as agent.py."""
    from kavach_eval.corpus_agent.proposer import PatternProposer
    from kavach_eval.corpus_agent.validator import PatternValidator

    benign_probe = json.loads(
        (Path(__file__).resolve().parent / "corpus_agent" / "benign_probe.json").read_text()
    )["benign_actions"]
    corpus_l1_by_min = {
        m: [(p["id"], p.get("L1_intent", "")) for p in corpus.get(m, {}).get("patterns", [])]
        for m in MINISTERS
    }
    validator = PatternValidator(thresholds, benign_probe, corpus_l1_by_min)
    proposer  = PatternProposer(model=model)

    # Collect evasions (ALLOW + malicious-by-construction) from top_examples.
    evasions = []
    for i, ex in enumerate(report.get("top_examples", [])):
        if ex.get("speaker_verdict") != "ALLOW":
            continue
        if minister_filter and minister_filter != "ALL" and ex.get("minister") != minister_filter:
            continue
        evasions.append({
            "evasion_id": f"{ex['pattern_id']}_{ex['level']}_{i}",
            "pattern_id": ex["pattern_id"], "minister": ex["minister"],
            "level": ex["level"], "paraphrase": ex["paraphrase"],
        })

    id_pools: dict[str, list[str]] = {}
    def next_id(m: str) -> str:
        if m not in id_pools:
            id_pools[m] = _next_ids(corpus, m, len(evasions))
        return id_pools[m].pop(0)

    def _l1l2l3(m, pid):
        for p in corpus.get(m, {}).get("patterns", []):
            if p["id"] == pid:
                return p.get("L1_intent",""), p.get("L2_mechanism",""), p.get("L3_surface","")
        return "", "", ""

    passed, rejected, failed = [], [], []
    for ev in evasions:
        l1, l2, l3 = _l1l2l3(ev["minister"], ev["pattern_id"])
        new_id = next_id(ev["minister"])
        pattern = proposer.propose(evasion_text=ev["paraphrase"], l1=l1, l2=l2, l3=l3,
                                   new_id=new_id, evasion_id=ev["evasion_id"])
        if pattern is None:
            failed.append({"evasion_id": ev["evasion_id"], "reason": "LLM produced no usable pattern"})
            id_pools[ev["minister"]].insert(0, new_id)
            continue
        vr = validator.validate(proposed_l1=pattern["L1_intent"], minister=ev["minister"],
                                evasion_text=ev["paraphrase"])
        if vr.verdict == "PASSED":
            passed.append({"pattern": pattern, "evasion": ev,
                           "validation": {"verdict": vr.verdict,
                                          "detection_sim": vr.detection_sim,
                                          "block_threshold": vr.block_threshold,
                                          "fp_max_sim": vr.fp_max_sim,
                                          "dedup_max_sim": vr.dedup_max_sim,
                                          "dedup_nearest_id": vr.dedup_nearest_id,
                                          "reason": vr.reason}})
        else:
            id_pools[ev["minister"]].insert(0, new_id)
            rejected.append({"evasion_id": ev["evasion_id"], "minister": ev["minister"],
                             "verdict": vr.verdict, "reason": vr.reason})
    return passed, rejected, failed


# ══════════════════════════════════════════════════════════════════════════════
# The "does it actually FIX the evasion?" check (temp ChromaDB, real scorer)
# ══════════════════════════════════════════════════════════════════════════════

def keep_effective_candidates(passed: list[dict], temp_corpus: dict,
                              staging_chroma: Path, thresholds: dict) -> list[dict]:
    """For each gate-PASSED candidate, add it to the temp corpus, rebuild the
    staging ChromaDB, and re-score its TRIGGERING evasion via the real scorer.
    Keep the candidate ONLY if its evasion now scores >= the block threshold
    (i.e. the pattern demonstrably closes the gap). Drop silently otherwise.

    This is the extra guarantee beyond the dedup gate: not just 'new', but
    'demonstrably covers a previously-uncovered evasion'.
    """
    if not passed:
        return []
    from kavach_eval.redteam_evasion_v0 import KavachScorer

    # Add ALL candidates to the temp corpus first, then rebuild once.
    for item in passed:
        m = item["evasion"]["minister"]
        temp_corpus[m]["patterns"].append({k: item["pattern"][k] for k in
            ("id", "category", "source", "rationale", "L1_intent", "L2_mechanism", "L3_surface")})
    # write temp corpus + rebuild staging chroma
    tmp_corpus_path = SCRATCH_DIR / "corpus_with_candidates.json"
    tmp_corpus_path.write_text(json.dumps(temp_corpus, indent=2, ensure_ascii=True))
    rebuild_chroma(tmp_corpus_path, staging_chroma)

    # Score each triggering evasion against the staging ChromaDB.
    th = {m: {"block": thresholds[m], "grey": 0.50} for m in MINISTERS}
    scorer = KavachScorer(chroma_path=staging_chroma, thresholds=th)
    effective = []
    for item in passed:
        m = item["evasion"]["minister"]
        scans = scorer.score(item["evasion"]["paraphrase"])
        conf = scans[m].confidence
        block_th = thresholds[m]
        item["fix_check"] = {"hybrid_conf": round(conf, 4), "block_threshold": block_th,
                             "fixed": conf >= block_th}
        if conf >= block_th:
            effective.append(item)
            log.info("[fix-check] %s FIXED its evasion (conf %.3f >= %.2f)",
                     item["pattern"]["id"], conf, block_th)
        else:
            log.info("[fix-check] %s did NOT fix its evasion (conf %.3f < %.2f) — dropped",
                     item["pattern"]["id"], conf, block_th)
    return effective


# ══════════════════════════════════════════════════════════════════════════════
# Integration (only after human types "yes")
# ══════════════════════════════════════════════════════════════════════════════

def integrate(effective: list[dict]) -> None:
    """APPEND survivors to kavach_corpus_v1.json (never edit existing), then
    rebuild the PRODUCTION ChromaDB. Only reached after explicit approval."""
    _assert_baseline_unchanged()                    # SAFETY 1 (re-check at write time)
    corpus = _load_corpus()
    for item in effective:
        m = item["evasion"]["minister"]
        pat = {k: item["pattern"][k] for k in
               ("id", "category", "source", "rationale", "L1_intent", "L2_mechanism", "L3_surface")}
        corpus[m]["patterns"].append(pat)          # APPEND ONLY
    CORPUS_PATH.write_text(json.dumps(corpus, indent=2, ensure_ascii=True))
    log.info("[integrate] appended %d patterns to %s — rebuilding PRODUCTION ChromaDB",
             len(effective), CORPUS_PATH.name)
    rebuild_chroma(CORPUS_PATH, PROD_CHROMA)


# ══════════════════════════════════════════════════════════════════════════════
# Main loop
# ══════════════════════════════════════════════════════════════════════════════

def _summary(it: int, before: dict, after: dict, n_proposed: int, n_gate: int,
             n_effective: int, candidates: list[dict]) -> None:
    eb, na = before["evasion_rate"] * 100, after["evasion_rate"] * 100
    print("\n" + "═" * 60)
    print(f"  ITERATION {it} SUMMARY")
    print("═" * 60)
    print(f"  Evasion before        : {eb:.1f}%  ({before['n_evaded']} evaded)")
    print(f"  Evasion after (temp)  : {na:.1f}%  ({after['n_evaded']} evaded)")
    print(f"  Delta                 : -{before['n_evaded'] - after['n_evaded']} evasions fixed")
    print(f"  Patterns proposed     : {n_proposed}")
    print(f"  Passed anti-poison gate: {n_gate}")
    print(f"  Actually fixed evasion: {n_effective}")
    print(f"  Ready to integrate    : {n_effective}")
    print("  ── candidates ──")
    for c in candidates:
        p = c["pattern"]
        print(f"    [{p['id']}] {p['L1_intent'][:70]}")
    print("═" * 60)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--model", default="gemma4:26b",
                    help="Ollama model for the corpus_agent proposer (default: gemma4:26b)")
    ap.add_argument("--minister", default="ALL",
                    choices=["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR", "ALL"],
                    help="Target a specific minister only (default: ALL evading ministers)")
    ap.add_argument("--parliament-url", default="http://127.0.0.1:8088",
                    help="Parliament URL (default: http://127.0.0.1:8088)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Run everything but NEVER write the corpus or the production "
                         "ChromaDB — just report what would happen.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    _assert_staging_path(STAGING_CHROMA)            # SAFETY 2
    _assert_baseline_unchanged()                    # SAFETY 1
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    thresholds = _load_thresholds()
    minister_filter = None if args.minister == "ALL" else args.minister

    iteration = 0
    while True:
        iteration += 1
        log.info("════ ITERATION %d ════", iteration)

        # 1. Baseline red-team (templated) against the PRODUCTION ChromaDB.
        rt_out = SCRATCH_DIR / f"iter{iteration}_before"
        before_report = read_report(run_redteam(PROD_CHROMA, CORPUS_PATH, rt_out, minister_filter))
        if before_report.get("n_evaded", 0) == 0:
            print("\n  Evasion is 0 — nothing to fix. Done.")
            _audit({"iteration": iteration, "n_evaded_before": 0, "stop": "no_evasions"})
            break

        # 2. corpus_agent: propose + anti-poisoning gate.
        corpus = _load_corpus()
        passed, rejected, failed = propose_and_gate(
            before_report, corpus, thresholds, args.model, minister_filter)
        if not passed:
            print("\n  corpus_agent produced no gate-passing patterns this iteration. Stop.")
            _audit({"iteration": iteration, "n_evaded_before": before_report["n_evaded"],
                    "candidates_proposed": len(passed)+len(rejected)+len(failed),
                    "candidates_gate_passed": 0, "stop": "no_gate_passing"})
            break

        # 3. Per-candidate "does it FIX the evasion?" check on a TEMP ChromaDB.
        temp_corpus = _load_corpus()               # fresh copy for the temp build
        effective = keep_effective_candidates(passed, temp_corpus, STAGING_CHROMA, thresholds)
        if not effective:
            print("\n  No candidate actually fixed its evasion against the temp ChromaDB. Stop.")
            _audit({"iteration": iteration, "n_evaded_before": before_report["n_evaded"],
                    "candidates_gate_passed": len(passed), "candidates_effective": 0,
                    "stop": "no_effective"})
            break

        # 4. Rebuild temp ChromaDB with ONLY the effective survivors, re-run red-team.
        temp_corpus2 = _load_corpus()
        for item in effective:
            m = item["evasion"]["minister"]
            temp_corpus2[m]["patterns"].append({k: item["pattern"][k] for k in
                ("id","category","source","rationale","L1_intent","L2_mechanism","L3_surface")})
        tmp2 = SCRATCH_DIR / "corpus_effective.json"
        tmp2.write_text(json.dumps(temp_corpus2, indent=2, ensure_ascii=True))
        rebuild_chroma(tmp2, STAGING_CHROMA)
        rt_after = SCRATCH_DIR / f"iter{iteration}_after"
        after_report = read_report(run_redteam(STAGING_CHROMA, tmp2, rt_after, minister_filter))

        delta = before_report["n_evaded"] - after_report["n_evaded"]
        n_proposed = len(passed) + len(rejected) + len(failed)
        _summary(iteration, before_report, after_report, n_proposed, len(passed),
                 len(effective), effective)

        if delta <= 0:
            print("\n  Delta did not improve — corpus_agent didn't help. Stop.")
            _audit({"iteration": iteration, "n_evaded_before": before_report["n_evaded"],
                    "n_evaded_after": after_report["n_evaded"], "delta": delta,
                    "candidates_effective": len(effective), "patterns_integrated": 0,
                    "human_approved": False, "stop": "no_delta"})
            break

        # 5. ASK approval (never auto-approve).
        if args.dry_run:
            print("\n  --dry-run: would ask for approval here; NOT writing anything.")
            _audit({"iteration": iteration, "n_evaded_before": before_report["n_evaded"],
                    "n_evaded_after": after_report["n_evaded"], "delta": delta,
                    "candidates_proposed": n_proposed, "candidates_effective": len(effective),
                    "patterns_integrated": 0, "human_approved": "dry_run"})
            break

        ans = input("\n  Approve integration of these patterns into the live corpus? (yes/no): ").strip().lower()
        if ans != "yes":
            print("  Not approved — discarding staging, stopping. (No changes made.)")
            _audit({"iteration": iteration, "n_evaded_before": before_report["n_evaded"],
                    "n_evaded_after": after_report["n_evaded"], "delta": delta,
                    "candidates_effective": len(effective), "patterns_integrated": 0,
                    "human_approved": False, "stop": "declined"})
            break

        # 6. Integrate (append-only) + rebuild PRODUCTION ChromaDB, then loop.
        integrate(effective)
        _audit({"iteration": iteration, "n_evaded_before": before_report["n_evaded"],
                "n_evaded_after": after_report["n_evaded"], "delta": delta,
                "candidates_proposed": n_proposed, "candidates_effective": len(effective),
                "patterns_integrated": len(effective),
                "integrated_ids": [c["pattern"]["id"] for c in effective],
                "human_approved": True})
        print(f"\n  Integrated {len(effective)} patterns. Looping to verify + find the next gap.\n")
        # Intentional: the corpus legitimately grew — update the in-memory baseline so
        # subsequent iterations' safety guard reflects the new approved state, not the
        # pre-session original. The guard still catches any OUT-OF-BAND edits.
        for c in effective:
            EXPECTED_COUNTS[c["evasion"]["minister"]] += 1


if __name__ == "__main__":
    main()
