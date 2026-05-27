"""
parliament/ministers.py
=======================

A "minister" runs one semantic detector against one ChromaDB collection. Each
minister has 50 attack patterns × 3 levels (L1 intent / L2 mechanism / L3
surface) = 150 documents in its collection. At query time the minister embeds
the proposed action with the BGE query-side prefix and asks Chroma for the
top-K nearest documents. Cosine similarity = 1.0 - distance (Chroma is
configured with hnsw:space="cosine" by corpus_loader.py).

The minister returns:
    - max similarity across all returned documents
    - the matched pattern ID and the matched text
    - the verdict — BLOCK / ESCALATE / ALLOW — based on thresholds

The speaker combines minister results into a final verdict (see speaker.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MinisterScan:
    minister:     str
    verdict:      str            # "BLOCK" | "ESCALATE" | "ALLOW"
    confidence:   float          # max cosine similarity across L1/L2/L3
    matched_id:   str | None
    matched_text: str | None
    matched_level: str | None    # "L1" | "L2" | "L3"


# ──────────────────────────────────────────────────────────────────────────────
# Minister scan
# ──────────────────────────────────────────────────────────────────────────────

def run_minister(
    minister: str,
    text: str,
    collection,
    embed_fn: Callable[[str], np.ndarray],
    thresholds: dict,
    top_k: int = 10,
) -> MinisterScan:
    """
    Query the minister's collection with the embedded text. Return the highest-
    similarity match and its verdict.

    `collection` is a chromadb.Collection. `embed_fn` is the query-side
    embedder that applies the BGE prefix and L2-normalizes. `thresholds` has
    keys "block" and "grey".
    """
    query_vec = embed_fn(text)
    q_list = query_vec.tolist()

    res = collection.query(
        query_embeddings=[q_list],
        n_results=top_k,
        include=["distances", "metadatas", "documents"],
    )

    if not res or not res.get("distances") or not res["distances"][0]:
        return MinisterScan(
            minister=minister,
            verdict="ALLOW",
            confidence=0.0,
            matched_id=None,
            matched_text=None,
            matched_level=None,
        )

    # Chroma cosine space: distance = 1 - cos_sim → cos_sim = 1 - distance
    distances = res["distances"][0]
    metadatas = res["metadatas"][0]
    documents = res["documents"][0]

    similarities = [max(0.0, 1.0 - d) for d in distances]

    # Take max across all returned documents (which span L1/L2/L3 of various
    # patterns). The pattern that contributed the max is the "matched" one.
    best_idx = int(np.argmax(similarities))
    best_sim = float(similarities[best_idx])
    best_meta = metadatas[best_idx] or {}
    best_doc = documents[best_idx]

    block_threshold = thresholds["block"]
    grey_threshold = thresholds["grey"]

    if best_sim >= block_threshold:
        verdict = "BLOCK"
    elif best_sim >= grey_threshold:
        verdict = "ESCALATE"
    else:
        verdict = "ALLOW"

    return MinisterScan(
        minister=minister,
        verdict=verdict,
        confidence=round(best_sim, 4),
        matched_id=best_meta.get("pattern_id"),
        matched_text=best_doc[:240] if best_doc else None,
        matched_level=best_meta.get("level"),
    )


def run_minister_dual(
    minister: str,
    text: str,
    collection_v1,
    collection_tech,
    embed_fn,
    thresholds: dict,
    top_k: int = 10,
) -> MinisterScan:
    """Query v1 semantic corpus AND technical precision corpus; return the
    higher-confidence result. Improves recall without raising FPR: v1 catches
    novel intent-level attacks; technical corpus catches exact tool patterns.
    The higher-confidence result is returned; matched_id is tagged ':tech' when
    the technical corpus wins so logs reveal which layer fired.
    """
    r1   = run_minister(minister, text, collection_v1,   embed_fn, thresholds, top_k)
    rT   = run_minister(minister, text, collection_tech, embed_fn, thresholds, top_k)
    if rT.confidence > r1.confidence:
        return MinisterScan(
            minister=rT.minister,
            verdict=rT.verdict,
            confidence=rT.confidence,
            matched_id=(rT.matched_id or "") + ":tech",
            matched_text=rT.matched_text,
            matched_level=rT.matched_level,
        )
    return r1
