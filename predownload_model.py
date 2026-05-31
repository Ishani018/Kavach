#!/usr/bin/env python3
"""
predownload_model.py
====================

Pre-downloads the BGE embedding model BEFORE you need it, so that corpus
loading, calibration, and the parliament don't stall on a slow or blocked
network at the worst possible moment.

WHY THIS MATTERS:
Everything in Kavach depends on BAAI/bge-base-en-v1.5, which is fetched from
huggingface.co the first time any script calls SentenceTransformer(). Many
campus / lab networks throttle or block huggingface. If that happens mid-run,
you get a confusing "couldn't connect to huggingface.co" error and nothing
works.

Run this FIRST, once, on the Dell. If it succeeds, the model is cached at
~/.cache/huggingface and every later script loads it instantly offline.

    python predownload_model.py

If the lab network blocks huggingface entirely, run this on a network that
works (your phone hotspot, home wifi), then the cache travels with the machine
— or copy ~/.cache/huggingface to the Dell manually.

After this succeeds once, you can even run fully offline:
    export HF_HUB_OFFLINE=1
"""

import sys
import time

MODEL = "BAAI/bge-base-en-v1.5"

def main():
    print(f"Pre-downloading {MODEL} ...")
    print("(first run pulls ~440MB; later runs are instant from cache)")
    t0 = time.time()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed.")
        print("Run: pip install -r requirements.txt --break-system-packages")
        sys.exit(1)

    try:
        model = SentenceTransformer(MODEL)
    except Exception as e:
        print(f"\nFAILED to download model: {e}")
        print("\nIf this is a network block on huggingface.co:")
        print("  1. Connect to a network that allows huggingface (phone hotspot)")
        print("  2. Re-run this script")
        print("  3. The model caches to ~/.cache/huggingface and persists")
        print("  4. Then on the lab network: export HF_HUB_OFFLINE=1")
        sys.exit(1)

    # Sanity check: actually embed something
    vec = model.encode("test sentence", normalize_embeddings=True)
    dt = time.time() - t0
    print(f"\nSUCCESS in {dt:.1f}s")
    print(f"Model cached. Embedding dimension: {len(vec)}")
    print("All Kavach scripts will now load this model instantly.")
    print("\nTo force offline mode on a blocked network:")
    print("  export HF_HUB_OFFLINE=1")

if __name__ == "__main__":
    main()
