#!/usr/bin/env python3
"""
Best-of-both harness, step 1: build a BGE-base-en-v1.5 dense index over
the EXACT SAME docs/ids/order as bge_m3_index.pkl (built by build_index.py),
so the two indexes can be combined by position for the best-of-both test
(BGE-base dense + BGE-M3 sparse). Read-only against the live corpus.
"""
import json, pickle, time
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer

REPO = Path(r"C:\Users\ishan\Desktop\Kavach")
HERE = Path(__file__).parent
PREFIX = "Represent this sentence for searching relevant passages: "

with open(HERE / "bge_m3_index.pkl", "rb") as f:
    m3_index = pickle.load(f)

model = SentenceTransformer("BAAI/bge-base-en-v1.5")

out = {}
for minister, data in m3_index.items():
    docs = data["docs"]
    print(f"[bge-base] {minister}: embedding {len(docs)} docs (same order as BGE-M3 index)...")
    t0 = time.time()
    # production corpus_loader.py embeds DOCUMENTS without the query prefix
    # (prefix is query-side only) -- confirmed via corpus_loader.py's
    # embed_documents() vs embed_query() split. Match that here.
    dense_vecs = model.encode(docs, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    elapsed = time.time() - t0
    print(f"[bge-base] {minister}: embedded in {elapsed:.1f}s ({elapsed/len(docs)*1000:.1f}ms/doc)")
    out[minister] = {
        "docs": docs, "ids": data["ids"], "metas": data["metas"],
        "dense_vecs": np.asarray(dense_vecs, dtype=np.float32),
    }

out_path = HERE / "bge_base_dense_index.pkl"
with open(out_path, "wb") as f:
    pickle.dump(out, f)
print(f"[bge-base] wrote {out_path}")
