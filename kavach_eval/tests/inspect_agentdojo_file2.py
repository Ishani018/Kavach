#!/usr/bin/env python3
"""Inspect an AgentDojo result file WITH an injection present."""
import json
from pathlib import Path

# Find first file where injection is present (not "none")
log_dir = Path("benchmarks/results_v2/agentdojo_slack_gemma_dell/logs")
for f in sorted(log_dir.rglob("*.json")):
    data = json.loads(f.read_text(encoding="utf-8"))
    if str(data.get("injection_task_id")) not in ("None", "none", ""):
        print(f"File: {f}")
        print(f"Keys: {sorted(data.keys())}")
        print(f"user_task_id: {data.get('user_task_id')}")
        print(f"injection_task_id: {data.get('injection_task_id')}")
        print(f"Has 'prompt' key: {'prompt' in data}")
        print(f"Has 'goal' key: {'goal' in data}")
        print(f"Has 'injection_goal' key: {'injection_goal' in data}")
        print(f"Has 'instructions' key: {'instructions' in data}")
        print(f"Has 'system_prompt' key: {'system_prompt' in data}")
        
        # Check messages[0].content for the prompt
        msgs = data.get("messages", [])
        if msgs:
            first = msgs[0]
            cnt = first.get("content", "")
            if isinstance(cnt, list):
                # It's a list of content blocks
                for block in cnt:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("content", "")
                        print(f"\nFirst {len(text)} chars of system prompt text:\n{text[:300]}")
                        break
            elif isinstance(cnt, str):
                print(f"\nFirst {len(cnt)} chars of system prompt:\n{cnt[:300]}")
        break
