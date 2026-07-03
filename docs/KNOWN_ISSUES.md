# Known Issues

Tracked, non-urgent items. Each is documented here rather than fixed when fixing
carries more risk than the issue warrants (e.g. touching the corpus close to a
benchmark session).

---

## 1. Corpus OWASP tags use the pre-2025 `A0x` numbering, not the corrected `ASIxx` taxonomy

**Status:** camera-ready cleanup item — not urgent, does not affect detection or the paper's prose.

**What:** Some patterns in `kavach_corpus_v1.json` carry OWASP Agentic tags in their
`source` / `category` / `rationale` fields using the **old `A01`–`A09` numbering**
(56 occurrences: `A01`×24, `A04`×15, `A02`×7, `A09`×6, `A03`×2, `A06`×2). The paper's
prose (corrected) uses the **December-2025 OWASP Top 10 for Agentic Applications
`ASIxx` taxonomy** with the per-minister mapping EXECUTOR↔ASI05/ASI04,
VAULT↔ASI03/ASI09, CHANNEL↔ASI07/ASI08, NAVIGATOR↔ASI01/ASI10.

**Why it is not urgent:**
- It is **metadata-only**. The OWASP tag is a secondary annotation; the primary
  taxonomic grounding for every pattern is its MITRE ATT&CK / ATLAS technique ID,
  which is correct and verified (see the corpus audit).
- The paper **does not quote corpus fields directly** — the ASI mapping in the
  paper is authored prose, so the corpus's internal `A0x` tags do not surface in
  any paper claim and create no paper-vs-corpus contradiction in the text.
- It does **not affect detection**: the OWASP tag is not used by the scorer, the
  router, or the Speaker. Retrieval is over the L1/L2/L3 text, not the tag.

**The risk of fixing now:** mapping 56 `A0x` occurrences across the four ministers
to the new `ASIxx` scheme is a 401-pattern metadata edit. Doing it immediately
before the Dell benchmark session risks introducing an error into the corpus for
no detection benefit. Deferred to a post-submission / camera-ready pass.

**Scope when fixed:** rewrite the `A0x` references in `source`/`category` to the
corresponding `ASIxx` code per the corrected per-minister mapping, then rebuild
ChromaDB. The `_ORIGINAL.json` ground-truth snapshot must remain untouched.

---

## 2. Semantic-generalization ablation (Ablation 3) — deferred to the S&P/CCS 2027 follow-on

**Status:** scoped-and-deferred (design done, not built). Not for July 24 (AISec).

**What:** re-run the red-team paraphrase generation (`kavach_eval/redteam_evasion_v0.py`)
with (a) **per-attempt logging** that persists every evaluated paraphrase — caught
*and* evaded — with its source pattern, verdict, and dense/BM25/hybrid scores, and
(b) an **intent-preservation filter** that drops paraphrases which drifted off the
original malicious intent. Then compute the **Jaccard lexical overlap** between each
paraphrase and its source pattern and **cross-tabulate catch-rate against overlap**.
Goal: show Kavach catches attacks at near-zero lexical overlap — i.e. semantic
detection, not keyword matching.

**Why it is deferred (not abandoned):**
- **Not pure re-analysis.** The existing red-team output persists only the evasions
  (`top_examples`) and the ambiguous cases (`human_review`, ~142/268 flagged
  off-intent) — it does **not** keep the ~117 *caught* paraphrases, which are
  exactly the population the catch-rate-vs-overlap curve needs. A ~10-line logging
  change plus a validity filter and one laptop re-run are required first.
- **Validity design needs time, not deadline pressure.** Many red-team
  "paraphrases" drifted off-intent (base64 blobs, different-attack substitutions),
  so a naive re-analysis would measure catch-rate over junk. The honest version
  needs a real intent-preservation gate — rushed, A3 becomes the weakest link.
- **Design note — the tension it must address honestly:** the retrieval ablation
  (Ablation 2, `kavach_eval/ablation_retrieval_modes.py`) shows the multiplicative
  lexical gate creates keyword-dependence at the LOLBIN blind spot (hybrid lets
  10/13 lexically-novel LOLBINs evade). A credible A3 must therefore report **both**
  where semantic generalization holds **and** where the gate reintroduces lexical
  dependence — not a one-sided "Kavach understands meaning" claim. That balanced
  framing is the whole reason it is better as a considered 2027 experiment than a
  rushed 2026 one.

**Scaffolding that already exists:** the generator, obfuscation/mutation stages,
source-pattern tracking (`pattern_id` + `original`), and the real hybrid scorer are
all present; only the logging, the intent filter, and the overlap analysis are new.
