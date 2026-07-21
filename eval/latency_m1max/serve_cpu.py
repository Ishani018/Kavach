"""CPU-pinned parliament server launcher for the M1 Max latency measurement.

The paper's latency claims are CPU-only, but parliament/server.py loads
SentenceTransformer with no device argument, so on Apple Silicon
sentence-transformers auto-selects MPS (verified in the 2026-07-21 server
log: "Use pytorch device_name: mps"). Rather than modify server.py, this
launcher disables MPS visibility BEFORE the server module is imported, so
the exact same code path runs with the embedding model on CPU.

Usage:  .venv_bench/bin/python eval/latency_m1max/serve_cpu.py
"""
import sys
from pathlib import Path

# Script lives at eval/latency_m1max/; the parliament package is at repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch

# sentence-transformers picks its device via torch.backends.mps.is_available()
# (after finding no CUDA). Forcing it to False here pins the model to CPU
# without any change to parliament/server.py.
torch.backends.mps.is_available = lambda: False  # type: ignore[assignment]
assert not torch.backends.mps.is_available()

import uvicorn

if __name__ == "__main__":
    uvicorn.run("parliament.server:app", host="127.0.0.1", port=8088, reload=False)
