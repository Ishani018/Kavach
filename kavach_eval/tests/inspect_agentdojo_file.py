#!/usr/bin/env python3
"""Inspect one AgentDojo result JSON file to see its top-level keys."""
import json
from pathlib import Path

# Find first JSON file in the slack gemma dell results
log_dir = Path("benchmarks/results_v2/agentdojo_slack_gemma_dell/logs")
first = sorted(log_dir.rglob("*.json"))[0]
data = json.loads(first.read_text(encoding="utf-8"))

print(f"File: {first}")
print(f"Top-level keys: {sorted(data.keys())}")
print()

for k in data.keys():
    v = data[k]
    if isinstance(v, str):
        print(f"  {k} = {v[:200]}")
    elif isinstance(v, list):
        print(f"  {k} = list[{len(v)}] items")
        if k == "messages" and len(v) > 0:
            first_msg = v[0]
            print(f"    messages[0] keys: {sorted(first_msg.keys())}")
            print(f"    messages[0] role: {first_msg.get('role')}")
            content = str(first_msg.get("content", ""))
            print(f"    messages[0] content[:150]: {content[:150]}")
    elif isinstance(v, dict):
        print(f"  {k} = dict with keys {sorted(v.keys())}")
    elif isinstance(v, bool):
        print(f"  {k} = {v}")
    elif v is None:
        print(f"  {k} = None")
    else:
        print(f"  {k} = {type(v).__name__}: {v}")
