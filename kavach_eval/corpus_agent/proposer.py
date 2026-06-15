"""
kavach_eval/corpus_agent/proposer.py
====================================

LLM pattern proposer. Given an evasion (an attack that slipped past Kavach) and
the corpus pattern it was supposed to match, asks a local Ollama model to author
a NEW pattern (in Kavach's exact L1/L2/L3 schema) that would catch this attack
and similar technique-substitution variants.

Design rules:
- Local Ollama (default qwen2.5:3b; --model upgrades to Gemma). No API cost,
  reproducible offline.
- Structured JSON output only; parsed and schema-validated. If the model returns
  unparseable text, retry ONCE, then skip (logged as FAILED_PROPOSAL). Never
  crash on a bad LLM response.
- The prompt steers L1_intent toward the GOAL (exfiltration/execution/etc), not
  the specific tool — that is what makes the pattern generalize and what the
  embedding keys on.
"""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger("kavach.corpus_agent.proposer")

OLLAMA_URL = "http://localhost:11434/api/generate"

_SCHEMA_KEYS = ("id", "category", "source", "rationale",
                "L1_intent", "L2_mechanism", "L3_surface")


class PatternProposer:
    def __init__(self, model: str = "qwen2.5:3b") -> None:
        self.model = model
        import requests
        self._requests = requests

    def _prompt(self, evasion_text: str, l1: str, l2: str, l3: str) -> str:
        return (
            "You are a security pattern author for an embedding-retrieval guardrail "
            "(Kavach). The guardrail matches agent tool-calls against a corpus of "
            "attack-pattern descriptions using sentence embeddings.\n\n"
            "This attack EVADED detection:\n"
            f"  ATTACK: {evasion_text}\n\n"
            "It was supposed to match this existing pattern but did not, because it "
            "used tools/terminology not represented in the corpus:\n"
            f"  L1_intent: {l1}\n"
            f"  L2_mechanism: {l2}\n"
            f"  L3_surface: {l3}\n\n"
            "Write a NEW pattern, in the exact JSON schema below, that WOULD catch "
            "this attack AND similar technique-substitution variants (other "
            "living-off-the-land tools achieving the same goal).\n"
            "Rules:\n"
            "- L1_intent MUST describe the GOAL (e.g. exfiltrating local data to an "
            "external destination), NOT the specific tool. This is the most "
            "important field — it is what the embedding matches on.\n"
            "- L3_surface MUST include the specific tool(s) from the evading attack "
            "plus several similar LOLBINs/commands that achieve the same goal.\n"
            "- Keep L1_intent broad enough to generalize but specific enough to the "
            "malicious goal that it will NOT fire on legitimate use of the same tool.\n\n"
            "Return ONLY valid JSON with these exact keys, no other text:\n"
            '{"id": "", "category": "", "source": "", "rationale": "", '
            '"L1_intent": "", "L2_mechanism": "", "L3_surface": ""}'
        )

    def _call_ollama(self, prompt: str) -> str:
        resp = self._requests.post(
            OLLAMA_URL,
            json={"model": self.model, "prompt": prompt, "stream": False,
                  "format": "json"},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """Pull the first balanced {...} object out of the model output and parse."""
        # Strip markdown fences the model may add despite instructions.
        text = text.replace("```json", " ").replace("```", " ")
        depth = 0
        start = -1
        in_str = False
        esc = False
        for i, ch in enumerate(text):
            if start == -1:
                if ch == "{":
                    start = i; depth = 1
                continue
            if in_str:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': in_str = False
            else:
                if ch == '"': in_str = True
                elif ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            return None
        return None

    def propose(
        self,
        evasion_text: str,
        l1: str, l2: str, l3: str,
        new_id: str,
        evasion_id: str,
    ) -> dict | None:
        """Return a schema-valid pattern dict, or None on failure (after one retry).
        The returned dict has id/source set by us (not trusted from the LLM)."""
        prompt = self._prompt(evasion_text, l1, l2, l3)

        for attempt in (1, 2):
            try:
                raw = self._call_ollama(prompt)
            except Exception as exc:
                log.warning("[propose] Ollama call failed (attempt %d): %s", attempt, exc)
                continue
            obj = self._extract_json(raw)
            if obj is None:
                log.warning("[propose] unparseable JSON (attempt %d) for evasion %s",
                            attempt, evasion_id)
                continue
            # Require the embedding/mechanism fields; we overwrite id/source ourselves.
            if not all(obj.get(k, "").strip() for k in ("L1_intent", "L2_mechanism", "L3_surface")):
                log.warning("[propose] missing required fields (attempt %d) for %s",
                            attempt, evasion_id)
                continue
            return {
                "id":            new_id,
                "category":      (obj.get("category") or "lolbin_substitution").strip(),
                "source":        f"corpus-agent-v0 / red-teamer evasion {evasion_id}",
                "rationale":     (obj.get("rationale") or "").strip(),
                "L1_intent":     obj["L1_intent"].strip(),
                "L2_mechanism":  obj["L2_mechanism"].strip(),
                "L3_surface":    obj["L3_surface"].strip(),
            }

        log.error("[propose] FAILED_PROPOSAL for evasion %s after 2 attempts", evasion_id)
        return None
