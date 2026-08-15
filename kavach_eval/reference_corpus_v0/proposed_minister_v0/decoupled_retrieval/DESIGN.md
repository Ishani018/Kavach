# Decoupled candidate selection: design

## Part 1 — Confirmed diagnosis, from the real code

Read `parliament/ministers.py::run_minister_hybrid()` (lines 223-393)
directly. The entanglement is real, and more specific than
`BEST_OF_BOTH_VERDICT.md`'s framing ("RRF picks a dense-favored
candidate") — it's a **hard visibility gate**, not just a ranking bias:

1. **Step 1** (line 283-289): `collection.query(query_embeddings=[q], n_results=top_k)`
   — ChromaDB's dense-only ANN search returns **only the top `top_k`
   (default 10) documents by dense cosine similarity**. This is the
   entire candidate universe from this point forward.
2. **Step 2** (lines 314-334): BM25 is scored against the **full corpus**
   (`bm25_index["bm25"].get_scores(query_tokens)`, shape = corpus_size),
   producing genuine full-corpus BM25 scores and ranks
   (`bm25_global_ranks`). **But** `bm25_order` (line 328-334) only
   iterates `range(len(chroma_ids))` — i.e., it re-ranks *only the
   documents dense already returned*, using their (real, full-corpus-
   computed) BM25 rank as a tiebreak/reordering signal. A document with
   a very strong BM25 match that dense's ANN search placed outside
   `top_k` is **never added to the candidate set at all** — not
   down-weighted, structurally invisible to the fusion step.
3. **Step 3** (RRF, `_rrf_fuse`, lines 118-133): fuses `dense_order` and
   `bm25_order` — but since `bm25_order` was already restricted to
   `chroma_ids`, RRF is fusing two rankings **over the same restricted
   set**, not truly combining two independent proposals.
4. **Step 4** (confidence formula, lines 350-369): scores whichever
   document RRF ranks #1 within that restricted set —
   `confidence = dense_sim(selected) × lexical_gate`.

**Confirmed, corrected from the prior investigation's framing**: the
issue isn't that "dense influences which candidate wins the RRF tiebreak"
— it's that **dense's own top-k cutoff (before RRF ever runs) determines
the entire pool BM25/sparse is allowed to compete over.** A strong
sparse-only match that dense ranks 15th (with `top_k=10`) cannot
influence the outcome under any circumstances, regardless of how RRF
weights it. This is a structural ceiling on sparse's ability to rescue a
case dense mis-ranks, not just a soft bias.

## Part 2 — Decoupled design

**Core change**: fetch `top_k` candidates from **each** retriever
independently, union the two candidate sets, then RRF-fuse over the
union (assigning each retriever's "worst possible rank" to documents it
didn't itself return, so RRF can still combine signals for
partially-covered documents) — rather than restricting sparse to
re-ranking only what dense already selected.

```
dense_candidates  = top_k documents by dense cosine similarity (ChromaDB ANN query, unchanged)
sparse_candidates = top_k documents by BM25 score (full-corpus BM25.get_scores(), take top_k — NEW, currently BM25 never gets its own top_k, only a re-rank of dense's)
candidate_union   = dense_candidates ∪ sparse_candidates   (typically top_k to 2*top_k documents, not always exactly 2x since overlap is common for real attacks per the docstring's own claim "actual attacks DO share both")
```

For every document in the union, RRF fusion needs a rank in BOTH
lists — for documents only one retriever proposed, the other retriever's
"rank" is set to `len(candidate_union)` (worst-possible, i.e. "this
retriever effectively didn't select it," consistent with `_rrf_fuse`'s
existing pattern of only fusing within a shared list length, generalized
to the larger union size instead of `len(chroma_ids)`).

RRF then selects the best candidate from the **union**, and the existing
confidence formula (`dense_sim(selected) × lexical_gate`) runs
UNCHANGED on whichever document wins — this is the compatibility
constraint from the prompt: keep the existing formula, only fix
candidate selection.

**One real new cost, flagged plainly**: for documents that only the
BM25/sparse side proposed (not in dense's own top_k), the confidence
formula still needs `dense_sim(selected)` — the isolated prototype gets
this for free since the test harness caches full-corpus dense vectors
(no extra encode calls). A **live production integration would need
this too** — either (a) always fetching each candidate's stored dense
embedding via `collection.get(ids=[...], include=["embeddings"])` for
the union (cheap — ChromaDB already stores every document's embedding,
this is a lookup not a re-encode), or (b) computing cosine directly from
the query vector and each candidate's stored embedding without going
through ChromaDB's ANN index at all for the sparse-only additions. This
is a **real but small** integration cost — no new model calls, no new
embeddings to compute, just a slightly different Chroma query for the
handful of documents (usually 0-10, since attacks are claimed to overlap
both signals) that only BM25 surfaced. Flagged here explicitly per the
prompt's "flag what needs re-calibration" instruction — this is
implementation cost, not recalibration, but worth naming since it's the
one place the decoupled design isn't a drop-in.

**What does NOT need recalibration**: the confidence formula itself
(`dense_sim × lexical_gate`, `GATE_FLOOR=0.65`) is unchanged — it still
operates on cosine units and BM25-relative-to-query-max exactly as
before. `config.yaml`'s block/grey thresholds are untouched. The only
behavioral change is which document is *eligible* to be selected as
"best" — the scoring math applied to that document once selected is
identical to production today.

**What MIGHT need recalibration, flagged honestly**: if decoupling
causes previously-dense-selected documents to lose to newly-visible
sparse-selected documents more often, the *distribution* of confidence
scores could shift even without changing the formula — e.g., if
sparse-favored documents tend to have systematically different
dense_sim values than the documents dense would have picked on its own,
average confidence could drift up or down. This is exactly what Part 3's
testing needs to check empirically, not assume either way.

**Explicitly scoped to CURRENT models only, per the prompt's
instruction**: this design uses BGE-base-en-v1.5 dense (production,
unchanged) + real BM25 (production, unchanged) — no BGE-M3, no
model swap of any kind. The architecture fix and the model-swap question
are kept fully separate, as instructed.
