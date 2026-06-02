"""
parliament/ministers.py
=======================

A "minister" runs one semantic detector against one ChromaDB collection. Each
minister has attack patterns × 3 levels (L1 intent / L2 mechanism / L3
surface). At query time the minister uses HYBRID retrieval: BM25 (lexical) +
dense BGE embeddings, fused with Reciprocal Rank Fusion (RRF, k=60).

Why hybrid: pure dense search causes abstract L1 patterns to over-match benign
natural-language queries (the InjecAgent FPR problem: 88.2%). BM25 adds a
lexical gate that requires keyword overlap — benign queries like "read src/main.py"
stop matching attack patterns like "agent reading credential files" because BM25
sees no shared attack keywords even when dense vectors are close.

RRF formula: score(d) = sum over retrievers of 1 / (k + rank(d))
k=60 is the standard value (Robertson et al.; avoids over-weighting rank-1).

The minister returns:
    - fused RRF score as confidence
    - the matched pattern ID and matched text
    - verdict: BLOCK / ESCALATE / ALLOW based on thresholds

BM25 indexes are built once at startup and stored in _state["bm25_indexes"]
by server.py. Each index is a dict: {"bm25": BM25Okapi, "ids": [...], "docs": [...]}.

The speaker combines minister results into a final verdict (see speaker.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import numpy as np

# rank_bm25 is a lightweight pure-Python BM25 implementation.
# Install: pip install rank-bm25
try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MinisterScan:
    minister:      str
    verdict:       str            # "BLOCK" | "ESCALATE" | "ALLOW"
    confidence:    float          # RRF-fused score (or raw cosine if BM25 unavailable)
    matched_id:    str | None
    matched_text:  str | None
    matched_level: str | None     # "L1" | "L2" | "L3"
    source:        str | None = None   # corpus pattern source for provenance
    retrieval_mode: str = "dense"      # "dense" | "hybrid"


# ──────────────────────────────────────────────────────────────────────────────
# BM25 index builder  (called once at startup by server.py)
# ──────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    return re.findall(r"[a-zA-Z0-9_/.-]+", text.lower())


def build_bm25_index(collection) -> dict | None:
    """
    Fetch ALL documents from a ChromaDB collection and build a BM25Okapi index.
    Returns a dict with keys: bm25, ids, docs, metadatas.
    Returns None if rank_bm25 is not installed or collection is empty.
    """
    if not _BM25_AVAILABLE:
        return None

    try:
        result = collection.get(include=["documents", "metadatas"])
    except Exception:
        return None

    docs = result.get("documents") or []
    ids  = result.get("ids") or []
    metas = result.get("metadatas") or []

    if not docs:
        return None

    tokenized = [_tokenize(d) for d in docs]
    bm25 = BM25Okapi(tokenized)

    return {
        "bm25":      bm25,
        "ids":       ids,
        "docs":      docs,
        "metadatas": metas,
    }


# ──────────────────────────────────────────────────────────────────────────────
# RRF fusion
# ──────────────────────────────────────────────────────────────────────────────

_RRF_K = 60  # Standard RRF constant (Robertson et al.)


def _rrf_fuse(
    dense_ranked: list[int],   # doc indices by dense rank (best first)
    bm25_ranked:  list[int],   # doc indices by BM25 rank (best first)
    n_docs: int,
) -> list[tuple[int, float]]:
    """
    Fuse two ranked lists with Reciprocal Rank Fusion.
    Returns list of (doc_index, rrf_score) sorted descending by score.
    """
    scores: dict[int, float] = {}
    for rank, idx in enumerate(dense_ranked):
        scores[idx] = scores.get(idx, 0.0) + 1.0 / (_RRF_K + rank + 1)
    for rank, idx in enumerate(bm25_ranked):
        scores[idx] = scores.get(idx, 0.0) + 1.0 / (_RRF_K + rank + 1)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# Core minister scan — pure dense (original, used as fallback)
# ──────────────────────────────────────────────────────────────────────────────

def run_minister(
    minister: str,
    text: str,
    collection,
    embed_fn: Callable[[str], np.ndarray],
    thresholds: dict,
    top_k: int = 10,
    query_vec: np.ndarray | None = None,
) -> MinisterScan:
    """
    Query the minister's collection with the embedded text using dense-only
    retrieval. Returns the highest-similarity match and its verdict.

    `collection` is a chromadb.Collection. `embed_fn` is the query-side
    embedder that applies the BGE prefix and L2-normalizes. `thresholds` has
    keys "block" and "grey".

    `query_vec`: optional precomputed BGE query vector for `text`. When the
    caller has already embedded the action (embed-once path in server.py),
    pass it here to skip the redundant embed. Falls back to embed_fn(text)
    when None, so existing callers are unaffected.

    Used as fallback when a BM25 index is not available (run_minister_hybrid
    is the primary path when rank_bm25 is installed).
    """
    query_vec = embed_fn(text) if query_vec is None else query_vec
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
            retrieval_mode="dense",
        )

    # Chroma cosine space: distance = 1 - cos_sim → cos_sim = 1 - distance
    distances = res["distances"][0]
    metadatas = res["metadatas"][0]
    documents = res["documents"][0]

    similarities = [max(0.0, 1.0 - d) for d in distances]

    best_idx = int(np.argmax(similarities))
    best_sim = float(similarities[best_idx])
    best_meta = metadatas[best_idx] or {}
    best_doc = documents[best_idx]

    block_threshold = thresholds["block"]
    grey_threshold  = thresholds["grey"]

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
        source=best_meta.get("source"),
        retrieval_mode="dense",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Hybrid minister scan — BM25 + dense + RRF fusion  (the FPR fix)
# ──────────────────────────────────────────────────────────────────────────────

def run_minister_hybrid(
    minister: str,
    text: str,
    collection,
    bm25_index: dict | None,
    embed_fn: Callable[[str], np.ndarray],
    thresholds: dict,
    top_k: int = 10,
    query_vec: np.ndarray | None = None,
) -> MinisterScan:
    """
    Hybrid BM25 + dense retrieval fused with RRF (k=60).

    Why this fixes the FPR:
    - Dense search alone scores abstract L1 patterns too broadly.
      A benign "read src/db.py" can match "agent reading credential files"
      at sim=0.72 because the embedding space conflates intent semantics.
    - BM25 requires lexical keyword overlap. Benign tool calls don't share
      attack keywords (credentials, exfil, malicious, etc.) with attack
      patterns → BM25 ranks them low → RRF fusion pulls their combined
      score below the block threshold.
    - Actual attacks DO share both semantic intent AND lexical keywords
      (e.g. "curl | bash" matches both dense and BM25) → high RRF score.

    RRF scores are in (0, 2/61] ≈ (0, 0.033]. They are NOT cosine similarities.
    The thresholds in config.yaml are calibrated for cosine (0.55–0.725).
    We apply a linear rescaling to map RRF scores onto the [0, 1] cosine range
    so the same threshold config works without changes:

        rescaled = rrf_score / rrf_max_possible × cosine_ceiling

    where rrf_max_possible = 2/(_RRF_K+1) ≈ 0.0328 (perfect rank-1 in both)
    and cosine_ceiling = 1.0 (max cosine similarity).

    This means a document ranked #1 by both retrievers gets rescaled ≈ 1.0,
    and a document ranked #10 by both gets rescaled ≈ 0.087/(0.0328) × ... —
    practically, documents that score well in only one retriever land around
    0.3–0.5; documents scoring poorly in both land below 0.2.

    Falls back to dense-only if bm25_index is None.
    """
    if bm25_index is None or not _BM25_AVAILABLE:
        # Graceful fallback: pure dense search, same as before
        return run_minister(minister, text, collection, embed_fn, thresholds, top_k, query_vec)

    # ── Step 1: Dense retrieval (fetch top_k from ChromaDB) ──────────────────
    # embed-once path: reuse the caller's precomputed vector when provided.
    query_vec = embed_fn(text) if query_vec is None else query_vec
    q_list = query_vec.tolist()

    res = collection.query(
        query_embeddings=[q_list],
        n_results=min(top_k, bm25_index["bm25"].corpus_size),
        include=["distances", "metadatas", "documents", "ids"],
    )

    if not res or not res.get("distances") or not res["distances"][0]:
        return MinisterScan(
            minister=minister,
            verdict="ALLOW",
            confidence=0.0,
            matched_id=None,
            matched_text=None,
            matched_level=None,
            retrieval_mode="hybrid",
        )

    chroma_ids   = res["ids"][0]
    distances    = res["distances"][0]
    metadatas    = res["metadatas"][0]
    documents    = res["documents"][0]

    # Map chroma doc IDs to positions in the BM25 index
    id_to_bm25_pos = {doc_id: i for i, doc_id in enumerate(bm25_index["ids"])}

    # Dense ranks: indices into chroma result list, sorted best-first
    similarities = [max(0.0, 1.0 - d) for d in distances]
    dense_order  = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)

    # ── Step 2: BM25 retrieval ────────────────────────────────────────────────
    query_tokens = _tokenize(text)
    bm25_scores  = bm25_index["bm25"].get_scores(query_tokens)  # shape: (corpus_size,)

    # We only fuse documents that ChromaDB returned (top_k subset).
    # For each chroma result, find its BM25 rank among the full corpus.
    # Sort all corpus docs by BM25 score descending to get global ranks.
    bm25_global_ranks = {
        pos: rank
        for rank, pos in enumerate(np.argsort(bm25_scores)[::-1])
    }

    # For chroma result i, its BM25 rank = bm25_global_ranks[id_to_bm25_pos[id]]
    # If the doc isn't in BM25 index (shouldn't happen), use a very low rank.
    bm25_order = sorted(
        range(len(chroma_ids)),
        key=lambda i: bm25_global_ranks.get(
            id_to_bm25_pos.get(chroma_ids[i], -1),
            len(bm25_scores)  # worst possible rank as default
        )
    )

    # ── Step 3: RRF fusion ────────────────────────────────────────────────────
    fused = _rrf_fuse(dense_order, bm25_order, len(chroma_ids))

    if not fused:
        return MinisterScan(
            minister=minister,
            verdict="ALLOW",
            confidence=0.0,
            matched_id=None,
            matched_text=None,
            matched_level=None,
            retrieval_mode="hybrid",
        )

    # ── Step 4: Rescale RRF score → [0, 1] cosine-comparable range ───────────
    # Max possible RRF score (rank #1 in both lists): 2 / (k+1)
    rrf_max = 2.0 / (_RRF_K + 1)

    best_chroma_idx, best_rrf_raw = fused[0]
    best_rescaled = min(1.0, best_rrf_raw / rrf_max)

    best_meta = metadatas[best_chroma_idx] or {}
    best_doc  = documents[best_chroma_idx]

    # ── Step 5: Verdict ───────────────────────────────────────────────────────
    block_threshold = thresholds["block"]
    grey_threshold  = thresholds["grey"]

    if best_rescaled >= block_threshold:
        verdict = "BLOCK"
    elif best_rescaled >= grey_threshold:
        verdict = "ESCALATE"
    else:
        verdict = "ALLOW"

    return MinisterScan(
        minister=minister,
        verdict=verdict,
        confidence=round(best_rescaled, 4),
        matched_id=best_meta.get("pattern_id"),
        matched_text=best_doc[:240] if best_doc else None,
        matched_level=best_meta.get("level"),
        retrieval_mode="hybrid",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Dual-corpus scan (v1 semantic + technical precision) — unchanged from before
# ──────────────────────────────────────────────────────────────────────────────

def run_minister_dual(
    minister: str,
    text: str,
    collection_v1,
    collection_tech,
    embed_fn,
    thresholds: dict,
    top_k: int = 10,
    query_vec: np.ndarray | None = None,
) -> MinisterScan:
    """Query v1 semantic corpus AND technical precision corpus; return the
    higher-confidence result. Improves recall without raising FPR: v1 catches
    novel intent-level attacks; technical corpus catches exact tool patterns.
    The higher-confidence result is returned; matched_id is tagged ':tech' when
    the technical corpus wins so logs reveal which layer fired.

    Dense-only for both collections (BM25 hybrid is applied at the primary
    collection level via run_minister_hybrid).

    `query_vec`: optional precomputed vector for `text`, shared across both
    corpus scans (embed-once path). When None, each scan embeds independently
    (legacy behaviour).
    """
    r1   = run_minister(minister, text, collection_v1,   embed_fn, thresholds, top_k, query_vec)
    rT   = run_minister(minister, text, collection_tech, embed_fn, thresholds, top_k, query_vec)
    if rT.confidence > r1.confidence:
        return MinisterScan(
            minister=rT.minister,
            verdict=rT.verdict,
            confidence=rT.confidence,
            matched_id=(rT.matched_id or "") + ":tech",
            matched_text=rT.matched_text,
            matched_level=rT.matched_level,
            source=rT.source,
            retrieval_mode="hybrid",
        )
    return r1


# ──────────────────────────────────────────────────────────────────────────────
# Dual-corpus + hybrid scan  (combines both improvements)
# ──────────────────────────────────────────────────────────────────────────────

def run_minister_dual_hybrid(
    minister: str,
    text: str,
    collection_v1,
    collection_tech,
    bm25_index_v1: dict | None,
    embed_fn,
    thresholds: dict,
    top_k: int = 10,
    query_vec: np.ndarray | None = None,
) -> MinisterScan:
    """
    Hybrid RRF retrieval on v1 collection + dense on tech collection.
    Returns the higher-confidence result.

    `query_vec`: optional precomputed vector shared across both scans
    (embed-once path in server.py).
    """
    r1 = run_minister_hybrid(
        minister, text, collection_v1, bm25_index_v1, embed_fn, thresholds, top_k, query_vec
    )
    rT = run_minister(minister, text, collection_tech, embed_fn, thresholds, top_k, query_vec)
    if rT.confidence > r1.confidence:
        return MinisterScan(
            minister=rT.minister,
            verdict=rT.verdict,
            confidence=rT.confidence,
            matched_id=(rT.matched_id or "") + ":tech",
            matched_text=rT.matched_text,
            matched_level=rT.matched_level,
            source=rT.source,
            retrieval_mode="hybrid",
        )
    return r1
