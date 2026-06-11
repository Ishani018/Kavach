# KAVACH — Claude Code Laptop Setup
# Run this file with Claude Code: `claude code CLAUDE.md`
# Covers two modes: offline analysis (no GPU) and live server (small Ollama model)

## Project context
Kavach is a runtime security monitor for LLM agents. You're helping run it on a
laptop (no GPU) as a fallback while waiting for Dell benchmark data from Parv.

The repo is at whatever directory you cloned it into. All commands below assume
you're in the repo root.

## Mode 1 — Offline analysis (NO Ollama, NO GPU required)
This is the primary fallback. If Parv's minister_runs.jsonl has arrived:

```bash
# Install deps (CPU-only torch to keep it fast)
pip install -r requirements.txt --break-system-packages
pip install rank-bm25 --break-system-packages

# Verify the eval suite works
python -m pytest parliament/test_speaker.py -v

# Run the trajectory smoke test
python -m parliament.trajectory

# Run provenance eval
python kavach_eval/eval_provenance.py

# Generate synthetic data to verify the pipeline (not for submission)
python kavach_eval/make_synthetic.py --n 400 --rho 0.3 --out /tmp/synth.jsonl

# Verify section-5 harness end to end
python kavach_eval/make_section5.py /tmp/synth.jsonl --rho-auto --synthetic

# When REAL minister_runs.jsonl arrives from Parv:
python kavach_eval/make_section5.py minister_runs.jsonl --rho-auto
# This writes paper/tables/*.tex — the §5 tables drop straight into the paper.
```

## Mode 2 — Live server on laptop (small Ollama model, CPU)
Only needed if you want to generate your own minister_runs.jsonl without Parv.
Results are less reliable than Dell (weaker model, slower) but valid for the
offline §5 analysis.

### Step 1: Install Ollama and pull a small model
```bash
# Install Ollama (Mac/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the smallest viable tool-calling model (~2GB, runs on 8GB RAM)
ollama pull qwen2.5:3b
# OR if you have 16GB RAM:
ollama pull gemma2:9b

# Verify it runs
ollama run qwen2.5:3b "say hello"
```

### Step 2: Load the corpus into ChromaDB
```bash
# This embeds the attack patterns using BGE-base (CPU, ~5 min first run)
python corpus_loader.py

# Verify corpus loaded
python -c "import chromadb; c=chromadb.PersistentClient('.chroma'); print({col.name: col.count() for col in c.list_collections()})"
```

### Step 3: Start the Kavach parliament server
```bash
# Start on port 8088 (what the plugin expects)
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088 --reload

# In another terminal, verify it's running:
curl http://127.0.0.1:8088/health
# Should return: {"status": "ok", "retrieval_mode": "hybrid", ...}
```

### Step 4: Run the InjecAgent benchmark (laptop version)
```bash
# This runs against the live parliament server on :8088
# Uses the synthetic/local agent rather than Gemma4 27B
# Takes ~30-60 min on CPU

python benchmarks/injecagent_runner.py \
  --kavach-url http://127.0.0.1:8088 \
  --out benchmarks/results_v2/injecagent_laptop.json \
  --model qwen2.5:3b

# Commit the result
git add benchmarks/results_v2/injecagent_laptop.json
git commit -m "data: laptop InjecAgent run (qwen2.5:3b, CPU) — preliminary"
```

### Step 5: Dump minister_runs.jsonl for offline analysis
```bash
# The server logs all verdicts to the SQLite ledger
# Export them in the handoff schema format:
python kavach_eval/minister_calibrate.py \
  --ledger kavach_parliament.db \
  --out minister_runs.jsonl

# Then run the full offline analysis
python kavach_eval/make_section5.py minister_runs.jsonl --rho-auto
```

## Verify the ledger is intact after any run
```bash
curl http://127.0.0.1:8088/ledger/verify
# Should return: {"intact": true, "entries_checked": N, "head_hash": "..."}
# Screenshot this for PARV_RESULTS.md
```

## Key files Parv should produce (on the Dell, preferred path)
- `benchmarks/results_v2/injecagent_results.json` — InjecAgent raw output
- `benchmarks/results_v2/native_results.json` — native benchmark raw output  
- `benchmarks/results_v2/benign_results.json` — benign 50-session gate
- `minister_runs.jsonl` — minister vote dump for §5 analysis
- Screenshot of `GET /ledger/verify` — tamper-evidence artifact

## What to tell Claude Code when you open this project
"I'm working on Kavach, a research security monitor for LLM agents targeting
AISec 2026. The repo is set up. I need help running the offline eval pipeline
and/or setting up the live server with a small Ollama model on my laptop.
Start by running the speaker tests to verify the environment."
