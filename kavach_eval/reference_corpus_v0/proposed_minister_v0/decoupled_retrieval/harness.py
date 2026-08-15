#!/usr/bin/env python3
"""
Shared harness: loads the isolated test_chroma_ablation store (BGE-base
dense, already built this investigation, includes CHAN-102), builds real
BM25 indexes exactly as production does, and exposes score_production()
and score_decoupled() with identical signatures for direct comparison.
"""
import sys
from pathlib import Path
import numpy as np
import yaml
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

REPO = Path(r"C:\Users\ishan\Desktop\Kavach")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from parliament.ministers import run_minister_hybrid, build_bm25_index, _tokenize
from decoupled_ministers import score_call_decoupled

SCRATCH_CHROMA = Path(r"C:\Users\ishan\AppData\Local\Temp\claude\c--Users-ishan-Desktop-Kavach\ef4b1a3b-08ff-424c-87f9-f88516cb207f\scratchpad\ablation\test_chroma_ablation")
PREFIX = "Represent this sentence for searching relevant passages: "
COLL = {"EXECUTOR": "kavach_executor", "VAULT": "kavach_vault",
        "CHANNEL": "kavach_channel", "NAVIGATOR": "kavach_navigator"}
THRESH = {"EXECUTOR": 0.55, "VAULT": 0.75, "CHANNEL": 0.6, "NAVIGATOR": 0.7}
GREY = 0.5

cfg = yaml.safe_load((REPO / "parliament" / "config.yaml").read_text())
_model = SentenceTransformer("BAAI/bge-base-en-v1.5")


def embed_fn(text):
    return np.asarray(_model.encode(PREFIX + text, normalize_embeddings=True), dtype=np.float32)


client = chromadb.PersistentClient(path=str(SCRATCH_CHROMA), settings=Settings(anonymized_telemetry=False))
collections = {m: client.get_collection(name=c) for m, c in COLL.items()}
bm25_indexes = {m: build_bm25_index(collections[m]) for m in COLL}

# For the decoupled scorer we need the FULL dense vector matrix per
# minister (not just chroma's top_k) -- fetch once, cache.
_dense_cache = {}
for m in COLL:
    res = collections[m].get(include=["embeddings", "documents", "metadatas"])
    _dense_cache[m] = {
        "dense_vecs": np.asarray(res["embeddings"], dtype=np.float32),
        "docs": res["documents"], "ids": res["ids"], "metas": res["metadatas"],
    }
    # sanity: order must match bm25_index's own ids order for index alignment
    assert _dense_cache[m]["ids"] == bm25_indexes[m]["ids"], f"{m}: id order mismatch between chroma.get() and bm25_index"


def score_production(minister: str, text: str, top_k: int = 10):
    scan = run_minister_hybrid(
        minister=minister, text=text, collection=collections[minister],
        bm25_index=bm25_indexes[minister], embed_fn=embed_fn,
        thresholds={"block": THRESH[minister], "grey": GREY}, top_k=top_k,
    )
    return scan


def score_decoupled(minister: str, text: str, top_k: int = 10):
    cache = _dense_cache[minister]
    return score_call_decoupled(
        minister=minister, text=text,
        dense_vecs=cache["dense_vecs"], bm25_index=bm25_indexes[minister]["bm25"],
        docs=cache["docs"], ids=cache["ids"], metas=cache["metas"],
        embed_fn=embed_fn, tokenize_fn=_tokenize,
        thresholds={"block": THRESH[minister], "grey": GREY}, top_k=top_k,
    )
