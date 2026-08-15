"""Regenerate parliament/benign_test_set/real_benign_trajectories.json with
REAL tool_output per call, via direct AgentDojo environment dispatch --
same "answer key" method Gate 1 already used successfully for the 8 attack
cases (runtime.run_function() against a loaded environment instance). No
execution, no live agent -- the environment objects are static fixture
data; dispatching a real tool function against them is deterministic.

Session-to-task mapping (all 22 sessions are the banking suite):
    benign\\local\\banking\\user_task_N\\none\\none.json           -> user_task_N
    benign\\local-kavach\\banking\\user_task_N\\none\\none.json     -> user_task_N (duplicate)
    local\\banking\\injection_task_N\\none\\none.json               -> injection_task_N
    local-kavach\\banking\\injection_task_N\\none\\none.json        -> injection_task_N (duplicate)

Calls within a session are dispatched IN ORDER against the SAME
environment instance, so later calls see state changes from earlier
calls in the same session (e.g. a send_money call would appear in a
later get_most_recent_transactions read) -- matches real session
semantics, not independent lookups.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentdojo.task_suite.load_suites import get_suite
from agentdojo.functions_runtime import FunctionsRuntime

FIXTURE_PATH = Path("parliament/benign_test_set/real_benign_trajectories.json")


def _map_source_to_task_id(source_file: str) -> str | None:
    m = re.search(r"(user_task_\d+|injection_task_\d+)", source_file)
    return m.group(1) if m else None


def _stringify_result(result) -> str:
    """Matches the same flattening a real tool-result message would carry
    -- str() on the AgentDojo model/object, same as what a real trajectory's
    'tool' role content would end up being once serialized."""
    if isinstance(result, list):
        return "\n".join(str(r) for r in result)
    return str(result)


def main() -> None:
    suite = get_suite("v1.2", "banking")
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    unmapped: list[str] = []
    dispatch_errors: list[tuple[str, str, str]] = []
    regenerated = 0

    for item in fixture:
        src = item["source_file"]
        task_id = _map_source_to_task_id(src)
        if task_id is None:
            unmapped.append(src)
            continue

        # Fresh environment per SESSION (not per call) -- state accumulates
        # across calls within a session, matching real trajectory semantics.
        env = suite.load_and_inject_default_environment({})
        runtime = FunctionsRuntime(suite.tools)

        session_ok = True
        for call in item["calls"]:
            tool_name = call["tool"]
            args = call["args"]
            try:
                result, error = runtime.run_function(env, tool_name, args)
            except Exception as e:
                dispatch_errors.append((src, tool_name, f"{type(e).__name__}: {e}"))
                call["tool_output"] = None
                session_ok = False
                continue
            if error is not None:
                dispatch_errors.append((src, tool_name, f"tool error: {error}"))
                call["tool_output"] = None
                session_ok = False
                continue
            call["tool_output"] = _stringify_result(result)

        if session_ok:
            regenerated += 1

    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2), encoding="utf-8")

    print(f"Total sessions: {len(fixture)}")
    print(f"Fully regenerated (all calls dispatched cleanly): {regenerated}")
    print(f"Unmapped (no task_id derivable from source_file): {len(unmapped)}")
    for u in unmapped:
        print("  UNMAPPED:", u)
    print(f"Dispatch errors (call succeeded on some calls, failed on others): {len(dispatch_errors)}")
    for src, tool, err in dispatch_errors:
        print(f"  ERROR  {src}  {tool}  ->  {err}")


if __name__ == "__main__":
    main()
