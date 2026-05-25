"""
parliament/speaker.py
=====================

The Speaker collects minister verdicts and combines them into a single
parliament verdict. Asymmetric: ONE confident BLOCK is enough to block.

This mirrors the speaker logic in kavach_embedding_lab.html so the lab demo
and the production service produce identical verdicts on identical inputs.

Design decisions:

  1. Any minister at confidence ≥ block_threshold → BLOCK. The reason is taken
     from the highest-confidence blocking minister.

  2. COMPASS drift alone (without any minister BLOCK) is treated as ESCALATE,
     not BLOCK. Drift is a soft signal — the user might have legitimately
     pivoted. The exception: COMPASS drift PLUS any minister at ≥ grey level
     escalates to BLOCK because we now have two corroborating signals.

  3. No minister at BLOCK and no COMPASS drift, but at least one minister
     at ≥ grey_threshold → ESCALATE.

  4. Otherwise → ALLOW.

We deliberately do NOT do score averaging across ministers. The four ministers
target different attack categories (code execution, credential theft, exfil,
trajectory) and a high score from one is meaningful regardless of whether the
others are silent. Averaging would dilute that signal.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ministers import MinisterScan


@dataclass
class SpeakerVerdict:
    verdict:    str          # "BLOCK" | "ESCALATE" | "ALLOW"
    decided_by: str          # minister name or "Speaker"
    confidence: float
    reason:     str
    blocks:     int          # count of ministers voting BLOCK
    escalates:  int          # count voting ESCALATE
    allows:     int          # count voting ALLOW


def combine_verdicts(
    minister_results: list[MinisterScan],
    compass_drift: bool,
    compass_sim: float,
    thresholds: dict,
) -> SpeakerVerdict:
    """
    Combine minister scans + COMPASS drift signal into a final verdict.

    Args:
      minister_results: scans from every activated minister
      compass_drift:    True if cosine(intent, action) < compass_drift threshold
      compass_sim:      the actual cosine value
      thresholds:       dict with block, grey, compass_drift keys
    """
    block_threshold = thresholds["block"]
    grey_threshold  = thresholds["grey"]
    drift_threshold = thresholds["compass_drift"]

    # Tally
    blocks    = [r for r in minister_results if r.verdict == "BLOCK"]
    escalates = [r for r in minister_results if r.verdict == "ESCALATE"]
    allows    = [r for r in minister_results if r.verdict == "ALLOW"]

    # ── Case 1: any minister at BLOCK ─────────────────────────────────────
    if blocks:
        winner = max(blocks, key=lambda r: r.confidence)
        reason = (
            f"{winner.minister} matched {winner.matched_id or 'pattern'} "
            f"({winner.matched_level or 'L?'}) at sim {winner.confidence:.3f} "
            f"≥ block threshold {block_threshold:.2f}"
        )
        if compass_drift:
            reason += (
                f"; COMPASS drift confirms (sim {compass_sim:.3f} "
                f"< {drift_threshold:.2f})"
            )
        return SpeakerVerdict(
            verdict="BLOCK",
            decided_by=winner.minister,
            confidence=winner.confidence,
            reason=reason,
            blocks=len(blocks),
            escalates=len(escalates),
            allows=len(allows),
        )

    # ── Case 2: COMPASS drift + at least one minister at ESCALATE → BLOCK ─
    if compass_drift and escalates:
        winner = max(escalates, key=lambda r: r.confidence)
        return SpeakerVerdict(
            verdict="BLOCK",
            decided_by=f"COMPASS+{winner.minister}",
            confidence=max(winner.confidence, 1.0 - compass_sim),
            reason=(
                f"COMPASS drift (sim {compass_sim:.3f} "
                f"< {drift_threshold:.2f}) corroborated by "
                f"{winner.minister} borderline match "
                f"({winner.matched_id} at {winner.confidence:.3f})"
            ),
            blocks=0,
            escalates=len(escalates),
            allows=len(allows),
        )

    # ── Case 3: any minister at ESCALATE → ESCALATE ────────────────────────
    if escalates:
        winner = max(escalates, key=lambda r: r.confidence)
        return SpeakerVerdict(
            verdict="ESCALATE",
            decided_by=winner.minister,
            confidence=winner.confidence,
            reason=(
                f"{winner.minister} borderline match "
                f"({winner.matched_id} at {winner.confidence:.3f}, "
                f"between grey {grey_threshold:.2f} and block "
                f"{block_threshold:.2f}) — escalating to user"
            ),
            blocks=0,
            escalates=len(escalates),
            allows=len(allows),
        )

    # ── Case 4: COMPASS drift alone → ESCALATE ─────────────────────────────
    if compass_drift:
        return SpeakerVerdict(
            verdict="ESCALATE",
            decided_by="COMPASS",
            confidence=1.0 - compass_sim,
            reason=(
                f"COMPASS drift detected (sim {compass_sim:.3f} "
                f"< {drift_threshold:.2f}) without minister match — "
                f"user intent diverged from proposed action; escalating"
            ),
            blocks=0,
            escalates=0,
            allows=len(allows),
        )

    # ── Case 5: clean ────────────────────────────────────────────────────
    avg = (
        sum(r.confidence for r in allows) / len(allows) if allows else 0.0
    )
    return SpeakerVerdict(
        verdict="ALLOW",
        decided_by="Speaker",
        confidence=round(avg, 4),
        reason=(
            f"no minister exceeded block threshold ({block_threshold:.2f}); "
            f"intent⇄action aligned (sim {compass_sim:.3f})"
        ),
        blocks=0,
        escalates=0,
        allows=len(allows),
    )
