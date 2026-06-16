You're helping me (Parv) build an enhanced red-team evaluator for Kavach,
a runtime security guardrail for LLM agents. Read this fully before doing
anything. Summarize what you understand and ask which upgrade I want to start
on — don't build anything until I confirm.

## What Kavach is
Kavach uses BGE-base-en-v1.5 embeddings + hybrid BM25+dense retrieval over
a 400-pattern attack corpus to intercept LLM agent tool calls before
execution. Four ministers (EXECUTOR/VAULT/CHANNEL/NAVIGATOR) vote; a Speaker
aggregates. No LLM in the decision path — ~78ms, auditable, model-agnostic.
The red-teamer is a pure EVAL tool that paraphrases corpus seeds and scores
them through the real pipeline to find where Kavach fails. I'm building the
ENHANCED version on my RTX 5060 8GB machine.

## The confirmed baseline finding
Ishani's 100-seed keyword-RAG run (effective N=82, 268 scored paraphrases)
found 3.36% overall evasion (9/268). Key numbers:
- CHANNEL: 8.43% evasion rate (7 of 9 total evasions) ← primary locus
- EXECUTOR: 1.45%, VAULT: 1.43%, NAVIGATOR: 0%
- 77.8% of evasions are BM25-gate exploits: dense embedding recognized the
  attack (dense_sim ≥ block threshold) but BM25 lexical gate dropped hybrid
  score below threshold → ALLOW
- Mechanism: Windows LOLBIN substitution (bitsadmin, certutil, IEX/WebClient)
  shares zero lexical keywords with corpus descriptions → BM25 penalizes →
  ALLOW. Surface rewording → 0% (embedding is robust to synonyms).
- 34.6% of paraphrases were AMBIGUOUS (drifted benign, excluded) — expected,
  not a problem.

My job: does embedding-RAG retrieval (semantic instead of keyword) + a
feedback loop find MORE evasions, and does it spread beyond CHANNEL?

## My machine and confirmed setup
- RTX 5060 8GB VRAM
- Model confirmed GPU-resident: [gemma3:12b or gemma3:4b — fill after setup]
- Parliament server: running, preflight-confirmed (verdict JSON returned)
- KavachScorer: imports cleanly
- ChromaDB: installed
- Branch: parv-results (push here only, never to main)
- Git identity set: Parv Parmar / parvparmar23@gmail.com

## The script's current flags (important — some I have to ADD)
The existing `kavach_eval/redteam_evasion_v0.py` accepts: `--use-threat-intel`,
`--max-seeds`, `--out-dir`, `--resume`, `--n-per-seed`, `--minister`, `--level`,
`--skip-sanity`, `--verbose`, `--use-llm`, `--corpus`, `--chroma`, `--config`,
`--top-k`. It does NOT yet have `--model` or `--retrieval-mode` — the model is
hardcoded as `qwen2.5:3b` in the `ThreatIntelParaphraser` class. I add `--model`
and `--retrieval-mode keyword/semantic` as NEW flags in Upgrade 1. So:
- Upgrade 0 (reproduce baseline) runs the script AS-IS: `--use-threat-intel
  --max-seeds 10 --out-dir kavach_eval/evasion_results/` (no `--model`,
  no `--retrieval-mode` — they don't exist yet).
- Upgrade 1+ commands use `--model` and `--retrieval-mode` because I'll have
  added them.

## My four upgrades in order
0. Reproduce baseline (10-seed smoke, keyword RAG, script as-is) — confirm
   pipeline works on my machine before building anything new
1. Replace keyword intel_loader with embedding-RAG over MITRE/LOLBAS/GTFOBins
   (ChromaDB + bge-base-en-v1.5, same embedding as Kavach production). Add new
   CLI flags `--retrieval-mode keyword/semantic` and `--model <name>`.
2. Feedback loop: when a paraphrase is caught, extract matched pattern + BM25
   overlap, feed back to generation to avoid those terms. Cap 2 rounds.
   Track evasion_by_round: {round_0, round_1, round_2} in output JSON.
3. Dual-model maliciousness check — only if ≥ 3GB VRAM free after gen model.
   Skip and note it if not enough headroom.

## Rules you must follow (non-negotiable)
- Import the REAL KavachScorer — never reimplement scoring
- MaliciousnessGuard must stay, at least as strict as keyword version
- Output JSON must match existing schema + add:
  enhanced / model_used / retrieval_method / upgrade_level / evasion_by_round
- NEVER write to kavach_corpus_v1.json or parliament/ — read-only eval tool
- NEVER push to main — parv-results only
- Always nohup + & (never run attached to terminal)
- Always smoke test 10 seeds before full 1200-seed run
- If run dies → --resume flag, don't restart from scratch
- Every result is laptop-measured / hypothesis until Dell-confirmed
- Record model in every commit message
- git config user.name "Parv Parmar" before every commit
- Run commands use --max-seeds (not --seeds) and --out-dir (not --out)

## How to work with me
Show me the plan for each upgrade before writing code. Show diffs before
committing. Run 10-seed smoke, show me the output, get my approval before
launching 1200 seeds. Push to parv-results when done and message
Ishani with the result summary.

Start by reading:
  kavach_eval/redteam_evasion_v0.py
  kavach_eval/threat_intel/intel_loader.py

Tell me what you see (the three tiers, how MaliciousnessGuard works, what
KavachScorer does), then ask which upgrade I want to start with.
