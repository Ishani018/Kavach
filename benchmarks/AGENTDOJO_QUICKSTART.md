# AgentDojo — Quickstart (read this before running)

This is the idiot-proof path so you never waste a multi-hour run on the wrong
setup again. **Always run STEP 1 first** — it takes seconds and tells you exactly
what's wrong if anything is.

---

## Why the 2026-06-18 run was wasted

`gemma2:9b` **cannot do function-calling**. It acknowledges its role ("I will
assist Emma...") but never actually calls a tool, so ~every task fails before any
injection is tested. The numbers were noise. The new pre-flight probe (STEP 1)
now **hard-stops** on a model like that, with instructions, before any compute is
spent. See `results_v2/agentdojo_gemma_laptop/FINDINGS_AND_PLAN.md` for the full
post-mortem.

---

## STEP 0 — start the two services

```bash
# 1. Ollama (in its own terminal)
ollama serve

# 2. Kavach parliament (in its own terminal, from repo root)
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
```

## STEP 1 — sanity check (ALWAYS do this first — seconds, not hours)

```bash
python benchmarks/run_agentdojo_kavach.py --sanity --model-id llama3.1:8b
```

This checks: Ollama up · model present · Kavach up · **and whether the model will
actually initiate tool calls.** It prints ✅/❌ for each with the exact fix
command. **If any line is ❌, fix it and re-run STEP 1. Do not proceed.**

If the tool-call probe fails (❌ model did NOT initiate a tool call), the model is
too weak — pull a function-calling model:

```bash
ollama pull llama3.1:8b      # good local function-caller, ~5 GB
```

## STEP 2 — the real run (only after STEP 1 is all ✅)

```bash
export LOCAL_LLM_PORT=11434
export KAVACH_URL=http://127.0.0.1:8088

python benchmarks/run_agentdojo_kavach.py \
  --suite workspace --model-id llama3.1:8b \
  --attack important_instructions \
  --out benchmarks/results_v2/agentdojo_llama_laptop \
  2>&1 | tee benchmarks/results_v2/agentdojo_llama_laptop/workspace.log
```

While it runs, a live monitor prints a running tally. If utility stays 0%, it
prints an **early-abort** message telling you to Ctrl+C — stop and switch models
rather than waiting hours.

---

## Which model?

| Model | Function-calling | Use for |
|---|---|---|
| **gemma2:9b** | ❌ NO | **do not use** — this is what failed |
| **llama3.1:8b** | ✅ yes | laptop validation (proves the harness + Kavach work) |
| **qwen2.5:7b** | ✅ yes | alternative laptop validation |
| **gemma4:26b** (Dell) | ✅ yes | **the paper's primary number** — run on the Dell |

> ⚠️ A laptop run with llama3.1:8b / qwen2.5:7b is a **plumbing check** (does it
> work end-to-end?), **not a paper number.** The AgentDojo result we report must
> come from **gemma4:26b on the Dell**, the primary config.

## Flags you might need

| Flag | What |
|---|---|
| `--sanity` | run pre-flight only, then exit (STEP 1) |
| `--model-id NAME` | which Ollama model |
| `--no-preflight` | skip all pre-flight checks (not recommended) |
| `--skip-toolcall-probe` | skip only the tool-initiation probe (NOT recommended — it's the check that saves you) |
| `--abort-threshold N` | warn to abort if utility is 0% after N pairs (default 30; 0=off) |

## Targets (for a real run on a capable model)
ASR < 5% (vs ~17.6% baseline) · benign utility > 40%. Check the **FAIL-OPEN
AUDIT** banner and `run_fully_defended: true` in the summary before trusting any
number.
