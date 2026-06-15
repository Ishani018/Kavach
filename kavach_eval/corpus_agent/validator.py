"""
kavach_eval/corpus_agent/validator.py
=====================================

The anti-poisoning validation gate — the centerpiece of the corpus agent.

Every LLM-proposed corpus pattern must pass ALL THREE checks before it can be
staged. A pattern that fails any check is REJECTED with the triggering score
logged. This is what prevents corpus poisoning and false-positive inflation
(the exact CHANNEL over-firing failure mode we already had to fix by hand).

CHECK A — FP gate (anti-poisoning core):
    Embed the proposed pattern's L1_intent with the REAL bge-base-en-v1.5 and
    score it against a curated benign-action probe set. If it scores at or
    above the owning minister's block threshold on ANY benign action, REJECT
    (it would false-positive on legitimate traffic). This is the CHANNEL lesson
    applied automatically.

CHECK B — Detection:
    Embed L1_intent, cosine to the evading paraphrase it was written to catch.
    If below the block threshold, REJECT (the pattern wouldn't even catch its
    own target evasion).

CHECK C — Dedup:
    Embed L1_intent, cosine to every existing pattern's L1 in the same
    minister's corpus. If >= 0.92 to any, REJECT (near-duplicate — we want new
    coverage, not a rephrasing).

All embeddings use the SAME bge-base-en-v1.5 as production. All thresholds are
read from parliament/config.yaml — never hardcoded.

This module is READ-ONLY on the corpus and never touches parliament/.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger("kavach.corpus_agent.validator")

BGE_MODEL_NAME   = "BAAI/bge-base-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DEDUP_THRESHOLD  = 0.92   # tight: reject near-duplicates of existing patterns


@dataclass
class ValidationResult:
    verdict:        str                      # "PASSED" | "REJECTED_FP" | "REJECTED_DETECTION" | "REJECTED_DEDUP"
    fp_max_sim:     float = 0.0              # CHECK A: highest benign-probe similarity
    fp_worst_action: str = ""               # the benign action it came closest to firing on
    detection_sim:  float = 0.0             # CHECK B: similarity to the target evasion
    dedup_max_sim:  float = 0.0             # CHECK C: highest existing-pattern similarity
    dedup_nearest_id: str = ""              # the existing pattern it's closest to
    block_threshold: float = 0.0            # the minister threshold used
    reason:         str = ""                # human-readable explanation


class PatternValidator:
    """Runs the 3-part anti-poisoning gate on proposed patterns."""

    def __init__(
        self,
        thresholds:       dict[str, float],          # per-minister block thresholds
        benign_probe:     list[dict],                # [{minister_domain, text}, ...]
        corpus_l1_by_min: dict[str, list[tuple[str, str]]],  # minister -> [(pattern_id, L1_intent)]
        model=None,
    ) -> None:
        self._thresholds = thresholds
        self._benign     = benign_probe
        self._corpus_l1  = corpus_l1_by_min

        if model is None:
            from sentence_transformers import SentenceTransformer
            log.info("Loading BGE model: %s", BGE_MODEL_NAME)
            model = SentenceTransformer(BGE_MODEL_NAME)
        self._model = model

        # Pre-embed the benign probe and the corpus L1s once (reused per proposal).
        self._benign_vecs = [
            (b["text"], self._embed(b["text"])) for b in self._benign
        ]
        self._corpus_vecs: dict[str, list[tuple[str, np.ndarray]]] = {}
        for minister, items in self._corpus_l1.items():
            self._corpus_vecs[minister] = [
                (pid, self._embed(text)) for pid, text in items
            ]
        log.info("Validator ready: %d benign probes, corpus L1s embedded for %s",
                 len(self._benign_vecs), list(self._corpus_vecs.keys()))

    def _embed(self, text: str) -> np.ndarray:
        vec = self._model.encode(
            BGE_QUERY_PREFIX + text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vec, dtype=np.float32)

    @staticmethod
    def _cos(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.clip(np.dot(a, b), -1.0, 1.0))

    def validate(
        self,
        proposed_l1: str,
        minister:    str,
        evasion_text: str,
    ) -> ValidationResult:
        """Run all three checks (FP -> detection -> dedup). The first failure
        decides the verdict, but all measured scores are recorded."""
        block_th = self._thresholds.get(minister, 0.60)
        l1_vec   = self._embed(proposed_l1)

        # ── CHECK A: FP gate ──────────────────────────────────────────────────
        fp_scores = [(txt, self._cos(l1_vec, v)) for txt, v in self._benign_vecs]
        fp_worst, fp_max = max(fp_scores, key=lambda x: x[1]) if fp_scores else ("", 0.0)

        # ── CHECK B: detection ────────────────────────────────────────────────
        det_sim = self._cos(l1_vec, self._embed(evasion_text))

        # ── CHECK C: dedup ────────────────────────────────────────────────────
        dd = self._corpus_vecs.get(minister, [])
        dd_scores = [(pid, self._cos(l1_vec, v)) for pid, v in dd]
        dd_id, dd_max = max(dd_scores, key=lambda x: x[1]) if dd_scores else ("", 0.0)

        res = ValidationResult(
            verdict="PASSED",
            fp_max_sim=round(fp_max, 4), fp_worst_action=fp_worst,
            detection_sim=round(det_sim, 4),
            dedup_max_sim=round(dd_max, 4), dedup_nearest_id=dd_id,
            block_threshold=block_th,
        )

        # Verdict precedence: FP first (most important), then detection, then dedup.
        if fp_max >= block_th:
            res.verdict = "REJECTED_FP"
            res.reason = (f"FP risk: fires on benign action at sim {fp_max:.3f} "
                          f">= block threshold {block_th:.2f} "
                          f"(benign: \"{fp_worst[:60]}\")")
        elif det_sim < block_th:
            res.verdict = "REJECTED_DETECTION"
            res.reason = (f"detection miss: sim to target evasion {det_sim:.3f} "
                          f"< block threshold {block_th:.2f} — would not catch it")
        elif dd_max >= DEDUP_THRESHOLD:
            res.verdict = "REJECTED_DEDUP"
            res.reason = (f"near-duplicate of {dd_id} at sim {dd_max:.3f} "
                          f">= {DEDUP_THRESHOLD}")
        else:
            res.reason = (f"PASSED — FP {fp_max:.3f} < {block_th:.2f}, "
                          f"detection {det_sim:.3f} >= {block_th:.2f}, "
                          f"dedup {dd_max:.3f} < {DEDUP_THRESHOLD} (nearest {dd_id})")

        log.info("[validate] %s minister=%s | %s", res.verdict, minister, res.reason)
        return res
