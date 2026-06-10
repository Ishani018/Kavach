# Kavach — Master Consolidation & Pre-Submission Runbook
**Generated June 10, 2026.** Single source of truth for today's work. Open this tonight before pushing.

Deadline: AISec 2026 (ACM CCS workshop, The Hague) — **July 24, 2026 (44 days out).**

---

## 1. Where everything lives right now

Nothing is pushed yet. All of today's work is local commits on three branches in the repo, plus standalone patch files. Two ways to land it (pick ONE per branch):

- **If you push from the extracted `kavach_push_updated/` repo** (the zip): all 9 `main` commits and both feature branches are already committed there. Just push.
- **If you push from your primary `kavach_push/` working copy** (still pristine at `1786e58`): apply patches `0005`–`0009` on top of the four commits already in the zip... which your primary copy doesn't have either. So for the primary copy, simplest is to apply ALL nine as patches, or just push from the extracted repo. **Recommended: push from the extracted repo, then resync the primary copy** (§3).

### `main` — 9 commits beyond the zip baseline `1786e58`
| # | Commit | What | In zip? |
|---|---|---|---|
| 1 | `afde3a7` | adaptive_attack v3 — test the REAL Speaker | ✅ zip |
| 2 | `ecdb7a1` | reconcile bge-base 768-d + Gemma4 27B in paper | ✅ zip |
| 3 | `231228d` | SHA-256 hash-chained ledger + `/ledger/verify` | ✅ zip |
| 4 | `bfc541c` | ACM sigconf AISec skeleton | ✅ zip |
| 5 | `7ae1fbf` | latency scrub + artifact flags + runbook addendum | patch **0005** |
| 6 | `19bd1a4` | provenance Axis B (taxonomy-grounded, tamper-evident) | patch **0006** |
| 7 | `3ce492c` | paper prose wired (§1/§3/§4/§5/§7, compiles) | patch **0007** |
| 8 | `6775da9` | make_section5.py — one-command table generation | patch **0008** |
| 9 | `c65d6d8` | kavach.bib — verified anchors + honest stubs | patch **0009** |

### `ishani/hybrid-retrieval` — rebased onto main, +2 commits
`72ba3bc` hybrid BM25+dense RRF · `4e5f0eb` **RRF calibration bug fix** (the one that would have blocked benign calls at ~100% FPR).

### `ishani/dynamic-thresholds` — rebased onto main, +2 commits
`14925ab` dynamic COMPASS thresholds · `adc2914` duplicate per_minister + double-modulation fix.

---

## 2. Push sequence (tonight)

From the extracted repo (`C:\Users\ishan\Downloads\kavach_push_updated`). Apply patches 0005–0009 FIRST if they aren't already in this repo's main — check with `git log --oneline -9 main`; if you see `c65d6d8` at the top, they're in, skip to pushing.

```cmd
cd C:\Users\ishan\Downloads\kavach_push_updated
git log --oneline -9 main          :: expect c65d6d8 at top. If only bfc541c, apply patches:
:: git am C:\Users\ishan\Downloads\0005-docs-cleanup-followup.patch
:: git am C:\Users\ishan\Downloads\0006-provenance-axis-b.patch
:: git am C:\Users\ishan\Downloads\0007-paper-prose-wired.patch
:: git am C:\Users\ishan\Downloads\0008-section5-harness.patch
:: git am C:\Users\ishan\Downloads\0009-kavach-bib.patch
```

**main** is protected (PRs only — you hit GH013 earlier). Push as a PR branch:
```cmd
git push origin main:ishani/audit-fixes
```
Open PR `ishani/audit-fixes` → `main`, let Parv review, merge.

**Feature branches** (not protected; rebased, so force-with-lease is required):
```cmd
git checkout ishani/hybrid-retrieval
git push --force-with-lease origin ishani/hybrid-retrieval
git checkout ishani/dynamic-thresholds
git push --force-with-lease origin ishani/dynamic-thresholds
```
If either force-with-lease is REJECTED → the remote branch moved since the zip. **Stop, ping Parv, do not `--force`.**

After the `audit-fixes` PR merges, optionally re-align the feature branches onto the new main (`git rebase origin/main` on each, then force-with-lease again) so their own PRs show clean diffs.

---

## 3. Resync your primary working copy (after pushing)
```cmd
cd C:\Users\ishan\Downloads\kavach_push
git fetch origin
git checkout main
git reset --hard origin/main
```

---

## 4. When Parv's Dell data lands (~48h) — the one-command workflow

The whole §5 + §4-cost table pipeline is one command. Pre-reqs Parv must satisfy (in `DELL_BENCHMARK_RUNBOOK.md` June-10 addendum): use `main` (not trajectory-monitor), `pip install rank-bm25`, confirm `/health` shows `retrieval_mode: hybrid`, dump `minister_runs.jsonl` per the updated schema (ESCALATE + compass_sim + traj_risk fields), **commit raw outputs to `results_v2/`**.

```cmd
:: §5 + §4-cost tables, measured rho, straight into the paper:
python kavach_eval/make_section5.py minister_runs.jsonl --rho-auto
cd paper
pdflatex skeleton_aisec.tex & bibtex skeleton_aisec & pdflatex skeleton_aisec.tex & pdflatex skeleton_aisec.tex
```
That regenerates `paper/tables/*.tex` (gitignored, rebuilt from data) and fills every `[TBD]` table. The prose already `\input`s them.

For the §4 detection numbers (InjecAgent recall/FPR, native benchmark, latency p50/p95) — those come from Parv's committed `results_v2/` JSON; drop them into the marked `\TBD` slots in `section_4_deployment.tex` by hand (they're labeled).

---

## 5. Integrity scorecard — what today fixed

| Audit finding | Status |
|---|---|
| adaptive_attack tested a non-existent Speaker; all its numbers invalid | ✅ Fixed — v3 tests real `combine_verdicts`; old numbers marked invalid |
| `adaptive_attack.py` couldn't import against merged repo | ✅ Fixed |
| Hybrid RRF rescaling → would block benign at ~100% FPR | ✅ **Caught & fixed** before any Dell run |
| Duplicate `per_minister` YAML key silently dropping VAULT value | ✅ Fixed |
| Latent double-modulation (server.py + speaker.py) | ✅ Fixed + documented |
| `eval_harness` `MinisterVote` import silently broken → ablation crash | ✅ **Caught & fixed** |
| Stale Speaker decision table in §3 (said ESCALATE, code does BLOCK) | ✅ Fixed |
| bge-large/sarvam in paper vs bge-base/Gemma in code | ✅ Fixed |
| Fictional `<200ms` / `<1s` latency claims | ✅ Scrubbed to measured 826/1649ms |
| Hash-chained ledger claimed but unimplemented | ✅ Implemented + `/ledger/verify` |
| 68 undefined citations | ✅ Resolved; paper compiles clean |
| Two headline numbers (98.4%, 2.1%) have no committed artifacts | ⏳ Flagged in README/FINDINGS; **Parv re-runs + commits** |
| InjecAgent FPR / latency / frontier numbers | ⏳ `[TBD]` — waiting on Dell data |

---

## 6. Verification to-dos that are GENUINELY yours (I can't do these)

1. **Confirm the backbone.** I set the paper to Gemma 4 27B per FINDINGS June 1. If any committed benchmark actually ran on sarvam, tell me and it flips back. (One fact I couldn't verify from artifacts.)
2. **Verify the `[NOTES-ID]` citations** in `kavach.bib` — ClawGuard 2604.11790, AgentArmor 2508.01249, LlamaFirewall 2505.03574, PRISM 2603.11853, MELON 2502.05174. Open each arxiv.org/abs/<id>, confirm author+title, remove the `(VERIFY)` placeholders. (Verified already: AgentDojo, InjecAgent, BGE.)
3. **Fill or remove the `[STUB]` citations** (~18). Each is marked TODO with the suspected real ID where known.
4. **Verify the ATLAS technique IDs** in `parliament/provenance.py` against atlas.mitre.org — the taxonomy is churning monthly; I corrected several vs the research draft but the live source is ground truth.
5. **Get `acmart.cls`** for the real build (Overleaf has it built-in, or CTAN/`tlmgr install acmart`). My validation used a stand-in `article` class because acmart isn't in this environment; structure is proven, but do a real acmart build.

---

## 7. Paper build (full, with acmart)
```
cd paper
pdflatex skeleton_aisec.tex
bibtex skeleton_aisec
pdflatex skeleton_aisec.tex
pdflatex skeleton_aisec.tex
```
Sections `\input` by the skeleton: `section_1_intro_aisec`, `section_2_background`, `section_3_design_aisec`, `section_4_deployment`, `section_5_frontier`, `related_work_table`, `section_7_limitations`, plus `tables/*` (generated). The old `section_4_temporal_spatial.tex` is intentionally NOT input (demoted to a §3 design principle per the audit).

---

## 8. Suggested timeline to July 24
- **This week:** push tonight; Parv's P0 Dell runs; verify citations + ATLAS IDs.
- **~June 14:** data in → `make_section5.py` → §5 tables; fill §4 detection numbers.
- **June 18–20:** full acmart draft, internal read, Prof. Banginwar pass.
- **July 1–14:** tighten, re-run anything flaky, optional AgentDojo partial (kills the "ClawGuard head-to-head" reviewer question).
- **July 18–22:** freeze, proofread, anonymization check, artifact link (anonymous.4open.science).
- **July 24:** submit.

---

*This document reflects the repo state at commit `c65d6d8` on `main` plus the two rebased feature branches. Every change was verified offline (12/12 speaker tests; trajectory demos; hybrid scenario; hash-chain + provenance tamper tests; full paper compile through bibtex). The only `[TBD]`s remaining are real measured numbers awaiting the Dell runs.*
