#!/usr/bin/env python3
"""
ablation_retrieval_modes.py — Retrieval ablation (Ablation 2)
=============================================================

EVAL-TIME ONLY. Does not touch the deployed decision path, config.yaml, or the
frozen corpus. Reuses the EXACT production scorer internals from
parliament.ministers (run_minister_hybrid, build_bm25_index, _GATE_FLOOR,
_tokenize, _rrf_fuse) and the production ChromaDB so the numbers are faithful.

Three retrieval modes, all sharing the same dense+BM25 retrieval; only the
CONFIDENCE computation differs (thresholds unchanged, cosine units):

  hybrid      confidence = dense_sim(selected) * lexical_gate   [DEPLOYED PATH]
  dense_only  confidence = dense_sim(selected)                  [no lexical gate]
  bm25_only   confidence = bm25(selected) / bm25_qmax           [lexical only]

For hybrid we call run_minister_hybrid() directly (the real function). For
dense_only and bm25_only we replicate the SAME selection+scoring using the same
ChromaDB query and the same BM25 index, changing only the confidence formula —
so the three modes are exact ablations of one pipeline, not reimplementations.

Test sets (laptop-runnable, no agent backbone, no InjecAgent download):
  - LOLBINs : the 13 R2 tools (imported from _r2b_pipeline TOOLS) — attacks that
              SHOULD be caught; measures evasion per mode.
  - benign  : the 17 InjecAgent benign user instructions (benchmarks/data/
              user_cases.jsonl) — SHOULD NOT be blocked; measures FPR per mode.

The full-InjecAgent 3-mode recall row is DEFERRED to the Dell (case text is an
external download, not in the repo) — see docs/LAB_DAY.md post-Dell checklist.

Usage:
    python kavach_eval/ablation_retrieval_modes.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

import chromadb
from sentence_transformers import SentenceTransformer

from parliament.ministers import (
    run_minister_hybrid, build_bm25_index, _tokenize,
)

MINISTERS = ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"]
CHROMA = _REPO / "parliament" / ".chroma_kavach"
CFG = yaml.safe_load(open(_REPO / "parliament" / "config.yaml"))["thresholds"]
PER_MIN = {m: float(CFG["per_minister"][m]) for m in MINISTERS}
GREY = float(CFG["grey"])
BGE = "BAAI/bge-base-en-v1.5"
BGE_PREFIX = "Represent this sentence for searching relevant passages: "
TOP_K = 10


def _verdict(conf: float, block: float) -> str:
    if conf >= block:
        return "BLOCK"
    if conf >= GREY:
        return "ESCALATE"
    return "ALLOW"


def _dense_bm25_common(text, collection, bm25_index, query_vec):
    """Run the shared dense + BM25 retrieval exactly as run_minister_hybrid does,
    returning the per-candidate similarities, the selected index, dense_sim of
    the selected doc, and its normalized bm25 term. Mirrors ministers.py."""
    res = collection.query(
        query_embeddings=[query_vec.tolist()],
        n_results=min(TOP_K, bm25_index["bm25"].corpus_size),
        include=["distances", "metadatas", "documents"],
    )
    if not res or not res.get("distances") or not res["distances"][0]:
        return None
    chroma_ids = res["ids"][0]
    distances = res["distances"][0]
    similarities = [max(0.0, 1.0 - d) for d in distances]
    dense_order = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)

    id_to_bm25_pos = {doc_id: i for i, doc_id in enumerate(bm25_index["ids"])}
    bm25_scores = bm25_index["bm25"].get_scores(_tokenize(text))
    bm25_global_ranks = {pos: rank for rank, pos in enumerate(np.argsort(bm25_scores)[::-1])}
    bm25_order = sorted(
        range(len(chroma_ids)),
        key=lambda i: bm25_global_ranks.get(id_to_bm25_pos.get(chroma_ids[i], -1), len(bm25_scores)),
    )
    bm25_qmax = float(np.max(bm25_scores)) if len(bm25_scores) else 0.0
    return chroma_ids, similarities, dense_order, bm25_order, id_to_bm25_pos, bm25_scores, bm25_qmax


def score_modes(text, collection, bm25_index, embed_fn, block):
    """Return {mode: (confidence, verdict)} for the three retrieval modes."""
    qv = embed_fn(text)

    # HYBRID — call the REAL deployed scorer, no reimplementation.
    hy = run_minister_hybrid(
        minister="_", text=text, collection=collection, bm25_index=bm25_index,
        embed_fn=embed_fn, thresholds={"block": block, "grey": GREY},
        top_k=TOP_K, query_vec=qv,
    )
    out = {"hybrid": (round(hy.confidence, 4), _verdict(hy.confidence, block))}

    common = _dense_bm25_common(text, collection, bm25_index, qv)
    if common is None:
        out["dense_only"] = (0.0, "ALLOW")
        out["bm25_only"] = (0.0, "ALLOW")
        return out
    chroma_ids, sims, dense_order, bm25_order, id2pos, bm25_scores, bm25_qmax = common

    # DENSE_ONLY — select best-dense candidate, confidence = its dense cosine.
    best_dense = dense_order[0]
    dconf = sims[best_dense]
    out["dense_only"] = (round(dconf, 4), _verdict(dconf, block))

    # BM25_ONLY — select best-BM25 candidate, confidence = normalized bm25 score.
    best_bm25 = bm25_order[0]
    sel_pos = id2pos.get(chroma_ids[best_bm25])
    bm25_sel = float(bm25_scores[sel_pos]) if sel_pos is not None else 0.0
    bconf = (bm25_sel / bm25_qmax) if bm25_qmax > 1e-9 else 0.0
    out["bm25_only"] = (round(bconf, 4), _verdict(bconf, block))
    return out


def parliament_verdict(per_mode_per_minister):
    """Pure-veto Speaker across ministers, per mode. Input:
    {mode: {minister: (conf, verdict)}}. Returns {mode: verdict}."""
    out = {}
    for mode, mins in per_mode_per_minister.items():
        v = "ALLOW"
        for m, (conf, vd) in mins.items():
            if vd == "BLOCK":
                v = "BLOCK"
                break
            if vd == "ESCALATE" and v == "ALLOW":
                v = "ESCALATE"
        out[mode] = v
    return out


def main():
    print("[setup] loading BGE + prod ChromaDB + BM25 indexes ...", file=sys.stderr)
    model = SentenceTransformer(BGE)

    def embed_fn(text):
        return model.encode(BGE_PREFIX + text, normalize_embeddings=True)

    client = chromadb.PersistentClient(str(CHROMA))
    # Collections are named kavach_<minister-lower> (per parliament COLL map).
    avail = {c.name: c for c in client.list_collections()}
    collections, bm25 = {}, {}
    for m in MINISTERS:
        cname = f"kavach_{m.lower()}"
        if cname not in avail:
            sys.exit(f"[fatal] collection {cname} not found; have {list(avail)}")
        coll = client.get_collection(cname)
        collections[m] = coll
        bm25[m] = build_bm25_index(coll)

    # ── Load test sets ────────────────────────────────────────────────────────
    from kavach_eval._r2b_pipeline import SPECS  # (name, minister, [cmd parts])
    lolbins = [(name, minister, " ".join(parts)) for (name, minister, parts) in SPECS]

    benign = []
    ucp = _REPO / "benchmarks" / "data" / "user_cases.jsonl"
    for line in open(ucp, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        instr = d.get("User Instruction", "").strip()
        if instr:
            benign.append(instr)

    modes = ["dense_only", "bm25_only", "hybrid"]

    # ── LOLBIN leg: for each tool, score its OWN minister; caught = BLOCK ───────
    print("\n=== LOLBIN leg (13 R2 tools; caught = hard BLOCK by the tool's minister) ===")
    print(f"{'tool':<18} {'min':<9} " + " ".join(f"{m:>10}" for m in modes))
    lolbin_caught = {mode: 0 for mode in modes}
    for name, minister, cmd in lolbins:
        block = PER_MIN[minister]
        scored = score_modes(cmd, collections[minister], bm25[minister], embed_fn, block)
        row = []
        for mode in modes:
            conf, vd = scored[mode]
            if vd == "BLOCK":
                lolbin_caught[mode] += 1
            row.append(f"{conf:>5} {vd[:1]}")
        print(f"{name:<18} {minister:<9} " + " ".join(f"{c:>10}" for c in row))
    n_lol = len(lolbins)
    print(f"\n  LOLBINs CAUGHT (hard BLOCK) / {n_lol}:")
    for mode in modes:
        print(f"    {mode:<12} {lolbin_caught[mode]:>2}/{n_lol}  "
              f"(evaded: {n_lol - lolbin_caught[mode]})")

    # ── Benign leg: full parliament (pure veto); FPR = block-or-escalate rate ───
    print("\n=== Benign leg (17 InjecAgent user instructions; want ALLOW) ===")
    fpr_block = {mode: 0 for mode in modes}
    fpr_esc = {mode: 0 for mode in modes}
    for instr in benign:
        per_mode = {mode: {} for mode in modes}
        for m in MINISTERS:
            scored = score_modes(instr, collections[m], bm25[m], embed_fn, PER_MIN[m])
            for mode in modes:
                per_mode[mode][m] = scored[mode]
        verdicts = parliament_verdict(per_mode)
        for mode in modes:
            if verdicts[mode] == "BLOCK":
                fpr_block[mode] += 1
            elif verdicts[mode] == "ESCALATE":
                fpr_esc[mode] += 1
    nb = len(benign)
    print(f"  Benign FPR / {nb} (pure-veto parliament):")
    for mode in modes:
        print(f"    {mode:<12} block={fpr_block[mode]:>2}/{nb}  "
              f"escalate={fpr_esc[mode]:>2}/{nb}  "
              f"block-only-FPR={fpr_block[mode]/nb:.3f}  "
              f"block-or-esc-FPR={(fpr_block[mode]+fpr_esc[mode])/nb:.3f}")

    # ── Summary table ──────────────────────────────────────────────────────────
    print("\n=== SUMMARY (Ablation 2, laptop; InjecAgent recall row deferred to Dell) ===")
    print(f"{'mode':<12} {'LOLBIN caught':>14} {'LOLBIN evaded':>14} "
          f"{'benign block-FPR':>18} {'benign B/E-FPR':>16}")
    for mode in modes:
        print(f"{mode:<12} {lolbin_caught[mode]:>10}/{n_lol} "
              f"{n_lol-lolbin_caught[mode]:>14} "
              f"{fpr_block[mode]/nb:>18.3f} "
              f"{(fpr_block[mode]+fpr_esc[mode])/nb:>16.3f}")


if __name__ == "__main__":
    main()
