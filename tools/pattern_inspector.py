#!/usr/bin/env python3
# =============================================================================
# tools/pattern_inspector.py  —  DEV / DIAGNOSTIC TOOL, *NOT* PRODUCTION CODE.
# =============================================================================
#
#   This is a local, offline aid for iteratively improving minister patterns
#   before the July 2 Dell run. It is deliberately NOT in parliament/ and is
#   never imported by the live server. It exists so you can build intuition
#   about *why* a given action matches a given attack pattern, and which
#   corpus patterns are responsible for real benign false positives.
#
#   ── READ THIS DISCLAIMER ──────────────────────────────────────────────
#   The cosine / hybrid scores this tool prints GUIDE pattern work; they are
#   NOT a substitute for the Dell benchmark. Any FPR or recall change you
#   think you see here is a HYPOTHESIS until it is re-measured on the Dell
#   (InjecAgent DH/DS + benign gate). This tool is for diagnosis and
#   intuition, not for producing reportable numbers. Do not quote a number
#   from this tool in the paper.
#
#   FIDELITY: to make the scores track the real pipeline, this tool uses the
#   REAL production embedding (BAAI/bge-base-en-v1.5 via sentence-transformers,
#   exact query prefix from parliament/config.yaml), the REAL Chroma corpus
#   collections built by corpus_loader.py, the REAL BM25 index builder, and
#   the REAL thresholds from parliament/config.yaml. The single-best verdict
#   is computed by calling parliament.ministers.run_minister_hybrid directly.
#   The top-3 view (feature 1) MIRRORS the dense-query + RRF-selection +
#   lexical-gate math of run_minister_hybrid — reusing its own _tokenize,
#   _rrf_fuse, _RRF_K and _GATE_FLOOR — to expose more than the single match
#   the production function returns. parliament/ministers.py remains the
#   source of truth; if it changes, re-check the mirror below.
# =============================================================================

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Production code — single source of truth for retrieval/fusion/gate math.
from parliament.ministers import (  # noqa: E402
    MinisterScan,
    build_bm25_index,
    run_minister_hybrid,
    _tokenize,
    _rrf_fuse,
    _RRF_K,
    _GATE_FLOOR,
)

# Must match parliament/server.py:_COLL_NAMES exactly.
COLL_NAMES = {
    "EXECUTOR":  "kavach_executor",
    "VAULT":     "kavach_vault",
    "CHANNEL":   "kavach_channel",
    "NAVIGATOR": "kavach_navigator",
}

CONFIG_PATH = REPO_ROOT / "parliament" / "config.yaml"
CORPUS_PATH = REPO_ROOT / "kavach_corpus_v1.json"
DEFAULT_RUNS = REPO_ROOT / "minister_runs.jsonl"

DISCLAIMER = (
    "  DEV DIAGNOSTIC ONLY — scores guide pattern work, they are NOT a\n"
    "  substitute for the Dell benchmark. Any FPR/recall change is a\n"
    "  HYPOTHESIS until re-measured on the Dell. Do not quote these numbers.\n"
    f"  (embedding + corpus + thresholds read live from {CONFIG_PATH.name})"
)


def banner(title: str) -> None:
    line = "=" * 74
    print(line)
    print(f"  {title}")
    print(line)
    print(DISCLAIMER)
    print(line)


# ─────────────────────────────────────────────────────────────────────────────
# Config + corpus loading (real system state)
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"[fatal] config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def minister_thresholds(cfg: dict, minister: str) -> dict:
    """Per-minister block threshold (falls back to global) + grey band — exactly
    what parliament uses to turn a confidence into BLOCK/ESCALATE/ALLOW."""
    th = cfg["thresholds"]
    per = th.get("per_minister", {}) or {}
    return {
        "block": float(per.get(minister, th["block"])),
        "grey":  float(th["grey"]),
    }


def verdict_for(confidence: float, th: dict) -> str:
    if confidence >= th["block"]:
        return "BLOCK"
    if confidence >= th["grey"]:
        return "ESCALATE"
    return "ALLOW"


def load_corpus_index() -> dict:
    """pattern_id -> {minister, category, source, L1, L2, L3}. Used to join a
    recorded matched_id (feature 2) back to human-readable pattern text."""
    if not CORPUS_PATH.exists():
        sys.exit(f"[fatal] corpus not found: {CORPUS_PATH}")
    raw = json.loads(CORPUS_PATH.read_text())
    idx: dict[str, dict] = {}
    for minister in ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"):
        for pat in raw.get(minister, {}).get("patterns", []):
            idx[pat["id"]] = {
                "minister": minister,
                "category": pat.get("category", ""),
                "source":   pat.get("source", ""),
                "L1":       pat.get("L1_intent", ""),
                "L2":       pat.get("L2_mechanism", ""),
                "L3":       pat.get("L3_surface", ""),
            }
    return idx


# ─────────────────────────────────────────────────────────────────────────────
# Live pipeline (BGE model + Chroma collections + BM25 indexes)
# ─────────────────────────────────────────────────────────────────────────────

class LivePipeline:
    """Loads exactly what parliament/server.py loads at startup, minus the HTTP
    server: the BGE model, the per-minister Chroma collections, and the BM25
    indexes. Embedding and retrieval therefore match the live pipeline."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.query_prefix = cfg.get(
            "query_prefix",
            "Represent this sentence for searching relevant passages: ",
        )

        chroma_path = Path(cfg.get("chroma_path", "./parliament/.chroma_kavach"))
        if not chroma_path.is_absolute():
            chroma_path = (REPO_ROOT / chroma_path).resolve()
        if not chroma_path.exists():
            sys.exit(
                f"[fatal] Chroma DB not found at {chroma_path}\n"
                "        Build it first (one-time):\n"
                "            pip install -r requirements.txt --break-system-packages\n"
                "            python predownload_model.py\n"
                "            python corpus_loader.py --rebuild\n"
                "        The tool deliberately refuses to invent a different index."
            )

        import chromadb
        from chromadb.config import Settings
        from sentence_transformers import SentenceTransformer

        print(f"[setup] loading BGE model: {cfg['embed_model']} ...", file=sys.stderr)
        self.model = SentenceTransformer(cfg["embed_model"])

        print(f"[setup] opening Chroma: {chroma_path}", file=sys.stderr)
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False),
        )

        self.collections: dict[str, object] = {}
        self.bm25: dict[str, object] = {}
        for minister, coll_name in COLL_NAMES.items():
            try:
                coll = client.get_collection(name=coll_name)
            except Exception as e:
                sys.exit(
                    f"[fatal] collection {coll_name} missing ({e}). "
                    "Run: python corpus_loader.py --rebuild"
                )
            self.collections[minister] = coll
            self.bm25[minister] = build_bm25_index(coll)
            mode = "hybrid" if self.bm25[minister] else "DENSE-ONLY (rank_bm25 missing)"
            print(f"[setup] {minister:<9} {coll.count():>4} docs  [{mode}]", file=sys.stderr)

    def embed_query(self, text: str) -> np.ndarray:
        """BGE query-side embedding — same prefix + normalization as server.py."""
        vec = self.model.encode(
            self.query_prefix + text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vec, dtype=np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Top-k mirror of run_minister_hybrid  (feature 1)
# ─────────────────────────────────────────────────────────────────────────────

def topk_hybrid_matches(
    minister: str,
    text: str,
    collection,
    bm25_index,
    query_vec: np.ndarray,
    k: int = 3,
    top_k: int = 10,
) -> list[dict]:
    """Return the top-k candidates ranked by the SAME RRF selection that
    run_minister_hybrid uses, each with confidence = dense_cosine x lexical_gate
    computed by the SAME formula. This mirrors parliament/ministers.py so the
    top-1 here equals what run_minister_hybrid returns; it just keeps more than
    one candidate. Falls back to pure dense (cosine) when BM25 is unavailable,
    exactly as the production function does.
    """
    res = collection.query(
        query_embeddings=[query_vec.tolist()],
        n_results=top_k if bm25_index is None else min(top_k, bm25_index["bm25"].corpus_size),
        include=["distances", "metadatas", "documents"],
    )
    if not res or not res.get("distances") or not res["distances"][0]:
        return []

    distances = res["distances"][0]
    metadatas = res["metadatas"][0]
    documents = res["documents"][0]
    chroma_ids = res["ids"][0]
    similarities = [max(0.0, 1.0 - d) for d in distances]  # chroma cosine -> sim

    def candidate(i: int, conf: float) -> dict:
        meta = metadatas[i] or {}
        return {
            "pattern_id": meta.get("pattern_id"),
            "level":      meta.get("level"),
            "category":   meta.get("category", ""),
            "dense_sim":  round(similarities[i], 4),
            "confidence": round(conf, 4),
            "text":       documents[i],
        }

    # ── Dense-only fallback (matches run_minister -> run_minister_hybrid path) ──
    if bm25_index is None:
        order = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)
        return [candidate(i, similarities[i]) for i in order[:k]]

    # ── Hybrid: dense order + BM25 global ranks -> RRF selection (mirror) ──
    dense_order = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)

    bm25_scores = bm25_index["bm25"].get_scores(_tokenize(text))
    id_to_pos = {doc_id: i for i, doc_id in enumerate(bm25_index["ids"])}
    bm25_global_ranks = {pos: rank for rank, pos in enumerate(np.argsort(bm25_scores)[::-1])}
    bm25_order = sorted(
        range(len(chroma_ids)),
        key=lambda i: bm25_global_ranks.get(id_to_pos.get(chroma_ids[i], -1), len(bm25_scores)),
    )
    fused = _rrf_fuse(dense_order, bm25_order, len(chroma_ids))  # (idx, rrf) desc

    bm25_qmax = float(np.max(bm25_scores)) if len(bm25_scores) else 0.0

    out: list[dict] = []
    for chroma_idx, _rrf in fused[:k]:
        sel_pos = id_to_pos.get(chroma_ids[chroma_idx])
        bm25_sel = float(bm25_scores[sel_pos]) if sel_pos is not None else 0.0
        if bm25_qmax <= 1e-9:
            gate = _GATE_FLOOR
        else:
            gate = _GATE_FLOOR + (1.0 - _GATE_FLOOR) * min(1.0, max(0.0, bm25_sel) / bm25_qmax)
        conf = min(1.0, similarities[chroma_idx] * gate)
        out.append(candidate(chroma_idx, conf))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1: inspect an action
# ─────────────────────────────────────────────────────────────────────────────

def cmd_inspect(pipe: LivePipeline, cfg: dict, text: str) -> None:
    qvec = pipe.embed_query(text)
    print(f'\n  ACTION: "{text}"\n')
    for minister in ("EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"):
        th = minister_thresholds(cfg, minister)
        coll = pipe.collections[minister]
        bm25 = pipe.bm25[minister]

        # Production single-best verdict (source of truth).
        scan: MinisterScan = run_minister_hybrid(
            minister, text, coll, bm25, pipe.embed_query, th, query_vec=qvec,
        )
        top = topk_hybrid_matches(minister, text, coll, bm25, qvec, k=3)

        mode = scan.retrieval_mode
        print(f"  ── {minister}  (block>={th['block']:.2f}  escalate>={th['grey']:.2f}  "
              f"[{mode}]) ─→  {scan.verdict}  conf={scan.confidence:.4f}")
        if not top:
            print("       (no matches)\n")
            continue
        for rank, c in enumerate(top, 1):
            v = verdict_for(c["confidence"], th)
            flag = {"BLOCK": "!!", "ESCALATE": " ~", "ALLOW": "  "}[v]
            print(f"     {flag}#{rank} {c['pattern_id']} [{c['level']}] "
                  f"conf={c['confidence']:.4f} (dense={c['dense_sim']:.4f}) -> {v}")
            print(f"        L1: {_clip(c['text'], 160)}")
        print()


def _clip(s: str | None, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2: known false positives from minister_runs.jsonl
# ─────────────────────────────────────────────────────────────────────────────

def cmd_falsepos(cfg: dict, runs_path: Path, limit: int) -> None:
    if not runs_path.exists():
        sys.exit(f"[fatal] runs file not found: {runs_path}")
    corpus = load_corpus_index()

    fps: list[dict] = []
    raw_available = 0
    with runs_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("is_attack") is False and r.get("speaker_verdict") == "BLOCK":
                fps.append(r)
                raw = r.get("action", {}).get("raw", "none")
                if raw and raw != "none":
                    raw_available += 1

    print(f"\n  Benign actions HARD-BLOCKED by the parliament (false positives): "
          f"{len(fps)}")
    print(f"  Of these, action.raw text is present for {raw_available}/{len(fps)}.")
    if raw_available == 0:
        print("  -> action.raw is 'none' for every FP row, so the action text cannot\n"
              "     be re-embedded. The analysis below uses the RECORDED per-minister\n"
              "     matched_id + confidence from the Dell run (not a re-scored value).")
    print()

    # Aggregate: which corpus patterns are tripped by BLOCK/ESCALATE votes on FPs.
    block_trips: Counter = Counter()
    escalate_trips: Counter = Counter()
    minister_block_counts: Counter = Counter()

    # Threshold-drift check: the recorded `vote` reflects the thresholds in
    # force during the Dell run. config.yaml may have changed since. Re-derive
    # each minister's verdict at the CURRENT thresholds from the recorded
    # confidence, and count how many recorded BLOCK votes would still block.
    recorded_blocks = 0
    still_block_now = 0
    fps_no_minister_blocks_now = 0  # FPs where no minister would BLOCK at current thr

    for r in fps:
        any_block_now = False
        for vote in r.get("minister_votes", []):
            pid = vote.get("matched_id")
            if vote.get("vote") == "BLOCK":
                block_trips[pid] += 1
                minister_block_counts[vote.get("minister")] += 1
                recorded_blocks += 1
                th = minister_thresholds(cfg, vote.get("minister"))
                if verdict_for(vote.get("confidence", 0.0), th) == "BLOCK":
                    still_block_now += 1
            elif vote.get("vote") == "ESCALATE":
                escalate_trips[pid] += 1
            th = minister_thresholds(cfg, vote.get("minister"))
            if verdict_for(vote.get("confidence", 0.0), th) == "BLOCK":
                any_block_now = True
        if not any_block_now:
            fps_no_minister_blocks_now += 1

    if recorded_blocks and still_block_now < recorded_blocks:
        print("  ── THRESHOLD DRIFT (config.yaml has changed since this run) ──")
        print(f"     {recorded_blocks} minister BLOCK votes were recorded, but only "
              f"{still_block_now} clear the\n"
              f"     CURRENT per-minister block thresholds in config.yaml. "
              f"{fps_no_minister_blocks_now} of {len(fps)} FPs\n"
              f"     have NO minister that would hard-block at current thresholds — "
              f"those may\n     already be resolved by config and need re-measuring "
              f"on the Dell to confirm.\n"
              f"     (Minister-level only; the Speaker's final verdict is not "
              f"re-derived here.)\n")

    print("  ── Ministers driving the benign hard-blocks (count of BLOCK votes) ──")
    for minister, n in minister_block_counts.most_common():
        print(f"       {minister:<9} {n}")
    print()

    print("  ── Worst-offender patterns (most BLOCK votes on benign actions) ──")
    print("     These are the corpus patterns to revisit first.")
    for pid, n in block_trips.most_common(15):
        info = corpus.get(pid, {})
        m = info.get("minister", "?")
        print(f"     [{n:>3}x] {pid} ({m})")
        print(f"             L1: {_clip(info.get('L1'), 150)}")
    print()

    # Per-FP detail (bounded).
    show = fps if limit <= 0 else fps[:limit]
    print(f"  ── Per-FP detail (showing {len(show)} of {len(fps)}; "
          f"use --limit 0 for all) ──")
    for r in show:
        aid = r.get("action_id")
        cat = r.get("category", "")
        print(f"\n   {aid}  category={cat}  ground_truth={r.get('ground_truth')} "
              f"-> speaker={r.get('speaker_verdict')}")
        for vote in r.get("minister_votes", []):
            minister = vote.get("minister")
            th = minister_thresholds(cfg, minister)
            v = vote.get("vote")
            conf = vote.get("confidence", 0.0)
            pid = vote.get("matched_id")
            info = corpus.get(pid, {})
            flag = {"BLOCK": "!!", "ESCALATE": " ~", "ALLOW": "  "}.get(v, "  ")
            now = verdict_for(conf, th)
            drift = f"  [now {now} @cfg]" if now != v else ""
            print(f"     {flag} {minister:<9} {v:<8} conf={conf:.4f} "
                  f"(block>={th['block']:.2f}) trips {pid}{drift}")
            if v in ("BLOCK", "ESCALATE") and info:
                print(f"            L1: {_clip(info.get('L1'), 150)}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3: interactive REPL
# ─────────────────────────────────────────────────────────────────────────────

def cmd_repl(pipe: LivePipeline, cfg: dict) -> None:
    print("\n  Interactive inspect — type an action, blank line or Ctrl-D to quit.\n")
    while True:
        try:
            text = input("  action> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            return
        cmd_inspect(pipe, cfg, text)


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="DEV pattern-inspection tool for Kavach ministers (NOT production).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ins = sub.add_parser("inspect", help="inspect a single action text")
    p_ins.add_argument("text", help="the tool-call / action text to score")

    p_fp = sub.add_parser("falsepos", help="analyze benign hard-blocks from a runs file")
    p_fp.add_argument("--runs", type=Path, default=DEFAULT_RUNS,
                      help=f"minister_runs.jsonl path (default: {DEFAULT_RUNS})")
    p_fp.add_argument("--limit", type=int, default=20,
                      help="per-FP detail rows to print (0 = all; default 20)")

    sub.add_parser("repl", help="interactive inspect loop")

    args = ap.parse_args()

    cfg = load_config()

    if args.cmd == "inspect":
        banner("KAVACH PATTERN INSPECTOR — inspect")
        pipe = LivePipeline(cfg)
        cmd_inspect(pipe, cfg, args.text)
    elif args.cmd == "falsepos":
        banner("KAVACH PATTERN INSPECTOR — known false positives")
        cmd_falsepos(cfg, args.runs, args.limit)
    elif args.cmd == "repl":
        banner("KAVACH PATTERN INSPECTOR — repl")
        pipe = LivePipeline(cfg)
        cmd_repl(pipe, cfg)


if __name__ == "__main__":
    main()
