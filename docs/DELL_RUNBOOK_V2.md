# Dell Benchmark Runbook v2 — gemma4:26b

**Machine:** Dell Precision 3660 · RTX 4090 · Gemma 4 26B via Ollama · OpenClaw 2026.4.15
**Branch:** `parv` (results commit to `parv-results`)

This is the single document to follow at the Dell. Do the sections **in order**.
All paths/flags below are verified against the `parv` branch.

---

## 0. Preflight (mandatory — do this before anything else)

```bash
# 1. Get the latest parv branch with the AgentDojo methodology fixes
git checkout parv && git pull origin parv
git log --oneline -6        # CONFIRM commit 360b5a8 is present (the fixes)

# 2. Start OpenClaw (hooks already fixed upstream on 2026.4.15)
bash kavach_boot.sh --skip-patch

# 3. REBUILD ChromaDB — REQUIRED. CHAN-101 was added after the original setup;
#    the live ChromaDB does not pick up corpus edits automatically. Skipping this
#    means CHAN-101 is invisible and a first /hook/parliament call may 500.
python corpus_loader.py --rebuild

# 4. Verify parliament is healthy AND has CHAN-101
curl http://localhost:8088/health
#    → MUST show doc_counts CHANNEL: 303 (not 300). If 300, the rebuild didn't take
#      — stop and re-run step 3.

# 5. Confirm the model is present
ollama list                 # must list gemma4:26b
```

**If any check fails, stop here and fix it. Do not proceed to a run.**

---

## 1. AgentDojo  (PRIMARY — this is the paper number)

```bash
export LOCAL_LLM_PORT=11434
export KAVACH_URL=http://127.0.0.1:8088
export OPENAI_API_KEY=ollama
export OPENAI_API_BASE=http://localhost:11434/v1

python benchmarks/run_agentdojo_kavach.py \
  --suite slack --model-id gemma4:26b \
  --kavach-url http://127.0.0.1:8088 \
  --out benchmarks/results_v2/agentdojo_slack_gemma_dell \
  --abort-threshold 20
```

- **Suite:** `slack` (the paper's primary suite — 92% ASR undefended, so Kavach has
  clear room to show a reduction).
- **Watch for:** the early-abort warning fires if utility stays 0% after 20 pairs —
  if that happens, **something is wrong; stop and ping Ishani.**
- **`EMPTY ACTION sent to parliament: 'tool:get_channels args:{}'`** — this is
  EXPECTED. `get_channels` is a real no-arg tool; the guard over-warns on it. It is
  NOT bug #1 (which would say `tool:unknown`). Do **not** abort over it.
- **End-of-run KAVACH AUDIT** must show real screening (`N tool calls reached the
  defense, M screened, K BLOCKED`) and `run_fully_defended: true`. If it says
  `Kavach screened 0 tool calls` → the numbers are fake, do not report them.
- **Output:** `benchmarks/results_v2/agentdojo_slack_gemma_dell/`
- **Expected duration:** ~45–90 min on RTX 4090.

> A laptop run was llama3.1:8b (a validation/plumbing check). **This Dell gemma4:26b
> run is the reportable number.**

---

## 2. InjecAgent  (SECONDARY)

```bash
python injecagent_runner.py \
  --full \
  --parliament-url http://127.0.0.1:8088 \
  --output benchmarks/results_v2/injecagent_gemma_dell/ \
  --include-benign
```

- **Canonical runner:** `injecagent_runner.py` at the **repo root** (696 lines) — NOT
  the `benchmarks/injecagent_runner.py` copy.
- **Threshold** is set in `parliament/config.yaml` (per-minister, hybrid BM25+dense).
  **Do not edit it.**
- `--full` synthesizes the 1,054-case benchmark; `--include-benign` runs the paired
  benign instructions so the FPR is computed.
- **Expected (sanity-check against the committed Dell figures):** loose recall ~0.88,
  strict ~0.53, DH hard-block FPR ~19%. If the numbers are *wildly* off, **note it
  and move on — do not re-run.**
- **Output:** `benchmarks/results_v2/injecagent_gemma_dell/`

---

## 3. Red-team LLM run  (TERTIARY — time permitting)

```bash
python kavach_eval/redteam_evasion_v0.py \
  --use-llm --model gemma4:26b \
  --max-seeds 250 \
  --use-threat-intel \
  --out-dir kavach_eval/evasion_results/redteam_gemma_dell_n250
```

- Flags are `--max-seeds` (NOT `--n`) and `--out-dir` (NOT `--out`).
- `--use-threat-intel` enables the RAG-augmented paraphraser (stronger evasions).
- **Checkpointing is on.** If it dies mid-run, relaunch the **same command with
  `--resume`** — it picks up from the newest `checkpoint_*.jsonl` in the out-dir.
- **Output:** `kavach_eval/evasion_results/redteam_gemma_dell_n250/` — **note the
  exact `evasion_report_*.json` filename printed at the end; section 4 needs it.**

---

## 4. corpus_agent LOLBIN fix  (TERTIARY — run AFTER section 3 completes)

> **Dependency:** this consumes the **evasion report produced by section 3.** Run
> section 3 first; do not run this standalone.

```bash
# Replace <report> with the actual evasion_report_*.json filename from section 3.
python kavach_eval/corpus_agent/agent.py \
  --evasion-report kavach_eval/evasion_results/redteam_gemma_dell_n250/<report>.json \
  --minister CHANNEL --model gemma4:26b \
  --measure-closure
```

- The agent has **no `--seeds` flag** — it takes an `--evasion-report` (section 3's
  output) and proposes corpus patterns for the evasions in it.
- This is the real-fix path for the **12 HIGH-risk Windows LOLBINs** characterized in
  R2 (`kavach_eval/R2_FINDINGS.md`). On the Dell, gemma4:26b tests whether proposer
  quality scales (qwen2.5:3b passed only ~1/28 on the laptop).
- The agent **never writes the live corpus** — survivors are staged for human review.
- **Output:** `kavach_eval/corpus_agent/results/` (and `staging/`).

---

## 5. Committing results

> All results go to **`parv-results`**, NOT `main`, NOT `parv`.

```bash
git checkout parv-results
git add benchmarks/results_v2/ kavach_eval/evasion_results/ kavach_eval/corpus_agent/results/
git commit -m "data: Dell gemma4:26b AgentDojo + InjecAgent + red-team results"
git push origin parv-results
# Then message Ishani with the headline numbers.
```

---

## 6. Known gotchas

- **`EMPTY ACTION: 'tool:get_channels args:{}'`** → expected false-positive (a real
  no-arg tool). Only `tool:unknown` would be the real bug. **Do not abort.**
- **Gateway mode does NOT fire the `before_tool_call` hook.** Use **embedded mode
  only:** `openclaw agent --local --agent kavach …`.
- **Parliament 500 on the first call** → the ChromaDB wasn't rebuilt (or a stale
  handle). Stop, re-run `python corpus_loader.py --rebuild`, restart parliament,
  retry. (Symptom in the log: `Nothing found on disk` from the HNSW reader.)
- **corpus_agent (section 4) requires section 3's evasion report** — do not run it
  first; it has nothing to consume otherwise.
- **Label outputs honestly** as `_gemma_dell` (the primary config), not `_laptop`.
