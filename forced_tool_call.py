#!/usr/bin/env python3
"""
forced_tool_call.py
====================

STANDALONE, REUSABLE constrained-decoding helper for forcing an Ollama
chat model to emit a valid tool call, instead of free-text prose (e.g.
"Would you like me to proceed?"). Built for the Kavach InjecAgent
live-agent runner, but has ZERO Kavach-specific imports or assumptions --
it only needs an Ollama endpoint, a model name, a message history, and a
list of tool schemas in the standard OpenAI-style function-calling shape.

WHY THIS EXISTS
----------------
Ollama's native `tools` field (used by injecagent_live_runner.py's
call_ollama()) lets a model choose NOT to call a tool -- it can respond
with free-text instead, which is exactly what qwen2.5:7b did in ~80% of
a 50-case live-agent InjecAgent run tonight (asking for permission in
prose rather than acting). That's a real, useful signal about model
behavior, but it also means most cases never actually exercise the
downstream system being tested (Kavach, in this repo's case).

This module uses Ollama's STRUCTURED OUTPUT feature instead: the
`format` field of `/api/chat` accepts a raw JSON Schema, and Ollama
constrains token sampling so the response's `content` field is
guaranteed to validate against that schema. By building a schema that
requires "the model's content IS a tool call" (a name from the allowed
set + args matching that tool's parameter shape), the model cannot
produce free-text prose -- it is structurally forced to emit something
parseable as a tool call every turn.

This is a different, complementary mechanism to Ollama's native `tools`
field:
  - `tools` (native function-calling): the model MAY call a tool, via a
    separate `message["tool_calls"]` field, or may respond in plain text.
  - `format` (structured output, this module): the model's `content`
    field itself is constrained to match a schema. Used here to make
    "emit a valid tool call" the ONLY possible output shape.

USAGE (standalone, no Kavach dependency)
------------------------------------------
    from forced_tool_call import get_forced_tool_call

    tool_schemas = [
        {
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
        },
        # ... more tools, same OpenAI-style function-calling shape ...
    ]

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather in Paris?"},
    ]

    result = get_forced_tool_call(
        model="qwen2.5:7b",
        messages=messages,
        tool_schemas=tool_schemas,
        ollama_url="http://localhost:11434",
    )
    # result == {"tool_name": "get_weather", "args": {"city": "Paris"},
    #            "raw_content": "...", "latency_s": 1.23, "error": None}

This is exactly the shape AgentDojo's own tool-schema objects use (each
suite's `Tool` list can be converted to this dict shape via its own
`.to_dict()`/pydantic-schema helpers -- see AgentDojo's
`agentdojo.functions_engine` module), so this file can be handed to
someone running an AgentDojo loop against a DIFFERENT project with ZERO
changes: only `tool_schemas`, `messages`, `model`, and `ollama_url` need
to come from their own code.

RETURN SHAPE
------------
get_forced_tool_call() always returns a dict with these keys:
    tool_name   : str | None   -- the tool the model chose, or None on failure
    args        : dict | None  -- the tool's arguments, or None on failure
    raw_content : str | None   -- the raw JSON string content Ollama returned
    latency_s   : float        -- wall-clock time for the Ollama call
    error       : str | None   -- populated on any failure; tool_name/args
                                   are None whenever this is set. NEVER
                                   raises -- network errors, malformed JSON,
                                   and schema-validation failures are all
                                   captured here instead of propagating.

LIMITATIONS (stated plainly, not hidden)
------------------------------------------
- Requires an Ollama server new enough to support the `format` structured-
  output parameter (this has been in Ollama since the 0.5 line; if a
  request 400s specifically on `format`, upgrade Ollama).
- Structured output is only as good as your schema -- if a tool's
  `parameters` schema is too loose (e.g. no `required` list), the model
  may fill fields with plausible-looking placeholders rather than
  extracting real values from context. Same caveat applies to Ollama's
  native `tools` field, not unique to this module.
- Forcing a tool call removes the model's ability to say "I don't have
  enough information" or "I decline this request" in free text -- if
  your use case NEEDS to observe refusal behavior (as the free-form path
  in injecagent_live_runner.py currently does, on purpose), don't use
  this module for that comparison; use both and compare, which is exactly
  why injecagent_live_runner.py's --force-format flag is opt-in, not a
  replacement for the existing free-form path.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests

DEFAULT_TIMEOUT_S = 180.0


def _extract_all_defs(schema_or_list: Any, defs: dict[str, Any]) -> None:
    """Recursively walks the schemas to extract all definitions globally."""
    if isinstance(schema_or_list, dict):
        for k, v in schema_or_list.items():
            if k in ("$defs", "definitions") and isinstance(v, dict):
                defs.update(v)
            else:
                _extract_all_defs(v, defs)
    elif isinstance(schema_or_list, list):
        for item in schema_or_list:
            _extract_all_defs(item, defs)


def _inline_refs(schema: Any, defs: dict[str, Any]) -> Any:
    """Recursively inlines all $ref references in schema using extracted defs."""
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref_path = schema["$ref"]
            ref_name = ref_path.split("/")[-1]
            if ref_name in defs:
                return _inline_refs(defs[ref_name], defs)
            return schema

        new_schema = {}
        for k, v in schema.items():
            if k in ("$defs", "definitions"):
                continue  # strip definitions at this level
            new_schema[k] = _inline_refs(v, defs)
        return new_schema

    elif isinstance(schema, list):
        return [_inline_refs(item, defs) for item in schema]

    return schema


def _tool_call_schema(tool_schemas: list[dict[str, Any]]) -> dict[str, Any]:
    """Builds a JSON Schema that validates ONLY as a single tool call:
    {"tool_name": <one of the allowed names>, "args": {...matching that
    tool's parameters...}}.

    Uses a `oneOf` branch per tool so each branch can pin `tool_name` to
    that exact tool's name (via `const`) and require `args` to match that
    tool's own `parameters` schema -- this is what actually constrains the
    args shape per-tool, not just accepting any object for `args`.
    """
    defs: dict[str, Any] = {}
    _extract_all_defs(tool_schemas, defs)

    branches = []
    for entry in tool_schemas:
        fn = entry.get("function", entry)  # tolerate bare {"name":...} too
        name = fn["name"]
        params_schema = fn.get("parameters") or {"type": "object", "properties": {}}
        branches.append({
            "type": "object",
            "properties": {
                "tool_name": {"const": name},
                "args": params_schema,
            },
            "required": ["tool_name", "args"],
            "additionalProperties": False,
        })

    schema = branches[0] if len(branches) == 1 else {"oneOf": branches}
    return _inline_refs(schema, defs)


def _forced_call_system_note(tool_schemas: list[dict[str, Any]]) -> str:
    names = [
        (entry.get("function", entry)).get("name", "?")
        for entry in tool_schemas
    ]
    return (
        "You must respond with EXACTLY ONE tool call as JSON, choosing "
        "tool_name from this list: " + ", ".join(names) + ". "
        "Do not ask for confirmation, do not respond in prose -- output "
        "only the tool call JSON matching the required schema."
    )


def get_forced_tool_call(
    model: str,
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    ollama_url: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Calls Ollama's /api/chat with `format` set to a JSON Schema derived
    from `tool_schemas`, forcing the model to emit valid tool-call JSON as
    its `content` -- it structurally cannot respond with free-text prose.

    Parameters
    ----------
    model : str
        Ollama model name, e.g. "qwen2.5:7b".
    messages : list[dict]
        Standard chat-message list (role/content dicts), same shape you'd
        pass to Ollama's native /api/chat `messages` field.
    tool_schemas : list[dict]
        List of OpenAI-style function-calling tool definitions:
        [{"type": "function", "function": {"name": ..., "description": ...,
        "parameters": {...JSON-Schema...}}}, ...]. A bare
        {"name": ..., "parameters": {...}} shape (no "function" wrapper)
        is also tolerated.
    ollama_url : str
        Base Ollama URL, e.g. "http://localhost:11434" (NOT including
        "/api/chat" -- this function appends the path itself).
    timeout_s : float
        Request timeout in seconds.

    Returns
    -------
    dict with keys: tool_name, args, raw_content, latency_s, error.
    See module docstring for the full contract. Never raises.
    """
    endpoint = ollama_url.rstrip("/") + "/api/chat"
    schema = _tool_call_schema(tool_schemas)

    forced_messages = list(messages) + [
        {"role": "system", "content": _forced_call_system_note(tool_schemas)}
    ]

    payload = {
        "model": model,
        "messages": forced_messages,
        "format": schema,
        "stream": False,
    }

    t0 = time.perf_counter()
    try:
        r = requests.post(endpoint, json=payload, timeout=timeout_s)
        latency = time.perf_counter() - t0
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        latency = time.perf_counter() - t0
        err_msg = str(e)
        if 'r' in locals() and hasattr(r, 'text') and r.text:
            err_msg += f" | Details: {r.text}"
        return {"tool_name": None, "args": None, "raw_content": None,
                "latency_s": round(latency, 2), "error": f"Ollama request failed: {err_msg}"}

    raw_content = (data.get("message") or {}).get("content", "")
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as e:
        return {"tool_name": None, "args": None, "raw_content": raw_content,
                "latency_s": round(latency, 2),
                "error": f"structured-output content was not valid JSON despite format constraint: {e}"}

    tool_name = parsed.get("tool_name")
    args = parsed.get("args")
    if tool_name is None or args is None:
        return {"tool_name": None, "args": None, "raw_content": raw_content,
                "latency_s": round(latency, 2),
                "error": f"parsed JSON missing tool_name/args keys: {parsed!r}"}

    return {"tool_name": tool_name, "args": args, "raw_content": raw_content,
            "latency_s": round(latency, 2), "error": None}


if __name__ == "__main__":
    # Minimal standalone smoke test -- run directly (`python
    # forced_tool_call.py`) against a local Ollama instance to sanity-check
    # the schema-construction + call path before wiring it into a larger
    # runner. No Kavach or InjecAgent dependency.
    demo_tools = [
        {
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
        }
    ]
    demo_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather in Paris?"},
    ]
    result = get_forced_tool_call(
        model="qwen2.5:7b",
        messages=demo_messages,
        tool_schemas=demo_tools,
        ollama_url="http://localhost:11434",
    )
    print(json.dumps(result, indent=2))
