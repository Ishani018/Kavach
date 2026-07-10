#!/usr/bin/env python3
"""
Decoupled-candidate-selection variant of parliament/ministers.py's
run_minister_hybrid(). CURRENT MODELS ONLY (BGE-base dense + real BM25) --
no BGE-M3, no model swap. Isolated prototype, not wired into parliament/.

Difference from production (documented in DESIGN.md): production's dense
ChromaDB top_k query is the ONLY candidate source; BM25 only re-ranks
within that set. Here, dense and BM25 EACH independently propose their
own top_k, the two sets are unioned, and RRF fuses over the union. The
confidence formula (dense_sim(selected) x lexical_gate, GATE_FLOOR=0.65)
is UNCHANGED -- only candidate visibility changes.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
import numpy as np

_RRF_K = 60
_GATE_FLOOR = float(os.environ.get("KAVACH_BM25_GATE_FLOOR", "0.65"))


@dataclass
class DecoupledScan:
    minister: str
    verdict: str
    confidence: float
    matched_id: str | None
    matched_text: str | None
    matched_level: str | None
    dense_sim: float
    lexical_gate: float
    candidate_source: str  # "dense_only" | "sparse_only" | "both" -- which retriever(s) proposed the WINNING candidate
    n_dense_only_candidates: int
    n_sparse_only_candidates: int
    n_overlap_candidates: int


def _rrf_fuse_union(dense_ranked: list[int], sparse_ranked: list[int], union_size: int) -> list[tuple[int, float]]:
    """Same RRF formula as production's _rrf_fuse, but over the UNION of
    two independently-proposed candidate sets rather than one list being
    a subset/rerank of the other. A document absent from one retriever's
    list gets that retriever's worst-possible rank (len of the OTHER
    retriever's own top_k list, not the union size -- matches how a
    real retriever would have ranked it if forced to extend, i.e. "just
    past its own cutoff", which is a fairer worst-case than the full
    corpus size)."""
    scores: dict[int, float] = {}
    dense_worst_rank = len(dense_ranked)
    sparse_worst_rank = len(sparse_ranked)

    dense_rank_of = {idx: r for r, idx in enumerate(dense_ranked)}
    sparse_rank_of = {idx: r for r, idx in enumerate(sparse_ranked)}

    all_idx = set(dense_ranked) | set(sparse_ranked)
    for idx in all_idx:
        dr = dense_rank_of.get(idx, dense_worst_rank)
        sr = sparse_rank_of.get(idx, sparse_worst_rank)
        scores[idx] = 1.0 / (_RRF_K + dr + 1) + 1.0 / (_RRF_K + sr + 1)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def score_call_decoupled(
    minister: str,
    text: str,
    dense_vecs: np.ndarray,       # (N, dim) full-corpus dense vectors, precomputed
    bm25_index,                    # BM25Okapi instance
    docs: list[str],
    ids: list[str],
    metas: list[dict],
    embed_fn,                      # callable(text) -> query dense vector
    tokenize_fn,                   # callable(text) -> list[str] tokens
    thresholds: dict,              # {"block": float, "grey": float}
    top_k: int = 10,
) -> DecoupledScan:
    n = len(docs)

    # ── Dense side: its OWN top_k, independent of sparse ──────────────────
    q_dense = embed_fn(text)
    sims = dense_vecs @ q_dense  # cosine, vectors pre-normalized
    dense_top = list(np.argsort(sims)[::-1][:top_k])

    # ── Sparse side: its OWN top_k, independent of dense (THE FIX) ────────
    query_tokens = tokenize_fn(text)
    bm25_scores = bm25_index.get_scores(query_tokens)
    sparse_top = list(np.argsort(bm25_scores)[::-1][:top_k])

    dense_set = set(int(i) for i in dense_top)
    sparse_set = set(int(i) for i in sparse_top)
    n_dense_only = len(dense_set - sparse_set)
    n_sparse_only = len(sparse_set - dense_set)
    n_overlap = len(dense_set & sparse_set)

    # ── RRF fusion over the UNION (not restricted to dense's candidates) ──
    fused = _rrf_fuse_union(dense_top, sparse_top, union_size=len(dense_set | sparse_set))

    if not fused:
        return DecoupledScan(
            minister=minister, verdict="ALLOW", confidence=0.0,
            matched_id=None, matched_text=None, matched_level=None,
            dense_sim=0.0, lexical_gate=_GATE_FLOOR, candidate_source="none",
            n_dense_only_candidates=n_dense_only, n_sparse_only_candidates=n_sparse_only,
            n_overlap_candidates=n_overlap,
        )

    best_idx, _ = fused[0]

    dense_sim_sel = float(sims[best_idx])
    bm25_sel = float(bm25_scores[best_idx])
    bm25_qmax = float(np.max(bm25_scores)) if n else 0.0

    if bm25_qmax <= 1e-9:
        lexical_gate = _GATE_FLOOR
    else:
        lexical_gate = _GATE_FLOOR + (1.0 - _GATE_FLOOR) * min(1.0, max(0.0, bm25_sel) / bm25_qmax)

    confidence = min(1.0, dense_sim_sel * lexical_gate)

    if best_idx in dense_set and best_idx in sparse_set:
        source = "both"
    elif best_idx in dense_set:
        source = "dense_only"
    else:
        source = "sparse_only"

    block_th, grey_th = thresholds["block"], thresholds["grey"]
    if confidence >= block_th:
        verdict = "BLOCK"
    elif confidence >= grey_th:
        verdict = "ESCALATE"
    else:
        verdict = "ALLOW"

    return DecoupledScan(
        minister=minister, verdict=verdict, confidence=round(confidence, 4),
        matched_id=metas[best_idx].get("pattern_id"), matched_text=docs[best_idx][:240],
        matched_level=metas[best_idx].get("level"),
        dense_sim=round(dense_sim_sel, 4), lexical_gate=round(lexical_gate, 4),
        candidate_source=source,
        n_dense_only_candidates=n_dense_only, n_sparse_only_candidates=n_sparse_only,
        n_overlap_candidates=n_overlap,
    )
