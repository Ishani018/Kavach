#!/usr/bin/env python3
"""
parliament/server.py
====================

Kavach Parliament — production HTTP service.

Replaces the Stage-I demo (kavach_parliament_demo.py, port 8080) which used a
hardcoded 25-description corpus and one shared ChromaDB collection. This server
loads the full kavach_corpus_v1.json into FIVE separate collections (one per
minister + COMPASS), uses BGE mean pooling, and applies the asymmetric query
prefix. Same wire format as the Stage-I server so existing callers (the post-
hoc monitor, the embedding lab) keep working.

Default port: 8088 (the OpenClaw plugin defaults to this URL).

Endpoints:
    GET  /health
    POST /hook/seed_intent      — store user intent vector for a session
    POST /hook/check_drift      — COMPASS-only drift check vs stored intent
    POST /hook/parliament       — full pipeline: COMPASS + router + ministers
    GET  /ledger/votes          — recent decisions

Run:
    python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088

Or directly:
    python parliament/server.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import numpy as np
import uvicorn
import yaml
from chromadb.config import Settings
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

# Support both: `uvicorn parliament.server:app` (package mode, relative imports work)
# and `python parliament/server.py` (script mode, need to add project root to path).
try:
    from .ministers import MinisterScan, run_minister, run_minister_dual
    from .speaker import SpeakerVerdict, combine_verdicts
    from . import trajectory as traj
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from parliament.ministers import MinisterScan, run_minister, run_minister_dual
    from parliament.speaker import SpeakerVerdict, combine_verdicts
    from parliament import trajectory as traj

# ──────────────────────────────────────────────────────────────────────────────
# Configuration loading
# ──────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
ROUTER_PATH = ROOT.parent / "kavach_router_config.json"
DB_PATH = ROOT / "kavach_parliament.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("kavach.parliament")


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return yaml.safe_load(CONFIG_PATH.read_text())
    log.warning("config.yaml missing, using defaults")
    return {
        "embed_model": "BAAI/bge-base-en-v1.5",
        "chroma_path": str(ROOT / ".chroma_kavach"),
        "router_config_path": str(ROUTER_PATH),
        "thresholds": {
            "block":          0.65,
            "grey":           0.50,
            "compass_drift":  0.40,
            "router_min":     0.40,
        },
        "query_prefix":
            "Represent this sentence for searching relevant passages: ",
        "ministers": ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"],
        "compass_collection": "COMPASS",
        "host": "127.0.0.1",
        "port": 8088,
    }


CFG = _load_config()


# ──────────────────────────────────────────────────────────────────────────────
# Global state — model, chroma client, router, session intent vectors, ledger
# ──────────────────────────────────────────────────────────────────────────────

from collections import defaultdict

_state: dict[str, Any] = {
    "model":      None,
    "chroma":     None,
    "collections": {},      # minister name → chroma Collection (v1 semantic corpus)
    "tech_collections": {},  # minister name → chroma Collection (technical precision corpus)
    "router":     None,
    "intents":    {},    # session_id → np.ndarray (BGE vector of user intent)
    "history":    defaultdict(traj.new_history),  # session_id → deque[ActionRecord]
}


def _embed_query(text: str) -> np.ndarray:
    """BGE query-side embedding with the asymmetric instruction prefix."""
    prefix = CFG["query_prefix"]
    vec = _state["model"].encode(
        prefix + text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vec, dtype=np.float32)


def _embed_doc(text: str) -> np.ndarray:
    """BGE document-side embedding — no prefix."""
    vec = _state["model"].encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vec, dtype=np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))   # both normalized


# ──────────────────────────────────────────────────────────────────────────────
# Routing — pick which ministers to activate based on cosine distance to each
# minister's domain centroid (precomputed from kavach_router_config.json)
# ──────────────────────────────────────────────────────────────────────────────

def _route(text: str) -> list[str]:
    """Return the list of ministers to activate for this text."""
    q = _embed_query(text)
    activated: list[str] = []
    threshold = CFG["thresholds"]["router_min"]

    for minister, descriptions in _state["router"].items():
        # Score: max cosine across all routing descriptions for this minister.
        max_sim = 0.0
        for desc in descriptions:
            doc_vec = _embed_doc(desc)
            sim = _cosine(q, doc_vec)
            if sim > max_sim:
                max_sim = sim
        if max_sim >= threshold:
            activated.append(minister)

    # Always activate at least one minister — fall back to the highest-scoring
    # one if none crossed the threshold. Better to over-evaluate than to skip.
    if not activated:
        log.info("router: no minister crossed %.2f, falling back to all four",
                 threshold)
        return list(_state["router"].keys())

    return activated


# ──────────────────────────────────────────────────────────────────────────────
# COMPASS drift — cosine between session intent vector and proposed action
# ──────────────────────────────────────────────────────────────────────────────

def _compass_drift(session_id: str, action_text: str,
                   action_vec: np.ndarray | None = None) -> tuple[bool, float]:
    """Return (drift_detected, similarity). If no intent stored, returns (False, 1.0).

    `action_vec`: optional precomputed BGE vector for `action_text` (embed-once
    path). When None, embeds internally (legacy behaviour).
    """
    intent_vec = _state["intents"].get(session_id)
    if intent_vec is None:
        return (False, 1.0)
    if action_vec is None:
        action_vec = _embed_query(action_text)
    sim = _cosine(intent_vec, action_vec)
    drift = sim < CFG["thresholds"]["compass_drift"]
    return (drift, sim)


# ──────────────────────────────────────────────────────────────────────────────
# SQLite ledger
# ──────────────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            correlation_id  TEXT,
            stage           TEXT,
            input_text      TEXT,
            verdict         TEXT,
            decided_by      TEXT,
            confidence      REAL,
            reason          TEXT,
            ministers_json  TEXT,
            compass_sim     REAL,
            traj_risk       REAL,
            latency_ms      REAL
        )
    """)
    # Migrate pre-trajectory DBs: add traj_risk if the table predates it.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(votes)")}
    if "traj_risk" not in cols:
        conn.execute("ALTER TABLE votes ADD COLUMN traj_risk REAL")
    conn.commit()
    conn.close()


def _log_vote(
    session_id: str,
    correlation_id: str,
    stage: str,
    input_text: str,
    verdict: str,
    decided_by: str,
    confidence: float,
    reason: str,
    ministers: dict,
    compass_sim: float | None,
    latency_ms: float,
    traj_risk: float | None = None,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO votes
           (ts, session_id, correlation_id, stage, input_text, verdict,
            decided_by, confidence, reason, ministers_json, compass_sim,
            traj_risk, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            session_id,
            correlation_id,
            stage,
            input_text[:500],
            verdict,
            decided_by,
            confidence,
            reason[:500],
            json.dumps(ministers),
            compass_sim,
            traj_risk,
            latency_ms,
        ),
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Lifespan — load model, chroma collections, router on startup
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("loading BGE model: %s", CFG["embed_model"])
    _state["model"] = SentenceTransformer(CFG["embed_model"])

    # Resolve chroma_path relative to parliament/ directory (ROOT) so that
    # relative paths in config.yaml work regardless of the CWD at launch.
    chroma_path = Path(CFG["chroma_path"])
    if not chroma_path.is_absolute():
        chroma_path = (ROOT.parent / chroma_path).resolve()
    log.info("opening Chroma at: %s", chroma_path)
    chroma_path.mkdir(parents=True, exist_ok=True)
    _state["chroma"] = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(anonymized_telemetry=False),
    )

    # Collection names: attack ministers use kavach_<minister_lower>,
    # COMPASS uses kavach_compass_calibration (matches corpus_loader.py DEFAULT_COLLECTIONS).
    _COLL_NAMES = {
        "EXECUTOR":  "kavach_executor",
        "VAULT":     "kavach_vault",
        "CHANNEL":   "kavach_channel",
        "NAVIGATOR": "kavach_navigator",
        "COMPASS":   "kavach_compass_calibration",
    }
    for minister in CFG["ministers"] + [CFG["compass_collection"]]:
        try:
            coll_name = _COLL_NAMES.get(minister, f"kavach_{minister.lower()}")
            _state["collections"][minister] = (
                _state["chroma"].get_collection(name=coll_name)
            )
            log.info("collection loaded: %s → %s (%d docs)",
                     minister, coll_name, _state["collections"][minister].count())
        except Exception as e:
            log.error(
                "collection %s (name=%s) missing: %s — run corpus_loader.py first",
                minister, _COLL_NAMES.get(minister, "?"), e,
            )
            raise

    # Load technical precision collections (supplementary; non-fatal if absent).
    _TECH_NAMES = {
        "EXECUTOR":  "kavach_executor_tech",
        "VAULT":     "kavach_vault_tech",
        "CHANNEL":   "kavach_channel_tech",
        "NAVIGATOR": "kavach_navigator_tech",
    }
    for _minister in CFG["ministers"]:
        _tname = _TECH_NAMES.get(_minister)
        if not _tname:
            continue
        try:
            _state["tech_collections"][_minister] = (
                _state["chroma"].get_collection(name=_tname)
            )
            log.info("tech collection loaded: %s (%d docs)",
                     _minister, _state["tech_collections"][_minister].count())
        except Exception:
            _state["tech_collections"][_minister] = None
            log.info("tech collection %s not found — using v1 only", _minister)

    log.info("loading router config: %s", CFG["router_config_path"])
    with open(CFG["router_config_path"]) as f:
        _router_full = json.load(f)
    # Extract routing_corpus sub-key (the full JSON has version/description/reversibility_tiers too)
    _state["router"] = _router_full.get("routing_corpus", _router_full)
    # Remove COMPASS from router — it always runs, never needs routing
    _state["router"].pop("COMPASS", None)
    log.info("router loaded ministers: %s", list(_state["router"].keys()))

    _init_db()
    log.info("parliament ready on %s:%d", CFG["host"], CFG["port"])
    yield
    log.info("parliament shutting down")


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Kavach Parliament API",
    version="2.0.0",
    description="Semantic firewall for OpenClaw agents",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Request / response models
# ──────────────────────────────────────────────────────────────────────────────

class IntentRequest(BaseModel):
    text:       str
    session_id: str = "default"


class ParliamentRequest(BaseModel):
    text:       str
    session_id: str = "default"
    context:    dict[str, Any] = Field(default_factory=dict)


class MinisterResult(BaseModel):
    verdict:    str
    confidence: float
    matched_id: str | None = None
    matched_text: str | None = None


class ParliamentResponse(BaseModel):
    verdict:        str
    speaker:        dict[str, Any]
    ministers:      dict[str, MinisterResult]
    pattern:        str
    compass_sim:    float | None
    traj_risk:      float | None = None
    activated:      list[str]
    correlation_id: str
    latency_ms:     float
    ts:             str


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status":      "ok",
        "service":     "Kavach Parliament API",
        "version":     "2.0.0",
        "host":        CFG["host"],
        "port":        CFG["port"],
        "model":       CFG["embed_model"],
        "ministers":   list(CFG["ministers"]),
        "thresholds":  CFG["thresholds"],
        "doc_counts":  {
            m: _state["collections"][m].count()
            for m in CFG["ministers"] + [CFG["compass_collection"]]
        },
        "active_sessions": len(_state["intents"]),
    }


@app.post("/hook/seed_intent")
async def seed_intent(req: IntentRequest) -> dict[str, Any]:
    """Stage II — store user intent vector for COMPASS drift checks."""
    vec = _embed_query(req.text)
    _state["intents"][req.session_id] = vec
    return {
        "ok":         True,
        "session_id": req.session_id,
        "dim":        int(vec.shape[0]),
    }


@app.post("/hook/check_drift")
async def check_drift(req: ParliamentRequest) -> dict[str, Any]:
    """Stage IV — COMPASS-only drift check vs stored intent."""
    drift, sim = _compass_drift(req.session_id, req.text)
    return {
        "session_id":      req.session_id,
        "compass_sim":     sim,
        "drift_detected":  drift,
        "threshold":       CFG["thresholds"]["compass_drift"],
        "verdict":         "BLOCK" if drift else "ALLOW",
    }


@app.post("/hook/parliament", response_model=ParliamentResponse)
async def parliament(req: ParliamentRequest) -> ParliamentResponse:
    """Full pipeline: COMPASS drift + router + activated ministers + speaker."""
    t0 = time.perf_counter()
    correlation_id = req.context.get("correlation_id") or str(uuid.uuid4())

    # Step 0: embed the action ONCE. Shared across COMPASS, ministers, and the
    # trajectory deque — replaces up to 9 redundant embeds of the same text.
    action_vec = _embed_query(req.text)

    # Step 0b: trajectory risk from PRIOR calls in this session (current call
    # not yet appended). Pure cosine math over cached vectors — no embed.
    hist = _state["history"][req.session_id]
    traj_res = traj.trajectory_risk(hist, intent_vec=_state["intents"].get(req.session_id))

    # Step 0c: modulate this call's block threshold by COMPASS + trajectory.
    # A suspicious build-up lowers the bar to BLOCK on this call.
    call_thresholds = dict(CFG["thresholds"])
    call_thresholds["block"] = traj.modulate_threshold(
        base=CFG["thresholds"]["block"],
        compass_sim=None,  # filled after COMPASS below
        traj_risk=traj_res.risk,
    )

    # Step 1: COMPASS drift (reuses action_vec, no re-embed).
    drift, compass_sim = _compass_drift(req.session_id, req.text, action_vec)

    # Recompute the modulated threshold now that compass_sim is known.
    call_thresholds["block"] = traj.modulate_threshold(
        base=CFG["thresholds"]["block"],
        compass_sim=compass_sim if _state["intents"].get(req.session_id) is not None else None,
        traj_risk=traj_res.risk,
    )

    # Step 2: Router selects ministers.
    activated = _route(req.text)

    # Step 3: Run activated ministers in parallel (sharing action_vec + the
    # trajectory-modulated thresholds for this call).
    loop = asyncio.get_event_loop()
    minister_tasks = [
        loop.run_in_executor(
            None,
            run_minister_dual if _state["tech_collections"].get(minister) else run_minister,
            minister,
            req.text,
            _state["collections"][minister],
            *([_state["tech_collections"][minister]]
              if _state["tech_collections"].get(minister) else []),
            _embed_query,
            call_thresholds,
            10,
            action_vec,
        )
        for minister in activated
    ]
    minister_results: list[MinisterScan] = await asyncio.gather(*minister_tasks)

    # Step 4: Speaker combines verdicts (under the modulated thresholds).
    speaker_v: SpeakerVerdict = combine_verdicts(
        minister_results,
        compass_drift=drift,
        compass_sim=compass_sim,
        thresholds=call_thresholds,
    )

    # Step 4b: record THIS action into the session trajectory (reuses the
    # vector; appended after scoring so risk reflects only prior calls).
    traj.record_action(
        hist,
        action_vec=action_vec,
        verdict=speaker_v.verdict,
        confidence=speaker_v.confidence,
        decided_by=speaker_v.decided_by,
    )

    latency_ms = (time.perf_counter() - t0) * 1000.0
    ts = datetime.now(timezone.utc).isoformat()

    minister_dict: dict[str, MinisterResult] = {}
    for r in minister_results:
        minister_dict[r.minister] = MinisterResult(
            verdict=r.verdict,
            confidence=r.confidence,
            matched_id=r.matched_id,
            matched_text=r.matched_text,
        )

    pattern = (
        "intent_drift" if drift and speaker_v.verdict == "BLOCK"
        else (minister_results[0].matched_id if minister_results
              and minister_results[0].verdict == "BLOCK"
              else "none")
    )

    _log_vote(
        session_id=req.session_id,
        correlation_id=correlation_id,
        stage="parliament",
        input_text=req.text,
        verdict=speaker_v.verdict,
        decided_by=speaker_v.decided_by,
        confidence=speaker_v.confidence,
        reason=speaker_v.reason,
        ministers={
            m: {
                "verdict":     r.verdict,
                "confidence":  r.confidence,
                "matched_id":  r.matched_id,
            }
            for m, r in zip(activated, minister_results)
        },
        compass_sim=compass_sim,
        latency_ms=latency_ms,
        traj_risk=round(traj_res.risk, 4),
    )

    return ParliamentResponse(
        verdict=speaker_v.verdict,
        speaker={
            "decided_by": speaker_v.decided_by,
            "confidence": speaker_v.confidence,
            "reason":     speaker_v.reason,
        },
        ministers=minister_dict,
        pattern=pattern,
        compass_sim=compass_sim if drift or _state["intents"].get(req.session_id) is not None else None,
        traj_risk=round(traj_res.risk, 4),
        activated=activated,
        correlation_id=correlation_id,
        latency_ms=round(latency_ms, 2),
        ts=ts,
    )


@app.get("/ledger/votes")
async def ledger(limit: int = 100) -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT ts, session_id, correlation_id, stage, input_text, verdict,
                  decided_by, confidence, reason, ministers_json, compass_sim,
                  traj_risk, latency_ms
           FROM votes ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()

    votes = [
        {
            "ts":             r[0],
            "session_id":     r[1],
            "correlation_id": r[2],
            "stage":          r[3],
            "input":          r[4],
            "verdict":        r[5],
            "decided_by":     r[6],
            "confidence":     r[7],
            "reason":         r[8],
            "ministers":      json.loads(r[9]) if r[9] else {},
            "compass_sim":    r[10],
            "traj_risk":      r[11],
            "latency_ms":     r[12],
        }
        for r in rows
    ]

    return {
        "total":   len(votes),
        "blocked": sum(1 for v in votes if v["verdict"] == "BLOCK"),
        "allowed": sum(1 for v in votes if v["verdict"] == "ALLOW"),
        "escalated": sum(1 for v in votes if v["verdict"] == "ESCALATE"),
        "votes":   votes,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "parliament.server:app",
        host=CFG["host"],
        port=CFG["port"],
        log_level="info",
        reload=False,
    )
