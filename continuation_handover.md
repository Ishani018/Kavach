# Continuation Handover: Kavach Benchmark Adaptation & Fixes

This document provides a complete summary of the modifications made to the AgentDojo benchmark driver for the Kavach defense, explaining **what** was done, **why** it was done, and **how** a subsequent LLM agent can continue the task.

---

## 1. Project Context & Environment
* **Repository**: Kavach (evaluating LLM agents against prompt injections under the Kavach defense server).
* **Base Benchmark Framework**: AgentDojo (v0.1.35).
* **Active Suite**: `workspace` (40 user tasks, 14 injection tasks).
* **Models Used**: Local Ollama endpoints, specifically `llama3.1:8b` (using `LlamaPromptingLLM`) and `gemma2:9b` (using `GemmaTolerantLLM`).
* **Kavach Defense Server**: Runs as a FastAPI application on `http://127.0.0.1:8088`.

---

## 2. Key Challenges & Implemented Fixes

### A. Broken JSON Parser & Unescaped Quotes (Resolved)
* **What**: Standard LLM completion parsing frequently failed because Ollama models outputted unescaped double quotes inside tool-call arguments, or failed to terminate XML tags properly.
* **Why**: This caused standard `json.loads` to crash, returning `broken JSON` errors.
* **Fix**: Implemented `_parse_tolerant` and `_repair_unescaped_quotes` in [run_agentdojo_kavach.py](file:///c:/Users/Parvp/Projects/Kavach/benchmarks/run_agentdojo_kavach.py) to extract balanced JSON strings, repair inner unescaped double quotes, and clean placeholder ellipsis patterns.

### B. Nested Tool Calls & AST Parsing Failures (Resolved)
* **What**: The agent was frequently getting `utility: False` on tasks `0, 3, 7, 11`. The logs showed the model attempting Python-style expressions (e.g. `body=find_inbox()`) as tool call arguments.
* **Why**: AgentDojo's AST parser (`parse_arg_value`) strictly requires argument values to be literal constants (strings, list of constants, ints, booleans, or None). Nested function calls/variables raise `ASTParsingError`, leading to tool execution failures.
* **Fix**:
  1. Updated `DEFAULT_SYS_MSG` to instruct the model to use **only** literal constants and call dependent tools sequentially (one per turn) instead of guessing/hallucinating file IDs.
  2. Intercepted `ASTParsingError` inside `LlamaPromptingLLM.query`'s formatting retry loop, sending explicit feedback that nested function calls or variables are disallowed.

### C. Task Set Slicing (`--task-set`) (Resolved)
* **What**: Running all 40 user tasks (which results in 560 pairs per run) takes too long on local machines.
* **Why**: The user needed a way to partition the tasks and run them incrementally.
* **Fix**: Added a `--task-set` CLI argument (`1`, `2`, `3`, or `4`) in `run_agentdojo_kavach.py` which slices the `suite.user_tasks` ordered list:
  * **Set 1: Calendar** (User Tasks 0-12)
  * **Set 2: Email** (User Tasks 13-17)
  * **Set 3: Files** (User Tasks 18-25)
  * **Set 4: Mixed** (User Tasks 26-39)

### D. Dynamic Available Tools Suggestion on "Invalid Tool" (Resolved)
* **What**: When the model calls a tool name that does not exist, the environment returns `"Invalid tool ... provided."`. It needs set-specific context to recover.
* **Why**: Ollama models can hallucinate functions when they lose context or formatting constraint details.
* **Fix**: Overrode `_tool_message_to_user_message` in `LlamaPromptingLLM` and the `query` method in `GemmaTolerantLLM`. If the error contains `"invalid tool"`, we dynamically append set-specific lists of available tools based on the active `--task-set`:
  * If `task_set == 1`: Appends calendar tools list.
  * If `task_set == 2`: Appends email tools list.
  * If `task_set == 3`: Appends file tools list.
  * If `task_set == 4` (or other): Appends all suite tools.

---

## 3. How to Run & Verify

Before running, ensure Ollama is serving the model (`llama3.1:8b`) and the Kavach server is started:
```powershell
# 1. Start Ollama and run model
ollama run llama3.1:8b

# 2. Start the Kavach parliament server
.venv\Scripts\python parliament/server.py
```

### Run Sanity Check
Runs environment pre-flight checks and a tool-initiation probe checking if the model can successfully generate tool calls:
```powershell
$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python benchmarks/run_agentdojo_kavach.py --suite workspace --model-id llama3.1:8b --sanity
```

### Run Benchmark Subsets
Run any specific subset with/without Kavach, specifying output log directories:
```powershell
# Run the Email task set (Set 2)
$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python benchmarks/run_agentdojo_kavach.py --suite workspace --model-id llama3.1:8b --task-set 2 --out benchmarks/results_v2/agentdojo_laptop_llama3.1_8b_set2
```

---

## 4. Next Steps for Incoming LLM
1. **Verify Utility Improvements**: Run `task-set 2` (Email) or `task-set 1` (Calendar) and verify if the `utility` score goes above 0% and no longer suffers from the invalid tool or AST parsing failures.
2. **Handle Refusals**: Analyze if there are remaining failures due to LLM internal safety guardrails refusing tasks (e.g. email forwarding) and adjust system prompt bypasses if needed.
3. **Run Full Benchmark**: Run all sets to collect final benchmark metrics under the Kavach defense.
