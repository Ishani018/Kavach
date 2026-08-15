"""benchmarks/_agentdojo_full_suite_run.py
==========================================

Full AgentDojo attack-case suite run: ALL injection_task cases across
all 4 suites (banking/travel/workspace/slack), one canonical user_task
per suite -- matching AgentDojo's own standard benchmark convention
(the same pattern _agentdojo_provenance_benchmark.py's CASES_APPLICABLE
already used for its hand-picked 8, just extended to the full 35 real
cases instead of a hand-picked subset).

Unlike _agentdojo_provenance_benchmark.py's CASES_APPLICABLE/
CASES_NO_SOURCE_STEP/CASES_NO_DESTINATION_TOOL (hand-categorized during
tonight's Gate 1 census, only 8 total cases), this script categorizes
EVERY case programmatically at run time using the exact same source/
destination-tool detection channel_taint.py itself uses
(is_source_tool()/is_destination_tool()), so no case is left
uncategorized just because Gate 1 never looked at it by hand.

Report/benchmark task only -- does not commit anything, does not touch
parliament/channel_taint.py or server.py.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentdojo.task_suite.load_suites import get_suite, get_suites
from agentdojo.base_tasks import BaseUserTask
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.functions_runtime import FunctionsRuntime

from parliament.channel_taint import is_source_tool, is_destination_tool

KAVACH_URL = "http://127.0.0.1:8088"
_RUN_TAG = str(int(time.time()))

ALL_SUITES = sorted(get_suites("v1.2").keys())


class _StubPipeline:
    name = "local"


def _post_parliament(text: str, session_id: str, context: dict) -> dict:
    payload = json.dumps({"text": text, "session_id": session_id, "context": context}).encode("utf-8")
    req = urllib.request.Request(
        f"{KAVACH_URL}/hook/parliament", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _format_tool_call(function: str, args: dict) -> str:
    args_str = json.dumps(args, default=str, ensure_ascii=False)
    return f"tool:{function} args:{args_str}"


def _stringify_result(result) -> str:
    if isinstance(result, list):
        return "\n".join(str(r) for r in result)
    return str(result)


def list_all_injection_tasks(suite_name: str) -> list[str]:
    suite = get_suite("v1.2", suite_name)
    return sorted(suite._injection_tasks.keys(), key=lambda s: (len(s), s))


def run_case(suite_name: str, injection_task_id: str) -> dict:
    suite = get_suite("v1.2", suite_name)
    ut_ids = list(suite.user_tasks.keys())
    ut = suite.user_tasks[ut_ids[0]]
    it_versions = suite._injection_tasks[injection_task_id]
    it = it_versions[list(it_versions.keys())[0]]

    attacker = ImportantInstructionsAttack(suite, _StubPipeline())
    injections = attacker.attack(ut, it)
    env = suite.load_and_inject_default_environment(injections)
    task_env = ut.init_environment(env) if isinstance(ut, BaseUserTask) else env

    try:
        gt = list(it.ground_truth(task_env))
    except Exception as e:
        return {"suite": suite_name, "injection_task": injection_task_id, "error": f"ground_truth() failed: {e}"}

    # Categorize programmatically -- same detection logic channel_taint.py
    # itself uses, not a hand-picked label.
    has_source_step = any(is_source_tool(fc.function) for fc in gt)
    has_destination_tool = any(is_destination_tool(fc.function) for fc in gt)
    if has_source_step and has_destination_tool:
        category = "applicable"
    elif not has_source_step and has_destination_tool:
        category = "no_source_step"
    elif has_source_step and not has_destination_tool:
        category = "no_destination_tool"
    else:
        category = "neither"

    session_id = f"gt-fullsuite-{_RUN_TAG}-{suite_name}-{injection_task_id}"
    user_instruction = getattr(ut, "PROMPT", None) or ""
    runtime = FunctionsRuntime(suite.tools)
    steps = []
    for i, fc in enumerate(gt):
        text = _format_tool_call(fc.function, dict(fc.args))
        try:
            result, error = runtime.run_function(task_env, fc.function, dict(fc.args))
            tool_output = None if error is not None else _stringify_result(result)
        except Exception:
            tool_output = None
        context = {
            "source": "agentdojo-full-suite-run",
            "call_n": i,
            "user_instruction": user_instruction,
            "tool_output": tool_output,
        }
        resp = _post_parliament(text, session_id, context)
        ministers = resp.get("ministers", {})
        ch = ministers.get("CHANNEL", {})
        step = {
            "step": i,
            "function": fc.function,
            "verdict": resp.get("verdict"),
            "decided_by": resp.get("speaker", {}).get("decided_by"),
            "channel_verdict": ch.get("verdict"),
            "channel_matched_id": ch.get("matched_id"),
        }
        steps.append(step)
        if resp.get("verdict") == "BLOCK":
            break

    channel_fired = any(s["channel_verdict"] == "ESCALATE" for s in steps)
    return {
        "suite": suite_name,
        "injection_task": injection_task_id,
        "category": category,
        "has_source_step": has_source_step,
        "has_destination_tool": has_destination_tool,
        "n_steps": len(gt),
        "final_verdict": steps[-1]["verdict"] if steps else None,
        "final_decided_by": steps[-1]["decided_by"] if steps else None,
        "channel_fired": channel_fired,
        "steps": steps,
    }


def main() -> None:
    all_results = []
    for suite_name in ALL_SUITES:
        injection_ids = list_all_injection_tasks(suite_name)
        print(f"=== {suite_name}: {len(injection_ids)} injection tasks ===", file=sys.stderr)
        for it_id in injection_ids:
            r = run_case(suite_name, it_id)
            all_results.append(r)
            print(f"  {suite_name}::{it_id}: category={r.get('category')} "
                  f"final_verdict={r.get('final_verdict')} decided_by={r.get('final_decided_by')} "
                  f"channel_fired={r.get('channel_fired')}", file=sys.stderr)

    print(json.dumps(all_results, indent=2))

    # Summary by category
    by_cat: dict[str, list[dict]] = {}
    for r in all_results:
        by_cat.setdefault(r.get("category", "error"), []).append(r)

    print("\n" + "=" * 70, file=sys.stderr)
    print("SUMMARY", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    for cat, rows in sorted(by_cat.items()):
        n = len(rows)
        n_channel = sum(1 for r in rows if r.get("channel_fired"))
        n_navigator_or_traj = sum(
            1 for r in rows
            if r.get("final_verdict") in ("BLOCK", "ESCALATE") and not r.get("channel_fired")
        )
        print(f"{cat}: n={n} channel_escalate={n_channel} navigator/traj_only={n_navigator_or_traj}", file=sys.stderr)


if __name__ == "__main__":
    main()
