#!/usr/bin/env python3
"""
Replicates parliament/ministers.py's run_minister_hybrid() scoring formula
EXACTLY (RRF for candidate selection, confidence = dense_sim x lexical_gate,
GATE_FLOOR=0.65), but with BGE-M3 dense_vecs + lexical_weights standing in
for BGE-base dense + raw BM25. Uses the isolated bge_m3_index.pkl built by
build_index.py -- never touches production .chroma_kavach or the BM25
indexes built from it.
"""
import pickle, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
_GATE_FLOOR = 0.65  # same constant as parliament/ministers.py

with open(HERE / "bge_m3_index.pkl", "rb") as f:
    INDEX = pickle.load(f)

_model = None


def get_model():
    global _model
    if _model is None:
        from FlagEmbedding import BGEM3FlagModel
        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, devices=["cpu"])
    return _model


def _rrf_fuse(dense_order, sparse_order, n, k=60):
    scores = [0.0] * n
    for rank, idx in enumerate(dense_order):
        scores[idx] += 1.0 / (k + rank)
    for rank, idx in enumerate(sparse_order):
        scores[idx] += 1.0 / (k + rank)
    fused = sorted(range(n), key=lambda i: scores[i], reverse=True)
    return [(i, scores[i]) for i in fused]


def score_call(minister: str, text: str, top_k: int = 10, return_debug: bool = False):
    """Same formula as run_minister_hybrid: dense_sim(selected) x lexical_gate,
    where lexical_gate = GATE_FLOOR + (1-GATE_FLOOR) * (sparse_sel / sparse_qmax),
    RRF used only to pick the best candidate across dense+sparse rankings."""
    corpus = INDEX[minister]
    model = get_model()

    t0 = time.time()
    q = model.encode([text], return_dense=True, return_sparse=True, return_colbert_vecs=False)
    encode_ms = (time.time() - t0) * 1000

    q_dense = q["dense_vecs"][0]
    q_lex = q["lexical_weights"][0]

    dense_vecs = corpus["dense_vecs"]  # (N, dim), already normalized by BGEM3FlagModel default
    sims = dense_vecs @ q_dense  # cosine, since normalize_embeddings=True by default
    n = len(sims)
    top_idx = np.argsort(sims)[::-1][:top_k]

    # sparse score of the query against EVERY corpus doc among the top_k dense
    # candidates (mirrors production: BM25 scored against full corpus, but for
    # apples-to-apples RRF fusion we only need relative order among candidates
    # we'll actually consider -- computing sparse against the full corpus for
    # bm25_qmax equivalent, matching production's "max over the whole corpus"
    # semantics for the query's own best lexical match).
    sparse_scores_full = np.array([
        model.compute_lexical_matching_score(q_lex, lw) for lw in corpus["lexical_weights"]
    ])

    dense_order = list(top_idx)
    sparse_order_full = list(np.argsort(sparse_scores_full)[::-1])
    # restrict sparse_order to the same candidate set the dense side returned,
    # same as production's chroma-result-set restriction
    candidate_set = set(top_idx.tolist())
    sparse_order = [i for i in sparse_order_full if i in candidate_set]
    # pad with any candidates sparse ranking didn't include (shouldn't happen
    # since sparse_order_full covers the whole corpus)
    for i in top_idx:
        if i not in sparse_order:
            sparse_order.append(int(i))

    fused = _rrf_fuse(dense_order, sparse_order, n=n)
    # fused is over ALL n indices scored 0 for non-participants; restrict to
    # candidates that actually appeared in dense_order (mirrors production
    # picking best among the chroma-returned top_k)
    fused_candidates = [(i, s) for i, s in fused if i in candidate_set]
    best_idx, _ = fused_candidates[0]

    dense_sim_sel = float(sims[best_idx])
    sparse_sel = float(sparse_scores_full[best_idx])
    sparse_qmax = float(np.max(sparse_scores_full)) if n else 0.0

    if sparse_qmax <= 1e-9:
        lexical_gate = _GATE_FLOOR
    else:
        lexical_gate = _GATE_FLOOR + (1.0 - _GATE_FLOOR) * min(1.0, max(0.0, sparse_sel) / sparse_qmax)

    confidence = min(1.0, dense_sim_sel * lexical_gate)

    result = {
        "minister": minister, "confidence": round(confidence, 4),
        "dense_sim": round(dense_sim_sel, 4), "sparse_sel": round(sparse_sel, 4),
        "sparse_qmax": round(sparse_qmax, 4), "lexical_gate": round(lexical_gate, 4),
        "matched_id": corpus["metas"][best_idx]["pattern_id"],
        "matched_level": corpus["metas"][best_idx]["level"],
        "matched_text": corpus["docs"][best_idx][:160],
        "encode_ms": round(encode_ms, 1),
    }
    if return_debug:
        result["q_lex_readable"] = model.convert_id_to_token(q_lex)
    return result
