#!/usr/bin/env python3
"""Quick inspection of the agentdojo_groundtruth_dataset.jsonl"""
import json
from pathlib import Path

p = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "results_v2" / "agentdojo_groundtruth_dataset.jsonl"
lines = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]

print(f"Total records: {len(lines)}")
print(f"Attack cases:  {sum(1 for r in lines if r['labels']['is_attack_case'])}")
print(f"Benign cases:  {sum(1 for r in lines if not r['labels']['is_attack_case'])}")
print(f"Total turns:   {sum(len(r['turns']) for r in lines)}")

tools = {}
for r in lines:
    for t in r['turns']:
        tools[t['tool']] = tools.get(t['tool'], 0) + 1
print(f"\nTool frequency (top 15):")
for t, c in sorted(tools.items(), key=lambda x: -x[1])[:15]:
    print(f"  {t}: {c}")

sources = {}
for r in lines:
    src = r.get("source_file", "unknown")
    sources[src] = sources.get(src, 0) + 1
print(f"\nFrom {len(sources)} source directories")

# Check prompt/goal quality
empty_prompt = sum(1 for r in lines if not r.get("prompt"))
empty_goal = sum(1 for r in lines if not r.get("goal"))
has_injection_goal = sum(1 for r in lines if r.get("injection_goal"))
print(f"\nempty_prompt:     {empty_prompt}/{len(lines)}")
print(f"empty_goal:       {empty_goal}/{len(lines)}")
print(f"has_injection_goal: {has_injection_goal}/{len(lines)}")

# Sample records
print("\n--- Sample benign ---")
for r in lines:
    if not r['labels']['is_attack_case']:
        print(f"  case_id={r['case_id']}")
        print(f"  prompt[:120]: {str(r.get('prompt',''))[:120]}")
        print(f"  goal[:120]:   {str(r.get('goal',''))[:120]}")
        print(f"  injection_goal: {r.get('injection_goal')}")
        print(f"  turns: {len(r['turns'])} calls")
        for t in r['turns'][:2]:
            print(f"    [{t['step_index']}] {t['tool']}")
        break

print("\n--- Sample attack ---")
for r in lines:
    if r['labels']['is_attack_case']:
        print(f"  case_id={r['case_id']}")
        print(f"  prompt[:120]: {str(r.get('prompt',''))[:120]}")
        print(f"  goal[:120]:   {str(r.get('goal',''))[:120]}")
        print(f"  injection_goal: {str(r.get('injection_goal',''))[:120]}")
        print(f"  turns: {len(r['turns'])} calls")
        for t in r['turns'][:3]:
            print(f"    [{t['step_index']}] {t['tool']} args={list(t['args'].keys())}")
        break
