"""
kavach_eval/threat_intel/intel_loader.py
-----------------------------------------
MITRE ATT&CK technique retrieval for the Kavach red-team evasion harness.

Two retrieval modes:
  keyword  — fast BM25-style keyword match over atomic_index.json (335 techniques).
             Default; no model load required.  Used by the baseline run.
  semantic — embedding-RAG over a ChromaDB store built by build_technique_db.py.
             Requires sentence-transformers + chromadb and the persisted DB at
             kavach_eval/threat_intel/technique_db/.

Public API (both modes share the same signature so callers are mode-agnostic):
    get_relevant_techniques(query: str, top_k: int = 5) -> list[dict]
    get_techniques_semantic(query: str, top_k: int = 5) -> list[dict]

Each returned dict has:
    technique_id   : str   e.g. "T1059.001"
    name           : str   e.g. "PowerShell"
    description    : str   short procedure or tactic description
    source         : str   "mitre" | "lolbas" | "gtfobins"
    score          : float relevance score (keyword: overlap ratio; semantic: cosine sim)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_INDEX_PATH = _HERE / "atomic_index.json"
_CHROMADB_PATH = _HERE / "technique_db"

# ---------------------------------------------------------------------------
# Shared lazy state
# ---------------------------------------------------------------------------

_atomic_index: Optional[dict] = None        # loaded once from atomic_index.json
_chroma_collection = None                    # ChromaDB collection (semantic mode)
_embed_model = None                          # SentenceTransformer (semantic mode)


# ---------------------------------------------------------------------------
# Internal: load atomic_index.json
# ---------------------------------------------------------------------------

def _load_index() -> dict:
    global _atomic_index
    if _atomic_index is None:
        if not _INDEX_PATH.exists():
            raise FileNotFoundError(
                f"atomic_index.json not found at {_INDEX_PATH}. "
                "Run build_technique_db.py first to generate it."
            )
        with open(_INDEX_PATH, "r", encoding="utf-8") as fh:
            _atomic_index = json.load(fh)
    return _atomic_index


# ---------------------------------------------------------------------------
# Internal: load ChromaDB + embedding model (lazy, semantic mode only)
# ---------------------------------------------------------------------------

def _load_semantic_backend():
    global _chroma_collection, _embed_model
    if _chroma_collection is not None:
        return  # already loaded

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ImportError(
            "Semantic retrieval requires 'chromadb' and 'sentence-transformers'. "
            "Run: pip install chromadb sentence-transformers --break-system-packages"
        ) from exc

    if not _CHROMADB_PATH.exists():
        raise FileNotFoundError(
            f"ChromaDB not found at {_CHROMADB_PATH}. "
            "Run kavach_eval/threat_intel/build_technique_db.py first."
        )

    client = chromadb.PersistentClient(path=str(_CHROMADB_PATH))
    _chroma_collection = client.get_collection("technique_db")

    # Must use the SAME model as the Kavach parliament (bge-base-en-v1.5)
    _embed_model = SentenceTransformer("BAAI/bge-base-en-v1.5")


# ---------------------------------------------------------------------------
# Keyword retrieval (mode="keyword", default)
# ---------------------------------------------------------------------------

def get_relevant_techniques(query: str, top_k: int = 5) -> list[dict]:
    """
    Fast keyword-overlap retrieval over atomic_index.json.

    Tokenises both the query and each technique entry, scores by unigram
    overlap, and returns the top_k hits sorted by descending score.
    Falls back to an empty list (never raises) so the red-teamer is not
    blocked when threat intel is unavailable.
    """
    try:
        index = _load_index()
    except FileNotFoundError:
        return []

    query_tokens = set(re.findall(r"\b\w+\b", query.lower()))
    if not query_tokens:
        return []

    scored: list[tuple[float, dict]] = []

    for tech_id, entry in index.items():
        # atomic_index.json schema: each entry is
        #   {"technique_name": str, "tests": [{name, description, command,
        #    executor_name, platforms, ...}, ...]}
        technique_name = entry.get("technique_name", "")
        tests = entry.get("tests", [])

        # Build a text blob from the technique name + all its atomic tests.
        parts = [technique_name]
        for t in tests:
            parts.extend([
                t.get("name", ""),
                t.get("description", ""),
                t.get("command", ""),
                t.get("executor_name", ""),
                " ".join(t.get("platforms", [])),
            ])
        blob = " ".join(parts).lower()

        blob_tokens = set(re.findall(r"\b\w+\b", blob))
        overlap = len(query_tokens & blob_tokens)
        if overlap == 0:
            continue

        score = overlap / (len(query_tokens) + 1e-9)

        # Description: first test's description, else the technique name.
        description = (tests[0].get("description", "") if tests else "") or technique_name

        scored.append((score, {
            "technique_id": tech_id,
            "name": technique_name,
            "description": description,
            "source": entry.get("source", "mitre"),
            "score": round(score, 4),
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:top_k]]


# ---------------------------------------------------------------------------
# Semantic retrieval (mode="semantic")
# ---------------------------------------------------------------------------

def get_techniques_semantic(query: str, top_k: int = 5) -> list[dict]:
    """
    Embedding-RAG retrieval over the ChromaDB vector store.

    Uses BAAI/bge-base-en-v1.5 — the same model as Kavach's parliament —
    so retrieved techniques share the same embedding space as the corpus
    Kavach monitors.  This makes generated evasion payloads maximally
    targeted at Kavach's own blind spots.

    Falls back to get_relevant_techniques() if the ChromaDB is not built.
    """
    try:
        _load_semantic_backend()
    except (FileNotFoundError, ImportError):
        # Graceful degradation: fall back to keyword
        return get_relevant_techniques(query, top_k=top_k)

    query_vec = _embed_model.encode(query, normalize_embeddings=True).tolist()

    results = _chroma_collection.query(
        query_embeddings=[query_vec],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        cosine_sim = max(0.0, 1.0 - dist)  # ChromaDB returns L2 distance
        hits.append({
            "technique_id": meta.get("technique_id", "UNKNOWN"),
            "name": meta.get("name", ""),
            "description": doc,
            "source": meta.get("source", "mitre"),
            "score": round(cosine_sim, 4),
        })

    return hits


# ---------------------------------------------------------------------------
# Unified entry point — used by redteam_evasion_v0.py
# ---------------------------------------------------------------------------

def get_techniques(
    query: str,
    top_k: int = 5,
    mode: str = "keyword",
) -> list[dict]:
    """
    Route to keyword or semantic retrieval based on `mode`.

    Args:
        query:  The tool call text or attack description to match against.
        top_k:  Number of techniques to return.
        mode:   "keyword" (default) or "semantic".

    Returns:
        list of dicts, each with keys:
            technique_id, name, description, source, score
    """
    if mode == "semantic":
        return get_techniques_semantic(query, top_k=top_k)
    return get_relevant_techniques(query, top_k=top_k)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "keyword"
    query = sys.argv[2] if len(sys.argv) > 2 else "download file using curl exfiltrate data"

    print(f"\n[intel_loader] mode={mode}  query='{query}'\n")
    results = get_techniques(query, top_k=5, mode=mode)

    if not results:
        print("No results — check atomic_index.json / ChromaDB build.")
        sys.exit(1)

    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['technique_id']}] {r['name']}  (score={r['score']}, src={r['source']})")
        print(f"     {r['description'][:120]}...")
        print()
