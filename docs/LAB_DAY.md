# Lab Day — July 2–3, 2026

The single file to follow on lab day. Two independent tracks: **Ishani** runs the
primary benchmarks on the Dell; **Parv** runs the embedding comparison on his
laptop. The tracks do not block each other — start both, sync at end of day.

Everything is on `main`. There is no `parv` branch anymore — ignore any older doc
that says `git checkout parv`.

---

## Before you leave home (both machines)

```bash
cd Kavach
git checkout main
git pull origin main
```

Confirm Ollama has the models each machine needs:
- **Ishani / Dell:** `ollama list` must show `gemma4:26b`
- **Parv / laptop:** `ollama list` must show `qwen2.5:7b` — needed for the
  AgentDojo subset leg only (the InjecAgent leg needs no LLM; it only re-embeds
  and replays). Pull it ahead of time: `ollama pull qwen2.5:7b`.

---

## Ishani — Dell Precision 3660 (RTX 4090)

Primary benchmarks. The whole session runs through one browser dashboard.

### 1. Boot

```bash
# Start OpenClaw + dependencies (hooks already fixed upstream in 2026.4.15)
bash kavach_boot.sh --skip-patch

# Rebuild ChromaDB — REQUIRED. The live index does not pick up corpus edits
# automatically, and CHAN-101 (101st CHANNEL pattern) must be present.
python corpus_loader.py --rebuild

# Health check — MUST show CHANNEL: 303 (not 300). If 300, the rebuild didn't
# take: stop, re-run the rebuild, restart, recheck.
curl -s http://127.0.0.1:8088/health | python -m json.tool
```

If `kavach_boot.sh` didn't start the parliament itself, start it:

```bash
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
```

Optional one-time: install the pre-commit hook that keeps the concatenated paper
draft in sync (only matters if you edit `paper/` on the Dell):

```bash
cp docs/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

### 2. Launch the dashboard

```bash
python tools/dell_lab.py
```

This serves a dark-theme dashboard on `http://127.0.0.1:7788` and opens Chrome
automatically. It does **not** start parliament or Ollama — it checks they're up
(top status bar: parliament dot green, ChromaDB `C303`, gemma4:26b listed). Each
benchmark is a button; the live log streams in the center; results land in the
right panel as files appear.

### 3. Run order (click the buttons in this order)

The dashboard buttons map to `scripts/dell_run_*.sh`. Run them top to bottom:

1. **AgentDojo** (PRIMARY — this is the paper number). Slack suite, gemma4:26b,
   ~45–90 min.
   - The early-abort warning fires if utility stays 0% after 20 pairs. If it
     fires, **something is wrong — stop and message Ishani.**
   - `EMPTY ACTION ... 'tool:get_channels args:{}'` in the log is **expected**
     (`get_channels` is a real no-arg tool). Only `tool:unknown` would be the real
     bug. Do **not** abort over `get_channels`.
   - At end of run the **KAVACH AUDIT** line must show real screening
     (`N reached, M screened, K BLOCKED`) and `run_fully_defended: true`. If it
     says `screened 0 tool calls`, the numbers are fake — do not report them.

2. **InjecAgent** (SECONDARY). Full 1,054 cases + benign FPR.
   - Sanity check vs the committed Dell figures: **direct-harm** loose ~0.90 /
     strict ~0.63 / hard-block FPR ~23.5%; **data-stealing** loose ~0.875 /
     strict ~0.44 / FPR 0.0%. If wildly off, note it and move on — **do not
     re-run.**
   - Threshold lives in `parliament/config.yaml` (per-minister, hybrid). **Do not
     edit it.**

3. **Red-team** (TERTIARY — time permitting). LLM evasion, 250 seeds,
   threat-intel RAG paraphraser.
   - Checkpointed: if it dies, relaunch the **same command with `--resume`**.
   - Note the exact `evasion_report_*.json` filename it prints — the Improvement
     Loop consumes it.

4. **Improvement Loop** (LAST — needs the red-team report from step 3).
   - It dry-runs first (writes nothing). If `n_evaded > 0`, it proceeds and will
     **pause for approval** inside the dashboard: a purple box appears above the
     log showing the iteration summary (evasion before/after, candidate pattern)
     with **YES / NO** buttons. Clicking writes `yes`/`no` to the loop's stdin —
     no terminal needed.
   - **Approve carefully.** Each `yes` permanently **appends** patterns to
     `kavach_corpus_v1.json` (append-only — never edits/deletes existing). The
     ground truth `kavach_corpus_v1_ORIGINAL.json` is frozen; recover anytime with
     `git show origin/main:kavach_corpus_v1_ORIGINAL.json`.
   - The loop stops on its own (evasion hits 0 / nothing passes the gate / no
     candidate fixes its evasion / delta stops improving / you decline). There is
     no iteration counter.

### 4. Commit Dell results

Results go to a `parv-results` branch (NOT `main`). Whoever finishes first
creates this branch — the other just checks it out.

```bash
git fetch origin
git checkout parv-results 2>/dev/null || git checkout -b parv-results
git add benchmarks/results_v2/ kavach_eval/evasion_results/ \
        kavach_eval/corpus_agent/results/ kavach_eval/improvement_loop_audit.jsonl
git commit -m "data: Dell gemma4:26b AgentDojo + InjecAgent + red-team + loop results"
git push -u origin parv-results
```

Then message Ishani the headline numbers.

### Dell gotchas

- **Gateway mode does not fire the hook.** Use embedded mode only
  (`kavach_boot.sh` already does this). If the ledger shows no entries after tool
  calls, you're on the gateway path — stop and check the boot mode.
- **Parliament 500 on the first call** → ChromaDB wasn't rebuilt or has a stale
  handle. Stop, `python corpus_loader.py --rebuild`, restart parliament, retry.
  (Log symptom: `Nothing found on disk` from the HNSW reader.)
- **`\r: command not found` / `dos2unix`** → a script has CRLF line endings from
  the Windows checkout. Run `dos2unix scripts/*.sh kavach_boot.sh` then re-run.
- **Label outputs `_gemma_dell`**, never `_laptop` — this is the reportable config.

---

## Parv — Laptop (RTX 5060)

The embedding-model comparison. **Parallel and non-blocking** — it does not need
the Dell and does not need to sync with Ishani until end of day. If the laptop is
needed for anything else, this yields.

**Goal:** compare the deployed `BAAI/bge-base-en-v1.5` against `intfloat/e5-base-v2`
and `thenlp/gte-base` on **InjecAgent (full)** and a small **AgentDojo subset
(25 pairs)**, varying **only** the embedding model (thresholds, Speaker, corpus,
and agent backbone held identical). This turns the paper's "embedding model not
ablated; future work" (§3.2, §7) into a real result.

**Before lab day (not on the day):** the AgentDojo leg needs an agent backbone on
the laptop. Pull it ahead of time:
```bash
ollama pull qwen2.5:7b
```
(The InjecAgent leg does not use an LLM backbone — it only re-embeds and replays.
Only AgentDojo drives the agent, so only it needs `qwen2.5:7b`.)

**Safety:** scratch-only. Never touches `kavach_corpus_v1.json`,
`kavach_corpus_v1_ORIGINAL.json`, or the production ChromaDB. Each model gets its
own scratch index under `parliament/.chroma_embedding_test_<tag>/` (gitignored),
and the server is pointed at it via env vars — no file edits, nothing committed.

### Per-model procedure

Run this block **once per model**, serially (build index → start server against
it → run InjecAgent → stop server → next model). Do **bge first** to confirm the
harness reproduces the headline numbers, then e5, then gte.

```bash
mkdir -p kavach_eval/results/embedding_comparison

# ===== set these two lines per run, then run the rest unchanged =====
#   bge : MODEL=BAAI/bge-base-en-v1.5   TAG=bge
#   e5  : MODEL=intfloat/e5-base-v2     TAG=e5
#   gte : MODEL=thenlp/gte-base         TAG=gte
MODEL=intfloat/e5-base-v2 ; TAG=e5

# 1. Build that model's scratch ChromaDB (first use downloads the model ~440MB).
#    Confirm "indexed 1403 documents" and CHANNEL = 303.
python corpus_loader.py \
  --embed-model "$MODEL" \
  --corpus kavach_corpus_v1.json \
  --chroma parliament/.chroma_embedding_test_${TAG} \
  --rebuild --skip-smoke

# 2. Start parliament against that model + its scratch index (env overrides, no
#    YAML edit). Leave this running in its own terminal.
KAVACH_EMBED_MODEL="$MODEL" \
KAVACH_CHROMA_PATH="parliament/.chroma_embedding_test_${TAG}" \
  python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088

# 3. In a SECOND terminal, confirm the server loaded the right model:
curl -s http://127.0.0.1:8088/health | python -m json.tool   # "model" == $MODEL, CHANNEL 303

# 3a. InjecAgent (full, embedding-only replay — no agent backbone needed):
python injecagent_runner.py --full \
  --parliament-url http://127.0.0.1:8088 \
  --output kavach_eval/results/embedding_comparison/${TAG}/ \
  --include-benign

# 3b. AgentDojo SUBSET — 25 pairs (5 user × 5 injection), qwen2.5:7b backbone.
#     --max-pairs 25 truncates to exactly 25 pairs. This is a SUBSET, not the full
#     benchmark; it is for the embedding comparison only.
export OPENAI_API_KEY=ollama
export OPENAI_API_BASE=http://localhost:11434/v1
python benchmarks/run_agentdojo_kavach.py \
  --suite slack --model-id qwen2.5:7b \
  --kavach-url http://127.0.0.1:8088 \
  --max-pairs 25 \
  --out kavach_eval/results/embedding_comparison/agentdojo_subset_${TAG}/

# 4. Ctrl-C the server. Repeat from step 1 for the next model. Unsetting the env
#    vars (or just starting the server without them) restores the production config.
```

- **InjecAgent: full 1,054 cases** per model if the 5060 has time. If not, run a
  **stratified subset of ~150 cases**, the *same subset* across all three models,
  and append `SUBSET_n150` to the output dir name so it can't be mistaken for a
  full run.
- **AgentDojo: always the 25-pair subset** here — this is a fast comparison signal,
  not the headline AgentDojo number (that's Ishani's full Dell run). Keep
  `--max-pairs 25` identical across all three models.
- e5 and gte use a different query-prefix convention than BGE. If recall looks
  *catastrophically* low for one model, check the prefix before concluding it lost.

### What to record (per model)

A 3-row table (bge / e5 / gte) with **both** benchmarks per row:

| | InjecAgent (full) | | AgentDojo subset (25 pairs) | |
|---|---|---|---|---|
| **model** | strict / loose recall (DH, DS) | hard-block FPR | ASR with Kavach | utility under attack |

- InjecAgent numbers: from
  `kavach_eval/results/embedding_comparison/<tag>/summary.json` — strict recall,
  loose recall, hard-block FPR for both direct-harm and data-stealing.
- AgentDojo numbers: from
  `kavach_eval/results/embedding_comparison/agentdojo_subset_<tag>/` — the
  end-of-run summary's ASR (with Kavach) and utility-under-attack. Confirm the run
  log says `5 user tasks × 5 injection tasks = 25 pairs`.

### Commit laptop results

Whoever finishes first creates this branch — the other just checks it out.

```bash
git fetch origin
git checkout parv-results 2>/dev/null || git checkout -b parv-results
git add kavach_eval/results/embedding_comparison/
git commit -m "data: embedding-model comparison (bge / e5 / gte) — InjecAgent full + AgentDojo 25-pair subset"
git push origin parv-results
```

**Report whichever model wins, honestly.** If BGE wins or ties, it strengthens
the §3.2 justification; if an alternative wins, the paper says so. Do not
cherry-pick.

---

## End of day — both tracks

1. Both tracks have pushed their results to **`parv-results`** (Dell benchmarks +
   embedding comparison). Confirm `git log origin/parv-results` shows both commits.
2. The Dell run also produces the §5 vote dump. Regenerate the paper's §5 tables
   from it:
   ```bash
   python kavach_eval/make_section5.py minister_runs.jsonl --rho-auto
   ```
   This replaces the `[TBD]` slots in `paper/tables/*.tex` with measured numbers
   (the ablation uses the deployed pure-veto Speaker automatically — no extra
   steps). The embedding-comparison numbers fill the new comparison table the same
   way once Parv's results land.
3. Message Ishani the headline numbers from both tracks so the `[TBD]`s in the
   paper can be replaced and a fresh PDF compiled.
