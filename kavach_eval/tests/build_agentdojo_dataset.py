#!/usr/bin/env python3
"""
kavach_eval/tests/build_agentdojo_dataset.py
=============================================

Build a Navigator-evaluation dataset by mining EXISTING AgentDojo result files
from the runs directory. This avoids the circular-import problem in AgentDojo's
own package by reading the JSON result files that were already written by
previous runs (e.g. under benchmarks/results_v2/agentdojo_*).

Strategy:
- Scans a log directory for result JSON files (one per {user_task}_{injection_task} pair)
- Each file contains the full message history including tool calls
- Extracts tool calls as "benign" (from the user task's ground truth flow) and
  "attack" (from what the injection goal drove the agent to do)
- Labels: is_attack_case=True if an injection_task was present

Output:
    benchmarks/results_v2/agentdojo_groundtruth_dataset.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = ROOT / "benchmarks" / "results_v2" / "agentdojo_groundtruth_dataset.jsonl"


def _serialize_text(tool: str, args: dict) -> str:
    """Format exactly as fed to NAVIGATOR: tool:<name> args:<json>."""
    return f"tool:{tool} args:{json.dumps(args, default=str, sort_keys=True)}"


def extract_tool_calls_from_messages(messages: list[dict]) -> list[dict]:
    """Extract all tool call turns from AgentDojo's message format.

    AgentDojo records messages with roles: system, user, assistant, tool.
    Assistant messages may have `tool_calls` field (list of {function, args}).
    """
    turns = []
    step_index = 0
    for msg in messages:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                if isinstance(tc, dict):
                    fn = tc.get("function", "")
                    args = tc.get("args", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {"raw": args}
                    turns.append({
                        "type": "call",
                        "step_index": step_index,
                        "tool": fn,
                        "args": args,
                        "text": _serialize_text(fn, args),
                    })
                    step_index += 1
        elif role == "function" or role == "tool":
            # Skip tool output messages — they're results, not calls
            pass
    return turns


def extract_text_from_content(content_field) -> str:
    """Extract plain text from AgentDojo's content field.
    
    AgentDojo stores content as either:
      - A list of dicts: [{"type": "text", "content": "..."}, ...]
      - A plain string: "..."
    """
    if isinstance(content_field, list):
        for block in content_field:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("content", "")
    elif isinstance(content_field, str):
        return content_field
    return ""


def scan_result_directory(result_dir: Path) -> list[dict[str, Any]]:
    """Scan a directory tree for AgentDojo result JSON files and extract tool calls."""
    records = []
    json_files = list(result_dir.rglob("*.json"))
    print(f"  Found {len(json_files)} JSON files in {result_dir}")

    for fpath in sorted(json_files):
        # Skip summary files and large aggregate files
        if fpath.name in ("agentdojo_summary.json", "results.json"):
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"    SKIP {fpath.relative_to(result_dir)}: {e}")
            continue

        # AgentDojo result files contain: messages, utility (bool), security (bool),
        # user_task_id, injection_task_id, etc.
        messages = data.get("messages", [])
        if not messages:
            continue

        turns = extract_tool_calls_from_messages(messages)
        if not turns:
            continue

        # Determine identity
        user_task_id = data.get("user_task_id") or data.get("user_task") or fpath.parent.parent.name
        injection_task_id = data.get("injection_task_id") or data.get("injection_task") or fpath.parent.name

        is_attack = injection_task_id not in ("none", "None", "null", "", None)

        # --- Extract prompt from the system message (messages[0].content) ---
        prompt = ""
        if messages:
            prompt = extract_text_from_content(messages[0].get("content", ""))

        # --- Extract goal from the FIRST user message ---
        goal = ""
        injection_goal = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_text = extract_text_from_content(msg.get("content", ""))
                if not goal:
                    goal = user_text
                # For attack cases, look for injection instructions in user messages
                if is_attack and user_text:
                    lower = user_text.lower()
                    if "important_instructions" in lower or "injection" in lower:
                        injection_goal = user_text[:500]
                if not is_attack:
                    break  # benign: first user message is the goal

        # If injection goal was found separately, store it
        injection_goal_text = injection_goal if is_attack else None

        record = {
            "case_id": f"{user_task_id}_{injection_task_id}",
            "user_task_id": str(user_task_id),
            "injection_task_id": str(injection_task_id) if is_attack else None,
            "prompt": prompt,
            "goal": goal,
            "injection_goal": injection_goal_text,
            "difficulty": data.get("difficulty"),
            "utility": data.get("utility"),
            "security": data.get("security"),
            "turns": turns,
            "labels": {
                "is_attack_case": is_attack,
                "n_benign_calls": 0,
                "n_attack_calls": len(turns),
            },
            "source_file": str(fpath.relative_to(result_dir)),
        }
        records.append(record)

    return records


def build_dataset():
    """Scan all AgentDojo result directories and build the dataset."""

    # Candidate directories with AgentDojo log files
    candidates = [
        ROOT / "benchmarks" / "results_v2" / "agentdojo_slack_gemma_dell" / "logs",
    ]

    # Also check any runs directory
    runs_dir = ROOT / "runs"
    if runs_dir.exists():
        for d in runs_dir.iterdir():
            if d.is_dir():
                candidates.append(d)

    # Check agentdojo_workspace_not_forced path
    adv_path = ROOT / "benchmarks" / "results_v2" / "agentdojo_workspace_not_forced"
    for sub in ["logs", ""]:
        p = adv_path / sub
        if p.exists():
            for d in p.rglob("*.json"):
                candidates.append(d)

    # Fallback to any results_v2 dirs with log structure
    results_v2 = ROOT / "benchmarks" / "results_v2"
    for d in results_v2.iterdir():
        if d.is_dir() and "agentdojo" in d.name.lower() and (d / "logs").exists():
            candidates.append(d / "logs")

    print(f"Scanning {len(candidates)} candidate directories...")
    all_records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for cand in sorted(set(candidates)):
        if not cand.exists():
            continue
        try:
            records = scan_result_directory(cand)
            for rec in records:
                case_id = rec["case_id"]
                if case_id not in seen:
                    seen.add(case_id)
                    all_records.append(rec)
        except Exception as e:
            print(f"  ERROR scanning {cand}: {e}")

    # Write dataset
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, default=str) + "\n")

    # Summary
    total = len(all_records)
    attack_cases = [r for r in all_records if r["labels"]["is_attack_case"]]
    benign_cases = [r for r in all_records if not r["labels"]["is_attack_case"]]
    total_turns = sum(len(r["turns"]) for r in all_records)

    tool_counts: dict[str, int] = {}
    for r in all_records:
        for t in r["turns"]:
            tool_counts[t["tool"]] = tool_counts.get(t["tool"], 0) + 1

    print(f"\nDataset written to: {OUT_PATH}")
    print(f"  Total records: {total}")
    print(f"  Attack cases:  {len(attack_cases)}")
    print(f"  Benign cases:  {len(benign_cases)}")
    print(f"  Total turns:   {total_turns}")
    print(f"\n  Tool call frequency:")
    for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"    {tool}: {count}")

    return all_records


if __name__ == "__main__":
    build_dataset()
