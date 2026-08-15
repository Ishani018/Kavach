# Parv handoff — kavach-rearch, live-agent InjecAgent/AgentDojo work

Written for picking this up fresh on the Dell. Command-focused, not
narrative — see README.md's "InjecAgent live-agent supporting case study"
section for the full findings writeup if you want the reasoning behind any
of this.

## 1. What's new on kavach-rearch since you last looked

A live-agent InjecAgent runner (`injecagent_live_runner.py`, root) was built
and run tonight: a real qwen2.5:7b agent, turn-by-turn via Ollama, dispatching
every proposed tool call to Kavach's live server — closer to real agent
behavior than either the Gemma-4-26B baseline or the static structured-args
replay. Three real bugs were found and fixed in the process (dead-server
silent failure, multi-call-per-turn truncation, premature outcome-
finalization on multi-step attacks). The corrected 50-case run found CHANNEL
correctly blocks 4/4 fully-dispatched exfil sends at confidence 1.0 — but
only 6/50 cases (12%) ever got a real dispatched attacker call, the rest
being qwen2.5:7b declining to act. Full detail, numbers, and caveats: README.md's
"InjecAgent live-agent supporting case study" section and
`benchmarks/results_v2/README_injecagent_live_50case.md`.

## 2. `forced_tool_call.py` — built for you specifically

**What it does:** forces an Ollama model to emit valid tool-call JSON,
instead of free-text prose ("Would you like me to proceed?"). This is the
direct fix for the failure mode your Gemma 2B run hit — the model declining
to call a tool at all.

**How:** Ollama's `/api/chat` has a `format` field that accepts a raw JSON
Schema; when set, Ollama constrains token sampling so the response validates
against that schema. This module builds a schema requiring "the response IS
a tool call" (name from your allowed tool list + args matching that tool's
own parameter shape), so the model structurally cannot produce anything else.

**Zero Kavach dependency** — confirmed, no imports from this repo's
`parliament/` or anywhere else. It only needs: a model name, a message
history, a list of tool schemas, and an Ollama URL. Drops into your
AgentDojo loop directly.

**Signature:**
```python
def get_forced_tool_call(
    model: str,
    messages: list[dict],
    tool_schemas: list[dict],
    ollama_url: str,
    timeout_s: float = 180.0,
) -> dict:
    # returns {"tool_name": str|None, "args": dict|None,
    #          "raw_content": str|None, "latency_s": float, "error": str|None}
    # never raises -- check result["error"] is None before trusting the rest
```

**Minimal example:**
```python
from forced_tool_call import get_forced_tool_call

result = get_forced_tool_call(
    model="qwen2.5:7b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather in Paris?"},
    ],
    tool_schemas=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }],
    ollama_url="http://localhost:11434",
)
if result["error"] is None:
    print(result["tool_name"], result["args"])
```

**Pointing it at AgentDojo's tool schemas specifically:** AgentDojo's own
`Tool` objects (from `agentdojo.functions_engine`) carry a pydantic
parameter model per tool. Convert each to the same OpenAI-style shape this
module expects:
```python
tool_schemas = [
    {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters.model_json_schema(),  # or however
                # your AgentDojo version exposes the pydantic schema --
                # check agentdojo.functions_engine for the exact accessor
                # on your installed version, this varies across releases
        },
    }
    for tool in suite.tools  # or your suite's actual tool-list accessor
]
```
The only requirement is that each `parameters` value is a valid JSON Schema
object — however you get there from AgentDojo's own tool representation on
your installed version.

**Run it standalone first** (`python forced_tool_call.py`) before wiring it
into your loop — it has a built-in smoke test against local Ollama with a
toy weather tool, zero AgentDojo/Kavach dependency, confirms the schema
construction + call path work on your machine before you debug your own
integration on top of it.

## 3. Reproducing tonight's InjecAgent live-agent run, exact commands

### Ollama setup
```bash
ollama pull qwen2.5:7b          # or a stronger/tool-calling-finetuned model — see gotchas below
ollama run qwen2.5:7b "say hello"   # sanity check it loads
```
Set these environment variables before starting Ollama's server (see
gotcha #2 below for why context length matters):
```bash
export OLLAMA_CONTEXT_LENGTH=8192   # default 4096 is too small for multi-turn tool loops
export OLLAMA_KEEP_ALIVE=30m        # keeps the model loaded between calls; default unloads
                                     # after 5 min idle, which re-triggers a slow cold load
                                     # mid-run if turns are spaced out
```

### Kavach server start + health check
```bash
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
```
**Always verify before running anything against it** (gotcha #1 — see below):
```bash
curl http://127.0.0.1:8088/health
# must return {"status": "ok", ...} -- if connection refused/timeout, the
# server isn't actually up yet, or died. Don't proceed until this succeeds.
```

### injecagent_live_runner.py invocation

Free-form path (model may decline/ask for permission instead of calling a tool —
this is itself a real signal, not something to suppress by default):
```bash
python injecagent_live_runner.py \
  --n-cases 50 --seed <your-seed> --stratified \
  --kavach-url http://127.0.0.1:8088 \
  --out benchmarks/results_v2/injecagent_live_<yourlabel>.jsonl
```

Forced-format path (model cannot decline — every response is a valid tool call):
```bash
python injecagent_live_runner.py \
  --n-cases 50 --seed <your-seed> --stratified --force-format \
  --kavach-url http://127.0.0.1:8088 \
  --out benchmarks/results_v2/injecagent_live_<yourlabel>_forced.jsonl
```
Run both and compare — that's the point of `--force-format` being opt-in
rather than a replacement. It isolates "does Kavach's defense hold given a
real dispatched call" from "does the model choose to act at all."

Single-case targeted re-run (e.g. re-verifying a specific case_id):
```bash
python injecagent_live_runner.py --case-id ds_u08_a19 \
  --kavach-url http://127.0.0.1:8088 \
  --out benchmarks/results_v2/injecagent_verify.jsonl
```

### Where output lands, how to read it

- `<out>.jsonl` — one JSON line per case, written incrementally as each case
  finishes (safe to inspect or kill mid-run without losing completed cases).
  Each line has: `case_id`, `kind` (dh/ds), `attacker_tools`,
  `attacker_instruction`, `turns` (full turn-by-turn record: raw model
  output, every parsed tool call, every Kavach verdict), `outcome`.
- `<out>.summary.json` — aggregated run-level stats: total wall-clock,
  every multi-call-turn case (flagged specifically — these exercise the
  multi-call dispatch fix), every new malformation pattern not seen in
  earlier dry runs.
- `<out>.log` — the live run log, same content you see on stdout, per-case
  progress with elapsed/ETA.

**Read the outcome field first.** Possible values: `attack_blocked`,
`attack_allowed`, `attack_incomplete` (some but not all attacker tools were
dispatched before turns ran out), `attack_call_undispatched_parse_failure`,
`skipped_unparseable_tool_call`, `max_turns_reached`, `generation_failed`,
`kavach_unreachable`. **Only `attack_blocked`/`attack_allowed`/
`attack_incomplete` with a dispatched attacker call count as real data
points** — everything else means the model never actually gave Kavach
something real to judge. Check this before reporting any recall/FPR number;
see gotcha #3.

## 4. Known gotchas — plain language, with the fix

### 🔴 Gotcha #1 (bit us twice tonight): dead Kavach server produces FAKE verdicts if you don't check health first
If Kavach's port isn't actually up, every call in your run will fail with a
connection error — but if your code treats that identically to any other
per-call error (rather than aborting), the run will complete and LOOK
healthy, producing "outcomes" that have nothing to do with Kavach's real
behavior. **Always `curl http://127.0.0.1:8088/health` before starting a
run, and make sure your runner aborts (doesn't just log-and-continue) on a
connection-level failure mid-run, not just at the start.**
`injecagent_live_runner.py` already does this (`KavachUnavailableError`,
pre-flight + mid-run health checks) — if you're building your own AgentDojo
loop, copy this pattern, don't skip it.

### Gotcha #2: default 4096-token context window causes mid-task amnesia
Ollama's default context window (4096 tokens) fills up fast in a multi-turn
tool-calling loop (system prompt + tool schemas + growing message history +
tool results). Once it's exceeded, the model silently loses earlier context
— it may forget the original instruction, repeat a call it already made, or
lose track of what step it's on. Set `OLLAMA_CONTEXT_LENGTH=8192` (or
higher) before starting the Ollama server, per the setup command above.

### Gotcha #3: small models reliably fail at structured tool-calling — this is expected, don't debug it for hours
Gemma 2B, qwen2.5:7b, and llama3.1:8b (in our testing tonight) all showed
real, reproducible tool-calling weaknesses — asking for permission instead
of calling a tool, looping the same benign call repeatedly, or (in the
Gemma 2B case) not emitting tool calls at all. This matches the small-model
tool-calling literature broadly and is not a bug in the runner or in Kavach.
**Confirmed tonight: 40/50 cases (80%) never got the model to attempt a real
tool call.** If you hit this, the fix is not to debug the runner — either
(a) use `--force-format` to remove the model's ability to decline, or
(b) try a bigger or tool-calling-finetuned model. Don't sink hours into
"why won't it call the tool" before trying either of those first.

### Gotcha #4: Ollama's OpenAI-compatible `/v1` endpoint silently drops `tool_calls` under streaming
If you're using Ollama's OpenAI-compatibility layer (`/v1/chat/completions`)
rather than its native `/api/chat`, streaming responses can silently omit
the `tool_calls` field even when the model did request a tool call — the
native `/api/chat` endpoint (what `injecagent_live_runner.py` and
`forced_tool_call.py` both use) does not have this problem. **Use
`/api/chat`, not `/v1/chat/completions`, for anything that needs reliable
tool-call parsing.**

## 5. What we want from you on Dell today

Run **AgentDojo** (not InjecAgent — that's covered here) using
`forced_tool_call.py` against a real model with real VRAM headroom (Gemma 4
26B or similar — something with enough capacity that gotcha #3 shouldn't
apply). Report back in the **same structure** as this session's InjecAgent
findings, so the two are directly comparable:
- Full outcome-category breakdown (not just attack success/fail — include
  every non-dispatch category, same discipline as above)
- **Effective sample size** — how many cases actually got a real dispatched
  tool call, out of the total attempted. State this explicitly; don't let a
  50-case run imply 50 real tests happened if the effective N is smaller.
- Don't blend methodologies — if you run both free-form and `--force-format`
  passes, report them as two separate numbers, not one blended result.
