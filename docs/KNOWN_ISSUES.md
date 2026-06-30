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
