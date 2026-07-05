# Lab Day — July 2–3, 2026

The single file to follow on lab day. Two independent tracks: **Ishani** runs the
primary benchmarks on the Dell; **Parv** runs the embedding comparison on his
laptop. The tracks do not block each other — start both, sync at end of day.

Everything is on `main`. There is no `parv` branch anymore — ignore any older doc
that says `git checkout parv`.

---

## ⭐ START HERE (morning summary — full detail below)

**Before anything:** `ollama list` must show your model — **Dell:** `gemma4:26b`, **Parv:** `qwen2.5:7b`. Pull if missing.

**ISHANI — Dell, in order (health-check after each ★):**
1. **Boot:** `bash kavach_boot.sh --skip-patch` → `python corpus_loader.py --rebuild` → `curl -s http://127.0.0.1:8088/health | python -m json.tool` → **★ MUST show CHANNEL: 303.** If not 303, STOP — rebuild didn't take.
2. **Launch dashboard:** `python tools/dell_lab.py` (status bar must show parliament green + `C303` + gemma4:26b).
3. **AgentDojo** (PRIMARY, ~45–90 min) — runs baseline-first + WITH-Kavach in one command. **★ end-of-run KAVACH AUDIT must say `run_fully_defended: true` + non-zero baseline ASR. Fail-open = HARD STOP, numbers are fake.** The delta (baseline→defended ASR) is the headline.
4. **InjecAgent** (SECONDARY) — sanity: DH loose ~0.90 / strict ~0.63; DS loose ~0.875 / strict ~0.44. Off? note & move on, don't re-run.
5. **Red-team** (time permitting) — note the `evasion_report_*.json` filename; the loop needs it.
6. **Improvement Loop** (LAST, needs step 5) — approve each pattern carefully (appends to corpus).
7. **LOLBIN experiment** (HIGH-VALUE, only after 3+4 done) — capture baseline FIRST, then corpus_agent → staging → validate 3 gates → v2 rebuild → **FPR side-effect check** → report delta.
8. **Optional Dell checks (cheap, back two paper claims):** with the server up, fire `curl http://127.0.0.1:8088/ledger/verify` (tamper-evidence), and kill+call to confirm fail-closed `deny`. Screenshot both.
9. **Commit** to `parv-results` (NOT main).

**PARV — laptop, in order:**
1. Setup: `git pull`, `ollama pull qwen2.5:7b`.
2. **Embedding comparison** (BGE / e5 / gte) — rebuild index per model → restart server with `KAVACH_EMBED_MODEL` + `KAVACH_CHROMA_PATH` → InjecAgent + AgentDojo 25-pair subset → **★ /health `model` must match + CHANNEL 303.**
3. **Threshold recalibration** (510-case CHANNEL sweep) — post-Dell checklist item.
4. **Commit** to `parv-results`.

**INVARIANT (both, before AND after):** `md5sum kavach_corpus_v1_ORIGINAL.json` = `7ce71ec38c9bdd2f273a34205c13fc5e` — must be unchanged.

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

5. **LOLBIN corpus-improvement experiment** (HIGH-VALUE, but only if time
   permits **after AgentDojo + InjecAgent complete** — it must not compete with
   the headline benchmark). This demonstrates the corpus_agent (Kavach's
   *proposed* structural fix) actually closing the R2 LOLBIN blind spot,
   turning the Ablation-2 limitation into "limitation **+ working fix**."

   **Safety guardrails — non-negotiable, verify each before proceeding:**
   - `kavach_corpus_v1_ORIGINAL.json` is **NEVER touched.** Its MD5 must be
     `7ce71ec38c9bdd2f273a34205c13fc5e` before AND after. Check both ends:
     `md5sum kavach_corpus_v1_ORIGINAL.json`.
   - The corpus_agent **only writes to `kavach_eval/corpus_agent/staging/`**
     (`proposed_patterns_<ts>.json`) — it never writes the live corpus or
     anything under `parliament/`. A human accepts from staging into a **new**
     corpus version, never overwriting the original.
   - Every proposed pattern must pass all **three anti-poisoning gates**
     (A: FP gate — no benign false-positive inflation; B: detection — it
     actually improves detection; C: dedup — reject ≥0.92 near-duplicates).
   - The **"before" evasion measurement is captured and committed FIRST**, or
     the delta is meaningless.

   **Ordered steps:**
   1. **Baseline (before).** Run `python kavach_eval/ablation_retrieval_modes.py`
      on the Dell against the current corpus; record how many of the 13 R2
      LOLBINs evade the hybrid pipeline (laptop showed 10/13 — confirm on Dell).
      **Commit this baseline FIRST**, tagged `pre-corpus-improvement`.
   2. **Propose.** Feed the R2 evasions to the corpus_agent
      (`python -m kavach_eval.corpus_agent.agent ...`) to propose **full**
      patterns (real command signatures + MITRE technique IDs + rationale — NOT
      just appended keyword tokens) for certutil, bitsadmin, mshta, regsvr32,
      etc. **Show the proposed patterns (staging file) before accepting any.**
   3. **Validate (no poisoning).** Confirm each proposal's 3-gate result in the
      `staging_report_<ts>.txt`; report the gate breakdown (accepted/rejected +
      reason). Reject anything that fails A/B/C.
   4. **Rebuild + re-measure (after).** Accept the validated patterns into a
      **new** corpus (`kavach_corpus_v2.json`, do not overwrite v1/original),
      rebuild ChromaDB against it, and re-run `ablation_retrieval_modes.py` on
      the same 13 LOLBINs. Record how many now evade.
   5. **FPR side-effect check (the honesty gate).** Re-run the benign probe
      (the 17 `user_cases.jsonl` instructions, and the 10-action benign set)
      with the v2 corpus and confirm the added LOLBIN patterns did **not** raise
      the benign FPR. If they did, that is a real finding — report it.
   6. **Report the delta:** *"corpus_agent reduced LOLBIN evasion from X/13 to
      Y/13 while benign FPR changed from A% to B%."* That sentence — with the
      honest FPR side-effect number — is the result.

   **Where it goes:** §4.5 gains a "mitigation validated" paragraph — the paper
   identifies the blind spot, proposes the corpus_agent, and demonstrates it
   working, with honest numbers including any FPR side-effect. If it closes the
   blind spot without wrecking FPR, that is a strong result; if it fixes LOLBINs
   but raises FPR, that is also a real, reportable finding.

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

---

## Post-Dell paper checklist (July 5th evening → submit by July 24)

The definitive, ordered to-do from the Dell run to submission. Work top to
bottom — each stage depends on the one above. Root LaTeX file is
`paper/skeleton_aisec.tex` (compiled in WSL); `\TBD` renders as red `[TBD]`
(defined at `skeleton_aisec.tex:31`), so a stray one is visible in the PDF.

### Stage 1 — Fill placeholders from the Dell numbers

Regenerate the auto tables first (this fills the frontier/ablation/correlation
tables under `paper/tables/` and leaves the *prose* `\TBD`s for hand-editing):
```bash
python kavach_eval/make_section5.py minister_runs.jsonl --rho-auto
```

Then resolve every remaining live `\TBD` by hand. Current inventory (9 render
tokens; verify with `grep -rn "\\TBD" paper/section_*.tex`):

- [ ] **§4.4 `section_4_deployment.tex:121`** — `Table~\TBD` → `\ref{tab:frontier}` (gate-floor recall/FPR sweep table).
- [ ] **§4.5 `section_4_deployment.tex:126`** — `Table~\TBD` → `\ref{tab:injecagent}` (InjecAgent strict/loose recall + FPR).
- [ ] **§4.6 `section_4_deployment.tex:193`** — threshold-matched cross-model comparison `\TBD` + `Table~\TBD` → the side-by-side config table (needs the Dell InjecAgent re-run to compare against the laptop-secondary numbers).
- [ ] **§5 `section_5_frontier.tex:31`** — pure-veto clean FPR `\TBD\%` → measured benign FPR.
- [ ] **§5 `section_5_frontier.tex:33`** — Bayesian clean FPR `\TBD\%` and `K{=}\TBD` (corruption count where it breaks).
- [ ] **§5 `section_5_frontier.tex:34`** — Bayesian ASR-under-corruption `\TBD\%`.
- [ ] **§5 `section_5_frontier.tex:37`** — hybrid clean FPR `\TBD\%` (note: this line's "<5% gate" wording is corrected on branch `fix/section5-gate-consistency` — confirm that PR merged before editing, or you'll re-introduce the contradiction).
- [ ] **§5 `section_5_frontier.tex:38`** — hybrid robustness gap `\TBD` points and `K{=}\TBD`, plus `Table~\TBD` → `\ref{tab:frontier}`.
- [ ] **§5 `section_5_frontier.tex:59`** — ablation `Table~\TBD` → `\ref{tab:ablation}`.
- [ ] `\MeasuredRho` (`tables/section5_macros.tex`) is already `0.091`; `--rho-auto` overwrites it from the real dump — confirm it updated.

**AgentDojo delta** (the headline — from `benchmarks/results_v2/agentdojo_dell/agentdojo_summary.json`):
- [ ] `dell_number_macros.tex` **does not exist yet** — create it (or add macros to `skeleton_aisec.tex` preamble): `\newcommand{\AgentDojoBaseline}{..}`, `\AgentDojoASR`, `\AgentDojoReduction`, `\AgentDojoUtility`.
- [ ] Fill from the JSON: `.baseline.attack_success_rate` (baseline ASR), `.with_kavach.attack_success_rate` (defended ASR), `.asr_reduction` (delta), utility-under-attack, `.benign_utility.benign_overblock` (FP cost).
- [ ] Add the AgentDojo result + delta sentence to §4.2 (live interception) and a row to the results table. **State it as a delta:** "ASR from [baseline]% to [defended]% at [utility]% utility."
- [ ] **This delta is the head-to-head axis vs ClawGuard's published AgentDojo numbers** (0% ASR from a 0.6–3.1% baseline, arXiv:2604.11790) — same benchmark, **cite-only** comparison (we do not reproduce ClawGuard; see Stage 7). Note the scope difference in the writeup: ClawGuard also tests SkillInject/MCPSafeBench (attack surfaces Kavach does not cover), while Kavach adds InjecAgent + the semantic-corpus approach ClawGuard's rule-based method lacks.

### Stage 2 — Insert deferred §4.5 (R2 promotion)

- [ ] Insert the body of `paper/section_4_5_lolbin_DRAFT.tex` into `section_4_deployment.tex` after §4.4 (`\label{sec:hybridresults}`), per that file's header. Move its table into `paper/tables/tab_r2b.tex` and `\inputtable` it (or keep inline). Numbers are model-independent (embedding-only) — no need to re-run on Dell.
- [ ] This adds ~1 column. Make **one offsetting trim** to hold body ≤10pp — candidate: §4.6 cross-model paragraph (compresses once the real Dell AgentDojo number supersedes the laptop-secondary hedging), or tighten the related-work prose. Recompile and confirm the References still begin by p11.

### Stage 3 — Statistical rigor (laptop, no Dell)

- [ ] Bootstrap 95% CIs (10k resamples) on: InjecAgent recall + FPR (DH & DS), the **paired** AgentDojo ASR delta (baseline − defended), and the red-team evasion rate. Add `point [lo, hi]` to the results tables/prose. (Full spec is in the "Statistical rigor (post-Dell, laptop)" subsection above, once `feat/agentdojo-baseline-first` merges.)

### Stage 4 — Threshold recalibration result (from Parv's 510-case run)

- [ ] Replace the 10-action CHANNEL-overlap finding in §4.3/§4.4 with the statistically-weighted **510-case** sweep (Parv's `benign_gate_usercases.py` across θ_CHANNEL 0.45/0.50/0.55/0.60). Keep the honest framing: if it still shows no separating knee, that *strengthens* the "corpus recalibration, not threshold tuning" conclusion. Update the §7 next-step sentence to cite the 510-case result.

### Stage 4b — Ablation studies (extend the existing four-minister ablation)

- [ ] **Ablation 2 (retrieval modes) — laptop portion DONE**, InjecAgent leg
      pending Dell. The dense/BM25/hybrid comparison ran on the R2 LOLBIN set +
      17 benign instructions (`kavach_eval/ablation_retrieval_modes.py`,
      results in `kavach_eval/ablation_results/retrieval_modes_laptop.txt`):
      dense-only catches 10/13 LOLBINs but 70.6% benign B/E-FPR; hybrid 0%
      hard-block FPR but 10/13 LOLBINs evade; a **trade-off**, not
      "hybrid dominates." On the Dell, extend it with the full InjecAgent
      3-mode recall row (the case text lives at `/tmp/InjecAgent/data/` on the
      Dell, not in the repo — re-run `ablation_retrieval_modes.py` there with
      the InjecAgent set wired in). Folds into §4.5 next to the R2b table;
      frame as "same lexical-gate mechanism, opposite sides" so it does not
      appear to contradict "hybrid recovers recall" (that is InjecAgent
      register-matched attacks; LOLBINs are lexically novel).
- [ ] **§4.5 "mitigation validated" paragraph** — IF the Dell LOLBIN
      corpus-improvement experiment ran (Dell run-order step 5): add the
      before/after delta ("corpus_agent reduced LOLBIN evasion from X/13 to
      Y/13 while benign FPR changed from A% to B%") to §4.5, turning the R2
      blind spot into "limitation + demonstrated fix." Report the FPR
      side-effect honestly whichever way it goes. If the experiment did not run,
      leave §4.5 as identified-blind-spot + corpus_agent-as-proposed-fix.
- [ ] **Ablation 1 (COMPASS + trajectory on/off) — DEFERRED, needs a Dell
      re-run.** The current `minister_runs.jsonl` dump records per-minister
      votes but **no** `compass_drift` or `trajectory`/`session_risk` fields
      (verified: 0 of 2108 records), so it cannot be replayed with those
      signals toggled. To run it: re-dump the minister runs WITH `compass_drift`
      and `trajectory_risk` logged per call, and — because trajectory is
      session-level — as sequential sessions, not per-case replay. Only do this
      if AgentDojo + InjecAgent are already done; do NOT let it compete with the
      primary AgentDojo run for Dell time. Likely a weak result on single-turn
      benchmarks — acceptable to defer to the 2027 follow-on.
- [ ] **Ablation 3 (semantic generalization) — decision pending.** Not pure
      re-analysis: the red-team output persists only the evasions + ambiguous
      cases, not the caught paraphrases, and ~142/268 attempts drifted
      off-intent. Needs per-attempt logging + an intent-preservation filter, then
      a re-run (laptop). Build only if the validity design is clean; otherwise
      2027 follow-on. See the session notes.

### Stage 5 — Embedding comparison (only if it ran cleanly)

- [ ] If Parv's BGE-vs-e5-vs-gte run completed: add the comparison table to §3.2 and change the §3.2 / §7 "we did not perform an embedding ablation" framing to "we compared three encoders holding corpus and thresholds fixed." **If it did not finish cleanly, leave the future-work framing untouched** — do not half-report it.

### Stage 6 — Competitor framing (paper-writing only — do NOT run anything)

Neither competitor is reproduced; both are **cite-only**. Do not attempt a
head-to-head run on lab day — it is dead: PRISM (arXiv:2603.11853) reports no
validated empirical results (methodology-only, no reproducible numbers), and
ClawGuard (arXiv:2604.11790) uses SkillInject/MCPSafeBench and requires OpenClaw
live sessions, not our InjecAgent replay harness.

- [ ] **Tighten the PRISM latency caveat in the paper:** PRISM reports no
      validated results, so reframe the ~15.8\,s p95 figure (§4 results/cost)
      as "from PRISM's proposed methodology, not a validated measurement."
- [ ] **Add the ClawGuard AgentDojo comparison to the related-work discussion**
      once real Kavach AgentDojo numbers exist (Stage 1): same-benchmark,
      cite-only, with the SkillInject/MCPSafeBench scope-difference note above.

### Stage 7 — Final checks and submit

- [ ] Recompile in WSL: `pdflatex → bibtex → pdflatex → pdflatex` on `skeleton_aisec.tex`.
- [ ] Confirm **body ≤10pp** (References begin p11) and **0 undefined refs** (`grep -i undefined skeleton_aisec.log`).
- [ ] **No stray `\TBD`:** `grep -rn "\\TBD" paper/section_*.tex` returns only comment lines.
- [ ] Final consistency grep — none of these survive as a live claim:
      `grep -rniE "gate|production hardware|real time|19\\%|fifty benign" paper/section_*.tex`
      (legitimate: gateway path, lexical gate, router gating, the real laptop 17-instruction benign gate; everything else must be gone).
- [ ] Regenerate `FULL_PAPER_DRAFT.tex` (pre-commit hook does this automatically) and the PDF.
- [ ] Commit to a branch → PR → merge to `main` (main is branch-protected; direct push is rejected).
- [ ] **Submit via the AISec 2026 portal (aisec.cc) before July 24.**
