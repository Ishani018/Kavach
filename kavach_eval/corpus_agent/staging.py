"""
kavach_eval/corpus_agent/staging.py
===================================

Writes validated candidate patterns to a STAGING file — never to the live
corpus. A human reviews the staging file and decides what (if anything) goes
into kavach_corpus_v1.json.

Outputs (to kavach_eval/corpus_agent/staging/):
  proposed_patterns_<ts>.json — candidates in kavach_corpus_v1.json schema,
      each annotated with the triggering evasion and the validation scores,
      plus "human_review_required": true.
  staging_report_<ts>.txt — human-readable summary: counts, gate breakdown,
      the candidates, and explicit measured-vs-estimated caveats.

CRITICAL: this module NEVER writes to kavach_corpus_v1.json or parliament/.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("kavach.corpus_agent.staging")

STAGING_DIR = Path(__file__).resolve().parent / "staging"


def write_staging(
    passed:      list[dict],   # [{pattern, evasion, validation}, ...]
    rejected:    list[dict],   # [{evasion_id, minister, verdict, reason, ...}, ...]
    failed:      list[dict],   # [{evasion_id, reason}, ...]
    n_evasions:  int,
    config:      dict,
    closure:     dict | None = None,
) -> tuple[Path, Path]:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # ── JSON staging file ─────────────────────────────────────────────────────
    json_path = STAGING_DIR / f"proposed_patterns_{ts}.json"
    staged = []
    for item in passed:
        p = dict(item["pattern"])
        p["_staging"] = {
            "human_review_required": True,
            "triggering_evasion":    item["evasion"],
            "validation":            item["validation"],
        }
        staged.append(p)
    json_path.write_text(json.dumps({
        "_warning": "CANDIDATES ONLY. These were proposed by an LLM and passed "
                    "the 3-part anti-poisoning gate, but have NOT been added to "
                    "the live corpus. A human must review before any admission "
                    "to kavach_corpus_v1.json.",
        "generated": ts,
        "config":    config,
        "candidates": staged,
    }, indent=2), encoding="utf-8")

    # ── Human-readable report ─────────────────────────────────────────────────
    txt_path = STAGING_DIR / f"staging_report_{ts}.txt"
    from collections import Counter
    rej_breakdown = Counter(r["verdict"] for r in rejected)

    lines = []
    A = lines.append
    A("=" * 72)
    A(f"KAVACH CORPUS-AGENT v0 — STAGING REPORT — {ts}")
    A("=" * 72)
    A("")
    A(f"  Evasions loaded            : {n_evasions}")
    A(f"  Proposals attempted        : {len(passed) + len(rejected)}")
    A(f"  FAILED proposals (LLM)     : {len(failed)}")
    A(f"  PASSED all gates (staged)  : {len(passed)}")
    A(f"  REJECTED                   : {len(rejected)}")
    for verdict, n in sorted(rej_breakdown.items()):
        A(f"      {verdict:<22} {n}")
    A("")
    A(f"  Model: {config.get('model')}   Minister(s): {config.get('ministers')}")
    A("")
    A("  NOTE ON THE FP GATE (CHECK A): it scores proposed patterns against a")
    A("  CURATED benign-action probe set (corpus_agent/benign_probe.json), not")
    A("  the full Dell benign distribution. It targets the exact legitimate-use")
    A("  cases CHANNEL was over-firing on (git push, send-email, bitsadmin")
    A("  update, gist, SMS). Real FP validation happens on the Dell re-run.")
    A("")

    if closure is not None:
        A("-" * 72)
        A("  ESTIMATED GAP CLOSURE (forward-looking, NOT a benchmark re-run):")
        A(f"    Of {closure['n_target_evasions']} evasions that triggered a staged")
        A(f"    pattern, {closure['n_would_catch']} would be caught by the proposed")
        A(f"    pattern's L1 (sim >= block threshold).")
        A( "    This is a local embedding estimate IF the proposals are admitted —")
        A( "    not a confirmed result. Real closure needs a Dell red-teamer re-run.")
        A("")

    A("-" * 72)
    A("  STAGED CANDIDATES (review before admitting to corpus):")
    A("-" * 72)
    for item in passed:
        p = item["pattern"]; v = item["validation"]; e = item["evasion"]
        A("")
        A(f"  [{p['id']}] {p['category']}   (for evasion {e['evasion_id']}, "
          f"minister {e['minister']})")
        A(f"    triggered by: {e['paraphrase'][:80]}")
        A(f"    L1_intent : {p['L1_intent']}")
        A(f"    L2_mechanism: {p['L2_mechanism']}")
        A(f"    L3_surface: {p['L3_surface']}")
        A(f"    gate: FP_max={v['fp_max_sim']} (<{v['block_threshold']}) "
          f"detection={v['detection_sim']} (>= {v['block_threshold']}) "
          f"dedup_max={v['dedup_max_sim']} (nearest {v['dedup_nearest_id']})")
    A("")
    A("-" * 72)
    A("  REJECTED (not staged) — the gate working as intended:")
    for r in rejected:
        A(f"    evasion {r['evasion_id']} [{r['minister']}] -> {r['verdict']}: {r['reason']}")
    if failed:
        A("")
        A("  FAILED PROPOSALS (LLM produced no usable pattern):")
        for f in failed:
            A(f"    evasion {f['evasion_id']}: {f['reason']}")
    A("")
    A("  >>> These are CANDIDATES. Review before adding to the corpus. <<<")
    A("=" * 72)

    txt_path.write_text("\n".join(lines), encoding="utf-8")

    log.info("Staging written: %s  +  %s", json_path.name, txt_path.name)
    return json_path, txt_path
