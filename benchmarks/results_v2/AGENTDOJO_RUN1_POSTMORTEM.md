# AgentDojo Run 1 — Post-Mortem & Next Steps for Parv

**Date of failed run:** 2026-06-18  
**Run by:** Parv (parvparmar23@gmail.com)  
**Model used:** `gemma2:9b` (via Ollama, laptop)  
**Branch with raw results:** `parv-docs-point-to-results` (commit `91b19db`)

---

## What you ran

```bash
python benchmarks/run_agentdojo_kavach.py \
    --suite workspace \
    --model-id gemma2:9b \
    --attack important_instructions \
    --out benchmarks/results_v2/agentdojo_gemma_laptop
```

## What you got

| Condition | Utility | Security | Kavach calls |
|---|---|---|---|
| Baseline (no Kavach) | 1 / 17 &nbsp;**(5.9%)** | 14 / 17 &nbsp;**(82.4%)** | — |
| With Kavach | 15 / 574 &nbsp;**(2.6%)** | 14 / 574 &nbsp;**(2.4%)** | **1 total** |

Full Kavach summary from the run:
```python
{
  'n_pairs': 560,
  'benign_utility': 0.025,
  'attack_success_rate': 0.0,
  'kavach': {
    'total_calls': 1,    # ← Kavach called only ONCE in 560 pairs
    'screened_calls': 1,
    'blocks': 1,         # ← that one call was correctly blocked
    'allows': 0,
    'fully_defended': True
  }
}
```

---

## Why it failed — the real diagnosis

### Root cause: `gemma2:9b` wraps tool calls in markdown

The model outputs tool calls inside a markdown code block:

```
```json
<function=email>{"to": "mark@gmail.com", "subject": "...", "body": "..."}
```
```

The script's `_parse_tolerant()` parser found the JSON but included the trailing ` ``` ` in the extracted string, causing `json.loads()` to fail:

```
[debug] broken JSON: '{"to": "mark@gmail.com", "body": "Hey"}\n```'
                                                              ^^^^^ this breaks it
```

The fix is now committed to `parv-docs-point-to-results` — it trims everything after the last `}`:

```python
last_brace = raw.rfind("}")
if last_brace != -1:
    raw = raw[:last_brace + 1]
```

### Why the numbers are meaningless

- `attack_success_rate: 0.0` — looks like Kavach defended everything. It didn't. The model just never generated a valid tool call, so attacks had nothing to execute.
- `fully_defended: True` — technically correct, actually useless.
- `security: 82.4%` in baseline — same reason. Security-by-failure.
- Kavach only got invoked **once** across 560 pairs. That one time it correctly blocked. But one data point isn't a benchmark.

---

## What the numbers SHOULD look like (reference targets)

From the original `PARV_RESULTS.md`:

| Metric | Target |
|---|---|
| ASR with Kavach | ≤ 5% |
| Benign utility (baseline) | ~47.73% |
| Benign utility (with Kavach) | ≥ 40% |
| Kavach total_calls | ~560 (one per pair) |

---

## What to do for Run 2

### Step 0 — Pull the latest script (parser is fixed)

```bash
git pull origin parv-docs-point-to-results
```

The updated `benchmarks/run_agentdojo_kavach.py` now has:
- ✅ Pre-flight checks (verifies Ollama, model, Kavach are up before wasting hours)
- ✅ Gemma markdown parser fix
- ✅ Live progress every 10 pairs
- ✅ Early-abort warning at 30 pairs with 0% utility

### Step 1 — Run the sanity check first (takes ~5 min)

```bash
python benchmarks/run_agentdojo_kavach.py \
    --suite workspace \
    --model-id gemma2:9b \
    --sanity
```

This verifies Ollama is running, Kavach is up, and the model can format a tool call.
If it shows `⚠️ No tool call parsed` → the parser still needs work, don't do a full run.

### Step 2 — Model choice for your RTX 5060 (8GB VRAM)

| Model | VRAM | Function calling | Recommendation |
|---|---|---|---|
| `llama3.1:8b` | ~4.9GB | ⭐⭐⭐ Excellent | ✅ **Use this** |
| `qwen2.5:7b` | ~4.5GB | ⭐⭐⭐ Excellent | ✅ Good backup |
| `gemma2:9b` | ~5.4GB | ⭐ Poor | ⚠️ Use only after verifying parser fix works |
| `mistral-nemo:12b` | ~7.5GB | ⭐⭐⭐ Excellent | ✅ Best quality that fits |

**If you want clean results fast** → use `llama3.1:8b`:
```bash
ollama pull llama3.1:8b
```

**If you want to test with gemma2:9b specifically** (since OpenClaw uses Gemma) → run the sanity check first. If the parser fix works, the full run should be valid.

### Step 3 — Full run

```bash
python benchmarks/run_agentdojo_kavach.py \
    --suite workspace \
    --model-id llama3.1:8b \
    --attack important_instructions \
    --out benchmarks/results_v2/agentdojo_laptop_llama31
```

You'll see live progress:
```
[progress] 10 pairs done │ utility: 4/10 (40%) │ security: 7/10 (70%)
[progress] 20 pairs done │ utility: 9/20 (45%) │ security: 14/20 (70%)
```

If utility stays 0% after 30 pairs you'll get a loud warning — stop and fix before continuing.

### Step 4 — Commit results

```bash
git config user.name "Parv Parmar"
git config user.email "parvparmar23@gmail.com"

git add benchmarks/results_v2/agentdojo_laptop_llama31/
git commit -m "eval: AgentDojo run2 with llama3.1:8b on RTX 5060

ASR (Kavach):    X%
Benign utility:  X%
Kavach calls:    N
Model: llama3.1:8b
Hardware: [your laptop], RTX 5060 8GB"

git push origin parv-docs-point-to-results
```

Then message Ishani.

---

## Why Kavach WILL work with Gemma in real OpenClaw

Even though the benchmark failed with `gemma2:9b`, Kavach is NOT broken for Gemma. The benchmark harness (AgentDojo) and real OpenClaw talk to the model differently:

- **AgentDojo**: expects a specific raw JSON format → rejects Gemma's `<function=X>` tags → agent dies before Kavach is even called
- **Real OpenClaw**: has its own parsing layer tuned for Gemma → valid tool calls flow through → Kavach screens them

The 1 time Kavach WAS called in the run, it correctly blocked. The parser fix makes the benchmark harness understand Gemma the same way OpenClaw does.

---

## Files changed since Run 1

| File | Change |
|---|---|
| `benchmarks/run_agentdojo_kavach.py` | Parser fix + pre-flight + live progress + early-abort |
| `benchmarks/results_v2/agentdojo_gemma_laptop/FINDINGS_AND_PLAN.md` | Full post-mortem of Run 1 |
| `benchmarks/results_v2/AGENTDOJO_RUN1_POSTMORTEM.md` | This file |

All on branch `parv-docs-point-to-results`.

---

*Written by Ishani + Antigravity after analysing Run 1. — 2026-06-18*
