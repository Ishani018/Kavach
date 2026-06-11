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
| False positives observed | 0 |
| Latency p50 / p95 | 2566 ms / 3198 ms (CPU) |

By harm category (strict block rate): Physical 0/10, Financial 3/9, Data Security 1/11.

## Honest caveats — read before citing
1. **No FPR measured.** `--include-benign` only runs benign-paired cases when a
   case carries a `user_prompt` field; `attacker_cases_dh.jsonl` does not, so
   `n_benigns = 0`. To get a laptop FPR, run against the paired benign set
   (`benchmarks/data/user_cases.jsonl`) or the benign-trace gate
   (`benchmarks/benign_traces.py`). **TODO.**
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
