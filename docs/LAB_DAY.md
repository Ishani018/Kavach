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

1. **AgentDojo** (PRIMARY — this is the paper number, and the single
   highest-leverage result of the whole session). Slack suite, gemma4:26b,
   ~45–90 min.

   **The headline is a DELTA, not a single number.** A standalone "Kavach
   ASR = Y%" is uninterpretable without knowing the attack rate *without*
   Kavach. `run_agentdojo_kavach.py` already runs **both conditions in one
   invocation** — WITH Kavach and the undefended BASELINE — over the identical
   suite, model, attack, and user-task slice (only the Kavach hook toggles in
   the pipeline). AgentDojo tasks are deterministic by construction (fixed suite
   + fixed injection set, per-pair result caching), so both conditions see
   identical pairs — there is no seed to set. The end-of-run
   `agentdojo_summary.json` already computes `asr_reduction =
   baseline.ASR − with_kavach.ASR`. **That delta is the citable result:**
   "Kavach reduces AgentDojo Slack ASR from [baseline]% to [defended]% at
   [utility]% task utility."

   ```bash
   # Both conditions + benign-utility (over-block) pass, one command:
   python benchmarks/run_agentdojo_kavach.py \
     --suite slack --model-id gemma4:26b \
     --attack important_instructions \
     --benign \
     --out benchmarks/results_v2/agentdojo_dell
   # Headline lands in benchmarks/results_v2/agentdojo_dell/agentdojo_summary.json:
   #   .baseline.attack_success_rate   <- undefended ASR (what every number is measured against)
   #   .with_kavach.attack_success_rate <- defended ASR
   #   .asr_reduction                   <- the delta (the paper number)
   #   .benign_utility.benign_overblock <- FP cost of the defense on no-attack tasks
   ```

   - **The baseline is what every other number is measured against — protect
     it.** The script runs WITH-Kavach first, then baseline. If you must stop
     early, let it reach the baseline block (the second `run_one`) before
     killing it, or you lose the number that makes the defended result mean
     anything. If time is tight, a completed baseline + partial defended is
     more salvageable than the reverse.
   - The early-abort warning fires if utility stays 0% after 20 pairs. If it
     fires, **something is wrong — stop and message Ishani.**
   - `EMPTY ACTION ... 'tool:get_channels args:{}'` in the log is **expected**
     (`get_channels` is a real no-arg tool). Only `tool:unknown` would be the real
     bug. Do **not** abort over `get_channels`.
   - At end of run the **KAVACH AUDIT** line must show real screening
     (`N reached, M screened, K BLOCKED`) and `run_fully_defended: true`. If it
     says `screened 0 tool calls`, the numbers are fake — do not report them.
     A valid result needs BOTH the defended run fully screened (`failopen 0`)
     AND a non-zero baseline ASR to compare against.

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

This runs in parallel with Ishani's Dell work — you don't need to sync with her
until both tracks are done.

### What you're doing and why

The paper currently makes an honest admission: we chose `BAAI/bge-base-en-v1.5`
as Kavach's embedding model for offline-reproducibility reasons, but we never
compared it against alternatives (it's stated as future work in §3.2 and §7).
Your job today turns that admission into a real evaluated result: run the same
InjecAgent benchmark and a small AgentDojo subset against **three** embedding
models — BGE (current), `intfloat/e5-base-v2`, and `thenlp/gte-base` — holding
everything else identical, and record which one gives better recall/FPR. This
upgrades a "future work" limitation into a real finding. **Whatever wins, we
report honestly** — if BGE wins or ties it strengthens the paper's justification;
if an alternative wins, the paper says so. No cherry-picking.

### How it works (so you know what you're actually changing)

Kavach's parliament server does **all** the embedding. InjecAgent and AgentDojo
never embed anything themselves — they just POST raw action text to
`/hook/parliament` and get back a `BLOCK` / `ESCALATE` / `ALLOW` verdict. So
swapping the embedding model is three moves: **rebuild the corpus index with the
new model → restart the server with that model → run the benchmarks.** The agent
backbone (`qwen2.5:7b`, used only by AgentDojo) stays the same across all three
runs — the *only* thing changing is how Kavach embeds and scores actions. That's
exactly the variable we want to isolate.

### Before you leave home

```bash
cd Kavach
git checkout main
git pull origin main            # gets the --embed-model flag + this runbook

ollama pull qwen2.5:7b          # agent backbone for the AgentDojo leg
```

The three **embedding** models (BGE / e5 / gte) do **not** need a manual pull —
`corpus_loader.py` auto-downloads them from HuggingFace on first use and caches
them under `~/.cache/huggingface`. It's ~1GB total across the three, one-time.
Just have internet the first time you build each index; the first rebuild of each
new model includes its download.

### Run procedure — one model at a time (repeat 3×)

Do **BGE first** (it's the baseline — confirm the harness reproduces the paper's
committed numbers before trusting the alternatives). Then e5, then gte.

```bash
mkdir -p kavach_eval/results/embedding_comparison

# ===== set these two lines per model, then run the rest unchanged =====
#   bge : MODEL=BAAI/bge-base-en-v1.5   TAG=bge   (baseline)
#   e5  : MODEL=intfloat/e5-base-v2     TAG=e5
#   gte : MODEL=thenlp/gte-base         TAG=gte
MODEL=intfloat/e5-base-v2 ; TAG=e5

# --- Step 1: rebuild the corpus index with THIS model. -----------------------
# WHY: the index and the server must use the SAME model. If the index is built
# with BGE but the server queries with e5, you're comparing e5 vectors against
# BGE vectors — garbage scores. This step re-embeds all 1,403 docs with $MODEL
# into a scratch index (gitignored; never touches production .chroma_kavach).
# First use of a new model downloads it (~3-5 min); the embed itself is <1 min on
# the 5060. Confirm the tail says "indexed 1403 documents" and CHANNEL = 303.
python corpus_loader.py \
  --embed-model "$MODEL" \
  --corpus kavach_corpus_v1.json \
  --chroma parliament/.chroma_embedding_test_${TAG} \
  --rebuild --skip-smoke

# --- Step 2: start the server against THIS model + its index. ----------------
# WHY: this is what actually changes Kavach's behavior. The server embeds every
# incoming action with $MODEL and compares it against the $MODEL-built index. The
# two env vars override config.yaml with no file edit — nothing is committed, and
# unsetting them (or restarting plain) restores production. Leave this running in
# its own terminal.
KAVACH_EMBED_MODEL="$MODEL" \
KAVACH_CHROMA_PATH="parliament/.chroma_embedding_test_${TAG}" \
  python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088

# --- Step 3: verify the server actually loaded THIS model. -------------------
# WHY: catches a silent fallback (wrong model / wrong index) BEFORE you burn
# 30 min on a run whose numbers are secretly BGE's. In a SECOND terminal:
curl -s http://127.0.0.1:8088/health | python -m json.tool
#   -> "model" MUST equal $MODEL, and doc_counts CHANNEL MUST be 303.
#      If not, stop and fix step 1/2 before running anything.

# --- Step 4: InjecAgent (full). ---------------------------------------------
# WHY: the primary metric — does this embedding model catch more or fewer attacks
# (recall) at what false-positive cost (FPR)? Pure replay: no agent backbone, the
# runner just POSTs the 1,054 cases to the server.
python injecagent_runner.py --full \
  --parliament-url http://127.0.0.1:8088 \
  --output kavach_eval/results/embedding_comparison/${TAG}/ \
  --include-benign

# --- Step 5: AgentDojo 25-pair subset (qwen2.5:7b backbone). -----------------
# WHY: secondary check — does the embedding model affect REAL agent interception
# (a live agent generating tool calls that Kavach screens), not just static
# replay? --max-pairs 25 => exactly 5 user x 5 injection = 25 pairs; the agent is
# qwen2.5:7b for all three models, so only Kavach's scoring differs. This is a
# SUBSET signal, not the headline AgentDojo number (that's Ishani's full run).
export OPENAI_API_KEY=ollama
export OPENAI_API_BASE=http://localhost:11434/v1
python benchmarks/run_agentdojo_kavach.py \
  --suite slack --model-id qwen2.5:7b \
  --kavach-url http://127.0.0.1:8088 \
  --max-pairs 25 \
  --out kavach_eval/results/embedding_comparison/agentdojo_subset_${TAG}/

# --- Step 6: stop the server (Ctrl-C), record the numbers (table below), and
#             repeat from Step 1 for the next model.
```

### What to record (per model)

Fill one row per model. BGE's InjecAgent columns are pre-filled from the paper's
committed Dell run — use them to sanity-check your BGE re-run (they should match
closely; if BGE is wildly off, the harness is misconfigured — stop before trusting
e5/gte). AgentDojo columns are blank for all three; this is the first time we run
that subset.

| Model | InjecAgent strict recall (DH) | InjecAgent strict recall (DS) | InjecAgent FPR (DH) | InjecAgent FPR (DS) | AgentDojo ASR (25-pair) | AgentDojo utility (25-pair) |
|---|---|---|---|---|---|---|
| **BGE** (baseline) | 0.633 | 0.438 | 23.5% | 0.0% | — | — |
| **e5-base-v2** | | | | | | |
| **gte-base** | | | | | | |

- InjecAgent numbers: from each run's
  `kavach_eval/results/embedding_comparison/<tag>/summary.json` — `strict.recall`
  and `strict.fpr` for both the direct-harm (DH) and data-stealing (DS) settings.
- AgentDojo numbers: from the end-of-run summary in
  `kavach_eval/results/embedding_comparison/agentdojo_subset_<tag>/` — the ASR
  (with Kavach) and utility-under-attack. Confirm the run log printed
  `5 user tasks × 5 injection tasks = 25 pairs`.
- Query and document prefixes are set **automatically per model** — no manual
  configuration. Each model uses its own convention on both the index and the
  query side (BGE: instruction prefix on queries; e5: `query: `/`passage: `; gte:
  none). The rebuild log prints the prefixes it used, so you can confirm at a
  glance. So a fair comparison is the default — you don't have to do anything to
  get it.

### Committing results

Results go to the `parv-results` branch (NOT `main`). Whoever finishes first —
you or Ishani — creates the branch; the other just checks it out.

```bash
git fetch origin
git checkout parv-results 2>/dev/null || git checkout -b parv-results
git add kavach_eval/results/embedding_comparison/
git commit -m "data: embedding-model comparison (bge / e5 / gte) — InjecAgent full + AgentDojo 25-pair subset"
git push origin parv-results
```

Then send Ishani the filled-in table.

### Timing

Per model, on the RTX 5060:
- **Corpus rebuild (Step 1):** <1 min compute on GPU. **First** build of e5 and gte
  adds a one-time HuggingFace download (~3-5 min each); BGE is likely already
  cached. So budget ~1 min for BGE, ~4-6 min each for the first e5/gte build.
- **InjecAgent full (Step 4):** ~10-20 min (1,054 cases, GPU embedding, no agent
  LLM in the loop).
- **AgentDojo 25-pair subset (Step 5):** ~10-20 min (25 pairs, each driving
  qwen2.5:7b to generate tool calls — the agent LLM is the slow part, not Kavach).

Rough total: **~30-45 min per model × 3 ≈ 1.5-2.5 hours**, dominated by the
benchmark runs, not the rebuilds. It's parallel to Ishani's Dell session, so it
doesn't compete for her time.

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

### Statistical rigor (post-Dell, laptop — no Dell hardware needed)

Once the real numbers exist, compute **bootstrap 95% confidence intervals
(10,000 resamples)** on every headline rate, so reviewers don't read a point
estimate like "5/10 blocked" or "ASR 0.63" as noise. This is a `scipy.stats`
script run against the per-case result JSONs already on disk — no benchmark
re-run, no GPU.

Rates that need a CI:
- **InjecAgent** recall + FPR, direct-harm and data-stealing
  (`benchmarks/results_v2/injecagent_dell_dh|ds/summary.json` — resample the
  per-case tp/fp/fn/tn rows).
- **AgentDojo** ASR *defended vs. undefended* and benign over-block
  (`agentdojo_dell/agentdojo_summary.json` + per-pair logs) — a CI on the
  **delta** (`asr_reduction`) matters most, since the delta is the paper claim.
- **Red-team** evasion rate (evasion count / N seeds from the evasion report).

Report each as `point [lo, hi]` and add the intervals to the results tables /
prose (this directly answers the reviewer's "no confidence intervals / small-N"
gap). Bootstrapping the *paired* AgentDojo delta (resample pairs, recompute
baseline−defended each draw) is the honest way to show the reduction is real
rather than sampling noise.
