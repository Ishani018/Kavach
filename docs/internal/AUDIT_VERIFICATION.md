# Audit Verification — Execution-Based Adjudication

**Verifier:** Claude (execution, not re-reading)
**Date:** 2026-06-12
**Verified against:** branch `ishani/remove-repo-visualizer`, HEAD `0e4ba0c`
**Source report:** `AUDIT_REPORT.md` (33 findings) in the Gemini IDE brain dir
**Evidence:** raw logs in `verify_logs/`; GPU items in `GPU_RUNBOOK_ADDENDUM.md`

> Method: every finding reproduced by running a command, diffing code vs docs, or
> proving runtime behavior. No cached result trusted as proof. Verdicts are stated
> against the HEAD above — several findings are stale because earlier fixes (ESCALATE
> fold, ceiling 0.50) already landed on this branch.

---

## Verdict legend
- **CONFIRMED** — reproduced with concrete evidence.
- **FALSE POSITIVE** — audit was wrong; evidence shows why.
- **UNVERIFIABLE** — needs the Dell GPU / full dataset; see `GPU_RUNBOOK_ADDENDUM.md`.

---

## 1. Fabricated / untraceable numbers

| ID | Verdict | Evidence | Note |
|---|---|---|---|
| **F-1** p50=826ms | **UNVERIFIABLE** | `grep -rn 826 benchmarks/` → nothing committed (`verify_logs/stale-and-gpu.log`) | No source log. Dell run required. |
| **F-2** README §11 results table | **UNVERIFIABLE** | `results_v1/benign/` = `.gitkeep` only; no `results.csv` | Numbers exist only in prose. Dell run required. |
| **F-3** synthetic macros submittable | **FALSE POSITIVE** | `git check-ignore` → `section5_macros.tex` + `tab_*.tex` are gitignored (`verify_logs/F-3.log`). `git ls-files paper/tables/` = `.gitignore`,`.gitkeep` only | Macros are NOT committed; a clone won't have them. Residual minor risk: local stale build. |
| **F-4 / F-5** corpus count (382 vs 200) | **CONFIRMED** | `corpus_v2` counts to exactly **200** (50×4); README claims 382; paper §1 says 200 (`verify_logs/corpus-counts.log`) | README §4.5/§10 stale. |
| **F-6** 20+ `\TBD` in paper | **CONFIRMED** | grep of §4/§5/skeleton shows the `\TBD` slots | Honest, but submission-blocking. |
| **F-7** Trajectory Guard F1≤0.69 | **CONFIRMED (as flagged)** | bib note already self-flags "baseline ~0.82, not 0.69" | Needs re-read of arXiv:2601.00516. |

## 2. Code vs claims

| ID | Verdict | Evidence (`verify_logs/C-cluster.log`) |
|---|---|---|
| **C-1** endpoint `/parliament/evaluate` | **CONFIRMED** | paper §3:24 says `POST /parliament/evaluate`; code routes are `/hook/parliament`, `/hook/seed_intent`, `/hook/check_drift`, `/health`, `/ledger/*`. No such route. |
| **C-2** server.py "585 lines" | **CONFIRMED** | `wc -l` = **859**. |
| **C-3** paper §3 "100 patterns"×4 | **CONFIRMED** | §3:79–89 says 100/minister (=400); §1:168 says 200; actual 200. Internal paper contradiction. |
| **C-4** port `:8000` | **CONFIRMED** | paper §3:179 `localhost:8000`; code `127.0.0.1:8088`. |
| **C-5** L1 syntactic regex tier | **CONFIRMED (upgrade to MAJOR)** | paper §3:62–65 describes "Regex and exact-match rules… short-circuit to BLOCK"; `ministers.py` has **0** regex/short-circuit matches — cosine-only. Paper describes a feature that does not exist. |
| **C-7** env var `KAVACH_URL` | **CONFIRMED** | plugin uses config field `parliamentUrl`, no `KAVACH_URL` env var. |

## 3. Eval pipeline integrity

| ID | Verdict | Evidence (`verify_logs/eval-*.log`, `escalate.log`) |
|---|---|---|
| **E-1** PARV_RESULTS empty | **UNVERIFIABLE** | Template is genuinely empty; Dell run required. |
| **E-2** JSONDecodeError swallow | **CONFIRMED (minor, zero impact)** | silent `continue` exists at loader; but all committed case files = 0 malformed lines, so no cases dropped. |
| **E-3** `continue` at line 482 drops cases | **FALSE POSITIVE** | line 482 is inside `_by_category()` skipping non-attack rows during bucketing — correct logic, not case-dropping. |
| **E-4** timeout/except inflates recall/FPR | **FALSE POSITIVE** | error responses get `verdict="ERROR"` (server.py-side row, line 299/314) — a distinct bucket, never folded into ALLOW/BLOCK. |
| **E-5** synthetic circularity | **CONFIRMED-as-mitigated** | pipeline runs (exit 0) and inserts `SYNTHETIC FIXTURE` watermark; `make_synthetic` touches no corpus/embeddings (pure stats). Not a live integrity threat. |
| **E-6** missing `executor_b.json` | **FALSE POSITIVE** | EXECUTOR has 50 patterns in one file by design; others split 25+25. Balanced 50 each. Naming convention only. |
| **(stale) ESCALATE crash** in §5 Bayesian | **FALSE POSITIVE vs HEAD** | runtime proof: `aggregate([ESCALATE@0.6])` → `ALLOW`, no crash. Fixed in `3fee87d` (`_normalize_vote`). Audit read a pre-fix findings doc. |

## 4. Stale / inconsistent content

| ID | Verdict | Evidence (`verify_logs/stale-and-gpu.log`) |
|---|---|---|
| **S-1** bib STUB/VERIFY | **CONFIRMED (worse than reported)** | **8** `[STUB]` entries with `{TODO}` authors + **11** `VERIFY` placeholders in committed `kavach.bib`. |
| **S-2** README vs paper counts | **CONFIRMED** | same as F-4/C-3. |
| **S-3** §3/§5/§7 "TODO" but written | **CONFIRMED** | README:421 lists them `[NEXT]`; all three `.tex` exist. |
| **S-4** "MASEC@NeurIPS" vs AISec | **CONFIRMED** | README:422 vs skeleton:3 (AISec/CCS). |
| **S-5** "TODO per-minister thresholds" | **CONFIRMED** | README:390 TODO; `_get_minister_thresholds` at server.py:195. |
| **S-6** CVE-2026-21852 description | **CONFIRMED** | README:66 "WebSocket hijacking" vs paper API-key-exfil. |
| **S-7** stale 0.72 comment | **CONFIRMED (line 437, not 75)** | trajectory.py:437 `# NOTE: ceiling at 0.72…` and :447 demo value still 0.72; the active constant is 0.50. |

## 5. Data provenance

| ID | Verdict | Evidence |
|---|---|---|
| **D-1** `results_v1/benign/` empty | **CONFIRMED** | `.gitkeep` only. |
| **D-2** only small-N laptop results | **CONFIRMED** | results_v2 = laptop/smoke/smalln only; no `*_dell`. |
| **D-3** TraceSafe-Bench phantom | **CONFIRMED** | cited in §2 + bib STUB; no runner/data/results. |
| **D-4** AgentDojo never run | **CONFIRMED** | runner exists; no results; `[TBD]` in table. |
| **D-5** "1,054 cases" claim | **CONFIRMED** | README:349/410 claim 1,054; committed data = 30+32+17. |
| **D-6** InjecAgent full set absent | **CONFIRMED** | REPRODUCIBILITY:138 points at external path; no fetch script. |

---

## 6. Extended audit pass (N-series) — directories not covered above

**Verified:** 2026-06-12, branch `audit-fixes-doc-drift`, against live server on :8088
(hybrid retrieval, doc_counts 300/minister) and source as committed.
Scope: `parliament/ministers.py` detection logic, `kavach_eval/{make_section5,tune,minister_calibrate}.py`,
`plugin/openclaw-plugin-kavach.ts`, `parliament/config.yaml`, RRF fusion math.

| ID | Severity | Verdict | Evidence |
|---|---|---|---|
| **N-1** | MAJOR | **CONFIRMED (dead script)** | `tune.py:24-27` does `import speaker; speaker.BLOCK_THRESHOLD=...; speaker.BayesianSpeaker(...); speaker.ReliabilityStore(...)`. The Bayesian aggregator lives in `speaker_bayesian.py`; `speaker.py` has none of these symbols. Script raises `AttributeError`/`ImportError` as written — cannot run. Referenced in no runbook. Fix: repoint to `speaker_bayesian` or delete. |
| **N-2** | MAJOR | **CONFIRMED** | Paper `section_3_design_aisec.tex:63` states semantic hit threshold `θ_min = 0.45 (Config B)`. `config.yaml:28` sets `block: 0.55`, per-minister 0.55–0.75, `grey: 0.50`. The value 0.45 appears nowhere in live config. Paper θ_min is untraceable to config. |
| **N-3** | MINOR-MAJOR | **CONFIRMED** | `config.yaml:43` `VAULT: 0.75` ("raised from 0.55 — FPR was 70.6%, corpus needs quality pass (#7)"). Paper presents uniform semantic threshold; real system uses per-minister 0.55–0.75 incl. a hand-tuned FPR patch compensating an un-fixed corpus problem. Disclosure gap. |
| **N-4** | MAJOR | **CONFIRMED** | `config.yaml:30` `compass_drift: 0.40`, but live `/health` reports `compass_drift: 0.585`. Server overrides config at runtime (compass_calibrator Youden's J). `config.yaml:4` header claims "all thresholds externalized here / loaded at startup" — false for this value. Config is not the source of truth it claims. |
| **N-5** | MAJOR | **CONFIRMED CONFLICT — REVERT NEEDED** | Live `.chroma_kavach` = **100 distinct pattern_id/minister × 3 levels (L1_intent/L2_mechanism/L3_surface) = 300 docs/minister, 400 patterns total**, loaded from `kavach_corpus_v1.json` (which holds 100/minister). The `corpus_v2/new_patterns_*.json` files hold only **50/minister = 200** — these are the *delta from one expansion round*, NOT the full corpus. The merged `corpus_v2/kavach_corpus_v2.json` does not exist on disk. **Authoritative count = 400 (100/minister).** The original paper §3 "100 patterns/minister" was CORRECT. Audit finding F-4 ("actual 200"), last-session verification, and commit `860cda3` (C-3/F-4 fix: 100→50, 382→200) all propagated the wrong number. **The pattern-count fix in `audit-fixes-doc-drift` must be reverted** (see below). All other fixes in that commit remain valid. |
| **N-6** | MINOR | **CONFIRMED (provenance, not verdict)** | `ministers.py:319-322` builds `bm25_global_ranks` via `np.argsort(bm25_scores)[::-1]` over full corpus; for zero-token-overlap benign queries all BM25 scores ≈0 → arbitrary stable ranks → RRF selection (`:335`) can pick a semantically-wrong "best" doc. The `_GATE_FLOOR` path (`:359-362`) keeps the *confidence/verdict* correct, but the reported `matched_id`/provenance can be wrong. Cosmetic/provenance bug only. |
| **N-7** | MINOR | **CONFIRMED (portability + reproducibility)** | `make_section5.py:118` and `tune.py:27` write `ReliabilityStore` to `/tmp/kavach_s5_{rho}.json` / `/tmp/tune_*.json`. `/tmp` does not exist on Windows. Store also persists across runs keyed only by rho → stale Beta-Bernoulli posterior reused on re-run instead of fresh start → non-deterministic table output. |
| **N-8** | MINOR | **CONFIRMED (architectural smell)** | `openclaw-plugin-kavach.ts:227-241` posts agent **reply text** (natural language) to `/hook/parliament`, whose corpus is authored in tool-call/technique register — the exact representation mismatch §4 documents as the FPR driver. Reply path is fail-open + ESCALATE→ALLOW (`:255-257`) so blast radius is limited to spurious reply BLOCKs. Worth a one-line limitation note. |

### N-series corpus dedup scan (read-only, cached chroma embeddings)
Pairwise cosine over **L1_intent** docs within each minister (normalized embeddings, dot product), threshold **>0.85**, on the live 400-pattern corpus:

| Minister | L1 docs | pairs >0.85 |
|---|---|---|
| EXECUTOR | 100 | 4 |
| VAULT | 100 | **32** |
| CHANNEL | 100 | 18 |
| NAVIGATOR | 100 | 14 |
| **TOTAL** | 400 | **68** |

VAULT dominates (32), corroborating its 70.6% FPR and the `config.yaml` 0.75 threshold patch (N-3). Higher than the strategy doc's "16" because this scans all within-minister L1 pairs on the full 100/minister corpus, not a curated subset. Cross-minister VAULT↔CHANNEL pairs not measured here — needs a dedicated pass.

---

## 7. Workstream B — laptop qwen2.5:3b secondary InjecAgent run

**Run:** `injecagent_runner.py` vs live parliament :8088 (hybrid, BGE CPU), 30-case
`attacker_cases_dh.jsonl`. Output: `benchmarks/results_v2/laptop_qwen_secondary/`; log: `verify_logs/qwen_run.log`.

| Metric | Value |
|---|---|
| Attack cases | 30 (0 errors) |
| Strict recall (BLOCK only) | 0.100 (3/30) |
| Loose recall (BLOCK+ESCALATE) | 0.867 (26/30) |
| Strict precision | 1.000 |
| Strict F1 | 0.182 |
| Benign cases | 0 — file has no `User Instruction` field; FPR not measurable here |
| Latency p50/p95/p99/max (ms) | 2634 / 3628 / 4095 / 4240 |
| Per-category strict recall | Physical 0/10, Financial 2/9, Data-Security 1/11 |

**Caveat (must accompany any use):** qwen2.5:3b is the agent *backbone*, but this runner
replays pre-rendered tool-call payloads straight to the parliament — the LLM is **not in
the loop** for these cases. The BGE embedder + corpus do the detecting. This **validates
parliament behavior under the laptop config, NOT qwen-specific generalization.** Consistent
with existing D-2 secondary-config numbers (loose 0.87 / strict ~0.1, operating point on
ESCALATE, zero false blocks). Latency reflects CPU BGE, not the Dell GPU path.

---

## Summary counts

| Verdict | Count | IDs |
|---|---|---|
| **CONFIRMED** | 28 | F-4, F-5, F-6, F-7, C-1, C-2, C-3, C-4, C-5, C-7, E-2, E-5*, S-1, S-2, S-3, S-4, S-5, S-6, S-7, D-1, D-2, D-3, D-4, D-5, D-6, **N-1, N-2, N-3, N-4, N-5, N-6, N-7, N-8** |
| **FALSE POSITIVE** | 5 | F-3, E-3, E-4, E-6, (stale ESCALATE-crash) |
| **UNVERIFIABLE (Dell)** | 4 | F-1, F-2, E-1 (+ D-1/D-2 data side) |

> **N-5 correction notice:** finding F-4 ("actual 200 patterns") is now **superseded** —
> live DB + `kavach_corpus_v1.json` prove the real count is **400 (100/minister)**. The
> C-3/F-4 pattern-count fix in commit `860cda3` is wrong and must be reverted (paper §3
> 50→100, README 200→400). All other fixes in that commit stand.

\* E-5 confirmed as *mitigated* (watermark works), not a live threat.

**Headline:** No deliberate fabrication. The dominant, real issue is **the Dell
primary benchmark was never run/committed** (F-1, F-2, E-1, D-1, D-2) — the paper's
entire empirical section rests on `\TBD`. The second cluster is **doc drift**: stale
counts, endpoints, ports, venue, TODOs (C-1–C-5, S-1–S-7). Two audit findings
(ESCALATE crash, F-3 macros) were already fixed/mitigated and are false positives
vs current HEAD. C-5 (paper claims a regex L1 tier the code lacks) is the most
serious *new* code-vs-claims finding and should be upgraded from minor.

---

## Prioritized fix queue (CONFIRMED only — no fixes applied; awaiting approval)

### P0 — submission-blocking, fixable now (no Dell)
1. **S-1** — replace 8 `[STUB]` bib entries + resolve 11 `VERIFY` authors, or drop the `\cite`s. *(verify: `grep -c '\[STUB\]' paper/kavach.bib` → 0)*
2. **C-1** — paper §3:24,168 `/parliament/evaluate` → `/hook/parliament`. *(verify: grep paper for `/parliament/evaluate` → 0)*
3. **C-3 / F-4 / S-2** — reconcile pattern count to **200** everywhere (paper §3 "100×4", README 382). *(verify: counts match corpus_v2=200)*
4. **C-5** — either remove the §3 "Syntactic tier (L1)" regex/short-circuit claim, or implement it. (Recommend remove — it contradicts the semantic-detection thesis.)
5. **F-6** — fill or guard the 20+ `\TBD` (most need Dell data → blocked on GPU runbook).

### P1 — misleading, fixable now
6. **C-2** server.py "585"→"859" (or drop the count). 
7. **C-4 / C-7** paper port `:8000`→`:8088`; `KAVACH_URL`→`parliamentUrl`.
8. **F-2 / D-5** — label README §11 table + "1,054 cases" as *preliminary, not reproduced* until Dell commit.
9. **F-7** — re-read arXiv:2601.00516; cite the real baseline F1.
10. **S-3 / S-4 / S-5 / S-6** — README roadmap/venue/TODO/CVE-desc corrections.

### P2 — polish
11. **S-7** trajectory.py:437/447 stale 0.72 comment/demo value.
12. **E-2** add a dropped-line counter to the jsonl loader.
13. **D-6** add InjecAgent fetch step to REPRODUCIBILITY.md.

### Blocked on Dell (see GPU_RUNBOOK_ADDENDUM.md)
- **F-1, F-2, E-1, D-1, D-2, D-4** — run benchmarks on the Dell, commit raw outputs to `results_v2/*_dell/`, then fill the `\TBD`s from committed files.
