# Naive keyword/regex baseline — `eval/naive_baseline/`

## READ THIS FIRST

**This is not a serious detector, and this is not a rigorous comparison
point.** It is a deliberately naive, single-author, unvalidated keyword/regex
blocklist — ~30 hand-written patterns for things a non-expert defender might
reach for first (`curl`, `wget`, `eval(`, `chmod +x`, `base64 -d`, `.ssh`/
`.pem` paths, reverse-shell strings, persistence strings). No AST parsing,
no cosine retrieval, no corpus, no session state, no calibration, no security
review, no red-teaming, no iteration.

**Do not cite the numbers below as "keyword matching achieves X%" in any
general sense.** They describe only this one hand-written list, on this one
run, against this one benchmark. A different (even naively) chosen pattern
list could plausibly score very differently. The point of this baseline is
narrow: to give a rough, honest sense of the floor that basic keyword
matching alone gives you, so that Kavach's actual deterministic+cosine
pipeline numbers (see the root README's "Round 2" section: VAULT 34.2%→74.4%,
EXECUTOR 34.5%→90.1%) are read next to *some* naive reference point instead
of in a vacuum — not as a competitive baseline Kavach is being benchmarked
against.

## Methodology discipline

All ~30 patterns in `naive_baseline.py` were **hand-written in a single pass,
before the script was ever run against Kavach-PB data.** The script was then
run **exactly once**. The numbers below are reported as they came out,
unedited — including the fact that recall is low. No pattern was added,
removed, reworded, or reweighted after seeing a score. (The only kind of
change permitted post-hoc would have been a genuine bug fix — e.g. a crash
or a broken regex — and none was needed; the script ran clean on the first
attempt.)

## Data

Reuses the exact same Kavach-PB population files the rest of the repo's eval
harnesses use (not a re-synthesized copy):

- `benchmarks/results_v2/_kavach_pb_attack_checkpoint.json` — 519 attack
  cases (AtomicRedTeam capped 456 + GTFOBins capped 63)
- `benchmarks/results_v2/_kavach_pb_bfcl_general_purpose_checkpoint.json` —
  793 BFCL general-purpose benign cases
- `benchmarks/results_v2/_kavach_pb_benign_v0_agent_shaped_checkpoint.json` —
  55 agent-shaped benign_v0 cases

Each case's `call_text` field (`tool:<name> args:<json>`) is scanned
case-insensitively against every pattern; any match flags the case BLOCK,
otherwise ALLOW. This is a single binary decision — no BLOCK/ESCALATE/ALLOW
tri-state, no confidence, no minister attribution, unlike Kavach itself.

## Results (one run, unedited)

| | n | flagged | rate |
|---|---|---|---|
| Attack recall (519 total) | 519 | 63 | **12.1%** |
| FPR — BFCL general-purpose benign (793) | 793 | 0 | **0.0%** |
| FPR — agent-shaped benign_v0 (55) | 55 | 0 | **0.0%** |
| FPR — combined benign (848) | 848 | 0 | **0.0%** |

For comparison, Kavach's own deterministic-only layer (VAULT/EXECUTOR,
before cosine triage) reports 34.2% and 34.5% recall on the relevant
sub-populations, and the full pipeline reports 74.4% / 90.1%, with 0 new
hard-block FPs on the same two benign populations (see root README, "Round
2" section). The naive baseline's 12.1% recall sits well below even the
deterministic-only numbers, which is the expected shape for an unvalidated,
un-corpus-driven blocklist — most attack cases in Kavach-PB simply don't
contain any of these ~30 literal strings (e.g. structured PowerShell/AST-only
attack shapes, or techniques expressed without any of the chosen keywords at
all). The 0.0% FPR is unsurprising for the same reason: a short hand list is
too narrow to false-positive much, not evidence it's a good detector — a
naive list that flags nothing on benign traffic is trivially easy to build
and tells you nothing about its ability to actually separate attack from
benign in general.

## Files

- `naive_baseline.py` — the ~30 hand-written patterns + scoring script. Run
  with `python3 eval/naive_baseline/naive_baseline.py` from the repo root.
- `naive_baseline_results.json` — full per-case output from the single run
  (which patterns matched, if any, per case).

## What this does NOT do

- Does not touch, call, or modify any of Kavach's actual detection code
  (`parliament/`, `kavach_eval/`, `benchmarks/`). Purely a standalone,
  read-only comparison script.
- Does not attempt AST parsing, tokenization, session/taint tracking,
  provenance, cosine similarity, or any corpus-driven expansion — all of
  which Kavach's real pipeline uses and this intentionally does not, to keep
  the "naive" framing honest.
- Was not iterated on, tuned, or pattern-adjusted after seeing scores.
