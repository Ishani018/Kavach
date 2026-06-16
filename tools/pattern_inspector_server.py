#!/usr/bin/env python3
# =============================================================================
# tools/pattern_inspector_server.py — local web backend for the pattern inspector
# =============================================================================
#
#   A thin local HTTP wrapper around tools/pattern_inspector.py. It REUSES that
#   module's real-pipeline scoring (BGE bge-base-en-v1.5 + Chroma + BM25 +
#   run_minister_hybrid) — no scoring math is reimplemented here. It just
#   assembles the existing functions' output into JSON and serves a single-page
#   HTML frontend.
#
#   DEV DIAGNOSTIC ONLY. Same disclaimer as the CLI: scores guide pattern work,
#   they are NOT a substitute for the Dell benchmark. Do not cite these numbers.
#
#   Run:   python tools/pattern_inspector_server.py
#   Open:  http://127.0.0.1:8077
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# Reuse the EXISTING inspector logic — do not reimplement scoring.
from tools.pattern_inspector import (  # noqa: E402
    LivePipeline,
    topk_hybrid_matches,
    run_minister_hybrid,
    minister_thresholds,
    verdict_for,
    load_config,
    load_corpus_index,
    _clip,
    MinisterScan,
)

MINISTERS = ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR")
HTML_PATH = Path(__file__).resolve().parent / "pattern_inspector_web.html"
HOST = "127.0.0.1"
PORT = 8077

app = FastAPI(title="Kavach Pattern Inspector (web)")

# Loaded once at startup (BGE model + Chroma + BM25 + corpus index).
_STATE: dict = {}


@app.on_event("startup")
def _startup() -> None:
    cfg = load_config()
    # LivePipeline loads BGE + Chroma + BM25 exactly as the CLI does. It calls
    # sys.exit() if Chroma is missing — acceptable: fail fast before serving.
    _STATE["cfg"] = cfg
    _STATE["pipe"] = LivePipeline(cfg)
    _STATE["corpus"] = load_corpus_index()
    print(f"\n  Pattern Inspector web UI ready → http://{HOST}:{PORT}\n", file=sys.stderr)


# ── Scoring assembly (reuses run_minister_hybrid + topk_hybrid_matches) ──────

def _inspect(text: str) -> dict:
    pipe = _STATE["pipe"]
    cfg = _STATE["cfg"]
    qvec = pipe.embed_query(text)
    ministers_out = []
    for minister in MINISTERS:
        th = minister_thresholds(cfg, minister)
        coll = pipe.collections[minister]
        bm25 = pipe.bm25[minister]

        scan: MinisterScan = run_minister_hybrid(
            minister, text, coll, bm25, pipe.embed_query, th, query_vec=qvec,
        )
        top = topk_hybrid_matches(minister, text, coll, bm25, qvec, k=3)
        top_out = [{
            "pattern_id":   c["pattern_id"],
            "level":        c["level"],
            "category":     c.get("category", ""),
            "dense_sim":    c["dense_sim"],
            "lexical_gate": c["lexical_gate"],
            "confidence":   c["confidence"],
            "verdict":      verdict_for(c["confidence"], th),
            "text":         _clip(c["text"], 220),
        } for c in top]

        # The single-best verdict (source of truth) is scan; expose its
        # confidence + the gate from the matching top-1 candidate for display.
        best_gate = top_out[0]["lexical_gate"] if top_out else None
        best_dense = top_out[0]["dense_sim"] if top_out else None
        ministers_out.append({
            "minister":     minister,
            "verdict":      scan.verdict,
            "confidence":   round(scan.confidence, 4),
            "dense_sim":    best_dense,
            "lexical_gate": best_gate,
            "block":        th["block"],
            "grey":         th["grey"],
            "retrieval_mode": scan.retrieval_mode,
            "top3":         top_out,
        })
    return {"action": text, "ministers": ministers_out}


def _corpus_search(minister: str | None, q: str) -> list[dict]:
    corpus = _STATE["corpus"]
    q = (q or "").strip().lower()
    out = []
    for pid, info in corpus.items():
        if minister and minister != "ALL" and info["minister"] != minister:
            continue
        if q:
            blob = f"{pid} {info['L1']} {info['L2']} {info['L3']} {info['category']}".lower()
            if q not in blob:
                continue
        out.append({
            "id":       pid,
            "minister": info["minister"],
            "category": info["category"],
            "L1":       info["L1"],
            "L2":       info["L2"],
            "L3":       info["L3"],
        })
    out.sort(key=lambda r: r["id"])
    return out[:200]  # cap


# ── Routes ───────────────────────────────────────────────────────────────────

class InspectReq(BaseModel):
    text: str


@app.get("/")
def index():
    if not HTML_PATH.exists():
        return JSONResponse({"error": f"frontend not found: {HTML_PATH}"}, status_code=500)
    return FileResponse(str(HTML_PATH), media_type="text/html")


@app.get("/health")
def health():
    pipe = _STATE.get("pipe")
    counts = {m: pipe.collections[m].count() for m in MINISTERS} if pipe else {}
    return {"ok": pipe is not None, "ministers": list(MINISTERS), "doc_counts": counts}


@app.post("/inspect")
def inspect(req: InspectReq):
    text = (req.text or "").strip()
    if not text:
        return JSONResponse({"error": "empty text"}, status_code=400)
    return _inspect(text)


@app.get("/corpus")
def corpus(minister: str = "ALL", q: str = ""):
    return {"minister": minister, "q": q, "results": _corpus_search(minister, q)}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
