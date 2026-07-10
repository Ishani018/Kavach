#!/usr/bin/env python3
"""
PROTOTYPE ONLY -- not wired into parliament/, standalone isolated script.

Literal constraint-type extractor (Option B, cheap tier). Given a real user
instruction, calls a local Ollama model to extract structured constraints:
    {applies_to_tools, constraint_type, target_argument, authorized_value}

Uses the EXACT call/parse/retry scaffolding pattern from
kavach_eval/corpus_agent/proposer.py (PatternProposer): plain requests.post
to Ollama's /api/generate, format="json" for structured output, a
balanced-brace JSON extractor tolerant of markdown fences, retry-once-then-
skip on parse failure.
"""
from __future__ import annotations

import json
import logging
import requests

log = logging.getLogger("literal_constraint_prototype")
logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

OLLAMA_URL = "http://localhost:11434/api/generate"

_SCHEMA_KEYS = ("applies_to_tools", "constraint_type", "target_argument", "authorized_value")


class LiteralConstraintExtractor:
    def __init__(self, model: str = "qwen2.5:7b") -> None:
        self.model = model

    def _prompt(self, instruction_text: str, tool_schema: dict | None = None) -> str:
        """
        v2 fix: the model must be told the REAL tool name(s) and argument
        schema available in this session -- v1 asked it to freely invent
        both from instruction text alone, which produced plausible-sounding
        but wrong names (e.g. 'slack_invite' instead of the real
        'invite_user_to_slack'), so the downstream equality check never
        found an applicable constraint at all. Mirrors how a real
        integration would provide this (the tool registry / runtime.functions
        schema is already known ahead of time, same as what the LLM agent
        itself sees to be able to call the tool in the first place).

        tool_schema: {"tool_name": ["arg1", "arg2", ...], ...} -- the actual
        callable tools and their argument names visible in this session.
        """
        schema_block = ""
        if tool_schema:
            schema_lines = "\n".join(
                f"  - {name}({', '.join(args)})" for name, args in tool_schema.items()
            )
            schema_block = (
                "\nThe following REAL tools and their REAL argument names are "
                "available in this session -- you MUST use these exact tool names "
                "and argument names in your output, never invent new ones:\n"
                f"{schema_lines}\n"
            )
        return (
            "You are extracting authorization constraints for an AI-agent security "
            "guardrail (Kavach). The agent will execute tool calls on behalf of a "
            "user; some of those calls might be tampered with by a prompt-injection "
            "attack. Your job is to read the user's ACTUAL instruction and identify "
            "any LITERAL VALUE the user explicitly named that a tool argument must "
            "match exactly.\n"
            f"{schema_block}\n"
            "Only extract a constraint when the user's instruction contains an "
            "explicit, literal value (a specific string, number, name, or "
            "identifier) that should be used as-is in a tool call. Do NOT extract "
            "a constraint if the value must come from a document, a computed "
            "result, or is only vaguely described (e.g. 'the largest file', "
            "'my usual bills') -- those are NOT literal constraints, leave "
            "constraints empty for those.\n\n"
            f"USER INSTRUCTION: {instruction_text}\n\n"
            "Return ONLY valid JSON with this exact shape, no other text:\n"
            '{"constraints": [{"applies_to_tools": ["EXACT_tool_name_from_the_list_above"], '
            '"constraint_type": "literal", "target_argument": "EXACT_arg_name_from_the_list_above", '
            '"authorized_value": "the exact value the user named"}]}\n\n'
            "If there is no clear literal value to extract, return "
            '{"constraints": []}'
        )

    def _call_ollama(self, prompt: str) -> str:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        text = text.replace("```json", " ").replace("```", " ")
        depth = 0
        start = -1
        in_str = False
        esc = False
        for i, ch in enumerate(text):
            if start == -1:
                if ch == "{":
                    start = i
                    depth = 1
                continue
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            return None
        return None

    def extract(self, instruction_text: str, case_id: str = "", tool_schema: dict | None = None) -> list[dict] | None:
        """Return a list of constraint dicts, or None on failure after 2 attempts."""
        prompt = self._prompt(instruction_text, tool_schema=tool_schema)
        for attempt in (1, 2):
            try:
                raw = self._call_ollama(prompt)
            except Exception as exc:
                log.warning("[%s] Ollama call failed (attempt %d): %s", case_id, attempt, exc)
                continue
            obj = self._extract_json(raw)
            if obj is None:
                log.warning("[%s] unparseable JSON (attempt %d): %r", case_id, attempt, raw[:200])
                continue
            constraints = obj.get("constraints")
            if constraints is None:
                log.warning("[%s] missing 'constraints' key (attempt %d)", case_id, attempt)
                continue
            # basic schema validation, defensively
            valid = []
            for c in constraints:
                if not isinstance(c, dict):
                    continue
                if not all(k in c for k in _SCHEMA_KEYS):
                    log.warning("[%s] constraint missing required keys: %r", case_id, c)
                    continue
                valid.append(c)
            return valid
        log.error("[%s] extraction FAILED after 2 attempts", case_id)
        return None


def _normalize_value(v) -> str:
    """Strip whitespace, then strip one layer of matching surrounding quote
    characters (straight or curly, single or double) the extractor model
    sometimes emits around string values, e.g. "'mark@x.com'" -> "mark@x.com".
    Only strips a single matching pair, never touches interior content."""
    s = str(v).strip()
    quote_pairs = (('"', '"'), ("'", "'"), ("‘", "’"), ("“", "”"))
    for open_q, close_q in quote_pairs:
        if len(s) >= 2 and s[0] == open_q and s[-1] == close_q:
            s = s[1:-1].strip()
            break
    return s


def check_action_against_constraints(
    tool_name: str, action_args: dict, constraints: list[dict]
) -> tuple[str, str]:
    """Deterministic literal-constraint check. Returns (verdict, reason).
    verdict is one of: "PASS" (no applicable constraint or matched),
    "VIOLATION" (an applicable constraint's value doesn't match)."""
    applicable = [c for c in constraints if tool_name in c.get("applies_to_tools", [])]
    if not applicable:
        return "PASS", f"no literal constraint applies to tool '{tool_name}'"
    for c in applicable:
        arg = c["target_argument"]
        expected = c["authorized_value"]
        actual = action_args.get(arg)
        if actual is None:
            return "PASS", f"argument '{arg}' not present in action (constraint doesn't apply)"
        if _normalize_value(actual) != _normalize_value(expected):
            return "VIOLATION", (
                f"argument '{arg}'={actual!r} does not match authorized value "
                f"{expected!r} extracted from user instruction"
            )
    return "PASS", "all applicable literal constraints matched"
