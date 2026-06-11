# Laptop secondary run — qwen2.5:3b (CPU-only)

**Cross-model generalization check.** Not the paper's headline numbers — those
are the Dell primary config (Gemma4 27B, RTX 4090). See `REPRODUCIBILITY.md`
("Hardware configurations") and `../PARV_RESULTS.md`.

## Configuration
- **Hardware:** Intel i5-1155G7 laptop, 16 GB RAM, **CPU only** (no GPU)
- **Agent backbone:** `qwen2.5:3b` via Ollama (v0.30.7)
- **Embedding model:** `BAAI/bge-base-en-v1.5` (768-d) — identical to Dell
- **Corpus:** same `kavach_corpus_v1.json` (1,400 docs across 5 collections) — identical to Dell
- **Parliament:** hybrid retrieval (BM25 + dense RRF), per-minister thresholds,
  `compass_drift` calibrated locally to 0.585
- **Date:** 2026-06-11

## Run
```bash
py benchmarks/injecagent_runner.py \
  --parliament-url http://127.0.0.1:8088 \
  --cases benchmarks/data/attacker_cases_dh.jsonl \
  --include-benign \
  --output benchmarks/results_v2/laptop_qwen25_3b
```
Wall-clock: 13:40:13 → 13:41:35 (~82 s for 30 attack cases).

## Results (measured)
| Metric | Value |
|---|---|
| Attack cases | 30 (0 errors) |
| **Loose recall** (BLOCK or ESCALATE) | **0.867** (26/30) |
| **Strict recall** (BLOCK only) | **0.133** (4/30) |
| Precision (strict) | 1.00 |
| Latency p50 / p95 | 2566 ms / 3198 ms (CPU) |

By harm category (strict block rate): Physical 0/10, Financial 3/9, Data Security 1/11.

### Benign FPR gate (`benign_results.json`)
Run separately against the 17 real benign InjecAgent user instructions
(`benchmarks/data/user_cases.jsonl`) via `benchmarks/benign_gate_usercases.py`:

| Metric | Value |
|---|---|
| Benign cases | 17 (0 errors) |
| **FPR (block-only)** | **0.0%** (0/17 hard-blocked) |
| FPR (block-or-escalate) | 23.5% (4/17 escalated) |
| Latency p50 / p95 | 2534 ms / 3141 ms (CPU) |

**Reading:** at the BLOCK level the laptop config is high-precision — it
hard-blocks **zero** benign instructions (passes the ≤5% gate) while still
hard-blocking some attacks. The operating point is shifted toward ESCALATE on
*both* sides (attacks: loose 0.87 vs strict 0.13; benign: 23.5% escalate vs 0%
block), i.e. the small CPU backbone produces more human-review flags and fewer
hard decisions, rather than more false blocks.

## Honest caveats — read before citing
1. **FPR measured separately** (the InjecAgent runner has no benign-only mode and
   `attacker_cases_dh.jsonl` carries no paired `user_prompt`, so its run reported
   `n_benigns = 0`). The benign gate above was run against the 17 real benign
   user instructions in `user_cases.jsonl`: **block-only FPR 0.0%**,
   block-or-escalate FPR 23.5%. Note this is 17 cases — a small sample; treat the
   23.5% escalate-FPR as indicative, not precise.
2. **Cross-model agreement is at the *flag* level, not the *block* level.** Loose
   recall generalizes well (0.87) but strict hard-BLOCK recall is low (0.13):
   most attacks land in ESCALATE under the laptop's freshly calibrated
   thresholds. The "backbone independence" claim holds for *flagging* attacks,
   not for the final block decision. Do not overstate this as "detection held
   identically."
3. Thresholds here were calibrated on this machine's corpus run; they are **not**
   matched to the Dell's. A matched-threshold comparison is the right apples-to-
   apples test and is still **TODO**.

Artifacts: `summary.json`, `results.csv` (per-case verdicts + per-minister sims).
