#!/usr/bin/env python3
"""
Best-of-both scorer: dense side = BGE-base-en-v1.5 (production, unchanged),
sparse side = BGE-M3 learned lexical_weights (compute_lexical_matching_score),
REPLACING raw BM25. Same production formula as parliament/ministers.py's
run_minister_hybrid(): confidence = dense_sim(selected) x lexical_gate,
GATE_FLOOR=0.65, RRF(k=60) used only to select the best candidate across
the two rankings, not for confidence itself.

Requires bge_m3_index.pkl (lexical_weights + BGE-M3 dense, only lexical
used here) and bge_base_dense_index.pkl (same docs/order, BGE-base dense)
to already exist -- both built by earlier scripts in this dir.
"""
import pickle, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
_GATE_FLOOR = 0.65
PREFIX = "Represent this sentence for searching relevant passages: "

with open(HERE / "bge_m3_index.pkl", "rb") as f:
    M3_INDEX = pickle.load(f)
with open(HERE / "bge_base_dense_index.pkl", "rb") as f:
    BASE_INDEX = pickle.load(f)

_m3_model = None
_base_model = None


def get_m3_model():
    global _m3_model
    if _m3_model is None:
        from FlagEmbedding import BGEM3FlagModel
        _m3_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, devices=["cpu"])
    return _m3_model


def get_base_model():
    global _base_model
    if _base_model is None:
        from sentence_transformers import SentenceTransformer
        _base_model = SentenceTransformer("BAAI/bge-base-en-v1.5")
    return _base_model


def _rrf_fuse(dense_order, sparse_order, n, k=60):
    scores = [0.0] * n
    for rank, idx in enumerate(dense_order):
        scores[idx] += 1.0 / (k + rank)
    for rank, idx in enumerate(sparse_order):
        scores[idx] += 1.0 / (k + rank)
    fused = sorted(range(n), key=lambda i: scores[i], reverse=True)
    return [(i, scores[i]) for i in fused]


def score_call(minister: str, text: str, top_k: int = 10, return_debug: bool = False):
    base_corpus = BASE_INDEX[minister]
    m3_corpus = M3_INDEX[minister]
    base_model = get_base_model()
    m3_model = get_m3_model()

    t0 = time.time()
    q_dense = np.asarray(base_model.encode(PREFIX + text, normalize_embeddings=True), dtype=np.float32)
    base_encode_ms = (time.time() - t0) * 1000

    t0 = time.time()
    m3_out = m3_model.encode([text], return_dense=False, return_sparse=True, return_colbert_vecs=False)
    q_lex = m3_out["lexical_weights"][0]
    m3_encode_ms = (time.time() - t0) * 1000

    dense_vecs = base_corpus["dense_vecs"]  # (N, dim), already normalized
    sims = dense_vecs @ q_dense
    n = len(sims)
    top_idx = np.argsort(sims)[::-1][:top_k]

    sparse_scores_full = np.array([
        m3_model.compute_lexical_matching_score(q_lex, lw) for lw in m3_corpus["lexical_weights"]
    ])

    dense_order = list(top_idx)
    sparse_order_full = list(np.argsort(sparse_scores_full)[::-1])
    candidate_set = set(top_idx.tolist())
    sparse_order = [i for i in sparse_order_full if i in candidate_set]
    for i in top_idx:
        if i not in sparse_order:
            sparse_order.append(int(i))

    fused = _rrf_fuse(dense_order, sparse_order, n=n)
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
        "matched_id": base_corpus["metas"][best_idx]["pattern_id"],
        "matched_level": base_corpus["metas"][best_idx]["level"],
        "matched_text": base_corpus["docs"][best_idx][:160],
        "base_encode_ms": round(base_encode_ms, 1), "m3_encode_ms": round(m3_encode_ms, 1),
        "total_encode_ms": round(base_encode_ms + m3_encode_ms, 1),
    }
    if return_debug:
        result["q_lex_readable"] = m3_model.convert_id_to_token(q_lex)
    return result
