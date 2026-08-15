#!/usr/bin/env python3
"""
Isolated BGE-M3 test index builder. Embeds the LIVE kavach_corpus_v1.json's
CHANNEL and EXECUTOR patterns (read-only; the two ministers needed for the
url/user FP test and the LOLBIN test respectively) with BGE-M3 dense+sparse,
writes a pickle to this scratchpad dir. Does NOT touch .chroma_kavach,
kavach_corpus_v1.json, or any production file.
"""
import json, pickle, time
from pathlib import Path

REPO = Path(r"C:\Users\ishan\Desktop\Kavach")
OUT = Path(__file__).parent

from FlagEmbedding import BGEM3FlagModel

MINISTERS = ["CHANNEL", "EXECUTOR", "VAULT", "NAVIGATOR"]


def pattern_docs(corpus, minister):
    """Same doc rendering the live corpus_loader.py uses: one doc per level
    (L1_intent/L2_mechanism/L3_surface) per pattern, matching production
    granularity so this is an apples-to-apples corpus, not a coarser one."""
    docs, ids, metas = [], [], []
    for p in corpus[minister]["patterns"]:
        for level_key, level_tag in [("L1_intent", "L1"), ("L2_mechanism", "L2"), ("L3_surface", "L3")]:
            text = p.get(level_key)
            if not text:
                continue
            docs.append(text)
            ids.append(f"{p['id']}::{level_tag}")
            metas.append({"pattern_id": p["id"], "level": level_tag})
    return docs, ids, metas


def main():
    corpus = json.loads((REPO / "kavach_corpus_v1.json").read_text(encoding="utf-8"))

    print("[bge-m3] loading model...")
    t0 = time.time()
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, devices=["cpu"])
    print(f"[bge-m3] model loaded in {time.time()-t0:.1f}s")

    index = {}
    for minister in MINISTERS:
        docs, ids, metas = pattern_docs(corpus, minister)
        print(f"[bge-m3] {minister}: embedding {len(docs)} docs...")
        t0 = time.time()
        out = model.encode(docs, return_dense=True, return_sparse=True, return_colbert_vecs=False,
                            batch_size=32)
        elapsed = time.time() - t0
        print(f"[bge-m3] {minister}: embedded in {elapsed:.1f}s ({elapsed/len(docs)*1000:.1f}ms/doc)")
        index[minister] = {
            "docs": docs, "ids": ids, "metas": metas,
            "dense_vecs": out["dense_vecs"], "lexical_weights": out["lexical_weights"],
        }

    out_path = OUT / "bge_m3_index.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(index, f)
    print(f"[bge-m3] wrote index to {out_path}")


if __name__ == "__main__":
    main()
