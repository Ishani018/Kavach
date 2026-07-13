# Overnight batch — summary for morning review

All 4 tasks worked in order. `kavach_corpus_v1_ORIGINAL.json` MD5 verified
unchanged at every step: `7ce71ec38c9bdd2f273a34205c13fc5e`. `kavach_corpus_v1.json`
(the live, non-frozen corpus) also verified unchanged throughout:
`3f260dfa7d7387e97c66ac9cb98e2202`. `main` never touched. Nothing merged into
the live corpus or Chroma store — everything stayed in scratchpad/test copies
per the standing rules.

Full step-by-step log: `OVERNIGHT_LOG.md` (same directory).

---

## Task 1 — Pull qwen2.5:7b — ✅ DONE, clean

Pulled successfully (4.7GB), confirmed via `ollama list`. Ready to use — this
is what Task 3's extractor prototype ran against.

## Task 2 — CHAN-102 sanity check + test-copy validation — ✅ DONE, real findings, no regressions

**BM25 rarity check found a real issue, same class as the original bug, smaller
scale.** Several of CHAN-102's filler/connector words (`session`, `similar`,
`equivalent`, `tools`, `immediately`, `same`, `via`) score as rare in the
current CHANNEL corpus — some rarer than the original bug's `url`/`user`
tokens, a couple in the same IDF band as genuinely attack-specific words like
`payload`/`credentials`. **Proposed a wording adjustment (drop or replace the
flagged filler words), did NOT apply it** — per your "propose, don't
guess-fix silently" instruction. This is not blocking; it's a smaller-scale
version of the same risk class, confined to filler words, not the pattern's
core content.

**Full validation suite run against a TEST COPY only** (isolated corpus file +
isolated Chroma store, CHAN-102 as-drafted, unmodified). Production
`.chroma_kavach` never touched.

| check | baseline | with CHAN-102 | result |
|---|---|---|---|
| get_webpage/read_inbox FP | both BLOCK (pre-existing, unrelated bug) | both BLOCK (unchanged) | no interaction |
| R2b LOLBIN (13 real) | 10 evaded / 3 blocked | 10 evaded / 3 blocked | no regression |
| Real benign replay (14 calls) | 71.4% wrongly flagged | 71.4% wrongly flagged | no new FPs |
| **Real attack catch rate (30 cases)** | **63.3%** | **70.0%** | **real improvement** |

Verified the improvement is genuine (not noise) by checking which 2 cases
flipped — both are exactly CHAN-102's target shape (read sensitive record,
then expose/share it).

**CHAN-102 looks safe and effective. Still NOT merged into the live corpus** —
awaiting your explicit approval, per standing instruction. Recommend: review
the BM25 wording suggestion, decide whether to apply it before or after
merging, then merge for real when ready.

## Task 3 — Literal constraint-type extractor prototype — ⚠️ MIXED RESULT, needs your input

Built as an isolated prototype (`scratchpad/literal_constraint_prototype/`),
reusing `corpus_agent/proposer.py`'s exact Ollama call/parse/retry scaffolding.
Not wired into `parliament/` anywhere.

**First pass (v1) failed 5/5 on the actual injection-catching test** — but the
underlying cause was one specific, understood bug: the prompt asked the model
to invent tool/argument names from instruction text alone, and it invented
plausible-but-wrong names (`slack_invite` instead of the real
`invite_user_to_slack`), so the equality check never found an applicable
constraint.

**Fixed it (v2) by giving the extractor the real tool/argument schema per
case** (the same information a real integration would have available, since
the LLM agent itself needs the schema to call the tool in the first place).
Result improved to **2/5 clean catches** (password change, Slack invite —
both correctly extracted the real value and correctly flagged the attacker's
substituted value). The other 3: one negative-case pass (correctly declined
to extract "the largest file" as a literal — this is intentional, correct
behavior, not a failure), one case where the model non-deterministically
dropped a constraint it had extracted correctly in the v1 run, and one case
where extraction was correct but a value-normalization bug in my comparison
code (the model quoted its output, the equality check didn't strip quotes)
caused even the LEGITIMATE action to fail the check.

**This needs your decision before going further:**
1. The quote-stripping bug is a trivial, obvious fix — happy to apply it
   given a go-ahead, or you may want to look at the raw output first.
2. The model non-determinism (correctly extracting a constraint on one run,
   missing it on another) is a more open design question — worth deciding
   whether the real version needs retry-with-validation, multiple-call
   consensus, or a different model/prompting strategy, before investing more
   in this specific prototype.
3. Whether 2/5 clean + fixable issues on the other 3 is "good enough
   signal to proceed toward a real Option B build" or "needs another
   iteration first" is your call, not mine to decide overnight.

Full raw output: `test_results.json` (v1) and `test_results_v2.json` (v2) in
the prototype directory.

## Task 4 — This summary — ✅ DONE

---

## What's ready for your review vs. what needs a decision

**Ready to review/act on:**
- CHAN-102's validation results (Task 2) — looks safe, recommend merging when
  you're ready; the BM25 wording tweak is optional/your call on timing.
- The literal-constraint approach's core viability (Task 3) — 2/5 clean
  end-to-end catches is real, positive signal that the mechanism works when
  given the right inputs.

**Needs your decision before I'd continue unilaterally:**
- Whether to apply the BM25 wording fix to CHAN-102 before merging, and
  whether to merge it into the live corpus now.
- Whether to fix the quote-stripping bug and continue iterating on the
  extractor prototype, or treat tonight's result as sufficient signal and
  move to scoping a fuller version.
- How to handle the model-nondeterminism finding — this affects the honest
  reliability estimate for the whole literal-constraint approach, not just a
  bug to patch.

No genuine blockers hit — everything above is a real, informed decision point,
not a "couldn't figure out how" stall. All test servers were stopped cleanly
after use; only the pre-existing (already-known, unrelated, already-broken
before tonight) process on port 8088 is still running, untouched throughout.
