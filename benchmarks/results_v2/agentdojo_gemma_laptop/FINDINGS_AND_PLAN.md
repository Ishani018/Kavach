# AgentDojo Run — gemma2:9b — Findings & Next Steps

**Branch:** `parv-docs-point-to-results`  
**Run by:** Parv (parvparmar23@gmail.com)  
**Date:** 2026-06-18  
**Model:** `gemma2:9b` (via Ollama, local laptop)  
**Commit:** `91b19db`

---

## Results Summary

| Condition | Utility | Utility % | Security | Security % |
|---|---|---|---|---|
| **Baseline** (no Kavach, `local`) | 1 / 17 | **5.9%** | 14 / 17 | **82.4%** |
| **With Kavach** (`local-kavach`) | 15 / 574 | **2.6%** | 14 / 574 | **2.4%** |

> ⚠️ **These results are not meaningful.** See "What Went Wrong" below.

---

## What the Numbers Mean (AgentDojo scoring)

- **Utility = did the agent complete the legitimate user task?**  
  Higher is better. Low utility = the model can't do basic tasks.

- **Security = did the agent resist the injected attack?**  
  Higher is better. Low security = the model executed the malicious instruction.

In a healthy run we'd expect:
- Baseline: moderate utility (~40–70%), moderate security (~30–60%)
- With Kavach: similar or slightly lower utility, meaningfully higher security

---

## What Went Wrong

### 1. Wrong model for function-calling

`gemma2:9b` was not trained for structured function-calling. It generates tool calls in this format:

```
<function=email>{"to": "mark@gmail.com", "subject": "Hi", "body": "Hey"}
```

AgentDojo expects a structured JSON format. The harness responds with:

```
"Invalid tool email provided."
```

The agent then gives up and outputs:
> "Please let me know what Emma would like to do first!"

This means **almost every task fails immediately at step 1**, before any injection attack even has a chance to be evaluated.

### 2. The `_parse_tolerant()` fix was insufficient

`benchmarks/run_agentdojo_kavach.py` has a `_parse_tolerant()` function that tries to handle malformed tool-call JSON. The commit `91b19db` improved its error logging:

```python
# Before:
except Exception:
    print(f"[debug] broken JSON after tolerant parse: {raw!r}")

# After:
except Exception as e:
    print(f"[debug] broken JSON after tolerant parse: {raw!r}. Error: {e}")
```

But the function still doesn't handle Gemma's `<function=X>{...}` tag format, so it doesn't help.

### 3. Baseline run was incomplete (17 files vs 574 for Kavach)

The `local` (baseline) run only produced **17 result files** — just the standalone injection tasks. The `local-kavach` run produced the full **574-file grid** (all `user_task × injection_task` combinations). This means the two conditions aren't directly comparable, making any diff between them unreliable.

### 4. "Security looks good" in baseline — but it's a false positive

Baseline security of 82.4% sounds promising, but it's an artifact of the model failing. When the agent can't call tools at all, it can't execute the malicious injection either. Security-by-failure is not real security.

### 5. Kavach security collapsed to 2.4%

AgentDojo marks security as **failed** whenever the agent errors out mid-task (the attack "succeeded by default" since the agent couldn't complete the benign task). Since `gemma2:9b` errors on almost every task, 97.6% of runs are counted as security failures — regardless of what Kavach does.

---

## Root Cause Summary

> **`gemma2:9b` is too weak for this benchmark.** It cannot reliably format tool calls, so the benchmark never gets to actually test Kavach's injection-blocking capability. All numbers are noise.

---

## Plan: What To Do Next

### Option A — Switch to a better local model (recommended first step)

Run AgentDojo with a model that has explicit function-calling support:

| Model | Provider | Quality | Notes |
|---|---|---|---|
| `llama3.1:8b` | Ollama | ✅ Good | Best local option, solid function calling |
| `mistral-nemo` | Ollama | ✅ Good | Fast, reliable tool use |
| `qwen2.5:7b` | Ollama | ✅ Good | Strong function calling for its size |

```bash
ollama pull llama3.1:8b
python benchmarks/run_agentdojo_kavach.py --model llama3.1:8b
```

### Option B — Fix the parser for Gemma's format

If we need to keep using `gemma2:9b` (e.g. it's the only model that fits in VRAM), patch `_parse_tolerant()` in `run_agentdojo_kavach.py` to also handle Gemma's tag format:

```python
import re

def _extract_gemma_tool_call(text: str):
    """Handle <function=NAME>{...}</function> format from gemma models."""
    match = re.search(r'<function=(\w+)>(.*?)</function>', text, re.DOTALL)
    if match:
        fn_name = match.group(1)
        args_str = match.group(2).strip()
        try:
            args = json.loads(args_str)
            return fn_name, args
        except Exception:
            pass
    return None, None
```

Then call this in `_parse_tolerant()` as a fallback before giving up.

### Option C — Use an API model (for definitive results)

For a clean, publishable benchmark:

```bash
# Gemini Flash (free tier)
python benchmarks/run_agentdojo_kavach.py --model gemini-1.5-flash

# OpenAI (cheapest option)
python benchmarks/run_agentdojo_kavach.py --model gpt-4o-mini
```

These models handle function calling natively and would give us real numbers to compare Kavach against a baseline.

### Option D — Run the baseline completely

Regardless of model, make sure BOTH `local` and `local-kavach` conditions run the **full grid** of user tasks × injection tasks so the comparison is valid.

---

## Immediate Action Items

- [ ] **Parv**: Pull `llama3.1:8b` via Ollama and re-run AgentDojo
- [ ] **Ishani**: Review `_parse_tolerant()` and decide if we want to add Gemma format support
- [ ] **Both**: Ensure baseline `local` run covers the same task grid as `local-kavach` before comparing
- [ ] **Both**: Decide on target model for the "real" benchmark run we report in the paper

---

## Files Changed in This Run

- `benchmarks/results_v2/agentdojo_gemma_laptop/logs/local/` — 17 baseline result JSONs
- `benchmarks/results_v2/agentdojo_gemma_laptop/logs/local-kavach/` — 574 Kavach result JSONs  
- `benchmarks/run_agentdojo_kavach.py` — improved debug logging in `_parse_tolerant()`
- `parliament/config.yaml` — comments stripped (whitespace/formatting only change, no logic change)
- `corpus_v2/merge_corpus.py` — minor tweak

---

*This document written by Antigravity (AI assistant) based on analysis of commit `91b19db` on branch `parv-docs-point-to-results`, 2026-06-18.*
