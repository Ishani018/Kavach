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

import json
import numpy as np

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
# The REAL production Speaker — final verdict combination.
from parliament.speaker import combine_verdicts  # noqa: E402

MINISTERS = ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR")
ROUTER_PATH = REPO_ROOT / "kavach_router_config.json"
COMPASS_CALIB_PATH = REPO_ROOT / "compass_calibration.json"
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

    # Router descriptions (kavach_router_config.json -> routing_corpus). Embed each
    # description ONCE at startup so /simulate never re-embeds them per request.
    # _STATE["router_emb"] = {minister: [(desc, vec), ...]} for the 4 scoring ministers.
    pipe = _STATE["pipe"]
    router_emb: dict = {}
    if ROUTER_PATH.exists():
        rc = json.loads(ROUTER_PATH.read_text()).get("routing_corpus", {})
        for minister in MINISTERS:
            descs = rc.get(minister, []) or []
            router_emb[minister] = [(d, pipe.embed_query(d)) for d in descs]
        n = sum(len(v) for v in router_emb.values())
        print(f"[setup] cached {n} router-description embeddings "
              f"({', '.join(f'{m}:{len(router_emb[m])}' for m in MINISTERS)})",
              file=sys.stderr)
    else:
        print(f"[setup] WARNING: {ROUTER_PATH} not found — /simulate routing disabled",
              file=sys.stderr)
    _STATE["router_emb"] = router_emb

    print(f"\n  Pattern Inspector web UI ready → http://{HOST}:{PORT}\n", file=sys.stderr)


def _cosine(a, b) -> float:
    """Cosine over already-normalized BGE vectors (mirrors server.py _cosine)."""
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) or 1.0))


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


class SimulateReq(BaseModel):
    intent: str = ""
    action: str


@app.post("/simulate")
def simulate(req: SimulateReq):
    """Full parliament pipeline on (intent, action). Wraps the REAL pipeline:
    COMPASS drift (mirror of server _compass_drift), semantic router (mirror of
    server _route, cached embeddings), run_minister_hybrid per activated
    minister, and combine_verdicts (the real Speaker)."""
    action = (req.action or "").strip()
    if not action:
        return JSONResponse({"error": "empty action"}, status_code=400)
    pipe = _STATE["pipe"]
    cfg = _STATE["cfg"]
    th_cfg = cfg["thresholds"]
    action_vec = pipe.embed_query(action)

    # ── Stage 1: COMPASS drift (mirror server.py _compass_drift) ──
    intent = (req.intent or "").strip()
    if intent:
        intent_vec = pipe.embed_query(intent)
        compass_sim = _cosine(intent_vec, action_vec)
        seeded = True
    else:
        compass_sim = 1.0  # no intent seeded → 1.0, exactly like the server
        seeded = False
    compass_drift = compass_sim < float(th_cfg["compass_drift"])

    # ── Stage 2: semantic router (mirror server.py _route, cached embeddings) ──
    router_min = float(th_cfg["router_min"])
    router_emb = _STATE.get("router_emb", {})
    routing = []
    for minister in MINISTERS:
        pairs = router_emb.get(minister, [])
        max_sim = max((_cosine(action_vec, vec) for _, vec in pairs), default=0.0)
        routing.append({"minister": minister, "max_sim": round(max_sim, 4),
                        "activated": max_sim >= router_min})
    activated = [r["minister"] for r in routing if r["activated"]] or list(MINISTERS)

    # ── Stage 3: run_minister_hybrid on activated ministers (REAL) ──
    scans, per_min = [], []
    for minister in activated:
        th = minister_thresholds(cfg, minister)
        scan: MinisterScan = run_minister_hybrid(
            minister, action, pipe.collections[minister], pipe.bm25[minister],
            pipe.embed_query, th, query_vec=action_vec,
        )
        scans.append(scan)
        top = topk_hybrid_matches(minister, action, pipe.collections[minister],
                                  pipe.bm25[minister], action_vec, k=1)
        per_min.append({
            "minister":     minister,
            "verdict":      scan.verdict,
            "confidence":   round(scan.confidence, 4),
            "matched_id":   scan.matched_id,
            "dense_sim":    top[0]["dense_sim"] if top else None,
            "lexical_gate": top[0]["lexical_gate"] if top else None,
            "block":        th["block"],
            "top_text":     _clip(top[0]["text"], 180) if top else None,
        })

    # ── Stage 4: combine_verdicts (the REAL production Speaker) ──
    speaker_th = {"block": float(th_cfg["block"]), "grey": float(th_cfg["grey"]),
                  "compass_drift": float(th_cfg["compass_drift"])}
    sv = combine_verdicts(minister_results=scans, compass_drift=compass_drift,
                          compass_sim=compass_sim, thresholds=speaker_th, traj_risk=0.0)

    return {
        "intent": intent, "action": action,
        "compass": {"sim": round(compass_sim, 4), "drift": compass_drift,
                    "threshold": float(th_cfg["compass_drift"]), "seeded": seeded},
        "routing": {"router_min": router_min, "ministers": routing, "activated": activated},
        "ministers": per_min,
        "verdict": {"final": sv.verdict, "decided_by": sv.decided_by,
                    "confidence": round(sv.confidence, 4), "reason": sv.reason,
                    "blocks": sv.blocks, "escalates": sv.escalates, "allows": sv.allows,
                    "dynamic_threshold_active": sv.dynamic_threshold_active},
    }


class SimilarityReq(BaseModel):
    text_a: str
    text_b: str


@app.post("/similarity")
def similarity(req: SimilarityReq):
    """Raw BGE cosine between two arbitrary phrases (real pipe.embed_query)."""
    a = (req.text_a or "").strip()
    b = (req.text_b or "").strip()
    if not a or not b:
        return JSONResponse({"error": "both text_a and text_b required"}, status_code=400)
    pipe = _STATE["pipe"]
    sim = _cosine(pipe.embed_query(a), pipe.embed_query(b))
    return {"text_a": a, "text_b": b, "cosine": round(sim, 4)}


@app.get("/compass/calibration")
def compass_calibration():
    """Serve the precomputed COMPASS calibration (threshold, tpr, fpr, youden_j,
    distributions, sweep). No recomputation."""
    if not COMPASS_CALIB_PATH.exists():
        return JSONResponse(
            {"error": f"compass_calibration.json not found at {COMPASS_CALIB_PATH}"},
            status_code=404)
    return json.loads(COMPASS_CALIB_PATH.read_text())


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
