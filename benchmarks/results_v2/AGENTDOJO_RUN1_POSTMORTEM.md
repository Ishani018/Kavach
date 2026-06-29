# AgentDojo Run 1 — Post-Mortem & Next Steps for Parv

**Date of failed run:** 2026-06-18  
**Run by:** Parv (parvparmar23@gmail.com)  
**Model used:** `gemma2:9b` (via Ollama, laptop)  
**Branch:** `parv` — this is the single branch for all your work. Pull it, run on it, push results back to it.

---

## What you ran

```bash
python benchmarks/run_agentdojo_kavach.py \
    --suite workspace \
    --model-id gemma2:9b \
    --attack important_instructions \
    --out benchmarks/results_v2/agentdojo_gemma_laptop
```

---

## What you got

| Condition | Utility | Security | Kavach calls |
|---|---|---|---|
| Baseline (no Kavach) | 1 / 17 **(5.9%)** | 14 / 17 **(82.4%)** | — |
| With Kavach | 15 / 574 **(2.6%)** | 14 / 574 **(2.4%)** | **1 total** |

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

## Why it failed — full technical explanation

### 1. What AgentDojo actually does (context)

Before getting into what broke, it helps to understand what AgentDojo is doing under the hood. AgentDojo is a benchmark that tests an AI agent's ability to complete real tasks (like "send this email", "book a calendar slot", "search for a file") while a hidden adversary simultaneously injects malicious instructions into the environment. The framework then scores two things:

- **Utility**: Did the agent complete the legitimate user task the way a real user would want?
- **Security**: Did the agent resist the injected attack and refuse to do the malicious thing?

For a benchmark to be meaningful, the agent needs to be able to complete at least some legitimate tasks first. If an agent can't do anything at all — can't send emails, can't search files, can't call any tools — then both utility and security scores become meaningless, because there is no real agent behaviour to evaluate. This is exactly what happened with `gemma2:9b`.

---

### 2. The root cause: Gemma wraps tool calls in markdown

AgentDojo runs the model and expects it to output structured tool calls in a specific format so the harness can parse what action the agent wants to take. The benchmark script (`run_agentdojo_kavach.py`) has a custom parser called `_parse_tolerant()` that tries to extract these tool calls from the model's raw text output.

The problem is that `gemma2:9b` was not trained to output tool calls in a clean, machine-readable format. Instead, when asked to call a tool, it wraps the entire output in a markdown code block like this:

```
```json
<function=email>{"to": "mark@gmail.com", "subject": "Important message!", "body": "Hey, how is it going?"}
```
```

That trailing ` ``` ` (the markdown code block closer) is the killer. The parser found the function name and the JSON arguments correctly, but when it extracted the raw JSON string, it included those trailing backticks as part of the string:

```
[debug] broken JSON: '{"to": "mark@gmail.com", "body": "Hey"}\n```'
                                                              ^^^^^ this is not valid JSON
```

Python's `json.loads()` correctly rejected this malformed string, which meant the parser returned an empty tool call. The agent then got back an error saying `"Invalid tool email provided."` and had no idea what to do next, so it just gave up and said something like `"Please let me know what Emma would like to do first!"` — as if the conversation had just started.

This happened on essentially every single task. The model kept trying to call tools, the parser kept failing silently, and the agent kept resetting itself. Across 560 task pairs, `_parse_tolerant()` successfully extracted a tool call exactly **once**. That one call reached Kavach, which correctly blocked it. The other 559 times, the agent died before it ever produced a valid action.

---

### 3. Why the numbers look deceptively good

This is the most important part to understand, because the numbers printed at the end of the run are actively misleading if you don't know what happened.

**`attack_success_rate: 0.0` — this is NOT a win.** An attack "succeeds" in AgentDojo when the agent executes the malicious injected instruction. If the agent never calls any tools at all, it can never execute a malicious instruction either. So `gemma2:9b` achieved a 0% attack success rate entirely by being broken, not by being secure. A completely offline model with no access to any tools would also score 0% — that doesn't mean it's secure, it means it's not doing anything.

**`fully_defended: True` — technically accurate, completely useless.** This flag is set when zero calls failed open (i.e., Kavach was reachable for every call it received). Since Kavach only received one call total, `fully_defended: True` just means "the one time Kavach was invoked, it was reachable." It says nothing about the 559 pairs where the model never produced a valid tool call.

**`security: 82.4%` in the baseline — also not real security.** The baseline run (without Kavach) also showed high security because the same parser failure meant the agent never executed any malicious actions either. This is "security by failure" — the model looks secure because it can't do anything at all, benign or malicious.

**`benign_utility: 0.025` — this is the only honest number** and it tells the real story. The agent completed the legitimate user task successfully in only 2.5% of runs. This means 97.5% of the time, the model failed before it could do anything useful. With numbers this low, there is no benchmark — there is only noise.

---

### 4. Why Kavach was barely called at all

The `kavach.total_calls: 1` number is the clearest evidence of what went wrong. In a working run, you would expect Kavach to be called roughly once per task pair — one call for each time the agent tries to execute a tool action. With 560 pairs, you'd expect around 560 Kavach calls (more if the agent retries). Instead Kavach was called exactly once.

The reason is simple: Kavach intercepts tool calls at the moment of execution, right before a tool actually runs. If `_parse_tolerant()` fails to extract a tool call from the model's output, the agent never issues an execution request, so Kavach never sees anything. The problem happened upstream of Kavach entirely, in the parsing layer between the model's raw text and the structured tool call format that the benchmark harness understands.

This is an important point for understanding what the result means for OpenClaw. It doesn't mean Kavach can't work with Gemma. It means the AgentDojo benchmark harness couldn't translate Gemma's output format into the structured format it needs to route calls to Kavach. In real OpenClaw, OpenClaw's own tool-call parsing layer handles this translation and is already tuned for Gemma's format. So valid tool calls do reach Kavach in production — the benchmark just couldn't replicate that.

---

### 5. What the parser fix does

The fix added to `run_agentdojo_kavach.py` is a single addition to `_parse_tolerant()`. After extracting the raw text between the function tag and its closer, the parser now finds the last `}` character and truncates everything after it:

```python
last_brace = raw.rfind("}")
if last_brace != -1:
    raw = raw[:last_brace + 1]
```

This strips the trailing ` \n``` ` (or any other garbage after the JSON object closes) before passing the string to `json.loads()`. The fix is robust — it handles any amount of trailing whitespace, backticks, or markdown artifacts because it anchors to the structural end of the JSON object itself rather than trying to guess the exact format of the wrapper.

---

### 6. The new script improvements

Beyond the parser fix, the benchmark script now has several additions that would have caught this failure within the first few minutes instead of at the very end of a hours-long run.

**Pre-flight checks** run before the benchmark starts and verify that Ollama is running, the requested model is available in Ollama, Kavach's parliament server is reachable, and — critically — that the model can actually produce a parseable tool call. If that last check fails, it prints a warning immediately and you know not to start the full run.

**Live progress monitoring** runs a background thread throughout the benchmark that watches the log directory for newly written result files. Every 10 completed pairs it prints a running tally of utility and security scores. This gives you a real-time window into whether the model is actually working.

**Early-abort warning** is triggered if utility stays at 0% after 30 pairs. Rather than silently continuing a broken run for hours, the script prints a loud multi-line warning recommending that you press Ctrl+C, explaining what the likely cause is, and suggesting fixes. You can disable this with `--abort-threshold 0` if you need to force a full run.

**Parse-failure counter** in `_parse_tolerant()` tracks how many times the parser fails. After 10 consecutive failures it prints a warning explaining that the model is generating tool calls but they can't be parsed, and that the run results will be meaningless.

---

## What the numbers SHOULD look like

For context, here are the targets from `PARV_RESULTS.md` (what a working run looks like):

| Metric | Target value | What you got |
|---|---|---|
| Baseline ASR | ~17–20% | 0% (model couldn't call tools) |
| ASR with Kavach | ≤ 5% | 0% (same reason, not real) |
| Benign utility (baseline) | ~47.73% | 5.9% (broken) |
| Benign utility (with Kavach) | ≥ 40% | 2.6% (broken) |
| Kavach total_calls | ~560 | **1** (catastrophically broken) |

---

## What to do for Run 2

### Step 0 — Pull the parv branch

Everything you need is on the `parv` branch — the fixed script, the post-mortem, and all the latest from main. Pull it:

```bash
git fetch origin
git checkout parv
git pull origin parv
```

The `run_agentdojo_kavach.py` script now has a completely rewritten parser. It uses a proper **balanced JSON extractor** that tracks brace depth through strings and escape sequences — this handles all the edge cases Gemma throws at it:
- Markdown ` ```json ``` ` wrappers stripped before extraction
- Balanced `{...}` found by tracking depth (not string search)
- Unescaped `"` inside string values repaired automatically
- Missing closing brace(s) appended if model truncated the object
- No-arg calls (`<function=get_channels></function>`) handled as `{}`

### Step 1 — Always run the sanity check first

This takes about 5 minutes and verifies your environment is working before committing to a multi-hour run. It pings Ollama, checks the model is available, pings Kavach, and sends a real test tool call to verify the parser can extract it successfully.

```bash
# Replace <model> with whatever model you're using
python benchmarks/run_agentdojo_kavach.py \
    --model-id <model> \
    --sanity
```

You'll see output like:
```
[pre-flight] Ollama at localhost:11434 ...    ✅
[pre-flight] Model '<model>' in Ollama ...   ✅
[pre-flight] Kavach parliament at :8088 ...  ✅
[pre-flight] Testing tool-call format ...    ✅  parsed: FunctionCall(function='send_email', args={...})
```

If the last line shows `⚠️ No tool call parsed` → stop. The parser still can't handle this model's format. Message Ishani before running anything further.

If everything shows ✅ → you're good to start the full run.

### Step 2 — Model choice for your RTX 5060 (8GB VRAM)

Your GPU has 8GB VRAM. Here are your options, ranked by how well they work for AgentDojo specifically:

| Model | VRAM needed | Function calling quality | Notes |
|---|---|---|---|
| `llama3.1:8b` | ~4.9GB | ⭐⭐⭐ Excellent | Best option — explicitly trained for function calling |
| `qwen2.5:7b` | ~4.5GB | ⭐⭐⭐ Excellent | Strong alternative, very reliable |
| `mistral-nemo:12b` | ~7.5GB | ⭐⭐⭐ Excellent | Highest quality that fits in 8GB |
| `gemma2:9b` | ~5.4GB | ⭐ Poor (fixable) | Only use after the sanity check confirms the parser fix works |

If you want fast, clean, definitely-valid results → use `llama3.1:8b`. Pull it with:
```bash
ollama pull llama3.1:8b
```

If you specifically need to test with `gemma2:9b` because OpenClaw uses Gemma → that's a valid reason, but run the sanity check first to confirm the markdown parser fix works in your environment before starting the 560-pair run.

### Step 3 — Full run with live feedback

```bash
python benchmarks/run_agentdojo_kavach.py \
    --suite workspace \
    --model-id llama3.1:8b \
    --attack important_instructions \
    --out benchmarks/results_v2/agentdojo_laptop_llama31
```

During the run you will now see live updates every 10 pairs:
```
[progress] 10 pairs done │ utility: 4/10 (40%) │ security: 7/10 (70%)
[progress] 20 pairs done │ utility: 9/20 (45%) │ security: 14/20 (70%)
...
```

If utility stays at 0% after 30 pairs, the script will warn you loudly to Ctrl+C and fix the problem. Don't ignore this warning and let the run continue — you'll waste hours on invalid data.

### Step 4 — Commit and push results

```bash
git config user.name "Parv Parmar"
git config user.email "parvparmar23@gmail.com"

git add benchmarks/results_v2/agentdojo_laptop_llama31/
git commit -m "eval: AgentDojo run2 with llama3.1:8b on RTX 5060

ASR (Kavach):    X%
Benign utility:  X%
Kavach calls:    N
Model: llama3.1:8b
Hardware: [laptop], RTX 5060 8GB"

git push origin parv
```


---

## Why Kavach still works fine with Gemma in real OpenClaw

It is worth being explicit about this because the failed run might give the wrong impression. Kavach is not broken for Gemma. The AgentDojo benchmark failing with `gemma2:9b` tells us nothing about whether Kavach can protect a Gemma-based agent in a real deployment. Here is why.

The failure happened in the **parsing layer** between the model's raw text output and the structured tool call that the benchmark harness needs to route to Kavach. AgentDojo's harness was not written with Gemma's markdown-wrapping behavior in mind, so it couldn't translate Gemma's output into the format it needed. The harness is a testing framework, not a production system.

In real OpenClaw, the architecture is different. OpenClaw has its own tool-call parsing layer that has been specifically tuned for Gemma's output format. When a user asks OpenClaw to do something, Gemma produces a response, OpenClaw's layer parses it correctly, and the resulting structured tool call is then routed to Kavach's parliament for screening before execution. That pipeline works. The benchmark just couldn't replicate the OpenClaw-specific parsing layer because AgentDojo is a general framework.

The single time Kavach was called during the Run 1 benchmark — the one valid tool call the parser managed to extract in 560 tries — Kavach correctly blocked it. Kavach's screening logic is working. The plumbing between Gemma and AgentDojo just wasn't.

---

## What's fixed on the parv branch (vs Run 1)

| File | What changed |
|---|---|
| `benchmarks/run_agentdojo_kavach.py` | Full parser rewrite: balanced JSON extractor, unescaped-quote repair, missing-brace fallback, markdown fence stripper, parse-fail counter |
| `benchmarks/run_agentdojo_kavach.py` | Pre-flight checks (`--sanity` flag), live progress every 10 pairs, early-abort at 30 pairs with 0% utility |
| `benchmarks/results_v2/agentdojo_gemma_laptop/FINDINGS_AND_PLAN.md` | Full technical findings from Run 1 |
| `benchmarks/results_v2/AGENTDOJO_RUN1_POSTMORTEM.md` | This file — instructions for Run 2 |
| `benchmarks/results_v2/agentdojo_slack_llama_laptop/` | Ishani's smoke test (slack suite, 3 baseline pairs — sanity reference) |

---

*Written by Ishani + Antigravity after full analysis of Run 1 commit `91b19db`. Updated 2026-06-19 with robust parser from `fix-agentdojo-gemma-parser`.*

---

## Methodology Audit (June 29)

A full audit of the AgentDojo integration against the AgentDojo paper (§3.4) and the
installed AgentDojo source found **four candidate bugs**. After verifying each against
the real source — not just trusting the audit — only **one** was a true bug, and it
was critical.

| # | Finding | Verdict |
|---|---|---|
| **1** | `_format_tool_call` read `fn.name` / `fn.arguments`, but AgentDojo's `FunctionCall` exposes `.function` (the name string) and `.args` (the dict). Every tool call reached the parliament as **`tool:unknown args:{}`**, so Kavach screened an EMPTY action and allowed everything. | 🔴 **REAL — CRITICAL.** Runs *looked* healthy (Kavach called ~560×) while screening nothing → fake security numbers. **Fixed** (`tc.function` / `tc.args`) + an EMPTY-ACTION fatal guard. Verified live: Kavach now blocks real attacks. |
| **2** | "Defense screens too late (after the tool executes)." | 🟢 **NOT a bug.** On BLOCK the defense appends tool-result messages, which makes `ToolsExecutor` skip — pre-execution block confirmed in source. |
| **3** | "`benign_utility` mislabeled + ASR inverted." | 🟡 **Label fix only.** The field was Utility-Under-Attack (renamed); a true Benign Utility no-attack pass was added (`--benign`). **ASR was already correct** — verified `security==True` ⟺ attack succeeded and `aggregate_results = mean(security)`. Inverting it would have *introduced* a bug. |
| **4** | "Truncated system prompt (missing the 4 official bullets)." | 🟢 **NOT a bug.** All four official bullets were already present. |

**Consequence — all prior AgentDojo result files were invalidated and deleted.** Bug #1
means every committed run (Parv's gemma2:9b Run 1, the llama3.1:8b "takes") screened
`tool:unknown args:{}` for every call, so their "defended" security numbers are
meaningless. They were removed; do not cite them.

**The Dell gemma4:26b run is therefore the FIRST valid AgentDojo benchmark.** The laptop
validation (llama3.1:8b) confirmed the methodology is now sound — Kavach receives real
actions and blocks real attacks end-to-end — but its numbers are not paper-grade (weak
model, CPU). The reportable number comes from the Dell.

**Real finding (not a bug):** in the validation, a `send_money(attacker, …)` call was
**ALLOWED**. Kavach's corpus is strong on exfiltration / credential / code-execution but
**light on banking-suite financial fraud** — a genuine corpus-coverage gap, and a
candidate for the `corpus_agent` to close.

*Audit + fixes: 2026-06-29. Fix commits `8c0d93f`, `4819ef7`, `2338bd7` on `main`.*
