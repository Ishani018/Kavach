"""
corpus_loader.py
================

Loads kavach_corpus_v1.json into five separate ChromaDB collections, one per
minister (EXECUTOR, VAULT, CHANNEL, NAVIGATOR, COMPASS), embedding each pattern
description with BAAI/bge-base-en-v1.5.

Run order on the lab system:
    1. python corpus_loader.py --rebuild
    2. python compass_calibrator.py        # uses the COMPASS collection
    3. python -m pytest parliament/test_speaker.py

Author: Kavach team (Chain of Trust, PES University 2026)
Status: Standalone module. No dependencies on the live parliament server.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CORPUS_PATH      = Path(__file__).parent / "kavach_corpus_v1.json"
TECH_CORPUS_PATH = Path(__file__).parent / "kavach_corpus_technical.json"
CHROMA_PATH = Path(__file__).parent / "parliament" / ".chroma_kavach"
# Default embedding model. KAVACH_EMBED_MODEL env var overrides it (so the loader
# and the parliament server can be pointed at the same non-default model for an
# embedding-comparison run without editing this file); --embed-model overrides both.
EMBED_MODEL_NAME = os.environ.get("KAVACH_EMBED_MODEL", "BAAI/bge-base-en-v1.5")

# Collection names (must match what parliament/server.py queries).
# Pulled from the JSON's `collections` block at runtime; defined here as
# a fallback if the JSON is missing the field.
DEFAULT_COLLECTIONS: Dict[str, str] = {
    "EXECUTOR":  "kavach_executor",
    "VAULT":     "kavach_vault",
    "CHANNEL":   "kavach_channel",
    "NAVIGATOR": "kavach_navigator",
    "COMPASS":   "kavach_compass_calibration",
}

# Levels stored per attack pattern. COMPASS does NOT use these.
ATTACK_LEVELS = ("L1_intent", "L2_mechanism", "L3_surface")
ATTACK_MINISTERS = ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR")


# ---------------------------------------------------------------------------
# Model-specific asymmetric-retrieval prefixes
# ---------------------------------------------------------------------------
# Retrieval encoders differ in how they want queries vs. documents prefixed, and
# using the wrong prefix silently degrades a model (e.g. querying an e5 index that
# was built bare, or prepending BGE's instruction to gte which wants none). For a
# FAIR embedding comparison each model must use ITS OWN convention on BOTH sides.
#   BGE : instruction prefix on queries, documents bare.
#   e5  : "query: " on queries, "passage: " on documents (asymmetric — the index
#         MUST be built with "passage: " or the query prefix cannot help).
#   gte : no prefix on either side (plain sentence encoder).
# Detection is by model-name substring; anything unrecognized falls back to BGE's
# behavior, so the default (no --embed-model) path is byte-identical to before.
_PREFIXES = {
    # model-name substring : (query_prefix, doc_prefix)
    "bge": ("Represent this sentence for searching relevant passages: ", ""),
    "e5":  ("query: ", "passage: "),
    "gte": ("", ""),
}


def _prefixes_for(model_name: str) -> tuple[str, str]:
    """Return (query_prefix, doc_prefix) for a model name. Falls back to BGE."""
    ml = model_name.lower()
    for key, pair in _PREFIXES.items():
        if key in ml:
            return pair
    return _PREFIXES["bge"]


# ---------------------------------------------------------------------------
# BGE wrapper
# ---------------------------------------------------------------------------

class BGEEmbedder:
    """
    Lazy-loaded sentence-embedding wrapper (default BAAI/bge-base-en-v1.5).

    Query/document prefixes are model-specific and auto-detected from the model
    name (see _prefixes_for): BGE prefixes queries only; e5 prefixes both sides
    asymmetrically; gte prefixes neither. This keeps an embedding comparison fair
    — each model uses its own convention on both the index and the query side.
    """

    def __init__(self, model_name: str = EMBED_MODEL_NAME) -> None:
        print(f"[loader] loading {model_name} ...", flush=True)
        t0 = time.time()
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.query_prefix, self.doc_prefix = _prefixes_for(model_name)
        print(f"[loader] loaded in {time.time()-t0:.1f}s  dim={self.dim}  "
              f"query_prefix={self.query_prefix!r}  doc_prefix={self.doc_prefix!r}",
              flush=True)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed corpus documents (with the model's doc prefix, if any)."""
        embs = self.model.encode(
            [self.doc_prefix + t for t in texts] if self.doc_prefix else texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return embs.tolist()

    def embed_query(self, text: str) -> List[float]:
        """Embed a query (with the model's query prefix, if any)."""
        emb = self.model.encode(
            self.query_prefix + text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return emb.tolist()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_corpus_file(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"corpus file not found at {path}")
    with path.open() as f:
        corpus = json.load(f)
    print(f"[loader] read corpus v{corpus.get('version', '?')} from {path}")
    return corpus


def get_chroma_client(persist_dir: Path) -> chromadb.PersistentClient:
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False),
    )


def reset_collection(client: chromadb.PersistentClient, name: str):
    """
    Delete and recreate a collection with cosine distance space.

    ChromaDB cosine space: distance in [0, 2]; sim = 1.0 - distance.
    The earlier shared-collection code used the wrong formula assuming L2;
    this fixes it at the schema level.
    """
    try:
        client.delete_collection(name=name)
    except Exception:
        pass
    return client.create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Minister loaders
# ---------------------------------------------------------------------------

def load_attack_minister(
    client: chromadb.PersistentClient,
    embedder: BGEEmbedder,
    minister: str,
    patterns: List[dict],
    collection_name: str,
) -> int:
    """
    Load one of EXECUTOR / VAULT / CHANNEL / NAVIGATOR.

    Each pattern produces three documents (one per level). Returns total docs
    indexed for that minister.
    """
    coll = reset_collection(client, collection_name)

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[dict] = []

    missing_levels = 0

    for pat in patterns:
        pid = pat["id"]
        for level in ATTACK_LEVELS:
            text = pat.get(level)
            if not text:
                missing_levels += 1
                continue
            ids.append(f"{pid}_{level}")
            documents.append(text)
            metadatas.append({
                "minister":   minister,
                "pattern_id": pid,
                "category":   pat.get("category", "uncategorized"),
                "level":      level,
                "source":     pat.get("source", ""),
                "rationale":  pat.get("rationale", ""),
            })

    if not ids:
        raise ValueError(f"no documents to index for {minister}")

    print(f"[{minister:<9}] embedding {len(ids):>4} documents ...", flush=True)
    t0 = time.time()
    embeddings = embedder.embed_documents(documents)
    coll.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    elapsed = time.time() - t0
    print(f"[{minister:<9}] indexed in {elapsed:.1f}s "
          f"({missing_levels} missing levels skipped)")

    return len(ids)


def load_compass(
    client: chromadb.PersistentClient,
    embedder: BGEEmbedder,
    pairs: List[dict],
    collection_name: str,
) -> int:
    """
    Load the COMPASS calibration pairs.

    Each pair contributes two documents: one for user_intent, one for
    proposed_action. Both carry pair_id and label metadata so the calibrator
    can reconstruct (intent, action, label) triples for Youden's J.
    """
    coll = reset_collection(client, collection_name)

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[dict] = []

    for pair in pairs:
        pid = pair["id"]
        label = pair["label"]
        ids.extend([f"{pid}_intent", f"{pid}_action"])
        documents.extend([pair["user_intent"], pair["proposed_action"]])
        metadatas.extend([
            {"pair_id": pid, "label": label, "role": "intent",
             "rationale": pair.get("rationale", "")},
            {"pair_id": pid, "label": label, "role": "action",
             "rationale": pair.get("rationale", "")},
        ])

    print(f"[COMPASS  ] embedding {len(ids):>4} documents ({len(pairs)} pairs)...", flush=True)
    t0 = time.time()
    embeddings = embedder.embed_documents(documents)
    coll.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    print(f"[COMPASS  ] indexed in {time.time()-t0:.1f}s")

    return len(ids)


# ---------------------------------------------------------------------------
# Smoke test (post-load self-query)
# ---------------------------------------------------------------------------

def smoke_test(
    client: chromadb.PersistentClient,
    embedder: BGEEmbedder,
    collections: Dict[str, str],
) -> bool:
    """
    For each attack minister, embed one of its own L2_mechanism strings and
    check that the top hit is the same pattern_id with similarity >= 0.95.

    Validates:
      (a) The 1.0 - distance conversion is correct.
      (b) Per-collection isolation works (EXECUTOR queries don't bleed into VAULT).
    """
    print("\n[smoke] running self-query smoke test ...")
    all_ok = True

    for minister in ATTACK_MINISTERS:
        coll_name = collections[minister]
        coll = client.get_collection(name=coll_name)

        sample = coll.get(limit=1, include=["documents", "metadatas"])
        if not sample["documents"]:
            print(f"[smoke] {minister} collection empty — FAIL")
            all_ok = False
            continue

        sample_text = sample["documents"][0]
        sample_pid = sample["metadatas"][0]["pattern_id"]

        # Use embed_documents (no prefix) to match how corpus was indexed.
        q_emb = embedder.embed_documents([sample_text])[0]
        result = coll.query(query_embeddings=[q_emb], n_results=1,
                            include=["distances", "metadatas"])

        top_distance = result["distances"][0][0]
        top_pid = result["metadatas"][0][0]["pattern_id"]
        similarity = 1.0 - top_distance

        ok = (top_pid == sample_pid) and (similarity >= 0.95)
        status = "OK  " if ok else "FAIL"
        print(f"[smoke] {minister:<9} self-query "
              f"top={top_pid} sim={similarity:.3f} ... {status}")
        if not ok:
            all_ok = False

    # Cross-collection isolation check
    exec_text = "Agent piping curl output to bash for immediate execution"
    exec_q = embedder.embed_query(exec_text)
    vault_coll = client.get_collection(name=collections["VAULT"])
    vault_top_dist = vault_coll.query(
        query_embeddings=[exec_q], n_results=1, include=["distances"]
    )["distances"][0][0]
    vault_top_sim = 1.0 - vault_top_dist
    ok_cross = vault_top_sim < 0.7
    print(f"[smoke] cross-leak  EXECUTOR-shaped query vs VAULT "
          f"max_sim={vault_top_sim:.3f} ({'OK' if ok_cross else 'WARN: high bleed'})")

    return all_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load kavach_corpus_v1.json into ChromaDB collections."
    )
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH,
                        help="path to kavach_corpus_v1.json")
    parser.add_argument("--chroma", type=Path, default=CHROMA_PATH,
                        help="ChromaDB persistence directory")
    parser.add_argument("--rebuild", action="store_true",
                        help="reset and reload all collections (default action)")
    parser.add_argument("--skip-smoke", action="store_true",
                        help="skip the post-load self-query smoke test")
    parser.add_argument("--embed-model", default=EMBED_MODEL_NAME,
                        help="sentence-transformers embedding model to index with "
                             "(default: %(default)s; also settable via "
                             "KAVACH_EMBED_MODEL). Use a scratch --chroma dir when "
                             "building with a non-default model.")
    args = parser.parse_args()

    corpus = load_corpus_file(args.corpus)
    collections = corpus.get("collections", DEFAULT_COLLECTIONS)

    embedder = BGEEmbedder(model_name=args.embed_model)
    client = get_chroma_client(args.chroma)

    total = 0
    for minister in ATTACK_MINISTERS:
        if minister not in corpus:
            print(f"[loader] WARN corpus missing {minister}, skipping")
            continue
        total += load_attack_minister(
            client, embedder, minister,
            corpus[minister]["patterns"],
            collections[minister],
        )

    if "COMPASS" in corpus and "pairs" in corpus["COMPASS"]:
        total += load_compass(
            client, embedder, corpus["COMPASS"]["pairs"], collections["COMPASS"]
        )
    else:
        print("[loader] WARN corpus missing COMPASS.pairs, skipping calibration set")

    # Load technical precision corpus (supplementary; OK if absent).
    #total += load_technical_corpus(client, embedder)

    print(f"\n[loader] indexed {total} documents across {len(collections)} collections")
    print(f"[loader] persisted to {args.chroma.resolve()}")

    if not args.skip_smoke:
        ok = smoke_test(client, embedder, collections)
        if not ok:
            print("\n[loader] SMOKE TEST FAILED — investigate before running parliament")
            sys.exit(1)
        print("\n[loader] all smoke tests passed")


if __name__ == "__main__":
    main()
