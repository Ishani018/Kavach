#!/usr/bin/env python3
"""Patch test_navigator_isolated.py to read 'turns' key and use labels for truth."""
from pathlib import Path

p = Path('kavach_eval/tests/test_navigator_isolated.py')
text = p.read_text(encoding='utf-8')

old1 = '''        tool_sequence = case.get("tool_sequence") or []
        # dataset extraction stored only tool calls (no explicit type markers)
        tool_calls = []
        for tc in tool_sequence:
            if isinstance(tc, dict) and tc.get("tool"):
                tool_calls.append(tc)

        truth_benign = _is_benign_case(case)
        truth_label = "BENIGN" if truth_benign else "ATTACK"'''

new1 = '''        # Use 'turns' key (from build_agentdojo_dataset.py) or fallback 'tool_sequence'
        tool_sequence = case.get("turns") or case.get("tool_sequence") or []
        tool_calls = []
        for tc in tool_sequence:
            if isinstance(tc, dict):
                tool = tc.get("tool") or tc.get("tool_name")
                if tool:
                    tool_calls.append(tc)

        # Truth from labels.is_attack_case (set by build_agentdojo_dataset.py)
        labels = case.get("labels", {})
        is_attack = labels.get("is_attack_case", False)
        truth_label = "ATTACK" if is_attack else "BENIGN"'''

assert old1 in text, "old1 not found"
text = text.replace(old1, new1, 1)

# Also remove unused _is_benign_case function (optional, no harm keeping it)
p.write_text(text, encoding='utf-8')
print("Patched successfully.")
