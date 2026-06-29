# AgentDojo + Kavach — Definitive Run Guide

**Read this fully before running.** It exists so you never waste a multi-hour run
again. The driver now hard-stops on the failure modes that wasted earlier runs.

---

## ⛔ Why earlier runs were thrown away

| Run | What went wrong | Now caught by |
|---|---|---|
| gemma2:9b (Jun 18) | Model can't function-call → ~97% tasks error before any attack | Pre-flight **tool-call probe** (hard-stops) |
| All llama3.1 "takes" | **Bug #1**: Kavach was fed `tool:unknown args:{}` every call → it screened an EMPTY action and allowed everything. Runs *looked* healthy (Kavach called ~560×) but the security numbers were FAKE. | **Bug #1 fixed** + an **EMPTY-ACTION fatal guard** that aborts the run |

**Those old result JSONs were deleted** — they are meaningless. Re-run from scratch.

---

## The three guards (all abort/​warn loudly — you cannot miss them)

1. **Pre-flight tool-call probe** — before any task runs, checks the model will
   actually *initiate* a tool call. A model that can't (gemma2:9b) → **hard-stop**
   with `ollama pull llama3.1:8b` instructions.
2. **EMPTY-ACTION fatal guard** (`kavach_agentdojo_defense.py`) — if ≥5 tool calls
   reach Kavach as `tool:unknown`/`args:{}`, the run **raises a fatal error**.
   This is the bug-#1 regression detector: Kavach screening nothing = fake numbers.
3. **FAIL-OPEN AUDIT** (end of run) — `run_fully_defended: true` only if every
   call reached a live parliament. If any failed open, those actions were NOT
   screened and the with-Kavach numbers are partially invalid.

---

## STEP 0 — start the two services

```powershell
# Terminal 1: Ollama
ollama run llama3.1:8b

# Terminal 2: Kavach parliament (from repo root)
.venv\Scripts\python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
```

## STEP 1 — sanity check (ALWAYS first; seconds, not hours)

```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python benchmarks/run_agentdojo_kavach.py --suite workspace --model-id llama3.1:8b --sanity
```
Every line must be ✅, including **"will it INITIATE tool calls … ✅"**. If any ❌,
fix it and re-run. Do not proceed past a ❌.

## STEP 2 — the run (only after STEP 1 is all green)

Use `--task-set` to run in chunks on a laptop (the full workspace is 560 pairs/condition):

| `--task-set` | Tasks | Pairs |
|---|---|---|
| 1 | Calendar (user 0–12) | ~182 |
| 2 | Email (user 13–17) | ~70 |
| 3 | Files (user 18–25) | ~112 |
| 4 | Mixed (user 26–39) | ~196 |

```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python benchmarks/run_agentdojo_kavach.py `
  --suite workspace --model-id llama3.1:8b --task-set 2 `
  --out benchmarks/results_v2/agentdojo_llama_set2
```

Add `--benign` to also compute the no-attack **Benign Utility** (and Kavach's
benign over-blocking cost). It's a separate pass, so it adds time.

---

## What the numbers MEAN (paper §3.4 — get these right)

The driver reports three distinct metrics. They are NOT interchangeable:

| Metric | Definition | In the summary |
|---|---|---|
| **Benign Utility** | user tasks solved with **NO attack** | `benign_utility` (only with `--benign`) |
| **Utility Under Attack** | user task solved **while the injection is present** | `utility_under_attack` |
| **Targeted ASR** | security cases where the **attacker's goal is MET** | `attack_success_rate` |

- `attack_success_rate = mean(security_results)` where AgentDojo sets
  `security = True` when the **attack succeeded** (verified in source). Lower ASR =
  better defense. (This is correct as-is — it is *not* inverted.)
- `asr_reduction = baseline ASR − with-Kavach ASR`. Positive = Kavach helped.

## Sanity-check your numbers against the paper's baselines

If your numbers are wildly off these, something is wrong (check the guards):

| Reference (paper, GPT-4o) | ASR |
|---|---|
| No defense | ~25% (and **Slack suite = 92%** — easiest to attack) |
| Tool-filter defense | **7.5%** |
| PI-detector (BERT) defense | low ASR but high false positives (utility drop) |

Kavach is a detector-style defense, so a healthy result is **ASR well below the
~25% no-defense baseline**, ideally near the tool-filter's 7.5%, with some benign
over-blocking cost (the paper's detectors lose 15–20% utility under attack).

> ⚠️ A laptop run with **llama3.1:8b** is a **plumbing/validation check**, not a
> paper number. The reportable AgentDojo result must come from **gemma4:26b on the
> Dell** (the primary config). Label laptop outputs accordingly.

---

## If a run looks wrong

- **`[KAVACH FATAL] EMPTY ACTION`** → bug #1 regressed; `_format_tool_call` must use
  `tc.function` / `tc.args`. Do not trust any numbers from such a run.
- **Pre-flight tool-call probe ❌** → the model can't function-call; switch model.
- **`run_fully_defended: false`** → parliament was unreachable for some calls; fix
  the server (one instance, real `/hook/parliament` verdict) and re-run.
- **utility stays 0%** → the early-abort warning will tell you to Ctrl+C; usually a
  weak model or a parser issue.
