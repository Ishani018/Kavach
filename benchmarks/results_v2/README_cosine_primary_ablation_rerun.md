# `cosine_primary_ablation_rerun_20260723.json` — settling the Block-or-Escalate convention question

## Why this exists

§4.3's central ablation compares the deterministic-primary pipeline
(74.4%/90.1%) against the pre-rearchitecture cosine-primary configuration
(67.5%/85.7%), and claims "same scoring convention" without originally
spelling out explicitly whether cosine-primary's number counted
Block-or-Escalate as a hit, or Block-only. This is load-bearing: if
cosine-primary's number were secretly Block-only while the new number is
Block-or-Escalate, the two aren't comparable and the recall-win claim
would not hold as stated. No raw data file backing the original
67.5%/85.7% figure could be found in the repo to check this after the
fact, so it was re-verified from scratch rather than asserted.

## How it was verified

1. Found the actual pre-rearchitecture commit via `git log --follow --
   parliament/prefilters.py`: `7216dea` ("Stage 1 re-architecture ---
   deterministic VAULT/EXECUTOR pre-filters") is the first commit to add
   any deterministic parsing at all. Its parent, `bb23b8c` ("Kavach
   re-architecture scoping plan, Phase 0, no detection code"), is the
   last commit before any deterministic code existed --- confirmed by
   `git cat-file -e bb23b8c:parliament/prefilters.py` failing (file
   doesn't exist at that commit).
2. Checked out `bb23b8c` into an isolated git worktree
   (`/tmp/kavach_cosine_primary`, not committed to this repo).
3. Copied the *current* `.chroma_kavach` corpus into that worktree, so
   the only variable changed is the code (deterministic layer absent),
   not the attack-pattern corpus.
4. Ran that old code as a live server on port 8089 (separate from the
   main server on 8088), and dispatched all 519 reference-corpus cases
   from `_kavach_pb_attack_checkpoint.json` through it, recording every
   minister's own verdict (not just the final one).
5. Computed both conventions directly from the same run: Block-or-Escalate
   as a hit, and Block-only as a hit.

## Result

```
VAULT:    n=117  Block-or-Escalate=79 (67.5%)   Block-only=5  (4.3%)
EXECUTOR: n=203  Block-or-Escalate=174 (85.7%)  Block-only=147 (72.4%)
```

**Block-or-Escalate reproduces the paper's existing 67.5%/85.7% figures
exactly.** Block-only would have given completely different numbers
(4.3%/72.4%). This confirms the paper's "same scoring convention" claim
was correct — Block-or-Escalate is counted identically on both the
deterministic-primary and cosine-primary sides — rather than leaving it
as an assumption. `section_4_deployment.tex` §4.3 now states this
explicitly, citing this re-run.

Side note, not used in the paper: cosine-primary's EXECUTOR ministers
relied on hard Block far more often relative to Escalate (147/174 of its
hits are Block) than VAULT did (5/79) — a real difference in how
confident/aggressive the old cosine thresholds were per minister, but not
relevant to the convention question this run was designed to answer.
